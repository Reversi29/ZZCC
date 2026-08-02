"""routers/_db.py — DB 路由工具"""
import json
from datetime import date, datetime
from sqlalchemy.orm import Session
from sqlalchemy import inspect as sa_inspect
from database import Base

# doctype → (model_class, id_prefix)
DOCTYPE_MODEL: dict[str, tuple[type, str]] = {}


def register(doctype: str, model_class: type, prefix: str):
    DOCTYPE_MODEL[doctype] = (model_class, prefix)


def seq_for(doctype: str, db: Session) -> str:
    """按 doctype 查询总行数，生成序列名"""
    if doctype not in DOCTYPE_MODEL:
        return doctype.replace(" ", "") + "-001"
    _, prefix = DOCTYPE_MODEL[doctype]
    count = db.query(DOCTYPE_MODEL[doctype][0]).count()
    return f"{prefix}-{count + 1:04d}"


def model_to_dict(model: Base) -> dict:
    """SQLAlchemy 模型 → dict（含 JSON 列反序列化、date 序列化）"""
    result = {}
    for col in sa_inspect(model).mapper.columns:
        v = getattr(model, col.key)
        if isinstance(v, (date, datetime)):
            v = v.isoformat() if v else None
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
