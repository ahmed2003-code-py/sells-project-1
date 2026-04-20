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

    # Initialize database (creates users + kpi_entries tables + default admin)
    from app.database import init_all_tables
    init_all_tables()

    # Register blueprints
    from app.blueprints.auth_bp import auth_bp
    from app.blueprints.users_bp import users_bp
    from app.blueprints.kpi_bp import kpi_bp
    from app.blueprints.pages_bp import pages_bp
    from app.blueprints.propfinder_bp import propfinder_bp

    app.register_blueprint(pages_bp)          # HTML pages (/, /login, /dashboard, ...)
    app.register_blueprint(auth_bp)           # /api/auth/*
    app.register_blueprint(users_bp)          # /api/users/*
    app.register_blueprint(kpi_bp)            # /api/kpi/*
    app.register_blueprint(propfinder_bp)     # /api/units, /api/stats, /api/sync/*

    # Generic error handlers
    @app.errorhandler(404)
    def not_found(e):
        from flask import request, jsonify, redirect
        if request.path.startswith("/api/"):
            return jsonify({"error": "Not found"}), 404
        return redirect("/")

    @app.errorhandler(500)
    def server_error(e):
        log.error(f"500 error: {e}")
        from flask import request, jsonify
        if request.path.startswith("/api/"):
            return jsonify({"error": "Internal server error"}), 500
        return "Server error. Please try again later.", 500

    log.info("✅ Flask app ready — routes registered")
    return app
