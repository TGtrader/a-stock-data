#!/usr/bin/env python3
"""A股七大指数缠论分析 v2 — 含K线图"""
import sys, os
sys.path.insert(0, '.')
import pandas as pd, numpy as np
import tushare as ts
from czsc import CZSC, Freq, RawBar, Direction
from TG_trading_sys.core.config import Config
import plotly.graph_objects as go
from plotly.subplots import make_subplots

ts.set_token(Config.get_tushare_token())
pro = ts.pro_api()

INDICES = {
    '上证指数': '000001.SH', '深证成指': '399001.SZ', '创业板指': '399006.SZ',
    '科创50': '000688.SH', '沪深300': '000300.SH', '上证50': '000016.SH', '中证500': '000905.SH',
}

def fetch_and_analyze(ts_code):
    df = pro.index_daily(ts_code=ts_code, start_date='20260101', end_date='20260807',
                         fields='trade_date,open,high,low,close,vol,amount')
    if df.empty: return None
    df = df.sort_values('trade_date').reset_index(drop=True)
    df['dt'] = pd.to_datetime(df['trade_date'])
    bars = [RawBar(symbol=ts_code, dt=r['dt'], open=float(r['open']),
                   high=float(r['high']), low=float(r['low']),
                   close=float(r['close']), vol=float(r['vol']),
                   amount=float(r['amount']), freq=Freq.D) for _, r in df.iterrows()]
    cz = CZSC(bars, max_bi_num=50)
    return df, cz

def compute_zs(bis):
    zs = []
    for i in range(len(bis)-2):
        b1,b2,b3 = bis[i],bis[i+1],bis[i+2]
        zd = max(b1.low,b2.low,b3.low)
        zg = min(b1.high,b2.high,b3.high)
        if zd < zg:
            zs.append({'start':b1.fx_a.dt,'end':b3.edt,'zd':round(zd,2),'zg':round(zg,2),'zz':round((zd+zg)/2,2)})
    return zs

def make_chart(name, df, cz, bis, zs_list, idx):
    """生成单个指数K线图"""
    plot_df = df.tail(80).copy()

    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                        row_heights=[0.7, 0.3], vertical_spacing=0.05)

    # K线
    fig.add_trace(go.Candlestick(
        x=plot_df['dt'], open=plot_df['open'], high=plot_df['high'],
        low=plot_df['low'], close=plot_df['close'],
        increasing_line_color='#ef4444', decreasing_line_color='#22c55e',
        increasing_fillcolor='#ef4444', decreasing_fillcolor='#22c55e',
        name='日K', showlegend=False), row=1, col=1)

    # 中枢
    for z in zs_list:
        if z['end'] >= plot_df['dt'].iloc[0] and z['start'] <= plot_df['dt'].iloc[-1]:
            s, e = max(z['start'], plot_df['dt'].iloc[0]), min(z['end'], plot_df['dt'].iloc[-1])
            fig.add_trace(go.Scatter(
                x=[s,e,e,s,s], y=[z['zg'],z['zg'],z['zd'],z['zd'],z['zg']],
                fill='toself', fillcolor='rgba(56,189,248,0.10)',
                line=dict(color='rgba(56,189,248,0.3)', width=1, dash='dot'),
                showlegend=False, hoverinfo='text',
                text=f'中枢 [{z["zd"]}~{z["zg"]}]'), row=1, col=1)

    # 最新中枢高亮
    if zs_list:
        z = zs_list[-1]
        fig.add_hline(y=z['zg'], line_dash='dash', line_color='#fbbf24', line_width=1, row=1, col=1)
        fig.add_hline(y=z['zd'], line_dash='dash', line_color='#fbbf24', line_width=1, row=1, col=1)

    # 笔连线
    for bi in bis:
        if bi.edt >= plot_df['dt'].iloc[0]:
            color = '#ef4444' if bi.direction == Direction.Up else '#22c55e'
            sdt = max(bi.fx_a.dt, plot_df['dt'].iloc[0])
            edt = min(bi.edt, plot_df['dt'].iloc[-1])
            y0 = bi.fx_a.low if bi.direction == Direction.Up else bi.fx_a.high
            y1 = bi.high if bi.direction == Direction.Up else bi.low
            fig.add_trace(go.Scatter(
                x=[sdt, edt], y=[y0, y1], mode='lines',
                line=dict(color=color, width=2.2),
                showlegend=False, hoverinfo='text',
                text=f'笔: {bi.fx_a.dt.strftime("%m-%d")}→{bi.edt.strftime("%m-%d")} {bi.change:+.1%}'
            ), row=1, col=1)

    # 分型
    buy_x, buy_y, sell_x, sell_y = [], [], [], []
    for fx in cz.fx_list:
        if fx.dt >= plot_df['dt'].iloc[0]:
            if repr(fx.mark) == 'Mark.D':
                buy_x.append(fx.dt); buy_y.append(fx.low)
            elif repr(fx.mark) == 'Mark.G':
                sell_x.append(fx.dt); sell_y.append(fx.high)

    fig.add_trace(go.Scatter(x=buy_x, y=buy_y, mode='markers',
        marker=dict(symbol='triangle-up', size=8, color='#22c55e', line=dict(width=1,color='#fff')),
        name='底分型', showlegend=False), row=1, col=1)
    fig.add_trace(go.Scatter(x=sell_x, y=sell_y, mode='markers',
        marker=dict(symbol='triangle-down', size=8, color='#ef4444', line=dict(width=1,color='#fff')),
        name='顶分型', showlegend=False), row=1, col=1)

    # 成交量
    colors_v = ['#ef4444' if plot_df['close'].iloc[i] >= plot_df['open'].iloc[i] else '#22c55e' for i in range(len(plot_df))]
    fig.add_trace(go.Bar(x=plot_df['dt'], y=plot_df['vol'], marker_color=colors_v,
                         marker_opacity=0.4, showlegend=False), row=2, col=1)

    fig.update_layout(
        template='plotly_dark', height=400, margin=dict(l=10, r=10, t=30, b=10),
        font=dict(family='Microsoft YaHei, SimHei, sans-serif'),
        title=dict(text=name, font=dict(size=14, color='#38bdf8')),
    )
    fig.update_xaxes(rangeslider_visible=False, row=1, col=1)
    fig.update_yaxes(title='元/点', row=1, col=1)
    fig.update_yaxes(title='量', row=2, col=1)

    path = f'data/chan_idx_{idx}.html'
    fig.write_html(path, include_plotlyjs=False, config={'displayModeBar': False})
    return path

def detect_div(bis):
    divs = []
    up_bis = [b for b in bis if b.direction == Direction.Up]
    dn_bis = [b for b in bis if b.direction == Direction.Down]
    for i in range(1,len(up_bis)):
        p,c = up_bis[i-1],up_bis[i]
        if c.high > p.high and c.power < p.power*0.85:
            divs.append({'type':'顶背离','date':str(c.edt)[:10],'detail':f'{c.high:.1f}>{p.high:.1f} power{c.power:.0f}<{p.power:.0f}'})
    for i in range(1,len(dn_bis)):
        p,c = dn_bis[i-1],dn_bis[i]
        if c.low < p.low and c.power < p.power*0.85:
            divs.append({'type':'底背离','date':str(c.edt)[:10],'detail':f'{c.low:.1f}<{p.low:.1f} power{c.power:.0f}<{p.power:.0f}'})
    return divs

# ── 批量分析 + 出图 ────────────────────────────────────────
results = {}
chart_files = {}
for idx_i, (name, code) in enumerate(INDICES.items()):
    print(f"[{idx_i+1}/7] {name} ({code})...")
    ret = fetch_and_analyze(code)
    if ret is None: continue
    df, cz = ret
    all_bis = list(cz.finished_bis)
    if cz.bi_list: all_bis = all_bis + list(cz.bi_list)
    zs_list = compute_zs(all_bis)
    div_list = detect_div(all_bis)

    last_close = float(df['close'].iloc[-1])
    lb = all_bis[-1] if all_bis else None
    bi_dir = '上涨' if lb and lb.direction == Direction.Up else ('下跌' if lb else 'N/A')
    bi_chg = f'{lb.change:+.1%}' if lb else 'N/A'
    bi_pw = f'{lb.power:.0f}' if lb else 'N/A'

    ma5 = float(df['close'].tail(5).mean())
    ma20 = float(df['close'].tail(20).mean())
    ma_trend = '多头' if ma5 > ma20 else '空头'

    if zs_list:
        z = zs_list[-1]
        if last_close > z['zg']: position, bias = '中枢上方 ▲', '偏多'
        elif last_close < z['zd']: position, bias = '中枢下方 ▼', '偏空'
        else: position, bias = '中枢内部 ◇', '震荡'
    else:
        position, bias = '无中枢', '不明'

    results[name] = {
        'df': df, 'cz': cz, 'bis': all_bis, 'zs': zs_list, 'divs': div_list,
        'status': {
            'name': name, 'date': str(df['trade_date'].iloc[-1])[:10],
            'close': last_close, 'ma5': round(ma5,1), 'ma20': round(ma20,1),
            'ma_trend': ma_trend, 'bi_count': len(all_bis), 'zs_count': len(zs_list),
            'fx_count': len(cz.fx_list), 'bi_dir': bi_dir, 'bi_change': bi_chg,
            'bi_power': bi_pw, 'position': position, 'bias': bias,
            'zs_zg': zs_list[-1]['zg'] if zs_list else None,
            'zs_zd': zs_list[-1]['zd'] if zs_list else None,
        }
    }

    # 生成图表
    try:
        chart_path = make_chart(name, df, cz, all_bis, zs_list, idx_i)
        chart_files[name] = chart_path
        print(f"  chart OK")
    except Exception as e:
        print(f"  chart FAIL: {e}")

# ── 组合所有图表到一个独立HTML(不依赖Plotly CDN) ──────────
print("\n合并图表...")
combined_charts = ''
plotly_js_included = False
for idx_i, name in enumerate(results.keys()):
    if name in chart_files:
        with open(chart_files[name], 'r', encoding='utf-8') as f:
            content = f.read()
        # 只在第一个文件包含plotly.js
        if not plotly_js_included:
            combined_charts += content
            plotly_js_included = True
        else:
            # 移除plotly.js引用，后续图表复用第一个的plotly
            content_no_plotly = content.replace(
                '<script src="https://cdn.plot.ly/plotly-3.1.0.min.js" charset="utf-8"></script>', '')
            combined_charts += content_no_plotly

# 清理临时文件
for p in chart_files.values():
    os.remove(p)

# ── 生成最终报告 ──────────────────────────────────────────
def trend_badge(bias):
    if '多' in bias: return '<span class="badge badge-up">偏多</span>'
    if '空' in bias: return '<span class="badge badge-down">偏空</span>'
    return '<span class="badge badge-neutral">震荡</span>'

html = """<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8">
<title>A股七大指数 缠论日线分析</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:"Microsoft YaHei","SimHei",sans-serif;background:#0f172a;color:#e2e8f0;padding:20px;line-height:1.6}
.container{max-width:1300px;margin:0 auto}
h1{text-align:center;font-size:22pt;color:#38bdf8;margin-bottom:4px}
.sub{text-align:center;color:#94a3b8;font-size:9pt;margin-bottom:24px}
h2{font-size:15pt;color:#38bdf8;margin:28px 0 14px;padding-left:10px;border-left:3px solid #0ea5e9}
h3{font-size:13pt;color:#e2e8f0;margin:16px 0 8px}
.card{background:#1e293b;border-radius:10px;padding:18px 22px;margin-bottom:18px;border:1px solid #334155}
table{width:100%;border-collapse:collapse;font-size:9pt;margin:8px 0}
th{background:#0f172a;color:#38bdf8;padding:7px 10px;text-align:center;font-weight:600;border-bottom:2px solid #1e3b5a}
td{padding:6px 10px;text-align:center;border-bottom:1px solid #1e293b}
tr:hover td{background:#1e3b5a}
.up{color:#ef4444;font-weight:700}.down{color:#22c55e;font-weight:700}
.badge{display:inline-block;padding:3px 10px;border-radius:12px;font-size:9pt;font-weight:700}
.badge-up{background:#7f1d1d;color:#fca5a5}
.badge-down{background:#064e3b;color:#86efac}
.badge-neutral{background:#1e3b5a;color:#bae6fd}
.signal{font-size:8pt;padding:2px 6px;border-radius:4px;margin:1px;display:inline-block}
.signal-div-top{background:#4a044e;color:#e879f9}
.signal-div-bot{background:#064e3b;color:#86efac}
.status-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(155px,1fr));gap:10px}
.idx-card{background:#0f172a;border-radius:10px;padding:16px;text-align:center;border:1px solid #334155;transition:border-color .2s}
.idx-card:hover{border-color:#38bdf8}
.idx-name{font-size:11pt;font-weight:700;color:#e2e8f0}
.idx-price{font-size:20pt;font-weight:800;margin:6px 0}
.idx-detail{font-size:8pt;color:#94a3b8;margin:3px 0}
.idx-row{display:flex;justify-content:center;gap:12px;margin-top:8px}
.idx-stat{text-align:center}
.idx-stat-val{font-size:12pt;font-weight:700;color:#38bdf8}
.idx-stat-lbl{font-size:7pt;color:#64748b}
.advice-box{background:linear-gradient(135deg,#1e293b,#0f172a);border:1px solid #fbbf24;border-radius:10px;padding:16px 20px;margin:14px 0}
.advice-title{font-size:12pt;font-weight:700;color:#fbbf24;margin-bottom:8px}
.summary-table td:first-child{text-align:left;font-weight:600}
.price-up{color:#ef4444}.price-down{color:#22c55e}
.chart-container{background:#0f172a;border-radius:8px;padding:8px;margin:12px 0}
.footer{text-align:center;color:#475569;font-size:8pt;margin-top:36px;padding-top:14px;border-top:1px solid #1e293b}
</style></head><body><div class="container">
<h1>A股七大指数 缠论日线分析</h1>
<p class="sub">数据区间: 2026-01-01 ~ 2026-08-07 | 缠论引擎: czsc v0.10.12 | 生成: 2026-08-07</p>
"""

# 总览卡片
html += '<h2>一、七大指数总览</h2>\n<div class="status-grid">\n'
for name, r in results.items():
    s = r['status']
    pc = 'price-up' if s['close'] > s['ma5'] else 'price-down'
    html += f"""<div class="idx-card">
<div class="idx-name">{name}</div>
<div class="idx-price {pc}">{s['close']:.0f}</div>
<div class="idx-detail">MA5 {s['ma5']:.0f} | MA20 {s['ma20']:.0f} | {s['ma_trend']}</div>
<div class="idx-row">
<div class="idx-stat"><div class="idx-stat-val">{s['bi_count']}</div><div class="idx-stat-lbl">笔</div></div>
<div class="idx-stat"><div class="idx-stat-val">{s['zs_count']}</div><div class="idx-stat-lbl">中枢</div></div>
<div class="idx-stat"><div class="idx-stat-val">{s['fx_count']}</div><div class="idx-stat-lbl">分型</div></div>
<div class="idx-stat"><div class="idx-stat-val">{len(r['divs'])}</div><div class="idx-stat-lbl">背离</div></div>
</div>
<div style="margin-top:10px">{trend_badge(s['bias'])} {s['bi_dir']}笔 {s['bi_change']}</div>
</div>\n"""
html += '</div>\n'

# 汇总对比
html += '<h2>二、汇总对比</h2>\n<div class="card"><table class="summary-table">\n'
html += '<tr><th>指数</th><th>收盘</th><th>MA5</th><th>均线</th><th>笔方向</th><th>笔幅度</th><th>中枢位置</th><th>判断</th><th>背离</th></tr>\n'
for name, r in results.items():
    s = r['status']
    html += f"<tr><td>{name}</td><td>{s['close']:.0f}</td><td>{s['ma5']:.0f}</td>"
    html += f"<td>{s['ma_trend']}</td><td>{s['bi_dir']}</td><td>{s['bi_change']}</td>"
    html += f"<td>{s['position']}</td><td>{trend_badge(s['bias'])}</td>"
    div_tags = ''.join([f"<span class='signal signal-div-{"top" if d["type"]=="顶背离" else "bot"}'>{d['type'][:1]}{d['date'][5:]}</span> " for d in r['divs'][-3:]])
    html += f"<td>{div_tags if div_tags else '-'}</td></tr>\n"
html += '</table></div>\n'

# K线图
html += '<h2>三、日K线图 — 缠论笔+中枢叠加</h2>\n'
html += '<p style="color:#94a3b8;font-size:9pt;margin-bottom:12px">🔴红线=上涨笔 | 🟢绿线=下跌笔 | 绿三角=底分型(买) | 红三角=顶分型(卖) | 蓝虚线框=中枢 | 黄虚线=当前中枢</p>\n'
html += f'<div style="background:#0f172a;border-radius:10px;padding:10px">\n{combined_charts}\n</div>\n'

# 各指数笔详情
html += '<h2>四、各指数笔详情</h2>\n'
for name, r in results.items():
    s = r['status']
    z = r['zs'][-1] if r['zs'] else None
    html += f'<h3>{name} {trend_badge(s["bias"])}</h3>\n<div class="card">\n'
    html += f'<p>{s["bi_dir"]}笔 · 幅度 {s["bi_change"]} · 力量 {s["bi_power"]} · {s["ma_trend"]}排列 · 收盘 {s["close"]:.0f}</p>\n'

    if z:
        html += f'<p>当前中枢 [{z["zd"]}~{z["zg"]}] ({z["start"]}~{z["end"]})</p>\n'
        if s['close'] > z['zg']:
            html += '<p style="color:#fca5a5;font-size:9pt">→ 中枢上方，回踩不破上沿为三买</p>\n'
        elif s['close'] < z['zd']:
            html += '<p style="color:#86efac;font-size:9pt">→ 中枢下方，反弹不过下沿为三卖</p>\n'
        else:
            html += '<p style="color:#bae6fd;font-size:9pt">→ 中枢内部震荡</p>\n'

    if r['divs']:
        html += '<p style="margin-top:4px">背离: '
        for d in r['divs'][-3:]:
            cls = 'signal-div-top' if '顶' in d['type'] else 'signal-div-bot'
            html += f'<span class="signal {cls}">{d["type"]} {d["date"]} {d["detail"]}</span> '
        html += '</p>\n'

    html += '<details style="margin-top:8px"><summary style="cursor:pointer;color:#38bdf8">全部笔列表</summary>'
    html += '<table style="margin-top:6px"><tr><th>#</th><th>方向</th><th>起始</th><th>结束</th><th>幅度</th><th>力量</th><th>SNR</th></tr>'
    for i,bi in enumerate(r['bis']):
        d = '↑涨' if bi.direction == Direction.Up else '↓跌'
        cls = 'up' if bi.direction == Direction.Up else 'down'
        html += f"<tr><td>{i+1}</td><td class='{cls}'>{d}</td><td>{str(bi.fx_a.dt)[:10]}</td>"
        html += f"<td>{str(bi.edt)[:10]}</td><td class='{cls}'>{bi.change:+.1%}</td>"
        html += f"<td>{bi.power:.0f}</td><td>{bi.SNR:.1f}</td></tr>"
    html += '</table></details></div>\n'

# 综合研判
bull_count = sum(1 for r in results.values() if '多' in r['status']['bias'])
bear_count = sum(1 for r in results.values() if '空' in r['status']['bias'])
neutral_count = len(results) - bull_count - bear_count

html += '<h2>五、综合研判</h2>\n<div class="advice-box">\n'
html += '<div class="advice-title">市场整体状态</div>\n'
html += f'<p>偏多: {bull_count} | 偏空: {bear_count} | 震荡: {neutral_count}</p>\n'

sorted_idx = sorted(results.items(), key=lambda x: (
    1 if '多' in x[1]['status']['bias'] else (0 if '震' in x[1]['status']['bias'] else -1)), reverse=True)
html += '<p style="margin-top:8px"><strong>最强</strong>: '
html += '、'.join([f'{n}({r["status"]["close"]:.0f})' for n,r in sorted_idx[:2]])
html += ' &emsp; <strong>最弱</strong>: '
html += '、'.join([f'{n}({r["status"]["close"]:.0f})' for n,r in sorted_idx[-2:]])
html += '</p>\n'

all_divs = [(name, d) for name, r in results.items() for d in r['divs']]
if all_divs:
    html += '<p style="margin-top:8px;color:#fbbf24">背离预警: '
    for name, d in all_divs:
        html += f'{name} {d["type"]}({d["date"]}) '
    html += '</p>\n'

if bull_count >= 5: pos = '偏积极（5-7成）— 多指数偏多共振'
elif bull_count >= 3: pos = '中性偏多（4-6成）— 分化行情'
elif bear_count >= 5: pos = '偏防御（1-3成）— 多指数偏空'
elif bear_count >= 3: pos = '中性偏空（2-4成）— 谨慎参与'
else: pos = '中性（3-5成）— 震荡市低吸高抛'
html += f'<p style="margin-top:10px;font-size:13pt;font-weight:700;color:#fbbf24">仓位建议: {pos}</p>\n'
html += '</div>\n'

html += '<div class="footer">czsc v0.10.12 · Tushare Pro · 2026-08-07 · 不构成投资建议</div>\n'
html += '</div></body></html>'

report_path = 'data/chan_index_report.html'
with open(report_path, 'w', encoding='utf-8') as f:
    f.write(html)
print(f"\n报告已保存: {report_path} ({os.path.getsize(report_path)//1024}KB)")
print("DONE")
