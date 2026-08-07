"""
组合约束管理
============
事前风控规则：单票上限 / 行业上限 / 流动性过滤 / 黑名单 / 仓位上下限
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set
import pandas as pd
import numpy as np

from ..data.cache import DataCache

logger = logging.getLogger("tg.portfolio.constraints")


@dataclass
class PortfolioConstraints:
    """组合约束配置"""
    max_single_weight: float = 0.10       # 单票上限 10%
    min_single_weight: float = 0.01       # 单票下限 1%
    max_sector_weight: float = 0.30       # 单行业上限 30%
    max_positions: int = 30               # 最大持仓数
    min_positions: int = 5                # 最少持仓数
    min_daily_amount: float = 10_000_000  # 最低日均成交额（1000万）
    min_market_cap: float = 1_000_000_000 # 最低市值（10亿）
    exclude_st: bool = True               # 排除ST
    exclude_suspended: bool = True        # 排除停牌
    blacklist: Set[str] = field(default_factory=set)  # 黑名单代码
    blacklist_industries: Set[str] = field(default_factory=set)  # 黑名单行业

    def to_dict(self) -> dict:
        return {
            "max_single_weight": self.max_single_weight,
            "min_single_weight": self.min_single_weight,
            "max_sector_weight": self.max_sector_weight,
            "max_positions": self.max_positions,
            "min_positions": self.min_positions,
        }


def validate_constraints(
    weights: pd.Series,
    industries: pd.Series = None,
    constraints: PortfolioConstraints = None,
) -> dict:
    """
    验证组合权重是否满足约束条件。

    Args:
        weights: 组合权重 Series (index=code, value=weight)
        industries: 行业归属 Series (index=code, value=industry)
        constraints: 约束配置

    Returns:
        {"passed": bool, "violations": [...], "warnings": [...]}
    """
    if constraints is None:
        constraints = PortfolioConstraints()

    violations = []
    warnings = []

    # 1. 持仓数检查
    n_positions = len(weights)
    if n_positions > constraints.max_positions:
        violations.append(f"持仓数 {n_positions} > 上限 {constraints.max_positions}")
    if n_positions < constraints.min_positions:
        violations.append(f"持仓数 {n_positions} < 下限 {constraints.min_positions}")

    # 2. 单票权重检查
    for code, w in weights.items():
        if w > constraints.max_single_weight:
            violations.append(f"{code} 权重 {w*100:.1f}% > 上限 {constraints.max_single_weight*100:.0f}%")
        if w < constraints.min_single_weight and w > 0:
            warnings.append(f"{code} 权重 {w*100:.1f}% < 下限 {constraints.min_single_weight*100:.0f}%")

    # 3. 行业集中度检查
    if industries is not None:
        for industry in industries.dropna().unique():
            sector_codes = industries[industries == industry].index
            sector_weight = weights.reindex(sector_codes, fill_value=0).sum()
            if sector_weight > constraints.max_sector_weight:
                violations.append(
                    f"行业 {industry} 权重 {sector_weight*100:.1f}% > 上限 {constraints.max_sector_weight*100:.0f}%"
                )

    # 4. 权重总和检查
    total_weight = weights.sum()
    if abs(total_weight - 1.0) > 0.01:
        violations.append(f"权重总和 {total_weight:.4f} ≠ 1.0")

    return {
        "passed": len(violations) == 0,
        "violations": violations,
        "warnings": warnings,
    }


def prefilter_codes(
    codes: List[str],
    cache: DataCache = None,
    constraints: PortfolioConstraints = None,
) -> List[str]:
    """
    预处理过滤：排除ST/停牌/低市值/低流动/黑名单。

    Returns:
        通过过滤的代码列表
    """
    if cache is None:
        cache = DataCache()
    if constraints is None:
        constraints = PortfolioConstraints()

    filtered = []
    for code in codes:
        if code in constraints.blacklist:
            logger.debug(f"黑名单排除: {code}")
            continue

        info = cache.get_stock_basic(code) or {}
        name = info.get("name", "")

        # ST排除
        if constraints.exclude_st and ("ST" in name or "*ST" in name):
            logger.debug(f"ST排除: {code}")
            continue

        # 市值过滤
        mcap = info.get("mcap_yi", 0) or 0
        if mcap > 0 and mcap * 100000000 < constraints.min_market_cap:
            logger.debug(f"低市值排除: {code} ({mcap}亿)")
            continue

        # 流动性过滤（换手率极低视为停牌/僵尸股）
        turnover = info.get("turnover_pct", 0) or 0
        if constraints.exclude_suspended and turnover < 0.05 and mcap > 0:
            logger.debug(f"疑似停牌: {code}")
            continue

        # 行业黑名单
        industry = info.get("industry", "")
        if industry and industry in constraints.blacklist_industries:
            logger.debug(f"行业黑名单排除: {code} ({industry})")
            continue

        filtered.append(code)

    logger.info(f"预处理过滤: {len(codes)} → {len(filtered)} (排除 {len(codes)-len(filtered)} 只)")
    return filtered
