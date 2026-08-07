"""
VPA 趋势分析层 — 趋势交易核心引擎
===================================
基于 Anna Coulling 动态趋势线方法和 Charles Dow 三阶段理论。

核心能力：
  1. 短期趋势判断 (5-20日，主交易周期)
  2. 中期趋势判断 (20-60日，方向约束)
  3. 趋势强度评分 (0-100)
  4. 动态趋势线 (实时支点跟踪)
  5. 吸筹/派筹阶段识别
  6. 支撑阻力位计算
"""

import logging
from typing import Dict, List, Optional, Tuple
import numpy as np
import pandas as pd

logger = logging.getLogger("vpa.trend")


# ═══════════════════════════════════════════════════════════════
# 基础计算
# ═══════════════════════════════════════════════════════════════

def _ma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(window=period).mean()


def _body(open_: pd.Series, close: pd.Series) -> pd.Series:
    return (close - open_).abs()


def _total_range(high: pd.Series, low: pd.Series) -> pd.Series:
    return (high - low).replace(0, np.nan)


# ═══════════════════════════════════════════════════════════════
# 支点检测 (Pivot Detection)
# ═══════════════════════════════════════════════════════════════

def find_pivots(high: pd.Series, low: pd.Series, window: int = 3) -> dict:
    """
    寻找高位支点(swing highs)和低位支点(swing lows)。
    支点是 Anna Coulling 动态趋势线方法的基石。

    Args:
        high: 最高价序列
        low: 最低价序列
        window: 两侧窗口大小（默认3，即±3根K线确认一个支点）

    Returns:
        {"highs": [(index, price), ...], "lows": [(index, price), ...]}
    """
    n = len(high)
    high_pivots = []
    low_pivots = []

    for i in range(window, n - window):
        # 高位支点：当前最高价 > 两侧的最高价
        h_seg = high.iloc[i - window:i + window + 1]
        if high.iloc[i] == h_seg.max() and list(h_seg).count(h_seg.max()) == 1:
            high_pivots.append((high.index[i], float(high.iloc[i])))

        # 低位支点：当前最低价 < 两侧的最低价
        l_seg = low.iloc[i - window:i + window + 1]
        if low.iloc[i] == l_seg.min() and list(l_seg).count(l_seg.min()) == 1:
            low_pivots.append((low.index[i], float(low.iloc[i])))

    return {"highs": high_pivots, "lows": low_pivots}


# ═══════════════════════════════════════════════════════════════
# 短期趋势判断 (5-20日)
# ═══════════════════════════════════════════════════════════════

def analyze_short_term_trend(df: pd.DataFrame, window: int = 3) -> dict:
    """
    短期趋势（5-20个交易日）判定——主要交易依据。

    三维判定：
      1. 均线排列 (MA5/MA10/MA20)
      2. 价格结构 (高位/低位支点)
      3. 成交量验证

    Returns:
        {
            "direction": 上涨 | 下跌 | 盘整,
            "phase": 趋势加速 | 趋势匀速 | 趋势减速 | ...,
            "strength": 0-100,
            "ma_alignment": 多头排列 | 空头排列 | 交叉混乱,
            "channel": {...},
            "volume_confirmation": str,
            "days_in_trend": int,
            "summary": str,
        }
    """
    if df is None or len(df) < 20:
        return {"direction": "数据不足", "strength": 0}

    close = df["close"]
    high = df["high"]
    low = df["low"]
    vol = df["volume"]
    o = df["open"]

    ma5 = _ma(close, 5)
    ma10 = _ma(close, 10)
    ma20 = _ma(close, 20)
    avg_vol_20 = _ma(vol, 20)
    vr = vol / avg_vol_20.replace(0, np.nan)

    latest = len(df) - 1
    ma5_v = ma5.iloc[latest]
    ma10_v = ma10.iloc[latest]
    ma20_v = ma20.iloc[latest]
    price = close.iloc[latest]

    # ── 均线排列 ──
    if ma5_v > ma10_v > ma20_v:
        ma_alignment = "多头排列"
        # 间距趋势
        spread_5_10 = (ma5_v - ma10_v) / ma10_v * 100
        spread_5_20 = (ma5_v - ma20_v) / ma20_v * 100
        if spread_5_10 > 1.5 and spread_5_20 > 3:
            ma_detail = "完美多头排列，间距递增"
            ma_score = 30
        elif spread_5_10 > 0.5:
            ma_detail = "多头排列"
            ma_score = 25
        else:
            ma_detail = "多头排列但间距递减"
            ma_score = 20
    elif ma5_v < ma10_v < ma20_v:
        ma_alignment = "空头排列"
        ma_detail = "空头排列"
        ma_score = 0
    else:
        # 检查是否接近多头/空头
        if abs(ma5_v - ma10_v) / ma10_v * 100 < 0.5 if ma10_v != 0 else True:
            ma_alignment = "均线缠绕(偏多)" if ma5_v > ma20_v else "均线缠绕(偏空)"
            ma_detail = ma_alignment
            ma_score = 10
        else:
            ma_alignment = "交叉混乱"
            ma_detail = "交叉混乱"
            ma_score = 5

    # ── 价格结构 (支点分析) ──
    pivots = find_pivots(high, low, window=window)
    high_pivots = pivots["highs"]
    low_pivots = pivots["lows"]

    # 最近的高位支点序列
    recent_highs = [p for p in high_pivots if p[0] >= df.index[max(0, latest - 40)]]
    recent_lows = [p for p in low_pivots if p[0] >= df.index[max(0, latest - 40)]]

    # 高位支点是否抬高
    pivot_score = 0
    if len(recent_highs) >= 2:
        highs_rising = all(
            recent_highs[i][1] > recent_highs[i - 1][1]
            for i in range(1, len(recent_highs))
        )
        if highs_rising:
            if len(recent_highs) >= 3:
                pivot_score = 30
                pivot_detail = f"高位支点连续{len(recent_highs)}次抬高"
            else:
                pivot_score = 20
                pivot_detail = "高位支点抬高2次"
        else:
            pivot_score = 5
            pivot_detail = "高位支点不再抬高"
    elif len(recent_highs) >= 1:
        pivot_score = 10
        pivot_detail = "高位支点出现1次"
    else:
        pivot_score = 0
        pivot_detail = "无明显支点结构"

    # 低位支点是否抬高
    if len(recent_lows) >= 2:
        lows_rising = all(
            recent_lows[i][1] > recent_lows[i - 1][1]
            for i in range(1, len(recent_lows))
        )
        if lows_rising:
            pivot_score = max(pivot_score, 30)
            pivot_detail += "，低位支点连续抬高"

    # ── 量价配合 ──
    up_days_vol_ok = 0
    down_days_vol_ok = 0
    total_up = 0
    total_down = 0

    for i in range(max(0, latest - 4), latest + 1):
        if close.iloc[i] > o.iloc[i]:
            total_up += 1
            if vr.iloc[i] > 1.0:
                up_days_vol_ok += 1
        elif close.iloc[i] < o.iloc[i]:
            total_down += 1
            if vr.iloc[i] < 0.8:
                down_days_vol_ok += 1

    if total_up > 0 and up_days_vol_ok == total_up and total_down > 0 and down_days_vol_ok == total_down:
        vol_score = 40
        vol_detail = "全部上涨日放量+回调日缩量——完美配合"
    elif total_up > 0 and up_days_vol_ok / total_up >= 0.7:
        vol_score = 30
        vol_detail = "多数上涨日放量"
    elif total_up > 0 and up_days_vol_ok / total_up < 0.5:
        vol_score = 10
        vol_detail = "上涨缩量——量价背离"
    else:
        vol_score = 20
        vol_detail = "量价关系中性"

    # ── 综合评分和方向 ──
    strength = ma_score + pivot_score + vol_score

    if ma_alignment in ("多头排列", "均线缠绕(偏多)") and price > ma20_v:
        direction = "上涨"
    elif ma_alignment in ("空头排列", "均线缠绕(偏空)") and price < ma20_v:
        direction = "下跌"
    else:
        direction = "盘整"

    # ── 趋势阶段 ──
    if direction == "上涨" and strength >= 70:
        # 检查是否加速
        ma5_slope = (ma5.iloc[latest] - ma5.iloc[max(0, latest - 5)]) / ma5.iloc[max(0, latest - 5)] * 100
        if ma5_slope > 3:
            phase = "趋势加速"
        elif ma5_slope > 1:
            phase = "趋势匀速"
        elif ma5_slope > 0:
            phase = "趋势减速"
        elif ma5_v < ma10_v:
            phase = "趋势衰竭"
        else:
            phase = "趋势匀速"
    elif direction == "上涨" and strength >= 40:
        phase = "趋势启动"
    elif direction == "盘整":
        phase = "盘整"
    elif direction == "下跌":
        phase = "下跌趋势"
    else:
        phase = "无明确趋势"

    # ── 动态趋势通道 ──
    channel = _build_dynamic_channel(df, recent_highs, recent_lows, direction)

    # ── 在趋势中的天数 ──
    days_in_trend = 0
    if direction == "上涨":
        for i in range(latest, 0, -1):
            if close.iloc[i] > ma20.iloc[i]:
                days_in_trend += 1
            else:
                break

    return {
        "direction": direction,
        "phase": phase,
        "strength": min(strength, 100),
        "ma_alignment": ma_alignment,
        "ma_detail": ma_detail,
        "pivot_detail": pivot_detail,
        "vol_detail": vol_detail,
        "volume_confirmation": vol_detail,
        "channel": channel,
        "days_in_trend": days_in_trend,
        "price_vs_ma20_pct": round((price - ma20_v) / ma20_v * 100, 1),
        "summary": (
            f"短期{direction}趋势，{phase}阶段。"
            f"均线{ma_alignment}，{pivot_detail}。"
            f"量价配合：{vol_detail}。"
            f"趋势强度{min(strength,100)}/100。"
        ),
    }


def _build_dynamic_channel(df, high_pivots, low_pivots, direction) -> dict:
    """构建动态趋势通道"""
    if len(high_pivots) < 2 or len(low_pivots) < 2:
        return {"status": "支点不足", "upper": None, "lower": None, "stop_loss": None}

    # 最近的高位支点作为通道上轨
    upper = high_pivots[-1][1]
    # 最近的低位支点作为通道下轨
    lower = low_pivots[-1][1]

    # 检查支点序列
    if len(high_pivots) >= 3:
        if high_pivots[-1][1] < high_pivots[-2][1]:
            status = "趋势破坏"
        else:
            status = "趋势完好"
    else:
        status = "趋势发展中"

    stop_loss = lower * 0.98  # 通道下轨下方2%作为止损

    return {
        "upper": round(upper, 2),
        "lower": round(lower, 2),
        "stop_loss": round(stop_loss, 2),
        "status": status,
    }


# ═══════════════════════════════════════════════════════════════
# 中期趋势判断 (20-60日)
# ═══════════════════════════════════════════════════════════════

def analyze_medium_term_trend(df: pd.DataFrame) -> dict:
    """
    中期趋势（20-60个交易日）——提供方向性约束。

    短期交易方向应与中期趋势一致（顺大势、逆小势）。
    """
    if df is None or len(df) < 60:
        # 不足60根K线，用20根作为简化版
        if df is not None and len(df) >= 20:
            return _analyze_medium_short(df)
        return {"direction": "数据不足", "strength": 0}

    close = df["close"]
    high = df["high"]
    low = df["low"]
    vol = df["volume"]

    ma20 = _ma(close, 20)
    ma60 = _ma(close, 60)
    ma120 = _ma(close, 120) if len(df) >= 120 else ma60  # fallback

    latest = len(df) - 1
    ma20_v = ma20.iloc[latest]
    ma60_v = ma60.iloc[latest]
    ma120_v = ma120.iloc[latest]
    price = close.iloc[latest]

    # MA60 斜率（线性回归）
    if len(df) >= 80:
        ma60_recent = ma60.iloc[-20:].dropna()
        if len(ma60_recent) > 10:
            x = np.arange(len(ma60_recent), dtype=float)
            slope = np.polyfit(x, ma60_recent.values, 1)[0]
            weekly_slope_pct = slope * 5 / ma60_recent.values[-1] * 100
        else:
            weekly_slope_pct = 0
    else:
        weekly_slope_pct = 0

    # 方向判断
    if ma20_v > ma60_v > ma120_v and weekly_slope_pct > 0.1:
        direction = "上涨"
        alignment = "MA20>MA60>MA120 多头排列"
        constraint = "做多为主"
    elif ma20_v > ma60_v and weekly_slope_pct < 0.1:
        direction = "上涨(转弱)"
        alignment = "MA20>MA60但斜率趋零"
        constraint = "谨慎做多"
    elif ma20_v < ma60_v < ma120_v and weekly_slope_pct < -0.1:
        direction = "下跌"
        alignment = "MA20<MA60<MA120 空头排列"
        constraint = "做空/持币为主"
    elif ma20_v < ma60_v and weekly_slope_pct > -0.1:
        direction = "下跌(转强)"
        alignment = "MA20<MA60但斜率趋零转正"
        constraint = "关注筑底"
    else:
        direction = "盘整"
        alignment = "MA20与MA60反复交叉"
        constraint = "降低仓位等突破"

    # 强度评分
    strength = 0
    if direction in ("上涨", "上涨(转弱)"):
        strength = 50 + min(weekly_slope_pct * 15, 30)
    elif direction in ("下跌", "下跌(转强)"):
        strength = max(0, 30 + weekly_slope_pct * 10)
    else:
        strength = 30

    return {
        "direction": direction,
        "strength": round(min(max(strength, 0), 100)),
        "ma60_slope_pct_per_week": round(weekly_slope_pct, 2),
        "ma_alignment": alignment,
        "constraint": constraint,
        "phase": direction,
    }


def _analyze_medium_short(df: pd.DataFrame) -> dict:
    """简化版中期分析（K线不足60根时使用）"""
    close = df["close"]
    ma20 = _ma(close, 20)
    latest = len(df) - 1
    price = close.iloc[latest]
    ma20_v = ma20.iloc[latest]

    if price > ma20_v:
        return {"direction": "上涨", "strength": 55, "ma_alignment": "价格>MA20", "constraint": "做多为主"}
    else:
        return {"direction": "下跌", "strength": 30, "ma_alignment": "价格<MA20", "constraint": "做空/持币为主"}


# ═══════════════════════════════════════════════════════════════
# 趋势共振判断
# ═══════════════════════════════════════════════════════════════

def assess_trend_alignment(short_term: dict, medium_term: dict) -> dict:
    """
    判断短期和中期趋势的共振/背离关系。
    """
    st_dir = short_term.get("direction", "")
    mt_dir = medium_term.get("direction", "")

    st_bull = st_dir.startswith("上涨")
    st_bear = st_dir.startswith("下跌")
    mt_bull = mt_dir.startswith("上涨")
    mt_bear = mt_dir.startswith("下跌")

    if st_bull and mt_bull:
        alignment = "短中期共振看多"
        signal = "[最佳做多窗口]"
    elif st_bull and mt_bear:
        alignment = "短多中空(背离)"
        signal = "[短期反弹，中期仍看空——谨慎参与]"
    elif st_bear and mt_bull:
        alignment = "短空中多(回调)"
        signal = "[短期回调，中期趋势向好——关注回调结束信号]"
    elif st_bear and mt_bear:
        alignment = "短中期共振看空"
        signal = "[持币观望最佳策略]"
    else:
        alignment = "方向不明确"
        signal = "[观望]"

    return {
        "alignment": alignment,
        "signal": signal,
        "short_term_direction": st_dir,
        "medium_term_direction": mt_dir,
    }


# ═══════════════════════════════════════════════════════════════
# 吸筹/派筹阶段识别
# ═══════════════════════════════════════════════════════════════

def detect_accumulation_distribution(df: pd.DataFrame) -> dict:
    """
    基于价格震荡区间+成交量特征，识别吸筹/派筹阶段。

    对趋势交易者而言：
      - 识别吸筹 → 提前关注，等放量突破后进场
      - 识别派筹 → 提前减仓，不等顶部确认
    """
    if df is None or len(df) < 30:
        return {"phase": "数据不足", "confidence": 0, "signals": []}

    close = df["close"]
    high = df["high"]
    low = df["low"]
    vol = df["volume"]
    o = df["open"]
    ma20 = _ma(close, 20)
    ma5 = _ma(close, 5)

    latest = len(df) - 1
    price = close.iloc[latest]

    # 近20日价格区间
    win_20 = slice(max(0, latest - 19), latest + 1)
    high_20 = high.iloc[win_20].max()
    low_20 = low.iloc[win_20].min()
    price_range_pct = (high_20 - low_20) / low_20 * 100

    # 价格位置
    position = (price - low_20) / (high_20 - low_20) if high_20 > low_20 else 0.5
    # 相对60日高低点的位置
    high_60 = high.iloc[-60:].max()
    low_60 = low.iloc[-60:].min()
    position_60 = (price - low_60) / (high_60 - low_60) if high_60 > low_60 else 0.5

    # 成交量模式
    avg_vol_20 = vol.iloc[win_20].mean()
    vr = vol.iloc[win_20] / avg_vol_20

    signals = []
    phase = "趋势运行中"
    confidence = 0

    # 吸筹特征
    acc_score = 0
    if price_range_pct < 15:
        signals.append("窄幅震荡")
        acc_score += 20
    if position_60 < 0.4:
        signals.append("位于60日低位区域")
        acc_score += 25
    # 检查锤头线是否频繁出现
    hammer_count = 0
    for i in range(max(0, latest - 19), latest + 1):
        body = abs(close.iloc[i] - o.iloc[i])
        lower_shadow = min(o.iloc[i], close.iloc[i]) - low.iloc[i]
        total_range_v = high.iloc[i] - low.iloc[i]
        if total_range_v > 0 and lower_shadow > 2 * body and body / total_range_v < 0.3:
            hammer_count += 1
    if hammer_count >= 2:
        signals.append(f"锤头线出现{hammer_count}次")
        acc_score += 25

    # 派筹特征
    dist_score = 0
    if price_range_pct < 15:
        dist_score += 20
    if position_60 > 0.6:
        signals.append("位于60日高位区域")
        dist_score += 25
    # 检查射击十字星是否频繁
    star_count = 0
    for i in range(max(0, latest - 19), latest + 1):
        body = abs(close.iloc[i] - o.iloc[i])
        upper_shadow = high.iloc[i] - max(o.iloc[i], close.iloc[i])
        total_range_v = high.iloc[i] - low.iloc[i]
        if total_range_v > 0 and upper_shadow > 2 * body and body / total_range_v < 0.3:
            star_count += 1
    if star_count >= 2:
        signals.append(f"射击十字星出现{star_count}次")
        dist_score += 25

    # 综合判断
    if acc_score >= 50 and acc_score > dist_score:
        phase = "疑似吸筹"
        confidence = min(acc_score, 95)
    elif dist_score >= 50 and dist_score > acc_score:
        phase = "疑似派筹"
        confidence = min(dist_score, 95)
    elif price_range_pct < 10:
        phase = "窄幅盘整"
        confidence = 30
    else:
        phase = "趋势运行中"
        confidence = 40

    return {
        "phase": phase,
        "confidence": confidence,
        "signals": signals,
        "price_range_pct": round(price_range_pct, 1),
        "position_60d_pct": round(position_60 * 100, 1),
    }


# ═══════════════════════════════════════════════════════════════
# 支撑阻力位
# ═══════════════════════════════════════════════════════════════

def compute_sr_levels(df: pd.DataFrame, num_levels: int = 3) -> dict:
    """通过峰值聚类计算支撑位和阻力位"""
    if df is None or len(df) < 20:
        return {"short_term": {"support": [], "resistance": []}}

    high = df["high"]
    low = df["low"]
    close = df["close"]

    def _cluster(prices, n):
        if not prices:
            return []
        sp = sorted(set(prices))
        if len(sp) <= n:
            return sp[-n:]
        clusters = [[sp[0]]]
        rng = sp[-1] - sp[0]
        thr = rng * 0.03 if rng > 0 else 0.01
        for p in sp[1:]:
            if abs(p - np.mean(clusters[-1])) <= thr:
                clusters[-1].append(p)
            else:
                clusters.append([p])
        centers = [(len(c), float(np.mean(c))) for c in clusters]
        centers.sort(key=lambda x: x[1], reverse=True)  # 按价格排序
        # 取最重要的n个
        return [c for _, c in sorted(centers, key=lambda x: x[0], reverse=True)[:n]]

    # 短期 (20日)
    st_win = slice(-20, None)
    st_pivots = find_pivots(high.iloc[st_win], low.iloc[st_win])
    st_highs = [p[1] for p in st_pivots["highs"]]
    st_lows = [p[1] for p in st_pivots["lows"]]

    # 中期 (60日)
    mt_pivots = find_pivots(high.iloc[-60:], low.iloc[-60:]) if len(df) >= 60 else st_pivots
    mt_highs = [p[1] for p in mt_pivots["highs"]]
    mt_lows = [p[1] for p in mt_pivots["lows"]]

    st_support = _cluster(st_lows, num_levels)
    st_resistance = _cluster(st_highs, num_levels)
    mt_support = _cluster(mt_lows, num_levels)
    mt_resistance = _cluster(mt_highs, num_levels)

    current_price = close.iloc[-1]
    nearest_support = max([s for s in st_support if s < current_price], default=None)
    nearest_resistance = min([r for r in st_resistance if r > current_price], default=None)

    return {
        "short_term": {
            "support": sorted(st_support, reverse=True),
            "resistance": sorted(st_resistance),
        },
        "medium_term": {
            "support": sorted(mt_support, reverse=True),
            "resistance": sorted(mt_resistance),
        },
        "nearest_support": nearest_support,
        "nearest_resistance": nearest_resistance,
        "current_price": round(float(current_price), 2),
    }


# ═══════════════════════════════════════════════════════════════
# 综合趋势分析
# ═══════════════════════════════════════════════════════════════

def analyze_trend(df: pd.DataFrame) -> dict:
    """
    综合趋势分析——输出完整的趋势评估报告。

    Returns:
        包含短期/中期趋势、共振判断、阶段识别、支撑阻力、动态通道的完整dict。
    """
    if df is None or len(df) < 20:
        return {"error": "数据不足（至少需要20根K线）"}

    short_term = analyze_short_term_trend(df)
    medium_term = analyze_medium_term_trend(df)
    alignment = assess_trend_alignment(short_term, medium_term)
    phase = detect_accumulation_distribution(df)
    sr_levels = compute_sr_levels(df)

    return {
        "short_term": short_term,
        "medium_term": medium_term,
        "alignment": alignment,
        "phase": phase,
        "sr_levels": sr_levels,
    }
