"""ZZCC OA — 配置管理（对齐 ERPNext env conventions）

所有敏感配置均从环境变量读取（.env），禁止硬编码默认值到业务代码。
Secrets: DATABASE_URL, JWT_SECRET_KEY, PASSWORD_SALT_HEX, API_KEY, API_SECRET
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    APP_NAME: str = "ZZCC OA System"
    APP_VERSION: str = "v15"
    DEBUG: bool = True

    # ── 数据库 ────────────────────────────────────────────────────
    # 生产：mysql+pymysql://USER:PASS@HOST:PORT/DB
    # 开发：sqlite:///./data/zzcc_oa.db
    DATABASE_URL: str = "sqlite:///./data/zzcc_oa.db"

    # ── JWT / 密码哈希（生产必须改）───────────────────────────────
    # JWT 签名密钥（>= 32 字符随机串）
    JWT_SECRET_KEY: str = "CHANGE_ME_USE_32_PLUS_CHARS_RANDOM_SECRET"
    # 密码哈希盐，hex 编码的 bytes（任意长度，生产建议 >= 16 字节）
    PASSWORD_SALT_HEX: str = "7a7a63632d6f612d73616c74"

    # ── API Key ──────────────────────────────────────────────────
    API_KEY: str = "CHANGE_ME_API_KEY"
    API_SECRET: str = "CHANGE_ME_API_SECRET"

    # ── AI 服务 ──────────────────────────────────────────────────
    OPENAI_API_KEY: str = ""
    LLM_MODEL: str = "gpt-4o-mini"

    # ── Redis（可选）─────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"

    # ── Casdoor OIDC（可选）──────────────────────────────────────
    OAUTH_CASDOOR_URL: str = "http://localhost:8004"
    OAUTH_CLIENT_ID: str = ""
    OAUTH_CLIENT_SECRET: str = ""
    OAUTH_REDIRECT_URI: str = "http://localhost:8003/api/auth/oidc/callback"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


_PRODUCTION_CHANGES = (
    "CHANGE_ME",
    "CHANGE_IN_PROD",
    "dev-secret",
    "CHANGE_ME_",
)


def _check_production_settings(s: Settings) -> None:
    """启动守卫：生产模式(DEBUG=false)下检测未改的占位符并拒绝启动"""
    if s.DEBUG:
        return  # 开发模式跳过
    issues = []
    for name, val in (
        ("JWT_SECRET_KEY", s.JWT_SECRET_KEY),
        ("API_KEY", s.API_KEY),
        ("API_SECRET", s.API_SECRET),
        ("DATABASE_URL", s.DATABASE_URL),
    ):
        if any(p in val.upper() for p in _PRODUCTION_CHANGES):
            issues.append(f"  {name}: 仍为默认值 '{val[:40]}'")
    if issues:
        raise RuntimeError(
            "\n\n⚠️  生产环境检测到未改的配置项，启动已拒绝。\n"
            "请修改 backend/.env 中的以下字段：\n"
            + "\n".join(issues)
            + "\n\n或设置 DEBUG=true 以开发模式启动。\n"
        )


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    _check_production_settings(s)
    return s
