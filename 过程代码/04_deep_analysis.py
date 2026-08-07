"""
Phase 2: 深度分析数据补全
- 科技二级子行业拆解（东财行业分类）
- 业绩数据补全（东财+新浪）
- 资金流向（北向+主力）
- 估值对比
- 量价形态分类
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
from io import StringIO

ts.set_token("53399fa4a4f51a769a4455978feb0b04c88f87d5c916507a61131f34")
pro = ts.pro_api()
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
OUTPUT_DIR = Path(__file__).parent / "deep_data"
OUTPUT_DIR.mkdir(exist_ok=True)

TRADE_END = "20260722"
JULY_START = "20260701"
JUNE_START = "20260601"

# ===== 东财限流 =====
EM_SESSION = requests.Session()
EM_SESSION.headers.update({"User-Agent": UA})
_em_last = [0.0]

def em_get(url, params=None, timeout=15):
    wait = 1.0 - (time.time() - _em_last[0])
    if wait > 0: time.sleep(wait + np.random.uniform(0.1, 0.5))
    try: return EM_SESSION.get(url, params=params, timeout=timeout)
    finally: _em_last[0] = time.time()

def em_datacenter(report_name, filter_str="", page_size=100, sort_columns="", sort_types="-1"):
    params = {"reportName": report_name, "columns": "ALL", "filter": filter_str,
              "pageNumber": "1", "pageSize": str(page_size),
              "sortColumns": sort_columns, "sortTypes": sort_types,
              "source": "WEB", "client": "WEB"}
    r = em_get("https://datacenter-web.eastmoney.com/api/data/v1/get", params=params, timeout=15)
    return (r.json().get("result") or {}).get("data", [])

print("=" * 70)
print("Phase 2: 深度数据补全 - 科技二级子行业 + 业绩 + 资金 + 估值")
print("=" * 70)

# ============================================================
# 1. 科技二级子行业拆解（东财行业分类）
# ============================================================
print("\n[1/6] 东财行业板块细分数据...")

# 东财行业板块（m:90+t:2 全行业 + 三级细分用 t:3）
def fetch_em_sector(sector_type="2", page_size=200):
    """拉取东财行业板块列表及7月表现"""
    url = "https://push2.eastmoney.com/api/qt/clist/get"
    params = {"pn": "1", "pz": str(page_size), "po": "1", "np": "1",
              "fltt": "2", "invt": "2",
              "fs": f"m:90+t:{sector_type}",
              "fields": "f2,f3,f4,f12,f14,f20,f104,f105,f140,f136"}
    try:
        r = em_get(url, params=params, timeout=15)
        items = r.json().get("data", {}).get("diff", [])
        if isinstance(items, dict): items = list(items.values())
        return [{"code": i.get("f12",""), "name": i.get("f14",""),
                 "change_pct": i.get("f3",0), "up": i.get("f104",0), "down": i.get("f105",0),
                 "leader": i.get("f140",""), "leader_chg": i.get("f136",0)}
                for i in items]
    except Exception as e:
        print(f"    东财板块失败: {e}")
        return []

# 二级行业
sectors_l2 = fetch_em_sector("2", 200)
print(f"  东财二级行业: {len(sectors_l2)} 个")

# 概念板块（三级/题材）
concepts_l3 = fetch_em_sector("3", 400)
print(f"  东财概念板块: {len(concepts_l3)} 个")

# 分类：科技相关 vs 非科技
TECH_KEYWORDS = ["电子", "半导体", "芯片", "通信", "计算机", "软件", "人工智能",
                 "机器人", "自动化", "军工", "航天", "航空", "光伏", "新能源",
                 "电池", "储能", "光电", "光学", "光刻", "封测", "消费电子",
                 "物联网", "大数据", "云计算", "信创", "网络安全", "5G", "6G",
                 "智能", "存储", "算力", "服务器", "激光", "传感器", "雷达",
                 "汽车电子", "元器件", "仪器仪表", "电机", "电网", "充电桩"]

tech_sectors = [s for s in sectors_l2 if any(kw in s["name"] for kw in TECH_KEYWORDS)]
non_tech_sectors = [s for s in sectors_l2 if not any(kw in s["name"] for kw in TECH_KEYWORDS)]

tech_sorted = sorted(tech_sectors, key=lambda x: x.get("change_pct", 0), reverse=True)
non_tech_sorted = sorted(non_tech_sectors, key=lambda x: x.get("change_pct", 0), reverse=True)

print(f"\n  科技相关二级行业 ({len(tech_sectors)} 个):")
for s in tech_sorted[:25]:
    bar = "[DOWN]" if s["change_pct"] < -10 else "[weak]" if s["change_pct"] < -5 else "[UP]" if s["change_pct"] > 0 else "[-]"
    print(f"    {bar} {s['name']:16s}: {s['change_pct']:+6.2f}% | 涨{s.get('up',0)}跌{s.get('down',0)}家 | 领涨:{s.get('leader','')}")

print(f"\n  非科技行业 TOP10:")
for s in non_tech_sorted[:10]:
    print(f"    {s['name']:16s}: {s['change_pct']:+6.2f}% | 领涨:{s.get('leader','')}")

# 概念板块科技TOP
tech_concepts = [c for c in concepts_l3 if any(kw in c["name"] for kw in TECH_KEYWORDS)]
concept_sorted = sorted(tech_concepts, key=lambda x: x.get("change_pct", 0), reverse=True)
print(f"\n  科技概念板块 TOP20 ({len(tech_concepts)} 个科技概念):")
for c in concept_sorted[:20]:
    print(f"    {c['name']:20s}: {c['change_pct']:+6.2f}%")
print(f"\n  科技概念跌幅TOP10:")
for c in concept_sorted[-10:]:
    print(f"    {c['name']:20s}: {c['change_pct']:+6.2f}%")

# ============================================================
# 2. 业绩数据补全（东财业绩预告 + 快报）
# ============================================================
print("\n[2/6] 业绩数据补全（多源聚合）...")

# 2a. Tushare 业绩预告 retry with different params
all_forecast_codes = set()
try:
    # Try with broader date range
    f1 = pro.forecast(start_date="20260101", end_date="20260831",
                       fields="ts_code,ann_date,type,p_change_min,p_change_max,net_profit_min")
    if f1 is not None and not f1.empty:
        f1["p_change_min"] = pd.to_numeric(f1["p_change_min"], errors="coerce")
        positive = f1[f1["type"].isin(["预增", "略增", "扭亏", "续盈"])]
        strong = positive[positive["p_change_min"] >= 30]
        for _, row in strong.iterrows():
            all_forecast_codes.add((row["ts_code"], row["p_change_min"]))
        print(f"  Tushare业绩预告: 预增{len(positive)}只, 高增(>=30%){len(strong)}只")
    else:
        print(f"  Tushare业绩预告: 返回空")
except Exception as e:
    print(f"  Tushare业绩预告: {e}")

# 2b. Try Tushare express (业绩快报)
try:
    expr = pro.express(start_date="20260601", end_date="20260831",
                        fields="ts_code,ann_date,profit,yoy_net_profit")
    if expr is not None and not expr.empty:
        expr["yoy_net_profit"] = pd.to_numeric(expr["yoy_net_profit"], errors="coerce")
        strong_expr = expr[expr["yoy_net_profit"] >= 30]
        for _, row in strong_expr.iterrows():
            all_forecast_codes.add((row["ts_code"], row["yoy_net_profit"]))
        print(f"  Tushare业绩快报: 共{len(expr)}只, 高增(>=30%){len(strong_expr)}只")
    else:
        print(f"  Tushare业绩快报: 返回空")
except Exception as e:
    print(f"  Tushare业绩快报: {e}")

# 2c. 东财 - 从研报中提取盈利预测（reportapi）
print("  东财研报盈利预测...")
report_forecast_codes = set()
try:
    # 通过东财reportapi拉最近有盈利预测上调的股票
    r = em_get("https://reportapi.eastmoney.com/report/list", params={
        "industryCode": "*", "pageSize": "200", "industry": "*",
        "rating": "*", "ratingChange": "调高",
        "beginTime": "2026-06-01", "endTime": "2026-08-01",
        "pageNo": "1", "qType": "0", "fields": "",
    }, timeout=30)
    data = r.json().get("data", [])
    for row in data[:100]:
        code = row.get("stockCode", "")
        this_eps = row.get("predictThisYearEps", 0)
        next_eps = row.get("predictNextYearEps", 0)
        if code and this_eps and next_eps and float(this_eps) > 0 and float(next_eps) > 0:
            growth = (float(next_eps) / float(this_eps) - 1) * 100
            if growth >= 30:
                report_forecast_codes.add((code, growth))
    print(f"  东财研报: 盈利预测高增(>=30%) {len(report_forecast_codes)} 只")
except Exception as e:
    print(f"  东财研报: {e}")

# 合并所有数据源
all_earnings_support = {}
for code, growth in all_forecast_codes | report_forecast_codes:
    if code not in all_earnings_support or growth > all_earnings_support[code]:
        all_earnings_support[code] = growth

print(f"\n  业绩支撑汇总: {len(all_earnings_support)} 只（预增>=30%或有盈利预测上修）")

# ============================================================
# 3. 北向资金流向
# ============================================================
print("\n[3/6] 北向资金分析...")

# 3a. Tushare moneyflow
try:
    # 用moneyflow_hsgt获取沪深港通
    hsgt = pro.moneyflow_hsgt(start_date=JULY_START, end_date=TRADE_END)
    if hsgt is not None and not hsgt.empty:
        total_north = hsgt["north_money"].sum() if "north_money" in hsgt.columns else hsgt["ggt_ss"].sum()
        print(f"  北向资金7月累计净流入: {total_north/1e8:.2f}亿")
except Exception as e:
    print(f"  北向Tushare: {e}")

# 3b. Try another Tushare endpoint
try:
    hsgt2 = pro.hsgt_top10(start_date=JULY_START, end_date=TRADE_END, market_type="N")
    if hsgt2 is not None and not hsgt2.empty:
        print(f"  北向活跃股记录: {len(hsgt2)} 条")
        # Top net buy stocks
        if "buy_amount" in hsgt2.columns and "sell_amount" in hsgt2.columns:
            hsgt2["net_buy"] = hsgt2["buy_amount"] - hsgt2["sell_amount"]
            top_north = hsgt2.groupby("ts_code")["net_buy"].sum().sort_values(ascending=False).head(10)
            print(f"  北向净买入TOP5:")
            for code, amt in top_north.head(5).items():
                print(f"    {code}: {amt/1e8:+.2f}亿")
except Exception as e:
    print(f"  北向TOP10: {e}")

# ============================================================
# 4. 板块资金流向（东财行业板块资金）
# ============================================================
print("\n[4/6] 板块资金流向...")

# 4a. 东财行业资金流
sector_fund_flow = []
try:
    url = "https://push2.eastmoney.com/api/qt/clist/get"
    params = {"pn": "1", "pz": "200", "po": "1", "np": "1",
              "fltt": "2", "invt": "2", "fs": "m:90+t:2",
              "fields": "f2,f3,f4,f12,f14,f62,f66,f72,f78,f184,f66,f69"}
    r = em_get(url, params=params, timeout=15)
    items = r.json().get("data", {}).get("diff", [])
    if isinstance(items, dict): items = list(items.values())
    for it in items:
        sector_fund_flow.append({
            "name": it.get("f14",""), "code": it.get("f12",""),
            "main_net": it.get("f62", 0),
            "super_large_net": it.get("f66", 0),
            "change_pct": it.get("f3", 0),
        })

    # 按主力净流入排序
    fund_sorted = sorted(sector_fund_flow, key=lambda x: x.get("main_net", 0) or 0, reverse=True)
    print("  主力净流入TOP10板块:")
    for s in fund_sorted[:10]:
        name = s["name"]
        main = s.get("main_net", 0) or 0
        super_large = s.get("super_large_net", 0) or 0
        print(f"    {name:16s}: 主力={main/1e8:+.2f}亿 超大单={super_large/1e8:+.2f}亿 涨跌={s['change_pct']}%")

    print("\n  主力净流出TOP10板块:")
    for s in fund_sorted[-10:]:
        name = s["name"]
        main = s.get("main_net", 0) or 0
        print(f"    {name:16s}: 主力={main/1e8:+.2f}亿")

except Exception as e:
    print(f"  板块资金流失败: {e}")

# ============================================================
# 5. 估值对比 - 腾讯实时估值
# ============================================================
print("\n[5/6] 估值对比分析...")

# 拉取各大指数成分股估值中位数（用腾讯API）
# 这里我们直接基于之前已有数据做分析
# 用东财行业PE数据

sector_valuation = []
try:
    url = "https://push2.eastmoney.com/api/qt/clist/get"
    params = {"pn": "1", "pz": "200", "po": "1", "np": "1",
              "fltt": "2", "invt": "2", "fs": "m:90+t:2",
              "fields": "f2,f3,f4,f12,f14,f20,f21,f23"}
    r = em_get(url, params=params, timeout=15)
    items = r.json().get("data", {}).get("diff", [])
    if isinstance(items, dict): items = list(items.values())
    for it in items:
        pe = it.get("f20", 0)
        pb = it.get("f21", 0)
        if pe and pb and float(pe) > 0 and float(pb) > 0 and float(pe) < 1000:
            sector_valuation.append({
                "name": it.get("f14",""), "code": it.get("f12",""),
                "pe": float(pe), "pb": float(pb),
                "change_pct": it.get("f3", 0),
            })

    tech_val = [s for s in sector_valuation if any(kw in s["name"] for kw in TECH_KEYWORDS)]

    # PE中位数
    tech_pes = [s["pe"] for s in tech_val if s["pe"] > 0]
    all_pes = [s["pe"] for s in sector_valuation if s["pe"] > 0]

    print(f"  科技板块PE中位数: {np.median(tech_pes):.1f}x (全市场: {np.median(all_pes):.1f}x)")
    print(f"  科技板块PE最低TOP5:")
    pe_sorted = sorted(tech_val, key=lambda x: x["pe"])[:5]
    for s in pe_sorted:
        print(f"    {s['name']:16s}: PE={s['pe']:.1f}x PB={s['pb']:.2f}x 涨跌={s['change_pct']}%")
    print(f"  科技板块PE最高TOP5:")
    pe_sorted_high = sorted(tech_val, key=lambda x: x["pe"], reverse=True)[:5]
    for s in pe_sorted_high:
        print(f"    {s['name']:16s}: PE={s['pe']:.1f}x PB={s['pb']:.2f}x")

except Exception as e:
    print(f"  估值对比失败: {e}")

# ============================================================
# 6. 量价形态分类
# ============================================================
print("\n[6/6] 量价形态分类...")

# 加载之前Phase 1的个股数据
try:
    stats_df = pd.read_csv(OUTPUT_DIR.parent / "exploration_data" / "stock_stats.csv")
    print(f"  加载个股统计: {len(stats_df)} 只")

    # 量价形态分类
    conditions = [
        (stats_df["july_chg"] > 5) & (stats_df["vol_change_pct"] > 50),
        (stats_df["july_chg"] > 5) & (stats_df["vol_change_pct"] <= 50),
        (stats_df["july_chg"] > 0) & (stats_df["july_chg"] <= 5) & (stats_df["vol_change_pct"] > 30),
        (stats_df["july_chg"] > -5) & (stats_df["july_chg"] <= 0) & (stats_df["vol_change_pct"] > 0),
        (stats_df["july_chg"] > -15) & (stats_df["july_chg"] <= -5),
        (stats_df["july_chg"] <= -15),
    ]
    choices = [
        "放量突破",      # >5% + vol>50%
        "价升量平",      # >5% + vol normal
        "底部放量",      # 0-5% + vol>30%
        "缩量筑底",      # -5%~0% + vol>0
        "缩量下跌",      # -15%~-5%
        "放量杀跌",      # <-15%
    ]
    stats_df["pattern"] = np.select(conditions, choices, default="其他")

    pattern_counts = stats_df["pattern"].value_counts()
    print("  量价形态分布:")
    for p, c in pattern_counts.items():
        bar = "█" * (c // 50)
        print(f"    {p:10s}: {c:5d} 只 {bar}")

    # 放量突破+业绩支撑 = 最值得关注
    gold_stocks = stats_df[
        (stats_df["pattern"].isin(["放量突破", "价升量平", "底部放量"]))
    ].copy()
    gold_stocks["has_earnings"] = gold_stocks["ts_code"].isin(
        [c.split(".")[0] for c in all_earnings_support.keys()])

    print(f"\n  强势形态+业绩支撑: {gold_stocks['has_earnings'].sum()} 只")
    print(f"  强势形态总计: {len(gold_stocks)} 只")

    # 保存
    stats_df.to_csv(OUTPUT_DIR / "stock_patterns.csv", index=False)

except Exception as e:
    print(f"  量价分类失败: {e}")

# ============================================================
# 7. 保存所有深度数据
# ============================================================
print("\n保存深度分析数据...")
deep_data = {
    "meta": {"generated": datetime.now().strftime("%Y-%m-%d %H:%M"), "end": TRADE_END},
    "tech_sectors_l2": tech_sorted,
    "non_tech_sectors_top": non_tech_sorted[:15],
    "tech_concepts": concept_sorted,
    "earnings_support": {k: round(v, 1) for k, v in all_earnings_support.items()},
    "sector_fund_flow": sector_fund_flow,
    "sector_valuation": sector_valuation,
}

class NpEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (np.integer,)): return int(obj)
        if isinstance(obj, (np.floating,)):
            return None if np.isnan(obj) or np.isinf(obj) else float(obj)
        return super().default(obj)

with open(OUTPUT_DIR / "deep_data.json", "w", encoding="utf-8") as f:
    json.dump(deep_data, f, ensure_ascii=False, indent=2, cls=NpEncoder)

print(f"  深度数据已保存至: {OUTPUT_DIR}")
print("\n>>> Phase 2 完成，准备生成HTML报告 <<<")
