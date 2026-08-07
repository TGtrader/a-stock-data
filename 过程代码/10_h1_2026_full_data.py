"""
Phase 7: 全A中报快报标的综合数据采集
- 37只已披露H1 2026快报
- 同比(H1 2025→H1 2026) + 环比(Q1→Q2 2026)
- 12个月K线 + 估值 + 资金流 + 融资融券
"""
import tushare as ts
import pandas as pd
import numpy as np
import requests
import time, json, urllib.request
from datetime import datetime
from pathlib import Path

ts.set_token("53399fa4a4f51a769a4455978feb0b04c88f87d5c916507a61131f34")
pro = ts.pro_api()
UA = "Mozilla/5.0"
OUT = Path(__file__).parent / "h1_2026_data"
OUT.mkdir(exist_ok=True)
now_str = datetime.now().strftime("%Y%m%d_%H%M")

print("=" * 70)
print("Phase 7: A股中报快报标的全量数据采集")
print("=" * 70)

# ============================================================
# 1. 拉取H1 2026 + H1 2025 快报，计算真实同比
# ============================================================
print("\n[1/8] 拉取中报快报 + 计算真实同比...")

# H1 2026
e26 = pro.express(start_date="20260701", end_date="20260831")
e26_dict = {}
for _, r in e26.iterrows():
    code = r["ts_code"]
    e26_dict[code] = {
        "ann_date": str(r.get("ann_date",""))[:10],
        "revenue": float(r.get("revenue",0) or 0),
        "n_income": float(r.get("n_income",0) or 0),
        "diluted_eps": float(r.get("diluted_eps",0) or 0),
        "diluted_roe": float(r.get("diluted_roe",0) or 0),
        "bps": float(r.get("bps",0) or 0),
        "total_assets": float(r.get("total_assets",0) or 0),
        "perf_summary": str(r.get("perf_summary",""))[:200],
    }

# H1 2025
e25 = pro.express(start_date="20250701", end_date="20250831")
e25_dict = {}
for _, r in e25.iterrows():
    code = r["ts_code"]
    e25_dict[code] = {
        "n_income": float(r.get("n_income",0) or 0),
        "revenue": float(r.get("revenue",0) or 0),
        "diluted_eps": float(r.get("diluted_eps",0) or 0),
    }

# 计算真实同比
valid_stocks = {}
for code, info26 in e26_dict.items():
    info25 = e25_dict.get(code)
    if not info25 or info25["n_income"] <= 0 or info26["n_income"] <= 0:
        continue
    yoy_profit = ((info26["n_income"] / info25["n_income"]) - 1) * 100
    yoy_revenue = ((info26["revenue"] / info25["revenue"]) - 1) * 100 if info25["revenue"] > 0 else None
    yoy_eps = ((info26["diluted_eps"] / info25["diluted_eps"]) - 1) * 100 if info25["diluted_eps"] > 0 else None
    if yoy_profit < 0:  # 只保留正增长
        continue
    valid_stocks[code] = {**info26, "yoy_profit": round(yoy_profit, 1),
                          "yoy_revenue": round(yoy_revenue, 1) if yoy_revenue else None,
                          "yoy_eps": round(yoy_eps, 1) if yoy_eps else None}

print(f"  H1 2026快报: {len(e26_dict)} 只")
print(f"  H1 2025快报: {len(e25_dict)} 只")
print(f"  有同比+正增长: {len(valid_stocks)} 只")

# ============================================================
# 2. 拉取季度利润表，计算环比(Q2 vs Q1)
# ============================================================
print("\n[2/8] 拉取季度利润表 + 计算环比...")

codes_list = list(valid_stocks.keys())
qoq_data = {}

for code in codes_list:
    try:
        inc = pro.income(ts_code=code, start_date="20260101", end_date="20260630")
        if inc is None or inc.empty: continue
        inc = inc.sort_values("end_date")
        # Q1 2026: end_date=20260331
        q1_rows = inc[inc["end_date"] == "20260331"]
        q2_h1_rows = inc[inc["end_date"] == "20260630"]  # This is H1 cumulative
        if q1_rows.empty: continue

        q1_ni = float(q1_rows["n_income"].iloc[0] or 0)
        # H1 cumulative from income statement
        h1_inc_ni = float(q2_h1_rows["n_income"].iloc[0] or 0) if not q2_h1_rows.empty else None
        # Q2 single quarter = H1 - Q1
        # Use express H1 data for consistency
        h1_ni = valid_stocks[code]["n_income"]
        q2_ni = h1_ni - q1_ni
        qoq = ((q2_ni / q1_ni) - 1) * 100 if q1_ni > 0 else None

        qoq_data[code] = {
            "q1_ni": round(q1_ni/1e8, 2),
            "q2_ni_est": round(q2_ni/1e8, 2),
            "h1_ni": round(h1_ni/1e8, 2),
            "qoq": round(qoq, 1) if qoq else None,
        }
    except Exception as e:
        pass
    time.sleep(0.15)

for code in codes_list:
    if code in qoq_data:
        valid_stocks[code]["qoq"] = qoq_data[code].get("qoq")
        valid_stocks[code]["q1_ni"] = qoq_data[code].get("q1_ni")
        valid_stocks[code]["q2_ni"] = qoq_data[code].get("q2_ni")
    else:
        valid_stocks[code]["qoq"] = None
        valid_stocks[code]["q1_ni"] = None
        valid_stocks[code]["q2_ni"] = None

cnt_qoq = sum(1 for v in valid_stocks.values() if v.get("qoq") is not None)
print(f"  环比数据: {cnt_qoq} 只")

# ============================================================
# 3. 股票基本信息 + 行业分类
# ============================================================
print("\n[3/8] 拉取基本信息 + 行业分类...")

basic = pro.stock_basic(list_status="L", fields="ts_code,name,industry,market,list_date")
basic_dict = {}
for _, r in basic.iterrows():
    basic_dict[r["ts_code"]] = {"name": r["name"], "industry": r.get("industry",""),
                                 "market": r["market"], "list_date": str(r.get("list_date",""))}

# 精确行业映射
INDUSTRY_MAP = {}
with open(OUT / "industry_map.txt", "w", encoding="utf-8") as f_log:
    for code in codes_list:
        info = basic_dict.get(code, {})
        name = info.get("name", code)
        ind = info.get("industry", "")
        f_log.write(f"{code} {name} {ind}\n")

for code in codes_list:
    info = basic_dict.get(code, {})
    name = info.get("name", "")
    valid_stocks[code]["name"] = name
    valid_stocks[code]["sw_industry"] = info.get("industry", "")

print(f"  基本信息匹配: {sum(1 for c in codes_list if c in basic_dict)} 只")

# ============================================================
# 4. 12个月K线 + 综合技术指标
# ============================================================
print("\n[4/8] 拉取12个月K线 + 技术指标...")

def calc_all_indicators(df):
    df = df.sort_values("trade_date").reset_index(drop=True)
    close = df["close"]
    high = df["high"]
    low = df["low"]
    vol = df["vol"]

    # MACD
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    dif = ema12 - ema26
    dea = dif.ewm(span=9, adjust=False).mean()
    macd_bar = 2 * (dif - dea)

    # MA
    ma5 = close.rolling(5).mean()
    ma10 = close.rolling(10).mean()
    ma20 = close.rolling(20).mean()
    ma60 = close.rolling(60).mean()
    ma120 = close.rolling(120).mean()

    # RSI
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    rsi14 = 100 - (100 / (1 + gain.ewm(alpha=1/14, adjust=False).mean() /
                          loss.ewm(alpha=1/14, adjust=False).mean()))

    # KDJ
    low9 = low.rolling(9).min()
    high9 = high.rolling(9).max()
    rsv = (close - low9) / (high9 - low9) * 100
    k = rsv.ewm(alpha=1/3, adjust=False).mean()
    d = k.ewm(alpha=1/3, adjust=False).mean()
    j = 3 * k - 2 * d

    # 布林带
    boll_mid = close.rolling(20).mean()
    boll_std = close.rolling(20).std()
    boll_up = boll_mid + 2 * boll_std
    boll_dn = boll_mid - 2 * boll_std

    # 量比
    vol_ma5 = vol.rolling(5).mean()
    vol_ratio = vol / vol_ma5.shift(1)

    n = len(df) - 1

    # 长期趋势判断(12个月)
    # 用120日MA斜率
    ma120_vals = ma120.dropna()
    if len(ma120_vals) >= 40:
        x = np.arange(len(ma120_vals[-40:]))
        y = ma120_vals[-40:].values
        slope = np.polyfit(x, y, 1)[0]
        if slope > 0.01: lt_trend = "上升"
        elif slope < -0.01: lt_trend = "下降"
        else: lt_trend = "横盘"
    else:
        lt_trend = "数据不足"

    # 近3个月涨跌幅
    close_vals = close.values
    if len(close_vals) >= 60:
        chg_3m = (close_vals[-1] / close_vals[-60] - 1) * 100
    else:
        chg_3m = None

    # 近1个月涨跌幅
    if len(close_vals) >= 20:
        chg_1m = (close_vals[-1] / close_vals[-20] - 1) * 100
    else:
        chg_1m = None

    # 7月涨跌
    july_mask = df["trade_date"] >= "20260701"
    july_df = df[july_mask]
    if len(july_df) >= 3:
        july_chg = (july_df["close"].iloc[-1] / july_df["close"].iloc[0] - 1) * 100
        july_max_dd = ((july_df["close"] - july_df["close"].cummax()) /
                       july_df["close"].cummax() * 100).min()
        july_vol_avg = july_df["vol"].mean()
        pre_july_vol = df[~july_mask]["vol"].tail(15).mean()
        july_vol_chg = ((july_vol_avg / pre_july_vol - 1) * 100) if pre_july_vol > 0 else 0
    else:
        july_chg = july_max_dd = july_vol_chg = 0

    # 判断量价形态
    if july_chg > 5 and july_vol_chg > 30:
        vp_pattern = "放量突破"
    elif july_chg > 0 and july_vol_chg > 10:
        vp_pattern = "价升量增"
    elif july_chg > -5 and july_chg <= 0 and july_vol_chg < -10:
        vp_pattern = "缩量筑底"
    elif july_chg > -15 and july_chg <= -5:
        vp_pattern = "缩量回调"
    elif july_chg <= -15:
        vp_pattern = "放量杀跌"
    else:
        vp_pattern = "正常波动"

    return {
        "latest": {
            "date": df["trade_date"].iloc[-1],
            "close": float(close.iloc[-1]), "open": float(df["open"].iloc[-1]),
            "high": float(high.iloc[-1]), "low": float(low.iloc[-1]),
            "vol": float(vol.iloc[-1]), "amount": float(df["amount"].iloc[-1]),
            "ma5": float(ma5.iloc[-1]) if not pd.isna(ma5.iloc[-1]) else None,
            "ma10": float(ma10.iloc[-1]) if not pd.isna(ma10.iloc[-1]) else None,
            "ma20": float(ma20.iloc[-1]) if not pd.isna(ma20.iloc[-1]) else None,
            "ma60": float(ma60.iloc[-1]) if not pd.isna(ma60.iloc[-1]) else None,
            "ma120": float(ma120.iloc[-1]) if not pd.isna(ma120.iloc[-1]) else None,
            "dif": float(dif.iloc[-1]) if not pd.isna(dif.iloc[-1]) else None,
            "dea": float(dea.iloc[-1]) if not pd.isna(dea.iloc[-1]) else None,
            "macd_bar": float(macd_bar.iloc[-1]) if not pd.isna(macd_bar.iloc[-1]) else None,
            "k": float(k.iloc[-1]) if not pd.isna(k.iloc[-1]) else None,
            "d": float(d.iloc[-1]) if not pd.isna(d.iloc[-1]) else None,
            "j": float(j.iloc[-1]) if not pd.isna(j.iloc[-1]) else None,
            "rsi14": float(rsi14.iloc[-1]) if not pd.isna(rsi14.iloc[-1]) else None,
            "boll_up": float(boll_up.iloc[-1]) if not pd.isna(boll_up.iloc[-1]) else None,
            "boll_mid": float(boll_mid.iloc[-1]) if not pd.isna(boll_mid.iloc[-1]) else None,
            "boll_dn": float(boll_dn.iloc[-1]) if not pd.isna(boll_dn.iloc[-1]) else None,
            "vol_ratio": float(vol_ratio.iloc[-1]) if not pd.isna(vol_ratio.iloc[-1]) else None,
        },
        "lt_trend": lt_trend,
        "chg_3m": round(chg_3m, 1) if chg_3m else None,
        "chg_1m": round(chg_1m, 1) if chg_1m else None,
        "july_chg": round(july_chg, 2),
        "july_max_dd": round(july_max_dd, 2),
        "july_vol_chg": round(july_vol_chg, 1),
        "vp_pattern": vp_pattern,
        "total_rows": len(df),
    }

all_klines = {}
for code in codes_list:
    try:
        df = pro.daily(ts_code=code, start_date="20250701", end_date="20260722")
        if len(df) < 30: continue
        all_klines[code] = calc_all_indicators(df)
    except: pass
    time.sleep(0.12)
print(f"  K线数据: {len(all_klines)} 只 (12个月)")

# ============================================================
# 5. 腾讯实时估值
# ============================================================
print("\n[5/8] 腾讯实时估值...")

def tencent_batch(clist):
    result = {}
    for batch_start in range(0, len(clist), 30):
        batch = clist[batch_start:batch_start+30]
        pref = []
        for c in batch:
            pure = c.split(".")[0]
            pref.append(f"sh{pure}" if pure.startswith(("6","9")) else f"sz{pure}")
        url = "https://qt.gtimg.cn/q=" + ",".join(pref)
        req = urllib.request.Request(url); req.add_header("User-Agent", UA)
        try:
            resp = urllib.request.urlopen(req, timeout=10)
            data = resp.read().decode("gbk")
            for line in data.strip().split(";"):
                if "=" not in line or '"' not in line: continue
                key = line.split("=")[0].split("_")[-1]
                vals = line.split('"')[1].split("~")
                if len(vals) < 53: continue
                for tc in batch:
                    if tc.split(".")[0] == key[2:]:
                        result[tc] = {
                            "price": float(vals[3]) if vals[3] else 0,
                            "chg_pct": float(vals[32]) if vals[32] else 0,
                            "pe_ttm": float(vals[39]) if vals[39] else 0,
                            "pb": float(vals[46]) if vals[46] else 0,
                            "mcap_yi": float(vals[44]) if vals[44] else 0,
                            "float_mcap": float(vals[45]) if vals[45] else 0,
                            "turnover": float(vals[38]) if vals[38] else 0,
                            "pe_static": float(vals[52]) if vals[52] else 0,
                            "vol_ratio_tt": float(vals[49]) if vals[49] else 0,
                        }; break
        except: pass
    return result

all_quotes = tencent_batch(codes_list)
print(f"  估值数据: {len(all_quotes)} 只")

# ============================================================
# 6. 东财资金流(选前20只重点标的)
# ============================================================
print("\n[6/8] 东财资金流...")
EM_S = requests.Session(); EM_S.headers.update({"User-Agent": UA})
_em_t = [0.0]
def em_g(url, params=None, timeout=15):
    wait = 1.0 - (time.time() - _em_t[0])
    if wait > 0: time.sleep(wait + np.random.uniform(0.2, 0.6))
    try: return EM_S.get(url, params=params, timeout=timeout)
    finally: _em_t[0] = time.time()

# Sort by yoy_profit to pick top stocks for fund flow
sorted_by_growth = sorted(valid_stocks.items(), key=lambda x: x[1]["yoy_profit"], reverse=True)
top20 = [c for c, _ in sorted_by_growth[:20]]

all_fund_flow = {}
for code in top20:
    pure = code.split(".")[0]
    mkt = 1 if pure.startswith("6") else 0
    try:
        r = em_g("https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get",
                 params={"secid": f"{mkt}.{pure}", "fields1":"f1,f2,f3,f7",
                         "fields2":"f51,f52,f53,f54,f55,f56,f57", "lmt":"120"}, timeout=15)
        kls = r.json().get("data",{}).get("klines",[])
        rows = []
        for line in kls:
            p = line.split(",")
            if len(p)>=7:
                rows.append({"date":p[0],"main_net":float(p[1]) if p[1]!="-" else 0,
                             "super_net":float(p[5]) if p[5]!="-" else 0})
        all_fund_flow[code] = rows
    except: pass
    time.sleep(1.3)
print(f"  资金流: {len(all_fund_flow)} 只")

# ============================================================
# 7. 融资融券
# ============================================================
print("\n[7/8] 融资融券数据...")

def em_datacenter(report_name, filter_str="", page_size=5):
    params = {"reportName": report_name, "columns":"ALL","filter":filter_str,
              "pageNumber":"1","pageSize":str(page_size),"sortColumns":"DATE",
              "sortTypes":"-1","source":"WEB","client":"WEB"}
    r = em_g("https://datacenter-web.eastmoney.com/api/data/v1/get", params=params, timeout=15)
    return (r.json().get("result") or {}).get("data", [])

all_margin = {}
for code in codes_list:
    pure = code.split(".")[0]
    try:
        data = em_datacenter("RPTA_WEB_RZRQ_GGMX", filter_str=f'(SCODE="{pure}")', page_size=5)
        if data:
            all_margin[code] = [{"date":str(r.get("DATE",""))[:10],
                                 "rzye":r.get("RZYE",0),"rzmre":r.get("RZMRE",0),
                                 "rzche":r.get("RZCHE",0),"rqye":r.get("RQYE",0)} for r in data]
    except: pass
    time.sleep(0.6)
print(f"  融资融券: {len(all_margin)} 只")

# ============================================================
# 8. 组装 + 多维评分
# ============================================================
print("\n[8/8] 多维综合评分...")

for code in codes_list:
    info = valid_stocks[code]
    k = all_klines.get(code, {})
    q = all_quotes.get(code, {})
    ff = all_fund_flow.get(code, [])
    mg = all_margin.get(code, [])

    # === 综合评分 (0-100) ===
    score = 50

    # 增长(25分)
    yoy = info["yoy_profit"]
    qoq = info.get("qoq")
    if yoy >= 100: score += 12
    elif yoy >= 50: score += 8
    elif yoy >= 30: score += 5
    elif yoy >= 15: score += 2
    if qoq and qoq >= 30: score += 8
    elif qoq and qoq >= 10: score += 5
    elif qoq and qoq >= 0: score += 2
    elif qoq and qoq < 0: score -= 5
    # Revenue growth bonus
    yoy_rev = info.get("yoy_revenue")
    if yoy_rev and yoy_rev >= 20: score += 5
    elif yoy_rev and yoy_rev >= 10: score += 3

    # 估值(20分)
    pe = q.get("pe_ttm", 0)
    pb = q.get("pb", 0)
    if 0 < pe < 25: score += 12
    elif 0 < pe < 40: score += 8
    elif 0 < pe < 60: score += 4
    elif pe > 200: score -= 5
    elif pe <= 0: score -= 3
    if 0 < pb < 2: score += 5
    elif 0 < pb < 4: score += 3
    elif pb > 10: score -= 3

    # 技术(20分)
    lt_trend = k.get("lt_trend", "")
    dif_val = k.get("latest",{}).get("dif",0) or 0
    dea_val = k.get("latest",{}).get("dea",0) or 0
    rsi = k.get("latest",{}).get("rsi14",50) or 50
    j_val = k.get("latest",{}).get("j",50) or 50
    close_p = k.get("latest",{}).get("close",0) or 0
    ma20_v = k.get("latest",{}).get("ma20",close_p) or close_p
    ma60_v = k.get("latest",{}).get("ma60",close_p) or close_p

    if lt_trend == "上升": score += 6
    elif lt_trend == "横盘": score += 3
    if dif_val > dea_val: score += 5
    if rsi < 35: score += 5  # 超卖
    elif rsi > 75: score -= 3  # 超买
    if close_p > ma20_v: score += 2
    if close_p > ma60_v: score += 2

    # 资金(15分)
    if ff:
        main_20 = sum(x["main_net"] for x in ff[-20:])
        super_20 = sum(x["super_net"] for x in ff[-20:])
        if main_20 > 5e8: score += 8
        elif main_20 > 1e8: score += 5
        elif main_20 > 0: score += 2
        elif main_20 < -1e8: score -= 5
        if super_20 > 1e8: score += 3
    if mg and len(mg)>=2:
        m_chg = (mg[0]["rzye"]/mg[1]["rzye"]-1)*100 if mg[1]["rzye"]>0 else 0
        if m_chg > 3: score += 3
        elif m_chg > 0: score += 1
        elif m_chg < -3: score -= 3

    # 量价(10分)
    vp = k.get("vp_pattern","")
    if vp in ("放量突破","价升量增"): score += 8
    elif vp == "缩量筑底": score += 5
    elif vp == "放量杀跌": score -= 5

    # ROE bonus
    roe = info.get("diluted_roe", 0)
    if roe > 15: score += 5
    elif roe > 10: score += 3
    elif roe < 0: score -= 3

    info["score"] = min(100, max(0, score))
    info["score_detail"] = {
        "growth_yoy": yoy, "growth_qoq": qoq,
        "pe": pe, "pb": pb,
        "lt_trend": lt_trend, "macd": "金叉" if dif_val>dea_val else "死叉",
        "rsi14": rsi, "vp_pattern": vp,
    }

# 排序
ranked = sorted(valid_stocks.items(), key=lambda x: x[1]["score"], reverse=True)
print(f"\n  TOP20 综合评分:")
for i, (code, info) in enumerate(ranked[:20], 1):
    name = info["name"]
    qoq_val = info.get('qoq')
    qoq_str = f'{qoq_val:.0f}%' if qoq_val is not None else 'N/A'
    pe_val = all_quotes.get(code,{}).get('pe_ttm',0) or 0
    print(f"  {i:2d}. {name:10s} score={info['score']}/100 yoy={info['yoy_profit']:.0f}% qoq={qoq_str} PE={pe_val:.0f}x")

# ============================================================
# 保存
# ============================================================
export = {
    "meta": {"generated": datetime.now().strftime("%Y-%m-%d %H:%M"), "stock_count": len(valid_stocks)},
    "stocks": valid_stocks,
    "klines": all_klines,
    "quotes": all_quotes,
    "fund_flow": all_fund_flow,
    "margin": all_margin,
}

class NpEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (np.integer,)): return int(obj)
        if isinstance(obj, (np.floating,)):
            return None if np.isnan(obj) or np.isinf(obj) else float(obj)
        return super().default(obj)

fpath = OUT / "h1_2026_full.json"
with open(fpath, "w", encoding="utf-8") as f:
    json.dump(export, f, ensure_ascii=False, indent=2, cls=NpEncoder)
print(f"\n[完成] {fpath} ({fpath.stat().st_size/1024:.1f} KB)")
print(f"覆盖: {len(valid_stocks)} 只有效标的")
