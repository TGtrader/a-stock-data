"""
Phase 6: 33只业绩高增标的深度挖掘
- 精确拉取业绩预增>=30%标的
- 行业分类 + 估值预测 + 研报观点
- 量价数据 + 技术指标
"""
import tushare as ts
import pandas as pd
import numpy as np
import requests
import time
import json
import urllib.request
from datetime import datetime
from pathlib import Path

ts.set_token("53399fa4a4f51a769a4455978feb0b04c88f87d5c916507a61131f34")
pro = ts.pro_api()
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
OUT = Path(__file__).parent / "earnings_data"
OUT.mkdir(exist_ok=True)

TRADE_END = "20260722"
START = "20260301"

# 东财限流
EM_SESSION = requests.Session()
EM_SESSION.headers.update({"User-Agent": UA})
_em_last = [0.0]

def em_get(url, params=None, timeout=20):
    wait = 1.2 - (time.time() - _em_last[0])
    if wait > 0: time.sleep(wait + np.random.uniform(0.2, 0.6))
    try: return EM_SESSION.get(url, params=params, timeout=timeout)
    finally: _em_last[0] = time.time()

print("=" * 60)
print("Phase 6: 33只业绩高增标的深度挖掘")
print("=" * 60)

# ============================================================
# 1. 精确拉取业绩预增>=30%标的
# ============================================================
print("\n[1/5] 拉取业绩预增数据...")

earnings_stocks = {}

# 1a. Tushare 业绩预告
try:
    f1 = pro.forecast(start_date="20260101", end_date="20260831",
                       fields="ts_code,ann_date,type,p_change_min,p_change_max,net_profit_min,summary")
    if f1 is not None and not f1.empty:
        f1["p_change_min"] = pd.to_numeric(f1["p_change_min"], errors="coerce")
        positive = f1[f1["type"].isin(["预增", "略增", "扭亏", "续盈"])]
        strong = positive[positive["p_change_min"] >= 30].copy()
        for _, row in strong.iterrows():
            code = row["ts_code"]
            if code not in earnings_stocks or row["p_change_min"] > earnings_stocks[code]["growth"]:
                earnings_stocks[code] = {
                    "growth": float(row["p_change_min"]),
                    "growth_max": float(row.get("p_change_max", 0)) if pd.notna(row.get("p_change_max")) else None,
                    "profit_min": float(row.get("net_profit_min", 0)) if pd.notna(row.get("net_profit_min")) else None,
                    "type": row["type"],
                    "ann_date": str(row.get("ann_date", ""))[:10],
                    "source": "业绩预告",
                }
        print(f"  Tushare业绩预告: 预增>=30% → {len(earnings_stocks)} 只")
except Exception as e:
    print(f"  Tushare预告失败: {e}")

# 1b. Tushare 业绩快报
try:
    expr = pro.express(start_date="20260601", end_date="20260831",
                        fields="ts_code,ann_date,profit,yoy_net_profit")
    if expr is not None and not expr.empty:
        expr["yoy_net_profit"] = pd.to_numeric(expr["yoy_net_profit"], errors="coerce")
        strong_expr = expr[expr["yoy_net_profit"] >= 30]
        for _, row in strong_expr.iterrows():
            code = row["ts_code"]
            growth = float(row["yoy_net_profit"])
            if code not in earnings_stocks or growth > earnings_stocks[code]["growth"]:
                earnings_stocks[code] = {
                    "growth": growth,
                    "profit_min": float(row.get("profit", 0)) if pd.notna(row.get("profit")) else None,
                    "type": "业绩快报",
                    "ann_date": str(row.get("ann_date", ""))[:10],
                    "source": "业绩快报",
                }
        print(f"  Tushare业绩快报: >=30% → 新增至 {len(earnings_stocks)} 只")
except Exception as e:
    print(f"  Tushare快报失败: {e}")

# 1c. 东财研报盈利预测补充
try:
    for page in range(1, 4):
        params = {
            "industryCode": "*", "pageSize": "100", "industry": "*",
            "rating": "*", "ratingChange": "*",
            "beginTime": "2026-05-01", "endTime": "2026-08-01",
            "pageNo": str(page), "qType": "0", "fields": "",
        }
        r = em_get("https://reportapi.eastmoney.com/report/list", params=params, timeout=30)
        for row in (r.json().get("data", []) or []):
            code_raw = row.get("stockCode", "")
            ts_code = f"{code_raw}.SH" if code_raw.startswith("6") else f"{code_raw}.SZ"
            eps_this = float(row.get("predictThisYearEps", 0) or 0)
            eps_next = float(row.get("predictNextYearEps", 0) or 0)
            if eps_this > 0 and eps_next > 0:
                growth = (eps_next / eps_this - 1) * 100
                if growth >= 30 and ts_code not in earnings_stocks:
                    earnings_stocks[ts_code] = {
                        "growth": round(growth, 1),
                        "type": "分析师预测",
                        "source": "东财研报",
                        "eps_this": round(eps_this, 2),
                        "eps_next": round(eps_next, 2),
                    }
    print(f"  东财盈利预测补充 → 总计 {len(earnings_stocks)} 只")
except Exception as e:
    print(f"  东财研报补充失败: {e}")

# 排序取前35只
sorted_earnings = sorted(earnings_stocks.items(), key=lambda x: x[1]["growth"], reverse=True)
TOP_N = min(35, len(sorted_earnings))
top_stocks = dict(sorted_earnings[:TOP_N])

print(f"\n  最终入选: {len(top_stocks)} 只（业绩增速TOP{TOP_N}）")
for i, (code, info) in enumerate(sorted_earnings[:TOP_N], 1):
    print(f"  {i:2d}. {code:12s} 增速={info['growth']:+.1f}% 来源={info.get('source','?')}")

# ============================================================
# 2. 股票基本信息 + 行业分类
# ============================================================
print("\n[2/5] 拉取基本信息+行业分类...")

codes_list = list(top_stocks.keys())
try:
    basic = pro.stock_basic(list_status="L", fields="ts_code,name,industry,market,list_date")
    basic_dict = {}
    for _, row in basic.iterrows():
        basic_dict[row["ts_code"]] = {
            "name": row["name"], "industry": row.get("industry", ""),
            "market": row["market"], "list_date": str(row.get("list_date", "")),
        }
    print(f"  基本信息: {len([c for c in codes_list if c in basic_dict])} 只匹配")
except:
    basic_dict = {}

# 手动行业归类
def classify_industry(code, info):
    name = basic_dict.get(code, {}).get("name", "")
    ind = basic_dict.get(code, {}).get("industry", "")
    keywords = {
        "CXO/医药": ["医药", "药", "医疗", "生物", "化学制药", "中药", "CXO", "CRO", "CDMO", "康龙化成", "药明", "普洛"],
        "电力设备/新能源": ["电力", "电网", "电气", "充电桩", "光伏", "储能", "风电", "逆变器", "变压器", "电缆"],
        "半导体/电子": ["半导体", "芯片", "电子", "光刻", "封测", "晶圆", "集成电路", "PCB", "元器件"],
        "AI算力/通信": ["算力", "通信", "光模块", "服务器", "AI", "人工智能", "数据", "云计算"],
        "汽车/零部件": ["汽车", "新能源车", "锂电", "电池", "零部件", "模具"],
        "化工/材料": ["化工", "材料", "化学", "塑料", "橡胶", "钛白粉"],
        "机械/设备": ["机械", "设备", "机器人", "自动化", "机床"],
        "消费/其他": ["食品", "饮料", "家电", "纺织", "商贸", "旅游"],
        "有色/资源": ["有色", "钢铁", "煤炭", "矿业", "黄金"],
    }
    for cat, kws in keywords.items():
        if any(kw in name or kw in ind for kw in kws):
            return cat
    return f"其他({ind[:20] if ind else '未知'})"

for code in codes_list:
    info = top_stocks[code]
    info["industry_cat"] = classify_industry(code, info)
    info["name"] = basic_dict.get(code, {}).get("name", code)

# 行业分布
from collections import Counter
ind_dist = Counter(top_stocks[c]["industry_cat"] for c in top_stocks)
print("\n  行业分布:")
for cat, cnt in ind_dist.most_common():
    stocks_in_cat = [f"{top_stocks[c]['name']}({c.split('.')[0]})" for c in top_stocks if top_stocks[c]["industry_cat"] == cat]
    print(f"    {cat}: {cnt}只 → {', '.join(stocks_in_cat[:8])}")

# ============================================================
# 3. 日K线数据 + 技术指标
# ============================================================
print("\n[3/5] 拉取日K线+估值...")

def calc_macd(close):
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    dif = ema12 - ema26
    dea = dif.ewm(span=9, adjust=False).mean()
    return dif, dea, 2*(dif-dea)

all_klines = {}
for code in codes_list[:35]:
    info = top_stocks[code]
    name = info.get("name", code)
    try:
        df = pro.daily(ts_code=code, start_date=START, end_date=TRADE_END)
        if df.empty: continue
        df = df.sort_values("trade_date").reset_index(drop=True)
        close = df["close"]
        dif, dea, bar = calc_macd(close)
        ma5 = close.rolling(5).mean()
        ma10 = close.rolling(10).mean()
        ma20 = close.rolling(20).mean()
        delta = close.diff()
        gain = delta.where(delta>0, 0.0)
        loss = -delta.where(delta<0, 0.0)
        rsi14 = 100 - (100/(1+gain.ewm(alpha=1/14,adjust=False).mean()/loss.ewm(alpha=1/14,adjust=False).mean()))

        july_mask = df["trade_date"] >= "20260701"
        july_df = df[july_mask]
        if len(july_df) > 1:
            july_chg = (july_df["close"].iloc[-1]/july_df["close"].iloc[0]-1)*100
            july_dd = ((july_df["close"]-july_df["close"].cummax())/july_df["close"].cummax()*100).min()
        else:
            july_chg = 0; july_dd = 0

        vol = df["vol"]
        july_vol = vol[july_mask].mean() if july_mask.any() else 0
        june_vol = vol[~july_mask].mean() if (~july_mask).any() else 0
        vol_chg = ((july_vol/june_vol-1)*100) if june_vol>0 else 0

        last = len(df)-1
        all_klines[code] = {
            "latest": {
                "close": float(close.iloc[-1]), "ma5": float(ma5.iloc[-1]) if not pd.isna(ma5.iloc[-1]) else None,
                "ma10": float(ma10.iloc[-1]) if not pd.isna(ma10.iloc[-1]) else None,
                "ma20": float(ma20.iloc[-1]) if not pd.isna(ma20.iloc[-1]) else None,
                "dif": float(dif.iloc[-1]) if not pd.isna(dif.iloc[-1]) else None,
                "dea": float(dea.iloc[-1]) if not pd.isna(dea.iloc[-1]) else None,
                "macd_bar": float(bar.iloc[-1]) if not pd.isna(bar.iloc[-1]) else None,
                "rsi14": float(rsi14.iloc[-1]) if not pd.isna(rsi14.iloc[-1]) else None,
            },
            "july_chg": round(july_chg, 2),
            "july_max_dd": round(july_dd, 2),
            "vol_chg_pct": round(vol_chg, 1),
            "rows": len(df),
        }
    except Exception as e:
        pass
    time.sleep(0.15)

print(f"  K线数据: {len(all_klines)} 只")

# 腾讯估值
def tencent_quote(codes_list):
    prefixed = []
    for c in codes_list:
        pure = c.split(".")[0]
        prefixed.append(f"sh{pure}" if pure.startswith(("6","9")) else f"sz{pure}")
    url = "https://qt.gtimg.cn/q=" + ",".join(prefixed)
    req = urllib.request.Request(url)
    req.add_header("User-Agent", UA)
    resp = urllib.request.urlopen(req, timeout=10)
    data = resp.read().decode("gbk")
    result = {}
    for line in data.strip().split(";"):
        if not line.strip() or "=" not in line or '"' not in line: continue
        key = line.split("=")[0].split("_")[-1]
        vals = line.split('"')[1].split("~")
        if len(vals) < 53: continue
        code_num = key[2:]
        for tc in codes_list:
            if tc.split(".")[0] == code_num:
                result[tc] = {
                    "price": float(vals[3]) if vals[3] else 0,
                    "change_pct": float(vals[32]) if vals[32] else 0,
                    "pe_ttm": float(vals[39]) if vals[39] else 0,
                    "pb": float(vals[46]) if vals[46] else 0,
                    "mcap_yi": float(vals[44]) if vals[44] else 0,
                    "turnover_pct": float(vals[38]) if vals[38] else 0,
                }
                break
    return result

all_quotes = tencent_quote(codes_list)
print(f"  腾讯估值: {len(all_quotes)} 只")

# ============================================================
# 4. 东财研报拉取
# ============================================================
print("\n[4/5] 拉取东财研报...")

all_reports = {}
for code in codes_list[:35]:
    pure = code.split(".")[0]
    name = top_stocks[code].get("name", code)
    try:
        params = {
            "industryCode": "*", "pageSize": "10", "industry": "*",
            "rating": "*", "ratingChange": "*",
            "beginTime": "2026-01-01", "endTime": "2026-08-01",
            "pageNo": "1", "qType": "0", "code": pure,
        }
        r = em_get("https://reportapi.eastmoney.com/report/list", params=params, timeout=30)
        rows = r.json().get("data", [])
        all_reports[code] = []
        for row in rows[:5]:
            all_reports[code].append({
                "title": row.get("title","")[:80],
                "org": row.get("orgSName",""),
                "date": (row.get("publishDate") or "")[:10],
                "rating": row.get("emRatingName",""),
                "eps_this": row.get("predictThisYearEps",0),
                "eps_next": row.get("predictNextYearEps",0),
                "eps_next2": row.get("predictNextTwoYearEps",0),
            })
        if all_reports[code]:
            print(f"  {name}: {len(all_reports[code])}篇")
    except:
        all_reports[code] = []
    time.sleep(1.3)

# ============================================================
# 5. 保存数据
# ============================================================
print("\n[5/5] 保存...")

# 构建权重评分
for code in top_stocks:
    k = all_klines.get(code, {})
    q = all_quotes.get(code, {})
    growth = top_stocks[code]["growth"]
    july = k.get("july_chg", 0)
    pe = q.get("pe_ttm", 0)

    # 综合评分 0-100
    score = 50
    if growth >= 100: score += 15
    elif growth >= 50: score += 8
    elif growth >= 30: score += 4
    if 0 < pe < 30: score += 10
    elif 0 < pe < 50: score += 5
    elif pe > 100: score -= 10
    if july > 5: score += 10
    elif july > 0: score += 5
    elif july < -10: score -= 8
    top_stocks[code]["score"] = min(100, max(0, score))

export = {
    "meta": {"generated": datetime.now().strftime("%Y-%m-%d %H:%M"), "count": len(top_stocks)},
    "stocks": top_stocks,
    "klines": all_klines,
    "quotes": all_quotes,
    "reports": all_reports,
}

class NpEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (np.integer,)): return int(obj)
        if isinstance(obj, (np.floating,)):
            return None if np.isnan(obj) or np.isinf(obj) else float(obj)
        return super().default(obj)

with open(OUT / "earnings_stocks.json", "w", encoding="utf-8") as f:
    json.dump(export, f, ensure_ascii=False, indent=2, cls=NpEncoder)

print(f"  数据: {OUT / 'earnings_stocks.json'}")
print(f"  大小: {(OUT / 'earnings_stocks.json').stat().st_size/1024:.1f} KB")
print("\n>>> Phase 6 完成 <<<")
