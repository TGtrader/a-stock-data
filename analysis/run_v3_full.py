"""
V3 全量重跑: 价格锁定 2026-07-28
================================
1. 修补 DataCache 让价格从K线提取（非腾讯实时价）
2. 调用 report_v3_collect 的函数采集12只 × 11模块
3. 调用 report_v3_html 生成报告
"""
import sys, os, io, json, time
os.environ['PYTHONIOENCODING'] = 'utf-8'
sys.path.insert(0, '.')
if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import numpy as np
import pandas as pd
from datetime import datetime

PRICE_DATE = '2026-07-28'
OUTPUT_JSON = 'data/deep_reports/all_reports_v3.json'
OUTPUT_HTML = 'data/deep_reports/A股科技成长_V3_深度分析.html'

print('=' * 60)
print(f'  V3 全量重跑 — 基准日 {PRICE_DATE}')
print('=' * 60)

# ═══════════════════════════════════
# 修补: 价格锁定DataCache
# ═══════════════════════════════════
from TG_trading_sys.data.cache import DataCache as _OrigCache

_orig_get_stock_basic = _OrigCache.get_stock_basic
_orig_get_kline = _OrigCache.get_kline

def _patched_get_stock_basic(self, code, force_refresh=False, use_cache_price=True):
    result = _orig_get_stock_basic(self, code, force_refresh=force_refresh)
    if not result: return None
    try:
        kline = _orig_get_kline(self, code, lookback=30)
        if kline is not None and len(kline) > 0:
            mask = kline.index <= PRICE_DATE
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
        mask = kline.index <= PRICE_DATE
        if mask.any(): return kline[mask].copy()
    return kline

_OrigCache.get_stock_basic = _patched_get_stock_basic
_OrigCache.get_kline = _patched_get_kline

# 替换 TG_trading_sys 内部引用
import TG_trading_sys.data.cache as cache_mod
cache_mod.DataCache.get_stock_basic = _patched_get_stock_basic
cache_mod.DataCache.get_kline = _patched_get_kline

print(f'已修补 DataCache: 价格锁定到 {PRICE_DATE}')

# ═══════════════════════════════════
# Step 1: 导入采集函数 + 标的池
# ═══════════════════════════════════
# 从 report_v3_collect 导入函数（不触发模块级循环）
import analysis.report_v3_collect as collector

# 标的重设为12只精选
PICKS = collector.PICKS
collect_research = collector.collect_research
collect_business = collector.collect_business
collect_moneyflow = collector.collect_moneyflow
analyze_volume_price_vpa = collector.analyze_volume_price_vpa
VPA_AVAILABLE = collector.VPA_AVAILABLE

cache = _OrigCache()
all_reports = {}

print(f'\n[Step 1/2] 深度数据采集 — {len(PICKS)}只 × 11模块')
vpa_status = "已加载" if VPA_AVAILABLE else "不可用(简化模式)"
print(f'VPA引擎: {vpa_status}')
print('-' * 60)

for idx, (code, name, sw2, biz, comp, edge, plan, risk) in enumerate(PICKS):
    print(f'\n[{idx+1}/{len(PICKS)}] {code} {name}')
    report = {
        'code': code, 'name': name, 'sw2': sw2,
        'biz_hardcoded': biz, 'comp_hardcoded': comp,
        'edge_hardcoded': edge, 'plan_hardcoded': plan, 'risk_hardcoded': risk,
        'analysis_date': PRICE_DATE,
    }

    # 1. Basic info (price-locked)
    try:
        basic = cache.get_stock_basic(code, force_refresh=True)
        report['basic'] = {
            'price': basic.get('price', 0) if basic else 0,
            'pe_ttm': basic.get('pe_ttm', 0) if basic else 0,
            'pb': basic.get('pb', 0) if basic else 0,
            'mcap_yi': basic.get('mcap_yi', 0) if basic else 0,
            'industry': basic.get('industry', '') if basic else '',
        }
    except Exception:
        report['basic'] = {}

    # 2. K-line + Technical
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
                'kline_rows': len(kline),
                'ma_score': ma.get('score', 50),
                'ma_verdict': ma.get('verdict', ''),
                'ma_alignment': ma.get('ma_alignment', {}).get('state', ''),
                'verdict': verdict.verdict,
                'verdict_score': verdict.score,
                'confidence': verdict.confidence,
                'position_advice': verdict.position_advice,
            }
    except Exception:
        report['technical'] = {}

    # 3. Valuation
    try:
        from TG_trading_sys.valuation.val_report import val_report
        val = val_report(code)
        report['valuation'] = {
            'final_value': val.get('final_value'),
            'current_price': val.get('current_price', 0),
            'margin_of_safety_pct': val.get('margin_of_safety_pct'),
            'margin_verdict': val.get('margin_of_safety_verdict', ''),
            'dcf_per_share': val.get('dcf', {}).get('per_share_value'),
            'peg_value': val.get('relative', {}).get('peg_value', {}),
            'pb_roe_value': val.get('relative', {}).get('pb_roe_value', {}),
            'research_consensus': val.get('relative', {}).get('research_consensus', {}),
            'scenarios': val.get('scenarios', {}),
            'earnings': val.get('earnings', {}),
            'estimate_components': val.get('estimate_components', []),
        }
        mos = val.get('margin_of_safety_pct')
        print(f'  估值: {val.get("final_value", "N/A")} | 安全边际={mos:.1f}%' if mos else f'  估值: {val.get("final_value", "N/A")}')
    except Exception as e:
        print(f'  估值ERROR: {e}')
        report['valuation'] = {}

    # 4. Financials
    try:
        fin = {}
        from TG_trading_sys.valuation.wacc import _extract_number
        lrb_data = cache.get_financials(code, report_type='lrb', force_refresh=True)
        if lrb_data:
            annual_lrb = next((r for r in lrb_data if '12-31' in str(r.get('report_date', ''))), None)
            if annual_lrb is None and lrb_data: annual_lrb = lrb_data[0]
            if annual_lrb:
                fin['key_metrics'] = {
                    'revenue': _extract_number(annual_lrb, '营业收入') or _extract_number(annual_lrb, '营业总收入'),
                    'net_profit': _extract_number(annual_lrb, '归属于母公司股东的净利润') or _extract_number(annual_lrb, '净利润'),
                    'report_period': annual_lrb.get('report_date', ''),
                }
            fin['lrb'] = {'reports': len(lrb_data)}
        fzb_data = cache.get_financials(code, report_type='fzb', force_refresh=True)
        if fzb_data:
            annual_fzb = next((r for r in fzb_data if '12-31' in str(r.get('report_date', ''))), None)
            if annual_fzb is None and fzb_data: annual_fzb = fzb_data[0]
            if annual_fzb:
                ta = _extract_number(annual_fzb, '资产总计')
                eq = _extract_number(annual_fzb, '归属于母公司股东权益合计') or _extract_number(annual_fzb, '所有者权益合计')
                fin['balance'] = {
                    'total_assets': ta, 'equity': eq,
                    'cash': _extract_number(annual_fzb, '货币资金'),
                    'debt_ratio': round((1 - eq / ta) * 100, 1) if (ta and eq and ta > 0) else None,
                    'report_period': annual_fzb.get('report_date', ''),
                }
            fin['fzb'] = {'reports': len(fzb_data)}
        llb_data = cache.get_financials(code, report_type='llb', force_refresh=True)
        if llb_data: fin['llb'] = {'reports': len(llb_data)}
        report['financials'] = fin
    except Exception as e:
        print(f'  财务ERROR: {e}')
        report['financials'] = {}

    # 5. Consensus EPS
    try:
        eps = cache.get_consensus_eps(code)
        if eps:
            report['consensus'] = {k: v for k, v in eps.items() if k != 'historical'}
            if eps.get('historical'): report['consensus']['hist_eps'] = eps['historical'][-5:]
    except Exception:
        report['consensus'] = {}

    # 6. WACC
    try:
        from TG_trading_sys.valuation.wacc import estimate_wacc
        w = estimate_wacc(code)
        report['wacc'] = {'wacc': w.get('wacc', 0), 'ke': w.get('ke', 0), 'kd': w.get('kd', 0),
                          'beta': w.get('beta', 0), 'd_e_ratio': w.get('d_e_ratio', 0)}
    except Exception:
        report['wacc'] = {}

    # 7. Risk
    try:
        from TG_trading_sys.risk.var import calc_var
        if kline is not None and len(kline) >= 60:
            rets = kline['close'].pct_change().dropna()
            var95 = calc_var(rets, method='historical', confidence=0.95)
            report['risk'] = {
                'var_95_pct': var95.get('var_pct', 0) if isinstance(var95, dict) else 0,
                'cvar_95_pct': var95.get('cvar_pct', var95.get('var_pct', 0) * 1.5) if isinstance(var95, dict) else 0,
                'annual_vol': round(float(rets.std() * np.sqrt(252) * 100), 1),
            }
    except Exception:
        report['risk'] = {}

    # 8. Research reports
    research = collect_research(code, cache=cache)
    # 研报PDF下载+文本提取（最近3篇）
    from analysis.report_v3_collect import synthesize_research, download_and_extract_reports
    reports_list = research.get('reports', [])
    pdf_extracts = download_and_extract_reports(code, reports_list, max_pdfs=3) if reports_list else []
    research['pdf_extracts'] = pdf_extracts
    # 研报观点综合（现在包含PDF正文分析）
    cur_price = report.get('basic', {}).get('price', 0)
    cur_pe = report.get('basic', {}).get('pe_ttm', 0)
    research_synth = synthesize_research(research, current_price=cur_price, pe_ttm=cur_pe)
    research['synthesis'] = research_synth
    report['research'] = research
    stats = research.get('stats')
    if stats:
        buys = stats.get('rating_dist', {}).get('买入', 0)
        pdf_count = len([p for p in pdf_extracts if p.get('full_text')])
        if research_synth:
            print(f'  研报: {stats["total"]}篇 买入{buys}家 PDF×{pdf_count} | {research_synth["rating_consensus"]}')
        else:
            print(f'  研报: {stats["total"]}篇 买入{buys}家 PDF×{pdf_count}')
    else:
        print(f'  研报: 无数据')

    # 9. Business description + F10 summary
    biz_data = collect_business(code, cache=cache)
    from analysis.report_v3_collect import collect_f10_summary
    f10_data = collect_f10_summary(code)
    biz_data['f10_tips'] = f10_data.get('latest_tips', '')
    biz_data['f10_events'] = f10_data.get('company_events', '')
    report['business'] = biz_data
    has_f10 = len(f10_data.get('latest_tips', '')) > 50
    print(f'  业务: {biz_data["source"]} F10={has_f10} ({len(biz_data["f10_summary"])}字)')

    # 10. Money flow
    mf = collect_moneyflow(code)
    report['moneyflow'] = mf
    mf_stats = mf.get('stats')
    if mf_stats:
        print(f'  资金流: {mf_stats["data_days"]}日 20日主力{mf_stats["direction"]}{abs(mf_stats["main_net_20d_yi"]):.2f}亿')
    else:
        print(f'  资金流: 无数据')

    # 11. VPA
    mf_rows = mf.get('flow_data', [])
    float_mv = (report.get('basic', {}).get('mcap_yi', 0) or 0) * 1e4
    vpa_result = analyze_volume_price_vpa(kline, moneyflow_rows=mf_rows, float_mv=float_mv)
    report['vpa'] = vpa_result
    if vpa_result.get('vpa_available'):
        rat = vpa_result.get('rating', {})
        sig_count = len(vpa_result.get('signals', {}).get('recent_signals', []))
        print(f'  VPA: {rat.get("rating", "?")}/{rat.get("score", "?")}分 信号{sig_count}条')
    else:
        sim = vpa_result.get('simple', {})
        print(f'  VPA: 简化模式{" 量比"+str(sim.get("vol_ratio_5v20",1)) if sim else " 无数据"}')

    all_reports[code] = report
    time.sleep(1.0)  # 风控间隔

# 输出JSON
os.makedirs('data/deep_reports', exist_ok=True)
with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
    json.dump(all_reports, f, ensure_ascii=False, indent=2)

size_kb = os.path.getsize(OUTPUT_JSON) / 1024
print(f'\n{"=" * 60}')
print(f'[Step 1/2] 采集完成: {OUTPUT_JSON} ({size_kb:.0f} KB)')
print(f'共 {len(all_reports)} 只标的, 每只含11个分析模块')

# ═══════════════════════════════════
# Step 2: HTML报告生成
# ═══════════════════════════════════
print(f'\n[Step 2/2] 生成V3 HTML报告...')
# 直接执行HTML生成器（它会读取 all_reports_v3.json）
exec(open('analysis/report_v3_html.py', encoding='utf-8').read())

print(f'\n{"=" * 60}')
print(f'  ✅ V3 全量重跑完成！')
print(f'  价格基准日: {PRICE_DATE}')
print(f'  数据: {OUTPUT_JSON} ({os.path.getsize(OUTPUT_JSON)/1024:.0f} KB)')
print(f'  报告: {OUTPUT_HTML} ({os.path.getsize(OUTPUT_HTML)/1024:.0f} KB)')
print(f'{"=" * 60}')
