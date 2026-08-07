# moneyflow_ths_fetcher.py - 同花顺资金流向数据更新模块
import tushare as ts
import pandas as pd
from sqlalchemy import create_engine, inspect, text
import time
from datetime import datetime
import os

# 设置 Tushare API Token
ts.set_token('53399fa4a4f51a769a4455978feb0b04c88f87d5c916507a61131f34')
pro = ts.pro_api()

# 数据库路径
script_dir = os.path.dirname(os.path.abspath(__file__))
db_path = os.path.join(script_dir, 'stock_data.db')
engine = create_engine(f'sqlite:///{db_path}', echo=True)

TABLE_NAME = 'moneyflow_ths_data'

def get_moneyflow_ths_data(trade_date):
    """获取指定交易日的同花顺资金流向数据"""
    try:
        df = pro.moneyflow_ths(trade_date=trade_date)
        return df
    except Exception as e:
        print(f"获取 {trade_date} 的同花顺资金流向数据失败: {e}")
        return pd.DataFrame()

def update_table_structure(table_name, df):
    """更新表结构，确保表的列与 DataFrame 的列一致"""
    with engine.connect() as connection:
        result = connection.execute(text(f"PRAGMA table_info({table_name})"))
        existing_columns = [row[1] for row in result]

    new_columns = df.columns.tolist()
    columns_to_add = [col for col in new_columns if col not in existing_columns]

    if columns_to_add:
        with engine.connect() as connection:
            for column in columns_to_add:
                col_type = 'TEXT' if any(k in column.lower() for k in ['name', 'code', 'date']) else 'REAL'
                connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column} {col_type}"))
            connection.commit()
        print(f"表 {table_name} 已添加列: {columns_to_add}")

def init_table():
    """初始化表（如果不存在则创建）"""
    inspector = inspect(engine)
    if not inspector.has_table(TABLE_NAME):
        sample = get_moneyflow_ths_data(datetime.now().strftime('%Y%m%d'))
        if sample.empty:
            columns = [
                'trade_date', 'ts_code', 'name', 'pct_change', 'latest',
                'net_amount', 'net_d5_amount', 'buy_lg_amount', 'buy_lg_amount_rate',
                'buy_md_amount', 'buy_md_amount_rate', 'buy_sm_amount', 'buy_sm_amount_rate'
            ]
            sample = pd.DataFrame(columns=columns)
        sample.to_sql(TABLE_NAME, con=engine, if_exists='replace', index=False)
        print(f"表 {TABLE_NAME} 已创建")

def find_first_data_date(start_date='20190101', end_date=None):
    """二分查找最早有数据的日期"""
    if end_date is None:
        end_date = datetime.now().strftime('%Y%m%d')
    cal = pro.trade_cal(exchange='', start_date=start_date, end_date=end_date, is_open='1')
    if cal.empty:
        return None
    dates = cal['cal_date'].tolist()
    left, right = 0, len(dates) - 1
    first = None
    while left <= right:
        mid = (left + right) // 2
        date = dates[mid]
        print(f"检查 {date}...", end='')
        df = get_moneyflow_ths_data(date)
        if not df.empty:
            print("有数据")
            first = date
            right = mid - 1
        else:
            print("无数据")
            left = mid + 1
        time.sleep(0.5)
    return first

def update_moneyflow_ths_data():
    """供调度器调用的入口函数：更新同花顺资金流向数据"""
    print("开始更新同花顺资金流向数据...")
    init_table()
    end_date = datetime.now().strftime('%Y%m%d')
    start_date = '20190101'

    # 1. 确定最早有数据的日期
    first_date = find_first_data_date(start_date, end_date)
    if first_date is None:
        print("未找到任何有数据的日期，请检查API权限")
        return
    print(f"\n最早有数据日期：{first_date}")

    # 2. 获取该日期之后的所有交易日
    trade_cal = pro.trade_cal(exchange='', start_date=first_date, end_date=end_date, is_open='1')
    all_dates = trade_cal['cal_date'].tolist()

    # 3. 查询数据库中已存在的日期
    existing = pd.read_sql(f"SELECT DISTINCT trade_date FROM {TABLE_NAME}", con=engine)['trade_date'].tolist()
    missing = [d for d in all_dates if d not in existing]

    if not missing:
        print("所有数据已存在，无需更新")
        return

    # 4. 限流控制逐日更新
    start_time = datetime.now()
    call_count = 0
    for trade_date in missing:
        if call_count >= 200:
            elapsed = (datetime.now() - start_time).total_seconds()
            if elapsed < 60:
                time.sleep(60 - elapsed)
            start_time = datetime.now()
            call_count = 0

        df = get_moneyflow_ths_data(trade_date)
        call_count += 1

        if not df.empty:
            update_table_structure(TABLE_NAME, df)
            try:
                df.to_sql(TABLE_NAME, con=engine, if_exists='append', index=False)
                print(f"已更新 {trade_date}，共 {len(df)} 条")
            except Exception as e:
                print(f"插入 {trade_date} 失败: {e}")
        else:
            print(f"{trade_date} 无数据，跳过")

    # 打印最新10条数据
    latest = pd.read_sql(f"SELECT * FROM {TABLE_NAME} ORDER BY trade_date DESC LIMIT 10", con=engine)
    print("\n最新10条记录：")
    print(latest)

if __name__ == "__main__":
    update_moneyflow_ths_data()