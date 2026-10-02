from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from nestris_ltm.config import DatabaseSettings, load_settings


def test_defaults_without_config_file(tmp_path: Path) -> None:
    settings = load_settings(tmp_path / "missing.toml")
    assert settings.database.name == "nestrisltm"
    assert settings.mqtt.topic_prefix == "retroverse/nestris"
    assert settings.http.port == 7990


def test_toml_file_and_env_precedence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = tmp_path / "config.toml"
    config.write_text(
        '[database]\nhost = "db.local"\nport = 6543\n[http]\nport = 8080\n', encoding="utf-8"
    )
    monkeypatch.setenv("NESTRIS_LTM__HTTP__PORT", "9090")

    settings = load_settings(config)

    assert settings.database.host == "db.local"
    assert settings.database.port == 6543
    assert settings.http.port == 9090  # env beats the file


def test_unknown_key_is_rejected(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text("typo_section = 1\n", encoding="utf-8")
    with pytest.raises(ValidationError):
        load_settings(config)


@pytest.mark.parametrize("name", ['x"; DROP DATABASE y; --', "1abc", "with-dash", ""])
def test_database_name_must_be_identifier(name: str) -> None:
    with pytest.raises(ValidationError):
        DatabaseSettings(name=name)


def test_database_url_hides_nothing_but_builds() -> None:
    url = DatabaseSettings(password="s3cret", name="abc").url()  # type: ignore[arg-type]
    assert url.drivername == "postgresql+asyncpg"
    assert url.database == "abc"
    assert url.password == "s3cret"
    assert "s3cret" not in repr(DatabaseSettings(password="s3cret"))  # type: ignore[arg-type]
