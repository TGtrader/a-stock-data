"""
全链路重跑: 从全市场筛选到深度分析
覆盖: Phase 1(行业筛选) → Phase 2(估值初筛) → Phase 3(技术深筛) → Phase 4(申万分类)
"""
import sys, os, io, time
os.environ['PYTHONIOENCODING'] = 'utf-8'
sys.path.insert(0, '.')
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from TG_trading_sys.core.config import Config
import tushare as ts
import pandas as pd
import numpy as np
from datetime import datetime

token = Config.get_tushare_token()
ts.set_token(token)
api = ts.pro_api()

DATE = '20260728'
print(f'{"="*80}')
print(f'  全链路重跑 — 日期: {DATE}')
print(f'{"="*80}')

# ═══════════════════════════════════════════════
# Phase 1: 全市场 → 科技板块
# ═══════════════════════════════════════════════
print('\n[Phase 1] 全市场行业筛选...')
stocks = api.stock_basic(exchange='', list_status='L',
                         fields='ts_code,symbol,name,area,industry,list_date')
print(f'  全市场: {len(stocks)} 只')

TECH_INDUSTRIES = [
    '半导体', '软件服务', '通信设备', 'IT设备', '互联网',
    '元器件', '电气设备', '专用机械', '电器仪表',
    '医疗保健', '生物制药', '化学制药', '航空',
]
tech_stocks = stocks[stocks['industry'].isin(TECH_INDUSTRIES)].copy()
print(f'  科技板块: {len(tech_stocks)} 只')

# ═══════════════════════════════════════════════
# Phase 2: 批量获取估值 + 初筛
# ═══════════════════════════════════════════════
print('\n[Phase 2] 估值初筛...')
daily = api.daily_basic(trade_date=DATE,
                        fields='ts_code,trade_date,close,pe,pe_ttm,pb,total_mv,circ_mv,turnover_rate,volume_ratio')
print(f'  daily_basic: {len(daily)} 条')

tech_daily = tech_stocks.merge(daily, on='ts_code', how='inner')
for col in ['pe_ttm','pb','total_mv','turnover_rate','close']:
    tech_daily[col] = pd.to_numeric(tech_daily[col], errors='coerce')

valid = tech_daily[
    (tech_daily['pe_ttm'] > 0) & (tech_daily['pe_ttm'] < 500) &
    (tech_daily['pb'] > 0) & (tech_daily['pb'] < 50) &
    (tech_daily['total_mv'] > 100000) &
    (tech_daily['close'] > 3)
].copy()
print(f'  有效标的: {len(valid)} 只')

# 行业中性化
valid['pe_rank'] = valid.groupby('industry')['pe_ttm'].rank(pct=True)
valid['pb_rank'] = valid.groupby('industry')['pb'].rank(pct=True)
valid['value_score'] = (1 - valid['pe_rank']) * 0.6 + (1 - valid['pb_rank']) * 0.4
valid['liq_score'] = valid['turnover_rate'].clip(0, 10) / 10
valid['mcap_log'] = np.log10(valid['total_mv'])
valid['mcap_score'] = (valid['mcap_log'] - valid['mcap_log'].min()) / (valid['mcap_log'].max() - valid['mcap_log'].min())
valid['composite'] = (
    valid['value_score'] * 0.50 +
    valid['liq_score'] * 0.15 +
    valid['mcap_score'] * 0.10 +
    (1 - valid['pe_rank']) * 0.25
)

# 选候选
top_overall = valid.nlargest(80, 'composite')
industry_picks = []
for ind in TECH_INDUSTRIES:
    ind_stocks = top_overall[top_overall['industry'] == ind].nsmallest(8, 'pe_ttm')
    industry_picks.append(ind_stocks)
final_candidates = pd.concat(industry_picks).drop_duplicates(subset=['ts_code'])
remaining = top_overall[~top_overall['ts_code'].isin(final_candidates['ts_code'])]
final_candidates = pd.concat([final_candidates, remaining]).head(80)
print(f'  初筛候选: {len(final_candidates)} 只')

# ═══════════════════════════════════════════════
# Phase 3: 深度技术分析
# ═══════════════════════════════════════════════
print('\n[Phase 3] 深度技术分析(120日K线)...')
codes = final_candidates['ts_code'].tolist()
all_klines = {}
success_k = 0
for i, ts_code in enumerate(codes):
    try:
        df = api.daily(ts_code=ts_code, start_date='20260101', end_date=DATE)
        if df is not None and len(df) >= 20:
            all_klines[ts_code] = df.sort_values('trade_date')
            success_k += 1
    except Exception:
        pass
    if (i + 1) % 30 == 0:
        print(f'  K线进度: {i+1}/{len(codes)} ({success_k} 成功)')
    time.sleep(0.1)
print(f'  K线获取: {success_k}/{len(codes)} 成功')

# 技术指标
results = []
for _, row in final_candidates.iterrows():
    ts_code = row['ts_code']
    kline = all_klines.get(ts_code)
    if kline is None or len(kline) < 20:
        continue

    closes = pd.to_numeric(kline['close'], errors='coerce')
    volumes = pd.to_numeric(kline['vol'], errors='coerce')

    ret_5d = (closes.iloc[-1] / closes.iloc[-5] - 1) * 100 if len(closes) >= 5 else 0
    ret_20d = (closes.iloc[-1] / closes.iloc[-20] - 1) * 100 if len(closes) >= 20 else 0

    ma20 = closes.rolling(20).mean().iloc[-1]
    ma60 = closes.rolling(60).mean().iloc[-1] if len(closes) >= 60 else ma20
    price_vs_ma20 = (closes.iloc[-1] / ma20 - 1) * 100
    price_vs_ma60 = (closes.iloc[-1] / ma60 - 1) * 100

    high_60 = closes.iloc[-60:].max() if len(closes) >= 60 else closes.max()
    pct_from_high = (closes.iloc[-1] / high_60 - 1) * 100

    delta = closes.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs.fillna(1)))
    rsi_now = rsi.iloc[-1] if not pd.isna(rsi.iloc[-1]) else 50

    avg_vol_20 = volumes.iloc[-20:].mean()
    avg_vol_60 = volumes.iloc[-60:].mean() if len(volumes) >= 60 else avg_vol_20
    vol_ratio = avg_vol_20 / avg_vol_60 if avg_vol_60 > 0 else 1

    # MA score
    if len(closes) >= 60:
        ma5 = closes.rolling(5).mean().iloc[-1]
        ma10 = closes.rolling(10).mean().iloc[-1]
        mas = [ma5, ma10, ma20, ma60]
        bullish = sum(1 for i in range(len(mas)-1) if mas[i] > mas[i+1])
        ma_score = bullish / (len(mas)-1) * 100
    else:
        ma_score = 50

    # Oversold score
    oversold_score = 0
    if rsi_now < 30: oversold_score += 30
    elif rsi_now < 40: oversold_score += 20
    elif rsi_now < 50: oversold_score += 10
    if price_vs_ma20 < -5: oversold_score += 20
    elif price_vs_ma20 < 0: oversold_score += 10
    if pct_from_high < -20: oversold_score += 25
    elif pct_from_high < -10: oversold_score += 15
    elif pct_from_high < -5: oversold_score += 5
    if ret_20d < -10: oversold_score += 15
    elif ret_20d < -5: oversold_score += 10

    vs = row['value_score']
    tech_score = oversold_score / 100
    to = row['turnover_rate']
    composite_final = vs * 0.50 + tech_score * 0.35 + min(to, 10) / 10 * 0.15

    results.append({
        'ts_code': ts_code, 'symbol': row['symbol'], 'name': row['name'],
        'industry': row['industry'],
        'close': row['close'], 'pe_ttm': row['pe_ttm'], 'pb': row['pb'],
        'mcap_yi': row['total_mv'] / 10000, 'turnover': to,
        'ret_5d': round(ret_5d, 1), 'ret_20d': round(ret_20d, 1),
        'price_vs_ma20': round(price_vs_ma20, 1), 'price_vs_ma60': round(price_vs_ma60, 1),
        'pct_from_60h': round(pct_from_high, 1),
        'rsi14': round(rsi_now, 1), 'ma_score': round(ma_score, 1),
        'vol_ratio': round(vol_ratio, 2),
        'value_score': round(vs * 100, 1), 'oversold_score': oversold_score,
        'composite_final': round(composite_final * 100, 1),
    })

df_results = pd.DataFrame(results).sort_values('composite_final', ascending=False)

# Quality grading
df_results['quality'] = 'C'
df_results.loc[(df_results['composite_final'] >= 75) & (df_results['pe_ttm'] < 40) & (df_results['mcap_yi'] > 20), 'quality'] = 'B'
df_results.loc[(df_results['composite_final'] >= 80) & (df_results['pe_ttm'] < 30) & (df_results['mcap_yi'] > 30), 'quality'] = 'A'
df_results.loc[(df_results['composite_final'] >= 85) & (df_results['pe_ttm'] < 20), 'quality'] = 'A+'

# ═══════════════════════════════════════════════
# Output: Phase 4 Final Results
# ═══════════════════════════════════════════════
print(f'\n{"="*100}')
print(f'  最终结果 — 按综合评分排序')
print(f'{"="*100}')
print(f'  {"#":<3} {"评级":<4} {"代码":<8} {"名称":<10} {"行业":<12} {"价格":>7} {"PE":>5} {"PB":>5} {"市值":>7} {"20日":>6} {"RSI":>4} {"超卖":>4} {"价值":>5} {"综合":>5}')
print(f'  {"─"*100}')

a_plus = df_results[df_results['quality'] == 'A+']
a_class = df_results[df_results['quality'] == 'A']

for i, (_, r) in enumerate(df_results.head(30).iterrows()):
    signals = []
    if r['rsi14'] < 30: signals.append('RSI超卖')
    if r['pe_ttm'] < 15: signals.append('低PE')
    if r['ret_20d'] < -20: signals.append('超跌')
    if r['pct_from_60h'] < -30: signals.append('深回撤')
    print(f'  {i+1:<3} {r["quality"]:<4} {r["symbol"]:<8} {r["name"]:<10} {r["industry"]:<12} {r["close"]:>7.2f} {r["pe_ttm"]:>5.1f} {r["pb"]:>5.2f} {r["mcap_yi"]:>5.0f}亿 {r["ret_20d"]:>+5.1f}% {r["rsi14"]:>4.0f} {r["oversold_score"]:>4} {r["value_score"]:>5.1f} {r["composite_final"]:>5.1f}  {', '.join(signals)}')

b_count = len(df_results[df_results['quality'] == 'B'])
rsi_count = len(df_results[df_results['rsi14'] < 30])
drop_count = len(df_results[df_results['ret_20d'] < -20])
print(f'\nA+级: {len(a_plus)} 只 | A级: {len(a_class)} 只 | B级: {b_count} 只')
print(f'RSI<30超卖: {rsi_count} 只 | 20日跌幅>20%: {drop_count} 只')

# Save
df_results.to_csv('data/tech_deep_analysis_v2.csv', index=False, encoding='utf-8-sig')
print(f'\n保存到 data/tech_deep_analysis_v2.csv')

# Print A-class list for deep analysis
a_list = pd.concat([a_plus, a_class]).sort_values('composite_final', ascending=False)
print(f'\n{"="*80}')
print(f'  A/A+ 级精选池 (进入深度分析)')
print(f'{"="*80}')
for _, r in a_list.iterrows():
    print(f'  {r["quality"]} {r["symbol"]} {r["name"]} | {r["industry"]} | PE{r["pe_ttm"]:.1f} | 综合{r["composite_final"]:.1f}')
print(f'\n共 {len(a_list)} 只进入深度分析')
a_list.to_csv('data/tech_a_class_v2.csv', index=False, encoding='utf-8-sig')
