"""
Router: /api/v1/query — raw nGQL execution with basic safety gate.
"""
from fastapi import APIRouter, Depends, HTTPException, Query

from dependencies import get_client, get_session, require_api_key
from models.schemas import QueryResp, check_identifier
from modules.nebula_client import NebulaError
from services.graph import run_query

router = APIRouter(prefix="/query", tags=["query"])

# Destructive keywords blocked on /query (read-only endpoint)
_DANGEROUS_KEYWORDS = frozenset({
    "DROP", "DELETE", "UPDATE", "INSERT", "ALTER",
    "CREATE", "SUBMIT", "RESTORE", "REBUILD", "ADD",
    "CHANGE", "REMOVE", "SWAP", "CLEAR", "SET",
})


@router.get("", response_model=QueryResp)
async def run_query_endpoint(
    q: str = Query(..., description="nGQL statement (URL-encode the query string)"),
    space: str = Query(..., description="Target space name"),
    sess=Depends(get_session),
    auth: str = Depends(require_api_key),
):
    check_identifier(space, "空间名")

    # Basic safety gate — block destructive statements
    if any(kw in q.strip().upper() for kw in _DANGEROUS_KEYWORDS):
        raise HTTPException(
            status_code=403,
            detail="Destructive statements (DROP/DELETE/UPDATE/…) are blocked on /query",
        )

    try:
        rows = run_query(get_client(), sess, space=space, q=q)
        cols = list(rows[0].keys()) if rows else []
    except NebulaError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {"ok": True, "data": {"rows": rows, "columns": cols}}
