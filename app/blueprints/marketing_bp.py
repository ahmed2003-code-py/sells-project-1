"""
Marketing blueprint — campaign CRUD + actuals tracking
"""
import logging
import json
import psycopg2.extras
from decimal import Decimal
from datetime import datetime, date
from flask import Blueprint, request, session, Response
from app.database import get_conn
from app.auth import login_required, role_required

log = logging.getLogger(__name__)
marketing_bp = Blueprint("marketing", __name__, url_prefix="/api/marketing")


def _serial(obj):
    if isinstance(obj, Decimal):
        v = float(obj)
        return None if v != v else v
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    raise TypeError(f"Not serializable: {type(obj)}")


def _json(data, status=200):
    return Response(
        json.dumps(data, default=_serial, allow_nan=False, ensure_ascii=False),
        status=status, mimetype="application/json"
    )


# ─── List campaigns ────────────────────────────────────────────────────────────

@marketing_bp.route("/campaigns", methods=["GET"])
@role_required("marketing", "manager", "admin")
def list_campaigns():
    try:
        conn = get_conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                role = session.get("role")
                uid  = session.get("user_id")
                if role in ("admin", "manager"):
                    cur.execute("""
                        SELECT c.*, u.full_name AS owner_name,
                               a.actual_spend, a.actual_leads, a.actual_deals,
                               a.updated_at AS actuals_updated
                        FROM marketing_campaigns c
                        JOIN users u ON u.id = c.user_id
                        LEFT JOIN marketing_actuals a ON a.campaign_id = c.id
                        ORDER BY c.created_at DESC
                    """)
                else:
                    cur.execute("""
                        SELECT c.*, u.full_name AS owner_name,
                               a.actual_spend, a.actual_leads, a.actual_deals,
                               a.updated_at AS actuals_updated
                        FROM marketing_campaigns c
                        JOIN users u ON u.id = c.user_id
                        LEFT JOIN marketing_actuals a ON a.campaign_id = c.id
                        WHERE c.user_id = %s
                        ORDER BY c.created_at DESC
                    """, (uid,))
                rows = [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()
        return _json(rows)
    except Exception as e:
        log.error(f"list_campaigns: {e}")
        return _json({"error": str(e)}, 500)


# ─── Get single campaign ───────────────────────────────────────────────────────

@marketing_bp.route("/campaigns/<int:cid>", methods=["GET"])
@role_required("marketing", "manager", "admin")
def get_campaign(cid):
    try:
        conn = get_conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT c.*, a.actual_spend, a.actual_leads, a.actual_qualified_leads,
                           a.actual_meetings, a.actual_follow_ups, a.actual_deals,
                           a.updated_at AS actuals_updated
                    FROM marketing_campaigns c
                    LEFT JOIN marketing_actuals a ON a.campaign_id = c.id
                    WHERE c.id = %s
                """, (cid,))
                row = cur.fetchone()
        finally:
            conn.close()
        if not row:
            return _json({"error": "الحملة غير موجودة"}, 404)
        uid = session.get("user_id")
        role = session.get("role")
        if role == "marketing" and row["user_id"] != uid:
            return _json({"error": "Forbidden"}, 403)
        return _json(dict(row))
    except Exception as e:
        return _json({"error": str(e)}, 500)


# ─── Create campaign ───────────────────────────────────────────────────────────

@marketing_bp.route("/campaigns", methods=["POST"])
@role_required("marketing", "manager", "admin")
def create_campaign():
    data = request.get_json() or {}
    try:
        conn = get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO marketing_campaigns
                        (user_id, campaign_name, avg_unit_price, commission_input,
                         commission_type, tax_rate, expected_close_rate, campaign_budget,
                         recommended_scenario, month, notes)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    RETURNING id
                """, (
                    session["user_id"],
                    data.get("campaign_name", "").strip(),
                    float(data.get("avg_unit_price") or 0),
                    float(data.get("commission_input") or 0),
                    data.get("commission_type", "percentage"),
                    float(data.get("tax_rate") or 19) / 100,
                    float(data.get("expected_close_rate") or 0) / 100,
                    float(data.get("campaign_budget") or 0),
                    data.get("recommended_scenario", "balanced"),
                    data.get("month") or None,
                    data.get("notes") or None,
                ))
                cid = cur.fetchone()[0]
            conn.commit()
        finally:
            conn.close()
        log.info(f"✅ Campaign created: id={cid}")
        return _json({"id": cid, "message": "تم إنشاء الحملة"}, 201)
    except Exception as e:
        log.error(f"create_campaign: {e}")
        return _json({"error": str(e)}, 500)


# ─── Update campaign inputs ────────────────────────────────────────────────────

@marketing_bp.route("/campaigns/<int:cid>", methods=["PUT"])
@role_required("marketing", "manager", "admin")
def update_campaign(cid):
    data = request.get_json() or {}
    try:
        conn = get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT user_id FROM marketing_campaigns WHERE id = %s", (cid,))
                row = cur.fetchone()
                if not row:
                    return _json({"error": "الحملة غير موجودة"}, 404)
                if session.get("role") == "marketing" and row[0] != session["user_id"]:
                    return _json({"error": "Forbidden"}, 403)

                cur.execute("""
                    UPDATE marketing_campaigns SET
                        campaign_name        = %s,
                        avg_unit_price       = %s,
                        commission_input     = %s,
                        commission_type      = %s,
                        tax_rate             = %s,
                        expected_close_rate  = %s,
                        campaign_budget      = %s,
                        recommended_scenario = %s,
                        month                = %s,
                        notes                = %s,
                        updated_at           = NOW()
                    WHERE id = %s
                """, (
                    data.get("campaign_name", "").strip(),
                    float(data.get("avg_unit_price") or 0),
                    float(data.get("commission_input") or 0),
                    data.get("commission_type", "percentage"),
                    float(data.get("tax_rate") or 19) / 100,
                    float(data.get("expected_close_rate") or 0) / 100,
                    float(data.get("campaign_budget") or 0),
                    data.get("recommended_scenario", "balanced"),
                    data.get("month") or None,
                    data.get("notes") or None,
                    cid,
                ))
            conn.commit()
        finally:
            conn.close()
        return _json({"message": "تم التحديث"})
    except Exception as e:
        return _json({"error": str(e)}, 500)


# ─── Save actuals ──────────────────────────────────────────────────────────────

@marketing_bp.route("/campaigns/<int:cid>/actuals", methods=["PUT"])
@role_required("marketing", "manager", "admin")
def save_actuals(cid):
    data = request.get_json() or {}
    try:
        conn = get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO marketing_actuals
                        (campaign_id, actual_spend, actual_leads, actual_qualified_leads,
                         actual_meetings, actual_follow_ups, actual_deals)
                    VALUES (%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (campaign_id) DO UPDATE SET
                        actual_spend             = EXCLUDED.actual_spend,
                        actual_leads             = EXCLUDED.actual_leads,
                        actual_qualified_leads   = EXCLUDED.actual_qualified_leads,
                        actual_meetings          = EXCLUDED.actual_meetings,
                        actual_follow_ups        = EXCLUDED.actual_follow_ups,
                        actual_deals             = EXCLUDED.actual_deals,
                        updated_at               = NOW()
                """, (
                    cid,
                    float(data.get("actual_spend") or 0),
                    int(data.get("actual_leads") or 0),
                    int(data.get("actual_qualified_leads") or 0),
                    int(data.get("actual_meetings") or 0),
                    int(data.get("actual_follow_ups") or 0),
                    int(data.get("actual_deals") or 0),
                ))
            conn.commit()
        finally:
            conn.close()
        return _json({"message": "تم حفظ الأرقام الفعلية"})
    except Exception as e:
        return _json({"error": str(e)}, 500)


# ─── Delete campaign ───────────────────────────────────────────────────────────

@marketing_bp.route("/campaigns/<int:cid>", methods=["DELETE"])
@role_required("marketing", "manager", "admin")
def delete_campaign(cid):
    try:
        conn = get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT user_id FROM marketing_campaigns WHERE id = %s", (cid,))
                row = cur.fetchone()
                if not row:
                    return _json({"error": "الحملة غير موجودة"}, 404)
                if session.get("role") == "marketing" and row[0] != session["user_id"]:
                    return _json({"error": "Forbidden"}, 403)
                cur.execute("DELETE FROM marketing_campaigns WHERE id = %s", (cid,))
            conn.commit()
        finally:
            conn.close()
        return _json({"message": "تم الحذف"})
    except Exception as e:
        return _json({"error": str(e)}, 500)
