#!/usr/bin/env python3
"""Genera config/odoo.conf dal template sostituendo le variabili d'ambiente.

A differenza di sed, questo script gestisce correttamente password con
caratteri speciali come | & \\ $ etc.

Legge `.env` da sé (senza interpolare `$` e senza tagliare `#` nei valori),
così Make non deve fare `-include .env` con `export`.

I valori con `$` vanno tra apici singoli (`POSTGRES_PASSWORD='p$ss#w0rd'`):
Docker Compose interpola `$` se il valore è senza virgolette o tra virgolette
doppie. Questo parser toglie gli apici singoli e tiene il valore letterale,
allineato a Compose.
"""

import os
import sys
from collections.abc import MutableMapping
from pathlib import Path


class DotenvError(ValueError):
    """File `.env` non allineato a Docker Compose."""


DEFAULTS = {
    "DB_HOST": "db",
    "DB_PORT": "5432",
    "POSTGRES_USER": "odoo",
    "POSTGRES_DB": "vo_demo",
}


def env_file_path(project_dir: Path) -> Path:
    """Percorso del `.env`: ``VO_ENV_FILE`` se impostata, altrimenti ``project_dir/.env``."""
    override = os.environ.get("VO_ENV_FILE")
    if override is not None:
        return Path(override)
    return project_dir / ".env"


def load_dotenv(path: Path, environ: MutableMapping[str, str] | None = None) -> None:
    """Carica KEY=VALUE da ``path`` senza interpolare `$`.

    I commenti `#` valgono solo a inizio riga o dopo uno spazio in un valore
    non quotato. I valori con `$` devono usare apici singoli, come Compose.
    Non sovrascrive chiavi già presenti.
    """
    env = os.environ if environ is None else environ
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key or key in env:
            continue
        value = value.strip()
        quote = ""
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            quote = value[0]
            value = value[1:-1]
        else:
            value = _unquoted_env_value(value)
        if "$" in value and quote != "'":
            if quote == '"':
                raise DotenvError(
                    f"{key} usa virgolette doppie e contiene $. "
                    "Docker Compose interpola $. Usare apici singoli, "
                    f"es. {key}='...'"
                )
            raise DotenvError(
                f"{key} contiene $ senza apici singoli. "
                "Docker Compose interpola $. "
                f"Usare {key}='...'"
            )
        env[key] = value


def _unquoted_env_value(value: str) -> str:
    """Mantiene `#` attaccato al valore; taglia solo un commento dopo uno spazio."""
    for index, char in enumerate(value):
        if char == "#" and (index == 0 or value[index - 1].isspace()):
            return value[:index].rstrip()
    return value


def _reject_control_chars(name: str, value: str) -> bool:
    if any(ord(c) < 32 or ord(c) == 127 for c in value):
        print(
            f"Errore: il valore di {name} contiene caratteri di controllo",
            file=sys.stderr,
        )
        return True
    return False


def write_secure(path: Path, content: str) -> None:
    """Crea o sovrascrive ``path`` con permessi 0o600 fin dall'apertura."""
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    fd = os.open(path, flags, 0o600)
    try:
        os.fchmod(fd, 0o600)
        os.write(fd, content.encode("utf-8"))
    finally:
        os.close(fd)


def main() -> int:
    script_dir = Path(__file__).parent
    project_dir = script_dir.parent
    args = sys.argv[1:]
    get_key: str | None = None
    if "--get" in args:
        index = args.index("--get")
        if index + 1 >= len(args) or args[index + 1].startswith("--"):
            print("Errore: --get richiede un nome di variabile", file=sys.stderr)
            return 1
        get_key = args[index + 1]

    try:
        load_dotenv(env_file_path(project_dir))
    except DotenvError as exc:
        print(f"Errore: {exc}", file=sys.stderr)
        return 1

    if get_key:
        print(os.environ.get(get_key) or DEFAULTS.get(get_key, ""))
        return 0

    check_only = "--check" in args

    template_path = project_dir / "config" / "odoo.conf.template"
    output_path = project_dir / "config" / "odoo.conf"

    postgres_password = os.environ.get("POSTGRES_PASSWORD")
    if not postgres_password:
        print("Errore: POSTGRES_PASSWORD non definita", file=sys.stderr)
        return 1

    odoo_admin_password = os.environ.get("ODOO_ADMIN_PASSWORD")
    if not odoo_admin_password:
        print("Errore: ODOO_ADMIN_PASSWORD non definita", file=sys.stderr)
        return 1

    db_host = os.environ.get("DB_HOST", DEFAULTS["DB_HOST"])
    db_port = os.environ.get("DB_PORT", DEFAULTS["DB_PORT"])
    postgres_user = os.environ.get("POSTGRES_USER", DEFAULTS["POSTGRES_USER"])
    postgres_db = os.environ.get("POSTGRES_DB", DEFAULTS["POSTGRES_DB"])

    values = (
        ("POSTGRES_PASSWORD", postgres_password),
        ("ODOO_ADMIN_PASSWORD", odoo_admin_password),
        ("DB_HOST", db_host),
        ("DB_PORT", db_port),
        ("POSTGRES_USER", postgres_user),
        ("POSTGRES_DB", postgres_db),
    )
    if any(_reject_control_chars(name, value) for name, value in values):
        return 1

    if check_only:
        return 0

    if not template_path.exists():
        print(f"Errore: template non trovato: {template_path}", file=sys.stderr)
        return 1

    template_content = template_path.read_text()

    # Usa sostituzione manuale per evitare problemi con caratteri speciali
    config_content = template_content
    config_content = config_content.replace("${DB_HOST:-db}", db_host)
    config_content = config_content.replace("${DB_PORT:-5432}", db_port)
    config_content = config_content.replace("${POSTGRES_USER:-odoo}", postgres_user)
    config_content = config_content.replace("${POSTGRES_PASSWORD}", postgres_password)
    config_content = config_content.replace("${POSTGRES_DB:-vo_demo}", postgres_db)
    config_content = config_content.replace("${ODOO_ADMIN_PASSWORD}", odoo_admin_password)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_secure(output_path, config_content)

    print(f"Generato: {output_path} (permessi: 600)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
