"""
事件驱动信号检测
================
基于研报/新闻/公告/互动易的事件信号：
  - 研报密集上调（5日内3家以上上调评级/目标价）
  - 业绩超预期（最新季报 vs 一致预期）
  - 股东增持/回购
  - 互动易情绪（问答密度/关键词）
  - 限售解禁预警（反向信号）
"""

import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

from ...data.cache import DataCache

logger = logging.getLogger("tg.strategy.event")


def analyze_event_signals(code: str, cache: DataCache = None) -> dict:
    """
    事件驱动综合信号分析。

    Returns:
        {
            "research_surge": dict|None,    # 研报密集上调
            "earnings_surprise": dict|None, # 业绩超预期
            "insider_trade": dict|None,     # 股东增持/减持
            "unlocking_alert": dict|None,   # 解禁预警
            "signals": [...],
            "verdict": str,
        }
    """
    if cache is None:
        cache = DataCache()

    result = {
        "research_surge": _check_research_surge(cache, code),
        "earnings_surprise": _check_earnings_surprise(cache, code),
        "insider_trade": _check_insider(cache, code),
        "unlocking_alert": _check_unlocking(cache, code),
    }

    signals = []
    for key, data in result.items():
        if data and data.get("signals"):
            signals.extend(data["signals"])

    bull = [s for s in signals if s["action"] in ("加仓", "关注")]
    bear = [s for s in signals if s["action"] in ("减仓", "预警")]

    if bull and not bear:
        verdict = "事件面偏多"
    elif bear and not bull:
        verdict = "事件面偏空"
    elif bull and bear:
        verdict = "事件面多空交织"
    else:
        verdict = "事件面无明显信号"

    result["signals"] = signals
    result["verdict"] = verdict
    return result


def _check_research_surge(cache: DataCache, code: str) -> Optional[dict]:
    """
    研报密集上调检测。

    信号逻辑：
      - 5日内 ≥3 家机构发布研报且评级为"买入/增持/推荐" → 机构看好信号
      - 目标价上调（最近目标价 > 前期均值×1.1）→ 强烈看好
      - 首次覆盖 → 新进入机构视野
    """
    try:
        research = cache.get_research_targets(code, limit=20)
    except Exception as e:
        logger.debug(f"研报获取失败 {code}: {e}")
        return None

    if not research:
        return None

    now = datetime.now()
    recent_5d = []
    recent_10d = []

    for r in research:
        try:
            r_date = datetime.strptime(r["date"], "%Y-%m-%d")
            days_ago = (now - r_date).days
            if days_ago <= 5:
                recent_5d.append(r)
            if days_ago <= 10:
                recent_10d.append(r)
        except Exception:
            continue

    signals = []

    # 5日内密集发布
    if len(recent_5d) >= 3:
        buy_ratings = [r for r in recent_5d
                       if any(w in r.get("rating", "") for w in ["买入", "增持", "推荐", "优于"])]
        if len(buy_ratings) >= 3:
            signals.append({
                "signal": f"5日内{len(recent_5d)}家机构密集覆盖，{len(buy_ratings)}家积极评级",
                "type": "事件驱动",
                "action": "加仓",
                "priority": 2,
            })

    # 目标价上调
    prices_10d = [r["target_price"] for r in recent_10d if r.get("target_price")]
    prices_5d = [r["target_price"] for r in recent_5d if r.get("target_price")]

    if prices_5d and prices_10d:
        avg_old = sum(prices_10d) / len(prices_10d)
        avg_new = sum(prices_5d) / len(prices_5d)
        if avg_old > 0 and avg_new > avg_old * 1.1:
            signals.append({
                "signal": f"目标价上调: {avg_new:.1f} vs 前期{avg_old:.1f}（+{(avg_new/avg_old-1)*100:.0f}%）",
                "type": "事件驱动",
                "action": "加仓",
                "priority": 1,
            })

    if not signals:
        return None

    return {
        "recent_5d_count": len(recent_5d),
        "buy_count": len([r for r in recent_5d if any(w in r.get("rating", "") for w in ["买入", "增持"])]),
        "signals": signals,
    }


def _check_earnings_surprise(cache: DataCache, code: str) -> Optional[dict]:
    """
    业绩超预期检测。

    信号逻辑：
      - 最新财报净利润 > 一致预期 × 1.1 → 超预期
      - 最新财报净利润 < 一致预期 × 0.9 → 低于预期
      - 营收超预期同理
    """
    from ...valuation.earnings_forecast import get_earnings_forecast

    try:
        earnings = get_earnings_forecast(code)
    except Exception:
        return None

    trailing_eps = earnings.get("trailing_eps")
    eps_forecast = earnings.get("eps_forecast", [])

    if not trailing_eps or not eps_forecast:
        return None

    # 当前年度的一致预期 EPS
    current_year_eps = eps_forecast[0] if eps_forecast else None
    if not current_year_eps or current_year_eps <= 0:
        return None

    # TTM vs 一致预期差值
    surprise_pct = (trailing_eps - current_year_eps) / current_year_eps * 100

    if surprise_pct > 15:
        return {
            "type": "业绩超预期",
            "surprise_pct": round(surprise_pct, 1),
            "actual_eps": trailing_eps,
            "expected_eps": current_year_eps,
            "signals": [{
                "signal": f"业绩超预期{surprise_pct:.1f}%（TTM EPS {trailing_eps:.2f} vs 预期 {current_year_eps:.2f}）",
                "type": "事件驱动",
                "action": "加仓",
                "priority": 1,
            }],
        }
    elif surprise_pct > 5:
        return {
            "type": "业绩略超预期",
            "surprise_pct": round(surprise_pct, 1),
            "signals": [{
                "signal": f"业绩略超预期{surprise_pct:.1f}%",
                "type": "事件驱动",
                "action": "关注",
                "priority": 2,
            }],
        }
    elif surprise_pct < -20:
        return {
            "type": "业绩低于预期",
            "surprise_pct": round(surprise_pct, 1),
            "signals": [{
                "signal": f"业绩低于预期{abs(surprise_pct):.1f}%",
                "type": "事件驱动",
                "action": "减仓",
                "priority": 1,
            }],
        }

    return None


def _check_insider(cache: DataCache, code: str) -> Optional[dict]:
    """
    股东增持/减持检测（简化版，占位）。

    数据源：巨潮公告中的增减持公告。
    Phase 5 数据层完善时实现精确解析。
    """
    return None


def _check_unlocking(cache: DataCache, code: str) -> Optional[dict]:
    """
    限售解禁预警。

    信号逻辑：
      - 未来30天内有解禁，且解禁量 > 流通股 5% → 预警
      - 解禁量 > 流通股 20% → 强烈预警
    """
    # 解禁数据需要东财 datacenter 的限售解禁接口
    # 占位，Phase 5 数据层完善时实现
    return None
