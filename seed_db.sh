#!/usr/bin/env bash
set -euo pipefail

# ── Config ───────────────────────────────────────────────────
DB_HOST=""
DB_USER=""
DB_NAME=""
DATA_FOLDER=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --db-host)     DB_HOST="$2";   shift 2 ;;
        --db-user)     DB_USER="$2";     shift 2 ;;
        --db-name)     DB_NAME="$2";     shift 2 ;;
        --data-folder) DATA_FOLDER="$2"; shift 2 ;;
        *) echo "Argumento desconocido: $1"; exit 1 ;;
    esac
done

CONTAINER_DATA_DIR="/tmp/csv_load" 

# ── Helpers de color ─────────────────────────────────────────
info()    { echo -e "\e[34m[INFO]\e[0m  $*"; }
warn()    { echo -e "\e[33m[WARN]\e[0m  $*"; }
success() { echo -e "\e[32m[OK]\e[0m    $*"; }

# ── 1. Verificar que haya CSVs ───────────────────────────────
csv_files=("$DATA_FOLDER"/*.csv)   # glob seguro, evita parsear ls

if [ ! -e "${csv_files[0]}" ]; then
  warn "No se encontraron archivos .csv en $DATA_FOLDER. Continuando sin cargar datos."
  exit 0
fi

info "CSVs encontrados: ${#csv_files[@]}"

for filepath in "${csv_files[@]}"; do
  perl -i -pe 's/"(\$[0-9,]+(\.[0-9]+)?)"/my $n=$1; $n=~s%[\$,]%%g; $n/ge; s/\$([0-9]+(\.[0-9]+)?)/my $n=$1; $n/ge; s/, ,/,,/g;' "$filepath"
done


# ── 2. Verificar que la base de datos exista ─────────────────
db_exists=$(docker exec "$DB_HOST" psql -U "$DB_USER" -tAc \
  "SELECT 1 FROM pg_database WHERE datname='$DB_NAME';")

if [ "$db_exists" != "1" ]; then
  warn "La base de datos '$DB_NAME' no existe. Abortando carga."
  exit 1
fi

info "Base de datos '$DB_NAME' verificada."

# ── 3. Copiar CSVs al contenedor ─────────────────────────────
docker exec "$DB_HOST" mkdir -p "$CONTAINER_DATA_DIR"
docker cp "$DATA_FOLDER/." "$DB_HOST:$CONTAINER_DATA_DIR/"
info "Archivos copiados a $DB_HOST:$CONTAINER_DATA_DIR"

# ── 4. Iterar y cargar ───────────────────────────────────────
loaded=()
skipped=()

for filepath in "${csv_files[@]}"; do
  filename=$(basename "$filepath")
  table="${filename%.csv}"

  
  container_path="$CONTAINER_DATA_DIR/$filename"

  # ── 4a. Verificar que la tabla exista en el schema ─────────
  table_exists=$(docker exec "$DB_HOST" psql -U "$DB_USER" -d "$DB_NAME" -tAc \
    "SELECT 1 FROM information_schema.tables
     WHERE table_schema='public' AND table_name='$table';")

  if [ "$table_exists" != "1" ]; then
    warn "Tabla '$table' no existe en '$DB_NAME'. Saltando $filename."
    skipped+=("$table (tabla no existe)")
    continue
  fi

  # ── 4b. Verificar que la tabla esté vacía ──────────────────
  row_count=$(docker exec "$DB_HOST" psql -U "$DB_USER" -d "$DB_NAME" -tAc \
    "SELECT COUNT(*) FROM \"$table\";")

  if [ "$row_count" -ne 0 ]; then
    warn "Tabla '$table' ya tiene $row_count filas. Saltando."
    skipped+=("$table ($row_count filas existentes)")
    continue
  fi

  # ── 4c. Ejecutar COPY ──────────────────────────────────────
  docker exec "$DB_HOST" psql -U "$DB_USER" -d "$DB_NAME" -c \
    "SET datestyle = 'DMY';
    SET session_replication_role = 'replica';
    COPY \"$table\" FROM '$container_path' WITH (FORMAT csv, HEADER true, NULL '');
    SET session_replication_role = 'origin';
    SET datestyle = 'ISO, MDY';"

  success "Cargado: $filename → $table"
  loaded+=("$table")
done

# ── 5. Limpiar archivos temporales del contenedor ────────────
docker exec "$DB_HOST" rm -rf "$CONTAINER_DATA_DIR"
info "Archivos temporales eliminados del contenedor."

# ── 6. Resumen ───────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════"
echo "  RESUMEN DE CARGA"
echo "════════════════════════════════════════"

if [ ${#loaded[@]} -gt 0 ]; then
  success "Tablas cargadas (${#loaded[@]}):"
  for t in "${loaded[@]}"; do echo "    ✓ $t"; done
else
  warn "Ninguna tabla fue cargada."
fi

if [ ${#skipped[@]} -gt 0 ]; then
  echo ""
  warn "Tablas omitidas (${#skipped[@]}):"
  for t in "${skipped[@]}"; do echo "    ✗ $t"; done
fi

echo "════════════════════════════════════════"