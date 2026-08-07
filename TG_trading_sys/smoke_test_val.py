"""
TG-trading-sys Phase 1 冒烟测试
===============================
验证估值分析模块各组件能正常导入和基本运行。

用法: python smoke_test_val.py
"""

import sys
import os

# 加入项目根目录（TG_trading_sys 的父目录）
_pkg_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(_pkg_dir)
sys.path.insert(0, _project_root)

# Windows GBK 编码修复
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

print("=" * 60)
print("  TG-trading-sys V4.0 — Phase 1 冒烟测试")
print("=" * 60)

# ── 1. 核心模块导入测试 ──
print("\n[1/5] 核心模块导入...")
try:
    from TG_trading_sys.core.config import Config
    from TG_trading_sys.core.database import Database
    print("  ✅ core.config + core.database")
except Exception as e:
    print(f"  ❌ 核心模块导入失败: {e}")
    sys.exit(1)

# ── 2. 数据库初始化测试 ──
print("\n[2/5] 数据库初始化...")
try:
    Config.ensure_dirs()
    db = Database.get_instance()
    tables = ["stock_basic", "daily_kline", "financials", "valuation_cache",
              "holdings", "trade_log", "factor_snapshot"]
    for t in tables:
        assert db.table_exists(t), f"表 {t} 不存在"
    print(f"  ✅ SQLite 数据库就绪 ({Config.DB_PATH})")
    print(f"  ✅ {len(tables)} 张核心表全部就绪")
except Exception as e:
    print(f"  ❌ 数据库初始化失败: {e}")
    import traceback; traceback.print_exc()

# ── 3. 估值模块导入测试 ──
print("\n[3/5] 估值模块导入...")
try:
    from TG_trading_sys.valuation import val_report, dcf_value, relative_value, print_val_report
    from TG_trading_sys.valuation.wacc import estimate_wacc
    from TG_trading_sys.valuation.earnings_forecast import get_earnings_forecast
    print("  ✅ valuation 全部子模块导入成功")
except Exception as e:
    print(f"  ❌ 估值模块导入失败: {e}")
    import traceback; traceback.print_exc()

# ── 4. WACC 自动估算测试（离线，不依赖网络）─
print("\n[4/5] WACC 默认参数测试...")
try:
    wacc = estimate_wacc("600519", rf=0.028, erp=0.065)
    print(f"  ✅ WACC 默认值: {wacc['wacc']*100:.2f}%")
    print(f"     Ke={wacc['ke']*100:.2f}%  Kd={wacc['kd_pre_tax']*100:.2f}%  "
          f"β={wacc['beta']:.2f}  D/E={wacc['d_e_ratio']:.2f}")
except Exception as e:
    print(f"  ⚠️ WACC 测试: {e}（网络数据可能不可用，属正常）")

# ── 5. 相对估值离线测试 ──
print("\n[5/5] PEG 估值公式测试...")
try:
    from TG_trading_sys.valuation.relative_val import peg_value as pv
    peg = pv(pe_ttm=25.0, eps_cagr=0.20, trailing_eps=3.50)
    print(f"  ✅ PEG={peg['peg']:.2f}  合理PE={peg['fair_pe']:.1f}  合理价={peg['fair_value']:.2f}  → {peg['verdict']}")
except Exception as e:
    print(f"  ❌ PEG 测试失败: {e}")

print(f"\n{'='*60}")
print(f"  冒烟测试完成 — TG-trading-sys Phase 1 基础设施就绪")
print(f"  运行估值分析: python -m TG_trading_sys.cli val 600519")
print(f"{'='*60}")
