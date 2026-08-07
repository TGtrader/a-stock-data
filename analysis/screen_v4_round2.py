"""
V4 Round 2: 增长质量 + 超预期检测 + 经营稳健性 (v2)
====================================================
改进:
  1. 扩展至5期income做QoQ环比(近2期高权重)
  2. 负债>70%负分惩罚
  3. 营收+利润双改善加分
  4. 盈喜公司单独标记,独立管线输出
"""
import sys, os, io, time
os.environ['PYTHONIOENCODING'] = 'utf-8'
sys.path.insert(0, '.')
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from TG_trading_sys.core.config import Config
import tushare as ts
import pandas as pd
import numpy as np

DATE = '20260729'
token = Config.get_tushare_token()
ts.set_token(token)
api = ts.pro_api()

# ═══════════════════════════════
# 1. 科技行业初筛
# ═══════════════════════════════
print(f'[Round 2 v2] 增长质量+超预期+稳健性 — {DATE}')
stocks = api.stock_basic(exchange='', list_status='L',
                         fields='ts_code,symbol,name,area,industry,list_date')
TECH_INDUSTRIES = ['半导体', '软件服务', '通信设备', 'IT设备', '互联网',
                   '元器件', '电气设备', '专用机械', '电器仪表',
                   '医疗保健', '生物制药', '化学制药', '航空']
tech = stocks[stocks['industry'].isin(TECH_INDUSTRIES)].copy()
print(f'  全市场: {len(stocks)} → 科技: {len(tech)}')

# ═══════════════════════════════
# 2. daily_basic预过滤
# ═══════════════════════════════
daily = api.daily_basic(trade_date=DATE,
    fields='ts_code,trade_date,close,pe_ttm,pb,total_mv,circ_mv,turnover_rate')
tech = tech.merge(daily, on='ts_code', how='inner')
for col in ['pe_ttm','pb','total_mv','close','turnover_rate']:
    tech[col] = pd.to_numeric(tech[col], errors='coerce')

tech = tech[(tech['total_mv'] > 500000) &
            (tech['total_mv'] < 10000000) &
            (tech['close'] > 5) &
            (tech['pe_ttm'] > 5) & (tech['pe_ttm'] < 80) &
            (tech['turnover_rate'] > 0.5)].copy()
tech = tech[~tech['name'].str.contains('ST', na=False)]
n_pre = len(tech)
print(f'  预过滤后: {n_pre} 只 (市值50-1000亿/PE5-80/换手>0.5%)')

# ═══════════════════════════════
# 3. 批量获取业绩预告(盈喜标记)
# ═══════════════════════════════
print('  获取2026H1业绩预告...')
forecast_map = {}  # {ts_code: {type, p_change_min, p_change_max, net_profit_min}}
codes_all = tech['ts_code'].tolist()
for ts_code in codes_all:
    try:
        fc = api.forecast(ts_code=ts_code, period='20260630',
            fields='ts_code,type,p_change_min,p_change_max,net_profit_min')
        if fc is not None and len(fc) > 0:
            r = fc.iloc[0]
            forecast_map[ts_code] = {
                'type': r['type'], 'p_change_min': r['p_change_min'],
                'p_change_max': r['p_change_max'],
                'net_profit_min': float(r['net_profit_min']) if pd.notna(r.get('net_profit_min')) else None,
            }
    except:
        pass
    time.sleep(0.12)

# 盈喜: 预增 / 略增 / 扭亏
YINGXI_TYPES = {'预增', '略增', '扭亏'}
yingxi_codes = {c for c, v in forecast_map.items() if v['type'] in YINGXI_TYPES}
print(f'  有预告: {len(forecast_map)}, 盈喜: {len(yingxi_codes)}')

# ═══════════════════════════════
# 4. 逐只获取5期income + fina_indicator
# ═══════════════════════════════
print(f'  逐只获取5期财报...')
PERIODS = ['20260331', '20251231', '20250930', '20250630', '20250331']

results = []
for i, ts_code in enumerate(codes_all):
    if (i + 1) % 80 == 0:
        print(f'    {i+1}/{n_pre}...')

    stock_info = tech[tech['ts_code'] == ts_code].iloc[0]

    # ── 获取5期income ──
    quarters = {}  # {period: {revenue, total_cogs, n_income, eps}}
    for period in PERIODS:
        try:
            inc = api.income(ts_code=ts_code, period=period,
                            fields='ts_code,report_type,end_date,revenue,total_cogs,n_income_attr_p,basic_eps')
            if inc is not None and len(inc) > 0:
                inc_cons = inc[inc['report_type'] == '1']
                r = inc_cons.iloc[0] if len(inc_cons) > 0 else inc.iloc[0]
                quarters[period] = {
                    'revenue': float(r.get('revenue', 0) or 0),
                    'total_cogs': float(r.get('total_cogs', 0) or 0),
                    'n_income': float(r.get('n_income_attr_p', 0) or 0),
                    'eps': float(r.get('basic_eps', 0) or 0),
                }
        except:
            pass

    # ── 获取fina_indicator ──
    fi = {}
    try:
        fi_df = api.fina_indicator(ts_code=ts_code, period='20260331',
            fields='ts_code,gross_margin,current_ratio,quick_ratio,cash_ratio,debt_to_assets,roe')
        if fi_df is not None and len(fi_df) > 0:
            for col in fi_df.columns:
                if col != 'ts_code':
                    v = fi_df.iloc[0][col]
                    fi[col] = float(v) if pd.notna(v) else None
    except:
        pass

    # ── 至少需要最近2期 ──
    q1 = quarters.get('20260331', {})
    q4 = quarters.get('20251231', {})
    q3 = quarters.get('20250930', {})
    q2 = quarters.get('20250630', {})
    q1_prev = quarters.get('20250331', {})

    if not q1.get('revenue') or not q4.get('revenue'):
        continue

    # ═══════════════════════════════
    # A. 增长质量 (40分) — QoQ环比, 近2期高权重
    # ═══════════════════════════════
    # 计算4组QoQ环比
    def qoq(cur, prev):
        if prev and prev > 0 and cur:
            return (cur - prev) / prev * 100
        return 0

    rev_qoq = [
        qoq(q1.get('revenue'), q4.get('revenue')),      # Q1/Q4 (最新)
        qoq(q4.get('revenue'), q3.get('revenue')),      # Q4/Q3
        qoq(q3.get('revenue'), q2.get('revenue')),      # Q3/Q2
        qoq(q2.get('revenue'), q1_prev.get('revenue')), # Q2/Q1_prev (最旧)
    ]
    np_qoq = [
        qoq(q1.get('n_income'), q4.get('n_income')),
        qoq(q4.get('n_income'), q3.get('n_income')),
        qoq(q3.get('n_income'), q2.get('n_income')),
        qoq(q2.get('n_income'), q1_prev.get('n_income')),
    ]

    # 加权: 近2期70%, 远2期30%
    rev_weighted = (rev_qoq[0]*0.4 + rev_qoq[1]*0.3 + rev_qoq[2]*0.2 + rev_qoq[3]*0.1)
    np_weighted = (np_qoq[0]*0.4 + np_qoq[1]*0.3 + np_qoq[2]*0.2 + np_qoq[3]*0.1)

    # A1. 营收环比增长 (15分)
    s_rev = 0
    if rev_weighted > 30: s_rev = 15
    elif rev_weighted > 20: s_rev = 12
    elif rev_weighted > 10: s_rev = 8
    elif rev_weighted > 5: s_rev = 5
    elif rev_weighted > 0: s_rev = 3

    # A2. 利润环比增长 (15分)
    s_np = 0
    if np_weighted > 50: s_np = 15
    elif np_weighted > 30: s_np = 12
    elif np_weighted > 15: s_np = 8
    elif np_weighted > 5: s_np = 5
    elif np_weighted > 0: s_np = 3

    # A3. 毛利率 (10分)
    s_margin = 0
    gross_margin = None
    if q1.get('revenue') and q1.get('total_cogs') and q1['revenue'] > 0:
        gross_margin = (q1['revenue'] - q1['total_cogs']) / q1['revenue'] * 100
        if gross_margin > 40: s_margin = 10
        elif gross_margin > 30: s_margin = 8
        elif gross_margin > 20: s_margin = 5
        elif gross_margin > 10: s_margin = 3

    score_growth = s_rev + s_np + s_margin

    # ═══════════════════════════════
    # B. 超预期检测 (30分)
    # ═══════════════════════════════
    # B1. 业绩预告信号 (15分)
    fc = forecast_map.get(ts_code, {})
    s_forecast = 0
    fc_type = fc.get('type', '')
    p_min = fc.get('p_change_min')
    if fc_type == '预增' and p_min and p_min > 100:
        s_forecast = 15
    elif fc_type == '预增' and p_min and p_min > 50:
        s_forecast = 12
    elif fc_type == '预增':
        s_forecast = 9
    elif fc_type == '扭亏':
        s_forecast = 12  # 扭亏是高价值信号
    elif fc_type == '略增':
        s_forecast = 6
    elif fc_type in ('预减', '略减', '续亏', '首亏'):
        s_forecast = -5  # 负面预告惩罚

    # B2. 环比加速信号 (15分)
    s_accel = 0
    # 最近2期环比都为正且加速
    if rev_qoq[0] > 0 and np_qoq[0] > 0:
        s_accel += 5  # 最新季度双增
    if rev_qoq[1] > 0 and np_qoq[1] > 0:
        s_accel += 3  # 前一季度双增
    # 利润环比加速
    if np_qoq[0] > np_qoq[1] > 0:
        s_accel += 4
    elif np_qoq[0] > 0 and np_qoq[1] > 0:
        s_accel += 2
    # PEG匹配
    pe = float(stock_info['pe_ttm'])
    np_yoy_est = np_weighted * 4  # 季度环比年化估算
    if np_yoy_est > 0 and pe > 0:
        peg_est = pe / max(np_yoy_est, 1)
        if peg_est < 1: s_accel += 3
        elif peg_est < 2: s_accel += 1

    s_accel = min(15, s_accel)

    score_beat = s_forecast + s_accel

    # ═══════════════════════════════
    # C. 经营稳健性 (30分) — 含负债惩罚
    # ═══════════════════════════════
    # C1. 现金流健康 (15分)
    cash_ratio = fi.get('cash_ratio')
    current_ratio = fi.get('current_ratio')
    quick_ratio = fi.get('quick_ratio')
    s_cash = 0
    if cash_ratio is not None:
        if cash_ratio > 0.5: s_cash += 7
        elif cash_ratio > 0.3: s_cash += 5
        elif cash_ratio > 0.15: s_cash += 2
    if current_ratio is not None:
        if current_ratio > 2: s_cash += 4
        elif current_ratio > 1: s_cash += 2
    if quick_ratio is not None:
        if quick_ratio > 1: s_cash += 4
        elif quick_ratio > 0.5: s_cash += 2
    s_cash = min(15, s_cash)

    # C2. 负债率 (10分, 高负债惩罚)
    debt = fi.get('debt_to_assets')
    if debt is not None:
        if debt < 30: s_debt = 10
        elif debt < 50: s_debt = 7
        elif debt < 70: s_debt = 4
        elif debt < 85: s_debt = -2   # 惩罚
        else: s_debt = -5              # 严重惩罚
    else:
        s_debt = 5

    # C3. 盈利确定性 (5分)
    s_quality = 0
    if q1.get('eps', 0) > 0: s_quality += 2
    if 5 < pe < 80: s_quality += 2
    if q1.get('n_income', 0) > 0 and q4.get('n_income', 0) > 0:
        s_quality += 1

    score_health = s_cash + s_debt + s_quality

    # ═══════════════════════════════
    # D. 额外加分: 营收+利润双改善 (max +8)
    # ═══════════════════════════════
    s_dual = 0
    # 最新季度双环比正增长
    if rev_qoq[0] > 0 and np_qoq[0] > 0:
        s_dual += 3
    # 连续2季度双正
    if rev_qoq[0] > 0 and np_qoq[0] > 0 and rev_qoq[1] > 0 and np_qoq[1] > 0:
        s_dual += 3
    # 营收和利润环比同时加速
    if rev_qoq[0] > rev_qoq[1] and np_qoq[0] > np_qoq[1]:
        s_dual += 2

    # ── 总分 (含双改善加分) ──
    score_total = score_growth + score_beat + score_health + s_dual

    # 利润双正检查(Q1和Q4)
    np_valid = q1.get('n_income', 0) > 0 and q4.get('n_income', 0) > 0

    # 盈喜标记
    is_yingxi = ts_code in yingxi_codes

    results.append({
        'ts_code': ts_code, 'code': str(ts_code.split('.')[0]).zfill(6),
        'name': stock_info['name'], 'industry': stock_info['industry'],
        'close': float(stock_info['close']), 'pe_ttm': float(stock_info['pe_ttm']),
        'pb': float(stock_info['pb']), 'total_mv': float(stock_info['total_mv']),
        'turnover_rate': float(stock_info['turnover_rate']),
        # 环比数据
        'rev_qoq1': round(rev_qoq[0],1), 'rev_qoq2': round(rev_qoq[1],1),
        'rev_qoq3': round(rev_qoq[2],1), 'rev_qoq4': round(rev_qoq[3],1),
        'np_qoq1': round(np_qoq[0],1), 'np_qoq2': round(np_qoq[1],1),
        'np_qoq3': round(np_qoq[2],1), 'np_qoq4': round(np_qoq[3],1),
        'rev_weighted': round(rev_weighted,1), 'np_weighted': round(np_weighted,1),
        'gross_margin': round(gross_margin,1) if gross_margin else None,
        'cash_ratio': round(cash_ratio,3) if cash_ratio else None,
        'debt_to_assets': round(debt,1) if debt else None,
        'roe': round(fi.get('roe',0),1) if fi.get('roe') else None,
        # 业绩预告
        'fc_type': fc_type, 'fc_p_min': p_min, 'fc_p_max': fc.get('p_change_max'),
        'fc_np_min': fc.get('net_profit_min'),
        # 评分明细
        's_rev': s_rev, 's_np': s_np, 's_margin': s_margin,
        's_forecast': s_forecast, 's_accel': s_accel,
        's_cash': s_cash, 's_debt': s_debt, 's_quality': s_quality,
        's_dual': s_dual,
        'score_growth': score_growth, 'score_beat': score_beat,
        'score_health': score_health, 'score_total': score_total,
        'np_valid': np_valid, 'is_yingxi': is_yingxi,
    })

    time.sleep(0.2)

result_df = pd.DataFrame(results)
print(f'\n  评分完成: {len(result_df)} 只有效数据')

# ═══════════════════════════════
# 5. 分轨输出
# ═══════════════════════════════
# 常规轨: >=50分 + 利润双正
qualified = result_df[(result_df['score_total'] >= 50) & result_df['np_valid']].sort_values('score_total', ascending=False)

# 盈喜轨: 盈喜标记 + 利润双正 + >=30分(降低门槛)
yingxi_qualified = result_df[result_df['is_yingxi'] & result_df['np_valid'] & (result_df['score_total'] >= 30)].sort_values('score_total', ascending=False)

print(f'  常规轨: {len(qualified)} 只 (≥50分)')
print(f'  盈喜轨: {len(yingxi_qualified)} 只 (盈喜+≥30分)')

# 输出
out_dir = 'data'
os.makedirs(out_dir, exist_ok=True)

qualified.to_csv(f'{out_dir}/screen_v4_round2.csv', index=False)
yingxi_qualified.to_csv(f'{out_dir}/screen_v4_round2_yingxi.csv', index=False)

# ── 打印常规轨 Top 20 ──
sep = '=' * 110
print(f'\n{sep}')
print(f'  [常规轨] Round 2: {len(qualified)} 只 (≥50分 + 利润双正)')
print(f'{sep}')
header = '{:<12} {:<10} {:>7} {:>6} {:>7} {:>7} {:>6} {:>5} {:>5} {:>5} {:>5} {:>5} {:>5} {:>5}'.format(
    'ts_code','name','price','PE','rev_w','np_w','margin','grow','beat','hlth','dual','fc','debt','tot')
print(header)
print('-' * 100)
for _, r in qualified.head(20).iterrows():
    fc_s = f'{r["fc_type"]}' if r['fc_type'] else '-'
    vals = (r['ts_code'], r['name'], r['close'], r['pe_ttm'],
            r['rev_weighted'], r['np_weighted'], r['gross_margin'],
            r['score_growth'], r['score_beat'], r['score_health'],
            r['s_dual'], fc_s, r['s_debt'], r['score_total'])
    row = '{:<12} {:<10} {:>7.2f} {:>6.1f} {:>7.1f} {:>7.1f} {:>6.1f} {:>5} {:>5} {:>5} {:>5} {:>5} {:>5} {:>5}'.format(*vals)
    print(row)

# ── 打印盈喜轨 Top 20 ──
print(f'\n{sep}')
print(f'  [盈喜轨] Round 2: {len(yingxi_qualified)} 只 (盈喜+≥30分+利润双正)')
print(f'{sep}')
print(header)
print('-' * 100)
for _, r in yingxi_qualified.head(20).iterrows():
    fc_s = f'{r["fc_type"]}' if r['fc_type'] else '-'
    vals = (r['ts_code'], r['name'], r['close'], r['pe_ttm'],
            r['rev_weighted'], r['np_weighted'], r['gross_margin'],
            r['score_growth'], r['score_beat'], r['score_health'],
            r['s_dual'], fc_s, r['s_debt'], r['score_total'])
    row = '{:<12} {:<10} {:>7.2f} {:>6.1f} {:>7.1f} {:>7.1f} {:>6.1f} {:>5} {:>5} {:>5} {:>5} {:>5} {:>5} {:>5}'.format(*vals)
    print(row)

print(f'\n常规轨: {out_dir}/screen_v4_round2.csv')
print(f'盈喜轨: {out_dir}/screen_v4_round2_yingxi.csv')
