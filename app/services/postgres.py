# ========================================
# app-gci/services/postgres.py
# Extracción de datos desde PostgreSQL
# ========================================

from __future__ import annotations
import logging
from contextlib import contextmanager
from typing import Generator

import psycopg2
import psycopg2.extras

from settings import settings

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


def fetch_table(query: str) -> list[dict]:
    """
    Ejecuta una query y retorna lista de dicts.

    Args:
        query: SQL con parámetros ya interpolados.

    Returns:
        Lista de filas como dicts.
    """
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            logger.debug(f"Executing: {query[:120]}...")
            cur.execute(query)
            rows = cur.fetchall()
            logger.info(f"Fetched {len(rows)} rows")
            return [dict(row) for row in rows]


def ping() -> bool:
    """Verifica conectividad con Postgres."""
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        return True
    except Exception:
        return False