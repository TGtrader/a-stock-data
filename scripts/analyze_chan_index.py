#!/usr/bin/env python3
"""A股七大指数日线缠论分析 — 走势/中枢/背离/买卖点"""
import sys, os
sys.path.insert(0, '.')
import pandas as pd, numpy as np
import tushare as ts
from czsc import CZSC, Freq, RawBar, Direction
from TG_trading_sys.core.config import Config

ts.set_token(Config.get_tushare_token())
pro = ts.pro_api()

INDICES = {
    '上证指数': '000001.SH',
    '深证成指': '399001.SZ',
    '创业板指': '399006.SZ',
    '科创50':  '000688.SH',
    '沪深300': '000300.SH',
    '上证50':  '000016.SH',
    '中证500': '000905.SH',
}

def fetch_index(ts_code, name):
    df = pro.index_daily(ts_code=ts_code, start_date='20260101', end_date='20260807',
                         fields='trade_date,open,high,low,close,vol,amount')
    if df.empty:
        return None, None
    df = df.sort_values('trade_date').reset_index(drop=True)
    df['dt'] = pd.to_datetime(df['trade_date'])
    bars = [RawBar(symbol=ts_code, dt=r['dt'], open=float(r['open']),
                   high=float(r['high']), low=float(r['low']),
                   close=float(r['close']), vol=float(r['vol']),
                   amount=float(r['amount']), freq=Freq.D)
            for _, r in df.iterrows()]
    cz = CZSC(bars, max_bi_num=50)
    return df, cz

def compute_zs(bis):
    zs = []
    for i in range(len(bis)-2):
        b1,b2,b3 = bis[i],bis[i+1],bis[i+2]
        zd = max(b1.low,b2.low,b3.low)
        zg = min(b1.high,b2.high,b3.high)
        if zd < zg:
            zs.append({'start':str(b1.fx_a.dt)[:10],'end':str(b3.edt)[:10],
                       'zd':round(zd,2),'zg':round(zg,2),'zz':round((zd+zg)/2,2)})
    return zs

def detect_div(bis):
    divs = []
    up_bis = [b for b in bis if b.direction == Direction.Up]
    dn_bis = [b for b in bis if b.direction == Direction.Down]
    for i in range(1,len(up_bis)):
        p,c = up_bis[i-1],up_bis[i]
        if c.high > p.high and c.power < p.power*0.85:
            divs.append({'type':'顶背离','date':str(c.edt)[:10],
                         'detail':f'新高{c.high:.1f}>{p.high:.1f} power{c.power:.0f}<{p.power:.0f}'})
    for i in range(1,len(dn_bis)):
        p,c = dn_bis[i-1],dn_bis[i]
        if c.low < p.low and c.power < p.power*0.85:
            divs.append({'type':'底背离','date':str(c.edt)[:10],
                         'detail':f'新低{c.low:.1f}<{p.low:.1f} power{c.power:.0f}<{p.power:.0f}'})
    return divs

def chan_status(cz, df, zs_list):
    """综合判断多空状态"""
    last_close = float(df['close'].iloc[-1])
    last_date = str(df['trade_date'].iloc[-1])[:10]
    all_bis = list(cz.finished_bis)
    if cz.bi_list:
        all_bis = all_bis + list(cz.bi_list)

    # 趋势判断
    if zs_list:
        z = zs_list[-1]
        if last_close > z['zg']:
            position = '中枢上方 ▲'
            bias = '偏多'
        elif last_close < z['zd']:
            position = '中枢下方 ▼'
            bias = '偏空'
        else:
            position = '中枢内部 ◇'
            bias = '震荡'
    else:
        position = '无中枢'
        bias = '不明'

    # MA趋势
    ma5 = float(df['close'].tail(5).mean())
    ma20 = float(df['close'].tail(20).mean())
    ma_trend = '多头' if ma5 > ma20 else '空头'

    # 最新笔
    lb = all_bis[-1] if all_bis else None
    bi_dir = '上涨' if lb and lb.direction == Direction.Up else ('下跌' if lb else 'N/A')

    return {
        'name': cz.symbol,
        'date': last_date,
        'close': last_close,
        'ma5': round(ma5,1), 'ma20': round(ma20,1),
        'ma_trend': ma_trend,
        'bi_count': len(all_bis),
        'zs_count': len(zs_list),
        'fx_count': len(cz.fx_list),
        'bi_dir': bi_dir,
        'bi_change': f'{lb.change:+.1%}' if lb else 'N/A',
        'bi_power': f'{lb.power:.0f}' if lb else 'N/A',
        'position': position,
        'bias': bias,
        'zs_zg': zs_list[-1]['zg'] if zs_list else None,
        'zs_zd': zs_list[-1]['zd'] if zs_list else None,
    }

# ── 批量分析 ──────────────────────────────────────────────
results = {}
for name, code in INDICES.items():
    print(f"分析 {name} ({code})...")
    df, cz = fetch_index(code, name)
    if df is None:
        print(f"  SKIP: 无数据")
        continue
    all_bis = list(cz.finished_bis)
    if cz.bi_list:
        all_bis = all_bis + list(cz.bi_list)
    zs_list = compute_zs(all_bis)
    div_list = detect_div(all_bis)
    status = chan_status(cz, df, zs_list)
    results[name] = {
        'df': df, 'cz': cz, 'bis': all_bis,
        'zs': zs_list, 'divs': div_list, 'status': status
    }
    print(f"  K线:{len(df)} 分型:{len(cz.fx_list)} 笔:{len(all_bis)} 中枢:{len(zs_list)} 背离:{len(div_list)} {status['bias']}")

# ── 生成 HTML ────────────────────────────────────────────
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
.row{display:flex;gap:16px;flex-wrap:wrap}
.col{flex:1;min-width:280px}
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
.heatmap-header{display:flex;gap:4px;align-items:center}
.zs-bar{display:inline-block;height:14px;border-radius:3px;margin:1px 0}
.footer{text-align:center;color:#475569;font-size:8pt;margin-top:36px;padding-top:14px;border-top:1px solid #1e293b}
.advice-box{background:linear-gradient(135deg,#1e293b,#0f172a);border:1px solid #fbbf24;border-radius:10px;padding:16px 20px;margin:14px 0}
.advice-title{font-size:12pt;font-weight:700;color:#fbbf24;margin-bottom:8px}
.summary-table td:first-child{text-align:left;font-weight:600}
.price-up{color:#ef4444}.price-down{color:#22c55e}
</style></head><body><div class="container">
<h1>A股七大指数 缠论日线分析</h1>
<p class="sub">数据区间: 2026-01-01 ~ 2026-08-07 | 缠论引擎: czsc v0.10.12 | 生成: 2026-08-07</p>
"""

# ── 总览卡片 ──────────────────────────────────────────────
html += '<h2>一、七大指数总览</h2>\n<div class="status-grid">\n'
for name, r in results.items():
    s = r['status']
    price_cls = 'price-up' if s['close'] > s['ma5'] else 'price-down'
    html += f"""<div class="idx-card">
<div class="idx-name">{name}</div>
<div class="idx-price {price_cls}">{s['close']:.0f}</div>
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

# ── 汇总对比表 ────────────────────────────────────────────
html += '<h2>二、汇总对比</h2>\n<div class="card"><table class="summary-table">\n'
html += '<tr><th>指数</th><th>收盘</th><th>MA5</th><th>MA20</th><th>均线</th><th>笔方向</th><th>笔幅度</th><th>笔力量</th><th>中枢位置</th><th>判断</th><th>背离</th></tr>\n'
for name, r in results.items():
    s = r['status']
    html += f"<tr><td>{name}</td>"
    html += f"<td>{s['close']:.0f}</td><td>{s['ma5']:.0f}</td><td>{s['ma20']:.0f}</td>"
    html += f"<td>{s['ma_trend']}</td><td>{s['bi_dir']}</td><td>{s['bi_change']}</td><td>{s['bi_power']}</td>"
    html += f"<td>{s['position']}</td><td>{trend_badge(s['bias'])}</td>"
    div_tags = ''.join([f"<span class='signal signal-div-{"top" if d["type"]=="顶背离" else "bot"}'>{d['type'][:1]}</span> " for d in r['divs'][-3:]])
    html += f"<td>{div_tags if div_tags else '-'}</td></tr>\n"
html += '</table></div>\n'

# ── 各指数详细分析 ────────────────────────────────────────
html += '<h2>三、各指数详细分析</h2>\n'
for name, r in results.items():
    s = r['status']
    html += f'<h3>{name}</h3>\n<div class="card">\n'
    html += f'<p><strong>最新笔</strong>: {s["bi_dir"]}笔 · 幅度 {s["bi_change"]} · 力量 {s["bi_power"]} · {s["ma_trend"]}排列</p>\n'

    if r['zs']:
        z = r['zs'][-1]
        html += f'<p style="margin-top:6px"><strong>当前中枢</strong>: [{z["zd"]} ~ {z["zg"]}] ({z["start"]} ~ {z["end"]}) · 中轴 {z["zz"]}</p>\n'
        if s['close'] > z['zg']:
            html += f'<p style="color:#fca5a5">→ 中枢上方，若回踩不破为三买；跌破则回归震荡</p>\n'
        elif s['close'] < z['zd']:
            html += f'<p style="color:#86efac">→ 中枢下方，反弹不过为三卖；站回则回归震荡</p>\n'
        else:
            html += f'<p style="color:#bae6fd">→ 中枢内部震荡，下沿低吸上沿高抛</p>\n'

    if r['divs']:
        html += '<p style="margin-top:6px"><strong>背离信号</strong>: '
        for d in r['divs'][-3:]:
            cls = 'signal-div-top' if '顶' in d['type'] else 'signal-div-bot'
            html += f'<span class="signal {cls}">{d["type"]} {d["date"]}</span> '
        html += '</p>\n'

    # 笔列表（折叠）
    html += '<details style="margin-top:10px"><summary style="cursor:pointer;color:#38bdf8">展开笔列表</summary>'
    html += '<table style="margin-top:6px"><tr><th>#</th><th>方向</th><th>起始</th><th>结束</th><th>幅度</th><th>力量</th><th>SNR</th></tr>'
    for i,bi in enumerate(r['bis']):
        d = '↑涨' if bi.direction == Direction.Up else '↓跌'
        cls = 'up' if bi.direction == Direction.Up else 'down'
        html += f"<tr><td>{i+1}</td><td class='{cls}'>{d}</td>"
        html += f"<td>{str(bi.fx_a.dt)[:10]}</td><td>{str(bi.edt)[:10]}</td>"
        html += f"<td class='{cls}'>{bi.change:+.1%}</td><td>{bi.power:.0f}</td><td>{bi.SNR:.1f}</td></tr>"
    html += '</table></details>\n'
    html += '</div>\n'

# ── 综合判断 ──────────────────────────────────────────────
html += '<h2>四、综合研判</h2>\n<div class="advice-box">\n'
html += '<div class="advice-title">市场整体状态</div>\n'

bull_count = sum(1 for r in results.values() if '多' in r['status']['bias'])
bear_count = sum(1 for r in results.values() if '空' in r['status']['bias'])
neutral_count = len(results) - bull_count - bear_count

# 多空比
html += f'<p>偏多指数: {bull_count} | 偏空指数: {bear_count} | 震荡: {neutral_count}</p>\n'

# 找出最强和最弱
sorted_by_bias = sorted(results.items(), key=lambda x: (
    1 if '多' in x[1]['status']['bias'] else (0 if '震' in x[1]['status']['bias'] else -1)
), reverse=True)

strongest = sorted_by_bias[:2]
weakest = sorted_by_bias[-2:]

html += '<p style="margin-top:8px"><strong>最强</strong>: '
html += '、'.join([f'{n}({r["status"]["close"]:.0f})' for n,r in strongest])
html += ' &emsp; <strong>最弱</strong>: '
html += '、'.join([f'{n}({r["status"]["close"]:.0f})' for n,r in weakest])
html += '</p>\n'

# 背离预警
all_divs = [(name, d) for name, r in results.items() for d in r['divs']]
if all_divs:
    html += '<p style="margin-top:8px;color:#fbbf24">⚠️ 背离预警: '
    for name, d in all_divs:
        html += f'{name} {d["type"]}({d["date"]}) '
    html += '</p>\n'
else:
    html += '<p style="margin-top:8px;color:#86efac">✅ 七大指数均无背离信号</p>\n'

# 仓位建议
if bull_count >= 5:
    pos = '偏积极（5-7成）— 多数指数偏多共振'
elif bull_count >= 3:
    pos = '中性偏多（4-6成）— 分化行情，精选标的'
elif bear_count >= 5:
    pos = '偏防御（1-3成）— 多数指数偏空'
elif bear_count >= 3:
    pos = '中性偏空（2-4成）— 谨慎参与'
else:
    pos = '中性（3-5成）— 震荡市，低吸高抛'

html += f'<p style="margin-top:10px;font-size:13pt;font-weight:700;color:#fbbf24">仓位建议: {pos}</p>\n'
html += '</div>\n'

html += """<div class="footer">
本报告由 czsc (缠中说禅技术分析工具 v0.10.12) 自动生成 · 数据: Tushare Pro<br>仅用于技术分析研究，不构成任何投资建议
</div></div></body></html>"""

report_path = 'data/chan_index_report.html'
os.makedirs('data', exist_ok=True)
with open(report_path, 'w', encoding='utf-8') as f:
    f.write(html)
print(f"\n报告已保存: {report_path}")
print("DONE")
