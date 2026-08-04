#!/usr/bin/env python3
"""
migrate_sqlite_to_mariadb.py
一次性脚本：将 SQLite 数据迁移到 MariaDB。
运行前提：pymysql 已安装，MariaDB zzcc_oa 库已存在（0张表状态）。
"""
import sqlite3, pymysql, logging
from datetime import datetime, date

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("migrate")

SRC = "data/zzcc_oa.db"
DST = "mysql+pymysql://root:zzcc_oa_2024@127.0.0.1:3307/zzcc_oa"

# 跳过的表（schema 差异或无数据）
SKIP_TABLES = {"sqlite_sequence", "counters"}


def _serialize(val):
    """把 Python 值转成 MariaDB INSERT 兼容格式"""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.isoformat()
    if isinstance(val, date):
        return val.isoformat()
    if isinstance(val, (int, float)):
        return val
    return str(val)


def migrate():
    src = sqlite3.connect(SRC)
    dst = pymysql.connect(
        host="127.0.0.1", port=3307,
        user="root", password="zzcc_oa_2024",
        database="zzcc_oa", charset="utf8mb4", autocommit=False,
    )

    cur_src = src.cursor()
    cur_dst = dst.cursor()

    tables = [r[0] for r in
              src.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
              if r[0] not in SKIP_TABLES]

    total = 0
    for tbl in tables:
        cur_src.execute(f"SELECT * FROM [{tbl}]")
        rows = cur_src.fetchall()
        cols = [d[0] for d in cur_src.description]

        if not rows:
            log.info(f"  {tbl}: 0 rows — skip")
            continue

        placeholders = ", ".join(["%s"] * len(cols))
        insert_sql = f"INSERT IGNORE INTO `{tbl}` ({', '.join(cols)}) VALUES ({placeholders})"
        inserted = 0
        for row in rows:
            try:
                cur_dst.execute(insert_sql, [_serialize(v) for v in row])
                inserted += cur_dst.rowcount
            except Exception as e:
                log.warning(f"  [{tbl}] 跳过行 {row[:2]}... : {e}")
        dst.commit()
        log.info(f"  {tbl}: {inserted}/{len(rows)} 行迁移")
        total += inserted

    src.close()
    cur_dst.close()
    dst.close()
    log.info(f"\n迁移完成，共 {total} 行。")


if __name__ == "__main__":
    migrate()
