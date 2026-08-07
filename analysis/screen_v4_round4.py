"""
V4 Round 4: 深度分析 + Tushare资金流
====================================
对Round 3筛选出的低估成长股做V3全模块深度分析，
集成Tushare moneyflow 全市场资金流（参考 参考代码/资金流/）。
"""
import sys, os, io, json, time
os.environ['PYTHONIOENCODING'] = 'utf-8'
sys.path.insert(0, '.')
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from TG_trading_sys.core.config import Config
from TG_trading_sys.data.cache import DataCache

DATE = '20260729'
INPUT_FILE = 'data/screen_v4_round3.csv'
OUTPUT_JSON = 'data/deep_reports/all_reports_v4.json'

df = pd.read_csv(INPUT_FILE)
print(f'[Round 4] 深度分析 + Tushare资金流 — {len(df)} 只标的')
print(f'  基准日期: {DATE}')

# ═══════════════════════════════
# 0. Tushare资金流批量获取（参考 参考代码/资金流/）
# ═══════════════════════════════
print('获取Tushare moneyflow全市场数据（近20个交易日）...')
try:
    import tushare as ts
    token = Config.get_tushare_token()
    ts.set_token(token)
    pro = ts.pro_api()

    mf_records = []
    for lookback in range(20):
        try_date = (datetime.now() - timedelta(days=lookback)).strftime('%Y%m%d')
        try:
            mf_day = pro.moneyflow(trade_date=try_date)
            if mf_day is not None and len(mf_day) > 0:
                mf_day['trade_date'] = try_date
                mf_records.append(mf_day)
        except:
            continue

    if mf_records:
        mf_all = pd.concat(mf_records, ignore_index=True)

        # 数值化所有资金流列
        mf_cols = ['buy_sm_vol','buy_sm_amount','sell_sm_vol','sell_sm_amount',
                    'buy_md_vol','buy_md_amount','sell_md_vol','sell_md_amount',
                    'buy_lg_vol','buy_lg_amount','sell_lg_vol','sell_lg_amount',
                    'buy_elg_vol','buy_elg_amount','sell_elg_vol','sell_elg_amount',
                    'net_mf_vol','net_mf_amount']
        for col in mf_cols:
            if col in mf_all.columns:
                mf_all[col] = pd.to_numeric(mf_all[col], errors='coerce').fillna(0)

        mf_days = sorted(mf_all['trade_date'].unique())
        print(f'  Tushare moneyflow: {len(mf_days)}个交易日, {len(mf_all)}条记录')

        # 按ts_code聚合计算趋势指标（参考 moneyflow_summary.py 的净额计算逻辑）
        mf_trend = {}
        for ts_code, grp in mf_all.groupby('ts_code'):
            grp_sorted = grp.sort_values('trade_date')
            n = len(grp_sorted)

            # 净买入金额（参考 moneyflow_summary.py calculate_net_values）
            net_mf = grp_sorted['net_mf_amount'].values  # 主力净流入
            # 分单类净额
            if 'buy_lg_amount' in grp_sorted.columns and 'sell_lg_amount' in grp_sorted.columns:
                net_lg = (grp_sorted['buy_lg_amount'] - grp_sorted['sell_lg_amount']).values  # 大单净
                net_elg = (grp_sorted['buy_elg_amount'] - grp_sorted['sell_elg_amount']).values  # 特大单净
                net_big = net_lg + net_elg  # 大单+特大单 = 主力
            else:
                net_big = net_mf.copy()
                net_lg = net_mf.copy()

            if 'buy_sm_amount' in grp_sorted.columns:
                net_sm = (grp_sorted['buy_sm_amount'] - grp_sorted['sell_sm_amount']).values
                net_md = (grp_sorted['buy_md_amount'] - grp_sorted['sell_md_amount']).values
            else:
                net_sm = np.zeros(n)
                net_md = np.zeros(n)

            # 连续流入/流出天数
            cons_in, cons_out = 0, 0
            for v in reversed(net_mf):
                if v > 0 and cons_out == 0: cons_in += 1
                elif v < 0 and cons_in == 0: cons_out += 1
                else: break

            # 大单占比（主力控盘度）
            total_big_buy = grp_sorted[['buy_lg_amount','buy_elg_amount']].sum(axis=1).values if 'buy_elg_amount' in grp_sorted.columns else net_big
            total_buy = total_big_buy + net_sm.clip(min=0) + net_md.clip(min=0)  # 近似总买入
            big_ratio = float(np.sum(total_big_buy[-5:]) / max(np.sum(total_buy[-5:]), 1)) if len(total_buy) >= 5 else 0

            # 资金共振：最近5日价格方向 vs 资金方向
            # (无法在此获取价格，留到per-stock阶段计算)

            # 主力(大单+特大单)作为主力净流入依据
            net_big_total = net_lg + net_elg  # 逐日主力净额

            # 频率统计：主力净流入/流出天数
            big_in_days = int(np.sum(net_big_total > 0))
            big_out_days = int(np.sum(net_big_total < 0))
            big_neutral_days = int(np.sum(net_big_total == 0))
            big_in_ratio = round(big_in_days / n, 3) if n > 0 else 0
            total_big_net = float(net_big_total.sum())

            # 主力净流入强度（日均净流入/总成交额）
            total_buy_all = grp_sorted[['buy_lg_amount','buy_elg_amount','buy_md_amount','buy_sm_amount']].sum(axis=1).values if 'buy_md_amount' in grp_sorted.columns else total_big_buy
            total_sell_all = total_big_buy + net_sm.clip(min=0) + net_md.clip(min=0)  # 近似
            avg_daily_turnover = float(np.mean(total_buy_all[:20])) if n > 0 else 1
            intensity = round(total_big_net / max(avg_daily_turnover * n, 1), 4)

            # 5日短期vs20日趋势一致性
            big_net_5d = float(net_big_total[-5:].sum()) if n >= 5 else total_big_net
            big_net_prev_15d = float(net_big_total[:-5].sum()) if n > 5 else 0
            trend_consistent = (big_net_5d * total_big_net > 0) if total_big_net != 0 and big_net_5d != 0 else False

            mf_trend[ts_code] = {
                'days_count': n,
                'period': f'{mf_days[0] if mf_days else "?"}~{mf_days[-1] if mf_days else "?"}',
                'net_mf_5d': float(net_mf[-5:].sum()) if n >= 5 else float(net_mf.sum()),
                'net_mf_20d': float(net_mf.sum()),
                'net_mf_5d_avg': float(net_mf[-5:].mean()) if n >= 5 else float(net_mf.mean()),
                'net_lg_5d': float(net_lg[-5:].sum()) if n >= 5 else float(net_lg.sum()),
                'net_elg_5d': float(net_elg[-5:].sum()) if n >= 5 and len(net_elg) >= 5 else 0,
                'net_sm_5d': float(net_sm[-5:].sum()) if n >= 5 else float(net_sm.sum()),
                'consecutive_in': cons_in,
                'consecutive_out': cons_out,
                'big_order_ratio': round(big_ratio, 3),
                # 频率统计
                'big_in_days': big_in_days, 'big_out_days': big_out_days,
                'big_neutral_days': big_neutral_days, 'big_in_ratio': big_in_ratio,
                'total_big_net': total_big_net, 'intensity': intensity,
                'big_net_5d': big_net_5d, 'trend_consistent': trend_consistent,
            }

        tushare_mf_available = True
    else:
        tushare_mf_available = False
        mf_all = pd.DataFrame()
        mf_trend = {}
except Exception as e:
    print(f'  Tushare moneyflow不可用: {e}')
    tushare_mf_available = False
    mf_all = pd.DataFrame()
    mf_trend = {}

# ═══════════════════════════════
# Patch: 价格锁定
# ═══════════════════════════════
_orig_get_stock_basic = DataCache.get_stock_basic
_orig_get_kline = DataCache.get_kline

def _patched_get_stock_basic(self, code, force_refresh=False, use_cache_price=True):
    result = _orig_get_stock_basic(self, code, force_refresh=force_refresh)
    if not result: return None
    try:
        kline = _orig_get_kline(self, code, lookback=30)
        if kline is not None and len(kline) > 0:
            mask = kline.index <= DATE
            if mask.any():
                last = kline[mask].iloc[-1]
                orig_price = result.get('price', 0) or last['close']
                if orig_price > 0:
                    ratio = float(last['close']) / orig_price
                    result['price'] = float(last['close'])
                    result['pe_ttm'] = result.get('pe_ttm', 0) * ratio
                    result['pb'] = result.get('pb', 0) * ratio
                    result['mcap_yi'] = result.get('mcap_yi', 0) * ratio
    except: pass
    return result

def _patched_get_kline(self, code, lookback=250):
    kline = _orig_get_kline(self, code, lookback=lookback)
    if kline is not None and len(kline) > 0:
        mask = kline.index <= DATE
        if mask.any(): return kline[mask].copy()
    return kline

DataCache.get_stock_basic = _patched_get_stock_basic
DataCache.get_kline = _patched_get_kline
import TG_trading_sys.data.cache as cache_mod
cache_mod.DataCache.get_stock_basic = _patched_get_stock_basic
cache_mod.DataCache.get_kline = _patched_get_kline

# ═══════════════════════════════
# 导入采集函数
# ═══════════════════════════════
from analysis.report_v3_collect import (
    collect_research, collect_business, collect_moneyflow,
    analyze_volume_price_vpa, synthesize_research,
    download_and_extract_reports, collect_f10_summary
)

cache = DataCache()
all_reports = {}

print(f'\n开始逐只深度分析 ({len(df)} 只)...')
print('-' * 60)

for idx, (_, row) in enumerate(df.iterrows()):
    code = str(row['code']).zfill(6)
    name = row['name']
    sw2 = row.get('industry', '')
    print(f'\n[{idx+1}/{len(df)}] {code} {name}')

    report = {
        'code': code, 'name': name, 'sw2': sw2,
        'analysis_date': DATE,
    }

    # 1. Basic
    try:
        basic = cache.get_stock_basic(code, force_refresh=True)
        report['basic'] = {
            'price': basic.get('price', row['price']) if basic else row['price'],
            'pe_ttm': basic.get('pe_ttm', row['pe_ttm']) if basic else row['pe_ttm'],
            'pb': basic.get('pb', row['pb']) if basic else row['pb'],
            'mcap_yi': basic.get('mcap_yi', row['mcap_yi']) if basic else row['mcap_yi'],
        }
    except:
        report['basic'] = {'price': row['price'], 'pe_ttm': row['pe_ttm'],
                           'pb': row['pb'], 'mcap_yi': row['mcap_yi']}

    # 2. Kline + Technical
    kline = None
    try:
        kline = cache.get_kline(code, lookback=250)
        if kline is not None and len(kline) >= 20:
            from TG_trading_sys.strategy.timing.ma_signals import analyze_ma_system
            from TG_trading_sys.strategy.timing.pattern_signals import detect_patterns
            from TG_trading_sys.strategy.timing.signal_aggregator import aggregate_signals
            ma = analyze_ma_system(kline)
            pat = detect_patterns(kline)
            verdict = aggregate_signals(ma, None, None, pat, None)
            report['technical'] = {
                'kline_rows': len(kline), 'ma_score': ma.get('score', 50),
                'ma_verdict': ma.get('verdict', ''), 'ma_alignment': ma.get('ma_alignment', {}).get('state', ''),
                'verdict': verdict.verdict, 'verdict_score': verdict.score,
                'confidence': verdict.confidence, 'position_advice': verdict.position_advice,
            }
    except:
        report['technical'] = {}

    # 3. Valuation
    try:
        from TG_trading_sys.valuation.val_report import val_report
        val = val_report(code)
        report['valuation'] = {
            'final_value': val.get('final_value'), 'current_price': val.get('current_price', 0),
            'margin_of_safety_pct': val.get('margin_of_safety_pct'),
            'margin_verdict': val.get('margin_of_safety_verdict', ''),
            'dcf_per_share': val.get('dcf', {}).get('per_share_value'),
            'peg_value': val.get('relative', {}).get('peg_value', {}),
            'pb_roe_value': val.get('relative', {}).get('pb_roe_value', {}),
            'scenarios': val.get('scenarios', {}), 'earnings': val.get('earnings', {}),
            'estimate_components': val.get('estimate_components', []),
        }
        mos = val.get('margin_of_safety_pct')
        print(f'  估值: {val.get("final_value", "N/A")}' +
              (f' MOS={mos:.1f}%' if mos else ''))
    except Exception as e:
        print(f'  估值ERR: {e}')
        report['valuation'] = {}

    # 4. Financials (实际数据提取，非仅计数)
    try:
        from TG_trading_sys.valuation.wacc import _extract_number
        fin_data = {}
        # 获取最近8期数据
        for rt in ['lrb', 'fzb', 'llb']:
            data = cache.get_financials(code, report_type=rt, force_refresh=True)
            if data: fin_data[rt] = data

        # 提取关键指标
        key_metrics = {}
        balance = {}
        lrb_data = fin_data.get('lrb', [])
        fzb_data = fin_data.get('fzb', [])

        if lrb_data:
            latest = lrb_data[0]
            key_metrics['report_period'] = latest.get('report_date', '')
            key_metrics['revenue'] = _extract_number(latest, '营业收入') or \
                                      _extract_number(latest, '营业总收入') or 0
            key_metrics['net_profit'] = _extract_number(latest, '归属于母公司股东的净利润') or \
                                         _extract_number(latest, '净利润') or 0
            # 计算季度营收/利润(YoY对比)
            if len(lrb_data) >= 5:
                key_metrics['rev_last_q'] = _extract_number(lrb_data[1], '营业收入') or 0
                key_metrics['np_last_q'] = _extract_number(lrb_data[1], '归属于母公司股东的净利润') or 0
                key_metrics['rev_4q_ago'] = _extract_number(lrb_data[4], '营业收入') or 0
                key_metrics['np_4q_ago'] = _extract_number(lrb_data[4], '归属于母公司股东的净利润') or 0
            # 最近4季度营收/利润列表
            key_metrics['q_revenues'] = []
            key_metrics['q_profits'] = []
            for j in range(min(4, len(lrb_data))):
                key_metrics['q_revenues'].append(_extract_number(lrb_data[j], '营业收入') or 0)
                key_metrics['q_profits'].append(_extract_number(lrb_data[j], '归属于母公司股东的净利润') or \
                                                 _extract_number(lrb_data[j], '净利润') or 0)

        if fzb_data:
            latest_fzb = fzb_data[0]
            balance['total_assets'] = _extract_number(latest_fzb, '资产总计') or 0
            balance['equity'] = _extract_number(latest_fzb, '归属于母公司股东权益合计') or \
                               _extract_number(latest_fzb, '所有者权益合计') or 0
            balance['cash'] = _extract_number(latest_fzb, '货币资金') or 0
            total_liab = _extract_number(latest_fzb, '负债合计') or 0
            if balance['total_assets'] > 0:
                balance['debt_ratio'] = round(total_liab / balance['total_assets'] * 100, 1)
            else:
                balance['debt_ratio'] = None

        report['financials'] = {'analysis_date': DATE, 
            'key_metrics': key_metrics,
            'balance': balance,
            'reports_available': {rt: len(data) for rt, data in fin_data.items()},
        }
    except:
        report['financials'] = {'analysis_date': DATE, }

    # 4b. 成长数据 (从Round2 CSV提取QoQ环比)
    try:
        r2_csv = 'data/screen_v4_round2.csv'
        if os.path.exists(r2_csv):
            r2_df = pd.read_csv(r2_csv)
            r2_row = r2_df[r2_df['code'] == int(code)]
            if len(r2_row) > 0:
                r2 = r2_row.iloc[0]
                report['growth'] = {'analysis_date': DATE, 
                    'rev_qoq1': float(r2.get('rev_qoq1', 0) or 0),
                    'rev_qoq2': float(r2.get('rev_qoq2', 0) or 0),
                    'rev_qoq3': float(r2.get('rev_qoq3', 0) or 0),
                    'rev_qoq4': float(r2.get('rev_qoq4', 0) or 0),
                    'np_qoq1': float(r2.get('np_qoq1', 0) or 0),
                    'np_qoq2': float(r2.get('np_qoq2', 0) or 0),
                    'np_qoq3': float(r2.get('np_qoq3', 0) or 0),
                    'np_qoq4': float(r2.get('np_qoq4', 0) or 0),
                    'rev_weighted': float(r2.get('rev_weighted', 0) or 0),
                    'np_weighted': float(r2.get('np_weighted', 0) or 0),
                    'gross_margin': float(r2.get('gross_margin', 0)) if pd.notna(r2.get('gross_margin')) else None,
                    'cash_ratio': float(r2.get('cash_ratio', 0)) if pd.notna(r2.get('cash_ratio')) else None,
                    'debt_to_assets': float(r2.get('debt_to_assets', 0)) if pd.notna(r2.get('debt_to_assets')) else None,
                    'roe': float(r2.get('roe', 0)) if pd.notna(r2.get('roe')) else None,
                    'fc_type': str(r2.get('fc_type', '')) if pd.notna(r2.get('fc_type')) else '',
                    'fc_p_min': float(r2.get('fc_p_min', 0)) if pd.notna(r2.get('fc_p_min')) else None,
                }
    except:
        report['growth'] = {'analysis_date': DATE, }

    # 5. Consensus
    try:
        eps = cache.get_consensus_eps(code)
        if eps:
            report['consensus'] = {k: v for k, v in eps.items() if k != 'historical'}
            if eps.get('historical'): report['consensus']['hist_eps'] = eps['historical'][-5:]
    except:
        report['consensus'] = {}

    # 6. WACC + Risk
    try:
        from TG_trading_sys.valuation.wacc import estimate_wacc
        w = estimate_wacc(code)
        report['wacc'] = {'wacc': w.get('wacc', 0), 'ke': w.get('ke', 0),
                          'beta': w.get('beta', 0), 'd_e_ratio': w.get('d_e_ratio', 0)}
    except:
        report['wacc'] = {}

    try:
        from TG_trading_sys.risk.var import calc_var
        if kline is not None and len(kline) >= 60:
            rets = kline['close'].pct_change().dropna()
            var95 = calc_var(rets, method='historical', confidence=0.95)
            report['risk'] = {
                'var_95_pct': var95.get('var_pct', 0) if isinstance(var95, dict) else 0,
                'annual_vol': round(float(rets.std() * np.sqrt(252) * 100), 1),
            }
    except:
        report['risk'] = {}

    # 7. Research + PDF
    research = collect_research(code, cache=cache)
    pdf_extracts = download_and_extract_reports(code, research.get('reports', []), max_pdfs=3)
    research['pdf_extracts'] = pdf_extracts
    cur_price = report.get('basic', {}).get('price', 0)
    cur_pe = report.get('basic', {}).get('pe_ttm', 0)
    research_synth = synthesize_research(research, current_price=cur_price, pe_ttm=cur_pe)
    research['synthesis'] = research_synth
    report['research'] = research
    stats = research.get('stats')
    if stats:
        print(f'  研报: {stats["total"]}篇 PDF×{len([p for p in pdf_extracts if p.get("full_text")])}')

    # 8. Business + F10
    biz_data = collect_business(code, cache=cache)
    f10_data = collect_f10_summary(code)
    biz_data['f10_tips'] = f10_data.get('latest_tips', '')
    biz_data['f10_events'] = f10_data.get('company_events', '')
    report['business'] = biz_data

    # 9. Moneyflow (东财)
    mf = collect_moneyflow(code)
    report['moneyflow'] = mf

    # 9b. Tushare moneyflow (主力资金流 — 参考 参考代码/资金流/moneyflow_summary.py)
    if tushare_mf_available:
        ts_code_match = f'{code}.SH' if code.startswith('6') else f'{code}.SZ'
        trend = mf_trend.get(ts_code_match, {})

        # 资金-价格共振信号
        flow_price_signal = 'neutral'
        if trend and kline is not None and len(kline) >= 5:
            price_5d_chg = float(kline['close'].iloc[-1] / kline['close'].iloc[-6] - 1) * 100 if len(kline) >= 6 else 0
            net_5d = trend.get('net_mf_5d', 0)
            if net_5d > 1e6 and price_5d_chg > 1:
                flow_price_signal = '共振看多'
            elif net_5d < -1e6 and price_5d_chg < -1:
                flow_price_signal = '共振看空'
            elif net_5d > 1e6 and price_5d_chg < -1:
                flow_price_signal = '背离_主力逆势吸筹'
            elif net_5d < -1e6 and price_5d_chg > 1:
                flow_price_signal = '背离_主力趁高出货'

        if trend:
            cons_in = trend.get('consecutive_in', 0)
            net_5d = trend.get('net_mf_5d', 0)
            if cons_in >= 3 and net_5d > 0:
                mf_verdict = '主力积极做多'
            elif cons_in >= 2 and net_5d > 0:
                mf_verdict = '主力偏多'
            elif trend.get('consecutive_out', 0) >= 3:
                mf_verdict = '主力持续出逃'
            elif net_5d < 0:
                mf_verdict = '主力偏空'
            else:
                mf_verdict = '主力中性'

            report['moneyflow_tushare'] = {
                'verdict': mf_verdict,
                'flow_price_signal': flow_price_signal,
                '统计期': trend.get('period', ''),
                'trend': {
                    '主力净额5日_万': round(net_5d / 1e4, 1),
                    '大单净额5日_万': round(trend.get('net_lg_5d', 0) / 1e4, 1),
                    '特大单净额5日_万': round(trend.get('net_elg_5d', 0) / 1e4, 1),
                    '散户净额5日_万': round(trend.get('net_sm_5d', 0) / 1e4, 1),
                    '连续流入天数': cons_in,
                    '连续流出天数': trend.get('consecutive_out', 0),
                    '大单买入占比': trend.get('big_order_ratio', 0),
                    '累计20日主力净额_万': round(trend.get('net_mf_20d', 0) / 1e4, 1),
                },
                # 频率统计
                '频率统计': {
                    '统计天数': trend.get('days_count', 0),
                    '主力净流入天数': trend.get('big_in_days', 0),
                    '主力净流出天数': trend.get('big_out_days', 0),
                    '主力流入占比': str(round(trend.get('big_in_ratio', 0) * 100)) + '%',
                    '主力累计净额_万': round(trend.get('total_big_net', 0) / 1e4, 1),
                    '主力流入强度': str(round(trend.get('intensity', 0) * 100, 2)) + '%',
                    '近5日主力净额_万': round(trend.get('big_net_5d', 0) / 1e4, 1),
                    '趋势一致性': '一致' if trend.get('trend_consistent') else '背离',
                }
            }
        else:
            report['moneyflow_tushare'] = {'verdict': '无Tushare数据', 'flow_price_signal': 'neutral'}
    else:
        report['moneyflow_tushare'] = {'verdict': 'Tushare不可用'}

    # 10. VPA
    mf_rows = mf.get('flow_data', [])
    float_mv = (report.get('basic', {}).get('mcap_yi', 0) or 0) * 1e4
    vpa_result = analyze_volume_price_vpa(kline, moneyflow_rows=mf_rows, float_mv=float_mv)
    report['vpa'] = vpa_result
    if vpa_result.get('vpa_available'):
        rat = vpa_result.get('rating', {})
        print(f'  VPA: {rat.get("rating", "?")}/{rat.get("score", "?")}')

    all_reports[code] = report
    time.sleep(0.8)

# 输出
os.makedirs('data/deep_reports', exist_ok=True)
with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
    json.dump(all_reports, f, ensure_ascii=False, indent=2)

print(f'\n{"="*60}')
print(f'  Round 4 完成: {OUTPUT_JSON} ({os.path.getsize(OUTPUT_JSON)/1024:.0f} KB)')
print(f'  共 {len(all_reports)} 只标的深度分析')
