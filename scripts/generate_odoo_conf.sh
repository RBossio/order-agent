#!/bin/bash
# Genera config/odoo.conf dal template sostituendo le variabili d'ambiente
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
TEMPLATE="$PROJECT_DIR/config/odoo.conf.template"
OUTPUT="$PROJECT_DIR/config/odoo.conf"

if [[ ! -f "$TEMPLATE" ]]; then
    echo "Errore: template non trovato: $TEMPLATE" >&2
    exit 1
fi

# Verifica variabili obbligatorie
if [[ -z "$POSTGRES_PASSWORD" ]]; then
    echo "Errore: POSTGRES_PASSWORD non definita" >&2
    exit 1
fi

if [[ -z "$ODOO_ADMIN_PASSWORD" ]]; then
    echo "Errore: ODOO_ADMIN_PASSWORD non definita" >&2
    exit 1
fi

# Valori di default
DB_HOST="${DB_HOST:-db}"
DB_PORT="${DB_PORT:-5432}"
POSTGRES_USER="${POSTGRES_USER:-odoo}"
POSTGRES_DB="${POSTGRES_DB:-vo_demo}"

# Genera il file di configurazione usando sed
sed -e "s|\${DB_HOST:-db}|$DB_HOST|g" \
    -e "s|\${DB_PORT:-5432}|$DB_PORT|g" \
    -e "s|\${POSTGRES_USER:-odoo}|$POSTGRES_USER|g" \
    -e "s|\${POSTGRES_PASSWORD}|$POSTGRES_PASSWORD|g" \
    -e "s|\${POSTGRES_DB:-vo_demo}|$POSTGRES_DB|g" \
    -e "s|\${ODOO_ADMIN_PASSWORD}|$ODOO_ADMIN_PASSWORD|g" \
    "$TEMPLATE" > "$OUTPUT"

echo "Generato: $OUTPUT"
