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

# Genera il file di configurazione usando envsubst
export DB_HOST="${DB_HOST:-db}"
export DB_PORT="${DB_PORT:-5432}"
export POSTGRES_USER="${POSTGRES_USER:-odoo}"
export POSTGRES_DB="${POSTGRES_DB:-vo_demo}"

envsubst < "$TEMPLATE" > "$OUTPUT"

echo "Generato: $OUTPUT"
