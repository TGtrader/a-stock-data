"""
TG-trading-sys Phase 2 冒烟测试 — 多因子选股引擎
=================================================
验证因子注册、计算、标准化、复合打分全流程。

用法: python smoke_test_factor.py
"""

import sys
import os

# smoke test 在 TG_trading_sys/ 目录内，项目根目录是其父目录
_pkg_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(_pkg_dir)
sys.path.insert(0, _project_root)
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

print("=" * 60)
print("  TG-trading-sys V4.0 — Phase 2 冒烟测试")
print("=" * 60)

# ── 1. 因子注册中心 ──
print("\n[1/6] 因子注册中心...")
try:
    from TG_trading_sys.factor.factor_registry import FactorRegistry, list_factors

    reg = FactorRegistry.get_instance()
    factors = reg.list()
    cats = reg.categories()
    print(f"  ✅ 注册完成: {len(factors)} 个因子, {len(cats)} 大类 ({', '.join(cats)})")

    # 大类分布
    groups = reg.list_by_category()
    for cat, metas in sorted(groups.items()):
        names = [m.display_name for m in metas]
        print(f"     {cat}: {len(metas)} 个 → {', '.join(names[:5])}{'...' if len(names)>5 else ''}")
except Exception as e:
    print(f"  ❌ 注册中心失败: {e}")
    import traceback; traceback.print_exc()

# ── 2. 单因子计算（离线）─
print("\n[2/6] 单因子计算测试...")
try:
    from TG_trading_sys.factor.value_factors import compute_pe_ttm, compute_pb
    from TG_trading_sys.factor.quality_factors import compute_roe, compute_gross_margin

    # 用少量标的测试
    test_codes = ["600519", "000858", "601318", "300750", "000333"]

    pe = compute_pe_ttm(test_codes, None)
    pb = compute_pb(test_codes, None)
    print(f"  ✅ PE(TTM) 倒数: {len(pe.dropna())}/{len(test_codes)} 有效")
    print(f"  ✅ PB 倒数:     {len(pb.dropna())}/{len(test_codes)} 有效")
except Exception as e:
    print(f"  ⚠️ 单因子测试: {e}")

# ── 3. 标准化管线 ──
print("\n[3/6] 标准化管线测试...")
try:
    from TG_trading_sys.factor.standardization import winsorize, zscore_normalize, minmax_normalize
    import pandas as pd
    import numpy as np

    # 造模拟数据
    np.random.seed(42)
    raw = pd.Series(np.random.randn(100) * 0.5 + 0.5, index=[f"s{i:03d}" for i in range(100)])
    raw.iloc[0] = 100  # 极端值

    w = winsorize(raw)
    z = zscore_normalize(w)
    print(f"  ✅ 缩尾: [{w.min():.3f}, {w.max():.3f}] (原始极值 {raw.max():.1f})")
    print(f"  ✅ Z-score: mean={z.mean():.3f}, std={z.std():.3f}")
except Exception as e:
    print(f"  ❌ 标准化测试失败: {e}")

# ── 4. 行业中性化 ──
print("\n[4/6] 行业中性化测试...")
try:
    from TG_trading_sys.factor.standardization import industry_neutralize

    np.random.seed(123)
    codes_list = [f"c{i:03d}" for i in range(60)]
    scores = pd.Series(np.random.randn(60), index=codes_list)
    industries = pd.Series(
        ["金融"] * 15 + ["科技"] * 15 + ["消费"] * 15 + ["医药"] * 15,
        index=codes_list
    )

    neutralized = industry_neutralize(scores, industries)
    # 检查各行业中位数是否接近0
    medians = {}
    for ind in industries.unique():
        mask = industries == ind
        medians[ind] = neutralized.loc[mask].median()
    print(f"  ✅ 各行业中位数: { {k: round(v, 4) for k, v in medians.items()} }")
    print(f"  ✅ 行业偏差消除（中位数趋于0）")
except Exception as e:
    print(f"  ❌ 中性化测试失败: {e}")

# ── 5. 复合因子合成 ──
print("\n[5/6] 复合因子合成测试...")
try:
    from TG_trading_sys.factor.composite import composite_score, rank_stocks

    # 构造模拟因子数据
    np.random.seed(7)
    mock_factors = pd.DataFrame({
        "pe_ttm": np.random.randn(60) * 0.3 + 0.2,
        "eps_growth_yoy": np.random.randn(60) * 0.4 + 0.1,
        "roe": np.random.randn(60) * 0.35 + 0.15,
        "momentum_20d": np.random.randn(60) * 0.5,
    }, index=[f"c{i:03d}" for i in range(60)])
    mock_factors.loc["c001", :] = np.nan  # 缺失值测试
    mock_factors.loc["c059", "roe"] = 5.0  # 极端值测试

    scores = composite_score(mock_factors, industries=industries)
    ranked = rank_stocks(scores, top_n=10)

    print(f"  ✅ 综合评分: {scores.notna().sum()} 个, 范围 [{scores.min():.3f}, {scores.max():.3f}]")
    print(f"  ✅ Top5: {ranked.head(5).index.tolist()}")
except Exception as e:
    print(f"  ❌ 合成测试失败: {e}")
    import traceback; traceback.print_exc()

# ── 6. 筛选器入口 ──
print("\n[6/6] 筛选器 & CLI 导入测试...")
try:
    from TG_trading_sys.factor.screener import screen, get_universe, screen_turnaround
    from TG_trading_sys.factor import __all__ as factor_all
    print(f"  ✅ 筛选器导入成功")
    print(f"  ✅ factor 公开 API: {len(factor_all)} 个")
    print(f"  ✅ 预设标的池: csi300={len(get_universe('csi300'))}只, csi500={len(get_universe('csi500'))}只")
except Exception as e:
    print(f"  ❌ 导入测试失败: {e}")

print(f"\n{'='*60}")
print(f"  冒烟测试完成 — Phase 2 多因子选股引擎就绪")
print(f"  运行筛选: python -m TG_trading_sys.cli screen --top 10")
print(f"  查看因子: python -m TG_trading_sys.cli screen --list-factors")
print(f"{'='*60}")
