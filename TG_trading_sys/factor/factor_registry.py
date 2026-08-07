"""
因子注册中心 — 因子定义/发现/元数据管理
========================================
提供统一的因子注册、发现和计算调度机制。
每个因子是一个函数，签名: (codes: List[str], cache: DataCache) -> pd.Series
"""

import logging
from typing import Dict, List, Callable, Optional
from dataclasses import dataclass, field
import pandas as pd

from ..data.cache import DataCache
from ..core.config import Config

logger = logging.getLogger("tg.factor.registry")


@dataclass
class FactorMeta:
    """因子元数据"""
    name: str                          # 因子唯一标识
    category: str                      # 大类: value/growth/quality/momentum/fund/sentiment/special
    display_name: str                  # 中文显示名
    description: str                   # 简要描述
    direction: str = "positive"        # positive=值越大越好, negative=值越小越好
    default_weight: float = 0.05       # 默认权重
    data_required: List[str] = field(default_factory=list)  # 所需数据: kline/financials/moneyflow/research
    min_samples: int = 50              # 最少样本数
    enabled: bool = True               # 是否启用


class FactorRegistry:
    """
    因子注册中心 — 管理所有已注册的选股因子。

    用法:
        reg = FactorRegistry()
        reg.register("pe_ttm", compute_pe_ttm, meta)
        factors = reg.list(category="value")
        scores = reg.compute("pe_ttm", codes)
    """

    _instance: Optional["FactorRegistry"] = None

    def __init__(self):
        self._factors: Dict[str, Callable] = {}
        self._meta: Dict[str, FactorMeta] = {}

    @classmethod
    def get_instance(cls) -> "FactorRegistry":
        if cls._instance is None:
            cls._instance = cls()
            cls._instance._register_builtin()
        return cls._instance

    def register(self, name: str, compute_fn: Callable, meta: FactorMeta):
        """注册一个因子"""
        self._factors[name] = compute_fn
        self._meta[name] = meta

    def get(self, name: str) -> Optional[Callable]:
        """获取因子计算函数"""
        return self._factors.get(name)

    def get_meta(self, name: str) -> Optional[FactorMeta]:
        return self._meta.get(name)

    def list(self, category: str = None, enabled_only: bool = True) -> List[FactorMeta]:
        """列出因子（可按大类过滤）"""
        result = []
        for name, meta in self._meta.items():
            if enabled_only and not meta.enabled:
                continue
            if category and meta.category != category:
                continue
            result.append(meta)
        return result

    def list_by_category(self) -> Dict[str, List[FactorMeta]]:
        """按大类分组列出所有因子"""
        groups = {}
        for meta in self._meta.values():
            if not meta.enabled:
                continue
            groups.setdefault(meta.category, []).append(meta)
        return groups

    def categories(self) -> List[str]:
        """列出所有因子大类"""
        cats = set(m.category for m in self._meta.values() if m.enabled)
        return sorted(cats)

    def compute(self, name: str, codes: List[str], cache: DataCache = None) -> pd.Series:
        """
        计算单个因子的横截面得分。

        Args:
            name: 因子名
            codes: 股票代码列表
            cache: 数据缓存（None则创建新实例）

        Returns:
            Series indexed by code, values = raw factor values (未标准化)
        """
        fn = self._factors.get(name)
        if fn is None:
            raise ValueError(f"因子 '{name}' 未注册")

        if cache is None:
            cache = DataCache()

        try:
            result = fn(codes, cache)
            if not isinstance(result, pd.Series):
                result = pd.Series(result, index=codes)
            return result
        except Exception as e:
            logger.warning(f"因子 '{name}' 计算失败: {e}")
            return pd.Series(index=codes, dtype=float)

    def compute_all(self, codes: List[str], cache: DataCache = None,
                    categories: List[str] = None) -> pd.DataFrame:
        """
        计算所有已启用因子的横截面得分。

        Args:
            codes: 股票代码列表
            cache: 数据缓存
            categories: 限定大类（None=全部）

        Returns:
            DataFrame: index=code, columns=factor_names, values=raw factor values
        """
        if cache is None:
            cache = DataCache()

        results = {}
        for name, meta in self._meta.items():
            if not meta.enabled:
                continue
            if categories and meta.category not in categories:
                continue

            try:
                series = self.compute(name, codes, cache)
                results[name] = series
                logger.debug(f"因子 '{name}' 计算完成: {series.count()} 个有效值")
            except Exception as e:
                logger.warning(f"因子 '{name}' 跳过: {e}")

        return pd.DataFrame(results)

    def get_default_weights(self, categories: List[str] = None) -> Dict[str, float]:
        """获取默认权重（可覆盖）"""
        weights = {}
        for name, meta in self._meta.items():
            if not meta.enabled:
                continue
            if categories and meta.category not in categories:
                continue
            weights[name] = meta.default_weight
        return weights

    # ── 内置因子注册 ──

    def _register_builtin(self):
        """注册所有内置因子"""
        from . import value_factors, growth_factors, quality_factors, momentum_factors

        # ── 价值因子 ──
        self.register("pe_ttm", value_factors.compute_pe_ttm, FactorMeta(
            name="pe_ttm", category="value", display_name="PE(TTM)",
            description="市盈率(TTM)，越低越有价值",
            direction="negative", default_weight=0.07,
            data_required=["kline", "stock_basic"],
        ))
        self.register("pb", value_factors.compute_pb, FactorMeta(
            name="pb", category="value", display_name="PB",
            description="市净率，越低越有价值",
            direction="negative", default_weight=0.05,
            data_required=["stock_basic"],
        ))
        self.register("ps_ttm", value_factors.compute_ps_ttm, FactorMeta(
            name="ps_ttm", category="value", display_name="PS(TTM)",
            description="市销率，越低越有价值",
            direction="negative", default_weight=0.04,
            data_required=["financials", "stock_basic"],
        ))
        self.register("fcf_yield", value_factors.compute_fcf_yield, FactorMeta(
            name="fcf_yield", category="value", display_name="FCF收益率",
            description="自由现金流/市值，越高越好",
            direction="positive", default_weight=0.04,
            data_required=["financials", "stock_basic"],
        ))

        # ── 成长因子 ──
        self.register("eps_growth_yoy", growth_factors.compute_eps_growth_yoy, FactorMeta(
            name="eps_growth_yoy", category="growth", display_name="EPS增速(YoY)",
            description="归母净利润同比增长率",
            direction="positive", default_weight=0.06,
            data_required=["financials"],
        ))
        self.register("revenue_growth_yoy", growth_factors.compute_revenue_growth_yoy, FactorMeta(
            name="revenue_growth_yoy", category="growth", display_name="营收增速(YoY)",
            description="营业收入同比增长率",
            direction="positive", default_weight=0.05,
            data_required=["financials"],
        ))
        self.register("earnings_acceleration", growth_factors.compute_earnings_acceleration, FactorMeta(
            name="earnings_acceleration", category="growth", display_name="盈利加速度",
            description="本期增速 vs 上期增速差值，正向加速越好",
            direction="positive", default_weight=0.04,
            data_required=["financials"],
        ))
        self.register("turnaround", growth_factors.compute_turnaround, FactorMeta(
            name="turnaround", category="growth", display_name="扭亏反转",
            description="上期亏损→本期盈利=1，否则0。识别行业反转信号",
            direction="positive", default_weight=0.03,
            data_required=["financials"],
        ))
        self.register("revenue_leap", growth_factors.compute_revenue_leap, FactorMeta(
            name="revenue_leap", category="growth", display_name="营收跃进",
            description="Q1单季营收/去年全年营收，>30%为高弹性信号",
            direction="positive", default_weight=0.03,
            data_required=["financials"],
        ))
        self.register("consensus_eps_cagr", growth_factors.compute_consensus_eps_cagr, FactorMeta(
            name="consensus_eps_cagr", category="growth", display_name="一致预期CAGR",
            description="分析师一致预期EPS 3年复合增长率",
            direction="positive", default_weight=0.04,
            data_required=["research"],
        ))

        # ── 质量因子 ──
        self.register("roe", quality_factors.compute_roe, FactorMeta(
            name="roe", category="quality", display_name="ROE",
            description="净资产收益率，越高盈利质量越好",
            direction="positive", default_weight=0.06,
            data_required=["financials"],
        ))
        self.register("gross_margin", quality_factors.compute_gross_margin, FactorMeta(
            name="gross_margin", category="quality", display_name="毛利率",
            description="毛利率，越高护城河越深",
            direction="positive", default_weight=0.04,
            data_required=["financials"],
        ))
        self.register("debt_ratio", quality_factors.compute_debt_ratio, FactorMeta(
            name="debt_ratio", category="quality", display_name="资产负债率",
            description="总负债/总资产，越低财务越稳健",
            direction="negative", default_weight=0.04,
            data_required=["financials"],
        ))
        self.register("cashflow_quality", quality_factors.compute_cashflow_quality, FactorMeta(
            name="cashflow_quality", category="quality", display_name="现金流质量",
            description="经营现金流/净利润，>1说明利润含金量高",
            direction="positive", default_weight=0.03,
            data_required=["financials"],
        ))
        self.register("roe_stability", quality_factors.compute_roe_stability, FactorMeta(
            name="roe_stability", category="quality", display_name="ROE稳定性",
            description="近3年ROE标准差(取负)，越低越稳定",
            direction="positive", default_weight=0.03,
            data_required=["financials"],
        ))

        # ── 动量因子 ──
        self.register("momentum_20d", momentum_factors.compute_momentum_20d, FactorMeta(
            name="momentum_20d", category="momentum", display_name="20日动量",
            description="近20个交易日涨跌幅",
            direction="positive", default_weight=0.04,
            data_required=["kline"],
        ))
        self.register("momentum_60d", momentum_factors.compute_momentum_60d, FactorMeta(
            name="momentum_60d", category="momentum", display_name="60日动量",
            description="近60个交易日涨跌幅",
            direction="positive", default_weight=0.04,
            data_required=["kline"],
        ))
        self.register("volume_momentum", momentum_factors.compute_volume_momentum, FactorMeta(
            name="volume_momentum", category="momentum", display_name="量能动量",
            description="近5日均量/20日均量，放量看多",
            direction="positive", default_weight=0.03,
            data_required=["kline"],
        ))
        self.register("turnover_rate", momentum_factors.compute_turnover_rate, FactorMeta(
            name="turnover_rate", category="momentum", display_name="换手率",
            description="日均换手率，适度活跃为佳",
            direction="positive", default_weight=0.03,
            data_required=["kline"],
        ))

        logger.info(f"因子注册完成: {len(self._factors)} 个因子, "
                     f"{len(self.categories())} 大类")


# ── 便捷函数 ──

def list_factors(category: str = None) -> pd.DataFrame:
    """列出所有因子（返回 DataFrame 便于查看）"""
    reg = FactorRegistry.get_instance()
    factors = reg.list(category=category)
    rows = [{
        "name": f.name, "类别": f.category, "显示名": f.display_name,
        "方向": "正向" if f.direction == "positive" else "负向",
        "默认权重": f"{f.default_weight*100:.0f}%",
        "描述": f.description,
    } for f in factors]
    return pd.DataFrame(rows)
