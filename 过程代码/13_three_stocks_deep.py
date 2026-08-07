"""
Phase 8: 亚联机械·思源电气·厦钨新能 三只标的深度分析
- 12月K线全技术指标 + 量价关系
- 东财研报(行业地位/竞争格局/盈利预测)
- 资金流+融资融券+板块归属
- 估值多维度对比 + PEG框架
"""
import tushare as ts, pandas as pd, numpy as np, requests, time, json, urllib.request
from datetime import datetime
from pathlib import Path

ts.set_token("53399fa4a4f51a769a4455978feb0b04c88f87d5c916507a61131f34")
pro = ts.pro_api()
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
OUT = Path(__file__).parent / "three_stocks"
OUT.mkdir(exist_ok=True)
now = datetime.now().strftime("%Y-%m-%d %H:%M")

TARGETS = {
    "001395.SZ": "亚联机械",
    "002028.SZ": "思源电气",
    "688778.SH": "厦钨新能",
}
CODES = list(TARGETS.keys())

print("=" * 60)
print("Phase 8: 三只标的深度分析")
print(f"  {', '.join(TARGETS.values())}")
print("=" * 60)

# ============================================================
# 1. 12月K线 + 全技术指标
# ============================================================
print("\n[1/6] 12个月K线+技术指标...")

def full_technical(df):
    df = df.sort_values("trade_date").reset_index(drop=True)
    close, high, low, vol = df["close"], df["high"], df["low"], df["vol"]
    n = len(df)

    # MACD
    e12 = close.ewm(span=12, adjust=False).mean()
    e26 = close.ewm(span=26, adjust=False).mean()
    dif = e12 - e26; dea = dif.ewm(span=9, adjust=False).mean(); bar = 2*(dif-dea)

    # MA系统
    ma5, ma10, ma20, ma60, ma120 = [close.rolling(p).mean() for p in [5,10,20,60,120]]

    # RSI
    d = close.diff(); g = d.where(d>0,0); l = -d.where(d<0,0)
    rsi6 = 100-(100/(1+g.ewm(alpha=1/6,adjust=False).mean()/l.ewm(alpha=1/6,adjust=False).mean()))
    rsi14 = 100-(100/(1+g.ewm(alpha=1/14,adjust=False).mean()/l.ewm(alpha=1/14,adjust=False).mean()))

    # KDJ
    l9, h9 = low.rolling(9).min(), high.rolling(9).max()
    rsv = (close-l9)/(h9-l9)*100
    k = rsv.ewm(alpha=1/3,adjust=False).mean()
    d = k.ewm(alpha=1/3,adjust=False).mean(); j = 3*k-2*d

    # 布林
    bm = close.rolling(20).mean(); bs = close.rolling(20).std()
    bu, bd = bm+2*bs, bm-2*bs

    # 量比+OBV
    v5 = vol.rolling(5).mean(); vr = vol / v5.shift(1)
    obv = (vol * np.sign(close.diff())).cumsum()

    # 换手率估算
    amt = df.get("amount", vol*close)

    # 长期趋势(120日MA斜率)
    ma120v = ma120.dropna()
    if len(ma120v) >= 40:
        sl = np.polyfit(np.arange(40), ma120v[-40:].values, 1)[0]
        lt_trend = "上升" if sl > 0.01 else "下降" if sl < -0.01 else "横盘"
        trend_strength = abs(sl) / ma120v[-40:].mean() * 100  # 月化%斜率
    else:
        lt_trend, trend_strength = "数据不足", 0

    # 各周期涨跌幅
    def chg(p):
        return (close.iloc[-1]/close.iloc[-p-1]-1)*100 if n > p else None

    # 7月分析
    jm = df["trade_date"] >= "20260701"; jdf = df[jm]
    if len(jdf) >= 3:
        july_chg = (jdf["close"].iloc[-1]/jdf["close"].iloc[0]-1)*100
        july_dd = ((jdf["close"]-jdf["close"].cummax())/jdf["close"].cummax()*100).min()
        jv = jdf["vol"].mean(); pjv = df[~jm]["vol"].tail(15).mean()
        july_vol_chg = ((jv/pjv-1)*100) if pjv > 0 else 0
    else: july_chg=july_dd=july_vol_chg=0

    # 量价形态
    if july_chg > 5 and july_vol_chg > 30: vp = "放量突破"
    elif july_chg > 0 and july_vol_chg > 10: vp = "价升量增"
    elif july_chg > -5 and july_chg <= 0 and july_vol_chg < -10: vp = "缩量筑底"
    elif july_chg > -15 and july_chg <= -5: vp = "缩量回调"
    elif july_chg <= -15: vp = "放量杀跌"
    else: vp = "正常波动"

    # OBV背离
    obv_recent = obv.iloc[-20:].values
    price_recent = close.iloc[-20:].values
    obv_slope = np.polyfit(np.arange(20), obv_recent, 1)[0]
    price_slope = np.polyfit(np.arange(20), price_recent, 1)[0]
    if obv_slope > 0 and price_slope < 0: obv_div = "底部背离(看涨)"
    elif obv_slope < 0 and price_slope > 0: obv_div = "顶部背离(看跌)"
    else: obv_div = "量价同步"

    li = n - 1
    return {
        "latest": {
            "date": df["trade_date"].iloc[-1], "close": float(close.iloc[-1]),
            "open": float(df["open"].iloc[-1]), "high": float(high.iloc[-1]), "low": float(low.iloc[-1]),
            "vol": float(vol.iloc[-1]), "amount": float(df["amount"].iloc[-1]),
            "ma5": float(ma5.iloc[-1]) if not pd.isna(ma5.iloc[-1]) else None,
            "ma10": float(ma10.iloc[-1]) if not pd.isna(ma10.iloc[-1]) else None,
            "ma20": float(ma20.iloc[-1]) if not pd.isna(ma20.iloc[-1]) else None,
            "ma60": float(ma60.iloc[-1]) if not pd.isna(ma60.iloc[-1]) else None,
            "ma120": float(ma120.iloc[-1]) if not pd.isna(ma120.iloc[-1]) else None,
            "dif": float(dif.iloc[-1]) if not pd.isna(dif.iloc[-1]) else None,
            "dea": float(dea.iloc[-1]) if not pd.isna(dea.iloc[-1]) else None,
            "macd_bar": float(bar.iloc[-1]) if not pd.isna(bar.iloc[-1]) else None,
            "k": float(k.iloc[-1]) if not pd.isna(k.iloc[-1]) else None,
            "d": float(d.iloc[-1]) if not pd.isna(d.iloc[-1]) else None,
            "j": float(j.iloc[-1]) if not pd.isna(j.iloc[-1]) else None,
            "rsi6": float(rsi6.iloc[-1]) if not pd.isna(rsi6.iloc[-1]) else None,
            "rsi14": float(rsi14.iloc[-1]) if not pd.isna(rsi14.iloc[-1]) else None,
            "boll_up": float(bu.iloc[-1]) if not pd.isna(bu.iloc[-1]) else None,
            "boll_mid": float(bm.iloc[-1]) if not pd.isna(bm.iloc[-1]) else None,
            "boll_dn": float(bd.iloc[-1]) if not pd.isna(bd.iloc[-1]) else None,
            "vol_ratio": float(vr.iloc[-1]) if not pd.isna(vr.iloc[-1]) else None,
            "obv_div": obv_div,
        },
        "lt_trend": lt_trend, "trend_strength_pct": round(trend_strength, 3),
        "chg_5d": round(chg(5), 1) if chg(5) else None,
        "chg_1m": round(chg(20), 1) if chg(20) else None,
        "chg_3m": round(chg(60), 1) if chg(60) else None,
        "chg_6m": round(chg(120), 1) if chg(120) else None,
        "chg_12m": round(chg(min(240, n-2)), 1) if n > 240 else None,
        "july_chg": round(july_chg, 2), "july_dd": round(july_dd, 2),
        "july_vol_chg": round(july_vol_chg, 1), "vp_pattern": vp,
        "total_rows": n,
    }

all_klines = {}
for code in CODES:
    name = TARGETS[code]
    try:
        df = pro.daily(ts_code=code, start_date="20250701", end_date="20260722")
        if len(df) < 30: continue
        all_klines[code] = full_technical(df)
        t = all_klines[code]
        print(f"  {name}: {t['total_rows']}条K线 | 趋势:{t['lt_trend']} | 12月:{t.get('chg_12m','?'):+.1f}% | 6月:{t.get('chg_6m','?'):+.1f}% | 3月:{t.get('chg_3m','?'):+.1f}% | 7月:{t['july_chg']:+.1f}%")
    except Exception as e:
        print(f"  {name}: FAIL - {e}")
    time.sleep(0.15)

# ============================================================
# 2. 腾讯实时估值
# ============================================================
print("\n[2/6] 腾讯实时估值...")

def tencent_quote(clist):
    pref = [f"sh{c.split('.')[0]}" if c.split('.')[0].startswith(("6","9")) else f"sz{c.split('.')[0]}" for c in clist]
    url = "https://qt.gtimg.cn/q=" + ",".join(pref)
    req = urllib.request.Request(url); req.add_header("User-Agent", UA)
    resp = urllib.request.urlopen(req, timeout=10)
    data = resp.read().decode("gbk")
    result = {}
    for line in data.strip().split(";"):
        if "=" not in line or '"' not in line: continue
        key = line.split("=")[0].split("_")[-1]
        vals = line.split('"')[1].split("~")
        if len(vals) < 53: continue
        for tc in clist:
            if tc.split(".")[0] == key[2:]:
                result[tc] = {
                    "price": float(vals[3]) if vals[3] else 0,
                    "last_close": float(vals[4]) if vals[4] else 0,
                    "open": float(vals[5]) if vals[5] else 0,
                    "chg_pct": float(vals[32]) if vals[32] else 0,
                    "high": float(vals[33]) if vals[33] else 0,
                    "low": float(vals[34]) if vals[34] else 0,
                    "amount_wan": float(vals[37]) if vals[37] else 0,
                    "turnover": float(vals[38]) if vals[38] else 0,
                    "pe_ttm": float(vals[39]) if vals[39] else 0,
                    "amplitude": float(vals[43]) if vals[43] else 0,
                    "mcap_yi": float(vals[44]) if vals[44] else 0,
                    "float_mcap": float(vals[45]) if vals[45] else 0,
                    "pb": float(vals[46]) if vals[46] else 0,
                    "limit_up": float(vals[47]) if vals[47] else 0,
                    "limit_down": float(vals[48]) if vals[48] else 0,
                    "vol_ratio_tt": float(vals[49]) if vals[49] else 0,
                    "pe_static": float(vals[52]) if vals[52] else 0,
                }; break
    return result

all_quotes = tencent_quote(CODES)
for code, q in all_quotes.items():
    print(f"  {TARGETS[code]}: price={q['price']:.2f} PE={q['pe_ttm']:.1f}x PB={q['pb']:.2f}x mcap={q['mcap_yi']:.0f}亿 turnover={q['turnover']:.2f}% vol_ratio={q.get('vol_ratio_tt',0):.2f}")

# ============================================================
# 3. 东财研报
# ============================================================
print("\n[3/6] 东财研报...")
EM_S = requests.Session(); EM_S.headers.update({"User-Agent": UA})
_em_t = [0.0]
def em_g(url, params=None, timeout=20):
    wait = 1.0 - (time.time() - _em_t[0])
    if wait > 0: time.sleep(wait + np.random.uniform(0.2, 0.5))
    try: return EM_S.get(url, params=params, timeout=timeout)
    finally: _em_t[0] = time.time()

all_reports = {}
for code in CODES:
    pure = code.split(".")[0]
    name = TARGETS[code]
    try:
        params = {"industryCode":"*","pageSize":"15","industry":"*","rating":"*","ratingChange":"*",
                  "beginTime":"2025-01-01","endTime":"2026-08-01","pageNo":"1","qType":"0","code":pure}
        r = em_g("https://reportapi.eastmoney.com/report/list", params=params, timeout=30)
        rows = r.json().get("data", [])
        all_reports[code] = []
        for row in rows[:10]:
            all_reports[code].append({
                "title": row.get("title","")[:80], "org": row.get("orgSName",""),
                "date": (row.get("publishDate") or "")[:10], "rating": row.get("emRatingName",""),
                "eps_t": row.get("predictThisYearEps",0), "eps_n": row.get("predictNextYearEps",0),
                "eps_n2": row.get("predictNextTwoYearEps",0),
                "industry": row.get("indvInduName",""),
            })
        print(f"  {name}: {len(all_reports[code])}篇研报")
        for rp in all_reports[code][:3]:
            print(f"    {rp['date']} | {rp['org']} | {rp['rating']} | {rp['title'][:55]}")
    except Exception as e:
        all_reports[code] = []
        print(f"  {name}: FAIL - {str(e)[:50]}")
    time.sleep(1.3)

# ============================================================
# 4. 资金流向(东财push2his)
# ============================================================
print("\n[4/6] 主力资金流向...")

all_fund_flow = {}
for code in CODES:
    pure = code.split(".")[0]; mkt = 1 if pure.startswith("6") else 0; name = TARGETS[code]
    try:
        r = em_g("https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get",
                 params={"secid":f"{mkt}.{pure}","fields1":"f1,f2,f3,f7",
                         "fields2":"f51,f52,f53,f54,f55,f56,f57","lmt":"120"}, timeout=15)
        kls = r.json().get("data",{}).get("klines",[])
        rows = []
        for line in kls:
            p = line.split(",")
            if len(p)>=7:
                rows.append({"date":p[0],"main_net":float(p[1]) if p[1]!="-" else 0,
                             "super_net":float(p[5]) if p[5]!="-" else 0,
                             "large_net":float(p[4]) if p[4]!="-" else 0})
        all_fund_flow[code] = rows
        if rows:
            m5 = sum(r["main_net"] for r in rows[-5:])
            m20 = sum(r["main_net"] for r in rows[-20:])
            m60 = sum(r["main_net"] for r in rows[-60:])
            print(f"  {name}: 近5日主力={m5/1e8:+.2f}亿 | 近20日={m20/1e8:+.2f}亿 | 近60日={m60/1e8:+.2f}亿")
    except Exception as e:
        all_fund_flow[code] = []
        print(f"  {name}: FAIL - {str(e)[:40]}")
    time.sleep(1.5)

# ============================================================
# 5. 融资融券+板块归属
# ============================================================
print("\n[5/6] 融资融券+板块归属...")

def em_dc(report, filt="", ps=10):
    r = em_g("https://datacenter-web.eastmoney.com/api/data/v1/get",
             params={"reportName":report,"columns":"ALL","filter":filt,
                     "pageNumber":"1","pageSize":str(ps),"sortColumns":"DATE",
                     "sortTypes":"-1","source":"WEB","client":"WEB"}, timeout=15)
    return (r.json().get("result") or {}).get("data", [])

all_margin, all_blocks = {}, {}
for code in CODES:
    pure = code.split(".")[0]; name = TARGETS[code]

    # 融资融券
    try:
        d = em_dc("RPTA_WEB_RZRQ_GGMX", f'(SCODE="{pure}")', 5)
        if d:
            all_margin[code] = [{"date":str(r.get("DATE",""))[:10],"rzye":r.get("RZYE",0),
                                 "rzmre":r.get("RZMRE",0),"rqye":r.get("RQYE",0)} for r in d]
            m = all_margin[code][0]
            print(f"  {name} 融资: {m['rzye']/1e8:.2f}亿 融券: {m['rqye']/1e8:.4f}亿")
    except: pass

    # 概念板块
    try:
        mkt = 1 if pure.startswith("6") else 0
        r = em_g("https://push2.eastmoney.com/api/qt/slist/get",
                 params={"fltt":"2","invt":"2","secid":f"{mkt}.{pure}",
                         "spt":"3","pi":"0","pz":"100","po":"1","fields":"f12,f14,f3,f128"}, timeout=15)
        items = r.json().get("data",{}).get("diff",[])
        if isinstance(items, dict): items = list(items.values())
        all_blocks[code] = [{"name":i.get("f14",""),"code":i.get("f12",""),
                             "chg":i.get("f3","")} for i in items]
        tags = [b["name"] for b in all_blocks[code]]
        print(f"  {name} 板块: {', '.join(tags[:8])}")
    except: pass
    time.sleep(0.8)

# ============================================================
# 6. H1业绩(厦钨新能需要单独拉)
# ============================================================
print("\n[6/6] H1业绩数据...")

earnings = {}
for code in CODES:
    pure = code.split(".")[0]; name = TARGETS[code]
    # Try express
    try:
        e = pro.express(ts_code=code, start_date="20260701", end_date="20260831")
        if e is not None and not e.empty:
            r = e.iloc[0]
            earnings[code] = {
                "n_income": float(r.get("n_income",0) or 0),
                "revenue": float(r.get("revenue",0) or 0),
                "diluted_eps": float(r.get("diluted_eps",0) or 0),
                "diluted_roe": float(r.get("diluted_roe",0) or 0),
                "bps": float(r.get("bps",0) or 0),
            }
            # Try get H1 2025 for YoY
            e25 = pro.express(ts_code=code, start_date="20250701", end_date="20250831")
            if e25 is not None and not e25.empty:
                r25 = e25.iloc[0]
                ni25 = float(r25.get("n_income",0) or 0)
                rev25 = float(r25.get("revenue",0) or 0)
                if ni25 > 0:
                    earnings[code]["yoy_profit"] = round((earnings[code]["n_income"]/ni25-1)*100, 1)
                    earnings[code]["yoy_revenue"] = round((earnings[code]["revenue"]/rev25-1)*100, 1) if rev25>0 else None
            print(f"  {name}: 净利={earnings[code]['n_income']/1e8:.2f}亿 YOY={earnings[code].get('yoy_profit','?'):+.0f}% ROE={earnings[code]['diluted_roe']:.1f}%")
    except Exception as ex:
        print(f"  {name}: express FAIL - {str(ex)[:50]}")
    time.sleep(0.2)

# ============================================================
# 保存
# ============================================================
export = {
    "meta": {"generated": now},
    "targets": TARGETS,
    "klines": all_klines,
    "quotes": all_quotes,
    "reports": all_reports,
    "fund_flow": all_fund_flow,
    "margin": all_margin,
    "blocks": all_blocks,
    "earnings": earnings,
}

class NpEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (np.integer,)): return int(obj)
        if isinstance(obj, (np.floating,)):
            return None if np.isnan(obj) or np.isinf(obj) else float(obj)
        return super().default(obj)

fpath = OUT / "three_stocks.json"
with open(fpath, "w", encoding="utf-8") as f:
    json.dump(export, f, ensure_ascii=False, indent=2, cls=NpEncoder)
print(f"\n[OK] {fpath} ({fpath.stat().st_size/1024:.1f} KB)")
print(">>> Phase 8 done <<<")
