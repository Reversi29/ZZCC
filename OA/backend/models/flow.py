"""models/flow.py — 业务流程编排数据模型

FlowTemplate  = 可复用的流程模板（画布定义的 JSON 快照）
FlowInstance  = 一次流程执行实例
FlowNode       = 实例中的每个节点执行记录
FlowEdge       = 节点间的连接关系（实例级，含分支执行记录）
"""
from sqlalchemy import Column, Integer, String, Text, Float, JSON, DateTime, ForeignKey, Boolean, Enum as SAEnum
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base, Timestamped


# ── 节点类型注册表（前端+后端共享，单数据源）────────────────────
FLOW_NODE_TYPES = {
    "start":      {"label": "开始",       "emoji": "🚀", "category": "terminal",
                   "desc": "流程入口，无前置节点"},
    "input":      {"label": "输入",       "emoji": "📥", "category": "io",
                   "desc": "收集用户输入（表单字段定义在 config.fields）"},
    "output":     {"label": "输出",       "emoji": "📤", "category": "terminal",
                   "desc": "流程终点，返回结果"},
    "action":     {"label": "API 调用",   "emoji": "⚡", "category": "action",
                   "desc": "调用内部 API（CRUD 任意 doctype）"},
    "http":       {"label": "外部 HTTP",  "emoji": "🌐", "category": "action",
                   "desc": "调用外部 HTTP 端点"},
    "decision":   {"label": "条件分支",   "emoji": "🔀", "category": "control",
                   "desc": "if/else 条件判断，支持多分支"},
    "loop":       {"label": "循环",       "emoji": "🔄", "category": "control",
                   "desc": "遍历数组执行子流程"},
    "notify":     {"label": "通知",       "emoji": "🔔", "category": "action",
                   "desc": "发送站内/企微/钉钉/邮件通知"},
    "approve":    {"label": "审批门禁",   "emoji": "🚧", "category": "control",
                   "desc": "人工审批关卡（挂起等待操作）"},
    "agent":      {"label": "AI Agent",   "emoji": "🤖", "category": "ai",
                   "desc": "调用 AI 代理执行（LLM + 工具调用）"},
    "delay":      {"label": "延迟",       "emoji": "⏳", "category": "control",
                   "desc": "等待指定时长后继续"},
    "webhook":    {"label": "Webhook",    "emoji": "🔗", "category": "io",
                   "desc": "外部系统回调入口/出口"},
}

# 节点类别分组（画布工具栏使用）
FLOW_NODE_CATEGORIES = {
    "terminal": {"label": "终端", "emoji": "🎯"},
    "io":       {"label": "输入输出", "emoji": "📡"},
    "action":   {"label": "动作", "emoji": "⚡"},
    "control":  {"label": "控制流", "emoji": "🎮"},
    "ai":       {"label": "AI", "emoji": "🧠"},
}


class FlowTemplate(Base, Timestamped):
    __tablename__ = "flow_templates"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    name         = Column(String(255), nullable=False, unique=True)
    description  = Column(Text, nullable=True)
    category     = Column(String(100), nullable=True)   # hr / finance / ops / custom
    icon         = Column(String(50), nullable=True)
    version      = Column(Integer, default=1)
    published    = Column(Boolean, default=False)
    created_by   = Column(String(100), default="admin")

    config       = Column(Text, nullable=True)  # JSON: nodes[] + edges[]

    instances    = relationship("FlowInstance", back_populates="template", cascade="all, delete-orphan")


class FlowInstance(Base, Timestamped):
    __tablename__ = "flow_instances"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    template_id  = Column(Integer, ForeignKey("flow_templates.id"), nullable=True)
    template_name = Column(String(255), nullable=True)
    name         = Column(String(255), nullable=False, default="run")

    status       = Column(String(50), default="pending")  # pending/running/paused/suspended/complete/failed

    current_step = Column(String(255), nullable=True)
    result       = Column(Text, nullable=True)
    error        = Column(Text, nullable=True)

    trigger_type = Column(String(50), default="manual")  # manual/ai/webhook/cron
    triggered_by = Column(String(100), nullable=True)
    trigger_ctx  = Column(Text, nullable=True)

    created_by   = Column(String(100), default="system")

    template     = relationship("FlowTemplate", back_populates="instances")
    nodes        = relationship("FlowNode", back_populates="instance", cascade="all, delete-orphan",
                                 order_by="FlowNode.creation")


class FlowNode(Base, Timestamped):
    __tablename__ = "flow_nodes"

    id             = Column(Integer, primary_key=True, autoincrement=True)
    instance_id    = Column(Integer, ForeignKey("flow_instances.id"), nullable=False)

    node_type      = Column(String(50), nullable=False)  # start/input/action/...
    label          = Column(String(255), nullable=True)
    status         = Column(String(50), default="pending")  # pending/running/done/skipped/failed

    config         = Column(Text, nullable=True)  # 节点配置 JSON
    input_data     = Column(Text, nullable=True)  # 进入节点的输入
    output_data    = Column(Text, nullable=True)  # 执行结果
    error          = Column(Text, nullable=True)

    parent_node_id = Column(Integer, ForeignKey("flow_nodes.id"), nullable=True)

    instance       = relationship("FlowInstance", back_populates="nodes")
    parent         = relationship("FlowNode", remote_side=[id], backref="children")


class FlowEdge(Base, Timestamped):
    __tablename__ = "flow_edges"

    id             = Column(Integer, primary_key=True, autoincrement=True)
    instance_id    = Column(Integer, ForeignKey("flow_instances.id"), nullable=False)

    source_id      = Column(Integer, ForeignKey("flow_nodes.id"), nullable=False)
    target_id      = Column(Integer, ForeignKey("flow_nodes.id"), nullable=False)
    condition      = Column(String(50), nullable=True)  # true / false / default / "x > 5" 等分支标签

    weight         = Column(Float, default=0)


class FlowAgentLog(Base, Timestamped):
    __tablename__ = "flow_agent_logs"

    id             = Column(Integer, primary_key=True, autoincrement=True)
    instance_id    = Column(Integer, ForeignKey("flow_instances.id"), nullable=False)
    node_id        = Column(Integer, ForeignKey("flow_nodes.id"), nullable=True)

    prompt         = Column(Text, nullable=True)
    response       = Column(Text, nullable=True)
    tool_calls     = Column(Text, nullable=True)  # JSON: 工具调用记录
    tokens_used    = Column(Integer, default=0)
    error          = Column(Text, nullable=True)