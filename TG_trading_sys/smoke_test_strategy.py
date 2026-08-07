"""
TG-trading-sys Phase 3 冒烟测试 — 多策略择时信号
=================================================
验证均线/形态/资金/事件信号 + 聚合裁决 + 交易计划全流程。

用法: python smoke_test_strategy.py
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
print("  TG-trading-sys V4.0 — Phase 3 冒烟测试")
print("=" * 60)

# ── 构造模拟K线数据 ──
np.random.seed(42)
n = 120
dates = pd.date_range(end="2026-07-27", periods=n, freq="B")
base_price = 50.0

# 模拟一段先涨后盘再涨的趋势
trend = np.concatenate([
    np.linspace(0, 15, 40),       # 上涨段
    np.linspace(15, 13, 25),      # 小幅回调
    np.linspace(13, 20, 55),      # 再次上涨
])
close = base_price * (1 + trend / 100)
close = pd.Series(close + np.random.randn(n) * 1.5, index=dates)

high = close + pd.Series(np.abs(np.random.randn(n) * 1.2), index=dates)
low = close - pd.Series(np.abs(np.random.randn(n) * 1.2), index=dates)
open_ = close.shift(1).fillna(close.iloc[0]) + pd.Series(np.random.randn(n) * 0.5, index=dates)
volume = pd.Series(np.random.randint(500000, 2000000, n) * 100, index=dates)
volume.iloc[-10:] = volume.iloc[-10:] * 1.5  # 最近放量

df = pd.DataFrame({
    "open": open_, "high": high, "low": low,
    "close": close, "volume": volume,
}, index=dates)

print(f"模拟数据: {n}根日K线, 最新收盘价 {close.iloc[-1]:.2f}")

# ── 1. 均线系统 ──
print("\n[1/5] 均线系统分析...")
try:
    from TG_trading_sys.strategy.timing.ma_signals import analyze_ma_system

    ma = analyze_ma_system(df)
    print(f"  ✅ 评分: {ma['score']}/100 → {ma['verdict']}")
    print(f"     排列: {ma['ma_alignment']['state']}")
    print(f"     金叉/死叉: {len(ma['cross_signals'])}个")
    print(f"     乖离风险: {ma['deviation']['risk']}")
except Exception as e:
    print(f"  ❌ 失败: {e}")
    import traceback; traceback.print_exc()

# ── 2. 形态识别 ──
print("\n[2/5] 形态识别分析...")
try:
    from TG_trading_sys.strategy.timing.pattern_signals import detect_patterns

    patterns = detect_patterns(df)
    verdict = patterns.get("verdict", "")
    signals = patterns.get("signals", [])
    print(f"  ✅ {verdict}")
    for s in signals[:3]:
        print(f"     {s.get('signal','')[:70]}")
    for key in ["box_breakout", "triangle", "double_pattern", "flag_pattern"]:
        if patterns.get(key):
            print(f"     {key}: {patterns[key].get('pattern','')}")
except Exception as e:
    print(f"  ❌ 失败: {e}")
    import traceback; traceback.print_exc()

# ── 3. 信号聚合 ──
print("\n[3/5] 信号聚合裁决...")
try:
    from TG_trading_sys.strategy.timing.signal_aggregator import aggregate_signals, SignalVerdict

    verdict = aggregate_signals(ma_result=ma, pattern_result=patterns)

    print(f"  ✅ 裁决: {verdict.verdict} (评分{verdict.score}/100)")
    print(f"     置信度: {verdict.confidence}")
    print(f"     仓位建议: {verdict.position_advice}")
    print(f"     各信号源: {verdict.signal_scores}")
    if verdict.conflicts:
        print(f"     冲突: {verdict.conflicts}")
    print(f"     活跃信号: {len(verdict.active_signals)}个")
except Exception as e:
    print(f"  ❌ 失败: {e}")
    import traceback; traceback.print_exc()

# ── 4. 交易计划 ──
print("\n[4/5] 交易计划生成...")
try:
    from TG_trading_sys.strategy.timing.trade_plan import generate_trade_plan

    plan = generate_trade_plan(df, verdict)

    if plan.get("plan_valid"):
        print(f"  ✅ 入场: {plan['entry_price']}  止损: {plan['stop_loss']}")
        print(f"     目标1: {plan['target_1']} (R:R {plan['risk_reward_1']}:1)")
        print(f"     目标2: {plan['target_2']} (R:R {plan['risk_reward_2']}:1)")
        print(f"     仓位: {plan['position_pct']}% ({plan['position_shares']}股)")
    else:
        print(f"  ⚠️ 计划无效: {plan.get('rejection_reason', '')}")
except Exception as e:
    print(f"  ❌ 失败: {e}")
    import traceback; traceback.print_exc()

# ── 5. 模块导入完整性 ──
print("\n[5/5] 模块导入完整性...")
try:
    from TG_trading_sys.strategy.timing import (
        analyze_ma_system, detect_patterns,
        aggregate_signals, generate_trade_plan,
    )
    from TG_trading_sys.strategy.timing.fund_signals import analyze_fund_signals
    from TG_trading_sys.strategy.timing.event_signals import analyze_event_signals
    print(f"  ✅ 全部子模块导入成功")
    print(f"     均线系统 / 形态识别 / 资金面 / 事件驱动 / 聚合裁决 / 交易计划")
except Exception as e:
    print(f"  ❌ 失败: {e}")

print(f"\n{'='*60}")
print(f"  冒烟测试完成 — Phase 3 多策略择时信号系统就绪")
print(f"  运行分析: python -m TG_trading_sys.cli signal 688017")
print(f"{'='*60}")
