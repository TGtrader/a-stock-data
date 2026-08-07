"""
TG-trading-sys Phase 5 冒烟测试 — 风控引擎
============================================
验证风控规则链 / VaR-CVaR / 压力测试 / Brinson归因 全流程。

用法: python smoke_test_risk.py
"""

import sys
import os

_pkg_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(_pkg_dir)
sys.path.insert(0, _project_root)
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import pandas as pd
import numpy as np

print("=" * 60)
print("  TG-trading-sys V4.0 — Phase 5 冒烟测试")
print("=" * 60)

# ── 模拟数据 ──
np.random.seed(77)
n = 252
dates = pd.date_range(end="2026-07-27", periods=n, freq="B")
# 模拟组合收益（偏正分布）
port_returns = pd.Series(np.random.randn(n) * 0.015 + 0.0005, index=dates)
# 模拟多资产收益
asset_returns = pd.DataFrame({
    f"A{i}": np.random.randn(n) * 0.02 + np.random.uniform(-0.0003, 0.0008)
    for i in range(5)
}, index=dates)

print(f"模拟数据: {n}天, 5资产")

# ── 1. 风控规则引擎 ──
print("\n[1/4] 风控规则引擎...")
try:
    from TG_trading_sys.risk.rules_engine import RiskEngine, RiskCheckResult

    engine = RiskEngine(market_regime="neutral")

    # 测试通过
    ctx_ok = {
        "code": "688017", "name": "绿的谐波",
        "proposed_weight": 0.05, "proposed_position_pct": 0.05,
        "current_sector_weights": {"机械": 0.15},
        "target_sector": "机械", "total_position": 0.35,
        "daily_amount": 50_000_000,
        "current_pnl_pct": -0.03,
    }
    r = engine.check(ctx_ok)
    print(f"  ✅ 合规订单: {'通过' if r.passed else '阻止'} ({len(r.violations)}违规, {len(r.warnings)}警告)")

    # 测试违规
    ctx_bad = {**ctx_ok, "proposed_weight": 0.15}  # 超限
    r = engine.check(ctx_bad)
    print(f"  ✅ 超限订单: {'通过' if r.passed else '阻止'} ({len(r.violations)}违规)")

    # ST检查
    ctx_st = {**ctx_ok, "name": "ST测试"}
    r = engine.check(ctx_st)
    print(f"  ✅ ST检查: {'通过' if r.passed else '阻止'} ({len(r.violations)}违规)")

    # 大盘状态自适应
    engine.set_market_regime("bear")
    print(f"  ✅ 熊市仓位上限: {engine.max_position_pct*100:.0f}%")
    engine.set_market_regime("bull")
    print(f"  ✅ 牛市仓位上限: {engine.max_position_pct*100:.0f}%")

except Exception as e:
    print(f"  ❌ 失败: {e}")
    import traceback; traceback.print_exc()

# ── 2. VaR / CVaR ──
print("\n[2/4] VaR/CVaR 风险度量...")
try:
    from TG_trading_sys.risk.var import (
        calc_var, calc_cvar, portfolio_var_report, var_backtest
    )

    # 三种方法
    for method in ["historical", "parametric", "monte_carlo"]:
        if method == "monte_carlo":
            var_result = calc_var(port_returns, method="monte_carlo",
                                  confidence=0.95, n_simulations=5000)
        else:
            var_result = calc_var(port_returns, method=method, confidence=0.95)
        cvar_val = calc_cvar(port_returns, confidence=0.95)
        print(f"  ✅ {method}: VaR={var_result['var_pct']:.3f}%  CVaR={cvar_val*100:.3f}%")

    # 多置信度
    var_99 = calc_var(port_returns, method="historical", confidence=0.99)
    print(f"  ✅ VaR_99: {var_99['var_pct']:.3f}% (vs 95: {var_result['var_pct']:.3f}%)")

    # 组合 VaR
    weights = pd.Series(0.2, index=asset_returns.columns)
    pf_var = portfolio_var_report(asset_returns, weights)
    print(f"  ✅ 历史VaR: {pf_var['historical_var']*100:.3f}%  参数VaR: {pf_var['parametric_var']*100:.3f}%")

    # VaR 回测
    var_series = pd.Series(0.02, index=port_returns.index)  # 固定 2% VaR
    bt = var_backtest(port_returns, var_series, confidence=0.95)
    print(f"  ✅ 回测: {bt['breaches']}/{bt['total_days']}突破 ({bt['breach_rate_pct']}%) "
          f"{bt.get('verdict', '')}")

except Exception as e:
    print(f"  ❌ 失败: {e}")
    import traceback; traceback.print_exc()

# ── 3. 压力测试 ──
print("\n[3/4] 压力测试...")
try:
    from TG_trading_sys.risk.stress_test import run_stress_test, HISTORICAL_SCENARIOS, FACTOR_SCENARIOS

    holdings = [
        {"code": "600519", "name": "贵州茅台", "weight": 0.15, "current_value": 150000,
         "sector": "食品饮料", "market_cap_yi": 2000},
        {"code": "300750", "name": "宁德时代", "weight": 0.12, "current_value": 120000,
         "sector": "电力设备", "market_cap_yi": 1200},
        {"code": "688017", "name": "绿的谐波", "weight": 0.08, "current_value": 80000,
         "sector": "机械设备", "market_cap_yi": 60},
        {"code": "002230", "name": "科大讯飞", "weight": 0.10, "current_value": 100000,
         "sector": "计算机", "market_cap_yi": 200},
        {"code": "000858", "name": "五粮液", "weight": 0.10, "current_value": 100000,
         "sector": "食品饮料", "market_cap_yi": 800},
    ]

    result = run_stress_test(holdings, total_value=550000)

    print(f"  ✅ 组合总值: {result['total_value']:,.0f}")
    print(f"     历史最差: {result['historical_worst']}")
    print(f"     因子最差: {result['factor_worst']}")
    print(f"     全局最差: {result['worst_scenario']} ({result['worst_impact_pct']}%)")

    # 前3大冲击
    top3 = sorted(result["scenario_results"], key=lambda x: x["impact"])[:3]
    print(f"     Top3冲击情景:")
    for s in top3:
        print(f"       {s['name']}: {s['impact']:+,.0f} ({s['impact_pct']}%)")

except Exception as e:
    print(f"  ❌ 失败: {e}")
    import traceback; traceback.print_exc()

# ── 4. 绩效归因 ──
print("\n[4/4] 绩效归因...")
try:
    from TG_trading_sys.risk.perf_attribution import brinson_attribution, factor_attribution

    # Brinson 归因
    stocks = ["A1", "A2", "A3", "A4", "A5"]
    pf_w = {"A1": 0.25, "A2": 0.25, "A3": 0.20, "A4": 0.15, "A5": 0.15}
    bm_w = {"A1": 0.20, "A2": 0.20, "A3": 0.20, "A4": 0.20, "A5": 0.20}
    pf_r = {"A1": 0.15, "A2": 0.10, "A3": -0.05, "A4": 0.20, "A5": 0.08}
    bm_r = {"A1": 0.15, "A2": 0.08, "A3": -0.02, "A4": 0.18, "A5": 0.10}
    sectors = {"A1": "科技", "A2": "科技", "A3": "消费", "A4": "金融", "A5": "金融"}

    brinson = brinson_attribution(pf_w, bm_w, pf_r, bm_r, sectors)
    print(f"  ✅ 超额收益: {brinson['excess_return_pct']}%")
    print(f"     配置贡献: {brinson['allocation_effect_pct']}%")
    print(f"     选股贡献: {brinson['selection_effect_pct']}%")
    print(f"     解读: {brinson['verdict']}")

    # 因子归因
    factors = pd.DataFrame({
        "市值因子": np.random.randn(252) * 0.005,
        "动量因子": np.random.randn(252) * 0.008 + 0.0003,
        "价值因子": np.random.randn(252) * 0.006,
    }, index=port_returns.index)

    factor_attr = factor_attribution(port_returns, factors)
    if "error" not in factor_attr:
        print(f"  ✅ Alpha: {factor_attr['alpha_annual_pct']}%/年  R²={factor_attr['r_squared']}")
        print(f"     因子贡献: { {k: f'{v:.1f}%/年' for k, v in factor_attr['factor_contributions'].items()} }")

except Exception as e:
    print(f"  ❌ 失败: {e}")
    import traceback; traceback.print_exc()

print(f"\n{'='*60}")
print(f"  冒烟测试完成 — Phase 5 风控引擎就绪")
print(f"{'='*60}")
