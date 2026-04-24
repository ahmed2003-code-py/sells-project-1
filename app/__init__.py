"""
Flask application factory
"""
import logging
import os
from flask import Flask
from config import Config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

log = logging.getLogger(__name__)


def create_app():
    app = Flask(
        __name__,
        static_folder="static",
        template_folder="templates"
    )
    app.config.from_object(Config)

    from app.database import init_all_tables
    init_all_tables()

    # Register blueprints
    from app.blueprints.auth_bp import auth_bp
    from app.blueprints.users_bp import users_bp
    from app.blueprints.kpi_bp import kpi_bp
    from app.blueprints.pages_bp import pages_bp
    from app.blueprints.propfinder_bp import propfinder_bp
    from app.blueprints.finance_bp import finance_bp
    from app.blueprints.teams_bp import teams_bp
    from app.blueprints.marketing_bp import marketing_bp

    app.register_blueprint(pages_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(kpi_bp)
    app.register_blueprint(propfinder_bp)
    app.register_blueprint(finance_bp)
    app.register_blueprint(teams_bp)
    app.register_blueprint(marketing_bp)

    # Error handlers — API paths get structured JSON, browser gets a friendly page
    @app.errorhandler(404)
    def not_found(e):
        from flask import request, jsonify, redirect
        if request.path.startswith("/api/"):
            return jsonify({"error_code": "not_found", "error": "not_found"}), 404
        return redirect("/")

    @app.errorhandler(500)
    def server_error(e):
        log.error(f"500 error: {e}")
        from flask import request, jsonify
        if request.path.startswith("/api/"):
            return jsonify({"error_code": "server", "error": "server"}), 500
        return "Server error. Please try again later.", 500

    @app.errorhandler(405)
    def method_not_allowed(e):
        from flask import request, jsonify
        if request.path.startswith("/api/"):
            return jsonify({"error_code": "forbidden", "error": "method_not_allowed"}), 405
        return "Method not allowed", 405

    # Security-hardening response headers
    @app.after_request
    def _sec_headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        resp.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
        return resp

    log.info("✅ Flask app ready — all blueprints registered")
    return app
