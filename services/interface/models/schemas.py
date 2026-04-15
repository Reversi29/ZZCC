"""
Pydantic request/response models.
All API contracts are defined here — routers import from here, not main.py.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

# Shared pattern — exported for use in routers without importing re
IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


# ============================================================
# Request models
# ============================================================
class PropertyDef(BaseModel):
    name: str = Field(..., description="Property name (Nebula identifier)")
    type: str = Field(..., description="Nebula type: string, int, double, bool, timestamp…")


class SpaceCreate(BaseModel):
    name: str = Field(..., description="Space name (Nebula identifier)")
    partition_num: int = Field(default=3, ge=1, le=1024, description="Partition count")
    replica_factor: int = Field(default=1, ge=1, description="Replica factor")
    vid_type: str = Field(default="FIXED_STRING(64)", description="VID type")

    @field_validator("name")
    @classmethod
    def name_ok(cls, v: str) -> str:
        if not IDENTIFIER_RE.match(v):
            raise ValueError("非法标识符")
        return v


class TagCreate(BaseModel):
    space: str = Field(..., description="Target space name")
    tag: str = Field(..., description="Tag name")
    properties: List[PropertyDef] = Field(default_factory=list)


class TagDrop(BaseModel):
    space: str = Field(..., description="Space name")
    tag: str = Field(..., description="Tag name")


class EdgeTypeCreate(BaseModel):
    space: str = Field(..., description="Target space name")
    edge: str = Field(..., description="Edge type name")
    properties: List[PropertyDef] = Field(default_factory=list)


class EdgeTypeDrop(BaseModel):
    space: str = Field(..., description="Space name")
    edge: str = Field(..., description="Edge type name")


class EdgeTypeAlter(BaseModel):
    """Request body for PATCH /edge-types (add properties to existing edge type)."""
    space: str = Field(..., description="Space name")
    edge: str = Field(..., description="Edge type name")
    properties: list[dict[str, str]]


class TagDef(BaseModel):
    name: str
    properties: List[PropertyDef] = Field(default_factory=list)


class EdgeDef(BaseModel):
    name: str
    properties: List[PropertyDef] = Field(default_factory=list)


class DeployRequest(BaseModel):
    space: str = Field(..., description="Space name")
    partition_num: int = Field(default=3, ge=1)
    replica_factor: int = Field(default=1, ge=1)
    vid_type: str = Field(default="FIXED_STRING(64)")
    tags: List[TagDef] = Field(default_factory=list)
    edges: List[EdgeDef] = Field(default_factory=list)


class VertexCreate(BaseModel):
    space: str = Field(..., description="Target space name")
    tag: str = Field(..., description="Tag name")
    vid: str = Field(..., min_length=1, description="Vertex ID")
    props: Dict[str, Any] = Field(default_factory=dict)


class VertexDelete(BaseModel):
    space: str = Field(..., description="Space name")
    vid: str = Field(..., description="Vertex ID to delete")
    with_edges: bool = Field(default=True, description="Delete connected edges")


class VertexPatch(BaseModel):
    """Request body for PATCH /vertices/{vid} (vid comes from path, not body)."""
    space: str = Field(..., description="Target space name")
    tag: str = Field(..., description="Tag name")
    props: Dict[str, Any] = Field(default_factory=dict)


class EdgePatch(BaseModel):
    """Request body for PATCH /edges (partial update)."""
    space: str = Field(..., description="Target space name")
    edge: str = Field(..., description="Edge type name")
    src: str = Field(..., min_length=1, description="Source vertex ID")
    dst: str = Field(..., min_length=1, description="Destination vertex ID")
    props: Dict[str, Any] = Field(default_factory=dict)


class EdgeCreate(BaseModel):
    space: str = Field(..., description="Target space name")
    edge: str = Field(..., description="Edge type name")
    src: str = Field(..., min_length=1, description="Source vertex ID")
    dst: str = Field(..., min_length=1, description="Destination vertex ID")
    props: Dict[str, Any] = Field(default_factory=dict)


class EdgeDelete(BaseModel):
    space: str = Field(..., description="Space name")
    edge: str = Field(..., description="Edge type name")
    src: str = Field(..., description="Source vertex ID")
    dst: str = Field(..., description="Destination vertex ID")


# ============================================================
# Response models
# ============================================================
class SpaceResp(BaseModel):
    ok: bool
    data: Dict[str, Any] = Field(default_factory=dict)


class SpaceListResp(BaseModel):
    ok: bool
    data: Dict[str, List[Dict[str, Any]]]


class TagListResp(BaseModel):
    ok: bool
    data: Dict[str, List[Dict[str, Any]]]


class EdgeListResp(BaseModel):
    ok: bool
    data: Dict[str, List[Dict[str, Any]]]


class VertexResp(BaseModel):
    ok: bool
    data: Dict[str, Any]


class EdgeResp(BaseModel):
    ok: bool
    data: Dict[str, Any]


class QueryResp(BaseModel):
    ok: bool
    data: Dict[str, Any]


class ImportResp(BaseModel):
    ok: bool
    data: Dict[str, Any]


class HealthResp(BaseModel):
    status: str
    nebula: str
    postgres: Optional[str] = None
    redis: Optional[str] = None


# ============================================================
# Validation helpers (shared, exported)
# ============================================================
def check_identifier(name: str, kind: str) -> None:
    """Raise ValueError if name is not a valid Nebula identifier."""
    if not IDENTIFIER_RE.match(name):
        raise ValueError(
            f"{kind} '{name}' 非法。标识符必须 ^[A-Za-z_][A-Za-z0-9_]*$"
        )


def check_props(props: Dict[str, Any]) -> None:
    """Validate all keys in a props dict as identifiers."""
    for k in props:
        check_identifier(str(k), "属性名")
