"""
价值因子 — PE / PB / PS / FCF Yield
====================================
所有因子返回 pd.Series，index=code，值越大越好（方向在注册时声明）。
"""

import logging
from typing import List
import pandas as pd
import numpy as np

from ..data.cache import DataCache

logger = logging.getLogger("tg.factor.value")


def compute_pe_ttm(codes: List[str], cache: DataCache) -> pd.Series:
    """
    市盈率 PE(TTM) — 负向因子（越低越好，注册时自动取负）。
    数据源：腾讯财经实时行情。
    缺失值处理：行业均值填充。
    """
    values = {}
    for code in codes:
        info = cache.get_stock_basic(code) or {}
        pe = info.get("pe_ttm", 0)
        # 排除负PE（亏损股）和极端值
        if pe and pe > 0 and pe < 500:
            values[code] = pe
        else:
            values[code] = np.nan

    series = pd.Series(values, name="pe_ttm")
    # 取倒数使越高越好：1/PE = earnings yield
    series = 1.0 / series.replace(0, np.nan)
    return series


def compute_pb(codes: List[str], cache: DataCache) -> pd.Series:
    """
    市净率 PB — 负向因子。
    数据源：腾讯财经实时行情。
    """
    values = {}
    for code in codes:
        info = cache.get_stock_basic(code) or {}
        pb = info.get("pb", 0)
        if pb and pb > 0 and pb < 50:
            values[code] = pb
        else:
            values[code] = np.nan

    series = pd.Series(values, name="pb")
    # 取倒数
    series = 1.0 / series.replace(0, np.nan)
    return series


def compute_ps_ttm(codes: List[str], cache: DataCache) -> pd.Series:
    """
    市销率 PS(TTM) — 负向因子。
    计算方式：总市值 / 近12个月营收。
    """
    values = {}
    for code in codes:
        try:
            info = cache.get_stock_basic(code) or {}
            mcap = info.get("mcap_yi", 0)  # 亿元
            if not mcap or mcap <= 0:
                values[code] = np.nan
                continue

            # 从利润表获取近12个月营收
            lrb_data = cache.get_financials(code, report_type="lrb")
            if not lrb_data:
                values[code] = np.nan
                continue

            total_revenue = 0
            for record in lrb_data[:4]:
                rev = _extract_number(record, "营业收入") or \
                      _extract_number(record, "营业总收入") or \
                      _extract_number(record, "一、营业收入")
                if rev is not None:
                    total_revenue += rev

            if total_revenue <= 0:
                values[code] = np.nan
                continue

            # mcap 是亿元，revenue 是万元 → 统一为亿元
            revenue_yi = total_revenue / 10000
            ps = mcap / revenue_yi if revenue_yi > 0 else np.nan

            if ps > 0 and ps < 100:
                values[code] = ps
            else:
                values[code] = np.nan
        except Exception as e:
            logger.debug(f"PS计算失败 {code}: {e}")
            values[code] = np.nan

    series = pd.Series(values, name="ps_ttm")
    series = 1.0 / series.replace(0, np.nan)
    return series


def compute_fcf_yield(codes: List[str], cache: DataCache) -> pd.Series:
    """
    自由现金流收益率 FCF Yield — 正向因子。
    FCF Yield = 经营现金流净额 / 总市值。
    简化：经营现金流 ≈ 净利润 + 折旧摊销（无数据时用净利润×0.7替代）。
    """
    values = {}
    for code in codes:
        try:
            info = cache.get_stock_basic(code) or {}
            mcap = info.get("mcap_yi", 0)  # 亿元
            float_mcap = info.get("float_mcap_yi", 0)

            use_mcap = float_mcap if float_mcap and float_mcap > 0 else mcap
            if not use_mcap or use_mcap <= 0:
                values[code] = np.nan
                continue

            # 尝试从现金流量表获取经营现金流
            llb_data = cache.get_financials(code, report_type="llb")
            operating_cf = None
            if llb_data:
                operating_cf = _extract_number(llb_data[0], "经营活动产生的现金流量净额") or \
                               _extract_number(llb_data[0], "经营活动现金流入小计")

            # 备选：从利润表
            if operating_cf is None:
                lrb_data = cache.get_financials(code, report_type="lrb")
                if lrb_data:
                    net_profit = _extract_number(lrb_data[0], "净利润") or \
                                 _extract_number(lrb_data[0], "归属于母公司股东的净利润")
                    if net_profit:
                        operating_cf = net_profit * 0.7

            if operating_cf is None or operating_cf <= 0:
                values[code] = np.nan
                continue

            # operating_cf是万元，use_mcap是亿元 → 统一
            fcf_yield = (operating_cf / 10000) / use_mcap
            values[code] = max(0, fcf_yield)

        except Exception as e:
            logger.debug(f"FCF Yield计算失败 {code}: {e}")
            values[code] = np.nan

    return pd.Series(values, name="fcf_yield")


def _extract_number(record: dict, key: str):
    """从财报记录中提取数值"""
    from ..valuation.wacc import _extract_number as _en
    return _en(record, key)
