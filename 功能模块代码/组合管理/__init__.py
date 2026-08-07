"""
组合管理模块 — 选股→建仓→回测→监控
=====================================
支持6种权重方法、风险约束、内置回测引擎、实盘持仓监控。

快速使用:
  from 组合管理 import build_portfolio, simple_backtest, get_snapshot

  # 从筛选结果构建组合
  portfolio = build_portfolio(codes, method="risk_parity")

  # 回测
  result = simple_backtest(codes, weights, start_date="2024-01-01")

  # 持仓监控
  snap = get_snapshot("portfolio_demo")
"""

import sys
import os

_pkg_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _pkg_root not in sys.path:
    sys.path.insert(0, _pkg_root)

from TG_trading_sys.portfolio.builder import build_portfolio, optimize_weights
from TG_trading_sys.portfolio.constraints import PortfolioConstraints, validate_constraints
from TG_trading_sys.portfolio.backtest_bridge import simple_backtest, generate_config
from TG_trading_sys.portfolio.perf_metrics import compute_metrics, summary_table
from TG_trading_sys.portfolio.monitor import (
    get_snapshot, save_portfolio_snapshot, list_portfolios, check_rebalance,
)

__version__ = "4.0.0-alpha"
__all__ = [
    "build_portfolio", "optimize_weights",
    "PortfolioConstraints", "validate_constraints",
    "simple_backtest", "generate_config",
    "compute_metrics", "summary_table",
    "get_snapshot", "save_portfolio_snapshot", "list_portfolios", "check_rebalance",
]
