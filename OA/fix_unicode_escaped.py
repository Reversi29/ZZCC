#!/usr/bin/env python3
# Fix unicode escapes in MariaDB that lost their backslash during migration.

import pymysql, re, sys

conn = pymysql.connect(host='127.0.0.1', port=3307, user='root',
                       password='zzcc_oa_2024', db='zzcc_oa', charset='utf8mb4')
cur = conn.cursor()

cur.execute("""
    SELECT TABLE_NAME, COLUMN_NAME 
    FROM information_schema.COLUMNS 
    WHERE TABLE_SCHEMA = 'zzcc_oa' AND DATA_TYPE IN ('text','longtext','mediumtext','tinytext','varchar','char')
""")
columns = cur.fetchall()

UNICODE_ESCAPE_RE = re.compile(r'u([0-9a-fA-F]{4})')
UNICODE_ESCAPE_FULL = re.compile(r'u[0-9a-fA-F]{4}')

def is_unicode_escaped(s):
    if not isinstance(s, str) or len(s) < 8:
        return False
    matches = list(UNICODE_ESCAPE_FULL.finditer(s))
    if not matches:
        return False
    consumed = sum(5 for _ in matches)
    return consumed / len(s) > 0.3

def decode_unicode_escaped(s):
    fixed = UNICODE_ESCAPE_RE.sub(lambda m: '\\u' + m.group(1), s)
    try:
        return fixed.encode('utf-8').decode('unicode_escape')
    except:
        return None

total_fixed = 0
total_checked = 0
total_skipped = 0

for tbl, col in columns:
    # Find primary key column name (fallback to first column)
    cur.execute(f"SELECT COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = 'zzcc_oa' AND TABLE_NAME = %s AND ORDINAL_POSITION = 1", (tbl,))
    first_col = cur.fetchone()
    pk_col = first_col[0] if first_col else col

    cur.execute(f"SELECT `{pk_col}`, `{col}` FROM `{tbl}` LIMIT 5")
    samples = cur.fetchall()
    sample_vals = [str(r[1]) for r in samples if r[1]]
    
    has_unicode_escaped = any(is_unicode_escaped(v) for v in sample_vals)
    if not has_unicode_escaped:
        total_skipped += 1
        continue

    print(f"\n{'='*60}")
    print(f"Fixing `{tbl}`.`{col}` (PK: `{pk_col}`)", flush=True)

    cur.execute(f"SELECT `{pk_col}`, `{col}` FROM `{tbl}`")
    rows = cur.fetchall()
    count = 0
    for pk_val, val in rows:
        total_checked += 1
        if val is None:
            continue
        s = str(val)
        if is_unicode_escaped(s):
            decoded = decode_unicode_escaped(s)
            if decoded and decoded != s:
                try:
                    cur.execute(f"UPDATE `{tbl}` SET `{col}` = %s WHERE `{pk_col}` = %s", (decoded, pk_val))
                    count += 1
                    if count <= 3:
                        print(f"  [{pk_val}] {s[:60]} → {decoded[:60]}", flush=True)
                except Exception as e:
                    print(f"  ⚠️  [{pk_val}]: {e}", flush=True)
    if count > 0:
        conn.commit()
        total_fixed += count
        print(f"  ✅ {count} rows fixed", flush=True)
    else:
        print(f"  ⏭️  No new fixes needed", flush=True)

cur.close()
conn.close()
print(f"\n{'='*60}")
print(f"Tables skipped (no unicode escapes): {total_skipped}")
print(f"Rows checked: {total_checked}")
print(f"Total fixed: {total_fixed} rows")