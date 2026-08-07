"""
VaR / CVaR 风险度量
====================
三种计算方法 + 尾部风险度量 + 回测验证

方法：
  - Historical VaR: 直接用历史收益率的百分位
  - Parametric VaR: 假设正态分布，μ + σ × z_α
  - Monte Carlo VaR: 基于协方差矩阵模拟
"""

import logging
from typing import Dict, List, Optional, Tuple
import numpy as np
import pandas as pd

logger = logging.getLogger("tg.risk.var")


# ═══════════════════════════════════════════════════════════════
# VaR 计算
# ═══════════════════════════════════════════════════════════════

def historical_var(
    returns: pd.Series,
    confidence: float = 0.95,
    horizon: int = 1,
) -> float:
    """
    历史模拟法 VaR。

    在给定置信度下，基于历史收益率分布，估计最大损失。

    Args:
        returns: 日收益率序列
        confidence: 置信水平（0.95/0.99）
        horizon: 持有期（天数）

    Returns:
        VaR 值（正数表示损失）
    """
    if len(returns) < 20:
        return 0.0

    alpha = 1 - confidence
    var_daily = -np.percentile(returns.dropna(), alpha * 100)
    var_horizon = var_daily * np.sqrt(horizon)

    return round(float(var_horizon), 6)


def parametric_var(
    returns: pd.Series,
    confidence: float = 0.95,
    horizon: int = 1,
) -> Tuple[float, float, float]:
    """
    参数法 VaR（假设正态分布）。

    Returns:
        (VaR, mean_return, std_return)
    """
    if len(returns) < 20:
        return 0.0, 0.0, 0.0

    from scipy import stats

    mu = returns.mean()
    sigma = returns.std()

    z_score = stats.norm.ppf(1 - confidence)

    var_daily = -(mu + z_score * sigma)
    var_horizon = var_daily * np.sqrt(horizon)

    return round(float(var_horizon), 6), round(float(mu), 6), round(float(sigma), 6)


def monte_carlo_var(
    returns: pd.DataFrame,
    weights: pd.Series = None,
    confidence: float = 0.95,
    horizon: int = 1,
    n_simulations: int = 10000,
) -> float:
    """
    蒙特卡洛模拟 VaR — 基于历史协方差矩阵。

    Args:
        returns: 多资产日收益率 DataFrame
        weights: 组合权重（None = 等权）
        confidence: 置信水平
        horizon: 持有期
        n_simulations: 模拟次数

    Returns:
        组合 VaR
    """
    if returns.empty or len(returns) < 20:
        return 0.0

    # 兼容 Series（单资产）和 DataFrame（多资产）
    if isinstance(returns, pd.Series):
        returns = returns.to_frame("asset")

    assets = returns.columns
    n = len(assets)

    if weights is None:
        weights = pd.Series(1.0 / n, index=assets)
    else:
        weights = weights.reindex(assets, fill_value=0)
        weights = weights / weights.sum()

    mu = returns.mean().values
    cov = returns.cov().values

    # Cholesky 分解
    try:
        L = np.linalg.cholesky(cov)
    except np.linalg.LinAlgError:
        L = np.linalg.cholesky(cov + np.eye(n) * 1e-6)

    # 模拟
    np.random.seed(12345)
    sim_returns = []
    for _ in range(n_simulations):
        z = np.random.randn(n)
        r = mu + L @ z  # 日收益率
        sim_returns.append(weights.values @ r)

    sim_returns = np.array(sim_returns)
    alpha = 1 - confidence
    var_daily = -np.percentile(sim_returns, alpha * 100)
    var_horizon = var_daily * np.sqrt(horizon)

    return round(float(var_horizon), 6)


def calc_cvar(
    returns: pd.Series,
    confidence: float = 0.95,
) -> float:
    """
    CVaR（条件风险价值）— 超过 VaR 的平均损失。

    即：在最坏的 (1-confidence)% 情况下，平均会亏多少。
    """
    if len(returns) < 20:
        return 0.0

    alpha = 1 - confidence
    var_value = -np.percentile(returns.dropna(), alpha * 100)

    # 取所有 < -var_value 的收益率的平均值
    tail_returns = returns[returns < -var_value]
    if len(tail_returns) == 0:
        return float(var_value)

    cvar = -tail_returns.mean()
    return round(float(cvar), 6)


def calc_var(
    returns: pd.Series,
    weights: pd.Series = None,
    method: str = "historical",
    confidence: float = 0.95,
    horizon: int = 1,
    n_simulations: int = 10000,
) -> dict:
    """
    统一 VaR 计算入口 — 单资产或组合。

    Returns:
        {
            "var": float,          # VaR（正数 = 损失）
            "cvar": float,         # CVaR
            "confidence": float,
            "horizon_days": int,
            "method": str,
            "var_pct": float,      # VaR 占资产比例
            "detail": {...},
        }
    """
    if method == "historical":
        var_val = historical_var(returns, confidence, horizon)
        cvar_val = calc_cvar(returns, confidence)
        detail = {"method": "历史模拟法"}
    elif method == "parametric":
        var_val, mu, sigma = parametric_var(returns, confidence, horizon)
        cvar_val = calc_cvar(returns, confidence)
        detail = {"method": "参数法(正态假设)", "mu": mu, "sigma": sigma}
    elif method == "monte_carlo":
        var_val = monte_carlo_var(returns, weights, confidence, horizon, n_simulations)
        cvar_val = calc_cvar(returns, confidence)
        detail = {"method": "蒙特卡洛", "n_simulations": n_simulations}
    else:
        var_val = historical_var(returns, confidence, horizon)
        cvar_val = calc_cvar(returns, confidence)
        detail = {"method": method}

    # 计算 VaR 占当前价值的比例
    var_pct = var_val * 100  # VaR 本身是收益率形式

    return {
        "var": var_val,
        "cvar": cvar_val,
        "confidence": confidence,
        "horizon_days": horizon,
        "method": method,
        "var_pct": round(var_pct, 4),
        "detail": detail,
    }


# ═══════════════════════════════════════════════════════════════
# 组合 VaR 工具
# ═══════════════════════════════════════════════════════════════

def portfolio_var_report(
    returns: pd.DataFrame,
    weights: pd.Series,
    confidence: float = 0.95,
) -> dict:
    """
    组合层面的完整 VaR 报告。

    Returns:
        包含各方法 VaR/CVaR + 边际 VaR + 成分 VaR
    """
    if returns.empty:
        return {"error": "无收益率数据"}

    # 组合收益率
    aligned_weights = weights.reindex(returns.columns, fill_value=0)
    aligned_weights = aligned_weights / aligned_weights.sum()
    port_returns = returns @ aligned_weights

    # 多种方法计算
    hist = calc_var(port_returns, method="historical", confidence=confidence)
    param = calc_var(port_returns, method="parametric", confidence=confidence)

    # 边际 VaR（每资产对组合 VaR 的边际贡献）
    sigma_p = port_returns.std()
    if sigma_p > 0:
        cov_with_port = returns.apply(lambda x: x.cov(port_returns))
        marginal_var = cov_with_port / sigma_p  # ∂VaR/∂w
    else:
        marginal_var = pd.Series(0, index=returns.columns)

    # 成分 VaR = w_i × MVaR_i
    component_var = aligned_weights * marginal_var

    return {
        "historical_var": hist["var"],
        "parametric_var": param["var"],
        "cvar": hist["cvar"],
        "confidence": confidence,
        "marginal_var": {k: round(v, 6) for k, v in marginal_var.to_dict().items()},
        "component_var": {k: round(v, 6) for k, v in component_var.to_dict().items()
                          if abs(v) > 0.0001},
    }


# ═══════════════════════════════════════════════════════════════
# VaR 回测 (Kupiec 检验)
# ═══════════════════════════════════════════════════════════════

def var_backtest(
    returns: pd.Series,
    var_values: pd.Series,
    confidence: float = 0.95,
) -> dict:
    """
    VaR 回测 — 检验 VaR 预测的准确性。

    统计实际损失超过 VaR 的天数（突破天数），
    理想情况：突破比例 = (1 - confidence)。

    Kupiec 检验：失败率是否显著偏离预期。
    """
    if len(returns) < 50:
        return {"error": "数据不足（需要 >50 天）"}

    # 比对：实际收益率 < -VaR 为突破
    breaches = (returns < -var_values).sum()
    total = len(returns)
    breach_rate = breaches / total
    expected_rate = 1 - confidence

    # Kupiec LR 统计量
    if breach_rate > 0 and breach_rate < 1:
        lr = -2 * (
            (total - breaches) * np.log((1 - expected_rate) / (1 - breach_rate)) +
            breaches * np.log(expected_rate / breach_rate)
        )
    else:
        lr = float("inf")

    # 判断（5% 显著性水平，卡方 1df 临界值 3.841）
    is_accurate = abs(lr) < 3.841

    return {
        "total_days": total,
        "breaches": int(breaches),
        "breach_rate_pct": round(breach_rate * 100, 2),
        "expected_rate_pct": round(expected_rate * 100, 2),
        "kupiec_lr": round(float(lr), 2),
        "is_accurate": is_accurate,
        "verdict": "VaR 模型合理" if is_accurate else "VaR 模型可能不准确（需调整）",
    }
