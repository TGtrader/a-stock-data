"""
TG-trading-sys 估值报告生成器
=============================
整合 DCF + 相对估值 + 研报目标价 + 情景分析，
输出终端文本报告 & HTML 可视化报告。
"""

import json
from datetime import datetime
from typing import Optional

from ..core.config import Config
from ..data.cache import DataCache
from .dcf import dcf_value
from .relative_val import relative_value
from .earnings_forecast import get_earnings_forecast
from .wacc import estimate_wacc


def val_report(code: str, wacc: float = None, terminal_growth: float = None) -> dict:
    """
    综合估值报告 — 整合 DCF + 相对估值 + 一致预期。

    Returns:
        V4 标准估值报告 dict
    """
    cache = DataCache()

    # 基本信息
    basic_info = cache.get_stock_basic(code) or {}
    name = basic_info.get("name", code)
    current_price = basic_info.get("price", 0)

    # ── WACC ──
    wacc_data = estimate_wacc(code)
    if wacc is None:
        wacc = wacc_data.get("wacc", 0.09)

    # ── DCF ──
    dcf_result = dcf_value(code, wacc=wacc, terminal_growth=terminal_growth)

    # ── 相对估值 ──
    rel_result = relative_value(code)

    # ── 一致预期 ──
    earnings = get_earnings_forecast(code)

    # ── 情景分析 ──
    scenarios = _run_scenarios(code, dcf_result, rel_result, wacc, current_price)

    # ── 综合定价 ──
    # 科技成长股：PE-PEG/PB-ROE 为主，DCF 为辅（FCF不稳定）
    # 传统价值股：DCF 为主
    style = "tech"  # 默认使用科技股估值风格
    if style == "tech":
        default_weights = {"DCF": 0.10, "PE-PEG": 0.40, "PB-ROE": 0.35, "研报均价": 0.15}
    else:
        default_weights = {"DCF": 0.40, "PE-PEG": 0.25, "PB-ROE": 0.15, "研报均价": 0.20}

    estimates = []
    if dcf_result.get("per_share_value"):
        estimates.append(("DCF", dcf_result["per_share_value"], default_weights["DCF"]))
    if rel_result.get("peg_value", {}).get("fair_value"):
        estimates.append(("PE-PEG", rel_result["peg_value"]["fair_value"], default_weights["PE-PEG"]))
    if rel_result.get("pb_roe_value", {}).get("fair_value"):
        estimates.append(("PB-ROE", rel_result["pb_roe_value"]["fair_value"], default_weights["PB-ROE"]))
    if rel_result.get("research_consensus", {}).get("avg_target"):
        estimates.append(("研报均价", rel_result["research_consensus"]["avg_target"], default_weights["研报均价"]))

    if estimates:
        total_w = sum(e[2] for e in estimates)
        weights = [e[2] / total_w for e in estimates]
        final_value = sum(e[1] * w for e, w in zip(estimates, weights))
    else:
        final_value = None

    # 安全边际
    if final_value and current_price and current_price > 0:
        margin_of_safety = (final_value - current_price) / final_value * 100
        if margin_of_safety > 30:
            mos_verdict = "显著低估"
        elif margin_of_safety > 10:
            mos_verdict = "适度低估"
        elif margin_of_safety > -10:
            mos_verdict = "合理估值"
        elif margin_of_safety > -30:
            mos_verdict = "适度高估"
        else:
            mos_verdict = "显著高估"
    else:
        margin_of_safety = None
        mos_verdict = "无法判断"

    report = {
        "code": code,
        "name": name,
        "date": datetime.now().strftime("%Y-%m-%d"),
        "current_price": current_price,

        # 综合估值
        "final_value": round(final_value, 2) if final_value else None,
        "margin_of_safety_pct": round(margin_of_safety, 1) if margin_of_safety is not None else None,
        "margin_of_safety_verdict": mos_verdict,
        "estimate_components": [
            {"method": e[0], "value": e[1], "weight": f"{e[2]*100:.0f}%"}
            for e in estimates
        ],

        # 各模块详情
        "wacc": wacc_data,
        "dcf": dcf_result,
        "relative": rel_result,
        "earnings": earnings,
        "scenarios": scenarios,

        # 关键比率
        "key_ratios": {
            "pe_ttm": basic_info.get("pe_ttm", 0),
            "pb": basic_info.get("pb", 0),
            "market_cap_yi": basic_info.get("mcap_yi", 0),
        },
    }

    # ── 存入缓存 ──
    try:
        cache.db.upsert_valuation(code, report["date"], {
            "dcf_value": dcf_result.get("per_share_value"),
            "pe_peg_value": rel_result.get("peg_value", {}).get("fair_value"),
            "pb_roe_value": rel_result.get("pb_roe_value", {}).get("fair_value"),
            "consensus_target": rel_result.get("research_consensus", {}).get("avg_target"),
            "final_value": final_value,
            "scenarios": scenarios,
        })
    except Exception:
        pass

    return report


def _run_scenarios(code: str, dcf_result: dict, rel_result: dict,
                   wacc: float, current_price: float) -> dict:
    """运行三档情景分析"""
    scenarios = {}
    dcf_base = dcf_result.get("per_share_value")
    rel_base = rel_result.get("final_estimate")

    for scenario, params in Config.SCENARIOS.items():
        g_adj = params["growth_adj"]
        m_adj = params["margin_adj"]

        scenario_data = {
            "growth_adjustment": f"{g_adj*100:.0f}%",
            "margin_adjustment": f"{m_adj*100:.0f}%",
        }

        # DCF 情景：调整WACC 和 增长率
        if dcf_base:
            adj_wacc = wacc * (2 - m_adj)  # 乐观→WACC降低, 悲观→WACC升高
            adj_growth = dcf_result.get("terminal_growth", 3.0) / 100 * g_adj
            try:
                scenario_dcf = dcf_value(code, wacc=adj_wacc, terminal_growth=adj_growth)
                scenario_data["dcf_value"] = scenario_dcf.get("per_share_value")
            except Exception:
                scenario_data["dcf_value"] = dcf_base * m_adj

        # 相对估值情景
        if rel_base:
            scenario_data["relative_value"] = round(rel_base * m_adj, 2)

        # 综合
        vals = [v for v in [scenario_data.get("dcf_value"), scenario_data.get("relative_value")] if v]
        if vals:
            scenario_data["composite_value"] = round(sum(vals) / len(vals), 2)
        else:
            scenario_data["composite_value"] = None

        if current_price and current_price > 0 and scenario_data.get("composite_value"):
            upside = (scenario_data["composite_value"] - current_price) / current_price * 100
            scenario_data["upside_pct"] = round(upside, 1)
        else:
            scenario_data["upside_pct"] = None

        scenarios[scenario] = scenario_data

    return scenarios


# ═══════════════════════════════════════════════════════════════
# 终端打印
# ═══════════════════════════════════════════════════════════════

def print_val_report(report: dict):
    """在终端打印简洁的估值报告"""
    if "error" in report:
        print(f"X 估值分析失败: {report['error']}")
        return

    name = report.get("name", report.get("code", ""))
    code = report.get("code", "")
    price = report.get("current_price", 0)

    print(f"\n{'='*60}")
    print(f"  估值分析报告 — {name}({code})")
    print(f"{'='*60}")
    print(f"  日期: {report['date']}     现价: {price}")

    # 综合结果
    final_val = report.get("final_value")
    mos = report.get("margin_of_safety_pct")
    mos_v = report.get("margin_of_safety_verdict", "")

    print(f"\n  ┌─────────────────────────────────────┐")
    if final_val:
        print(f"  │  综合估值: {final_val} 元"
              f"  {'△' if mos and mos > 0 else '▽'} {abs(mos or 0):.1f}%"
              f"  ({mos_v})  │")
    else:
        print(f"  │  综合估值: 数据不足                        │")
    print(f"  └─────────────────────────────────────┘")

    # 估值分项
    components = report.get("estimate_components", [])
    if components:
        print(f"\n  【估值分项】")
        for c in components:
            print(f"    {c['method']:<12} {c['value']:>10.2f}  权重 {c['weight']}")

    # DCF 关键参数
    dcf = report.get("dcf", {})
    if dcf.get("per_share_value"):
        print(f"\n  【DCF 模型】")
        print(f"    WACC: {dcf.get('wacc', '?')}%  |  永续增长: {dcf.get('terminal_growth', '?')}%")
        print(f"    每股价值: {dcf['per_share_value']}  |  终值占比: {dcf.get('terminal_value_ratio', '?')}%")
        tv_warn = dcf.get("terminal_value_warning")
        if tv_warn:
            print(f"    !! {tv_warn}")

    # 相对估值
    rel = report.get("relative", {})
    peg = rel.get("peg_value", {})
    pb_roe = rel.get("pb_roe_value", {})
    print(f"\n  【相对估值】")
    print(f"    PE-PEG: {peg.get('detail', '数据不足')} → {peg.get('verdict', '')}")
    if peg.get("fair_value"):
        print(f"           合理价: {peg['fair_value']}")
    print(f"    PB-ROE: {pb_roe.get('detail', '数据不足')} → {pb_roe.get('verdict', '')}")
    if pb_roe.get("fair_value"):
        print(f"           合理价: {pb_roe['fair_value']}")

    # 研报
    res = rel.get("research_consensus", {})
    if res.get("avg_target"):
        print(f"\n  【研报共识】({res.get('count', 0)} 篇)")
        print(f"    目标均价: {res['avg_target']}  |  区间: [{res.get('low_target', '?')}, {res.get('high_target', '?')}]")
        ratings = res.get("ratings_summary", {})
        if ratings:
            print(f"    评级: {ratings}")

    # 情景分析
    scenarios = report.get("scenarios", {})
    if scenarios:
        print(f"\n  【情景分析】")
        print(f"    {'情景':<6} {'估值':>10} {'涨跌幅':>8}")
        print(f"    {'-'*26}")
        for name, data in scenarios.items():
            val = data.get("composite_value", "-")
            upside = data.get("upside_pct")
            val_str = f"{val:.2f}" if isinstance(val, (int, float)) else str(val)
            up_str = f"{upside:+.1f}%" if upside is not None else "-"
            print(f"    {name:<6} {val_str:>10} {up_str:>8}")

    # 一致预期
    earnings = report.get("earnings", {})
    if earnings.get("eps_forecast"):
        eps_list = earnings["eps_forecast"]
        cagr = earnings.get("cagr_3y", 0)
        print(f"\n  【一致预期】来源: {earnings.get('source', '未知')}")
        print(f"    预测EPS: {eps_list}  |  3年CAGR: {cagr*100:.1f}%")

    print(f"\n{'='*60}\n")


# ═══════════════════════════════════════════════════════════════
# HTML 报告生成
# ═══════════════════════════════════════════════════════════════

def generate_html_report(report: dict, output_path: str = None) -> str:
    """生成 HTML 估值报告"""
    name = report.get("name", report.get("code", ""))
    code = report.get("code", "")
    date = report.get("date", "")
    price = report.get("current_price", 0)
    final_val = report.get("final_value")
    mos = report.get("margin_of_safety_pct")
    mos_v = report.get("margin_of_safety_verdict", "")

    # 颜色
    if mos and mos > 10:
        score_color = "#4caf50"
        mos_emoji = "🟢"
    elif mos and mos > -10:
        score_color = "#ffc107"
        mos_emoji = "🟡"
    else:
        score_color = "#f44336"
        mos_emoji = "🔴"

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>估值分析报告 — {name}({code})</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #1a1a2e; color: #e0e0e0; padding: 20px; }}
.container {{ max-width: 960px; margin: 0 auto; }}
.header {{ background: linear-gradient(135deg, #16213e, #0f3460); border-radius: 12px; padding: 30px; margin-bottom: 20px; text-align: center; }}
.header h1 {{ font-size: 28px; }}
.valuation-badge {{ display: inline-block; padding: 12px 36px; border-radius: 30px; font-size: 28px; font-weight: bold; margin: 15px 0; color: {score_color}; background: rgba(255,255,255,0.05); }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 15px; margin-bottom: 20px; }}
.card {{ background: #16213e; border-radius: 10px; padding: 20px; border: 1px solid #2a2a4a; }}
.card h3 {{ font-size: 15px; color: #888; margin-bottom: 12px; text-transform: uppercase; letter-spacing: 1px; }}
.value-big {{ font-size: 28px; font-weight: bold; }}
.bull {{ color: #4caf50; }}
.bear {{ color: #f44336; }}
.neutral {{ color: #ffc107; }}
.row {{ display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid #1e2a3a; }}
.row:last-child {{ border-bottom: none; }}
.scenario-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }}
.scenario-card {{ background: #1a1a2e; border-radius: 8px; padding: 16px; text-align: center; border: 1px solid #2a2a4a; }}
.scenario-card .title {{ font-size: 14px; color: #888; }}
.scenario-card .value {{ font-size: 22px; font-weight: bold; margin: 8px 0; }}
.scenario-card .upside {{ font-size: 13px; }}
.footer {{ text-align: center; color: #555; font-size: 12px; margin-top: 30px; }}
</style>
</head>
<body>
<div class="container">
<div class="header">
    <h1>{name} ({code})</h1>
    <p style="color:#888;font-size:14px">{date} · 现价 {price}</p>
    <div class="valuation-badge">{mos_emoji} {final_val or 'N/A'}</div>
    <p style="margin-top:8px">综合估值 · 安全边际: {mos:+.1f}% · {mos_v}</p>
</div>

<div class="grid">
    <div class="card">
        <h3>DCF 估值</h3>
        <div class="value-big {'bull' if report.get('dcf',{}).get('per_share_value',0) > price else 'bear'}">{report.get('dcf',{}).get('per_share_value','N/A')}</div>
        <p style="color:#888;font-size:13px">WACC {report.get('dcf',{}).get('wacc','?')}% · 永续g {report.get('dcf',{}).get('terminal_growth','?')}%</p>
    </div>
    <div class="card">
        <h3>PE-PEG 估值</h3>
        <div class="value-big">{report.get('relative',{}).get('peg_value',{}).get('fair_value','N/A')}</div>
        <p style="color:#888;font-size:13px">{report.get('relative',{}).get('peg_value',{}).get('detail','')}</p>
    </div>
    <div class="card">
        <h3>研报目标均价</h3>
        <div class="value-big">{report.get('relative',{}).get('research_consensus',{}).get('avg_target','N/A')}</div>
        <p style="color:#888;font-size:13px">{report.get('relative',{}).get('research_consensus',{}).get('count',0)} 篇研报</p>
    </div>
</div>

<div class="card" style="margin-bottom:20px">
    <h3>情景分析</h3>
    <div class="scenario-grid">
"""
    scenarios = report.get("scenarios", {})
    for name, data in scenarios.items():
        val = data.get("composite_value", "-")
        upside = data.get("upside_pct")
        val_str = f"{val:.2f}" if isinstance(val, (int, float)) else str(val)
        up_str = f"{upside:+.1f}%" if upside is not None else "-"
        up_color = "bull" if upside and upside > 0 else "bear"
        html += f"""        <div class="scenario-card">
            <div class="title">{name}</div>
            <div class="value">{val_str}</div>
            <div class="upside {up_color}">{up_str}</div>
        </div>
"""
    html += """    </div>
</div>

<div class="footer">
    TG-trading-sys V4.0 · 估值分析模块 · 生成时间: """ + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + """
</div>
</div>
</body>
</html>"""

    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)

    return html
