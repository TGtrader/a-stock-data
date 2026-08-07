import tushare as ts
import pandas as pd
from sqlalchemy import create_engine, inspect, text
import time
from datetime import datetime, timedelta

# 设置 Tushare 的 API Token
ts.set_token('53399fa4a4f51a769a4455978feb0b04c88f87d5c916507a61131f34')  # 替换为你的 Tushare API Token
pro = ts.pro_api()

# 创建数据库连接
engine = create_engine('sqlite:///stock_data.db', echo=True)


def get_moneyflow_data(trade_date):
    """
    获取指定交易日的资金流向数据
    :param trade_date: 交易日期（YYYYMMDD）
    :return: DataFrame
    """
    try:
        # 获取资金流向数据
        df = pro.moneyflow(trade_date=trade_date)
        return df
    except Exception as e:
        print(f"获取 {trade_date} 的资金流向数据失败: {e}")
        return pd.DataFrame()


def update_table_structure(table_name, df):
    """
    更新表结构，确保表的列与 DataFrame 的列一致
    :param table_name: 表名
    :param df: 数据 DataFrame
    """
    # 获取表的现有列
    with engine.connect() as connection:
        result = connection.execute(text(f"PRAGMA table_info({table_name})"))
        existing_columns = [row[1] for row in result]  # 提取列名

    # 获取 DataFrame 的列
    new_columns = df.columns.tolist()

    # 找出需要添加的列
    columns_to_add = [col for col in new_columns if col not in existing_columns]

    # 添加缺失的列
    if columns_to_add:
        with engine.connect() as connection:
            for column in columns_to_add:
                connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column} REAL"))
            connection.commit()  # 提交事务
        print(f"表 {table_name} 已添加列: {columns_to_add}")


def update_moneyflow_data():
    """
    更新资金流向数据
    """
    # 定义资金流向表名
    table_name = 'moneyflow_data'

    # 检查表是否存在
    inspector = inspect(engine)
    if not inspector.has_table(table_name):
        # 如果表不存在，先获取一条数据以确定列名
        sample_data = pd.DataFrame(columns=[
            'ts_code', 'trade_date', 'buy_sm_vol', 'buy_sm_amount', 'sell_sm_vol', 'sell_sm_amount',
            'buy_md_vol', 'buy_md_amount', 'sell_md_vol', 'sell_md_amount', 'buy_lg_vol', 'buy_lg_amount',
            'sell_lg_vol', 'sell_lg_amount', 'buy_elg_vol', 'buy_elg_amount', 'sell_elg_vol', 'sell_elg_amount',
            'net_mf_vol', 'net_mf_amount'
        ])
        sample_data.to_sql(table_name, con=engine, if_exists='replace', index=False)
        print(f"表 {table_name} 已创建")

    # 获取当前日期
    end_date = datetime.now().strftime('%Y%m%d')
    start_date = '20200101'  # 从 2020 年 1 月 1 日开始

    # 获取所有交易日历
    trade_cal = pro.trade_cal(exchange='', start_date=start_date, end_date=end_date, is_open='1')
    trade_dates = trade_cal['cal_date'].tolist()

    # 获取数据库中已有的交易日期
    query = f"SELECT DISTINCT trade_date FROM {table_name}"
    existing_dates = pd.read_sql(query, con=engine)['trade_date'].tolist()

    # 找出缺失的交易日期
    missing_dates = [date for date in trade_dates if date not in existing_dates]

    if not missing_dates:
        print("所有交易日的资金流向数据已存在，无需更新")
        return

    # 初始化时间节拍器
    start_time = datetime.now()
    call_count = 0  # 调用计数器

    # 遍历缺失的交易日，获取资金流向数据并存入数据库
    for trade_date in missing_dates:
        # 每分钟最多调用 200 次 API
        if call_count >= 200:
            elapsed_time = (datetime.now() - start_time).total_seconds()
            if elapsed_time < 60:
                sleep_time = 60 - elapsed_time
                print(f"已达到每分钟 200 次调用限制，等待 {sleep_time:.1f} 秒...")
                time.sleep(sleep_time)  # 等待剩余时间
            start_time = datetime.now()  # 重置计时器
            call_count = 0  # 重置计数器

        df = get_moneyflow_data(trade_date)
        call_count += 1  # 增加调用计数

        if not df.empty:
            # 检查并更新表结构
            update_table_structure(table_name, df)

            # 存入数据库
            df.to_sql(table_name, con=engine, if_exists='append', index=False)
            print(f"已更新 {trade_date} 的资金流向数据")
        else:
            print(f"{trade_date} 的资金流向数据为空，跳过更新")

    # 打印更新后的 moneyflow_data 表倒数 10 行数据
    query = f"SELECT * FROM {table_name} ORDER BY trade_date DESC LIMIT 10"
    updated_data = pd.read_sql(query, con=engine)
    print("更新后的 moneyflow_data 表倒数 10 行数据：")
    print(updated_data)


# 更新资金流向数据
if __name__ == "__main__":
    update_moneyflow_data()