"""
Phase 1: A股7月回调数据探索
数据源: Tushare (行情+业绩) + a-stock-data (腾讯估值/资金流) + Vibe-Trading
目标: 摸清7月以来市场脉络，找出相对强势的板块和个股
"""
import tushare as ts
import pandas as pd
import numpy as np
import requests
import time
import json
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

# ============================================================
ts.set_token("53399fa4a4f51a769a4455978feb0b04c88f87d5c916507a61131f34")
pro = ts.pro_api()
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
OUTPUT_DIR = Path(__file__).parent / "exploration_data"
OUTPUT_DIR.mkdir(exist_ok=True)

TRADE_END = "20260722"
TRADE_START = "20260601"  # 6月起点，用于对比
JULY_START = "20260701"

print("=" * 60)
print("A股7月科技回调 · 数据探索")
print(f"分析区间: {JULY_START} ~ {TRADE_END}")
print("=" * 60)

# ============================================================
# 1. 主要指数表现
# ============================================================
print("\n[1] 主要指数7月以来表现...")

INDEX_CODES = {
    "000001.SH": "上证指数", "399001.SZ": "深证成指", "399006.SZ": "创业板指",
    "000688.SH": "科创50", "000300.SH": "沪深300", "000905.SH": "中证500",
    "000852.SH": "中证1000", "399303.SZ": "国证2000",
}

index_perf = {}
for idx_code, idx_name in INDEX_CODES.items():
    try:
        df = pro.index_daily(ts_code=idx_code, start_date=TRADE_START, end_date=TRADE_END)
        if len(df) < 5: continue
        df = df.sort_values("trade_date").reset_index(drop=True)
        close_series = df["close"]

        # 分段涨跌幅
        end_val = close_series.iloc[-1]
        start_val = close_series.iloc[0]
        july_start = df[df["trade_date"] <= JULY_START]["close"].iloc[-1] if any(df["trade_date"] <= JULY_START) else start_val

        total_chg = (end_val / start_val - 1) * 100
        july_chg = (end_val / july_start - 1) * 100

        # 最大回撤
        cummax = close_series.cummax()
        drawdown = ((close_series - cummax) / cummax * 100)
        max_dd = drawdown.min()

        # 量能变化
        vol_series = df["vol"]
        july_vol = vol_series[df["trade_date"] >= JULY_START].mean() if any(df["trade_date"] >= JULY_START) else 0
        june_vol = vol_series[df["trade_date"] < JULY_START].mean() if any(df["trade_date"] < JULY_START) else 0
        vol_change = ((july_vol / june_vol - 1) * 100) if june_vol > 0 else 0

        index_perf[idx_code] = {
            "name": idx_name, "total_chg": round(total_chg, 2),
            "july_chg": round(july_chg, 2), "max_dd": round(max_dd, 2),
            "vol_change_pct": round(vol_change, 1),
            "latest": float(end_val),
            "data": df,
        }
        print(f"  {idx_name:8s}: 7月={july_chg:+.2f}% | 6月至今={total_chg:+.2f}% | 最大回撤={max_dd:.2f}% | 量变={vol_change:+.0f}%")
    except Exception as e:
        print(f"  {idx_name}: 失败 - {e}")
    time.sleep(0.2)

# ============================================================
# 2. 申万行业板块分析（用Tushare SW行业指数）
# ============================================================
print("\n[2] 申万行业板块7月表现...")

# 申万一级行业指数代码（部分）
SW_INDUSTRIES = {
    "801080.SI": "电子", "801750.SI": "计算机", "801770.SI": "通信",
    "801760.SI": "传媒", "801150.SI": "医药生物", "801180.SI": "房地产",
    "801780.SI": "银行", "801790.SI": "非银金融", "801880.SI": "汽车",
    "801730.SI": "电力设备", "801740.SI": "国防军工", "801050.SI": "有色金属",
    "801030.SI": "化工", "801710.SI": "建筑材料", "801720.SI": "建筑装饰",
    "801120.SI": "食品饮料", "801130.SI": "纺织服饰", "801140.SI": "轻工制造",
    "801890.SI": "机械设备", "801960.SI": "石油石化", "801970.SI": "煤炭",
    "801980.SI": "公用事业", "801160.SI": "交通运输", "801170.SI": "商贸零售",
    "801200.SI": "社会服务", "801210.SI": "综合", "801230.SI": "基础化工(新)",
}

sw_perf = {}
for sw_code, sw_name in SW_INDUSTRIES.items():
    try:
        df = pro.index_daily(ts_code=sw_code, start_date=TRADE_START, end_date=TRADE_END)
        if len(df) < 5: continue
        df = df.sort_values("trade_date").reset_index(drop=True)
        close = df["close"]
        july_start = df[df["trade_date"] <= JULY_START]["close"].iloc[-1] if any(df["trade_date"] <= JULY_START) else close.iloc[0]
        end = close.iloc[-1]
        july_chg = (end / july_start - 1) * 100
        total_chg = (end / close.iloc[0] - 1) * 100

        # 量能
        vol = df["vol"]
        july_vol_mean = vol[df["trade_date"] >= JULY_START].mean() if any(df["trade_date"] >= JULY_START) else 0
        june_vol_mean = vol[df["trade_date"] < JULY_START].mean() if any(df["trade_date"] < JULY_START) else 0
        vol_ratio = (july_vol_mean / june_vol_mean) if june_vol_mean > 0 else 1

        sw_perf[sw_code] = {
            "name": sw_name, "july_chg": round(july_chg, 2),
            "total_chg": round(total_chg, 2), "vol_ratio": round(vol_ratio, 2),
            "data": df,
        }
    except Exception as e:
        pass  # 部分申万代码可能不可用
    time.sleep(0.15)

# 排序
sw_sorted = sorted(sw_perf.items(), key=lambda x: x[1]["july_chg"], reverse=True)
print("\n  7月涨幅TOP 5:")
for code, info in sw_sorted[:5]:
    print(f"    {info['name']:8s}: 7月={info['july_chg']:+.2f}% | 量比={info['vol_ratio']:.2f}")
print("  7月跌幅TOP 5:")
for code, info in sw_sorted[-5:]:
    print(f"    {info['name']:8s}: 7月={info['july_chg']:+.2f}% | 量比={info['vol_ratio']:.2f}")

# ============================================================
# 3. 科技子板块细化（Tushare概念板块 or 东财行业）
# ============================================================
print("\n[3] 科技细分板块分析（Tushare概念/主题指数）...")

# Tushare 概念板块
TECH_CONCEPTS = {
    "884999.WI": "半导体", "884224.WI": "芯片", "884162.WI": "人工智能",
    "884091.WI": "5G", "884116.WI": "云计算", "884148.WI": "大数据",
    "884202.WI": "机器人", "884039.WI": "新能源车", "884076.WI": "物联网",
    "884128.WI": "消费电子", "884221.WI": "光刻机", "884232.WI": "存储芯片",
    "884234.WI": "先进封装", "884136.WI": "信创", "884141.WI": "网络安全",
    "884074.WI": "苹果概念", "884105.WI": "华为概念", "884155.WI": "国产软件",
    "884166.WI": "智能穿戴", "884232.WI": "第三代半导体",
}

concept_perf = {}
for tc_code, tc_name in TECH_CONCEPTS.items():
    try:
        df = pro.index_daily(ts_code=tc_code, start_date=TRADE_START, end_date=TRADE_END)
        if len(df) < 5: continue
        df = df.sort_values("trade_date").reset_index(drop=True)
        close = df["close"]
        july_start = df[df["trade_date"] <= JULY_START]["close"].iloc[-1] if any(df["trade_date"] <= JULY_START) else close.iloc[0]
        end = close.iloc[-1]
        july_chg = (end / july_start - 1) * 100
        total_chg = (end / close.iloc[0] - 1) * 100

        vol = df["vol"]
        july_vol = vol[df["trade_date"] >= JULY_START].mean() if any(df["trade_date"] >= JULY_START) else 0
        june_vol = vol[df["trade_date"] < JULY_START].mean() if any(df["trade_date"] < JULY_START) else 0
        vol_ratio = (july_vol / june_vol) if june_vol > 0 else 1

        concept_perf[tc_code] = {
            "name": tc_name, "july_chg": round(july_chg, 2),
            "total_chg": round(total_chg, 2), "vol_ratio": round(vol_ratio, 2),
        }
    except Exception:
        pass
    time.sleep(0.15)

concept_sorted = sorted(concept_perf.items(), key=lambda x: x[1]["july_chg"], reverse=True)
print("\n  科技概念7月表现:")
for code, info in concept_sorted[:20]:
    bar = "█" * max(0, int(info["july_chg"])) if info["july_chg"] > 0 else "░" * min(10, abs(int(info["july_chg"])))
    print(f"    {info['name']:12s}: 7月={info['july_chg']:+6.2f}% | 量比={info['vol_ratio']:.2f} {bar}")

# ============================================================
# 4. 个股筛选：抗跌+放量+业绩支撑
# ============================================================
print("\n[4] 筛选相对强势个股（抗跌+量价配合+业绩）...")

# 4a. 先拉业绩预告
print("  4a. 拉取2026中报业绩预告...")
try:
    forecasts = pro.forecast(start_date="20260601", end_date="20260831", fields="ts_code,ann_date,type,p_change_min,p_change_max,summary")
    print(f"    共 {len(forecasts)} 条业绩预告")
    # 筛选预增/略增/扭亏
    positive_types = ["预增", "略增", "扭亏", "续盈"]
    f_positive = forecasts[forecasts["type"].isin(positive_types)]
    # 取利润增速下限>=30%的
    f_positive["p_change_min"] = pd.to_numeric(f_positive["p_change_min"], errors="coerce")
    f_strong = f_positive[f_positive["p_change_min"] >= 30].drop_duplicates("ts_code")
    strong_forecast_codes = set(f_strong["ts_code"].tolist())
    print(f"    预增+增速>=30%: {len(strong_forecast_codes)} 只")
except Exception as e:
    print(f"    业绩预告拉取失败: {e}")
    # fallback: 用业绩快报
    try:
        express = pro.express(ts_code="", start_date="20260601", end_date="20260831")
        strong_forecast_codes = set(express["ts_code"].tolist())
        print(f"    fallback 业绩快报: {len(strong_forecast_codes)} 只")
    except:
        strong_forecast_codes = set()
        print("    无业绩数据可用")

# 4b. 拉取全市场个股7月表现（先做中小盘代表性池子）
print("  4b. 拉取全市场个股7月数据...")

# 分批次拉取（沪深主板+创业板+科创板各取代表性股票）
all_stocks_data = []

# 方法: 从主要概念板块中获取成分股表现
# 先用几个关键指数的成分股来做初筛
sample_pools = [
    ("000300.SH", "沪深300"),
    ("000905.SH", "中证500"),
    ("000688.SH", "科创50"),
    ("399006.SZ", "创业板指"),
]

# 实际上Tushare的index_daily不返回成分股。让我用stock_basic获取全市场股票，
# 然后筛选市值>50亿的，计算7月表现。

# 先拉取stock_basic
try:
    stocks_basic = pro.stock_basic(list_status="L", fields="ts_code,name,industry,market,list_date")
    # 过滤上市满1年的（2025年7月以前）
    stocks_basic = stocks_basic[stocks_basic["list_date"] < "20250701"]
    # 去掉ST
    stocks_basic = stocks_basic[~stocks_basic["name"].str.contains("ST")]
    print(f"    全市场正常交易股票: {len(stocks_basic)} 只")
except Exception as e:
    print(f"    stock_basic失败: {e}")
    stocks_basic = pd.DataFrame()

# 分批拉取日线数据
candidate_codes = stocks_basic["ts_code"].tolist()[:3000]  # 限制数量防止超时
batch_size = 80
all_daily = []

for i in range(0, len(candidate_codes), batch_size):
    batch = candidate_codes[i:i+batch_size]
    try:
        df = pro.daily(ts_code=",".join(batch), start_date=TRADE_START, end_date=TRADE_END)
        if not df.empty:
            all_daily.append(df)
        if (i // batch_size) % 10 == 0:
            print(f"    进度: {i}/{len(candidate_codes)}")
    except Exception as e:
        pass
    time.sleep(0.3)

print(f"    共拉取 {len(all_daily)} 批日线数据")
if all_daily:
    daily_all = pd.concat(all_daily, ignore_index=True)
    daily_all.to_csv(OUTPUT_DIR / "daily_all.csv", index=False)
    print(f"    总日线记录: {len(daily_all)}")

    # 计算每只股票7月表现
    july_data = daily_all[daily_all["trade_date"] >= JULY_START]
    june_data = daily_all[(daily_all["trade_date"] >= "20260601") & (daily_all["trade_date"] < JULY_START)]

    stock_stats = []
    for code, group in daily_all.groupby("ts_code"):
        if len(group) < 20: continue  # 至少20个交易日
        group = group.sort_values("trade_date")
        close = group["close"]
        vol = group["vol"]

        # 7月表现
        july_group = group[group["trade_date"] >= JULY_START]
        if len(july_group) < 5: continue

        july_start_price = july_group["close"].iloc[0]
        july_end_price = july_group["close"].iloc[-1]
        july_chg = (july_end_price / july_start_price - 1) * 100

        # 7月最大回撤
        july_close = july_group["close"]
        july_cummax = july_close.cummax()
        july_max_dd = ((july_close - july_cummax) / july_cummax * 100).min()

        # 量能变化
        july_avg_vol = july_group["vol"].mean()
        june_group = group[(group["trade_date"] >= "20260601") & (group["trade_date"] < JULY_START)]
        june_avg_vol = june_group["vol"].mean() if len(june_group) > 0 else july_avg_vol
        vol_change = ((july_avg_vol / june_avg_vol - 1) * 100) if june_avg_vol > 0 else 0

        # 总涨跌幅
        total_chg = (close.iloc[-1] / close.iloc[0] - 1) * 100

        # 最近5日涨跌
        last_5_chg = (close.iloc[-1] / close.iloc[-6] - 1) * 100 if len(close) >= 6 else 0

        stock_stats.append({
            "ts_code": code,
            "july_chg": round(july_chg, 2),
            "july_max_dd": round(july_max_dd, 2),
            "vol_change_pct": round(vol_change, 1),
            "total_chg": round(total_chg, 2),
            "last_5_chg": round(last_5_chg, 2),
            "latest_price": float(july_end_price),
            "has_forecast": code in strong_forecast_codes,
        })

    stats_df = pd.DataFrame(stock_stats)
    stats_df.to_csv(OUTPUT_DIR / "stock_stats.csv", index=False)
    print(f"    统计完成: {len(stats_df)} 只股票有有效数据")

    # 筛选条件:
    # 1) 7月涨跌幅 > -5% (跑赢大盘)
    # 2) 7月最大回撤 < 15% (相对抗跌)
    # 3) 量比 > 1.0 (有资金关注/放量)
    # 4) 有业绩支撑优先

    resistant = stats_df[
        (stats_df["july_chg"] > -5) &
        (stats_df["july_max_dd"] > -15) &
        (stats_df["vol_change_pct"] > 0)
    ].sort_values("july_chg", ascending=False)

    print(f"\n  抗跌+放量个股: {len(resistant)} 只")
    print(f"  其中业绩预增: {resistant['has_forecast'].sum()} 只")

    # TOP 30
    print("\n  TOP 30 相对强势股:")
    for i, (_, row) in enumerate(resistant.head(30).iterrows()):
        name = stocks_basic[stocks_basic["ts_code"] == row["ts_code"]]["name"].values
        name = name[0] if len(name) > 0 else row["ts_code"]
        forecast_tag = "★业绩" if row["has_forecast"] else ""
        print(f"    {i+1:2d}. {name:8s} {row['ts_code']:12s} 7月={row['july_chg']:+6.2f}% DD={row['july_max_dd']:.1f}% 量变={row['vol_change_pct']:+6.0f}% {forecast_tag}")

    # 保存TOP结果
    resistant.to_csv(OUTPUT_DIR / "resistant_stocks.csv", index=False)
else:
    print("    未拉取到个股数据")

# ============================================================
# 5. 保存探索结果
# ============================================================
print("\n[5] 保存探索数据...")
explore_data = {
    "meta": {"generated": datetime.now().strftime("%Y-%m-%d %H:%M"), "end_date": TRADE_END},
    "indices": {k: {kk: vv for kk, vv in v.items() if kk != "data"} for k, v in index_perf.items()},
    "sectors_sw": {k: {kk: vv for kk, vv in v.items() if kk != "data"} for k, v in sw_perf.items()},
    "concepts": {k: v for k, v in concept_perf.items()},
}

class NpEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (np.integer,)): return int(obj)
        if isinstance(obj, (np.floating,)):
            return None if np.isnan(obj) or np.isinf(obj) else float(obj)
        return super().default(obj)

with open(OUTPUT_DIR / "explore_results.json", "w", encoding="utf-8") as f:
    json.dump(explore_data, f, ensure_ascii=False, indent=2, cls=NpEncoder)

print(f"  数据已保存至: {OUTPUT_DIR}")
print("\n>>> 探索完成，等待讨论后生成正式报告 <<<")
