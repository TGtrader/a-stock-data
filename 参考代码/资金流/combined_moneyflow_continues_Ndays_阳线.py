# 选股脚本/run_combined_moneyflow_strategy.py
import pandas as pd
from sqlalchemy import create_engine
import sys
import os
from datetime import datetime
import tushare as ts
import sqlite3
import argparse

sys.path.append(r'D:\QUANT_SEEKING')
sys.path.append(r'D:\QUANT_SEEKING\过滤器')

from 策略库.moneyflow_conbine_THS_AND_TRIDITION import CombinedMoneyFlowStrategy
from 策略库.moneyinflow_continuous import MoneyFlowContinuousStrategy
from 策略库.THSMoneyFlowContinuousStrategy import THSMoneyFlowContinuousStrategy
from 过滤器.st_stock_filter import STStockFilter

ts.set_token('53399fa4a4f51a769a4455978feb0b04c88f87d5c916507a61131f34')
pro = ts.pro_api()

# ==================== 全局配置参数 ====================
CONFIG = {
    # 资金流策略配置
    "continuous_days": 3,           # 连续资金净流入天数
    "debug": True,                  # 开启调试输出，便于观察两个子策略的选股结果

    # 历史回顾配置
    "historical_review": {
        "enabled": True,
        "lookback_days": 20,
        "x_threshold": 3,
        "y_threshold": 10,
        "z_threshold": 2
    },

    # 连续阳线筛选配置
    "consecutive_up_days": [3, 4, 5],

    # 输出相关配置
    "output_base_dir": "everyday_moneyflow_compair_2or3days",
    "export_chinese_columns": True,
}

# ==================== 数据获取函数（不变） ====================
def fetch_trade_dates(engine, end_date, days):
    query = f"""
    SELECT DISTINCT trade_date FROM moneyflow_summary
    WHERE trade_date <= '{end_date}'
    ORDER BY trade_date DESC
    LIMIT {days}
    """
    df = pd.read_sql(query, engine)
    return sorted(df['trade_date'].tolist())

def fetch_moneyflow_data(engine, trade_dates):
    placeholders = ','.join([f"'{d}'" for d in trade_dates])
    query = f"""
    SELECT ts_code, trade_date, net_mf_amount, net_lg_amount, net_elg_amount
    FROM moneyflow_summary
    WHERE trade_date IN ({placeholders})
    """
    return pd.read_sql(query, engine)

def fetch_ths_data(engine, trade_dates):
    placeholders = ','.join([f"'{d}'" for d in trade_dates])
    query = f"""
    SELECT ts_code, trade_date, net_amount, buy_lg_amount
    FROM moneyflow_ths_data
    WHERE trade_date IN ({placeholders})
    """
    return pd.read_sql(query, engine)

def fetch_daily_data(engine, trade_dates, stock_list=None):
    placeholders = ','.join([f"'{d}'" for d in trade_dates])
    query = f"""
    SELECT ts_code, trade_date, open, high, low, close, pct_chg, vol, amount
    FROM daily_data
    WHERE trade_date IN ({placeholders})
    """
    if stock_list:
        codes_str = ','.join([f"'{c}'" for c in stock_list])
        query += f" AND ts_code IN ({codes_str})"
    return pd.read_sql(query, engine)

def fetch_basic_data(engine, trade_dates):
    placeholders = ','.join([f"'{d}'" for d in trade_dates])
    query = f"""
    SELECT ts_code, trade_date, circ_mv, total_mv, turnover_rate, pe
    FROM daily_basic_data
    WHERE trade_date IN ({placeholders})
    """
    return pd.read_sql(query, engine)

def prepare_multiindex_df(df, date_col='trade_date', stock_col='ts_code'):
    df = df.copy()
    df.set_index([date_col, stock_col], inplace=True)
    df.index.names = ['date', 'stock']
    df.sort_index(level=['date', 'stock'], inplace=True)
    return df

def build_traditional_history_data(engine, trade_dates):
    mf_df = fetch_moneyflow_data(engine, trade_dates)
    daily_df = fetch_daily_data(engine, trade_dates)
    basic_df = fetch_basic_data(engine, trade_dates)
    mf_multi = prepare_multiindex_df(mf_df)
    daily_multi = prepare_multiindex_df(daily_df)
    basic_multi = prepare_multiindex_df(basic_df)
    history = pd.concat([mf_multi, daily_multi, basic_multi], axis=1)
    numeric_cols = ['net_mf_amount', 'net_lg_amount', 'net_elg_amount',
                    'open', 'high', 'low', 'close', 'pct_chg', 'vol', 'amount',
                    'circ_mv', 'total_mv', 'turnover_rate', 'pe']
    for col in numeric_cols:
        if col in history.columns:
            history[col] = pd.to_numeric(history[col], errors='coerce').fillna(0)
    return history

# ==================== 指标计算函数 ====================
def calculate_additional_metrics(engine, qualified_stocks, analysis_date, history_data):
    codes_str = ','.join([f"'{code}'" for code in qualified_stocks])
    query_basic = f"""
    SELECT ts_code, name, market FROM stock_basic
    WHERE ts_code IN ({codes_str})
    """
    df_basic = pd.read_sql(query_basic, engine)
    query_industry = f"""
    SELECT ts_code, sw_industry FROM sw_industry
    WHERE ts_code IN ({codes_str})
    """
    df_ind = pd.read_sql(query_industry, engine)
    industry_dict = dict(zip(df_ind['ts_code'], df_ind['sw_industry']))

    results = []
    for ts_code in qualified_stocks:
        stock_data = history_data.xs(ts_code, level='stock')
        if analysis_date not in stock_data.index:
            continue
        today_data = stock_data.loc[analysis_date]
        float_mv = today_data.get('circ_mv', 0)

        daily_net = today_data.get('net_mf_amount', 0)
        daily_large = today_data.get('net_lg_amount', 0)
        daily_extra = today_data.get('net_elg_amount', 0)
        daily_large_extra = daily_large + daily_extra

        if float_mv > 0:
            daily_net_ratio = (daily_net / float_mv) * 100
            daily_large_ratio = (daily_large / float_mv) * 100
            daily_extra_ratio = (daily_extra / float_mv) * 100
            daily_large_extra_ratio = (daily_large_extra / float_mv) * 100
        else:
            daily_net_ratio = daily_large_ratio = daily_extra_ratio = daily_large_extra_ratio = 0

        dates = stock_data.index.sort_values()
        try:
            idx = dates.get_loc(analysis_date)
        except KeyError:
            continue

        period_3_ratio = period_5_ratio = period_10_ratio = 0.0
        if float_mv > 0:
            start_3 = max(0, idx - 2)
            dates_3 = dates[start_3:idx+1]
            if len(dates_3) >= 1:
                period_3_data = stock_data.loc[dates_3]
                large_extra_sum = (period_3_data['net_lg_amount'] + period_3_data['net_elg_amount']).sum()
                period_3_ratio = (large_extra_sum / float_mv) * 100
            start_5 = max(0, idx - 4)
            dates_5 = dates[start_5:idx+1]
            if len(dates_5) >= 1:
                period_5_data = stock_data.loc[dates_5]
                large_extra_sum = (period_5_data['net_lg_amount'] + period_5_data['net_elg_amount']).sum()
                period_5_ratio = (large_extra_sum / float_mv) * 100
            start_10 = max(0, idx - 9)
            dates_10 = dates[start_10:idx+1]
            if len(dates_10) >= 1:
                period_10_data = stock_data.loc[dates_10]
                large_extra_sum = (period_10_data['net_lg_amount'] + period_10_data['net_elg_amount']).sum()
                period_10_ratio = (large_extra_sum / float_mv) * 100

        pct_chg_dict = {}
        for period in [2,3,5,10]:
            if idx - period >= 0:
                start_date = dates[idx - period]
                start_close = stock_data.loc[start_date, 'close']
                end_close = today_data['close']
                pct = (end_close - start_close) / start_close * 100 if start_close > 0 else 0
            else:
                pct = 0
            pct_chg_dict[period] = round(pct, 2)

        vol = today_data.get('vol', 0)
        amount = today_data.get('amount', 0)
        if vol > 0:
            avg_price = (amount * 1000) / (vol * 100)
        else:
            avg_price = today_data.get('close', 0)

        row = {
            'analysis_date': analysis_date,
            'ts_code': ts_code,
            'name': df_basic.loc[df_basic['ts_code'] == ts_code, 'name'].values[0] if not df_basic.empty else '',
            'market': df_basic.loc[df_basic['ts_code'] == ts_code, 'market'].values[0] if not df_basic.empty else '',
            'industry': industry_dict.get(ts_code, 'Other'),
            'float_market_value': float_mv,
            'period_3_ratio_float_mv': round(period_3_ratio, 4),
            'period_5_ratio_float_mv': round(period_5_ratio, 4),
            'period_10_ratio_float_mv': round(period_10_ratio, 4),
            'daily_large_ratio_float_mv': round(daily_large_ratio, 4),
            'daily_extra_large_ratio_float_mv': round(daily_extra_ratio, 4),
            'daily_large_extra_ratio_float_mv': round(daily_large_extra_ratio, 4),
            'daily_net_ratio_float_mv': round(daily_net_ratio, 4),
            'avg_price': round(avg_price, 2),
            'pct_chg_daily': round(today_data.get('pct_chg', 0), 2),
            'turnover_rate': round(today_data.get('turnover_rate', 0), 4),
            'total_mv': round(today_data.get('total_mv', 0), 2),
            'pct_chg_2d': pct_chg_dict[2],
            'pct_chg_3d': pct_chg_dict[3],
            'pct_chg_5d': pct_chg_dict[5],
            'pct_chg_10d': pct_chg_dict[10],
            'daily_net_inflow': round(daily_net, 2),
            'daily_large_inflow': round(daily_large, 2),
            'daily_extra_large_inflow': round(daily_extra, 2),
            'daily_large_extra_inflow': round(daily_large_extra, 2),
        }
        results.append(row)
    return pd.DataFrame(results)

# ==================== 导出 CSV ====================
def export_to_csv(df, output_dir, filename_prefix, use_chinese=True):
    os.makedirs(output_dir, exist_ok=True)
    filename = os.path.join(output_dir, filename_prefix)
    if use_chinese:
        column_mapping = {
            'analysis_date': '分析日期', 'ts_code': '股票代码', 'name': '股票名称',
            'market': '市场', 'industry': '申万二级行业', 'float_market_value': '流通市值(万元)',
            'period_3_ratio_float_mv': '3日大特单流入/流通市值(%)',
            'period_5_ratio_float_mv': '5日大特单流入/流通市值(%)',
            'period_10_ratio_float_mv': '10日大特单流入/流通市值(%)',
            'daily_large_ratio_float_mv': '当日大单流入/流通市值(%)',
            'daily_extra_large_ratio_float_mv': '当日特大单流入/流通市值(%)',
            'daily_large_extra_ratio_float_mv': '当日大特单合计/流通市值(%)',
            'daily_net_ratio_float_mv': '当日净流入/流通市值(%)',
            'avg_price': '均价(元)', 'pct_chg_daily': '当日涨跌幅(%)',
            'turnover_rate': '换手率(%)', 'total_mv': '总市值(万元)',
            'pct_chg_2d': '2日涨跌幅(%)', 'pct_chg_3d': '3日涨跌幅(%)',
            'pct_chg_5d': '5日涨跌幅(%)', 'pct_chg_10d': '10日涨跌幅(%)',
            'daily_net_inflow': '当日净流入额(万元)', 'daily_large_inflow': '当日大单净流入(万元)',
            'daily_extra_large_inflow': '当日特大单净流入(万元)',
            'daily_large_extra_inflow': '当日大特单合计(万元)',
        }
        rename_dict = {k: v for k, v in column_mapping.items() if k in df.columns}
        df = df.rename(columns=rename_dict)
    df.to_csv(filename, index=False, encoding='utf-8-sig', float_format='%.4f')
    print(f"✅ 已导出 {len(df)} 条记录到 {filename}")

def save_signals_to_db(df, strategy_name, analysis_date, db_path):
    if df.empty:
        return
    conn = sqlite3.connect(db_path)
    records = []
    for _, row in df.iterrows():
        records.append({
            'signal_date': analysis_date,
            'stock_code': row['ts_code'],
            'strategy_name': strategy_name,
            'signal_price': row.get('avg_price', 0),
            'industry': row.get('industry', None),
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })
    new_df = pd.DataFrame(records)
    try:
        existing = pd.read_sql(
            f"SELECT stock_code FROM strategy_signals WHERE signal_date='{analysis_date}' AND strategy_name='{strategy_name}'",
            conn
        )
        if not existing.empty:
            new_df = new_df[~new_df['stock_code'].isin(existing['stock_code'])]
    except Exception:
        pass
    if not new_df.empty:
        new_df.to_sql('strategy_signals', conn, if_exists='append', index=False)
        print(f"✅ 已写入 {len(new_df)} 条 {strategy_name} 信号到数据库")
    conn.close()

# ==================== 连续阳线筛选 ====================
def filter_consecutive_up_in_stock_list(stock_list, target_date, N, db_path):
    if not stock_list:
        return []
    engine = create_engine(f'sqlite:///{db_path}')
    trade_dates = fetch_trade_dates(engine, target_date, N + 5)
    if len(trade_dates) < N:
        return []
    needed_dates = trade_dates[-N:]
    if target_date not in needed_dates:
        return []
    codes_str = ','.join([f"'{c}'" for c in stock_list])
    date_str = ','.join([f"'{d}'" for d in needed_dates])
    query = f"""
    SELECT ts_code, trade_date, open, close
    FROM daily_data
    WHERE ts_code IN ({codes_str}) AND trade_date IN ({date_str})
    """
    df = pd.read_sql(query, engine)
    if df.empty:
        return []
    df['is_up'] = df['close'] > df['open']
    grouped = df.groupby('ts_code')
    result_codes = []
    for code, group in grouped:
        if set(needed_dates).issubset(set(group['trade_date'])) and group['is_up'].all():
            result_codes.append(code)
    return result_codes

# ==================== 历史回顾 ====================
def historical_review(df_result, analysis_date, engine, db_path, config):
    if df_result.empty or not config.get("enabled", True):
        return
    review_cfg = config
    lookback_days = review_cfg['lookback_days']
    x_th = review_cfg['x_threshold']
    y_th = review_cfg['y_threshold']
    z_th = review_cfg['z_threshold']
    trade_dates = fetch_trade_dates(engine, analysis_date, lookback_days + 5)
    if analysis_date in trade_dates:
        trade_dates.remove(analysis_date)
    history_dates = trade_dates[-lookback_days:] if len(trade_dates) >= lookback_days else trade_dates
    if not history_dates:
        print("历史交易日不足，跳过回顾")
        return
    stock_codes = df_result['ts_code'].tolist()
    codes_str = ','.join([f"'{c}'" for c in stock_codes])
    date_str = ','.join([f"'{d}'" for d in history_dates])
    query_signals = f"""
    SELECT stock_code, signal_date FROM strategy_signals
    WHERE strategy_name = '资金流综合'
      AND signal_date IN ({date_str})
      AND stock_code IN ({codes_str})
    """
    signals_df = pd.read_sql(query_signals, engine)
    signal_counts = signals_df.groupby('stock_code').size().to_dict()
    query_daily = f"""
    SELECT ts_code, trade_date, close, open
    FROM daily_data
    WHERE ts_code IN ({codes_str}) AND trade_date IN ({date_str})
    """
    daily_df = pd.read_sql(query_daily, engine)
    daily_df['is_up'] = daily_df['close'] > daily_df['open']
    up_counts = daily_df[daily_df['is_up']].groupby('ts_code').size().to_dict()
    query_z = f"""
    SELECT stock_code, signal_date FROM strategy_signals
    WHERE strategy_name = '资金流连续阳线3天'
      AND signal_date IN ({date_str})
      AND stock_code IN ({codes_str})
    """
    z_signals_df = pd.read_sql(query_z, engine)
    z_counts = z_signals_df.groupby('stock_code').size().to_dict()
    review_list = []
    for _, row in df_result.iterrows():
        code = row['ts_code']
        name = row['name']
        cnt_x = signal_counts.get(code, 0)
        cnt_y = up_counts.get(code, 0)
        cnt_z = z_counts.get(code, 0)
        review_list.append({
            'ts_code': code,
            'name': name,
            f'过去{lookback_days}日入选综合策略次数': cnt_x,
            f'是否超过阈值{x_th}': '是' if cnt_x >= x_th else '否',
            f'过去{lookback_days}日阳线天数': cnt_y,
            f'是否超过阈值{y_th}': '是' if cnt_y >= y_th else '否',
            f'过去{lookback_days}日入选阳线3天策略次数': cnt_z,
            f'是否超过阈值{z_th}': '是' if cnt_z >= z_th else '否',
        })
    review_df = pd.DataFrame(review_list)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    base_dir = os.path.join(script_dir, CONFIG["output_base_dir"])
    date_dir = os.path.join(base_dir, analysis_date)
    os.makedirs(date_dir, exist_ok=True)
    out_file = os.path.join(date_dir, f"historical_review_{analysis_date}.csv")
    review_df.to_csv(out_file, index=False, encoding='utf-8-sig')
    print(f"✅ 历史回顾结果已保存到 {out_file}")

# ==================== 主流程 ====================
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--date', type=str, help='分析日期 YYYYMMDD')
    parser.add_argument('--days', type=int, help='连续天数')
    args = parser.parse_args()

    today_str = datetime.now().strftime('%Y%m%d')
    if args.date:
        analysis_date = args.date
    else:
        date_input = input(f"请输入分析日期 (YYYYMMDD，直接回车使用今天 {today_str}): ").strip()
        analysis_date = date_input if date_input else today_str

    if args.days:
        continuous_days = args.days
    else:
        days_input = input(f"请输入连续天数 (直接回车使用配置的 {CONFIG['continuous_days']}): ").strip()
        continuous_days = int(days_input) if days_input.isdigit() else CONFIG['continuous_days']

    print(f"分析日期: {analysis_date}")
    print(f"连续天数: {continuous_days}")

    db_path = r"D:/QUANT_SEEKING/数据采集功能/stock_data.db"
    engine = create_engine(f'sqlite:///{db_path}', echo=False)

    trade_dates = fetch_trade_dates(engine, analysis_date, continuous_days + 10)
    if len(trade_dates) < continuous_days:
        print("❌ 交易日不足")
        return

    mf_df = fetch_moneyflow_data(engine, trade_dates)
    ths_df = fetch_ths_data(engine, trade_dates)
    if mf_df.empty or ths_df.empty:
        print("❌ 资金流数据为空")
        return
    for col in ['net_mf_amount', 'net_lg_amount', 'net_elg_amount']:
        mf_df[col] = pd.to_numeric(mf_df[col], errors='coerce').fillna(0)
    for col in ['net_amount', 'buy_lg_amount']:
        ths_df[col] = pd.to_numeric(ths_df[col], errors='coerce').fillna(0)

    moneyflow_multi = prepare_multiindex_df(mf_df)
    ths_multi = prepare_multiindex_df(ths_df)

    # ========== 增加调试输出：分别运行两个子策略并打印结果 ==========
    print("\n" + "="*60)
    print("【资金流策略对比】")
    print("="*60)
    # 传统资金流策略
    mf_strategy = MoneyFlowContinuousStrategy(config={'continuous_days': continuous_days, 'debug': False})
    mf_signals = mf_strategy.generate_signals(analysis_date, moneyflow_multi)
    print(f"传统资金流策略选股数量: {len(mf_signals)}")
    # 同花顺资金流策略
    ths_strategy = THSMoneyFlowContinuousStrategy(config={'continuous_days': continuous_days, 'debug': False})
    ths_signals = ths_strategy.generate_signals(analysis_date, ths_multi)
    print(f"同花顺资金流策略选股数量: {len(ths_signals)}")
    common_count = len(set(mf_signals) & set(ths_signals))
    print(f"两个策略共同选出的股票数量（取交集）: {common_count}")

    # 运行综合策略（实际取交集）
    config_combined = {
        'moneyflow_config': {'continuous_days': continuous_days, 'debug': CONFIG['debug']},
        'ths_config': {'continuous_days': continuous_days, 'debug': CONFIG['debug']},
        'debug': CONFIG['debug']
    }
    combined = CombinedMoneyFlowStrategy(config=config_combined)
    result = combined.generate_signals(analysis_date, moneyflow_multi, ths_multi)
    print(f"综合策略最终输出数量（与上面交集一致）: {len(result)}")

    # 剔除ST
    st_filter = STStockFilter(pro=pro)
    result = st_filter.filter_stocks(result, analysis_date)
    print(f"剔除ST后股票数量: {len(result)}")
    if not result:
        print("无股票，退出")
        return

    traditional_history = build_traditional_history_data(engine, trade_dates)
    df_result = calculate_additional_metrics(engine, result, analysis_date, traditional_history)

    script_dir = os.path.dirname(os.path.abspath(__file__))
    base_dir = os.path.join(script_dir, CONFIG["output_base_dir"])
    date_dir = os.path.join(base_dir, analysis_date)
    logic_type = f"combined_{continuous_days}days_continuous"
    output_dir = os.path.join(date_dir, logic_type)

    export_to_csv(df_result, output_dir, f"all_stocks_combined_{analysis_date}.csv",
                  use_chinese=CONFIG["export_chinese_columns"])
    save_signals_to_db(df_result, "资金流综合", analysis_date, db_path)

    if CONFIG["historical_review"]["enabled"]:
        historical_review(df_result, analysis_date, engine, db_path, CONFIG["historical_review"])

    print("\n" + "="*60)
    print("【连续阳线筛选（仅对当日选中股票）】")
    for n in CONFIG["consecutive_up_days"]:
        print(f"\n正在筛选连续{n}天阳线...")
        up_codes = filter_consecutive_up_in_stock_list(
            stock_list=df_result['ts_code'].tolist(),
            target_date=analysis_date,
            N=n,
            db_path=db_path
        )
        if not up_codes:
            print(f"连续{n}天阳线：无股票")
            continue
        merged = df_result[df_result['ts_code'].isin(up_codes)].copy()
        output_subdir = os.path.join(date_dir, f"continues_阳线_{n}days")
        os.makedirs(output_subdir, exist_ok=True)
        out_filename = f"combined_moneyflow_continues_{n}days_阳线.csv"
        export_to_csv(merged, output_subdir, out_filename, use_chinese=CONFIG["export_chinese_columns"])
        save_signals_to_db(merged, f"资金流连续阳线{n}天", analysis_date, db_path)
        print(f"连续{n}天阳线符合股票数: {len(merged)}")

    print("\n✅ 全部选股完成")

if __name__ == "__main__":
    main()