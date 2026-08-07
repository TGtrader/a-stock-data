"""
大盘状态判定 — 牛/熊/震荡识别
===============================
对主要指数进行多维度分析，判断市场处于什么状态。

判定维度（共5维，满分125→归一化100）：
  1. 均线排列（多头/空头/缠绕）       25分
  2. 价格动量（涨跌幅+斜率）           25分
  3. 波动率环境（低波/高波）           25分
  4. 成交量趋势（放量/缩量）           25分
  5. 极端事件/反转信号                 25分  ← 单日暴涨暴跌/V型反转

状态转换信号：震荡→牛市确认、牛市→震荡衰竭、震荡→熊市确认
"""

import logging
from typing import Dict, List, Optional
from datetime import datetime
import pandas as pd
import numpy as np

from ..data.cache import DataCache

logger = logging.getLogger("tg.market.regime")


# 六大指数
MAJOR_INDICES = {
    "000001": "上证指数",
    "399001": "深证成指",
    "000300": "沪深300",
    "399006": "创业板指",
    "000688": "科创50",
    "000905": "中证500",
}


def _ma(s: pd.Series, p: int) -> pd.Series:
    return s.rolling(p).mean()


def detect_regime(df: pd.DataFrame) -> dict:
    """
    单指数大盘状态判定。

    Args:
        df: OHLCV DataFrame (index=date)

    Returns:
        {
            "regime": str,            # 牛市/震荡偏多/震荡市/震荡偏空/熊市
            "score": int,             # 0-100
            "dimensions": {...},      # 各维度得分
            "transition_signal": str, # 状态转换信号
            "confidence": str,        # 置信度
            "advice": str,            # 操作建议
        }
    """
    if df is None or len(df) < 60:
        return _empty_regime("数据不足（至少需要60根K线）")

    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]
    n = len(df)

    # ── 维度1: 均线排列 (0-25分) ──
    ma5, ma10, ma20, ma60 = _ma(close, 5), _ma(close, 10), _ma(close, 20), _ma(close, 60)
    ma_score = _score_ma_alignment(ma5, ma10, ma20, ma60, n)

    # ── 维度2: 价格动量 (0-25分) ──
    momentum_score = _score_momentum(close, n)

    # ── 维度3: 波动率环境 (0-25分) ──
    vol_score = _score_volatility(close, n)

    # ── 维度4: 成交量趋势 (0-25分) ──
    volume_score = _score_volume(volume, close, n)

    # ── 维度5: 极端事件/反转信号 (0-25分) ──  ★ NEW
    extreme_score, extreme_signals = _score_extreme_events(df, n)

    total_raw = ma_score + momentum_score + vol_score + volume_score + extreme_score
    total = int(total_raw * 100 / 125)  # 归一化到100

    # ── 判定状态 ──
    if total >= 80:
        regime = "牛市"
        advice = "积极做多，仓位可至70-80%"
    elif total >= 60:
        regime = "震荡偏多"
        advice = "可以参与，仓位40-60%"
    elif total >= 40:
        regime = "震荡市"
        advice = "降低仓位至30-50%，精选个股"
    elif total >= 20:
        regime = "震荡偏空"
        advice = "防御为主，仓位20-30%"
    else:
        regime = "熊市"
        advice = "持币观望，仓位≤20%"

    # ── 状态转换信号 ──
    transition = _detect_transition(df, total, regime, n)

    # ── 置信度 ──
    confidence = "高" if abs(total - 50) > 25 else ("中" if abs(total - 50) > 12 else "低")

    return {
        "regime": regime,
        "score": total,
        "dimensions": {
            "ma_alignment": ma_score,
            "momentum": momentum_score,
            "volatility": vol_score,
            "volume": volume_score,
            "extreme_events": extreme_score,
        },
        "extreme_signals": extreme_signals,
        "transition_signal": transition,
        "confidence": confidence,
        "advice": advice,
        "details": {
            "ma5_vs_ma20": "多头" if ma5.iloc[-1] > ma20.iloc[-1] else "空头",
            "price_vs_ma60_pct": round((close.iloc[-1] - ma60.iloc[-1]) / ma60.iloc[-1] * 100, 1),
            "volatility_20d": round(close.pct_change().tail(20).std() * np.sqrt(252) * 100, 1),
            "volume_vs_20ma": round(volume.iloc[-5:].mean() / volume.tail(20).mean(), 2),
        },
    }


def multi_index_regime(cache: DataCache = None) -> dict:
    """
    六大指数综合状态判定。

    Returns:
        {index_code: {regime, score, ...}, "composite": {...}}
    """
    if cache is None:
        cache = DataCache()

    results = {}
    scores = []

    for code, name in MAJOR_INDICES.items():
        df = cache.get_kline(code, lookback=200)
        if df is not None and len(df) >= 60:
            regime = detect_regime(df)
            regime["name"] = name
            results[code] = regime
            scores.append(regime["score"])
        else:
            results[code] = _empty_regime(f"数据不足 ({name})")
            results[code]["name"] = name

    # 综合评分
    if scores:
        avg_score = sum(scores) / len(scores)
        # 沪深300和创业板权重更高
        weighted = scores.copy()
        if "000300" in results and "error" not in results["000300"]:
            weighted.append(results["000300"]["score"])
        if "399006" in results and "error" not in results["399006"]:
            weighted.append(results["399006"]["score"])
        composite_score = sum(weighted) / len(weighted)
    else:
        composite_score = 50

    # 综合状态
    if composite_score >= 75:
        composite_regime = "牛市格局"
    elif composite_score >= 55:
        composite_regime = "震荡偏多"
    elif composite_score >= 40:
        composite_regime = "震荡格局"
    elif composite_score >= 20:
        composite_regime = "震荡偏空"
    else:
        composite_regime = "熊市格局"

    # 广度：多少指数在多头
    bullish_count = sum(1 for r in results.values()
                        if r.get("regime", "") in ("牛市", "震荡偏多"))

    results["composite"] = {
        "regime": composite_regime,
        "score": round(composite_score, 1),
        "bullish_indices": f"{bullish_count}/{len(results)-1}",
        "advice": _composite_advice(composite_regime, bullish_count),
        "divergence": _check_divergence(results),
    }

    return results


# ═══════════════════════════════════════════════════════════════
# 各维度评分
# ═══════════════════════════════════════════════════════════════

def _score_ma_alignment(ma5, ma10, ma20, ma60, n) -> int:
    """均线排列评分"""
    m5, m10, m20, m60 = ma5.iloc[-1], ma10.iloc[-1], ma20.iloc[-1], ma60.iloc[-1]
    score = 12  # 基线

    if m5 > m10 > m20 > m60:
        score = 25  # 完美多头
    elif m5 > m10 > m20:
        score = 22  # 多头排列（缺MA60）
    elif m5 > m20 and m10 > m20:
        score = 18  # 偏多
    elif m5 < m10 < m20 < m60:
        score = 0   # 完美空头
    elif m5 < m20 and m10 < m20:
        score = 3   # 偏空
    else:
        # 均线缠绕——检查趋势
        spread = (max(m5, m10, m20, m60) - min(m5, m10, m20, m60)) / abs(ma20.iloc[-1]) * 100
        if spread < 3:
            score = 13  # 高度粘合（变盘前兆）
        elif ma20.iloc[-1] > ma20.iloc[-20]:
            score = 15  # 缠绕偏多
        else:
            score = 8   # 缠绕偏空

    # 斜率加分
    ma20_slope = (ma20.iloc[-1] - ma20.iloc[-20]) / ma20.iloc[-20] * 100 if ma20.iloc[-20] != 0 else 0
    if ma20_slope > 3:
        score = min(25, score + 2)
    elif ma20_slope < -3:
        score = max(0, score - 2)

    return score


def _score_momentum(close, n) -> int:
    """价格动量评分"""
    score = 12
    current = close.iloc[-1]

    # 不同周期的涨跌幅
    for window, weight in [(5, 0.3), (20, 0.35), (60, 0.35)]:
        if n > window:
            ret = (current - close.iloc[-window]) / close.iloc[-window] * 100
            if ret > 10:
                score += weight * 13
            elif ret > 3:
                score += weight * 8
            elif ret > 0:
                score += weight * 4
            elif ret > -3:
                score += weight * 1
            elif ret > -10:
                score -= weight * 4
            else:
                score -= weight * 8

    return max(0, min(25, int(score)))


def _score_volatility(close, n) -> int:
    """波动率环境评分 — 低波牛市更健康，高波需警惕"""
    rets = close.pct_change().dropna()

    # 近期波动率 vs 长期波动率
    vol_short = rets.tail(20).std() * np.sqrt(252)
    vol_long = rets.tail(60).std() * np.sqrt(252) if len(rets) >= 60 else vol_short

    if vol_long == 0:
        return 12

    vol_ratio = vol_short / vol_long

    if vol_short < 0.18:
        score = 20  # 低波可能酝酿牛市
    elif vol_short < 0.25:
        score = 16  # 正常
    elif vol_short < 0.35:
        score = 10  # 偏高
    else:
        score = 4   # 极高波动（恐慌或亢奋）

    # 波动率放大系数
    if vol_ratio > 1.5:
        score -= 3  # 波动突然放大 → 不确定性增加
    elif vol_ratio < 0.7:
        score += 2  # 波动收敛 → 可能变盘

    return max(0, min(25, score))


def _score_volume(volume, close, n) -> int:
    """成交量趋势评分 — 放量上涨健康，缩量下跌衰竭"""
    score = 12
    vol_5 = volume.tail(5).mean()
    vol_20 = volume.tail(20).mean()

    if vol_20 == 0:
        return score

    vol_ratio = vol_5 / vol_20

    # 最近上涨还是下跌
    ret_5d = (close.iloc[-1] - close.iloc[-5]) / close.iloc[-5] if close.iloc[-5] != 0 else 0

    if ret_5d > 0 and vol_ratio > 1.2:
        score = 22  # 放量上涨 — 健康
    elif ret_5d > 0 and vol_ratio > 1.0:
        score = 18  # 量价配合
    elif ret_5d < 0 and vol_ratio < 0.8:
        score = 16  # 缩量下跌 — 可能衰竭
    elif ret_5d < 0 and vol_ratio > 1.3:
        score = 4   # 放量下跌 — 危险
    elif ret_5d > 0 and vol_ratio < 0.7:
        score = 10  # 缩量上涨 — 动力不足
    else:
        score = 12

    return max(0, min(25, score))


# ═══════════════════════════════════════════════════════════════
# 状态转换检测
# ═══════════════════════════════════════════════════════════════

def _detect_transition(df, current_score, current_regime, n) -> str:
    """检测状态转换信号"""
    if n < 40:
        return "数据不足"

    # 简单方法：比较最近10天的得分变化
    close = df["close"]
    ma20 = _ma(close, 20)

    # 均线上穿/下穿
    if n >= 21:
        was_below = close.iloc[-11] < ma20.iloc[-11]
        now_above = close.iloc[-1] > ma20.iloc[-1]
        was_above = close.iloc[-11] > ma20.iloc[-11]
        now_below = close.iloc[-1] < ma20.iloc[-1]

        if was_below and now_above:
            return "【突破确认】价格上穿MA20，可能进入上涨趋势"
        if was_above and now_below:
            return "【破位确认】价格下穿MA20，可能进入下跌趋势"

    # 分数变化
    if current_regime in ("牛市", "震荡偏多") and current_score < 65:
        return "【动能减弱】牛市/偏多格局但评分偏低，关注是否转弱"
    if current_regime in ("熊市", "震荡偏空") and current_score > 35:
        return "【底部特征】熊市/偏空格局但评分偏高，下跌动能可能衰竭"

    return "无明确转换信号"


def _composite_advice(regime: str, bullish_count: int) -> str:
    """综合操作建议"""
    if regime == "牛市格局":
        return "市场整体强势，建议积极参与，总仓位70-80%"
    elif regime == "震荡偏多":
        return "多数指数偏多，精选板块参与，仓位50-65%"
    elif regime == "震荡格局":
        return "市场方向不明，降低仓位至35-50%，等待方向选择"
    elif regime == "震荡偏空":
        return "多数指数偏弱，防御为主，仓位20-35%"
    else:
        return "市场整体弱势，建议持币观望，仓位≤20%"


def _check_divergence(results: dict) -> str:
    """检查指数间背离"""
    scores_300 = results.get("000300", {}).get("score", 50)
    scores_cyb = results.get("399006", {}).get("score", 50)
    scores_kcb = results.get("000688", {}).get("score", 50)

    if scores_300 > 60 and scores_cyb < 40:
        return "沪深300走强 vs 创业板走弱 — 资金流向大市值（防御性轮动）"
    if scores_300 < 40 and scores_cyb > 60:
        return "创业板走强 vs 沪深300走弱 — 资金流向成长股（风险偏好提升）"
    if scores_kcb > 70 and scores_300 < 50:
        return "科创板独强 — 主题炒作特征，注意持续性"

    return "无明显背离"


def _score_extreme_events(df: pd.DataFrame, n: int) -> tuple:
    """
    极端事件/反转信号评分 (0-25分) — 检测单日异常现象。

    检测类型：
      - V型反转: 前日大跌 + 今日大涨（或反向）
      - 放量止跌: 连跌后出现放量长下影线
      - 放量止涨: 连涨后出现放量长上影线
      - 量能爆炸: 单日成交量 > 3x 20日均量
      - 冰点日: 振幅极小+缩量（变盘前兆）
      - 沸点日: 振幅极大+放量（情绪极端）
    """
    if n < 10:
        return 12, []

    close = df["close"]
    open_ = df["open"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]
    signals = []
    score = 12  # 基线

    # 去最近10天逐日分析
    for i in range(max(0, n - 10), n):
        if i < 3:
            continue

        body = abs(close.iloc[i] - open_.iloc[i])
        total_range = high.iloc[i] - low.iloc[i]
        body_ratio = body / total_range if total_range > 0 else 0
        upper_shadow = high.iloc[i] - max(open_.iloc[i], close.iloc[i])
        lower_shadow = min(open_.iloc[i], close.iloc[i]) - low.iloc[i]
        day_ret = (close.iloc[i] - close.iloc[i - 1]) / close.iloc[i - 1] * 100
        vol_20avg = volume.iloc[max(0, i - 20):i].mean() if i >= 20 else volume.iloc[:i].mean()
        vol_ratio = volume.iloc[i] / vol_20avg if vol_20avg > 0 else 1

        date_str = df.index[i].strftime("%m-%d") if hasattr(df.index[i], 'strftime') else str(df.index[i])[:10]

        # ── V型反转：前日大跌(<-2%) + 今日大涨(>2%) ──
        if i >= 1:
            prev_ret = (close.iloc[i - 1] - close.iloc[i - 2]) / close.iloc[i - 2] * 100 if i >= 2 else 0
            if prev_ret < -2.0 and day_ret > 2.0:
                signals.append(f"V型反转({date_str}): 前日{prev_ret:.1f}%→今日{day_ret:+.1f}%")
                score += 5
            elif prev_ret > 2.0 and day_ret < -2.0:
                signals.append(f"倒V反转({date_str}): 前日{prev_ret:+.1f}%→今日{day_ret:+.1f}%")
                score -= 3

        # ── 放量止跌：连跌3日+今日长下影+放量 ──
        if i >= 4:
            prev_3_down = all(close.iloc[i - j] < close.iloc[i - j - 1] for j in range(1, 4))
            if prev_3_down and lower_shadow > body * 1.5 and vol_ratio > 1.5:
                signals.append(f"放量止跌({date_str}): 连跌3日后长下影+放量{vol_ratio:.1f}x")
                score += 6  # 强反转信号

        # ── 放量止涨：连涨3日后长上影+放量 ──
        if i >= 4:
            prev_3_up = all(close.iloc[i - j] > close.iloc[i - j - 1] for j in range(1, 4))
            if prev_3_up and upper_shadow > body * 1.5 and vol_ratio > 1.5:
                signals.append(f"放量止涨({date_str}): 连涨3日后长上影+放量{vol_ratio:.1f}x")
                score -= 4  # 顶部信号

        # ── 量能爆炸日：vol > 3x 均量 ──
        if vol_ratio > 3.0:
            if day_ret > 0:
                signals.append(f"爆量上涨({date_str}): 量{vol_ratio:.1f}x 涨幅{day_ret:+.1f}%")
                score += 4  # 放量大涨 → 机构入场可能
            else:
                signals.append(f"爆量下跌({date_str}): 量{vol_ratio:.1f}x 跌幅{day_ret:+.1f}%")
                score -= 5  # 放量大跌 → 恐慌出逃

        # ── 冰点日：振幅<1%+缩量<0.5x ──
        amp = (high.iloc[i] - low.iloc[i]) / close.iloc[i] * 100
        if amp < 1.0 and vol_ratio < 0.5:
            signals.append(f"冰点日({date_str}): 振幅{amp:.2f}% 量{vol_ratio:.2f}x → 变盘前兆")
            score += 3

        # ── 沸点日：振幅>5%+放量>2x ──
        if amp > 5.0 and vol_ratio > 2.0:
            if day_ret > 0:
                signals.append(f"沸点日({date_str}): 振幅{amp:.1f}% 量{vol_ratio:.1f}x → 情绪亢奋")
            else:
                signals.append(f"恐慌日({date_str}): 振幅{amp:.1f}% 量{vol_ratio:.1f}x → 情绪崩溃")
            score -= 2

    return max(0, min(25, score)), signals[-8:]  # 最近8个


def _empty_regime(reason: str) -> dict:
    return {
        "regime": "无法判断",
        "score": 50,
        "dimensions": {"ma_alignment": 12, "momentum": 12, "volatility": 12, "volume": 12, "extreme_events": 12},
        "transition_signal": reason,
        "confidence": "低",
        "advice": "观望",
        "error": reason,
    }
