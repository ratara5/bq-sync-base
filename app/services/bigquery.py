# ========================================
# app-gci/services/bigquery.py
# Escritura de datos hacia BigQuery
# ========================================

from __future__ import annotations
import logging
from typing import Literal

from google.cloud import bigquery
from google.oauth2 import service_account

from settings import settings

logger = logging.getLogger(__name__)

WriteMode = Literal["WRITE_APPEND", "WRITE_TRUNCATE", "WRITE_EMPTY"]


def _get_client() -> bigquery.Client:
    credentials = service_account.Credentials.from_service_account_file(
        settings.google_application_credentials,
        scopes=["https://www.googleapis.com/auth/bigquery"],
    )
    return bigquery.Client(
        project=settings.bq_project,
        credentials=credentials,
    )


def insert_rows(
    table_id: str,
    rows: list[dict],
    write_mode: WriteMode = "WRITE_APPEND",
) -> int:
    """
    Inserta filas en una tabla de BigQuery.

    Args:
        table_id:   Nombre de tabla destino (sin project/dataset).
        rows:       Lista de dicts a insertar.
        write_mode: WRITE_APPEND | WRITE_TRUNCATE | WRITE_EMPTY

    Returns:
        Número de filas insertadas.
    """
    if not rows:
        logger.info(f"[{table_id}] No rows to insert, skipping")
        return 0

    client    = _get_client()
    full_ref  = f"{settings.bq_project}.{settings.bq_dataset}.{table_id}"
    job_config = bigquery.LoadJobConfig(
        write_disposition=write_mode,
        autodetect=True,
    )

    job = client.load_table_from_json(rows, full_ref, job_config=job_config)
    job.result()  # bloquea hasta completar

    logger.info(f"[{table_id}] Inserted {len(rows)} rows → {full_ref}")
    return len(rows)


def ping() -> bool:
    """Verifica conectividad con BigQuery."""
    try:
        client = _get_client()
        client.query("SELECT 1").result()
        return True
    except Exception:
        return False