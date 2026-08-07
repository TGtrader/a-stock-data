"""
多因子选股模块 — 一键筛选A股优质标的
======================================
基于六大类因子（价值/成长/质量/动量）+ 特殊反转因子，
行业中性化+Z-score标准化后加权排名。

特色因子：
  - 扭亏反转：识别上期亏损→本期盈利的反转信号
  - 营收跃进：Q1营收/去年全年营收 >30% 的爆发信号
  - 盈利加速度：增速在加快的公司
  - 现金流质量：经营现金流/净利润，识别利润含金量

快速使用:
  from 多因子选股 import screen, screen_turnaround, screen_value_growth

  # 全因子筛选
  result = screen(top_n=20)

  # 反转信号精选（扭亏/营收跃进/加速增长）
  result = screen_turnaround(top_n=15)

  # 价值+成长双维
  result = screen_value_growth(top_n=20)

CLI使用:
  python -m TG_trading_sys.cli screen --top 20
  python -m TG_trading_sys.cli screen --mode turnaround
  python -m TG_trading_sys.cli screen --list-factors
"""

import sys
import os

_pkg_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _pkg_root not in sys.path:
    sys.path.insert(0, _pkg_root)

from TG_trading_sys.factor.screener import (
    screen, get_universe,
    screen_value_growth, screen_quality_momentum, screen_turnaround,
)
from TG_trading_sys.factor.factor_registry import FactorRegistry, list_factors

__version__ = "4.0.0-alpha"
__all__ = [
    "screen", "get_universe",
    "screen_value_growth", "screen_quality_momentum", "screen_turnaround",
    "FactorRegistry", "list_factors",
]
