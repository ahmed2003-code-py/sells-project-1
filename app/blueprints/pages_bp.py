"""
Pages blueprint: serves HTML pages with role-based routing
"""
from flask import Blueprint, render_template, redirect, session
from app.auth import login_required, role_required, role_home, current_user

pages_bp = Blueprint("pages", __name__)


@pages_bp.route("/")
def home():
    if "user_id" in session:
        return redirect(role_home(session["role"]))
    return redirect("/login")


@pages_bp.route("/login")
def login_page():
    if "user_id" in session:
        return redirect(role_home(session["role"]))
    return render_template("login.html")


@pages_bp.route("/register")
def register_page():
    if "user_id" in session:
        return redirect(role_home(session["role"]))
    return render_template("register.html")


@pages_bp.route("/sales")
@login_required
def sales_page():
    return render_template("sales.html", user=current_user())


@pages_bp.route("/data-entry")
@role_required("dataentry", "manager", "admin")
def dataentry_page():
    return render_template("dataentry.html", user=current_user())


@pages_bp.route("/dashboard")
@role_required("manager", "dataentry", "admin")
def dashboard_page():
    return render_template("dashboard.html", user=current_user())


@pages_bp.route("/finance")
@role_required("admin", "manager")
def finance_page():
    return render_template("finance.html", user=current_user())


@pages_bp.route("/admin")
@role_required("admin")
def admin_page():
    return render_template("admin.html", user=current_user())


@pages_bp.route("/profile")
@login_required
def profile_page():
    return render_template("profile.html", user=current_user())


@pages_bp.route("/teams")
@role_required("admin")
def teams_page():
    return render_template("teams.html", user=current_user())


@pages_bp.route("/team-leader")
@role_required("team_leader", "manager", "admin")
def team_leader_page():
    return render_template("team_leader.html", user=current_user())


@pages_bp.route("/tl-evaluation")
@role_required("manager", "admin")
def tl_evaluation_page():
    return render_template("tl_evaluation.html", user=current_user())


@pages_bp.route("/propfinder")
@login_required
def propfinder_page():
    return render_template("propfinder.html", user=current_user())
