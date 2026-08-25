"""services/flow_engine.py — 业务流编排引擎

核心概念：
- FlowTemplate  = 静态流程定义（画布 → JSON）
- FlowInstance  = 一次执行
- Node  = 原子执行单元

引擎支持：
1. 手动编排：用户在画布拖拽定义节点/边，保存为模板
2. AI 自主编排：AI 调用 POST /flow/build 接口，自动从 goal 生成模板
3. 执行引擎：同步/异步执行实例，支持人工审批挂起、AI Agent 节点
"""
import json
import asyncio
from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session
from models.flow import (
    FlowTemplate, FlowInstance, FlowNode, FlowEdge, FlowAgentLog,
    FLOW_NODE_TYPES, FLOW_NODE_CATEGORIES,
)


# ═══════════════════════════════════════════════════════════════════
#  1. 模板操作
# ═══════════════════════════════════════════════════════════════════

def create_template(db: Session, name: str, description: str,
                    category: str, config: dict, created_by: str,
                    icon: str = None) -> FlowTemplate:
    """创建流程模板"""
    existing = db.query(FlowTemplate).filter_by(name=name).first()
    if existing:
        raise ValueError(f"模板 '{name}' 已存在")
    t = FlowTemplate(
        name=name, description=description, category=category,
        config=json.dumps(config, ensure_ascii=False),
        created_by=created_by, icon=icon,
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


def save_template(db: Session, template_id: int, config: dict) -> FlowTemplate:
    """更新流程模板配置"""
    t = db.query(FlowTemplate).filter_by(id=template_id).first()
    if not t:
        raise ValueError("模板不存在")
    t.config = json.dumps(config, ensure_ascii=False)
    t.version += 1
    t.modified_by = "admin"
    db.commit()
    db.refresh(t)
    return t


def publish_template(db: Session, template_id: int) -> FlowTemplate:
    t = db.query(FlowTemplate).filter_by(id=template_id).first()
    if not t:
        raise ValueError("模板不存在")
    t.published = True
    db.commit()
    db.refresh(t)
    return t


# ═══════════════════════════════════════════════════════════════════
#  2. 实例执行
# ═══════════════════════════════════════════════════════════════════

def create_instance(db: Session, template: FlowTemplate,
                    name: str = None, trigger_type: str = "manual",
                    triggered_by: str = None, trigger_ctx: dict = None,
                    override_nodes: list = None) -> FlowInstance:
    """创建实例：从模板克隆节点配置"""
    inst = FlowInstance(
        template_id=template.id,
        template_name=template.name,
        name=name or f"{template.name}-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        status="pending",
        trigger_type=trigger_type,
        triggered_by=triggered_by,
        trigger_ctx=json.dumps(trigger_ctx or {}, ensure_ascii=False),
        created_by=triggered_by or "system",
    )
    db.add(inst)
    db.flush()

    # 从模板复制节点
    template_config = json.loads(template.config) if template.config else {"nodes": [], "edges": []}
    nodes_config = override_nodes or template_config.get("nodes", [])
    edges_config = template_config.get("edges", [])

    node_map = {}  # template_node_id → FlowNode
    for nc in nodes_config:
        fn = FlowNode(
            instance_id=inst.id,
            node_type=nc.get("type", "action"),
            label=nc.get("label"),
            status="pending",
            config=json.dumps(nc.get("config", {}), ensure_ascii=False),
        )
        db.add(fn)
        db.flush()
        node_map[str(nc.get("id", ""))] = fn

    # 克隆边
    for ec in edges_config:
        src = node_map.get(str(ec.get("source", "")))
        tgt = node_map.get(str(ec.get("target", "")))
        if src and tgt:
            fe = FlowEdge(
                instance_id=inst.id,
                source_id=src.id, target_id=tgt.id,
                condition=ec.get("condition"),
                weight=ec.get("weight", 0),
            )
            db.add(fe)

    db.commit()
    db.refresh(inst)
    return inst


# ═══════════════════════════════════════════════════════════════════
#  3. 同步执行引擎（轻量）
# ═══════════════════════════════════════════════════════════════════

def execute_instance(db: Session, inst: FlowInstance, context: dict = None,
                     dry_run: bool = False) -> dict:
    """
    同步执行实例，返回执行结果。
    
    - dry_run=True：仅验证节点/边结构，不执行
    - 遇到 approve 节点 → 暂停（状态=suspended），等待外部回调
    - 遇到 agent 节点 → 调用 LLM
    - 其他节点直接执行
    
    返回：
    {
      "status": "complete" | "suspended" | "failed",
      "result": {...},
      "steps": [{"node_id", "type", "label", "status", "output"}],
    }
    """
    inst.status = "running"
    db.commit()

    nodes = {n.id: n for n in inst.nodes}
    edges = inst.__class__ if False else db.query(FlowEdge).filter_by(instance_id=inst.id).all()
    # Build adjacency list
    adj = {}  # node_id → [FlowEdge]
    for e in edges:
        adj.setdefault(e.source_id, []).append(e)

    context = context or {}
    start_node = next((n for n in nodes.values() if n.node_type == "start"), None)
    current_id = start_node.id if start_node else (list(nodes.values())[0].id if nodes else None)

    steps = []
    loop_count = 0
    max_loops = 200  # 防死循环

    while current_id and current_id in nodes and loop_count < max_loops:
        loop_count += 1
        node = nodes[current_id]

        # 处理当前节点
        result = _execute_node(db, node, context, dry_run)
        node.status = result["status"]
        node.input_data = json.dumps(context, ensure_ascii=False, default=str)
        node.output_data = json.dumps(result.get("output", {}), ensure_ascii=False, default=str)
        if result.get("error"):
            node.error = result["error"]
        db.commit()

        steps.append({
            "node_id": node.id,
            "type": node.node_type,
            "label": node.label,
            "status": node.status,
            "output": result.get("output"),
        })

        # 终止条件
        if node.node_type == "output" or result["status"] == "complete":
            inst.status = "complete"
            inst.result = json.dumps(result.get("output", {}), ensure_ascii=False, default=str)
            db.commit()
            return {"status": "complete", "result": result.get("output"), "steps": steps}

        if result["status"] == "suspended":
            inst.status = "suspended"
            inst.current_step = node.id
            db.commit()
            return {"status": "suspended", "result": result.get("output"), "steps": steps}

        if result["status"] == "failed":
            inst.status = "failed"
            inst.error = result.get("error")
            db.commit()
            return {"status": "failed", "result": result.get("output"), "steps": steps}

        # 推进到下一个节点
        current_id = _next_node(db, current_id, adj, nodes, context)
        if current_id is None:
            inst.status = "complete"
            db.commit()
            return {"status": "complete", "result": context, "steps": steps}

    # 超过循环限制
    inst.status = "failed"
    inst.error = f"Max loop limit ({max_loops}) reached"
    db.commit()
    return {"status": "failed", "error": inst.error, "steps": steps}


def _execute_node(db: Session, node: FlowNode, context: dict, dry_run: bool) -> dict:
    """执行单个节点，返回 {status, output, error}"""
    config = {}
    try:
        config = json.loads(node.config) if node.config else {}
    except Exception:
        pass

    if node.node_type in ("start", "output"):
        return {"status": "done", "output": {"complete": True, "context": context}}

    if node.node_type == "input":
        # 输入节点：等待外部提供数据（模拟）
        fields = config.get("fields", [])
        return {"status": "suspended", "output": {"fields": fields, "message": "等待输入"}}

    if node.node_type == "decision":
        # 条件判断
        condition = config.get("condition", "true")
        try:
            # 简单条件求值：支持 "x > 100", "status == 'approved'" 等
            ctx_vars = context.copy()
            result = eval(condition, {"__builtins__": {}}, ctx_vars)
            return {"status": "done", "output": {"decision": bool(result)}, "branch": "true" if result else "false"}
        except Exception:
            return {"status": "done", "output": {"decision": True}, "branch": "true"}

    if node.node_type == "loop":
        return {"status": "done", "output": {"loops": 0}}

    if node.node_type == "approve":
        approver = config.get("approver_role", "admin")
        return {"status": "suspended", "output": {"message": f"等待 {approver} 审批", "approver": approver}}

    if node.node_type == "agent":
        # AI Agent 节点 — 通过 HTTP 调用 AI 咨询 API
        prompt = config.get("prompt", "")
        module = config.get("module", "procurement")
        if dry_run:
            return {"status": "done", "output": {"ai_response": f"[dry_run] Agent: {prompt[:50]}"}}
        try:
            result = call_internal_api("POST", "/api/ai/consult", {"module": module, "context": {"prompt": prompt, **context}})
            return {"status": "done", "output": result.get("body", result)}
        except Exception as e:
            return {"status": "done", "output": {"ai_response": f"AI 暂不可用: {str(e)}"}}

    if node.node_type == "action":
        # API 调用
        method = config.get("method", "GET")
        path = config.get("path", "")
        body = config.get("body", {})
        if dry_run:
            return {"status": "done", "output": {"method": method, "path": path, "body": body}}
        result = call_internal_api(method, path, body or {})
        ctx_key = config.get("ctx_key") or path.split("/")[-1]
        context[ctx_key] = result.get("body", result)
        return {"status": "done", "output": result}

    if node.node_type == "http":
        url = config.get("url", "")
        method = config.get("method", "GET")
        body = config.get("body", {})
        if dry_run:
            return {"status": "done", "output": {"url": url, "note": "dry_run 模式未实际发送"}}
        import urllib.request, urllib.error
        data = json.dumps(body).encode() if body else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = json.loads(resp.read().decode())
                context[config.get("ctx_key") or "http_result"] = body
                return {"status": "done", "output": {"status": resp.status, "body": body}}
        except urllib.error.HTTPError as e:
            return {"status": "failed", "error": f"HTTP {e.code}: {e.read().decode()[:500]}"}
        except Exception as e:
            return {"status": "failed", "error": str(e)}

    if node.node_type == "notify":
        channels = config.get("channels", ["inapp"])
        message = config.get("message", "")
        try:
            from routers.notifications import push_external
            push_external(message, json.dumps(context, ensure_ascii=False))
            return {"status": "done", "output": {"channels": channels, "message": message}}
        except Exception as e:
            return {"status": "done", "output": {"note": f"通知跳过: {str(e)}", "channels": channels}}

    if node.node_type == "delay":
        duration = config.get("duration", 0)
        if dry_run:
            return {"status": "done", "output": {"delayed_ms": duration}}
        import time
        delay_s = min(int(duration) / 1000.0, 60)
        time.sleep(delay_s)
        context["_delayed"] = duration
        return {"status": "done", "output": {"delayed_ms": duration}}

    if node.node_type == "webhook":
        url = config.get("url", "")
        method = config.get("method", "POST")
        payload = config.get("payload", {})
        if dry_run:
            return {"status": "done", "output": {"url": url, "note": "dry_run 模式未实际发送"}}
        if url:
            import urllib.request, urllib.error
            data = json.dumps({**payload, "_context": json.dumps(context, ensure_ascii=False)}).encode()
            req = urllib.request.Request(url, data=data, method=method)
            req.add_header("Content-Type", "application/json")
            try:
                with urllib.request.urlopen(req, timeout=15) as resp:
                    return {"status": "done", "output": {"url": url, "status": resp.status}}
            except urllib.error.HTTPError as e:
                return {"status": "failed", "error": f"Webhook {e.code}"}
            except Exception as e:
                return {"status": "failed", "error": str(e)}
        return {"status": "suspended", "output": {"message": "等待 Webhook 回调"}}

    return {"status": "done", "output": {"type": node.node_type}}


def _next_node(db: Session, current_id: int, adj: dict, nodes: dict, context: dict) -> Optional[int]:
    """根据边和当前上下文选择下一个节点"""
    outgoing = adj.get(current_id, [])
    if not outgoing:
        return None

    # 如果有 decision 分支，根据上下文中的 _branch 值选择
    branch = context.get("_branch", "true")
    for e in sorted(outgoing, key=lambda x: x.weight):
        if e.condition and e.condition not in ("true", "default"):
            if str(e.condition) == str(branch):
                return e.target_id
            continue
        # 默认分支
        return e.target_id

    return outgoing[0].target_id


# ═══════════════════════════════════════════════════════════════════
#  4. 外部 API 调用（action 节点使用）
# ═══════════════════════════════════════════════════════════════════

def call_internal_api(method: str, path: str, body: dict = None,
                      headers: dict = None) -> dict:
    """
    action 节点调用内部 API。
    使用 httpx 客户端同步调用。
    可配置 API_BASE_URL 环境变量。
    """
    import os
    import urllib.request
    import urllib.error

    api_base = os.environ.get("OA_API_BASE_URL", "http://localhost:8003")
    url = api_base + path
    data = json.dumps(body or {}).encode() if body else None

    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    api_key = os.environ.get("OA_API_KEY", "zzcc_oadev_key_2024")
    req.add_header("X-API-Key", api_key)

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return {"status": resp.status, "body": json.loads(resp.read().decode())}
    except urllib.error.HTTPError as e:
        return {"status": e.code, "error": e.read().decode()}
    except Exception as e:
        return {"error": str(e)}