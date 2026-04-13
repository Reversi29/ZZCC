"""
Centralized config using pydantic-settings.
All env vars are typed, validated, and documented here.
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class NebulaSettings(BaseSettings):
    """NebulaGraph connection settings."""
    model_config = SettingsConfigDict(env_prefix="NEBULA_")

    host: str = Field(default="124.223.47.167", description="NebulaGraph server host")
    port: int = Field(default=9669, ge=1, le=65535, description="NebulaGraph server port")
    user: str = Field(default="root", description="NebulaGraph username")
    password: str = Field(default="nebula", description="NebulaGraph password")
    pool_size: int = Field(default=10, ge=1, description="Connection pool size")


class DatabaseSettings(BaseSettings):
    """Postgres (KnowledgeTable) connection settings."""
    model_config = SettingsConfigDict(env_prefix="KT_DB_")

    user: str = Field(default="ktuser", description="Postgres user")
    password: str = Field(default="ktpass", description="Postgres password")
    name: str = Field(default="ktdb", description="Postgres database name")
    host: str = Field(default="db", description="Postgres host (docker service name)")
    port: int = Field(default=5432, ge=1, le=65535, description="Postgres port")
    min_pool: int = Field(default=2, ge=1, description="Min pool connections")
    max_pool: int = Field(default=10, ge=1, description="Max pool connections")

    @property
    def dsn(self) -> str:
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"


class RedisSettings(BaseSettings):
    """Redis connection settings."""
    model_config = SettingsConfigDict(env_prefix="KT_REDIS_")

    host: str = Field(default="redis", description="Redis host (docker service name)")
    port: int = Field(default=6379, ge=1, le=65535, description="Redis port")
    db: int = Field(default=0, ge=0, description="Redis database number")
    password: str | None = Field(default=None, description="Redis password")

    @property
    def url(self) -> str:
        auth = f":{self.password}@" if self.password else ""
        return f"redis://{auth}{self.host}:{self.port}/{self.db}"


class APISettings(BaseSettings):
    """API-level settings."""
    model_config = SettingsConfigDict(env_prefix="")

    api_key: str = Field(default="", description="X-API-Key secret. Empty = auth disabled")
    api_version: str = Field(default="1", description="API version string")
    api_key_header: str = Field(default="X-API-Key", description="HTTP header for API key")
    # CORS
    cors_origins: List[str] = Field(
        default=["*"],
        description="Allowed CORS origins (list or '*')",
    )
    cors_allow_credentials: bool = Field(
        default=True,
        description="Allow credentials in CORS",
    )
    cors_allow_methods: List[str] = Field(
        default=["*"],
        description="Allowed HTTP methods",
    )
    cors_allow_headers: List[str] = Field(
        default=["*"],
        description="Allowed HTTP headers",
    )
    # Rate limiting
    rate_limit_enabled: bool = Field(
        default=True,
        description="Enable rate limiting middleware",
    )
    rate_limit_requests: int = Field(
        default=60,
        ge=1,
        description="Max requests per rate_limit_window_seconds",
    )
    rate_limit_window_seconds: int = Field(
        default=60,
        ge=1,
        description="Rate limit window in seconds",
    )
    # Slow API threshold
    slow_request_threshold_ms: int = Field(
        default=3000,
        ge=0,
        description="Log requests slower than this (ms). 0 = disabled.",
    )


class AppSettings(BaseSettings):
    """Root settings — compose all sub-settings."""
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    nebula: NebulaSettings = Field(default_factory=NebulaSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    api: APISettings = Field(default_factory=APISettings)

    # App metadata
    app_name: str = Field(default="NebulaGraph Interface")
    app_description: str = Field(
        default="NebulaGraph interface service with optional API-key auth",
    )
    debug: bool = Field(default=False, description="Enable debug mode (verbose logs, etc.)")

    @property
    def api_key_set(self) -> bool:
        return bool(self.api.api_key)


@lru_cache
def get_settings() -> AppSettings:
    """Singleton — parsed once, cached for the process lifetime."""
    return AppSettings()
