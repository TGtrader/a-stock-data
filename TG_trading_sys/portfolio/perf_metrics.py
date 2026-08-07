"""
绩效指标体系
============
年化收益 / 夏普比率 / 索提诺比率 / 卡玛比率 / 最大回撤 /
胜率 / 盈亏比 / 信息比率 / 月度收益热力图 / 滚动指标
"""

import logging
from typing import Dict, List, Optional
from datetime import datetime
import pandas as pd
import numpy as np

logger = logging.getLogger("tg.portfolio.metrics")


def compute_metrics(
    equity_curve: pd.Series,
    benchmark_equity: pd.Series = None,
    risk_free_rate: float = 0.028,
    trades: List[dict] = None,
) -> dict:
    """
    计算完整的绩效指标。

    Args:
        equity_curve: 组合权益曲线 (index=date, value=equity)
        benchmark_equity: 基准权益曲线
        risk_free_rate: 无风险利率（年化）
        trades: 交易记录列表

    Returns:
        完整绩效指标 dict
    """
    if equity_curve is None or len(equity_curve) < 2:
        return _empty_metrics()

    # 日收益率
    returns = equity_curve.pct_change().dropna()
    if len(returns) < 5:
        return _empty_metrics()

    n_days = len(returns)
    years = n_days / 252

    # ── 收益指标 ──
    total_return = (equity_curve.iloc[-1] / equity_curve.iloc[0]) - 1
    annual_return = (1 + total_return) ** (1 / max(years, 0.1)) - 1
    daily_mean = returns.mean()
    daily_std = returns.std()
    annual_vol = daily_std * np.sqrt(252)

    # ── 风险指标 ──
    max_drawdown, max_dd_start, max_dd_end = _calc_max_drawdown(equity_curve)
    max_dd_duration = (max_dd_end - max_dd_start).days if max_dd_start and max_dd_end else 0

    # 下行标准差
    downside_returns = returns[returns < 0]
    downside_std = downside_returns.std() * np.sqrt(252) if len(downside_returns) > 0 else 0

    # ── 风险调整收益 ──
    sharpe = (annual_return - risk_free_rate) / annual_vol if annual_vol > 0 else 0
    sortino = (annual_return - risk_free_rate) / downside_std if downside_std > 0 else 0
    calmar = annual_return / abs(max_drawdown) if max_drawdown != 0 else 0

    # ── 超额收益（vs基准）──
    excess_return = None
    information_ratio = None
    tracking_error = None
    beta = None
    alpha = None

    if benchmark_equity is not None and len(benchmark_equity) > 2:
        bench_returns = benchmark_equity.pct_change().dropna()
        # 对齐
        aligned = pd.concat([returns, bench_returns], axis=1).dropna()
        if len(aligned) > 20:
            aligned.columns = ["portfolio", "benchmark"]
            excess_ret = aligned["portfolio"] - aligned["benchmark"]
            excess_return = float(excess_ret.mean() * 252)
            tracking_error = float(excess_ret.std() * np.sqrt(252))
            information_ratio = excess_return / tracking_error if tracking_error > 0 else 0

            # Beta & Alpha
            cov = aligned.cov()
            bench_var = aligned["benchmark"].var()
            if bench_var > 0:
                beta = float(cov.loc["portfolio", "benchmark"] / bench_var)
                alpha = float(annual_return - risk_free_rate - beta * (
                    (1 + aligned["benchmark"].mean()) ** 252 - 1 - risk_free_rate
                ))
            else:
                beta = 1.0
                alpha = 0.0

    # ── 交易统计 ──
    if trades:
        trade_stats = _calc_trade_stats(trades, equity_curve)
    else:
        trade_stats = {}

    # ── 月度收益 ──
    monthly_returns = _calc_monthly_returns(returns)

    return {
        "total_return_pct": round(total_return * 100, 2),
        "annual_return_pct": round(annual_return * 100, 2),
        "annual_volatility_pct": round(annual_vol * 100, 2),
        "sharpe_ratio": round(sharpe, 2),
        "sortino_ratio": round(sortino, 2),
        "calmar_ratio": round(calmar, 2),
        "max_drawdown_pct": round(max_drawdown * 100, 2),
        "max_dd_duration_days": max_dd_duration,
        "excess_return_pct": round(excess_return * 100, 2) if excess_return is not None else None,
        "information_ratio": round(information_ratio, 2) if information_ratio is not None else None,
        "tracking_error_pct": round(tracking_error * 100, 2) if tracking_error is not None else None,
        "beta": round(beta, 2) if beta is not None else None,
        "alpha_pct": round(alpha * 100, 2) if alpha is not None else None,
        "risk_free_rate_pct": round(risk_free_rate * 100, 2),
        "n_trading_days": n_days,
        "years": round(years, 2),
        **trade_stats,
        "monthly_returns": monthly_returns,
    }


def _calc_max_drawdown(equity: pd.Series) -> tuple:
    """计算最大回撤"""
    cummax = equity.cummax()
    drawdown = (equity - cummax) / cummax
    max_dd = drawdown.min()
    end_idx = drawdown.idxmin()
    start_idx = cummax.loc[:end_idx].idxmax() if pd.notna(end_idx) else None
    return float(max_dd), start_idx, end_idx


def _calc_trade_stats(trades: List[dict], equity: pd.Series) -> dict:
    """从交易记录计算交易统计"""
    if not trades:
        return {"win_rate": None, "profit_factor": None, "total_trades": 0}

    # 简化：如果有 pnl 字段
    pnls = [t.get("pnl", 0) for t in trades if "pnl" in t]
    if pnls:
        wins = sum(1 for p in pnls if p > 0)
        total_trades = len(pnls)
        win_rate = wins / total_trades if total_trades > 0 else 0

        total_profit = sum(p for p in pnls if p > 0)
        total_loss = abs(sum(p for p in pnls if p < 0))
        profit_factor = total_profit / total_loss if total_loss > 0 else float("inf")

        avg_win = total_profit / wins if wins > 0 else 0
        avg_loss = total_loss / (total_trades - wins) if total_trades > wins else 0

        return {
            "total_trades": total_trades,
            "win_rate_pct": round(win_rate * 100, 1),
            "profit_factor": round(profit_factor, 2),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
        }
    else:
        # 没有详细的 pnl，只返回交易次数
        return {"total_trades": len(trades)}


def _calc_monthly_returns(returns: pd.Series) -> dict:
    """计算月度收益（用于热力图）"""
    if len(returns) < 20:
        return {}

    monthly = returns.resample("ME").apply(lambda x: (1 + x).prod() - 1)

    result = {}
    for idx, val in monthly.items():
        key = idx.strftime("%Y-%m")
        result[key] = round(float(val) * 100, 2)

    return result


def _empty_metrics() -> dict:
    return {
        "total_return_pct": 0, "annual_return_pct": 0,
        "annual_volatility_pct": 0, "sharpe_ratio": 0,
        "sortino_ratio": 0, "calmar_ratio": 0,
        "max_drawdown_pct": 0, "max_dd_duration_days": 0,
        "n_trading_days": 0, "years": 0,
    }


def summary_table(metrics: dict) -> str:
    """生成绩效指标摘要表格文本"""
    lines = [
        f"总收益:     {metrics.get('total_return_pct', 0):.2f}%",
        f"年化收益:   {metrics.get('annual_return_pct', 0):.2f}%",
        f"年化波动:   {metrics.get('annual_volatility_pct', 0):.2f}%",
        f"夏普比率:   {metrics.get('sharpe_ratio', 0):.2f}",
        f"索提诺:     {metrics.get('sortino_ratio', 0):.2f}",
        f"卡玛比率:   {metrics.get('calmar_ratio', 0):.2f}",
        f"最大回撤:   {metrics.get('max_drawdown_pct', 0):.2f}%",
        f"回撤持续:   {metrics.get('max_dd_duration_days', 0)}天",
    ]

    if metrics.get("beta") is not None:
        lines.append(f"Beta:       {metrics.get('beta', 0):.2f}")
    if metrics.get("alpha_pct") is not None:
        lines.append(f"Alpha:      {metrics.get('alpha_pct', 0):.2f}%")
    if metrics.get("information_ratio") is not None:
        lines.append(f"信息比率:   {metrics.get('information_ratio', 0):.2f}")
    if metrics.get("win_rate_pct") is not None:
        lines.append(f"胜率:       {metrics.get('win_rate_pct', 0):.1f}%")

    return "\n".join(lines)
