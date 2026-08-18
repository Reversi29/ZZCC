#!/usr/bin/env python3
"""ZZCC OA — 数据库备份脚本（P4.18）

支持 MariaDB（生产）和 SQLite（开发）。

用法：
  python scripts/backup.py                    # 备份到 backups/ 目录
  python scripts/backup.py --restore 2026-08-17-143022  # 从备份恢复
  python scripts/backup.py --list             # 列出可用备份

依赖：
  - MariaDB: mysqldump（需在 PATH 中）
  - SQLite:  sqlite3 或 Python sqlite3（内置）
"""
import argparse, os, shutil, subprocess, sys, datetime as dt

BACKUP_DIR = os.path.join(os.path.dirname(__file__), "..", "backups")


def _db_url() -> str:
    # 优先 .env DATABASE_URL，否则取 Settings
    env_url = os.environ.get("DATABASE_URL", "")
    if env_url:
        return env_url
    # Settings() 读 .env
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from config import get_settings
        return get_settings().DATABASE_URL
    except Exception:
        return "sqlite:///./data/zzcc_oa.db"


def _ensure_dir():
    os.makedirs(BACKUP_DIR, exist_ok=True)


# ── SQLite ────────────────────────────────────────────────────
def _sqlite_backup(db_path: str, dest: str):
    shutil.copy2(db_path, dest)
    # 附带 WAL + SHM（如果存在）
    for suffix in ("-wal", "-shm"):
        src = db_path + suffix
        if os.path.exists(src):
            shutil.copy2(src, dest + suffix)
    # vacuum
    import sqlite3
    conn = sqlite3.connect(dest)
    conn.execute("VACUUM")
    conn.close()
    print(f"  SQLite 备份完成: {dest}")


def _sqlite_restore(backup_path: str, db_path: str):
    shutil.copy2(backup_path, db_path)
    print(f"  SQLite 恢复完成: {db_path}")


# ── MariaDB ─────────────────────────────────────────────────
def _parse_mysql_url(url: str) -> dict:
    # mysql+pymysql://user:pass@host:port/db
    import re
    m = re.match(r"mysql(?:[+]pymysql)?://([^:@]+):([^@]+)@([^:/]+)(?::(\d+))?/(.+)", url)
    if not m:
        raise ValueError(f"无法解析 MySQL URL: {url}")
    return {
        "user": m.group(1),
        "pass": m.group(2),
        "host": m.group(3),
        "port": m.group(4) or "3306",
        "db": m.group(5),
    }


def _mariadb_backup(url: str, dest: str):
    c = _parse_mysql_url(url)
    cmd = [
        "mysqldump",
        "-h", c["host"],
        "-P", c["port"],
        "-u", c["user"],
        f"-p{c['pass']}",
        "--single-transaction",
        "--quick",
        "--lock-tables=false",
        "--routines",
        "--triggers",
        "--events",
        c["db"],
    ]
    with open(dest, "w") as f:
        subprocess.run(cmd, stdout=f, check=True)
    print(f"  MariaDB 备份完成: {dest} ({os.path.getsize(dest) // 1024} KB)")


def _mariadb_restore(url: str, backup_path: str):
    c = _parse_mysql_url(url)
    cmd = [
        "mysql",
        "-h", c["host"],
        "-P", c["port"],
        "-u", c["user"],
        f"-p{c['pass']}",
        c["db"],
    ]
    with open(backup_path) as f:
        subprocess.run(cmd, stdin=f, check=True)
    print(f"  MariaDB 恢复完成")


# ── 主逻辑 ────────────────────────────────────────────────────
def backup():
    _ensure_dir()
    url = _db_url()
    ts = dt.datetime.now().strftime("%Y-%m-%d-%H%M%S")
    fname = f"zzcc_oa_{ts}.sql"
    dest = os.path.join(BACKUP_DIR, fname)

    if url.startswith("mysql"):
        _mariadb_backup(url, dest)
    elif url.startswith("sqlite"):
        # sqlite:///./data/zzcc_oa.db
        db_path = url.split("///", 1)[1].lstrip("/")
        _sqlite_backup(db_path, dest)
    else:
        print(f"未知数据库类型: {url}", file=sys.stderr)
        sys.exit(1)

    # 保留最近 30 份，删旧
    _trim_old(30)
    print(f"备份路径: {dest}")


def restore(tag: str):
    """tag = 备份文件名（不含目录）"""
    _ensure_dir()
    candidates = [f for f in os.listdir(BACKUP_DIR) if tag in f and f.endswith(".sql")]
    if not candidates:
        print(f"找不到包含 '{tag}' 的备份文件", file=sys.stderr)
        sys.exit(1)
    path = os.path.join(BACKUP_DIR, sorted(candidates)[-1])
    url = _db_url()
    print(f"将从 {path} 恢复…")
    if url.startswith("mysql"):
        _mariadb_restore(url, path)
    elif url.startswith("sqlite"):
        db_path = url.split("///", 1)[1].lstrip("/")
        _sqlite_restore(path, db_path)
    else:
        print(f"未知数据库类型: {url}", file=sys.stderr)
        sys.exit(1)


def list_backups():
    _ensure_dir()
    files = sorted(os.listdir(BACKUP_DIR), reverse=True)
    if not files:
        print("暂无备份")
        return
    print(f"{'文件名':<35} {'大小':>10}  {'修改时间'}")
    print("-" * 60)
    base = BACKUP_DIR
    for f in files:
        fp = os.path.join(base, f)
        size = os.path.getsize(fp)
        mtime = dt.datetime.fromtimestamp(os.path.getmtime(fp)).strftime("%Y-%m-%d %H:%M")
        label = f"{size/1024:.0f} KB" if size < 1024 * 1024 else f"{size/1024/1024:.1f} MB"
        print(f"{f:<35} {label:>10}  {mtime}")


def _trim_old(keep: int):
    files = sorted(os.listdir(BACKUP_DIR), key=lambda f: os.path.getmtime(os.path.join(BACKUP_DIR, f)), reverse=True)
    for f in files[keep:]:
        os.remove(os.path.join(BACKUP_DIR, f))
        print(f"  清理旧备份: {f}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="ZZCC OA 数据库备份工具")
    ap.add_argument("--restore", metavar="TAG", help="从备份恢复（传入文件名关键字或时间戳）")
    ap.add_argument("--list", "-l", action="store_true", help="列出可用备份")
    args = ap.parse_args()

    if args.restore:
        restore(args.restore)
    elif args.list:
        list_backups()
    else:
        backup()
