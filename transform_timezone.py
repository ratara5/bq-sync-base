# 2026-04-23 Se usa en el bootstrap.sh-seed-db.sh, pero el objetivo es convertirlo en servicio
"""
transform_timestamps.py

Localiza columnas datetime en CSVs a la zona del usuario
y las convierte a UTC antes de cargar a PostgreSQL.

Uso:
    python3 transform_timestamps.py --data-folder ./data --config ./timezone_config.yml
"""
import sys
import argparse

from pathlib import Path
from zoneinfo import ZoneInfo  # Python 3.9+
import pandas as pd
import yaml

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Transforma timestamps a UTC en CSVs.")
    parser.add_argument("--data-folder", required=True, help="Carpeta con los CSVs")
    parser.add_argument("--config",      required=True, help="Ruta al timezone_config.yml")
    return parser.parse_args()


def load_config(config_path: str) -> dict:
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config no encontrado: {config_path}")
    return yaml.safe_load(path.read_text())


def resolve_tz(config: dict, table: str, col: str) -> ZoneInfo:
    tz_name = (
        config
        .get("overrides", {})
        .get(table, {})
        .get(col, config["default_timezone"])
    )
    return ZoneInfo(tz_name)


def transform_csv(csv_path: Path, config: dict) -> int:
    """
    Transforma las columnas datetime de un CSV a UTC in-place.
    Retorna el número de columnas transformadas.
    """
    table = csv_path.stem
    df = pd.read_csv(csv_path, keep_default_na=True)
    transformed = 0

    for col in df.columns:
        if table == "pausas" and col == "fecha_hora_pausa":
            parsed = pd.to_datetime(df[col], errors="coerce", dayfirst=True)
            valid = parsed.notna().sum()
            print(f"  {table}.{col}: dtype={df[col].dtype}, valid_dt={valid}/{len(parsed)}")

        if not (pd.api.types.is_object_dtype(df[col]) or pd.api.types.is_string_dtype(df[col])):
            continue

        # Si ya la csv está procesada, no intentar parsear de nuevo (parece no estar funcionando)
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            print(f"  [SKIP] {table}.{col} ya es datetime")
            continue

        parsed = pd.to_datetime(df[col], errors="coerce", dayfirst=True, format="mixed")

        # Saltar si menos del 50% de los valores no nulos son datetime válidos
        non_null = df[col].dropna()
        valid_ratio = parsed[df[col].notna()].notna().sum() / max(len(non_null), 1)

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
            print(f"  [OK] {table}.{col} → UTC (desde {tz})")
        except Exception as e:
            raise RuntimeError(f"Error transformando {table}.{col}: {e}") from e

    for col in df.columns:
        if pd.api.types.is_float_dtype(df[col]):
            if (df[col].dropna() % 1 == 0).all():
                df[col] = df[col].astype('Int64')  # nullable integer


    df.to_csv(csv_path, index=False)
    return transformed

def transform(data_folder: str, config_path: str) -> None:
    config = load_config(config_path)
    csv_files = list(Path(data_folder).glob("*.csv"))

    if not csv_files:
        print("[WARN] No se encontraron CSVs en la carpeta.", file=sys.stderr)
        return

    total_cols = 0
    for csv_path in csv_files:
        print(f"[INFO] Procesando: {csv_path.name}")
        cols = transform_csv(csv_path, config)
        total_cols += cols
        print(f"  → {cols} columna(s) transformada(s)")

    print(f"[INFO] Transformación completa. Total columnas procesadas: {total_cols}")


if __name__ == "__main__":
    args = parse_args()
    try:
        transform(args.data_folder, args.config)
        sys.exit(0)
    except Exception as e:
        print(f"[ERROR] transform_timestamps: {e}", file=sys.stderr)
        sys.exit(1)