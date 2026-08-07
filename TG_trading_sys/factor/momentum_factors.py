"""
动量因子 — 价格动量 / 成交量动能 / 换手率
===========================================
基于K线数据计算中短期动量信号。
"""

import logging
from typing import List
import pandas as pd
import numpy as np

from ..data.cache import DataCache

logger = logging.getLogger("tg.factor.momentum")


def compute_momentum_20d(codes: List[str], cache: DataCache) -> pd.Series:
    """20日价格动量 — 近20个交易日涨跌幅"""
    return _price_momentum(codes, cache, window=20, name="momentum_20d")


def compute_momentum_60d(codes: List[str], cache: DataCache) -> pd.Series:
    """60日价格动量 — 近60个交易日涨跌幅"""
    return _price_momentum(codes, cache, window=60, name="momentum_60d")


def _price_momentum(codes: List[str], cache: DataCache, window: int, name: str) -> pd.Series:
    """通用价格动量计算"""
    values = {}
    for code in codes:
        try:
            # 多取一些数据以覆盖非交易日
            df = cache.get_kline(code, lookback=window + 20)
            if df is None or len(df) < window // 3:
                values[code] = np.nan
                continue

            close = df["close"]
            if len(close) < max(5, window // 5):
                values[code] = np.nan
                continue

            start_price = close.iloc[-(min(window, len(close)))]
            end_price = close.iloc[-1]

            if start_price > 0:
                momentum = (end_price - start_price) / start_price
                momentum = max(-0.80, min(3.0, momentum))
                values[code] = momentum
            else:
                values[code] = np.nan
        except Exception as e:
            logger.debug(f"动量计算失败 {code}: {e}")
            values[code] = np.nan

    return pd.Series(values, name=name)


def compute_volume_momentum(codes: List[str], cache: DataCache) -> pd.Series:
    """
    量能动量 — 近5日均量 / 20日均量，衡量近期交投活跃度变化。
    放量（>1.2）说明有资金关注，缩量（<0.6）说明人气息淡。
    """
    values = {}
    for code in codes:
        try:
            df = cache.get_kline(code, lookback=60)
            if df is None or len(df) < 20:
                values[code] = np.nan
                continue

            vol = df["volume"]
            vol_5d = vol.iloc[-5:].mean()
            vol_20d = vol.iloc[-20:].mean()

            if vol_20d > 0:
                ratio = vol_5d / vol_20d
                # 居中处理：1.0 附近为中性
                values[code] = ratio
            else:
                values[code] = np.nan
        except Exception as e:
            logger.debug(f"量能动量计算失败 {code}: {e}")
            values[code] = np.nan

    return pd.Series(values, name="volume_momentum")


def compute_turnover_rate(codes: List[str], cache: DataCache) -> pd.Series:
    """
    换手率因子 — 适度活跃为佳。
    数据源：腾讯实时行情中的换手率。
    换手率适中（2-10%）更优；过高可能有出货风险，过低无人气。
    """
    values = {}
    for code in codes:
        try:
            info = cache.get_stock_basic(code) or {}
            turnover = info.get("turnover_pct", 0)
            if turnover and turnover > 0:
                # 换手率在 3-8% 得分最高（适度活跃）
                if 3 <= turnover <= 8:
                    score = 1.0
                elif 1 <= turnover < 3:
                    score = 0.6
                elif 8 < turnover <= 15:
                    score = 0.5
                elif turnover > 15:
                    score = 0.2  # 过高换手可能是出货
                else:
                    score = 0.1  # 极低换手无人气
                values[code] = score
            else:
                values[code] = np.nan
        except Exception as e:
            logger.debug(f"换手率计算失败 {code}: {e}")
            values[code] = np.nan

    return pd.Series(values, name="turnover_rate")
