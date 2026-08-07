"""
多策略择时信号系统
==================
整合五大类信号源：
  - VPA 量价分析（威科夫理论）✅ 已有
  - 均线系统信号（金叉/死叉/排列/斜率）
  - 形态识别信号（突破/反转/整理）
  - 资金面信号（北向/融资/大宗）
  - 事件驱动信号（研报/业绩/增减持）

→ 信号聚合裁决 → 交易计划生成
"""

from .ma_signals import analyze_ma_system
from .pattern_signals import detect_patterns
from .signal_aggregator import aggregate_signals, SignalVerdict
from .trade_plan import generate_trade_plan

__all__ = [
    "analyze_ma_system",
    "detect_patterns",
    "aggregate_signals", "SignalVerdict",
    "generate_trade_plan",
]
