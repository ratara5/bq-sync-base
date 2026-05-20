# ========================================
# app/services/bigquery.py
# Escritura de datos hacia BigQuery
# ========================================

from __future__ import annotations
import json
import time
from typing import Any, Literal

from google.cloud import bigquery
from google.oauth2 import service_account

from settings import settings

import logging
import structlog

log = structlog.get_logger(__name__)

# Tabla de control de tablas temporales pendientes de eliminar
_TEMP_QUEUE_TABLE = "_temp_deletion_queue"


WriteMode = Literal["WRITE_APPEND", "WRITE_TRUNCATE", "WRITE_EMPTY"]


# ── Cliente ──────────────────────────────────────────────────

def _get_client() -> bigquery.Client:
    credentials = service_account.Credentials.from_service_account_file(
        settings.google_application_credentials,
        scopes=["https://www.googleapis.com/auth/bigquery"],
    )
    return bigquery.Client(
        project=settings.bq_project,
        credentials=credentials,
    )

def _absolute_reference(table_id: str) -> str:
    return f"{settings.bq_project}.{settings.bq_dataset}.{table_id}"

# ── Schema ───────────────────────────────────────────────────
 
def get_bq_schema(table_id: str) -> list[bigquery.SchemaField]:
    """Obtiene el schema de una tabla BQ existente."""
    client = _get_client()
    table  = client.get_table(_absolute_reference(table_id))
    return table.schema

# ── Consultas ────────────────────────────────────────────────
 
def run_query(sql: str) -> list[dict]:
    """Ejecuta una query SQL arbitraria y retorna filas como dicts."""
    client = _get_client()
    rows   = client.query(sql).result()
    return [dict(row) for row in rows]
 
 
def get_last_sync_timestamp(table_id: str) -> str | None:
    """
    Retorna el último timestamp sincronizado en BQ para una tabla.
    Útil para sincronizaciones incrementales.
    """
    sql = f"""
        SELECT FORMAT_TIMESTAMP('%Y-%m-%dT%H:%M:%SZ', MAX(_sync_timestamp)) 
        AS last_sync
        FROM {_absolute_reference(table_id)}
    """
    try:
        rows = run_query(sql)
        val  = rows[0].get("last_sync") if rows else None
        return str(val) if val else None
    except Exception as e:
        log.warning(f"[{table_id}] get_last_sync_timestamp: {e}")
        return None
 
 
def row_exists_in_bq(table_id: str, key: list[str], row: dict) -> bool:
    """Verifica si una fila existe en BQ por su clave primaria."""
    conditions = " AND ".join(f"{k} = '{row[k]}'" for k in key)
    sql = f"SELECT 1 FROM {_absolute_reference(table_id)} WHERE {conditions} LIMIT 1"
    try:
        return bool(run_query(sql))
    except Exception:
        return False

# ── Escritura ────────────────────────────────────────────────
 
def insert_rows(table_id: str, rows: list[dict]) -> int:
    """Inserta filas en BQ (WRITE_APPEND). Retorna filas insertadas."""
    if not rows:
        return 0
    client     = _get_client()
    job_config = bigquery.LoadJobConfig(
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        autodetect=True,
    )
    job = client.load_table_from_json(rows, _absolute_reference(table_id), job_config=job_config)
    job.result()
    log.info(f"[{table_id}] insert_rows: {len(rows)} filas")
    return len(rows)
 
 
def update_row_in_bq(table_id: str, key: list[str], row: dict) -> None:
    """Actualiza una fila existente en BQ por su clave primaria."""
    set_clause = ", ".join(
        f"{k} = '{v}'" for k, v in row.items() if k not in key
    )
    where_clause = " AND ".join(f"{k} = '{row[k]}'" for k in key)
    sql = f"UPDATE {_absolute_reference(table_id)} SET {set_clause} WHERE {where_clause}"
    run_query(sql)
 
 
def truncate_and_insert(table_id: str, rows: list[dict]) -> int:
    """Full refresh: reemplaza toda la tabla. Retorna filas insertadas."""
    if not rows:
        log.warning(f"[{table_id}] truncate_and_insert: sin filas, abortando")
        return 0
    client     = _get_client()
    job_config = bigquery.LoadJobConfig(
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        autodetect=True,
    )
    job = client.load_table_from_json(rows, _absolute_reference(table_id), job_config=job_config)
    job.result()
    log.info(f"[{table_id}] truncate_and_insert: {len(rows)} filas")
    return len(rows)

# ── Merge ────────────────────────────────────────────────────
 
def merge_into_bq(
    table_id: str,
    rows: list[dict],
    key: list[str],
    from_date: dict | None = None,
) -> int:
    """
    MERGE tabla temporal → tabla destino.
    Sincroniza inserts, updates y deletes (WHEN NOT MATCHED BY SOURCE).
 
    Args:
        table_id:  Tabla destino en BQ.
        rows:      Filas desde Postgres.
        key:       Campos clave primaria.
        from_date: {"field": "fecha_campo", "date": "2025-01-01"} — limita DELETE por rango.
                   Si es None, DELETE aplica sobre toda la tabla.
    """
    if not rows:
        log.warning(f"[{table_id}] merge_into_bq: sin filas")
        return 0
 
    client       = _get_client()
    temp_table   = f"{table_id}_temp_{int(time.time() * 1000)}"
    temp_ref     = _absolute_reference(temp_table)
    dest_ref     = _absolute_reference(table_id)
 
    # 0. Eliminar temporales en cola de ejecuciones anteriores
    _delete_temp_tables(client)
 
    # 1. Cargar rows en tabla temporal
    schema     = get_bq_schema(table_id)
    job_config = bigquery.LoadJobConfig(
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        schema=schema,
    )
    job = client.load_table_from_json(rows, temp_ref, job_config=job_config)
    job.result()
    log.info(f"[{table_id}] temp table cargada: {temp_table}")
 
    # 2. Construir MERGE SQL
    on_clause     = " AND ".join(f"T.{k} = S.{k}" for k in key)
    non_key_cols  = [c for c in rows[0].keys() if c not in key]
    set_clause    = ", ".join(f"T.{c} = S.{c}" for c in non_key_cols)
    insert_cols   = ", ".join(rows[0].keys())
    insert_vals   = ", ".join(f"S.{c}" for c in rows[0].keys())
    not_matched_filter = _build_not_matched_filter(from_date)
 
    merge_sql = f"""
        MERGE `{dest_ref}` T
        USING `{temp_ref}` S
        ON {on_clause}
        WHEN MATCHED THEN
            UPDATE SET {set_clause}
        WHEN NOT MATCHED BY TARGET THEN
            INSERT ({insert_cols}) VALUES ({insert_vals})
        WHEN NOT MATCHED BY SOURCE
            {not_matched_filter}
            THEN DELETE
    """
 
    run_query(merge_sql)
    log.info(f"[{table_id}] merge_into_bq: {len(rows)} filas procesadas")
 
    # 3. Encolar temporal para eliminar en próxima ejecución
    _enqueue_temp_to_del(client, temp_table)
 
    return len(rows)

# ── Upsert ───────────────────────────────────────────────────
         
def upsert_rows(table_id: str, rows: list[dict], key: list[str]) -> dict:
    """
    Upsert fila a fila: rowExistsInBQ → updateRowInBQ | insertRows.
    Retorna conteo de inserts y updates.
    """
    inserted = updated = 0
    for row in rows:
        if row_exists_in_bq(table_id, key, row):
            update_row_in_bq(table_id, key, row)
            updated += 1
        else:
            insert_rows(table_id, [row])
            inserted += 1
    log.info(f"[{table_id}] upsert: {inserted} inserts, {updated} updates")
    return {"inserted": inserted, "updated": updated}

# ── Helpers internos ─────────────────────────────────────────
 
def _build_not_matched_filter(from_date: dict | None) -> str:
    """Construye el filtro para WHEN NOT MATCHED BY SOURCE."""
    if from_date:
        field = from_date["field"]
        date  = from_date["date"]
        return f"AND T.{field} >= '{date}'"
    return ""
 
 
def _enqueue_temp_to_del(client: bigquery.Client, temp_table: str) -> None:
    """Registra una tabla temporal para eliminar en la próxima ejecución."""
    try:
        row = {"temp_table": temp_table, "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ")}
        client.insert_rows_json(_absolute_reference(_TEMP_QUEUE_TABLE), [row])
    except Exception as e:
        log.warning(f"_enqueue_temp_to_del: {e}")
 
 
def _delete_temp_tables(client: bigquery.Client) -> None:
    """Elimina tablas temporales encoladas de ejecuciones anteriores."""
    try:
        rows = run_query(f"SELECT temp_table FROM {_absolute_reference(_TEMP_QUEUE_TABLE)}")
        for row in rows:
            try:
                client.delete_table(_absolute_reference(row["temp_table"]), not_found_ok=True)
                log.info(f"Temp table eliminada: {row['temp_table']}")
            except Exception as e:
                log.warning(f"No se pudo eliminar {row['temp_table']}: {e}")
        # Limpiar la cola
        run_query(f"TRUNCATE TABLE {_absolute_reference(_TEMP_QUEUE_TABLE)}")
    except Exception as e:
        log.warning(f"_delete_temp_tables: {e}")
 
 
def ping() -> bool:
    """Verifica conectividad con BigQuery."""
    try:
        _get_client().query("SELECT 1").result()
        return True
    except Exception as e:
        log.error(f"BQ ping error: {e}")
        return False
 