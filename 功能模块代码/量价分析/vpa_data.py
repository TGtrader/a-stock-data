"""
VPA 数据适配层 — 统一 OHLCV + 资金流数据获取
==============================================
三级降级策略：mootdx(TCP) → Tushare(HTTP) → 腾讯(仅实时)
资金流：Tushare pro.moneyflow()

支持：个股 / 指数 / ETF / 行业板块
"""

import time
import random
import logging
import os
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple

import numpy as np
import pandas as pd
import requests

logger = logging.getLogger("vpa.data")

# ═══════════════════════════════════════════════════════════════
# 全局配置
# ═══════════════════════════════════════════════════════════════

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

# mootdx 服务器列表
_TDX_SERVERS = [
    ('119.97.185.59', 7709), ('124.70.133.119', 7709), ('116.205.183.150', 7709),
    ('123.60.73.44', 7709),  ('116.205.163.254', 7709), ('121.36.225.169', 7709),
    ('123.60.70.228', 7709), ('124.71.9.153', 7709),    ('110.41.147.114', 7709),
    ('124.71.187.122', 7709),
]

# 东财限流配置
EM_MIN_INTERVAL = 1.0
_em_last_call = [0.0]


# ═══════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════

def _probe(ip, port, timeout=2.0):
    """TCP 握手探测"""
    import socket
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except Exception:
        return False


def get_tushare_token() -> Optional[str]:
    """从 vibe-trading 或环境变量读取 Tushare token"""
    # 优先环境变量
    token = os.environ.get("TUSHARE_TOKEN", "")
    if token and token not in ("", "your-tushare-token"):
        return token

    # vibe-trading 配置文件
    for env_path in [
        os.path.expanduser(r"~\.vibe-trading\.env"),
        os.path.join(os.path.dirname(__file__), "..", "..", "vibe-trading-repo", "agent", ".env"),
    ]:
        try:
            if os.path.exists(env_path):
                with open(env_path, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("TUSHARE_TOKEN="):
                            val = line.split("=", 1)[1].strip().strip('"').strip("'")
                            if val and val not in ("your-tushare-token", ""):
                                return val
        except Exception:
            pass
    return None


def normalize_code(code: str) -> str:
    """归一化股票代码为纯6位数字"""
    code = code.strip().upper()
    for prefix in ("SH", "SZ", "BJ"):
        if code.startswith(prefix):
            code = code[2:]
    if "." in code:
        code = code.split(".")[0]
    return code.zfill(6)


def to_tushare_code(code: str) -> str:
    """纯数字代码 → Tushare格式 (600519.SH / 000001.SZ / 832000.BJ)"""
    code = normalize_code(code)
    if code.startswith(("6", "9")):
        return f"{code}.SH"
    elif code.startswith("8"):
        return f"{code}.BJ"
    else:
        return f"{code}.SZ"


def get_prefix(code: str) -> str:
    """6位代码 → 市场前缀"""
    code = normalize_code(code)
    if code.startswith(("6", "9")):
        return "sh"
    elif code.startswith("8"):
        return "bj"
    return "sz"


# ═══════════════════════════════════════════════════════════════
# 数据源1: mootdx (TCP 7709，不封IP)
# ═══════════════════════════════════════════════════════════════

class MootdxSource:
    """通达信 TCP 行情数据源"""

    def __init__(self):
        self._client = None

    @property
    def client(self):
        if self._client is None:
            from mootdx.quotes import Quotes
            for ip, port in _TDX_SERVERS:
                if _probe(ip, port):
                    self._client = Quotes.factory(market='std', server=(ip, port))
                    logger.info(f"mootdx 连接成功: {ip}:{port}")
                    break
            if self._client is None:
                try:
                    self._client = Quotes.factory(market='std', bestip=True)
                except Exception:
                    try:
                        self._client = Quotes.factory(market='std')
                    except Exception as e:
                        raise RuntimeError(f"mootdx 所有服务器不可达: {e}")
        return self._client

    def is_available(self) -> bool:
        try:
            _ = self.client
            return True
        except Exception:
            return False

    def get_daily(self, code: str, start_date: str = None, end_date: str = None, count: int = 250) -> pd.DataFrame:
        """获取个股日K线"""
        raw_code = normalize_code(code)
        try:
            bars = self.client.bars(symbol=raw_code, frequency=9, offset=count)
            # mootdx 0.11.x 可能返回 DataFrame 或 list
            if bars is None:
                return pd.DataFrame()
            if isinstance(bars, pd.DataFrame):
                if bars.empty:
                    return pd.DataFrame()
                df = bars.copy()
            elif isinstance(bars, list):
                if len(bars) == 0:
                    return pd.DataFrame()
                df = pd.DataFrame(bars)
            else:
                return pd.DataFrame()

            df = df.rename(columns={"vol": "volume", "datetime": "date"})
            df["date"] = pd.to_datetime(df["date"])
            df = df.set_index("date").sort_index()
            df = df[["open", "high", "low", "close", "volume", "amount"]]
            df = df.astype({c: float for c in df.columns})

            if start_date:
                df = df[df.index >= pd.Timestamp(start_date)]
            if end_date:
                df = df[df.index <= pd.Timestamp(end_date)]
            return df
        except Exception as e:
            logger.warning(f"mootdx 获取K线失败 {code}: {e}")
            return pd.DataFrame()

    def get_minute(self, code: str, freq: int = 0, count: int = 240) -> pd.DataFrame:
        """获取分钟K线。freq: 0=5min, 1=15min, 2=30min, 3=60min, 8=1min"""
        raw_code = normalize_code(code)
        try:
            bars = self.client.bars(symbol=raw_code, frequency=freq, offset=count)
            if not bars:
                return pd.DataFrame()
            df = pd.DataFrame(bars)
            df = df.rename(columns={"vol": "volume", "datetime": "date"})
            df["date"] = pd.to_datetime(df["date"])
            return df.set_index("date").sort_index()
        except Exception as e:
            logger.warning(f"mootdx 获取分钟K线失败 {code}: {e}")
            return pd.DataFrame()


# ═══════════════════════════════════════════════════════════════
# 数据源2: Tushare (HTTP，已配置token)
# ═══════════════════════════════════════════════════════════════

class TushareSource:
    """Tushare HTTP 行情+资金流数据源"""

    def __init__(self, token: str = None):
        self._token = token or get_tushare_token()
        self._api = None

    @property
    def api(self):
        if self._api is None and self._token:
            import tushare as ts
            ts.set_token(self._token)
            self._api = ts.pro_api()
        return self._api

    def is_available(self) -> bool:
        return self._token is not None and len(self._token) > 10

    def get_daily(self, code: str, start_date: str = None, end_date: str = None, count: int = 250) -> pd.DataFrame:
        """获取个股日K线（含复权）"""
        if not self.is_available():
            return pd.DataFrame()
        ts_code = to_tushare_code(code)
        if end_date is None:
            end_date = datetime.now().strftime("%Y%m%d")
        if start_date is None:
            start_date = (datetime.now() - timedelta(days=count * 2)).strftime("%Y%m%d")
        try:
            df = self.api.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
            if df is None or df.empty:
                return pd.DataFrame()
            df = df.rename(columns={
                "trade_date": "date", "ts_code": "code",
                "pre_close": "prev_close", "pct_chg": "change_pct",
            })
            df["date"] = pd.to_datetime(df["date"])
            df = df.set_index("date").sort_index()
            vol_col = "vol" if "vol" in df.columns else "volume"
            if vol_col in df.columns:
                df["volume"] = df[vol_col].astype(float)
            for c in ["open", "high", "low", "close", "amount"]:
                if c in df.columns:
                    df[c] = df[c].astype(float)
            cols = [c for c in ["open", "high", "low", "close", "volume", "amount"] if c in df.columns]
            return df[cols]
        except Exception as e:
            logger.warning(f"Tushare 获取K线失败 {code}: {e}")
            return pd.DataFrame()

    def get_index_daily(self, code: str, start_date: str = None, end_date: str = None) -> pd.DataFrame:
        """获取指数日K线"""
        if not self.is_available():
            return pd.DataFrame()
        # 指数代码映射
        index_map = {
            "000001": "000001.SH", "000300": "000300.SH", "000016": "000016.SH",
            "399001": "399001.SZ", "399006": "399006.SZ", "399005": "399005.SZ",
            "000688": "000688.SH", "000905": "000905.SH",
        }
        pure = normalize_code(code)
        ts_code = index_map.get(pure)
        if ts_code is None:
            # 不在映射表中的指数：000/9开头→SH, 399开头→SZ
            if pure.startswith("000") or pure.startswith("9"):
                ts_code = f"{pure}.SH"
            elif pure.startswith("399") or pure.startswith("3"):
                ts_code = f"{pure}.SZ"
            else:
                ts_code = f"{pure}.SH"
        if end_date is None:
            end_date = datetime.now().strftime("%Y%m%d")
        if start_date is None:
            start_date = (datetime.now() - timedelta(days=500)).strftime("%Y%m%d")
        try:
            df = self.api.index_daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
            if df is None or df.empty:
                return pd.DataFrame()
            df = df.rename(columns={"trade_date": "date", "pct_chg": "change_pct"})
            df["date"] = pd.to_datetime(df["date"])
            df = df.set_index("date").sort_index()
            vol_col = "vol" if "vol" in df.columns else "volume"
            if vol_col in df.columns:
                df["volume"] = df[vol_col].astype(float)
            for c in ["open", "high", "low", "close", "amount"]:
                if c in df.columns:
                    df[c] = df[c].astype(float)
            cols = [c for c in ["open", "high", "low", "close", "volume", "amount"] if c in df.columns]
            return df[cols]
        except Exception as e:
            logger.warning(f"Tushare 获取指数K线失败 {code}: {e}")
            return pd.DataFrame()

    def get_moneyflow(self, code: str, start_date: str = None, end_date: str = None) -> pd.DataFrame:
        """获取个股资金流数据"""
        if not self.is_available():
            return pd.DataFrame()
        ts_code = to_tushare_code(code)
        if end_date is None:
            end_date = datetime.now().strftime("%Y%m%d")
        if start_date is None:
            start_date = (datetime.now() - timedelta(days=180)).strftime("%Y%m%d")
        try:
            df = self.api.moneyflow(ts_code=ts_code, start_date=start_date, end_date=end_date)
            if df is None or df.empty:
                return pd.DataFrame()
            df = df.rename(columns={"trade_date": "date"})
            df["date"] = pd.to_datetime(df["date"])
            df = df.set_index("date").sort_index()
            # 数值列转换
            for col in df.columns:
                if col != "ts_code":
                    df[col] = pd.to_numeric(df[col], errors="coerce")
            return df
        except Exception as e:
            logger.warning(f"Tushare 获取资金流失败 {code}: {e}")
            return pd.DataFrame()

    def get_stock_basic(self, code: str) -> dict:
        """获取个股基本信息（流通市值、总市值等）"""
        if not self.is_available():
            return {}
        ts_code = to_tushare_code(code)
        try:
            # 用 daily_basic 获取最近交易日的指标
            end_date = datetime.now().strftime("%Y%m%d")
            start_date = (datetime.now() - timedelta(days=10)).strftime("%Y%m%d")
            df = self.api.daily_basic(
                ts_code=ts_code, start_date=start_date, end_date=end_date,
                fields="ts_code,trade_date,circ_mv,total_mv,turnover_rate,pe,pb,volume_ratio"
            )
            if df is None or df.empty:
                return {}
            latest = df.iloc[-1].to_dict()
            return {
                "float_mv": float(latest.get("circ_mv", 0) or 0),     # 流通市值(万元)
                "total_mv": float(latest.get("total_mv", 0) or 0),    # 总市值(万元)
                "turnover_rate": float(latest.get("turnover_rate", 0) or 0),
                "pe": float(latest.get("pe", 0) or 0),
                "pb": float(latest.get("pb", 0) or 0),
            }
        except Exception as e:
            logger.warning(f"Tushare 获取基本信息失败 {code}: {e}")
            return {}


# ═══════════════════════════════════════════════════════════════
# 数据源3: 腾讯财经 (HTTP，实时估值，不封IP)
# ═══════════════════════════════════════════════════════════════

class TencentSource:
    """腾讯财经实时行情数据源"""

    @staticmethod
    def get_realtime(codes: List[str]) -> Dict[str, dict]:
        """批量获取实时行情（PE/PB/市值/涨跌停等）"""
        prefixed = []
        for c in codes:
            c = normalize_code(c)
            if c.startswith(("6", "9")):
                prefixed.append(f"sh{c}")
            elif c.startswith("8"):
                prefixed.append(f"bj{c}")
            else:
                prefixed.append(f"sz{c}")

        import urllib.request
        url = "https://qt.gtimg.cn/q=" + ",".join(prefixed)
        req = urllib.request.Request(url)
        req.add_header("User-Agent", "Mozilla/5.0")
        try:
            resp = urllib.request.urlopen(req, timeout=10)
            data = resp.read().decode("gbk")
        except Exception as e:
            logger.warning(f"腾讯行情请求失败: {e}")
            return {}

        result = {}
        for line in data.strip().split(";"):
            if not line.strip() or "=" not in line or '"' not in line:
                continue
            key = line.split("=")[0].split("_")[-1]
            vals = line.split('"')[1].split("~")
            if len(vals) < 53:
                continue
            code = key[2:]
            result[code] = {
                "name": vals[1],
                "price": float(vals[3]) if vals[3] else 0,
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
            }
        return result


# ═══════════════════════════════════════════════════════════════
# 数据源4: 东财 (仅用于独有数据)
# ═══════════════════════════════════════════════════════════════

class EastmoneySource:
    """东财数据中心（已内置限流）"""

    def __init__(self):
        self._session = None

    @property
    def session(self):
        if self._session is None:
            s = requests.Session()
            s.headers.update({"User-Agent": UA})
            try:
                from requests.adapters import HTTPAdapter
                from urllib3.util.retry import Retry
                adapter = HTTPAdapter(max_retries=Retry(
                    total=3, connect=3, backoff_factor=0.6,
                    status_forcelist=[429, 500, 502, 503, 504],
                    allowed_methods=["GET"]))
                s.mount("https://", adapter)
                s.mount("http://", adapter)
            except Exception:
                pass
            self._session = s
        return self._session

    def _throttle(self):
        """东财限流"""
        global _em_last_call
        wait = EM_MIN_INTERVAL - (time.time() - _em_last_call[0])
        if wait > 0:
            time.sleep(wait + random.uniform(0.1, 0.5))
        _em_last_call[0] = time.time()

    def _get(self, url: str, params: dict = None, headers: dict = None, timeout: int = 15):
        self._throttle()
        return self.session.get(url, params=params, headers=headers, timeout=timeout)

    def get_datacenter(self, report_name: str, filter_str: str = "", page_size: int = 50,
                       sort_columns: str = "", sort_types: str = "-1") -> List[dict]:
        """东财数据中心通用查询"""
        url = "https://datacenter-web.eastmoney.com/api/data/v1/get"
        params = {
            "reportName": report_name, "columns": "ALL",
            "filter": filter_str, "pageNumber": "1", "pageSize": str(page_size),
            "sortColumns": sort_columns, "sortTypes": sort_types,
            "source": "WEB", "client": "WEB",
        }
        try:
            r = self._get(url, params=params)
            d = r.json()
            if d.get("result") and d["result"].get("data"):
                return d["result"]["data"]
        except Exception as e:
            logger.warning(f"东财数据中心查询失败: {e}")
        return []

    def get_sector_ranking(self, top_n: int = 30) -> List[dict]:
        """获取行业板块排名"""
        url = "https://push2.eastmoney.com/api/qt/clist/get"
        params = {
            "pn": "1", "pz": str(min(top_n, 100)), "po": "1", "np": "1",
            "fltt": "2", "invt": "2", "fs": "m:90+t:2",
            "fields": "f2,f3,f4,f12,f13,f14,f104,f105,f128,f140",
        }
        try:
            r = self._get(url, params=params, headers={"User-Agent": UA})
            items = r.json().get("data", {}).get("diff", [])
            if isinstance(items, dict):
                items = list(items.values())
            rows = []
            for i, it in enumerate(items):
                rows.append({
                    "rank": i + 1,
                    "code": it.get("f12", ""),
                    "name": it.get("f14", ""),
                    "change_pct": it.get("f3", 0),
                    "up_count": it.get("f104", 0),
                    "down_count": it.get("f105", 0),
                    "leader": it.get("f140", ""),
                })
            return rows
        except Exception as e:
            logger.warning(f"东财行业排名获取失败: {e}")
            return []


# ═══════════════════════════════════════════════════════════════
# 统一数据接口
# ═══════════════════════════════════════════════════════════════

class VpaDataAdapter:
    """
    量价分析统一数据适配器。
    数据优先级：Tushare(付费)→ mootdx(免费)→ 腾讯(实时)
    """

    def __init__(self):
        self.mootdx = MootdxSource()
        self.tushare = TushareSource()
        self.tencent = TencentSource()
        self.eastmoney = EastmoneySource()
        self._source_status = {}

    @staticmethod
    def _is_index_code(code: str) -> bool:
        """判断是否为指数代码"""
        pure = normalize_code(code)
        return any(pure.startswith(p) for p in ("000", "399", "899"))

    def _check_sources(self):
        """检测各数据源可用性"""
        self._source_status = {
            "mootdx": self.mootdx.is_available(),
            "tushare": self.tushare.is_available(),
            "tencent": True,
        }
        logger.info(f"数据源状态: {self._source_status}")

    def get_ohlcv(self, code: str, period: str = "daily", lookback: int = 120,
                  start_date: str = None, end_date: str = None) -> pd.DataFrame:
        """
        获取标准化 OHLCV 数据，自动降级。
        Tushare(付费)→ mootdx(免费)→ 腾讯(实时)
        """
        # 分钟K线仅 mootdx 支持
        if period != "daily":
            freq_map = {"5min": 0, "15min": 1, "30min": 2, "60min": 3, "1min": 8}
            freq = freq_map.get(period, 0)
            count = {"5min": 48, "15min": 16, "30min": 8, "60min": 4, "1min": 240}.get(period, 48)
            df = self.mootdx.get_minute(code, freq=freq, count=count * 20)
            if not df.empty:
                logger.info(f"[{code}] mootdx 分钟K线获取成功, freq={freq}")
                return df
            logger.warning(f"[{code}] mootdx 分钟K线为空")
            return pd.DataFrame()

        # ── 日K线：Tushare(付费优先) → mootdx(免费备选) → 腾讯 ──

        # Level 1: Tushare (付费会员，数据最准)
        if self.tushare.is_available():
            if self._is_index_code(code):
                # 指数用 index_daily()
                df = self.tushare.get_index_daily(code, start_date=start_date, end_date=end_date)
            else:
                # 个股用 daily()
                df = self.tushare.get_daily(code, start_date=start_date, end_date=end_date, count=lookback)

            if df is not None and not df.empty and len(df) >= 20:
                logger.info(f"[{code}] Tushare K线获取成功({'指数' if self._is_index_code(code) else '个股'}), {len(df)} 条")
                return df

        # Level 2: mootdx (免费TCP，不封IP)
        df = self.mootdx.get_daily(code, start_date=start_date, end_date=end_date, count=lookback)
        if not df.empty and len(df) >= 20:
            # ⚠️ mootdx 对指数返回缩放值，需要修正
            if self._is_index_code(code):
                df = self._fix_mootdx_index_scale(code, df)
            logger.info(f"[{code}] mootdx 日K线获取成功(备选), {len(df)} 条")
            return df

        # Level 3: 腾讯（仅实时，没有历史K线）
        logger.warning(f"[{code}] 所有K线数据源均失败")
        return pd.DataFrame()

    def _fix_mootdx_index_scale(self, code: str, df: pd.DataFrame) -> pd.DataFrame:
        """修复 mootdx 指数数据的缩放问题（通过与腾讯实时行情比对）"""
        try:
            info = self.tencent.get_realtime([code])
            pure = normalize_code(code)
            real_price = info.get(pure, {}).get("price", 0) if info else 0
        except Exception:
            real_price = 0

        if real_price <= 0 or df is None or df.empty:
            return df

        latest_close = float(df["close"].iloc[-1]) if "close" in df.columns else 0
        if latest_close <= 0:
            return df

        scale = real_price / latest_close
        if abs(scale - 1.0) > 0.02:
            logger.info(f"[{code}] mootdx 指数缩放修正 ×{scale:.1f}")
            for col in ["open", "high", "low", "close"]:
                if col in df.columns:
                    df[col] = df[col] * scale
            if "amount" in df.columns:
                df["amount"] = df["amount"] * scale
        return df

    def get_moneyflow(self, code: str, lookback_days: int = 60) -> pd.DataFrame:
        """获取资金流数据"""
        if not self.tushare.is_available():
            logger.warning(f"[{code}] Tushare 不可用，无法获取资金流")
            return pd.DataFrame()

        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=lookback_days + 30)).strftime("%Y%m%d")
        df = self.tushare.get_moneyflow(code, start_date=start_date, end_date=end_date)
        if not df.empty:
            logger.info(f"[{code}] Tushare 资金流获取成功, {len(df)} 条")
        return df

    def get_stock_basic(self, code: str) -> dict:
        """获取个股基本信息"""
        info = {}
        if self.tushare.is_available():
            info.update(self.tushare.get_stock_basic(code))

        # 腾讯作为补充
        try:
            tq = self.tencent.get_realtime([code])
            if code in tq:
                t = tq[code]
                info.update({
                    "name": t.get("name", ""),
                    "price": t.get("price", 0),
                    "pe_ttm": t.get("pe_ttm", 0),
                    "pb": t.get("pb", 0),
                    "mcap_yi": t.get("mcap_yi", 0),
                    "float_mcap_yi": t.get("float_mcap_yi", 0),
                })
        except Exception:
            pass
        return info

    def get_realtime(self, codes: List[str]) -> Dict[str, dict]:
        """批量获取实时行情"""
        return self.tencent.get_realtime(codes)

    def get_sector_data(self, top_n: int = 30) -> List[dict]:
        """获取行业板块排名"""
        return self.eastmoney.get_sector_ranking(top_n)


# ═══════════════════════════════════════════════════════════════
# 模块级便捷函数
# ═══════════════════════════════════════════════════════════════

_adapter = None

def get_adapter() -> VpaDataAdapter:
    global _adapter
    if _adapter is None:
        _adapter = VpaDataAdapter()
    return _adapter


def fetch_ohlcv(code: str, period: str = "daily", lookback: int = 120) -> pd.DataFrame:
    return get_adapter().get_ohlcv(code, period=period, lookback=lookback)


def fetch_moneyflow(code: str, lookback_days: int = 60) -> pd.DataFrame:
    return get_adapter().get_moneyflow(code, lookback_days=lookback_days)
