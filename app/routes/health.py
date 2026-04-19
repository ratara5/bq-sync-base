# ========================================
# app-gci/routes/health.py
# GET /health
# ========================================

from flask import Blueprint, jsonify
from services.postgres import ping as pg_ping
from services.bigquery import ping as bq_ping

health_bp = Blueprint("health", __name__)


@health_bp.get("/health")
def health():
    pg_ok = pg_ping()
    bq_ok = bq_ping()
    status = "ok" if pg_ok and bq_ok else "degraded"

    return jsonify({
        "status": status,
        "postgres": "ok" if pg_ok else "error",
        "bigquery": "ok" if bq_ok else "error",
    }), 200 if status == "ok" else 503