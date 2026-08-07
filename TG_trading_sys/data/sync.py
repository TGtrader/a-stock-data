"""
TG-trading-sys 数据同步管理
===========================
定时/批量同步数据到本地 SQLite。
支持：全市场K线同步、财务数据批量更新、资金流同步。
"""

import logging
from datetime import datetime
from typing import List, Optional

from ..core.database import Database
from .cache import DataCache

logger = logging.getLogger("tg.data.sync")


class SyncManager:
    """
    数据同步调度管理器。
    用于批量预拉取全市场 / 自选池数据到本地 SQLite。
    """

    def __init__(self):
        self.cache = DataCache()
        self.db = Database.get_instance()

    def sync_kline_batch(self, codes: List[str], lookback: int = 250, progress: bool = True):
        """
        批量同步K线数据。

        Args:
            codes: 股票代码列表
            lookback: 回溯K线数
            progress: 是否打印进度
        """
        total = len(codes)
        success = 0
        for i, code in enumerate(codes):
            try:
                df = self.cache.get_kline(code, lookback=lookback, force_refresh=True)
                if df is not None and not df.empty:
                    success += 1
                if progress and (i + 1) % 50 == 0:
                    logger.info(f"K线同步: {i+1}/{total} ({success} 成功)")
            except Exception as e:
                logger.warning(f"同步失败 {code}: {e}")

        logger.info(f"K线同步完成: {success}/{total} 成功")
        return success

    def sync_financials_batch(self, codes: List[str], report_types: List[str] = None):
        """批量同步财务数据"""
        if report_types is None:
            report_types = ["lrb", "fzb", "llb"]

        total = len(codes) * len(report_types)
        success = 0
        for code in codes:
            for rt in report_types:
                try:
                    data = self.cache.get_financials(code, report_type=rt, force_refresh=True)
                    if data:
                        success += 1
                except Exception as e:
                    logger.warning(f"财务同步失败 {code}/{rt}: {e}")

        logger.info(f"财务同步完成: {success}/{total} 成功")
        return success

    def get_db_stats(self) -> dict:
        """获取数据库统计信息"""
        tables = ["daily_kline", "financials", "moneyflow", "earnings_forecast",
                   "valuation_cache", "holdings", "trade_log", "factor_snapshot", "stock_basic"]
        stats = {}
        for table in tables:
            stats[table] = self.db.count(table)

        # 最新K线日期
        latest_kline = self.db.fetchone("SELECT MAX(date) as d FROM daily_kline")
        stats["latest_kline_date"] = latest_kline["d"] if latest_kline else None

        return stats

    def print_stats(self):
        """打印数据库统计"""
        stats = self.get_db_stats()
        print(f"\n{'='*50}")
        print(f"  TG-trading-sys 数据库统计")
        print(f"{'='*50}")
        for table, count in stats.items():
            if table != "latest_kline_date":
                print(f"  {table:<25} {count:>8} 条")
        print(f"  {'最新K线日期':<25} {str(stats.get('latest_kline_date', 'N/A')):>8}")
        print(f"{'='*50}\n")
