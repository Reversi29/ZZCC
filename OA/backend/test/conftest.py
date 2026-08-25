import pytest
"""test/conftest.py — pytest fixtures"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 测试环境关闭 API 限流（TestClient 所有请求共享同一 IP，全量跑易触发 429）
os.environ["RATELIMIT_ENABLED"] = "false"
# 生产启动守卫需要这些环境变量，测试环境统一覆盖
os.environ["API_KEY"] = "zzcc_oadev_key_2024"
os.environ["API_SECRET"] = "zzcc_oadev_key_2024"
os.environ["JWT_SECRET_KEY"] = "test-jwt-secret-key-32chars-plus"
os.environ["PASSWORD_SALT_HEX"] = "7a7a63632d6f612d73616c74"
os.environ["OAUTH_CLIENT_ID"] = "zzcc-oa-test-client"
os.environ["OAUTH_CLIENT_SECRET"] = "zzcc-oa-test-secret"
# 必须在 import database 之前设置（database.py 在模块加载时就创建 engine）
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from database import Base, get_db
from main import app
from routers.auth import create_access_token, _hash_pw
import database as db_module

# ── Test DB: in-memory SQLite (isolated per test) ──────────────
TEST_URL = "sqlite:///:memory:"

test_engine = create_engine(
    TEST_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

# Override get_db to use test DB
def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[db_module.get_db] = override_get_db

# Re-create tables for each test session
@pytest.fixture(scope="function")
def db():
    """每个测试独立的 DB session（函数级）"""
    Base.metadata.create_all(bind=test_engine)
    db = TestingSessionLocal()
    # Seed admin user
    from database import User
    db.add(User(
        username="admin",
        hashed_password=_hash_pw("admin123"),
        display_name="管理员",
        role="admin",
    ))
    db.add(User(
        username="alice",
        hashed_password=_hash_pw("pass01"),
        display_name="张三",
        role="user",
    ))
    db.add(User(
        username="user01",
        hashed_password=_hash_pw("pass01"),
        display_name="李四",
        role="user",
    ))
    db.commit()
    yield db
    db.rollback()
    db.close()
    Base.metadata.drop_all(bind=test_engine)  # clean up

@pytest.fixture(scope="function")
def client(db):
    """每个测试独立的 TestClient"""
    with TestClient(app) as c:
        yield c

@pytest.fixture(scope="function")
def admin_token():
    """Admin JWT fixture"""
    return create_access_token("admin", "管理员", "admin")

@pytest.fixture(scope="function")
def auth_headers(admin_token):
    """Admin auth headers"""
    return {"Authorization": f"Bearer {admin_token}"}

@pytest.fixture
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}

@pytest.fixture
def user_headers(user_token):
    return {"Authorization": f"Bearer {user_token}"}

@pytest.fixture(scope="function")
def api_key_headers():
    """X-API-Key headers (backward compat)"""
    return {"X-API-Key": "zzcc_oadev_key_2024"}

@pytest.fixture(scope="function")
def user_token():
    """普通用户（role=user）JWT fixture"""
    return create_access_token("alice", "张三", "user")

@pytest.fixture(scope="function")
def user_headers(user_token):
    """普通用户 auth headers"""
    return {"Authorization": f"Bearer {user_token}"}
