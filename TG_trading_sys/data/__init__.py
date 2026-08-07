"""
TG-trading-sys 数据层
====================
统一数据获取 + SQLite 缓存。
复用现有 SKILL.md 中的 40 端点能力，
将数据拉取结果持久化到本地 SQLite。
"""

from .cache import DataCache
from .sync import SyncManager

__all__ = ["DataCache", "SyncManager"]
