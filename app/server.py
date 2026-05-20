# ========================================
# app/server.py
# Flask app factory
# ========================================

import logging
from flask import Flask
from routes import all_blueprints


def create_app() -> Flask:
    app = Flask(__name__)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    )

    for bp in all_blueprints:
        app.register_blueprint(bp)

    return app