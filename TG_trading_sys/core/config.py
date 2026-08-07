"""
TG-trading-sys 全局配置管理
==========================
统一管理：数据库路径 / Token / 估值参数 / 因子权重 / 风控参数
"""

import os
import json
from pathlib import Path
from typing import Optional, Dict


class Config:
    """全局配置单例，支持从环境变量 + 配置文件 + 内置默认值三层加载"""

    # ── 项目路径 ──
    ROOT_DIR = Path(__file__).resolve().parent.parent
    DATA_DIR = ROOT_DIR.parent / "data"
    DB_PATH = DATA_DIR / "tg_trading.db"

    # ── 估值默认参数 ──
    # 无风险利率：中国10年期国债收益率（约）
    RISK_FREE_RATE = 0.028         # 2.8%
    # 股权风险溢价
    EQUITY_RISK_PREMIUM = 0.065    # 6.5%
    # 永续增长率默认
    PERPETUAL_GROWTH_RATE = 0.03   # 3%
    # 显式预测期
    EXPLICIT_FORECAST_YEARS = 5
    # 终值占比上限（终值超过此比例时发出警告）
    TERMINAL_VALUE_MAX_RATIO = 0.80
    # 情景分析参数
    SCENARIOS = {
        "乐观": {"growth_adj": 1.2,  "margin_adj": 1.1},
        "中性": {"growth_adj": 1.0,  "margin_adj": 1.0},
        "悲观": {"growth_adj": 0.8,  "margin_adj": 0.9},
    }

    # ── 因子默认权重 ──
    FACTOR_WEIGHTS = {
        "value":    0.20,   # 价值
        "growth":   0.25,   # 成长（含反转/超预期）
        "quality":  0.20,   # 质量
        "momentum": 0.15,   # 动量
        "fund":     0.10,   # 资金
        "sentiment":0.10,   # 情绪/研报
    }

    # ── 风控默认参数 ──
    MAX_SINGLE_WEIGHT = 0.10       # 单票上限 10%
    MAX_SECTOR_WEIGHT = 0.30       # 单行业上限 30%
    MAX_TOTAL_POSITION = {
        "bull": 0.80,              # 牛市总仓位
        "neutral_bull": 0.60,      # 震荡偏多
        "neutral": 0.50,           # 震荡
        "neutral_bear": 0.30,      # 震荡偏空
        "bear": 0.20,              # 熊市
    }
    DEFAULT_STOP_LOSS = 0.08       # 默认止损 8%
    MIN_RISK_REWARD_RATIO = 2.0    # 最低风险回报比

    # ── 筛选默认 ──
    MIN_DAILY_AMOUNT = 10_000_000  # 最低日均成交额（1000万）
    MIN_MARKET_CAP = 1_000_000_000 # 最低市值（10亿）

    @classmethod
    def get_tushare_token(cls) -> Optional[str]:
        """从环境变量或 vibe-trading 配置读取 Tushare token"""
        token = os.environ.get("TUSHARE_TOKEN", "")
        if token and token not in ("", "your-tushare-token"):
            return token

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

    @classmethod
    def ensure_dirs(cls):
        """确保所有必要的目录存在"""
        cls.DATA_DIR.mkdir(parents=True, exist_ok=True)

    @classmethod
    def display(cls) -> str:
        """打印当前配置"""
        lines = [
            f"数据目录: {cls.DATA_DIR}",
            f"数据库:   {cls.DB_PATH}",
            f"无风险利率: {cls.RISK_FREE_RATE*100:.1f}%",
            f"ERP:       {cls.EQUITY_RISK_PREMIUM*100:.1f}%",
            f"永续增长率: {cls.PERPETUAL_GROWTH_RATE*100:.1f}%",
            f"单票上限:   {cls.MAX_SINGLE_WEIGHT*100:.0f}%",
            f"行业上限:   {cls.MAX_SECTOR_WEIGHT*100:.0f}%",
        ]
        return "\n".join(lines)
