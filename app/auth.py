"""
Authentication helpers: password hashing, decorators, role checks
"""
import hashlib
from functools import wraps
from flask import request, jsonify, session, redirect


# Role hierarchy used by the system
ROLES = ["admin", "manager", "team_leader", "dataentry", "sales", "marketing"]


def hash_password(password: str) -> str:
    salt = "ain_kpi_2026_salt"
    return hashlib.sha256((password + salt).encode()).hexdigest()


def verify_password(password: str, hashed: str) -> bool:
    return hash_password(password) == hashed


def current_user():
    if "user_id" not in session:
        return None
    return {
        "id": session.get("user_id"),
        "username": session.get("username"),
        "full_name": session.get("full_name"),
        "role": session.get("role"),
    }


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            if request.path.startswith("/api/"):
                return jsonify({"error": "Not authenticated"}), 401
            return redirect("/login")
        return f(*args, **kwargs)
    return wrapper


def role_required(*allowed_roles):
    """Admin always passes. Otherwise must be in allowed_roles."""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if "user_id" not in session:
                if request.path.startswith("/api/"):
                    return jsonify({"error": "Not authenticated"}), 401
                return redirect("/login")
            user_role = session.get("role")
            if user_role != "admin" and user_role not in allowed_roles:
                if request.path.startswith("/api/"):
                    return jsonify({"error": "Forbidden"}), 403
                return redirect("/")
            return f(*args, **kwargs)
        return wrapper
    return decorator


def role_home(role: str) -> str:
    return {
        "admin": "/admin",
        "manager": "/dashboard",
        "team_leader": "/team-leader",
        "dataentry": "/data-entry",
        "sales": "/sales",
        "marketing": "/marketing",
    }.get(role, "/dashboard")
