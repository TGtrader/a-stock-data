"""
Phase 3: 深度技术分析 — 对初筛候选标的批量获取K线 + 技术指标
"""
import sys, os, io, time
os.environ['PYTHONIOENCODING'] = 'utf-8'
sys.path.insert(0, '.')
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from TG_trading_sys.core.config import Config
import tushare as ts
import pandas as pd
import numpy as np

token = Config.get_tushare_token()
ts.set_token(token)
api = ts.pro_api()

# Load Phase 1 candidates
candidates = pd.read_csv('data/tech_candidates_phase1.csv')
print(f'加载 {len(candidates)} 只候选标的')

# Fetch 120-day K-line for all candidates
end_date = '20260728'
start_date = '20260101'

codes = candidates['ts_code'].tolist()
print(f'批量获取 {len(codes)} 只标的 K线数据 (120天)...')

all_klines = {}
success = 0
for i, ts_code in enumerate(codes):
    try:
        df = api.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
        if df is not None and len(df) >= 20:
            df = df.sort_values('trade_date')
            all_klines[ts_code] = df
            success += 1
    except Exception:
        pass
    if (i + 1) % 20 == 0:
        print(f'  进度: {i+1}/{len(codes)} ({success} 成功)')
    time.sleep(0.12)

print(f'K线获取完成: {success}/{len(codes)} 成功')

# Technical Analysis
print(f'\n计算技术指标...')
results = []

for _, row in candidates.iterrows():
    ts_code = row['ts_code']
    symbol = row['symbol']
    name = row['name']
    industry = row['industry']
    close_price = row['close']
    pe_ttm = row['pe_ttm']
    pb = row['pb']
    total_mv = row['total_mv']
    turnover = row['turnover_rate']
    value_score = row['value_score']

    kline = all_klines.get(ts_code)
    if kline is None or len(kline) < 20:
        continue

    closes = pd.to_numeric(kline['close'], errors='coerce')
    volumes = pd.to_numeric(kline['vol'], errors='coerce')

    ret_5d = (closes.iloc[-1] / closes.iloc[-5] - 1) * 100 if len(closes) >= 5 else 0
    ret_10d = (closes.iloc[-1] / closes.iloc[-10] - 1) * 100 if len(closes) >= 10 else 0
    ret_20d = (closes.iloc[-1] / closes.iloc[-20] - 1) * 100 if len(closes) >= 20 else 0

    ma20 = closes.rolling(20).mean().iloc[-1]
    ma60 = closes.rolling(60).mean().iloc[-1] if len(closes) >= 60 else ma20
    price_vs_ma20 = (closes.iloc[-1] / ma20 - 1) * 100
    price_vs_ma60 = (closes.iloc[-1] / ma60 - 1) * 100

    high_60 = closes.iloc[-60:].max() if len(closes) >= 60 else closes.max()
    low_60 = closes.iloc[-60:].min() if len(closes) >= 60 else closes.min()
    pct_from_high = (closes.iloc[-1] / high_60 - 1) * 100
    pct_from_low = (closes.iloc[-1] / low_60 - 1) * 100

    avg_vol_20 = volumes.iloc[-20:].mean()
    avg_vol_60 = volumes.iloc[-60:].mean() if len(volumes) >= 60 else avg_vol_20
    vol_ratio = avg_vol_20 / avg_vol_60 if avg_vol_60 > 0 else 1

    delta = closes.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs.fillna(1)))
    rsi_now = rsi.iloc[-1] if not pd.isna(rsi.iloc[-1]) else 50

    if len(closes) >= 60:
        ma5 = closes.rolling(5).mean().iloc[-1]
        ma10 = closes.rolling(10).mean().iloc[-1]
        mas = [ma5, ma10, ma20, ma60]
        bullish_pairs = sum(1 for i in range(len(mas)-1) if mas[i] > mas[i+1])
        ma_score = bullish_pairs / (len(mas)-1) * 100
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

    tech_score = oversold_score / 100
    composite_final = value_score * 0.50 + tech_score * 0.35 + min(turnover, 10) / 10 * 0.15

    results.append({
        'ts_code': ts_code, 'symbol': symbol, 'name': name, 'industry': industry,
        'close': close_price, 'pe_ttm': pe_ttm, 'pb': pb,
        'mcap_yi': total_mv / 10000,
        'turnover': turnover,
        'ret_5d': round(ret_5d, 1), 'ret_10d': round(ret_10d, 1), 'ret_20d': round(ret_20d, 1),
        'price_vs_ma20': round(price_vs_ma20, 1), 'price_vs_ma60': round(price_vs_ma60, 1),
        'pct_from_60h': round(pct_from_high, 1),
        'rsi14': round(rsi_now, 1),
        'ma_score': round(ma_score, 1),
        'vol_ratio': round(vol_ratio, 2),
        'value_score': round(value_score * 100, 1),
        'oversold_score': oversold_score,
        'composite_final': round(composite_final * 100, 1),
    })

df_results = pd.DataFrame(results)
df_results = df_results.sort_values('composite_final', ascending=False)

# Output by industry
print(f'\n{"="*120}')
print(f'  科技成长板块 -- 低估/超跌个股深度筛选结果')
print(f'  日期: 2026-07-28 | 有效分析: {len(df_results)} 只')
print(f'{"="*120}')

for ind in df_results['industry'].unique():
    subset = df_results[df_results['industry'] == ind].head(6)
    if len(subset) == 0:
        continue
    print(f'\n{"─"*120}')
    print(f'  [{ind}]')
    hdr = f'  {"代码":<8} {"名称":<10} {"价格":>7} {"PE":>6} {"PB":>5} {"市值亿":>8} {"5日%":>6} {"20日%":>6} {"vsMA20":>7} {"60高%":>7} {"RSI":>5} {"超卖":>4} {"综合":>5}'
    print(hdr)
    print(f'  {"─"*108}')

    for _, r in subset.iterrows():
        markers = ''
        if r['rsi14'] < 30: markers += ' RSI超卖'
        if r['pct_from_60h'] < -20: markers += ' 深跌'
        if r['pe_ttm'] < 20: markers += ' 低PE'
        if r['ret_20d'] < -10: markers += ' 急跌'

        print(f'  {r["symbol"]:<8} {r["name"]:<10} {r["close"]:>7.2f} {r["pe_ttm"]:>6.1f} {r["pb"]:>5.2f} {r["mcap_yi"]:>8.1f} {r["ret_5d"]:>+5.1f}% {r["ret_20d"]:>+5.1f}% {r["price_vs_ma20"]:>+6.1f}% {r["pct_from_60h"]:>+6.1f}% {r["rsi14"]:>5.0f} {r["oversold_score"]:>4} {r["composite_final"]:>5.1f}{markers}')

# Top overall
print(f'\n\n{"="*120}')
print(f'  TOP 30 综合排名 (价值50% + 超跌信号35% + 流动性15%)')
print(f'{"="*120}')
print(f'  {"#":<4} {"代码":<8} {"名称":<10} {"行业":<12} {"PE":>6} {"PB":>5} {"20日%":>6} {"vsMA20":>7} {"RSI":>5} {"超卖":>4} {"价值":>5} {"综合":>5} {"信号"}')
print(f'  {"─"*110}')

for i, (_, r) in enumerate(df_results.head(30).iterrows()):
    signals = []
    if r['rsi14'] < 30: signals.append('RSI超卖')
    if r['pe_ttm'] < 15: signals.append('深度低估')
    elif r['pe_ttm'] < 20: signals.append('低估值')
    if r['ret_20d'] < -10: signals.append('超跌')
    if r['pct_from_60h'] < -20: signals.append('高位回落')
    print(f'  {i+1:<4} {r["symbol"]:<8} {r["name"]:<10} {r["industry"]:<12} {r["pe_ttm"]:>6.1f} {r["pb"]:>5.2f} {r["ret_20d"]:>+5.1f}% {r["price_vs_ma20"]:>+6.1f}% {r["rsi14"]:>5.0f} {r["oversold_score"]:>4} {r["value_score"]:>5.1f} {r["composite_final"]:>5.1f}  {", ".join(signals)}')

df_results.to_csv('data/tech_deep_analysis.csv', index=False, encoding='utf-8-sig')
print(f'\n详细结果已保存到 data/tech_deep_analysis.csv')
