"""
VPA 筛选层 — 量价+趋势+资金流 三维选股扫描
===========================================
支持大盘/行业/概念板块/个股四层级的系统性量价筛选。
"""

import logging
from typing import Dict, List, Optional
from datetime import datetime

import numpy as np
import pandas as pd

try:
    from .vpa_data import get_adapter
    from .vpa_engine import vpa_analyze
except ImportError:
    from vpa_data import get_adapter
    from vpa_engine import vpa_analyze

logger = logging.getLogger("vpa.screener")


# ═══════════════════════════════════════════════════════════════
# 主筛选函数
# ═══════════════════════════════════════════════════════════════

def vpa_screen(
    universe: str = "csi300",
    trend_patterns: List[str] = None,
    vpa_patterns: List[str] = None,
    flow_patterns: List[str] = None,
    resonance_mode: str = "any",
    min_strength: int = 60,
    date: str = None,
    top_n: int = 20,
    codes: List[str] = None,
) -> List[dict]:
    """
    三维量价筛选。

    Args:
        universe: 标的范围 csi300 | csi500 | all_a | 自定义
        trend_patterns: 趋势条件 ["trend_accel", "trend_start", "pullback_done"]
        vpa_patterns: 量价形态 ["breakout_volume", "hammer", "stopping_vol_down"]
        flow_patterns: 资金流条件 ["continuous_inflow_5d", "smart_accumulate"]
        resonance_mode: any(任一匹配) | trend_vpa(趋势+量价) | all(三维全中)
        min_strength: 最低综合评分
        codes: 自定义代码列表（优先级高于 universe）

    Returns:
        按评分排序的筛选结果列表
    """
    if codes is None:
        codes = _get_universe(universe)
    if not codes:
        return []

    logger.info(f"开始筛选: universe={universe}, 共{len(codes)}只标的")

    results = []
    for i, code in enumerate(codes):
        try:
            report = vpa_analyze(code)
            if "error" in report:
                continue

            score = report["rating"]["score"]
            if score < min_strength:
                continue

            # 三维条件匹配
            matches = _check_patterns(report, trend_patterns, vpa_patterns, flow_patterns, resonance_mode)
            if not matches["passed"]:
                continue

            results.append({
                "code": code,
                "name": report.get("name", code),
                "score": score,
                "rating": report["rating"]["rating"],
                "trend_dir": report["trend"]["short_term"].get("direction", ""),
                "trend_phase": report["trend"]["short_term"].get("phase", ""),
                "phase": report["position"]["phase"].get("phase", ""),
                "resonance": report["money_flow"]["flow_trend_resonance"].get("resonance", ""),
                "matched_patterns": matches["matched"],
                "conclusion_preview": report["conclusion"][:200],
            })

            if (i + 1) % 50 == 0:
                logger.info(f"  已处理 {i+1}/{len(codes)}...")

        except Exception as e:
            logger.warning(f"筛选跳过 {code}: {e}")
            continue

    results.sort(key=lambda x: x["score"], reverse=True)
    logger.info(f"筛选完成: {len(results)} 只符合条件")

    return results[:top_n] if top_n else results


# ═══════════════════════════════════════════════════════════════
# 大盘/板块筛选
# ═══════════════════════════════════════════════════════════════

def vpa_screen_index() -> dict:
    """分析主要指数的量价状态"""
    indices = {
        "000001": "上证指数",
        "399001": "深证成指",
        "000300": "沪深300",
        "399006": "创业板指",
        "000688": "科创50",
        "000905": "中证500",
    }
    results = {}
    for code, name in indices.items():
        try:
            report = vpa_analyze(code, name=name, market="指数")
            if "error" not in report:
                results[code] = {
                    "name": name,
                    "rating": report["rating"]["rating"],
                    "score": report["rating"]["score"],
                    "trend_dir": report["trend"]["short_term"].get("direction", ""),
                    "phase": report["position"]["phase"].get("phase", ""),
                    "summary": report["trend"]["short_term"].get("summary", ""),
                }
        except Exception as e:
            logger.warning(f"指数分析失败 {code}: {e}")
    return results


def vpa_screen_sectors() -> List[dict]:
    """扫描行业板块，找出量价形态最好的板块"""
    adapter = get_adapter()
    sectors = adapter.get_sector_data(top_n=50)
    if not sectors:
        return []

    results = []
    for sector in sectors:
        try:
            bk_code = sector.get("code", "")
            if not bk_code:
                continue

            report = vpa_analyze(bk_code, name=sector.get("name", bk_code), market="行业板块")
            if "error" in report:
                continue

            results.append({
                "code": bk_code,
                "name": sector.get("name", ""),
                "change_pct": sector.get("change_pct", 0),
                "score": report["rating"]["score"],
                "rating": report["rating"]["rating"],
                "trend_dir": report["trend"]["short_term"].get("direction", ""),
                "trend_phase": report["trend"]["short_term"].get("phase", ""),
            })
        except Exception as e:
            logger.warning(f"板块分析跳过 {bk_code}: {e}")

    results.sort(key=lambda x: x["score"], reverse=True)
    return results


# ═══════════════════════════════════════════════════════════════
# 内部辅助函数
# ═══════════════════════════════════════════════════════════════

def _get_universe(universe: str) -> List[str]:
    """获取筛选范围"""
    # 常用标的池（沪深300前50只代表性股票）
    CSI300_SAMPLE = [
        "600519", "000858", "601318", "600036", "000333", "601166", "600030",
        "600887", "601012", "002475", "300750", "000002", "601398", "600276",
        "002415", "300059", "600900", "000651", "002714", "601888",
        "600585", "000568", "603259", "688981", "002594", "300274",
        "600809", "000725", "002230", "601899",
    ]
    CSI500_SAMPLE = [
        "688017", "300308", "300476", "002463", "600770", "300474",
        "688012", "300502", "002049", "603986", "688008",
    ]

    if universe == "csi300":
        return CSI300_SAMPLE
    elif universe == "csi500":
        return CSI500_SAMPLE
    elif universe == "csi300_csi500":
        return CSI300_SAMPLE + CSI500_SAMPLE
    elif universe == "test":
        return ["600519", "000858", "601318", "300750"]
    else:
        # 假设是逗号分隔的代码列表
        return [c.strip() for c in universe.split(",") if c.strip()]


def _check_patterns(report: dict, trend_pats: List[str], vpa_pats: List[str],
                    flow_pats: List[str], mode: str) -> dict:
    """
    检查报告是否匹配指定的三维条件。

    Returns:
        {"passed": bool, "matched": List[str]}
    """
    matched = []

    # 趋势条件匹配
    if trend_pats:
        trend_phase = report["trend"]["short_term"].get("phase", "")
        trend_dir = report["trend"]["short_term"].get("direction", "")
        trend_strength = report["trend"]["short_term"].get("strength", 0)

        for pat in trend_pats:
            hit = False
            if pat == "trend_start" and trend_phase == "趋势启动":
                hit = True
            elif pat == "trend_accel" and trend_phase == "趋势加速":
                hit = True
            elif pat == "uptrend" and trend_dir.startswith("上涨"):
                hit = True
            elif pat == "pullback_done" and trend_phase == "趋势匀速":
                hit = True
            elif pat == "consolidation" and trend_phase == "盘整":
                hit = True
            elif pat == "strong_trend" and trend_strength >= 70:
                hit = True

            if hit:
                matched.append(f"trend:{pat}")

    # 量价信号匹配
    if vpa_pats:
        signals_text = " ".join([
            s.get("signal", "") for s in report["signals"]["recent_signals"]
        ])
        latest_pattern = report["signals"]["latest_bar"].get("candle_pattern", "")
        latest_vpa = report["signals"]["latest_bar"].get("vpa_validation", "")

        for pat in vpa_pats:
            hit = False
            if pat == "hammer" and latest_pattern == "锤头线":
                hit = True
            elif pat == "shooting_star" and latest_pattern == "射击十字星":
                hit = True
            elif pat == "breakout_volume" and "放量突破" in signals_text:
                hit = True
            elif pat == "stopping_vol_down" and "放量止跌" in signals_text:
                hit = True
            elif pat == "stopping_vol_up" and "放量止涨" in signals_text:
                hit = True
            elif pat == "confirmed_bull" and latest_vpa == "CONFIRMED_BULL":
                hit = True

            if hit:
                matched.append(f"vpa:{pat}")

    # 资金流条件匹配
    if flow_pats:
        mf = report["money_flow"]
        divergence = mf.get("smart_retail", {}).get("divergence", "")
        flow_rating = mf.get("flow_trend_resonance", {}).get("resonance", "")
        continuous = mf.get("continuous_flow", {}).get("max_consecutive_days", 0)

        for pat in flow_pats:
            hit = False
            if pat == "continuous_inflow_5d" and continuous >= 5:
                hit = True
            elif pat == "smart_accumulate" and "吸筹" in divergence:
                hit = True
            elif pat == "flow_surge":
                ratios = mf.get("flow_ratios", {})
                if ratios.get("flow_ratio_3d", 0) and ratios["flow_ratio_3d"] > 0.3:
                    hit = True
            elif pat == "main_force_outflow_3d":
                cf = mf.get("continuous_flow", {})
                if cf.get("continuous_outflow_3d"):
                    hit = True
            elif pat == "flow_trend_resonance" and "共振" in flow_rating:
                hit = True

            if hit:
                matched.append(f"flow:{pat}")

    # 根据模式判断
    all_patterns = (trend_pats or []) + (vpa_pats or []) + (flow_pats or [])
    if not all_patterns:
        return {"passed": True, "matched": []}

    has_trend = bool(matched and any(m.startswith("trend:") for m in matched))
    has_vpa = bool(matched and any(m.startswith("vpa:") for m in matched))
    has_flow = bool(matched and any(m.startswith("flow:") for m in matched))

    if mode == "any":
        passed = len(matched) > 0
    elif mode == "trend_vpa":
        passed = has_trend or has_vpa
    elif mode == "all":
        passed = has_trend and has_vpa and has_flow
    else:
        passed = len(matched) > 0

    return {"passed": passed, "matched": matched}


# ═══════════════════════════════════════════════════════════════
# 便捷筛选函数
# ═══════════════════════════════════════════════════════════════

def screen_best_buy_signals(top_n: int = 20) -> List[dict]:
    """最强做多信号筛选——三维共振"""
    return vpa_screen(
        universe="csi300_csi500",
        trend_patterns=["trend_accel", "trend_start", "strong_trend"],
        vpa_patterns=["breakout_volume", "confirmed_bull"],
        flow_patterns=["continuous_inflow_5d", "flow_trend_resonance"],
        resonance_mode="trend_vpa",
        min_strength=55,
        top_n=top_n,
    )


def screen_smart_money_accumulating(top_n: int = 20) -> List[dict]:
    """主力吸筹但价格未动——资金领先信号"""
    return vpa_screen(
        universe="csi300_csi500",
        trend_patterns=["consolidation", "uptrend"],
        flow_patterns=["smart_accumulate", "continuous_inflow_5d"],
        resonance_mode="all",
        min_strength=40,
        top_n=top_n,
    )


def screen_risk_warnings(top_n: int = 20) -> List[dict]:
    """风险预警——趋势在涨但主力在撤"""
    return vpa_screen(
        universe="csi300_csi500",
        trend_patterns=["uptrend", "trend_accel"],
        vpa_patterns=["stopping_vol_up"],
        flow_patterns=["main_force_outflow_3d"],
        resonance_mode="any",
        min_strength=30,
        top_n=top_n,
    )
