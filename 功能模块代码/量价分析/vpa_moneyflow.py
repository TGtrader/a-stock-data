"""
VPA 资金流分析层 — 主力资金动向检测
====================================
基于 Tushare moneyflow 数据，将威科夫理论中的"局内人行为"数据化。

核心能力：
  1. 连续净流入/流出检测
  2. 周期累计流入率（标准化跨股票对比指标）
  3. 主力 vs 散户背离分析
  4. 资金流 × 趋势 三维共振决策矩阵
"""

import logging
from typing import Dict, List, Optional, Tuple
import numpy as np
import pandas as pd

logger = logging.getLogger("vpa.moneyflow")


# ═══════════════════════════════════════════════════════════════
# 连续净流入/流出检测
# ═══════════════════════════════════════════════════════════════

def detect_continuous_flow(moneyflow_df: pd.DataFrame) -> dict:
    """
    检测主力资金的持续行为。

    Args:
        moneyflow_df: Tushare moneyflow 数据，需含 net_mf_amount 列

    Returns:
        {continuous_inflow_Nd: bool, continuous_outflow_Nd: bool, ...}
    """
    result = {}
    if moneyflow_df is None or moneyflow_df.empty:
        return result

    # 确保有主力净流入字段
    mf_col = None
    for col in ["net_mf_amount", "net_amount"]:
        if col in moneyflow_df.columns:
            mf_col = col
            break

    if mf_col is None:
        return result

    net_mf = moneyflow_df[mf_col].values
    if len(net_mf) < 2:
        return result

    # 检测连续N日流入/流出
    for n in [3, 5, 7, 10]:
        if len(net_mf) >= n:
            recent = net_mf[-n:]
            result[f"continuous_inflow_{n}d"] = bool((recent > 0).all())
            result[f"continuous_outflow_{n}d"] = bool((recent < 0).all())
        else:
            result[f"continuous_inflow_{n}d"] = False
            result[f"continuous_outflow_{n}d"] = False

    # 连续流入/流出的最大天数
    consecutive = 0
    current_sign = 1 if net_mf[-1] > 0 else (-1 if net_mf[-1] < 0 else 0)
    for i in range(len(net_mf) - 1, -1, -1):
        if current_sign == 1 and net_mf[i] > 0:
            consecutive += 1
        elif current_sign == -1 and net_mf[i] < 0:
            consecutive += 1
        else:
            break
    result["max_consecutive_days"] = consecutive
    result["flow_direction"] = "净流入" if current_sign == 1 else ("净流出" if current_sign == -1 else "平衡")

    return result


# ═══════════════════════════════════════════════════════════════
# 周期累计流入率
# ═══════════════════════════════════════════════════════════════

def calc_period_flow_ratio(moneyflow_df: pd.DataFrame, float_mv: float = 0) -> dict:
    """
    计算 N 日内主力累计净流入 / 流通市值 —— 标准化跨股票对比指标。

    参考代码逻辑：
      period_N_ratio = sum(net_lg_amount + net_elg_amount) / float_mv * 100

    Args:
        moneyflow_df: Tushare moneyflow 数据
        float_mv: 流通市值（万元）。为0时返回绝对值不除市值。

    Returns:
        {flow_ratio_Nd: float(%), flow_absolute_Nd: float(万元), ...}
    """
    result = {}
    if moneyflow_df is None or moneyflow_df.empty:
        return result

    # 找主力净流入字段
    lg_col = elg_col = None
    for col in ["net_lg_amount", "buy_lg_amount"]:
        if col in moneyflow_df.columns:
            lg_col = col
            break
    for col in ["net_elg_amount", "buy_elg_amount"]:
        if col in moneyflow_df.columns:
            elg_col = col
            break

    # 如果找到大单和特大单，用两者之和；否则用主力净流入
    if lg_col and elg_col:
        if "net" in lg_col:
            large = moneyflow_df[lg_col].fillna(0)
        else:
            sell_lg = moneyflow_df.get("sell_lg_amount", pd.Series(0, index=moneyflow_df.index)).fillna(0)
            large = moneyflow_df[lg_col].fillna(0) - sell_lg
        large = pd.to_numeric(large, errors="coerce").fillna(0)

        if "net" in elg_col:
            extra = moneyflow_df[elg_col].fillna(0)
        else:
            sell_elg = moneyflow_df.get("sell_elg_amount", pd.Series(0, index=moneyflow_df.index)).fillna(0)
            extra = moneyflow_df[elg_col].fillna(0) - sell_elg
        extra = pd.to_numeric(extra, errors="coerce").fillna(0)

        main_force = large + extra
    else:
        mf_col = None
        for col in ["net_mf_amount", "net_amount"]:
            if col in moneyflow_df.columns:
                mf_col = col
                break
        if mf_col is None:
            return result
        main_force = pd.to_numeric(moneyflow_df[mf_col], errors="coerce").fillna(0)

    # 各周期的累计值
    n = len(main_force)
    for period in [3, 5, 10, 20]:
        if n >= period:
            period_sum = main_force.iloc[-period:].sum()
            result[f"flow_absolute_{period}d"] = round(float(period_sum), 2)
            if float_mv > 0:
                result[f"flow_ratio_{period}d"] = round(float(period_sum / float_mv * 100), 4)
            else:
                result[f"flow_ratio_{period}d"] = None
        else:
            result[f"flow_absolute_{period}d"] = 0
            result[f"flow_ratio_{period}d"] = None

    # 日平均流入额
    if n >= 5:
        result["avg_daily_inflow_5d"] = round(float(main_force.iloc[-5:].mean()), 2)
    if n >= 10:
        result["avg_daily_inflow_10d"] = round(float(main_force.iloc[-10:].mean()), 2)

    return result


# ═══════════════════════════════════════════════════════════════
# 主力 vs 散户背离检测
# ═══════════════════════════════════════════════════════════════

def detect_smart_retail_divergence(moneyflow_df: pd.DataFrame, lookback: int = 5) -> dict:
    """
    局内人(主力)和散户的行为背离——威科夫理论核心观察。

    - 主力连续买入 + 散户连续卖出 = 吸筹信号
    - 主力连续卖出 + 散户连续买入 = 派筹信号
    """
    if moneyflow_df is None or moneyflow_df.empty:
        return {"divergence": "数据不足"}

    # 计算主力净额
    main_net = None
    for col in ["net_mf_amount", "net_amount"]:
        if col in moneyflow_df.columns:
            main_net = pd.to_numeric(moneyflow_df[col], errors="coerce").fillna(0)
            break

    # 计算散户净额
    retail_net = None
    if "buy_sm_amount" in moneyflow_df.columns and "sell_sm_amount" in moneyflow_df.columns:
        retail_net = (
            pd.to_numeric(moneyflow_df["buy_sm_amount"], errors="coerce").fillna(0) -
            pd.to_numeric(moneyflow_df["sell_sm_amount"], errors="coerce").fillna(0)
        )
    elif "net_sm_amount" in moneyflow_df.columns:
        retail_net = pd.to_numeric(moneyflow_df["net_sm_amount"], errors="coerce").fillna(0)

    if main_net is None:
        return {"divergence": "主力数据不足"}

    n = min(len(main_net), lookback)
    main_sum = main_net.iloc[-n:].sum()
    retail_sum = retail_net.iloc[-n:].sum() if retail_net is not None else 0

    if main_sum > 0 and retail_sum < 0:
        divergence = "主力吸筹_散户出货"
        interpretation = "局内人(主力)在买入、散户在卖出——典型的威科夫吸筹特征，看涨信号"
        signal = "bullish"
    elif main_sum < 0 and retail_sum > 0:
        divergence = "主力派筹_散户接盘"
        interpretation = "局内人(主力)在卖出、散户在买入——典型的威科夫派筹特征，看跌信号"
        signal = "bearish"
    elif main_sum > 0 and retail_sum > 0:
        divergence = "主力散户同步做多"
        interpretation = "主力和散户都在买入——需结合趋势位置判断（高位可能是诱多）"
        signal = "neutral_bullish"
    elif main_sum < 0 and retail_sum < 0:
        divergence = "主力散户同步做空"
        interpretation = "主力散户都在卖出——市场情绪一致看空"
        signal = "neutral_bearish"
    else:
        divergence = "数据不足"
        interpretation = ""
        signal = "neutral"

    return {
        "divergence": divergence,
        "signal": signal,
        "main_force_net_5d": round(float(main_sum), 2),
        "retail_net_5d": round(float(retail_sum), 2) if retail_net is not None else None,
        "interpretation": interpretation,
    }


# ═══════════════════════════════════════════════════════════════
# 资金流综合状态
# ═══════════════════════════════════════════════════════════════

def analyze_moneyflow(moneyflow_df: pd.DataFrame, float_mv: float = 0) -> dict:
    """
    综合资金流分析。

    Args:
        moneyflow_df: Tushare moneyflow DataFrame
        float_mv: 流通市值（万元）

    Returns:
        完整资金流分析结果
    """
    if moneyflow_df is None or moneyflow_df.empty:
        return {
            "available": False,
            "error": "资金流数据不可用",
            "flow_ratios": {},
        }

    result = {"available": True}
    result.update(detect_continuous_flow(moneyflow_df))
    result["flow_ratios"] = calc_period_flow_ratio(moneyflow_df, float_mv)
    result["smart_retail"] = detect_smart_retail_divergence(moneyflow_df)

    # 综合判断
    continuous = result.get("max_consecutive_days", 0)
    divergence = result["smart_retail"].get("divergence", "")

    if continuous >= 7 and "吸筹" in divergence:
        result["summary"] = "强烈看多：主力持续7日以上净流入+散户出货，局内人坚定建仓"
        result["rating"] = "strong_bullish"
    elif continuous >= 5:
        result["summary"] = "偏多：主力连续净流入，资金面积极"
        result["rating"] = "bullish"
    elif continuous <= -5:
        result["summary"] = "偏空：主力连续净流出，资金在撤"
        result["rating"] = "bearish"
    elif "派筹" in divergence:
        result["summary"] = "看空：主力出货散户接盘，派筹信号明确"
        result["rating"] = "strong_bearish"
    else:
        result["summary"] = "中性：资金流方向不明确"
        result["rating"] = "neutral"

    return result


# ═══════════════════════════════════════════════════════════════
# 资金流 × 趋势 三维共振决策矩阵
# ═══════════════════════════════════════════════════════════════

def assess_flow_trend_resonance(trend: dict, moneyflow_result: dict) -> dict:
    """
    判断资金流与趋势的共振/背离关系。

    三维共振体系：趋势方向 × 量价确认 × 资金流方向
    """
    if not moneyflow_result.get("available"):
        return {
            "resonance": "资金流数据不可用",
            "signal_strength": 0,
            "summary": "无法进行三维共振判断（资金流数据缺失）",
        }

    # 趋势方向
    trend_direction = trend.get("short_term", {}).get("direction", "")
    trend_strength = trend.get("short_term", {}).get("strength", 50)

    # 资金流方向
    flow_rating = moneyflow_result.get("rating", "neutral")
    flow_continuous = moneyflow_result.get("max_consecutive_days", 0)
    flow_divergence = moneyflow_result.get("smart_retail", {}).get("divergence", "")

    # 共振判断
    is_trend_up = trend_direction.startswith("上涨")
    is_trend_down = trend_direction.startswith("下跌")
    is_flow_in = flow_rating in ("bullish", "strong_bullish")
    is_flow_out = flow_rating in ("bearish", "strong_bearish")

    resonance = ""
    signal_strength = 0

    if is_trend_up and is_flow_in:
        resonance = "资金趋势共振看多"
        signal_strength = min(90, trend_strength * 0.5 + 40)
        if "吸筹" in flow_divergence:
            signal_strength = min(100, signal_strength + 10)
        summary = "三维共振最强信号：趋势向上+主力持续流入——A级做多信号"
    elif is_trend_up and is_flow_out:
        resonance = "趋势向上涨但资金在撤(背离)"
        signal_strength = 30
        summary = "趋势还在涨但主力已在撤——'诱多陷阱'风险高，建议减仓"
    elif is_trend_down and is_flow_out:
        resonance = "资金趋势共振看空"
        signal_strength = min(90, trend_strength * 0.3 + 50)
        summary = "趋势向下+主力持续流出——持币观望最佳策略"
    elif is_trend_down and is_flow_in:
        resonance = "趋势下跌但资金在吸(背离)"
        signal_strength = 35
        summary = "趋势还在跌但主力在偷偷吸筹——'黄金坑'可能性，关注反转信号"
    else:
        resonance = "资金趋势关系中性"
        signal_strength = 45
        summary = "趋势和资金流方向不明确——观望等待"

    return {
        "resonance": resonance,
        "signal_strength": signal_strength,
        "trend_direction": trend_direction,
        "flow_rating": flow_rating,
        "flow_continuous_days": flow_continuous,
        "smart_retail_divergence": flow_divergence,
        "summary": summary,
    }
