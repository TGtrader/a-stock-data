"""
Phase 4: 信创/网安/算力 三大板块深度挖掘
- 个股量价数据 + 技术指标
- 东财研报拉取 (行业地位/竞争格局)
- 资金流向 + 融资融券
- 板块归属
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
OUT = Path(__file__).parent / "sector_data"
OUT.mkdir(exist_ok=True)

TRADE_END = "20260722"
START = "20260301"

# ===== 三大板块目标标的 =====
TARGETS = {
    "信创": {
        "688041.SH": "海光信息",
        "688111.SH": "金山办公",
        "000977.SZ": "浪潮信息",
        "688047.SH": "龙芯中科",
        "603019.SH": "中科曙光",
        "002819.SZ": "东方中科",
    },
    "网络安全": {
        "300454.SZ": "深信服",
        "300369.SZ": "绿盟科技",
        "688561.SH": "奇安信",
        "002439.SZ": "启明星辰",
        "688023.SH": "安恒信息",
    },
    "算力": {
        "300308.SZ": "中际旭创",
        "300502.SZ": "新易盛",
        "688041.SH": "海光信息",
        "688256.SH": "寒武纪",
        "601138.SH": "工业富联",
        "002463.SZ": "沪电股份",
    },
}

# 去重后所有代码
ALL_CODES = list(set([c for v in TARGETS.values() for c in v]))
ALL_NAMES = {}
for v in TARGETS.values():
    for c, n in v.items():
        ALL_NAMES[c] = n

print("=" * 60)
print("Phase 4: 信创·网安·算力 深度挖掘")
print(f"目标标的: {len(ALL_CODES)} 只")
print("=" * 60)

# ============================================================
# 1. 东财研报拉取
# ============================================================
print("\n[1/5] 拉取东财研报...")

EM_SESSION = requests.Session()
EM_SESSION.headers.update({"User-Agent": UA})
_em_last = [0.0]

def em_get(url, params=None, timeout=20):
    wait = 1.0 - (time.time() - _em_last[0])
    if wait > 0: time.sleep(wait + np.random.uniform(0.2, 0.6))
    try: return EM_SESSION.get(url, params=params, timeout=timeout)
    finally: _em_last[0] = time.time()

all_reports = {}
for code in ALL_CODES:
    name = ALL_NAMES.get(code, code)
    pure = code.split(".")[0]
    try:
        params = {
            "industryCode": "*", "pageSize": "20", "industry": "*",
            "rating": "*", "ratingChange": "*",
            "beginTime": "2026-01-01", "endTime": "2026-08-01",
            "pageNo": "1", "fields": "", "qType": "0",
            "code": pure,
        }
        r = em_get("https://reportapi.eastmoney.com/report/list", params=params, timeout=30)
        d = r.json()
        rows = d.get("data", [])
        all_reports[code] = []
        for row in rows[:8]:
            all_reports[code].append({
                "title": row.get("title", ""),
                "org": row.get("orgSName", ""),
                "date": (row.get("publishDate") or "")[:10],
                "rating": row.get("emRatingName", ""),
                "eps_this": row.get("predictThisYearEps", 0),
                "eps_next": row.get("predictNextYearEps", 0),
                "eps_next2": row.get("predictNextTwoYearEps", 0),
                "industry": row.get("indvInduName", ""),
            })
        print(f"  {name}: {len(all_reports[code])} 篇研报")
    except Exception as e:
        all_reports[code] = []
        print(f"  {name}: 研报失败 ({str(e)[:40]})")
    time.sleep(1.3)

# ============================================================
# 2. Tushare 日K线 + 技术指标
# ============================================================
print("\n[2/5] 拉取日K线+计算技术指标...")

def calc_macd(close):
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    dif = ema12 - ema26
    dea = dif.ewm(span=9, adjust=False).mean()
    bar = 2 * (dif - dea)
    return dif, dea, bar

def calc_kdj(high, low, close, n=9):
    low_n = low.rolling(n).min()
    high_n = high.rolling(n).max()
    rsv = (close - low_n) / (high_n - low_n) * 100
    k = rsv.ewm(alpha=1/3, adjust=False).mean()
    d = k.ewm(alpha=1/3, adjust=False).mean()
    j = 3 * k - 2 * d
    return k, d, j

all_klines = {}
for code in ALL_CODES:
    name = ALL_NAMES.get(code, code)
    try:
        df = pro.daily(ts_code=code, start_date=START, end_date=TRADE_END)
        if df.empty: continue
        df = df.sort_values("trade_date").reset_index(drop=True)
        close = df["close"]
        high = df["high"]
        low = df["low"]
        vol = df["vol"]
        amount = df["amount"]

        # MACD
        dif, dea, bar = calc_macd(close)
        # KDJ
        k, d, j = calc_kdj(high, low, close)
        # MA
        ma5 = close.rolling(5).mean()
        ma10 = close.rolling(10).mean()
        ma20 = close.rolling(20).mean()
        ma60 = close.rolling(60).mean()
        # 量比
        vol_ma5 = vol.rolling(5).mean()
        vol_ratio = vol / vol_ma5.shift(1)
        # OBV
        obv = (vol * np.sign(close.diff())).cumsum()
        # RSI
        delta = close.diff()
        gain = delta.where(delta > 0, 0.0)
        loss = -delta.where(delta < 0, 0.0)
        rsi14 = 100 - (100 / (1 + gain.ewm(alpha=1/14, adjust=False).mean() / loss.ewm(alpha=1/14, adjust=False).mean()))

        latest_idx = len(df) - 1
        # July sub-data
        july_mask = df["trade_date"] >= "20260701"
        july_df = df[july_mask]
        july_chg = (july_df["close"].iloc[-1] / july_df["close"].iloc[0] - 1) * 100 if len(july_df) > 1 else 0
        july_max_dd = ((july_df["close"] - july_df["close"].cummax()) / july_df["close"].cummax() * 100).min() if len(july_df) > 1 else 0
        july_vol_avg = july_df["vol"].mean() if len(july_df) > 0 else 0
        june_vol_avg = df[~july_mask]["vol"].mean() if (~july_mask).sum() > 0 else july_vol_avg
        vol_change = ((july_vol_avg / june_vol_avg - 1) * 100) if june_vol_avg > 0 else 0

        # OBV趋势
        obv_recent = obv.iloc[-10:].values
        obv_trend = "上升" if obv_recent[-1] > obv_recent[0] else "下降"

        all_klines[code] = {
            "name": name,
            "latest": {
                "date": df["trade_date"].iloc[-1],
                "close": float(close.iloc[-1]),
                "open": float(df["open"].iloc[-1]),
                "high": float(high.iloc[-1]),
                "low": float(low.iloc[-1]),
                "vol": float(vol.iloc[-1]),
                "amount": float(amount.iloc[-1]),
                "ma5": float(ma5.iloc[-1]) if not pd.isna(ma5.iloc[-1]) else None,
                "ma10": float(ma10.iloc[-1]) if not pd.isna(ma10.iloc[-1]) else None,
                "ma20": float(ma20.iloc[-1]) if not pd.isna(ma20.iloc[-1]) else None,
                "ma60": float(ma60.iloc[-1]) if not pd.isna(ma60.iloc[-1]) else None,
                "dif": float(dif.iloc[-1]) if not pd.isna(dif.iloc[-1]) else None,
                "dea": float(dea.iloc[-1]) if not pd.isna(dea.iloc[-1]) else None,
                "macd_bar": float(bar.iloc[-1]) if not pd.isna(bar.iloc[-1]) else None,
                "k": float(k.iloc[-1]) if not pd.isna(k.iloc[-1]) else None,
                "d": float(d.iloc[-1]) if not pd.isna(d.iloc[-1]) else None,
                "j": float(j.iloc[-1]) if not pd.isna(j.iloc[-1]) else None,
                "rsi14": float(rsi14.iloc[-1]) if not pd.isna(rsi14.iloc[-1]) else None,
                "vol_ratio": float(vol_ratio.iloc[-1]) if not pd.isna(vol_ratio.iloc[-1]) else None,
            },
            "july_chg": round(july_chg, 2),
            "july_max_dd": round(july_max_dd, 2),
            "vol_change_pct": round(vol_change, 1),
            "obv_trend": obv_trend,
            "df": df,
        }
        print(f"  {name}: 共{len(df)}条K线, 7月涨跌{july_chg:+.2f}%")
    except Exception as e:
        print(f"  {name}: 失败 - {e}")
    time.sleep(0.2)

# ============================================================
# 3. 腾讯实时估值
# ============================================================
print("\n[3/5] 腾讯实时估值...")

def tencent_quote(codes_list):
    prefixed = []
    for c in codes_list:
        pure = c.split(".")[0]
        if pure.startswith(("6", "9")): prefixed.append(f"sh{pure}")
        else: prefixed.append(f"sz{pure}")
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
        # Map back to ts_code format
        for tc in codes_list:
            if tc.split(".")[0] == code_num:
                result[tc] = {
                    "price": float(vals[3]) if vals[3] else 0,
                    "change_pct": float(vals[32]) if vals[32] else 0,
                    "pe_ttm": float(vals[39]) if vals[39] else 0,
                    "pb": float(vals[46]) if vals[46] else 0,
                    "mcap_yi": float(vals[44]) if vals[44] else 0,
                    "turnover_pct": float(vals[38]) if vals[38] else 0,
                    "vol_ratio_tt": float(vals[49]) if vals[49] else 0,
                    "pe_static": float(vals[52]) if vals[52] else 0,
                    "amplitude": float(vals[43]) if vals[43] else 0,
                }
                break
    return result

all_quotes = tencent_quote(ALL_CODES)
for code, q in all_quotes.items():
    name = ALL_NAMES.get(code, code)
    print(f"  {name}: PE={q['pe_ttm']:.1f}x PB={q['pb']:.2f}x 市值={q['mcap_yi']:.0f}亿 换手={q['turnover_pct']:.2f}%")

# ============================================================
# 4. 资金流向（东财push2his 120日）
# ============================================================
print("\n[4/5] 资金流向（选重点标的）...")

# 每个板块选前3只拉资金流
fund_flow = {}
KEY_FUND = ["688041.SH", "000977.SZ", "688111.SH", "300454.SZ", "300369.SZ", "688561.SH",
            "300308.SZ", "300502.SZ", "688256.SH"]

for code in KEY_FUND:
    if code not in ALL_CODES: continue
    name = ALL_NAMES.get(code, code)
    pure = code.split(".")[0]
    market_code = 1 if pure.startswith("6") else 0
    try:
        url = "https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get"
        params = {"secid": f"{market_code}.{pure}", "fields1": "f1,f2,f3,f7",
                  "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65",
                  "lmt": "60"}
        r = em_get(url, params=params, timeout=15)
        klines = r.json().get("data", {}).get("klines", [])
        rows = []
        for line in klines:
            parts = line.split(",")
            if len(parts) >= 7:
                rows.append({"date": parts[0],
                             "main_net": float(parts[1]) if parts[1] != "-" else 0,
                             "super_net": float(parts[5]) if parts[5] != "-" else 0})
        fund_flow[code] = rows
        if rows:
            recent_20_main = sum(r["main_net"] for r in rows[-20:])
            print(f"  {name}: 近20日主力={recent_20_main/1e8:+.2f}亿")
    except Exception as e:
        print(f"  {name}: 资金流失败")
    time.sleep(1.5)

# ============================================================
# 5. 板块归属（东财slist）
# ============================================================
print("\n[5/5] 板块归属+概念标签...")

all_blocks = {}
BLOCK_KEY = ["688041.SH", "000977.SZ", "300454.SZ", "300308.SZ"]
for code in BLOCK_KEY:
    pure = code.split(".")[0]
    market_code = 1 if pure.startswith("6") else 0
    try:
        params = {"fltt": "2", "invt": "2", "secid": f"{market_code}.{pure}",
                  "spt": "3", "pi": "0", "pz": "100", "po": "1",
                  "fields": "f12,f14,f3,f128"}
        r = em_get("https://push2.eastmoney.com/api/qt/slist/get", params=params, timeout=15)
        items = r.json().get("data", {}).get("diff", [])
        if isinstance(items, dict): items = list(items.values())
        all_blocks[code] = [{"name": i.get("f14",""), "code": i.get("f12",""),
                              "change_pct": i.get("f3","")} for i in items]
        tags = [b["name"] for b in all_blocks[code] if any(kw in b["name"] for kw in ["信创","安全","算力","AI","芯片","国产","数据","云"])]
        print(f"  {ALL_NAMES.get(code, code)}: {tags[:8]}")
    except Exception as e:
        all_blocks[code] = []
        print(f"  {ALL_NAMES.get(code, code)}: 失败")
    time.sleep(1.2)

# ============================================================
# 6. 保存数据
# ============================================================
print("\n保存数据...")

# 清除DataFrame（不可序列化）
klines_export = {}
for code, info in all_klines.items():
    t = info["latest"]
    klines_export[code] = {
        "name": info["name"],
        "latest": t,
        "july_chg": info["july_chg"],
        "july_max_dd": info["july_max_dd"],
        "vol_change_pct": info["vol_change_pct"],
        "obv_trend": info["obv_trend"],
    }

sector_data = {
    "meta": {"generated": datetime.now().strftime("%Y-%m-%d %H:%M"), "end": TRADE_END},
    "targets": TARGETS,
    "reports": all_reports,
    "klines": klines_export,
    "quotes": all_quotes,
    "fund_flow": fund_flow,
    "blocks": all_blocks,
}

class NpEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (np.integer,)): return int(obj)
        if isinstance(obj, (np.floating,)):
            return None if np.isnan(obj) or np.isinf(obj) else float(obj)
        return super().default(obj)

with open(OUT / "sector_deep.json", "w", encoding="utf-8") as f:
    json.dump(sector_data, f, ensure_ascii=False, indent=2, cls=NpEncoder)

print(f"  数据已保存: {OUT / 'sector_deep.json'}")
print(f"  大小: {(OUT / 'sector_deep.json').stat().st_size / 1024:.1f} KB")
print("\n>>> Phase 4 完成，准备生成报告 <<<")
