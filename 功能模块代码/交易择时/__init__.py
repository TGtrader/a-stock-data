"""
交易择时模块 — 多策略信号融合 + 交易计划生成
==============================================
整合五大信号源：
  - 均线系统（金叉/死叉/排列/斜率）
  - 形态识别（箱体突破/三角形/W底-M头/旗形）
  - 资金面（北向/融资/主力资金流/背离）
  - 事件驱动（研报上调/业绩超预期）
  - VPA 量价分析（威科夫理论）✅ 已有

→ 多信号聚合裁决 → 出入场计划 + 仓位建议

快速使用:
  from 交易择时 import analyze_timing, print_timing_report

  report = analyze_timing("688017")
  print_timing_report(report)
"""

import sys
import os

_pkg_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _pkg_root not in sys.path:
    sys.path.insert(0, _pkg_root)

from TG_trading_sys.strategy.timing.signal_aggregator import aggregate_signals, SignalVerdict
from TG_trading_sys.strategy.timing.trade_plan import generate_trade_plan
from TG_trading_sys.strategy.timing.ma_signals import analyze_ma_system
from TG_trading_sys.strategy.timing.pattern_signals import detect_patterns
from TG_trading_sys.strategy.timing.fund_signals import analyze_fund_signals
from TG_trading_sys.strategy.timing.event_signals import analyze_event_signals

__version__ = "4.0.0-alpha"
__all__ = [
    "aggregate_signals", "SignalVerdict",
    "generate_trade_plan",
    "analyze_ma_system", "detect_patterns",
    "analyze_fund_signals", "analyze_event_signals",
]
