#!/bin/bash
# ========================================
# bootstrap.sh
# Setup y prueba local del proyecto bq-sync
#
# Uso:
#   ./gci-companies/gci-base/bq-sync-base/bootstrap.sh \
#     --db-name db_gci_acme \
#     --pg-user postgres \
#     --pg-port 5433 \
#     --project-root ~/Documents/GoogleCloudProjects \
#     --compose-file docker-compose.yml \
#     --init-file init.sql \
#     --config-file config_example.py
# ========================================
set -euo pipefail

# ── Argumentos ───────────────────────────────────────────────
DB_NAME=""
PG_USER=""
PG_PORT_ARG=""
PROJECT_ROOT=""
COMPOSE_FILE_ARG=""
INIT_FILE_ARG=""
CONFIG_FILE_ARG=""

usage() {
    echo "Uso: ./bootstrap.sh --db-name <nombre> --pg-user <usuario> --project-root <ruta> --compose-file <archivo>"
    echo ""
    echo "  --db-name       Nombre de la base de datos a crear"
    echo "  --pg-user       Usuario de PostgreSQL"
    echo "  --pg-port       Puerto de PostgreSQL"
    echo "  --project-root  Ruta raíz del proyecto"
    echo "  --compose-file  Nombre del compose file (default: docker-compose.yml)"
    echo "  --init-file      Nombre del script de creación sql (default: init.sql)"
    echo "  --config-file      Nombre del archivo de configuración python (default config_example.py)"
    exit 1
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --db-name)      DB_NAME="$2";      shift 2 ;;
        --pg-user)      PG_USER="$2";      shift 2 ;;
        --pg-port)      PG_PORT_ARG="$2";      shift 2 ;;
        --project-root) PROJECT_ROOT="$2"; shift 2 ;;
        --compose-file) COMPOSE_FILE_ARG="$2"; shift 2 ;;
        --init-file)    INIT_FILE_ARG="$2"; shift 2 ;;
        --config-file)  CONFIG_FOLDER_ARG="$2"; shift 2 ;;

        *) echo "Argumento desconocido: $1"; usage ;;
    esac
done

[ -z "$DB_NAME"      ] && { echo "✗ --db-name es requerido";      usage; }
[ -z "$PG_USER"      ] && { echo "✗ --pg-user es requerido";      usage; }
[ -z "$PROJECT_ROOT" ] && { echo "✗ --project-root es requerido"; usage; }

# ── Variables derivadas ───────────────────────────────────────
PG_PORT="${PG_PORT_ARG:-5433}"
PR_PATH="$PROJECT_ROOT"
COMPOSE_FILE="${PR_PATH}/${COMPOSE_FILE_ARG:-docker-compose.yml}"
INIT_SQL="${PR_PATH}/templates/gci/${INIT_FILE_ARG:-init.sql}"
CONFIG_FILE="${PR_PATH}/templates/gci/bq-sync/config/${CONFIG_FILE_ARG:-config_example.py}"
BASE_PATH="$PR_PATH/gci-companies/gci-base/bq-sync-base"

# ── Helpers ──────────────────────────────────────────────────
log()  { echo -e "\n\033[1;34m▶ $*\033[0m"; }
ok()   { echo -e "\033[1;32m✓ $*\033[0m"; }
fail() { echo -e "\033[1;31m✗ $*\033[0m"; exit 1; }

# ── Validaciones previas ─────────────────────────────────────
log "Verificando dependencias..."
command -v python3.12 >/dev/null || fail "python3.12 no encontrado"
command -v docker     >/dev/null || fail "docker no encontrado"

[ -f "$COMPOSE_FILE" ] || fail "No se encontró $COMPOSE_FILE"
[ -f "$INIT_SQL"     ] || fail "No se encontró $INIT_SQL"

# ── Entorno Python ───────────────────────────────────────────
log "Configurando entorno Python..."
cd "$BASE_PATH"

if [ ! -d "venv" ]; then
    python3.12 -m venv venv
    ok "venv creado"
else
    ok "venv ya existe"
fi

source venv/bin/activate
pip install --quiet -r requirements.txt
ok "Dependencias instaladas"

# ── Postgres ─────────────────────────────────────────────────
log "Levantando postgres-gci..."
POSTGRES_GCI_PORT=$PG_PORT docker compose -f "$COMPOSE_FILE" up -d postgres-gci

log "Esperando a que Postgres esté listo..."
until docker exec postgres-gci pg_isready -U "$PG_USER" >/dev/null 2>&1; do
    echo "  esperando..."
    sleep 2
done
ok "Postgres listo"

# ── Base de datos ─────────────────────────────────────────────
log "Creando base de datos '$DB_NAME'..."
DB_EXISTS=$(docker exec postgres-gci psql -U "$PG_USER" -tAc \
    "SELECT 1 FROM pg_database WHERE datname='$DB_NAME'")

if [ "$DB_EXISTS" = "1" ]; then
    ok "Base de datos '$DB_NAME' ya existe"
else
    docker exec postgres-gci psql -U "$PG_USER" -c "CREATE DATABASE $DB_NAME"
    ok "Base de datos '$DB_NAME' creada"
fi

# ── Init SQL ─────────────────────────────────────────────────
log "Ejecutando init.sql..."
docker exec -i postgres-gci psql -U "$PG_USER" -d "$DB_NAME" < "$INIT_SQL"
ok "init.sql ejecutado"

# ── Carga de configuración ───────────────────────────────────
log "Cargando configuración..."
CONFIG_DIR="$BASE_PATH/app/config"
mkdir -p "$CONFIG_DIR"
cp "$CONFIG_FILE" "$CONFIG_DIR/config.py"
ok "Configuración copiada → $CONFIG_DIR/config.py"

# ── Carga de credenciales ───────────────────────────────────
log "Carga manual de credenciales es requerida"
CRED_DIR="$BASE_PATH/app/credentials"

# ── Fin ───────────────────────────────────────────────────────
echo -e "\n\033[1;32m✓ Bootstrap completado\033[0m"
echo "  DB:           $DB_NAME"
echo "  PG user:      $PG_USER"
echo "  Project root: $PR_PATH"