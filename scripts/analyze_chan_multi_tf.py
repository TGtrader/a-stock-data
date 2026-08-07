#!/usr/bin/env python3
"""A股三大指数多级别缠论分析 — 日线+30分钟+5分钟 立体走势"""
import sys, os
sys.path.insert(0, '.')
sys.path.insert(0, 'scripts')
import pandas as pd, numpy as np
import tushare as ts
from czsc import CZSC, Freq, RawBar, Direction
from TG_trading_sys.core.config import Config
from Ashare import get_price
import plotly.graph_objects as go
from plotly.subplots import make_subplots

ts.set_token(Config.get_tushare_token())
pro = ts.pro_api()

FOCUS = {'上证指数': 'sh000001', '沪深300': 'sh000300', '科创50': 'sh000688'}

def fetch_daily(code, name):
    """Tushare 日线 + czsc 分析"""
    df = pro.index_daily(ts_code={'sh000001':'000001.SH','sh000300':'000300.SH','sh000688':'000688.SH'}[code],
                         start_date='20260501', end_date='20260807',
                         fields='trade_date,open,high,low,close,vol,amount')
    df = df.sort_values('trade_date').reset_index(drop=True)
    df['dt'] = pd.to_datetime(df['trade_date'])
    bars = [RawBar(symbol=code, dt=r['dt'], open=float(r['open']), high=float(r['high']),
                   low=float(r['low']), close=float(r['close']), vol=float(r['vol']),
                   amount=float(r['amount']), freq=Freq.D) for _, r in df.iterrows()]
    cz = CZSC(bars, max_bi_num=30)
    return df, cz, bars

def fetch_minute(code, freq, count):
    """Ashare 分钟数据 → RawBar列表"""
    fstr = {'5min':'5m','30min':'30m','60min':'60m'}[freq]
    df = get_price(code, frequency=fstr, count=count)
    if df.empty: return [], df
    freq_map = {'5min': Freq.F5, '30min': Freq.F30, '60min': Freq.F60}
    bars = []
    for idx, row in df.iterrows():
        bars.append(RawBar(symbol=code, dt=idx, open=float(row['open']),
                          high=float(row['high']), low=float(row['low']),
                          close=float(row['close']), vol=float(row['volume']),
                          amount=0, freq=freq_map[freq]))
    return bars, df

def compute_zs(bis):
    zs = []
    for i in range(len(bis)-2):
        b1,b2,b3 = bis[i],bis[i+1],bis[i+2]
        zd = max(b1.low,b2.low,b3.low)
        zg = min(b1.high,b2.high,b3.high)
        if zd < zg:
            zs.append({'start':b1.fx_a.dt,'end':b3.edt,'zd':round(zd,2),'zg':round(zg,2),'zz':round((zd+zg)/2,2)})
    return zs

def make_tf_chart(name, df_daily, cz_daily, minute_results, zs_daily):
    """多级别K线图: 日线+60min+30min+5min 四面板"""
    plot_d = df_daily.tail(40).copy()

    # 子图: 日线 / 60min / 30min / 5min
    fig = make_subplots(
        rows=4, cols=1, shared_xaxes=False,
        row_heights=[0.30, 0.23, 0.23, 0.24],
        vertical_spacing=0.05,
        subplot_titles=('日线（笔+中枢）', '60分钟', '30分钟', '5分钟（含未完成走势）')
    )

    # ── Panel 1: 日线 ──
    fig.add_trace(go.Candlestick(
        x=plot_d['dt'], open=plot_d['open'], high=plot_d['high'],
        low=plot_d['low'], close=plot_d['close'],
        increasing_line_color='#ef4444', decreasing_line_color='#22c55e',
        name='日K', showlegend=False), row=1, col=1)

    all_bis_d = list(cz_daily.finished_bis)
    if cz_daily.bi_list: all_bis_d = all_bis_d + list(cz_daily.bi_list)

    for bi in all_bis_d:
        if bi.edt >= plot_d['dt'].iloc[0]:
            c = '#ef4444' if bi.direction == Direction.Up else '#22c55e'
            sdt = max(bi.fx_a.dt, plot_d['dt'].iloc[0])
            y0 = bi.fx_a.low if bi.direction == Direction.Up else bi.fx_a.high
            y1 = bi.high if bi.direction == Direction.Up else bi.low
            fig.add_trace(go.Scatter(x=[sdt,bi.edt], y=[y0,y1], mode='lines',
                line=dict(color=c, width=2), showlegend=False,
                hovertext=f'笔 {bi.change:+.1%}'), row=1, col=1)

    for z in zs_daily:
        if z['end'] >= plot_d['dt'].iloc[0]:
            s = max(z['start'], plot_d['dt'].iloc[0])
            e = min(z['end'], plot_d['dt'].iloc[-1])
            fig.add_trace(go.Scatter(x=[s,e,e,s,s], y=[z['zg'],z['zg'],z['zd'],z['zd'],z['zg']],
                fill='toself', fillcolor='rgba(56,189,248,0.10)',
                line=dict(color='rgba(56,189,248,0.3)', width=1, dash='dot'),
                showlegend=False, hovertext=f'中枢[{z["zd"]}~{z["zg"]}]'), row=1, col=1)

    if zs_daily:
        z = zs_daily[-1]
        fig.add_hline(y=z['zg'], line_dash='dash', line_color='#fbbf24', line_width=1, row=1, col=1)
        fig.add_hline(y=z['zd'], line_dash='dash', line_color='#fbbf24', line_width=1, row=1, col=1)

    # Mark the unfinished zone on daily
    last_bi_dt = all_bis_d[-1].edt if all_bis_d else plot_d['dt'].iloc[0]
    fig.add_vrect(x0=last_bi_dt, x1=plot_d['dt'].iloc[-1],
                  fillcolor='rgba(251,191,36,0.08)', line_width=0, row=1, col=1)

    # ── Panels 2-4: 分钟级别 ──
    for row_i, freq in enumerate(['60min', '30min', '5min'], start=2):
        if freq in minute_results:
            bars, df_m = minute_results[freq]
            if df_m.empty: continue
            fig.add_trace(go.Candlestick(
                x=df_m.index, open=df_m['open'], high=df_m['high'],
                low=df_m['low'], close=df_m['close'],
                increasing_line_color='#ef4444', decreasing_line_color='#22c55e',
                name=f'{freq}K', showlegend=False), row=row_i, col=1)

            # czsc sub-level on minute bars
            try:
                cz_m = CZSC(bars, max_bi_num=30)
                bis_m = list(cz_m.finished_bis)
                if cz_m.bi_list: bis_m = bis_m + list(cz_m.bi_list)
                zs_m = compute_zs(bis_m)

                for bi in bis_m:
                    c = '#ef4444' if bi.direction == Direction.Up else '#22c55e'
                    y0 = bi.fx_a.low if bi.direction == Direction.Up else bi.fx_a.high
                    y1 = bi.high if bi.direction == Direction.Up else bi.low
                    fig.add_trace(go.Scatter(x=[bi.fx_a.dt, bi.edt], y=[y0,y1],
                        mode='lines', line=dict(color=c, width=1.5), showlegend=False,
                        hovertext=f'{freq}笔 {bi.change:+.1%} pow={bi.power:.0f}'), row=row_i, col=1)

                for z in zs_m:
                    fig.add_trace(go.Scatter(x=[z['start'],z['end'],z['end'],z['start'],z['start']],
                        y=[z['zg'],z['zg'],z['zd'],z['zd'],z['zg']],
                        fill='toself', fillcolor='rgba(56,189,248,0.08)',
                        line=dict(color='rgba(56,189,248,0.2)', width=1, dash='dot'),
                        showlegend=False), row=row_i, col=1)

                # FX markers
                bx, by, sx, sy = [], [], [], []
                for fx in cz_m.fx_list:
                    if repr(fx.mark) == 'Mark.D': bx.append(fx.dt); by.append(fx.low)
                    elif repr(fx.mark) == 'Mark.G': sx.append(fx.dt); sy.append(fx.high)
                fig.add_trace(go.Scatter(x=bx, y=by, mode='markers',
                    marker=dict(symbol='triangle-up', size=6, color='#22c55e'),
                    showlegend=False), row=row_i, col=1)
                fig.add_trace(go.Scatter(x=sx, y=sy, mode='markers',
                    marker=dict(symbol='triangle-down', size=6, color='#ef4444'),
                    showlegend=False), row=row_i, col=1)
            except Exception:
                pass

    fig.update_layout(
        template='plotly_dark', height=1100,
        margin=dict(l=10, r=10, t=40, b=10),
        title=dict(text=f'{name} 多级别缠论走势', font=dict(size=16, color='#38bdf8')),
        font=dict(family='Microsoft YaHei')
    )
    for r in range(1,5):
        fig.update_xaxes(rangeslider_visible=False, row=r, col=1)

    path = f'data/chan_mtf_{name}.html'
    fig.write_html(path, include_plotlyjs='cdn', config={'displayModeBar': True})
    return path

# ── MAIN ──────────────────────────────────────────────────
os.makedirs('data', exist_ok=True)
all_results = {}
chart_paths = {}

for name, code in FOCUS.items():
    print(f"\n{'='*60}\n{name} ({code})\n{'='*60}")

    # 1. 日线分析
    df_d, cz_d, bars_d = fetch_daily(code, name)
    all_bis_d = list(cz_d.finished_bis)
    if cz_d.bi_list: all_bis_d = all_bis_d + list(cz_d.bi_list)
    zs_daily = compute_zs(all_bis_d)

    last_close = float(df_d['close'].iloc[-1])
    last_date = str(df_d['trade_date'].iloc[-1])[:10]
    last_bi = all_bis_d[-1] if all_bis_d else None
    last_bi_end = last_bi.edt if last_bi else df_d['dt'].iloc[0]

    print(f"日线: {len(df_d)}根K, {len(all_bis_d)}笔, {len(zs_daily)}中枢")
    print(f"最新笔: {'上涨' if last_bi and last_bi.direction==Direction.Up else '下跌'}笔 "
          f"({str(last_bi.fx_a.dt)[:10]}→{str(last_bi.edt)[:10] if last_bi else 'N/A'}) "
          f"幅度{last_bi.change:+.1%}" if last_bi else "N/A")

    # 2. 判断未完成段
    days_since_bi = (df_d['dt'].iloc[-1] - last_bi_end).days if last_bi else 0
    print(f"日线末笔结束于 {str(last_bi_end)[:10]}, 距今 {days_since_bi} 天")

    # 3. 多级别分钟分析
    minute_results = {}
    need_minute = days_since_bi >= 0  # always do minute for the latest segment

    # 60min: 覆盖最近1个月
    bars_60, df_60 = fetch_minute(code, '60min', 80)
    if bars_60:
        cz_60 = CZSC(bars_60, max_bi_num=30)
        bis_60 = list(cz_60.finished_bis)
        if cz_60.bi_list: bis_60 = bis_60 + list(cz_60.bi_list)
        zs_60 = compute_zs(bis_60)
        print(f"60分钟: {len(df_60)}根K, {len(bis_60)}笔, {len(zs_60)}中枢")
        minute_results['60min'] = (bars_60, df_60)

        # Check for divergence on 60min
        up_60 = [b for b in bis_60 if b.direction == Direction.Up]
        dn_60 = [b for b in bis_60 if b.direction == Direction.Down]
        for i in range(1, len(up_60)):
            p, c = up_60[i-1], up_60[i]
            if c.high > p.high and c.power < p.power * 0.85:
                print(f"  [!] 60min顶背离: {str(c.edt)[:16]} 新高{c.high:.1f}>{p.high:.1f} 力衰{c.power:.0f}<{p.power:.0f}")
        for i in range(1, len(dn_60)):
            p, c = dn_60[i-1], dn_60[i]
            if c.low < p.low and c.power < p.power * 0.85:
                print(f"  [OK] 60min底背离: {str(c.edt)[:16]} 新低{c.low:.1f}<{p.low:.1f} 力衰{c.power:.0f}<{p.power:.0f}")

    # 30min: 覆盖最近2周
    bars_30, df_30 = fetch_minute(code, '30min', 100)
    if bars_30:
        cz_30 = CZSC(bars_30, max_bi_num=30)
        bis_30 = list(cz_30.finished_bis)
        if cz_30.bi_list: bis_30 = bis_30 + list(cz_30.bi_list)
        zs_30 = compute_zs(bis_30)
        print(f"30分钟: {len(df_30)}根K, {len(bis_30)}笔, {len(zs_30)}中枢")
        minute_results['30min'] = (bars_30, df_30)

        # Check sub-level structure
        lb_30 = bis_30[-1] if bis_30 else None
        if lb_30:
            print(f"  最新30min笔: {'上涨' if lb_30.direction==Direction.Up else '下跌'}"
                  f" ({str(lb_30.fx_a.dt)[:16]}→{str(lb_30.edt)[:16]}) 幅度{lb_30.change:+.1%}")

    # 5min: 覆盖最近5日
    bars_5, df_5 = fetch_minute(code, '5min', 200)
    if bars_5:
        cz_5 = CZSC(bars_5, max_bi_num=30)
        bis_5 = list(cz_5.finished_bis)
        if cz_5.bi_list: bis_5 = bis_5 + list(cz_5.bi_list)
        zs_5 = compute_zs(bis_5)
        print(f"5分钟: {len(df_5)}根K, {len(bis_5)}笔, {len(zs_5)}中枢")
        minute_results['5min'] = (bars_5, df_5)

        # Find the critical detail
        if bis_5:
            lb_5 = bis_5[-1]
            print(f"  最新5min笔: {'上涨' if lb_5.direction==Direction.Up else '下跌'}"
                  f" ({str(lb_5.fx_a.dt)[:16]}→{str(lb_5.edt)[:16]}) 幅度{lb_5.change:+.1%}")
            # Check if there's a 三买/三卖 forming
            if len(zs_5) > 0:
                z_5 = zs_5[-1]
                last_5_close = float(df_5['close'].iloc[-1])
                if last_5_close > z_5['zg']:
                    print(f"  → 5min中枢上方，小级别三买待确认")
                elif last_5_close < z_5['zd']:
                    print(f"  → 5min中枢下方，小级别三卖风险")

    # Generate chart
    cp = make_tf_chart(name, df_d, cz_d, minute_results, zs_daily)
    chart_paths[name] = cp
    print(f"图表: {cp}")

    all_results[name] = {
        'df_d': df_d, 'cz_d': cz_d, 'bis_d': all_bis_d, 'zs_d': zs_daily,
        'minute': minute_results, 'last_close': last_close, 'last_bi': last_bi,
    }

# ── 生成报告 ──────────────────────────────────────────────
html = """<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><title>多级别缠论分析 — 上证·沪深300·科创50</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:"Microsoft YaHei","SimHei",sans-serif;background:#0f172a;color:#e2e8f0;padding:20px;line-height:1.6}
.c{max-width:1300px;margin:0 auto}
h1{text-align:center;font-size:20pt;color:#38bdf8;margin-bottom:4px}
.sub{text-align:center;color:#94a3b8;font-size:9pt;margin-bottom:20px}
h2{font-size:15pt;color:#38bdf8;margin:24px 0 12px;padding-left:10px;border-left:3px solid #0ea5e9}
h3{font-size:12pt;color:#e2e8f0;margin:14px 0 8px}
.card{background:#1e293b;border-radius:10px;padding:16px 20px;margin-bottom:14px;border:1px solid #334155}
table{width:100%;border-collapse:collapse;font-size:9pt;margin:6px 0}
th{background:#0f172a;color:#38bdf8;padding:6px 10px;text-align:center;font-weight:600;border-bottom:2px solid #1e3b5a}
td{padding:5px 10px;text-align:center;border-bottom:1px solid #1e293b}
tr:hover td{background:#1e3b5a}
.up{color:#ef4444;font-weight:700}.down{color:#22c55e;font-weight:700}
.bd{display:inline-block;padding:3px 10px;border-radius:12px;font-size:9pt;font-weight:700}
.bd-up{background:#7f1d1d;color:#fca5a5}.bd-down{background:#064e3b;color:#86efac}
.bd-n{background:#1e3b5a;color:#bae6fd}
.sg{font-size:8pt;padding:2px 6px;border-radius:4px;margin:2px;display:inline-block}
.sg-t{background:#4a044e;color:#e879f9}.sg-b{background:#064e3b;color:#86efac}
.sg-w{background:#78350f;color:#fbbf24}
.mtf-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px}
.mtf-card{background:#0f172a;border-radius:8px;padding:14px;border:1px solid #334155}
.mtf-label{font-size:8pt;color:#64748b}
.mtf-val{font-size:10pt;font-weight:600}
.chart-wrap{background:#0f172a;border-radius:10px;padding:8px;margin:12px 0}
.chart-wrap iframe{width:100%;height:1140px;border:none;border-radius:6px}
.key-finding{background:linear-gradient(135deg,#1e293b,#0f172a);border:1px solid #fbbf24;border-radius:10px;padding:16px 20px;margin:14px 0}
.key-finding h3{color:#fbbf24;margin:0 0 10px}
.footer{text-align:center;color:#475569;font-size:8pt;margin-top:32px;padding-top:14px;border-top:1px solid #1e293b}
</style></head><body><div class="c">
<h1>A股三大指数 · 多级别缠论分析</h1>
<p class="sub">日线 → 60分钟 → 30分钟 → 5分钟 | 未完成笔精确分解 | czsc v0.10.12 + Ashare | 2026-08-07</p>
"""

# 总览表
html += '<h2>一、日线级别总览</h2>\n<div class="card"><table>\n'
html += '<tr><th>指数</th><th>收盘</th><th>笔数</th><th>中枢数</th><th>最新日线笔</th><th>日线幅度</th><th>未完成天数</th><th>小级别信号</th></tr>\n'
for name, r in all_results.items():
    s = r
    lb = r['last_bi']
    bi_str = f"{'上涨' if lb and lb.direction==Direction.Up else '下跌'} ({str(lb.fx_a.dt)[5:10]}→{str(lb.edt)[5:10]})" if lb else "N/A"
    bi_chg = f'{lb.change:+.1%}' if lb else 'N/A'
    days = (r['df_d']['dt'].iloc[-1] - (lb.edt if lb else r['df_d']['dt'].iloc[0])).days if lb else 0

    # sub-level signals
    signals = []
    if '5min' in r['minute']:
        bars, df_m = r['minute']['5min']
        try:
            cz_m = CZSC(bars, max_bi_num=20)
            bis_m = list(cz_m.finished_bis)
            if cz_m.bi_list: bis_m = bis_m + list(cz_m.bi_list)
            if bis_m:
                lb_m = bis_m[-1]
                d5 = '上涨' if lb_m.direction == Direction.Up else '下跌'
                signals.append(f'5min{d5}笔{lb_m.change:+.1%}')
                # 背离检查
                up_m = [b for b in bis_m if b.direction == Direction.Up]
                dn_m = [b for b in bis_m if b.direction == Direction.Down]
                for i in range(1, len(up_m)):
                    if up_m[i].high > up_m[i-1].high and up_m[i].power < up_m[i-1].power * 0.85:
                        signals.append('<span class="sg sg-t">5min顶背</span>')
                for i in range(1, len(dn_m)):
                    if dn_m[i].low < dn_m[i-1].low and dn_m[i].power < dn_m[i-1].power * 0.85:
                        signals.append('<span class="sg sg-b">5min底背</span>')
        except: pass

    html += f"<tr><td style='text-align:left;font-weight:600'>{name}</td><td>{r['last_close']:.0f}</td>"
    html += f"<td>{len(r['bis_d'])}</td><td>{len(r['zs_d'])}</td><td>{bi_str}</td><td>{bi_chg}</td>"
    html += f"<td>{days}天</td><td>{' '.join(signals) if signals else '—'}</td></tr>\n"
html += '</table></div>\n'

# 各指数详细分析
html += '<h2>二、多级别走势图（四面板）</h2>\n'
html += '<p style="color:#94a3b8;font-size:9pt;margin-bottom:12px">'
html += '日线: 笔连线+中枢框 | 黄色半透明=未完成段 | 分钟级: 笔连线+中枢+分型<br>'
html += '🔴红线=上涨笔 | 🟢绿线=下跌笔 | ▲底分型 | ▼顶分型 | 蓝色框=中枢 | 可交互缩放</p>\n'

for name in ['上证指数', '沪深300', '科创50']:
    if name in chart_paths:
        html += f'<h3>{name}</h3>\n<div class="chart-wrap"><iframe src="{os.path.basename(chart_paths[name])}"></iframe></div>\n'

# 小级别核心发现
html += '<h2>三、小级别新发现</h2>\n'

# Analyze each index for key sub-level insights
for name in ['上证指数', '沪深300', '科创50']:
    r = all_results.get(name)
    if not r: continue
    html += f'<h3>{name}</h3>\n<div class="mtf-grid">\n'

    for freq in ['60min', '30min', '5min']:
        if freq not in r['minute']: continue
        bars, df_m = r['minute'][freq]
        try:
            cz_m = CZSC(bars, max_bi_num=25)
            bis_m = list(cz_m.finished_bis)
            if cz_m.bi_list: bis_m = bis_m + list(cz_m.bi_list)
            zs_m = compute_zs(bis_m)
            lb_m = bis_m[-1] if bis_m else None
            last_m_close = float(df_m['close'].iloc[-1])

            # 状态判断
            if zs_m:
                zm = zs_m[-1]
                if last_m_close > zm['zg']: pos = '中枢上方'
                elif last_m_close < zm['zd']: pos = '中枢下方'
                else: pos = '中枢内部'
            else:
                pos = '单边无中枢'

            bi_dir = '↑涨' if lb_m and lb_m.direction==Direction.Up else '↓跌' if lb_m else '—'
            bi_chg = f'{lb_m.change:+.1%}' if lb_m else '—'

            html += f"""<div class="mtf-card">
<div class="mtf-label">{freq}级别</div>
<div><span class="mtf-val">{len(bis_m)}笔</span> · <span class="mtf-val">{len(zs_m)}中枢</span> · <span class="mtf-val">{len(cz_m.fx_list)}分型</span></div>
<div style="margin-top:6px">最新笔: <span class="{'up' if lb_m and lb_m.direction==Direction.Up else 'down'}">{bi_dir} {bi_chg}</span></div>
<div>当前位置: <span class="bd {'bd-up' if '上' in pos else 'bd-down' if '下' in pos else 'bd-n'}">{pos}</span></div>\n"""

            # Check for key signals
            if zs_m and lb_m and lb_m.direction == Direction.Down and last_m_close > zm['zg']:
                html += '<div style="margin-top:4px"><span class="sg sg-w">⚡下跌笔+回升至中枢上沿 → 可能二买确认</span></div>\n'
            elif zs_m and lb_m and lb_m.direction == Direction.Up and last_m_close < zm['zd']:
                html += '<div style="margin-top:4px"><span class="sg sg-t">⚡上涨笔+跌回中枢下沿 → 警惕二卖</span></div>\n'

            html += '</div>\n'
        except Exception as e:
            html += f'<div class="mtf-card"><div class="mtf-label">{freq}</div><div>分析异常: {e}</div></div>\n'

    html += '</div>\n'

# 综合研判
html += '<h2>四、多级别立体研判</h2>\n<div class="key-finding">\n'
html += '<h3>核心发现</h3>\n'

findings = []
for name, r in all_results.items():
    lb = r['last_bi']
    if not lb: continue
    days_since = (r['df_d']['dt'].iloc[-1] - lb.edt).days

    # Check 60min for direction confirmation
    if '60min' in r['minute']:
        bars60, df60 = r['minute']['60min']
        try:
            cz60 = CZSC(bars60, max_bi_num=20)
            bis60 = list(cz60.finished_bis) + (list(cz60.bi_list) if cz60.bi_list else [])
            if bis60:
                lb60 = bis60[-1]
                zs60 = compute_zs(bis60)

                # Multi-TF conclusion
                d_dir = '上涨' if lb.direction == Direction.Up else '下跌'
                m60_dir = '上涨' if lb60.direction == Direction.Up else '下跌'

                if d_dir == m60_dir:
                    findings.append(f'{name}: 日线{d_dir}笔 + 60min{m60_dir}笔 → <b style="color:#38bdf8">日线笔大概率延续</b>，60min笔完成前日线笔不会转向')
                else:
                    findings.append(f'{name}: 日线{d_dir}笔 + 60min已转{m60_dir} → <b style="color:#fbbf24">日线笔可能接近尾声</b>，等待60min笔完成确认')

                # ZS overlap
                zs_d = r['zs_d']
                if zs_d and zs60:
                    zd, zg = zs_d[-1]['zd'], zs_d[-1]['zg']
                    last_c = float(df60['close'].iloc[-1])
                    if last_c > zg and m60_dir == '下跌':
                        findings.append(f'{name}: <b style="color:#fca5a5">日线中枢上方的60min下跌 → 若止跌即为60min二买/日线三买共振</b>')
                    elif last_c < zd and m60_dir == '上涨':
                        findings.append(f'{name}: <b style="color:#86efac">日线中枢下方的60min上涨 → 若遇阻即为60min二卖/日线三卖共振</b>')
        except: pass

    # Check 5min for immediate direction
    if '5min' in r['minute']:
        bars5, df5 = r['minute']['5min']
        try:
            cz5 = CZSC(bars5, max_bi_num=20)
            bis5 = list(cz5.finished_bis) + (list(cz5.bi_list) if cz5.bi_list else [])
            if bis5:
                lb5 = bis5[-1]
                findings.append(f'{name}: 5分钟最新{("上涨" if lb5.direction==Direction.Up else "下跌")}笔 幅度{lb5.change:+.1%} power={lb5.power:.0f}')
        except: pass

for f in findings:
    html += f'<p style="margin:6px 0">{f}</p>\n'

html += '</div>\n'

html += '<div class="footer">czsc v0.10.12 · Ashare 新浪+腾讯分钟数据 · Tushare Pro 日线 · 2026-08-07 · 不构成投资建议</div>\n'
html += '</div></body></html>'

report_path = 'data/chan_multi_tf_report.html'
with open(report_path, 'w', encoding='utf-8') as f:
    f.write(html)

# Size
total_kb = os.path.getsize(report_path)//1024
for cp in chart_paths.values():
    total_kb += os.path.getsize(cp)//1024
print(f"\n报告: {report_path} ({os.path.getsize(report_path)//1024}KB)")
print(f"图表: {len(chart_paths)}个 (总{sum(os.path.getsize(c) for c in chart_paths.values())//1024}KB)")
print("DONE")
