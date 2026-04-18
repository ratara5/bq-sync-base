# ========================================
# app-gci/routes/sync.py
# POST /sync/<group>
# ========================================

from __future__ import annotations
import logging
from datetime import datetime, timezone

from flask import Blueprint, jsonify

from services.postgres import fetch_table
from services.bigquery import insert_rows

logger = logging.getLogger(__name__)
sync_bp = Blueprint("sync", __name__)


def _load_config() -> dict:
    """Importa config montada via volume en tiempo de request."""
    import importlib.util, sys
    spec = importlib.util.spec_from_file_location("config", "/app/config/config.py")
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.SYNC_GROUPS


@sync_bp.post("/sync/<group>")
def sync_group(group: str):
    started_at = datetime.now(tz=timezone.utc)

    try:
        groups = _load_config()
    except Exception as e:
        return jsonify({"error": f"config load failed: {e}"}), 500

    if group not in groups:
        return jsonify({"error": f"group '{group}' not found", "available": list(groups)}), 404

    cfg        = groups[group]
    last_sync  = started_at.strftime("%Y-%m-%d %H:%M:%S")
    summary    = {}

    for table in cfg["tables"]:
        try:
            query    = cfg["query"].format(table=table, last_sync=last_sync)
            bq_table = cfg["bq_table"].format(table=table)
            rows     = fetch_table(query)
            inserted = insert_rows(bq_table, rows)
            summary[table] = {"rows": inserted, "status": "ok"}
        except Exception as e:
            logger.error(f"[{group}][{table}] {e}")
            summary[table] = {"status": "error", "detail": str(e)}

    elapsed = (datetime.now(tz=timezone.utc) - started_at).total_seconds()
    ok      = all(v["status"] == "ok" for v in summary.values())

    return jsonify({
        "group":   group,
        "elapsed": elapsed,
        "summary": summary,
    }), 200 if ok else 207