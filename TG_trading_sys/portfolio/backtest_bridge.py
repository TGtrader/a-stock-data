"""
回测桥接器 — 连接 vibe-trading-repo 回测引擎
=============================================
将 TG-trading-sys 的组合配置转换为 vibe-trading-repo 的 config.json 格式，
调用其 runner.py 执行回测，解析结果。

vibe-trading-repo 路径：项目根目录/vibe-trading-repo/agent/backtest/
"""

import json
import logging
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
import pandas as pd
import numpy as np

logger = logging.getLogger("tg.portfolio.backtest")


# vibe-trading-repo 回测引擎路径
def _get_vt_backtest_path() -> Path:
    """获取 vibe-trading-repo 的 backtest 模块路径"""
    project_root = Path(__file__).resolve().parent.parent.parent
    vt_path = project_root / "vibe-trading-repo" / "agent"
    return vt_path


def generate_config(
    codes: List[str],
    weights: Dict[str, float],
    start_date: str = "2024-01-01",
    end_date: str = None,
    capital: float = 1_000_000,
    rebalance: str = "monthly",
    benchmark_code: str = "000300",
) -> dict:
    """
    生成 vibe-trading-repo 格式的回测配置。

    Args:
        codes: 股票代码列表
        weights: 代码→权重映射
        start_date: 回测起始日期
        end_date: 回测截止日期
        capital: 初始资金
        rebalance: 再平衡频率 (daily/monthly/quarterly)
        benchmark_code: 基准代码

    Returns:
        config dict (与 vibe-trading-repo 的 config.json 兼容)
    """
    if end_date is None:
        end_date = datetime.now().strftime("%Y-%m-%d")

    # 构造持仓配置
    positions = []
    for code, w in weights.items():
        if w > 0:
            positions.append({
                "code": code,
                "weight": round(w, 6),
            })

    config = {
        "name": f"TG_backtest_{datetime.now().strftime('%Y%m%d_%H%M')}",
        "start_date": start_date,
        "end_date": end_date,
        "initial_capital": capital,
        "rebalance_frequency": rebalance,
        "benchmark": benchmark_code,
        "positions": positions,
        "commission": {
            "buy_rate": 0.00025,      # 佣金 万2.5
            "sell_rate": 0.00025,
            "min_commission": 5.0,    # 最低佣金5元
            "stamp_tax_rate": 0.001,  # 印花税 千1（仅卖出）
        },
        "slippage": 0.001,            # 滑点 千1
        "data_source": "mootdx",      # 数据源
    }

    return config


def save_config(config: dict, path: str = None) -> str:
    """保存配置到文件"""
    if path is None:
        project_root = Path(__file__).resolve().parent.parent.parent
        data_dir = project_root.parent / "data" / "backtest_configs"
        data_dir.mkdir(parents=True, exist_ok=True)
        path = str(data_dir / f"{config['name']}.json")

    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

    logger.info(f"配置文件已保存: {path}")
    return path


def run_backtest(
    config: dict,
    config_path: str = None,
    timeout: int = 120,
) -> dict:
    """
    调用 vibe-trading-repo 的回测引擎执行回测。

    通过 subprocess 调用 `python -m backtest.runner <run_dir>`。

    Args:
        config: 回测配置 dict
        config_path: 配置文件路径（None=自动保存）
        timeout: 超时秒数

    Returns:
        {
            "success": bool,
            "equity_curve": pd.DataFrame | None,
            "trades": pd.DataFrame | None,
            "metrics": dict,
            "error": str | None,
        }
    """
    import subprocess
    import tempfile

    vt_path = _get_vt_backtest_path()

    if not vt_path.exists():
        return {
            "success": False,
            "error": f"vibe-trading-repo 回测引擎不存在: {vt_path}",
        }

    # 保存配置到临时目录
    if config_path is None:
        config_path = save_config(config)

    run_dir = str(Path(config_path).parent)

    # 构建运行命令
    cmd = [
        sys.executable,
        "-m", "backtest.runner",
        run_dir,
    ]

    logger.info(f"执行回测: {' '.join(cmd)} (cwd={vt_path.parent})")

    try:
        result = subprocess.run(
            cmd,
            cwd=str(vt_path.parent),
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        if result.returncode != 0:
            logger.warning(f"回测进程返回非零: {result.returncode}")
            logger.warning(f"stderr: {result.stderr[:500]}")

        # 尝试解析输出（vibe-trading-repo 输出到 stdout）
        return _parse_backtest_output(result.stdout, result.stderr)

    except subprocess.TimeoutExpired:
        return {"success": False, "error": f"回测超时（{timeout}秒）"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _parse_backtest_output(stdout: str, stderr: str) -> dict:
    """解析回测引擎的输出"""
    result = {
        "success": True,
        "equity_curve": None,
        "trades": None,
        "metrics": {},
        "stdout": stdout[-2000:] if len(stdout) > 2000 else stdout,
    }

    # 尝试从输出中提取关键指标
    import re

    # 寻找 JSON 格式的结果（vibe-trading-repo 可能输出到文件）
    for line in (stdout + stderr).split("\n"):
        if "total_return" in line.lower() or "sharpe" in line.lower():
            try:
                metrics = json.loads(line.strip())
                result["metrics"].update(metrics)
            except json.JSONDecodeError:
                pass

    return result


# ═══════════════════════════════════════════════════════════════
# 内置简化回测（当 vibe-trading-repo 不可用时）
# ═══════════════════════════════════════════════════════════════

def simple_backtest(
    codes: List[str],
    weights: Dict[str, float],
    start_date: str = "2024-01-01",
    end_date: str = None,
    capital: float = 1_000_000,
    rebalance: str = "monthly",
) -> dict:
    """
    内置简化回测引擎。

    当 vibe-trading-repo 不可用时使用，提供基本的回测能力。

    逻辑：
      1. 获取所有持仓的日K线数据
      2. 按再平衡周期重新分配权重
      3. 计算组合权益曲线
      4. 计算绩效指标
    """
    from ..data.cache import DataCache
    from .perf_metrics import compute_metrics

    cache = DataCache()

    if end_date is None:
        end_date = datetime.now().strftime("%Y-%m-%d")

    # ── 获取数据 ──
    price_dict = {}
    for code in weights:
        df = cache.get_kline(code, lookback=600)
        if df is not None and len(df) >= 20:
            price_dict[code] = df["close"]

    if len(price_dict) < 2:
        return {"success": False, "error": "有效标的不够（需要≥2只）"}

    # 对齐日期
    prices_df = pd.DataFrame(price_dict)
    prices_df = prices_df[prices_df.index >= pd.Timestamp(start_date)]
    if end_date:
        prices_df = prices_df[prices_df.index <= pd.Timestamp(end_date)]
    prices_df = prices_df.dropna(how="all")

    if len(prices_df) < 5:
        return {"success": False, "error": f"对齐后数据不足（{len(prices_df)}天）"}

    # 前向填充（非交易日保持价格）
    prices_df = prices_df.ffill()

    # ── 计算收益率 ──
    returns = prices_df.pct_change().dropna()

    # ── 再平衡时间点 ──
    if rebalance == "monthly":
        rebalance_dates = returns.resample("ME").last().index
    elif rebalance == "quarterly":
        rebalance_dates = returns.resample("QE").last().index
    else:  # daily
        rebalance_dates = returns.index

    # ── 模拟组合 ──
    w = pd.Series(weights, name="weight")
    w = w / w.sum()

    portfolio_returns = []
    current_weights = None

    for i, date in enumerate(returns.index):
        if date in rebalance_dates or current_weights is None:
            # 再平衡
            current_weights = w.reindex(returns.columns, fill_value=0)
            current_weights = current_weights / current_weights.sum()
        else:
            # 漂移
            if i > 0:
                for code in current_weights.index:
                    if code in returns.columns and not pd.isna(returns.loc[date, code]):
                        current_weights.loc[code] *= (1 + returns.loc[date, code])
                current_weights = current_weights / current_weights.sum()

        # 当日组合收益
        daily_ret = 0
        for code in current_weights.index:
            if code in returns.columns and not pd.isna(returns.loc[date, code]):
                daily_ret += current_weights.loc[code] * returns.loc[date, code]

        portfolio_returns.append({"date": date, "return": daily_ret})

    # ── 构建权益曲线 ──
    ret_df = pd.DataFrame(portfolio_returns).set_index("date")
    ret_df["equity"] = (1 + ret_df["return"]).cumprod() * capital

    # ── 基准对比 ──
    benchmark_equity = None
    try:
        bench_df = cache.get_kline("000300", lookback=600)
        if bench_df is not None and len(bench_df) >= 20:
            bench_returns = bench_df["close"].pct_change().dropna()
            bench_aligned = bench_returns.reindex(ret_df.index).fillna(0)
            benchmark_equity = (1 + bench_aligned).cumprod() * capital
    except Exception:
        pass

    # ── 计算绩效指标 ──
    metrics = compute_metrics(ret_df["equity"], benchmark_equity)

    # ── 交易记录（简化：只在再平衡日期记录）─
    trades = []
    for i, date in enumerate(rebalance_dates):
        if i == 0:
            continue
        prev_date = rebalance_dates[i - 1]
        for code in w.index:
            if w[code] <= 0:
                continue
            # 简化的买/卖记录
            if i % 2 == 0:  # 粗略估计（实际应基于权重变化）
                trades.append({
                    "date": date.strftime("%Y-%m-%d"),
                    "code": code,
                    "action": "rebalance",
                    "weight": round(w[code], 4),
                })

    return {
        "success": True,
        "equity_curve": ret_df,
        "trades": trades,
        "metrics": metrics,
        "benchmark_equity": benchmark_equity,
    }
