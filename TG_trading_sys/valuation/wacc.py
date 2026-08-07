"""
WACC 加权平均资本成本自动估算
==============================
基于可获取的财务数据自动计算 WACC，不需手动输入参数。

方法：
  - 无风险利率 Rf：10年期国债收益率（Config默认2.8%，可动态从同花顺获取）
  - 股权风险溢价 ERP：Config 默认 6.5%
  - Beta β：从历史日收益率对沪深300做回归（至少60个交易日）
  - 股权成本 Ke = Rf + β × ERP
  - 债权成本 Kd：利息支出 / 总负债（从财报提取，缺失时用 4.0%）
  - 目标资本结构：D/E 从财报计算
  - WACC = Ke × E/(D+E) + Kd×(1-t) × D/(D+E)
"""

import logging
from typing import Optional, Tuple
import numpy as np
import pandas as pd

from ..core.config import Config
from ..data.cache import DataCache

logger = logging.getLogger("tg.val.wacc")


def estimate_wacc(
    code: str,
    rf: float = None,
    erp: float = None,
    tax_rate: float = 0.25,
) -> dict:
    """
    自动估算 WACC。

    Args:
        code: 股票代码
        rf: 无风险利率（None=使用Config默认 2.8%）
        erp: 股权风险溢价（None=使用Config默认 6.5%）
        tax_rate: 企业所得税率（默认25%）

    Returns:
        {
            "wacc": float,          # WACC（如 9.2%）
            "ke": float,            # 股权成本
            "kd": float,            # 债权成本（税后）
            "beta": float,          # Beta
            "rf": float,            # 无风险利率
            "erp": float,           # 股权风险溢价
            "equity_weight": float, # 权益权重
            "debt_weight": float,   # 债务权重
            "d_e_ratio": float,     # D/E 比
            "regression_r2": float, # Beta 回归 R²
            "data_points": int,     # 回归用的数据点数
            "method": str,          # 估算方法说明
        }
    """
    if rf is None:
        rf = Config.RISK_FREE_RATE
    if erp is None:
        erp = Config.EQUITY_RISK_PREMIUM

    cache = DataCache()

    # ── 1. 估算 Beta ──
    beta, r2, n_days = _estimate_beta(cache, code)

    # ── 2. 股权成本 ──
    ke = rf + beta * erp

    # ── 3. 资本结构 ──
    equity_weight, debt_weight, d_e_ratio = _estimate_capital_structure(cache, code)

    # ── 4. 债权成本 ──
    kd_pre_tax = _estimate_cost_of_debt(cache, code)
    kd_after_tax = kd_pre_tax * (1 - tax_rate)

    # ── 5. WACC ──
    wacc = ke * equity_weight + kd_after_tax * debt_weight

    return {
        "wacc": round(wacc, 4),
        "ke": round(ke, 4),
        "kd_pre_tax": round(kd_pre_tax, 4),
        "kd_after_tax": round(kd_after_tax, 4),
        "beta": round(beta, 2),
        "rf": rf,
        "erp": erp,
        "tax_rate": tax_rate,
        "equity_weight": round(equity_weight, 3),
        "debt_weight": round(debt_weight, 3),
        "d_e_ratio": round(d_e_ratio, 2),
        "regression_r2": round(r2, 3) if r2 is not None else None,
        "data_points": n_days,
        "method": f"CAPM: Ke={ke*100:.2f}% = Rf{rf*100:.1f}% + β{beta:.1f}×ERP{erp*100:.1f}%",
    }


def _estimate_beta(cache: DataCache, code: str, min_days: int = 60) -> Tuple[float, Optional[float], int]:
    """
    通过个股日收益率对沪深300日收益率做线性回归估算 Beta。

    Returns:
        (beta, r_squared, n_days)
    """
    # 获取个股K线
    stock_df = cache.get_kline(code, lookback=300)
    if stock_df is None or len(stock_df) < min_days:
        logger.warning(f"[{code}] K线不足 {min_days} 天，无法回归 Beta，使用默认 1.0")
        return 1.0, None, len(stock_df) if stock_df is not None else 0

    # 获取沪深300 K线
    index_df = cache.get_kline("000300", lookback=300)
    if index_df is None or len(index_df) < min_days:
        logger.warning(f"沪深300 K线不足，无法回归 Beta，使用默认 1.0")
        return 1.0, None, len(stock_df)

    # 计算日收益率
    stock_ret = stock_df["close"].pct_change().dropna()
    index_ret = index_df["close"].pct_change().dropna()

    # 对齐日期
    common_idx = stock_ret.index.intersection(index_ret.index)
    if len(common_idx) < min_days:
        logger.warning(f"[{code}] 与沪深300对齐后数据不足，使用默认 Beta=1.0")
        return 1.0, None, len(common_idx)

    x = index_ret.loc[common_idx].values
    y = stock_ret.loc[common_idx].values

    # 线性回归
    try:
        x_with_const = np.vstack([x, np.ones(len(x))]).T
        coef, residuals, rank, s = np.linalg.lstsq(x_with_const, y, rcond=None)
        beta = coef[0]

        # R²
        y_pred = x_with_const @ coef
        ss_res = np.sum((y - y_pred) ** 2)
        ss_tot = np.sum((y - np.mean(y)) ** 2)
        r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0

        # 限制 Beta 在合理范围 [0.2, 3.0]
        beta = max(0.2, min(3.0, beta))

        return beta, r2, len(common_idx)
    except Exception as e:
        logger.warning(f"Beta 回归失败: {e}")
        return 1.0, None, 0


def _estimate_capital_structure(cache: DataCache, code: str) -> Tuple[float, float, float]:
    """
    从资产负债表估算资本结构（权益权重/债务权重/D/E比）。

    Returns:
        (equity_weight, debt_weight, d_e_ratio)
    """
    # 从 fzb（资产负债表）获取
    fzb_data = cache.get_financials(code, report_type="fzb")
    if not fzb_data:
        logger.warning(f"[{code}] 无资产负债表数据，使用默认 80/20 资本结构")
        return 0.80, 0.20, 0.25

    latest = fzb_data[0]

    # 尝试提取关键科目
    total_equity = _extract_number(latest, "归属于母公司股东权益合计") or \
                   _extract_number(latest, "股东权益合计") or \
                   _extract_number(latest, "所有者权益合计")

    total_liability = _extract_number(latest, "负债合计") or \
                      _extract_number(latest, "总负债")

    if total_equity is None or total_liability is None:
        logger.warning(f"[{code}] 资产负债表关键科目缺失，使用默认 80/20 结构")
        return 0.80, 0.20, 0.25

    total_assets = total_equity + total_liability
    if total_assets <= 0:
        return 0.80, 0.20, 0.25

    equity_weight = total_equity / total_assets
    debt_weight = total_liability / total_assets
    d_e_ratio = total_liability / total_equity if total_equity > 0 else 0.5

    # 限制合理范围
    equity_weight = max(0.1, min(0.95, equity_weight))
    debt_weight = 1 - equity_weight
    d_e_ratio = max(0.01, min(10.0, d_e_ratio))

    return equity_weight, debt_weight, d_e_ratio


def _estimate_cost_of_debt(cache: DataCache, code: str) -> float:
    """
    从财报估算税前债务成本。

    方法：利息支出 / 总负债
    缺失时使用默认 4.0%。
    """
    lrb_data = cache.get_financials(code, report_type="lrb")
    if not lrb_data:
        return 0.04

    # 取最近4个季度的利息支出求和
    total_interest = 0
    for record in lrb_data[:4]:
        interest = _extract_number(record, "利息费用") or \
                   _extract_number(record, "财务费用")
        if interest is not None:
            total_interest += abs(interest)

    # 获取最新总负债
    fzb_data = cache.get_financials(code, report_type="fzb")
    if not fzb_data or total_interest <= 0:
        return 0.04

    total_liability = _extract_number(fzb_data[0], "负债合计") or \
                      _extract_number(fzb_data[0], "总负债")

    if total_liability is None or total_liability <= 0:
        return 0.04

    kd = total_interest / total_liability
    # 限制合理范围 [1%, 15%]
    kd = max(0.01, min(0.15, kd))

    return kd


def _extract_number(record: dict, key: str) -> Optional[float]:
    """
    从财报记录中提取数值。
    注意：新浪财报数据已由 DataCache._fetch_sina_financials 统一归一化为"万元"，
    此函数不再做单位转换。
    """
    val = record.get(key)
    if val is None:
        return None
    try:
        if isinstance(val, str):
            val = val.replace(",", "").replace("%", "").strip()
            if "万" in val:
                return float(val.replace("万", ""))
            if "亿" in val:
                return float(val.replace("亿", "")) * 10000
            if val in ("", "-", "--", "None", "null"):
                return None
            return float(val)
        return float(val)
    except (ValueError, TypeError):
        return None
