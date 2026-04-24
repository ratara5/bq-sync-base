#!/usr/bin/env python3
"""
transform_csv.py

Limpia y normaliza archivos CSV exportados desde Google Sheets
antes de cargarlos a PostgreSQL (via COPY):

  1. Elimina símbolos de moneda y comas de valores numéricos  ($1,234.56 → 1234.56)
  2. Convierte floats enteros a enteros reales             (3.0 → 3)
  3. Localiza columnas datetime a la zona del usuario y convierte a UTC

Uso:
    python3 transform_csv.py --data-folder ./data --config ./timezone_config.yml

Diseñado para ser reutilizado como módulo en un servicio ETL dedicado.
"""

import sys
import re
import argparse
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import yaml


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Limpia y normaliza CSVs para PostgreSQL.")
    parser.add_argument("--data-folder", required=True, help="Carpeta con los CSVs")
    parser.add_argument("--config",      required=True, help="Ruta al timezone_config.yml")
    return parser.parse_args()


def load_config(config_path: str) -> dict:
    """Carga la configuración de zonas horarias desde YAML."""
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config no encontrado: {config_path}")
    return yaml.safe_load(path.read_text())


def resolve_tz(config: dict, table: str, col: str) -> ZoneInfo:
    """Retorna la zona horaria de origen para una tabla/columna dada."""
    tz_name = (
        config
        .get("overrides", {})
        .get(table, {})
        .get(col, config["default_timezone"])
    )
    return ZoneInfo(tz_name)


def clean_currency(series: pd.Series) -> pd.Series:
    """
    Elimina símbolos de moneda y separadores de miles.
    '$1,234.56' → 1234.56 | '1,234' → 1234.0
    Solo actúa sobre columnas string que contengan $ o comas numéricas.
    """
    if not pd.api.types.is_string_dtype(series):
        return series

    sample = series.dropna().head(20).str.cat(sep=" ")
    if not re.search(r'\$|(?<=\d),(?=\d)', sample):
        return series

    cleaned = (
        series
        .str.replace(r'^\s*\$', '', regex=True)
        .str.replace(r',(?=\d{3})', '', regex=True)
    )
    return pd.to_numeric(cleaned, errors="coerce").combine_first(series)


def fix_integer_floats(df: pd.DataFrame) -> pd.DataFrame:
    """
    Convierte columnas float que solo contienen valores enteros a Int64.
    Evita que pandas serialice '3' como '3.0' al escribir el CSV.
    """
    for col in df.columns:
        if not pd.api.types.is_float_dtype(df[col]):
            continue
        non_null = df[col].dropna()
        if non_null.empty:
            continue
        if (non_null % 1 == 0).all():
            df[col] = df[col].astype("Int64")
    return df


def localize_timestamps(df: pd.DataFrame, config: dict, table: str) -> tuple[pd.DataFrame, int]:
    """
    Detecta columnas datetime, las localiza a la zona del usuario y convierte a UTC.
    Retorna el DataFrame modificado y el número de columnas transformadas.
    """
    transformed = 0

    for col in df.columns:
        if not pd.api.types.is_string_dtype(df[col]):
            continue

        parsed = pd.to_datetime(df[col], errors="coerce", dayfirst=True, format="mixed")

        if parsed.dt.tz is not None:
            df[col] = parsed.dt.tz_convert("UTC").dt.strftime("%Y-%m-%d %H:%M:%S+00")
            transformed += 1
            print(f"    [TZ] {table}.{col} → UTC (ya tz-aware)")
            continue

        non_null_mask  = df[col].notna()
        valid_ratio = parsed[non_null_mask].notna().sum() / max(non_null_mask.sum(), 1)
        if valid_ratio < 0.5:
            continue

        tz = resolve_tz(config, table, col)
        try:
            df[col] = (
                parsed
                .dt.tz_localize(tz)
                .dt.tz_convert("UTC")
                .dt.strftime("%Y-%m-%d %H:%M:%S+00")
            )
            transformed += 1
            print(f"    [TZ] {table}.{col} → UTC (desde {tz})")
        except Exception as e:
            raise RuntimeError(f"Error localizando {table}.{col}: {e}") from e

    return df, transformed


def transform_csv(csv_path: Path, config: dict) -> int:
    """
    Aplica todas las transformaciones a un CSV in-place.
    Retorna el número de columnas de timestamp transformadas.
    """
    table = csv_path.stem
    df = pd.read_csv(csv_path, keep_default_na=True, dtype_backend="numpy_nullable")

    # 1. Limpiar moneda
    df = df.apply(clean_currency)

    # 2. Convertir strings vacíos/blancos a NULL
    df = df.apply(lambda col: col.str.strip().replace("", pd.NA) 
                if pd.api.types.is_string_dtype(col) else col)

    # 3. Corregir floats enteros
    df = fix_integer_floats(df)

    # 4. Localizar timestamps a UTC
    df, transformed = localize_timestamps(df, config, table)

    df.to_csv(csv_path, index=False)
    return transformed


def transform(data_folder: str, config_path: str) -> None:
    """Punto de entrada principal. Procesa todos los CSVs de la carpeta."""
    config = load_config(config_path)
    csv_files = list(Path(data_folder).glob("*.csv"))

    if not csv_files:
        print("[WARN] No se encontraron CSVs.", file=sys.stderr)
        return

    total_cols = 0
    for csv_path in csv_files:
        print(f"[INFO] Procesando: {csv_path.name}")
        cols = transform_csv(csv_path, config)
        total_cols += cols
        print(f"       → {cols} columna(s) de timestamp transformada(s)")

    print(f"[INFO] Listo. Total columnas timestamp procesadas: {total_cols}")


if __name__ == "__main__":
    args = parse_args()
    try:
        transform(args.data_folder, args.config)
        sys.exit(0)
    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)