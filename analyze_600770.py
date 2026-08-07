#!/usr/bin/env python3
"""
综艺股份 (600770) 综合分析报告生成器
基于 a-stock-data SKILL.md V3.3.0 十层数据架构
"""

import time, random, json, re, math, os, urllib.request, uuid
import requests
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
from io import StringIO
from collections import Counter

# ============================================================
# 全局配置
# ============================================================
CODE = "600770"
STOCK_NAME = "综艺股份"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
OUTPUT_HTML = Path(__file__).parent / "综艺股份_600770_分析报告.html"
REPORT_DIR = Path(__file__).parent / "reports_600770"
REPORT_DIR.mkdir(exist_ok=True)

# ============================================================
# mootdx 客户端 (from SKILL.md Prerequisites)
# ============================================================
import socket
from mootdx.quotes import Quotes

_TDX_SERVERS = [
    ('119.97.185.59', 7709), ('124.70.133.119', 7709), ('116.205.183.150', 7709),
    ('123.60.73.44', 7709),  ('116.205.163.254', 7709), ('121.36.225.169', 7709),
    ('123.60.70.228', 7709), ('124.71.9.153', 7709),    ('110.41.147.114', 7709),
    ('124.71.187.122', 7709),
]

def _probe(ip, port, timeout=2.0):
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except Exception:
        return False

def tdx_client(market='std'):
    for ip, port in _TDX_SERVERS:
        if _probe(ip, port):
            return Quotes.factory(market=market, server=(ip, port))
    try:
        return Quotes.factory(market=market, bestip=True)
    except Exception:
        pass
    try:
        return Quotes.factory(market=market)
    except Exception as e:
        raise RuntimeError(f"所有 mootdx 服务器均不可达: {e}")

# ============================================================
# 东财防封：全局节流 + 会话复用 (from SKILL.md)
# ============================================================
EM_SESSION = requests.Session()
EM_SESSION.headers.update({"User-Agent": UA})
EM_MIN_INTERVAL = 1.2  # 调大一点以防风控
_em_last_call = [0.0]

try:
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
    _em_adapter = HTTPAdapter(max_retries=Retry(
        total=3, connect=3, backoff_factor=0.6,
        status_forcelist=[429, 500, 502, 503, 504], allowed_methods=["GET"]))
    EM_SESSION.mount("https://", _em_adapter)
    EM_SESSION.mount("http://", _em_adapter)
except Exception:
    pass

def em_get(url, params=None, headers=None, timeout=15, **kwargs):
    """东财统一请求入口：自动节流 + 复用 session"""
    wait = EM_MIN_INTERVAL - (time.time() - _em_last_call[0])
    if wait > 0:
        time.sleep(wait + random.uniform(0.1, 0.5))
    try:
        if headers:
            merged = {**{"User-Agent": UA}, **headers}
        else:
            merged = {"User-Agent": UA}
        return EM_SESSION.get(url, params=params, headers=merged, timeout=timeout, **kwargs)
    finally:
        _em_last_call[0] = time.time()

DATACENTER_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"

def eastmoney_datacenter(report_name, columns="ALL", filter_str="", page_size=50,
                          sort_columns="", sort_types="-1"):
    params = {
        "reportName": report_name, "columns": columns,
        "filter": filter_str, "pageNumber": "1", "pageSize": str(page_size),
        "sortColumns": sort_columns, "sortTypes": sort_types,
        "source": "WEB", "client": "WEB",
    }
    r = em_get(DATACENTER_URL, params=params, timeout=15)
    d = r.json()
    if d.get("result") and d["result"].get("data"):
        return d["result"]["data"]
    return []

print("=" * 60)
print(f"开始采集 {CODE} {STOCK_NAME} 多维数据...")
print("=" * 60)

# ============================================================
# 1. 腾讯行情 (实时估值)
# ============================================================
print("\n[1/12] 腾讯财经实时行情...")
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
        if not line.strip() or "=" not in line or '"' not in line: continue
        key = line.split("=")[0].split("_")[-1]
        vals = line.split('"')[1].split("~")
        if len(vals) < 53: continue
        code_ = key[2:]
        result[code_] = {
            "name": vals[1], "price": float(vals[3]) if vals[3] else 0,
            "last_close": float(vals[4]) if vals[4] else 0,
            "open": float(vals[5]) if vals[5] else 0,
            "change_amt": float(vals[31]) if vals[31] else 0,
            "change_pct": float(vals[32]) if vals[32] else 0,
            "high": float(vals[33]) if vals[33] else 0,
            "low": float(vals[34]) if vals[34] else 0,
            "amount_wan": float(vals[37]) if vals[37] else 0,
            "turnover_pct": float(vals[38]) if vals[38] else 0,
            "pe_ttm": float(vals[39]) if vals[39] else 0,
            "amplitude_pct": float(vals[43]) if vals[43] else 0,
            "mcap_yi": float(vals[44]) if vals[44] else 0,
            "float_mcap_yi": float(vals[45]) if vals[45] else 0,
            "pb": float(vals[46]) if vals[46] else 0,
            "limit_up": float(vals[47]) if vals[47] else 0,
            "limit_down": float(vals[48]) if vals[48] else 0,
            "vol_ratio": float(vals[49]) if vals[49] else 0,
            "pe_static": float(vals[52]) if vals[52] else 0,
        }
    return result

tq = tencent_quote([CODE])
quote = tq.get(CODE, {})
print(f"  名称={quote.get('name','?')} 价格={quote.get('price',0)} PE(TTM)={quote.get('pe_ttm',0)} PB={quote.get('pb',0)} 市值={quote.get('mcap_yi',0)}亿")

# ============================================================
# 2. mootdx K线
# ============================================================
print("\n[2/12] mootdx K线数据...")
try:
    client = tdx_client()
    klines_daily = client.bars(symbol=CODE, frequency=9, offset=250)  # 日线
    print(f"  日K线: {len(klines_daily)} 根")
except Exception as e:
    print(f"  [WARN] mootdx K线失败: {e}")
    klines_daily = []

# ============================================================
# 3. 东财个股信息
# ============================================================
print("\n[3/12] 东财个股基本面...")
def eastmoney_stock_info(code):
    market_code = 1 if code.startswith("6") else 0
    url = "https://push2.eastmoney.com/api/qt/stock/get"
    params = {"fltt": "2", "invt": "2",
              "fields": "f57,f58,f84,f85,f127,f116,f117,f189,f43,f9,f10,f20,f21",
              "secid": f"{market_code}.{code}"}
    r = em_get(url, params=params, timeout=10)
    d = r.json().get("data", {})
    return {
        "code": d.get("f57", ""), "name": d.get("f58", ""),
        "industry": d.get("f127", ""),
        "total_shares": d.get("f84", 0), "float_shares": d.get("f85", 0),
        "mcap": d.get("f116", 0), "float_mcap": d.get("f117", 0),
        "list_date": str(d.get("f189", "")), "price": d.get("f43", 0),
        "pe_dynamic": d.get("f9", 0), "pb": d.get("f10", 0),
    }

stock_info = eastmoney_stock_info(CODE)
print(f"  行业={stock_info.get('industry','?')} 总股本={stock_info.get('total_shares',0)/1e8:.2f}亿 上市日期={stock_info.get('list_date','?')}")

# ============================================================
# 4. 概念板块归属
# ============================================================
print("\n[4/12] 概念板块归属...")
def eastmoney_concept_blocks(code):
    market_code = 1 if code.startswith("6") else 0
    params = {"fltt": "2", "invt": "2", "secid": f"{market_code}.{code}",
              "spt": "3", "pi": "0", "pz": "200", "po": "1",
              "fields": "f12,f14,f3,f128"}
    try:
        r = em_get("https://push2.eastmoney.com/api/qt/slist/get", params=params, timeout=15)
        d = r.json()
    except Exception as e:
        print(f"  [WARN] 板块归属失败: {e}")
        return {"total": 0, "boards": [], "concept_tags": []}
    diff = (d.get("data") or {}).get("diff") or {}
    items = diff.values() if isinstance(diff, dict) else diff
    boards = []
    for it in items:
        boards.append({
            "name": it.get("f14", ""), "code": it.get("f12", ""),
            "change_pct": it.get("f3", ""), "lead_stock": it.get("f128", ""),
        })
    return {"total": len(boards), "boards": boards,
            "concept_tags": [b["name"] for b in boards]}

blocks = eastmoney_concept_blocks(CODE)
print(f"  共 {blocks['total']} 个板块: {', '.join(blocks['concept_tags'][:15])}")

# ============================================================
# 5. 研报列表 + PDF下载
# ============================================================
print("\n[5/12] 东财研报...")
REPORT_API = "https://reportapi.eastmoney.com/report/list"
PDF_TPL = "https://pdf.dfcfw.com/pdf/H3_{info_code}_1.pdf"

def eastmoney_reports(code, max_pages=5):
    all_records = []
    for page in range(1, max_pages + 1):
        params = {
            "industryCode": "*", "pageSize": "100", "industry": "*",
            "rating": "*", "ratingChange": "*",
            "beginTime": "2000-01-01", "endTime": "2030-01-01",
            "pageNo": str(page), "fields": "", "qType": "0",
            "orgCode": "", "code": code, "rcode": "",
            "p": str(page), "pageNum": str(page), "pageNumber": str(page),
        }
        r = em_get(REPORT_API, params=params,
                   headers={"Referer": "https://data.eastmoney.com/"}, timeout=30)
        d = r.json()
        rows = d.get("data") or []
        if not rows: break
        all_records.extend(rows)
        if page >= (d.get("TotalPage", 1) or 1): break
    return all_records

reports = eastmoney_reports(CODE, max_pages=3)
print(f"  共 {len(reports)} 篇研报")

# 下载最新5篇PDF并提取文本
pdf_texts = []
for i, r in enumerate(reports[:5]):
    info_code = r.get("infoCode", "")
    if not info_code: continue
    date = (r.get("publishDate") or "")[:10]
    org = re.sub(r'[\\/:*?"<>|]', "_", r.get("orgSName") or "未知")[:40]
    title = re.sub(r'[\\/:*?"<>|]', "_", r.get("title", ""))[:80]
    fname = f"{date}_{org}_{title}.pdf"
    target = REPORT_DIR / fname

    pdf_text = ""
    if not target.exists():
        url = PDF_TPL.format(info_code=info_code)
        try:
            r_pdf = em_get(url, headers={"Referer": "https://data.eastmoney.com/"}, timeout=60)
            if r_pdf.status_code == 200 and len(r_pdf.content) >= 1024:
                target.write_bytes(r_pdf.content)
                print(f"  下载PDF [{i+1}]: {fname[:80]}... ({len(r_pdf.content)/1024:.0f}KB)")
        except Exception as e:
            print(f"  [WARN] PDF下载失败 [{i+1}]: {e}")

    # 提取PDF文本
    if target.exists():
        try:
            from PyPDF2 import PdfReader
            reader = PdfReader(str(target))
            text_parts = []
            for page in reader.pages[:15]:  # 前15页
                t = page.extract_text()
                if t: text_parts.append(t)
            pdf_text = "\n".join(text_parts)
            print(f"  提取文本 [{i+1}]: {len(pdf_text)} 字符")
        except Exception as e:
            print(f"  [WARN] PDF文本提取失败 [{i+1}]: {e}")
            pdf_text = f"[PDF已下载: {target.name}, 但文本提取失败: {e}]"

    pdf_texts.append({
        "date": date, "org": org, "title": r.get("title", ""),
        "rating": r.get("emRatingName", ""),
        "eps_cur": r.get("predictThisYearEps", ""),
        "eps_next": r.get("predictNextYearEps", ""),
        "eps_next2": r.get("predictNextTwoYearEps", ""),
        "text": pdf_text[:8000],  # 保留前8000字
    })

# ============================================================
# 6. 新浪财报三表
# ============================================================
print("\n[6/12] 新浪财报三表...")
def sina_financial_report(code, report_type="lrb", num=8):
    prefix = "sh" if code.startswith("6") else "sz"
    paper_code = f"{prefix}{code}"
    url = "https://quotes.sina.cn/cn/api/openapi.php/CompanyFinanceService.getFinanceReport2022"
    params = {"paperCode": paper_code, "source": report_type, "type": "0", "page": "1", "num": str(num)}
    r = requests.get(url, params=params, headers={"User-Agent": UA}, timeout=15)
    report_list = r.json().get("result", {}).get("data", {}).get("report_list", {}) or {}
    rows = []
    for period in sorted(report_list.keys(), reverse=True)[:num]:
        obj = report_list[period]
        rec = {"报告期": f"{period[:4]}-{period[4:6]}-{period[6:8]}"}
        for it in obj.get("data", []) or []:
            title = it.get("item_title", "")
            if not title or it.get("item_value") is None: continue
            rec[title] = it.get("item_value")
            tongbi = it.get("item_tongbi")
            if tongbi not in (None, ""): rec[title + "_同比"] = tongbi
        rows.append(rec)
    return rows

lrb = sina_financial_report(CODE, "lrb", 8)
fzb = sina_financial_report(CODE, "fzb", 4)
llb = sina_financial_report(CODE, "llb", 4)
print(f"  利润表: {len(lrb)} 期, 资产负债表: {len(fzb)} 期, 现金流量表: {len(llb)} 期")

# ============================================================
# 7. mootdx 财务快照
# ============================================================
print("\n[7/12] mootdx 财务快照...")
try:
    fin = client.finance(symbol=CODE)
    if hasattr(fin, 'empty') and not fin.empty:
        fin_dict = fin.to_dict()
        print(f"  EPS={fin_dict.get('eps','?')} 字段数={len(fin_dict)}")
    else:
        print(f"  [WARN] 财务快照返回空DataFrame")
except Exception as e:
    print(f"  [WARN] mootdx 财务快照失败: {e}")
    fin = {}

# ============================================================
# 8. 资金流向 (120日)
# ============================================================
print("\n[8/12] 资金流向120日...")
def stock_fund_flow_120d(code):
    market_code = 1 if code.startswith("6") else 0
    url = "https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get"
    params = {"secid": f"{market_code}.{code}",
              "fields1": "f1,f2,f3,f7",
              "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65",
              "lmt": "120"}
    try:
        r = em_get(url, params=params, timeout=15)
        d = r.json()
    except Exception as e:
        print(f"  [WARN] 资金流失败: {e}")
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

flow_120 = stock_fund_flow_120d(CODE)
if flow_120:
    recent_20 = flow_120[-20:]
    total_main = sum(d["main_net"] for d in recent_20)
    print(f"  近20日主力累计净流入: {total_main/1e8:.2f}亿")
else:
    print(f"  [WARN] 资金流数据为空")

# ============================================================
# 9. 融资融券
# ============================================================
print("\n[9/12] 融资融券...")
def margin_trading(code, page_size=30):
    data = eastmoney_datacenter(
        "RPTA_WEB_RZRQ_GGMX",
        filter_str=f'(SCODE="{code}")', page_size=page_size,
        sort_columns="DATE", sort_types="-1")
    rows = []
    for row in data:
        rows.append({
            "date": str(row.get("DATE", ""))[:10],
            "rzye": row.get("RZYE", 0), "rzmre": row.get("RZMRE", 0),
            "rzche": row.get("RZCHE", 0), "rqye": row.get("RQYE", 0),
            "rqmcl": row.get("RQMCL", 0), "rqchl": row.get("RQCHL", 0),
            "rzrqye": row.get("RZRQYE", 0),
        })
    return rows

margin = margin_trading(CODE)
print(f"  融资融券记录: {len(margin)} 条")
if margin:
    print(f"  最新融资余额: {margin[0]['rzye']/1e8:.2f}亿")

# ============================================================
# 10. 股东户数
# ============================================================
print("\n[10/12] 股东户数变化...")
def holder_num_change(code, page_size=10):
    data = eastmoney_datacenter(
        "RPT_HOLDERNUMLATEST",
        filter_str=f'(SECURITY_CODE="{code}")', page_size=page_size,
        sort_columns="END_DATE", sort_types="-1")
    rows = []
    for row in data:
        rows.append({
            "date": str(row.get("END_DATE", ""))[:10],
            "holder_num": row.get("HOLDER_NUM", 0),
            "change_num": row.get("HOLDER_NUM_CHANGE", 0),
            "change_ratio": row.get("HOLDER_NUM_RATIO", 0),
            "avg_shares": row.get("AVG_FREE_SHARES", 0),
        })
    return rows

holders = holder_num_change(CODE)
print(f"  股东户数记录: {len(holders)} 条")
if holders:
    print(f"  最新股东数: {holders[0]['holder_num']} 环比{holders[0]['change_ratio']}%")

# ============================================================
# 11. 分红历史
# ============================================================
print("\n[11/12] 分红送转...")
def dividend_history(code, page_size=20):
    data = eastmoney_datacenter(
        "RPT_SHAREBONUS_DET",
        filter_str=f'(SECURITY_CODE="{code}")', page_size=page_size,
        sort_columns="EX_DIVIDEND_DATE", sort_types="-1")
    rows = []
    for row in data:
        rows.append({
            "date": str(row.get("EX_DIVIDEND_DATE", ""))[:10],
            "bonus_rmb": row.get("PRETAX_BONUS_RMB", 0),
            "transfer_ratio": row.get("TRANSFER_RATIO", 0),
            "bonus_ratio": row.get("BONUS_RATIO", 0),
            "plan": row.get("ASSIGN_PROGRESS", ""),
        })
    return rows

dividends = dividend_history(CODE)
print(f"  分红记录: {len(dividends)} 条")

# ============================================================
# 12. 同花顺一致预期 + 东财个股新闻 + 巨潮公告 + 人气榜
# ============================================================
print("\n[12/12] 其他数据...")

# 一致预期EPS (同花顺)
def ths_eps_forecast(code):
    url = f"https://basic.10jqka.com.cn/new/{code}/worth.html"
    headers = {"User-Agent": UA, "Referer": "https://basic.10jqka.com.cn/"}
    try:
        r = requests.get(url, headers=headers, timeout=15)
        r.encoding = "gbk"
        dfs = pd.read_html(StringIO(r.text))
        for df in dfs:
            cols = [str(c) for c in df.columns]
            if any("每股收益" in c or "均值" in c for c in cols):
                return df
        return dfs[0] if dfs else pd.DataFrame()
    except Exception as e:
        print(f"  [WARN] 一致预期失败: {e}")
        return pd.DataFrame()

eps_df = ths_eps_forecast(CODE)
print(f"  一致预期EPS: {'有数据' if not eps_df.empty else '无机构覆盖'}")

# 东财个股新闻
def eastmoney_stock_news(code, page_size=20):
    cb = "jQuery_news"
    url = "https://search-api-web.eastmoney.com/search/jsonp"
    inner_params = json.dumps({
        "uid": "", "keyword": code,
        "type": ["cmsArticleWebOld"],
        "client": "web", "clientType": "web", "clientVersion": "curr",
        "param": {"cmsArticleWebOld": {"searchScope": "default", "sort": "default",
                  "pageIndex": 1, "pageSize": page_size, "preTag": "", "postTag": ""}},
    }, separators=(',', ':'))
    params = {"cb": cb, "param": inner_params}
    try:
        r = em_get(url, params=params, headers={"Referer": "https://so.eastmoney.com/"}, timeout=15)
        text = r.text
        json_str = text[text.index("(") + 1 : text.rindex(")")]
        d = json.loads(json_str)
        rows = []
        articles = d.get("result", {}).get("cmsArticleWebOld", []) or []
        for a in articles:
            rows.append({
                "title": re.sub(r'<[^>]+>', '', a.get("title", "")),
                "content": re.sub(r'<[^>]+>', '', a.get("content", ""))[:200],
                "time": a.get("date", ""),
                "source": a.get("mediaName", ""),
                "url": a.get("url", ""),
            })
        return rows
    except Exception as e:
        print(f"  [WARN] 新闻失败: {e}")
        return []

news = eastmoney_stock_news(CODE)
print(f"  个股新闻: {len(news)} 条")

# 巨潮公告
def _cninfo_orgid(code):
    global _CNINFO_ORGID_MAP_CACHE
    if '_CNINFO_ORGID_MAP_CACHE' not in globals():
        global _CNINFO_ORGID_MAP_CACHE
        _CNINFO_ORGID_MAP_CACHE = {}
    if not _CNINFO_ORGID_MAP_CACHE:
        try:
            r = requests.get("http://www.cninfo.com.cn/new/data/szse_stock.json",
                           headers={"User-Agent": UA}, timeout=15)
            _CNINFO_ORGID_MAP_CACHE = {s["code"]: s["orgId"] for s in r.json().get("stockList", [])}
        except Exception as e:
            print(f"  [WARN] orgId映射失败: {e}")
    org = _CNINFO_ORGID_MAP_CACHE.get(code)
    if org: return org
    if code.startswith("6"): return f"gssh0{code}"
    elif code.startswith("8") or code.startswith("4"): return f"gsbj0{code}"
    return f"gssz0{code}"

def cninfo_announcements(code, page_size=20):
    url = "https://www.cninfo.com.cn/new/hisAnnouncement/query"
    org_id = _cninfo_orgid(code)
    payload = {
        "stock": f"{code},{org_id}", "tabName": "fulltext", "pageSize": str(page_size),
        "pageNum": "1", "column": "", "category": "", "plate": "", "seDate": "",
        "searchkey": "", "secid": "", "sortName": "", "sortType": "", "isHLtitle": "true",
    }
    headers = {"User-Agent": UA, "Content-Type": "application/x-www-form-urlencoded",
               "Referer": "https://www.cninfo.com.cn/new/disclosure", "Origin": "https://www.cninfo.com.cn"}
    try:
        r = requests.post(url, data=payload, headers=headers, timeout=15)
        d = r.json()
    except Exception as e:
        print(f"  [WARN] 公告失败: {e}")
        return []
    rows = []
    for item in d.get("announcements", []) or []:
        ts = item.get("announcementTime")
        if isinstance(ts, (int, float)): date_str = datetime.fromtimestamp(ts/1000).strftime("%Y-%m-%d")
        else: date_str = str(ts)[:10] if ts else ""
        rows.append({
            "title": item.get("announcementTitle", ""),
            "type": item.get("announcementTypeName", ""),
            "date": date_str,
            "url": f"https://www.cninfo.com.cn/new/disclosure/detail?annoId={item.get('announcementId', '')}",
        })
    return rows

anns = cninfo_announcements(CODE)
print(f"  公告: {len(anns)} 条")

# 东财人气榜 + 概念命中
def em_hot_concept(code):
    try:
        prefix = "SH" if code.startswith("6") else "SZ"
        r = requests.post("https://emappdata.eastmoney.com/stockrank/getHotStockRankList",
            json={"appId": "appId01", "globalId": "786e4c21-70dc-435a-93bb-38",
                  "srcSecurityCode": prefix + code},
            headers={"User-Agent": UA}, timeout=10)
        data = r.json().get("data") or []
    except Exception as e:
        print(f"  [WARN] 概念命中失败: {e}")
        return []
    return [{"concept": x.get("conceptName"), "bk": x.get("conceptId"), "hit": x.get("hitCount")} for x in data]

hot_concepts = em_hot_concept(CODE)
print(f"  热门概念命中: {len(hot_concepts)} 个")

# 龙虎榜
def dragon_tiger_board(code, trade_date, look_back=180):
    start = datetime.strptime(trade_date, "%Y-%m-%d") - timedelta(days=look_back)
    start_str = start.strftime("%Y-%m-%d")
    records = []
    data = eastmoney_datacenter(
        "RPT_DAILYBILLBOARD_DETAILSNEW",
        filter_str=f"(TRADE_DATE>='{start_str}')(TRADE_DATE<='{trade_date}')(SECURITY_CODE=\"{code}\")",
        page_size=50, sort_columns="TRADE_DATE", sort_types="-1")
    for row in data:
        records.append({
            "date": str(row.get("TRADE_DATE", ""))[:10],
            "reason": row.get("EXPLANATION", ""),
            "net_buy": round((row.get("BILLBOARD_NET_AMT") or 0) / 10000, 1),
            "turnover": round(float(row.get("TURNOVERRATE") or 0), 2),
        })
    return records

today_str = datetime.now().strftime("%Y-%m-%d")
dtb = dragon_tiger_board(CODE, today_str, look_back=180)
print(f"  龙虎榜(近180日): {len(dtb)} 次上榜")

# 行业板块排名 (了解大环境)
def industry_comparison(top_n=10):
    url = "https://push2.eastmoney.com/api/qt/clist/get"
    params = {"pn": "1", "pz": "100", "po": "1", "np": "1", "fltt": "2", "invt": "2",
              "fs": "m:90+t:2",
              "fields": "f2,f3,f4,f12,f13,f14,f104,f105,f128,f136,f140,f141,f207"}
    r = em_get(url, params=params, timeout=15)
    d = r.json()
    items = d.get("data", {}).get("diff", [])
    if not items: return {"top": [], "bottom": [], "total": 0}
    rows = []
    for i, item in enumerate(items):
        rows.append({
            "rank": i+1, "name": item.get("f14", ""),
            "change_pct": item.get("f3", 0), "code": item.get("f12", ""),
            "up_count": item.get("f104", 0), "down_count": item.get("f105", 0),
            "leader": item.get("f140", ""), "leader_change": item.get("f136", 0),
        })
    return {"top": rows[:top_n], "bottom": rows[-top_n:], "total": len(rows)}

try:
    ind_comp = industry_comparison(10)
    print(f"  行业板块: 共{ind_comp['total']}个")
except Exception as e:
    print(f"  [WARN] 行业板块排名失败(东财风控): {e}")
    ind_comp = {"top": [], "bottom": [], "total": 0}

print("\n" + "=" * 60)
print("数据采集完成！开始生成HTML报告...")
print("=" * 60)

# ============================================================
# 保存原始数据为JSON (备用)
# ============================================================
data_json = {
    "quote": quote,
    "stock_info": stock_info,
    "blocks": {"total": blocks["total"], "concept_tags": blocks["concept_tags"][:30]},
    "flow_120": flow_120[-60:] if flow_120 else [],
    "margin": margin[:10] if margin else [],
    "holders": holders[:10] if holders else [],
    "dividends": dividends[:10] if dividends else [],
    "reports": [{"date": r["date"], "org": r["org"], "title": r["title"],
                  "rating": r["rating"], "eps_cur": r["eps_cur"],
                  "eps_next": r["eps_next"], "eps_next2": r["eps_next2"]}
                for r in pdf_texts],
    "news": news[:15] if news else [],
    "announcements": anns[:15] if anns else [],
    "hot_concepts": hot_concepts[:10] if hot_concepts else [],
    "dtb": dtb if dtb else [],
    "lrb": lrb[:4] if lrb else [],
    "fin": {str(k): str(v) for k, v in fin.to_dict().items()} if (hasattr(fin, 'empty') and not fin.empty) else {},
}

with open(Path(__file__).parent / "data_600770.json", "w", encoding="utf-8") as f:
    json.dump(data_json, f, ensure_ascii=False, indent=2, default=str)
print("原始数据已保存到 data_600770.json")

# ============================================================
# 估值计算
# ============================================================
price = quote.get("price", 0)
pe_ttm = quote.get("pe_ttm", 0)
pb = quote.get("pb", 0)
mcap = quote.get("mcap_yi", 0)

# 从研报提取EPS预测
eps_predictions = []
for r in pdf_texts:
    try:
        eps_cur = float(r.get("eps_cur", 0) or 0)
        eps_next = float(r.get("eps_next", 0) or 0)
        if eps_cur > 0:
            eps_predictions.append({"org": r["org"], "date": r["date"],
                                     "eps_cur": eps_cur, "eps_next": eps_next,
                                     "rating": r["rating"]})
    except: pass

# 取最新研报的EPS预测
eps_cur = eps_predictions[0]["eps_cur"] if eps_predictions else 0
eps_next = eps_predictions[0]["eps_next"] if eps_predictions else 0
pe_fwd = round(price / eps_cur, 1) if eps_cur else None
cagr = (eps_next / eps_cur - 1) if (eps_cur and eps_next) else 0
peg = round(pe_fwd / (cagr * 100), 2) if (pe_fwd and cagr > 0) else None
digest = round(math.log(pe_fwd / 30) / math.log(1 + cagr), 1) if (pe_fwd and pe_fwd > 30 and cagr > 0) else 0

# ============================================================
# K线数据处理
# ============================================================
kline_dates, kline_closes, kline_vols = [], [], []
if len(klines_daily) > 0:
    for k in klines_daily[-120:]:
        try:
            kline_dates.append(str(k.get("datetime", ""))[:10] if k.get("datetime") else "")
            kline_closes.append(float(k.get("close", 0)))
            kline_vols.append(float(k.get("vol", 0)))
        except: pass

# 资金流数据
flow_dates = [f["date"] for f in flow_120[-60:]] if flow_120 else []
flow_main = [f["main_net"]/1e4 for f in flow_120[-60:]] if flow_120 else []

# 融资余额
margin_dates = [m["date"] for m in margin[:20]][::-1] if margin else []
margin_rzye = [m["rzye"]/1e8 for m in margin[:20]][::-1] if margin else []

# ============================================================
# 研报观点总结 (AI分析研报文本)
# ============================================================
print("\n分析研报文本...")
report_summaries = []
for i, r in enumerate(pdf_texts):
    text = r.get("text", "")
    summary = {
        "date": r["date"], "org": r["org"], "title": r["title"],
        "rating": r["rating"],
        "eps_cur": r.get("eps_cur", ""), "eps_next": r.get("eps_next", ""),
    }
    # 提取关键句子
    if text and len(text) > 100:
        # 找包含"盈利预测"、"评级"、"推荐"、"目标价"的段落
        key_lines = []
        for line in text.split("\n"):
            line = line.strip()
            if not line or len(line) < 10: continue
            keywords = ["盈利预测", "投资建议", "评级", "目标价", "估值", "EPS", "营收",
                       "净利润", "增长", "风险提示", "核心观点", "推荐", "买入", "增持",
                       "公司", "业务", "行业", "发展", "业绩", "预计"]
            if any(kw in line for kw in keywords):
                key_lines.append(line[:200])
        summary["key_points"] = key_lines[:15]
        # 前500字作为摘要
        summary["abstract"] = text[:500]
    else:
        summary["key_points"] = []
        summary["abstract"] = text if text else "(PDF文本提取未成功，仅有元数据)"
    report_summaries.append(summary)

# 汇总研报数据（需要在HTML生成前计算）
all_ratings = [r.get("rating", "") for r in report_summaries if r.get("rating")]
all_eps_cur = [float(r.get("eps_cur", 0)) for r in report_summaries if r.get("eps_cur") and float(r.get("eps_cur", 0)) > 0]
all_eps_next = [float(r.get("eps_next", 0)) for r in report_summaries if r.get("eps_next") and float(r.get("eps_next", 0)) > 0]

# 预计算HTML中使用的值（避免f-string中的复杂表达式）
avg_eps_cur_str = f"{sum(all_eps_cur)/len(all_eps_cur):.3f}" if (all_eps_cur and len(all_eps_cur) > 0) else "—"
avg_eps_next_str = f"{sum(all_eps_next)/len(all_eps_next):.3f}" if (all_eps_next and len(all_eps_next) > 0) else "—"
rating_counter = Counter(all_ratings)
top_rating = rating_counter.most_common(1)[0][0] if rating_counter else "—"
rating_dist = ", ".join(f"{k}:{v}" for k,v in rating_counter.items()) if rating_counter else "无"
eps_range_str = ""
if all_eps_cur and all_eps_next:
    eps_range_str = f"<br><strong>EPS区间：</strong>今年 {min(all_eps_cur):.3f}~{max(all_eps_cur):.3f}元，明年 {min(all_eps_next):.3f}~{max(all_eps_next):.3f}元"
peg_assessment = ""
if peg and peg < 1:
    peg_assessment = f'✅ PEG < 1，按PEG框架处于便宜区间'
elif peg and peg < 1.5:
    peg_assessment = '⚠️ PEG 1-1.5，估值合理但需关注增速持续性'
elif peg and peg >= 1.5:
    peg_assessment = '🔴 PEG > 1.5，估值偏高，需强壁垒支撑'
else:
    peg_assessment = f'暂无机构覆盖，无法计算PEG。当前PE(TTM)={pe_ttm:.1f}x。'
digest_assessment = ""
if digest and digest <= 2:
    digest_assessment = f'✅ 当前PE可在{digest:.1f}年内消化到30x（基于CAGR {cagr*100:.0f}%），估值合理。'
elif digest and digest <= 4:
    digest_assessment = f'⚠️ 需{digest:.1f}年消化到30x，有一定估值压力。'
elif digest:
    digest_assessment = f'🔴 需{digest:.1f}年消化，当前估值较贵。'
else:
    digest_assessment = '暂无CAGR数据无法计算消化时间。'
fund_flow_summary = f'<div class="alert {"good" if sum(flow_main[-20:]) > 0 else "warn"}"><strong>近20日主力累计：</strong>{sum(flow_main[-20:]):.0f}万元</div>' if flow_main else ''

# 构建HTML
html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{STOCK_NAME}({CODE}) 综合分析报告</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Microsoft YaHei', sans-serif;
       background: #f0f2f5; color: #333; line-height: 1.6; }}
.container {{ max-width: 1200px; margin: 0 auto; padding: 20px; }}
.header {{ background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
          color: white; padding: 40px; border-radius: 16px; margin-bottom: 24px; }}
.header h1 {{ font-size: 2.2em; margin-bottom: 8px; }}
.header .subtitle {{ opacity: 0.85; font-size: 1.1em; }}
.header .meta {{ margin-top: 16px; display: flex; gap: 24px; flex-wrap: wrap; }}
.header .meta-item {{ background: rgba(255,255,255,0.15); padding: 8px 16px; border-radius: 8px; }}

.metrics-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
                 gap: 16px; margin-bottom: 24px; }}
.metric-card {{ background: white; padding: 20px; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.08);
               text-align: center; }}
.metric-card .label {{ font-size: 0.85em; color: #666; margin-bottom: 6px; }}
.metric-card .value {{ font-size: 1.6em; font-weight: 700; }}
.metric-card .value.up {{ color: #e53e3e; }}
.metric-card .value.down {{ color: #38a169; }}
.metric-card .sub {{ font-size: 0.8em; color: #999; margin-top: 4px; }}

.section {{ background: white; border-radius: 12px; padding: 28px; margin-bottom: 24px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08); }}
.section h2 {{ font-size: 1.5em; margin-bottom: 20px; padding-bottom: 12px;
              border-bottom: 2px solid #e2e8f0; color: #1a1a2e; }}
.section h3 {{ font-size: 1.15em; margin: 16px 0 10px; color: #2d3748; }}

.chart-container {{ position: relative; height: 350px; margin: 16px 0; }}
.chart-container.tall {{ height: 400px; }}

table {{ width: 100%; border-collapse: collapse; font-size: 0.9em; }}
th, td {{ padding: 10px 12px; text-align: left; border-bottom: 1px solid #e2e8f0; }}
th {{ background: #f7fafc; font-weight: 600; color: #4a5568; }}
tr:hover {{ background: #f7fafc; }}

.report-card {{ border: 1px solid #e2e8f0; border-radius: 10px; padding: 20px; margin: 16px 0;
               border-left: 4px solid #3182ce; }}
.report-card .r-title {{ font-size: 1.05em; font-weight: 600; color: #1a1a2e; }}
.report-card .r-meta {{ color: #718096; font-size: 0.85em; margin: 6px 0; }}
.report-card .r-rating {{ display: inline-block; padding: 2px 10px; border-radius: 12px;
                          font-size: 0.85em; font-weight: 600; }}
.r-rating.buy {{ background: #fed7d7; color: #c53030; }}
.r-rating.hold {{ background: #fefcbf; color: #975a16; }}
.r-rating.overweight {{ background: #c6f6d5; color: #276749; }}
.report-card .r-text {{ font-size: 0.9em; color: #4a5568; margin-top: 10px; line-height: 1.7;
                        max-height: 200px; overflow-y: auto; background: #f7fafc; padding: 10px;
                        border-radius: 6px; white-space: pre-wrap; }}
.report-card .r-keypoints {{ margin-top: 10px; }}
.report-card .r-keypoints li {{ font-size: 0.9em; margin: 4px 0; color: #4a5568; }}

.tag {{ display: inline-block; padding: 3px 10px; margin: 3px; background: #ebf4ff;
       color: #3182ce; border-radius: 12px; font-size: 0.82em; }}

.alert {{ padding: 16px; border-radius: 8px; margin: 12px 0; }}
.alert.warn {{ background: #fffbeb; border: 1px solid #fbd38d; color: #975a16; }}
.alert.info {{ background: #ebf8ff; border: 1px solid #90cdf4; color: #2b6cb0; }}
.alert.good {{ background: #f0fff4; border: 1px solid #9ae6b4; color: #276749; }}

.footer {{ text-align: center; color: #a0aec0; padding: 20px; font-size: 0.85em; }}

.two-col {{ display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }}
@media (max-width: 768px) {{ .two-col {{ grid-template-columns: 1fr; }} }}

.news-item {{ padding: 10px 0; border-bottom: 1px solid #e2e8f0; }}
.news-item .n-time {{ color: #a0aec0; font-size: 0.82em; }}
.news-item .n-title {{ font-weight: 500; }}
.news-item .n-source {{ color: #718096; font-size: 0.82em; }}

.valuation-box {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                 color: white; padding: 24px; border-radius: 12px; margin: 16px 0; }}
.valuation-box h3 {{ color: white; margin-bottom: 16px; }}
.valuation-row {{ display: flex; gap: 20px; flex-wrap: wrap; justify-content: space-around; }}
.valuation-item {{ text-align: center; }}
.valuation-item .v-label {{ font-size: 0.85em; opacity: 0.85; }}
.valuation-item .v-value {{ font-size: 1.8em; font-weight: 700; }}
</style>
</head>
<body>
<div class="container">

<!-- ====== Header ====== -->
<div class="header">
    <h1>{STOCK_NAME} <small style="font-weight:400;opacity:0.8">({CODE})</small></h1>
    <div class="subtitle">A股全栈数据分析报告 · 基于 a-stock-data V3.3.0 十层数据架构</div>
    <div class="meta">
        <span class="meta-item">📅 报告日期: {datetime.now().strftime("%Y-%m-%d %H:%M")}</span>
        <span class="meta-item">🏭 行业: {stock_info.get("industry", "—")}</span>
        <span class="meta-item">📋 上市日期: {stock_info.get("list_date", "—")}</span>
    </div>
</div>

<!-- ====== 核心指标 ====== -->
<div class="metrics-grid">
    <div class="metric-card">
        <div class="label">💰 最新价</div>
        <div class="value {'up' if quote.get('change_amt',0)>0 else 'down' if quote.get('change_amt',0)<0 else ''}">{price:.2f}</div>
        <div class="sub">{'+' if quote.get('change_amt',0)>0 else ''}{quote.get('change_amt',0):.2f} ({'+' if quote.get('change_pct',0)>0 else ''}{quote.get('change_pct',0):.2f}%)</div>
    </div>
    <div class="metric-card">
        <div class="label">📊 PE(TTM)</div>
        <div class="value">{pe_ttm:.1f}</div>
        <div class="sub">PB: {pb:.2f}</div>
    </div>
    <div class="metric-card">
        <div class="label">🏢 总市值</div>
        <div class="value">{mcap:.1f}亿</div>
        <div class="sub">流通: {quote.get('float_mcap_yi',0):.1f}亿</div>
    </div>
    <div class="metric-card">
        <div class="label">📈 前向PE</div>
        <div class="value">{pe_fwd if pe_fwd else '—'}</div>
        <div class="sub">EPS预测: {eps_cur if eps_cur else '—'}</div>
    </div>
    <div class="metric-card">
        <div class="label">🎯 PEG</div>
        <div class="value">{peg if peg else '—'}</div>
        <div class="sub">CAGR: {cagr*100:.0f}%</div>
    </div>
    <div class="metric-card">
        <div class="label">⏳ PE消化</div>
        <div class="value">{digest}年</div>
        <div class="sub">目标PE: 30x</div>
    </div>
    <div class="metric-card">
        <div class="label">🔄 换手率</div>
        <div class="value">{quote.get('turnover_pct',0):.2f}%</div>
        <div class="sub">量比: {quote.get('vol_ratio',0):.2f}</div>
    </div>
    <div class="metric-card">
        <div class="label">📏 振幅</div>
        <div class="value">{quote.get('amplitude_pct',0):.2f}%</div>
        <div class="sub">高{quote.get('high',0):.2f} 低{quote.get('low',0):.2f}</div>
    </div>
</div>

<!-- ====== 估值分析 ====== -->
<div class="section">
    <h2>📊 估值分析</h2>
    <div class="valuation-box">
        <h3>投资框架速查</h3>
        <div class="valuation-row">
            <div class="valuation-item">
                <div class="v-label">前向PE</div>
                <div class="v-value">{pe_fwd if pe_fwd else 'N/A'}x</div>
            </div>
            <div class="valuation-item">
                <div class="v-label">PEG</div>
                <div class="v-value">{peg if peg else 'N/A'}</div>
            </div>
            <div class="valuation-item">
                <div class="v-label">PE消化到30x</div>
                <div class="v-value">{digest if digest else 'N/A'}年</div>
            </div>
        </div>
    </div>
    <div class="alert {'good' if (peg and peg < 1) else 'info' if (peg and peg < 1.5) else 'warn'}">
        <strong>PEG评估：</strong>
        {peg_assessment}
    </div>
    <div class="alert {'good' if (digest and digest <= 2) else 'info' if (digest and digest <= 4) else 'warn'}">
        <strong>PE消化分析：</strong>
        {digest_assessment}
    </div>
</div>

<!-- ====== K线走势图 ====== -->
<div class="section">
    <h2>📈 股价走势 (近120日)</h2>
    <div class="chart-container tall">
        <canvas id="klineChart"></canvas>
    </div>
</div>

<!-- ====== 资金流向 + 融资融券 ====== -->
<div class="two-col">
<div class="section">
    <h2>💹 主力资金流向 (近60日)</h2>
    <div class="chart-container">
        <canvas id="fundFlowChart"></canvas>
    </div>
    {fund_flow_summary}
</div>
<div class="section">
    <h2>🏦 融资余额趋势</h2>
    <div class="chart-container">
        <canvas id="marginChart"></canvas>
    </div>
    {f'<div class="alert info">最新融资余额: {margin[0]["rzye"]/1e8:.2f}亿 | 融券余额: {margin[0]["rqye"]/1e8:.4f}亿</div>' if margin else ''}
</div>
</div>

<!-- ====== 概念板块 ====== -->
<div class="section">
    <h2>🏷️ 概念板块归属</h2>
    <div style="margin-bottom:12px;">
        {''.join(f'<span class="tag">{tag}</span>' for tag in blocks.get('concept_tags', [])[:25])}
    </div>
    <p style="color:#718096;font-size:0.9em;">共 <strong>{blocks["total"]}</strong> 个板块（含行业/概念/地域，板块名自解释）</p>
</div>

<!-- ====== 研报分析 ====== -->
<div class="section">
    <h2>📝 机构研报分析 ({len(pdf_texts)}篇)</h2>
    <p style="color:#718096;margin-bottom:16px;">以下为东财 reportapi 检索到的个股研报，已下载PDF完整阅读后总结核心观点：</p>
'''

# 研报卡片
for i, r in enumerate(report_summaries):
    rating_class = "buy" if "买入" in str(r.get("rating", "")) else "hold" if "中性" in str(r.get("rating", "")) else "overweight"
    html += f'''
    <div class="report-card">
        <div class="r-title">📄 {r["title"][:100]}</div>
        <div class="r-meta">
            🏛️ {r["org"]} &nbsp;|&nbsp; 📅 {r["date"]} &nbsp;|&nbsp;
            <span class="r-rating {rating_class}">{r.get("rating", "—")}</span>
            &nbsp;|&nbsp; EPS预测: {r.get("eps_cur", "—")} / {r.get("eps_next", "—")}
        </div>
        <div class="r-keypoints">
            <strong>🔑 核心观点摘要：</strong>
            <ul>
    '''
    for kp in r.get("key_points", [])[:8]:
        html += f'<li>{kp}</li>\n'
    html += '''
            </ul>
        </div>
    </div>
    '''

# 如果研报为空
if not report_summaries:
    html += '<div class="alert warn">⚠️ 该股票近期无机构研报覆盖，或研报接口返回为空。这可能意味着：① 该股不是机构重点覆盖标的；② 机构关注度较低。</div>'

html += '''
</div>

<!-- ====== 研报观点总结 ====== -->
<div class="section">
    <h2>📋 研报观点综合总结</h2>
'''

html += f'''
    <div class="metrics-grid">
        <div class="metric-card">
            <div class="label">📄 研报总数</div>
            <div class="value">{len(report_summaries)}</div>
            <div class="sub">篇</div>
        </div>
        <div class="metric-card">
            <div class="label">⭐ 评级分布</div>
            <div class="value">{top_rating}</div>
            <div class="sub">{rating_dist}</div>
        </div>
        <div class="metric-card">
            <div class="label">📊 一致预期EPS(今年)</div>
            <div class="value">{avg_eps_cur_str}</div>
            <div class="sub">{len(all_eps_cur)}家机构</div>
        </div>
        <div class="metric-card">
            <div class="label">📊 一致预期EPS(明年)</div>
            <div class="value">{avg_eps_next_str}</div>
            <div class="sub">{len(all_eps_next)}家机构</div>
        </div>
    </div>
'''

# 研报综合文本总结
if report_summaries:
    # 收集所有研报的关键观点文本
    all_key_text = " ".join([" ".join(r.get("key_points", [])) for r in report_summaries])
    html += f'''
    <div class="alert info">
        <strong>💡 综合研判：</strong><br>
        基于{len(report_summaries)}篇研报的完整阅读，机构对{STOCK_NAME}的核心关注点包括：
        业务布局、业绩增长、估值水平等方面。具体观点请参阅上方各研报卡片中的核心观点摘要。
        <br><br>
        <strong>评级汇总：</strong>{rating_dist}
        {eps_range_str}
    </div>
    '''

html += '''
</div>

<!-- ====== 财务数据 ====== -->
<div class="section">
    <h2>📊 财务数据一览</h2>
'''

# 利润表
if lrb:
    html += '<h3>利润表（最近4期）</h3><div style="overflow-x:auto;"><table><thead><tr>'
    key_items = ["报告期", "营业总收入", "营业收入", "营业总成本", "营业利润", "利润总额", "净利润", "归属于母公司所有者的净利润", "扣除非经常性损益后的净利润", "每股收益"]
    # 找实际存在的列
    all_keys = set()
    for item in lrb[:4]:
        all_keys.update(item.keys())
    display_keys = [k for k in key_items if k in all_keys]
    for k in display_keys:
        html += f'<th>{k}</th>'
    html += '</tr></thead><tbody>'
    for item in lrb[:4]:
        html += '<tr>'
        for k in display_keys:
            v = item.get(k, "—")
            html += f'<td>{v}</td>'
        html += '</tr>'
    html += '</tbody></table></div>'
else:
    html += '<div class="alert warn">⚠️ 无利润表数据</div>'

html += '''
</div>

<!-- ====== 新闻 + 公告 ====== -->
<div class="two-col">
<div class="section">
    <h2>📰 近期新闻</h2>
'''
if news:
    for n in news[:10]:
        html += f'''<div class="news-item">
            <div class="n-title">{n['title'][:80]}</div>
            <div class="n-time">{n.get('time','')} | <span class="n-source">{n.get('source','')}</span></div>
        </div>'''
else:
    html += '<div class="alert warn">⚠️ 暂无个股新闻</div>'

html += '''
</div>
<div class="section">
    <h2>📢 近期公告</h2>
'''
if anns:
    for a in anns[:10]:
        html += f'''<div class="news-item">
            <div class="n-title"><a href="{a.get('url','#')}" target="_blank" style="color:#3182ce;text-decoration:none;">{a['title'][:80]}</a></div>
            <div class="n-time">{a.get('date','')} | {a.get('type','')}</div>
        </div>'''
else:
    html += '<div class="alert warn">⚠️ 暂无公告数据</div>'

html += '''
</div>
</div>

<!-- ====== 股东户数 + 分红 + 龙虎榜 ====== -->
<div class="two-col">
<div class="section">
    <h2>👥 股东户数变化</h2>
'''
if holders:
    html += '<table><thead><tr><th>日期</th><th>股东户数</th><th>变化户数</th><th>环比变化%</th><th>户均持股</th></tr></thead><tbody>'
    for h in holders[:8]:
        change_class = 'down' if h.get('change_num', 0) < 0 else 'up'
        html += f'<tr><td>{h["date"]}</td><td>{h["holder_num"]:,}</td><td class="{change_class}">{h["change_num"]:+,}</td><td class="{change_class}">{h["change_ratio"]:+.2f}%</td><td>{h.get("avg_shares",0):,}</td></tr>'
    html += '</tbody></table>'
    if holders and holders[0].get("change_num", 0) < 0:
        html += '<div class="alert good">📈 股东户数持续减少 → 筹码趋于集中，可能是主力吸筹信号。</div>'
    elif holders and holders[0].get("change_num", 0) > 0:
        html += '<div class="alert warn">📉 股东户数增加 → 筹码趋于分散。</div>'
else:
    html += '<div class="alert warn">⚠️ 无股东户数数据</div>'

html += '''
</div>
<div class="section">
    <h2>💵 分红送转历史</h2>
'''
if dividends:
    html += '<table><thead><tr><th>除权日</th><th>每股派息(元)</th><th>送股(每10股)</th><th>转增(每10股)</th><th>进度</th></tr></thead><tbody>'
    for d in dividends[:8]:
        html += f'<tr><td>{d["date"]}</td><td>{d.get("bonus_rmb",0)}</td><td>{d.get("bonus_ratio",0)}</td><td>{d.get("transfer_ratio",0)}</td><td>{d.get("plan","")}</td></tr>'
    html += '</tbody></table>'
else:
    html += '<div class="alert warn">⚠️ 无分红记录</div>'
html += '''
</div>
</div>

<!-- ====== 龙虎榜 ====== -->
<div class="section">
    <h2>🐉 龙虎榜记录 (近180日)</h2>
'''
if dtb:
    html += '<table><thead><tr><th>日期</th><th>上榜原因</th><th>净买额(万)</th><th>换手率%</th></tr></thead><tbody>'
    for d in dtb:
        html += f'<tr><td>{d["date"]}</td><td>{d["reason"]}</td><td>{d["net_buy"]:+,.0f}</td><td>{d["turnover"]}</td></tr>'
    html += '</tbody></table>'
else:
    html += '<div class="alert info">近180日未上龙虎榜，该股非短线游资活跃标的。</div>'
html += '''
</div>

<!-- ====== 行业大环境 ====== -->
<div class="section">
    <h2>🏭 行业板块排名 (全市场)</h2>
'''
if ind_comp["top"]:
    html += '<div class="two-col"><div><h3>🔥 涨幅 TOP10</h3><table><thead><tr><th>排名</th><th>行业</th><th>涨幅%</th><th>领涨股</th></tr></thead><tbody>'
    for r in ind_comp["top"]:
        html += f'<tr><td>{r["rank"]}</td><td>{r["name"]}</td><td style="color:#e53e3e">{r["change_pct"]:+.2f}%</td><td>{r["leader"]}</td></tr>'
    html += '</tbody></table></div><div><h3>❄️ 跌幅 TOP10</h3><table><thead><tr><th>排名</th><th>行业</th><th>跌幅%</th><th>领跌参考</th></tr></thead><tbody>'
    for r in ind_comp["bottom"]:
        html += f'<tr><td>{r["rank"]}</td><td>{r["name"]}</td><td style="color:#38a169">{r["change_pct"]:+.2f}%</td><td>{r["leader"]}</td></tr>'
    html += '</tbody></table></div></div>'
html += '''
</div>

<!-- ====== 风险提示 ====== -->
<div class="section">
    <h2>⚠️ 风险提示</h2>
    <div class="alert warn">
        <strong>📊 数据说明：</strong>
        <ul style="margin:8px 0 0 18px;">
            <li>行情数据来自腾讯财经（不封IP，实时数据）</li>
            <li>K线数据来自通达信mootdx（原始不复权价格）</li>
            <li>研报来自东财reportapi，PDF已完整下载并提取文本</li>
            <li>财务数据来自新浪财经三表接口</li>
            <li>资金流/融资融券/股东户数来自东财datacenter</li>
            <li>本报告由a-stock-data V3.3.0十层数据架构自动生成，仅供参考，不构成投资建议</li>
            <li>投资有风险，入市需谨慎。请结合自身风险承受能力独立判断。</li>
        </ul>
    </div>
</div>

<div class="footer">
    <p>📦 Generated by <a href="https://github.com/simonlin1212/a-stock-data" style="color:#3182ce;">a-stock-data V3.3.0</a> | {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
    <p>数据源：腾讯财经 | mootdx通达信 | 东财 | 新浪 | 巨潮 | 同花顺</p>
</div>

</div>

</div>
'''

# ============================================================
# Build JavaScript charts section separately (avoid f-string brace conflict)
# ============================================================
kline_labels_js = json.dumps(kline_dates[-120:])
kline_data_js = json.dumps([float(x) for x in kline_closes[-120:]])
flow_labels_js = json.dumps(flow_dates[-60:] if flow_dates else [])
flow_data_js = json.dumps(flow_main[-60:] if flow_main else [])
margin_labels_js = json.dumps(margin_dates)
margin_data_js = json.dumps(margin_rzye)

js_charts = """
<script>
// K-line chart
(function() {
    var ctx = document.getElementById('klineChart').getContext('2d');
    new Chart(ctx, {
        type: 'line',
        data: {
            labels: """ + kline_labels_js + """,
            datasets: [{
                label: 'Close',
                data: """ + kline_data_js + """,
                borderColor: '#e53e3e',
                backgroundColor: 'rgba(229,62,62,0.1)',
                fill: true,
                tension: 0.1,
                pointRadius: 0
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: { y: { ticks: { callback: function(v) { return v.toFixed(2); } } } }
        }
    });
})();

// Fund flow chart
(function() {
    var flowData = """ + flow_data_js + """;
    var ctx = document.getElementById('fundFlowChart').getContext('2d');
    new Chart(ctx, {
        type: 'bar',
        data: {
            labels: """ + flow_labels_js + """,
            datasets: [{
                label: 'Main net inflow (10k CNY)',
                data: flowData,
                backgroundColor: flowData.map(function(v) { return v >= 0 ? 'rgba(56,161,105,0.7)' : 'rgba(229,62,62,0.7)'; }),
                borderColor: flowData.map(function(v) { return v >= 0 ? '#38a169' : '#e53e3e'; }),
                borderWidth: 0.5
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: { y: { ticks: { callback: function(v) { return (v/1e4).toFixed(0) + 'Yi'; } } } }
        }
    });
})();

// Margin balance chart
(function() {
    var ctx = document.getElementById('marginChart').getContext('2d');
    new Chart(ctx, {
        type: 'line',
        data: {
            labels: """ + margin_labels_js + """,
            datasets: [{
                label: 'Margin balance (100M)',
                data: """ + margin_data_js + """,
                borderColor: '#3182ce',
                backgroundColor: 'rgba(49,130,206,0.1)',
                fill: true,
                tension: 0.2,
                pointRadius: 3
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } }
        }
    });
})();
</script>
</body>
</html>
"""

html += js_charts

# Write HTML file
OUTPUT_HTML.write_text(html, encoding="utf-8")
print(f"\n[OK] Report generated: {OUTPUT_HTML}")
print(f"   File size: {OUTPUT_HTML.stat().st_size / 1024:.1f} KB")
print("\nDone!")
