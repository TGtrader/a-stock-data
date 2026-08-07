"""
仪表盘HTML报告生成器
===================
7大指数综合分析仪表盘
"""
import os
from datetime import datetime


def safe(v, fmt='.1f'):
    try: return f'{float(v):{fmt}}'
    except: return str(v) if v is not None else 'N/A'


def color_score(s):
    """评分着色"""
    try:
        s = float(s)
        if s >= 65: return '#00e676'
        elif s >= 50: return '#ffd740'
        else: return '#ff5252'
    except: return '#90a4ae'


def agent_color(v):
    if '多' in str(v) or '反弹' in str(v) or '健康' in str(v) or '低风险' in str(v):
        return '#00e676'
    elif '空' in str(v) or '回调' in str(v) or '恶化' in str(v) or '高风险' in str(v):
        return '#ff5252'
    return '#ffd740'


def generate_dashboard(all_data, output_path='大盘及板块分析/大盘分析报告.html', market_summary=None):
    """生成HTML仪表盘"""
    date_str = datetime.now().strftime('%Y-%m-%d %H:%M')
    N = len(all_data)
    mf = (market_summary or {}).get('moneyflow', {}) or {}
    nb = (market_summary or {}).get('northbound', [])
    nb_5d = (market_summary or {}).get('nb_5d', 0)
    margin = (market_summary or {}).get('margin', {}) or {}

    # Market summary HTML
    mkt_html = ''
    net_amt = float(mf.get('net_amount', 0)) / 1e8 if mf else 0
    mf_color = '#00e676' if net_amt > 0 else '#ff5252'
    nb_color = '#00e676' if nb_5d > 0 else '#ff5252'
    rz_color = '#00e676' if margin.get('net_rz', 0) > 0 else '#ff5252'

    # 主力资金流20日表格
    mf_trend = (market_summary or {}).get('mf_trend', [])
    mf_rows = ''
    if mf_trend:
        for r in mf_trend[-20:]:
            nc = '#00e676' if r['net_amount'] > 0 else '#ff5252'
            mf_rows += f'<tr><td>{r["date"]}</td><td style="color:{nc}">{r["net_amount"]:+.1f}</td><td>{r["net_rate"]:+.2f}%</td><td>{r["buy_big"]:.1f}</td><td>{r["sell_big"]:.1f}</td></tr>'
        mf_table = f'''<table class="trend-table"><tr><th>日期</th><th>主力净额(亿)</th><th>净额占比</th><th>大单买(亿)</th><th>大单卖(亿)</th></tr>{mf_rows}</table>'''
    else:
        mf_table = '<p style="color:#8b949e">主力资金流数据暂不可用</p>'

    # 两融余额20日表格
    margin_trend = (market_summary or {}).get('margin_trend', [])
    mg_rows = ''
    if margin_trend:
        for r in margin_trend[-20:]:
            nc = '#00e676' if r['net_rz'] > 0 else '#ff5252'
            mg_rows += f'<tr><td>{r["date"]}</td><td>{r["total"]:.0f}</td><td>{r["rz_balance"]:.0f}</td><td>{r["rq_balance"]:.1f}</td><td style="color:{nc}">{r["net_rz"]:+.1f}</td></tr>'
        mg_table = f'''<table class="trend-table"><tr><th>日期</th><th>两融余额(亿)</th><th>融资余额(亿)</th><th>融券余额(亿)</th><th>净融资买入(亿)</th></tr>{mg_rows}</table>'''
    else:
        mg_table = '<p style="color:#8b949e">两融数据暂不可用</p>'

    mkt_html = f'''
    <div class="market-summary">
        <div class="ms-card">
            <div class="ms-label">市场主力资金(当日)</div>
            <div class="ms-val" style="color:{mf_color}">{net_amt:+.1f}亿</div>
        </div>
        <div class="ms-card">
            <div class="ms-label">北向资金(近5日)</div>
            <div class="ms-val" style="color:{nb_color}">{nb_5d:+.1f}亿</div>
        </div>
        <div class="ms-card">
            <div class="ms-label">两融余额</div>
            <div class="ms-val">{margin.get('total_rzrq','?')}亿</div>
            <div class="ms-sub">融资{margin.get('total_rz','?')}亿 | 融券{margin.get('total_rq','?')}亿</div>
        </div>
        <div class="ms-card">
            <div class="ms-label">融资净买入(当日)</div>
            <div class="ms-val" style="color:{rz_color}">{margin.get('net_rz','?'):+.1f}亿</div>
        </div>
    </div>'''

    cards_html = ''
    for ts_code, d in all_data.items():
        info = d['info']
        tech = d.get('technical', {})
        agents = d.get('agents', {})

        pos = tech.get('position', {})
        ma = tech.get('ma', {})
        macd = tech.get('macd', {})
        trend = tech.get('trend', {})
        boll = tech.get('bollinger', {})
        intra = tech.get('intraday', {})
        vol = tech.get('volume', {})

        close = pos.get('close', 0)
        pos_v = pos.get('verdict', '')
        dd = pos.get('drawdown_from_high', 0)
        chg_5 = trend.get('5日', {}).get('change_pct', 0)
        chg_10 = trend.get('10日', {}).get('change_pct', 0)

        # Agent opinions
        agent_list = agents.get('agents', [])
        agent_rows = ''
        for a in agent_list:
            analysis_text = a['分析'][:150] if a['分析'] else '当前无显著信号'
            agent_rows += f'''
            <tr>
                <td>{a['角色']}</td>
                <td style="color:{color_score(a['评分'])};font-weight:bold">{a['评分']}</td>
                <td style="color:{agent_color(a['观点'])}">{a['观点']}</td>
                <td style="font-size:11px;color:#c9d1d9">{analysis_text}</td>
            </tr>'''

        chg_color = '#00e676' if chg_5 >= 0 else '#ff5252'

        cards_html += f'''
        <div class="index-card">
            <div class="card-header">
                <span class="card-name">{info['name']}</span>
                <span class="card-code">{ts_code}</span>
            </div>
            <div class="card-intraday">
                <span style="color:#58a6ff">当日:</span> {intra.get('summary','')}
                <span style="margin-left:8px;font-size:11px;color:#8b949e">开{intra.get('open','?')} 高{intra.get('high','?')} 低{intra.get('low','?')} 收{intra.get('close','?')}</span>
            </div>
            <div class="card-price-row">
                <span class="card-price">{close:.2f}</span>
                <span class="card-chg" style="color:{chg_color}">5日 {chg_5:+.2f}%</span>
                <span style="font-size:12px;color:#8b949e">10日 {chg_10:+.2f}%</span>
            </div>
            <div class="card-metrics">
                <div class="cm-item"><span class="cm-label">位置</span><span class="cm-val" style="color:{'#ff5252' if pos_v=='高位' else ('#00e676' if pos_v=='低位' else '#ffd740')}">{pos_v}({pos.get('position_pct',50):.0f}%)</span></div>
                <div class="cm-item"><span class="cm-label">回撤</span><span class="cm-val">{dd:.1f}%</span></div>
                <div class="cm-item"><span class="cm-label">MA排列</span><span class="cm-val">{tech.get('ma_alignment','')}</span></div>
                <div class="cm-item"><span class="cm-label">MACD</span><span class="cm-val" style="color:{'#00e676' if '金叉' in macd.get('signal','') or '多头' in macd.get('signal','') else ('#ff5252' if '死叉' in macd.get('signal','') else '#ffd740')}">{macd.get('signal','')}</span></div>
                <div class="cm-item"><span class="cm-label">RSI</span><span class="cm-val">{tech.get('rsi','')}</span></div>
                <div class="cm-item"><span class="cm-label">布林</span><span class="cm-val">{boll.get('status','')}</span></div>
            </div>
            <div class="card-volume">
                <span style="font-size:11px;color:#8b949e">成交量:</span>
                <span style="font-size:12px">当日{vol.get('latest_vol','?')}手</span>
                <span style="margin-left:8px;font-size:12px;color:{'#00e676' if '健康' in str(vol.get('vol_price_signal','')) or '正常' in str(vol.get('vol_price_signal','')) else '#ff5252'}">vs5日均量 {vol.get('vol_ratio_vs_5d','?')}%</span>
                <span style="margin-left:8px;font-size:12px">5vs20均量 {vol.get('vol_ratio_5vs20','?')}%</span>
                <span style="margin-left:8px;font-size:12px;color:{'#00e676' if '放量' in str(vol.get('vol_trend','')) else '#ffd740'}">{vol.get('vol_trend','')}</span>
                <span style="margin-left:8px;font-size:12px;font-weight:bold;color:{'#00e676' if '健康' in str(vol.get('vol_price_signal','')) else ('#ff5252' if '背离' in str(vol.get('vol_price_signal','')) or '抛售' in str(vol.get('vol_price_signal','')) else '#ffd740')}">{vol.get('vol_price_signal','')}</span>
            </div>
            <div class="card-agents">
                <table class="agent-table">{agent_rows}</table>
            </div>
            <div class="card-synthesis">
                <span>综合: <strong style="color:{color_score(agents.get('综合评分',50))}">{agents.get('综合评分',50)}分 {agents.get('综合观点','')}</strong></span>
                <span style="margin-left:12px">支撑 {safe(tech.get('sr',{}).get('support'),'.0f')} | 阻力 {safe(tech.get('sr',{}).get('resistance'),'.0f')}</span>
                <span style="margin-left:12px">趋势: 5日{trend.get('5日',{}).get('direction','')}/{trend.get('5日',{}).get('strength','')} 10日{trend.get('10日',{}).get('direction','')}/{trend.get('10日',{}).get('strength','')} 30日{trend.get('30日',{}).get('direction','')}/{trend.get('30日',{}).get('strength','')}</span>
            </div>
        </div>'''

    # Heatmap row
    heatmap = ''
    for ts_code, d in all_data.items():
        t5 = d.get('technical', {}).get('trend', {}).get('5日', {}).get('change_pct', 0)
        color = f'hsl({120 if t5>=0 else 0}, {min(abs(t5)*8, 80)}%, 45%)'
        heatmap += f'<div class="heat-cell" style="background:{color}" title="{d["info"]["name"]}: 5日{t5:+.2f}%">{d["info"]["short"]}<br>{t5:+.2f}%</div>'

    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>A股大盘综合分析报告</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0d1117;color:#c9d1d9;padding:20px}}
.container{{max-width:1400px;margin:0 auto}}
.header{{text-align:center;padding:20px 0 30px;border-bottom:1px solid #21262d;margin-bottom:20px}}
.header h1{{font-size:24px;margin-bottom:6px}}
.header .date{{font-size:13px;color:#8b949e}}
.heatmap{{display:flex;gap:8px;margin-bottom:24px;flex-wrap:wrap;justify-content:center}}
.heat-cell{{padding:10px 16px;border-radius:8px;text-align:center;font-size:13px;font-weight:bold;color:#fff;min-width:90px}}
.index-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(420px,1fr));gap:18px}}
.index-card{{background:#161b22;border:1px solid #21262d;border-radius:10px;padding:16px}}
.card-header{{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:8px}}
.card-name{{font-size:17px;font-weight:bold}}
.card-code{{font-size:11px;color:#8b949e}}
.card-price-row{{display:flex;align-items:baseline;gap:12px;margin-bottom:12px}}
.card-price{{font-size:26px;font-weight:bold}}
.card-chg{{font-size:14px;font-weight:600}}
.card-metrics{{display:grid;grid-template-columns:repeat(3,1fr);gap:6px;margin-bottom:12px}}
.cm-item{{background:#0d1117;padding:6px 8px;border-radius:6px;display:flex;justify-content:space-between;font-size:12px}}
.cm-label{{color:#8b949e}}
.cm-val{{font-weight:600}}
.card-agents{{margin-bottom:8px}}
.agent-table{{width:100%;font-size:12px;border-collapse:collapse}}
.agent-table td{{padding:4px 6px;border-bottom:1px solid #1a1a2e}}
.agent-table td:first-child{{color:#58a6ff;width:80px}}
.card-synthesis{{font-size:12px;color:#8b949e;padding-top:8px;border-top:1px solid #21262d;line-height:1.6}}
.card-intraday{{font-size:13px;color:#c9d1d9;margin-bottom:10px;padding:6px 10px;background:#0d1117;border-radius:6px;border-left:3px solid #58a6ff}}
.card-volume{{font-size:12px;color:#c9d1d9;margin-bottom:10px;padding:8px 10px;background:#0d1117;border-radius:6px;line-height:1.8}}
.section-title{{font-size:18px;font-weight:bold;margin:24px 0 12px;padding-bottom:8px;border-bottom:1px solid #21262d}}
.market-summary{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:20px}}
.ms-card{{background:#161b22;border:1px solid #21262d;border-radius:10px;padding:14px;text-align:center}}
.ms-val{{font-size:22px;font-weight:bold;margin:6px 0}}
.ms-label{{font-size:12px;color:#8b949e}}
.ms-sub{{font-size:11px;color:#484f58;margin-top:4px}}
.mf-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:16px}}
.mf-card{{background:#161b22;border:1px solid #21262d;border-radius:10px;padding:14px;text-align:center}}
.mf-val{{font-size:22px;font-weight:bold;margin:6px 0}}
.mf-label{{font-size:12px;color:#8b949e}}
.nb-table{{width:100%;font-size:12px;border-collapse:collapse;margin-top:10px}}
.trend-table{{width:100%;font-size:11px;border-collapse:collapse;max-height:400px;overflow-y:auto;display:block}}
.trend-table th{{text-align:right;padding:3px 6px;color:#58a6ff;border-bottom:1px solid #21262d;position:sticky;top:0;background:#161b22}}
.trend-table td{{text-align:right;padding:3px 6px;border-bottom:1px solid #1a1a2e;white-space:nowrap}}
.trend-table td:first-child,.trend-table th:first-child{{text-align:left}}
.nb-table th{{text-align:left;padding:6px 10px;color:#58a6ff;border-bottom:1px solid #21262d}}
.nb-table td{{padding:5px 10px;border-bottom:1px solid #1a1a2e}}
.footer{{text-align:center;color:#484f58;font-size:11px;margin-top:40px;padding-top:20px;border-top:1px solid #21262d}}
</style>
</head>
<body>
<div class="container">

<div class="header">
    <h1>A股大盘综合分析报告</h1>
    <div class="date">生成时间: {date_str} | 7大指数 · 4角色Agent · 日线300日</div>
</div>

<div class="section-title">市场宏观数据</div>
{mkt_html}

<div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:20px">
    <div>
        <div class="section-title" style="margin-top:0">主力资金 近20日进出 (亿)</div>
        {mf_table}
    </div>
    <div>
        <div class="section-title" style="margin-top:0">两融余额 近20日变化 (亿)</div>
        {mg_table}
    </div>
</div>

<div class="section-title">指数热度图 (近5日涨跌幅)</div>
<div class="heatmap">{heatmap}</div>

<div class="section-title">指数逐一深度分析</div>
<div class="index-grid">{cards_html}</div>

<div class="footer">
    数据来源: Tushare(日线K线) + Eastmoney(北向资金) | TG-trading-sys 大盘及板块分析模块
</div>
</div>
</body>
</html>'''
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f'仪表盘已生成: {output_path} ({os.path.getsize(output_path)/1024:.0f} KB)')
    return html
