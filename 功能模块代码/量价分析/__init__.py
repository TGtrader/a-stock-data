"""
VPA 量价分析模块 — 基于威科夫理论的趋势交易量价分析系统
========================================================
数据源: mootdx(TCP) → Tushare(HTTP) → 腾讯(实时) 三级降级
资金流: Tushare moneyflow (主力/大单/特大单/散户)

核心能力:
  vpa_analyze(code)       — 单标的全量三维分析
  vpa_compare(codes)      — 多标量价对比排名
  vpa_screen(...)         — 三维条件筛选
  vpa_screen_index()      — 大盘指数量价状态
  vpa_screen_sectors()    — 行业板块量价扫描

便捷筛选:
  screen_best_buy_signals()           — 最强做多信号
  screen_smart_money_accumulating()   — 主力吸筹检测
  screen_risk_warnings()              — 风险预警
"""

from .vpa_engine import vpa_analyze, vpa_compare, print_vpa_report
from .vpa_screener import (
    vpa_screen, vpa_screen_index, vpa_screen_sectors,
    screen_best_buy_signals, screen_smart_money_accumulating, screen_risk_warnings,
)

__version__ = "1.0.0"
__all__ = [
    "vpa_analyze", "vpa_compare", "print_vpa_report",
    "vpa_screen", "vpa_screen_index", "vpa_screen_sectors",
    "screen_best_buy_signals", "screen_smart_money_accumulating", "screen_risk_warnings",
]
