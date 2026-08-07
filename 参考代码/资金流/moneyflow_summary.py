from datetime import time

import pandas as pd
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import OperationalError

# 创建数据库连接时启用 WAL 模式
engine = create_engine('sqlite:///stock_data.db', echo=True, connect_args={"check_same_thread": False})

# 启用 WAL 模式
with engine.connect() as conn:
    conn.execute(text("PRAGMA journal_mode=WAL;"))
    conn.execute(text("PRAGMA synchronous=NORMAL;"))  # 设置同步模式为 NORMAL，提高写入性能

def calculate_net_values(df):
    """
    计算净买入量和净买入金额
    :param df: 原始资金流向数据 DataFrame
    :return: 加工后的汇总数据 DataFrame
    """
    # 将相关列转换为数值类型
    numeric_cols = [
        'buy_sm_vol', 'sell_sm_vol', 'buy_sm_amount', 'sell_sm_amount',
        'buy_md_vol', 'sell_md_vol', 'buy_md_amount', 'sell_md_amount',
        'buy_lg_vol', 'sell_lg_vol', 'buy_lg_amount', 'sell_lg_amount',
        'buy_elg_vol', 'sell_elg_vol', 'buy_elg_amount', 'sell_elg_amount',
        'net_mf_vol', 'net_mf_amount'
    ]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce')  # 将列转换为数值类型，无法转换的设为 NaN

    # 计算净买入量和净买入金额
    df['net_sm_vol'] = df['buy_sm_vol'] - df['sell_sm_vol']  # 小单净买入量
    df['net_sm_amount'] = df['buy_sm_amount'] - df['sell_sm_amount']  # 小单净买入金额
    df['net_md_vol'] = df['buy_md_vol'] - df['sell_md_vol']  # 中单净买入量
    df['net_md_amount'] = df['buy_md_amount'] - df['sell_md_amount']  # 中单净买入金额
    df['net_lg_vol'] = df['buy_lg_vol'] - df['sell_lg_vol']  # 大单净买入量
    df['net_lg_amount'] = df['buy_lg_amount'] - df['sell_lg_amount']  # 大单净买入金额
    df['net_elg_vol'] = df['buy_elg_vol'] - df['sell_elg_vol']  # 特大单净买入量
    df['net_elg_amount'] = df['buy_elg_amount'] - df['sell_elg_amount']  # 特大单净买入金额

    # 选择需要的字段
    summary_df = df[[
        'ts_code', 'trade_date', 'net_sm_vol', 'net_sm_amount', 'net_md_vol', 'net_md_amount',
        'net_lg_vol', 'net_lg_amount', 'net_elg_vol', 'net_elg_amount', 'net_mf_vol', 'net_mf_amount'
    ]]

    return summary_df


def create_moneyflow_summary_table():
    """
    生成 moneyflow 数据汇总表，仅对缺失的数据日期进行计算更新
    """
    # 定义汇总表名
    table_name = 'moneyflow_summary'

    # 检查表是否存在
    inspector = inspect(engine)
    if not inspector.has_table(table_name):
        # 如果表不存在，先创建表
        sample_data = pd.DataFrame(columns=[
            'ts_code', 'trade_date', 'net_sm_vol', 'net_sm_amount', 'net_md_vol', 'net_md_amount',
            'net_lg_vol', 'net_lg_amount', 'net_elg_vol', 'net_elg_amount', 'net_mf_vol', 'net_mf_amount'
        ])
        sample_data.to_sql(table_name, con=engine, if_exists='replace', index=False)
        print(f"表 {table_name} 已创建")

    # 获取 moneyflow_summary 表中的最新日期
    latest_date_query = f"SELECT MAX(trade_date) as latest_date FROM {table_name}"
    latest_date_df = pd.read_sql(latest_date_query, con=engine)
    latest_date = latest_date_df['latest_date'].iloc[0]

    # 从 moneyflow_data 表中获取比 latest_date 新的数据
    if latest_date:
        query = f"SELECT * FROM moneyflow_data WHERE trade_date > '{latest_date}'"
    else:
        query = "SELECT * FROM moneyflow_data"

    # 分块读取数据
    chunk_size = 10000  # 每次读取 1 万行
    chunks = pd.read_sql(query, con=engine, chunksize=chunk_size)

    for chunk in chunks:
        if not chunk.empty:
            # 计算净买入量和净买入金额
            summary_df = calculate_net_values(chunk)

            # 分块写入数据库，每次写入 100 行
            write_chunk_size = 100  # 进一步减少每块写入的数据量
            for i in range(0, len(summary_df), write_chunk_size):
                chunk_to_write = summary_df[i:i + write_chunk_size]
                try:
                    chunk_to_write.to_sql(table_name, con=engine, if_exists='append', index=False)
                    print(f"已写入 {len(chunk_to_write)} 行数据到 {table_name}")
                except OperationalError as e:
                    if "database is locked" in str(e):
                        print("数据库被锁定，等待后重试...")
                        time.sleep(5)  # 等待 5 秒后重试
                        chunk_to_write.to_sql(table_name, con=engine, if_exists='append', index=False)
                    else:
                        raise e  # 如果是其他错误，直接抛出

    # 打印更新后的汇总表前 10 行数据
    query = f"SELECT * FROM {table_name} ORDER BY trade_date DESC LIMIT 10"
    updated_data = pd.read_sql(query, con=engine)
    print("更新后的 moneyflow_summary 表前 10 行数据：")
    print(updated_data)


# 生成 moneyflow 数据汇总表
if __name__ == "__main__":
    create_moneyflow_summary_table()