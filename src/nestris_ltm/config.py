"""Application settings.

Sources, later wins: built-in defaults, the TOML config file, environment
variables (``NESTRIS_LTM__<SECTION>__<KEY>``), explicit keyword arguments.

The config file defaults to ``%APPDATA%\\NestrisLTM\\config.toml`` and can be
moved with the ``NESTRIS_LTM_CONFIG`` environment variable.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import ClassVar, Literal

from pydantic import BaseModel, Field, SecretStr, field_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    TomlConfigSettingsSource,
)
from sqlalchemy.engine import URL

APP_NAME = "NestrisLTM"
_DB_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")


def default_data_dir() -> Path:
    """Per-user data directory (config, logs, local state)."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / APP_NAME


def default_config_path() -> Path:
    override = os.environ.get("NESTRIS_LTM_CONFIG")
    return Path(override) if override else default_data_dir() / "config.toml"


class DatabaseSettings(BaseModel):
    host: str = "127.0.0.1"
    port: int = Field(default=5432, ge=1, le=65535)
    user: str = "postgres"
    password: SecretStr = SecretStr("")
    name: str = "nestrisltm"
    pool_size: int = Field(default=10, ge=1)
    connect_timeout_s: float = Field(default=5.0, gt=0)

    @field_validator("name")
    @classmethod
    def _valid_identifier(cls, value: str) -> str:
        # The name is interpolated into CREATE DATABASE, so keep it a plain identifier.
        if not _DB_NAME_RE.match(value):
            raise ValueError("database name must be a plain identifier ([A-Za-z_][A-Za-z0-9_]*)")
        return value

    def url(self, database: str | None = None) -> URL:
        return URL.create(
            "postgresql+asyncpg",
            username=self.user,
            password=self.password.get_secret_value() or None,
            host=self.host,
            port=self.port,
            database=database or self.name,
        )


class MqttSettings(BaseModel):
    enabled: bool = True
    host: str = "127.0.0.1"
    port: int = Field(default=1883, ge=1, le=65535)
    username: str | None = None
    password: SecretStr | None = None
    topic_prefix: str = "retroverse/nestris"
    # A fixed client id plus a persistent session lets the broker queue QoS 1
    # events while the host is down.
    client_id: str = "nestris-ltm-host"
    keepalive_s: int = Field(default=30, ge=5)
    reconnect_max_s: float = Field(default=30.0, ge=1)


class HttpSettings(BaseModel):
    host: str = "0.0.0.0"
    port: int = Field(default=7990, ge=1, le=65535)


class LogSettings(BaseModel):
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    to_file: bool = True
    buffer_size: int = Field(default=2000, ge=100)


class UpdateSettings(BaseModel):
    """Update checks against GitHub releases (docs/UPDATES.md)."""

    enabled: bool = True  # automatic checks; installing is always a click
    channel: Literal["stable", "beta"] = "stable"
    owner: str = "oe7set"
    repo: str = "nestris-ltm"
    token: SecretStr = SecretStr("")  # optional, for private repos / rate limits
    check_interval_h: float = Field(default=24.0, ge=1)
    # Empty = find pg_dump.exe of the local PostgreSQL installation.
    pg_dump: str = ""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="NESTRIS_LTM__",
        env_nested_delimiter="__",
        extra="forbid",
    )

    # Set by load_settings() before instantiation; read by the TOML source.
    config_file: ClassVar[Path | None] = None

    data_dir: Path = Field(default_factory=default_data_dir)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    mqtt: MqttSettings = Field(default_factory=MqttSettings)
    http: HttpSettings = Field(default_factory=HttpSettings)
    log: LogSettings = Field(default_factory=LogSettings)
    updates: UpdateSettings = Field(default_factory=UpdateSettings)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        sources: list[PydanticBaseSettingsSource] = [init_settings, env_settings]
        if cls.config_file is not None and cls.config_file.is_file():
            sources.append(TomlConfigSettingsSource(settings_cls, toml_file=cls.config_file))
        return tuple(sources)

    @property
    def log_dir(self) -> Path:
        return self.data_dir / "logs"


def load_settings(config_file: Path | None = None, **overrides: object) -> Settings:
    """Load settings from ``config_file`` (default location if ``None``)."""
    Settings.config_file = config_file if config_file is not None else default_config_path()
    return Settings(**overrides)  # type: ignore[arg-type]
