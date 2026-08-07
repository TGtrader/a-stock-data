"""
TG-trading-sys 数据缓存层
=========================
从各数据源拉取 → 标准化 → 存入 SQLite。
后续查询优先命中本地缓存，减少网络请求。

支持：
  - K线数据缓存（日线/分钟线）
  - 财务三表缓存（资产负债表/利润表/现金流量表）
  - 资金流缓存
  - 研报EPS预测缓存
  - 股票基本信息缓存
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
import pandas as pd
import numpy as np

from ..core.database import Database
from ..core.config import Config

logger = logging.getLogger("tg.data.cache")


class DataCache:
    """
    统一数据缓存层。
    从各数据源获取数据并存入 SQLite，后续查询命中缓存。
    """

    def __init__(self):
        self.db = Database.get_instance()

    # ═══════════════════════════════════════════════════════════════
    # K线缓存
    # ═══════════════════════════════════════════════════════════════

    def get_kline(
        self, code: str, start_date: str = None, end_date: str = None,
        lookback: int = 250, force_refresh: bool = False
    ) -> pd.DataFrame:
        """
        获取K线数据（缓存优先，Tushare 付费会员首选）。

        Args:
            code: 股票/指数代码（6位数字）
            start_date: 起始日期 YYYY-MM-DD
            end_date: 截止日期 YYYY-MM-DD
            lookback: 回溯天数
            force_refresh: 强制重新拉取
        """
        # 如果是强制刷新，清除旧缓存
        if force_refresh:
            self.db.execute("DELETE FROM daily_kline WHERE code=?", (code,))

        if not force_refresh:
            # 从缓存获取
            cached = self._get_kline_from_cache(code, start_date, end_date)
            if cached is not None and len(cached) >= 20:
                # 检查缓存来源：如果是 mootdx 且该代码是指数，优先用 Tushare 重取
                source_row = self.db.fetchone(
                    "SELECT source FROM daily_kline WHERE code=? LIMIT 1", (code,)
                )
                cache_source = source_row["source"] if source_row else ""
                if cache_source == "mootdx" and self._is_index_code(code):
                    logger.info(f"[{code}] 缓存来自 mootdx(指数数据可能不准)，尝试 Tushare 重取")
                    df = self._fetch_tushare_daily(code, lookback)
                    if df is not None and len(df) >= 20:
                        self._save_kline_to_cache(code, df, source="tushare")
                        logger.info(f"[{code}] ✓ 已用 Tushare 替换 mootdx 指数缓存")
                        if start_date:
                            df = df[df.index >= pd.Timestamp(start_date)]
                        if end_date:
                            df = df[df.index <= pd.Timestamp(end_date)]
                        return df

                logger.debug(f"[{code}] K线缓存命中({cache_source}), {len(cached)} 条")
                return cached

        # 从数据源拉取
        df = self._fetch_kline_from_source(code, lookback=lookback)
        if df is not None and not df.empty:
            self._save_kline_to_cache(code, df)
            if start_date:
                df = df[df.index >= pd.Timestamp(start_date)]
            if end_date:
                df = df[df.index <= pd.Timestamp(end_date)]
        return df if df is not None else pd.DataFrame()

    def _get_kline_from_cache(
        self, code: str, start_date: str = None, end_date: str = None
    ) -> Optional[pd.DataFrame]:
        """从 SQLite 读取缓存的K线"""
        where = "code = ?"
        params: List[Any] = [code]
        if start_date:
            where += " AND date >= ?"
            params.append(start_date)
        if end_date:
            where += " AND date <= ?"
            params.append(end_date)
        where += " ORDER BY date ASC"

        rows = self.db.fetchall(
            f"SELECT date, open, high, low, close, volume, amount FROM daily_kline WHERE {where}",
            tuple(params)
        )
        if not rows:
            return None

        df = pd.DataFrame(
            [dict(r) for r in rows],
            columns=["date", "open", "high", "low", "close", "volume", "amount"]
        )
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index()
        # 列类型转换
        for c in ["open", "high", "low", "close", "volume", "amount"]:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")
        return df

    # ── 已知指数代码（沪市深市主板代码 000001-004999 与指数代码冲突）──
    _KNOWN_INDEX_CODES = frozenset({
        "000001",  # 上证指数
        "000016",  # 上证50
        "000300",  # 沪深300
        "000688",  # 科创50
        "000852",  # 中证1000
        "000905",  # 中证500
        "000906",  # 中证800
        "000922",  # 中证红利
        "399001",  # 深证成指
        "399005",  # 创业板指
        "399006",  # 创业板指
        "399330",  # 深证100
        "399673",  # 创业板50
        "399905",  # 中证500(深)
        "399932",  # 中证消费
        "399967",  # 中证军工
        "399975",  # 证券公司
        "899001",  # 中证系列
        "899050",  # 中证全指
    })

    def _is_index_code(self, code: str) -> bool:
        """
        判断是否为指数代码。

        注意：深市主板代码 000001-004999 与上证指数系列 000xxx 冲突，
        因此采用已知指数白名单 + 前缀组合策略：
        1. 白名单精确匹配
        2. 399xxx 深证系列
        3. 899xxx 中证系列
        4. 000xxx 中不在深市股票范围 (000001-004999, 002000-002999, 003000-003999) 的可能是指数
        """
        pure = code.zfill(6)

        # 1) 已知指数白名单
        if pure in self._KNOWN_INDEX_CODES:
            return True

        # 2) 399xxx 深证指数系列（深市创业板 300xxx、中小板 002xxx，399不冲突）
        if pure.startswith("399"):
            return True

        # 3) 899xxx 中证系列
        if pure.startswith("899"):
            return True

        # 4) 000xxx 中的指数：排除深市股票范围 000001–004999
        #    深市还有 002000-002999, 003000-003999
        if pure.startswith("000"):
            num = int(pure)
            # 000001-004999 是深市股票 → 不是指数
            # 000016 (上证50), 000300 (沪深300) 等已在白名单中处理
            if 1 <= num <= 4999:
                return False
            # 其他 000xxx 视为潜在指数（如 000688 科创50、000852 中证1000）
            return True

        return False

    def _fetch_kline_from_source(self, code: str, lookback: int = 250) -> pd.DataFrame:
        """
        从数据源获取K线（三级降级：Tushare(付费)→ mootdx(免费)→ 腾讯）
        付费会员优先使用 Tushare，数据质量最高。
        每条数据入库前用腾讯实时价交叉校验，防止单位错误。
        """
        # ── Level 1: Tushare (付费会员，数据最准) ──
        df = self._fetch_tushare_daily(code, lookback)
        if df is not None and len(df) >= 20:
            if self._validate_kline_price(code, df):
                logger.info(f"[{code}] Tushare K线获取成功, {len(df)} 条")
                return df
            else:
                logger.warning(f"[{code}] Tushare K线价格校验失败，降级到 mootdx")

        # ── Level 2: mootdx (TCP 免费，不封IP，但指数数据有缩放问题) ──
        df = self._fetch_mootdx_daily(code, lookback)
        if df is not None and len(df) >= 20:
            if self._validate_kline_price(code, df):
                logger.info(f"[{code}] mootdx K线获取成功(备选), {len(df)} 条")
                return df
            else:
                logger.warning(f"[{code}] mootdx K线价格校验失败")

        # ── Level 3: 腾讯（仅实时，无法获取历史K线）──
        logger.warning(f"[{code}] 所有K线数据源均失败")
        return pd.DataFrame()

    def _validate_kline_price(self, code: str, df: pd.DataFrame, max_ratio: float = 3.0) -> bool:
        """
        用腾讯实时价交叉校验K线数据的最新收盘价。
        如果偏差超过 max_ratio 倍，判定为数据异常（如单位错误）。

        Returns:
            True = 价格合理, False = 价格异常
        """
        try:
            info = self._fetch_tencent_basic(code)
            real_price = info.get("price", 0) if info else 0
        except Exception:
            real_price = 0

        if real_price <= 0:
            # 无法获取实时价，跳过校验（非致命）
            return True

        latest_close = float(df["close"].iloc[-1])
        if latest_close <= 0:
            return False

        ratio = max(real_price, latest_close) / min(real_price, latest_close)
        if ratio > max_ratio:
            logger.warning(
                f"[{code}] 价格校验失败: K线收盘={latest_close:.2f} vs 腾讯现价={real_price:.2f} "
                f"(偏差 {ratio:.1f}x > {max_ratio:.1f}x)"
            )
            return False

        return True

    def _fetch_mootdx_daily(self, code: str, lookback: int = 250) -> Optional[pd.DataFrame]:
        """通过通达信 TCP 获取日K线（免费备选，指数数据可能缩放）"""
        try:
            from mootdx.quotes import Quotes
            import socket

            servers = [
                ('119.97.185.59', 7709), ('124.70.133.119', 7709),
                ('116.205.183.150', 7709), ('123.60.73.44', 7709),
                ('116.205.163.254', 7709), ('121.36.225.169', 7709),
                ('123.60.70.228', 7709), ('124.71.9.153', 7709),
                ('110.41.147.114', 7709), ('124.71.187.122', 7709),
            ]

            client = None
            for ip, port in servers:
                try:
                    with socket.create_connection((ip, port), timeout=2.0):
                        client = Quotes.factory(market='std', server=(ip, port))
                        break
                except Exception:
                    continue

            if client is None:
                try:
                    client = Quotes.factory(market='std', bestip=True)
                except Exception:
                    try:
                        client = Quotes.factory(market='std')
                    except Exception as e:
                        logger.warning(f"mootdx 连接失败: {e}")
                        return None

            bars = client.bars(symbol=code.zfill(6), frequency=9, offset=lookback)
            if bars is None:
                return None

            if isinstance(bars, list):
                if len(bars) == 0:
                    return None
                df = pd.DataFrame(bars)
            elif isinstance(bars, pd.DataFrame):
                if bars.empty:
                    return None
                df = bars.copy()
            else:
                return None

            df = df.rename(columns={"vol": "volume", "datetime": "date"})
            df["date"] = pd.to_datetime(df["date"])
            df = df.set_index("date").sort_index()
            cols = [c for c in ["open", "high", "low", "close", "volume", "amount"] if c in df.columns]
            if cols:
                df = df[cols]
            df = df.astype({c: float for c in df.columns})

            # ⚠️ mootdx 对指数返回缩放值（除以100），需要还原
            if self._is_index_code(code):
                df = self._fix_mootdx_index_scale(code, df)

            return df
        except ImportError:
            logger.warning("mootdx 未安装")
            return None
        except Exception as e:
            logger.warning(f"mootdx 获取K线失败 {code}: {e}")
            return None

    def _fix_mootdx_index_scale(self, code: str, df: pd.DataFrame) -> pd.DataFrame:
        """
        修复 mootdx 指数数据的缩放问题。
        mootdx 对部分指数返回的值是真实值÷某个因子（通常÷100或÷1000）。
        通过与腾讯实时行情比对来校准。
        """
        try:
            info = self._fetch_tencent_basic(code)
            real_price = info.get("price", 0) if info else 0
        except Exception:
            real_price = 0

        if real_price <= 0 or df is None or df.empty:
            return df

        latest_close = float(df["close"].iloc[-1])
        if latest_close <= 0:
            return df

        scale = real_price / latest_close

        # 仅当缩放因子明显偏离1时才修正（防止误判）
        if abs(scale - 1.0) > 0.02:
            logger.info(f"[{code}] mootdx 指数数据缩放修正 ×{scale:.1f} "
                        f"(原始{latest_close:.2f}→修正{real_price:.2f})")
            for col in ["open", "high", "low", "close"]:
                if col in df.columns:
                    df[col] = df[col] * scale
            if "amount" in df.columns:
                df["amount"] = df["amount"] * scale

        return df

    def _fetch_tushare_daily(self, code: str, lookback: int = 250) -> Optional[pd.DataFrame]:
        """
        通过 Tushare 获取日K线（付费会员首选）。

        对指数使用 index_daily()，对个股使用 daily()。
        Tushare Pro 付费会员拥有完整的历史数据和更高的访问频率。
        """
        token = Config.get_tushare_token()
        if not token:
            logger.warning("Tushare token 未配置")
            return None

        try:
            import tushare as ts
            ts.set_token(token)
            api = ts.pro_api()

            pure_code = code.zfill(6)
            is_index = self._is_index_code(code)

            end_date = datetime.now().strftime("%Y%m%d")
            start_date = (datetime.now() - timedelta(days=lookback * 2)).strftime("%Y%m%d")

            if is_index:
                # ── 指数：使用 index_daily() ──
                # 指数代码映射到 ts_code
                ts_code = self._to_ts_index_code(pure_code)
                logger.debug(f"[{code}] Tushare index_daily: {ts_code}")

                try:
                    df = api.index_daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
                except Exception:
                    # 某些指数可能不支持 index_daily，fallback 到 daily
                    df = api.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)

                if df is not None and not df.empty:
                    df = df.rename(columns={
                        "trade_date": "date",
                        "pct_chg": "change_pct",
                    })
                    # index_daily 的成交量字段可能是 vol
                    if "vol" in df.columns and "volume" not in df.columns:
                        df = df.rename(columns={"vol": "volume"})
            else:
                # ── 个股：使用 daily() ──
                if pure_code.startswith(("6", "9")):
                    ts_code = f"{pure_code}.SH"
                elif pure_code.startswith("8"):
                    ts_code = f"{pure_code}.BJ"
                else:
                    ts_code = f"{pure_code}.SZ"

                logger.debug(f"[{code}] Tushare daily: {ts_code}")
                df = api.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
                if df is not None and not df.empty:
                    df = df.rename(columns={"trade_date": "date", "vol": "volume"})

            if df is None or df.empty:
                return None

            df["date"] = pd.to_datetime(df["date"])
            df = df.set_index("date").sort_index()
            for c in ["open", "high", "low", "close", "volume", "amount"]:
                if c in df.columns:
                    df[c] = pd.to_numeric(df[c], errors="coerce")
            cols = [c for c in ["open", "high", "low", "close", "volume", "amount"] if c in df.columns]
            return df[cols] if cols else None

        except ImportError:
            logger.warning("tushare 未安装")
            return None
        except Exception as e:
            logger.warning(f"Tushare 获取K线失败 {code}: {e}")
            return None

    def _to_ts_index_code(self, pure_code: str) -> str:
        """6位指数代码 → Tushare ts_code 格式"""
        if pure_code.startswith("000") or pure_code.startswith("9"):
            return f"{pure_code}.SH"
        elif pure_code.startswith("399") or pure_code.startswith("3"):
            return f"{pure_code}.SZ"
        else:
            return f"{pure_code}.SH"

    def _save_kline_to_cache(self, code: str, df: pd.DataFrame, source: str = ""):
        """将K线数据存入 SQLite"""
        if df is None or df.empty:
            return

        # 自动判断来源
        if not source:
            # 检测 Tushare token 是否可用 → 标记为 tushare，否则标记为 mootdx
            from ..core.config import Config
            token = Config.get_tushare_token()
            source = "tushare" if token else "mootdx"

        rows = []
        for idx, row in df.iterrows():
            rows.append({
                "date": idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)[:10],
                "open": float(row.get("open", 0) or 0),
                "high": float(row.get("high", 0) or 0),
                "low": float(row.get("low", 0) or 0),
                "close": float(row.get("close", 0) or 0),
                "volume": float(row.get("volume", 0) or 0),
                "amount": float(row.get("amount", 0) or 0),
            })

        self.db.upsert_kline(code, rows, source=source)
        logger.info(f"[{code}] K线缓存已更新({source}), {len(rows)} 条")

    # ═══════════════════════════════════════════════════════════════
    # 财务数据缓存
    # ═══════════════════════════════════════════════════════════════

    def get_financials(
        self, code: str, report_type: str = "lrb", force_refresh: bool = False
    ) -> List[dict]:
        """
        获取财务三表数据（缓存优先）。

        Args:
            code: 股票代码
            report_type: lrb(利润表) / fzb(资产负债表) / llb(现金流量表)
            force_refresh: 强制刷新

        Returns:
            按报告期倒序排列的财报记录列表
        """
        if not force_refresh:
            rows = self.db.fetchall(
                """SELECT report_date, data_json FROM financials
                   WHERE code=? AND report_type=? ORDER BY report_date DESC""",
                (code, report_type)
            )
            if rows:
                results = []
                for r in rows:
                    data = json.loads(r["data_json"])
                    data["report_date"] = r["report_date"]
                    results.append(data)
                return results

        # 从新浪拉取
        data = self._fetch_sina_financials(code, report_type)
        if data:
            self._save_financials_to_cache(code, report_type, data)
        return data

    def _fetch_sina_financials(self, code: str, report_type: str) -> List[dict]:
        """
        从新浪财经获取财务三表数据。
        使用 CompanyFinanceService.getFinanceReport2022 API。
        """
        import urllib.request
        import json as _json

        pure_code = code.zfill(6)
        if pure_code.startswith(("6", "9")):
            prefix = "sh"
        elif pure_code.startswith("8"):
            prefix = "bj"
        else:
            prefix = "sz"

        paper_code = f"{prefix}{pure_code}"
        url = "https://quotes.sina.cn/cn/api/openapi.php/CompanyFinanceService.getFinanceReport2022"
        params = {
            "paperCode": paper_code,
            "source": report_type,
            "type": "0",
            "page": "1",
            "num": "8",
        }
        query_string = "&".join(f"{k}={v}" for k, v in params.items())
        full_url = f"{url}?{query_string}"

        req = urllib.request.Request(full_url)
        req.add_header("User-Agent", "Mozilla/5.0")
        req.add_header("Referer", "https://finance.sina.com.cn/")

        try:
            resp = urllib.request.urlopen(req, timeout=15)
            text = resp.read().decode("utf-8")
            data = _json.loads(text)
        except Exception as e:
            logger.warning(f"新浪财报获取失败 {code}/{report_type}: {e}")
            return []

        # 解析 report_list
        report_list = data.get("result", {}).get("data", {}).get("report_list", {}) or {}
        if not report_list:
            return []

        # ── 单位归一化：新浪API返回原始值为"元"，统一转为"万元" ──
        # 阈值: 原始值 > 10,000 (1万) 视为货币值 → /10000 得到万元
        # 原始值 ≤ 10,000 视为每股/比率值 → 保持不变
        # 同比值(百分比)不转换
        def _normalize_sina_value(raw_val: str) -> str:
            """将新浪原始值(元)归一化到万元"""
            try:
                v = float(str(raw_val).replace(",", ""))
                if abs(v) > 10_000:
                    return str(round(v / 10_000, 4))
                return str(v)
            except (ValueError, TypeError):
                return str(raw_val)

        results = []
        for period in sorted(report_list.keys(), reverse=True):
            obj = report_list[period]
            rec = {"report_date": f"{period[:4]}-{period[4:6]}-{period[6:8]}"}
            for it in obj.get("data", []) or []:
                title = it.get("item_title", "")
                if not title or it.get("item_value") is None:
                    continue
                rec[title] = _normalize_sina_value(it.get("item_value"))
                tongbi = it.get("item_tongbi")
                if tongbi not in (None, ""):
                    rec[f"{title}_同比"] = tongbi
            results.append(rec)

        return results

    def _save_financials_to_cache(self, code: str, report_type: str, data: List[dict]):
        for record in data:
            report_date = record.get("report_date", "")
            if not report_date:
                continue
            # 保存时用 copy，避免污染调用方的原始 dict
            save_data = {k: v for k, v in record.items() if k != "report_date"}
            self.db.execute(
                """INSERT OR REPLACE INTO financials (code, report_date, report_type, data_json, updated_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (code, report_date, report_type,
                 json.dumps(save_data, ensure_ascii=False),
                 datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            )

    # ═══════════════════════════════════════════════════════════════
    # 股票基本信息
    # ═══════════════════════════════════════════════════════════════

    def get_stock_basic(self, code: str, force_refresh: bool = False,
                        use_cache_price: bool = True) -> Optional[dict]:
        """获取股票基本信息（优先缓存，必要时实时更新）。

        Args:
            code: 股票代码
            force_refresh: 强制从腾讯获取最新数据
            use_cache_price: True=优先使用缓存（当天内有效），False=每次拉腾讯实时价

        缓存策略：
        - 当天内的缓存 → 直接返回（价格/PE/PB/市值已入库）
        - 缓存过期或force_refresh → 腾讯实时行情更新
        """
        cached = None
        cache_fresh = False
        today = datetime.now().strftime("%Y-%m-%d")

        if not force_refresh:
            row = self.db.fetchone("SELECT * FROM stock_basic WHERE code=?", (code,))
            if row:
                cached = dict(row)
                # 检查缓存是否当天内（价格有效）
                updated = cached.get("updated_at", "")
                if updated and updated[:10] == today and cached.get("price", 0) > 0:
                    cache_fresh = True

        # 当天缓存有效 → 直接返回，不再走HTTP
        if cache_fresh and use_cache_price:
            return cached

        # 需要实时更新：腾讯行情
        live_info = self._fetch_tencent_basic(code)

        if live_info:
            if cached:
                result = {**cached, **live_info}
            else:
                result = live_info
            self._save_stock_basic(code, result)
            return result

        # 腾讯获取失败，回退缓存（即使过期也比没有强）
        if cached:
            return cached

        # 兜底：最后尝试腾讯
        info = self._fetch_tencent_basic(code)
        if info:
            self._save_stock_basic(code, info)
        return info

    def _save_stock_basic(self, code: str, info: dict):
        """保存股票基本信息到缓存（含实时行情字段）"""
        self.db.execute(
            """INSERT OR REPLACE INTO stock_basic
               (code, name, market, industry, industry_code, list_date,
                total_shares, float_shares, price, pe_ttm, pb, mcap_yi, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (code, info.get("name", code), info.get("market", ""),
             info.get("industry", ""), info.get("industry_code", ""),
             info.get("list_date", ""), info.get("total_shares", 0),
             info.get("float_shares", 0),
             info.get("price", 0), info.get("pe_ttm", 0),
             info.get("pb", 0), info.get("mcap_yi", 0),
             datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )

    def _fetch_tencent_basic(self, code: str) -> Optional[dict]:
        """从腾讯财经获取股票基本信息"""
        import urllib.request

        pure_code = code.zfill(6)
        if pure_code.startswith(("6", "9")):
            prefix = "sh"
        elif pure_code.startswith("8"):
            prefix = "bj"
        else:
            prefix = "sz"

        url = f"https://qt.gtimg.cn/q={prefix}{pure_code}"
        req = urllib.request.Request(url)
        req.add_header("User-Agent", "Mozilla/5.0")

        try:
            resp = urllib.request.urlopen(req, timeout=10)
            data = resp.read().decode("gbk")
        except Exception as e:
            logger.warning(f"腾讯行情请求失败 {code}: {e}")
            return None

        for line in data.strip().split(";"):
            if not line.strip() or "=" not in line or '"' not in line:
                continue
            vals = line.split('"')[1].split("~")
            if len(vals) < 53:
                continue

            return {
                "name": vals[1],
                "price": float(vals[3]) if vals[3] else 0,
                "last_close": float(vals[4]) if vals[4] else 0,
                "pe_ttm": float(vals[39]) if vals[39] else 0,
                "pb": float(vals[46]) if vals[46] else 0,
                "mcap_yi": float(vals[44]) if vals[44] else 0,
                "float_mcap_yi": float(vals[45]) if vals[45] else 0,
                "total_shares": float(vals[44]) / float(vals[3]) * 10000 if vals[44] and vals[3] and float(vals[3]) > 0 else 0,
                "float_shares": float(vals[45]) / float(vals[3]) * 10000 if vals[45] and vals[3] and float(vals[3]) > 0 else 0,
                "turnover_pct": float(vals[38]) if vals[38] else 0,
                "vol_ratio": float(vals[49]) if vals[49] else 0,
                "amplitude_pct": float(vals[43]) if vals[43] else 0,
            }
        return None

    # ═══════════════════════════════════════════════════════════════
    # 同花顺一致预期
    # ═══════════════════════════════════════════════════════════════

    def get_consensus_eps(self, code: str) -> Optional[dict]:
        """
        从同花顺获取机构一致预期EPS数据。
        解析 worth.html 页面中的 yjycData JSON 数据块。

        Returns:
            {
                "eps_2025": float,    # 2025年一致预期EPS
                "eps_2026": float,    # 2026年一致预期EPS
                "eps_2027": float,    # 2027年一致预期EPS
                "num_analysts": int,  # 覆盖机构数
                "historical": [...],  # 历史EPS（实际值）
            }
        """
        import urllib.request
        import re

        pure_code = code.zfill(6)
        url = f"https://basic.10jqka.com.cn/{pure_code}/worth.html"

        req = urllib.request.Request(url)
        req.add_header("User-Agent", "Mozilla/5.0")

        try:
            resp = urllib.request.urlopen(req, timeout=15)
            html = resp.read().decode("gbk", errors="ignore")
        except Exception as e:
            logger.warning(f"同花顺一致预期获取失败 {code}: {e}")
            return None

        # 提取 yjycData JSON 数据块
        # 格式: <div id="yjycData" ...>[["2019","32.80","412.06","SJ"],...]</div>
        match = re.search(r'id="yjycData"[^>]*>(.*?)</div>', html)
        if not match:
            logger.warning(f"同花顺一致预期解析失败 {code}（未找到 yjycData）")
            return None

        try:
            rows = json.loads(match.group(1))
        except json.JSONDecodeError as e:
            logger.warning(f"同花顺一致预期 JSON 解析失败 {code}: {e}")
            return None

        if not rows or not isinstance(rows, list):
            return None

        result = {"num_analysts": 0, "historical": []}
        for row in rows:
            if len(row) < 4:
                continue
            year = row[0]
            try:
                eps = float(row[1])
            except (ValueError, TypeError):
                continue
            data_type = row[3]  # SJ=实际, YC=预测

            if data_type == "YC":
                result[f"eps_{year}"] = eps
                result["num_analysts"] = max(result.get("num_analysts", 0), 1)
            elif data_type == "SJ":
                result["historical"].append({"year": year, "eps": eps})

        # 检查是否有预测数据
        has_forecast = any(k.startswith("eps_20") for k in result.keys())
        return result if has_forecast else None

    # ═══════════════════════════════════════════════════════════════
    # 东财研报目标价
    # ═══════════════════════════════════════════════════════════════

    def get_research_targets(self, code: str, limit: int = 20) -> List[dict]:
        """
        从东财 reportapi 获取最近研报的评级和目标价。
        端点: reportapi.eastmoney.com/report/list (公开JSON API, 免费无key)

        Returns:
            [{org, date, rating, target_price, eps_2025, eps_2026, eps_2027}, ...]
        """
        import requests
        from datetime import datetime

        pure_code = code.zfill(6)

        url = "https://reportapi.eastmoney.com/report/list"
        current_year = datetime.now().year
        params = {
            "industryCode": "*",
            "pageSize": str(limit),
            "industry": "*",
            "rating": "*",
            "ratingChange": "*",
            "beginTime": f"{current_year - 2}-01-01",
            "endTime": f"{current_year + 2}-12-31",
            "pageNo": "1",
            "fields": "",
            "qType": "0",
            "orgCode": "",
            "code": pure_code,
            "rcode": "",
        }

        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Referer": "https://data.eastmoney.com/",
        }

        try:
            resp = requests.get(url, params=params, timeout=15, headers=headers)
            data = resp.json()
        except Exception as e:
            logger.warning(f"东财研报获取失败 {code}: {e}")
            return []

        # 响应结构: {"hits": N, "data": [...], "TotalPage": N, ...}
        records = data.get("data", [])
        if not isinstance(records, list):
            return []

        results = []
        for r in records:
            # 目标价: indvAimPriceT (个股目标价)
            target = r.get("indvAimPriceT", "") or r.get("indvAimPriceL", "")
            target_price = None
            if target and target != "-" and target != "":
                try:
                    target_price = float(target)
                except (ValueError, TypeError):
                    pass

            # EPS预测: predictThisYearEps / predictNextYearEps / predictNextTwoYearEps
            eps_this = r.get("predictThisYearEps", 0) or 0
            eps_next = r.get("predictNextYearEps", 0) or 0
            eps_two = r.get("predictNextTwoYearEps", 0) or 0

            results.append({
                "title": r.get("title", ""),
                "org": r.get("orgSName", r.get("orgName", "")),
                "date": (r.get("publishDate", "") or "")[:10],
                "rating": r.get("emRatingName", r.get("sRatingName", "")),
                "target_price": target_price,
                "eps_2025": float(eps_this),
                "eps_2026": float(eps_next),
                "eps_2027": float(eps_two),
                "industry_name": r.get("indvInduName", r.get("industryName", "")),
                "stock_name": r.get("stockName", ""),
                "info_code": r.get("infoCode", ""),
                "researcher": r.get("researcher", ""),
                "attach_pages": int(r.get("attachPages", 0) or 0),
            })

        return results
