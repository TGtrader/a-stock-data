"""
MLCC行业分析脚本
使用 Tushare (行情) + a-stock-data (腾讯/东财) + Vibe-Trading 双技能栈
分析标的：风华高科 三环集团 火炬电子 鸿远电子 洁美科技 国瓷材料 振华科技
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
# 配置
# ============================================================
TUSHARE_TOKEN = "53399fa4a4f51a769a4455978feb0b04c88f87d5c916507a61131f34"
ts.set_token(TUSHARE_TOKEN)
pro = ts.pro_api()

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
OUTPUT_DIR = Path(__file__).parent
DATA_DIR = OUTPUT_DIR / "analysis_data"
DATA_DIR.mkdir(exist_ok=True)

# MLCC 核心标的
MLCC_STOCKS = {
    "000636": "风华高科",   # 国内MLCC龙头
    "300408": "三环集团",   # 电子陶瓷+MLCC
    "603678": "火炬电子",   # 军用MLCC
    "603267": "鸿远电子",   # 军用MLCC
    "002859": "洁美科技",   # MLCC载带上游
    "300285": "国瓷材料",   # MLCC陶瓷粉上游
    "000733": "振华科技",   # 军用电子元器件
}

MLCC_CODES = list(MLCC_STOCKS.keys())

# 时间范围
END_DATE = "20260722"
START_DATE = "20251201"  # 取近8个月日K线
SHORT_START = "20260601"  # 近期60日

print(f"MLCC 分析脚本启动 - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
print(f"覆盖标的: {len(MLCC_STOCKS)} 只")

# ============================================================
# 1. Tushare 日K线数据
# ============================================================
print("\n[1/7] 拉取 Tushare 日K线数据...")

all_klines = {}
for code, name in MLCC_STOCKS.items():
    ts_code = f"{code}.{'SH' if code.startswith('6') else 'SZ'}"
    try:
        df = pro.daily(ts_code=ts_code, start_date=START_DATE, end_date=END_DATE)
        if not df.empty:
            df = df.sort_values("trade_date").reset_index(drop=True)
            all_klines[code] = {"name": name, "data": df}
            print(f"  {name}({code}): {len(df)} 条K线 | 最新收盘 {df['close'].iloc[-1]:.2f} | 涨跌幅 {df['pct_chg'].iloc[-1]:.2f}%")
        else:
            print(f"  {name}({code}): 无数据!")
    except Exception as e:
        print(f"  {name}({code}): 失败 - {e}")
    time.sleep(0.3)

# ============================================================
# 2. 腾讯实时行情（PE/PB/市值/换手率/量比）
# ============================================================
print("\n[2/7] 拉取腾讯实时行情（估值+量比）...")

def tencent_quote(codes):
    prefixed = []
    for c in codes:
        if c.startswith(("6", "9")): prefixed.append(f"sh{c}")
        elif c.startswith("8"): prefixed.append(f"bj{c}")
        else: prefixed.append(f"sz{c}")
    url = "https://qt.gtimg.cn/q=" + ",".join(prefixed)
    req = urllib.request.Request(url)
    req.add_header("User-Agent", UA)
    resp = urllib.request.urlopen(req, timeout=10)
    data = resp.read().decode("gbk")
    result = {}
    for line in data.strip().split(";"):
        if not line.strip() or "=" not in line or '"' not in line:
            continue
        key = line.split("=")[0].split("_")[-1]
        vals = line.split('"')[1].split("~")
        if len(vals) < 53: continue
        code = key[2:]
        result[code] = {
            "name": vals[1], "price": float(vals[3]) if vals[3] else 0,
            "last_close": float(vals[4]) if vals[4] else 0,
            "open": float(vals[5]) if vals[5] else 0,
            "change_pct": float(vals[32]) if vals[32] else 0,
            "high": float(vals[33]) if vals[33] else 0,
            "low": float(vals[34]) if vals[34] else 0,
            "amount_wan": float(vals[37]) if vals[37] else 0,
            "turnover_pct": float(vals[38]) if vals[38] else 0,
            "pe_ttm": float(vals[39]) if vals[39] else 0,
            "mcap_yi": float(vals[44]) if vals[44] else 0,
            "float_mcap_yi": float(vals[45]) if vals[45] else 0,
            "pb": float(vals[46]) if vals[46] else 0,
            "limit_up": float(vals[47]) if vals[47] else 0,
            "limit_down": float(vals[48]) if vals[48] else 0,
            "vol_ratio": float(vals[49]) if vals[49] else 0,
            "pe_static": float(vals[52]) if vals[52] else 0,
        }
    return result

live_quotes = {}
try:
    live_quotes = tencent_quote(MLCC_CODES)
    for code, q in live_quotes.items():
        print(f"  {q['name']}({code}): 价格{q['price']:.2f} | PE(TTM)={q['pe_ttm']:.1f} | PB={q['pb']:.2f} | 市值{q['mcap_yi']:.0f}亿 | 换手{q['turnover_pct']:.2f}% | 量比{q['vol_ratio']:.2f}")
except Exception as e:
    print(f"  腾讯行情失败: {e}")

# ============================================================
# 3. 东财资金流向（120日）
# ============================================================
print("\n[3/7] 拉取东财资金流向（120日）...")

EM_SESSION = requests.Session()
EM_SESSION.headers.update({"User-Agent": UA})
_em_last_call = [0.0]

def em_get(url, params=None, timeout=15):
    wait = 1.0 - (time.time() - _em_last_call[0])
    if wait > 0: time.sleep(wait + np.random.uniform(0.1, 0.5))
    try:
        return EM_SESSION.get(url, params=params, timeout=timeout)
    finally:
        _em_last_call[0] = time.time()

def stock_fund_flow_120d(code):
    market_code = 1 if code.startswith("6") else 0
    url = "https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get"
    params = {
        "secid": f"{market_code}.{code}",
        "fields1": "f1,f2,f3,f7",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65",
        "lmt": "120",
    }
    try:
        r = em_get(url, params=params, timeout=15)
        d = r.json()
    except Exception as e:
        print(f"    资金流请求失败: {e}")
        return []
    klines = d.get("data", {}).get("klines", [])
    rows = []
    for line in klines:
        parts = line.split(",")
        if len(parts) >= 7:
            rows.append({
                "date": parts[0],
                "main_net": float(parts[1]) if parts[1] != "-" else 0,
                "small_net": float(parts[2]) if parts[2] != "-" else 0,
                "mid_net": float(parts[3]) if parts[3] != "-" else 0,
                "large_net": float(parts[4]) if parts[4] != "-" else 0,
                "super_net": float(parts[5]) if parts[5] != "-" else 0,
            })
    return rows

all_fund_flows = {}
for code, name in MLCC_STOCKS.items():
    flows = stock_fund_flow_120d(code)
    if flows:
        all_fund_flows[code] = flows
        recent_20 = flows[-20:]
        total_main = sum(f["main_net"] for f in recent_20)
        total_super = sum(f["super_net"] for f in recent_20)
        print(f"  {name}({code}): {len(flows)}条 | 近20日主力净流入={total_main/1e8:.2f}亿 | 超大单={total_super/1e8:.2f}亿")
    else:
        print(f"  {name}({code}): 无资金流数据")
    time.sleep(1.2)  # 限流

# ============================================================
# 4. 行业估值对比（东财行业板块）
# ============================================================
print("\n[4/7] 拉取行业板块估值...")

def industry_pe_rank():
    """获取东财行业板块PE排名"""
    url = "https://push2.eastmoney.com/api/qt/clist/get"
    params = {
        "pn": "1", "pz": "150", "po": "1", "np": "1",
        "fltt": "2", "invt": "2",
        "fs": "m:90+t:2",
        "fields": "f2,f3,f4,f12,f14,f20,f21,f104,f105,f140",
    }
    try:
        r = em_get(url, params=params, timeout=15)
        items = r.json().get("data", {}).get("diff", [])
        rows = []
        for i, item in enumerate(items):
            rows.append({
                "rank": i+1, "name": item.get("f14",""),
                "change_pct": item.get("f3",0),
                "pe": item.get("f20",0),
                "pb": item.get("f21",0),
                "code": item.get("f12",""),
            })
        return rows
    except Exception as e:
        print(f"  行业估值拉取失败: {e}")
        return []

industry_data = industry_pe_rank()
if industry_data:
    # 找电子元件相关行业
    electronic = [i for i in industry_data if any(kw in i.get("name","") for kw in ["电子","元件","半导体","材料"])]
    print(f"  行业总数: {len(industry_data)}")
    print(f"  电子相关行业估值:")
    for ind in electronic[:10]:
        print(f"    {ind['name']}: PE={ind['pe']:.1f}x PB={ind['pb']:.2f}x 涨跌{ind['change_pct']}%")

# ============================================================
# 5. 技术指标计算
# ============================================================
print("\n[5/7] 计算技术指标（MACD/MA/量比/量价关系）...")

def calc_macd(close_series, fast=12, slow=26, signal=9):
    """计算MACD"""
    ema_fast = close_series.ewm(span=fast, adjust=False).mean()
    ema_slow = close_series.ewm(span=slow, adjust=False).mean()
    dif = ema_fast - ema_slow
    dea = dif.ewm(span=signal, adjust=False).mean()
    bar = 2 * (dif - dea)
    return dif, dea, bar

def calc_rsi(close_series, period=14):
    """计算RSI"""
    delta = close_series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def calc_boll(close_series, period=20, std=2):
    """计算布林带"""
    ma = close_series.rolling(period).mean()
    std_dev = close_series.rolling(period).std()
    upper = ma + std * std_dev
    lower = ma - std * std_dev
    return upper, ma, lower

all_technical = {}
for code, info in all_klines.items():
    df = info["data"].copy()
    close = df["close"]
    close_rev = close.iloc[::-1].reset_index(drop=True)  # 最早→最新

    # MACD
    dif, dea, bar = calc_macd(close_rev)

    # 均线
    ma5 = close_rev.rolling(5).mean()
    ma10 = close_rev.rolling(10).mean()
    ma20 = close_rev.rolling(20).mean()
    ma60 = close_rev.rolling(60).mean()

    # RSI
    rsi6 = calc_rsi(close_rev, 6)
    rsi14 = calc_rsi(close_rev, 14)

    # 布林带
    boll_upper, boll_mid, boll_lower = calc_boll(close_rev, 20, 2)

    # 量比（5日均量比）
    vol = df["vol"]
    vol_rev = vol.iloc[::-1].reset_index(drop=True)
    vol_ma5 = vol_rev.rolling(5).mean()
    vol_ratio_local = vol_rev / vol_ma5.shift(1)

    # 量价关系评分
    latest_close = close_rev.iloc[-1]
    latest_vol = vol_rev.iloc[-1]
    vol_avg_20 = vol_rev.iloc[-20:].mean()
    price_chg_5d = (close_rev.iloc[-1] / close_rev.iloc[-6] - 1) * 100 if len(close_rev) >= 6 else 0
    vol_chg_5d = (vol_rev.iloc[-5:].mean() / vol_rev.iloc[-10:-5].mean() - 1) * 100 if len(vol_rev) >= 10 else 0

    # 放量上涨/缩量下跌信号
    if price_chg_5d > 0 and vol_chg_5d > 10:
        vp_signal = "放量上涨（偏多）"
    elif price_chg_5d < 0 and vol_chg_5d < -10:
        vp_signal = "缩量下跌（偏中性）"
    elif price_chg_5d < 0 and vol_chg_5d > 10:
        vp_signal = "放量下跌（偏空）"
    elif price_chg_5d > 0 and vol_chg_5d < -10:
        vp_signal = "缩量上涨（谨慎偏多）"
    else:
        vp_signal = "量价配合正常"

    all_technical[code] = {
        "name": info["name"],
        "latest": {
            "close": float(latest_close),
            "ma5": float(ma5.iloc[-1]) if not pd.isna(ma5.iloc[-1]) else None,
            "ma10": float(ma10.iloc[-1]) if not pd.isna(ma10.iloc[-1]) else None,
            "ma20": float(ma20.iloc[-1]) if not pd.isna(ma20.iloc[-1]) else None,
            "ma60": float(ma60.iloc[-1]) if not pd.isna(ma60.iloc[-1]) else None,
            "dif": float(dif.iloc[-1]) if not pd.isna(dif.iloc[-1]) else None,
            "dea": float(dea.iloc[-1]) if not pd.isna(dea.iloc[-1]) else None,
            "macd_bar": float(bar.iloc[-1]) if not pd.isna(bar.iloc[-1]) else None,
            "rsi6": float(rsi6.iloc[-1]) if not pd.isna(rsi6.iloc[-1]) else None,
            "rsi14": float(rsi14.iloc[-1]) if not pd.isna(rsi14.iloc[-1]) else None,
            "boll_upper": float(boll_upper.iloc[-1]) if not pd.isna(boll_upper.iloc[-1]) else None,
            "boll_mid": float(boll_mid.iloc[-1]) if not pd.isna(boll_mid.iloc[-1]) else None,
            "boll_lower": float(boll_lower.iloc[-1]) if not pd.isna(boll_lower.iloc[-1]) else None,
            "vol_ratio_local": float(vol_ratio_local.iloc[-1]) if not pd.isna(vol_ratio_local.iloc[-1]) else None,
        },
        "price_chg_5d": round(price_chg_5d, 2),
        "vol_chg_5d": round(vol_chg_5d, 1),
        "vp_signal": vp_signal,
        "trend": "多头" if (all_technical.get(code, {}).get("latest", {}).get("close", 0) or 0) >
                 (all_technical.get(code, {}).get("latest", {}).get("ma20", 0) or 0) else "空头",
    }

for code, tech in all_technical.items():
    t = tech["latest"]
    macd_status = "金叉向上" if (t.get("dif") or 0) > (t.get("dea") or 0) else "死叉向下"
    ma_status = "多头排列" if (t.get("ma5") or 0) > (t.get("ma10") or 0) > (t.get("ma20") or 0) else "非多头"
    print(f"  {tech['name']}({code}): MACD={macd_status} | MA={ma_status} | RSI14={t.get('rsi14','-')} | {tech['vp_signal']}")

# ============================================================
# 6. 近期涨跌幅统计
# ============================================================
print("\n[6/7] 计算涨跌幅统计...")

perf_stats = {}
for code, info in all_klines.items():
    df = info["data"].copy()
    close_rev = df["close"].iloc[::-1].reset_index(drop=True)
    n = len(close_rev)
    perf = {"name": info["name"]}
    for period_name, days in [("5日", 5), ("10日", 10), ("20日", 20), ("60日", 60), ("120日", 120)]:
        if n >= days:
            chg = (close_rev.iloc[-1] / close_rev.iloc[-days-1] - 1) * 100
        else:
            chg = None
        perf[period_name] = round(chg, 2) if chg is not None else None
    perf_stats[code] = perf
    print(f"  {info['name']}({code}): 5日={perf.get('5日','-')}% | 10日={perf.get('10日','-')}% | 20日={perf.get('20日','-')}% | 60日={perf.get('60日','-')}%")

# ============================================================
# 7. 融资融券数据
# ============================================================
print("\n[7/7] 拉取融资融券数据...")

EASTMONEY_DATACENTER = "https://datacenter-web.eastmoney.com/api/data/v1/get"

def eastmoney_datacenter(report_name, filter_str="", page_size=10, sort_columns="", sort_types="-1"):
    params = {
        "reportName": report_name, "columns": "ALL",
        "filter": filter_str, "pageNumber": "1", "pageSize": str(page_size),
        "sortColumns": sort_columns, "sortTypes": sort_types,
        "source": "WEB", "client": "WEB",
    }
    r = em_get(EASTMONEY_DATACENTER, params=params, timeout=15)
    d = r.json()
    return (d.get("result") or {}).get("data", [])

all_margin = {}
for code, name in MLCC_STOCKS.items():
    data = eastmoney_datacenter(
        "RPTA_WEB_RZRQ_GGMX",
        filter_str=f'(SCODE="{code}")',
        page_size=5,
        sort_columns="DATE", sort_types="-1",
    )
    if data:
        rows = []
        for row in data:
            rows.append({
                "date": str(row.get("DATE",""))[:10],
                "rzye": row.get("RZYE",0),    # 融资余额
                "rzmre": row.get("RZMRE",0),  # 融资买入
                "rzche": row.get("RZCHE",0),  # 融资偿还
                "rqye": row.get("RQYE",0),    # 融券余额
            })
        all_margin[code] = rows
        latest = rows[0]
        print(f"  {name}({code}): 融资余额={latest['rzye']/1e8:.2f}亿 | 融券={latest['rqye']/1e8:.4f}亿")
    else:
        print(f"  {name}({code}): 无两融数据")
    time.sleep(0.8)

# ============================================================
# 保存数据
# ============================================================
print("\n保存分析数据...")
analysis_data = {
    "meta": {
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "end_date": END_DATE,
        "stocks": MLCC_STOCKS,
    },
    "live_quotes": {k: {kk: vv for kk, vv in v.items() if kk != "name"} for k, v in live_quotes.items()},
    "technical": all_technical,
    "performance": perf_stats,
    "fund_flows": {code: flows[-30:] for code, flows in all_fund_flows.items()},
    "margin": all_margin,
    "industry": industry_data,
}

# Convert to JSON-serializable
class NpEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (np.integer,)): return int(obj)
        if isinstance(obj, (np.floating,)):
            return None if np.isnan(obj) or np.isinf(obj) else float(obj)
        if isinstance(obj, np.ndarray): return obj.tolist()
        return super().default(obj)

json_path = DATA_DIR / "mlcc_analysis.json"
with open(json_path, "w", encoding="utf-8") as f:
    json.dump(analysis_data, f, ensure_ascii=False, indent=2, cls=NpEncoder)

print(f"数据已保存至: {json_path}")
print("\n✅ 数据采集完成，准备生成报告...")
