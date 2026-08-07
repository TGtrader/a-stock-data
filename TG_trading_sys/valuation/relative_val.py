"""
相对估值模型
============
PE-PEG 估值 / PB-ROE 估值 / 行业分位数估值 / 研报目标价汇总

PEG方法：
  合理 PE = 未来3年EPS CAGR × 100
  PEG = PE(TTM) / EPS_CAGR
  PEG < 1.0 → 低估，PEG > 2.0 → 高估

PB-ROE方法：
  合理 PB = ROE / (Ke - g)（基于戈登增长模型变形）
  或 简化：合理 PB = (ROE / 8%) × 行业平均PB
"""

import logging
from typing import Optional, List
from datetime import datetime

from ..data.cache import DataCache
from ..core.config import Config
from .earnings_forecast import get_earnings_forecast
from .wacc import estimate_wacc

logger = logging.getLogger("tg.val.relative")


def relative_value(code: str) -> dict:
    """
    综合相对估值。

    Returns:
        {
            "peg_value": dict,           # PEG估值结果
            "pb_roe_value": dict,        # PB-ROE估值结果
            "industry_percentile": dict, # 行业分位数
            "research_consensus": dict,  # 研报目标价汇总
            "final_estimate": float,     # 综合相对估值
        }
    """
    cache = DataCache()
    basic_info = cache.get_stock_basic(code) or {}
    name = basic_info.get("name", code)
    pe_ttm = basic_info.get("pe_ttm", 0)
    pb = basic_info.get("pb", 0)
    mcap = basic_info.get("mcap_yi", 0)  # 亿元

    # ── 一致预期 ──
    earnings = get_earnings_forecast(code)
    eps_cagr = earnings.get("cagr_3y", 0)
    trailing_eps = earnings.get("trailing_eps")

    # ── PEG 估值 ──
    peg_result = _peg_valuation(pe_ttm, eps_cagr, trailing_eps)

    # ── PB-ROE 估值 ──
    pb_roe_result = _pb_roe_valuation(cache, code, pb, basic_info)

    # ── 行业分位数 ──
    industry_pct = _industry_percentile(cache, code, pe_ttm, pb, basic_info)

    # ── 研报目标价汇总 ──
    research = _research_consensus(earnings.get("research_targets", []))

    # ── 综合估值 ──
    values = []
    weights = []
    if peg_result.get("fair_value"):
        values.append(peg_result["fair_value"])
        weights.append(0.35)
    if pb_roe_result.get("fair_value"):
        values.append(pb_roe_result["fair_value"])
        weights.append(0.25)
    if research.get("avg_target"):
        values.append(research["avg_target"])
        weights.append(0.40)

    # 调整权重（缺失来源按比例重新分配）
    if values:
        total_w = sum(weights)
        weights = [w / total_w for w in weights]
        final_estimate = sum(v * w for v, w in zip(values, weights))
    else:
        final_estimate = None

    return {
        "code": code,
        "name": name,
        "date": datetime.now().strftime("%Y-%m-%d"),
        "pe_ttm": pe_ttm,
        "pb": pb,
        "market_cap_yi": mcap,
        "eps_cagr": round(eps_cagr * 100, 1) if eps_cagr else None,
        "trailing_eps": trailing_eps,
        "peg_value": peg_result,
        "pb_roe_value": pb_roe_result,
        "industry_percentile": industry_pct,
        "research_consensus": research,
        "final_estimate": round(final_estimate, 2) if final_estimate else None,
    }


def peg_value(pe_ttm: float, eps_cagr: float, trailing_eps: float = None) -> dict:
    """PE-PEG 估值（独立调用）"""
    return _peg_valuation(pe_ttm, eps_cagr, trailing_eps)


def pb_roe_value(cache: DataCache = None, code: str = "", pb: float = 0,
                 basic_info: dict = None) -> dict:
    """PB-ROE 估值（独立调用）"""
    if cache is None:
        cache = DataCache()
    if not basic_info:
        basic_info = cache.get_stock_basic(code) or {}
    return _pb_roe_valuation(cache, code, pb, basic_info)


def _peg_valuation(pe_ttm: float, eps_cagr: float, trailing_eps: float = None) -> dict:
    """PEG 估值方法"""
    if not pe_ttm or pe_ttm <= 0 or not eps_cagr or eps_cagr <= 0:
        return {
            "peg": None,
            "fair_pe": None,
            "fair_value": None,
            "verdict": "数据不足"
        }

    cagr_pct = eps_cagr * 100
    peg = pe_ttm / cagr_pct

    # 合理 PE = EPS增速 × PEG标准（1.0）
    fair_pe = cagr_pct * 1.0

    if trailing_eps and trailing_eps > 0:
        fair_value = fair_pe * trailing_eps
    else:
        fair_value = None

    # 判断
    if peg < 0.5:
        verdict = "极度低估"
    elif peg < 0.8:
        verdict = "低估"
    elif peg < 1.2:
        verdict = "合理"
    elif peg < 2.0:
        verdict = "高估"
    else:
        verdict = "严重高估"

    return {
        "peg": round(peg, 2),
        "fair_pe": round(fair_pe, 1),
        "fair_value": round(fair_value, 2) if fair_value else None,
        "verdict": verdict,
        "detail": f"PE={pe_ttm:.1f}, EPS CAGR={cagr_pct:.1f}%, PEG={peg:.2f}"
    }


def _pb_roe_valuation(cache: DataCache, code: str, pb: float,
                      basic_info: dict = None) -> dict:
    """PB-ROE 估值方法"""
    if not pb or pb <= 0:
        return {"fair_pb": None, "fair_value": None, "verdict": "数据不足"}

    # 从利润表获取 ROE
    roe = _extract_roe(cache, code)

    if roe is None or roe <= 0:
        return {
            "pb": pb,
            "roe": None,
            "fair_pb": None,
            "fair_value": None,
            "verdict": "ROE数据不足"
        }

    roe_pct = roe * 100

    # 获取 WACC 中的 Ke（股权成本）用于 PB-ROE 模型
    wacc_data = estimate_wacc(code)
    ke = wacc_data.get("ke", 0.09)

    # 合理 PB = (ROE - g) / (Ke - g)
    g = Config.PERPETUAL_GROWTH_RATE
    if ke > g:
        fair_pb = (roe - g) / (ke - g)
        fair_pb = max(0.5, fair_pb)  # PB 至少 0.5
    else:
        # 简化方法：合理 PB = ROE / 8%
        fair_pb = roe / 0.08

    # 每股净资产
    nav_per_share = _extract_nav_per_share(cache, code)

    if nav_per_share and nav_per_share > 0:
        fair_value = fair_pb * nav_per_share
    else:
        fair_value = None

    # 判断
    if pb < fair_pb * 0.7:
        verdict = "低估"
    elif pb < fair_pb * 1.3:
        verdict = "合理"
    else:
        verdict = "高估"

    return {
        "pb": round(pb, 2),
        "roe_pct": round(roe_pct, 1),
        "fair_pb": round(fair_pb, 2),
        "fair_value": round(fair_value, 2) if fair_value else None,
        "verdict": verdict,
        "detail": f"ROE={roe_pct:.1f}%, PB={pb:.2f}, 合理PB={fair_pb:.2f}"
    }


def _extract_roe(cache: DataCache, code: str) -> Optional[float]:
    """
    计算 ROE = 归母净利润 / 归母股东权益

    优先使用同花顺 EPS × 总股本（避免新浪累计值陷阱）。
    """
    # ── 方法1：同花顺历史 EPS（最可靠）──
    ths = cache.get_consensus_eps(code)
    basic_info = cache.get_stock_basic(code) or {}
    total_shares = basic_info.get("total_shares", 0)

    if ths and ths.get("historical") and total_shares and total_shares > 0:
        sorted_hist = sorted(ths["historical"], key=lambda x: x["year"], reverse=True)
        for h in sorted_hist:
            if h.get("eps") and h["eps"] > 0:
                trailing_np = h["eps"] * total_shares  # 万元
                # 获取对应权益
                fzb_data = cache.get_financials(code, report_type="fzb")
                if fzb_data:
                    equity = _extract_number(fzb_data[0], "归属于母公司股东权益合计") or \
                             _extract_number(fzb_data[0], "股东权益合计") or \
                             _extract_number(fzb_data[0], "所有者权益合计")
                    if equity and equity > 0:
                        return trailing_np / equity
                break

    # ── 方法2：新浪财报（仅用最新一期年报，避免累计值叠加）──
    lrb_data = cache.get_financials(code, report_type="lrb")
    fzb_data = cache.get_financials(code, report_type="fzb")
    if not lrb_data or not fzb_data:
        return None

    # 找最新一期年报（报告期以 1231 结尾）
    annual_np = None
    for record in lrb_data:
        rp = record.get("report_date", "")
        if rp and "12-31" in rp:
            np_val = _extract_number(record, "归属于母公司股东的净利润") or \
                     _extract_number(record, "净利润")
            if np_val is not None:
                annual_np = np_val
                break

    # 如果没找到年报，取最新一期
    if annual_np is None:
        np_val = _extract_number(lrb_data[0], "归属于母公司股东的净利润") or \
                 _extract_number(lrb_data[0], "净利润")
        annual_np = np_val

    equity = _extract_number(fzb_data[0], "归属于母公司股东权益合计") or \
             _extract_number(fzb_data[0], "股东权益合计") or \
             _extract_number(fzb_data[0], "所有者权益合计")

    if not equity or equity <= 0 or not annual_np or annual_np <= 0:
        return None

    return annual_np / equity


def _extract_nav_per_share(cache: DataCache, code: str) -> Optional[float]:
    """计算每股净资产"""
    fzb_data = cache.get_financials(code, report_type="fzb")
    if not fzb_data:
        return None

    equity = _extract_number(fzb_data[0], "归属于母公司股东权益合计") or \
             _extract_number(fzb_data[0], "所有者权益合计")

    basic_info = cache.get_stock_basic(code) or {}
    total_shares = basic_info.get("total_shares", 0)

    if equity and total_shares and total_shares > 0:
        return equity / total_shares
    return None


def _industry_percentile(cache: DataCache, code: str, pe_ttm: float, pb: float,
                         basic_info: dict = None) -> dict:
    """
    判断当前 PE/PB 在同行业中的分位水平。

    简化版：获取板块龙头股的 PE/PB 做粗略对比。
    完整版（Phase 2 多因子选股时实现）：全行业分位数计算。
    """
    if not basic_info:
        basic_info = cache.get_stock_basic(code) or {}

    industry = basic_info.get("industry", "")

    return {
        "industry": industry or "未知行业",
        "pe_ttm": pe_ttm,
        "pb": pb,
        "pe_percentile": None,  # Phase 2 实现
        "pb_percentile": None,  # Phase 2 实现
        "note": "行业分位数需 Phase 2 因子模块支持（全市场数据批量获取后计算）",
    }


def _research_consensus(targets: List[dict]) -> dict:
    """汇总研报目标价"""
    if not targets:
        return {
            "count": 0,
            "avg_target": None,
            "high_target": None,
            "low_target": None,
            "median_target": None,
            "ratings_summary": {},
        }

    prices = [t["target_price"] for t in targets if t.get("target_price")]
    if not prices:
        return {"count": len(targets), "avg_target": None}

    # 评级分布
    ratings = {}
    for t in targets:
        r = t.get("rating", "未评级")
        ratings[r] = ratings.get(r, 0) + 1

    prices.sort()
    return {
        "count": len(prices),
        "avg_target": round(sum(prices) / len(prices), 2),
        "high_target": round(max(prices), 2),
        "low_target": round(min(prices), 2),
        "median_target": round(prices[len(prices) // 2], 2),
        "ratings_summary": ratings,
    }


def _extract_number(record: dict, key: str) -> Optional[float]:
    from .wacc import _extract_number as _en
    return _en(record, key)
