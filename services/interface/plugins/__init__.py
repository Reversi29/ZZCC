"""plugins/__init__.py — ZZCC OA 插件系统"""
from .registry import PluginRegistry, PluginStatus, PluginManifestError, registry
from .event_bus import EventBus, event_bus

__all__ = ["registry", "event_bus", "PluginRegistry", "PluginStatus", "PluginManifestError"]