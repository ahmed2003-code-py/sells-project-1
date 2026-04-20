"""
Configuration for Ain KPI System
"""
import os
import secrets
from datetime import timedelta


def _get_secret_key():
    """Load SECRET_KEY from env. If not set, generate ephemeral key.
    WARNING: on Railway, set SECRET_KEY env var so sessions survive restarts."""
    key = os.environ.get("SECRET_KEY")
    if key and len(key) >= 16:
        return key
    return secrets.token_hex(32)


class Config:
    SECRET_KEY = _get_secret_key()
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = False  # Railway proxies HTTPS at the edge; cookies still secure

    # Database — Railway provides DATABASE_URL automatically
    DATABASE_URL = os.environ.get("DATABASE_URL")

    # Fallback to individual settings if DATABASE_URL is not set
    DB_HOST = os.environ.get("DB_HOST", "caboose.proxy.rlwy.net")
    DB_PORT = int(os.environ.get("DB_PORT", 21778))
    DB_NAME = os.environ.get("DB_NAME", "railway")
    DB_USER = os.environ.get("DB_USER", "postgres")
    DB_PASSWORD = os.environ.get("DB_PASSWORD", "AdPVLYioZHOYsrpSswoILIvpkHwIReTz")

    # Master V API (only used if sync not disabled)
    MASTER_V_URL = "https://newapi.masterv.net/api/v3/public"
    MASTER_V_TOKEN = os.environ.get(
        "MASTER_V_TOKEN",
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJVc2VySWQiOjMyMTksIlVzZXJFbWFpbCI6Im1vaGFtZWRoYW16YTEzMDNAZ21haWwuY29tIiwiVXNlclBob25lTnVtYmVyIjoiMjAxMDk5MjQ5NDk5IiwiSXNDbGllbnQiOnRydWUsImlhdCI6MTc3MTQyNjgwOCwiZXhwIjoxNzc0MDE4ODA4fQ.S9I6GS6gk96R8BkZwyLP0JNUic7jwwVTzJtjTdt7nkI"
    )

    # Default admin credentials (only used on first run if users table is empty)
    DEFAULT_ADMIN_USER = os.environ.get("DEFAULT_ADMIN_USER", "admin")
    DEFAULT_ADMIN_PASSWORD = os.environ.get("DEFAULT_ADMIN_PASSWORD", "admin123")

    # Sync control
    DISABLE_SYNC = os.environ.get("DISABLE_SYNC", "false").lower() == "true"
