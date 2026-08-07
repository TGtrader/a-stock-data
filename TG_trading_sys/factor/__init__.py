"""
TG-trading-sys 多因子选股子系统
===============================
六大类因子（价值/成长/质量/动量/资金/事件）+ 特殊反转因子
→ 行业中性化 + Z-score 标准化 → 复合因子加权排名

核心 API:
  - FactorRegistry.list()              → 列出所有已注册因子
  - compute_all_factors(codes)         → 全因子计算
  - composite_score(factor_df)         → 加权合成
  - screen(top_n=30, weights=...)      → 多因子筛选
  - screen_turnaround(top_n=20)        → 反转信号精选
  - screen_value_growth(top_n=20)      → 价值成长双维
"""

from .factor_registry import FactorRegistry, list_factors
from .composite import composite_score, rank_stocks, run_screening
from .standardization import industry_neutralize, zscore_normalize, winsorize
from .screener import screen, get_universe, screen_value_growth, screen_quality_momentum, screen_turnaround

__all__ = [
    "FactorRegistry", "list_factors",
    "composite_score", "rank_stocks", "run_screening",
    "industry_neutralize", "zscore_normalize", "winsorize",
    "screen", "get_universe",
    "screen_value_growth", "screen_quality_momentum", "screen_turnaround",
]
