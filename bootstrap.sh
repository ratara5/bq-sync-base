#!/bin/bash
# ========================================
# bootstrap.sh
# Setup db para prueba local del proyecto bq-sync. Necesario pues la app hará parte de una infraestructura y postgres se levanta con docker compose
#
# Uso:
#   ./bootstrap.sh \
#     --project-root ~/Documents/GoogleCloudProjects \
#     --compose-file docker-compose.yml \
#     --init-file init.sql \
# ========================================
set -euo pipefail

# ── Argumentos ───────────────────────────────────────────────
PROJECT_ROOT=""
COMPOSE_FILE_ARG=""
INIT_FILE_ARG=""

usage() {
    echo "Uso: ./bootstrap.sh"
    echo ""
    echo "  --project-root  Ruta raíz del proyecto de infraestructura (requerido)"
    echo "  --compose-file  Nombre del compose file (default: docker-compose.yml)"
    echo "  --init-file     Nombre del script de creación sql (default: init.sql)"
    exit 1
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --project-root) PROJECT_ROOT="$2"; shift 2 ;;
        --compose-file) COMPOSE_FILE_ARG="$2"; shift 2 ;;
        --init-file)    INIT_FILE_ARG="$2"; shift 2 ;;
        *) echo "Argumento desconocido: $1"; usage ;;
    esac
done

[ -z "$PROJECT_ROOT" ] && { echo "✗ --project-root es requerido"; usage; }

# ── Variables derivadas ───────────────────────────────────────
COMPOSE_FILE="${PROJECT_ROOT}/${COMPOSE_FILE_ARG:-docker-compose.yml}"
INIT_SQL="${PROJECT_ROOT}/templates/gci/${INIT_FILE_ARG:-init.sql}"
BASE_PATH="$PROJECT_ROOT/gci-companies/gci-base/bq-sync-base"

# ── Variables cargadas desde env ──────────────────────────────
source .env
set -o allexport

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
POSTGRES_GCI_PORT=$DB_PORT docker compose -f "$COMPOSE_FILE" up -d postgres-gci

log "Esperando a que Postgres esté listo..."
until docker exec postgres-gci pg_isready -U "$DB_USER" >/dev/null 2>&1; do
    echo "  esperando..."
    sleep 2
done
ok "Postgres listo"

# ── Base de datos ─────────────────────────────────────────────
log "Creando base de datos '$DB_NAME'..."
DB_EXISTS=$(docker exec postgres-gci psql -U "$DB_USER" -tAc \
    "SELECT 1 FROM pg_database WHERE datname='$DB_NAME'")

if [ "$DB_EXISTS" = "1" ]; then
    ok "Base de datos '$DB_NAME' ya existe"
else
    docker exec postgres-gci psql -U "$DB_USER" -c "CREATE DATABASE $DB_NAME"
    ok "Base de datos '$DB_NAME' creada"
fi

# ── Init SQL ─────────────────────────────────────────────────
log "Ejecutando init.sql..."
docker exec -i postgres-gci psql -U "$DB_USER" -d "$DB_NAME" < "$INIT_SQL"
ok "init.sql ejecutado"

# ── Carga de datos ─────────────────────────────────────────────────
log "Cargando datos iniciales..."
"$BASE_PATH/seed_db.sh" \
  --db-host "$DB_HOST" \
  --db-user "$DB_USER" \
  --db-name "$DB_NAME" \
  --data-folder "${PROJECT_ROOT}/templates/gci/data"

# ── Carga de configuración ───────────────────────────────────
log "Carga manual de configuración es requerida"
CONFIG_DIR="$BASE_PATH/app/config"

# ── Carga de credenciales ───────────────────────────────────
log "Carga manual de credenciales es requerida"
CRED_DIR="$BASE_PATH/app/credentials"


# ── Fin ───────────────────────────────────────────────────────
echo -e "\n\033[1;32m✓ Bootstrap completado\033[0m"
echo "  DB:           $DB_NAME"
echo "  DB user:      $DB_USER"
echo "  Project root: $PROJECT_ROOT"
echo "    "
echo "  Siguientes pasos:"
echo "    1. Cargar configuración"
echo "    2. Cargar credenciales"
echo "    3. Modificar .env (¡SOLO si la app se ejecuta en LOCAL!) ->  DB_HOST=localhost"
echo "    4. Ejecutar app: cd app && python3.12 main.py"