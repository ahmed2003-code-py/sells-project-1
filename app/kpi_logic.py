"""
KPI configuration and scoring logic
Single source of truth for weights, targets, and calculation.
"""

KPI_CONFIG = {
    "calls":          {"weight": 15, "label": "Calls",         "label_ar": "المكالمات",       "input_type": "number",  "target_type": "fixed",     "target": 2000, "filled_by": "sales"},
    "meetings":       {"weight": 8,  "label": "Meetings",      "label_ar": "الاجتماعات",      "input_type": "number",  "target_type": "leads_pct", "target_pct": 0.20, "filled_by": "sales"},
    "crm_pct":        {"weight": 10, "label": "CRM Update",    "label_ar": "تحديث CRM",       "input_type": "percent", "target_type": "fixed",     "target": 95,   "filled_by": "sales"},
    "deals":          {"weight": 10, "label": "Deals",         "label_ar": "الصفقات",         "input_type": "number",  "target_type": "leads_pct", "target_pct": 0.03, "filled_by": "sales"},
    "reports":        {"weight": 8,  "label": "Reports",       "label_ar": "التقارير",        "input_type": "number",  "target_type": "fixed",     "target": 4,    "filled_by": "sales"},
    "reservations":   {"weight": 7,  "label": "Reservations",  "label_ar": "الحجوزات",        "input_type": "number",  "target_type": "leads_pct", "target_pct": 0.07, "filled_by": "sales"},
    "attitude":       {"weight": 4,  "label": "Attitude",      "label_ar": "السلوك",          "input_type": "passfail","target_type": "fixed",     "target": 100,  "filled_by": "dataentry"},
    "presentation":   {"weight": 4,  "label": "Presentation",  "label_ar": "المظهر والعرض",   "input_type": "passfail","target_type": "fixed",     "target": 100,  "filled_by": "dataentry"},
    "followup_pct":   {"weight": 15, "label": "Follow-up",     "label_ar": "متابعة العملاء",  "input_type": "percent", "target_type": "fixed",     "target": 100,  "filled_by": "sales"},
    "behaviour":      {"weight": 4,  "label": "Behaviour",     "label_ar": "التصرف",          "input_type": "passfail","target_type": "fixed",     "target": 100,  "filled_by": "dataentry"},
    "appearance":     {"weight": 4,  "label": "Appearance",    "label_ar": "المظهر",          "input_type": "passfail","target_type": "fixed",     "target": 100,  "filled_by": "dataentry"},
    "attendance_pct": {"weight": 7,  "label": "Attendance",    "label_ar": "الحضور",          "input_type": "percent", "target_type": "fixed",     "target": 100,  "filled_by": "sales"},
    "hr_roles":       {"weight": 4,  "label": "HR Roles",      "label_ar": "التزامات HR",     "input_type": "passfail","target_type": "fixed",     "target": 100,  "filled_by": "dataentry"},
}

SALES_FIELDS = [k for k, v in KPI_CONFIG.items() if v["filled_by"] == "sales"]
DATAENTRY_FIELDS = [k for k, v in KPI_CONFIG.items() if v["filled_by"] == "dataentry"]

RATINGS = [
    (90, "Excellent"),
    (75, "V.Good"),
    (55, "Good"),
    (40, "Medium"),
    (25, "Weak"),
    (0,  "Bad"),
]


def get_target(key: str, fresh_leads: float) -> float:
    cfg = KPI_CONFIG[key]
    if cfg["target_type"] == "fixed":
        return float(cfg["target"])
    if cfg["target_type"] == "leads_pct":
        return float(fresh_leads) * float(cfg["target_pct"])
    return 100.0


def get_rating(total_score: float) -> str:
    for threshold, label in RATINGS:
        if total_score >= threshold:
            return label
    return "Bad"


def compute_score(entry: dict):
    """
    Compute weighted KPI score.
    Returns: (total_score, rating, breakdown_dict)
    """
    L = float(entry.get("fresh_leads") or 0)
    breakdown = {}
    total = 0.0

    for key, cfg in KPI_CONFIG.items():
        actual = float(entry.get(key) or 0)
        target = get_target(key, L)

        if cfg["input_type"] == "passfail":
            # Pass=100 / Fail=0, scale to 0-1
            achievement = actual / 100.0
        else:
            achievement = min(actual / target, 1.0) if target > 0 else 0.0

        weighted = achievement * cfg["weight"]
        total += weighted

        breakdown[key] = {
            "label": cfg["label"],
            "label_ar": cfg["label_ar"],
            "actual": actual,
            "target": round(target, 2),
            "achievement_pct": round(achievement * 100, 1),
            "weight": cfg["weight"],
            "weighted_score": round(weighted, 2),
        }

    total = round(total, 2)
    return total, get_rating(total), breakdown
