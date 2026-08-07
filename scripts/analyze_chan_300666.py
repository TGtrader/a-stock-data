#!/usr/bin/env python3
"""江丰电子(300666) 日线级别缠论全分析 — 走势/中枢/背离/买卖点"""
import sys, os, json
sys.path.insert(0, '.')

import pandas as pd
import tushare as ts
from czsc import CZSC, Freq, RawBar, Direction
from TG_trading_sys.core.config import Config

# ── 1. 数据获取 ──────────────────────────────────────────
ts.set_token(Config.get_tushare_token())
pro = ts.pro_api()
df = pro.daily(ts_code='300666.SZ', start_date='20260101', end_date='20260806',
               fields='trade_date,open,high,low,close,vol,amount')
df = df.sort_values('trade_date').reset_index(drop=True)
df.rename(columns={'trade_date': 'dt', 'vol': 'volume'}, inplace=True)
print(f"获取 {len(df)} 根日K线 ({df['dt'].iloc[0]} ~ {df['dt'].iloc[-1]})")

# ── 2. 构造 RawBar ───────────────────────────────────────
bars = [RawBar(symbol='300666', dt=pd.Timestamp(str(r['dt'])),
               open=float(r['open']), high=float(r['high']),
               low=float(r['low']), close=float(r['close']),
               vol=float(r['volume']), amount=float(r['amount']),
               freq=Freq.D) for _, r in df.iterrows()]

# ── 3. 缠论分析 ───────────────────────────────────────────
cz = CZSC(bars, max_bi_num=50)

# ── 4. 中枢计算（三笔重叠区间） ─────────────────────────
def compute_zs(bis):
    """从中查找中枢：连续3笔有重叠区间"""
    zs_list = []
    i = 0
    while i < len(bis) - 2:
        b1, b2, b3 = bis[i], bis[i+1], bis[i+2]
        # 重叠区间 = [max(三笔低点), min(三笔高点)]
        zs_low = max(b1.low, b2.low, b3.low)
        zs_high = min(b1.high, b2.high, b3.high)
        if zs_low < zs_high:  # 有重叠
            zs_list.append({
                'idx': len(zs_list)+1,
                'start_dt': str(b1.fx_a.dt)[:10],
                'end_dt': str(b3.edt)[:10],
                'zd': round(zs_low, 2),   # 中枢低
                'zg': round(zs_high, 2),  # 中枢高
                'zz': round((zs_low+zs_high)/2, 2),
                'bi_range': f"笔{i+1}~笔{i+3}",
            })
        i += 1
    return zs_list

# ── 5. 背离检测 ───────────────────────────────────────────
def detect_divergence(bis, zs_list):
    """检测笔背离：同方向两笔，价格新高/低但力量衰减"""
    divs = []
    up_bis = [b for b in bis if b.direction == Direction.Up]
    dn_bis = [b for b in bis if b.direction == Direction.Down]

    # 顶背离：上涨笔中，价格创新高但power衰减
    for i in range(1, len(up_bis)):
        prev, cur = up_bis[i-1], up_bis[i]
        if cur.high > prev.high and cur.power < prev.power * 0.85:
            divs.append({
                'type': '顶背离',
                'date': str(cur.edt)[:10],
                'detail': f"价格新高 {cur.high:.2f}>{prev.high:.2f} 但力量衰减 {cur.power:.1f}<{prev.power:.1f}",
            })

    # 底背离：下跌笔中，价格创新低但power衰减
    for i in range(1, len(dn_bis)):
        prev, cur = dn_bis[i-1], dn_bis[i]
        if cur.low < prev.low and cur.power < prev.power * 0.85:
            divs.append({
                'type': '底背离',
                'date': str(cur.edt)[:10],
                'detail': f"价格新低 {cur.low:.2f}<{prev.low:.2f} 但力量衰减 {cur.power:.1f}<{prev.power:.1f}",
            })

    return divs

# ── 执行分析 ──────────────────────────────────────────────
all_bis = list(cz.finished_bis)
zs_list = compute_zs(all_bis)
div_list = detect_divergence(all_bis, zs_list)

print(f"K线: {len(cz.bars_raw)} | 分型: {len(cz.fx_list)} | 笔: {len(all_bis)} | 中枢: {len(zs_list)} | 背离: {len(div_list)}")

# ── 买卖点（分型标记） ────────────────────────────────────
buy_points = []   # 底分型 → 买点
sell_points = []  # 顶分型 → 卖点
for fx in cz.fx_list:
    if repr(fx.mark) == 'Mark.D':  # 底分型 = 潜在买点
        buy_points.append({'date': str(fx.dt)[:10], 'price': round(fx.low, 2)})
    elif repr(fx.mark) == 'Mark.G':  # 顶分型 = 潜在卖点
        sell_points.append({'date': str(fx.dt)[:10], 'price': round(fx.high, 2)})

buy_points = buy_points[-10:]   # 最近10个
sell_points = sell_points[-10:]

# ── 最新状态 ──────────────────────────────────────────────
last_close = float(df['close'].iloc[-1])
last_date = str(df['dt'].iloc[-1])[:10]

status_lines = []
if all_bis:
    lb = all_bis[-1]
    d = '上涨' if lb.direction == Direction.Up else '下跌'
    status_lines.append(f"最新完成笔: {d}笔 ({str(lb.fx_a.dt)[:10]} → {str(lb.edt)[:10]})")
    status_lines.append(f"  幅度: {lb.change:.1%} | 力量: {lb.power:.1f} | 斜率: {lb.slope:.2f}")

if zs_list:
    z = zs_list[-1]
    status_lines.append(f"最近中枢: [{z['zd']} ~ {z['zg']}] ({z['start_dt']} ~ {z['end_dt']})")
    if last_close > z['zg']:
        status_lines.append(f"当前价 {last_close:.2f} → 中枢上方（偏强）")
    elif last_close < z['zd']:
        status_lines.append(f"当前价 {last_close:.2f} → 中枢下方（偏弱）")
    else:
        status_lines.append(f"当前价 {last_close:.2f} → 中枢内部（震荡）")

# ── 6. 生成HTML报告 ───────────────────────────────────────
os.makedirs('data', exist_ok=True)

# 价格序列（用于手工图）
prices = [float(r['close']) for _, r in df.iterrows()]
dates = [str(r['dt'])[:10] for _, r in df.iterrows()]

html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>江丰电子(300666) 缠论日线分析</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:"Microsoft YaHei","SimHei",sans-serif;background:#0f172a;color:#e2e8f0;padding:20px}}
.container{{max-width:1100px;margin:0 auto}}
h1{{text-align:center;font-size:20pt;color:#38bdf8;margin-bottom:4px}}
.sub{{text-align:center;color:#94a3b8;font-size:9pt;margin-bottom:24px}}
h2{{font-size:14pt;color:#38bdf8;margin:24px 0 12px;padding-left:10px;border-left:3px solid #0ea5e9}}
.card{{background:#1e293b;border-radius:10px;padding:16px 20px;margin-bottom:16px;border:1px solid #334155}}
.row{{display:flex;gap:16px;flex-wrap:wrap}}
.col{{flex:1;min-width:300px}}
table{{width:100%;border-collapse:collapse;font-size:9pt;margin:8px 0}}
th{{background:#0f172a;color:#38bdf8;padding:6px 10px;text-align:center;font-weight:600;border-bottom:2px solid #1e3b5a}}
td{{padding:5px 10px;text-align:center;border-bottom:1px solid #1e293b}}
tr:hover td{{background:#1e3b5a}}
.up{{color:#22c55e;font-weight:700}}
.down{{color:#ef4444;font-weight:700}}
.tag{{display:inline-block;padding:2px 8px;border-radius:4px;font-size:8pt;font-weight:700}}
.tag-buy{{background:#064e3b;color:#22c55e}}
.tag-sell{{background:#7f1d1d;color:#ef4444}}
.tag-warn{{background:#78350f;color:#fbbf24}}
.tag-info{{background:#1e3b5a;color:#38bdf8}}
.tag-div{{background:#4a044e;color:#e879f9}}
.status-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}}
.stat{{background:#0f172a;border-radius:8px;padding:12px;text-align:center}}
.stat-num{{font-size:22pt;font-weight:800;color:#38bdf8}}
.stat-label{{font-size:8pt;color:#94a3b8;margin-top:2px}}
.chart-box{{background:#0f172a;border-radius:8px;padding:12px;margin:16px 0;text-align:center}}
.flow{{font-family:Consolas,monospace;font-size:8pt;background:#0f172a;padding:10px 16px;border-radius:6px;line-height:1.5;white-space:pre;overflow-x:auto}}
.footer{{text-align:center;color:#475569;font-size:8pt;margin-top:32px;padding-top:12px;border-top:1px solid #1e293b}}
</style>
</head>
<body>
<div class="container">
<h1>江丰电子 (300666) — 缠论日线分析</h1>
<p class="sub">数据区间: {dates[0]} ~ {dates[-1]} ({len(df)}根K线) | 分析日期: 2026-08-06 | 缠论引擎: czsc v0.10.12</p>

<!-- 总览卡片 -->
<div class="status-grid">
<div class="stat"><div class="stat-num">{len(cz.bars_raw)}</div><div class="stat-label">K线数量</div></div>
<div class="stat"><div class="stat-num">{len(all_bis)}</div><div class="stat-label">完成笔数</div></div>
<div class="stat"><div class="stat-num">{len(zs_list)}</div><div class="stat-label">识别中枢</div></div>
<div class="stat"><div class="stat-num">{len(div_list)}</div><div class="stat-label">背离信号</div></div>
<div class="stat"><div class="stat-num">{len(cz.fx_list)}</div><div class="stat-label">分型数量</div></div>
<div class="stat"><div class="stat-num">{last_close:.2f}</div><div class="stat-label">最新收盘价</div></div>
</div>

<!-- 当前状态 -->
<h2>一、当前走势状态</h2>
<div class="card">
"""
for s in status_lines:
    html += f"<p style='margin:4px 0'>{s}</p>\n"
html += "</div>\n"

# 笔列表
html += "<h2>二、笔分析（完成笔列表）</h2>\n<div class='card'><table>\n"
html += "<tr><th>#</th><th>方向</th><th>起始分型日期</th><th>结束日期</th><th>幅度</th><th>力量(power)</th><th>斜率</th><th>SNR</th></tr>\n"
for i, bi in enumerate(all_bis):
    d = '上涨' if bi.direction == Direction.Up else '下跌'
    cls = 'up' if bi.direction == Direction.Up else 'down'
    html += f"<tr><td>{i+1}</td><td class='{cls}'>{d}</td>"
    html += f"<td>{str(bi.fx_a.dt)[:10]}</td><td>{str(bi.edt)[:10]}</td>"
    html += f"<td class='{cls}'>{bi.change:+.1%}</td>"
    html += f"<td>{bi.power:.1f}</td><td>{bi.slope:.2f}</td><td>{bi.SNR:.1f}</td></tr>\n"
html += "</table></div>\n"

# 中枢列表
html += "<h2>三、中枢分析</h2>\n<div class='card'>\n"
if zs_list:
    html += "<table><tr><th>#</th><th>时间区间</th><th>中枢低(Zd)</th><th>中枢高(Zg)</th><th>中轴(Zz)</th><th>宽度</th><th>涉及笔</th></tr>\n"
    for z in zs_list:
        width = z['zg'] - z['zd']
        pct = width / z['zz'] * 100
        html += f"<tr><td>{z['idx']}</td><td>{z['start_dt']} ~ {z['end_dt']}</td>"
        html += f"<td>{z['zd']}</td><td>{z['zg']}</td><td>{z['zz']}</td>"
        html += f"<td>{width:.2f} ({pct:.1f}%)</td><td>{z['bi_range']}</td></tr>\n"
    html += "</table>\n"
else:
    html += "<p style='color:#94a3b8'>未检测到标准中枢（需要连续3笔重叠）</p>\n"
html += "</div>\n"

# 背离信号
html += "<h2>四、背离信号</h2>\n<div class='card'>\n"
if div_list:
    html += "<table><tr><th>类型</th><th>触发日期</th><th>详情</th></tr>\n"
    for dv in div_list:
        tag = 'tag-sell' if '顶' in dv['type'] else 'tag-buy'
        html += f"<tr><td><span class='tag {tag}'>{dv['type']}</span></td>"
        html += f"<td>{dv['date']}</td><td style='text-align:left'>{dv['detail']}</td></tr>\n"
    html += "</table>\n"
else:
    html += "<p style='color:#94a3b8'>近150日未检测到明显背离信号</p>\n"
html += "</div>\n"

# 买卖点（分型标记）
html += "<h2>五、买卖点信号（分型标记）</h2>\n<div class='card'>\n"
html += "<div class='row'>\n"
html += "<div class='col'><h3 style='color:#22c55e;margin-bottom:8px'>🟢 底分型（潜在买点）</h3><table><tr><th>日期</th><th>价格</th></tr>\n"
for bp in buy_points:
    html += f"<tr><td>{bp['date']}</td><td>{bp['price']}</td></tr>\n"
html += "</table></div>\n"
html += "<div class='col'><h3 style='color:#ef4444;margin-bottom:8px'>🔴 顶分型（潜在卖点）</h3><table><tr><th>日期</th><th>价格</th></tr>\n"
for sp in sell_points:
    html += f"<tr><td>{sp['date']}</td><td>{sp['price']}</td></tr>\n"
html += "</table></div>\n</div>\n</div>\n"

# 价格走势简图（文本）
html += "<h2>六、价格走势概览</h2>\n<div class='card'>\n"
html += "<p style='margin-bottom:8px;color:#94a3b8'>收盘价范围: {:.2f} ~ {:.2f}</p>\n".format(min(prices), max(prices))
html += "<div class='flow'>\n"
# Simple ASCII-ish chart
price_min, price_max = min(prices), max(prices)
for i in range(0, len(dates), 3):
    p = prices[i]
    bar_len = int((p - price_min) / (price_max - price_min) * 40) if price_max > price_min else 20
    color = '#22c55e' if (i > 0 and p >= prices[i-1]) else '#ef4444'
    html += f"<span style='color:#64748b'>{dates[i]}</span> <span style='color:{color}'>"
    html += "█" * bar_len + f" {p:.2f}</span>\n"
html += "</div></div>\n"

html += """
<div class="footer">
本报告由 czsc (缠中说禅技术分析工具 v0.10.12) 自动生成 · 数据来源: Tushare Pro<br>
仅用于技术分析研究，不构成任何投资建议 · 生成日期: 2026-08-06
</div>
</div>
</body>
</html>"""

report_path = 'data/chan_300666_daily.html'
with open(report_path, 'w', encoding='utf-8') as f:
    f.write(html)
print(f"HTML报告已保存: {report_path}")

# ── 同时尝试 czsc 自带图表 ──────────────────────────────
try:
    cz.to_plotly('data/chan_300666_plotly.html')
    print(f"Plotly图表已保存: data/chan_300666_plotly.html")
except Exception as e:
    print(f"Plotly图表生成失败: {e}")

print("\nDONE")
