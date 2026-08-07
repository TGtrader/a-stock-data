"""
TG-trading-sys 组合管理子系统
=============================
选股→建仓→回测→绩效→实盘跟踪 全流程。

核心 API:
  - build_portfolio(codes, method, constraints) → 组合配置
  - run_backtest(config) → 回测结果
  - compute_metrics(equity_curve, trades) → 绩效指标
  - monitor_portfolio(name) → 持仓快照+预警
"""

from .builder import build_portfolio, optimize_weights
from .constraints import PortfolioConstraints, validate_constraints
from .perf_metrics import compute_metrics, summary_table

__all__ = [
    "build_portfolio", "optimize_weights",
    "PortfolioConstraints", "validate_constraints",
    "compute_metrics", "summary_table",
]
