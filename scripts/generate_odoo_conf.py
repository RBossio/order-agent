#!/usr/bin/env python3
"""Genera config/odoo.conf dal template sostituendo le variabili d'ambiente.

A differenza di sed, questo script gestisce correttamente password con
caratteri speciali come | & \\ $ etc.
"""

import os
import stat
import sys
from pathlib import Path


def main() -> int:
    script_dir = Path(__file__).parent
    project_dir = script_dir.parent
    template_path = project_dir / "config" / "odoo.conf.template"
    output_path = project_dir / "config" / "odoo.conf"

    if not template_path.exists():
        print(f"Errore: template non trovato: {template_path}", file=sys.stderr)
        return 1

    # Verifica variabili obbligatorie
    postgres_password = os.environ.get("POSTGRES_PASSWORD")
    if not postgres_password:
        print("Errore: POSTGRES_PASSWORD non definita", file=sys.stderr)
        return 1

    odoo_admin_password = os.environ.get("ODOO_ADMIN_PASSWORD")
    if not odoo_admin_password:
        print("Errore: ODOO_ADMIN_PASSWORD non definita", file=sys.stderr)
        return 1

    # Valori con default
    db_host = os.environ.get("DB_HOST", "db")
    db_port = os.environ.get("DB_PORT", "5432")
    postgres_user = os.environ.get("POSTGRES_USER", "odoo")
    postgres_db = os.environ.get("POSTGRES_DB", "vo_demo")

    # Leggi template e sostituisci
    template_content = template_path.read_text()

    # Usa sostituzione manuale per evitare problemi con caratteri speciali
    config_content = template_content
    config_content = config_content.replace("${DB_HOST:-db}", db_host)
    config_content = config_content.replace("${DB_PORT:-5432}", db_port)
    config_content = config_content.replace("${POSTGRES_USER:-odoo}", postgres_user)
    config_content = config_content.replace("${POSTGRES_PASSWORD}", postgres_password)
    config_content = config_content.replace("${POSTGRES_DB:-vo_demo}", postgres_db)
    config_content = config_content.replace("${ODOO_ADMIN_PASSWORD}", odoo_admin_password)

    # Scrivi file con permessi restrittivi (600)
    output_path.write_text(config_content)
    os.chmod(output_path, stat.S_IRUSR | stat.S_IWUSR)  # 600

    print(f"Generato: {output_path} (permessi: 600)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
