"""
质量因子 — ROE / 毛利率 / 资产负债率 / 现金流质量 / ROE稳定性
=============================================================
衡量企业盈利质量和财务稳健性的因子。
"""

import logging
from typing import List, Optional
import pandas as pd
import numpy as np

from ..data.cache import DataCache

logger = logging.getLogger("tg.factor.quality")


def compute_roe(codes: List[str], cache: DataCache) -> pd.Series:
    """
    ROE（净资产收益率）— 正向因子。
    从利润表+资产负债表计算近12个月 ROE。
    """
    values = {}
    for code in codes:
        try:
            lrb_data = cache.get_financials(code, report_type="lrb")
            fzb_data = cache.get_financials(code, report_type="fzb")

            if not lrb_data or not fzb_data:
                values[code] = np.nan
                continue

            # 近12个月归母净利润
            total_np = 0
            for record in lrb_data[:4]:
                np_val = _extract_np(record)
                if np_val is not None:
                    total_np += np_val

            # 归母权益（最新一期）
            equity = _extract_equity(fzb_data[0])

            if equity and equity > 0 and total_np > 0:
                roe = total_np / equity
                roe = max(-0.5, min(1.0, roe))  # [-50%, 100%]
                values[code] = roe
            else:
                values[code] = np.nan
        except Exception as e:
            logger.debug(f"ROE计算失败 {code}: {e}")
            values[code] = np.nan

    return pd.Series(values, name="roe")


def compute_gross_margin(codes: List[str], cache: DataCache) -> pd.Series:
    """
    毛利率 — 正向因子。
    (营业收入 - 营业成本) / 营业收入
    """
    values = {}
    for code in codes:
        try:
            lrb_data = cache.get_financials(code, report_type="lrb")
            if not lrb_data:
                values[code] = np.nan
                continue

            latest = lrb_data[0]
            revenue = _extract_revenue(latest)
            cost = _extract_number(latest, "营业成本") or \
                   _extract_number(latest, "一、营业成本")

            if revenue and cost and revenue > 0:
                margin = (revenue - cost) / revenue
                margin = max(-0.5, min(0.95, margin))
                values[code] = margin
            else:
                values[code] = np.nan
        except Exception as e:
            logger.debug(f"毛利率计算失败 {code}: {e}")
            values[code] = np.nan

    return pd.Series(values, name="gross_margin")


def compute_debt_ratio(codes: List[str], cache: DataCache) -> pd.Series:
    """
    资产负债率 — 负向因子（越低越好）。
    总负债 / 总资产
    """
    values = {}
    for code in codes:
        try:
            fzb_data = cache.get_financials(code, report_type="fzb")
            if not fzb_data:
                values[code] = np.nan
                continue

            latest = fzb_data[0]
            total_liability = _extract_number(latest, "负债合计") or \
                              _extract_number(latest, "总负债")
            total_equity = _extract_equity(latest)

            if total_liability is not None and total_equity is not None:
                total_assets = total_liability + total_equity
                if total_assets > 0:
                    ratio = total_liability / total_assets
                    ratio = max(0.01, min(0.99, ratio))
                    values[code] = ratio
                else:
                    values[code] = np.nan
            else:
                values[code] = np.nan
        except Exception as e:
            logger.debug(f"资产负债率计算失败 {code}: {e}")
            values[code] = np.nan

    series = pd.Series(values, name="debt_ratio")
    # 取负使越高越好（注册时 direction=negative 也会处理，这里提前反转确保一致性）
    # 标准化时会根据 direction 再次处理，这里保持原始值
    return series


def compute_cashflow_quality(codes: List[str], cache: DataCache) -> pd.Series:
    """
    现金流质量 — 正向因子。
    经营现金流净额 / 归母净利润。
    >1 说明利润含金量高，<0.5 说明利润质量差。
    """
    values = {}
    for code in codes:
        try:
            llb_data = cache.get_financials(code, report_type="llb")
            lrb_data = cache.get_financials(code, report_type="lrb")

            if not llb_data or not lrb_data:
                values[code] = np.nan
                continue

            operating_cf = _extract_number(llb_data[0], "经营活动产生的现金流量净额") or \
                           _extract_number(llb_data[0], "经营活动现金流入小计")
            net_profit = _extract_np(lrb_data[0])

            if operating_cf is not None and net_profit and net_profit != 0:
                quality = operating_cf / net_profit
                quality = max(-5.0, min(10.0, quality))  # 限制极端值
                values[code] = quality
            else:
                values[code] = np.nan
        except Exception as e:
            logger.debug(f"现金流质量计算失败 {code}: {e}")
            values[code] = np.nan

    return pd.Series(values, name="cashflow_quality")


def compute_roe_stability(codes: List[str], cache: DataCache) -> pd.Series:
    """
    ROE稳定性 — 正向因子（越稳定越好）。
    近3年ROE的标准差（取负值，使越高越好）。

    需要至少3期年报数据。
    """
    values = {}
    for code in codes:
        try:
            lrb_data = cache.get_financials(code, report_type="lrb")
            fzb_data = cache.get_financials(code, report_type="fzb")

            if not lrb_data or len(lrb_data) < 3 or not fzb_data:
                values[code] = np.nan
                continue

            # 找最近3期年报的报告期号
            annual_periods = set()
            for record in lrb_data:
                rd = record.get("report_date", "")
                if rd.endswith("1231"):
                    annual_periods.add(rd)

            if len(annual_periods) < 3:
                values[code] = np.nan
                continue

            # 对每年报计算 ROE
            roes = []
            # 取资产负债表的最新数据作为权益近似（简化）
            equity = _extract_equity(fzb_data[0])
            if not equity or equity <= 0:
                values[code] = np.nan
                continue

            for record in lrb_data:
                rd = record.get("report_date", "")
                if rd.endswith("1231"):
                    np_val = _extract_np(record)
                    if np_val and equity > 0:
                        roes.append(np_val / equity)

            if len(roes) >= 3:
                std_roe = np.std(roes[:3])
                # 取负：标准差越小越好
                values[code] = -std_roe
            else:
                values[code] = np.nan
        except Exception as e:
            logger.debug(f"ROE稳定性计算失败 {code}: {e}")
            values[code] = np.nan

    return pd.Series(values, name="roe_stability")


# ── 辅助函数 ──

def _extract_np(record: dict) -> Optional[float]:
    keys = ["归属于母公司股东的净利润", "归母净利润", "净利润"]
    return _try_keys(record, keys)


def _extract_equity(record: dict) -> Optional[float]:
    keys = ["归属于母公司股东权益合计", "股东权益合计", "所有者权益合计"]
    return _try_keys(record, keys)


def _extract_revenue(record: dict) -> Optional[float]:
    keys = ["营业收入", "营业总收入", "一、营业收入"]
    return _try_keys(record, keys)


def _extract_number(record: dict, key: str) -> Optional[float]:
    return _try_keys(record, [key])


def _try_keys(record: dict, keys: list) -> Optional[float]:
    for key in keys:
        val = record.get(key)
        if val is not None:
            try:
                if isinstance(val, str):
                    val = val.replace(",", "").strip()
                    if "万" in val:
                        val = float(val.replace("万", "")) * 10000
                    elif "亿" in val:
                        val = float(val.replace("亿", "")) * 100000000
                    else:
                        val = float(val)
                val = float(val)
                if abs(val) > 1e10:
                    val = val / 10000
                return val
            except (ValueError, TypeError):
                continue
    return None
