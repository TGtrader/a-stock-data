"""
TG-trading-sys 大盘 & 市场环境子系统
=====================================
大盘状态判定 + 板块轮动 + 情绪仪表盘 + 仓位中枢

核心 API:
  - detect_regime(code)          → 大盘牛熊状态
  - sector_rotation()            → 板块轮动排名
  - sentiment_dashboard()        → 市场情绪仪表盘
  - position_guide()             → 综合仓位建议
"""

from .regime import detect_regime, multi_index_regime
from .rotation import sector_rotation, rotation_summary
from .sentiment import sentiment_dashboard, MarketSentiment
from .position_guide import position_guide, PositionAdvice

__all__ = [
    "detect_regime", "multi_index_regime",
    "sector_rotation", "rotation_summary",
    "sentiment_dashboard", "MarketSentiment",
    "position_guide", "PositionAdvice",
]
