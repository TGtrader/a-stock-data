#!/usr/bin/env python3
"""江丰电子(300666) K线+缠论叠加图 + 交易建议"""
import sys, os
sys.path.insert(0, '.')

import pandas as pd
import numpy as np
import tushare as ts
from czsc import CZSC, Freq, RawBar, Direction
from TG_trading_sys.core.config import Config

# ── 1. 数据 ─────────────────────────────────────────────
ts.set_token(Config.get_tushare_token())
pro = ts.pro_api()
df = pro.daily(ts_code='300666.SZ', start_date='20260101', end_date='20260806',
               fields='trade_date,open,high,low,close,vol,amount')
df = df.sort_values('trade_date').reset_index(drop=True)
df.rename(columns={'trade_date': 'dt', 'vol': 'volume'}, inplace=True)
df['dt'] = pd.to_datetime(df['dt'])

bars = [RawBar(symbol='300666', dt=r['dt'], open=float(r['open']),
               high=float(r['high']), low=float(r['low']),
               close=float(r['close']), vol=float(r['volume']),
               amount=float(r['amount']), freq=Freq.D) for _, r in df.iterrows()]

cz = CZSC(bars, max_bi_num=50)
all_bis = list(cz.finished_bis)
if cz.bi_list:
    all_bis = all_bis + list(cz.bi_list)

# ── 2. 中枢计算 ─────────────────────────────────────────
def compute_zs(bis):
    zs_list = []
    for i in range(len(bis) - 2):
        b1, b2, b3 = bis[i], bis[i+1], bis[i+2]
        zd = max(b1.low, b2.low, b3.low)
        zg = min(b1.high, b2.high, b3.high)
        if zd < zg:
            zs_list.append({'start_dt': b1.fx_a.dt, 'end_dt': b3.edt,
                           'zd': zd, 'zg': zg, 'zz': (zd+zg)/2})
    return zs_list

zs_list = compute_zs(all_bis)

# ── 3. 缠论交易建议 ─────────────────────────────────────
last_close = float(df['close'].iloc[-1])
last_date = df['dt'].iloc[-1]

def chan_advice(close, zs_list, bis):
    """基于缠论三买三卖原则给出建议"""
    advice = []
    signals = {'buy': [], 'sell': [], 'hold': [], 'watch': []}

    # 确定当前中枢
    current_zs = zs_list[-1] if zs_list else None

    # 1. 位置判断
    if current_zs:
        zg, zd = current_zs['zg'], current_zs['zd']
        if close > zg:
            advice.append(f'当前价 {close:.2f} > 中枢上沿 {zg:.2f}，处于中枢上方')
            # 判断是否为三类买点
            if len(bis) >= 2:
                last_bi = bis[-1]
                prev_bi = bis[-2]
                if last_bi.direction == Direction.Down:
                    # 下跌笔结束回拉不进中枢 → 三买
                    advice.append('⚠️ 若当前下跌笔结束且不破中枢上沿，可能出现【第三类买点】')
                    signals['watch'].append('三买候选：等底分型确认后回踩不破中枢上沿为三买')
                elif last_bi.direction == Direction.Up:
                    # 上涨离开中枢
                    advice.append('当前处于中枢上方离开段，关注是否形成背驰')
                    # 检查背驰
                    up_bis = [b for b in bis if b.direction == Direction.Up]
                    if len(up_bis) >= 2:
                        prev_up, cur_up = up_bis[-2], up_bis[-1]
                        if cur_up.high > prev_up.high and cur_up.power < prev_up.power * 0.85:
                            advice.append(f'🔴 顶背驰警告：价格新高但力量衰减，建议减仓')
                            signals['sell'].append(f'顶背驰卖点：{cur_up.edt.strftime("%m-%d")} 新高但power从{prev_up.power:.0f}降至{cur_up.power:.0f}')
                        else:
                            advice.append('未出现顶背驰，可继续持有观察')
                            signals['hold'].append('中枢上方无背驰，持多单')

        elif close < zd:
            advice.append(f'当前价 {close:.2f} < 中枢下沿 {zd:.2f}，处于中枢下方')
            if len(bis) >= 2:
                last_bi = bis[-1]
                if last_bi.direction == Direction.Up:
                    advice.append('⚠️ 若当前上涨笔不破中枢下沿，可能出现【第三类卖点】')
                    signals['sell'].append('三卖风险：反弹不进中枢下沿应止损')
                elif last_bi.direction == Direction.Down:
                    # 下跌离开中枢
                    dn_bis = [b for b in bis if b.direction == Direction.Down]
                    if len(dn_bis) >= 2:
                        prev_dn, cur_dn = dn_bis[-2], dn_bis[-1]
                        if cur_dn.low < prev_dn.low and cur_dn.power < prev_dn.power * 0.85:
                            advice.append('🟢 底背驰信号：价格新低但力量衰减，下跌动能衰竭')
                            signals['buy'].append('底背驰买点：下跌衰竭，等底分型确认后入场')
                        else:
                            advice.append('下跌未出现背驰，观望等待')
                            signals['watch'].append('中枢下方下跌中，等底分型或背驰信号')
        else:
            advice.append(f'当前价 {close:.2f} 处于中枢内部 [{zd:.2f} ~ {zg:.2f}]，震荡行情')
            advice.append('中枢震荡策略：下沿附近考虑低吸，上沿附近考虑高抛')
            if close < (zd+zg)/2:
                signals['watch'].append('中枢下半区，接近下沿可考虑低吸')
            else:
                signals['watch'].append('中枢上半区，接近上沿可考虑减仓')

    # 2. 最新笔方向
    if bis:
        lb = bis[-1]
        d = '上涨' if lb.direction == Direction.Up else '下跌'
        advice.append(f'最新笔方向：{d}（{lb.fx_a.dt.strftime("%m-%d")}→{lb.edt.strftime("%m-%d")}，幅度{lb.change:+.1%}）')

    # 3. 分型信号
    fx_list = cz.fx_list
    recent_fx = [fx for fx in fx_list[-6:] if fx.dt >= pd.Timestamp('2026-07-15')]
    for fx in recent_fx:
        if repr(fx.mark) == 'Mark.D':
            advice.append(f'🟢 近期底分型: {fx.dt.strftime("%m-%d")} @ {fx.low:.2f}')
        elif repr(fx.mark) == 'Mark.G':
            advice.append(f'🔴 近期顶分型: {fx.dt.strftime("%m-%d")} @ {fx.high:.2f}')

    return advice, signals, current_zs

advice, signals, current_zs = chan_advice(last_close, zs_list, all_bis)

print("=== 交易建议 ===")
for a in advice:
    # strip emoji for console (GBK), full text in HTML
    clean = a.encode('ascii', errors='replace').decode('ascii')
    print(f"  {clean}")

# ── 4. 生成 K线图 (plotly) ──────────────────────────────
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# 选最近60根K线让图清晰
plot_df = df.tail(80).copy()
plot_dates = plot_df['dt']

fig = make_subplots(
    rows=3, cols=1, shared_xaxes=True,
    row_heights=[0.55, 0.25, 0.20],
    vertical_spacing=0.04,
    subplot_titles=('江丰电子(300666) 日线 — 缠论笔+中枢', '成交量', '笔力度(Power)')
)

# K线
colors = ['#ef4444' if plot_df['close'].iloc[i] >= plot_df['open'].iloc[i]
          else '#22c55e' for i in range(len(plot_df))]
fig.add_trace(go.Candlestick(
    x=plot_dates, open=plot_df['open'], high=plot_df['high'],
    low=plot_df['low'], close=plot_df['close'],
    increasing_line_color='#ef4444', decreasing_line_color='#22c55e',
    increasing_fillcolor='#ef4444', decreasing_fillcolor='#22c55e',
    name='日K线', showlegend=True
), row=1, col=1)

# 中枢区域
for z in zs_list:
    if z['end_dt'] >= plot_dates.iloc[0] and z['start_dt'] <= plot_dates.iloc[-1]:
        start = max(z['start_dt'], plot_dates.iloc[0])
        end = min(z['end_dt'], plot_dates.iloc[-1])
        fig.add_trace(go.Scatter(
            x=[start, end, end, start, start],
            y=[z['zg'], z['zg'], z['zd'], z['zd'], z['zg']],
            fill='toself', fillcolor='rgba(56,189,248,0.12)',
            line=dict(color='rgba(56,189,248,0.4)', width=1, dash='dot'),
            name=f'中枢 [{z["zd"]:.0f}~{z["zg"]:.0f}]',
            showlegend=False, hoverinfo='text',
            text=f'中枢: {z["zd"]:.2f}~{z["zg"]:.2f}'
        ), row=1, col=1)

# 最新中枢高亮
if current_zs and current_zs['end_dt'] >= plot_dates.iloc[0]:
    z = current_zs
    fig.add_hline(y=z['zg'], line_dash='dash', line_color='#fbbf24', line_width=1.5,
                  annotation_text=f'Zg={z["zg"]:.1f}', row=1, col=1)
    fig.add_hline(y=z['zd'], line_dash='dash', line_color='#fbbf24', line_width=1.5,
                  annotation_text=f'Zd={z["zd"]:.1f}', row=1, col=1)

# 笔 - 画连线
for bi in all_bis:
    if bi.edt >= plot_dates.iloc[0]:
        color = '#ef4444' if bi.direction == Direction.Up else '#22c55e'
        sdt = max(bi.fx_a.dt, plot_dates.iloc[0])
        edt = min(bi.edt, plot_dates.iloc[-1])
        # 用笔的起点和终点价格
        y0 = bi.fx_a.low if bi.direction == Direction.Up else bi.fx_a.high
        y1 = bi.high if bi.direction == Direction.Up else bi.low
        fig.add_trace(go.Scatter(
            x=[sdt, edt], y=[y0, y1],
            mode='lines', line=dict(color=color, width=2.5),
            name=f'{"上涨" if bi.direction == Direction.Up else "下跌"}笔',
            showlegend=False, hoverinfo='text',
            text=f'笔: {bi.fx_a.dt.strftime("%m-%d")}→{bi.edt.strftime("%m-%d")} {bi.change:+.1%}'
        ), row=1, col=1)

# 分型标记
buy_x, buy_y, sell_x, sell_y = [], [], [], []
for fx in cz.fx_list:
    if fx.dt >= plot_dates.iloc[0]:
        if repr(fx.mark) == 'Mark.D':
            buy_x.append(fx.dt); buy_y.append(fx.low)
        elif repr(fx.mark) == 'Mark.G':
            sell_x.append(fx.dt); sell_y.append(fx.high)

fig.add_trace(go.Scatter(x=buy_x, y=buy_y, mode='markers',
    marker=dict(symbol='triangle-up', size=10, color='#22c55e', line=dict(width=1, color='#fff')),
    name='底分型(买)', showlegend=True), row=1, col=1)

fig.add_trace(go.Scatter(x=sell_x, y=sell_y, mode='markers',
    marker=dict(symbol='triangle-down', size=10, color='#ef4444', line=dict(width=1, color='#fff')),
    name='顶分型(卖)', showlegend=True), row=1, col=1)

# 成交量
fig.add_trace(go.Bar(
    x=plot_dates, y=plot_df['volume'],
    marker_color=['#ef4444' if plot_df['close'].iloc[i] >= plot_df['open'].iloc[i]
                  else '#22c55e' for i in range(len(plot_df))],
    marker_opacity=0.5, name='成交量', showlegend=False
), row=2, col=1)

# 笔力量 (Power) 柱状图
power_dates = [bi.edt for bi in all_bis if bi.edt >= plot_dates.iloc[0]]
power_vals = [bi.power for bi in all_bis if bi.edt >= plot_dates.iloc[0]]
power_colors = ['#ef4444' if bi.direction == Direction.Up else '#22c55e'
                for bi in all_bis if bi.edt >= plot_dates.iloc[0]]
fig.add_trace(go.Bar(
    x=power_dates, y=power_vals, marker_color=power_colors,
    marker_opacity=0.7, name='笔力量', showlegend=False
), row=3, col=1)
fig.add_hline(y=0, line_color='#64748b', line_width=1, row=3, col=1)

# Layout
fig.update_layout(
    template='plotly_dark',
    height=900,
    margin=dict(l=20, r=20, t=50, b=20),
    legend=dict(orientation='h', y=1.02, x=0, bgcolor='rgba(0,0,0,0)'),
    hovermode='x unified',
    font=dict(family='Microsoft YaHei, SimHei, sans-serif'),
)
fig.update_xaxes(rangeslider_visible=False, row=1, col=1)
fig.update_xaxes(rangeslider_visible=False, row=2, col=1)
fig.update_yaxes(title='价格(元)', row=1, col=1)
fig.update_yaxes(title='成交量', row=2, col=1)
fig.update_yaxes(title='Power', row=3, col=1)

chart_path = 'data/chan_300666_chart.html'
fig.write_html(chart_path, include_plotlyjs='cdn', config={'displayModeBar': True})
print(f"\nK线图已保存: {chart_path}")

# ── 5. 合并生成最终报告 ─────────────────────────────────
html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>江丰电子(300666) 缠论完整分析报告</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:"Microsoft YaHei","SimHei",sans-serif;background:#0f172a;color:#e2e8f0;padding:20px;line-height:1.6}}
.container{{max-width:1200px;margin:0 auto}}
h1{{text-align:center;font-size:22pt;color:#38bdf8;margin-bottom:4px}}
.sub{{text-align:center;color:#94a3b8;font-size:9pt;margin-bottom:20px}}
h2{{font-size:15pt;color:#38bdf8;margin:28px 0 14px;padding-left:10px;border-left:3px solid #0ea5e9}}
h3{{font-size:12pt;color:#e2e8f0;margin:16px 0 8px}}
.card{{background:#1e293b;border-radius:10px;padding:18px 22px;margin-bottom:18px;border:1px solid #334155}}
.row{{display:flex;gap:18px;flex-wrap:wrap}}
.col{{flex:1;min-width:280px}}
table{{width:100%;border-collapse:collapse;font-size:9pt;margin:8px 0}}
th{{background:#0f172a;color:#38bdf8;padding:7px 10px;text-align:center;font-weight:600;border-bottom:2px solid #1e3b5a}}
td{{padding:6px 10px;text-align:center;border-bottom:1px solid #1e293b}}
tr:hover td{{background:#1e3b5a}}
.up{{color:#ef4444;font-weight:700}}
.down{{color:#22c55e;font-weight:700}}
.tag{{display:inline-block;padding:2px 8px;border-radius:4px;font-size:8pt;font-weight:700;margin:0 2px}}
.tag-buy{{background:#064e3b;color:#22c55e}}
.tag-sell{{background:#7f1d1d;color:#ef4444}}
.tag-watch{{background:#1e3b5a;color:#38bdf8}}
.tag-hold{{background:#422006;color:#fbbf24}}
.tag-risk{{background:#4a044e;color:#e879f9}}
.status-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px}}
.stat{{background:#0f172a;border-radius:8px;padding:14px;text-align:center}}
.stat-num{{font-size:22pt;font-weight:800;color:#38bdf8}}
.stat-label{{font-size:8pt;color:#94a3b8;margin-top:2px}}
.signal-box{{padding:12px 16px;border-radius:8px;margin:8px 0;border-left:4px solid}}
.signal-buy{{background:#064e3b22;border-color:#22c55e;color:#86efac}}
.signal-sell{{background:#7f1d1d22;border-color:#ef4444;color:#fca5a5}}
.signal-hold{{background:#42200622;border-color:#fbbf24;color:#fde68a}}
.signal-watch{{background:#1e3b5a22;border-color:#38bdf8;color:#bae6fd}}
.chart-frame{{background:#0f172a;border-radius:8px;padding:4px;margin:18px 0}}
.advice-box{{background:linear-gradient(135deg,#1e293b,#0f172a);border:1px solid #334155;border-radius:12px;padding:22px;margin:20px 0}}
.advice-title{{font-size:14pt;font-weight:700;color:#fbbf24;margin-bottom:14px}}
.advice-item{{padding:8px 0;border-bottom:1px solid #1e293b}}
.advice-item:last-child{{border:none}}
.summary-grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}
.risk-meter{{background:#0f172a;border-radius:8px;padding:12px;text-align:center}}
.risk-bar{{height:8px;border-radius:4px;margin-top:8px;background:linear-gradient(90deg,#22c55e,#fbbf24,#ef4444)}}
.risk-fill{{height:8px;border-radius:4px;background:#1e293b}}
.footer{{text-align:center;color:#475569;font-size:8pt;margin-top:36px;padding-top:14px;border-top:1px solid #1e293b}}

@media (max-width:768px){{.row{{flex-direction:column}} .summary-grid{{grid-template-columns:1fr}}}}
</style>
</head>
<body>
<div class="container">
<h1>江丰电子 (300666) 缠论日线分析报告</h1>
<p class="sub">数据: 2026-01-05 ~ {last_date.strftime('%Y-%m-%d')} (138根日K线) | 缠论引擎: czsc v0.10.12 | 生成: 2026-08-06</p>

<!-- K线图 -->
<h2>一、K线图 — 笔+中枢叠加</h2>
<div class="chart-frame">
<iframe src="chan_300666_chart.html" width="100%" height="920" style="border:none;border-radius:6px"></iframe>
</div>
<p style="color:#94a3b8;font-size:8pt;margin-top:-12px">
🔴 红线=上涨笔 | 🟢 绿线=下跌笔 | 🔺 绿三角=底分型(买) | 🔻 红三角=顶分型(卖) | 蓝虚线框=中枢 | 黄虚线=当前中枢上下沿
</p>

<!-- 状态总览 -->
<h2>二、数据总览</h2>
<div class="status-grid">
<div class="stat"><div class="stat-num">{len(df)}</div><div class="stat-label">K线数量</div></div>
<div class="stat"><div class="stat-num">{len(all_bis)}</div><div class="stat-label">完成笔数</div></div>
<div class="stat"><div class="stat-num">{len(zs_list)}</div><div class="stat-label">识别中枢</div></div>
<div class="stat"><div class="stat-num">{len(cz.fx_list)}</div><div class="stat-label">分型数量</div></div>
<div class="stat"><div class="stat-num">{last_close:.2f}</div><div class="stat-label">最新收盘价</div></div>
<div class="stat"><div class="stat-num">{int(df['amount'].tail(5).mean()/1e8)}亿</div><div class="stat-label">近5日均成交</div></div>
</div>

<!-- 当前状态 -->
<h2>三、当前走势状态</h2>
<div class="card">
"""

# 笔结构
if all_bis:
    lb = all_bis[-1]
    d = '上涨' if lb.direction == Direction.Up else '下跌'
    html += f"<p><strong>最新完成笔</strong>: {d}笔 ({lb.fx_a.dt.strftime('%m-%d')} → {lb.edt.strftime('%m-%d')})</p>"
    html += f"<p style='margin-left:16px;color:#94a3b8'>幅度 {lb.change:+.1%} | 力量 {lb.power:.1f} | 斜率 {lb.slope:.2f} | SNR {lb.SNR:.1f}</p>"

if current_zs:
    z = current_zs
    html += f"<p style='margin-top:10px'><strong>当前中枢</strong>: [{z['zd']:.2f} ~ {z['zg']:.2f}] ({z['start_dt'].strftime('%m-%d')} ~ {z['end_dt'].strftime('%m-%d')})</p>"
    if last_close > z['zg']:
        pos_html = f"<span class='tag tag-buy'>中枢上方（偏强）</span>"
    elif last_close < z['zd']:
        pos_html = f"<span class='tag tag-sell'>中枢下方（偏弱）</span>"
    else:
        pos_html = f"<span class='tag tag-hold'>中枢内部（震荡）</span>"
    html += f"<p style='margin-left:16px'>当前价 {last_close:.2f} {pos_html}</p>"

html += "</div>\n"

# 交易建议
html += "<h2>四、缠论交易建议</h2>\n"
html += "<div class='advice-box'>\n"
html += "<div class='advice-title'>🎯 综合研判与操作建议</div>\n"

for a in advice:
    html += f"<div class='advice-item'>{a}</div>\n"
html += "</div>\n"

# 信号分类
html += "<div class='row'>\n"
for key, title, cls, emoji in [
    ('buy', '买入信号', 'buy', '🟢'),
    ('sell', '卖出/减仓信号', 'sell', '🔴'),
    ('hold', '持有信号', 'hold', '🟡'),
    ('watch', '观望/关注', 'watch', '🔵'),
]:
    html += f"<div class='col'><h3>{emoji} {title}</h3>\n"
    if signals[key]:
        for s in signals[key]:
            html += f"<div class='signal-box signal-{cls}'>{s}</div>\n"
    else:
        html += f"<div class='signal-box signal-{cls}' style='opacity:0.5'>暂无</div>\n"
    html += "</div>\n"
html += "</div>\n"

# 笔列表
html += "<h2>五、笔详细列表</h2>\n<div class='card'><table>\n"
html += "<tr><th>#</th><th>方向</th><th>起始</th><th>结束</th><th>幅度</th><th>力量</th><th>斜率</th><th>SNR</th></tr>\n"
for i, bi in enumerate(all_bis):
    d = '上涨' if bi.direction == Direction.Up else '下跌'
    cls = 'up' if bi.direction == Direction.Up else 'down'
    html += f"<tr><td>{i+1}</td><td class='{cls}'>{d}</td>"
    html += f"<td>{bi.fx_a.dt.strftime('%m-%d')}</td><td>{bi.edt.strftime('%m-%d')}</td>"
    html += f"<td class='{cls}'>{bi.change:+.1%}</td><td>{bi.power:.1f}</td><td>{bi.slope:.2f}</td><td>{bi.SNR:.1f}</td></tr>\n"
html += "</table></div>\n"

# 中枢列表
html += "<h2>六、中枢列表</h2>\n<div class='card'><table>\n"
html += "<tr><th>#</th><th>区间</th><th>Zd(下沿)</th><th>Zg(上沿)</th><th>中轴</th><th>宽度</th></tr>\n"
for z in zs_list:
    w = z['zg'] - z['zd']
    html += f"<tr><td>{zs_list.index(z)+1}</td><td>{z['start_dt'].strftime('%m-%d')}~{z['end_dt'].strftime('%m-%d')}</td>"
    html += f"<td>{z['zd']:.2f}</td><td>{z['zg']:.2f}</td><td>{z['zz']:.2f}</td><td>{w:.2f} ({w/z['zz']*100:.1f}%)</td></tr>\n"
html += "</table></div>\n"

# 仓位参考
html += "<h2>七、仓位参考与风险提示</h2>\n"
html += "<div class='row'>\n"
html += "<div class='col'><div class='card'>\n"
html += "<h3>仓位建议</h3>\n"

# 根据位置和信号判断仓位
position_score = 0
if current_zs:
    if last_close > current_zs['zg']:
        position_score += 2  # 中枢上方偏强
    elif last_close < current_zs['zd']:
        position_score -= 2  # 中枢下方偏弱
# 检查最新笔
if all_bis:
    lb = all_bis[-1]
    if lb.direction == Direction.Up:
        position_score += 1
    else:
        position_score -= 1
# 检查是否有底分型
recent_d_bottom = any(repr(fx.mark)=='Mark.D' and fx.dt >= pd.Timestamp('2026-08-01')
                      for fx in cz.fx_list)
if recent_d_bottom:
    position_score += 1

if position_score >= 3:
    pos_advice = '偏激进（6-8成仓位）'
    pos_detail = '中枢上方+上涨笔+底分型确认，可适度加仓'
elif position_score >= 1:
    pos_advice = '中性偏多（4-6成仓位）'
    pos_detail = '趋势偏强但需确认，分批建仓'
elif position_score >= -1:
    pos_advice = '中性谨慎（3-4成仓位）'
    pos_detail = '方向不明，轻仓观望'
elif position_score >= -3:
    pos_advice = '偏防御（1-3成仓位）'
    pos_detail = '中枢下方+下跌笔，等待企稳信号'
else:
    pos_advice = '防御（0-1成仓位/空仓）'
    pos_detail = '多重空头信号共振，建议等待右侧确认'

html += f"<p style='font-size:18pt;font-weight:800;color:#fbbf24'>{pos_advice}</p>\n"
html += f"<p style='color:#94a3b8;margin-top:6px'>{pos_detail}</p>\n"
html += "</div></div>\n"

html += "<div class='col'><div class='card'>\n"
html += "<h3>关键价位</h3>\n"
html += "<table><tr><th>类型</th><th>价格</th><th>说明</th></tr>\n"
if current_zs:
    html += f"<tr><td>中枢上沿</td><td class='up'>{current_zs['zg']:.2f}</td><td>突破确认后可加仓</td></tr>\n"
    html += f"<tr><td>中枢下沿</td><td class='down'>{current_zs['zd']:.2f}</td><td>跌破需警惕三卖</td></tr>\n"
    html += f"<tr><td>中轴</td><td>{current_zs['zz']:.2f}</td><td>多空平衡位</td></tr>\n"
html += f"<tr><td>当前价</td><td style='font-weight:800'>{last_close:.2f}</td><td>{last_date.strftime('%m-%d')} 收盘</td></tr>\n"
# 支撑阻力
recent_high = float(plot_df['high'].tail(20).max())
recent_low = float(plot_df['low'].tail(20).min())
html += f"<tr><td>近期高点</td><td class='up'>{recent_high:.2f}</td><td>20日阻力</td></tr>\n"
html += f"<tr><td>近期低点</td><td class='down'>{recent_low:.2f}</td><td>20日支撑</td></tr>\n"
html += "</table>\n"
html += "</div></div>\n"
html += "</div>\n"

# 风险提示
html += "<div class='card' style='margin-top:18px'>\n"
html += "<h3 style='color:#fbbf24'>⚠️ 风险提示</h3>\n"
risk_items = [
    "缠论分析基于历史K线形态，未来走势受政策、资金、情绪等多因素影响，不保证预测准确",
    "当前中枢 [183.83~222.22] 宽度18.9%，震荡空间大，止损需留足空间",
    "若跌破中枢下沿 183.83 且无底分型支撑，应考虑止损离场",
    "本报告仅用于技术分析研究，不构成任何投资建议",
]
for r in risk_items:
    html += f"<p style='margin:4px 0;color:#94a3b8;font-size:9pt'>• {r}</p>\n"
html += "</div>\n"

html += """
<div class="footer">
缠论分析引擎: czsc (缠中说禅) v0.10.12 · 数据: Tushare Pro<br>
技术分析工具，不构成投资建议 · 2026-08-06
</div>
</div>
</body>
</html>"""

report_path = 'data/chan_300666_full_report.html'
with open(report_path, 'w', encoding='utf-8') as f:
    f.write(html)

print(f"\n完整报告已保存: {report_path}")
print("DONE")
