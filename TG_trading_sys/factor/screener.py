"""
多因子筛选器入口
================
提供面向用户的友好筛选接口，支持：
  - 预定义标的池（CSI300/CSI500/自定义）
  - 行业/市值/板块过滤
  - 黑名单自动排除（ST/停牌）
  - CSV/HTML 结果输出
"""

import logging
from typing import List, Dict, Optional
from datetime import datetime
import pandas as pd
import numpy as np

from ..data.cache import DataCache
from ..core.config import Config
from .factor_registry import FactorRegistry, list_factors
from .composite import run_screening

logger = logging.getLogger("tg.factor.screener")


# ── 沪深300前50样本 ──
CSI300_SAMPLE = [
    "600519", "000858", "601318", "600036", "000333", "601166", "600030",
    "600887", "601012", "002475", "300750", "000002", "601398", "600276",
    "002415", "300059", "600900", "000651", "002714", "601888",
    "600585", "000568", "603259", "688981", "002594", "300274",
    "600809", "000725", "002230", "601899", "600031", "000063",
    "300124", "002129", "601088", "600104", "000625", "601211",
    "600690", "000100", "300015", "600406", "601225", "600196",
    "002142", "000776", "601857", "300498", "002304", "600048",
]

CSI500_SAMPLE = [
    "688017", "300308", "300476", "002463", "600770", "300474",
    "688012", "300502", "002049", "603986", "688008", "300395",
    "688111", "002920", "300782", "300502", "688036", "603160",
    "300866", "002415", "603501", "688396", "300782", "002007",
    "688185", "300601", "603259", "688126", "300433", "002044",
]


def get_universe(name: str = "csi300") -> List[str]:
    """获取预定义标的池"""
    if name == "csi300":
        return CSI300_SAMPLE
    elif name == "csi500":
        return CSI500_SAMPLE
    elif name == "csi300_csi500":
        return CSI300_SAMPLE + CSI500_SAMPLE
    elif name == "small":
        # 部分小盘精选
        return CSI500_SAMPLE
    elif name.startswith("custom:"):
        return [c.strip() for c in name.split(":", 1)[1].split(",") if c.strip()]
    else:
        return CSI300_SAMPLE


def screen(
    universe: str = "csi300",
    weights: Dict[str, float] = None,
    categories: List[str] = None,
    top_n: int = 30,
    exclude_st: bool = True,
    min_market_cap_yi: float = 10.0,      # 最低市值（亿元）
    min_daily_amount_yi: float = 0.1,     # 最低日成交额（亿元）
    industry_filter: List[str] = None,     # 限定行业
    neutralize_industry: bool = True,
    output_csv: str = None,
    output_html: str = None,
    cache: DataCache = None,
) -> pd.DataFrame:
    """
    多因子筛选入口。

    Args:
        universe: 标的池预设名 (csi300/csi500/csi300_csi500/small/custom:code1,code2)
        weights: 自定义因子权重 (None=默认等权)
        categories: 限定大类 (None=全部)
        top_n: 返回前N只
        exclude_st: 排除ST股
        min_market_cap_yi: 最低总市值（亿元）
        min_daily_amount_yi: 最低日均成交额（亿元）
        industry_filter: 限定行业列表
        neutralize_industry: 是否行业中性化
        output_csv: CSV输出路径
        output_html: HTML输出路径
        cache: 数据缓存

    Returns:
        筛选结果 DataFrame
    """
    if cache is None:
        cache = DataCache()

    codes = get_universe(universe)
    logger.info(f"标的池: {universe} → {len(codes)} 只")

    # ── 预处理过滤 ──
    codes = _prefilter(
        cache, codes,
        exclude_st=exclude_st,
        min_market_cap=min_market_cap_yi,
        min_daily_amount=min_daily_amount_yi,
        industry_filter=industry_filter,
    )
    if not codes:
        logger.warning("预处理过滤后无可用标的")
        return pd.DataFrame()

    logger.info(f"预处理过滤后: {len(codes)} 只")

    # ── 因子筛选 ──
    result = run_screening(
        codes, weights=weights, categories=categories,
        top_n=top_n, neutralize_industry=neutralize_industry,
        cache=cache,
    )

    if result.empty:
        return result

    # 附加实时行情
    result = _attach_realtime_info(cache, result)

    # 输出
    if output_csv:
        result.to_csv(output_csv, index=False, encoding="utf-8-sig")
        logger.info(f"结果已保存至 {output_csv}")

    if output_html:
        _generate_html(result, output_html, universe)

    return result


def _prefilter(cache: DataCache, codes: List[str], exclude_st: bool,
               min_market_cap: float, min_daily_amount: float,
               industry_filter: List[str] = None) -> List[str]:
    """预处理过滤"""
    filtered = []
    for code in codes:
        info = cache.get_stock_basic(code) or {}
        name = info.get("name", "")

        # ST排除
        if exclude_st and ("ST" in name or "*ST" in name):
            logger.debug(f"排除ST: {code} {name}")
            continue

        # 市值过滤
        mcap = info.get("mcap_yi", 0)
        if mcap and mcap < min_market_cap:
            logger.debug(f"排除低市值: {code} {mcap}亿")
            continue

        # 成交额过滤
        turnover = info.get("turnover_pct", 0)
        if turnover and mcap and turnover < 0.1:
            logger.debug(f"排除低流动: {code}")
            continue

        # 行业过滤
        if industry_filter:
            ind = info.get("industry", "")
            if not any(f in ind for f in industry_filter):
                continue

        filtered.append(code)

    return filtered


def _attach_realtime_info(cache: DataCache, result: pd.DataFrame) -> pd.DataFrame:
    """附加实时行情信息"""
    pe_values = []
    pb_values = []
    mcap_values = []
    price_values = []

    for code in result["code"]:
        info = cache.get_stock_basic(code) or {}
        pe_values.append(info.get("pe_ttm", 0))
        pb_values.append(info.get("pb", 0))
        mcap_values.append(info.get("mcap_yi", 0))
        price_values.append(info.get("price", 0))

    result["pe_ttm"] = pe_values
    result["pb"] = pb_values
    result["market_cap_yi"] = mcap_values
    result["price"] = price_values

    return result


def _generate_html(result: pd.DataFrame, output_path: str, universe: str):
    """生成筛选结果 HTML 报告"""
    top_n = len(result)
    date = datetime.now().strftime("%Y-%m-%d")

    rows_html = ""
    for _, row in result.iterrows():
        score = row.get("composite_score", 0)
        score_color = "#4caf50" if score > 0.5 else ("#ffc107" if score > 0 else "#f44336")
        rows_html += f"""
        <tr>
            <td>{row.get('rank', '')}</td>
            <td>{row.get('code', '')}</td>
            <td><strong>{row.get('name', '')}</strong></td>
            <td>{row.get('industry', '')}</td>
            <td style="color:{score_color};font-weight:bold">{score:.3f}</td>
            <td>{row.get('pe_ttm', 0):.1f}</td>
            <td>{row.get('pb', 0):.2f}</td>
            <td>{row.get('market_cap_yi', 0):.0f}亿</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>多因子筛选结果 — {universe}</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background:#1a1a2e; color:#e0e0e0; padding:20px; }}
.container {{ max-width:1100px; margin:0 auto; }}
.header {{ background:linear-gradient(135deg,#16213e,#0f3460); border-radius:12px; padding:30px; margin-bottom:20px; text-align:center; }}
.header h1 {{ font-size:24px; }}
.header .sub {{ color:#888; font-size:14px; margin-top:5px; }}
table {{ width:100%; border-collapse:collapse; background:#16213e; border-radius:10px; overflow:hidden; }}
th {{ background:#0f3460; padding:12px 15px; text-align:left; font-size:13px; text-transform:uppercase; color:#888; }}
td {{ padding:10px 15px; border-bottom:1px solid #2a2a4a; font-size:14px; }}
tr:hover {{ background:#1e3a5f; }}
.footer {{ text-align:center; color:#555; font-size:12px; margin-top:30px; }}
</style>
</head>
<body>
<div class="container">
<div class="header">
    <h1>多因子选股结果</h1>
    <div class="sub">标的池: {universe} · {date} · Top {top_n}</div>
</div>
<table>
<thead>
<tr>
    <th>排名</th><th>代码</th><th>名称</th><th>行业</th><th>综合评分</th>
    <th>PE(TTM)</th><th>PB</th><th>市值</th>
</tr>
</thead>
<tbody>
{rows_html}
</tbody>
</table>
<div class="footer">
    TG-trading-sys V4.0 · 多因子选股引擎 · 生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
</div>
</div>
</body>
</html>"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)


# ── 便捷函数 ──

def screen_value_growth(top_n: int = 20) -> pd.DataFrame:
    """价值+成长双维筛选（等权偏重成长）"""
    return screen(
        universe="csi300_csi500",
        categories=["value", "growth"],
        weights={
            "pe_ttm": 0.07, "pb": 0.04, "fcf_yield": 0.05,
            "eps_growth_yoy": 0.10, "revenue_growth_yoy": 0.06,
            "earnings_acceleration": 0.06, "turnaround": 0.05,
            "revenue_leap": 0.05, "consensus_eps_cagr": 0.06,
            "roe": 0.08, "gross_margin": 0.05, "debt_ratio": 0.04,
            "momentum_20d": 0.04, "momentum_60d": 0.04,
        },
        top_n=top_n,
    )


def screen_quality_momentum(top_n: int = 20) -> pd.DataFrame:
    """质量+动量双维筛选"""
    return screen(
        universe="csi300_csi500",
        categories=["quality", "momentum"],
        top_n=top_n,
    )


def screen_turnaround(top_n: int = 20) -> pd.DataFrame:
    """反转信号筛选 — 聚焦扭亏/营收跃进/加速增长"""
    return screen(
        universe="csi300_csi500",
        categories=["growth"],
        weights={
            "turnaround": 0.30,
            "revenue_leap": 0.25,
            "earnings_acceleration": 0.20,
            "eps_growth_yoy": 0.15,
            "revenue_growth_yoy": 0.10,
        },
        top_n=top_n,
    )
