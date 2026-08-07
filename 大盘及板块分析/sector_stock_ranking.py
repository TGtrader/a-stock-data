"""
科技板块+个股综合排名分析
========================
1. 板块抗跌排名(东财行业板块+主力资金流向)
2. 个股综合排名(趋势+VPA量价+资金流+技术形态+波动)
"""
import sys, os, time, json
sys.path.insert(0, '.')
import pandas as pd
import numpy as np
import requests
from datetime import datetime, timedelta

from index_data import INDICES, fetch_all_indices_daily, fetch_moneyflow_trend
from index_technical import comprehensive_technical
from index_agents import run_all_agents, _VPA_AVAILABLE, _vpa_trend, _vpa_signals

DATE = datetime.now().strftime('%Y%m%d')
TECH_INDUSTRIES = ['半导体','软件服务','通信设备','IT设备','互联网',
                   '元器件','电气设备','专用机械','电器仪表',
                   '医疗保健','生物制药','化学制药','航空']

# ═══════════════════════════════
# 1. 板块分析(基于Round2个股聚合)
# ═══════════════════════════════
def get_tech_sectors_from_stocks(stock_results):
    """从个股排名数据聚合到行业板块评分"""
    from collections import defaultdict
    sectors = defaultdict(lambda: {'count':0,'total_chg':0,'total_mf':0,'total_vpa':0,
                                     'total_tech':0,'total_vol':0,'total_composite':0})

    for s in stock_results:
        ind = s.get('industry','')
        if not ind: continue
        sec = sectors[ind]
        sec['count'] += 1
        sec['total_chg'] += s.get('chg_10d',0)
        sec['total_mf'] += s['mf_score']['score']
        sec['total_vpa'] += s['vpa_score']['score']
        sec['total_tech'] += s['tech_score']['score']
        sec['total_vol'] += s['vol_score']['score']
        sec['total_composite'] += s['composite']

    results = []
    for ind, sec in sectors.items():
        n = sec['count']
        if n < 1: continue
        avg_chg = sec['total_chg'] / n
        avg_mf = sec['total_mf'] / n
        avg_vpa = sec['total_vpa'] / n
        avg_tech = sec['total_tech'] / n
        avg_comp = sec['total_composite'] / n
        # 综合板块评分: 涨跌(30%) + 资金流(25%) + VPA(20%) + 技术(15%) + 数量(10% bonus)
        score = avg_chg * 0.3 + avg_mf * 0.25 + avg_vpa * 0.2 + avg_tech * 0.15 + min(n*2, 10)
        results.append({
            'name': ind, 'count': n,
            'avg_chg': round(avg_chg, 2), 'avg_mf': round(avg_mf, 1),
            'avg_vpa': round(avg_vpa, 1), 'avg_tech': round(avg_tech, 1),
            'avg_composite': round(avg_comp, 1), 'score': round(score, 1),
        })
    return sorted(results, key=lambda x: -x['score'])


# ═══════════════════════════════
# 2. 个股综合排名
# ═══════════════════════════════
def fetch_stock_moneyflow_batch(codes, days=10):
    """批量获取个股近N日资金流"""
    try:
        import tushare as ts
        from TG_trading_sys.core.config import Config
        token = Config.get_tushare_token()
        ts.set_token(token)
        pro = ts.pro_api()

        all_data = {}
        for lookback in range(days):
            try_date = (datetime.now() - timedelta(days=lookback)).strftime('%Y%m%d')
            try:
                df = pro.moneyflow(trade_date=try_date)
                if df is not None and len(df) > 0:
                    for _, r in df.iterrows():
                        ts_code = r['ts_code']
                        if ts_code not in all_data:
                            all_data[ts_code] = []
                        all_data[ts_code].append({
                            'date': try_date,
                            'net_mf': float(r.get('net_mf_amount',0) or 0),
                            'buy_lg': float(r.get('buy_lg_amount',0) or 0),
                            'sell_lg': float(r.get('sell_lg_amount',0) or 0),
                            'buy_elg': float(r.get('buy_elg_amount',0) or 0),
                            'sell_elg': float(r.get('sell_elg_amount',0) or 0),
                        })
            except: pass
            time.sleep(0.25)
        return all_data
    except Exception as e:
        print(f'资金流批量获取失败: {e}')
    return {}


def score_stock_moneyflow(mf_records):
    """资金流评分"""
    if not mf_records: return {'score': 50, 'detail': '无数据'}
    nets = [r['net_mf'] for r in mf_records]
    big_nets = [(r['buy_lg']+r['buy_elg']-r['sell_lg']-r['sell_elg']) for r in mf_records]
    total_net = sum(nets)
    total_big = sum(big_nets)
    in_days = sum(1 for n in nets if n > 0)
    out_days = sum(1 for n in nets if n < 0)
    in_ratio = in_days / len(nets) * 100 if nets else 50
    # 评分
    score = 50
    if total_big > 1e4: score += 20       # 净流入>1亿(万元单位)
    elif total_big > 1000: score += 10    # >1000万
    elif total_big < -1e4: score -= 20
    elif total_big < -1000: score -= 10
    if in_ratio > 70: score += 15
    elif in_ratio > 50: score += 5
    elif in_ratio < 30: score -= 15
    # Tushare moneyflow单位是万元, total_big已是万元
    score = max(0, min(100, score))
    if abs(total_big) >= 1e4:
        flow_str = f'{abs(total_big)/1e4:.1f}亿'
    else:
        flow_str = f'{abs(total_big):.0f}万'
    return {'score': score, 'total_big_net': round(total_big, 1), 'in_ratio': round(in_ratio,1),
            'in_days': in_days, 'out_days': out_days, 'detail': f'主力{"净流入" if total_big>0 else "净流出"}{flow_str}, {in_days}/{len(nets)}天流入'}


def score_stock_vpa(kline_df):
    """VPA量价评分(威科夫)"""
    if not _VPA_AVAILABLE or kline_df is None or len(kline_df) < 30:
        return {'score': 50, 'phase': 'N/A', 'detail': 'VPA不可用'}
    try:
        df_v = kline_df.copy()
        if 'vol' in df_v.columns: df_v = df_v.rename(columns={'vol':'volume'})
        if not hasattr(df_v.index, 'strftime'):
            df_v.index = pd.to_datetime(df_v.index)
        trend = _vpa_trend(df_v)
        signals = _vpa_signals(df_v)
        phase = trend.get('phase',{}).get('phase','')
        st_dir = trend.get('short_term',{}).get('direction','')
        st_str = trend.get('short_term',{}).get('strength',0)
        recent = signals.get('recent_signals',[])
        # Count types
        sig_counts = {}
        for s in recent[:12]:
            t = s['type']; sig_counts[t] = sig_counts.get(t,0)+1
        rev = sum(v for k,v in sig_counts.items() if '反转' in k or '衰竭' in k)
        cont = sum(v for k,v in sig_counts.items() if '延续' in k or '启动' in k)

        score = 50
        if '吸筹' in phase: score += 20
        elif '上涨' in phase: score += 15
        elif '派发' in phase: score -= 20
        elif '下跌' in phase: score -= 15
        if st_dir == '上涨' and st_str > 30: score += 10
        elif st_dir == '下跌' and st_str > 30: score -= 10
        if cont > rev: score += 10
        elif rev > cont: score -= 10
        score = max(0, min(100, score))
        return {'score': score, 'phase': phase, 'st_dir': st_dir, 'st_str': st_str,
                'signals': f'延续{cont}/反转{rev}', 'detail': f'威科夫:{phase} 趋势:{st_dir}{st_str} 信号:延续{cont}反转{rev}'}
    except: return {'score': 50, 'phase': '?', 'detail': 'VPA异常'}


def score_stock_technical(kline_df):
    """技术形态评分"""
    if kline_df is None or len(kline_df) < 20:
        return {'score': 50, 'detail': '数据不足'}
    try:
        tech = comprehensive_technical(kline_df)
        score = 50
        ma_align = tech.get('ma_alignment','')
        macd_sig = tech.get('macd',{}).get('signal','')
        rsi = tech.get('rsi',50)
        boll = tech.get('bollinger',{})

        if ma_align == '多头排列': score += 15
        elif ma_align == '空头排列': score -= 15
        if '金叉' in macd_sig: score += 10
        elif '死叉' in macd_sig: score -= 10
        if 30 < rsi < 70: score += 5
        if boll.get('status') == '下轨附近': score += 5
        elif boll.get('status') == '上轨附近': score -= 5
        score = max(0, min(100, score))
        return {'score': score, 'ma': ma_align, 'macd': macd_sig, 'rsi': rsi,
                'boll': boll.get('status',''), 'detail': ma_align + ' MACD:' + macd_sig + ' RSI:' + str(rsi) + ' 布林:' + str(boll.get('status',''))}
    except: return {'score': 50, 'detail': '计算异常'}


def score_stock_volatility(kline_df):
    """波动率评分(低波动=高分)"""
    if kline_df is None or len(kline_df) < 20:
        return {'score': 50, 'detail': '数据不足'}
    try:
        ret = kline_df['close'].pct_change().dropna()
        vol_20 = float(ret.iloc[-20:].std() * np.sqrt(252) * 100) if len(ret)>=20 else 50
        score = 100 - min(vol_20 * 2, 50)
        return {'score': round(score,1), 'vol_20d': round(vol_20,1),
                'detail': f'年化波幅{vol_20:.1f}%'}
    except: return {'score': 50, 'detail': '计算异常'}


def comprehensive_stock_ranking(r2_csv='data/screen_v4_round2.csv', top_n=20):
    """个股综合排名"""
    print('加载Round 2股票池...')
    r2 = pd.read_csv(r2_csv)
    codes = r2.head(150)['ts_code'].tolist()  # Top 150 for efficiency
    print(f'  股票池: {len(codes)} 只')

    # 批量获取K线+资金流
    print('获取K线+资金流数据...')
    import tushare as ts
    from TG_trading_sys.core.config import Config
    token = Config.get_tushare_token()
    ts.set_token(token)
    pro = ts.pro_api()
    kline_cache = {}
    mf_cache = {}

    # 批量资金流
    mf_batch = fetch_stock_moneyflow_batch(codes, 10)
    print(f'  资金流: {len(mf_batch)} 只有数据')

    results = []
    for i, ts_code in enumerate(codes):
        pure_code = ts_code.split('.')[0].zfill(6)
        name = r2[r2['ts_code']==ts_code]['name'].values[0] if len(r2[r2['ts_code']==ts_code])>0 else ''
        industry = r2[r2['ts_code']==ts_code]['industry'].values[0] if len(r2[r2['ts_code']==ts_code])>0 else ''
        r2_score = r2[r2['ts_code']==ts_code]['score_total'].values[0] if len(r2[r2['ts_code']==ts_code])>0 else 0

        if (i+1) % 50 == 0: print(f'    {i+1}/{len(codes)}...')

        # K线
        try:
            df = pro.daily(ts_code=ts_code, limit=120,
                fields='ts_code,trade_date,open,high,low,close,vol,amount')
            df = df.sort_values('trade_date')
            for c in ['open','high','low','close','vol']: df[c]=pd.to_numeric(df[c],errors='coerce')
            df['trade_date']=pd.to_datetime(df['trade_date'])
            df=df.set_index('trade_date').sort_index()
        except:
            df = None
        if df is None or len(df) < 20: continue

        # 资金流评分
        mf_records = mf_batch.get(ts_code, [])
        mf_score = score_stock_moneyflow(mf_records)
        # VPA评分
        vpa_score = score_stock_vpa(df)
        # 技术评分
        tech_score = score_stock_technical(df)
        # 波动评分
        vol_score = score_stock_volatility(df)
        # 趋势评分(近10日涨跌)
        if len(df) >= 10:
            chg_10 = (df['close'].iloc[-1] - df['close'].iloc[-10]) / df['close'].iloc[-10] * 100
            trend_score = min(100, max(0, 50 + chg_10 * 3))
        else:
            chg_10 = 0; trend_score = 50

        # 综合评分
        composite = (mf_score['score'] * 0.25 + vpa_score['score'] * 0.20 +
                    tech_score['score'] * 0.20 + vol_score['score'] * 0.15 +
                    trend_score * 0.15 + r2_score * 0.05)
        composite = round(composite, 1)

        results.append({
            'ts_code': ts_code, 'code': pure_code, 'name': name, 'industry': industry,
            'close': float(df['close'].iloc[-1]),
            'chg_10d': round(chg_10, 2),
            'r2_score': int(r2_score),
            'mf_score': mf_score, 'vpa_score': vpa_score,
            'tech_score': tech_score, 'vol_score': vol_score,
            'trend_score': round(trend_score, 1),
            'composite': composite,
        })
        time.sleep(0.2)

    results.sort(key=lambda x: -x['composite'])
    return results[:top_n]
