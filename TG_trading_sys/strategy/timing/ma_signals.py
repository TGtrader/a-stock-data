"""
均线系统信号检测
================
基于多周期均线的技术信号：
  - MA金叉/死叉（5×10 / 10×20 / 20×60）
  - 多头/空头排列判断
  - 均线斜率变化（加速上扬/走平/拐头）
  - 量能确认（金叉放量确认强度）
  - 价格与均线乖离率
"""

import logging
from typing import Dict, List, Optional, Tuple
import numpy as np
import pandas as pd

logger = logging.getLogger("tg.strategy.ma")


def _ma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(window=period).mean()


def _ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def analyze_ma_system(df: pd.DataFrame) -> dict:
    """
    完整均线系统分析。

    需要 df 包含列: open, high, low, close, volume

    Returns:
        {
            "ma_alignment": dict,       # 均线排列状态
            "cross_signals": list,      # 近期金叉/死叉信号
            "slope_signals": list,     # 均线斜率信号
            "deviation": dict,          # 乖离率
            "signals": list,            # 综合信号列表
            "score": int,              # 均线系统评分 (0-100)
            "verdict": str,            # 综合判断
        }
    """
    if df is None or len(df) < 60:
        return _empty_ma_result("数据不足（至少60根K线）")

    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]

    # ── 计算各周期均线 ──
    ma5 = _ma(close, 5)
    ma10 = _ma(close, 10)
    ma20 = _ma(close, 20)
    ma60 = _ma(close, 60)
    ma120 = _ma(close, 120) if len(df) >= 120 else ma60

    avg_vol_20 = _ma(volume, 20)
    latest = len(df) - 1
    price = close.iloc[latest]

    # ── 1. 均线排列 ──
    alignment = _check_alignment(ma5, ma10, ma20, ma60, ma120, price, latest)

    # ── 2. 金叉/死叉检测 ──
    cross_signals = _detect_cross(df, ma5, ma10, ma20, ma60, volume, avg_vol_20)

    # ── 3. 均线斜率 ──
    slope_signals = _analyze_slopes(ma5, ma10, ma20, ma60, latest)

    # ── 4. 乖离率 ──
    deviation = _calc_deviation(close, ma5, ma10, ma20, ma60, latest)

    # ── 5. 综合评分 ──
    score = _ma_composite_score(alignment, cross_signals, slope_signals, deviation)

    # ── 6. 综合信号列表 ──
    signals = _build_ma_signals(alignment, cross_signals, slope_signals, deviation)

    # ── 7. 综合判断 ──
    verdict = _ma_verdict(score, alignment)

    return {
        "ma_alignment": alignment,
        "cross_signals": cross_signals,
        "slope_signals": slope_signals,
        "deviation": deviation,
        "signals": signals,
        "score": score,
        "verdict": verdict,
    }


def _check_alignment(ma5, ma10, ma20, ma60, ma120, price, latest) -> dict:
    """判断均线排列状态"""
    m5 = ma5.iloc[latest]
    m10 = ma10.iloc[latest]
    m20 = ma20.iloc[latest]
    m60 = ma60.iloc[latest]
    m120 = ma120.iloc[latest]

    # 多头排列：MA5>MA10>MA20>MA60
    if m5 > m10 > m20 > m60:
        # 完美多头
        if m5 > m20 * 1.05:
            state = "强势多头排列"
            strength = 90
        elif m5 > m20:
            state = "多头排列"
            strength = 75
        else:
            state = "多头排列(弱)"
            strength = 65
    # 空头排列：MA5<MA10<MA20<MA60
    elif m5 < m10 < m20 < m60:
        if m5 < m20 * 0.95:
            state = "强势空头排列"
            strength = 10
        else:
            state = "空头排列"
            strength = 20
    # 多头初期（MA5上穿MA10/MA20）
    elif m5 > m10 and m10 < m20 and price > m20:
        state = "多头初期（均线修复中）"
        strength = 55
    # 空头初期
    elif m5 < m10 and m10 > m20 and price < m20:
        state = "空头初期（均线恶化中）"
        strength = 35
    # 均线缠绕
    else:
        spread = (max(m5, m10, m20, m60) - min(m5, m10, m20, m60)) / abs(price) * 100 if price != 0 else 0
        if spread < 3:
            state = "均线高度粘合（即将变盘）"
            strength = 50
        else:
            state = "均线缠绕无方向"
            strength = 40

    return {
        "state": state,
        "strength": strength,
        "ma5": round(float(m5), 2),
        "ma10": round(float(m10), 2),
        "ma20": round(float(m20), 2),
        "ma60": round(float(m60), 2),
        "price_vs_ma20_pct": round((price - m20) / m20 * 100, 1) if m20 != 0 else 0,
        "price_vs_ma60_pct": round((price - m60) / m60 * 100, 1) if m60 != 0 else 0,
    }


def _detect_cross(df, ma5, ma10, ma20, ma60, volume, avg_vol_20) -> List[dict]:
    """检测近期的金叉/死叉信号"""
    signals = []
    n = len(df)
    lookback = min(20, n - 1)

    for i in range(max(0, n - lookback), n):
        if i < 2:
            continue
        date = df.index[i]

        # MA5 × MA10
        if ma5.iloc[i - 1] <= ma10.iloc[i - 1] and ma5.iloc[i] > ma10.iloc[i]:
            vol_ratio = volume.iloc[i] / avg_vol_20.iloc[i] if avg_vol_20.iloc[i] > 0 else 1
            strength = "强" if vol_ratio > 1.3 else ("弱" if vol_ratio < 0.7 else "中")
            signals.append({
                "date": date.strftime("%Y-%m-%d") if hasattr(date, "strftime") else str(date)[:10],
                "cross": "MA5↑MA10",
                "type": "金叉",
                "days_ago": n - 1 - i,
                "vol_ratio": round(float(vol_ratio), 2),
                "strength": strength,
            })

        # MA5 × MA20
        if ma5.iloc[i - 1] <= ma20.iloc[i - 1] and ma5.iloc[i] > ma20.iloc[i]:
            vol_ratio = volume.iloc[i] / avg_vol_20.iloc[i] if avg_vol_20.iloc[i] > 0 else 1
            strength = "强" if vol_ratio > 1.5 else ("弱" if vol_ratio < 0.7 else "中")
            signals.append({
                "date": date.strftime("%Y-%m-%d") if hasattr(date, "strftime") else str(date)[:10],
                "cross": "MA5↑MA20",
                "type": "金叉",
                "days_ago": n - 1 - i,
                "vol_ratio": round(float(vol_ratio), 2),
                "strength": strength,
            })

        # MA10 × MA20
        if ma10.iloc[i - 1] <= ma20.iloc[i - 1] and ma10.iloc[i] > ma20.iloc[i]:
            signals.append({
                "date": date.strftime("%Y-%m-%d") if hasattr(date, "strftime") else str(date)[:10],
                "cross": "MA10↑MA20",
                "type": "金叉",
                "days_ago": n - 1 - i,
                "vol_ratio": round(float(volume.iloc[i] / avg_vol_20.iloc[i]), 2) if avg_vol_20.iloc[i] > 0 else 1,
                "strength": "中",
            })

        # 死叉（同逻辑反向）
        if ma5.iloc[i - 1] >= ma10.iloc[i - 1] and ma5.iloc[i] < ma10.iloc[i]:
            signals.append({
                "date": date.strftime("%Y-%m-%d") if hasattr(date, "strftime") else str(date)[:10],
                "cross": "MA5↓MA10",
                "type": "死叉",
                "days_ago": n - 1 - i,
                "strength": "中",
            })

        if ma5.iloc[i - 1] >= ma20.iloc[i - 1] and ma5.iloc[i] < ma20.iloc[i]:
            signals.append({
                "date": date.strftime("%Y-%m-%d") if hasattr(date, "strftime") else str(date)[:10],
                "cross": "MA5↓MA20",
                "type": "死叉",
                "days_ago": n - 1 - i,
                "strength": "中",
            })

    return list(reversed(signals[-10:]))  # 最近10个


def _analyze_slopes(ma5, ma10, ma20, ma60, latest) -> List[dict]:
    """分析均线斜率变化"""
    signals = []
    lines = [
        ("MA5", ma5, 3, "短期"),
        ("MA10", ma10, 5, "短期"),
        ("MA20", ma20, 10, "中期"),
        ("MA60", ma60, 20, "中期"),
    ]

    for name, ma, lookback, scope in lines:
        if latest < lookback + 1:
            continue

        recent = ma.iloc[latest - lookback:latest + 1].dropna()
        if len(recent) < lookback // 2:
            continue

        # 线性回归斜率
        x = np.arange(len(recent))
        try:
            slope, _ = np.polyfit(x, recent.values, 1)
        except Exception:
            continue

        slope_pct = slope / recent.iloc[-1] * 100 * len(recent) if recent.iloc[-1] != 0 else 0

        if slope_pct > 3:
            direction = "加速上扬"
        elif slope_pct > 1:
            direction = "稳步上倾"
        elif slope_pct > -1:
            direction = "走平"
        elif slope_pct > -3:
            direction = "下行"
        else:
            direction = "加速下跌"

        signals.append({
            "ma": name,
            "scope": scope,
            "slope_pct": round(float(slope_pct), 2),
            "direction": direction,
        })

    return signals


def _calc_deviation(close, ma5, ma10, ma20, ma60, latest) -> dict:
    """计算价格与各均线的乖离率"""
    price = close.iloc[latest]

    dev = {}
    for name, ma in [("MA5", ma5), ("MA10", ma10), ("MA20", ma20), ("MA60", ma60)]:
        ma_val = ma.iloc[latest]
        if pd.isna(ma_val) or ma_val == 0:
            dev[name] = None
        else:
            dev[name] = round((price - ma_val) / ma_val * 100, 2)

    # 判断极端乖离
    max_dev = max(abs(v) for v in dev.values() if v is not None) if any(v is not None for v in dev.values()) else 0

    if max_dev > 15:
        risk = "极度超买（乖离过大，回调风险极高）"
    elif max_dev > 10:
        risk = "超买（短期有回调压力）"
    elif max_dev < -15:
        risk = "极度超卖（乖离过大，反弹概率高）"
    elif max_dev < -10:
        risk = "超卖（短期有反弹需求）"
    else:
        risk = "正常区间"

    return {"values": dev, "max_abs": round(max_dev, 2), "risk": risk}


def _ma_composite_score(alignment, cross_signals, slope_signals, deviation) -> int:
    """均线系统综合评分"""
    score = alignment.get("strength", 50)

    # 金叉加分
    recent_golden = [s for s in cross_signals
                     if s["type"] == "金叉" and s.get("days_ago", 99) <= 5]
    for s in recent_golden:
        if s.get("strength") == "强":
            score += 10
        else:
            score += 5

    # 死叉减分
    recent_death = [s for s in cross_signals
                    if s["type"] == "死叉" and s.get("days_ago", 99) <= 5]
    for s in recent_death:
        score -= 8

    # 斜率加分
    up_slopes = [s for s in slope_signals if "上扬" in s.get("direction", "")]
    down_slopes = [s for s in slope_signals if "下跌" in s.get("direction", "")]
    score += len(up_slopes) * 3 - len(down_slopes) * 3

    # 极端乖离调整
    max_dev = deviation.get("max_abs", 0)
    if max_dev > 12:
        score -= 15
    elif max_dev > 8:
        score -= 5

    return max(0, min(100, score))


def _build_ma_signals(alignment, cross_signals, slope_signals, deviation) -> List[dict]:
    """构建均线综合信号列表"""
    signals = []

    # 排列信号
    state = alignment.get("state", "")
    if "多头排列" in state:
        signals.append({"signal": state, "type": "均线排列", "action": "做多/持仓", "priority": 1})
    elif "空头排列" in state:
        signals.append({"signal": state, "type": "均线排列", "action": "做空/持币", "priority": 1})
    elif "粘合" in state:
        signals.append({"signal": state, "type": "均线排列", "action": "等待突破", "priority": 2})

    # 金叉/死叉
    for cs in cross_signals[-5:]:
        if cs["days_ago"] <= 5:
            action = "加仓" if cs["type"] == "金叉" else "减仓"
            signals.append({
                "signal": f"{cs['cross']}（{cs.get('strength', '')}）",
                "type": cs["type"],
                "action": action,
                "priority": 1,
                "date": cs["date"],
            })

    # 乖离信号
    risk = deviation.get("risk", "")
    if "超买" in risk or "超卖" in risk:
        signals.append({
            "signal": risk,
            "type": "乖离",
            "action": "减仓" if "超买" in risk else "关注",
            "priority": 2,
        })

    return signals


def _ma_verdict(score: int, alignment: dict) -> str:
    """均线综合判断"""
    state = alignment.get("state", "")
    if score >= 80:
        return f"均线强烈看多（{state}，评分{score}）"
    elif score >= 65:
        return f"均线偏多（{state}，评分{score}）"
    elif score >= 45:
        return f"均线中性（{state}，评分{score}）"
    elif score >= 25:
        return f"均线偏空（{state}，评分{score}）"
    else:
        return f"均线强烈看空（{state}，评分{score}）"


def _empty_ma_result(reason: str) -> dict:
    return {
        "ma_alignment": {"state": reason, "strength": 50},
        "cross_signals": [],
        "slope_signals": [],
        "deviation": {"values": {}, "max_abs": 0, "risk": reason},
        "signals": [],
        "score": 50,
        "verdict": reason,
    }
