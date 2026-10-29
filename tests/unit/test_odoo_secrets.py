"""Test per la gestione sicura dei segreti Odoo."""

import stat
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent.parent / "scripts"
CONFIG_DIR = Path(__file__).parent.parent.parent / "config"


class TestGenerateOdooConf:
    """Test per generate_odoo_conf.py."""

    @pytest.fixture
    def temp_config_dir(self, tmp_path: Path) -> Path:
        """Crea una directory temporanea con il template."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()

        template = config_dir / "odoo.conf.template"
        template.write_text(
            "[options]\n"
            "db_host = ${DB_HOST:-db}\n"
            "db_port = ${DB_PORT:-5432}\n"
            "db_user = ${POSTGRES_USER:-odoo}\n"
            "db_password = ${POSTGRES_PASSWORD}\n"
            "db_name = ${POSTGRES_DB:-vo_demo}\n"
            "admin_passwd = ${ODOO_ADMIN_PASSWORD}\n"
            "list_db = False\n"
        )
        return tmp_path

    def test_generates_config_with_simple_password(
        self, temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verifica generazione config con password semplice."""
        monkeypatch.setenv("POSTGRES_PASSWORD", "simple_password")
        monkeypatch.setenv("ODOO_ADMIN_PASSWORD", "admin123")

        # Copia lo script nella temp dir e modifica i path
        script_content = (SCRIPTS_DIR / "generate_odoo_conf.py").read_text()
        script_content = script_content.replace(
            'project_dir = script_dir.parent',
            f'project_dir = Path("{temp_config_dir}")'
        )

        script_path = temp_config_dir / "generate_odoo_conf.py"
        script_path.write_text(script_content)

        result = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True,
            text=True,
            cwd=temp_config_dir,
        )

        assert result.returncode == 0, f"Script failed: {result.stderr}"

        output_file = temp_config_dir / "config" / "odoo.conf"
        assert output_file.exists()

        content = output_file.read_text()
        assert "db_password = simple_password" in content
        assert "admin_passwd = admin123" in content

    def test_generates_config_with_special_characters_in_password(
        self, temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verifica generazione config con password contenente caratteri speciali."""
        # Password con caratteri che romperebbero sed: | & \\ $ ' "
        special_password = r"p@ss|w&rd\\with$pecial'chars\""
        monkeypatch.setenv("POSTGRES_PASSWORD", special_password)
        monkeypatch.setenv("ODOO_ADMIN_PASSWORD", "admin|test&pass")

        script_content = (SCRIPTS_DIR / "generate_odoo_conf.py").read_text()
        script_content = script_content.replace(
            'project_dir = script_dir.parent',
            f'project_dir = Path("{temp_config_dir}")'
        )

        script_path = temp_config_dir / "generate_odoo_conf.py"
        script_path.write_text(script_content)

        result = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True,
            text=True,
            cwd=temp_config_dir,
        )

        assert result.returncode == 0, f"Script failed: {result.stderr}"

        output_file = temp_config_dir / "config" / "odoo.conf"
        content = output_file.read_text()

        # Verifica che i caratteri speciali siano preservati
        assert f"db_password = {special_password}" in content
        assert "admin_passwd = admin|test&pass" in content

    def test_sets_restrictive_permissions(
        self, temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verifica che il file generato abbia permessi 600."""
        monkeypatch.setenv("POSTGRES_PASSWORD", "test")
        monkeypatch.setenv("ODOO_ADMIN_PASSWORD", "test")

        script_content = (SCRIPTS_DIR / "generate_odoo_conf.py").read_text()
        script_content = script_content.replace(
            'project_dir = script_dir.parent',
            f'project_dir = Path("{temp_config_dir}")'
        )

        script_path = temp_config_dir / "generate_odoo_conf.py"
        script_path.write_text(script_content)

        subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True,
            text=True,
            cwd=temp_config_dir,
        )

        output_file = temp_config_dir / "config" / "odoo.conf"
        file_stat = output_file.stat()
        permissions = stat.S_IMODE(file_stat.st_mode)

        # Verifica permessi 600 (rw-------)
        assert permissions == 0o600, f"Expected 600, got {oct(permissions)}"

    def test_fails_without_postgres_password(
        self, temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verifica errore se POSTGRES_PASSWORD mancante."""
        monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)
        monkeypatch.setenv("ODOO_ADMIN_PASSWORD", "test")

        script_content = (SCRIPTS_DIR / "generate_odoo_conf.py").read_text()
        script_content = script_content.replace(
            'project_dir = script_dir.parent',
            f'project_dir = Path("{temp_config_dir}")'
        )

        script_path = temp_config_dir / "generate_odoo_conf.py"
        script_path.write_text(script_content)

        result = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True,
            text=True,
            cwd=temp_config_dir,
        )

        assert result.returncode == 1
        assert "POSTGRES_PASSWORD" in result.stderr

    def test_fails_without_odoo_admin_password(
        self, temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verifica errore se ODOO_ADMIN_PASSWORD mancante."""
        monkeypatch.setenv("POSTGRES_PASSWORD", "test")
        monkeypatch.delenv("ODOO_ADMIN_PASSWORD", raising=False)

        script_content = (SCRIPTS_DIR / "generate_odoo_conf.py").read_text()
        script_content = script_content.replace(
            'project_dir = script_dir.parent',
            f'project_dir = Path("{temp_config_dir}")'
        )

        script_path = temp_config_dir / "generate_odoo_conf.py"
        script_path.write_text(script_content)

        result = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True,
            text=True,
            cwd=temp_config_dir,
        )

        assert result.returncode == 1
        assert "ODOO_ADMIN_PASSWORD" in result.stderr


class TestSeedOdooBotPassword:
    """Test per la verifica di ODOO_BOT_PASSWORD in seed_odoo.py."""

    def test_exits_without_bot_password(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verifica che seed_odoo.py esca con errore se ODOO_BOT_PASSWORD mancante."""
        # Rimuovi ODOO_BOT_PASSWORD se presente
        monkeypatch.delenv("ODOO_BOT_PASSWORD", raising=False)

        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "seed_odoo.py")],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 1
        assert "ODOO_BOT_PASSWORD" in result.stderr

    def test_error_message_is_clear(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verifica che il messaggio di errore sia chiaro."""
        monkeypatch.delenv("ODOO_BOT_PASSWORD", raising=False)

        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "seed_odoo.py")],
            capture_output=True,
            text=True,
        )

        assert "non definita" in result.stderr.lower() or "not defined" in result.stderr.lower()
        assert "ODOO_BOT_PASSWORD" in result.stderr
