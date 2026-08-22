"""routers/_db.py — DB 路由工具"""
import json
import re
from datetime import date, datetime
from sqlalchemy.orm import Session
from sqlalchemy import inspect as sa_inspect
from database import Base

# doctype → (model_class, id_prefix)
DOCTYPE_MODEL: dict[str, tuple[type, str]] = {}


def register(doctype: str, model_class: type, prefix: str):
    DOCTYPE_MODEL[doctype] = (model_class, prefix)


def seq_for(doctype: str, db: Session, dept: str = "DEFAULT") -> str:
    """生成企业级单据编号：{类型前缀}-{部门}-{YYYYMM}-{4位序号}

    计数维度为 (doctype, dept, yyyymm)，跨月自动重置。
    P0 阶段组织架构未上线，dept 默认 DEFAULT；后续从 current_user 推断。
    """
    if doctype not in DOCTYPE_MODEL:
        return doctype.replace(" ", "") + "-001"
    model, prefix = DOCTYPE_MODEL[doctype]
    ym = datetime.now().strftime("%Y%m")
    pattern = f"{prefix}-{dept}-{ym}-%"
    rows = db.query(model.name).filter(model.name.like(pattern)).all()
    max_seq = 0
    rx = re.compile(rf"^{re.escape(prefix)}-{re.escape(dept)}-(\d{{6}})-(\d{{4}})$")
    for (n,) in rows:
        m = rx.match(n or "")
        if m:
            max_seq = max(max_seq, int(m.group(2)))
    return f"{prefix}-{dept}-{ym}-{max_seq + 1:04d}"


def model_to_dict(model: Base) -> dict:
    """SQLAlchemy 模型 → dict（含 JSON 列反序列化、date 序列化）"""
    result = {}
    for col in sa_inspect(model).mapper.columns:
        v = getattr(model, col.key)
        if isinstance(v, (date, datetime)):
            v = v.isoformat() if v else None
        elif isinstance(v, str):
            # MariaDB TEXT→datetime roundtrip
            if len(v) == 10 and v[4] == '-' and v[7] == '-':  # date
                pass
            elif len(v) >= 19 and v[4] == '-' and v[13] == ' ':  # datetime
                pass
            # leave str as-is; downstream can handle
        elif col.key.endswith("_json") and isinstance(v, str):
            try:
                v = json.loads(v)
            except Exception:
                pass
        result[col.key] = v
    return result


def model_from_dict(model_class: type, data: dict) -> Base:
    """dict → SQLAlchemy 模型（JSON 列序列化，忽略未定义字段）"""
    kwargs, json_keys = {}, set()
    for col in sa_inspect(model_class).mapper.columns:
        if col.key.endswith("_json"):
            json_keys.add(col.key)

    sa_cols = {c.key for c in sa_inspect(model_class).mapper.columns}
    for k, v in data.items():
        if k not in sa_cols:
            continue
        if k in json_keys and v is not None:
            kwargs[k] = json.dumps(v) if not isinstance(v, str) else v
        else:
            kwargs[k] = v
    return model_class(**kwargs)
