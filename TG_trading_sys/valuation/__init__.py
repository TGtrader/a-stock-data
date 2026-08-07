"""
TG-trading-sys 估值分析子模块
=============================
提供 DCF（现金流折现）估值、相对估值（PE-PEG / PB-ROE）、
研报目标价参考和情景分析。

核心 API:
  - val_report(code)        → 综合估值报告
  - dcf_value(code)         → DCF 每股内在价值
  - relative_value(code)    → 相对估值
  - print_val_report(code)  → 终端打印估值报告
"""

from .val_report import val_report, print_val_report
from .dcf import dcf_value, estimate_wacc
from .relative_val import relative_value, peg_value, pb_roe_value

__all__ = [
    "val_report", "print_val_report",
    "dcf_value", "estimate_wacc",
    "relative_value", "peg_value", "pb_roe_value",
]
