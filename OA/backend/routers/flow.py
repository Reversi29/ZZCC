"""routers/flow.py — 业务流程编排

端点：
- 模板管理: /api/flow/templates (CRUD)
- 实例管理: /api/flow/instances (CRUD + 执行)
- AI 编排:  POST /api/flow/build — AI 根据目标自动生成流程模板
- 节点类型:  GET /api/flow/node-types — 返回可用节点类型供前端画布使用
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import Optional, Annotated
from datetime import datetime
from pydantic import BaseModel
from database import get_db
import json
from models.flow import (
    FlowTemplate, FlowInstance, FlowNode, FlowEdge,
    FLOW_NODE_TYPES, FLOW_NODE_CATEGORIES,
)
from services.flow_engine import (
    create_template, save_template, publish_template,
    create_instance, execute_instance,
)
from routers.auth import require_auth, CurrentUser

router = APIRouter(prefix="/api/flow", tags=["Flow"])


def _safe_json(data):
    """递归替换无法序列化的对象"""
    if data is None:
        return None
    if isinstance(data, str):
        return data
    if isinstance(data, (int, float, bool)):
        return data
    if isinstance(data, datetime):
        return data.isoformat()
    if isinstance(data, list):
        return [_safe_json(i) for i in data]
    if isinstance(data, dict):
        return {str(k): _safe_json(v) for k, v in data.items()}
    return str(data)


def md_flow_template(t) -> dict:
    config = None
    if t.config:
        try:
            config = json.loads(t.config)
        except Exception:
            pass
    return {
        "id": t.id, "name": t.name, "description": t.description,
        "category": t.category, "icon": t.icon,
        "version": t.version, "published": t.published,
        "created_by": t.created_by, "config": config,
        "created_at": t.creation.isoformat() if t.creation else None,
    }


def md_instance(i, db) -> dict:
    nodes = []
    for n in i.nodes:
        cfg = None
        if n.config:
            try: cfg = json.loads(n.config)
            except: pass
        nodes.append({
            "id": n.id, "node_type": n.node_type, "label": n.label,
            "status": n.status, "config": cfg,
            "input_data": n.input_data, "output_data": n.output_data,
            "error": n.error,
            "created_at": n.creation.isoformat() if n.creation else None,
        })
    edges = []
    for e in db.query(FlowEdge).filter_by(instance_id=i.id).all():
        edges.append({"id": e.id, "source_id": e.source_id,
                      "target_id": e.target_id, "condition": e.condition})
    return {
        "id": i.id, "template_id": i.template_id, "template_name": i.template_name,
        "name": i.name, "status": i.status, "current_step": i.current_step,
        "result": i.result, "error": i.error,
        "trigger_type": i.trigger_type, "triggered_by": i.triggered_by,
        "created_by": i.created_by, "created_at": i.creation.isoformat() if i.creation else None,
        "nodes": nodes, "edges": edges,
    }


class TemplateCreate(BaseModel):
    name: str
    description: str = ""
    category: str = ""
    icon: Optional[str] = None
    config: dict = {}


class TemplateUpdate(BaseModel):
    config: dict


class InstanceCreate(BaseModel):
    template_id: int
    name: Optional[str] = None
    trigger_type: str = "manual"
    context: Optional[dict] = None
    override_nodes: Optional[list] = None


class ExecuteRequest(BaseModel):
    context: Optional[dict] = None
    dry_run: bool = False


class BuildRequest(BaseModel):
    goal: str
    description: str = ""
    category: str = ""


# ═══════════════════════════════════════════════════════════════════
#  节点类型（前端画布使用）
# ═══════════════════════════════════════════════════════════════════

@router.get("/node-types")
def get_node_types():
    return {
        "types": {k: {**v, "config_schema": _node_schema(k)} for k, v in FLOW_NODE_TYPES.items()},
        "categories": FLOW_NODE_CATEGORIES,
    }


def _node_schema(node_type: str) -> dict:
    """返回各节点类型的配置 schema（前端表单渲染使用）"""
    schemas = {
        "start":     {},
        "output":    {"label": "流程终点，可选择返回字段"},
        "input":     {
            "fields": {"type": "array", "items": {"type": "object",
                       "properties": {"key": "字段名", "label": "显示名",
                       "type": "text|number|select|date", "required": True,
                       "options": "[] for select", "default": ""}}},
        },
        "action":    {
            "method": "GET|POST|PUT|PATCH|DELETE",
            "path": "API 路径，如 /api/resource/Employee",
            "body": "{} 请求体 JSON",
            "parse_result": "是否解析返回值并注入 context",
        },
        "http":      {
            "url": "完整 URL",
            "method": "GET|POST|PUT",
            "headers": "{} 额外请求头",
            "body": "{} 请求体",
        },
        "decision":  {
            "condition": "Python 表达式，如 result.amount > 10000",
            "true_label": "true 分支标签",
            "false_label": "false 分支标签",
        },
        "loop":      {
            "iterator": "context 中的数组变量名",
            "item_var": "循环变量名",
        },
        "approve":   {
            "approver_role": "审批角色",
            "message": "审批提示",
        },
        "agent":     {
            "prompt": "AI 任务描述",
            "model": "模型选择（可选）",
            "tools": "可用工具列表",
            "max_steps": "最大推理步数",
        },
        "notify":    {
            "channels": "['inapp','wecom','dingtalk','email','webhook']",
            "message": "通知内容",
            "template": "通知模板 ID（可选）",
        },
        "delay":     {"duration": "毫秒数"},
        "webhook":   {
            "url": "回调 URL",
            "method": "GET|POST",
            "payload": "{} 附带数据",
        },
    }
    return schemas.get(node_type, {})


# ═══════════════════════════════════════════════════════════════════
#  模板管理
# ═══════════════════════════════════════════════════════════════════

@router.get("/templates")
def list_templates(category: Optional[str] = None,
                   published: Optional[bool] = None,
                   search: Optional[str] = None,
                   current_user: CurrentUser = Depends(require_auth),
                   db: Session = Depends(get_db)):
    q = db.query(FlowTemplate)
    if category:
        q = q.filter_by(category=category)
    if published is not None:
        q = q.filter_by(published=published)
    if search:
        q = q.filter(FlowTemplate.name.ilike(f"%{search}%"))
    rows = q.order_by(FlowTemplate.creation.desc()).all()
    return [md_flow_template(r) for r in rows]


@router.get("/templates/{template_id}")
def get_template(template_id: int,
                 current_user: CurrentUser = Depends(require_auth),
                 db: Session = Depends(get_db)):
    t = db.query(FlowTemplate).filter_by(id=template_id).first()
    if not t:
        raise HTTPException(404, "模板不存在")
    return md_flow_template(t)


@router.post("/templates", status_code=201)
def create_template_endpoint(req: TemplateCreate,
                              current_user: CurrentUser = Depends(require_auth),
                              db: Session = Depends(get_db)):
    try:
        t = create_template(db, req.name, req.description,
                             req.category, req.config,
                             current_user.username or "system",
                             icon=req.icon)
        return md_flow_template(t)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.put("/templates/{template_id}")
def update_template(template_id: int, req: TemplateUpdate,
                    current_user: CurrentUser = Depends(require_auth),
                    db: Session = Depends(get_db)):
    try:
        t = save_template(db, template_id, req.config)
        return md_flow_template(t)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.delete("/templates/{template_id}")
def delete_template(template_id: int,
                    current_user: CurrentUser = Depends(require_auth),
                    db: Session = Depends(get_db)):
    t = db.query(FlowTemplate).filter_by(id=template_id).first()
    if not t:
        raise HTTPException(404, "模板不存在")
    db.delete(t)
    db.commit()
    return {"ok": True}


@router.post("/templates/{template_id}/publish")
def publish_template_endpoint(template_id: int,
                               current_user: CurrentUser = Depends(require_auth),
                               db: Session = Depends(get_db)):
    try:
        t = publish_template(db, template_id)
        return md_flow_template(t)
    except ValueError as e:
        raise HTTPException(400, str(e))


# ═══════════════════════════════════════════════════════════════════
#  实例管理
# ═══════════════════════════════════════════════════════════════════

@router.get("/instances")
def list_instances(template_id: Optional[int] = None,
                   status: Optional[str] = None,
                   limit: int = 100,
                   current_user: CurrentUser = Depends(require_auth),
                   db: Session = Depends(get_db)):
    q = db.query(FlowInstance)
    if template_id:
        q = q.filter_by(template_id=template_id)
    if status:
        q = q.filter_by(status=status)
    rows = q.order_by(FlowInstance.creation.desc()).limit(limit).all()
    return [md_instance(r, db) for r in rows]


@router.get("/instances/{instance_id}")
def get_instance(instance_id: int,
                 current_user: CurrentUser = Depends(require_auth),
                 db: Session = Depends(get_db)):
    i = db.query(FlowInstance).filter_by(id=instance_id).first()
    if not i:
        raise HTTPException(404, "实例不存在")
    return md_instance(i, db)


@router.post("/instances", status_code=201)
def create_instance_endpoint(req: InstanceCreate,
                              current_user: CurrentUser = Depends(require_auth),
                              db: Session = Depends(get_db)):
    t = db.query(FlowTemplate).filter_by(id=req.template_id).first()
    if not t:
        raise HTTPException(404, "模板不存在")
    i = create_instance(db, t,
                        name=req.name,
                        trigger_type=req.trigger_type,
                        triggered_by=current_user.username,
                        trigger_ctx=req.context,
                        override_nodes=req.override_nodes)
    return md_instance(i, db)


@router.post("/instances/{instance_id}/execute")
def execute_instance_endpoint(instance_id: int, req: ExecuteRequest,
                               current_user: CurrentUser = Depends(require_auth),
                               db: Session = Depends(get_db)):
    i = db.query(FlowInstance).filter_by(id=instance_id).first()
    if not i:
        raise HTTPException(404, "实例不存在")
    result = execute_instance(db, i, context=req.context or {}, dry_run=req.dry_run)
    return {"status": result["status"], "result": result.get("result"),
            "steps": result.get("steps"), "error": result.get("error")}


@router.post("/instances/{instance_id}/approve")
def approve_step(instance_id: int, comment: str = "",
                  current_user: CurrentUser = Depends(require_auth),
                  db: Session = Depends(get_db)):
    i = db.query(FlowInstance).filter_by(id=instance_id).first()
    if not i:
        raise HTTPException(404, "实例不存在")
    if i.status != "suspended":
        raise HTTPException(400, "当前实例未处于暂停状态")
    i.status = "running"
    i.current_step = None
    db.commit()
    return {"ok": True, "status": "running"}


@router.post("/instances/{instance_id}/cancel")
def cancel_instance(instance_id: int,
                     current_user: CurrentUser = Depends(require_auth),
                     db: Session = Depends(get_db)):
    i = db.query(FlowInstance).filter_by(id=instance_id).first()
    if not i:
        raise HTTPException(404, "实例不存在")
    i.status = "failed"
    i.error = "手动取消"
    db.commit()
    return {"ok": True}


# ═══════════════════════════════════════════════════════════════════
#  AI 自主编排
# ═══════════════════════════════════════════════════════════════════

@router.post("/build")
def ai_build_flow(req: BuildRequest,
                  current_user: CurrentUser = Depends(require_auth),
                  db: Session = Depends(get_db)):
    """
    AI 编排入口。
    
    根据用户的自然语言目标(goal)，AI 自动生成流程模板。
    支持两种方式：
    1. 规则引擎（默认）：基于关键词匹配预定义流程
    2. LLM 引擎（可选）：调用 AI 生成节点/边
    
    返回：{template: {...}, suggestion: "..."}
    """
    from services.auto_approval import _get_llm

    goal = req.goal
    category = req.category or "custom"
    description = req.description

    # 规则引擎：基于关键词匹配预定义流程模式
    template = _rule_based_build(goal, category, description)
    if template:
        t = create_template(db, template["name"], template["description"],
                             category, template["config"],
                             current_user.username or "system",
                             icon=template.get("icon"))
        return {
            "template": md_flow_template(t),
            "method": "rule_engine",
            "suggestion": "已基于规则生成，可在画布中调整",
        }

    # LLM 引擎：调用 AI 生成
    llm = _get_llm()
    if llm:
        try:
            llm_config = _llm_build_goal(llm, goal, category)
            template_name = f"AI-{category}-{datetime.now().strftime('%Y%m%d%H%M')}"
            t = create_template(db, template_name, description,
                                 category, llm_config,
                                 current_user.username or "system",
                                 icon="🤖")
            return {
                "template": md_flow_template(t),
                "method": "llm",
                "suggestion": "AI 自动生成，建议在画布中确认节点逻辑",
            }
        except Exception as e:
            return {"error": f"LLM 编排失败: {str(e)}",
                     "hint": "请手动在画布中创建流程"}

    return {"error": "当前无可用编排引擎",
             "hint": "请手动在画布中创建流程"}


def _rule_based_build(goal: str, category: str, description: str) -> Optional[dict]:
    """基于关键词规则的自动流程生成"""
    goal_lower = goal.lower()

    # 审批流模式
    if any(k in goal_lower for k in ["审批", "approve", "审核", "报销", "采购审批"]):
        return {
            "name": f"{category or '审批'}流程",
            "description": description or "自动生成的审批流程",
            "config": {
                "nodes": [
                    {"id": "n1", "type": "start", "label": "开始", "config": {}},
                    {"id": "n2", "type": "input", "label": "提交申请", "config": {"fields": [{"key": "title", "label": "标题", "type": "text", "required": True}, {"key": "amount", "label": "金额", "type": "number", "required": True}]}},
                    {"id": "n3", "type": "decision", "label": "金额判断", "config": {"condition": "amount < 10000"}},
                    {"id": "n4", "type": "approve", "label": "经理审批", "config": {"approver_role": "operator", "message": "请审批此申请"}},
                    {"id": "n5", "type": "approve", "label": "总监审批", "config": {"approver_role": "admin", "message": "请审批此申请"}},
                    {"id": "n6", "type": "output", "label": "完成", "config": {}},
                    {"id": "n7", "type": "notify", "label": "发送结果通知", "config": {"channels": ["inapp"], "message": "审批流程已结束"}},
                ],
                "edges": [
                    {"source": "n1", "target": "n2", "condition": "default"},
                    {"source": "n2", "target": "n3", "condition": "default"},
                    {"source": "n3", "target": "n4", "condition": "true"},
                    {"source": "n3", "target": "n5", "condition": "false"},
                    {"source": "n4", "target": "n6", "condition": "default"},
                    {"source": "n5", "target": "n6", "condition": "default"},
                    {"source": "n6", "target": "n7", "condition": "default"},
                ],
            },
            "icon": "🚧",
        }

    # 招聘流程
    if any(k in goal_lower for k in ["招聘", "hire", "面试", "offer"]):
        return {
            "name": "招聘流程",
            "description": description or "自动招聘流程",
            "config": {
                "nodes": [
                    {"id": "n1", "type": "start", "label": "开始", "config": {}},
                    {"id": "n2", "type": "input", "label": "填写职位需求", "config": {"fields": [{"key": "title", "label": "职位名称", "type": "text", "required": True}, {"key": "department", "label": "部门", "type": "text", "required": True}, {"key": "salary", "label": "预算薪资", "type": "number", "required": True}]}},
                    {"id": "n3", "type": "agent", "label": "AI 生成JD", "config": {"prompt": "根据职位需求生成岗位描述"}},
                    {"id": "n4", "type": "action", "label": "创建招聘记录", "config": {"method": "POST", "path": "/api/resource/Recruitment", "body": {"title": "${title}", "department_id": "${department}"}}},
                    {"id": "n5", "type": "approve", "label": "HR审批", "config": {"approver_role": "hr", "message": "确认职位发布"}},
                    {"id": "n6", "type": "output", "label": "发布完成", "config": {}},
                ],
                "edges": [
                    {"source": "n1", "target": "n2"},
                    {"source": "n2", "target": "n3"},
                    {"source": "n3", "target": "n4"},
                    {"source": "n4", "target": "n5"},
                    {"source": "n5", "target": "n6"},
                ],
            },
            "icon": "🏆",
        }

    # 工单流转
    if any(k in goal_lower for k in ["工单", "ticket", "服务", "客服", "support"]):
        return {
            "name": "工单处理流程",
            "description": description or "自动工单流转",
            "config": {
                "nodes": [
                    {"id": "n1", "type": "start", "label": "开始", "config": {}},
                    {"id": "n2", "type": "input", "label": "创建工单", "config": {"fields": [{"key": "title", "label": "标题", "type": "text", "required": True}, {"key": "priority", "label": "优先级", "type": "select", "options": "low|medium|high|urgent"}]}},
                    {"id": "n3", "type": "decision", "label": "优先级判断", "config": {"condition": "priority in ['high','urgent']"}},
                    {"id": "n4", "type": "approve", "label": "主管审批", "config": {"approver_role": "admin", "message": "高优先级工单需主管确认"}},
                    {"id": "n5", "type": "action", "label": "分派处理", "config": {"method": "POST", "path": "/api/resource/SupportTicket", "body": {}}},
                    {"id": "n6", "type": "output", "label": "完成", "config": {}},
                ],
                "edges": [
                    {"source": "n1", "target": "n2"},
                    {"source": "n2", "target": "n3"},
                    {"source": "n3", "target": "n4", "condition": "true"},
                    {"source": "n3", "target": "n5", "condition": "false"},
                    {"source": "n4", "target": "n5"},
                    {"source": "n5", "target": "n6"},
                ],
            },
            "icon": "🎫",
        }

    return None


def _llm_build_goal(llm_func, goal: str, category: str) -> dict:
    """调用 LLM 生成流程配置"""
    system_prompt = """你是一个业务流程编排专家。根据用户的自然语言目标，生成一个流程模板。

流程模板格式：
{
  "nodes": [
    {"id": "n1", "type": "节点类型", "label": "显示名", "config": {}},
    ...
  ],
  "edges": [
    {"source": "n1", "target": "n2", "condition": "default"},
    ...
  ]
}

可用节点类型：
- start: 流程开始
- input: 用户输入
- output: 流程结束
- action: API 调用
- decision: 条件分支
- loop: 循环
- notify: 发送通知
- approve: 人工审批
- agent: AI Agent
- delay: 延迟
- http: 外部 HTTP
- webhook: Webhook

只输出纯 JSON，不要其他文字。"""

    user_prompt = f"目标: {goal}\n类别: {category}\n\n请生成流程模板配置。"
    result = llm_func(system_prompt, user_prompt)
    # 提取 JSON
    import re
    json_match = re.search(r'\{.*\}', result, re.DOTALL)
    if json_match:
        return json.loads(json_match.group())
    raise ValueError(f"LLM 返回无法解析为 JSON: {result[:200]}")