"""
Authentication blueprint — login, logout, register, change-password,
forgot-password + reset flow. All error responses use structured
{error_code} payloads; frontend maps them to localized text.
"""
import hashlib
import logging
import secrets
from datetime import datetime, timedelta

import psycopg2
import psycopg2.extras
from flask import Blueprint, current_app, jsonify, request, session

from app.auth import (
    current_user,
    ensure_csrf_token,
    error_response,
    hash_password,
    login_required,
    needs_rehash,
    rate_limit,
    rate_limit_reset,
    role_home,
    validate_email,
    validate_password,
    validate_phone,
    validate_username,
    verify_password,
)
from app.database import get_conn
from app.mailer import password_reset_email, send_mail
from config import Config

log = logging.getLogger(__name__)
auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


# ─── Helpers ───────────────────────────────────────────────────────────────

def _hash_token(tok: str) -> str:
    return hashlib.sha256(tok.encode("utf-8")).hexdigest()


def _client_ip() -> str:
    return (
        request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        or request.remote_addr
        or ""
    )


def _reset_base_url() -> str:
    if Config.APP_BASE_URL:
        return Config.APP_BASE_URL
    return request.url_root.rstrip("/")


# ─── Login ─────────────────────────────────────────────────────────────────

@auth_bp.route("/login", methods=["POST"])
@rate_limit("login", limit=8, window=60)
def login():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip().lower()
    password = data.get("password") or ""
    if not username or not password:
        return error_response("required_fields_missing", 400)

    conn = None
    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT id, username, full_name, password_hash, role, active, email,
                       failed_logins, locked_until
                FROM users WHERE LOWER(username) = %s
            """, (username,))
            user = cur.fetchone()

            # Constant-ish path to avoid username enumeration
            valid = bool(
                user
                and user["active"]
                and (not user.get("locked_until") or user["locked_until"] < datetime.utcnow())
                and verify_password(password, user["password_hash"])
            )

            if not valid:
                if user and user["active"]:
                    # Track failures; soft-lock at 10
                    fails = (user.get("failed_logins") or 0) + 1
                    locked = None
                    if fails >= 10:
                        locked = datetime.utcnow() + timedelta(minutes=15)
                        fails = 0
                    cur.execute(
                        "UPDATE users SET failed_logins = %s, locked_until = %s WHERE id = %s",
                        (fails, locked, user["id"]),
                    )
                    conn.commit()
                return error_response("invalid_credentials", 401)

            # Success — rotate session, transparently upgrade legacy hash
            if needs_rehash(user["password_hash"]):
                cur.execute(
                    "UPDATE users SET password_hash = %s WHERE id = %s",
                    (hash_password(password), user["id"]),
                )
            cur.execute(
                "UPDATE users SET last_login = NOW(), failed_logins = 0, locked_until = NULL WHERE id = %s",
                (user["id"],),
            )
        conn.commit()

        session.clear()
        session["user_id"] = user["id"]
        session["username"] = user["username"]
        session["full_name"] = user["full_name"]
        session["role"] = user["role"]
        session.permanent = True
        ensure_csrf_token()
        rate_limit_reset("login")

        log.info("✅ Login: %s (%s)", username, user["role"])
        return jsonify({
            "id": user["id"],
            "username": user["username"],
            "full_name": user["full_name"],
            "role": user["role"],
            "redirect": role_home(user["role"]),
        })
    except Exception as e:
        log.error("Login error: %s", e)
        return error_response("server", 500)
    finally:
        if conn:
            conn.close()


# Self-registration is disabled — accounts are admin-created only. The endpoint
# is kept as a 404 stub so external callers get a clean, enumeration-safe response.
@auth_bp.route("/register", methods=["POST"])
def register():
    return error_response("not_found", 404)


# ─── Session endpoints ─────────────────────────────────────────────────────

@auth_bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"ok": True})


@auth_bp.route("/me")
def me():
    u = current_user()
    if not u:
        return error_response("unauthorized", 401)
    u["csrf"] = ensure_csrf_token()
    return jsonify(u)


@auth_bp.route("/csrf", methods=["GET"])
@login_required
def csrf():
    return jsonify({"csrf": ensure_csrf_token()})


# ─── Change password ───────────────────────────────────────────────────────

@auth_bp.route("/change-password", methods=["POST"])
@login_required
def change_password():
    data = request.get_json(silent=True) or {}
    old_pw = data.get("old_password") or ""
    new_pw = data.get("new_password") or ""
    username = session.get("username") or ""

    if (err := validate_password(new_pw, username=username)):
        return error_response(err, 400)

    conn = None
    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT password_hash FROM users WHERE id = %s", (session["user_id"],))
            row = cur.fetchone()
            if not row or not verify_password(old_pw, row["password_hash"]):
                return error_response("wrong_current_password", 401)
            cur.execute("""
                UPDATE users SET password_hash = %s, updated_at = NOW() WHERE id = %s
            """, (hash_password(new_pw), session["user_id"]))
        conn.commit()
        return jsonify({"ok": True})
    except Exception as e:
        log.error("change-password error: %s", e)
        return error_response("server", 500)
    finally:
        if conn:
            conn.close()


# ─── Forgot password ───────────────────────────────────────────────────────

@auth_bp.route("/forgot-password", methods=["POST"])
@rate_limit("forgot", limit=5, window=600)
def forgot_password():
    """Always respond 200 to prevent email enumeration. If the email exists
    and SMTP is configured, a reset link is emailed."""
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    if not email or validate_email(email, required=True):
        # Still return OK to avoid enumeration
        return jsonify({"ok": True})

    conn = None
    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT id, full_name, active FROM users WHERE LOWER(email) = %s
            """, (email,))
            user = cur.fetchone()

            if user and user["active"]:
                # Invalidate previous unused tokens for this user
                cur.execute(
                    "UPDATE password_reset_tokens SET used_at = NOW() "
                    "WHERE user_id = %s AND used_at IS NULL",
                    (user["id"],),
                )

                raw_token = secrets.token_urlsafe(32)
                token_hash = _hash_token(raw_token)
                expires = datetime.utcnow() + timedelta(minutes=Config.PASSWORD_RESET_TTL_MINUTES)
                cur.execute("""
                    INSERT INTO password_reset_tokens (user_id, token_hash, expires_at, created_ip)
                    VALUES (%s, %s, %s, %s)
                """, (user["id"], token_hash, expires, _client_ip()[:64]))
                conn.commit()

                reset_url = f"{_reset_base_url()}/reset-password?token={raw_token}"
                subject, text, html = password_reset_email(
                    user["full_name"] or "",
                    reset_url,
                    Config.PASSWORD_RESET_TTL_MINUTES,
                )
                send_mail(email, subject, text, html)
    except Exception as e:
        log.error("forgot-password error: %s", e)
    finally:
        if conn:
            conn.close()

    return jsonify({"ok": True})


@auth_bp.route("/reset-password", methods=["POST"])
@rate_limit("reset", limit=10, window=600)
def reset_password():
    data = request.get_json(silent=True) or {}
    token = (data.get("token") or "").strip()
    new_pw = data.get("new_password") or ""

    if not token or len(token) < 16:
        return error_response("invalid_token", 400)

    token_hash = _hash_token(token)

    conn = None
    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT t.id AS token_id, t.user_id, t.expires_at, t.used_at,
                       u.username, u.active
                FROM password_reset_tokens t
                JOIN users u ON u.id = t.user_id
                WHERE t.token_hash = %s
            """, (token_hash,))
            row = cur.fetchone()
            if not row or not row["active"] or row["used_at"] is not None:
                return error_response("invalid_token", 400)
            if row["expires_at"] < datetime.utcnow():
                return error_response("token_expired", 400)

            if (err := validate_password(new_pw, username=row["username"])):
                return error_response(err, 400)

            cur.execute(
                "UPDATE users SET password_hash = %s, failed_logins = 0, "
                "locked_until = NULL, updated_at = NOW() WHERE id = %s",
                (hash_password(new_pw), row["user_id"]),
            )
            cur.execute(
                "UPDATE password_reset_tokens SET used_at = NOW() WHERE id = %s",
                (row["token_id"],),
            )
        conn.commit()
        return jsonify({"ok": True})
    except Exception as e:
        log.error("reset-password error: %s", e)
        return error_response("server", 500)
    finally:
        if conn:
            conn.close()


@auth_bp.route("/reset-password/validate", methods=["GET"])
def validate_reset_token():
    token = (request.args.get("token") or "").strip()
    if not token or len(token) < 16:
        return jsonify({"valid": False})
    token_hash = _hash_token(token)
    conn = None
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT expires_at, used_at
                FROM password_reset_tokens WHERE token_hash = %s
            """, (token_hash,))
            row = cur.fetchone()
            if not row:
                return jsonify({"valid": False})
            expires_at, used_at = row
            if used_at is not None:
                return jsonify({"valid": False})
            if expires_at < datetime.utcnow():
                return jsonify({"valid": False, "reason": "expired"})
            return jsonify({"valid": True})
    except Exception as e:
        log.error("validate_reset_token: %s", e)
        return jsonify({"valid": False})
    finally:
        if conn:
            conn.close()
