"""
Database: connection + schema initialization

IMPORTANT: This module ONLY creates the KPI-related tables (users, kpi_entries).
The `units` table already exists from the PropFinder sync service — we don't
touch its schema to avoid conflicts.
"""
import logging
import time
import psycopg2
import psycopg2.extras
from config import Config

log = logging.getLogger(__name__)


def get_conn(retries=2):
    """Get a fresh PostgreSQL connection with simple retry on transient failures."""
    last_err = None
    for attempt in range(retries + 1):
        try:
            if Config.DATABASE_URL:
                return psycopg2.connect(Config.DATABASE_URL, connect_timeout=10)
            return psycopg2.connect(
                host=Config.DB_HOST,
                port=Config.DB_PORT,
                database=Config.DB_NAME,
                user=Config.DB_USER,
                password=Config.DB_PASSWORD,
                connect_timeout=10
            )
        except psycopg2.OperationalError as e:
            last_err = e
            if attempt < retries:
                time.sleep(1)
                continue
            raise
    raise last_err


def table_exists(conn, table_name: str) -> bool:
    """Check if a table exists in the database"""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = %s
            )
        """, (table_name,))
        return cur.fetchone()[0]


def init_all_tables():
    """Create KPI-related tables if they don't exist. Leaves `units` table alone."""
    conn = None
    try:
        conn = get_conn()

        with conn.cursor() as cur:
            # ─── Users table ──────────────────────────────────────────────────
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    username VARCHAR(100) NOT NULL UNIQUE,
                    full_name VARCHAR(150) NOT NULL,
                    password_hash VARCHAR(255) NOT NULL,
                    role VARCHAR(20) NOT NULL DEFAULT 'sales',
                    email VARCHAR(150),
                    phone VARCHAR(30),
                    active BOOLEAN DEFAULT true,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW(),
                    last_login TIMESTAMP
                );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(LOWER(username));")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);")

            # ─── KPI entries table ────────────────────────────────────────────
            cur.execute("""
                CREATE TABLE IF NOT EXISTS kpi_entries (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    month VARCHAR(7) NOT NULL,

                    fresh_leads INTEGER DEFAULT 0,
                    calls INTEGER DEFAULT 0,
                    meetings INTEGER DEFAULT 0,
                    crm_pct NUMERIC(5,2) DEFAULT 0,
                    deals INTEGER DEFAULT 0,
                    reports INTEGER DEFAULT 0,
                    reservations INTEGER DEFAULT 0,
                    followup_pct NUMERIC(5,2) DEFAULT 0,
                    attendance_pct NUMERIC(5,2) DEFAULT 0,
                    sales_submitted_at TIMESTAMP,

                    attitude INTEGER DEFAULT 0,
                    presentation INTEGER DEFAULT 0,
                    behaviour INTEGER DEFAULT 0,
                    appearance INTEGER DEFAULT 0,
                    hr_roles INTEGER DEFAULT 0,
                    dataentry_submitted_at TIMESTAMP,
                    dataentry_by INTEGER REFERENCES users(id) ON DELETE SET NULL,

                    notes TEXT,
                    total_score NUMERIC(5,2) DEFAULT 0,
                    rating VARCHAR(20) DEFAULT 'Pending',

                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW(),

                    UNIQUE(user_id, month)
                );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_kpi_user_month ON kpi_entries(user_id, month);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_kpi_month ON kpi_entries(month);")

        conn.commit()
        log.info("✅ Users & KPI tables ensured")

        # ─── Create default admin if no users exist ─────────────────────────
        from app.auth import hash_password
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM users")
            count = cur.fetchone()[0]
            if count == 0:
                cur.execute("""
                    INSERT INTO users (username, full_name, password_hash, role)
                    VALUES (%s, %s, %s, 'admin')
                """, (
                    Config.DEFAULT_ADMIN_USER,
                    "System Administrator",
                    hash_password(Config.DEFAULT_ADMIN_PASSWORD)
                ))
                conn.commit()
                log.info(f"✅ Default admin created: {Config.DEFAULT_ADMIN_USER} / {Config.DEFAULT_ADMIN_PASSWORD}")
                log.warning("⚠️  Change the default admin password immediately after first login!")
            else:
                log.info(f"📋 Users table already has {count} user(s) — skipping default admin creation")

        # ─── Check units table (from PropFinder) ────────────────────────────
        if table_exists(conn, "units"):
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM units")
                units_count = cur.fetchone()[0]
                log.info(f"📦 Found existing `units` table with {units_count:,} rows (from PropFinder)")
        else:
            log.info("ℹ️  No `units` table found — PropFinder page will show empty state")

    except Exception as e:
        log.error(f"❌ DB init error: {e}")
        # Don't raise — let the app start even if init has issues;
        # routes will report errors individually
    finally:
        if conn:
            conn.close()
