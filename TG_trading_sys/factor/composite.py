"""
复合因子合成 & 排名
===================
加权合成 + IC分析 + 排名输出。
"""

import logging
from typing import List, Dict, Optional
import pandas as pd
import numpy as np

from .factor_registry import FactorRegistry
from .standardization import standardize_factors, get_industries
from ..data.cache import DataCache
from ..core.config import Config

logger = logging.getLogger("tg.factor.composite")


def composite_score(
    factor_df: pd.DataFrame,
    weights: Dict[str, float] = None,
    registry: FactorRegistry = None,
    industries: pd.Series = None,
    neutralize: bool = True,
) -> pd.Series:
    """
    加权合成复合因子得分。

    Args:
        factor_df: 原始因子 DataFrame (index=code, columns=factor_names)
        weights: 因子权重 dict {factor_name: weight}（自动归一化）
        registry: 因子注册中心
        industries: 行业归属（用于中性化）
        neutralize: 是否行业中性化

    Returns:
        复合得分 Series (index=code)，得分越高越好
    """
    if registry is None:
        registry = FactorRegistry.get_instance()

    # 标准化
    std_df = standardize_factors(
        factor_df, registry=registry,
        industries=industries,
        neutralize_industry=neutralize,
        winsorize_pct=True,
        fillna=True,
    )

    # 确定权重
    if weights is None:
        weights = {}
        for col in std_df.columns:
            meta = registry.get_meta(col)
            if meta:
                weights[col] = meta.default_weight

    # 只保留有数据的因子
    available_cols = [c for c in std_df.columns if c in weights]
    if not available_cols:
        logger.warning("无可用因子列")
        return pd.Series(0.0, index=factor_df.index)

    # 归一化权重
    total_w = sum(weights.get(c, 0) for c in available_cols)
    if total_w == 0:
        return pd.Series(0.0, index=factor_df.index)

    # 加权合成
    scores = pd.Series(0.0, index=std_df.index)
    weight_details = {}
    for col in available_cols:
        w = weights.get(col, 0) / total_w
        scores += std_df[col] * w
        weight_details[col] = round(w, 4)

    logger.info(f"复合得分计算完成: {len(available_cols)} 个因子, "
                 f"{scores.notna().sum()} 个有效标的")

    return scores


def rank_stocks(
    scores: pd.Series,
    ascending: bool = False,
    top_n: int = None,
) -> pd.DataFrame:
    """
    按复合得分排序。

    Args:
        scores: 复合得分 Series
        ascending: True=升序（选低估值）
        top_n: 返回前N只

    Returns:
        DataFrame: rank, code, score
    """
    ranked = scores.dropna().sort_values(ascending=ascending)
    result = pd.DataFrame({
        "score": ranked.values,
    }, index=ranked.index)
    result.index.name = "code"
    result["rank"] = range(1, len(result) + 1)

    if top_n:
        result = result.head(top_n)

    return result


def run_screening(
    codes: List[str],
    weights: Dict[str, float] = None,
    categories: List[str] = None,
    top_n: int = 30,
    neutralize_industry: bool = True,
    min_factors_available: int = 5,
    cache: DataCache = None,
) -> pd.DataFrame:
    """
    一键运行多因子筛选全流程。

    Pipeline:
      1. 获取行业归属
      2. 计算所有已启用因子
      3. 标准化（Winsorize + 行业中性化 + Z-score）
      4. 加权合成
      5. 排名输出

    Args:
        codes: 标的池
        weights: 自定义权重
        categories: 限定大类
        top_n: 返回前N只
        neutralize_industry: 是否行业中性化
        min_factors_available: 最少可用的因子数
        cache: 数据缓存

    Returns:
        DataFrame: rank, code, name, score, industry, [各因子得分...]
    """
    if cache is None:
        cache = DataCache()

    registry = FactorRegistry.get_instance()

    # 1. 行业归属
    industries = get_industries(codes, cache)
    logger.info(f"标的池: {len(codes)} 只, {industries.nunique()} 个行业")

    # 2. 因子计算
    logger.info("正在计算因子...")
    factor_df = registry.compute_all(codes, cache, categories=categories)

    if factor_df.empty or factor_df.columns.size < min_factors_available:
        logger.warning(f"有效因子不足: {factor_df.columns.size} < {min_factors_available}")
        return pd.DataFrame(columns=["rank", "code", "name", "score"])

    # 过滤：至少有一定数量因子有效的标的
    valid_mask = factor_df.notna().sum(axis=1) >= min_factors_available
    factor_df = factor_df.loc[valid_mask]
    logger.info(f"有效标的: {len(factor_df)}/{len(codes)} (至少{min_factors_available}个因子)")

    # 3. 复合得分
    scores = composite_score(
        factor_df, weights=weights, registry=registry,
        industries=industries, neutralize=neutralize_industry,
    )

    # 4. 排名
    result = rank_stocks(scores, top_n=top_n)
    result = result.reset_index()

    # 5. 附加信息：名称、行业、各因子得分
    names = []
    for code in result["code"]:
        info = cache.get_stock_basic(code) or {}
        names.append(info.get("name", code))

    result["name"] = names
    result["industry"] = result["code"].map(
        lambda c: industries.get(c, "未知") if isinstance(industries, pd.Series) else "未知"
    )

    # 附加各因子标准化得分（取前几列）
    if not factor_df.empty:
        std_df = standardize_factors(factor_df, registry=registry, neutralize_industry=False)
        for col in list(std_df.columns)[:8]:
            result[f"factor_{col}"] = result["code"].map(
                lambda c: round(std_df.loc[c, col], 3) if c in std_df.index else None
            )

    return result.rename(columns={"score": "composite_score"})


def compute_ic(
    factor_df: pd.DataFrame,
    forward_returns: pd.Series,
    method: str = "rank"
) -> Dict[str, float]:
    """
    计算各因子的 IC（Information Coefficient）。
    用于因子有效性评估。

    Args:
        factor_df: 因子 DataFrame
        forward_returns: 未来收益 Series (index=code)
        method: rank=秩相关系数, pearson=皮尔逊相关系数

    Returns:
        {factor_name: IC值}
    """
    ic_values = {}
    for col in factor_df.columns:
        valid = factor_df[col].dropna()
        codes = valid.index.intersection(forward_returns.index)
        if len(codes) < 20:
            ic_values[col] = np.nan
            continue

        x = valid.loc[codes]
        y = forward_returns.loc[codes]

        if method == "rank":
            ic = x.rank().corr(y.rank())
        else:
            ic = x.corr(y)

        ic_values[col] = round(ic, 4)

    return ic_values
