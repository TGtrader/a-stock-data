"""
DCF 两阶段现金流折现估值模型
============================
阶段一：显式预测期（默认5年）
阶段二：终值期（永续增长模型）

核心公式：
  企业价值 = Σ(FCF_t / (1+WACC)^t) + 终值/(1+WACC)^n
  股权价值 = 企业价值 - 净债务
  每股内在价值 = 股权价值 / 总股本

FCF（自由现金流）估算路径：
  FCF = 息前税后营业利润 - 资本支出 - 营运资本增加
  ≈ 经营现金流净额 - 资本支出
  （简化：用净利润 × (1-再投资率)，再投资率基于历史增长推算）
"""

import logging
from typing import Optional, Tuple
import numpy as np
import pandas as pd
from datetime import datetime

from ..core.config import Config
from ..data.cache import DataCache
from .wacc import estimate_wacc
from .earnings_forecast import get_earnings_forecast

logger = logging.getLogger("tg.val.dcf")


def dcf_value(
    code: str,
    wacc: float = None,
    growth_rates: list = None,
    fcf_base: float = None,
    trailing_eps: float = None,
    total_shares: float = None,
    explicit_years: int = None,
    terminal_growth: float = None,
) -> dict:
    """
    两阶段 DCF 估值。

    Args:
        code: 股票代码
        wacc: 折现率（None=自动估算）
        growth_rates: 各年增长率（None=从一致预期推算）
        fcf_base: 基准自由现金流（None=从财报推算）
        trailing_eps: TTM EPS（None=从财报提取）
        total_shares: 总股本（万股，None=自动获取）
        explicit_years: 显式预测年数
        terminal_growth: 永续增长率

    Returns:
        DCF 估值结果 dict
    """
    if explicit_years is None:
        explicit_years = Config.EXPLICIT_FORECAST_YEARS
    if terminal_growth is None:
        terminal_growth = Config.PERPETUAL_GROWTH_RATE

    cache = DataCache()

    # ── 1. 获取基础数据 ──
    # 总股本
    if total_shares is None:
        basic = cache.get_stock_basic(code) or {}
        total_shares = basic.get("total_shares", 0)
        if not total_shares or total_shares <= 0:
            # 从腾讯行情获取
            info = cache._fetch_tencent_basic(code) or {}
            total_shares = info.get("total_shares", 0)

    # EPS & 增长率
    earnings = get_earnings_forecast(code)
    if trailing_eps is None:
        trailing_eps = earnings.get("trailing_eps")
    if growth_rates is None:
        growth_rates = earnings.get("growth_rates", [])

    # WACC
    if wacc is None:
        wacc_result = estimate_wacc(code)
        wacc = wacc_result.get("wacc", 0.09)
    else:
        wacc_result = {}

    # FCF 基准
    if fcf_base is None:
        # 【修复1】提前估算平均增长率，用于动态再投资率计算
        _pre_growth = growth_rates if growth_rates else earnings.get("growth_rates", [])
        avg_g = sum(_pre_growth[:2]) / min(2, max(1, len(_pre_growth))) if _pre_growth else 0.10
        fcf_base, fcf_detail = _estimate_base_fcf(cache, code, trailing_eps, total_shares, avg_g)
    else:
        fcf_detail = {"method": "用户指定"}

    # ── 单位标准化：所有财务值统一为万元 ──
    # 如果 fcf_base 异常大（> 每股合理值 × 总股本 × 100），尝试缩放到合理范围
    if total_shares and total_shares > 0 and trailing_eps and trailing_eps > 0:
        expected_fcf_range = trailing_eps * total_shares * 2  # FCF 上限约为净利润 × 2
        if fcf_base > expected_fcf_range * 10:
            # 单位可能不匹配，用 EPS × 总股本 × 0.7 兜底
            fcf_base = trailing_eps * total_shares * 0.7
            fcf_detail = {"method": "EPS × 总股本 × 0.7（单位异常兜底）",
                          "trailing_eps": trailing_eps, "total_shares": total_shares}
            logger.warning(f"[{code}] FCF 基准异常大，使用兜底估算: {fcf_base:.0f} 万元")

    # 如果没有增长率和EPS，使用历史增速推算
    if not growth_rates and trailing_eps and trailing_eps > 0:
        growth_rates = _estimate_historical_growth(cache, code, explicit_years)

    # 如果仍然没有，设默认
    if not growth_rates:
        growth_rates = [0.10] * explicit_years  # 默认 10%

    # ── 【修复2】增长预测硬上限 ──
    growth_rates = list(growth_rates)  # 确保可变
    for i in range(len(growth_rates)):
        if i == 0:
            growth_rates[i] = min(growth_rates[i], 0.25)  # Year 1: max 25%
        elif i <= 2:
            growth_rates[i] = min(growth_rates[i], 0.20)  # Year 2-3: max 20%
        else:
            growth_rates[i] = min(growth_rates[i], 0.15)  # Year 4-5: max 15%

    # 【修复2】前2年平均增长>20% → 调低永续增长率（高速增长难以永续）
    if len(growth_rates) >= 2:
        avg_first_2 = (growth_rates[0] + growth_rates[1]) / 2
        if avg_first_2 > 0.20 and terminal_growth == Config.PERPETUAL_GROWTH_RATE:
            terminal_growth = 0.025  # 从3.0%降至2.5%
            logger.info(f"[{code}] 前2年平均增长 {avg_first_2*100:.1f}%>20%，永续增长率调整至 2.5%")

    # ── 2. 显式预测期 ──
    explicit_fcfs = []
    explicit_pv = 0
    current_fcf = fcf_base

    for i in range(explicit_years):
        g = growth_rates[i] if i < len(growth_rates) else growth_rates[-1]
        current_fcf = current_fcf * (1 + g)
        discount_factor = (1 + wacc) ** (i + 1)
        pv = current_fcf / discount_factor
        explicit_fcfs.append({
            "year": i + 1,
            "growth_rate": round(g * 100, 1),
            "fcf": round(current_fcf, 2),
            "pv": round(pv, 2),
        })
        explicit_pv += pv

    # ── 3. 终值 ──
    final_fcf = current_fcf
    # 安全检查：WACC 与永续增长率必须有足够利差，否则终值趋于无穷
    spread = wacc - terminal_growth
    min_spread = 0.04  # 最少 4% 利差（修复：从2%提升至4%，避免终值爆炸）
    if spread < min_spread:
        logger.warning(
            f"DCF: WACC({wacc*100:.2f}%) 与永续g({terminal_growth*100:.1f}%) "
            f"利差仅 {spread*100:.2f}%，低于安全阈值 {min_spread*100:.0f}%，"
            f"调整 WACC 至 {terminal_growth*100 + min_spread*100:.2f}%"
        )
        wacc = terminal_growth + min_spread
        spread = min_spread

    terminal_value = final_fcf * (1 + terminal_growth) / spread
    terminal_pv = terminal_value / (1 + wacc) ** explicit_years

    # ── 4. 企业价值 → 股权价值 → 每股价值 ──
    enterprise_value = explicit_pv + terminal_pv

    # 【修复3】终值占比自动纠偏：若>80%，提高WACC直至终值占比<=80%
    tv_ratio = terminal_pv / enterprise_value if enterprise_value > 0 else 0
    if tv_ratio > Config.TERMINAL_VALUE_MAX_RATIO:
        tv_warning_auto = (
            f"终值占比 {tv_ratio*100:.1f}% > {Config.TERMINAL_VALUE_MAX_RATIO*100:.0f}%，"
            f"自动提升WACC使其<=80%"
        )
        logger.warning(f"[{code}] {tv_warning_auto}")
        # 迭代提升WACC，每次+1%，最多迭代5次
        wacc_original = wacc
        for _ in range(5):
            wacc += 0.01
            spread = wacc - terminal_growth
            if spread < min_spread:
                wacc = terminal_growth + min_spread
                spread = min_spread
            # 重新计算终值和现值
            terminal_value_new = final_fcf * (1 + terminal_growth) / spread
            terminal_pv_new = terminal_value_new / (1 + wacc) ** explicit_years
            # 重新计算显式期PV（WACC变了）
            explicit_pv_new = 0
            cf_iter = fcf_base
            for i in range(explicit_years):
                g_iter = growth_rates[i] if i < len(growth_rates) else growth_rates[-1]
                cf_iter = cf_iter * (1 + g_iter)
                explicit_pv_new += cf_iter / (1 + wacc) ** (i + 1)
            ev_new = explicit_pv_new + terminal_pv_new
            tv_ratio_new = terminal_pv_new / ev_new if ev_new > 0 else 0
            if tv_ratio_new <= Config.TERMINAL_VALUE_MAX_RATIO:
                # 接受新估值
                explicit_pv = explicit_pv_new
                for j, item in enumerate(explicit_fcfs):
                    item["pv"] = round(fcf_base * (1+growth_rates[0]) if j==0 else item["fcf"], 2)
                terminal_value = terminal_value_new
                terminal_pv = terminal_pv_new
                enterprise_value = ev_new
                tv_ratio = tv_ratio_new
                break
        else:
            # 迭代5次仍超80%，使用最后一次结果
            enterprise_value = ev_new
            tv_ratio = tv_ratio_new

    # 终值占比检查（现在只是信息性警告）
    if tv_ratio > Config.TERMINAL_VALUE_MAX_RATIO:
        tv_warning = f"终值占比 {tv_ratio*100:.1f}%，超出 {Config.TERMINAL_VALUE_MAX_RATIO*100:.0f}% 警告线，增长假设可能过于乐观"
    else:
        tv_warning = None

    # ── 5. 净债务 + 股权价值 + 每股价值 ──
    net_debt = _estimate_net_debt(cache, code)
    equity_value = enterprise_value - net_debt

    if total_shares and total_shares > 0:
        per_share_value = equity_value / total_shares
    else:
        per_share_value = None

    return {
        "enterprise_value": round(enterprise_value, 2),
        "equity_value": round(equity_value, 2),
        "net_debt": round(net_debt, 2),
        "per_share_value": round(per_share_value, 2) if per_share_value else None,
        "wacc": round(wacc * 100, 2),  # 百分比
        "terminal_growth": round(terminal_growth * 100, 1),
        "terminal_value": round(terminal_value, 2),
        "terminal_pv": round(terminal_pv, 2),
        "terminal_value_ratio": round(tv_ratio * 100, 1),
        "terminal_value_warning": tv_warning,
        "explicit_pv": round(explicit_pv, 2),
        "explicit_cashflows": explicit_fcfs,
        "fcf_base": round(fcf_base, 2),
        "fcf_detail": fcf_detail,
        "trailing_eps": trailing_eps,
        "growth_rates_used": [round(g * 100, 1) for g in growth_rates[:explicit_years]],
        "wacc_detail": wacc_result,
        "total_shares": total_shares,
    }


def _estimate_base_fcf(
    cache: DataCache, code: str, trailing_eps: float, total_shares: float,
    avg_growth_rate: float = None
) -> Tuple[float, dict]:
    """
    从财报估算基准 FCF（自由现金流）。

    优先级：
    1. 从现金流量表取「经营活动产生的现金流量净额」-「购建固定资产」
    2. 从利润表用简化公式：净利润 × (1 - 动态再投资率)
    3. 用 TTM EPS × 总股本 × 0.7（70%现金转化率）

    【修复1】再投资率不再是固定20%，而是基于增长/ROE动态估算。
    【修复4】CFO方法与NI方法交叉验证，差距>3×时加权平均。
    """
    # ── 先计算NI-based FCF（用于交叉验证）──
    ni_fcf = None
    roe_estimate = _extract_roe_for_reinvestment(cache, code)
    if trailing_eps and total_shares and total_shares > 0:
        net_income = trailing_eps * total_shares
        # 【修复1】动态再投资率: g/ROE, bounded [15%, 80%]
        if avg_growth_rate is None:
            avg_growth_rate = 0.10  # 默认10%
        avg_growth_rate = max(0.03, min(0.25, avg_growth_rate))
        if roe_estimate and roe_estimate > 0.05:
            reinvestment_rate = avg_growth_rate / roe_estimate
        else:
            reinvestment_rate = avg_growth_rate / 0.15  # ROE未知时假设15%
        reinvestment_rate = max(0.15, min(0.80, reinvestment_rate))
        ni_fcf = net_income * (1 - reinvestment_rate)
        if ni_fcf <= 0:
            ni_fcf = None

    # ── 方法1：现金流量表 ──
    cfo_fcf = None
    llb_data = cache.get_financials(code, report_type="llb")
    if llb_data:
        latest = llb_data[0]
        operating_cf = _extract_cashflow_item(latest,
            ["经营活动产生的现金流量净额", "经营活动现金流入小计", "一、经营活动产生的现金流量"])
        capex = _extract_cashflow_item(latest,
            ["购建固定无形长期资产支付的现金", "购建固定资产、无形资产和其他长期资产支付的现金"])

        if operating_cf is not None:
            if capex is not None and capex > 0:
                cfo_fcf = operating_cf - capex
            else:
                cfo_fcf = operating_cf * 0.7

    # 【修复4】CFO与NI交叉验证
    if cfo_fcf is not None and cfo_fcf > 0 and ni_fcf is not None and ni_fcf > 0:
        if cfo_fcf > ni_fcf * 3:
            # CFO异常高于NI，取加权平均（CFO=60%, NI=40%）
            fcf = cfo_fcf * 0.6 + ni_fcf * 0.4
            detail = {
                "method": "CFO/NI加权（CFO×0.6+NI×0.4，CFO>3×NI异常）",
                "operating_cf": round(operating_cf, 2) if operating_cf else 0,
                "ni_fcf": round(ni_fcf, 2),
                "cfo_fcf": round(cfo_fcf, 2),
                "reinvestment_rate": reinvestment_rate,
            }
            logger.info(f"[{code}] CFO_FCF({cfo_fcf:.0f}) > 3× NI_FCF({ni_fcf:.0f})，加权平均 → {fcf:.0f}")
            return fcf, detail
        elif cfo_fcf < ni_fcf * 0.3:
            # CFO异常低于NI，使用NI方法（CFO可能受营运资本波动影响）
            logger.info(f"[{code}] CFO_FCF({cfo_fcf:.0f}) < 0.3× NI_FCF({ni_fcf:.0f})，使用NI方法")
            return ni_fcf, {
                "method": f"CFO异常低→NI×(1-{reinvestment_rate*100:.0f}%再投资率)",
                "net_income": round(net_income, 2),
                "reinvestment_rate": reinvestment_rate,
            }

    # 优先返回CFO方法
    if cfo_fcf is not None and cfo_fcf > 0:
        return cfo_fcf, {
            "method": "CFO - CapEx" if (capex is not None and capex > 0) else "CFO×0.7",
            "operating_cf": round(operating_cf, 2) if operating_cf else 0,
            "capex": round(capex, 2) if (capex is not None and capex > 0) else 0,
        }

    # ── 方法2：净利润 × (1-动态再投资率) ──
    if ni_fcf is not None and ni_fcf > 0:
        return ni_fcf, {
            "method": f"净利润 × (1-{reinvestment_rate*100:.0f}%再投资率)",
            "net_income": round(net_income, 2),
            "reinvestment_rate": reinvestment_rate,
            "roe_used": roe_estimate,
            "growth_used": avg_growth_rate,
        }

    # ── 方法3：兜底 ──
    if trailing_eps and total_shares and total_shares > 0:
        fcf = trailing_eps * total_shares * 0.7
        return fcf, {"method": "EPS × 总股本 × 0.7（兜底估算）"}

    return 0, {"method": "无法估算，返回0"}


def _estimate_net_debt(cache: DataCache, code: str) -> float:
    """
    从资产负债表估算净债务。

    净债务 = 短期借款 + 长期借款 + 应付债券 + 一年内到期非流动负债 - 货币资金
    """
    fzb_data = cache.get_financials(code, report_type="fzb")
    if not fzb_data:
        return 0

    latest = fzb_data[0]

    short_borrow = _extract_number(latest, "短期借款") or 0
    long_borrow = _extract_number(latest, "长期借款") or 0
    bonds_payable = _extract_number(latest, "应付债券") or 0
    noncurrent_1y = _extract_number(latest, "一年内到期的非流动负债") or 0
    cash = _extract_number(latest, "货币资金") or 0

    total_debt = short_borrow + long_borrow + bonds_payable + noncurrent_1y
    net_debt = total_debt - cash
    return net_debt


def _estimate_historical_growth(cache: DataCache, code: str, years: int = 5) -> list:
    """
    从历史净利润推算增长率（作为无一致预期时的后备方案）。

    用最近4个季度的净利润同比增长推算未来增长率。
    """
    lrb_data = cache.get_financials(code, report_type="lrb")
    if not lrb_data or len(lrb_data) < 2:
        return [0.05] * years

    # 简单方法：比较最近两期归母净利润增长率
    np_current = _extract_number(lrb_data[0], "归属于母公司股东的净利润") or \
                 _extract_number(lrb_data[0], "净利润")
    np_prev = _extract_number(lrb_data[1], "归属于母公司股东的净利润") or \
              _extract_number(lrb_data[1], "净利润")

    if np_current and np_prev and np_prev != 0:
        hist_growth = (np_current - np_prev) / abs(np_prev)
        hist_growth = max(-0.20, min(0.25, hist_growth))  # 【修复2】上限从40%→25%

        # 渐近回归到 5%
        rates = []
        for i in range(years):
            decay = (years - 1 - i) / (years - 1) if years > 1 else 0
            rate = hist_growth * decay + 0.05 * (1 - decay)
            rates.append(round(rate, 4))
        return rates

    return [0.05] * years


def _extract_roe_for_reinvestment(cache: DataCache, code: str) -> Optional[float]:
    """
    提取ROE用于动态再投资率计算。

    复用缓存层数据，避免重复拉取。
    """
    basic_info = cache.get_stock_basic(code) or {}
    total_shares = basic_info.get("total_shares", 0)
    if not total_shares or total_shares <= 0:
        return None

    # 优先：同花顺历史EPS
    ths = cache.get_consensus_eps(code)
    if ths and ths.get("historical") and total_shares > 0:
        sorted_hist = sorted(ths["historical"], key=lambda x: x["year"], reverse=True)
        for h in sorted_hist:
            if h.get("eps") and h["eps"] > 0:
                trailing_np = h["eps"] * total_shares
                fzb_data = cache.get_financials(code, report_type="fzb")
                if fzb_data:
                    equity = (_extract_number(fzb_data[0], "归属于母公司股东权益合计") or
                             _extract_number(fzb_data[0], "股东权益合计") or
                             _extract_number(fzb_data[0], "所有者权益合计"))
                    if equity and equity > 0:
                        return trailing_np / equity
                break

    # 备选：新浪财报（年频）
    lrb_data = cache.get_financials(code, report_type="lrb")
    fzb_data = cache.get_financials(code, report_type="fzb")
    if lrb_data and fzb_data:
        annual_np = None
        for record in lrb_data:
            rp = record.get("report_date", "")
            if rp and "12-31" in rp:
                np_val = (_extract_number(record, "归属于母公司股东的净利润") or
                         _extract_number(record, "净利润"))
                if np_val is not None:
                    annual_np = np_val
                    break
        if annual_np is None:
            np_val = (_extract_number(lrb_data[0], "归属于母公司股东的净利润") or
                     _extract_number(lrb_data[0], "净利润"))
            annual_np = np_val

        equity = (_extract_number(fzb_data[0], "归属于母公司股东权益合计") or
                 _extract_number(fzb_data[0], "股东权益合计") or
                 _extract_number(fzb_data[0], "所有者权益合计"))
        if equity and equity > 0 and annual_np and annual_np > 0:
            return annual_np / equity

    return None


def _extract_cashflow_item(record: dict, keys: list) -> Optional[float]:
    """从现金流量表记录中按优先级匹配科目值。数据已在缓存层归一化为万元。"""
    for key in keys:
        val = record.get(key)
        if val is not None:
            try:
                if isinstance(val, str):
                    val = val.replace(",", "").strip()
                    if "万" in val:
                        return float(val.replace("万", ""))
                    elif "亿" in val:
                        return float(val.replace("亿", "")) * 10000
                    else:
                        return float(val)
                return float(val)
            except (ValueError, TypeError):
                continue
    return None


def _extract_number(record: dict, key: str) -> Optional[float]:
    from .wacc import _extract_number as _en
    return _en(record, key)
