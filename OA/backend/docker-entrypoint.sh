#!/bin/sh
# ZZCC OA 后端容器启动入口
# 1) 等待 MariaDB 就绪  2) 建表 + seed  3) 应用 schema 迁移  4) 启动 uvicorn
set -e

echo "等待数据库就绪..."
until python - <<'PY' 2>/dev/null
from database import engine
from sqlalchemy import text
with engine.connect() as c:
    c.execute(text("SELECT 1"))
PY
do
  echo "  数据库未就绪，2 秒后重试..."
  sleep 2
done
echo "✓ 数据库就绪"

echo "初始化数据库表结构 + 默认用户..."
python -c "from database import init_db; init_db()"

echo "应用 schema 迁移（幂等）..."
python scripts/db_migrate.py

echo "启动 OA 后端 (port 8003)..."
exec uvicorn main:app --host 0.0.0.0 --port 8003
