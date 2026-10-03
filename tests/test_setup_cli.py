"""``nestris-ltm configure``: merges into config.toml and refuses invalid values."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from nestris_ltm.__main__ import main


def test_configure_keeps_other_keys(tmp_path: Path) -> None:
    cfg = tmp_path / "config.toml"
    cfg.write_text('[mqtt]\ntopic_prefix = "x/y"\n\n[database]\nname = "keep"\n', encoding="utf-8")
    assert (
        main(["--config", str(cfg), "configure", "--db-password", "pw", "--db-port", "5433"]) == 0
    )
    data = tomllib.loads(cfg.read_text(encoding="utf-8"))
    assert data["database"] == {"name": "keep", "password": "pw", "port": 5433}
    assert data["mqtt"]["topic_prefix"] == "x/y"


def test_configure_rejects_invalid_values(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cfg = tmp_path / "config.toml"
    cfg.write_text('[database]\nname = "keep"\n', encoding="utf-8")
    assert main(["--config", str(cfg), "configure", "--db-name", "bad name; drop"]) == 2
    assert "Invalid settings" in capsys.readouterr().err
    assert tomllib.loads(cfg.read_text(encoding="utf-8")) == {"database": {"name": "keep"}}


def test_configure_creates_missing_file(tmp_path: Path) -> None:
    cfg = tmp_path / "sub" / "config.toml"
    assert main(["--config", str(cfg), "configure", "--http-port", "8000"]) == 0
    assert tomllib.loads(cfg.read_text(encoding="utf-8")) == {"http": {"port": 8000}}
