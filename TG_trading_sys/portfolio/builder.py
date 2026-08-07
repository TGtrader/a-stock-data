"""
组合构建器
==========
从选股结果构建投资组合，支持多种权重优化方法：

  - equal_weight:        等权分配
  - market_cap_weight:   市值加权
  - inv_volatility:      波动率倒数加权（低波高配）
  - risk_parity:         风险平价（每只贡献相同风险）
  - min_variance:        最小方差组合
  - max_diversification: 最大分散度
"""

import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import pandas as pd
import numpy as np

from ..data.cache import DataCache
from ..core.config import Config
from .constraints import PortfolioConstraints, validate_constraints, prefilter_codes

logger = logging.getLogger("tg.portfolio.builder")


# ═══════════════════════════════════════════════════════════════
# 主构建函数
# ═══════════════════════════════════════════════════════════════

def build_portfolio(
    codes: List[str],
    method: str = "equal_weight",
    constraints: PortfolioConstraints = None,
    cache: DataCache = None,
    lookback_days: int = 120,
    target_return: float = None,
    name: str = None,
) -> dict:
    """
    从候选标的构建投资组合。

    Args:
        codes: 候选股票代码列表
        method: 权重方法
            - equal_weight: 等权
            - market_cap: 市值加权
            - inv_volatility: 波动率倒数
            - risk_parity: 风险平价
            - min_variance: 最小方差
            - max_diversification: 最大分散度
        constraints: 约束配置
        cache: 数据缓存
        lookback_days: 回溯天数（用于计算协方差）
        target_return: 目标收益（min_variance 约束用）
        name: 组合名称

    Returns:
        {
            "name": str,
            "created": str,
            "method": str,
            "holdings": [{code, name, weight, shares, price, market_cap, sector}, ...],
            "weights": pd.Series,
            "constraints": dict,
            "validation": dict,
            "stats": {"n_stocks": int, "n_sectors": int, "max_weight": float, ...},
        }
    """
    if cache is None:
        cache = DataCache()
    if constraints is None:
        constraints = PortfolioConstraints()

    # ── 预处理过滤 ──
    codes = prefilter_codes(codes, cache, constraints)
    if not codes:
        return {"error": "预处理过滤后无可用标的"}

    # ── 获取价格和行业数据 ──
    prices, returns, industries = _get_market_data(cache, codes, lookback_days)

    # ── 权重优化 ──
    if method == "equal_weight":
        weights = _equal_weight(codes)
    elif method == "market_cap":
        weights = _market_cap_weight(cache, codes)
    elif method == "inv_volatility":
        weights = _inv_volatility_weight(returns, codes)
    elif method == "risk_parity":
        weights = _risk_parity_weight(returns, codes, constraints)
    elif method == "min_variance":
        weights = _min_variance_weight(returns, codes, constraints, target_return)
    elif method == "max_diversification":
        weights = _max_diversification_weight(returns, codes, constraints)
    else:
        return {"error": f"不支持的权重方法: {method}"}

    # ── 归一化 ──
    weights = _normalize_weights(weights, constraints)

    # ── 验证 ──
    validation = validate_constraints(weights, industries, constraints)

    # ── 构建持仓列表 ──
    holdings = []
    total_capital = 0  # 虚拟组合，不实际计算股数
    for code in weights.index:
        w = weights.loc[code]
        if w <= 0:
            continue
        info = cache.get_stock_basic(code) or {}
        holdings.append({
            "code": code,
            "name": info.get("name", code),
            "weight": round(w, 4),
            "price": info.get("price", 0),
            "market_cap_yi": info.get("mcap_yi", 0),
            "sector": info.get("industry", ""),
            "pe_ttm": info.get("pe_ttm", 0),
            "pb": info.get("pb", 0),
        })

    # ── 统计 ──
    sectors = set(h.get("sector", "") for h in holdings if h.get("sector"))
    weights_series = pd.Series({h["code"]: h["weight"] for h in holdings})

    stats = {
        "n_stocks": len(holdings),
        "n_sectors": len(sectors),
        "max_weight": float(weights_series.max()),
        "min_weight": float(weights_series[weights_series > 0].min()),
        "top3_weight": float(weights_series.nlargest(3).sum()),
        "top5_weight": float(weights_series.nlargest(5).sum()),
        "herfindahl": float((weights_series ** 2).sum()),  # 集中度指数
    }

    return {
        "name": name or f"portfolio_{datetime.now().strftime('%Y%m%d_%H%M')}",
        "created": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "method": method,
        "holdings": holdings,
        "weights": weights_series,
        "constraints": constraints.to_dict(),
        "validation": validation,
        "stats": stats,
    }


# ═══════════════════════════════════════════════════════════════
# 权重方法实现
# ═══════════════════════════════════════════════════════════════

def _equal_weight(codes: List[str]) -> pd.Series:
    """等权分配"""
    n = len(codes)
    return pd.Series(1.0 / n, index=codes)


def _market_cap_weight(cache: DataCache, codes: List[str]) -> pd.Series:
    """市值加权"""
    mcaps = {}
    for code in codes:
        info = cache.get_stock_basic(code) or {}
        mcap = info.get("mcap_yi", 0) or 0
        mcaps[code] = max(mcap, 1)

    series = pd.Series(mcaps, name="weight")
    # 归一化到 sum=1
    total = series.sum()
    if total > 0:
        series = series / total
    return series


def _inv_volatility_weight(returns: pd.DataFrame, codes: List[str]) -> pd.Series:
    """波动率倒数加权 — 波动越低权重越高"""
    if returns.empty:
        return _equal_weight(codes)

    vols = returns.std()
    inv_vols = 1.0 / vols.replace(0, np.nan)
    inv_vols = inv_vols.fillna(inv_vols.median())
    # 归一化到 sum=1
    total = inv_vols.sum()
    if total > 0:
        inv_vols = inv_vols / total
    return inv_vols


def _risk_parity_weight(
    returns: pd.DataFrame, codes: List[str], constraints: PortfolioConstraints
) -> pd.Series:
    """
    风险平价 — 每只标的贡献相同的风险。
    迭代算法：权重 ∝ 1/波动率，迭代至各标的边际风险贡献均匀。
    """
    if returns.empty or len(codes) < 3:
        return _equal_weight(codes)

    valid_codes = [c for c in codes if c in returns.columns]
    if len(valid_codes) < 3:
        return _equal_weight(codes)

    ret = returns[valid_codes].dropna()
    if len(ret) < 20:
        return _equal_weight(valid_codes)

    cov = ret.cov().values
    vols = np.sqrt(np.diag(cov))

    # 初始权重 = 1/vol
    w = 1.0 / np.maximum(vols, 1e-8)
    w = w / w.sum()

    # 迭代
    for _ in range(50):
        port_vol = np.sqrt(w @ cov @ w)
        if port_vol < 1e-8:
            break
        # 边际风险贡献
        mrc = cov @ w / port_vol
        rc = w * mrc  # 各标的的风险贡献
        target_rc = port_vol / len(w)
        # 调整权重
        w_new = w * target_rc / np.maximum(rc, 1e-8)
        w = w_new / w_new.sum()
        if np.max(np.abs(rc - target_rc)) / port_vol < 0.01:
            break

    # 收束到约束
    w = np.clip(w, 0, constraints.max_single_weight)
    w = w / w.sum()

    return pd.Series(w, index=valid_codes)


def _min_variance_weight(
    returns: pd.DataFrame, codes: List[str],
    constraints: PortfolioConstraints, target_return: float = None
) -> pd.Series:
    """
    最小方差组合 — 在给定收益约束下最小化波动率。
    使用二次规划近似（简化：闭式解 + 约束截断）。
    """
    if returns.empty or len(codes) < 3:
        return _equal_weight(codes)

    valid_codes = [c for c in codes if c in returns.columns]
    if len(valid_codes) < 3:
        return _equal_weight(valid_codes)

    ret = returns[valid_codes].dropna()
    if len(ret) < 30:
        return _equal_weight(valid_codes)

    cov = ret.cov().values
    n = len(valid_codes)
    ones = np.ones(n)

    try:
        cov_inv = np.linalg.inv(cov)
        # 全局最小方差权重
        w = cov_inv @ ones / (ones @ cov_inv @ ones)
    except np.linalg.LinAlgError:
        # 协方差矩阵奇异，用波动率倒数替代
        vols = np.sqrt(np.diag(cov))
        w = 1.0 / np.maximum(vols, 1e-8)

    w = np.clip(w, 0, constraints.max_single_weight)
    w = w / w.sum()

    return pd.Series(w, index=valid_codes)


def _max_diversification_weight(
    returns: pd.DataFrame, codes: List[str], constraints: PortfolioConstraints
) -> pd.Series:
    """
    最大分散度 — 最大化组合的分散化比率。
    Diversification Ratio = (Σ w_i σ_i) / σ_portfolio
    """
    if returns.empty or len(codes) < 3:
        return _equal_weight(codes)

    valid_codes = [c for c in codes if c in returns.columns]
    if len(valid_codes) < 3:
        return _equal_weight(valid_codes)

    ret = returns[valid_codes].dropna()
    cov = ret.cov().values
    vols = np.sqrt(np.diag(cov))
    n = len(valid_codes)

    # 近似：波动率倒数 × 去相关调整
    try:
        corr = ret.corr().values
        avg_corr = (corr.sum() - n) / (n * (n - 1))  # 平均相关性
        # 低相关 → 高权重
        decorr_factor = 1.0 / max(avg_corr, 0.1)
    except Exception:
        decorr_factor = 1.0

    w = (1.0 / np.maximum(vols, 1e-8)) * decorr_factor
    w = np.clip(w, 0, constraints.max_single_weight)
    w = w / w.sum()

    return pd.Series(w, index=valid_codes)


# ═══════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════

def _get_market_data(
    cache: DataCache, codes: List[str], lookback: int
) -> Tuple[dict, pd.DataFrame, pd.Series]:
    """
    获取市场价格数据和行业归属。

    Returns:
        (prices_dict, returns_df, industries_series)
    """
    prices = {}
    returns_list = {}
    industries = {}
    for code in codes:
        df = cache.get_kline(code, lookback=lookback)
        if df is not None and len(df) >= 20:
            prices[code] = df["close"]
            returns_list[code] = df["close"].pct_change().dropna()
        info = cache.get_stock_basic(code) or {}
        industries[code] = info.get("industry", "未知")

    returns_df = pd.DataFrame(returns_list) if returns_list else pd.DataFrame()
    industries_series = pd.Series(industries)

    return prices, returns_df, industries_series


def _normalize_weights(weights: pd.Series, constraints: PortfolioConstraints) -> pd.Series:
    """归一化并收束权重到约束范围"""
    w = weights.copy()
    w = w.fillna(0)
    w = w.clip(0, constraints.max_single_weight)
    total = w.sum()
    if total > 0:
        w = w / total
    else:
        n = len(w)
        w = pd.Series(1.0 / n, index=w.index)
    return w


def optimize_weights(
    returns: pd.DataFrame,
    method: str = "risk_parity",
    constraints: PortfolioConstraints = None,
) -> pd.Series:
    """
    独立的权重优化函数（不依赖完整构建流程）。

    Args:
        returns: 收益率 DataFrame (columns=code, index=date)
        method: 优化方法
        constraints: 约束
    """
    codes = list(returns.columns)
    if constraints is None:
        constraints = PortfolioConstraints()

    if method == "equal_weight":
        return _equal_weight(codes)
    elif method == "risk_parity":
        return _risk_parity_weight(returns, codes, constraints)
    elif method == "min_variance":
        return _min_variance_weight(returns, codes, constraints)
    elif method == "max_diversification":
        return _max_diversification_weight(returns, codes, constraints)
    else:
        return _inv_volatility_weight(returns, codes)
