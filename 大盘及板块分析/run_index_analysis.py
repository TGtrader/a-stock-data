"""
大盘综合分析 — 主编排器
=======================
1. 获取7大指数300日日线数据
2. 每个指数做综合技术分析
3. 多角色Agent观点汇总
4. 市场资金流+北向资金
5. 生成HTML仪表盘
"""
import sys, os, json, time
sys.path.insert(0, '.')
from datetime import datetime

from index_data import (INDICES, fetch_all_indices_daily, fetch_market_moneyflow,
                        fetch_northbound, fetch_margin_data,
                        fetch_moneyflow_trend, fetch_margin_trend)
from index_technical import comprehensive_technical
from index_agents import run_all_agents
from index_dashboard import generate_dashboard

DATE = datetime.now().strftime('%Y%m%d')

print(f'{"="*60}')
print(f'  大盘综合分析 — {DATE}')
print(f'{"="*60}')

# ═══════════════════════════════
# 1. 获取数据
# ═══════════════════════════════
print('\n[1/5] 获取指数日线数据...')
index_data = fetch_all_indices_daily(lookback=300)

# ═══════════════════════════════
# 2. 市场资金流
# ═══════════════════════════════
print('\n[2/5] 获取市场资金流+北向资金+两融...')
market_mf = fetch_market_moneyflow()
northbound = fetch_northbound(20)
margin = fetch_margin_data()
mf_trend = fetch_moneyflow_trend(20)
margin_trend = fetch_margin_trend(20)
nb_total_5d = 0
if northbound:
    nb_latest = northbound[-1]
    nb_total_5d = sum(r['total'] for r in northbound[-5:]) if len(northbound) >= 5 else 0
    print(f'  北向资金: 最新{nb_latest["total"]:.1f}亿, 近5日累计{nb_total_5d:.1f}亿')
if market_mf:
    print(f'  市场资金流: 净额{market_mf.get("net_amount",0)/1e8:.1f}亿')
if margin:
    print(f'  两融余额: {margin["total_rzrq"]}亿 (融资{margin["total_rz"]}亿 融券{margin["total_rq"]}亿) 净买入{margin["net_rz"]:.1f}亿')

# ═══════════════════════════════
# 3. 每个指数做技术分析+Agent观点
# ═══════════════════════════════
print('\n[3/5] 技术分析+多角色Agent观点...')
all_data = {}
for ts_code, df in index_data.items():
    info = INDICES.get(ts_code, {})
    name = info.get('name', ts_code)
    print(f'  {name}...')

    tech = comprehensive_technical(df)
    agents = run_all_agents(tech, df, name)

    all_data[ts_code] = {
        'info': info,
        'technical': tech,
        'agents': agents,
        'market_moneyflow': market_mf,
        'northbound': northbound,
    }

# ═══════════════════════════════
# 4. 综合汇总
# ═══════════════════════════════
print('\n[4/5] 综合汇总...')
print(f'\n{"指数":<10} {"收盘":>8} {"10日涨跌":>8} {"位置":>6} {"均线":<10} {"MACD":<6} {"综合评分":>6} {"观点"}')
print('-' * 80)
for ts_code, d in all_data.items():
    tech = d['technical']
    pos = tech.get('position', {})
    trend = tech.get('trend', {})
    agents = d['agents']
    chg = trend.get('10日', {}).get('change_pct', 0)
    print(f'{d["info"]["short"]:<10} {pos.get("close",0):>8.2f} {chg:>+8.2f}% '
          f'{pos.get("verdict",""):>6} {tech.get("ma_alignment",""):<10} '
          f'{tech.get("macd",{}).get("signal",""):<6} '
          f'{agents.get("综合评分",50):>6.0f} {agents.get("综合观点","")}')

# ═══════════════════════════════
# 5. 生成HTML仪表盘
# ═══════════════════════════════
print('\n[5/5] 生成HTML仪表盘...')
output = '大盘及板块分析/大盘分析报告.html'
market_summary = {
    'moneyflow': market_mf,
    'northbound': northbound,
    'nb_5d': nb_total_5d,
    'margin': margin,
    'mf_trend': mf_trend,
    'margin_trend': margin_trend,
}
generate_dashboard(all_data, output, market_summary)

print(f'\n{"="*60}')
print(f'  分析完成!')
print(f'{"="*60}')
