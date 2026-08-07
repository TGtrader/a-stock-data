"""
仓位中枢建议
============
综合大盘状态 + 板块轮动 + 市场情绪 → 动态仓位比例建议

决策框架：
  大盘状态（权重50%）: 决定仓位中枢
  市场情绪（权重30%）: 在中枢基础上微调
  板块轮动（权重20%）: 风格匹配调整

输出：
  - 建议总仓位比例 (0-100%)
  - 防守/进攻配置比例
  - 大小盘风格建议
"""

import logging
from dataclasses import dataclass
from typing import Dict, Optional

logger = logging.getLogger("tg.market.position")


@dataclass
class PositionAdvice:
    """仓位建议"""
    total_position_pct: float              # 建议总仓位 0-100
    aggressive_pct: float                  # 进攻型仓位
    defensive_pct: float                   # 防守型仓位
    regime: str                            # 大盘状态
    sentiment_level: str                   # 情绪等级
    rotation_phase: str                    # 轮动阶段
    style_bias: str                        # 风格偏好: 大盘价值/大盘成长/小盘成长/均衡
    summary: str                           # 一句话建议
    risk_level: str                        # 当前风险等级: 低/中/高/极高


def position_guide(
    regime_result: dict = None,
    sentiment: "MarketSentiment" = None,
    rotation_result: dict = None,
) -> PositionAdvice:
    """
    综合仓位中枢建议。

    三要素加权决策：
      - 大盘状态 50%: 决定仓位中枢
      - 市场情绪 30%: 在中枢上微调
      - 板块轮动 20%: 影响风格配置

    Args:
        regime_result: detect_regime() 或 multi_index_regime() 的结果
        sentiment: MarketSentiment 对象
        rotation_result: sector_rotation() 的结果

    Returns:
        PositionAdvice 对象
    """
    # ── 1. 从大盘状态获取仓位中枢 ──
    if regime_result and "composite" in regime_result:
        regime_score = regime_result["composite"]["score"]
        regime_name = regime_result["composite"]["regime"]
    elif regime_result:
        regime_score = regime_result.get("score", 50)
        regime_name = regime_result.get("regime", "震荡格局")
    else:
        regime_score = 50
        regime_name = "震荡格局（默认）"

    # 仓位中枢：分数映射
    base_position = _regime_to_base_position(regime_score, regime_name)

    # ── 2. 情绪调整 ──
    if sentiment:
        sentiment_adjustment = _sentiment_adjustment(sentiment)
        sentiment_level = sentiment.level
    else:
        sentiment_adjustment = 0
        sentiment_level = "未知"

    # ── 3. 轮动阶段调整 ──
    if rotation_result:
        rotation_phase = rotation_result.get("rotation_phase", "")
        rotation_adjustment = _rotation_adjustment(rotation_phase)
    else:
        rotation_phase = "未知"
        rotation_adjustment = 0

    # ── 4. 综合 ──
    # 加权: 中枢50% + 情绪30% + 轮动20%
    adjusted = base_position + sentiment_adjustment * 0.30 + rotation_adjustment * 0.20

    # 收束 [0, 100]
    total_position = max(5, min(100, adjusted))

    # ── 5. 攻防配置 ──
    aggressive_pct, defensive_pct, style_bias = _style_allocation(
        regime_name, sentiment_level, rotation_phase, total_position
    )

    # ── 6. 风险等级 ──
    risk_level = _risk_level(regime_name, sentiment_level)

    # ── 7. 一句话建议 ──
    summary_lines = [
        f"建议总仓位: {total_position:.0f}%",
        f"进攻型: {aggressive_pct:.0f}% | 防守型: {defensive_pct:.0f}%",
        f"风格偏好: {style_bias}",
        f"风险等级: {risk_level}",
    ]

    return PositionAdvice(
        total_position_pct=round(total_position, 1),
        aggressive_pct=round(aggressive_pct, 1),
        defensive_pct=round(defensive_pct, 1),
        regime=regime_name,
        sentiment_level=sentiment_level,
        rotation_phase=rotation_phase,
        style_bias=style_bias,
        summary="\n".join(summary_lines),
        risk_level=risk_level,
    )


def _regime_to_base_position(score: float, regime: str) -> float:
    """大盘状态→仓位中枢"""
    if score >= 80:
        return 75
    elif score >= 65:
        return 60
    elif score >= 50:
        return 45
    elif score >= 35:
        return 30
    elif score >= 20:
        return 20
    else:
        return 10


def _sentiment_adjustment(sentiment) -> float:
    """情绪调整量 [-20, +20]"""
    level = sentiment.level
    score = sentiment.score

    # 极度恐惧 → 逆向加仓（+10~15）
    if level == "极度恐惧":
        return 12
    # 恐惧 → 略微加仓（+5）
    elif level == "恐惧":
        return 5
    # 中性 → 不调整
    elif level == "中性":
        return 0
    # 乐观 → 谨慎追高（-5）
    elif level == "乐观":
        return -5
    # 贪婪 → 逆向减仓（-15）
    elif level == "贪婪":
        return -15
    return 0


def _rotation_adjustment(phase: str) -> float:
    """板块轮动调整量 [-10, +10]"""
    if "防御" in phase:
        return -8
    elif "过热" in phase or "炒作" in phase:
        return -5
    elif "进攻" in phase or "Risk-On" in phase:
        return 5
    elif "回暖" in phase:
        return 8
    return 0


def _style_allocation(regime: str, sentiment: str, rotation: str, total: float) -> tuple:
    """确定攻防配置和风格偏好"""
    aggressive = total * 0.5
    defensive = total * 0.5
    style = "均衡"

    # 牛市/偏多 → 提高进攻比例
    if "牛市" in regime or "偏多" in regime:
        aggressive = total * 0.70
        defensive = total * 0.30
        style = "大盘成长"
    # 熊市/偏空 → 提高防守
    elif "熊市" in regime or "偏空" in regime:
        aggressive = total * 0.20
        defensive = total * 0.80
        style = "大盘价值"
    # 震荡 → 攻守均衡
    else:
        aggressive = total * 0.45
        defensive = total * 0.55

    # 情绪修正
    if sentiment == "贪婪":
        aggressive *= 0.85
    elif sentiment == "极度恐惧":
        aggressive *= 1.1

    # 轮动修正
    if "成长" in rotation:
        style = "大盘成长" if style == "大盘成长" else "小盘成长"
    elif "周期" in rotation:
        style = "大盘价值"

    return aggressive, defensive, style


def _risk_level(regime: str, sentiment: str) -> str:
    """综合风险等级"""
    if regime in ("牛市格局", "震荡偏多") and sentiment in ("乐观", "贪婪"):
        return "中"  # 涨多了有回调风险
    elif regime in ("牛市格局", "震荡偏多") and sentiment in ("恐惧", "极度恐惧"):
        return "低"  # 牛市中恐慌是买点
    elif regime in ("熊市格局", "震荡偏空") and sentiment in ("乐观", "贪婪"):
        return "极高"  # 熊市中乐观是陷阱
    elif regime in ("熊市格局", "震荡偏空") and sentiment in ("恐惧", "极度恐惧"):
        return "中"  # 恐慌后可能反弹
    else:
        return "中"
