"""
风控引擎模块 — 事前/事中/事后全流程风险管理
============================================
  - 事前风控规则链（单票/行业/总仓位/止损/ST/流动性）
  - VaR / CVaR 风险度量（历史模拟/参数法/蒙特卡洛）
  - 压力测试（5种历史情景 + 5种因子冲击）
  - 绩效归因（Brinson + 因子归因）

快速使用:
  from 风控引擎 import RiskEngine, calc_var, run_stress_test

  # 风控检查
  engine = RiskEngine(market_regime="neutral")
  result = engine.check({"code": "688017", "proposed_weight": 0.08, ...})

  # VaR
  var = calc_var(returns, method="historical", confidence=0.95)

  # 压力测试
  report = run_stress_test(holdings)
"""

import sys
import os

_pkg_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _pkg_root not in sys.path:
    sys.path.insert(0, _pkg_root)

from TG_trading_sys.risk.rules_engine import RiskEngine, RiskRule, RiskCheckResult
from TG_trading_sys.risk.var import calc_var, calc_cvar, historical_var, portfolio_var_report
from TG_trading_sys.risk.stress_test import run_stress_test, StressScenario, custom_scenario
from TG_trading_sys.risk.perf_attribution import brinson_attribution, factor_attribution

__version__ = "4.0.0-alpha"
__all__ = [
    "RiskEngine", "RiskRule", "RiskCheckResult",
    "calc_var", "calc_cvar", "historical_var", "portfolio_var_report",
    "run_stress_test", "StressScenario", "custom_scenario",
    "brinson_attribution", "factor_attribution",
]
