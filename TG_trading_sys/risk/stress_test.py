"""
压力测试引擎
============
历史情景重放 + 因子冲击测试

历史情景：
  - 2015股灾: 沪深300 -45%, 创业板 -56%
  - 2018熊市: 沪深300 -25%, 全年阴跌
  - 2020疫情: 2月暴跌15% + 快速反弹
  - 2024量化危机: 小盘股流动性危机 -30%

因子冲击：
  - 利率 +100bp
  - 人民币贬值 10%
  - 油价飙升 30%
  - 信用利差扩大 200bp
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime
import numpy as np
import pandas as pd

logger = logging.getLogger("tg.risk.stress")


# ═══════════════════════════════════════════════════════════════
# 历史情景定义
# ═══════════════════════════════════════════════════════════════

@dataclass
class StressScenario:
    """压力测试情景"""
    name: str
    category: str                      # historical / factor / custom
    description: str
    # 对各类资产的冲击（百分比，如 -0.25 = -25%）
    equity_shock: float = 0.0          # 股票冲击
    small_cap_shock: float = 0.0       # 小盘股额外冲击
    bond_shock: float = 0.0            # 债券冲击（收益率变化bp）
    commodity_shock: float = 0.0       # 商品冲击
    fx_shock: float = 0.0              # 汇率冲击
    liquidity_shock: float = 0.0       # 流动性折价
    volatility_multiplier: float = 1.0 # 波动率放大倍数


# ── 预定义历史情景 ──

HISTORICAL_SCENARIOS = [
    StressScenario(
        name="2015股灾",
        category="historical",
        description="2015年6-9月A股崩盘：沪深300 -45%，创业板 -56%，千股跌停",
        equity_shock=-0.35,
        small_cap_shock=-0.20,     # 小盘额外 -20%
        volatility_multiplier=3.0,
        liquidity_shock=-0.10,     # 流动性折价 10%
    ),
    StressScenario(
        name="2018熊市",
        category="historical",
        description="2018年贸易战全年阴跌：沪深300 -25%，中证500 -33%",
        equity_shock=-0.25,
        small_cap_shock=-0.10,
        volatility_multiplier=1.5,
        fx_shock=-0.08,            # 人民币贬值 8%
    ),
    StressScenario(
        name="2020疫情暴跌",
        category="historical",
        description="2020年2-3月疫情冲击：2月跌15%→反弹→3月再跌",
        equity_shock=-0.15,
        volatility_multiplier=2.5,
        commodity_shock=-0.25,     # 油价暴跌
    ),
    StressScenario(
        name="2024量化危机",
        category="historical",
        description="2024年1-2月小盘股流动性危机：微盘指数 -40%+",
        equity_shock=-0.10,
        small_cap_shock=-0.35,
        liquidity_shock=-0.20,
        volatility_multiplier=2.0,
    ),
    StressScenario(
        name="2008全球金融危机",
        category="historical",
        description="2008年雷曼危机：全球股市 -50%+",
        equity_shock=-0.45,
        small_cap_shock=-0.10,
        volatility_multiplier=3.5,
        fx_shock=-0.05,
        commodity_shock=-0.30,
    ),
]

FACTOR_SCENARIOS = [
    StressScenario(
        name="利率+100bp",
        category="factor",
        description="央行加息100基点，债券和利率敏感资产承压",
        equity_shock=-0.08,           # 股票估值压缩
        bond_shock=1.0,              # 债券价格下跌
        volatility_multiplier=1.3,
    ),
    StressScenario(
        name="人民币贬值10%",
        category="factor",
        description="人民币对美元贬值10%，外债重的企业承压",
        equity_shock=-0.05,
        fx_shock=-0.10,
        volatility_multiplier=1.5,
    ),
    StressScenario(
        name="油价飙升30%",
        category="factor",
        description="地缘政治导致油价暴涨30%，航空/化工板块承压",
        equity_shock=-0.03,
        commodity_shock=0.30,
        volatility_multiplier=1.4,
    ),
    StressScenario(
        name="信用利差+200bp",
        category="factor",
        description="信用危机，企业融资成本飙升",
        equity_shock=-0.10,
        bond_shock=0.5,              # 信用债下跌
        small_cap_shock=-0.08,
        volatility_multiplier=1.8,
    ),
    StressScenario(
        name="流动性枯竭",
        category="factor",
        description="市场流动性骤降，买卖价差扩大",
        equity_shock=-0.08,
        liquidity_shock=-0.15,
        volatility_multiplier=2.0,
    ),
]


# ═══════════════════════════════════════════════════════════════
# 压力测试执行
# ═══════════════════════════════════════════════════════════════

def run_stress_test(
    holdings: List[dict],
    scenarios: List[StressScenario] = None,
    total_value: float = None,
) -> dict:
    """
    对组合持仓执行压力测试。

    Args:
        holdings: 持仓列表 [{code, name, weight, sector, market_cap_type, ...}]
        scenarios: 测试情景（None=使用全部预定义）
        total_value: 组合总价值（None=权重加总为100%）

    Returns:
        {
            "total_value": float,
            "base_value": float,
            "scenario_results": [{name, impact, remaining_value, impact_pct}, ...],
            "worst_scenario": str,
            "summary": str,
        }
    """
    if scenarios is None:
        scenarios = HISTORICAL_SCENARIOS + FACTOR_SCENARIOS

    if total_value is None:
        total_value = sum(h.get("current_value",
                               h.get("weight", 0) * 100000)
                          for h in holdings)

    scenario_results = []

    for scenario in scenarios:
        impact = _calc_scenario_impact(holdings, scenario)
        remaining = total_value + impact
        scenario_results.append({
            "name": scenario.name,
            "category": scenario.category,
            "description": scenario.description,
            "impact": round(impact, 2),
            "impact_pct": round(impact / total_value * 100, 1) if total_value > 0 else 0,
            "remaining_value": round(remaining, 2),
            "remaining_pct": round(remaining / total_value * 100, 1) if total_value > 0 else 0,
        })

    # 找最差情景
    worst = min(scenario_results, key=lambda x: x["impact"])

    # 分类汇总
    historical = [s for s in scenario_results if s["category"] == "historical"]
    factor = [s for s in scenario_results if s["category"] == "factor"]

    summary_lines = [
        f"组合总值: {total_value:,.0f}",
        f"历史情景最差: {_worst_of(historical)}",
        f"因子冲击最差: {_worst_of(factor)}",
        f"全局最差: {worst['name']} ({worst['impact_pct']}%)",
    ]

    return {
        "total_value": total_value,
        "scenario_results": scenario_results,
        "historical_worst": _worst_of(historical),
        "factor_worst": _worst_of(factor),
        "worst_scenario": worst["name"],
        "worst_impact_pct": worst["impact_pct"],
        "summary": "\n".join(summary_lines),
    }


def _calc_scenario_impact(holdings: List[dict], scenario: StressScenario) -> float:
    """计算单一情景对组合的冲击金额"""
    total_impact = 0
    for h in holdings:
        value = h.get("current_value", h.get("weight", 0) * 100000)
        weight = h.get("weight", 0)
        mcap = h.get("market_cap_yi", 0) or 0

        # 基础股票冲击
        shock = scenario.equity_shock

        # 小盘股额外冲击（市值 < 100亿）
        if mcap and mcap < 100:
            shock += scenario.small_cap_shock

        # 流动性折价
        shock += scenario.liquidity_shock

        # 行业特定调整
        sector = h.get("sector", "")
        if scenario.commodity_shock != 0 and sector in ("能源", "化工", "有色金属"):
            shock += scenario.commodity_shock * 0.5  # 商品相关行业更敏感

        if scenario.fx_shock != 0:
            # 出口型企业（制造/电子）部分对冲
            if sector in ("电子", "机械设备", "纺织服装"):
                shock += scenario.fx_shock * 0.3  # 贬值利好出口，但资本外流压力
            else:
                shock += scenario.fx_shock * 0.2

        # 波动率放大（最大损失扩大）
        if scenario.volatility_multiplier > 1:
            shock *= scenario.volatility_multiplier

        # 限制单资产冲击范围 [-80%, +10%]
        shock = max(-0.80, min(0.10, shock))

        impact = value * shock
        total_impact += impact

    return total_impact


def _worst_of(results: list) -> str:
    if not results:
        return "无数据"
    worst = min(results, key=lambda x: x["impact"])
    return f"{worst['name']} ({worst['impact_pct']}%)"


# ═══════════════════════════════════════════════════════════════
# 自定义情景构建
# ═══════════════════════════════════════════════════════════════

def custom_scenario(
    name: str,
    equity: float = 0,
    small_cap: float = 0,
    fx: float = 0,
    vol_mult: float = 1.0,
    liquidity: float = 0,
) -> StressScenario:
    """构建自定义压力测试情景"""
    return StressScenario(
        name=name,
        category="custom",
        description=f"自定义: 股票{equity*100:+.0f}%",
        equity_shock=equity,
        small_cap_shock=small_cap,
        fx_shock=fx,
        volatility_multiplier=vol_mult,
        liquidity_shock=liquidity,
    )
