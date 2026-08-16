"""export.py — 数据导出（Excel / CSV）

通用导出：按 doctype 从 DOCTYPE_MODEL 取全表，生成 xlsx / csv。
权限：任意登录用户可导出（数据隔离在 P1.7 细化）。
"""
import csv
import io
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import inspect as sa_inspect

try:
    from openpyxl import Workbook
    HAVE_XLSX = True
except ImportError:
    HAVE_XLSX = False

from database import get_db
from routers._db import DOCTYPE_MODEL
from routers.auth import get_current_user, CurrentUser

router = APIRouter(prefix="/api/export", tags=["导出"])


@router.get("/{doctype}")
def export_doctype(
    doctype: str,
    format: str = Query("xlsx", pattern="^(xlsx|csv)$"),
    current_user: Annotated[CurrentUser, Depends(get_current_user)] = None,
    db=Depends(get_db),
):
    """导出指定 doctype 的全部数据为 Excel / CSV"""
    if doctype not in DOCTYPE_MODEL:
        raise HTTPException(400, f"不支持的 doctype: {doctype}")
    model = DOCTYPE_MODEL[doctype][0]
    cols = [c.key for c in sa_inspect(model).mapper.columns]
    rows = db.query(model).all()
    data = [[getattr(r, c) for c in cols] for r in rows]

    if format == "csv":
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(cols)
        w.writerows(data)
        return Response(
            buf.getvalue().encode("utf-8-sig"),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={doctype}.csv"},
        )

    # xlsx
    if not HAVE_XLSX:
        raise HTTPException(500, "服务端未安装 openpyxl，无法导出 Excel")
    wb = Workbook()
    ws = wb.active
    ws.title = doctype[:31]
    ws.append(cols)
    for row in data:
        ws.append(["" if v is None else v for v in row])
    out = io.BytesIO()
    wb.save(out)
    return Response(
        out.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={doctype}.xlsx"},
    )
