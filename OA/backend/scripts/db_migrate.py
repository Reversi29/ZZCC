"""
应用 schema 迁移（幂等）。

补齐 ORM model 与生产数据库之间的列差异。语句使用
`ADD COLUMN IF NOT EXISTS`，因此对全新库（create_all 已建好）与
已有库都能安全重复执行。

由 docker-entrypoint.sh 在容器启动时调用；也可手动执行：
    python scripts/db_migrate.py
"""
import os
import sys

# 允许以脚本方式直接运行（python scripts/db_migrate.py）时也能 import 到 /app 下的模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text

from database import engine

SQL_PATH = os.path.join(os.path.dirname(__file__), "..", "sql", "001_schema_fixes.sql")


def run_migrations() -> int:
    with open(SQL_PATH, "r", encoding="utf-8") as f:
        statements = [s.strip() for s in f.read().split(";") if s.strip()]
    with engine.begin() as conn:
        for stmt in statements:
            conn.execute(text(stmt))
    print(f"✓ schema 迁移完成（{len(statements)} 条语句）")
    return len(statements)


if __name__ == "__main__":
    run_migrations()
