"""services/brain/__init__.py — 类脑 AI 系统入口"""
from . import broker, core, rules, memory, reasoning, semantic, action_executor
from .memory import working_memory, init_brain_tables
from .broker import broker as memory_broker
from .core import brain_core
from .reasoning import engine as reasoning_engine
from .action_executor import executor as action_executor_instance
from .rules import init_builtin_rules, register_rule

__all__ = [
    "broker", "memory_broker", "core", "brain_core", "rules", "memory", "reasoning", "semantic", "action_executor",
    "working_memory", "init_brain_tables", "init_builtin_rules",
    "reasoning_engine", "action_executor_instance", "register_rule",
]
