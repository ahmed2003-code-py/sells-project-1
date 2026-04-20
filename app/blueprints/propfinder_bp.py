"""
PropFinder blueprint — real estate units API
Gracefully handles missing `units` table (returns empty data instead of crashing).
"""
import json
import logging
import threading
import psycopg2
import psycopg2.extras
from decimal import Decimal
from flask import Blueprint, jsonify, Response
from app.database import get_conn, table_exists
from app.auth import login_required
from config import Config

log = logging.getLogger(__name__)
propfinder_bp = Blueprint("propfinder", __name__, url_prefix="/api")


def _json_serial(obj):
    if isinstance(obj, Decimal):
        val = float(obj)
        if val != val:
            return None
        return val
    raise TypeError(f"Type {type(obj)} not serializable")


def _json_response(data, status=200):
    return Response(
        json.dumps(data, default=_json_serial, allow_nan=False),
        status=status,
        mimetype="application/json"
    )


def _get_sync_status():
    """Lazy import: sync_status dict exists only if sync_service has been imported"""
    try:
        from app.sync_service import sync_status
        return sync_status
    except Exception:
        return {
            "running": False, "last_run": None,
            "last_result": "Sync disabled", "error": None
        }


@propfinder_bp.route("/health")
def health():
    return _json_response({
        "status": "ok",
        "sync_enabled": not Config.DISABLE_SYNC,
        "sync": _get_sync_status(),
    })


@propfinder_bp.route("/units")
@login_required
def get_units():
    try:
        conn = get_conn()
        try:
            if not table_exists(conn, "units"):
                return _json_response([])

            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT
                        city_name, compound_name, compound_id,
                        developer_name, developer_id,
                        phase_name, phase_id, unit_type,
                        bedrooms,
                        NULLIF(CAST(built_up_area_sqm AS FLOAT), 'NaN') AS built_up_area_sqm,
                        NULLIF(CAST(total_price_egp AS FLOAT), 'NaN') AS total_price_egp,
                        NULLIF(CAST(price_per_sqm_egp AS FLOAT), 'NaN') AS price_per_sqm_egp,
                        NULLIF(CAST(cash_price_from_egp AS FLOAT), 'NaN') AS cash_price_from_egp,
                        NULLIF(CAST(cash_price_to_egp AS FLOAT), 'NaN') AS cash_price_to_egp,
                        delivery_from_months, delivery_to_months,
                        payment_plan, maintenance, club_fees,
                        parking_fees, finishing_type,
                        NULLIF(CAST(cash_discount_percent AS FLOAT), 'NaN') AS cash_discount_percent,
                        city_id, detail_id, outdoor_area, status, sub_type,
                        NULLIF(CAST(total_price_to_egp AS FLOAT), 'NaN') AS total_price_to_egp,
                        type_id,
                        COALESCE(is_sold, false) AS is_sold
                    FROM units
                    ORDER BY detail_id ASC
                """)
                rows = cur.fetchall()
        finally:
            conn.close()

        cleaned = []
        for row in rows:
            d = dict(row)
            for k, v in d.items():
                if isinstance(v, float) and v != v:
                    d[k] = None
            cleaned.append(d)
        return _json_response(cleaned)
    except Exception as e:
        log.error(f"Error fetching units: {e}")
        return _json_response({"error": str(e)}, 500)


@propfinder_bp.route("/stats")
@login_required
def get_stats():
    try:
        conn = get_conn()
        try:
            if not table_exists(conn, "units"):
                return _json_response({
                    "total": 0, "sold": 0, "compounds": 0,
                    "avg_price": None, "min_price": None, "max_price": None
                })

            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT
                        COUNT(*) AS total,
                        COUNT(CASE WHEN is_sold = true OR status = 0 THEN 1 END) AS sold,
                        AVG(CAST(total_price_egp AS FLOAT)) AS avg_price,
                        MIN(CAST(total_price_egp AS FLOAT)) AS min_price,
                        MAX(CAST(total_price_egp AS FLOAT)) AS max_price,
                        COUNT(DISTINCT compound_name) AS compounds
                    FROM units
                """)
                stats = dict(cur.fetchone())
        finally:
            conn.close()
        return _json_response(stats)
    except Exception as e:
        log.error(f"Stats error: {e}")
        return _json_response({"error": str(e)}, 500)


@propfinder_bp.route("/sync/status")
@login_required
def sync_status_route():
    return _json_response({
        "enabled": not Config.DISABLE_SYNC,
        **_get_sync_status()
    })


@propfinder_bp.route("/sync/trigger", methods=["POST"])
@login_required
def trigger_sync():
    if Config.DISABLE_SYNC:
        return _json_response({"error": "Sync is disabled (DISABLE_SYNC=true)"}, 400)
    try:
        from app.sync_service import run_sync, sync_status
    except Exception as e:
        return _json_response({"error": f"Sync unavailable: {e}"}, 500)
    if sync_status["running"]:
        return _json_response({"message": "Sync already running"}, 409)
    t = threading.Thread(target=run_sync, daemon=True)
    t.start()
    return _json_response({"message": "Sync triggered"})


@propfinder_bp.route("/reset-sold", methods=["POST"])
@login_required
def reset_sold():
    try:
        conn = get_conn()
        try:
            if not table_exists(conn, "units"):
                return _json_response({"error": "units table does not exist"}, 404)
            with conn.cursor() as cur:
                cur.execute("UPDATE units SET is_sold = FALSE, sold_at = NULL")
                affected = cur.rowcount
            conn.commit()
        finally:
            conn.close()
        return _json_response({"message": f"Reset {affected} units"})
    except Exception as e:
        return _json_response({"error": str(e)}, 500)
