"""ZZCC OA — 配置管理（对齐 ERPNext env conventions）"""
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    APP_NAME: str = "ZZCC OA System"
    APP_VERSION: str = "v15"
    DEBUG: bool = True

    # Database — SQLite 本地文件（开发用），可切换 MySQL/PostgreSQL
    DB_URL: str = "sqlite:///./zzcc_oa.db"

    # ERPNext 兼容 API Key
    API_KEY: str = "zzcc_oadev_key_2024"
    API_SECRET: str = "zzcc_oadev_secret_2024"

    # AI 服务
    OPENAI_API_KEY: str = ""
    LLM_MODEL: str = "gpt-4o-mini"

    # Redis（可选，用于缓存）
    REDIS_URL: str = "redis://localhost:6379/0"

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()
