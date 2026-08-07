"""
绩效归因分析
============
Brinson 归因（配置贡献/选股贡献/交互效应）+ 因子归因
"""

import logging
from typing import Dict, List, Optional, Tuple
import numpy as np
import pandas as pd

logger = logging.getLogger("tg.risk.attribution")


# ═══════════════════════════════════════════════════════════════
# Brinson 归因
# ═══════════════════════════════════════════════════════════════

def brinson_attribution(
    portfolio_weights: Dict[str, Dict[str, float]],
    benchmark_weights: Dict[str, float],
    portfolio_returns: Dict[str, float],
    benchmark_returns: Dict[str, float],
    sector_mapping: Dict[str, str] = None,
) -> dict:
    """
    Brinson 绩效归因模型。

    将超额收益分解为：
      - 配置贡献 (Allocation): 超配/低配某行业带来的收益
      - 选股贡献 (Selection):  行业内部选股带来的收益
      - 交互效应 (Interaction): 配置×选股交叉项

    Args:
        portfolio_weights: 组合权重 {stock_code: weight}
        benchmark_weights: 基准权重 {stock_code: weight}
        portfolio_returns: 组合各股收益 {stock_code: return}
        benchmark_returns: 基准各股收益 {stock_code: return}
        sector_mapping: 行业归属 {stock_code: sector_name}

    Returns:
        Brinson 归因分解结果
    """
    if sector_mapping is None:
        sector_mapping = {c: "全部" for c in portfolio_weights}

    # ── 按行业聚合 ──
    sectors = set(sector_mapping.values())
    sector_data = {}

    for sector in sectors:
        sec_codes = [c for c, s in sector_mapping.items() if s == sector]

        # 组合在行业中的权重和收益
        pf_w = sum(portfolio_weights.get(c, 0) for c in sec_codes)
        pf_codes = [c for c in sec_codes if portfolio_weights.get(c, 0) > 0]
        if pf_codes:
            pf_r = sum(portfolio_weights.get(c, 0) * portfolio_returns.get(c, 0)
                       for c in pf_codes) / max(pf_w, 0.0001)
        else:
            pf_r = 0

        # 基准在行业中的权重和收益
        bm_w = sum(benchmark_weights.get(c, 0) for c in sec_codes)
        bm_codes = [c for c in sec_codes if benchmark_weights.get(c, 0) > 0]
        if bm_codes:
            bm_r = sum(benchmark_weights.get(c, 0) * benchmark_returns.get(c, 0)
                       for c in bm_codes) / max(bm_w, 0.0001)
        else:
            bm_r = 0

        sector_data[sector] = {
            "pf_weight": pf_w, "bm_weight": bm_w,
            "pf_return": pf_r, "bm_return": bm_r,
        }

    # ── 计算各效应 ──
    # Q1: 基准配置 × 基准选股 (基准收益)
    # Q2: 组合配置 × 基准选股 (配置调整)
    # Q3: 基准配置 × 组合选股 (选股调整)
    # Q4: 组合配置 × 组合选股 (组合收益)

    total_bm = 0
    total_allocation = 0
    total_selection = 0
    total_interaction = 0

    sector_attribution = []

    for sector, data in sector_data.items():
        pf_w, bm_w = data["pf_weight"], data["bm_weight"]
        pf_r, bm_r = data["pf_return"], data["bm_return"]

        # 各象限
        q1 = bm_w * bm_r        # 基准
        q4 = pf_w * pf_r        # 组合

        allocation = (pf_w - bm_w) * bm_r
        selection = bm_w * (pf_r - bm_r)
        interaction = (pf_w - bm_w) * (pf_r - bm_r)

        total_bm += q1
        total_allocation += allocation
        total_selection += selection
        total_interaction += interaction

        sector_attribution.append({
            "sector": sector,
            "pf_weight_pct": round(pf_w * 100, 1),
            "bm_weight_pct": round(bm_w * 100, 1),
            "pf_return_pct": round(pf_r * 100, 2),
            "bm_return_pct": round(bm_r * 100, 2),
            "allocation_pct": round(allocation * 100, 3),
            "selection_pct": round(selection * 100, 3),
            "interaction_pct": round(interaction * 100, 3),
            "total_contribution_pct": round((allocation + selection + interaction) * 100, 3),
        })

    # 总超额收益
    total_pf_return = sum(portfolio_weights.get(c, 0) * portfolio_returns.get(c, 0)
                          for c in portfolio_weights)
    total_bm_return = sum(benchmark_weights.get(c, 0) * benchmark_returns.get(c, 0)
                          for c in benchmark_weights)
    excess_return = total_pf_return - total_bm_return

    # 按贡献排序
    sector_attribution.sort(key=lambda x: abs(x["total_contribution_pct"]), reverse=True)

    return {
        "total_portfolio_return_pct": round(total_pf_return * 100, 3),
        "total_benchmark_return_pct": round(total_bm_return * 100, 3),
        "excess_return_pct": round(excess_return * 100, 3),
        "allocation_effect_pct": round(total_allocation * 100, 3),
        "selection_effect_pct": round(total_selection * 100, 3),
        "interaction_effect_pct": round(total_interaction * 100, 3),
        "sector_details": sector_attribution,
        "verdict": _brinson_verdict(total_allocation, total_selection),
    }


def _brinson_verdict(allocation: float, selection: float) -> str:
    """解读 Brinson 结果"""
    parts = []
    if allocation > 0.001:
        parts.append("行业配置能力优秀（正向贡献）")
    elif allocation < -0.001:
        parts.append("行业配置拖累（负向贡献）")
    else:
        parts.append("行业配置中性")

    if selection > 0.001:
        parts.append("行业内选股能力优秀")
    elif selection < -0.001:
        parts.append("行业内选股能力较弱")
    else:
        parts.append("行业内选股能力中性")

    return "；".join(parts)


# ═══════════════════════════════════════════════════════════════
# 因子归因
# ═══════════════════════════════════════════════════════════════

def factor_attribution(
    portfolio_returns: pd.Series,
    factor_returns: pd.DataFrame,
    factor_exposures: pd.Series = None,
) -> dict:
    """
    因子归因 — 将收益分解到各因子的贡献。

    方法：时序回归，
      portfolio_return = α + Σ(β_i × factor_return_i) + ε

    Args:
        portfolio_returns: 组合日收益率序列
        factor_returns: 因子日收益率 DataFrame (columns=factor_names)
        factor_exposures: 预设因子暴露（None=自动回归估计）

    Returns:
        {
            "alpha_pct": float,          # 无法被因子解释的超额收益
            "factor_contributions": {...}, # 各因子贡献
            "r_squared": float,          # 解释力
            "residual_pct": float,       # 残差
        }
    """
    if portfolio_returns.empty or factor_returns.empty:
        return {"error": "数据不足"}

    # 对齐数据
    aligned = pd.concat([portfolio_returns, factor_returns], axis=1).dropna()
    if len(aligned) < 20:
        return {"error": f"对齐后数据不足 ({len(aligned)}天)"}

    y = aligned.iloc[:, 0].values
    X = aligned.iloc[:, 1:].values

    # 回归
    try:
        X_with_const = np.column_stack([X, np.ones(len(X))])
        coef, residuals, rank, s = np.linalg.lstsq(X_with_const, y, rcond=None)
        betas = coef[:-1]
        alpha = coef[-1]
    except Exception as e:
        return {"error": f"回归失败: {e}"}

    # R²
    y_pred = X_with_const @ coef
    ss_res = np.sum((y - y_pred) ** 2)
    ss_tot = np.sum((y - np.mean(y)) ** 2)
    r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0

    # 因子贡献
    factor_names = aligned.columns[1:].tolist()
    factor_mean_returns = X.mean(axis=0)
    factor_contributions = {}
    for i, name in enumerate(factor_names):
        contrib = betas[i] * factor_mean_returns[i]
        factor_contributions[name] = round(float(contrib) * 252 * 100, 4)  # 年化%

    # 年化
    n_days = len(aligned)
    alpha_annual = alpha * 252 * 100
    residual_annual = (1 - r_squared) * portfolio_returns.std() * np.sqrt(252) * 100

    return {
        "alpha_annual_pct": round(float(alpha_annual), 2),
        "r_squared": round(float(r_squared), 3),
        "factor_contributions": factor_contributions,
        "residual_vol_pct": round(float(residual_annual), 2),
        "n_observations": n_days,
        "interpretation": _factor_interpretation(alpha_annual, factor_contributions),
    }


def _factor_interpretation(alpha: float, contributions: dict) -> str:
    """因子归因解读"""
    total_factor = sum(contributions.values())
    parts = [f"因子合计贡献 {total_factor:.1f}%/年"]

    if alpha > 2:
        parts.append(f"纯Alpha显著({alpha:.1f}%/年) — 选股能力超越因子解释范围")
    elif alpha > 0:
        parts.append("略有正Alpha")
    elif alpha > -2:
        parts.append("Alpha不显著，收益主要由因子驱动")
    else:
        parts.append("负Alpha，因子调整后表现弱于因子预期")

    # 最大贡献因子
    if contributions:
        top_factor = max(contributions, key=lambda k: abs(contributions[k]))
        parts.append(f"最大贡献: {top_factor}({contributions[top_factor]:.1f}%/年)")

    return "；".join(parts)
