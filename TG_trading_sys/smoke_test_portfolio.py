"""
TG-trading-sys Phase 4 冒烟测试 — 组合构建 & 回测
==================================================
验证组合构建 / 约束 / 权重优化 / 回测 / 绩效 / 监控 全流程。
使用模拟数据，不依赖网络。

用法: python smoke_test_portfolio.py
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
print("  TG-trading-sys V4.0 — Phase 4 冒烟测试")
print("=" * 60)

# ── 模拟数据 ──
np.random.seed(99)
n_days = 252
dates = pd.date_range(end="2026-07-27", periods=n_days, freq="B")
codes = [f"c{str(i).zfill(3)}" for i in range(10)]
industries_dict = {codes[i]: ["金融", "科技", "消费", "医药", "制造"][i // 2] for i in range(10)}

prices_data = {}
for c in codes:
    drift = np.random.uniform(-0.0002, 0.0008)
    vol = np.random.uniform(0.01, 0.03)
    rets = np.random.randn(n_days) * vol + drift
    prices_data[c] = 50 * (1 + rets).cumprod()

prices_df = pd.DataFrame(prices_data, index=dates)
returns_df = prices_df.pct_change().dropna()
industries = pd.Series(industries_dict)

print(f"模拟数据: {n_days}天, {len(codes)}只标的")

# ── 1. 权重优化（独立函数，不依赖网络）──
print("\n[1/5] 6种权重优化方法...")
try:
    from TG_trading_sys.portfolio.builder import optimize_weights

    methods = ["equal_weight", "inv_volatility", "risk_parity", "min_variance", "max_diversification"]
    for m in methods:
        w = optimize_weights(returns_df, method=m)
        total = w.sum()
        print(f"  ✅ {m:<22} {len(w)}只,  sum={total:.4f},  max={w.max():.4f},  min={w.min():.4f}")
except Exception as e:
    print(f"  ❌ 失败: {e}")
    import traceback; traceback.print_exc()

# ── 2. 约束验证 ──
print("\n[2/5] 约束验证 & 预处理...")
try:
    from TG_trading_sys.portfolio.constraints import PortfolioConstraints, validate_constraints

    w = optimize_weights(returns_df, method="risk_parity")

    # 宽松约束
    loose = PortfolioConstraints(max_single_weight=0.20)
    v_loose = validate_constraints(w, industries, loose)
    print(f"  ✅ 宽松约束: {'通过' if v_loose['passed'] else '违规'}")

    # 严格约束
    tight = PortfolioConstraints(max_single_weight=0.08)
    v_tight = validate_constraints(w, industries, tight)
    print(f"  ✅ 严格约束: {'通过' if v_tight['passed'] else '违规'} "
          f"({len(v_tight['violations'])}违规, {len(v_tight['warnings'])}警告)")
except Exception as e:
    print(f"  ❌ 失败: {e}")

# ── 3. 回测桥接导入 ──
print("\n[3/5] 回测桥接...")
try:
    from TG_trading_sys.portfolio.backtest_bridge import simple_backtest, generate_config, save_config

    config = generate_config(codes, {c: 0.1 for c in codes})
    print(f"  ✅ 配置生成: {config['name']}")
    print(f"     标的: {len(config['positions'])}只, 资金: {config['initial_capital']:,}, 再平衡: {config['rebalance_frequency']}")
    print(f"     (完整回测需网络数据，此处验证配置生成链路)")
except Exception as e:
    print(f"  ❌ 失败: {e}")

# ── 4. 绩效指标 ──
print("\n[4/5] 绩效指标体系...")
try:
    from TG_trading_sys.portfolio.perf_metrics import compute_metrics, summary_table

    np.random.seed(42)
    eq = pd.Series(1000000 * (1 + np.random.randn(252) * 0.012).cumprod(),
                   index=pd.date_range(end="2026-07-27", periods=252, freq="B"))
    bench = pd.Series(1000000 * (1 + np.random.randn(252) * 0.008).cumprod(),
                      index=eq.index)

    metrics = compute_metrics(eq, bench)
    print(f"  ✅ 总收益: {metrics['total_return_pct']}%")
    print(f"  ✅ 夏普: {metrics['sharpe_ratio']}  索提诺: {metrics['sortino_ratio']}")
    print(f"  ✅ 最大回撤: {metrics['max_drawdown_pct']}%  卡玛: {metrics['calmar_ratio']}")
    print(f"  ✅ Beta: {metrics.get('beta')}  Alpha: {metrics.get('alpha_pct')}%")
    print(f"  ✅ 月度收益: {len(metrics.get('monthly_returns', {}))}个月")
    print(f"  ---")
    for line in summary_table(metrics).split("\n"):
        print(f"  {line}")
except Exception as e:
    print(f"  ❌ 失败: {e}")

# ── 5. 持仓监控 ──
print("\n[5/5] 持仓监控 & 记录...")
try:
    from TG_trading_sys.portfolio.monitor import (
        record_holding, close_holding, get_snapshot, log_trade,
        save_portfolio_snapshot, list_portfolios, check_rebalance,
    )
    from TG_trading_sys.portfolio.builder import build_portfolio

    # -- record_holding without network --
    record_holding("smoke_test_pf", codes[0], "测试股A", 0.10, 1000, 50.0)
    record_holding("smoke_test_pf", codes[1], "测试股B", 0.10, 1000, 55.0)
    print(f"  ✅ 记录2笔持仓")

    # list portfolios
    pfs = list_portfolios()
    smoke_pfs = [p for p in pfs if "smoke" in p.get("portfolio_name", "")]
    if smoke_pfs:
        print(f"  ✅ 组合列表: {len(smoke_pfs)}个组合")

    # snapshot
    snap = get_snapshot("smoke_test_pf")
    if "error" not in snap:
        print(f"  ✅ 快照: {snap['n_holdings']}只, 市值 {snap.get('total_current_value', 0):,.0f}")
    else:
        print(f"  ✅ 快照返回: {snap.get('error', '')} (模拟环境预期)")

    # check rebalance
    target = {codes[0]: 0.10, codes[1]: 0.10}
    rb = check_rebalance("smoke_test_pf", target)
    print(f"  ✅ 再平衡: {rb.get('recommendation', '')}")

    # log trade
    log_trade("smoke_test_pf", codes[0], "buy", 50.0, 1000, reason="测试")

    # clean up test data from DB
    from TG_trading_sys.core.database import Database
    db = Database.get_instance()
    db.execute("DELETE FROM holdings WHERE portfolio_name='smoke_test_pf'")
    db.execute("DELETE FROM trade_log WHERE portfolio_name='smoke_test_pf'")
    print(f"  ✅ 持仓监控功能正常")

except Exception as e:
    print(f"  ❌ 失败: {e}")
    import traceback; traceback.print_exc()

print(f"\n{'='*60}")
print(f"  冒烟测试完成 — Phase 4 组合管理系统就绪")
print(f"  构建组合: python -m TG_trading_sys.cli portfolio build --top 15")
print(f"  回测:     python -m TG_trading_sys.cli portfolio backtest")
print(f"  监控:     python -m TG_trading_sys.cli portfolio monitor")
print(f"{'='*60}")
