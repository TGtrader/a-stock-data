"""
V2 全链路重跑: 科技股估值重构 — PE-PEG/PB-ROE为主
Phase 1: 全市场→科技板块 (不变)
Phase 2: PE/PB行业中性化初筛 (不变)
Phase 3: 深度技术+PEG分析 (新增PEG因子)
Phase 4: 综合排名+PEG加权 → A类精选
"""
import sys, os, io, time
os.environ['PYTHONIOENCODING'] = 'utf-8'
sys.path.insert(0, '.')
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from TG_trading_sys.core.config import Config
from TG_trading_sys.data.cache import DataCache
import tushare as ts
import pandas as pd
import numpy as np

token = Config.get_tushare_token()
ts.set_token(token)
api = ts.pro_api()
cache = DataCache()

DATE = '20260728'
print(f'{"="*80}')
print(f'  V2 科技股估值重构 — PE-PEG/PB-ROE为主')
print(f'  日期: {DATE}')
print(f'{"="*80}')

# ═══════════════════════════════════════════════
# Phase 1: 全市场 → 科技板块
# ═══════════════════════════════════════════════
print('\n[Phase 1] 全市场行业筛选...')
stocks = api.stock_basic(exchange='', list_status='L',
                         fields='ts_code,symbol,name,area,industry,list_date')
TECH_INDUSTRIES = ['半导体', '软件服务', '通信设备', 'IT设备', '互联网',
                   '元器件', '电气设备', '专用机械', '电器仪表',
                   '医疗保健', '生物制药', '化学制药', '航空']
tech_stocks = stocks[stocks['industry'].isin(TECH_INDUSTRIES)].copy()
print(f'  全市场: {len(stocks)} → 科技: {len(tech_stocks)}')

# ═══════════════════════════════════════════════
# Phase 2: 估值初筛 (PE/PB行业中性化)
# ═══════════════════════════════════════════════
print('\n[Phase 2] PE/PB行业中性化初筛...')
daily = api.daily_basic(trade_date=DATE,
                        fields='ts_code,trade_date,close,pe,pe_ttm,pb,total_mv,circ_mv,turnover_rate,volume_ratio')
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

# 行业中性化PE/PB排名
valid['pe_rank'] = valid.groupby('industry')['pe_ttm'].rank(pct=True)
valid['pb_rank'] = valid.groupby('industry')['pb'].rank(pct=True)
# 价值分: PE低+PB低 = 高价值
valid['value_score_raw'] = (1 - valid['pe_rank']) * 0.5 + (1 - valid['pb_rank']) * 0.5

# ═══════════════════════════════════════════════
# Phase 3: K线技术 + 一致预期PEG
# ═══════════════════════════════════════════════
print('\n[Phase 3] 深度技术+PEG分析...')

# 3a. 初筛取 Top 100
candidates = valid.nlargest(100, 'value_score_raw')
codes = candidates['ts_code'].tolist()
print(f'  候选标的: {len(codes)} 只, 开始拉取K线+EPS...')

# 3b. 批量拉取K线
all_klines = {}
for i, ts_code in enumerate(codes):
    try:
        df = api.daily(ts_code=ts_code, start_date='20260101', end_date=DATE)
        if df is not None and len(df) >= 20:
            all_klines[ts_code] = df.sort_values('trade_date')
    except Exception:
        pass
    if (i + 1) % 30 == 0:
        print(f'  K线: {i+1}/{len(codes)}')
    time.sleep(0.08)

# 3c. 批量获取一致预期EPS (用于PEG计算)
print(f'  拉取同花顺一致预期EPS...')
consensus_eps = {}
for i, (_, row) in enumerate(candidates.iterrows()):
    code = row['symbol']
    try:
        eps_data = cache.get_consensus_eps(code)
        if eps_data:
            consensus_eps[code] = eps_data
    except Exception:
        pass
    if (i + 1) % 20 == 0:
        print(f'  EPS: {i+1}/{len(codes)} ({len(consensus_eps)} 成功)')
    time.sleep(0.25)

print(f'  一致预期EPS: {len(consensus_eps)}/{len(codes)} 成功')

# 3d. 综合计算 (技术 + PEG + 价值)
results = []
for _, row in candidates.iterrows():
    ts_code = row['ts_code']
    symbol = row['symbol']
    kline = all_klines.get(ts_code)
    if kline is None or len(kline) < 20:
        continue

    closes = pd.to_numeric(kline['close'], errors='coerce')
    volumes = pd.to_numeric(kline['vol'], errors='coerce')

    # 技术指标
    ret_5d = (closes.iloc[-1] / closes.iloc[-5] - 1) * 100 if len(closes) >= 5 else 0
    ret_20d = (closes.iloc[-1] / closes.iloc[-20] - 1) * 100 if len(closes) >= 20 else 0
    ma20 = closes.rolling(20).mean().iloc[-1]
    ma60 = closes.rolling(60).mean().iloc[-1] if len(closes) >= 60 else ma20
    price_vs_ma20 = (closes.iloc[-1] / ma20 - 1) * 100
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

    if len(closes) >= 60:
        ma5 = closes.rolling(5).mean().iloc[-1]
        ma10 = closes.rolling(10).mean().iloc[-1]
        mas = [ma5, ma10, ma20, ma60]
        ma_score = sum(1 for i in range(len(mas)-1) if mas[i] > mas[i+1]) / (len(mas)-1) * 100
    else:
        ma_score = 50

    # 超跌评分
    oversold = 0
    if rsi_now < 30: oversold += 30
    elif rsi_now < 40: oversold += 20
    elif rsi_now < 50: oversold += 10
    if price_vs_ma20 < -5: oversold += 20
    elif price_vs_ma20 < 0: oversold += 10
    if pct_from_high < -20: oversold += 25
    elif pct_from_high < -10: oversold += 15
    if ret_20d < -10: oversold += 15
    elif ret_20d < -5: oversold += 10

    # ── PEG 因子 (核心新增) ──
    pe = row['pe_ttm']
    eps_info = consensus_eps.get(symbol, {})
    peg_score = 0.50  # 默认中性

    if eps_info:
        # 获取EPS增长率
        hist = eps_info.get('historical', [])
        eps_forecast = []
        for yr_offset in range(3):
            yr = 2026 + yr_offset
            key = f'eps_{yr}'
            if key in eps_info and eps_info[key] and eps_info[key] > 0:
                eps_forecast.append(float(eps_info[key]))

        if eps_forecast and len(eps_forecast) >= 2:
            # 计算预测CAGR
            cagr = (eps_forecast[-1] / eps_forecast[0]) ** (1 / (len(eps_forecast) - 1)) - 1
            cagr = max(0.01, min(1.0, cagr))  # 限制1%-100%
        elif hist and len(hist) >= 2:
            # 用历史增速兜底
            growth_rates = []
            for j in range(1, len(hist)):
                if hist[j-1]['eps'] > 0 and hist[j]['eps'] > 0:
                    g = (hist[j]['eps'] / hist[j-1]['eps']) - 1
                    growth_rates.append(g)
            cagr = np.mean(growth_rates) if growth_rates else 0.05
            cagr = max(0.01, min(1.0, cagr))
        else:
            cagr = 0.10  # 默认10%

        # PEG = PE / (CAGR * 100)
        growth_pct = cagr * 100
        peg = pe / growth_pct if growth_pct > 0 else 999

        # PEG评分: PEG<1=极优, PEG<1.5=优良, PEG<2=合理, PEG>3=偏贵
        if peg < 0.5: peg_score = 1.0
        elif peg < 1.0: peg_score = 0.85
        elif peg < 1.5: peg_score = 0.70
        elif peg < 2.0: peg_score = 0.55
        elif peg < 3.0: peg_score = 0.40
        else: peg_score = 0.25

        # EPS趋势: 递增=加分, 递减=减分
        if eps_forecast and len(eps_forecast) >= 2:
            if eps_forecast[-1] > eps_forecast[0] * 1.1:
                peg_score = min(1.0, peg_score + 0.05)
            elif eps_forecast[-1] < eps_forecast[0] * 0.9:
                peg_score = max(0.1, peg_score - 0.10)
    else:
        cagr = 0.10
        peg = pe / 10
        peg_score = 0.50

    # ── 综合评分 (科技股重构权重) ──
    # PE-PEG价值: 35% | PB-ROE价值: 25% | 超跌信号: 25% | 流动性: 10% | PEG: 5%
    vs = row['value_score_raw']
    to = row['turnover_rate']
    tech_score = oversold / 100

    composite = (
        vs * 0.30 +           # PE/PB行业低估 (30%)
        peg_score * 0.25 +    # PEG因子 (25%) — 核心新增
        tech_score * 0.25 +   # 超跌信号 (25%)
        min(to, 10) / 10 * 0.10 +  # 流动性 (10%)
        (1 - row['pe_rank']) * 0.10  # 行业PE低位 (10%)
    )

    results.append({
        'ts_code': ts_code, 'symbol': symbol, 'name': row['name'],
        'industry': row['industry'],
        'close': row['close'], 'pe_ttm': pe, 'pb': row['pb'],
        'mcap_yi': row['total_mv'] / 10000, 'turnover': to,
        'ret_5d': round(ret_5d, 1), 'ret_20d': round(ret_20d, 1),
        'price_vs_ma20': round(price_vs_ma20, 1),
        'pct_from_60h': round(pct_from_high, 1),
        'rsi14': round(rsi_now, 1), 'ma_score': round(ma_score, 1),
        'vol_ratio': round(vol_ratio, 2),
        'cagr_pct': round(cagr * 100, 1),
        'peg': round(peg, 2),
        'peg_score': round(peg_score, 3),
        'value_score': round(vs * 100, 1),
        'oversold_score': oversold,
        'composite_final': round(composite * 100, 1),
    })

df = pd.DataFrame(results).sort_values('composite_final', ascending=False)

# Quality grading
df['quality'] = 'C'
df.loc[(df['composite_final'] >= 70) & (df['pe_ttm'] < 50) & (df['mcap_yi'] > 15), 'quality'] = 'B'
df.loc[(df['composite_final'] >= 75) & (df['pe_ttm'] < 35) & (df['mcap_yi'] > 20), 'quality'] = 'A'
df.loc[(df['composite_final'] >= 82) & (df['pe_ttm'] < 25), 'quality'] = 'A+'

# ═══════════════════════════════════════════════
# Output
# ═══════════════════════════════════════════════
print(f'\n{"="*115}')
print(f'  V2 科技成长 — PEG加权综合排名 (PE-PEG/PB-ROE为主)')
print(f'{"="*115}')
print(f'  {"#":<3} {"评级":<4} {"代码":<8} {"名称":<10} {"行业":<12} {"价格":>7} {"PE":>5} {"PEG":>6} {"增长%":>6} {"20日":>6} {"RSI":>4} {"超卖":>4} {"价值":>5} {"综合":>5} {"信号"}')
print(f'  {"─"*112}')

for i, (_, r) in enumerate(df.head(40).iterrows()):
    signals = []
    if r['rsi14'] < 30: signals.append('超卖')
    if r['peg'] < 1.0: signals.append('PEG<1')
    elif r['peg'] < 1.5: signals.append('PEG优')
    if r['pe_ttm'] < 15: signals.append('低PE')
    if r['ret_20d'] < -20: signals.append('超跌')
    if r['cagr_pct'] > 20: signals.append('高增长')
    print(f'  {i+1:<3} {r["quality"]:<4} {r["symbol"]:<8} {r["name"]:<10} {r["industry"]:<12} {r["close"]:>7.2f} {r["pe_ttm"]:>5.1f} {r["peg"]:>6.2f} {r["cagr_pct"]:>5.1f}% {r["ret_20d"]:>+5.1f}% {r["rsi14"]:>4.0f} {r["oversold_score"]:>4} {r["value_score"]:>5.1f} {r["composite_final"]:>5.1f}  {', '.join(signals)}')

# Stats
a_plus = df[df['quality'] == 'A+']
a_class = df[df['quality'] == 'A']
print(f'\nA+级: {len(a_plus)} | A级: {len(a_class)} | B级: {len(df[df["quality"]=="B"])}')
print(f'PEG<1: {len(df[df["peg"]<1])} | PEG 1-2: {len(df[(df["peg"]>=1)&(df["peg"]<2)])} | RSI<30: {len(df[df["rsi14"]<30])}')

# Show A/A+ list
a_list = pd.concat([a_plus, a_class]).sort_values('composite_final', ascending=False)
print(f'\n{"="*80}')
print(f'  A/A+ 级精选池 — 进入深度分析')
print(f'{"="*80}')
for _, r in a_list.iterrows():
    print(f'  {r["quality"]} {r["symbol"]} {r["name"]} | {r["industry"]} | PE{r["pe_ttm"]:.1f} PEG{r["peg"]:.2f} 增长{r["cagr_pct"]:.1f}% | 综合{r["composite_final"]:.1f}')
print(f'\n共 {len(a_list)} 只')
df.to_csv('data/tech_v2_results.csv', index=False, encoding='utf-8-sig')
a_list.to_csv('data/tech_v2_a_class.csv', index=False, encoding='utf-8-sig')
print('保存到 data/tech_v2_results.csv')
