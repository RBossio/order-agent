"""Test per la gestione sicura dei segreti Odoo."""

import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent.parent / "scripts"


def _run_generate_script(project_dir: Path) -> subprocess.CompletedProcess[str]:
    """Esegue una copia di generate_odoo_conf.py puntata a ``project_dir``."""
    script_content = (SCRIPTS_DIR / "generate_odoo_conf.py").read_text()
    script_content = script_content.replace(
        "project_dir = script_dir.parent",
        f'project_dir = Path("{project_dir}")',
    )
    script_path = project_dir / "generate_odoo_conf.py"
    script_path.write_text(script_content)
    return subprocess.run(
        [sys.executable, str(script_path)],
        capture_output=True,
        text=True,
        cwd=project_dir,
        check=False,
    )


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

        result = _run_generate_script(temp_config_dir)

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

        result = _run_generate_script(temp_config_dir)

        assert result.returncode == 0, f"Script failed: {result.stderr}"

        output_file = temp_config_dir / "config" / "odoo.conf"
        content = output_file.read_text()

        # Verifica che i caratteri speciali siano preservati
        assert f"db_password = {special_password}" in content
        assert "admin_passwd = admin|test&pass" in content

    def test_reads_dollar_and_hash_from_dotenv(
        self, temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Password con `$` e `#` restano intatte se lette da `.env`, non da Make."""
        monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)
        monkeypatch.delenv("ODOO_ADMIN_PASSWORD", raising=False)
        (temp_config_dir / ".env").write_text(
            "POSTGRES_PASSWORD=p$ss#w0rd\nODOO_ADMIN_PASSWORD=adm$in#123\n",
            encoding="utf-8",
        )

        result = _run_generate_script(temp_config_dir)

        assert result.returncode == 0, f"Script failed: {result.stderr}"
        content = (temp_config_dir / "config" / "odoo.conf").read_text()
        assert "db_password = p$ss#w0rd" in content
        assert "admin_passwd = adm$in#123" in content

    def test_rejects_newline_injection_in_password(
        self, temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Una password con `\\nlist_db = True` deve essere rifiutata."""
        monkeypatch.setenv("POSTGRES_PASSWORD", "test")
        monkeypatch.setenv("ODOO_ADMIN_PASSWORD", "secret\nlist_db = True")

        result = _run_generate_script(temp_config_dir)

        assert result.returncode == 1
        assert "ODOO_ADMIN_PASSWORD" in result.stderr
        assert "nuova riga" in result.stderr
        output_file = temp_config_dir / "config" / "odoo.conf"
        if output_file.exists():
            assert "list_db = True" not in output_file.read_text()

    def test_sets_restrictive_permissions(
        self, temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verifica che il file generato abbia permessi 600."""
        monkeypatch.setenv("POSTGRES_PASSWORD", "test")
        monkeypatch.setenv("ODOO_ADMIN_PASSWORD", "test")

        _run_generate_script(temp_config_dir)

        output_file = temp_config_dir / "config" / "odoo.conf"
        file_stat = output_file.stat()
        permissions = stat.S_IMODE(file_stat.st_mode)

        # Verifica permessi 600 (rw-------)
        assert permissions == 0o600, f"Expected 600, got {oct(permissions)}"

    def test_resecures_permissions_if_file_already_exists(
        self, temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Un odoo.conf già presente con 0644 viene riscritto a 0600 (fchmod)."""
        monkeypatch.setenv("POSTGRES_PASSWORD", "test")
        monkeypatch.setenv("ODOO_ADMIN_PASSWORD", "test")
        output_file = temp_config_dir / "config" / "odoo.conf"
        output_file.write_text("stale\n", encoding="utf-8")
        os.chmod(output_file, 0o644)

        result = _run_generate_script(temp_config_dir)

        assert result.returncode == 0, f"Script failed: {result.stderr}"
        permissions = stat.S_IMODE(output_file.stat().st_mode)
        assert permissions == 0o600, f"Expected 600, got {oct(permissions)}"
        assert "admin_passwd = test" in output_file.read_text()

    def test_fails_without_postgres_password(
        self, temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verifica errore se POSTGRES_PASSWORD mancante."""
        monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)
        monkeypatch.setenv("ODOO_ADMIN_PASSWORD", "test")

        result = _run_generate_script(temp_config_dir)

        assert result.returncode == 1
        assert "POSTGRES_PASSWORD" in result.stderr

    def test_fails_without_odoo_admin_password(
        self, temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verifica errore se ODOO_ADMIN_PASSWORD mancante."""
        monkeypatch.setenv("POSTGRES_PASSWORD", "test")
        monkeypatch.delenv("ODOO_ADMIN_PASSWORD", raising=False)

        result = _run_generate_script(temp_config_dir)

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
            check=False,
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
            check=False,
        )

        assert "non definita" in result.stderr.lower() or "not defined" in result.stderr.lower()
        assert "ODOO_BOT_PASSWORD" in result.stderr

    def test_exits_without_admin_login_password(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """La password di login admin non deve cadere sulla master password."""
        monkeypatch.setenv("ODOO_BOT_PASSWORD", "bot-secret")
        monkeypatch.setenv("ODOO_ADMIN_PASSWORD", "master-secret")
        monkeypatch.delenv("ODOO_ADMIN_LOGIN_PASSWORD", raising=False)

        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "seed_odoo.py")],
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 1
        assert "ODOO_ADMIN_LOGIN_PASSWORD" in result.stderr
        assert "ODOO_ADMIN_PASSWORD" in result.stderr


class TestSmokeTestAdminLoginPassword:
    """Test per ODOO_ADMIN_LOGIN_PASSWORD in smoke_test.py."""

    def test_exits_without_admin_login_password(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """smoke_test.py esce con codice 1 se manca la password di login admin."""
        monkeypatch.setenv("ODOO_ADMIN_PASSWORD", "master-secret")
        monkeypatch.delenv("ODOO_ADMIN_LOGIN_PASSWORD", raising=False)

        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "smoke_test.py")],
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 1
        assert "ODOO_ADMIN_LOGIN_PASSWORD" in result.stderr
        assert "ODOO_ADMIN_PASSWORD" in result.stderr
