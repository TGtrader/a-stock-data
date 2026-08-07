"""
TG-trading-sys SQLite 数据库管理
================================
轻量持久化存储：K线 / 财务 / 资金流 / 研报 / 估值缓存 / 持仓 / 交易日志 / 因子快照
"""

import sqlite3
import json
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
from contextlib import contextmanager

from .config import Config

logger = logging.getLogger("tg.db")

# ── 建表 DDL ──
DDL_STATEMENTS = [
    """CREATE TABLE IF NOT EXISTS stock_basic (
        code TEXT PRIMARY KEY,
        name TEXT,
        market TEXT,
        industry TEXT,
        industry_code TEXT,
        list_date TEXT,
        total_shares REAL,
        float_shares REAL,
        price REAL,
        pe_ttm REAL,
        pb REAL,
        mcap_yi REAL,
        updated_at TEXT
    )""",

    """CREATE TABLE IF NOT EXISTS daily_kline (
        code TEXT,
        date TEXT,
        open REAL, high REAL, low REAL, close REAL,
        volume REAL, amount REAL,
        source TEXT,
        PRIMARY KEY (code, date)
    )""",

    """CREATE TABLE IF NOT EXISTS financials (
        code TEXT,
        report_date TEXT,
        report_type TEXT,
        data_json TEXT,
        updated_at TEXT,
        PRIMARY KEY (code, report_date, report_type)
    )""",

    """CREATE TABLE IF NOT EXISTS moneyflow (
        code TEXT,
        date TEXT,
        net_mf_amount REAL,
        buy_lg_amount REAL,
        sell_lg_amount REAL,
        buy_elg_amount REAL,
        sell_elg_amount REAL,
        buy_sm_amount REAL,
        sell_sm_amount REAL,
        PRIMARY KEY (code, date)
    )""",

    """CREATE TABLE IF NOT EXISTS earnings_forecast (
        code TEXT,
        org TEXT,
        report_date TEXT,
        year INTEGER,
        eps REAL,
        rating TEXT,
        target_price REAL,
        PRIMARY KEY (code, org, report_date, year)
    )""",

    """CREATE TABLE IF NOT EXISTS valuation_cache (
        code TEXT,
        date TEXT,
        dcf_value REAL,
        pe_peg_value REAL,
        pb_roe_value REAL,
        consensus_target REAL,
        final_value REAL,
        scenario_json TEXT,
        PRIMARY KEY (code, date)
    )""",

    """CREATE TABLE IF NOT EXISTS holdings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        portfolio_name TEXT,
        code TEXT,
        name TEXT,
        weight REAL,
        shares INTEGER,
        entry_price REAL,
        entry_date TEXT,
        exit_price REAL,
        exit_date TEXT,
        status TEXT DEFAULT 'open'
    )""",

    """CREATE TABLE IF NOT EXISTS trade_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        portfolio_name TEXT,
        code TEXT,
        action TEXT,
        price REAL,
        shares INTEGER,
        amount REAL,
        commission REAL,
        reason TEXT,
        trade_date TEXT
    )""",

    """CREATE TABLE IF NOT EXISTS factor_snapshot (
        code TEXT,
        date TEXT,
        pe_ttm REAL, pb REAL, ps_ttm REAL,
        eps_growth_yoy REAL, revenue_growth_yoy REAL,
        roe REAL, gross_margin REAL, debt_ratio REAL,
        momentum_20d REAL, momentum_60d REAL,
        northbound_change REAL,
        composite_score REAL,
        updated_at TEXT,
        PRIMARY KEY (code, date)
    )""",

    "CREATE INDEX IF NOT EXISTS idx_kline_code_date ON daily_kline(code, date)",
    "CREATE INDEX IF NOT EXISTS idx_financials_code ON financials(code, report_date)",
    "CREATE INDEX IF NOT EXISTS idx_moneyflow_code ON moneyflow(code, date)",
    "CREATE INDEX IF NOT EXISTS idx_holdings_portfolio ON holdings(portfolio_name, status)",
    "CREATE INDEX IF NOT EXISTS idx_trade_log_portfolio ON trade_log(portfolio_name, trade_date)",
    "CREATE INDEX IF NOT EXISTS idx_factor_code_date ON factor_snapshot(code, date)",
]


class Database:
    """SQLite 数据库管理器（单例连接池）"""

    _instance: Optional["Database"] = None

    def __init__(self, db_path: Path = None):
        self.db_path = str(db_path or Config.DB_PATH)
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    @classmethod
    def get_instance(cls) -> "Database":
        if cls._instance is None:
            Config.ensure_dirs()
            cls._instance = cls()
        return cls._instance

    def _init_db(self):
        """初始化数据库：建表 + 索引 + 迁移"""
        Config.ensure_dirs()
        conn = self._get_conn()
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        for ddl in DDL_STATEMENTS:
            try:
                conn.execute(ddl)
            except sqlite3.Error as e:
                logger.warning(f"DDL 执行警告: {e}")

        # ── 迁移：为已有的 stock_basic 表添加实时行情列 ──
        self._migrate_stock_basic_columns(conn)

        conn.commit()
        logger.info(f"数据库就绪: {self.db_path}")

    def _migrate_stock_basic_columns(self, conn):
        """为旧版 stock_basic 表补充 price/pe_ttm/pb/mcap_yi 列"""
        migrations = [
            "ALTER TABLE stock_basic ADD COLUMN price REAL",
            "ALTER TABLE stock_basic ADD COLUMN pe_ttm REAL",
            "ALTER TABLE stock_basic ADD COLUMN pb REAL",
            "ALTER TABLE stock_basic ADD COLUMN mcap_yi REAL",
        ]
        for sql in migrations:
            try:
                conn.execute(sql)
                logger.info(f"迁移: {sql}")
            except sqlite3.Error:
                pass  # 列已存在，忽略

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path, timeout=10)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    @contextmanager
    def cursor(self):
        """获取游标的上下文管理器（自动commit/rollback）"""
        conn = self._get_conn()
        try:
            yield conn.cursor()
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    # ── 通用CRUD ──

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        """执行写操作"""
        conn = self._get_conn()
        cur = conn.execute(sql, params)
        conn.commit()
        return cur

    def executemany(self, sql: str, params_list: List[tuple]):
        """批量执行写操作"""
        conn = self._get_conn()
        conn.executemany(sql, params_list)
        conn.commit()

    def fetchone(self, sql: str, params: tuple = ()) -> Optional[sqlite3.Row]:
        """查询单行"""
        cur = self._get_conn().execute(sql, params)
        return cur.fetchone()

    def fetchall(self, sql: str, params: tuple = ()) -> List[sqlite3.Row]:
        """查询多行"""
        cur = self._get_conn().execute(sql, params)
        return cur.fetchall()

    def table_exists(self, table_name: str) -> bool:
        row = self.fetchone(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,)
        )
        return row is not None

    def count(self, table_name: str, where: str = "", params: tuple = ()) -> int:
        sql = f"SELECT COUNT(*) as cnt FROM {table_name}"
        if where:
            sql += f" WHERE {where}"
        row = self.fetchone(sql, params)
        return row["cnt"] if row else 0

    # ── K线缓存专用 ──

    def get_kline_date_range(self, code: str) -> tuple:
        """获取某股票K线的日期范围 (最早, 最晚)"""
        row = self.fetchone(
            "SELECT MIN(date) as d1, MAX(date) as d2 FROM daily_kline WHERE code=?",
            (code,)
        )
        if row and row["d1"]:
            return row["d1"], row["d2"]
        return None, None

    def upsert_kline(self, code: str, rows: List[dict], source: str = ""):
        """批量插入/更新K线数据"""
        sql = """INSERT OR REPLACE INTO daily_kline
                 (code, date, open, high, low, close, volume, amount, source)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"""
        params = [
            (code, r["date"], r.get("open"), r.get("high"), r.get("low"),
             r.get("close"), r.get("volume"), r.get("amount"), source)
            for r in rows
        ]
        self.executemany(sql, params)

    # ── 估值缓存专用 ──

    def get_latest_valuation(self, code: str) -> Optional[sqlite3.Row]:
        return self.fetchone(
            "SELECT * FROM valuation_cache WHERE code=? ORDER BY date DESC LIMIT 1",
            (code,)
        )

    def upsert_valuation(self, code: str, date: str, data: dict):
        sql = """INSERT OR REPLACE INTO valuation_cache
                 (code, date, dcf_value, pe_peg_value, pb_roe_value,
                  consensus_target, final_value, scenario_json)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?)"""
        self.execute(sql, (
            code, date,
            data.get("dcf_value"),
            data.get("pe_peg_value"),
            data.get("pb_roe_value"),
            data.get("consensus_target"),
            data.get("final_value"),
            json.dumps(data.get("scenarios", {}), ensure_ascii=False),
        ))

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None
