"""
事前风控规则引擎
================
链式规则检查，支持硬止损和软预警。
可配置的动态仓位上限（基于大盘状态）。
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable
from datetime import datetime

from ..core.config import Config

logger = logging.getLogger("tg.risk.rules")


# ═══════════════════════════════════════════════════════════════
# 数据结构
# ═══════════════════════════════════════════════════════════════

@dataclass
class RiskRule:
    """风控规则定义"""
    name: str                          # 规则名称
    description: str                   # 描述
    level: str                         # "block"(硬阻止) / "warn"(软预警)
    check_fn: Callable                 # 检查函数: (context) -> (passed: bool, message: str)


@dataclass
class RiskCheckResult:
    """单次风控检查结果"""
    passed: bool
    violations: List[dict] = field(default_factory=list)
    warnings: List[dict] = field(default_factory=list)
    max_position_pct: float = 0.80

    def is_blocked(self) -> bool:
        return any(v["level"] == "block" for v in self.violations)


# ═══════════════════════════════════════════════════════════════
# 风控引擎
# ═══════════════════════════════════════════════════════════════

class RiskEngine:
    """
    事前风控规则引擎 — 链式执行所有注册的风控规则。

    用法:
        engine = RiskEngine()
        engine.add_rule(RiskRule("单票上限", "单票≤10%", "block", check_single))
        result = engine.check(position_context)
    """

    def __init__(self, market_regime: str = "neutral"):
        """
        Args:
            market_regime: 大盘状态 (bull / neutral_bull / neutral / neutral_bear / bear)
        """
        self.rules: List[RiskRule] = []
        self.max_position_pct = Config.MAX_TOTAL_POSITION.get(market_regime, 0.50)
        self.market_regime = market_regime
        self._register_default_rules()

    def add_rule(self, rule: RiskRule):
        self.rules.append(rule)

    def set_market_regime(self, regime: str):
        """动态调整仓位上限（基于大盘状态）"""
        self.market_regime = regime
        total_positions = Config.MAX_TOTAL_POSITION
        self.max_position_pct = total_positions.get(regime, total_positions.get("neutral", 0.50))
        logger.info(f"大盘状态: {regime} → 总仓位上限: {self.max_position_pct*100:.0f}%")

    def check(self, context: dict) -> RiskCheckResult:
        """
        对一笔交易/订单执行所有风控规则检查。

        context 应包含:
          - code: 股票代码
          - name: 股票名称
          - proposed_weight: 建议仓位比例
          - proposed_position_pct: 建议仓位占资金比例
          - current_portfolio: dict {code: weight}  当前组合权重
          - current_sector_weights: dict {sector: weight}
          - target_sector: 目标代码所属行业
          - total_position: 当前总仓位
          - daily_amount: 日均成交额
        """
        violations = []
        warnings = []

        for rule in self.rules:
            try:
                passed, message = rule.check_fn(context)
                if not passed:
                    if rule.level == "block":
                        violations.append({
                            "rule": rule.name,
                            "level": "block",
                            "message": message,
                        })
                    else:
                        warnings.append({
                            "rule": rule.name,
                            "level": "warn",
                            "message": message,
                        })
            except Exception as e:
                logger.warning(f"规则 '{rule.name}' 执行异常: {e}")

        result = RiskCheckResult(
            passed=len(violations) == 0,
            violations=violations,
            warnings=warnings,
            max_position_pct=self.max_position_pct,
        )

        return result

    # ── 内置规则 ──

    def _register_default_rules(self):
        """注册默认风控规则"""
        self.add_rule(RiskRule(
            "单票仓位上限",
            f"单只股票仓位不超过 {Config.MAX_SINGLE_WEIGHT*100:.0f}%",
            "block",
            self._check_single_weight,
        ))
        self.add_rule(RiskRule(
            "行业集中度上限",
            f"单一行业仓位不超过 {Config.MAX_SECTOR_WEIGHT*100:.0f}%",
            "block",
            self._check_sector_weight,
        ))
        self.add_rule(RiskRule(
            "总仓位上限",
            "总仓位不超过大盘状态对应的上限",
            "block",
            self._check_total_position,
        ))
        self.add_rule(RiskRule(
            "ST/黑名单",
            "禁止买入ST股或黑名单标的",
            "block",
            self._check_blacklist,
        ))
        self.add_rule(RiskRule(
            "流动性检查",
            f"日均成交额不低于 {Config.MIN_DAILY_AMOUNT/10000:.0f}万",
            "warn",
            self._check_liquidity,
        ))
        self.add_rule(RiskRule(
            "止损检查",
            f"当前持仓浮亏不超过 {Config.DEFAULT_STOP_LOSS*100:.0f}%",
            "block",
            self._check_stop_loss,
        ))

    def _check_single_weight(self, ctx: dict) -> tuple:
        proposed = ctx.get("proposed_weight", 0)
        if proposed > Config.MAX_SINGLE_WEIGHT:
            return False, f"建议权重 {proposed*100:.1f}% > 上限 {Config.MAX_SINGLE_WEIGHT*100:.0f}%"
        return True, ""

    def _check_sector_weight(self, ctx: dict) -> tuple:
        proposed = ctx.get("proposed_weight", 0)
        sector = ctx.get("target_sector", "")
        current_sector = ctx.get("current_sector_weights", {}).get(sector, 0)
        new_sector = current_sector + proposed
        if new_sector > Config.MAX_SECTOR_WEIGHT:
            return False, f"行业 {sector} 新权重 {new_sector*100:.1f}% > 上限 {Config.MAX_SECTOR_WEIGHT*100:.0f}%"
        return True, ""

    def _check_total_position(self, ctx: dict) -> tuple:
        proposed = ctx.get("proposed_position_pct", ctx.get("proposed_weight", 0))
        total = ctx.get("total_position", 0) + proposed
        if total > self.max_position_pct:
            return False, f"新总仓位 {total*100:.1f}% > 上限 {self.max_position_pct*100:.0f}%"
        return True, ""

    def _check_blacklist(self, ctx: dict) -> tuple:
        code = ctx.get("code", "")
        name = ctx.get("name", "")
        if "ST" in name or "*ST" in name:
            return False, f"{name}({code}) 为ST股，禁止买入"
        return True, ""

    def _check_liquidity(self, ctx: dict) -> tuple:
        daily_amount = ctx.get("daily_amount", 0)
        if daily_amount < Config.MIN_DAILY_AMOUNT:
            return False, f"日均成交额 {daily_amount/10000:.0f}万 < {Config.MIN_DAILY_AMOUNT/10000:.0f}万"
        return True, ""

    def _check_stop_loss(self, ctx: dict) -> tuple:
        pnl_pct = ctx.get("current_pnl_pct", 0)
        if pnl_pct < -Config.DEFAULT_STOP_LOSS:
            return False, f"持仓浮亏 {pnl_pct*100:.1f}% 已触发止损线"
        return True, ""


# ═══════════════════════════════════════════════════════════════
# 动态止损/止盈
# ═══════════════════════════════════════════════════════════════

def atr_trailing_stop(
    prices: list, atr: float, multiplier: float = 2.0, direction: str = "long"
) -> list:
    """
    ATR 移动止损线计算。

    Args:
        prices: 价格序列（最近在前）
        atr: 当前 ATR 值
        multiplier: ATR倍数
        direction: long(追踪止损上移) / short(追踪止损下移)

    Returns:
        止损线序列（与 prices 等长）
    """
    stops = []
    if direction == "long":
        highest = prices[0]
        for p in prices:
            highest = max(highest, p)
            stop = highest - atr * multiplier
            if stops and stop < stops[-1]:
                stop = stops[-1]
            stops.append(stop)
    else:
        lowest = prices[0]
        for p in prices:
            lowest = min(lowest, p)
            stop = lowest + atr * multiplier
            if stops and stop > stops[-1]:
                stop = stops[-1]
            stops.append(stop)

    return stops
