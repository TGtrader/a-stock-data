"""
交易计划生成器
==============
基于技术分析自动生成：入场价 / 止损价 / 第一目标 / 第二目标 / 仓位建议

仓位计算方法：
  - 凯利公式: f = (bp - q) / b, where b=盈亏比, p=胜率
  - ATR-N标准化: 仓位 = 风险资金 / (N × ATR × 合约乘数)
  - 固定比例: 仓位 = 总资金 × 仓位比例 × 信号强度
  - 风险回报比过滤: 不达标的自动剔除（默认最低2:1）
"""

import logging
from typing import Dict, List, Optional, Tuple
import numpy as np
import pandas as pd

from ...core.config import Config

logger = logging.getLogger("tg.strategy.trade_plan")


def generate_trade_plan(
    df: pd.DataFrame,
    signal_verdict,            # SignalVerdict 对象
    current_price: float = None,
    total_capital: float = 100000,          # 总资金（元）
    risk_per_trade_pct: float = 0.02,       # 单笔风险比例（2%）
    min_risk_reward: float = None,          # 最低风险回报比
    position_method: str = "fixed_risk",    # kelly / atr / fixed_risk
    atr_period: int = 14,
) -> dict:
    """
    生成完整的交易计划。

    Args:
        df: OHLCV DataFrame
        signal_verdict: 信号裁决结果 (SignalVerdict)
        current_price: 当前价格（None则取最新收盘价）
        total_capital: 总资金
        risk_per_trade_pct: 每笔交易最大亏损比例
        min_risk_reward: 最低风险回报比（默认从Config读取）
        position_method: 仓位计算方法
        atr_period: ATR周期

    Returns:
        {
            "entry_price": float,
            "stop_loss": float,
            "target_1": float,
            "target_2": float,
            "risk_amount": float,
            "reward_1": float,
            "reward_2": float,
            "risk_reward_1": float,
            "risk_reward_2": float,
            "position_pct": float,       # 建议仓位比例
            "position_shares": int,      # 建议股数
            "plan_valid": bool,          # 计划是否有效（达标）
            "rejection_reason": str,     # 拒绝原因
            "detail": str,               # 可读描述
        }
    """
    if min_risk_reward is None:
        min_risk_reward = Config.MIN_RISK_REWARD_RATIO

    if df is None or len(df) < atr_period + 5:
        return _invalid_plan("数据不足")

    close = df["close"]
    high = df["high"]
    low = df["low"]

    if current_price is None:
        current_price = float(close.iloc[-1])

    # ── 1. 计算 ATR ──
    atr = _calc_atr(high, low, close, atr_period)
    atr_pct = atr / current_price * 100 if current_price > 0 else 2

    # ── 2. 判定交易方向 ──
    verdict_text = signal_verdict.verdict
    if "做多" in verdict_text or "偏多" in verdict_text:
        direction = "long"
    elif "做空" in verdict_text or "偏空" in verdict_text:
        direction = "short"
    else:
        return _invalid_plan(f"当前信号不支持交易: {verdict_text}")

    # ── 3. 入场价 ──
    if direction == "long":
        # 做多入场：回调到支撑位附近，或当前价
        entry_price = _find_entry_long(df, current_price, atr)
    else:
        entry_price = _find_entry_short(df, current_price, atr)

    # ── 4. 止损价 ──
    if direction == "long":
        # 做多止损：支撑位下方 / ATR轨道下轨 / 固定比例
        recent_low = low.iloc[-20:].min()
        atr_stop = entry_price - atr * 2.0
        pct_stop = current_price * (1 - Config.DEFAULT_STOP_LOSS)
        stop_loss = max(recent_low * 0.98, atr_stop, pct_stop)
    else:
        recent_high = high.iloc[-20:].max()
        atr_stop = entry_price + atr * 2.0
        pct_stop = current_price * (1 + Config.DEFAULT_STOP_LOSS)
        stop_loss = min(recent_high * 1.02, atr_stop, pct_stop)

    stop_loss = round(stop_loss, 2)

    # ── 5. 目标价 ──
    if direction == "long":
        recent_high = high.iloc[-30:].max()
        # 第一目标：最小阻力位
        target_1 = min(entry_price + atr * 3.0, recent_high * 0.99)
        # 第二目标：通道上轨或扩展
        target_2 = entry_price + atr * 5.0

        # 确保目标 > 入场
        target_1 = max(target_1, entry_price * 1.02)
        target_2 = max(target_2, target_1 * 1.03)
    else:
        recent_low = low.iloc[-30:].min()
        target_1 = max(entry_price - atr * 3.0, recent_low * 1.01)
        target_2 = entry_price - atr * 5.0
        target_1 = min(target_1, entry_price * 0.98)
        target_2 = min(target_2, target_1 * 0.97)

    target_1 = round(target_1, 2)
    target_2 = round(target_2, 2)

    # ── 6. 风险回报比 ──
    risk = abs(entry_price - stop_loss)
    reward_1 = abs(target_1 - entry_price)
    reward_2 = abs(target_2 - entry_price)

    risk_reward_1 = round(reward_1 / risk, 1) if risk > 0 else 0
    risk_reward_2 = round(reward_2 / risk, 1) if risk > 0 else 0

    # ── 7. 过滤检查 ──
    if risk_reward_1 < min_risk_reward and risk_reward_2 < min_risk_reward:
        return _invalid_plan(
            f"风险回报比不达标: R:R1={risk_reward_1:.1f}, R:R2={risk_reward_2:.1f}（最低要求{min_risk_reward:.1f}）"
        )

    if atr_pct < 0.5:
        return _invalid_plan(f"波动率过低（ATR={atr_pct:.2f}%），不适合交易")

    # ── 8. 仓位计算 ──
    risk_amount = total_capital * risk_per_trade_pct
    signal_strength = signal_verdict.score / 100

    if position_method == "kelly":
        # 凯利公式: f = (bp - q) / b
        win_rate = 0.55 + signal_strength * 0.15  # 估计胜率 55-70%
        win_rate = min(0.75, win_rate)
        b = risk_reward_1 if risk_reward_1 > 0 else 2
        kelly_f = (b * win_rate - (1 - win_rate)) / b
        kelly_f = max(0.02, min(0.20, kelly_f))  # 凯利上限20%
        position_pct = kelly_f * signal_strength * 0.8  # 半凯利
    elif position_method == "atr":
        # ATR-N 标准化: 1%风险对应仓位
        risk_per_share = atr * 2.0
        if risk_per_share > 0:
            position_pct = risk_amount / (risk_per_share * 100) * 100 / total_capital
            position_pct = max(0.01, min(0.25, position_pct))
        else:
            position_pct = 0.05
    else:  # fixed_risk
        # 固定风险比例
        if risk > 0:
            shares_risk = risk_amount / risk
            position_pct = shares_risk * entry_price / total_capital
            position_pct = max(0.01, min(0.25, position_pct))
        else:
            position_pct = 0.05

    # 收束：信号强度调节
    position_pct = position_pct * signal_strength

    # 上限控制
    position_pct = min(position_pct, Config.MAX_SINGLE_WEIGHT)

    # 下取整到百股
    shares = int(position_pct * total_capital / entry_price / 100) * 100
    shares = max(100, shares)

    position_pct = shares * entry_price / total_capital * 100

    # ── 9. 生成结果 ──
    detail_lines = [
        f"交易方向: {'做多 📈' if direction == 'long' else '做空 📉'}",
        f"信号评分: {signal_verdict.score}/100 ({signal_verdict.verdict})",
        f"入场价: {entry_price:.2f}",
        f"止损价: {stop_loss:.2f} (风险: {risk:.2f} / {risk/entry_price*100:.1f}%)",
        f"第一目标: {target_1:.2f} (R:R = {risk_reward_1:.1f}:1)",
        f"第二目标: {target_2:.2f} (R:R = {risk_reward_2:.1f}:1)",
        f"ATR: {atr:.2f} ({atr_pct:.1f}%)",
        f"建议仓位: {position_pct:.1f}% ({shares}股)",
    ]

    return {
        "entry_price": round(entry_price, 2),
        "stop_loss": stop_loss,
        "target_1": target_1,
        "target_2": target_2,
        "risk_amount_per_share": round(risk, 2),
        "reward_1": round(reward_1, 2),
        "reward_2": round(reward_2, 2),
        "risk_reward_1": risk_reward_1,
        "risk_reward_2": risk_reward_2,
        "atr": round(atr, 2),
        "atr_pct": round(atr_pct, 2),
        "position_pct": round(position_pct, 1),
        "position_shares": shares,
        "plan_valid": True,
        "rejection_reason": None,
        "detail": "\n".join(detail_lines),
        "direction": direction,
    }


def _calc_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> float:
    """计算 ATR（平均真实波幅）"""
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = true_range.rolling(window=period).mean().iloc[-1]
    return float(atr) if not pd.isna(atr) else 1.0


def _find_entry_long(df: pd.DataFrame, current_price: float, atr: float) -> float:
    """
    寻找做多入场价。

    优先：回调到MA20附近 → 挂单价
    否则：当前价（趋势中直接入场）
    """
    close = df["close"]
    if len(close) < 20:
        return current_price

    ma20 = close.rolling(20).mean().iloc[-1]
    if pd.isna(ma20):
        return current_price

    # 如果当前价高于MA20，建议回调入场
    if current_price > ma20 * 1.02:
        # 回调到 MA20 附近
        entry = ma20 * 1.005
    elif current_price > ma20 * 0.98:
        # 在MA20附近，直接入场
        entry = current_price
    else:
        # 低于MA20，等待突破
        entry = ma20 * 1.005

    return round(entry, 2)


def _find_entry_short(df: pd.DataFrame, current_price: float, atr: float) -> float:
    """寻找做空入场价"""
    close = df["close"]
    if len(close) < 20:
        return current_price

    ma20 = close.rolling(20).mean().iloc[-1]
    if pd.isna(ma20):
        return current_price

    if current_price < ma20 * 0.98:
        entry = ma20 * 0.995
    elif current_price < ma20 * 1.02:
        entry = current_price
    else:
        entry = ma20 * 0.995

    return round(entry, 2)


def _invalid_plan(reason: str) -> dict:
    return {
        "entry_price": None,
        "stop_loss": None,
        "target_1": None,
        "target_2": None,
        "plan_valid": False,
        "rejection_reason": reason,
        "detail": f"交易计划不成立: {reason}",
    }
