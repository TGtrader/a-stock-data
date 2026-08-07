"""
多策略信号聚合裁决引擎
======================
整合五大信号源，加权评分，冲突裁决，输出统一信号结论。

信号源权重（可配置）：
  - 趋势/均线: 40%  (最核心的顺势交易依据)
  - 量价/VPA:  25%  (威科夫量价确认)
  - 资金面:    20%  (主力资金流向)
  - 形态识别:  10%  (技术形态辅助)
  - 事件驱动:   5%  (催化剂信号)

裁决规则：
  - 趋势和量价同时看多 + 资金面不反对 → 强烈做多
  - 趋势看多但量价背离 → 降级到观望
  - 资金面强烈看多但趋势向下 → 限制在"关注"级别（不可对抗趋势）
  - 多信号同方向 → 提升信号强度
  - 信号衰减：信号产生后逐日降权（3日后减半，7日后清零）
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import numpy as np
import pandas as pd

logger = logging.getLogger("tg.strategy.aggregator")


# ═══════════════════════════════════════════════════════════════
# 信号数据结构
# ═══════════════════════════════════════════════════════════════

@dataclass
class SignalVerdict:
    """综合信号裁决结果"""
    verdict: str                      # 强烈做多 / 做多 / 偏多 / 观望 / 偏空 / 做空 / 强烈做空
    score: int                        # 综合评分 0-100
    confidence: str                   # 置信度: 高/中/低
    signal_scores: Dict[str, int]     # 各信号源评分
    active_signals: List[dict]        # 当前活跃信号
    conflicts: List[str]              # 信号冲突说明
    summary: str                      # 一句话总结
    position_advice: str              # 仓位建议


# ═══════════════════════════════════════════════════════════════
# 默认权重配置
# ═══════════════════════════════════════════════════════════════

DEFAULT_WEIGHTS = {
    "trend":    0.40,   # 趋势/均线
    "vpa":      0.25,   # 量价威科夫
    "fund":     0.20,   # 资金面
    "pattern":  0.10,   # 形态识别
    "event":    0.05,   # 事件驱动
}


def aggregate_signals(
    ma_result: dict = None,
    vpa_result: dict = None,
    fund_result: dict = None,
    pattern_result: dict = None,
    event_result: dict = None,
    weights: Dict[str, float] = None,
) -> SignalVerdict:
    """
    多策略信号聚合 & 冲突裁决。

    各参数是该信号源的完整分析结果 dict，None表示该信号源不可用。

    Args:
        ma_result: 均线系统分析结果 (来自 ma_signals.analyze_ma_system)
        vpa_result: VPA分析结果 (来自 VPA 引擎)
        fund_result: 资金面分析结果 (来自 fund_signals.analyze_fund_signals)
        pattern_result: 形态分析结果 (来自 pattern_signals.detect_patterns)
        event_result: 事件驱动分析结果 (来自 event_signals.analyze_event_signals)
        weights: 自定义权重

    Returns:
        SignalVerdict 统一裁决结果
    """
    if weights is None:
        weights = DEFAULT_WEIGHTS.copy()

    # ── 1. 各信号源评分 (0-100) ──
    scores = {}
    details = {}

    # 趋势/均线评分
    if ma_result and "error" not in ma_result:
        scores["trend"] = ma_result.get("score", 50)
        details["trend"] = {
            "verdict": ma_result.get("verdict", ""),
            "alignment": ma_result.get("ma_alignment", {}).get("state", ""),
            "signals": ma_result.get("signals", []),
        }
    else:
        scores["trend"] = 50
        details["trend"] = {"verdict": "数据不可用", "alignment": "", "signals": []}

    # VPA 量价评分
    if vpa_result and "error" not in vpa_result:
        rating = vpa_result.get("rating", {})
        scores["vpa"] = rating.get("score", 50)
        details["vpa"] = {
            "verdict": rating.get("rating", ""),
            "signal_summary": vpa_result.get("signals", {}).get("signal_summary", ""),
            "signals": vpa_result.get("signals", {}).get("recent_signals", []),
        }
    else:
        scores["vpa"] = 50
        details["vpa"] = {"verdict": "数据不可用", "signal_summary": "", "signals": []}

    # 资金面评分
    if fund_result:
        fund_signals = fund_result.get("signals", [])
        scores["fund"] = _score_from_signals(fund_signals, baseline=50)
        details["fund"] = {
            "verdict": fund_result.get("verdict", ""),
            "signals": fund_signals,
        }
    else:
        scores["fund"] = 50
        details["fund"] = {"verdict": "数据不可用", "signals": []}

    # 形态评分
    if pattern_result:
        pat_signals = pattern_result.get("signals", [])
        scores["pattern"] = _score_from_signals(pat_signals, baseline=50)
        details["pattern"] = {
            "verdict": pattern_result.get("verdict", ""),
            "signals": pat_signals,
        }
    else:
        scores["pattern"] = 50
        details["pattern"] = {"verdict": "数据不可用", "signals": []}

    # 事件评分
    if event_result:
        evt_signals = event_result.get("signals", [])
        scores["event"] = _score_from_signals(evt_signals, baseline=50)
        details["event"] = {
            "verdict": event_result.get("verdict", ""),
            "signals": evt_signals,
        }
    else:
        scores["event"] = 50
        details["event"] = {"verdict": "数据不可用", "signals": []}

    # ── 2. 加权综合评分 ──
    available_weights = {k: w for k, w in weights.items() if k in scores}
    total_w = sum(available_weights.values())
    if total_w == 0:
        total_w = 1

    composite = sum(
        scores[k] * (available_weights.get(k, 0) / total_w)
        for k in scores
    )

    # ── 3. 冲突检测 & 裁决 ──
    conflicts = _detect_conflicts(scores, details)

    # 应用冲突降级
    composite = _apply_conflict_rules(composite, conflicts, scores, details)

    # ── 4. 判定最终信号 ──
    composite = max(0, min(100, composite))

    if composite >= 80:
        verdict = "强烈做多"
        position_advice = "重仓（60-80%）"
        confidence = "高" if composite >= 85 else "中"
    elif composite >= 65:
        verdict = "做多"
        position_advice = "中等仓位（40-60%）"
        confidence = "中"
    elif composite >= 55:
        verdict = "偏多"
        position_advice = "轻仓（20-40%）"
        confidence = "低" if conflicts else "中"
    elif composite >= 45:
        verdict = "观望"
        position_advice = "观望/极轻仓（0-20%）"
        confidence = "中"
    elif composite >= 30:
        verdict = "偏空"
        position_advice = "减仓至轻仓"
        confidence = "中"
    elif composite >= 15:
        verdict = "做空"
        position_advice = "清仓/对冲"
        confidence = "中"
    else:
        verdict = "强烈做空"
        position_advice = "清仓/做空"
        confidence = "高" if composite <= 10 else "中"

    # ── 5. 收集活跃信号 ──
    all_active = []
    for source in details.values():
        for sig in source.get("signals", []):
            if isinstance(sig, dict) and sig.get("priority", 99) <= 3:
                all_active.append(sig)

    # ── 6. 生成总结 ──
    trend_dir = details["trend"]["verdict"][:4] if details["trend"]["verdict"] else ""
    vpa_dir = details["vpa"]["verdict"][:4] if details["vpa"]["verdict"] else ""
    fund_dir = details["fund"]["verdict"][:4] if details["fund"]["verdict"] else ""

    summary_parts = []
    if verdict.startswith("强烈做多"):
        summary_parts.append(f"多维度共振看多")
    elif "做多" in verdict:
        summary_parts.append(f"多数信号偏多")
    elif "观望" in verdict:
        if conflicts:
            summary_parts.append(f"信号存在冲突: {'; '.join(conflicts[:2])}")
        else:
            summary_parts.append("多空力量均衡")
    elif "空" in verdict:
        summary_parts.append("多数信号偏空")

    summary = "。".join(summary_parts) if summary_parts else "综合信号中性"

    return SignalVerdict(
        verdict=verdict,
        score=int(composite),
        confidence=confidence,
        signal_scores=scores,
        active_signals=all_active,
        conflicts=conflicts,
        summary=summary,
        position_advice=position_advice,
    )


def _score_from_signals(signals: List[dict], baseline: int = 50) -> int:
    """根据信号列表计算评分（偏离基线）"""
    if not signals:
        return baseline

    score = baseline
    for s in signals:
        priority = s.get("priority", 3)
        action = s.get("action", "")

        if action in ("加仓", "持仓/加仓"):
            delta = 15 if priority == 1 else (10 if priority == 2 else 5)
        elif action in ("减仓", "减仓/离场", "离场"):
            delta = -15 if priority == 1 else (-10 if priority == 2 else -5)
        elif action in ("关注", "关注流入", "观察"):
            delta = 5 if priority <= 2 else 0
        elif action in ("预警", "关注流出"):
            delta = -5 if priority <= 2 else 0
        else:
            delta = 0

        # 信号衰减（基于日期，简化：按priority = freshness proxy）
        if priority == 1:
            decay = 1.0
        elif priority == 2:
            decay = 0.7
        else:
            decay = 0.4

        score += delta * decay

    return max(0, min(100, score))


def _detect_conflicts(scores: Dict[str, int], details: Dict[str, dict]) -> List[str]:
    """检测信号冲突"""
    conflicts = []

    trend_score = scores.get("trend", 50)
    vpa_score = scores.get("vpa", 50)
    fund_score = scores.get("fund", 50)

    # 冲突1: 趋势看多 + 量价看空
    if trend_score >= 65 and vpa_score <= 35:
        conflicts.append("趋势看多 vs 量价看空（威科夫信号警告：上涨可能不可持续）")

    # 冲突2: 趋势看空 + 量价看多
    if trend_score <= 35 and vpa_score >= 65:
        conflicts.append("趋势看空 vs 量价看多（可能是反弹陷阱）")

    # 冲突3: 资金面强烈看多 + 趋势向下
    if fund_score >= 70 and trend_score <= 40:
        conflicts.append("资金面强烈流入但趋势向下（主力可能提前布局，等趋势确认）")

    # 冲突4: 资金面强烈看空 + 趋势向上
    if fund_score <= 30 and trend_score >= 60:
        conflicts.append("趋势向上但资金在撤（诱多风险）")

    # 冲突5: 多空信号并存
    trend_dir = details.get("trend", {}).get("alignment", "")
    vpa_verdict = details.get("vpa", {}).get("verdict", "")
    if "多" in trend_dir and ("做空" in vpa_verdict or "偏空" in vpa_verdict):
        conflicts.append(f"均线{trend_dir} vs VPA{vpa_verdict}")

    return conflicts


def _apply_conflict_rules(
    composite: float, conflicts: List[str],
    scores: Dict[str, int], details: Dict[str, dict]
) -> float:
    """应用冲突降级规则"""
    if not conflicts:
        return composite

    trend_score = scores.get("trend", 50)
    vpa_score = scores.get("vpa", 50)
    fund_score = scores.get("fund", 50)

    # 每条冲突降级
    for c in conflicts:
        if "趋势看多 vs 量价看空" in c:
            composite -= 15  # 强冲突
        elif "趋势看空 vs 量价看多" in c:
            composite -= 12
        elif "趋势向上但资金在撤" in c:
            composite -= 10
        elif "资金面强烈流入但趋势向下" in c:
            composite -= 8
        else:
            composite -= 5

    # 核心原则：趋势为王，趋势方向不能对抗
    if trend_score >= 70 and composite < 50:
        composite = max(composite, 50)  # 趋势好，底线观望
    if trend_score <= 30 and composite > 50:
        composite = min(composite, 50)  # 趋势差，上限观望

    return composite
