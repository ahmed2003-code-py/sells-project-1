"""
KPI blueprint — entry CRUD, reports, breakdowns
"""
import json
import logging
import psycopg2.extras
from decimal import Decimal
from datetime import datetime, date
from flask import Blueprint, request, session, Response
from app.database import get_conn
from app.auth import login_required, role_required
from app.kpi_logic import (
    KPI_CONFIG, SALES_FIELDS, DATAENTRY_FIELDS, compute_score,
    TL_KPI_CONFIG, TL_AUTO_FIELDS, TL_MANUAL_FIELDS, compute_tl_score,
)

log = logging.getLogger(__name__)
kpi_bp = Blueprint("kpi", __name__, url_prefix="/api/kpi")


# ─── JSON helpers ──────────────────────────────────────────────────────────────

def _json_default(obj):
    if isinstance(obj, Decimal):
        v = float(obj)
        return None if v != v else v
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")


def _json(data, status=200):
    return Response(
        json.dumps(data, default=_json_default, allow_nan=False, ensure_ascii=False),
        status=status,
        mimetype="application/json"
    )


def _entry_to_dict(row):
    return dict(row)


def _recompute_and_save(conn, entry_id):
    """Recompute score for an entry and persist it. Returns (total, rating)."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM kpi_entries WHERE id = %s", (entry_id,))
        entry = cur.fetchone()
        if not entry:
            return None, None
        total, rating, _ = compute_score(dict(entry))
        cur.execute("""
            UPDATE kpi_entries SET total_score = %s, rating = %s, updated_at = NOW()
            WHERE id = %s
        """, (total, rating, entry_id))
    return total, rating


# ─── Config (KPI weights/targets for frontend) ─────────────────────────────────

@kpi_bp.route("/config", methods=["GET"])
@login_required
def get_config():
    return _json({
        "kpis": KPI_CONFIG,
        "sales_fields": SALES_FIELDS,
        "dataentry_fields": DATAENTRY_FIELDS,
        "tl_kpis": TL_KPI_CONFIG,
        "tl_auto_fields": TL_AUTO_FIELDS,
        "tl_manual_fields": TL_MANUAL_FIELDS,
    })


# ─── Months list ───────────────────────────────────────────────────────────────

@kpi_bp.route("/months", methods=["GET"])
@login_required
def list_months():
    try:
        conn = get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT DISTINCT month FROM kpi_entries ORDER BY month DESC")
                months = [r[0] for r in cur.fetchall()]
        finally:
            conn.close()
        return _json(months)
    except Exception as e:
        log.error(f"months error: {e}")
        return _json({"error": str(e)}, 500)


# ─── SALES submits own data ────────────────────────────────────────────────────

@kpi_bp.route("/submit/sales", methods=["POST"])
@role_required("sales", "admin", "manager")
def submit_sales():
    data = request.get_json() or {}
    if session["role"] == "sales":
        user_id = session["user_id"]
    else:
        user_id = data.get("user_id", session["user_id"])
    month = data.get("month")

    if not month:
        return _json({"error_code": "required_fields_missing", "error": "month_required"}, 400)

    try:
        conn = get_conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    INSERT INTO kpi_entries (user_id, month,
                        fresh_leads, calls, meetings, crm_pct, deals,
                        reports, reservations, followup_pct, attendance_pct,
                        sales_submitted_at)
                    VALUES (%(user_id)s, %(month)s,
                        %(fresh_leads)s, %(calls)s, %(meetings)s, %(crm_pct)s, %(deals)s,
                        %(reports)s, %(reservations)s, %(followup_pct)s, %(attendance_pct)s,
                        NOW())
                    ON CONFLICT (user_id, month) DO UPDATE SET
                        fresh_leads = EXCLUDED.fresh_leads,
                        calls = EXCLUDED.calls,
                        meetings = EXCLUDED.meetings,
                        crm_pct = EXCLUDED.crm_pct,
                        deals = EXCLUDED.deals,
                        reports = EXCLUDED.reports,
                        reservations = EXCLUDED.reservations,
                        followup_pct = EXCLUDED.followup_pct,
                        attendance_pct = EXCLUDED.attendance_pct,
                        sales_submitted_at = NOW(),
                        updated_at = NOW()
                    RETURNING id
                """, {
                    "user_id": user_id, "month": month,
                    "fresh_leads": int(data.get("fresh_leads") or 0),
                    "calls": int(data.get("calls") or 0),
                    "meetings": int(data.get("meetings") or 0),
                    "crm_pct": float(data.get("crm_pct") or 0),
                    "deals": int(data.get("deals") or 0),
                    "reports": int(data.get("reports") or 0),
                    "reservations": int(data.get("reservations") or 0),
                    "followup_pct": float(data.get("followup_pct") or 0),
                    "attendance_pct": float(data.get("attendance_pct") or 0),
                })
                entry_id = cur.fetchone()["id"]
                total, rating = _recompute_and_save(conn, entry_id)
            conn.commit()
        finally:
            conn.close()
        log.info(f"✅ Sales submit: user={user_id} month={month} score={total}")
        return _json({"ok": True, "total_score": total, "rating": rating})
    except Exception as e:
        log.error(f"Sales submit error: {e}")
        return _json({"error": str(e)}, 500)


# ─── Data Entry / Manager fills evaluation ─────────────────────────────────────

@kpi_bp.route("/submit/evaluation", methods=["POST"])
@role_required("dataentry", "manager", "admin")
def submit_evaluation():
    data = request.get_json() or {}
    user_id = data.get("user_id")
    month = data.get("month")
    if not user_id or not month:
        return _json({"error_code": "required_fields_missing", "error": "required"}, 400)

    try:
        conn = get_conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                # Ensure entry exists
                cur.execute("""
                    INSERT INTO kpi_entries (user_id, month)
                    VALUES (%s, %s)
                    ON CONFLICT (user_id, month) DO NOTHING
                """, (user_id, month))

                base_params = {
                    "user_id": user_id,
                    "month": month,
                    "attitude": int(data.get("attitude") or 0),
                    "presentation": int(data.get("presentation") or 0),
                    "behaviour": int(data.get("behaviour") or 0),
                    "appearance": int(data.get("appearance") or 0),
                    "hr_roles": int(data.get("hr_roles") or 0),
                    "notes": data.get("notes") or None,
                    "dataentry_by": session["user_id"],
                }

                if data.get("fresh_leads") is not None and int(data.get("fresh_leads") or 0) > 0:
                    base_params["fresh_leads"] = int(data["fresh_leads"])
                    cur.execute("""
                        UPDATE kpi_entries SET
                            attitude = %(attitude)s,
                            presentation = %(presentation)s,
                            behaviour = %(behaviour)s,
                            appearance = %(appearance)s,
                            hr_roles = %(hr_roles)s,
                            fresh_leads = GREATEST(COALESCE(fresh_leads, 0), %(fresh_leads)s),
                            notes = %(notes)s,
                            dataentry_by = %(dataentry_by)s,
                            dataentry_submitted_at = NOW(),
                            updated_at = NOW()
                        WHERE user_id = %(user_id)s AND month = %(month)s
                        RETURNING id
                    """, base_params)
                else:
                    cur.execute("""
                        UPDATE kpi_entries SET
                            attitude = %(attitude)s,
                            presentation = %(presentation)s,
                            behaviour = %(behaviour)s,
                            appearance = %(appearance)s,
                            hr_roles = %(hr_roles)s,
                            notes = %(notes)s,
                            dataentry_by = %(dataentry_by)s,
                            dataentry_submitted_at = NOW(),
                            updated_at = NOW()
                        WHERE user_id = %(user_id)s AND month = %(month)s
                        RETURNING id
                    """, base_params)

                entry_id = cur.fetchone()["id"]
                total, rating = _recompute_and_save(conn, entry_id)
            conn.commit()
        finally:
            conn.close()
        log.info(f"✅ Evaluation submit: user={user_id} month={month} score={total}")
        return _json({"ok": True, "total_score": total, "rating": rating})
    except Exception as e:
        log.error(f"Evaluation submit error: {e}")
        return _json({"error": str(e)}, 500)


# ─── Get a single entry ────────────────────────────────────────────────────────

@kpi_bp.route("/entry/<int:user_id>/<month>", methods=["GET"])
@login_required
def get_entry(user_id, month):
    if session["role"] == "sales" and session["user_id"] != user_id:
        return _json({"error": "Forbidden"}, 403)

    try:
        conn = get_conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT e.*, u.full_name AS user_name, u.username
                    FROM kpi_entries e
                    JOIN users u ON u.id = e.user_id
                    WHERE e.user_id = %s AND e.month = %s
                """, (user_id, month))
                row = cur.fetchone()
        finally:
            conn.close()
        if not row:
            return _json(None)
        entry = dict(row)
        _, _, breakdown = compute_score(entry)
        entry["breakdown"] = breakdown
        return _json(entry)
    except Exception as e:
        log.error(f"get_entry error: {e}")
        return _json({"error": str(e)}, 500)


# ─── Delete entry ──────────────────────────────────────────────────────────────

@kpi_bp.route("/entry/<int:entry_id>", methods=["DELETE"])
@role_required("admin", "manager")
def delete_entry(entry_id):
    try:
        conn = get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM kpi_entries WHERE id = %s", (entry_id,))
                if cur.rowcount == 0:
                    return _json({"error_code": "not_found", "error": "not_found"}, 404)
            conn.commit()
        finally:
            conn.close()
        return _json({"ok": True})
    except Exception as e:
        return _json({"error": str(e)}, 500)


# ─── Report: all entries with filters ──────────────────────────────────────────

@kpi_bp.route("/report", methods=["GET"])
@login_required
def report():
    month = request.args.get("month")
    user_id_filter = request.args.get("user_id")

    if session["role"] == "sales":
        user_id_filter = session["user_id"]

    try:
        conn = get_conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                q = """
                    SELECT e.*, u.full_name AS user_name, u.username
                    FROM kpi_entries e
                    JOIN users u ON u.id = e.user_id
                    WHERE u.active = true
                """
                params = []
                if month:
                    q += " AND e.month = %s"
                    params.append(month)
                if user_id_filter:
                    q += " AND e.user_id = %s"
                    params.append(int(user_id_filter))
                q += " ORDER BY e.total_score DESC, u.full_name"
                cur.execute(q, params)
                rows = [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()
        for row in rows:
            _, _, breakdown = compute_score(row)
            row["breakdown"] = breakdown
        return _json(rows)
    except Exception as e:
        log.error(f"report error: {e}")
        return _json({"error": str(e)}, 500)


# ─── Summary for a month ───────────────────────────────────────────────────────

@kpi_bp.route("/summary", methods=["GET"])
@role_required("manager", "admin", "dataentry")
def summary():
    month = request.args.get("month")
    try:
        conn = get_conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                q = """
                    SELECT
                        COUNT(*) AS total_entries,
                        AVG(total_score) AS avg_score,
                        MAX(total_score) AS max_score,
                        MIN(total_score) AS min_score,
                        COUNT(CASE WHEN total_score < 55 THEN 1 END) AS below_55,
                        COUNT(CASE WHEN sales_submitted_at IS NOT NULL THEN 1 END) AS sales_done,
                        COUNT(CASE WHEN dataentry_submitted_at IS NOT NULL THEN 1 END) AS dataentry_done
                    FROM kpi_entries e
                    JOIN users u ON u.id = e.user_id
                    WHERE u.active = true
                """
                params = []
                if month:
                    q += " AND e.month = %s"
                    params.append(month)
                cur.execute(q, params)
                s = dict(cur.fetchone())

                # Top performer
                q2 = """
                    SELECT u.full_name, e.total_score, e.rating
                    FROM kpi_entries e JOIN users u ON u.id = e.user_id
                    WHERE u.active = true
                """
                if month:
                    q2 += " AND e.month = %s"
                q2 += " ORDER BY e.total_score DESC LIMIT 1"
                cur.execute(q2, params)
                top = cur.fetchone()
                s["top"] = dict(top) if top else None
        finally:
            conn.close()
        return _json(s)
    except Exception as e:
        log.error(f"summary error: {e}")
        return _json({"error": str(e)}, 500)


# ─── Sales Manager submits TL manual evaluation ────────────────────────────────

@kpi_bp.route("/submit/tl-evaluation", methods=["POST"])
@role_required("manager", "admin")
def submit_tl_evaluation():
    data = request.get_json() or {}
    tl_user_id = data.get("user_id")
    month = data.get("month")
    if not tl_user_id or not month:
        return _json({"error_code": "required_fields_missing", "error": "required"}, 400)

    try:
        conn = get_conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    INSERT INTO kpi_entries (user_id, month)
                    VALUES (%s, %s)
                    ON CONFLICT (user_id, month) DO NOTHING
                """, (tl_user_id, month))

                cur.execute("""
                    UPDATE kpi_entries SET
                        crm_pct          = %(crm_pct)s,
                        reports          = %(reports)s,
                        clients_pipeline = %(clients_pipeline)s,
                        attitude         = %(attitude)s,
                        presentation     = %(presentation)s,
                        behaviour        = %(behaviour)s,
                        appearance       = %(appearance)s,
                        attendance_pct   = %(attendance_pct)s,
                        hr_roles         = %(hr_roles)s,
                        notes            = %(notes)s,
                        dataentry_by     = %(dataentry_by)s,
                        dataentry_submitted_at = NOW(),
                        updated_at       = NOW()
                    WHERE user_id = %(user_id)s AND month = %(month)s
                    RETURNING id
                """, {
                    "user_id":          tl_user_id,
                    "month":            month,
                    "crm_pct":          float(data.get("crm_pct") or 0),
                    "reports":          int(data.get("reports") or 0),
                    "clients_pipeline": float(data.get("clients_pipeline") or 0),
                    "attitude":         int(data.get("attitude") or 0),
                    "presentation":     int(data.get("presentation") or 0),
                    "behaviour":        int(data.get("behaviour") or 0),
                    "appearance":       int(data.get("appearance") or 0),
                    "attendance_pct":   float(data.get("attendance_pct") or 0),
                    "hr_roles":         int(data.get("hr_roles") or 0),
                    "notes":            data.get("notes") or None,
                    "dataentry_by":     session["user_id"],
                })
            conn.commit()
        finally:
            conn.close()
        log.info(f"✅ TL evaluation submit: tl={tl_user_id} month={month}")
        return _json({"ok": True})
    except Exception as e:
        log.error(f"TL evaluation submit error: {e}")
        return _json({"error": str(e)}, 500)


# ─── Get computed TL KPI ───────────────────────────────────────────────────────

@kpi_bp.route("/tl-kpi/<int:tl_user_id>/<month>", methods=["GET"])
@login_required
def get_tl_kpi(tl_user_id, month):
    role = session.get("role")
    if role == "sales":
        return _json({"error_code": "forbidden", "error": "forbidden"}, 403)
    if role == "team_leader" and session["user_id"] != tl_user_id:
        return _json({"error_code": "forbidden", "error": "forbidden"}, 403)

    try:
        conn = get_conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                # TL's own entry (manual fields)
                cur.execute("""
                    SELECT e.* FROM kpi_entries e
                    WHERE e.user_id = %s AND e.month = %s
                """, (tl_user_id, month))
                tl_row = cur.fetchone()
                tl_entry = dict(tl_row) if tl_row else {}

                # Find TL's team
                cur.execute("""
                    SELECT id FROM teams WHERE leader_id = %s
                """, (tl_user_id,))
                team_row = cur.fetchone()
                if not team_row:
                    return _json({"error_code": "no_team_assigned", "error": "no_team_assigned"}, 404)
                team_id = team_row["id"]

                # Team size
                cur.execute("""
                    SELECT COUNT(*) AS cnt FROM users
                    WHERE team_id = %s AND role = 'sales' AND active = true
                """, (team_id,))
                team_size = cur.fetchone()["cnt"]

                # Submitted team entries for this month
                cur.execute("""
                    SELECT e.* FROM kpi_entries e
                    JOIN users u ON u.id = e.user_id
                    WHERE u.team_id = %s AND u.role = 'sales' AND u.active = true
                    AND e.month = %s
                """, (team_id, month))
                team_entries = [dict(r) for r in cur.fetchall()]

        finally:
            conn.close()

        total, rating, breakdown = compute_tl_score(tl_entry, team_entries)
        return _json({
            "tl_entry": tl_entry,
            "team_size": team_size,
            "team_submitted": len(team_entries),
            "total_score": total,
            "rating": rating,
            "breakdown": breakdown,
        })
    except Exception as e:
        log.error(f"get_tl_kpi error: {e}")
        return _json({"error": str(e)}, 500)


# ─── List team leaders (for manager evaluation page) ──────────────────────────

@kpi_bp.route("/team-leaders", methods=["GET"])
@role_required("manager", "admin")
def list_team_leaders():
    month = request.args.get("month")
    try:
        conn = get_conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT u.id, u.full_name, u.username,
                           t.id AS team_id, t.name AS team_name,
                           e.dataentry_submitted_at, e.notes
                    FROM users u
                    LEFT JOIN teams t ON t.leader_id = u.id
                    LEFT JOIN kpi_entries e ON e.user_id = u.id AND e.month = %s
                    WHERE u.role = 'team_leader' AND u.active = true
                    ORDER BY u.full_name
                """, (month,))
                rows = [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()
        return _json(rows)
    except Exception as e:
        log.error(f"list_team_leaders error: {e}")
        return _json({"error": str(e)}, 500)
