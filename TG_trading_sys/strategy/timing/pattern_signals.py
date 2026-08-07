"""
形态识别信号检测
================
基于价格结构的经典技术形态识别：
  - 箱体突破（横盘整理后放量突破上/下轨）
  - 三角形收敛突破（高低点收敛 + 方向选择）
  - W底 / M头（双重底/顶形态）
  - 旗形/楔形整理（趋势中继形态）
  - 头肩底/顶（简化检测）
"""

import logging
from typing import Dict, List, Optional, Tuple
import numpy as np
import pandas as pd

logger = logging.getLogger("tg.strategy.pattern")


def detect_patterns(df: pd.DataFrame) -> dict:
    """
    完整形态识别分析。

    Returns:
        {
            "box_breakout": dict|None,     # 箱体突破
            "triangle": dict|None,          # 三角形收敛
            "double_pattern": dict|None,    # W底/M头
            "flag_pattern": dict|None,      # 旗形/楔形
            "signals": [...],               # 综合信号列表
            "verdict": str,
        }
    """
    if df is None or len(df) < 40:
        return {"signals": [], "verdict": "数据不足（至少40根K线）"}

    result = {
        "box_breakout": _detect_box_breakout(df),
        "triangle": _detect_triangle(df),
        "double_pattern": _detect_double_pattern(df),
        "flag_pattern": _detect_flag(df),
    }

    # 汇总信号
    signals = []
    for key, data in result.items():
        if data and data.get("signal"):
            signals.append(data["signal"])

    result["signals"] = signals
    result["verdict"] = _pattern_verdict(signals)

    return result


# ═══════════════════════════════════════════════════════════════
# 1. 箱体突破检测
# ═══════════════════════════════════════════════════════════════

def _detect_box_breakout(df: pd.DataFrame) -> Optional[dict]:
    """
    检测横盘箱体整理后的突破。

    逻辑：
      1. 找近20日最高价/最低价作为箱体上/下轨
      2. 判断箱体振幅 <15%（横盘特征）
      3. 最新价格突破上轨（上涨突破）或下轨（下跌突破）
      4. 要求放量确认（量 > 1.5×20日均量）
    """
    if len(df) < 25:
        return None

    n = len(df)
    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]

    # 近20日箱体
    win_20 = slice(max(0, n - 25), n - 1)  # 不含最后1根（用于判断突破）
    box_high = high.iloc[win_20].max()
    box_low = low.iloc[win_20].min()
    box_range = (box_high - box_low) / box_low * 100 if box_low > 0 else 100

    # 横盘条件：振幅 5-18%
    if box_range < 3 or box_range > 20:
        return None

    # 箱体内天数（高位/低位触及次数）
    high_touches = (high.iloc[win_20] >= box_high * 0.97).sum()
    low_touches = (low.iloc[win_20] <= box_low * 1.03).sum()
    if high_touches + low_touches < 3:
        return None  # 不够多次确认的箱体

    # 最新价突破判断
    latest_close = close.iloc[-1]
    latest_volume = volume.iloc[-1]
    avg_vol_20 = volume.iloc[-25:-1].mean()

    vol_ratio = latest_volume / avg_vol_20 if avg_vol_20 > 0 else 1

    # 上突破
    if latest_close > box_high and vol_ratio > 1.3:
        target = box_high + (box_high - box_low)
        return {
            "pattern": "箱体上突破",
            "box_high": round(float(box_high), 2),
            "box_low": round(float(box_low), 2),
            "range_pct": round(box_range, 1),
            "volume_ratio": round(float(vol_ratio), 1),
            "target": round(float(target), 2),
            "stop_loss": round(float(box_low * 0.98), 2),
            "signal": {
                "signal": f"放量突破箱体（振幅{box_range:.1f}%，量{vol_ratio:.1f}x）",
                "type": "趋势启动",
                "action": "加仓",
                "priority": 1,
            },
        }

    # 下突破
    if latest_close < box_low and vol_ratio > 1.2:
        return {
            "pattern": "箱体下突破",
            "box_high": round(float(box_high), 2),
            "box_low": round(float(box_low), 2),
            "range_pct": round(box_range, 1),
            "volume_ratio": round(float(vol_ratio), 1),
            "signal": {
                "signal": f"放量跌破箱体（振幅{box_range:.1f}%，量{vol_ratio:.1f}x）",
                "type": "趋势破坏",
                "action": "减仓/离场",
                "priority": 1,
            },
        }

    # 箱体内运行中
    return {
        "pattern": "箱体整理中",
        "box_high": round(float(box_high), 2),
        "box_low": round(float(box_low), 2),
        "range_pct": round(box_range, 1),
        "position": round((latest_close - box_low) / (box_high - box_low) * 100, 1) if box_high > box_low else 50,
        "signal": {
            "signal": f"箱体整理（振幅{box_range:.1f}%），等待突破",
            "type": "盘整",
            "action": "观望",
            "priority": 2,
        },
    }


# ═══════════════════════════════════════════════════════════════
# 2. 三角形收敛检测
# ═══════════════════════════════════════════════════════════════

def _detect_triangle(df: pd.DataFrame) -> Optional[dict]:
    """
    检测三角形收敛形态。

    逻辑：
      1. 近30日内的高点序列和低点序列
      2. 高点呈下降趋势（上轨下倾）+ 低点呈上升趋势（下轨上倾）= 收敛三角形
      3. 价格接近顶点（振幅<5%），即将选择方向
    """
    if len(df) < 30:
        return None

    n = len(df)
    high = df["high"]
    low = df["low"]
    close = df["close"]

    win = slice(max(0, n - 30), n)

    # 提取局部高点和低点
    local_highs = []
    local_lows = []
    for i in range(max(0, n - 28), n - 1):
        if high.iloc[i] > high.iloc[i-1] and high.iloc[i] > high.iloc[i+1]:
            local_highs.append((i, float(high.iloc[i])))
        if low.iloc[i] < low.iloc[i-1] and low.iloc[i] < low.iloc[i+1]:
            local_lows.append((i, float(low.iloc[i])))

    if len(local_highs) < 3 or len(local_lows) < 3:
        return None

    # 上轨：线性回归高点
    h_indices = np.array([p[0] for p in local_highs[-5:]])
    h_values = np.array([p[1] for p in local_highs[-5:]])
    l_indices = np.array([p[0] for p in local_lows[-5:]])
    l_values = np.array([p[1] for p in local_lows[-5:]])

    try:
        h_slope, _ = np.polyfit(h_indices - h_indices[0], h_values, 1)
        l_slope, _ = np.polyfit(l_indices - l_indices[0], l_values, 1)
    except Exception:
        return None

    # 收敛条件：上轨下降 + 下轨上升
    if h_slope > -0.005 or l_slope < 0.005:
        return None  # 不是收敛三角

    # 振幅是否在收敛
    current_range = (high.iloc[-1] - low.iloc[-1]) / close.iloc[-1] * 100
    avg_range = (high.iloc[win] - low.iloc[win]).mean() / close.iloc[win].mean() * 100

    if current_range < avg_range * 0.6:
        convergence = True
        apex_near = current_range < 6
    else:
        convergence = False
        apex_near = False

    if not convergence:
        return None

    return {
        "pattern": "收敛三角形",
        "apex_near": apex_near,
        "current_range_pct": round(current_range, 1),
        "avg_range_pct": round(float(avg_range), 1),
        "h_slope": round(float(h_slope), 4),
        "l_slope": round(float(l_slope), 4),
        "signal": {
            "signal": f"三角形收敛（当前振幅{current_range:.1f}%）{'←顶点附近，即将变盘' if apex_near else ''}",
            "type": "形态孕育",
            "action": "密切关注，等待方向选择后跟进",
            "priority": 2 if apex_near else 3,
        },
    }


# ═══════════════════════════════════════════════════════════════
# 3. W底 / M头 检测
# ═══════════════════════════════════════════════════════════════

def _detect_double_pattern(df: pd.DataFrame) -> Optional[dict]:
    """
    检测 W底（双重底）或 M头（双重顶）。

    W底逻辑：
      1. 在60日低点区域附近形成两个低点
      2. 两个低点间隔10-30日
      3. 第二个低点高于第一个低点（或持平）
      4. 价格已上穿颈线（两个低点之间的高点）

    M头逻辑：
      1. 两个高点接近，间隔10-30日
      2. 第二个高点低于第一个高点
      3. 价格已下穿颈线
    """
    if len(df) < 40:
        return None

    n = len(df)
    high = df["high"]
    low = df["low"]
    close = df["close"]

    # ── 找近60日的主要转折点 ──
    lookback = min(60, n)
    start = n - lookback

    # 低位转折点
    pivots_low = []
    pivots_high = []
    for i in range(start + 3, n - 3):
        if low.iloc[i] < low.iloc[i-1] and low.iloc[i] < low.iloc[i-2] and \
           low.iloc[i] < low.iloc[i+1] and low.iloc[i] < low.iloc[i+2]:
            pivots_low.append((i, float(low.iloc[i])))
        if high.iloc[i] > high.iloc[i-1] and high.iloc[i] > high.iloc[i-2] and \
           high.iloc[i] > high.iloc[i+1] and high.iloc[i] > high.iloc[i+2]:
            pivots_high.append((i, float(high.iloc[i])))

    # ── W底检测 ──
    if len(pivots_low) >= 2:
        # 取最近的两个低点
        l1, l2 = pivots_low[-2], pivots_low[-1]
        gap = l2[0] - l1[0]

        if 5 <= gap <= 35:
            price_diff_pct = abs(l2[1] - l1[1]) / max(l1[1], l2[1]) * 100

            if price_diff_pct < 8:  # 两个低点价格接近
                # 找颈线（两个低点之间的最高点）
                neck = max(high.iloc[l1[0]:l2[0] + 1])

                if close.iloc[-1] > neck:  # 已上穿颈线
                    target = neck + (neck - min(l1[1], l2[1]))
                    return {
                        "pattern": "W底",
                        "left_bottom": round(l1[1], 2),
                        "right_bottom": round(l2[1], 2),
                        "neck": round(float(neck), 2),
                        "target": round(float(target), 2),
                        "confirmed": True,
                        "signal": {
                            "signal": "W底突破颈线（双重底确认）",
                            "type": "趋势反转",
                            "action": "加仓",
                            "priority": 1,
                        },
                    }
                elif close.iloc[-1] > min(l1[1], l2[1]) * 1.02:
                    return {
                        "pattern": "W底（未确认）",
                        "left_bottom": round(l1[1], 2),
                        "right_bottom": round(l2[1], 2),
                        "neck": round(float(neck), 2),
                        "confirmed": False,
                        "signal": {
                            "signal": "W底形态孕育中，关注颈线突破",
                            "type": "反转酝酿",
                            "action": "关注",
                            "priority": 2,
                        },
                    }

    # ── M头检测 ──
    if len(pivots_high) >= 2:
        h1, h2 = pivots_high[-2], pivots_high[-1]
        gap = h2[0] - h1[0]

        if 5 <= gap <= 35:
            price_diff_pct = abs(h2[1] - h1[1]) / max(h1[1], h2[1]) * 100

            if price_diff_pct < 8:
                neck = min(low.iloc[h1[0]:h2[0] + 1])

                if close.iloc[-1] < neck:
                    return {
                        "pattern": "M头",
                        "left_top": round(h1[1], 2),
                        "right_top": round(h2[1], 2),
                        "neck": round(float(neck), 2),
                        "confirmed": True,
                        "signal": {
                            "signal": "M头跌破颈线（双重顶确认）",
                            "type": "趋势反转",
                            "action": "减仓/离场",
                            "priority": 1,
                        },
                    }

    return None


# ═══════════════════════════════════════════════════════════════
# 4. 旗形/楔形整理检测
# ═══════════════════════════════════════════════════════════════

def _detect_flag(df: pd.DataFrame) -> Optional[dict]:
    """
    检测旗形（趋势中继整理形态）。

    逻辑：
      1. 前期有一段明显的趋势运动（旗杆）
      2. 随后窄幅整理（旗面），振幅缩小
      3. 旗面方向与原趋势相反或横盘
      4. 突破旗面时原趋势延续
    """
    if len(df) < 30:
        return None

    n = len(df)
    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]

    # 旗杆：前段（n-20 到 n-10）是否有明显趋势
    pole_start = max(0, n - 20)
    pole_end = max(0, n - 8)
    pole_close = close.iloc[pole_start:pole_end]

    if len(pole_close) < 8:
        return None

    pole_change = (pole_close.iloc[-1] - pole_close.iloc[0]) / pole_close.iloc[0] * 100

    if abs(pole_change) < 5:
        return None  # 没有明显的旗杆

    direction = "上涨旗形" if pole_change > 0 else "下跌旗形"

    # 旗面：近8日是否窄幅整理
    flag_start = pole_end
    flag_end = n
    flag_high = high.iloc[flag_start:flag_end].max()
    flag_low = low.iloc[flag_start:flag_end].min()
    flag_range = (flag_high - flag_low) / flag_low * 100 if flag_low > 0 else 100

    if flag_range > 8:
        return None  # 振幅太大不算旗面

    # 旗面成交量应递减
    flag_vol = volume.iloc[flag_start:flag_end]
    pole_vol = volume.iloc[pole_start:pole_end]
    vol_decline = flag_vol.mean() < pole_vol.mean() * 0.85

    # 判断突破
    if direction == "上涨旗形" and close.iloc[-1] > flag_high:
        if vol_decline or volume.iloc[-1] > flag_vol.mean() * 1.3:
            return {
                "pattern": "上涨旗形突破",
                "pole_change_pct": round(pole_change, 1),
                "flag_range_pct": round(flag_range, 1),
                "signal": {
                    "signal": f"上涨旗形突破（旗杆{pole_change:+.1f}%→整理{flag_range:.1f}%→再突破）",
                    "type": "趋势延续",
                    "action": "加仓",
                    "priority": 1,
                },
            }

    if direction == "下跌旗形" and close.iloc[-1] < flag_low:
        if vol_decline or volume.iloc[-1] > flag_vol.mean() * 1.3:
            return {
                "pattern": "下跌旗形突破",
                "pole_change_pct": round(pole_change, 1),
                "flag_range_pct": round(flag_range, 1),
                "signal": {
                    "signal": f"下跌旗形突破（旗杆{pole_change:+.1f}%→整理{flag_range:.1f}%→再下破）",
                    "type": "趋势延续",
                    "action": "减仓/做空",
                    "priority": 1,
                },
            }

    # 旗形整理中
    if flag_range < 6:
        return {
            "pattern": f"{direction}（整理中）",
            "pole_change_pct": round(pole_change, 1),
            "flag_range_pct": round(flag_range, 1),
            "signal": {
                "signal": f"{direction}整理中（旗杆{pole_change:+.1f}%），关注旗面突破方向",
                "type": "趋势延续",
                "action": "观察/持仓",
                "priority": 2,
            },
        }

    return None


def _pattern_verdict(signals: List[dict]) -> str:
    """形态综合判断"""
    if not signals:
        return "无明显技术形态"

    priority_1 = [s for s in signals if s["priority"] == 1]
    if priority_1:
        names = [s["signal"].split("（")[0] for s in priority_1]
        return f"强势形态信号: {'、'.join(names[:3])}"
    else:
        names = [s["signal"].split("（")[0] for s in signals]
        return f"关注形态: {'、'.join(names[:3])}"
