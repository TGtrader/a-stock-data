"""
市场情绪仪表盘
==============
多维度量化市场情绪，输出统一的情绪评分。

情绪维度（加权）：
  1. 涨跌比       25% — 上涨/下跌家数比
  2. 涨停/跌停比  20% — 涨停数/跌停数
  3. 炸板率       15% — 炸板数/涨停数（反向）
  4. 北向资金     15% — 当日净流向+5日累计
  5. 两融余额     10% — 融资余额变化
  6. 成交量       10% — 全市场成交量/20日均量
  7. 新高/新低     5% — 创N日新高/新低的股票比例

评分体系：0-100
  >70: 贪婪（可能过热）
  50-70: 乐观
  30-50: 中性
  10-30: 恐惧
  <10: 极度恐惧（可能超卖）
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional
from datetime import datetime
import numpy as np
import pandas as pd

logger = logging.getLogger("tg.market.sentiment")


@dataclass
class MarketSentiment:
    """市场情绪快照"""
    score: int                          # 0-100
    level: str                          # 贪婪/乐观/中性/恐惧/极度恐惧
    dimensions: Dict[str, float]        # 各维度得分
    signals: List[str]                  # 关键信号
    contrarian_signal: str              # 逆向投资信号
    timestamp: str


def sentiment_dashboard(
    cache = None,
    advance_decline_ratio: float = None,
    limit_up_count: int = None,
    limit_down_count: int = None,
    broken_board_count: int = None,
    northbound_net: float = None,
    northbound_5d: float = None,
    margin_change_pct: float = None,
    market_volume_ratio: float = None,
) -> MarketSentiment:
    """
    市场情绪仪表盘。

    各参数如为 None，则使用默认/中性值。
    实际使用时从东财/同花顺拉取实时数据。
    """
    scores = {}
    signals = []

    # ── 1. 涨跌比 (25分) ──
    if advance_decline_ratio is not None:
        ad_score = _score_ad_ratio(advance_decline_ratio)
    else:
        ad_score, advance_decline_ratio = 12.5, 1.0
    scores["涨跌比"] = ad_score
    if ad_score > 20:
        signals.append(f"涨跌比极高({advance_decline_ratio:.1f}:1)——市场普涨")
    elif ad_score < 5:
        signals.append(f"涨跌比极低({advance_decline_ratio:.1f}:1)——市场普跌")

    # ── 2. 涨停/跌停比 (20分) ──
    if limit_up_count is not None and limit_down_count is not None:
        ld_score = _score_limit_ratio(limit_up_count, limit_down_count)
    else:
        ld_score, limit_up_count, limit_down_count = 10, 50, 10
    scores["涨停跌停比"] = ld_score
    if ld_score > 17:
        signals.append(f"涨停{limit_up_count} vs 跌停{limit_down_count}——极端做多情绪")
    elif ld_score < 3:
        signals.append(f"跌停{limit_down_count} vs 涨停{limit_up_count}——恐慌抛售")

    # ── 3. 炸板率 (15分，反向) ──
    if broken_board_count is not None and limit_up_count is not None:
        bb_rate = broken_board_count / max(limit_up_count, 1)
        bb_score = _score_broken_board(bb_rate)
    else:
        bb_score, bb_rate = 7.5, 0.25
    scores["炸板率"] = bb_score
    if bb_rate > 0.40:
        signals.append(f"炸板率{bb_rate*100:.0f}%——封板资金犹豫")

    # ── 4. 北向资金 (15分) ──
    if northbound_net is not None:
        nb_score = _score_northbound(northbound_net, northbound_5d)
    else:
        nb_score, northbound_net = 7.5, 0
    scores["北向资金"] = nb_score
    if northbound_net > 50:
        signals.append(f"北向大幅流入{northbound_net:.0f}亿")
    elif northbound_net < -50:
        signals.append(f"北向大幅流出{abs(northbound_net):.0f}亿")

    # ── 5. 两融余额 (10分) ──
    if margin_change_pct is not None:
        mg_score = _score_margin(margin_change_pct)
    else:
        mg_score, margin_change_pct = 5, 0
    scores["两融余额"] = mg_score
    if margin_change_pct > 5:
        signals.append(f"融资余额急增{margin_change_pct:.1f}%——杠杆资金涌入")
    elif margin_change_pct < -5:
        signals.append(f"融资余额骤降{abs(margin_change_pct):.1f}%——杠杆资金撤离")

    # ── 6. 成交量 (10分) ──
    if market_volume_ratio is not None:
        vol_score = _score_volume_ratio(market_volume_ratio)
    else:
        vol_score, market_volume_ratio = 5, 1.0
    scores["成交量"] = vol_score
    if market_volume_ratio > 1.5:
        signals.append(f"放量{market_volume_ratio:.1f}x——交投活跃")
    elif market_volume_ratio < 0.6:
        signals.append(f"缩量至{market_volume_ratio:.2f}x——人气冰点")

    # ── 7. 新高新低 (5分) ──
    scores["新高新低"] = 2.5  # 中性默认

    # ── 加权综合（先归一化各维度到0-100，再赋权）──
    dim_max = {"涨跌比": 25, "涨停跌停比": 20, "炸板率": 15, "北向资金": 15,
               "两融余额": 10, "成交量": 10, "新高新低": 5}
    weights = {"涨跌比": 0.25, "涨停跌停比": 0.20, "炸板率": 0.15,
               "北向资金": 0.15, "两融余额": 0.10, "成交量": 0.10, "新高新低": 0.05}
    total = sum((scores[k] / dim_max[k] * 100) * weights[k] for k in scores)

    # ── 判定情绪等级 ──
    if total > 70:
        level = "贪婪"
        contrarian = "市场情绪过热——逆向投资者应考虑减仓"
    elif total > 50:
        level = "乐观"
        contrarian = "情绪偏乐观——趋势可能延续，但注意追高风险"
    elif total > 30:
        level = "中性"
        contrarian = "情绪中性——按正常策略交易"
    elif total > 10:
        level = "恐惧"
        contrarian = "市场恐慌——逆向投资者可开始关注抄底机会"
    else:
        level = "极度恐惧"
        contrarian = "市场极度恐慌——逆向投资者应积极寻找买入机会"

    if not signals:
        signals.append("各维度无明显极端信号")

    return MarketSentiment(
        score=int(total),
        level=level,
        dimensions=scores,
        signals=signals,
        contrarian_signal=contrarian,
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )


# ═══════════════════════════════════════════════════════════════
# 各维度评分函数（每项0-满分）
# ═══════════════════════════════════════════════════════════════

def _score_ad_ratio(ratio: float) -> float:
    """涨跌比评分（满分25）"""
    if ratio > 5:
        return 25
    elif ratio > 3:
        return 22
    elif ratio > 2:
        return 18
    elif ratio > 1.2:
        return 15
    elif ratio > 0.8:
        return 12.5
    elif ratio > 0.5:
        return 8
    elif ratio > 0.3:
        return 4
    else:
        return 1


def _score_limit_ratio(up: int, down: int) -> float:
    """涨停跌停比评分（满分20）"""
    if up == 0 and down == 0:
        return 10  # API未返回数据，中性
    if up > 0 and down == 0:
        return 18  # 有涨停无跌停
    ratio = up / max(down, 1)
    if ratio > 10:
        return 20
    elif ratio > 5:
        return 17
    elif ratio > 3:
        return 15
    elif ratio > 1.5:
        return 12
    elif ratio > 0.7:
        return 10
    elif ratio > 0.3:
        return 5
    else:
        return 1


def _score_broken_board(rate: float) -> float:
    """炸板率评分（满分15，反向）"""
    if rate < 0.15:
        return 15
    elif rate < 0.25:
        return 12
    elif rate < 0.35:
        return 8
    elif rate < 0.45:
        return 4
    else:
        return 1


def _score_northbound(net: float, net_5d: float = None) -> float:
    """北向评分（满分15）"""
    score = 7.5
    if net > 100:
        score += 6
    elif net > 50:
        score += 4
    elif net > 10:
        score += 2
    elif net < -100:
        score -= 6
    elif net < -50:
        score -= 4
    elif net < -10:
        score -= 2

    if net_5d is not None:
        if net_5d > 200:
            score += 1.5
        elif net_5d < -200:
            score -= 1.5

    return max(1, min(15, score))


def _score_margin(change_pct: float) -> float:
    """两融评分（满分10）"""
    if change_pct > 3:
        return 8
    elif change_pct > 1:
        return 6
    elif change_pct > -1:
        return 5
    elif change_pct > -3:
        return 3
    else:
        return 2


def _score_volume_ratio(ratio: float) -> float:
    """成交量评分（满分10）"""
    if 1.1 <= ratio <= 1.5:
        return 9  # 温和放量最佳
    elif 0.8 <= ratio <= 1.1:
        return 7  # 正常
    elif 1.5 < ratio <= 2.5:
        return 6  # 显著放量
    elif ratio > 2.5:
        return 3  # 极端放量
    else:
        return 3  # 缩量
