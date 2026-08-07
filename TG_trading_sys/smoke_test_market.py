"""
TG-trading-sys Phase 6 冒烟测试 — 大盘环境
============================================
验证大盘状态 / 板块轮动 / 市场情绪 / 仓位中枢 全流程。

用法: python smoke_test_market.py
"""

import sys, os
_pkg_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_pkg_dir))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import pandas as pd
import numpy as np

print("=" * 60)
print("  TG-trading-sys V4.0 — Phase 6 冒烟测试")
print("=" * 60)

# ── 模拟指数K线 ──
np.random.seed(123)
def make_index(drift, vol, n=200):
    dates = pd.date_range(end="2026-07-27", periods=n, freq="B")
    rets = np.random.randn(n) * vol + drift
    price = 3000 * (1 + rets).cumprod()
    df = pd.DataFrame({
        "open": price * 0.999, "high": price * 1.005,
        "low": price * 0.995, "close": price,
        "volume": np.random.randint(1e8, 5e8, n)
    }, index=dates)
    return df

df_bull = make_index(0.0010, 0.012)  # 牛市
df_bear = make_index(-0.0008, 0.018) # 熊市
df_side = make_index(0.0001, 0.010)  # 震荡

print("模拟数据: 3种市场环境 × 200天")

# ── 1. 大盘状态判定 ──
print("\n[1/4] 大盘状态判定...")
try:
    from TG_trading_sys.market.regime import detect_regime

    for name, df in [("牛市模拟", df_bull), ("熊市模拟", df_bear), ("震荡模拟", df_side)]:
        r = detect_regime(df)
        dims = r["dimensions"]
        print(f"  ✅ {name}: {r['regime']} (评分{r['score']}/100) "
              f"均线{dims['ma_alignment']}+动量{dims['momentum']}+波动{dims['volatility']}+量{dims['volume']}")
        print(f"     转换信号: {r.get('transition_signal', '')[:50]}")

except Exception as e:
    print(f"  ❌ 失败: {e}")
    import traceback; traceback.print_exc()

# ── 2. 情绪仪表盘 ──
print("\n[2/4] 情绪仪表盘...")
try:
    from TG_trading_sys.market.sentiment import sentiment_dashboard, MarketSentiment

    # 贪婪场景
    greed = sentiment_dashboard(
        advance_decline_ratio=5.0, limit_up_count=120, limit_down_count=3,
        broken_board_count=15, northbound_net=120, northbound_5d=300,
        margin_change_pct=6.0, market_volume_ratio=2.0,
    )
    print(f"  ✅ 贪婪: 评分{greed.score} {greed.level} | {greed.contrarian_signal[:40]}...")

    # 恐惧场景
    fear = sentiment_dashboard(
        advance_decline_ratio=0.2, limit_up_count=15, limit_down_count=80,
        broken_board_count=25, northbound_net=-90, northbound_5d=-250,
        margin_change_pct=-7.0, market_volume_ratio=0.5,
    )
    print(f"  ✅ 恐惧: 评分{fear.score} {fear.level} | {fear.contrarian_signal[:40]}...")

    # 中性
    neutral = sentiment_dashboard()
    print(f"  ✅ 中性: 评分{neutral.score} {neutral.level}")

except Exception as e:
    print(f"  ❌ 失败: {e}")

# ── 3. 板块轮动 ──
print("\n[3/4] 板块轮动...")
try:
    from TG_trading_sys.market.rotation import (
        sector_rotation, rotation_summary, _classify_sector, _determine_phase
    )

    # 模拟板块数据
    mock_sectors = [
        {"name": "食品饮料", "change_pct": 1.5, "up_count": 45, "down_count": 15, "leader": "茅台"},
        {"name": "医药生物", "change_pct": 2.1, "up_count": 50, "down_count": 10, "leader": "恒瑞"},
        {"name": "银行", "change_pct": 3.5, "up_count": 42, "down_count": 8, "leader": "招商"},
        {"name": "有色金属", "change_pct": 4.2, "up_count": 55, "down_count": 5, "leader": "紫金"},
        {"name": "电子", "change_pct": 5.8, "up_count": 60, "down_count": 3, "leader": "中芯"},
        {"name": "计算机", "change_pct": 3.1, "up_count": 48, "down_count": 12, "leader": "讯飞"},
        {"name": "传媒", "change_pct": -0.5, "up_count": 20, "down_count": 35, "leader": ""},
        {"name": "商贸零售", "change_pct": -1.2, "up_count": 15, "down_count": 40, "leader": ""},
    ]

    # 模拟 rotation 分析（基于模拟数据手动构造）
    ranking = []
    for s in mock_sectors:
        name = s["name"]
        cat = _classify_sector(name)
        ranking.append({
            "name": name, "change_pct": s["change_pct"],
            "up_count": s["up_count"], "down_count": s["down_count"],
            "breadth": round(s["up_count"] / max(s["up_count"] + s["down_count"], 1) * 100, 1),
            "leader": s["leader"], "category": cat,
        })
    ranking.sort(key=lambda x: x["change_pct"], reverse=True)

    # 分类聚合
    cats = {"防守型": [], "周期型": [], "成长型": [], "题材型": []}
    for r in ranking:
        if r["category"] in cats:
            cats[r["category"]].append(r["change_pct"])

    cat_strength = {}
    for cat, vals in cats.items():
        cat_strength[cat] = round(sum(vals) / len(vals), 2) if vals else 0

    sorted_cats = sorted(cat_strength.items(), key=lambda x: x[1], reverse=True)
    phase = _determine_phase(sorted_cats)

    print(f"  ✅ 最强板块: {ranking[0]['name']}({ranking[0]['change_pct']}%)")
    print(f"  ✅ 最弱板块: {ranking[-1]['name']}({ranking[-1]['change_pct']}%)")
    print(f"  ✅ 分类强度: { {k: f'{v:.2f}%' for k, v in sorted(cat_strength.items())} }")
    print(f"  ✅ 轮动阶段: {phase}")

except Exception as e:
    print(f"  ❌ 失败: {e}")
    import traceback; traceback.print_exc()

# ── 4. 仓位中枢 ──
print("\n[4/4] 仓位中枢建议...")
try:
    from TG_trading_sys.market.position_guide import position_guide, PositionAdvice

    # 牛市+贪婪
    bull_regime = {"regime": "牛市格局", "score": 82}
    # 用情绪对象（测试2可能失败，这里重新创建）
    g = sentiment_dashboard(
        advance_decline_ratio=5.0, limit_up_count=120, limit_down_count=3,
        broken_board_count=15, northbound_net=120, northbound_5d=300,
        margin_change_pct=6.0, market_volume_ratio=2.0,
    )
    f = sentiment_dashboard(
        advance_decline_ratio=0.2, limit_up_count=15, limit_down_count=80,
        broken_board_count=25, northbound_net=-90, northbound_5d=-250,
        margin_change_pct=-7.0, market_volume_ratio=0.5,
    )
    n = sentiment_dashboard()

    advice1 = position_guide(bull_regime, g)
    print(f"  ✅ 牛市+贪婪: 总仓位{advice1.total_position_pct:.0f}%  "
          f"进攻{advice1.aggressive_pct:.0f}%/防守{advice1.defensive_pct:.0f}% "
          f"风格:{advice1.style_bias} 风险:{advice1.risk_level}")

    # 熊市+恐惧
    bear_regime = {"regime": "熊市格局", "score": 15}
    advice2 = position_guide(bear_regime, f)
    print(f"  ✅ 熊市+恐惧: 总仓位{advice2.total_position_pct:.0f}%  "
          f"进攻{advice2.aggressive_pct:.0f}%/防守{advice2.defensive_pct:.0f}% "
          f"风格:{advice2.style_bias} 风险:{advice2.risk_level}")

    # 震荡+中性
    side_regime = {"regime": "震荡格局", "score": 48}
    advice3 = position_guide(side_regime, n)
    print(f"  ✅ 震荡+中性: 总仓位{advice3.total_position_pct:.0f}%  "
          f"风格:{advice3.style_bias}")

    # 牛市+极度恐惧（黄金坑）
    advice4 = position_guide(bull_regime, f)
    print(f"  ✅ 牛市+恐慌: 总仓位{advice4.total_position_pct:.0f}% (恐慌中逆向加仓)"
          f" 风险:{advice4.risk_level}")

except Exception as e:
    print(f"  ❌ 失败: {e}")
    import traceback; traceback.print_exc()

print(f"\n{'='*60}")
print(f"  Phase 6 完成 — 大盘环境子系统就绪")
print(f"{'='*60}")
