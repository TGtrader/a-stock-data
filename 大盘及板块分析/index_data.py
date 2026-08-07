"""
指数数据获取模块
===============
日线: Tushare index_daily (300日)
分钟线: mootdx (5min/30min) — 不稳定,有降级
资金流: Tushare moneyflow_mkt_dc (市场整体)
北向: Eastmoney KAMT
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import time, json

# 7大指数定义
INDICES = {
    '000001.SH': {'name': '上证指数', 'short': '上证', 'mootdx_code': '000001', 'market': 'SH'},
    '399001.SZ': {'name': '深证成指', 'short': '深成指', 'mootdx_code': '399001', 'market': 'SZ'},
    '399006.SZ': {'name': '创业板指', 'short': '创业板', 'mootdx_code': '399006', 'market': 'SZ'},
    '000688.SH': {'name': '科创50', 'short': '科创50', 'mootdx_code': '000688', 'market': 'SH'},
    '000300.SH': {'name': '沪深300', 'short': '沪深300', 'mootdx_code': '000300', 'market': 'SH'},
    '000852.SH': {'name': '中证1000', 'short': '中证1000', 'mootdx_code': '000852', 'market': 'SH'},
    '000510.SH': {'name': '中证A500', 'short': 'A500', 'mootdx_code': '000510', 'market': 'SH'},
}


def fetch_index_daily(ts_code, lookback=300):
    """Tushare获取指数日线K线"""
    try:
        import tushare as ts
        from TG_trading_sys.core.config import Config
        token = Config.get_tushare_token()
        ts.set_token(token)
        pro = ts.pro_api()
        df = pro.index_daily(ts_code=ts_code, limit=lookback,
                             fields='ts_code,trade_date,open,high,low,close,vol,amount,pct_chg')
        if df is not None and len(df) > 0:
            df = df.sort_values('trade_date')
            for c in ['open','high','low','close','vol','amount','pct_chg']:
                df[c] = pd.to_numeric(df[c], errors='coerce')
            df.set_index('trade_date', inplace=True)
            return df
    except Exception as e:
        print(f'    Tushare {ts_code} error: {e}')
    return None


def fetch_all_indices_daily(lookback=300):
    """获取所有指数的日线数据"""
    print(f'获取7大指数日线数据({lookback}日)...')
    data = {}
    for ts_code, info in INDICES.items():
        df = fetch_index_daily(ts_code, lookback)
        if df is not None and len(df) > 0:
            data[ts_code] = df
            print(f'  {info["name"]}({ts_code}): {len(df)}日, 最新{df.index[-1]}')
        else:
            print(f'  {info["name"]}({ts_code}): 获取失败')
        time.sleep(0.2)
    return data


def fetch_index_minute(mootdx_code, freq=5, days=5):
    """mootdx获取指数分钟K线(不稳定)"""
    try:
        from mootdx.quotes import Quotes
        client = Quotes.factory(market='std')
        # mootdx bars: offset是往回取的条数
        # 每天240分钟/48条5分钟线 → 5天=240条
        n_bars = 48 * days if freq == 5 else 8 * days
        df = client.bars(symbol=mootdx_code, frequency=freq, offset=n_bars)
        if df is not None and len(df) > 0:
            df.columns = ['open','high','low','close','volume','amount','date']
            df['date'] = pd.to_datetime(df['date'])
            return df.sort_values('date')
    except Exception as e:
        print(f'    mootdx {mootdx_code} {freq}min error: {e}')
    return None


def fetch_market_moneyflow(date=None):
    """Tushare市场整体资金流"""
    if date is None:
        date = datetime.now().strftime('%Y%m%d')
    try:
        import tushare as ts
        from TG_trading_sys.core.config import Config
        token = Config.get_tushare_token()
        ts.set_token(token)
        pro = ts.pro_api()
        # 尝试最近几天
        for d in range(5):
            try_date = (datetime.now() - timedelta(days=d)).strftime('%Y%m%d')
            df = pro.moneyflow_mkt_dc(trade_date=try_date)
            if df is not None and len(df) > 0:
                return df.iloc[0].to_dict()
    except Exception as e:
        print(f'    市场资金流 error: {e}')
    return None


def fetch_northbound(lookback=20):
    """东财北向资金"""
    try:
        import requests
        url = 'https://push2his.eastmoney.com/api/qt/kamt.kline/get'
        params = {
            'fields1': 'f1,f2,f3,f4',
            'fields2': 'f51,f52,f53,f54',
            'klt': '101', 'lmt': str(lookback),
        }
        r = requests.get(url, params=params, timeout=10,
                        headers={'User-Agent': 'Mozilla/5.0'})
        data = r.json().get('data', {})
        klines = data.get('klines', [])
        rows = []
        for line in klines:
            parts = line.split(',')
            if len(parts) >= 4:
                rows.append({
                    'date': parts[0],
                    'hk2sh': float(parts[1]) / 1e4 if parts[1] != '-' else 0,
                    'hk2sz': float(parts[2]) / 1e4 if parts[2] != '-' else 0,
                    'total': float(parts[3]) / 1e4 if parts[3] != '-' else 0,
                })
        if rows:
            return rows
        # If Eastmoney returned empty, fall through to Tushare
    except Exception as e:
        print(f'    东财北向资金 error: {e}')

    # Fallback: Tushare moneyflow_hsgt
    try:
        import tushare as ts
        from TG_trading_sys.core.config import Config
        token = Config.get_tushare_token()
        ts.set_token(token)
        pro = ts.pro_api()
        df = pro.moneyflow_hsgt(start_date=(datetime.now() - timedelta(days=lookback+5)).strftime('%Y%m%d'),
                                end_date=datetime.now().strftime('%Y%m%d'))
        if df is not None and len(df) >= 2:
            df = df.sort_values('trade_date')
            rows = []
            for i in range(1, len(df)):
                # north_money是累计值, 差值=当日净流入(百万元→亿元)
                net = (float(df.iloc[i]['north_money']) - float(df.iloc[i-1]['north_money'])) / 100
                rows.append({
                    'date': str(df.iloc[i]['trade_date']),
                    'hk2sh': 0, 'hk2sz': 0,
                    'total': round(net, 1),
                })
            return rows
    except Exception as e2:
        print(f'    Tushare北向 fallback error: {e2}')
    return []


def fetch_moneyflow_trend(days=20):
    """Tushare市场主力资金近N日趋势"""
    try:
        import tushare as ts
        from TG_trading_sys.core.config import Config
        token = Config.get_tushare_token()
        ts.set_token(token)
        pro = ts.pro_api()
        df = pro.moneyflow_mkt_dc(
            start_date=(datetime.now() - timedelta(days=days+10)).strftime('%Y%m%d'),
            end_date=datetime.now().strftime('%Y%m%d'),
            fields='trade_date,net_amount,net_amount_rate,buy_elg_amount,buy_lg_amount,sell_elg_amount,sell_lg_amount')
        if df is not None and len(df) > 0:
            df = df.sort_values('trade_date')
            rows = []
            for _, r in df.iterrows():
                rows.append({
                    'date': str(r['trade_date']),
                    'net_amount': round(float(r['net_amount']) / 1e8, 1),  # 亿
                    'net_rate': round(float(r.get('net_amount_rate', 0)), 2),
                    'buy_big': round((float(r.get('buy_elg_amount', 0)) + float(r.get('buy_lg_amount', 0))) / 1e8, 1),
                    'sell_big': round((float(r.get('sell_elg_amount', 0)) + float(r.get('sell_lg_amount', 0))) / 1e8, 1),
                })
            return rows[-days:] if len(rows) > days else rows
    except Exception as e:
        print(f'    资金流趋势 error: {e}')
    return []


def fetch_margin_trend(days=20):
    """Tushare两融余额近N日趋势"""
    try:
        import tushare as ts
        from TG_trading_sys.core.config import Config
        token = Config.get_tushare_token()
        ts.set_token(token)
        pro = ts.pro_api()
        df = pro.margin(
            start_date=(datetime.now() - timedelta(days=days+10)).strftime('%Y%m%d'),
            end_date=datetime.now().strftime('%Y%m%d'),
            fields='trade_date,exchange_id,rzye,rzmre,rzche,rqye')
        if df is not None and len(df) > 0:
            # Sum SSE + SZSE per day
            df['rzye'] = pd.to_numeric(df['rzye'], errors='coerce')
            df['rzmre'] = pd.to_numeric(df['rzmre'], errors='coerce')
            df['rzche'] = pd.to_numeric(df['rzche'], errors='coerce')
            df['rqye'] = pd.to_numeric(df['rqye'], errors='coerce')
            daily = df.groupby('trade_date').agg({
                'rzye': 'sum', 'rqye': 'sum', 'rzmre': 'sum', 'rzche': 'sum'
            }).reset_index().sort_values('trade_date')
            rows = []
            for _, r in daily.iterrows():
                rows.append({
                    'date': str(r['trade_date']),
                    'rz_balance': round(float(r['rzye']) / 1e8, 1),      # 融资余额(亿)
                    'rq_balance': round(float(r['rqye']) / 1e8, 1),      # 融券余额(亿)
                    'total': round((float(r['rzye']) + float(r['rqye'])) / 1e8, 1),
                    'rz_buy': round(float(r['rzmre']) / 1e8, 1),         # 融资买入(亿)
                    'rz_repay': round(float(r['rzche']) / 1e8, 1),       # 融资偿还(亿)
                    'net_rz': round((float(r['rzmre']) - float(r['rzche'])) / 1e8, 1),
                })
            return rows[-days:] if len(rows) > days else rows
    except Exception as e:
        print(f'    两融趋势 error: {e}')
    return []


def fetch_margin_data(date=None):
    """Tushare两融数据(交易所级别)"""
    if date is None:
        date = datetime.now().strftime('%Y%m%d')
    try:
        import tushare as ts
        from TG_trading_sys.core.config import Config
        token = Config.get_tushare_token()
        ts.set_token(token)
        pro = ts.pro_api()
        for d in range(5):
            try_date = (datetime.now() - timedelta(days=d)).strftime('%Y%m%d')
            df = pro.margin(trade_date=try_date)
            if df is not None and len(df) >= 2:
                sse = df[df['exchange_id'] == 'SSE']
                szse = df[df['exchange_id'] == 'SZSE']
                if len(sse) > 0 and len(szse) > 0:
                    s = sse.iloc[0]; z = szse.iloc[0]
                    return {
                        'date': try_date,
                        'total_rz': round((float(s['rzye']) + float(z['rzye'])) / 1e8, 1),   # 融资余额(亿)
                        'total_rq': round((float(s['rqye']) + float(z['rqye'])) / 1e8, 1),   # 融券余额(亿)
                        'total_rzrq': round((float(s['rzrqye']) + float(z['rzrqye'])) / 1e8, 1), # 两融余额(亿)
                        'rz_buy': round((float(s['rzmre']) + float(z['rzmre'])) / 1e8, 1),   # 融资买入额(亿)
                        'rz_repay': round((float(s['rzche']) + float(z['rzche'])) / 1e8, 1),  # 融资偿还额(亿)
                        'net_rz': round((float(s['rzmre']) + float(z['rzmre']) - float(s['rzche']) - float(z['rzche'])) / 1e8, 1),  # 净融资买入
                    }
    except Exception as e:
        print(f'    两融数据 error: {e}')
    return None
