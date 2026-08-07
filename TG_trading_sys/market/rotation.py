"""
板块轮动监测
============
行业板块相对强弱排名 + 资金流向方向 + 轮动阶段判断

轮动阶段：
  - 防守→周期: 经济复苏初期
  - 周期→成长: 经济扩张期
  - 成长→题材: 牛市后期
  - 题材→防守: 风险规避
"""

import logging
from typing import Dict, List, Optional
from datetime import datetime
import pandas as pd
import numpy as np

from ..data.cache import DataCache

logger = logging.getLogger("tg.market.rotation")


# 板块分类
SECTOR_CLASSIFICATION = {
    "防守型": ["食品饮料", "医药生物", "公用事业", "农林牧渔"],
    "周期型": ["银行", "非银金融", "房地产", "建筑材料", "钢铁", "有色金属", "采掘", "化工"],
    "成长型": ["电子", "计算机", "通信", "电力设备", "国防军工", "机械设备"],
    "题材型": ["传媒", "社会服务", "商贸零售", "纺织服装", "综合"],
}


def sector_rotation(cache: DataCache = None, top_n: int = 20) -> dict:
    """
    行业板块轮动分析。

    分析维度：
      1. 近5日/20日涨跌幅排名 → 短期强度
      2. 资金流向方向（主力净流入/流出） → 资金认可度
      3. 板块分类聚合强度 → 轮动方向

    Returns:
        {
            "sector_ranking": [...],
            "category_strength": {...},
            "rotation_direction": str,
            "rotation_phase": str,
            "strongest_sectors": [...],
            "weakest_sectors": [...],
        }
    """
    if cache is None:
        cache = DataCache()

    # ── 获取行业板块数据 ──
    try:
        sectors = cache.eastmoney.get_sector_ranking(top_n=50) if hasattr(cache, 'eastmoney') else []
    except Exception:
        sectors = []

    if not sectors:
        return _empty_rotation("行业板块数据不可用")

    # ── 按涨跌幅排序 ──
    ranking = []
    for s in sectors:
        name = s.get("name", "")
        chg = s.get("change_pct", 0) or 0
        up = s.get("up_count", 0) or 0
        down = s.get("down_count", 0) or 0
        leader = s.get("leader", "")

        # 分类
        category = _classify_sector(name)

        ranking.append({
            "name": name,
            "change_pct": round(float(chg), 2),
            "up_count": up,
            "down_count": down,
            "breadth": round(up / max(up + down, 1) * 100, 1),
            "leader": leader,
            "category": category,
        })

    ranking.sort(key=lambda x: x["change_pct"], reverse=True)

    # ── 各分类聚合强度 ──
    category_data = {}
    for cat, members in SECTOR_CLASSIFICATION.items():
        cat_sectors = [r for r in ranking if r["category"] == cat]
        if cat_sectors:
            avg_chg = sum(r["change_pct"] for r in cat_sectors) / len(cat_sectors)
            category_data[cat] = {
                "avg_change_pct": round(avg_chg, 2),
                "count": len(cat_sectors),
                "top_sector": max(cat_sectors, key=lambda x: x["change_pct"])["name"],
            }
        else:
            category_data[cat] = {"avg_change_pct": 0, "count": 0, "top_sector": ""}

    # ── 轮动方向判断 ──
    sorted_cats = sorted(category_data.items(),
                         key=lambda x: x[1]["avg_change_pct"], reverse=True)
    strongest_cat = sorted_cats[0][0] if sorted_cats else ""
    weakest_cat = sorted_cats[-1][0] if sorted_cats else ""

    rotation_phase = _determine_phase(sorted_cats)
    rotation_direction = _determine_direction(sorted_cats)

    return {
        "sector_ranking": ranking[:top_n],
        "category_strength": category_data,
        "rotation_direction": rotation_direction,
        "rotation_phase": rotation_phase,
        "strongest_category": strongest_cat,
        "weakest_category": weakest_cat,
        "strongest_sectors": [r["name"] for r in ranking[:5]],
        "weakest_sectors": [r["name"] for r in ranking[-5:]],
    }


def rotation_summary(rotation_result: dict) -> str:
    """生成板块轮动摘要"""
    lines = [
        f"最强板块: {', '.join(rotation_result.get('strongest_sectors', [])[:3])}",
        f"最弱板块: {', '.join(rotation_result.get('weakest_sectors', [])[:3])}",
        f"资金偏好: {rotation_result.get('strongest_category', '')} > {rotation_result.get('weakest_category', '')}",
        f"轮动阶段: {rotation_result.get('rotation_phase', '')}",
        f"轮动方向: {rotation_result.get('rotation_direction', '')}",
    ]
    return "\n".join(lines)


def _classify_sector(name: str) -> str:
    """将板块名称归类"""
    for cat, members in SECTOR_CLASSIFICATION.items():
        for keyword in members:
            if keyword in name:
                return cat
    return "其他"


def _determine_phase(sorted_cats) -> str:
    """根据各板块分类强度判断轮动阶段"""
    if not sorted_cats:
        return "无法判断"

    # 构建排名
    rankings = {cat: i + 1 for i, (cat, _) in enumerate(sorted_cats)}

    defense_rank = rankings.get("防守型", 4)
    cyclical_rank = rankings.get("周期型", 4)
    growth_rank = rankings.get("成长型", 4)
    thematic_rank = rankings.get("题材型", 4)

    # 判断阶段
    if defense_rank <= 2 and cyclical_rank >= 3:
        return "防守领涨 → 风险偏好低，市场防御阶段"
    elif cyclical_rank <= 2 and growth_rank >= 3:
        return "周期领涨 → 经济复苏预期，市场回暖阶段"
    elif growth_rank <= 2 and thematic_rank >= 3:
        return "成长领涨 → 风险偏好提升，市场进攻阶段"
    elif thematic_rank <= 2:
        return "题材炒作 → 市场过热，注意风险"
    elif defense_rank <= 2 and cyclical_rank <= 2:
        return "防守+周期双强 → 风格轮动中，市场转型期"
    else:
        return "风格均衡 → 无明显主导板块"


def _determine_direction(sorted_cats) -> str:
    """判断轮动方向"""
    if not sorted_cats:
        return "无法判断"

    strongest = sorted_cats[0][0]
    weakest = sorted_cats[-1][0]

    # 防守→周期
    if strongest == "周期型" and ("防守" in weakest or "题材" in weakest):
        return "防守→周期（Risk-On 初期）"
    # 周期→成长
    elif strongest == "成长型" and "周期" in weakest:
        return "周期→成长（Risk-On 加速）"
    # 成长→题材
    elif strongest == "题材型" and "成长" in weakest:
        return "成长→题材（情绪高潮）"
    # 成长→防守
    elif strongest == "防守型" and ("成长" in weakest or "题材" in weakest):
        return "成长→防守（Risk-Off）"
    # 均衡
    else:
        return "风格均衡轮动"


def _empty_rotation(reason: str) -> dict:
    return {
        "sector_ranking": [],
        "category_strength": {},
        "rotation_direction": reason,
        "rotation_phase": reason,
        "strongest_sectors": [],
        "weakest_sectors": [],
    }
