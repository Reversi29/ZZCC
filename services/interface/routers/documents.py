"""
Router: /import/pdf/*, /import/docx/*, /convert/pdf/*, /convert/docx/*
PDF/DOCX text extraction, CSV conversion, and optional Nebula import.
"""
from __future__ import annotations

import csv
import io
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile

from dependencies import get_client, get_session, require_api_key
from models.schemas import ImportResp, check_identifier
from modules.nebula_client import NebulaError
from services.graph import insert_edge, insert_vertex

router = APIRouter(prefix="/import", tags=["import", "documents"])
convert_router = APIRouter(prefix="/convert", tags=["convert", "documents"])

# ---- helpers ---------------------------------------------------------
def _coerce(raw: str | None) -> Any:
    if raw is None:
        return None
    s = raw.strip()
    if not s:
        return None
    low = s.lower()
    if low in ("true", "false"):
        return low == "true"
    try:
        if s.startswith("0") and len(s) > 1:
            raise ValueError
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        return s


def _extract_pdf_text(file: UploadFile) -> list[tuple[int, str]]:
    """Extract (page_num, text) from an uploaded PDF."""
    from pypdf import PdfReader

    reader = PdfReader(file.file)
    pages: list[tuple[int, str]] = []
    for i, page in enumerate(reader.pages, 1):
        text = page.extract_text() or ""
        if text.strip():
            pages.append((i, text))
    return pages


def _extract_docx_text(file: UploadFile) -> list[tuple[int, str]]:
    """Extract (paragraph_idx, text) from an uploaded DOCX."""
    from docx import Document

    doc = Document(file.file)
    paragraphs: list[tuple[int, str]] = []
    for i, para in enumerate(doc.paragraphs, 1):
        text = para.text.strip()
        if text:
            paragraphs.append((i, text))
    return paragraphs


# ---- PDF vertices ---------------------------------------------------
@router.post("/pdf/vertices")
async def import_pdf_vertices(
    space: str,
    tag: str,
    file: UploadFile = File(...),
    sess=Depends(get_session),
    auth: str = Depends(require_api_key),
):
    check_identifier(space, "空间名")
    check_identifier(tag, "标签名")

    pages = _extract_pdf_text(file)
    count, errors = 0, []
    for page_num, text in pages:
        vid = f"page_{page_num}"
        props = {"page": page_num, "content": text}
        for k in props:
            check_identifier(k, "属性名")
        try:
            insert_vertex(get_client(), sess, space=space, vid=vid, tag=tag, props=props)
            count += 1
        except NebulaError as exc:
            errors.append(f"page {page_num}: {exc}")
    return {"ok": True, "data": {"imported": count, "errors": errors[:50]}}


# ---- DOCX vertices --------------------------------------------------
@router.post("/docx/vertices")
async def import_docx_vertices(
    space: str,
    tag: str,
    file: UploadFile = File(...),
    sess=Depends(get_session),
    auth: str = Depends(require_api_key),
):
    check_identifier(space, "空间名")
    check_identifier(tag, "标签名")

    paragraphs = _extract_docx_text(file)
    count, errors = 0, []
    for idx, text in paragraphs:
        vid = f"para_{idx}"
        props = {"para": idx, "content": text}
        for k in props:
            check_identifier(k, "属性名")
        try:
            insert_vertex(get_client(), sess, space=space, vid=vid, tag=tag, props=props)
            count += 1
        except NebulaError as exc:
            errors.append(f"para {idx}: {exc}")
    return {"ok": True, "data": {"imported": count, "errors": errors[:50]}}


# ---- PDF edges ------------------------------------------------------
@router.post("/pdf/edges")
async def import_pdf_edges(
    space: str,
    edge: str,
    file: UploadFile = File(...),
    sess=Depends(get_session),
    auth: str = Depends(require_api_key),
):
    check_identifier(space, "空间名")
    check_identifier(edge, "边类型名")

    pages = _extract_pdf_text(file)
    count, errors = 0, []
    for page_num, text in pages:
        for line in text.splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 2:
                continue
            src, dst = parts[0], parts[1]
            relation = parts[2] if len(parts) > 2 else ""
            if not src or not dst:
                continue
            props = {"relation": relation}
            if relation:
                check_identifier("relation", "属性名")
            try:
                insert_edge(get_client(), sess, space=space, src=src, dst=dst, edge=edge, props=props)
                count += 1
            except NebulaError as exc:
                errors.append(f"line {page_num}: {exc}")
    return {"ok": True, "data": {"imported": count, "errors": errors[:50]}}


# ---- DOCX edges -----------------------------------------------------
@router.post("/docx/edges")
async def import_docx_edges(
    space: str,
    edge: str,
    file: UploadFile = File(...),
    sess=Depends(get_session),
    auth: str = Depends(require_api_key),
):
    check_identifier(space, "空间名")
    check_identifier(edge, "边类型名")

    paragraphs = _extract_docx_text(file)
    count, errors = 0, []
    for idx, text in paragraphs:
        parts = [p.strip() for p in text.split(",")]
        if len(parts) < 2:
            continue
        src, dst = parts[0], parts[1]
        relation = parts[2] if len(parts) > 2 else ""
        if not src or not dst:
            continue
        props = {"relation": relation}
        try:
            insert_edge(get_client(), sess, space=space, src=src, dst=dst, edge=edge, props=props)
            count += 1
        except NebulaError as exc:
            errors.append(f"para {idx}: {exc}")
    return {"ok": True, "data": {"imported": count, "errors": errors[:50]}}


# ---- Convert: PDF to CSV --------------------------------------------
@convert_router.post("/pdf/to-csv/vertices")
async def convert_pdf_vertices_csv(
    space: str = Query(...),
    tag: str = Query(...),
    import_now: bool = Query(False),
    file: UploadFile = File(...),
    sess=Depends(get_session),
    auth: str = Depends(require_api_key),
):
    check_identifier(space, "空间名")
    check_identifier(tag, "标签名")

    pages = _extract_pdf_text(file)
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["vid", "page", "content"])
    writer.writeheader()
    for page_num, text in pages:
        writer.writerow({"vid": f"page_{page_num}", "page": page_num, "content": text})
    csv_content = output.getvalue()

    if import_now:
        count, errors = 0, []
        for page_num, text in pages:
            vid = f"page_{page_num}"
            try:
                insert_vertex(get_client(), sess, space=space, vid=vid, tag=tag,
                              props={"page": page_num, "content": text})
                count += 1
            except NebulaError as exc:
                errors.append(f"page {page_num}: {exc}")
        return {"ok": True, "data": {"imported": count, "errors": errors[:50]}}

    return {"ok": True, "data": {"csv": csv_content}}


@convert_router.post("/pdf/to-csv/edges")
async def convert_pdf_edges_csv(
    space: str = Query(...),
    edge: str = Query(...),
    import_now: bool = Query(False),
    file: UploadFile = File(...),
    sess=Depends(get_session),
    auth: str = Depends(require_api_key),
):
    check_identifier(space, "空间名")
    check_identifier(edge, "边类型名")

    pages = _extract_pdf_text(file)
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["src", "dst", "relation", "page"])
    writer.writeheader()
    for page_num, text in pages:
        for line in text.splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 2:
                continue
            src, dst = parts[0], parts[1]
            if not src or not dst:
                continue
            writer.writerow({
                "src": src,
                "dst": dst,
                "relation": parts[2] if len(parts) > 2 else "",
                "page": page_num,
            })
    csv_content = output.getvalue()

    if import_now:
        count, errors = 0, []
        for page_num, text in pages:
            for line in text.splitlines():
                parts = [p.strip() for p in line.split(",")]
                if len(parts) < 2:
                    continue
                src, dst = parts[0], parts[1]
                if not src or not dst:
                    continue
                try:
                    insert_edge(get_client(), sess, space=space, src=src, dst=dst, edge=edge,
                                props={"relation": parts[2] if len(parts) > 2 else "", "page": page_num})
                    count += 1
                except NebulaError as exc:
                    errors.append(f"line {page_num}: {exc}")
        return {"ok": True, "data": {"imported": count, "errors": errors[:50]}}

    return {"ok": True, "data": {"csv": csv_content}}


# ---- Convert: DOCX to CSV -------------------------------------------
@convert_router.post("/docx/to-csv/vertices")
async def convert_docx_vertices_csv(
    space: str = Query(...),
    tag: str = Query(...),
    import_now: bool = Query(False),
    file: UploadFile = File(...),
    sess=Depends(get_session),
    auth: str = Depends(require_api_key),
):
    check_identifier(space, "空间名")
    check_identifier(tag, "标签名")

    paragraphs = _extract_docx_text(file)
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["vid", "para", "content"])
    writer.writeheader()
    for idx, text in paragraphs:
        writer.writerow({"vid": f"para_{idx}", "para": idx, "content": text})
    csv_content = output.getvalue()

    if import_now:
        count, errors = 0, []
        for idx, text in paragraphs:
            try:
                insert_vertex(get_client(), sess, space=space, vid=f"para_{idx}", tag=tag,
                              props={"para": idx, "content": text})
                count += 1
            except NebulaError as exc:
                errors.append(f"para {idx}: {exc}")
        return {"ok": True, "data": {"imported": count, "errors": errors[:50]}}

    return {"ok": True, "data": {"csv": csv_content}}


@convert_router.post("/docx/to-csv/edges")
async def convert_docx_edges_csv(
    space: str = Query(...),
    edge: str = Query(...),
    import_now: bool = Query(False),
    file: UploadFile = File(...),
    sess=Depends(get_session),
    auth: str = Depends(require_api_key),
):
    check_identifier(space, "空间名")
    check_identifier(edge, "边类型名")

    paragraphs = _extract_docx_text(file)
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["src", "dst", "relation", "para"])
    writer.writeheader()
    for idx, text in paragraphs:
        parts = [p.strip() for p in text.split(",")]
        if len(parts) < 2:
            continue
        writer.writerow({
            "src": parts[0],
            "dst": parts[1],
            "relation": parts[2] if len(parts) > 2 else "",
            "para": idx,
        })
    csv_content = output.getvalue()

    if import_now:
        count, errors = 0, []
        for idx, text in paragraphs:
            parts = [p.strip() for p in text.split(",")]
            if len(parts) < 2:
                continue
            src, dst = parts[0], parts[1]
            if not src or not dst:
                continue
            try:
                insert_edge(get_client(), sess, space=space, src=src, dst=dst, edge=edge,
                            props={"relation": parts[2] if len(parts) > 2 else "", "para": idx})
                count += 1
            except NebulaError as exc:
                errors.append(f"para {idx}: {exc}")
        return {"ok": True, "data": {"imported": count, "errors": errors[:50]}}

    return {"ok": True, "data": {"csv": csv_content}}
