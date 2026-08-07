"""
大盘环境实时分析 V2 — 集成了极端日检测 + VPA 量价分析
========================================================
增强点:
  ① 单日极端现象检测（V型反转/放量止跌/爆量/冰点/沸点）
  ② VPA 量价分析集成（威科夫三大定律：供求/因果/投入产出）
  ③ 全市场涨跌家数统计
  ④ 日级反转信号捕捉
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import pandas as pd
import numpy as np
from datetime import datetime

from TG_trading_sys.data.cache import DataCache
from TG_trading_sys.market.regime import detect_regime, multi_index_regime, MAJOR_INDICES
from TG_trading_sys.market.sentiment import sentiment_dashboard
from TG_trading_sys.market.position_guide import position_guide

cache = DataCache()

print("=" * 70)
print("  TG-trading-sys V4.0 — A股大盘环境实时分析 V2")
print(f"  分析时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 70)

# ═══════════════════════════════════════════════════════════
# STEP 0: 获取全市场涨跌数据
# ═══════════════════════════════════════════════════════════
print("\n[0] 全市场涨跌家数 & 单日极端事件...")
advance_count = None
decline_count = None
total_stocks = None
today_breadth_pct = None

try:
    import requests
    # 东财全市场行情概览
    url = "https://push2.eastmoney.com/api/qt/clist/get"
    params = {
        "pn": "1", "pz": "1", "po": "0", "np": "1",
        "fltt": "2", "invt": "2",
        "fid": "f3", "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
        "fields": "f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f12,f13,f14",
        "ut": "bd1d9ddb04089700cf9c27f6f7426281",
    }
    resp = requests.get(url, params=params, timeout=10,
                      headers={"User-Agent": "Mozilla/5.0"})
    if resp.status_code == 200:
        data = resp.json()
        total_info = data.get("data", {}).get("total", 0)
        if total_info:
            total_stocks = total_info
            print(f"  全市场股票数: {total_stocks}")
except Exception:
    pass

# 尝试获取涨跌家数
try:
    # 上证涨跌家数
    url2 = "https://push2.eastmoney.com/api/qt/clist/get"
    params2 = {
        "pn": "1", "pz": "1", "po": "0", "np": "1",
        "fltt": "2", "invt": "2",
        "fid": "f3", "fs": "m:1+t:2",
        "fields": "f104,f105",
        "ut": "bd1d9ddb04089700cf9c27f6f7426281",
    }
    resp2 = requests.get(url2, params=params2, timeout=10,
                       headers={"User-Agent": "Mozilla/5.0"})
    if resp2.status_code == 200:
        data2 = resp2.json()
        diff = data2.get("data", {}).get("diff", {})
        if isinstance(diff, dict) and diff:
            advance_count = diff.get("f104", 0)
            decline_count = diff.get("f105", 0)
            if advance_count and decline_count:
                total = advance_count + decline_count
                today_breadth_pct = advance_count / total * 100 if total > 0 else 50
                print(f"  今日上涨: {advance_count} 家  |  下跌: {decline_count} 家  |  上涨比例: {today_breadth_pct:.1f}%")
except Exception:
    pass

# 判断单日极端状态
breadth_signal = ""
if today_breadth_pct is not None:
    if today_breadth_pct > 90:
        breadth_signal = "🔥 极度普涨 — 近乎全市场上涨，可能是底部反转或情绪高潮"
    elif today_breadth_pct > 80:
        breadth_signal = "📈 大幅普涨 — 超80%股票上涨，市场情绪强烈回暖"
    elif today_breadth_pct > 65:
        breadth_signal = "📊 偏多 — 多数股票上涨"
    elif today_breadth_pct < 10:
        breadth_signal = "🧊 极度普跌 — 近乎全市场下跌，恐慌性抛售"
    elif today_breadth_pct < 20:
        breadth_signal = "📉 大幅普跌 — 超80%股票下跌"

if breadth_signal:
    print(f"\n  >>> {breadth_signal}")

# ═══════════════════════════════════════════════════════════
# STEP 1: 大盘状态多维度判定（含极端日检测）
# ═══════════════════════════════════════════════════════════
print(f"\n{'='*70}")
print(f"  [1] 大盘状态多维度判定（5维：均线+动量+波动+量能+极端事件）")
print(f"{'='*70}")

index_regimes = {}
all_extreme_signals = []

for code, name in MAJOR_INDICES.items():
    df = cache.get_kline(code, lookback=200)
    if df is not None and len(df) >= 60:
        r = detect_regime(df)
        index_regimes[code] = {**r, "name": name}
        dims = r["dimensions"]
        price = df["close"].iloc[-1]
        chg_1d = (price - df["close"].iloc[-2]) / df["close"].iloc[-2] * 100 if len(df) >= 2 else 0
        chg_5d = (price - df["close"].iloc[-5]) / df["close"].iloc[-5] * 100 if len(df) >= 5 else 0
        chg_20d = (price - df["close"].iloc[-20]) / df["close"].iloc[-20] * 100 if len(df) >= 20 else 0

        print(f"  {name:<8} {r['regime']:<8} 评分{r['score']:>3}/100  "
              f"今日{chg_1d:+.1f}%  5日{chg_5d:+.1f}%  20日{chg_20d:+.1f}%  |  "
              f"均线{dims['ma_alignment']} 动量{dims['momentum']} 波动{dims['volatility']} "
              f"量{dims['volume']} 极端{dims.get('extreme_events', '?')}")

        # 收集极端信号
        for sig in r.get("extreme_signals", []):
            all_extreme_signals.append(f"[{name}] {sig}")

# 综合判定
composite = multi_index_regime(cache).get("composite", {})

# ── 极端事件汇总 ──
if all_extreme_signals:
    print(f"\n  ⚡ 近期极端事件（单日异常检测）:")
    for sig in all_extreme_signals[-12:]:
        print(f"     {sig}")

# ═══════════════════════════════════════════════════════════
# STEP 2: VPA 量价分析集成
# ═══════════════════════════════════════════════════════════
print(f"\n{'='*70}")
print(f"  [2] VPA 量价分析（威科夫三大定律）")
print(f"{'='*70}")

vpa_available = False
try:
    # 尝试从 量价分析 模块导入
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "功能模块代码"))
    from 量价分析 import vpa_analyze
    vpa_available = True
except ImportError:
    try:
        # 尝试从项目根目录导入
        from 量价分析 import vpa_analyze
        vpa_available = True
    except ImportError:
        pass

if vpa_available:
    # 对三大核心指数做VPA分析
    vpa_indices = {
        "000300": "沪深300",
        "000688": "科创50",
        "000905": "中证500",
    }
    for code, name in vpa_indices.items():
        try:
            vpa = vpa_analyze(code)
            if isinstance(vpa, dict) and "error" not in vpa:
                rating_detail = vpa.get("rating_detail", {})
                signals = vpa.get("signals", {})
                latest_bar = signals.get("latest_bar", {})
                recent = signals.get("recent_signals", [])
                signal_summary = signals.get("signal_summary", "")

                print(f"\n  【{name}】VPA评级: {vpa.get('rating', '?')} ({rating_detail.get('score', '?')}/100)")
                print(f"    最新K线: {latest_bar.get('body_type', '')} "
                      f"| 量{latest_bar.get('volume_level', '')} "
                      f"| 验证: {latest_bar.get('vpa_validation', '')}")
                if latest_bar.get("is_anomaly"):
                    print(f"    ⚠️ 异常K线: {latest_bar.get('candle_pattern') or '量价异常'}")

                # 去重显示
                seen_vpa = set()
                if recent:
                    print(f"    近期VPA信号:")
                    for sig in recent[-5:]:
                        key = sig.get("signal", "")
                        if key not in seen_vpa:
                            seen_vpa.add(key)
                            icon = {"趋势延续": "✅", "趋势启动": "🚀", "趋势衰竭": "⚠️", "趋势反转": "🔄", "趋势破坏": "❌"}
                            i = icon.get(sig.get("type", ""), "•")
                            print(f"      {i} {sig.get('date', '')} {key} → {sig.get('action', '')}")
                else:
                    print(f"    信号: {signal_summary}")
            else:
                print(f"\n  【{name}】VPA: 数据不足")
        except Exception as e:
            print(f"\n  【{name}】VPA分析异常: {e}")
else:
    print("  VPA模块未找到，跳过量价分析")

# ═══════════════════════════════════════════════════════════
# STEP 3: 反转信号综合判断
# ═══════════════════════════════════════════════════════════
print(f"\n{'='*70}")
print(f"  [3] 反转信号综合判断")
print(f"{'='*70}")

reversal_score = 0
reversal_signals_list = []

# 1. 单日涨跌比极端
if today_breadth_pct is not None:
    if today_breadth_pct > 85:
        reversal_score += 3
        reversal_signals_list.append(f"今日上涨比例{today_breadth_pct:.0f}% → 极端普涨（可能是V型反转）")
    elif today_breadth_pct < 15:
        reversal_score += 3
        reversal_signals_list.append(f"今日上涨比例{today_breadth_pct:.0f}% → 极端普跌（恐慌底）")

# 2. 从各指数检查20日跌幅是否过大（超卖）
for code, r in index_regimes.items():
    if "error" in r:
        continue
    name = r.get("name", code)
    details = r.get("details", {})
    chg_20 = details.get("price_vs_ma60_pct", 0)  # 用price vs MA60做超卖判断
    score = r.get("score", 50)
    # 检查是否有放量止跌信号
    for sig in r.get("extreme_signals", []):
        if "止跌" in sig:
            reversal_score += 2
            reversal_signals_list.append(f"{name}: {sig}")

# 3. VPA 信号汇总（去重）
if vpa_available:
    vpa_seen = set()
    for code, name in vpa_indices.items():
        try:
            vpa = vpa_analyze(code)
            if isinstance(vpa, dict) and "error" not in vpa:
                for sig in vpa.get("signals", {}).get("recent_signals", []):
                    if not isinstance(sig, dict):
                        continue
                    if sig.get("type", "") in ("趋势反转", "趋势启动"):
                        key = f"{sig['signal']}"
                        if key not in vpa_seen:
                            vpa_seen.add(key)
                            reversal_score += 1
                            reversal_signals_list.append(f"{name} VPA: {key}")
        except Exception:
            pass

print(f"  反转信号强度: {reversal_score} (≥3=反转概率较高)")
for s in reversal_signals_list:
    print(f"    → {s}")

if reversal_score >= 5:
    print(f"\n  🔥 多项指标显示强烈反转信号！")
elif reversal_score >= 3:
    print(f"\n  📈 有反转迹象，需要后续确认")
elif reversal_score >= 1:
    print(f"\n  ⚠️ 微弱反转信号，尚需观察")
else:
    print(f"\n  无明显反转信号，原有趋势可能延续")

# ═══════════════════════════════════════════════════════════
# STEP 4: 市场情绪
# ═══════════════════════════════════════════════════════════
print(f"\n[4] 市场情绪评估...")

# 获取涨停数据
limit_up = None
limit_down = None
try:
    import requests
    url_zt = "https://push2ex.eastmoney.com/getTopicZTPool"
    resp_zt = requests.get(url_zt,
        params={"ut": "7eea3edcaed734bea9cbfce24459ed57", "pageindex": "0",
                "pagesize": "300", "sort": "fbt", "sorttype": "desc", "market": "all",
                "_": str(int(datetime.now().timestamp() * 1000))},
        timeout=10, headers={"User-Agent": "Mozilla/5.0"})
    if resp_zt.status_code == 200:
        zt_data = resp_zt.json()
        zt_pool = zt_data.get("data", {}).get("pool", []) if zt_data.get("data") else []
        limit_up = len(zt_pool) if isinstance(zt_pool, list) else 0
except Exception:
    pass

try:
    url_dt = "https://push2ex.eastmoney.com/getTopicDTPool"
    resp_dt = requests.get(url_dt,
        params={"ut": "7eea3edcaed734bea9cbfce24459ed57", "pageindex": "0",
                "pagesize": "300", "sort": "fund", "sorttype": "desc", "market": "all",
                "_": str(int(datetime.now().timestamp() * 1000))},
        timeout=10, headers={"User-Agent": "Mozilla/5.0"})
    if resp_dt.status_code == 200:
        dt_data = resp_dt.json()
        dt_pool = dt_data.get("data", {}).get("pool", []) if dt_data.get("data") else []
        limit_down = len(dt_pool) if isinstance(dt_pool, list) else 0
except Exception:
    pass

if limit_up is not None:
    print(f"  涨停: {limit_up}只  |  跌停: {limit_down}只" +
          (f"  |  比: {limit_up}/{max(limit_down or 1, 1)}" if limit_down is not None else ""))

# 北向资金
nb_net = nb_5d = None
try:
    url_nb = "https://push2his.eastmoney.com/api/qt/kamt.kline/get"
    resp_nb = requests.get(url_nb,
        params={"fields1": "f1,f2,f3,f4", "fields2": "f51,f52,f53,f54",
                "klt": "101", "lmt": "5",
                "ut": "7eea3edcaed734bea9cbfce24459ed57",
                "_": str(int(datetime.now().timestamp() * 1000))},
        timeout=10, headers={"User-Agent": "Mozilla/5.0"})
    if resp_nb.status_code == 200:
        nb_data = resp_nb.json()
        klines = nb_data.get("data", {}).get("klines", []) if nb_data.get("data") else []
        if klines:
            latest = klines[-1].split(",")
            nb_net = float(latest[2]) / 10000 if len(latest) >= 3 and latest[2] else 0
            nb_5d = sum(float(k.split(",")[2]) if len(k.split(",")) >= 3 and k.split(",")[2] else 0
                       for k in klines[-5:]) / 10000
            print(f"  北向资金: 今日{nb_net:+.0f}亿  5日{nb_5d:+.0f}亿")
except Exception:
    pass

# 成交量比
vol_ratio = None
sh_df = cache.get_kline("000001", lookback=30)
if sh_df is not None and len(sh_df) >= 25:
    vol_ratio = sh_df["volume"].iloc[-5:].mean() / sh_df["volume"].iloc[-20:].mean()
    print(f"  上证量比(5/20): {vol_ratio:.2f}x")

sentiment = sentiment_dashboard(
    advance_decline_ratio=(advance_count / max(decline_count or 1, 1)) if advance_count else None,
    limit_up_count=limit_up,
    limit_down_count=limit_down,
    northbound_net=nb_net,
    northbound_5d=nb_5d,
    market_volume_ratio=vol_ratio,
)

print(f"\n  情绪评分: {sentiment.score}/100 — {sentiment.level}")
if sentiment.signals:
    for s in sentiment.signals:
        print(f"  → {s}")
print(f"  逆向建议: {sentiment.contrarian_signal}")

# ═══════════════════════════════════════════════════════════
# STEP 5: 仓位中枢
# ═══════════════════════════════════════════════════════════
advice = position_guide(
    composite if composite else {"regime": "震荡格局", "score": 50},
    sentiment,
)
print(f"\n{'='*70}")
print(f"  综合仓位建议")
print(f"{'='*70}")
print(f"  大盘状态: {advice.regime}")
print(f"  市场情绪: {advice.sentiment_level} ({sentiment.score}/100)")
print(f"  反转强度: {reversal_score} {'(≥3=值得关注)' if reversal_score >= 3 else ''}")
print(f"")
print(f"  ┌──────────────────────────────────────────┐")
print(f"  │  建议总仓位: {advice.total_position_pct:>5.0f}%"
      f"{' ' * 21}│")
print(f"  │  进攻型: {advice.aggressive_pct:>5.0f}%  │  防守型: {advice.defensive_pct:>5.0f}%  │")
print(f"  │  风格偏好: {advice.style_bias:<31}│")
print(f"  │  风险等级: {advice.risk_level:<31}│")
print(f"  └──────────────────────────────────────────┘")
print(f"")
print(f"  {advice.summary}")

# ── 反转信号加持建议修正 ──
if reversal_score >= 5 and advice.total_position_pct < 40:
    suggest = min(advice.total_position_pct + 15, 50)
    print(f"\n  💡 反转信号强烈(reversal={reversal_score})，可在现有{advice.total_position_pct:.0f}%仓位基础上"
          f"试探性加仓至{suggest:.0f}%，但严格止损")

print(f"\n{'='*70}")
print(f"  分析完成 — TG-trading-sys V4.0 V2")
print(f"{'='*70}")
