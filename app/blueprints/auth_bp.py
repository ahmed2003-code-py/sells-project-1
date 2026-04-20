"""
Authentication blueprint: login, logout, register, change password
"""
import logging
import psycopg2
import psycopg2.extras
from flask import Blueprint, request, jsonify, session
from app.database import get_conn
from app.auth import hash_password, verify_password, login_required, role_home

log = logging.getLogger(__name__)
auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json() or {}
    username = data.get("username", "").strip().lower()
    password = data.get("password", "")
    if not username or not password:
        return jsonify({"error": "اسم المستخدم وكلمة المرور مطلوبان"}), 400

    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT id, username, full_name, password_hash, role, active
                FROM users WHERE LOWER(username) = %s
            """, (username,))
            user = cur.fetchone()

            if not user or not user["active"]:
                return jsonify({"error": "بيانات الدخول غير صحيحة"}), 401
            if not verify_password(password, user["password_hash"]):
                return jsonify({"error": "بيانات الدخول غير صحيحة"}), 401

            cur.execute("UPDATE users SET last_login = NOW() WHERE id = %s", (user["id"],))
        conn.commit()
        conn.close()

        session.clear()
        session["user_id"] = user["id"]
        session["username"] = user["username"]
        session["full_name"] = user["full_name"]
        session["role"] = user["role"]
        session.permanent = True

        log.info(f"✅ Login: {username} ({user['role']})")
        return jsonify({
            "id": user["id"],
            "username": user["username"],
            "full_name": user["full_name"],
            "role": user["role"],
            "redirect": role_home(user["role"])
        })
    except Exception as e:
        log.error(f"Login error: {e}")
        return jsonify({"error": "حدث خطأ في الخادم"}), 500


@auth_bp.route("/register", methods=["POST"])
def register():
    """Self-registration (creates Sales role by default)"""
    data = request.get_json() or {}
    username = data.get("username", "").strip().lower()
    full_name = data.get("full_name", "").strip()
    password = data.get("password", "")
    email = data.get("email", "").strip() or None
    phone = data.get("phone", "").strip() or None

    if not username or not full_name or not password:
        return jsonify({"error": "كل الحقول مطلوبة"}), 400
    if len(password) < 4:
        return jsonify({"error": "كلمة المرور يجب أن تكون 4 أحرف على الأقل"}), 400
    if len(username) < 3:
        return jsonify({"error": "اسم المستخدم يجب أن يكون 3 أحرف على الأقل"}), 400

    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO users (username, full_name, password_hash, role, email, phone, active)
                VALUES (%s, %s, %s, 'sales', %s, %s, true)
                RETURNING id
            """, (username, full_name, hash_password(password), email, phone))
            new_id = cur.fetchone()[0]
        conn.commit()
        conn.close()
        log.info(f"✅ Self-register: {username}")
        return jsonify({"id": new_id, "message": "تم إنشاء الحساب بنجاح"})
    except psycopg2.IntegrityError:
        return jsonify({"error": "اسم المستخدم موجود بالفعل"}), 409
    except Exception as e:
        log.error(f"Register error: {e}")
        return jsonify({"error": "حدث خطأ في الخادم"}), 500


@auth_bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"message": "تم تسجيل الخروج"})


@auth_bp.route("/me")
def me():
    if "user_id" not in session:
        return jsonify({"error": "Not authenticated"}), 401
    return jsonify({
        "id": session["user_id"],
        "username": session["username"],
        "full_name": session["full_name"],
        "role": session["role"],
    })


@auth_bp.route("/change-password", methods=["POST"])
@login_required
def change_password():
    data = request.get_json() or {}
    old_pw = data.get("old_password", "")
    new_pw = data.get("new_password", "")
    if len(new_pw) < 4:
        return jsonify({"error": "كلمة المرور الجديدة يجب أن تكون 4 أحرف على الأقل"}), 400

    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT password_hash FROM users WHERE id = %s", (session["user_id"],))
            row = cur.fetchone()
            if not row or not verify_password(old_pw, row["password_hash"]):
                return jsonify({"error": "كلمة المرور الحالية غير صحيحة"}), 401
            cur.execute("""
                UPDATE users SET password_hash = %s, updated_at = NOW() WHERE id = %s
            """, (hash_password(new_pw), session["user_id"]))
        conn.commit()
        conn.close()
        return jsonify({"message": "تم تغيير كلمة المرور"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
