"""
持仓监控 & 实盘跟踪
===================
持仓快照 / 实时盈亏 / 权重漂移 / 再平衡提醒 / 调仓日志 / 预警
"""

import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

from ..data.cache import DataCache
from ..core.database import Database
from ..core.config import Config

logger = logging.getLogger("tg.portfolio.monitor")


# ═══════════════════════════════════════════════════════════════
# 持仓快照
# ═══════════════════════════════════════════════════════════════

def get_snapshot(portfolio_name: str) -> dict:
    """
    获取持仓快照 — 包含实时价格和盈亏。

    Returns:
        {
            "portfolio_name": str,
            "date": str,
            "total_value": float,
            "holdings": [...],
            "alerts": [...],
        }
    """
    db = Database.get_instance()
    cache = DataCache()

    holdings = db.fetchall(
        "SELECT * FROM holdings WHERE portfolio_name=? AND status='open'",
        (portfolio_name,)
    )

    if not holdings:
        return {"portfolio_name": portfolio_name, "error": "无持仓记录", "holdings": []}

    total_cost = 0
    total_current_value = 0
    snapshots = []
    alerts = []

    for h in holdings:
        code = h["code"]
        shares = h["shares"]
        entry_price = h["entry_price"]

        # 获取实时价格
        info = cache.get_stock_basic(code) or {}
        current_price = info.get("price", 0) or entry_price  # fallback

        cost = shares * entry_price
        current_value = shares * current_price
        pnl = current_value - cost
        pnl_pct = (pnl / cost * 100) if cost > 0 else 0

        total_cost += cost
        total_current_value += current_value

        snapshots.append({
            "code": code,
            "name": info.get("name", code),
            "shares": shares,
            "entry_price": entry_price,
            "current_price": current_price,
            "cost": round(cost, 2),
            "current_value": round(current_value, 2),
            "pnl": round(pnl, 2),
            "pnl_pct": round(pnl_pct, 2),
            "weight": 0,  # 下面计算
            "entry_date": h["entry_date"],
        })

    # 计算当前权重
    if total_current_value > 0:
        for s in snapshots:
            s["weight"] = round(s["current_value"] / total_current_value * 100, 1)

    # ── 预警检查 ──
    for s in snapshots:
        # 止损预警
        if s["pnl_pct"] < -Config.DEFAULT_STOP_LOSS * 100:
            alerts.append({
                "level": "danger",
                "code": s["code"],
                "name": s["name"],
                "message": f"触发止损线: {s['pnl_pct']:.1f}%（止损{-Config.DEFAULT_STOP_LOSS*100:.0f}%）",
            })
        elif s["pnl_pct"] < -5:
            alerts.append({
                "level": "warning",
                "code": s["code"],
                "name": s["name"],
                "message": f"浮亏接近止损: {s['pnl_pct']:.1f}%",
            })

        # 权重漂移预警
        if s["weight"] > Config.MAX_SINGLE_WEIGHT * 100 * 1.3:
            alerts.append({
                "level": "warning",
                "code": s["code"],
                "name": s["name"],
                "message": f"权重漂移过大: {s['weight']:.1f}%（上限{Config.MAX_SINGLE_WEIGHT*100:.0f}%）",
            })

    total_pnl = total_current_value - total_cost
    total_pnl_pct = (total_pnl / total_cost * 100) if total_cost > 0 else 0

    return {
        "portfolio_name": portfolio_name,
        "date": datetime.now().strftime("%Y-%m-%d"),
        "total_cost": round(total_cost, 2),
        "total_current_value": round(total_current_value, 2),
        "total_pnl": round(total_pnl, 2),
        "total_pnl_pct": round(total_pnl_pct, 2),
        "n_holdings": len(snapshots),
        "holdings": snapshots,
        "alerts": alerts,
    }


# ═══════════════════════════════════════════════════════════════
# 再平衡检查
# ═══════════════════════════════════════════════════════════════

def check_rebalance(
    portfolio_name: str,
    target_weights: Dict[str, float],
    drift_threshold: float = 0.05,
) -> dict:
    """
    检查是否需要再平衡。

    Args:
        portfolio_name: 组合名称
        target_weights: 目标权重 {code: weight}
        drift_threshold: 漂移阈值（超过此值建议再平衡）

    Returns:
        {"needs_rebalance": bool, "drifts": [...], "recommendation": str}
    """
    snapshot = get_snapshot(portfolio_name)
    if "error" in snapshot:
        return {"needs_rebalance": False, "error": snapshot["error"]}

    current_weights = {h["code"]: h["weight"] / 100 for h in snapshot["holdings"]}

    drifts = []
    max_drift = 0

    for code, target_w in target_weights.items():
        current_w = current_weights.get(code, 0)
        drift = abs(current_w - target_w)
        if drift > drift_threshold:
            drifts.append({
                "code": code,
                "name": _get_name(code),
                "target_weight": round(target_w * 100, 1),
                "current_weight": round(current_w * 100, 1),
                "drift": round(drift * 100, 1),
                "action": "减仓" if current_w > target_w else "加仓",
            })
        max_drift = max(max_drift, drift)

    needs_rebalance = len(drifts) > 0

    if needs_rebalance:
        recommendation = f"建议再平衡: {len(drifts)} 只标的目标/实盘权重偏差>{drift_threshold*100:.0f}%"
    else:
        recommendation = "无需再平衡，权重偏差在阈值内"

    return {
        "needs_rebalance": needs_rebalance,
        "max_drift_pct": round(max_drift * 100, 1),
        "drift_threshold_pct": round(drift_threshold * 100, 1),
        "drifts": drifts,
        "recommendation": recommendation,
    }


# ═══════════════════════════════════════════════════════════════
# 持仓操作
# ═══════════════════════════════════════════════════════════════

def record_holding(
    portfolio_name: str,
    code: str,
    name: str,
    weight: float,
    shares: int,
    entry_price: float,
    entry_date: str = None,
):
    """记录一笔持仓"""
    db = Database.get_instance()
    if entry_date is None:
        entry_date = datetime.now().strftime("%Y-%m-%d")

    db.execute(
        """INSERT INTO holdings (portfolio_name, code, name, weight, shares, entry_price, entry_date, status)
           VALUES (?, ?, ?, ?, ?, ?, ?, 'open')""",
        (portfolio_name, code, name, weight, shares, entry_price, entry_date)
    )
    logger.info(f"持仓记录: {portfolio_name} + {code}({name}) {shares}股")


def close_holding(
    portfolio_name: str,
    code: str,
    exit_price: float,
    exit_date: str = None,
    reason: str = "",
):
    """平仓"""
    db = Database.get_instance()
    if exit_date is None:
        exit_date = datetime.now().strftime("%Y-%m-%d")

    db.execute(
        """UPDATE holdings SET exit_price=?, exit_date=?, status='closed'
           WHERE portfolio_name=? AND code=? AND status='open'""",
        (exit_price, exit_date, portfolio_name, code)
    )

    # 写交易日志
    holding = db.fetchone(
        "SELECT * FROM holdings WHERE portfolio_name=? AND code=? ORDER BY id DESC LIMIT 1",
        (portfolio_name, code)
    )
    if holding:
        pnl = (exit_price - holding["entry_price"]) * holding["shares"]
        log_trade(portfolio_name, code, "sell", exit_price, holding["shares"],
                  pnl, reason)


def log_trade(
    portfolio_name: str,
    code: str,
    action: str,
    price: float,
    shares: int,
    pnl: float = 0,
    reason: str = "",
):
    """记录交易日志"""
    db = Database.get_instance()
    trade_date = datetime.now().strftime("%Y-%m-%d")
    amount = price * shares
    commission = amount * 0.00025  # 简化佣金计算

    db.execute(
        """INSERT INTO trade_log (portfolio_name, code, action, price, shares, amount, commission, reason, trade_date)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (portfolio_name, code, action, price, shares, amount, commission, reason, trade_date)
    )


def get_trade_history(portfolio_name: str, limit: int = 50) -> List[dict]:
    """获取交易历史"""
    db = Database.get_instance()
    rows = db.fetchall(
        "SELECT * FROM trade_log WHERE portfolio_name=? ORDER BY trade_date DESC LIMIT ?",
        (portfolio_name, limit)
    )
    return [dict(r) for r in reversed(rows)]


# ═══════════════════════════════════════════════════════════════
# 组合快照存储
# ═══════════════════════════════════════════════════════════════

def save_portfolio_snapshot(portfolio: dict):
    """
    将 build_portfolio 的结果保存到 holdings 表。
    一键从构建结果转持仓记录。
    """
    portfolio_name = portfolio.get("name", "unnamed")
    for h in portfolio.get("holdings", []):
        if h.get("weight", 0) <= 0:
            continue
        # 每10万模拟资金计算股数
        shares = int(h["weight"] * 100000 / max(h.get("price", 1), 0.01) / 100) * 100
        if shares > 0:
            record_holding(
                portfolio_name=portfolio_name,
                code=h["code"],
                name=h.get("name", h["code"]),
                weight=h["weight"],
                shares=shares,
                entry_price=h.get("price", 0),
            )

    logger.info(f"组合 {portfolio_name} 快照已保存: {portfolio.get('stats', {}).get('n_stocks', 0)} 只标的")


def list_portfolios() -> List[dict]:
    """列出所有组合"""
    db = Database.get_instance()
    rows = db.fetchall(
        """SELECT portfolio_name, COUNT(*) as n, SUM(entry_price*shares) as cost,
                  MAX(entry_date) as last_date
           FROM holdings WHERE status='open'
           GROUP BY portfolio_name"""
    )
    return [dict(r) for r in rows]


def _get_name(code: str) -> str:
    cache = DataCache()
    info = cache.get_stock_basic(code) or {}
    return info.get("name", code)
