# ========================================
# app-gci/server.py
# Flask app factory
# ========================================

import logging
from flask import Flask
from routes.health import health_bp
from routes.sync   import sync_bp


def create_app() -> Flask:
    app = Flask(__name__)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    )

    app.register_blueprint(health_bp)
    app.register_blueprint(sync_bp)

    return app