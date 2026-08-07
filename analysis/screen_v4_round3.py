"""
V4 Round 3: 估值筛选 — 寻找被低估的成长股
==========================================
对Round 2通过的增长型股票，调用val_report()做综合估值
（含修复后DCF + PEG + PB-ROE + 研报目标价），
按安全边际+估值合理性评分筛选。
"""
import sys, os, io, time
os.environ['PYTHONIOENCODING'] = 'utf-8'
sys.path.insert(0, '.')
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import pandas as pd
import numpy as np
from TG_trading_sys.data.cache import DataCache

DATE = '20260729'
INPUT_FILE = 'data/screen_v4_round2.csv'
OUTPUT_FILE = 'data/screen_v4_round3.csv'

# ═══════════════════════════════
# 1. 加载Round 2结果
# ═══════════════════════════════
print(f'[Round 3] 估值筛选 — {DATE}')
df = pd.read_csv(INPUT_FILE)
print(f'  加载 Round 2 结果: {len(df)} 只')

if len(df) == 0:
    print('  Round 2 无通过标的，终止')
    sys.exit(0)

# 截取Top 50做深度估值
TOP_N = min(50, len(df))
df = df.head(TOP_N)
print(f'  截取 Top {TOP_N} 只做估值分析')

cache = DataCache()

results = []
for i, (_, row) in enumerate(df.iterrows()):
    ts_code = str(row['ts_code'])
    code = str(ts_code.split('.')[0]).zfill(6)
    name = row['name']
    price = row['close']
    pe_ttm = row['pe_ttm']
    pb = row['pb']

    if (i + 1) % 15 == 0:
        print(f'    {i+1}/{len(df)}...')

    # ── 综合估值（val_report含修复后DCF+PEG+PB-ROE+研报）──
    try:
        from TG_trading_sys.valuation.val_report import val_report
        val = val_report(code)
        final_value = val.get('final_value')
        mos = val.get('margin_of_safety_pct')
        mos_verdict = val.get('margin_of_safety_verdict', '')

        dcf_val = val.get('dcf', {}).get('per_share_value')
        peg_val = val.get('relative', {}).get('peg_value', {})
        pb_roe = val.get('relative', {}).get('pb_roe_value', {})
        research = val.get('relative', {}).get('research_consensus', {})
        n_reports = research.get('count', 0)
        consensus_target = research.get('avg_target')
    except Exception as e:
        val = {}
        final_value = None
        mos = None
        mos_verdict = ''
        dcf_val = None
        peg_val = {}
        pb_roe = {}
        research = {}
        n_reports = 0
        consensus_target = None

    # ── 评分 ──
    # 安全边际评分 (40分)
    if mos is not None:
        if mos > 20: score_mos = 40
        elif mos > 10: score_mos = 30
        elif mos > 0: score_mos = 20
        elif mos > -10: score_mos = 10
        elif mos > -30: score_mos = 5
        else: score_mos = 0
    else:
        score_mos = 0

    # PEG评分 (25分)
    peg_ratio = peg_val.get('peg')
    if peg_ratio is not None and peg_ratio > 0:
        if peg_ratio < 0.5: score_peg = 25
        elif peg_ratio < 1.0: score_peg = 20
        elif peg_ratio < 1.5: score_peg = 15
        elif peg_ratio < 2.0: score_peg = 10
        else: score_peg = 5
    else:
        score_peg = 0

    # 机构覆盖评分 (10分)
    if n_reports >= 10: score_research = 10
    elif n_reports >= 5: score_research = 7
    elif n_reports >= 1: score_research = 4
    else: score_research = 0

    # 正安全边际额外加分 (15分) — 优先选出被低估的标的
    score_mos_bonus = 0
    if mos is not None and mos > 0:
        if mos > 20: score_mos_bonus = 15
        elif mos > 10: score_mos_bonus = 10
        elif mos > 0: score_mos_bonus = 5

    score_total = score_mos + score_peg + score_research + score_mos_bonus

    results.append({
        'ts_code': ts_code, 'code': code, 'name': name,
        'industry': row['industry'], 'price': price,
        'pe_ttm': pe_ttm, 'pb': pb, 'mcap_yi': row['total_mv'] / 10000,
        'rev_yoy': row.get('rev_cur_yoy', 0), 'np_yoy': row.get('np_cur_yoy', 0),
        'gross_margin': row.get('gross_margin', None),
        'debt_to_assets': row.get('debt_to_assets', None),
        'roe': row.get('roe', None),
        'score_growth': row.get('score_growth', 0),
        'score_beat': row.get('score_beat', 0),
        'score_health': row.get('score_health', 0),
        # 估值
        'final_value': round(final_value, 2) if final_value else None,
        'mos_pct': mos,
        'mos_verdict': mos_verdict,
        'dcf_value': round(dcf_val, 2) if dcf_val else None,
        'peg_value': round(peg_val.get('fair_value'), 2) if peg_val.get('fair_value') else None,
        'pbroe_value': round(pb_roe.get('fair_value'), 2) if isinstance(pb_roe, dict) and pb_roe.get('fair_value') else None,
        'peg_ratio': round(peg_ratio, 2) if peg_ratio else None,
        'n_reports': n_reports,
        'consensus_target': consensus_target,
        'score_mos': score_mos, 'score_peg': score_peg,
        'score_research': score_research, 'score_mos_bonus': score_mos_bonus,
        'score_total': score_total,
    })

    time.sleep(0.15)  # API限流

# ═══════════════════════════════
# 3. 排名输出
# ═══════════════════════════════
result_df = pd.DataFrame(results)
result_df = result_df.sort_values('score_total', ascending=False)

# 筛选：
# 1. 优先轨: 正安全边际(MOS>0) + 总分≥15 → 直接进入深度分析
# 2. 常规轨: 总分≥25 → 次选
positive_mos = result_df[(result_df['mos_pct'].notna()) & (result_df['mos_pct'] > 0) & (result_df['score_total'] >= 15)]
regular_pass = result_df[(~result_df['mos_pct'].isin(positive_mos['mos_pct'])) | (result_df['mos_pct'].isna())]
regular_pass = regular_pass[regular_pass['score_total'] >= 25]

final = pd.concat([positive_mos, regular_pass]).sort_values('mos_pct', ascending=False).head(25)
print(f'  正安全边际: {len(positive_mos)} 只 | 常规通过: {len(regular_pass)} 只 | 合计进入R4: {len(final)} 只')

print(f'\n{"="*100}')
print(f'  Round 3 估值筛选 — Top {len(final)} 只 (总分≥20)')
print(f'{"="*100}')
print(f'{"code":<8} {"name":<10} {"price":>7} {"PE":>6} {"PEG":>6} {"MOS":>8} {"DCF":>8} {"PEG价":>8} {"研报":>6} {"估值分":>6} {"总分":>5}')
print('-' * 90)
for _, r in final.iterrows():
    mos_s = f'{r["mos_pct"]:+.1f}%' if pd.notna(r['mos_pct']) else 'N/A'
    peg_s = f'{r["peg_ratio"]:.2f}' if pd.notna(r['peg_ratio']) and r['peg_ratio'] else 'N/A'
    peg_v = f'{r["peg_value"]:.2f}' if pd.notna(r['peg_value']) and r['peg_value'] else 'N/A'
    dcf_s = f'{r["dcf_value"]:.2f}' if pd.notna(r['dcf_value']) and r['dcf_value'] else 'N/A'
    print(f'{r["code"]:<8} {r["name"]:<10} {r["price"]:>7.2f} {r["pe_ttm"]:>6.1f} {peg_s:>6} {mos_s:>8} {dcf_s:>8} {peg_v:>8} {r["n_reports"]:>6} {r["score_mos"]:>6} {r["score_total"]:>5}')

final.to_csv(OUTPUT_FILE, index=False)
print(f'\n结果: {OUTPUT_FILE} ({len(final)} 只)')
