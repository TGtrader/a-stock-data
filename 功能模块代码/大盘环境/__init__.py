"""
大盘环境模块 — 状态判定 + 轮动 + 情绪 + 仓位中枢
===================================================
四大子系统：
  - 大盘状态: 多维牛熊判定 + 六大指数综合 + 状态转换信号
  - 板块轮动: 行业强弱排名 + 四类板块聚合 + 轮动方向
  - 情绪仪表: 7维度加权评分 + 贪婪/恐惧指数
  - 仓位中枢: 三要素加权决策 + 攻防配置 + 风格偏好

快速使用:
  from 大盘环境 import detect_regime, sentiment_dashboard, position_guide

  regime = detect_regime(df)
  sentiment = sentiment_dashboard(...)
  advice = position_guide(regime, sentiment, rotation)
"""

import sys
import os

_pkg_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _pkg_root not in sys.path:
    sys.path.insert(0, _pkg_root)

from TG_trading_sys.market.regime import detect_regime, multi_index_regime
from TG_trading_sys.market.rotation import sector_rotation, rotation_summary
from TG_trading_sys.market.sentiment import sentiment_dashboard, MarketSentiment
from TG_trading_sys.market.position_guide import position_guide, PositionAdvice

__version__ = "4.0.0-alpha"
__all__ = [
    "detect_regime", "multi_index_regime",
    "sector_rotation", "rotation_summary",
    "sentiment_dashboard", "MarketSentiment",
    "position_guide", "PositionAdvice",
]
