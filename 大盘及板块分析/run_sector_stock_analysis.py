"""
科技板块+个股综合排名 — 主编排器
================================
输出HTML报告: 大盘及板块分析/科技板块个股排名报告.html
"""
import sys, os, json, time
sys.path.insert(0, '.')
from datetime import datetime
from sector_stock_ranking import (get_tech_sectors_from_stocks,
    comprehensive_stock_ranking)

DATE = datetime.now().strftime('%Y%m%d')
OUTPUT = '大盘及板块分析/科技板块个股排名报告.html'

print(f'{"="*60}')
print(f'  科技板块+个股综合排名 — {DATE}')
print(f'{"="*60}')

# ═══════════ 1+2. 个股排名 → 板块聚合 ═══════════
print('\n[1/2] 个股综合排名 + 板块聚合...')
stocks = comprehensive_stock_ranking('data/screen_v4_round2.csv', 20)
tech_sectors = get_tech_sectors_from_stocks(stocks)
print(f'  科技板块: {len(tech_sectors)} 个')
for i, s in enumerate(tech_sectors[:10]):
    print(f'  {i+1}. {s["name"]}({s["count"]}只): 均涨{s["avg_chg"]:+.2f}% MF{s["avg_mf"]:.0f} VPA{s["avg_vpa"]:.0f} Tech{s["avg_tech"]:.0f} 综合{s["score"]:.0f}分')
print(f'\nTop 20 综合排名:')
print(f'{"代码":<8} {"名称":<8} {"收盘":>7} {"10日":>7} {"资金流":>5} {"VPA":>5} {"技术":>5} {"波动":>5} {"趋势":>5} {"综合":>5}')
print('-' * 75)
for s in stocks:
    print(f'{s["code"]:<8} {s["name"]:<8} {s["close"]:>7.2f} {s["chg_10d"]:>+7.2f}% '
          f'{s["mf_score"]["score"]:>5.0f} {s["vpa_score"]["score"]:>5.0f} {s["tech_score"]["score"]:>5.0f} '
          f'{s["vol_score"]["score"]:>5.0f} {s["trend_score"]:>5.0f} {s["composite"]:>5.1f}')

# ═══════════ 3. HTML报告 ═══════════
print('\n[2/2] 生成HTML报告...')

# Build HTML
stock_rows = ''
for i, s in enumerate(stocks):
    mf = s['mf_score']; vpa = s['vpa_score']; tech = s['tech_score']; vol = s['vol_score']
    stock_rows += f'''<tr>
        <td>{i+1}</td><td>{s['code']}</td><td>{s['name']}</td><td>{s['industry']}</td>
        <td>{s['close']:.2f}</td>
        <td style="color:{'#00e676' if s['chg_10d']>=0 else '#ff5252'}">{s['chg_10d']:+.2f}%</td>
        <td><span style="color:{'#00e676' if mf['score']>=60 else '#ffd740'}">{mf['score']:.0f}</span><br><small>{mf['detail']}</small></td>
        <td><span style="color:{'#00e676' if vpa['score']>=60 else '#ffd740'}">{vpa['score']:.0f}</span><br><small>{vpa['detail'][:40]}</small></td>
        <td><span style="color:{'#00e676' if tech['score']>=60 else '#ffd740'}">{tech['score']:.0f}</span><br><small>{tech['detail']}</small></td>
        <td><span style="color:{'#00e676' if vol['score']>=60 else '#ff5252'}">{vol['score']:.0f}</span><br><small>{vol['detail']}</small></td>
        <td>{s['trend_score']:.0f}</td>
        <td style="font-weight:bold;font-size:16px;color:{'#00e676' if s['composite']>=60 else '#ffd740'}">{s['composite']:.1f}</td>
    </tr>'''

sector_rows = ''
for i, s in enumerate(tech_sectors[:15]):
    c = '#00e676' if s['avg_chg'] >= 0 else '#ff5252'
    sector_rows += f'''<tr>
        <td>{i+1}</td><td>{s['name']}</td><td>{s['count']}</td>
        <td style="color:{c}">{s['avg_chg']:+.2f}%</td>
        <td>{s['avg_mf']:.0f}</td><td>{s['avg_vpa']:.0f}</td><td>{s['avg_tech']:.0f}</td>
        <td style="font-weight:bold;color:{'#00e676' if s['score']>=60 else '#ffd740'}">{s['score']:.0f}</td>
    </tr>'''

html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>科技板块个股综合排名</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0d1117;color:#c9d1d9;padding:20px}}
.container{{max-width:1400px;margin:0 auto}}
.header{{text-align:center;padding:20px 0;border-bottom:1px solid #21262d;margin-bottom:24px}}
.header h1{{font-size:22px;margin-bottom:6px}}
.header .date{{color:#8b949e;font-size:13px}}
.section-title{{font-size:17px;font-weight:bold;margin:24px 0 12px;padding-bottom:6px;border-bottom:1px solid #21262d}}
.section-note{{font-size:12px;color:#8b949e;margin-bottom:12px}}
table{{width:100%;border-collapse:collapse;font-size:13px;margin-bottom:20px}}
th{{text-align:left;padding:8px 10px;background:#161b22;color:#58a6ff;border-bottom:2px solid #21262d;font-weight:600;position:sticky;top:0}}
td{{padding:8px 10px;border-bottom:1px solid #1a1a2e}}
tr:hover td{{background:#161b22}}
small{{color:#8b949e;font-size:11px}}
.score-box{{display:inline-block;padding:2px 8px;border-radius:10px;font-weight:bold;font-size:12px}}
.footer{{text-align:center;color:#484f58;font-size:11px;margin-top:30px;padding-top:16px;border-top:1px solid #21262d}}
</style>
</head>
<body>
<div class="container">
<div class="header">
    <h1>科技板块+个股综合排名分析</h1>
    <div class="date">日期: {DATE} | 维度: 资金流(25%) + 威科夫VPA(20%) + 技术形态(20%) + 波动率(15%) + 趋势(15%) + Round2增长质量(5%)</div>
</div>

<div class="section-title">科技板块排名 (基于个股聚合)</div>
<div class="section-note">评分: 均涨跌(30%) + 均资金流(25%) + 均VPA(20%) + 均技术(15%) + 标的数(10%) | 从个股VPA+资金流+技术+波动聚合</div>
<table>
    <tr><th>排名</th><th>板块</th><th>标的数</th><th>均涨跌</th><th>均资金流</th><th>均VPA</th><th>均技术</th><th>综合评分</th></tr>
    {sector_rows}
</table>

<div class="section-title">Top 20 科技个股综合排名</div>
<div class="section-note">维度: 资金流(近10日主力流向) | 威科夫VPA(阶段+信号) | 技术形态(MA/MACD/RSI/布林) | 波动率(年化波幅) | 趋势(10日涨跌) | Round2(增长质量)</div>
<table>
    <tr><th>排名</th><th>代码</th><th>名称</th><th>行业</th><th>收盘</th><th>10日涨跌</th><th>资金流</th><th>VPA量价</th><th>技术</th><th>波动</th><th>趋势</th><th>综合</th></tr>
    {stock_rows}
</table>

<div class="footer">
    数据来源: Tushare(K线/资金流) + Eastmoney(板块) + 威科夫VPA引擎 | TG-trading-sys 大盘及板块分析
</div>
</div>
</body>
</html>'''

os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
with open(OUTPUT, 'w', encoding='utf-8') as f:
    f.write(html)
print(f'\n报告: {OUTPUT} ({os.path.getsize(OUTPUT)/1024:.0f} KB)')
print('完成!')
