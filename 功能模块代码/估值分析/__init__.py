"""
估值分析模块 — 一键生成个股综合估值报告
========================================
基于 DCF（现金流折现） + 相对估值（PE-PEG / PB-ROE） + 研报目标价共识，
自动从新浪财报/同花顺一致预期/东财研报提取数据，支持情景分析。

快速使用:
  from 估值分析 import val_report, print_val_report

  # 终端估值报告
  report = val_report("688017")
  print_val_report(report)

  # HTML 报告
  from TG_trading_sys.valuation.val_report import generate_html_report
  generate_html_report(report, "valuation_688017.html")

方法来源:
  - DCF: 两阶段自由现金流折现模型 (McKinsey)
  - PE-PEG: Peter Lynch PEG定价
  - PB-ROE: 戈登增长模型变形
  - 一致预期: 同花顺机构一致预期 + 东财研报
"""

import sys
import os

# 确保 TG_trading_sys 可导入
_pkg_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _pkg_root not in sys.path:
    sys.path.insert(0, _pkg_root)

from TG_trading_sys.valuation.val_report import val_report, print_val_report, generate_html_report
from TG_trading_sys.valuation.dcf import dcf_value, estimate_wacc
from TG_trading_sys.valuation.relative_val import relative_value, peg_value, pb_roe_value

__version__ = "4.0.0-alpha"
__all__ = [
    "val_report", "print_val_report", "generate_html_report",
    "dcf_value", "estimate_wacc",
    "relative_value", "peg_value", "pb_roe_value",
]
