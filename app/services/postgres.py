# ========================================
# app/services/postgres.py
# Extracción de datos desde PostgreSQL
# ========================================

from __future__ import annotations
import logging
from contextlib import contextmanager
from typing import Generator

import psycopg2
import psycopg2.extras

from settings import settings
from services.dates import resolve_date
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


@contextmanager
def get_connection() -> Generator:
    conn = None
    try:
        conn = psycopg2.connect(settings.pg_dsn)
        yield conn
    except psycopg2.OperationalError as e:
        logger.error(f"Postgres connection error: {e}")
        raise
    finally:
        if conn:
            conn.close()


def fetch_table(
    table_name: str,
    exclude_fields: list[str] | None = None,
    parent_ids: set | None = None,
    parent_fk: str | None = None,
) -> list[dict]:
    """
    Extrae filas de una tabla Postgres aplicando filtros opcionales.
 
    Args:
        table_name:     Nombre de la tabla.
        exclude_fields: Campos a excluir de la extracción.
        from_date:      {"field": "fecha_campo", "date": "first_day_last_month"}
                        Filtra registros desde esa fecha.
        parent_ids:     Set de IDs padre — filtra hijas por FK.
        parent_fk:      Nombre del campo FK hacia la tabla padre.
    """
    exclude = set(exclude_fields or [])
 
    # Obtener columnas disponibles excluyendo las indicadas
    all_cols   = get_db_schema(table_name)
    select_cols = [c for c in all_cols if c not in exclude]
    cols_sql    = ", ".join(select_cols)
 
    where_clauses: list[str] = []
 
    # Filtro por IDs padre (tablas hijas)
    if parent_ids and parent_fk:
        ids_str = ", ".join(f"'{i}'" for i in parent_ids)
        where_clauses.append(f"{parent_fk} IN ({ids_str})")
 
    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
    query     = f"SELECT {cols_sql} FROM {table_name} {where_sql}"
 
    logger.debug(f"[{table_name}] query: {query[:200]}")
 
    now = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query)
            rows = cur.fetchall()
            logger.info(f"[{table_name}] {len(rows)} filas extraídas")
            return [{**row, "_sync_timestamp": now} for row in rows]
 
 
def get_db_schema(table_name: str) -> list[str]:
    """
    Retorna lista de nombres de columnas de una tabla Postgres.
    Usado para construir SELECT dinámico con exclude_fields.
    """
    query = """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = %s
        ORDER BY ordinal_position
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (table_name,))
            return [row[0] for row in cur.fetchall()]


def ping() -> bool:
    """Verifica conectividad con Postgres."""
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        return True
    except Exception:
        return False