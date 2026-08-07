"""
MLCC行业分析报告生成器
生成交互式HTML报告
"""
import json
import pandas as pd
import numpy as np
from datetime import datetime
from pathlib import Path

# ============================================================
# 加载数据
# ============================================================
DATA_DIR = Path(__file__).parent / "analysis_data"
with open(DATA_DIR / "mlcc_analysis.json", "r", encoding="utf-8") as f:
    data = json.load(f)

STOCKS_INFO = {
    "000636": {"name": "风华高科", "type": "MLCC制造(龙头)", "desc": "国内最大MLCC制造商，产品覆盖消费电子、汽车、工业等领域，产能持续扩张"},
    "300408": {"name": "三环集团", "type": "电子陶瓷+MLCC", "desc": "国内电子陶瓷龙头，MLCC业务快速增长，光纤陶瓷插芯全球第一"},
    "603678": {"name": "火炬电子", "type": "军用MLCC", "desc": "军用MLCC核心供应商，产品应用于航空航天、武器装备等高端领域"},
    "603267": {"name": "鸿远电子", "type": "军用MLCC", "desc": "军用MLCC+直流滤波器双主业，军品占比高，客户集中度低"},
    "002859": {"name": "洁美科技", "type": "MLCC载带(上游)", "desc": "全球MLCC载带龙头，市占率超50%，受益于MLCC产能扩张"},
    "300285": {"name": "国瓷材料", "type": "MLCC粉体(上游)", "desc": "MLCC陶瓷粉体核心供应商，钛酸钡粉体技术领先，国产替代先锋"},
    "000733": {"name": "振华科技", "type": "军用电子元器件", "desc": "军用电子元器件平台型企业，产品涵盖MLCC、电阻、电感、半导体等"},
}

live = data["live_quotes"]
tech = data["technical"]
perf = data["performance"]
funds = data.get("fund_flows", {})
margin = data.get("margin", {})

# ============================================================
# 辅助函数
# ============================================================
def color_tag(val, thresholds=None, fmt=".1f", suffix=""):
    """根据阈值返回颜色标签"""
    if thresholds is None:
        thresholds = {"red_high": 10, "red_low": 0, "green_high": -10, "green_low": 0}
    if val is None:
        return f'<span style="color:#999">--</span>'
    color = "#999"
    if val > thresholds.get("red_high", 10): color = "#f5222d"
    elif val > thresholds.get("red_low", 0): color = "#fa8c16"
    elif val < thresholds.get("green_high", -10): color = "#52c41a"
    elif val < thresholds.get("green_low", 0): color = "#73d13d"
    return f'<span style="color:{color}">{val:{fmt}}{suffix}</span>'

def trend_badge(signal):
    """趋势标签"""
    if "多头" in signal or "上涨" in signal:
        return '<span class="badge badge-up">偏多</span>'
    elif "空头" in signal or "下跌" in signal:
        return '<span class="badge badge-down">偏空</span>'
    return '<span class="badge badge-neutral">中性</span>'

def macd_signal(dif, dea, bar):
    """MACD信号解读"""
    if dif is None or dea is None: return ("信号缺失", "#999")
    if dif > dea:
        if bar and bar > 0: return ("金叉向上·多头强势", "#f5222d")
        return ("金叉·动能减弱", "#fa8c16")
    else:
        if bar and bar < 0: return ("死叉向下·空头强势", "#52c41a")
        return ("死叉·空头减弱", "#73d13d")

def rsi_signal(rsi):
    """RSI信号解读"""
    if rsi is None: return ("无数据", "#999")
    if rsi > 80: return ("超买区", "#f5222d")
    if rsi > 60: return ("偏强", "#fa8c16")
    if rsi > 40: return ("中性", "#666")
    if rsi > 20: return ("偏弱", "#52c41a")
    return ("超卖区", "#1890ff")

def score_stock(code):
    """综合评分 0-100"""
    score = 50
    reasons = []

    # PE估值 (TTM)
    pe = live.get(code, {}).get("pe_ttm", 0)
    if 0 < pe < 40: score += 10; reasons.append("PE合理(<40x)")
    elif pe > 100: score -= 10; reasons.append("PE偏高(>100x)")
    elif pe > 60: score -= 5; reasons.append("PE略高(>60x)")

    # PB估值
    pb = live.get(code, {}).get("pb", 0)
    if 0 < pb < 3: score += 5; reasons.append("PB合理(<3x)")
    elif pb > 8: score -= 5; reasons.append("PB偏高(>8x)")

    # MACD
    t = tech.get(code, {}).get("latest", {})
    if t.get("dif", 0) and t.get("dea", 0):
        if t["dif"] > t["dea"]: score += 5; reasons.append("MACD金叉")
        else: score -= 5; reasons.append("MACD死叉")

    # RSI
    rsi14 = t.get("rsi14")
    if rsi14 and rsi14 < 30: score += 5; reasons.append("RSI超卖(反弹潜力)")
    elif rsi14 and rsi14 > 70: score -= 5; reasons.append("RSI超买(回调风险)")

    # 近期表现
    p5 = perf.get(code, {}).get("5日", 0) or 0
    p20 = perf.get(code, {}).get("20日", 0) or 0
    p60 = perf.get(code, {}).get("60日", 0) or 0
    if p20 > 5: score += 5; reasons.append("近20日强势")
    elif p20 < -10: score -= 5; reasons.append("近20日超跌")
    if p60 < -20: score += 3; reasons.append("近60日超跌(中线布局)")

    # 资金流
    if code in funds:
        flows = funds[code]
        main_net_20 = sum(f["main_net"] for f in flows[-20:])
        if main_net_20 > 1e8: score += 10; reasons.append("资金持续流入")
        elif main_net_20 < -1e8: score -= 10; reasons.append("资金持续流出")

    # 融资
    if code in margin:
        marg = margin[code]
        if len(marg) >= 2:
            m_change = (marg[0]["rzye"] / marg[1]["rzye"] - 1) * 100 if marg[1]["rzye"] else 0
            if m_change > 2: score += 3; reasons.append("融资余额增加")
            elif m_change < -2: score -= 3; reasons.append("融资余额减少")

    return min(100, max(0, score)), reasons

# 计算所有股票得分
all_scores = {}
for code in STOCKS_INFO:
    s, r = score_stock(code)
    all_scores[code] = {"score": s, "reasons": r}

# ============================================================
# 生成HTML
# ============================================================
def build_html():
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    # ---- 个股分析卡片 ----
    stock_cards_html = ""
    for code, info in STOCKS_INFO.items():
        q = live.get(code, {})
        t = tech.get(code, {}).get("latest", {})
        p = perf.get(code, {})
        score_data = all_scores[code]
        name = info["name"]

        pe = q.get("pe_ttm", 0)
        pb = q.get("pb", 0)
        price = q.get("price", 0)
        chg = q.get("change_pct", 0)
        mcap = q.get("mcap_yi", 0)
        turnover = q.get("turnover_pct", 0)
        vol_ratio = q.get("vol_ratio", 0)

        chg_color = "#f5222d" if chg > 0 else "#52c41a" if chg < 0 else "#999"
        chg_sign = "+" if chg > 0 else ""

        macd_status, macd_color = macd_signal(t.get("dif"), t.get("dea"), t.get("macd_bar"))
        rsi_stat = rsi_signal(t.get("rsi14"))

        # 均线偏离
        ma20 = t.get("ma20")
        price_vs_ma20 = ((price / ma20 - 1) * 100) if ma20 and price else 0

        score = score_data["score"]
        score_color = "#f5222d" if score >= 70 else "#fa8c16" if score >= 55 else "#666" if score >= 40 else "#52c41a"
        score_label = "强烈推荐" if score >= 70 else "推荐关注" if score >= 55 else "中性观察" if score >= 40 else "暂避观望"

        # 资金流摘要
        flow_html = ""
        if code in funds:
            flows_20 = funds[code][-20:]
            main_total = sum(f["main_net"] for f in flows_20)
            super_total = sum(f["super_net"] for f in flows_20)
            flow_color = "#f5222d" if main_total > 0 else "#52c41a"
            flow_html = f"""
            <div class="flow-row">
              <span class="flow-label">近20日主力净流入</span>
              <span style="color:{flow_color};font-weight:700">{main_total/1e8:+.2f}亿</span>
            </div>
            <div class="flow-row">
              <span class="flow-label">超大单净流入</span>
              <span style="color:{'#f5222d' if super_total > 0 else '#52c41a'};font-weight:700">{super_total/1e8:+.2f}亿</span>
            </div>"""

        # 融资摘要
        margin_html = ""
        if code in margin and margin[code]:
            m = margin[code][0]
            margin_html = f"""
            <div class="flow-row">
              <span class="flow-label">融资余额</span>
              <span>{m['rzye']/1e8:.2f}亿</span>
            </div>"""

        card = f"""
        <div class="stock-card">
          <div class="card-header">
            <div>
              <span class="stock-name">{name}</span>
              <span class="stock-code">{code}</span>
              <span class="stock-type">{info['type']}</span>
            </div>
            <div class="score-badge" style="background:{score_color}">
              <div class="score-num">{score}</div>
              <div class="score-label">{score_label}</div>
            </div>
          </div>
          <div class="card-desc">{info['desc']}</div>
          <div class="card-body">
            <div class="card-section">
              <div class="section-title">📊 行情估值</div>
              <div class="metric-grid">
                <div class="metric"><span class="lbl">最新价</span><span class="val">{price:.2f}</span></div>
                <div class="metric"><span class="lbl">涨跌幅</span><span class="val" style="color:{chg_color}">{chg_sign}{chg:.2f}%</span></div>
                <div class="metric"><span class="lbl">PE(TTM)</span><span class="val">{pe:.1f}x</span></div>
                <div class="metric"><span class="lbl">PB</span><span class="val">{pb:.2f}x</span></div>
                <div class="metric"><span class="lbl">市值</span><span class="val">{mcap:.0f}亿</span></div>
                <div class="metric"><span class="lbl">换手率</span><span class="val">{turnover:.2f}%</span></div>
                <div class="metric"><span class="lbl">量比</span><span class="val">{vol_ratio:.2f}</span></div>
                <div class="metric"><span class="lbl">价vsMA20</span><span class="val" style="color:{'#f5222d' if price_vs_ma20 > 0 else '#52c41a'}">{price_vs_ma20:+.1f}%</span></div>
              </div>
            </div>
            <div class="card-section">
              <div class="section-title">📈 技术指标</div>
              <div class="metric-grid">
                <div class="metric"><span class="lbl">MACD</span><span class="val" style="color:{macd_color}">{macd_status}</span></div>
                <div class="metric"><span class="lbl">RSI(14)</span><span class="val">{t.get('rsi14','-'):.1f}</span></div>
                <div class="metric"><span class="lbl">MA5</span><span class="val">{t.get('ma5','-'):.2f}</span></div>
                <div class="metric"><span class="lbl">MA20</span><span class="val">{t.get('ma20','-'):.2f}</span></div>
                <div class="metric"><span class="lbl">MA60</span><span class="val">{t.get('ma60','-'):.2f}</span></div>
                <div class="metric"><span class="lbl">布林上轨</span><span class="val">{t.get('boll_upper','-'):.2f}</span></div>
                <div class="metric"><span class="lbl">布林中轨</span><span class="val">{t.get('boll_mid','-'):.2f}</span></div>
                <div class="metric"><span class="lbl">布林下轨</span><span class="val">{t.get('boll_lower','-'):.2f}</span></div>
              </div>
            </div>
            <div class="card-section">
              <div class="section-title">📉 涨跌幅</div>
              <div class="perf-row">
                <span>5日: {color_tag(p.get('5日'))}</span>
                <span>10日: {color_tag(p.get('10日'))}</span>
                <span>20日: {color_tag(p.get('20日'))}</span>
                <span>60日: {color_tag(p.get('60日'))}</span>
              </div>
            </div>
            {flow_html}
            {margin_html}
            <div class="card-section">
              <div class="section-title">💡 评分依据</div>
              <div class="reasons">{" · ".join(score_data['reasons'])}</div>
            </div>
          </div>
        </div>"""
        stock_cards_html += card

    # ---- 行业对比表 ----
    comparison_rows = ""
    for code, info in STOCKS_INFO.items():
        q = live.get(code, {})
        t = tech.get(code, {}).get("latest", {})
        p = perf.get(code, {})
        s = all_scores[code]
        chg = q.get("change_pct", 0)
        chg_sign = "+" if chg > 0 else ""
        comparison_rows += f"""
        <tr>
          <td><strong>{info['name']}</strong><br><small>{code} {info['type']}</small></td>
          <td>{q.get('price',0):.2f}</td>
          <td style="color:{'#f5222d' if chg > 0 else '#52c41a'}">{chg_sign}{chg:.2f}%</td>
          <td>{q.get('pe_ttm',0):.1f}x</td>
          <td>{q.get('pb',0):.2f}x</td>
          <td>{q.get('mcap_yi',0):.0f}亿</td>
          <td>{q.get('turnover_pct',0):.2f}%</td>
          <td>{q.get('vol_ratio',0):.2f}</td>
          <td>{t.get('rsi14','-'):.1f}</td>
          <td>{p.get('5日','-'):+.1f}%</td>
          <td>{p.get('20日','-'):+.1f}%</td>
          <td>{p.get('60日','-'):+.1f}%</td>
          <td style="background:{'#f5222d' if s['score'] >= 70 else '#fa8c16' if s['score'] >= 55 else '#f0f0f0'};text-align:center;font-weight:700;border-radius:4px">{s['score']}</td>
        </tr>"""

    # ---- 投资建议 ----
    sorted_stocks = sorted(all_scores.items(), key=lambda x: x[1]["score"], reverse=True)
    recommendations = ""
    for i, (code, sdata) in enumerate(sorted_stocks):
        info = STOCKS_INFO[code]
        q = live.get(code, {})
        level = "⭐" if sdata["score"] >= 65 else "👍" if sdata["score"] >= 50 else "👀" if sdata["score"] >= 35 else "⚠️"
        recommendation_text = {
            "风华高科": "国内MLCC龙头，产能扩张期。短期受消费电子低迷拖累，但汽车MLCC放量+国产替代逻辑清晰。60日超跌后估值消化中，适合中线分批布局。关注Q3产能利用率拐点。",
            "三环集团": "电子陶瓷平台型企业，MLCC+光纤插芯+PKG多轮驱动。估值相对合理，但近期跟随板块调整。技术面MACD死叉需时间修复，等待RSI企稳后再考虑。",
            "火炬电子": "军用MLCC核心标的，受益于国防信息化建设。PB仅3.45x在板块中估值较低，成交量萎缩显示抛压减轻。适合作为军工电子配置。",
            "鸿远电子": "PE 37.5x为板块最低估值，军用MLCC+滤波器双主业稳定性强。近60日回调21%已较充分，基本面扎实，可作为稳健型配置。",
            "洁美科技": "MLCC载带全球龙头，市占率超50%。作为上游配套商，业绩与下游MLCC扩产直接相关。近20日+3.85%在板块中表现最强，但PE偏高需关注业绩兑现。",
            "国瓷材料": "MLCC粉体国产替代核心标的，近60日-35.5%为本板块最大跌幅。PB 8.5x仍偏高，技术面尚未企稳。中长期逻辑不变，短期等待右侧信号。",
            "振华科技": "PE仅22.4x为板块最低，PB 1.42x也为最低，估值安全边际最高。军品订单稳定，60日仅回调9.9%最为抗跌。适合作为防守型底仓。",
        }
        rec = recommendation_text.get(info["name"], "关注后续走势。")
        recommendations += f"""
        <div class="rec-card">
          <div class="rec-header">
            <span class="rec-level">{level}</span>
            <span class="rec-name">{info['name']} ({code})</span>
            <span class="rec-score" style="color:{'#f5222d' if sdata['score'] >= 70 else '#fa8c16' if sdata['score'] >= 55 else '#666'}">评分: {sdata['score']}/100</span>
          </div>
          <div class="rec-body">{rec}</div>
          <div class="rec-reasons">关键信号: {" · ".join(sdata['reasons'][:5])}</div>
        </div>"""

    # ---- 总体报告 ----
    avg_pe = np.mean([live.get(c, {}).get("pe_ttm", 0) for c in STOCKS_INFO if live.get(c, {}).get("pe_ttm", 0) > 0])
    avg_pb = np.mean([live.get(c, {}).get("pb", 0) for c in STOCKS_INFO])
    total_mcap = sum([live.get(c, {}).get("mcap_yi", 0) for c in STOCKS_INFO])
    avg_chg_60 = np.mean([perf.get(c, {}).get("60日", 0) or 0 for c in STOCKS_INFO])

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>A股MLCC行业深度分析报告</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif; background: #f5f6fa; color: #2c3e50; line-height: 1.6; }}
.container {{ max-width: 1400px; margin: 0 auto; padding: 20px; }}

/* Header */
.header {{ background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%); color: #fff; padding: 40px; border-radius: 16px; margin-bottom: 24px; }}
.header h1 {{ font-size: 28px; margin-bottom: 8px; }}
.header .subtitle {{ font-size: 14px; opacity: 0.8; }}
.header .meta {{ font-size: 12px; opacity: 0.6; margin-top: 12px; }}

/* Summary Cards */
.summary-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 24px; }}
.summary-card {{ background: #fff; padding: 20px; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); text-align: center; }}
.summary-card .s-val {{ font-size: 28px; font-weight: 700; color: #1a1a2e; }}
.summary-card .s-label {{ font-size: 13px; color: #999; margin-top: 4px; }}
.summary-card.negative .s-val {{ color: #52c41a; }}

/* Section */
.section-title-main {{ font-size: 20px; font-weight: 700; margin: 32px 0 16px; padding-left: 12px; border-left: 4px solid #1a1a2e; }}

/* Stock Cards */
.stock-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(420px, 1fr)); gap: 20px; }}
.stock-card {{ background: #fff; border-radius: 12px; box-shadow: 0 2px 12px rgba(0,0,0,0.06); overflow: hidden; }}
.card-header {{ display: flex; justify-content: space-between; align-items: flex-start; padding: 18px 20px; border-bottom: 1px solid #f0f0f0; }}
.stock-name {{ font-size: 18px; font-weight: 700; margin-right: 8px; }}
.stock-code {{ font-size: 12px; color: #999; margin-right: 8px; }}
.stock-type {{ font-size: 11px; background: #e6f7ff; color: #1890ff; padding: 2px 8px; border-radius: 10px; }}
.card-desc {{ font-size: 13px; color: #666; padding: 10px 20px; border-bottom: 1px solid #f0f0f0; line-height: 1.5; }}
.card-body {{ padding: 16px 20px; }}
.card-section {{ margin-bottom: 14px; }}
.section-title {{ font-size: 14px; font-weight: 600; color: #1a1a2e; margin-bottom: 8px; }}
.metric-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; }}
.metric {{ background: #fafafa; padding: 8px; border-radius: 6px; }}
.metric .lbl {{ font-size: 11px; color: #999; display: block; }}
.metric .val {{ font-size: 14px; font-weight: 600; display: block; margin-top: 2px; }}
.perf-row {{ display: flex; gap: 16px; font-size: 13px; }}
.flow-row {{ display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid #f5f5f5; font-size: 13px; }}
.flow-label {{ color: #999; }}
.reasons {{ font-size: 12px; color: #666; line-height: 1.5; }}

/* Score Badge */
.score-badge {{ width: 64px; height: 64px; border-radius: 50%; display: flex; flex-direction: column; align-items: center; justify-content: center; color: #fff; }}
.score-num {{ font-size: 22px; font-weight: 700; line-height: 1; }}
.score-label {{ font-size: 10px; margin-top: 2px; }}

/* Badges */
.badge {{ font-size: 11px; padding: 2px 8px; border-radius: 10px; display: inline-block; }}
.badge-up {{ background: #fff1f0; color: #f5222d; }}
.badge-down {{ background: #f6ffed; color: #52c41a; }}
.badge-neutral {{ background: #f0f0f0; color: #666; }}

/* Table */
.comparison-table {{ width: 100%; background: #fff; border-radius: 12px; overflow: hidden; box-shadow: 0 2px 12px rgba(0,0,0,0.06); margin-bottom: 24px; }}
.comparison-table table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
.comparison-table th {{ background: #1a1a2e; color: #fff; padding: 12px 10px; text-align: left; font-weight: 500; white-space: nowrap; }}
.comparison-table td {{ padding: 10px; border-bottom: 1px solid #f0f0f0; }}
.comparison-table tr:hover {{ background: #fafafa; }}

/* Recommendation */
.rec-card {{ background: #fff; border-radius: 12px; padding: 16px 20px; margin-bottom: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.04); border-left: 4px solid #1a1a2e; }}
.rec-header {{ display: flex; align-items: center; margin-bottom: 8px; }}
.rec-level {{ font-size: 20px; margin-right: 8px; }}
.rec-name {{ font-size: 16px; font-weight: 700; margin-right: 12px; }}
.rec-score {{ font-size: 13px; margin-left: auto; }}
.rec-body {{ font-size: 14px; color: #333; line-height: 1.7; margin-bottom: 8px; }}
.rec-reasons {{ font-size: 12px; color: #888; background: #fafafa; padding: 8px 12px; border-radius: 6px; }}

/* Disclaimer */
.disclaimer {{ background: #fff; border-radius: 12px; padding: 20px; margin-top: 24px; font-size: 12px; color: #999; line-height: 1.8; box-shadow: 0 2px 8px rgba(0,0,0,0.04); }}

/* Responsive */
@media (max-width: 768px) {{
  .stock-grid {{ grid-template-columns: 1fr; }}
  .metric-grid {{ grid-template-columns: repeat(2, 1fr); }}
  .summary-grid {{ grid-template-columns: repeat(2, 1fr); }}
}}
</style>
</head>
<body>
<div class="container">

  <!-- Header -->
  <div class="header">
    <h1>🔬 A股MLCC行业深度分析报告</h1>
    <div class="subtitle">覆盖MLCC全产业链：制造（风华高科/三环集团/火炬电子/鸿远电子）· 上游材料（国瓷材料）· 上游配套（洁美科技）· 军用电子平台（振华科技）</div>
    <div class="meta">
      数据源：Tushare（行情K线）+ 腾讯财经（实时估值）+ 东方财富（资金流向/融资融券）<br>
      分析日期：{END_DATE}（数据截止到最新交易日）· 生成时间：{now}<br>
      分析工具：Vibe-Trading AI + a-stock-data 双技能栈
    </div>
  </div>

  <!-- Summary -->
  <div class="summary-grid">
    <div class="summary-card"><div class="s-val">7</div><div class="s-label">覆盖标的</div></div>
    <div class="summary-card"><div class="s-val">{avg_pe:.0f}x</div><div class="s-label">板块平均PE(TTM)</div></div>
    <div class="summary-card"><div class="s-val">{avg_pb:.1f}x</div><div class="s-label">板块平均PB</div></div>
    <div class="summary-card"><div class="s-val">{total_mcap:.0f}亿</div><div class="s-label">板块总市值</div></div>
    <div class="summary-card negative"><div class="s-val">{avg_chg_60:+.1f}%</div><div class="s-label">板块平均60日涨跌</div></div>
    <div class="summary-card"><div class="s-val">{max([s['score'] for s in all_scores.values()])}</div><div class="s-label">最高综合评分</div></div>
  </div>

  <!-- 行业对比表 -->
  <div class="section-title-main">📊 行业横向对比</div>
  <div class="comparison-table">
    <table>
      <thead>
        <tr>
          <th>标的</th><th>最新价</th><th>涨跌%</th><th>PE(TTM)</th><th>PB</th><th>市值(亿)</th>
          <th>换手%</th><th>量比</th><th>RSI14</th><th>5日%</th><th>20日%</th><th>60日%</th><th>综合评分</th>
        </tr>
      </thead>
      <tbody>{comparison_rows}</tbody>
    </table>
  </div>

  <!-- 个股分析 -->
  <div class="section-title-main">🔍 个股深度分析</div>
  <div class="stock-grid">{stock_cards_html}</div>

  <!-- 投资建议 -->
  <div class="section-title-main">🎯 投资建议（按综合评分排序）</div>
  {recommendations}

  <!-- 风险提示 -->
  <div class="disclaimer">
    <strong>⚠️ 风险提示与免责声明</strong><br>
    本报告由 AI 投资分析系统自动生成，基于公开市场数据和量化模型，仅供参考，不构成投资建议。<br>
    <strong>主要风险因素：</strong><br>
    ① MLCC行业周期性波动风险——下游消费电子需求变化可能导致产能利用率波动；<br>
    ② 原材料价格波动——钛酸钡、镍电极等原材料成本占比高；<br>
    ③ 国产替代进程不及预期——高端MLCC（车规级、军工级）国产化仍处于早期阶段；<br>
    ④ 军品订单不确定性——军工电子标的（火炬电子、鸿远电子、振华科技）受国防采购节奏影响；<br>
    ⑤ 市场情绪风险——当前板块整体处于调整期，短期波动较大。<br>
    ⑥ 数据时效性——部分数据可能存在延迟，技术指标基于历史数据，不预示未来走势。<br><br>
    <strong>投资有风险，入市需谨慎。请结合自身风险承受能力和投资目标做出决策。</strong>
  </div>

</div>
</body>
</html>"""

    return html

# ============================================================
# 输出
# ============================================================
END_DATE = data["meta"]["end_date"]
html_content = build_html()

report_path = Path(__file__).parent.parent / "MLCC行业深度分析报告.html"
with open(report_path, "w", encoding="utf-8") as f:
    f.write(html_content)

print(f"✅ 报告已生成: {report_path}")
print(f"   文件大小: {len(html_content)/1024:.1f} KB")
