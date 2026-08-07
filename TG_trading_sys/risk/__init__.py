"""
TG-trading-sys 风控子系统
=========================
事前规则检查 + 事中风险监控 + 事后压力测试 + 绩效归因

核心 API:
  - RiskEngine.check(order)         → 事前风控检查
  - calc_var(returns)               → VaR/CVaR
  - run_stress_test(portfolio)      → 压力测试
  - attribution(portfolio, bench)   → Brinson/因子归因
"""

from .rules_engine import RiskEngine, RiskRule, RiskCheckResult
from .var import calc_var, calc_cvar, historical_var
from .stress_test import run_stress_test, StressScenario

__all__ = [
    "RiskEngine", "RiskRule", "RiskCheckResult",
    "calc_var", "calc_cvar", "historical_var",
    "run_stress_test", "StressScenario",
]
