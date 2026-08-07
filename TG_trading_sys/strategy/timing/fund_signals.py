"""
资金面信号检测
==============
基于资金流数据的技术信号：
  - 北向资金（沪股通/深股通）连续流入/流出
  - 融资融券余额异动
  - 大宗交易溢价/折价
  - 主力资金连续净流入（复用 VPA moneyflow 数据）
  - 股东户数变化（筹码集中度）
"""

import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

from ...data.cache import DataCache

logger = logging.getLogger("tg.strategy.fund")


def analyze_fund_signals(code: str, cache: DataCache = None) -> dict:
    """
    资金面综合信号分析。

    Returns:
        {
            "northbound": dict|None,       # 北向资金信号
            "margin_alert": dict|None,     # 融资融券异动
            "block_trade": dict|None,      # 大宗交易信号
            "main_force_flow": dict|None,  # 主力资金流信号
            "signals": [...],
            "verdict": str,
        }
    """
    if cache is None:
        cache = DataCache()

    result = {
        "northbound": _check_northbound(cache, code),
        "margin_alert": _check_margin(cache, code),
        "block_trade": _check_block_trade(cache, code),
        "main_force_flow": _check_main_force(cache, code),
    }

    signals = []
    for key, data in result.items():
        if data and data.get("signals"):
            signals.extend(data["signals"])

    # 综合判断
    bull_signals = [s for s in signals if s["action"] in ("加仓", "关注流入")]
    bear_signals = [s for s in signals if s["action"] in ("减仓", "关注流出")]

    if len(bull_signals) >= 2:
        verdict = f"资金面偏多: {len(bull_signals)}个流入信号"
    elif len(bear_signals) >= 2:
        verdict = f"资金面偏空: {len(bear_signals)}个流出信号"
    elif bull_signals:
        verdict = "资金面略偏多"
    elif bear_signals:
        verdict = "资金面略偏空"
    else:
        verdict = "资金面无明显异动"

    result["signals"] = signals
    result["verdict"] = verdict
    return result


def _check_northbound(cache: DataCache, code: str) -> Optional[dict]:
    """
    北向资金信号检测 — 简化版（基于缓存数据）。

    北向资金属性：港资通过沪/深港通买入A股，被视为"聪明钱"。
    信号逻辑：连续3日净流入且加速 → 积极信号。
    """
    # 尝试从 moneyflow 表检查是否有 northbound 相关数据
    mf_df = _get_moneyflow_df(cache, code)
    if mf_df is None or mf_df.empty:
        return None

    # 检查是否包含北向相关字段
    nb_col = None
    for col in ["northbound_net", "hgt_net", "sgt_net", "ggt_net"]:
        if col in mf_df.columns:
            nb_col = col
            break

    if nb_col is None:
        return None  # 当前数据源不含北向字段（需要同花顺北向接口）

    # 检测连续流入
    recent = mf_df[nb_col].tail(10).values
    if len(recent) < 5:
        return None

    # 最近5日
    last5 = recent[-5:]
    consecutive_inflow = 0
    consecutive_outflow = 0
    for v in reversed(last5):
        if v > 0:
            if consecutive_outflow > 0:
                break
            consecutive_inflow += 1
            consecutive_outflow = 0
        elif v < 0:
            consecutive_outflow += 1
            consecutive_inflow = 0

    if consecutive_inflow >= 3:
        # 加速流入？
        if len(last5) >= 4:
            accel = last5[-1] - last5[-2] if last5[-2] > 0 else 0
            accel_str = "（加速）" if accel > 0 and last5[-1] > last5[-2] * 1.3 else ""
        else:
            accel_str = ""

        return {
            "direction": "北向流入",
            "consecutive_days": consecutive_inflow,
            "signals": [{
                "signal": f"北向资金连续{consecutive_inflow}日净流入{accel_str}",
                "type": "资金面",
                "action": "加仓",
                "priority": 2,
            }],
        }

    if consecutive_outflow >= 3:
        return {
            "direction": "北向流出",
            "consecutive_days": consecutive_outflow,
            "signals": [{
                "signal": f"北向资金连续{consecutive_outflow}日净流出",
                "type": "资金面",
                "action": "减仓",
                "priority": 2,
            }],
        }

    return None


def _check_margin(cache: DataCache, code: str) -> Optional[dict]:
    """
    融资融券异动检测。

    信号逻辑：
      - 融资余额5日增长 >10%：做多资金涌入，偏多
      - 融资余额5日减少 >10%：资金撤离，偏空
      - 融券余额大增：做空力量增强
    """
    mf_df = _get_moneyflow_df(cache, code)
    if mf_df is None or mf_df.empty:
        return None

    # 融资余额字段
    margin_cols = ["rzye", "margin_balance", "fin_balance"]
    margin_col = None
    for col in margin_cols:
        if col in mf_df.columns:
            margin_col = col
            break

    if margin_col is None:
        return None

    recent = mf_df[margin_col].tail(5).dropna()
    if len(recent) < 3:
        return None

    first = recent.iloc[0]
    last = recent.iloc[-1]
    if first <= 0:
        return None

    change_pct = (last - first) / first * 100

    if change_pct > 10:
        return {
            "type": "融资暴增",
            "change_pct": round(change_pct, 1),
            "signals": [{
                "signal": f"融资余额5日增{change_pct:.1f}%，做多资金涌入",
                "type": "资金面",
                "action": "加仓",
                "priority": 2,
            }],
        }
    elif change_pct > 5:
        return {
            "type": "融资增加",
            "change_pct": round(change_pct, 1),
            "signals": [{
                "signal": f"融资余额5日增{change_pct:.1f}%",
                "type": "资金面",
                "action": "关注流入",
                "priority": 3,
            }],
        }
    elif change_pct < -10:
        return {
            "type": "融资骤降",
            "change_pct": round(change_pct, 1),
            "signals": [{
                "signal": f"融资余额5日降{abs(change_pct):.1f}%，杠杆资金撤离",
                "type": "资金面",
                "action": "减仓",
                "priority": 2,
            }],
        }

    return None


def _check_block_trade(cache: DataCache, code: str) -> Optional[dict]:
    """
    大宗交易信号检测。

    信号逻辑：
      - 大宗成交价 > 当日收盘价 5%+ → 溢价交易，买方积极
      - 大宗成交价 < 当日收盘价 -5% → 折价交易，需关注减持
      - 连续多日出现大宗交易 → 筹码在转移
    """
    # 大宗交易数据需要东财 datacenter 接口，此处返回占位
    # Phase 5 数据层完善时补充
    return None


def _check_main_force(cache: DataCache, code: str) -> Optional[dict]:
    """
    主力资金流信号 — 基于 Tushare moneyflow 数据。

    复用 VPA 中的资金流分析逻辑。
    """
    mf_df = _get_moneyflow_df(cache, code)
    if mf_df is None or mf_df.empty:
        return None

    # 主力净流入字段
    mf_col = None
    for col in ["net_mf_amount", "net_amount", "buy_lg_amount", "buy_elg_amount"]:
        if col in mf_df.columns:
            mf_col = col
            break

    if mf_col is None:
        return None

    # 如果用的是买入字段，需要减去卖出
    if "buy" in mf_col:
        sell_col = mf_col.replace("buy", "sell")
        if sell_col in mf_df.columns:
            net = mf_df[mf_col].fillna(0) - mf_df[sell_col].fillna(0)
        else:
            net = mf_df[mf_col].fillna(0)
    else:
        net = mf_df[mf_col].fillna(0)

    if len(net) < 5:
        return None

    # 连续流入检测
    last5 = net.tail(5).values
    consecutive_in = 0
    for v in reversed(last5):
        if v > 0:
            consecutive_in += 1
        else:
            break

    consecutive_out = 0
    for v in reversed(last5):
        if v < 0:
            consecutive_out += 1
        else:
            break

    signals = []

    if consecutive_in >= 5:
        total_in = net.tail(5).sum()
        signals.append({
            "signal": f"主力资金连续{consecutive_in}日净流入（合计{total_in/10000:.1f}亿）",
            "type": "资金面",
            "action": "加仓",
            "priority": 1,
        })
    elif consecutive_in >= 3:
        signals.append({
            "signal": f"主力资金连续{consecutive_in}日净流入",
            "type": "资金面",
            "action": "关注流入",
            "priority": 2,
        })

    if consecutive_out >= 5:
        signals.append({
            "signal": f"主力资金连续{consecutive_out}日净流出",
            "type": "资金面",
            "action": "减仓",
            "priority": 1,
        })
    elif consecutive_out >= 3:
        signals.append({
            "signal": f"主力资金连续{consecutive_out}日净流出",
            "type": "资金面",
            "action": "关注流出",
            "priority": 2,
        })

    if not signals:
        return None

    # 主力vs散户背离
    sm_col = "buy_sm_amount"
    if sm_col in mf_df.columns and "sell_sm_amount" in mf_df.columns:
        main_5d = net.tail(5).sum()
        retail_5d = (mf_df[sm_col].tail(5).fillna(0) -
                     mf_df["sell_sm_amount"].tail(5).fillna(0)).sum()
        if main_5d > 0 and retail_5d < 0:
            signals.append({
                "signal": "主力吸筹 vs 散户出货（背离看涨）",
                "type": "资金面",
                "action": "加仓",
                "priority": 1,
            })
        elif main_5d < 0 and retail_5d > 0:
            signals.append({
                "signal": "主力出货 vs 散户接盘（背离看跌）",
                "type": "资金面",
                "action": "减仓/离场",
                "priority": 1,
            })

    return {"signals": signals, "consecutive_in": consecutive_in, "consecutive_out": consecutive_out}


def _get_moneyflow_df(cache: DataCache, code: str) -> Optional[pd.DataFrame]:
    """从缓存或数据源获取资金流DataFrame"""
    try:
        rows = cache.db.fetchall(
            "SELECT * FROM moneyflow WHERE code=? ORDER BY date ASC LIMIT 60",
            (code,)
        )
        if rows:
            df = pd.DataFrame([dict(r) for r in rows])
            df["date"] = pd.to_datetime(df["date"])
            return df.set_index("date").sort_index()
    except Exception:
        pass
    return None
