"""
Users management blueprint — admin-only CRUD for users
"""
import logging
import psycopg2
import psycopg2.extras
from flask import Blueprint, request, jsonify
from app.database import get_conn
from app.auth import hash_password, role_required, ROLES

log = logging.getLogger(__name__)
users_bp = Blueprint("users", __name__, url_prefix="/api/users")


def _user_to_dict(row):
    d = dict(row)
    for k in ["created_at", "updated_at", "last_login"]:
        if d.get(k):
            d[k] = d[k].isoformat()
    d.pop("password_hash", None)
    return d


@users_bp.route("", methods=["GET"])
@role_required("admin", "manager", "dataentry")
def list_users():
    role_filter = request.args.get("role")
    active_only = request.args.get("active_only") == "true"
    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            q = """SELECT id, username, full_name, role, email, phone, active,
                          created_at, updated_at, last_login
                   FROM users WHERE 1=1"""
            params = []
            if role_filter:
                q += " AND role = %s"
                params.append(role_filter)
            if active_only:
                q += " AND active = true"
            q += " ORDER BY role DESC, full_name ASC"
            cur.execute(q, params)
            users = [_user_to_dict(r) for r in cur.fetchall()]
        conn.close()
        return jsonify(users)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@users_bp.route("/<int:user_id>", methods=["GET"])
@role_required("admin", "manager")
def get_user(user_id):
    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT id, username, full_name, role, email, phone, active,
                       created_at, updated_at, last_login
                FROM users WHERE id = %s
            """, (user_id,))
            row = cur.fetchone()
        conn.close()
        if not row:
            return jsonify({"error": "User not found"}), 404
        return jsonify(_user_to_dict(row))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@users_bp.route("", methods=["POST"])
@role_required("admin")
def create_user():
    data = request.get_json() or {}
    username = data.get("username", "").strip().lower()
    full_name = data.get("full_name", "").strip()
    password = data.get("password", "")
    role = data.get("role", "sales")
    email = data.get("email", "").strip() or None
    phone = data.get("phone", "").strip() or None

    if not username or not full_name or not password:
        return jsonify({"error": "اسم المستخدم والاسم الكامل وكلمة المرور مطلوبة"}), 400
    if role not in ROLES:
        return jsonify({"error": "الدور غير صحيح"}), 400
    if len(password) < 4:
        return jsonify({"error": "كلمة المرور يجب أن تكون 4 أحرف على الأقل"}), 400

    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO users (username, full_name, password_hash, role, email, phone)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (username, full_name, hash_password(password), role, email, phone))
            new_id = cur.fetchone()[0]
        conn.commit()
        conn.close()
        log.info(f"✅ User created: {username} ({role})")
        return jsonify({"id": new_id, "message": "تم إنشاء المستخدم"}), 201
    except psycopg2.IntegrityError:
        return jsonify({"error": "اسم المستخدم موجود بالفعل"}), 409
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@users_bp.route("/<int:user_id>", methods=["PUT"])
@role_required("admin")
def update_user(user_id):
    data = request.get_json() or {}
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            fields = []
            params = []
            for f in ["full_name", "role", "email", "phone", "active"]:
                if f in data:
                    fields.append(f"{f} = %s")
                    params.append(data[f])
            if data.get("password"):
                if len(data["password"]) < 4:
                    return jsonify({"error": "كلمة المرور يجب أن تكون 4 أحرف على الأقل"}), 400
                fields.append("password_hash = %s")
                params.append(hash_password(data["password"]))
            if not fields:
                return jsonify({"error": "لا يوجد تعديلات"}), 400
            fields.append("updated_at = NOW()")
            params.append(user_id)
            cur.execute(f"UPDATE users SET {', '.join(fields)} WHERE id = %s", params)
            if cur.rowcount == 0:
                return jsonify({"error": "المستخدم غير موجود"}), 404
        conn.commit()
        conn.close()
        log.info(f"✅ User {user_id} updated")
        return jsonify({"message": "تم التحديث"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@users_bp.route("/<int:user_id>", methods=["DELETE"])
@role_required("admin")
def delete_user(user_id):
    """Hard delete — removes user and all their KPI entries (CASCADE)"""
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute("SELECT role FROM users WHERE id = %s", (user_id,))
            row = cur.fetchone()
            if not row:
                return jsonify({"error": "المستخدم غير موجود"}), 404
            if row[0] == "admin":
                cur.execute("SELECT COUNT(*) FROM users WHERE role = 'admin' AND active = true")
                if cur.fetchone()[0] <= 1:
                    return jsonify({"error": "لا يمكن حذف آخر مدير للنظام"}), 400

            cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
        conn.commit()
        conn.close()
        log.info(f"✅ User {user_id} deleted")
        return jsonify({"message": "تم الحذف"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@users_bp.route("/<int:user_id>/deactivate", methods=["POST"])
@role_required("admin")
def deactivate_user(user_id):
    """Soft delete — keeps data but disables login"""
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET active = false, updated_at = NOW() WHERE id = %s", (user_id,))
            if cur.rowcount == 0:
                return jsonify({"error": "المستخدم غير موجود"}), 404
        conn.commit()
        conn.close()
        return jsonify({"message": "تم تعطيل المستخدم"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@users_bp.route("/<int:user_id>/activate", methods=["POST"])
@role_required("admin")
def activate_user(user_id):
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET active = true, updated_at = NOW() WHERE id = %s", (user_id,))
            if cur.rowcount == 0:
                return jsonify({"error": "المستخدم غير موجود"}), 404
        conn.commit()
        conn.close()
        return jsonify({"message": "تم تفعيل المستخدم"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
