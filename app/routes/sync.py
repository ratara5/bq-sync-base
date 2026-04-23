# ========================================
# app/routes/sync.py
# POST /sync/<group>
# ========================================

from __future__ import annotations
import importlib
import logging
from datetime import datetime, timezone

from flask import Blueprint, jsonify

from services.postgres import fetch_table
from services.bigquery import (
    insert_rows,
    upsert_rows,
    truncate_and_insert,
    merge_into_bq,
    get_last_sync_timestamp,
)
from services.dates import resolve_date

logger = logging.getLogger(__name__)
sync_bp = Blueprint("sync", __name__)

Strategy = str  # "upsert" | "full_refresh" | "merge_refresh"

# ── Config loader ────────────────────────────────────────────

def _load_config() -> dict:
    """Importa config (TABLES y SYNC_GROUPS) montada via volume en tiempo de request."""
    import importlib.util, sys
    spec = importlib.util.spec_from_file_location("config", "/app/config/config.py")
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.TABLES, mod.SYNC_GROUPS

# ── Resolución de from_date ──────────────────────────────────
 
def _resolve_from_date(from_date: dict | None) -> dict | None:
    """Resuelve el token dinámico de from_date a fecha ISO."""
    if not from_date:
        return None
    date_val = from_date["date"]
    resolved = resolve_date(date_val) if not date_val[0].isdigit() else date_val
    return {"field": from_date["field"], "date": resolved}

# ── Estrategias ──────────────────────────────────────────────
 
def _run_full_refresh(table_cfg: dict, table_name: str) -> dict:
    rows = fetch_table(
        table_name,
        exclude_fields=table_cfg.get("exclude_fields"),
    )
    count = truncate_and_insert(table_name, rows)
    return {"rows": count, "status": "ok"}
 
 
def _run_upsert(table_cfg: dict, table_name: str) -> dict:
    rows = fetch_table(table_name, exclude_fields=table_cfg.get("exclude_fields"))
    if not rows:
        return {"rows": 0, "status": "ok"}

    last_sync = get_last_sync_timestamp(table_name)

    if not last_sync:
        count = truncate_and_insert(table_name, rows)
        return {"rows": count, "status": "ok", "mode": "full"}

    delta = [r for r in rows if r.get("updated_at") and r["updated_at"] > last_sync]

    if not delta:
        return {"rows": 0, "status": "ok", "mode": "no_changes"}

    result = upsert_rows(table_name, delta, table_cfg["key"])
    return {"rows": len(delta), "status": "ok", "mode": "delta", **result}
 
 
def _run_merge_refresh(table_cfg: dict, table_name: str) -> dict:
    from_date = _resolve_from_date(table_cfg.get("from_date"))
    rows = fetch_table(
        table_name,
        exclude_fields=table_cfg.get("exclude_fields"),
        from_date=from_date,
    )
    count = merge_into_bq(
        table_name,
        rows,
        key=table_cfg["key"],
        from_date=from_date,
    )
    return {"rows": count, "status": "ok"}
 
STRATEGY_MAP: dict[str, callable] = {
    "full_refresh":  _run_full_refresh,
    "upsert":        _run_upsert,
    "merge_refresh": _run_merge_refresh,
}

# ── Endpoint ─────────────────────────────────────────────────

@sync_bp.post("/sync/<group>")
def sync_group(group: str):
    started_at = datetime.now(tz=timezone.utc)

    try:
        tables_cfg, groups_cfg = _load_config()
    except Exception as e:
        return jsonify({"error": f"config load failed: {e}"}), 500

    if group not in groups_cfg:
        return jsonify({
            "error": f"group '{group}' not found", 
            "available": list(groups_cfg)
        }), 404

    group_cfg = groups_cfg[group]
    strategy =  group_cfg.get("strategy")
    
    if strategy not in STRATEGY_MAP:
        return jsonify({
            "error": f"strategy '{strategy}' not supported",
            "supported": list(STRATEGY_MAP)
        }), 400

    run_fn  = STRATEGY_MAP[strategy]
    summary = {}

    for table_name in group_cfg["tables"]:
        if table_name not in tables_cfg:
            summary[table_name] = {"status": "error", "detail": "tabla no definida en TABLES"}
            continue

        try:
            result = run_fn(tables_cfg[table_name], table_name)
            summary[table_name] = {"status": "ok", **result}
        except Exception as e:
            logger.error(f"[{group}][{table_name}] {e}")
            summary[table_name] = {"status": "error", "detail": str(e)}

    elapsed = (datetime.now(tz=timezone.utc) - started_at).total_seconds()
    ok      = all(v["status"] == "ok" for v in summary.values())

    return jsonify({
        "group":   group,
        "strategy": strategy,
        "elapsed": elapsed,
        "summary": summary,
    }), 200 if ok else 207