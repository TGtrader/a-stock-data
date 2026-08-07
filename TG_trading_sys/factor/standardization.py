"""
因子标准化 & 预处理
====================
行业中性化 + Z-score标准化 + 极值Winsorize + 缺失值处理
"""

import logging
from typing import List, Optional, Dict
import pandas as pd
import numpy as np

from ..data.cache import DataCache
from .factor_registry import FactorRegistry, FactorMeta

logger = logging.getLogger("tg.factor.std")


def winsorize(series: pd.Series, lower_pct: float = 0.01, upper_pct: float = 0.99) -> pd.Series:
    """
    极值缩尾处理 — 将超出分位数的值截断到分位边界。

    Args:
        series: 原始因子值
        lower_pct: 下界分位数（默认1%）
        upper_pct: 上界分位数（默认99%）

    Returns:
        缩尾后的 Series
    """
    lower = series.quantile(lower_pct)
    upper = series.quantile(upper_pct)
    return series.clip(lower, upper)


def zscore_normalize(series: pd.Series) -> pd.Series:
    """
    Z-score 标准化 — 使因子值服从均值为0、标准差为1的分布。

    Returns:
        标准化后的 Series（NaN 保持）
    """
    mean = series.mean()
    std = series.std()
    if std == 0 or np.isnan(std):
        return pd.Series(0.0, index=series.index)
    return (series - mean) / std


def minmax_normalize(series: pd.Series, feature_range: tuple = (0, 1)) -> pd.Series:
    """
    Min-Max 归一化。

    Returns:
        归一化到 [feature_range[0], feature_range[1]] 的 Series
    """
    s_min = series.min()
    s_max = series.max()
    if s_max - s_min == 0:
        return pd.Series(0.5, index=series.index)
    scaled = (series - s_min) / (s_max - s_min)
    lo, hi = feature_range
    return scaled * (hi - lo) + lo


def industry_neutralize(
    scores: pd.Series,
    industries: pd.Series,
    method: str = "subtract_median"
) -> pd.Series:
    """
    行业中性化 — 消除行业间的系统性偏差。

    方法：
      subtract_median: 每个因子值减去该行业的中位数
      zscore_within: 在每个行业内做 Z-score 标准化

    Args:
        scores: 因子得分（index=code）
        industries: 行业归属（index=code, value=industry_name）
        method: 中性化方法

    Returns:
        中性化后的 Series
    """
    aligned_codes = scores.index.intersection(industries.index)
    scores = scores.loc[aligned_codes]
    industries = industries.loc[aligned_codes]

    result = pd.Series(np.nan, index=scores.index)

    for industry in industries.dropna().unique():
        mask = industries == industry
        if mask.sum() < 3:
            continue
        group = scores[mask].dropna()
        if len(group) < 3:
            continue

        if method == "subtract_median":
            result.loc[group.index] = group - group.median()
        elif method == "zscore_within":
            result.loc[group.index] = zscore_normalize(group)

    return result


def fill_missing(series: pd.Series, method: str = "median", fallback: float = 0.0) -> pd.Series:
    """
    缺失值填充。

    Args:
        series: 含 NaN 的因子值
        method: median(行业中位数) / mean / zero / fallback
        fallback: method=fallback 时的填充值

    Returns:
        去除了 NaN 的 Series
    """
    result = series.copy()
    nan_mask = result.isna()
    if not nan_mask.any():
        return result

    if method == "median":
        fill_val = result.median()
        if np.isnan(fill_val):
            fill_val = 0.0
        result.loc[nan_mask] = fill_val
    elif method == "mean":
        fill_val = result.mean()
        if np.isnan(fill_val):
            fill_val = 0.0
        result.loc[nan_mask] = fill_val
    elif method == "zero":
        result.loc[nan_mask] = 0.0
    else:
        result.loc[nan_mask] = fallback

    return result


def standardize_factors(
    factor_df: pd.DataFrame,
    registry: FactorRegistry = None,
    industries: pd.Series = None,
    winsorize_pct: bool = True,
    neutralize_industry: bool = True,
    fillna: bool = True,
) -> pd.DataFrame:
    """
    一次性完成所有因子的标准化预处理。

    Pipeline:
      1. Winsorize 极值处理 (1%/99%)
      2. 行业中性化（如果提供了行业数据）
      3. Z-score 标准化
      4. 缺失值填充（中位数）
      5. 方向调整（负向因子取反）

    Args:
        factor_df: 原始因子 DataFrame (index=code, columns=factor_names)
        registry: 因子注册中心（用于获取因子方向）
        industries: 行业归属
        winsorize_pct: 是否缩尾
        neutralize_industry: 是否行业中性化
        fillna: 是否填充缺失值

    Returns:
        标准化后的因子 DataFrame
    """
    if registry is None:
        registry = FactorRegistry.get_instance()

    result = factor_df.copy()

    for col in result.columns:
        meta = registry.get_meta(col)
        if meta is None:
            continue

        series = result[col].copy()

        # 1. 清理非法值
        series = series.replace([np.inf, -np.inf], np.nan)

        # 2. Winsorize
        if winsorize_pct:
            valid = series.dropna()
            if len(valid) > 10:
                lower = valid.quantile(0.01)
                upper = valid.quantile(0.99)
                series = series.clip(lower, upper)

        # 3. 行业中性化
        if neutralize_industry and industries is not None:
            try:
                series = industry_neutralize(series, industries)
            except Exception as e:
                logger.debug(f"行业中性化失败 {col}: {e}")

        # 4. Z-score 标准化
        valid = series.dropna()
        if len(valid) >= 5:
            mean = valid.mean()
            std = valid.std()
            if std > 0:
                series = (series - mean) / std
            else:
                series = series - mean
        else:
            series = pd.Series(0.0, index=series.index)

        # 5. 缺失值填充
        if fillna:
            fill_val = valid.median() if len(valid) > 0 else 0.0
            if np.isnan(fill_val):
                fill_val = 0.0
            series = series.fillna(fill_val)

        # 6. 方向调整（负向因子取反）
        if meta.direction == "negative":
            series = -series

        result[col] = series

    return result


def get_industries(codes: List[str], cache: DataCache = None) -> pd.Series:
    """
    获取股票列表的行业归属。

    Returns:
        Series: index=code, value=industry_name
    """
    if cache is None:
        cache = DataCache()

    industries = {}
    for code in codes:
        info = cache.get_stock_basic(code) or {}
        ind = info.get("industry", "")
        if ind:
            industries[code] = ind
        else:
            industries[code] = "未知"

    return pd.Series(industries)
