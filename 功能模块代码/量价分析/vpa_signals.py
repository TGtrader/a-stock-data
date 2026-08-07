"""
VPA 信号检测层 — 威科夫量价分析信号系统
========================================
基于安娜·库林《量价分析》一书的核心方法论。

检测层级：
  1. 单K线形态 (9种)
  2. 量价确认/异常 (威科夫投入产出定律)
  3. 多K线序列信号 (趋势延续/衰竭/反转 共16种)
  4. 成交量相对水平
  5. 信号优先级排序
"""

import logging
from typing import Dict, List, Optional, Tuple
import numpy as np
import pandas as pd

logger = logging.getLogger("vpa.signals")

# ═══════════════════════════════════════════════════════════════
# 基础计算
# ═══════════════════════════════════════════════════════════════

def _ma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(window=period).mean()


def _body(open_: pd.Series, close: pd.Series) -> pd.Series:
    return (close - open_).abs()


def _total_range(high: pd.Series, low: pd.Series) -> pd.Series:
    return (high - low).replace(0, np.nan)


def _upper_shadow(open_: pd.Series, high: pd.Series, close: pd.Series) -> pd.Series:
    return high - pd.concat([open_, close], axis=1).max(axis=1)


def _lower_shadow(open_: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    return pd.concat([open_, close], axis=1).min(axis=1) - low


def _body_ratio(open_: pd.Series, high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    return _body(open_, close) / _total_range(high, low)


# ═══════════════════════════════════════════════════════════════
# 成交量相对水平
# ═══════════════════════════════════════════════════════════════

def classify_volume(volume: float, avg_volume_20: float) -> Tuple[str, int]:
    """将成交量分为7个等级"""
    if avg_volume_20 <= 0:
        return "无法判断", 0
    ratio = volume / avg_volume_20
    if ratio >= 2.0:   return "极高", 100
    if ratio >= 1.5:   return "高", 75
    if ratio >= 1.1:   return "高于平均", 55
    if ratio >= 0.9:   return "平均", 45
    if ratio >= 0.6:   return "低于平均", 30
    if ratio >= 0.3:   return "低", 15
    return "极低", 5


def volume_ratio_series(volume: pd.Series, period: int = 20) -> pd.Series:
    """计算每根K线的成交量相对均量倍数"""
    avg = volume.rolling(window=period).mean()
    return volume / avg


# ═══════════════════════════════════════════════════════════════
# 单K线形态检测
# ═══════════════════════════════════════════════════════════════

def detect_candle_patterns(df: pd.DataFrame) -> pd.DataFrame:
    """
    检测9种单K线形态，返回每根K线的信号DataFrame。

    需要 df 包含列: open, high, low, close, volume

    返回列:
      - pattern: 形态名称 (None=无特殊形态)
      - pattern_strength: 形态强度 0-100
      - is_bullish: True=看涨, False=看跌, None=中性
      - body_type: 高实体阳线/高实体阴线/低实体阳线/低实体阴线/十字星
    """
    o, h, l, c = df["open"], df["high"], df["low"], df["close"]
    body = _body(o, c)
    tr = _total_range(h, l)
    br = _body_ratio(o, h, l, c)
    us = _upper_shadow(o, h, c)
    ls = _lower_shadow(o, l, c)
    is_up = c > o

    result = pd.DataFrame(index=df.index)
    result["pattern"] = None
    result["pattern_strength"] = 0
    result["is_bullish"] = None
    result["body_type"] = None

    # ── 先分类 body_type ──
    high_body = br > 0.7
    low_body = br < 0.3
    doji = br < 0.1

    result.loc[high_body & is_up, "body_type"] = "高实体阳线"
    result.loc[high_body & ~is_up, "body_type"] = "高实体阴线"
    result.loc[low_body & is_up, "body_type"] = "低实体阳线"
    result.loc[low_body & ~is_up, "body_type"] = "低实体阴线"
    result.loc[doji, "body_type"] = "十字星"
    # 中间部分
    mid = ~high_body & ~low_body & ~doji
    result.loc[mid & is_up, "body_type"] = "中实体阳线"
    result.loc[mid & ~is_up, "body_type"] = "中实体阴线"

    # ── 射击十字星 (Shooting Star) ──
    # 上影线 > 2×实体 AND 下影线 < 实体 AND 实体/振幅 < 0.3
    is_shooting = (us > 2 * body) & (ls < body) & (br < 0.3)
    result.loc[is_shooting, "pattern"] = "射击十字星"
    result.loc[is_shooting, "is_bullish"] = False
    result.loc[is_shooting, "pattern_strength"] = (
        (us / tr * 60 + (1 - br) * 40).clip(0, 100).astype(int)
    )

    # ── 锤头线 (Hammer) ──
    # 下影线 > 2×实体 AND 上影线 < 实体 AND 实体/振幅 < 0.3
    is_hammer = (ls > 2 * body) & (us < body) & (br < 0.3)
    result.loc[is_hammer, "pattern"] = "锤头线"
    result.loc[is_hammer, "is_bullish"] = True
    result.loc[is_hammer, "pattern_strength"] = (
        (ls / tr * 60 + (1 - br) * 40).clip(0, 100).astype(int)
    )

    # ── 长腿十字线 (Long-legged Doji) ──
    # 上下影线均 > 1.5×实体 AND 实体/振幅 < 0.1
    is_ll_doji = (us > 1.5 * body) & (ls > 1.5 * body) & (br < 0.1)
    result.loc[is_ll_doji, "pattern"] = "长腿十字线"
    result.loc[is_ll_doji, "is_bullish"] = None  # 中性
    result.loc[is_ll_doji, "pattern_strength"] = (
        ((us + ls) / tr * 70).clip(0, 100).astype(int)
    )

    return result


# ═══════════════════════════════════════════════════════════════
# 量价确认/异常检测 (威科夫投入产出定律)
# ═══════════════════════════════════════════════════════════════

def vpa_validate(df: pd.DataFrame) -> pd.DataFrame:
    """
    对每根K线执行量价确认/异常检测。
    需要 df 包含: open, high, low, close, volume

    返回: 每根K线的验证结果 DataFrame
      - validation: CONFIRMED_BULL | CONFIRMED_BEAR | CONFIRMED_IDLE |
                     ANOMALY_FAKE_MOVE | ANOMALY_STOPPING_VOLUME |
                     ANOMALY_EFFORT_NO_RESULT | NEUTRAL
      - anomaly: True/False
      - signal_priority: 1(延续) | 2(衰竭) | 3(反转) | 0(无关)
    """
    o, h, l, c, vol = df["open"], df["high"], df["low"], df["close"], df["volume"]
    body = _body(o, c)
    tr = _total_range(h, l)
    br = _body_ratio(o, h, l, c)
    vr = volume_ratio_series(vol, 20)
    is_up = c > o

    result = pd.DataFrame(index=df.index)
    result["validation"] = "NEUTRAL"
    result["anomaly"] = False
    result["signal_priority"] = 0

    # ── 确认：大实体 + 大成交量 → 真实运动 ──
    confirmed_strong = (br > 0.6) & (vr > 1.2)
    result.loc[confirmed_strong & is_up, "validation"] = "CONFIRMED_BULL"
    result.loc[confirmed_strong & ~is_up, "validation"] = "CONFIRMED_BEAR"

    # ── 确认：小实体 + 小成交量 → 正常盘整 ──
    confirmed_idle = (br < 0.3) & (vr < 0.7)
    result.loc[confirmed_idle, "validation"] = "CONFIRMED_IDLE"

    # ── 异常：大实体 + 小成交量 → 虚假运动（陷阱）──
    fake_move = (br > 0.6) & (vr < 0.7)
    result.loc[fake_move, "validation"] = "ANOMALY_FAKE_MOVE"
    result.loc[fake_move, "anomaly"] = True
    result.loc[fake_move, "signal_priority"] = 2

    # ── 异常：小实体 + 大成交量 → 努力无结果（止跌/止涨）──
    stopping = (br < 0.3) & (vr > 1.5)
    result.loc[stopping, "validation"] = "ANOMALY_STOPPING_VOLUME"
    result.loc[stopping, "anomaly"] = True
    result.loc[stopping, "signal_priority"] = 2

    # ── 中等异常：中小实体 + 较大成交量 → 努力大于结果 ──
    effort = (br < 0.5) & (br > 0.15) & (vr > 1.5)
    result.loc[effort, "validation"] = "ANOMALY_EFFORT_NO_RESULT"
    result.loc[effort, "anomaly"] = True
    result.loc[effort, "signal_priority"] = 2

    return result


# ═══════════════════════════════════════════════════════════════
# 多K线序列信号检测
# ═══════════════════════════════════════════════════════════════

def detect_sequence_signals(df: pd.DataFrame, candle_patterns: pd.DataFrame,
                            vpa_result: pd.DataFrame) -> List[dict]:
    """
    检测多K线序列信号。

    Returns:
        List of signal dicts: {date, signal, type, strength, action, description}
    """
    signals = []
    o, h, l, c, vol = df["open"], df["high"], df["low"], df["close"], df["volume"]
    avg_vol_20 = vol.rolling(20).mean()
    vr = vol / avg_vol_20.replace(0, np.nan)
    ma5 = _ma(c, 5)
    ma10 = _ma(c, 10)
    ma20 = _ma(c, 20)
    body = _body(o, c)
    tr_h = _total_range(h, l)
    us = _upper_shadow(o, h, c)
    ls = _lower_shadow(o, l, c)

    n = len(df)
    if n < 20:
        return signals

    for i in range(19, n):
        date = df.index[i]
        win_5 = slice(max(0, i - 4), i + 1)
        win_10 = slice(max(0, i - 9), i + 1)
        win_20 = slice(max(0, i - 19), i + 1)

        # ── 放量突破盘整 (趋势启动) ──
        # 突破20日盘整区上轨 + 成交量 > 1.5×均量
        if i >= 20 and vr.iloc[i] > 1.5:
            high_20 = h.iloc[win_20].max()
            low_20 = l.iloc[win_20].min()
            range_20 = high_20 - low_20
            if range_20 > 0 and c.iloc[i] > high_20 - range_20 * 0.1:
                # 之前是否在盘整（振幅<15%）
                pct_range = range_20 / low_20 * 100
                if pct_range < 20 and c.iloc[i] > ma5.iloc[i]:
                    signals.append({
                        "date": date.strftime("%Y-%m-%d"),
                        "signal": "放量突破盘整",
                        "type": "趋势启动",
                        "priority": 1,
                        "action": "加仓",
                        "description": f"突破20日盘整区(振幅{pct_range:.1f}%)+放量{vr.iloc[i]:.1f}x",
                    })

        # ── 放量加速 ──
        if i >= 5:
            bodies_5 = body.iloc[win_5]
            vols_5 = vr.iloc[win_5]
            # 连续3根阳线实体递增 + 量递增
            if i >= 3:
                recent_3_up = all(
                    c.iloc[i - j] > o.iloc[i - j] for j in range(3)
                )
                recent_3_body_up = all(
                    body.iloc[i - j] > body.iloc[i - j - 1] for j in range(2)
                )
                recent_3_vol_up = all(
                    vol.iloc[i - j] > vol.iloc[i - j - 1] for j in range(2)
                )
                if recent_3_up and recent_3_body_up and recent_3_vol_up:
                    signals.append({
                        "date": date.strftime("%Y-%m-%d"),
                        "signal": "放量加速",
                        "type": "趋势延续",
                        "priority": 1,
                        "action": "持仓/加仓",
                        "description": "连续3日放量长阳，趋势加速中",
                    })

        # ── 健康回调 ──
        # 处于上涨趋势中，回踩MA10/MA20，缩量
        if (i >= 10 and
            c.iloc[i] < ma5.iloc[i] and
            c.iloc[i] > ma20.iloc[i] and
            ma5.iloc[i] > ma20.iloc[i] and
            vr.iloc[i] < 0.7):
            signals.append({
                "date": date.strftime("%Y-%m-%d"),
                "signal": "健康回调(缩量)",
                "type": "趋势延续",
                "priority": 2,
                "action": "观察/准备加仓",
                "description": f"回踩均线+缩量至{vr.iloc[i]:.1f}x，健康回调",
            })

        # ── 回调后放量反弹 ──
        if i >= 3:
            prev_2_down = (c.iloc[i - 2] < c.iloc[i - 3] and c.iloc[i - 1] < c.iloc[i - 2])
            today_up_vol = (c.iloc[i] > o.iloc[i] and vr.iloc[i] > 1.2)
            if prev_2_down and today_up_vol:
                signals.append({
                    "date": date.strftime("%Y-%m-%d"),
                    "signal": "回调后放量反弹",
                    "type": "趋势延续",
                    "priority": 1,
                    "action": "加仓",
                    "description": "缩量回调后出现放量阳线，回调结束信号",
                })

        # ── 放量止涨 (Stopping Volume Up) ──
        if i >= 3:
            prev_up = all(c.iloc[i - j] > o.iloc[i - j] for j in range(1, 4))
            prev_vol_shrink = all(vr.iloc[i - j] < 1.0 for j in range(1, 4))
            today_long_us = us.iloc[i] > body.iloc[i] * 2
            today_high_vol = vr.iloc[i] > 1.5
            if prev_up and prev_vol_shrink and today_long_us and today_high_vol:
                signals.append({
                    "date": date.strftime("%Y-%m-%d"),
                    "signal": "放量止涨",
                    "type": "趋势衰竭",
                    "priority": 1,
                    "action": "减仓",
                    "description": "连续阳线缩量后长上影线+放量——局内人出货信号",
                })

        # ── 量价背离_上涨 ──
        if i >= 5:
            price_new_high = c.iloc[i] > c.iloc[win_5].max() * 0.99
            vol_declining = all(
                avg_vol_20.iloc[i - j] < avg_vol_20.iloc[i - j - 1]
                for j in range(3)
            )
            if price_new_high and vol_declining and ma20.iloc[i] > ma20.iloc[i - 10]:
                signals.append({
                    "date": date.strftime("%Y-%m-%d"),
                    "signal": "量价背离(上涨)",
                    "type": "趋势衰竭",
                    "priority": 1,
                    "action": "减仓",
                    "description": "价格创新高但成交量递减——上涨动能衰竭",
                })

        # ── 连续射击十字星 ──
        if i >= 5:
            shooting_count = sum(
                1 for j in range(i - 4, i + 1)
                if candle_patterns.iloc[j].get("pattern") == "射击十字星"
            )
            if shooting_count >= 2:
                signals.append({
                    "date": date.strftime("%Y-%m-%d"),
                    "signal": f"连续射击十字星({shooting_count}次)",
                    "type": "趋势衰竭",
                    "priority": 1,
                    "action": "离场",
                    "description": f"近5日出现{shooting_count}次射击十字星，顶部确认",
                })

        # ── 放量止跌 (Stopping Volume Down) ──
        if i >= 3:
            prev_down = all(c.iloc[i - j] < o.iloc[i - j] for j in range(1, 4))
            prev_vol_shrink = all(vol.iloc[i - j] < avg_vol_20.iloc[i - j] for j in range(1, 4))
            today_long_ls = ls.iloc[i] > body.iloc[i] * 2
            today_high_vol = vr.iloc[i] > 1.5
            if prev_down and prev_vol_shrink and today_long_ls and today_high_vol:
                signals.append({
                    "date": date.strftime("%Y-%m-%d"),
                    "signal": "放量止跌",
                    "type": "趋势反转",
                    "priority": 2,
                    "action": "关注",
                    "description": "连续阴线缩量后长下影线+放量——局内人入场信号",
                })

        # ── 量价背离_下跌 ──
        if i >= 5:
            price_new_low = c.iloc[i] < l.iloc[win_5].min() * 1.01
            vol_declining = all(avg_vol_20.iloc[i - j] < avg_vol_20.iloc[i - j - 1] for j in range(3))
            if price_new_low and vol_declining and ma20.iloc[i] < ma20.iloc[i - 10]:
                signals.append({
                    "date": date.strftime("%Y-%m-%d"),
                    "signal": "量价背离(下跌)",
                    "type": "趋势反转",
                    "priority": 2,
                    "action": "关注",
                    "description": "价格创新低但成交量递减——下跌动能衰竭",
                })

        # ── 高位支点失败 ──
        if i >= 10:
            # 检测最近两个高位支点是否降低
            peaks_10 = []
            for j in range(i - 9, i):
                if (j > i - 10 and j < i - 1 and
                    h.iloc[j] > h.iloc[j - 1] and h.iloc[j] > h.iloc[j + 1]):
                    peaks_10.append((j, h.iloc[j]))
            if len(peaks_10) >= 2 and peaks_10[-1][1] < peaks_10[-2][1]:
                signals.append({
                    "date": date.strftime("%Y-%m-%d"),
                    "signal": "高位支点失败",
                    "type": "趋势破坏",
                    "priority": 1,
                    "action": "减仓",
                    "description": "最新高位支点低于前一高位支点——趋势结构破坏",
                })

        # ── 供给测试 (Supply Test) ──
        # 脱离盘整区后回踩原区间+缩量
        if i >= 30:
            consolidation_high = h.iloc[win_20].quantile(0.9)
            consolidation_low = l.iloc[win_20].quantile(0.1)
            above_consolidation = c.iloc[i - 1] > consolidation_high
            test_pullback = c.iloc[i] < consolidation_high * 1.02
            test_low_vol = vr.iloc[i] < 0.6
            if above_consolidation and test_pullback and test_low_vol:
                signals.append({
                    "date": date.strftime("%Y-%m-%d"),
                    "signal": "供给测试(缩量回踩)",
                    "type": "趋势确认",
                    "priority": 1,
                    "action": "持仓/加仓",
                    "description": "脱离盘整区后缩量回踩——供给测试通过",
                })

        # ── 买入高峰 (Buying Climax) ──
        # 下跌趋势末，长下影线+极高成交量
        if i >= 20 and c.iloc[i] < ma20.iloc[i] * 0.95:
            if ls.iloc[i] > body.iloc[i] * 3 and vr.iloc[i] > 2.0:
                signals.append({
                    "date": date.strftime("%Y-%m-%d"),
                    "signal": "买入高峰",
                    "type": "趋势反转",
                    "priority": 2,
                    "action": "关注",
                    "description": f"超长下影线+极量{vr.iloc[i]:.1f}x——吸筹尾声信号",
                })

        # ── 抛售高峰 (Selling Climax) ──
        # 上涨趋势末，长上影线+极高成交量
        if i >= 20 and c.iloc[i] > ma20.iloc[i] * 1.05:
            if us.iloc[i] > body.iloc[i] * 3 and vr.iloc[i] > 2.0:
                signals.append({
                    "date": date.strftime("%Y-%m-%d"),
                    "signal": "抛售高峰",
                    "type": "趋势反转",
                    "priority": 2,
                    "action": "减仓",
                    "description": f"超长上影线+极量{vr.iloc[i]:.1f}x——派筹尾声信号",
                })

    return signals


# ═══════════════════════════════════════════════════════════════
# 综合信号分析
# ═══════════════════════════════════════════════════════════════

def analyze_signals(df: pd.DataFrame) -> dict:
    """
    对OHLCV数据执行完整的信号检测。

    Returns:
        {
            "candle_patterns": DataFrame,       # 每根K线形态
            "vpa_validation": DataFrame,         # 每根K线量价验证
            "sequence_signals": List[dict],      # 多K线序列信号
            "latest_bar": dict,                  # 最新一根K线分析
            "recent_signals": List[dict],        # 近期信号(去重排序)
            "signal_summary": str,               # 信号总结
        }
    """
    if df is None or len(df) < 20:
        return {"error": "数据不足（至少需要20根K线）", "sequence_signals": []}

    # 单K线形态
    candle_patterns = detect_candle_patterns(df)

    # 量价验证
    vpa_result = vpa_validate(df)

    # 多K线序列
    sequence_signals = detect_sequence_signals(df, candle_patterns, vpa_result)

    # 最新一根K线
    latest = df.iloc[-1]
    avg_vol_20 = df["volume"].rolling(20).mean().iloc[-1]
    vol_level, vol_score = classify_volume(latest["volume"], avg_vol_20)

    latest_pattern = candle_patterns.iloc[-1]
    latest_vpa = vpa_result.iloc[-1]

    latest_bar = {
        "date": df.index[-1].strftime("%Y-%m-%d"),
        "open": round(float(latest["open"]), 2),
        "high": round(float(latest["high"]), 2),
        "low": round(float(latest["low"]), 2),
        "close": round(float(latest["close"]), 2),
        "volume": int(latest["volume"]),
        "body_type": latest_pattern.get("body_type", "未知"),
        "volume_level": f"{vol_level}({vol_score})",
        "vpa_validation": latest_vpa.get("validation", "NEUTRAL"),
        "candle_pattern": latest_pattern.get("pattern"),
        "is_anomaly": bool(latest_vpa.get("anomaly", False)),
    }

    # 去重排序（按 priority 升序，同日期同信号去重）
    seen = set()
    recent = []
    for s in sorted(sequence_signals, key=lambda x: (x["priority"], x["date"]), reverse=False):
        key = (s["date"], s["signal"])
        if key not in seen:
            seen.add(key)
            recent.append(s)

    # 信号总结
    continuation = [s for s in recent if s["type"].startswith("趋势延续") or s["type"].startswith("趋势启动")]
    exhaustion = [s for s in recent if s["type"].startswith("趋势衰竭")]
    reversal = [s for s in recent if s["type"].startswith("趋势反转") or s["type"].startswith("趋势破坏")]

    summary_parts = []
    if continuation:
        summary_parts.append(f"趋势延续信号{len(continuation)}个")
    if exhaustion:
        summary_parts.append(f"趋势衰竭信号{len(exhaustion)}个")
    if reversal:
        summary_parts.append(f"趋势反转信号{len(reversal)}个")
    if not summary_parts:
        summary_parts.append("无明确趋势信号")

    return {
        "candle_patterns": candle_patterns,
        "vpa_validation": vpa_result,
        "sequence_signals": sequence_signals,
        "latest_bar": latest_bar,
        "recent_signals": recent[-10:],  # 最近10个
        "signal_summary": "；".join(summary_parts),
    }
