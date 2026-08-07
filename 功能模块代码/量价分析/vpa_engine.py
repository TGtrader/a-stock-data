"""
VPA 综合研判引擎 — 趋势×量价×资金流 三维综合评级
==================================================
整合趋势分析、信号检测、资金流分析，输出统一的 VpaReport。
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

try:
    from .vpa_data import get_adapter
    from .vpa_signals import analyze_signals
    from .vpa_trend import analyze_trend
    from .vpa_moneyflow import analyze_moneyflow, assess_flow_trend_resonance
except ImportError:
    from vpa_data import get_adapter
    from vpa_signals import analyze_signals
    from vpa_trend import analyze_trend
    from vpa_moneyflow import analyze_moneyflow, assess_flow_trend_resonance

logger = logging.getLogger("vpa.engine")


# ═══════════════════════════════════════════════════════════════
# 单标的全量分析
# ═══════════════════════════════════════════════════════════════

def vpa_analyze(
    code: str,
    period: str = "daily",
    lookback: int = 120,
    name: str = None,
    market: str = None,
) -> dict:
    """
    单标的完整量价分析。

    Args:
        code: 股票/指数代码（纯数字如 "688017"）
        period: daily | 60min | 30min | 15min | 5min
        lookback: 回溯K线数
        name: 名称（可选，自动从腾讯获取）
        market: 市场（可选）

    Returns:
        VpaReport dict — 包含三维评级和完整分析结果
    """
    adapter = get_adapter()

    # ── 1. 数据获取 ──
    df = adapter.get_ohlcv(code, period=period, lookback=lookback)
    if df is None or df.empty:
        return _error_report(code, "OHLCV数据获取失败，所有数据源均不可用")

    if len(df) < 20:
        return _error_report(code, f"数据不足（仅{len(df)}根K线），至少需要20根")

    # ── 2. 基本信息 ──
    basic_info = adapter.get_stock_basic(code)
    if not name and basic_info.get("name"):
        name = basic_info["name"]

    float_mv = basic_info.get("float_mv", 0)  # 万元

    # ── 3. 趋势分析 ──
    trend = analyze_trend(df)

    # ── 4. 信号检测 ──
    signals = analyze_signals(df)
    if "error" in signals:
        return _error_report(code, signals["error"])

    # ── 5. 资金流分析 ──
    mf_df = adapter.get_moneyflow(code, lookback_days=60)
    mf_result = analyze_moneyflow(mf_df, float_mv)
    flow_trend = assess_flow_trend_resonance(trend, mf_result)

    # ── 6. 三维综合评级 ──
    rating = _compute_rating(trend, signals, flow_trend)

    # ── 7. 组装报告 ──
    report = {
        "code": code,
        "name": name or code,
        "market": market or _guess_market(code),
        "date": datetime.now().strftime("%Y-%m-%d"),
        "period": period,
        "data_points": len(df),

        # 三维评级
        "rating": rating["rating"],
        "rating_detail": rating,

        # 趋势
        "trend": {
            "short_term": trend.get("short_term", {}),
            "medium_term": trend.get("medium_term", {}),
            "alignment": trend.get("alignment", {}),
        },

        # 量价信号
        "signals": {
            "latest_bar": signals.get("latest_bar", {}),
            "recent_signals": signals.get("recent_signals", []),
            "signal_summary": signals.get("signal_summary", ""),
        },

        # 阶段和位置
        "position": {
            "phase": trend.get("phase", {}),
            "sr_levels": trend.get("sr_levels", {}),
        },

        # 资金流
        "money_flow": {
            "available": mf_result.get("available", False),
            "continuous_flow": {
                k: v for k, v in mf_result.items()
                if k.startswith("continuous") or k.startswith("max") or k.startswith("flow")
            },
            "flow_ratios": mf_result.get("flow_ratios", {}),
            "smart_retail": mf_result.get("smart_retail", {}),
            "flow_trend_resonance": flow_trend,
        },

        # 综合建议
        "conclusion": _generate_conclusion(code, name, rating, trend, signals, flow_trend),
    }

    return report


# ═══════════════════════════════════════════════════════════════
# 三维评级算法
# ═══════════════════════════════════════════════════════════════

def _compute_rating(trend: dict, signals: dict, flow_trend: dict) -> dict:
    """
    趋势(40%) × 量价(30%) × 资金流(30%) = 综合评分
    """
    # 趋势维度 (0-100, 权重40%)
    trend_score = trend.get("short_term", {}).get("strength", 50)
    trend_dir = trend.get("short_term", {}).get("direction", "")
    if trend_dir == "上涨":
        trend_adjusted = trend_score
    elif trend_dir == "下跌":
        trend_adjusted = 100 - trend_score  # 反转：下跌趋势分越高越看空
    else:
        trend_adjusted = 50

    # 量价维度 (0-100, 权重30%)
    vpa_score = 50
    recent_signals = signals.get("recent_signals", [])
    if recent_signals:
        continuation = sum(1 for s in recent_signals if s["type"].startswith("趋势延续") or s["type"].startswith("趋势启动"))
        exhaustion = sum(1 for s in recent_signals if s["type"].startswith("趋势衰竭"))
        if continuation > 0 and exhaustion == 0:
            vpa_score = 80
        elif continuation > exhaustion:
            vpa_score = 65
        elif exhaustion > continuation:
            vpa_score = 30
        elif exhaustion > 0:
            vpa_score = 20

    # 检查最新K线异常
    latest_bar = signals.get("latest_bar", {})
    if latest_bar.get("is_anomaly"):
        vpa_score -= 15

    # 资金流维度 (0-100, 权重30%)
    flow_score = flow_trend.get("signal_strength", 50)
    if not flow_trend.get("resonance"):
        flow_score = 50  # 无数据时中性

    # 加权综合
    overall = int(trend_adjusted * 0.40 + vpa_score * 0.30 + flow_score * 0.30)

    # 评级
    if overall >= 75:
        rating = "趋势做多"
    elif overall >= 55:
        rating = "偏多"
    elif overall >= 35:
        rating = "观望"
    elif overall >= 20:
        rating = "偏空"
    else:
        rating = "持币/做空"

    return {
        "rating": rating,
        "score": overall,
        "trend_score": trend_adjusted,
        "vpa_score": vpa_score,
        "flow_score": flow_score,
    }


# ═══════════════════════════════════════════════════════════════
# 综合建议生成
# ═══════════════════════════════════════════════════════════════

def _generate_conclusion(code: str, name: str, rating: dict, trend: dict,
                         signals: dict, flow_trend: dict) -> str:
    """生成自然语言综合建议"""
    rt = rating["rating"]
    score = rating["score"]

    st = trend.get("short_term", {})
    mt = trend.get("medium_term", {})
    align = trend.get("alignment", {})
    flow = flow_trend

    emoji = {"趋势做多": "[BUY]", "偏多": "[BUY]", "观望": "[WAIT]", "偏空": "[SELL]", "持币/做空": "[SELL]"}
    e = emoji.get(rt, "⚪")

    parts = [
        f"【三维评级：{e} {rt}，综合强度 {score}/100】",
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"趋势维度({rating['trend_score']}/100)：{st.get('summary', '数据不足')}",
        f"量价维度({rating['vpa_score']}/100)：{signals.get('signal_summary', '')}",
        f"资金维度({rating['flow_score']}/100)：{flow.get('summary', '数据不足')}",
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"短中期共振：{align.get('alignment', '')} → {align.get('signal', '')}",
    ]

    # 操作建议
    actions = []
    if rt == "趋势做多":
        actions.append("① 持仓者可继续持有，止损设在动态通道下轨")
        actions.append("② 空仓者等待缩量回调至MA10附近+资金流仍净流入时入场")
        actions.append("③ 关注首次出现射击十字星+放量止涨信号时减仓")
    elif rt == "偏多":
        actions.append("① 可轻仓参与，严格止损")
        actions.append("② 等待更多趋势确认信号后加仓")
    elif rt == "观望":
        actions.append("① 不建议新开仓位")
        actions.append("② 已持仓者考虑减仓至半仓")
        actions.append("③ 等待方向明确（放量突破盘整区或跌破支撑）")
    elif rt in ("偏空", "持币/做空"):
        actions.append("① 建议减仓或清仓")
        actions.append("② 不参与反弹（除非出现明确的放量止跌+锤头线确认）")
        actions.append("③ 持币观望，等待下一个趋势启动信号")

    parts.append("操作建议：")
    parts.extend(actions)

    return "\n".join(parts)


# ═══════════════════════════════════════════════════════════════
# 多标对比
# ═══════════════════════════════════════════════════════════════

def vpa_compare(codes: List[str], period: str = "daily", lookback: int = 120) -> List[dict]:
    """
    多标的量价对比排名。

    Args:
        codes: 股票代码列表（最多20只）
        period: 分析周期
        lookback: 回溯K线数

    Returns:
        按综合评分排序的对比列表
    """
    if len(codes) > 20:
        codes = codes[:20]

    results = []
    for code in codes:
        try:
            report = vpa_analyze(code, period=period, lookback=lookback)
            if "error" not in report:
                results.append({
                    "code": code,
                    "name": report.get("name", code),
                    "rating": report["rating"]["rating"],
                    "score": report["rating"]["score"],
                    "trend_score": report["rating"]["trend_score"],
                    "vpa_score": report["rating"]["vpa_score"],
                    "flow_score": report["rating"]["flow_score"],
                    "short_term_direction": report["trend"]["short_term"].get("direction", ""),
                    "phase": report["position"]["phase"].get("phase", ""),
                    "resonance": report["money_flow"]["flow_trend_resonance"].get("resonance", ""),
                })
        except Exception as e:
            logger.warning(f"对比分析失败 {code}: {e}")
            results.append({"code": code, "error": str(e)})

    # 按综合评分排序
    results.sort(key=lambda x: x.get("score", 0), reverse=True)

    return results


# ═══════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════

def _guess_market(code: str) -> str:
    code = code.strip()
    if code.startswith("6"):
        return "上海主板"
    elif code.startswith("0") or code.startswith("3"):
        return "深圳"
    elif code.startswith("68"):
        return "科创板"
    elif code.startswith("8"):
        return "北交所"
    return "其他"


def _error_report(code: str, error_msg: str) -> dict:
    return {
        "code": code,
        "date": datetime.now().strftime("%Y-%m-%d"),
        "error": error_msg,
        "rating": {"rating": "无法评估", "score": 0},
    }


# ═══════════════════════════════════════════════════════════════
# 便捷函数
# ═══════════════════════════════════════════════════════════════

def print_vpa_report(report: dict):
    """打印量价分析报告到终端"""
    if "error" in report:
        print(f"X 分析失败: {report['error']}")
        return

    print(f"\n{'='*60}")
    print(f"  量价分析报告 — {report['name']}({report['code']})")
    print(f"{'='*60}")
    print(f"  日期: {report['date']}    周期: {report['period']}")
    rd = report.get('rating_detail', {})
    print(f"  评级: {report.get('rating','?')} ({rd.get('score','?')}/100)")
    print(f"{'='*60}")

    st = report["trend"]["short_term"]
    print(f"  【短期趋势】{st.get('direction','')} / {st.get('phase','')} / 强度{st.get('strength',0)}")
    ch = st.get("channel", {})
    if ch.get("upper"):
        print(f"  【动态通道】上轨{ch['upper']} | 下轨{ch['lower']} | 止损{ch.get('stop_loss','')}")

    mt = report["trend"]["medium_term"]
    print(f"  【中期趋势】{mt.get('direction','')} → {mt.get('constraint','')}")

    align = report["trend"]["alignment"]
    print(f"  【趋势共振】{align.get('alignment','')} => {align.get('signal','')}")

    lb = report["signals"]["latest_bar"]
    print(f"  【最新K线】{lb.get('date','')} | {lb.get('body_type','')} | 量{lb.get('volume_level','')}")
    print(f"            量价验证: {lb.get('vpa_validation','')} | 异常: {lb.get('is_anomaly',False)}")

    phase = report["position"]["phase"]
    print(f"  【阶段判断】{phase.get('phase','')}(置信度{phase.get('confidence',0)})")

    sr = report["position"]["sr_levels"]
    if sr.get("nearest_support"):
        print(f"  【支撑阻力】支撑{sr['nearest_support']} | 阻力{sr['nearest_resistance']} | 现价{sr['current_price']}")

    print(f"  【近期信号】")
    for sig in report["signals"]["recent_signals"][-5:]:
        icon = {"趋势延续": "[+]", "趋势启动": "[>>]", "趋势衰竭": "[-]", "趋势反转": "[?]", "趋势破坏": "[X]", "趋势确认": "[OK]"}
        action_map = {"加仓": "+", "减仓": "-", "持仓": "=", "离场": "X", "关注": "?", "持仓/加仓": "=", "观察": "?", "观察/准备加仓": "?"}
        i = icon.get(sig.get("type", ""), "•")
        a = action_map.get(sig.get("action", ""), "")
        print(f"    {sig['date']} {i} {sig['signal']} → {a}{sig['action']}")

    mf = report["money_flow"]
    if mf.get("available"):
        ft = mf["flow_trend_resonance"]
        print(f"  【资金流】{ft.get('resonance','')} | 强度{ft.get('signal_strength',0)}")
        sr_div = mf.get("smart_retail", {})
        if sr_div.get("divergence"):
            print(f"            主力vs散户: {sr_div['divergence']}")

    print(f"\n{report['conclusion']}")
    print(f"{'='*60}\n")
