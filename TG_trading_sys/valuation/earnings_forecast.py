"""
一致预期 EPS 提取 & 成长率推算
===============================
整合同花顺一致预期 + 东财研报 EPS 预测，
输出未来 3 年的 EPS 预测序列和 CAGR。

V4.1: 新增 EPS 异常值检测 — 历史EPS异常年份标记 + 预测EPS合理性检查
"""

import logging
import statistics
from typing import Optional, List
from datetime import datetime

from ..data.cache import DataCache

logger = logging.getLogger("tg.val.earnings")


def get_earnings_forecast(code: str) -> dict:
    """
    获取个股 EPS 预测数据。

    优先级：同花顺一致预期 > 东财研报均值

    Returns:
        {
            "current_year": int,                 # 当前年份
            "eps_forecast": [eps_y1, eps_y2, eps_y3],  # 未来3年 EPS 序列
            "growth_rates": [g1, g2, g3],        # 同比增长率
            "cagr_3y": float,                    # 3年 CAGR
            "num_analysts": int,                 # 覆盖分析师数
            "source": str,                       # 数据来源
            "trailing_eps": float,               # 最近12个月 EPS
            "research_targets": [...],           # 研报目标价列表
        }
    """
    cache = DataCache()

    result = {
        "current_year": datetime.now().year,
        "eps_forecast": [],
        "growth_rates": [],
        "cagr_3y": 0.0,
        "num_analysts": 0,
        "source": "",
        "trailing_eps": None,
        "research_targets": [],
        "data_quality": {"level": "unknown", "warning": "", "adjusted_trailing_eps": None},
    }

    # ── 1. 获取 TTM EPS ──
    trailing_eps = _get_trailing_eps(cache, code)
    result["trailing_eps"] = trailing_eps

    # ── 2. 同花顺一致预期 ──
    ths = cache.get_consensus_eps(code)
    if ths:
        current_year = result["current_year"]
        eps_list = []
        for i in range(3):
            year = current_year + i
            eps_val = ths.get(f"eps_{year}")
            if eps_val and eps_val > 0:
                eps_list.append(float(eps_val))

        if eps_list:
            result["eps_forecast"] = eps_list
            result["num_analysts"] = ths.get("num_analysts", 0)
            result["source"] = "同花顺一致预期"

        # ── EPS 质量校验 ──
        quality = _validate_eps_quality(ths.get("historical", []), ths)
        result["data_quality"] = quality
        if quality.get("adjusted_trailing_eps") is not None:
            logger.info(
                f"[{code}] EPS异常检测: {quality['level']} — {quality['warning']}"
            )

    # ── 3. 东财研报（作为补充/替代）──
    research = cache.get_research_targets(code, limit=15)
    if research:
        # 提取有目标价的研报
        result["research_targets"] = [
            {"org": r["org"], "date": r["date"], "rating": r["rating"],
             "target_price": r["target_price"]}
            for r in research if r.get("target_price")
        ]

        # 如果同花顺没有数据，用研报 EPS 均值
        if not result["eps_forecast"]:
            current_year = result["current_year"]
            eps_by_year = {current_year: [], current_year+1: [], current_year+2: []}
            for r in research:
                for i in range(3):
                    yr = current_year + i
                    eps_key = f"eps_{yr}"
                    eps_val = r.get(eps_key, 0)
                    if eps_val and eps_val > 0:
                        eps_by_year[yr].append(eps_val)

            eps_means = []
            for yr in [current_year, current_year+1, current_year+2]:
                vals = eps_by_year.get(yr, [])
                if vals:
                    eps_means.append(round(sum(vals) / len(vals), 4))
            if eps_means:
                result["eps_forecast"] = eps_means
                result["source"] = f"东财研报均值({len(research)}篇)"

    # ── 4. 计算增长率 ──
    eps_forecast = result["eps_forecast"]
    # 如果历史EPS有异常值，使用调整后的trailing EPS做CAGR基准
    effective_trailing = trailing_eps
    quality = result.get("data_quality", {})
    if quality.get("adjusted_trailing_eps") is not None:
        effective_trailing = quality["adjusted_trailing_eps"]

    if eps_forecast and effective_trailing and effective_trailing > 0:
        growth_rates = []
        prev = effective_trailing
        for eps in eps_forecast:
            if prev > 0:
                g = (eps - prev) / prev
            else:
                g = 0
            growth_rates.append(round(g, 4))
            prev = eps
        result["growth_rates"] = growth_rates

        # 3年 CAGR
        if len(eps_forecast) >= 2 and eps_forecast[0] > 0:
            cagr = (eps_forecast[-1] / eps_forecast[0]) ** (1 / len(eps_forecast)) - 1
        elif len(eps_forecast) >= 1 and effective_trailing > 0:
            years = len(eps_forecast)
            cagr = (eps_forecast[-1] / effective_trailing) ** (1 / years) - 1
        else:
            cagr = 0
        result["cagr_3y"] = round(cagr, 4)

    return result


def _get_trailing_eps(cache: DataCache, code: str) -> Optional[float]:
    """
    获取最近12个月 EPS（trailing twelve months）。

    方法优先级：
    1. 同花顺 yjycData 中最近年份的 SJ(实际) EPS
    2. 新浪利润表最近4个季度（单季度数据求和）/ 总股本
    3. 兜底：最新一期归母净利润 / 总股本
    """
    # ── 方法1：同花顺历史实际EPS（最可靠）──
    ths = cache.get_consensus_eps(code)
    if ths and ths.get("historical"):
        # historical 按年份排序，取最新的实际值
        sorted_hist = sorted(ths["historical"], key=lambda x: x["year"], reverse=True)
        for h in sorted_hist:
            if h.get("eps") and h["eps"] > 0:
                logger.info(f"[{code}] TTM EPS 来自同花顺: {h['eps']} ({h['year']}年)")
                return float(h["eps"])

    # ── 方法2：新浪利润表 ──
    lrb_data = cache.get_financials(code, report_type="lrb")
    if lrb_data:
        # 获取总股本
        basic_info = cache.get_stock_basic(code)
        total_shares = None
        if basic_info:
            total_shares = basic_info.get("total_shares", 0)
        if not total_shares or total_shares <= 0:
            return None

        # 尝试从最新4个季度求和（单季度数据）
        total_np = 0
        found = 0
        for record in lrb_data[:8]:
            np_val = _extract_net_profit(record)
            if np_val is not None:
                total_np += np_val
                found += 1
            if found >= 4:
                break

        if found > 0 and total_np > 0:
            # 新浪数据：若 total_np 极大（> total_shares × 10000），说明是累计值叠加
            # 判断：用 total_np/total_shares 与同花顺最新EPS对比
            eps_raw = total_np / total_shares
            # 合理范围检查：EPS 应在 0.01 ~ 10000 之间
            if 0.01 <= eps_raw <= 10000:
                logger.info(f"[{code}] TTM EPS 来自新浪财报: {eps_raw:.2f} ({found}期合计)")
                return round(eps_raw, 4)
            # 超出合理范围，取最新一期单期
            for record in lrb_data[:1]:
                np_val = _extract_net_profit(record)
                if np_val is not None and np_val > 0:
                    eps_single = np_val / total_shares
                    if 0.01 <= eps_single <= 10000:
                        logger.info(f"[{code}] TTM EPS 来自新浪最新单期: {eps_single:.2f}")
                        return round(eps_single, 4)

    return None


def _extract_net_profit(record: dict) -> Optional[float]:
    """从利润表记录中提取净利润。数据已在缓存层归一化为万元。"""
    keys = [
        "归属于母公司股东的净利润",
        "归母净利润",
        "净利润(百万元)",
        "净利润",
        "三、利润总额",
    ]
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


def _extract_total_shares_from_financials(lrb_data: List[dict]) -> Optional[float]:
    """从利润表数据推断总股本"""
    # 利润表中 EPS = 净利润 / 总股本，反推 BUG-prone，改用其他方式
    return None


def _validate_eps_quality(historical: list, forecast: dict) -> dict:
    """
    检测 EPS 数据的异常值。

    检测维度：
    1. 历史EPS异常：最近年份实际值偏离历史中位数 > 阈值（5×MAD 或 50%中位数）
       → 可能是非经常性损益造成的暴增/暴跌
    2. 预测EPS合理性：预测值低于历史中位数的20% 或 高于500%
       → 可能数据错误或极端情景

    两项检查独立运行，报告最严重的问题。

    Returns:
        {
            "level": "good" | "suspicious_historical" | "suspicious_forecast" | "low_confidence",
            "warning": str,
            "adjusted_trailing_eps": float | None,  # 异常时给出调整后的基准EPS
        }
    """
    # 提取有效历史EPS（排除0值）
    hist_eps = []
    for h in (historical or []):
        eps = h.get("eps")
        if eps and eps != 0:
            hist_eps.append(float(eps))

    if not hist_eps:
        return {"level": "low_confidence", "warning": "无历史EPS数据", "adjusted_trailing_eps": None}

    if len(hist_eps) < 3:
        return {"level": "low_confidence", "warning": f"历史EPS仅{len(hist_eps)}年，趋势不可靠",
                "adjusted_trailing_eps": None}

    # 剔除0值后取中位数
    eps_positive = [e for e in hist_eps if e > 0]
    if not eps_positive:
        return {"level": "low_confidence", "warning": "历史EPS全为负值", "adjusted_trailing_eps": None}

    median = statistics.median(eps_positive)
    # 使用MAD（中位数绝对偏差）作为稳健的离散度指标
    mad = statistics.median([abs(e - median) for e in eps_positive])
    # 若MAD为0（所有值相同），使用中位数的10%作为最小阈值
    threshold = max(mad * 5, abs(median) * 0.5)  # 5×MAD 或 50%中位数

    latest = hist_eps[-1]

    warnings = []
    adjusted_eps = None
    worst_level = "good"

    # ── 检查1：最近年份是否异常 ──
    if abs(latest - median) > threshold and threshold > 0:
        recent_eps = eps_positive[-3:] if len(eps_positive) >= 3 else eps_positive
        adjusted_eps = round(statistics.median(recent_eps), 4)
        warnings.append(
            f"最近年份EPS({latest:.4f})偏离中位数({median:.4f})超过阈值({threshold:.4f})，"
            f"可能含非经常性损益"
        )
        worst_level = "suspicious_historical"

    # ── 检查2：预测值是否合理 ──
    forecast_warnings = []
    for key in sorted(forecast.keys()):
        if not key.startswith("eps_20"):
            continue
        eps_val = forecast[key]
        if not eps_val or eps_val <= 0:
            continue
        # 预测EPS < 历史中位数的20% → 异常低
        if eps_val < median * 0.2:
            forecast_warnings.append(
                f"{key}({eps_val:.4f})仅为历史中位数({median:.4f})的{eps_val/median*100:.1f}%"
            )
        # 预测EPS > 历史中位数的500% → 异常高
        elif eps_val > median * 5:
            forecast_warnings.append(
                f"{key}({eps_val:.4f})为历史中位数({median:.4f})的{eps_val/median*100:.0f}%"
            )

    # ──【修复5】新增检查：预测Year 1隐含增长率 ──
    latest_eps = hist_eps[-1] if hist_eps else 0
    for key in sorted(forecast.keys()):
        if not key.startswith("eps_20"):
            continue
        eps_val = forecast[key]
        if not eps_val or eps_val <= 0 or latest_eps <= 0:
            continue
        implied_g = (eps_val - latest_eps) / latest_eps
        if implied_g > 0.50:
            # 若历史中位数增长<30%，则Year 1预测>50%太激进
            hist_growth_rates = []
            for i in range(1, len(hist_eps)):
                if hist_eps[i-1] > 0:
                    hist_growth_rates.append((hist_eps[i] - hist_eps[i-1]) / abs(hist_eps[i-1]))
            median_hist_g = statistics.median(hist_growth_rates) if hist_growth_rates else 0
            if median_hist_g < 0.30:
                forecast_warnings.append(
                    f"{key}隐含增长{implied_g*100:.0f}%>50%, 但历史中位增长仅{median_hist_g*100:.0f}%"
                )

    if forecast_warnings:
        warnings.append("预测EPS异常: " + "; ".join(forecast_warnings))
        # 预测异常时，如尚未调整trailing EPS，使用中位数
        if adjusted_eps is None:
            adjusted_eps = round(median, 4)
        # 预测异常比历史异常更严重（影响未来估值）
        if worst_level == "good":
            worst_level = "suspicious_forecast"

    if worst_level == "good":
        return {"level": "good", "warning": "", "adjusted_trailing_eps": None}

    return {
        "level": worst_level,
        "warning": " | ".join(warnings),
        "adjusted_trailing_eps": adjusted_eps,
    }
