"""
VPA 命令行入口
==============
用法:
  python vpa_cli.py analyze 688017              # 单票分析
  python vpa_cli.py analyze 688017 --period 60min  # 分钟K线分析
  python vpa_cli.py compare 688017,300750,600519  # 多票对比
  python vpa_cli.py screen --universe csi300 --mode best_buy  # 筛选
  python vpa_cli.py index                        # 大盘指数分析
  python vpa_cli.py sectors                      # 行业板块扫描
"""

import sys
import os
import argparse

# 确保模块可以被导入
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vpa_engine import vpa_analyze, vpa_compare, print_vpa_report
from vpa_screener import (
    vpa_screen, vpa_screen_index, vpa_screen_sectors,
    screen_best_buy_signals, screen_smart_money_accumulating, screen_risk_warnings,
)


def cmd_analyze(args):
    """单票分析"""
    report = vpa_analyze(args.code, period=args.period, lookback=args.lookback)
    print_vpa_report(report)


def cmd_compare(args):
    """多票对比"""
    codes = [c.strip() for c in args.codes.split(",")]
    results = vpa_compare(codes, period=args.period, lookback=args.lookback)

    print(f"\n{'='*70}")
    print(f"  量价对比排名 ({len(results)}只)")
    print(f"{'='*70}")
    print(f"  {'排名':<4} {'代码':<10} {'名称':<10} {'评级':<10} {'评分':>5} {'趋势':>8}")
    print(f"  {'-'*60}")

    for i, r in enumerate(results):
        code = r.get("code", "")
        name = r.get("name", code)[:10]
        rating = r.get("rating", "")
        score = r.get("score", 0)
        trend = r.get("short_term_direction", "")[:8]
        print(f"  {i+1:<4} {code:<10} {name:<10} {rating:<10} {score:>5} {trend:>8}")

    print(f"{'='*70}\n")


def cmd_screen(args):
    """筛选"""
    mode = args.mode
    if mode == "best_buy":
        results = screen_best_buy_signals(top_n=args.top_n)
    elif mode == "smart_money":
        results = screen_smart_money_accumulating(top_n=args.top_n)
    elif mode == "risk":
        results = screen_risk_warnings(top_n=args.top_n)
    else:
        results = vpa_screen(
            universe=args.universe,
            resonance_mode=args.resonance,
            min_strength=args.min_score,
            top_n=args.top_n,
        )

    _print_screen_results(results, mode)


def cmd_index(args):
    """大盘指数"""
    results = vpa_screen_index()
    print(f"\n{'='*60}")
    print(f"  大盘指数量价状态")
    print(f"{'='*60}")
    for code, info in results.items():
        icon = {"趋势做多": "🟢", "偏多": "🟢", "观望": "🟡", "偏空": "🔴", "持币/做空": "🔴"}
        e = icon.get(info.get("rating", ""), "⚪")
        print(f"  {info['name']}({code}): {e} {info['rating']} ({info['score']}/100)")
        print(f"    趋势: {info['trend_dir']} | 阶段: {info['phase']}")
    print(f"{'='*60}\n")


def cmd_sectors(args):
    """行业板块"""
    results = vpa_screen_sectors()
    _print_screen_results(results, "sectors")


def _print_screen_results(results, mode):
    modes_cn = {
        "best_buy": "最强做多信号(三维共振)",
        "smart_money": "主力吸筹检测",
        "risk": "风险预警",
        "sectors": "行业板块量价扫描",
    }
    title = modes_cn.get(mode, f"筛选结果")
    print(f"\n{'='*70}")
    print(f"  {title} — {len(results)} 条结果")
    print(f"{'='*70}")

    if not results:
        print("  无符合条件的标的")
        return

    print(f"  {'排名':<4} {'代码':<12} {'名称':<12} {'评分':>5} {'评级':<10}")
    print(f"  {'-'*55}")
    for i, r in enumerate(results):
        code = r.get("code", "")
        name = r.get("name", code)[:12]
        score = r.get("score", 0)
        rating = r.get("rating", "")
        print(f"  {i+1:<4} {code:<12} {name:<12} {score:>5} {rating:<10}")

        # 额外信息
        extra = []
        if r.get("trend_phase"):
            extra.append(r["trend_phase"])
        if r.get("resonance"):
            extra.append(r["resonance"][:30])
        if extra:
            print(f"       {' '.join(extra)}")

    print(f"{'='*70}\n")


def main():
    parser = argparse.ArgumentParser(description="VPA 量价分析工具")
    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # analyze
    p = subparsers.add_parser("analyze", help="单票分析")
    p.add_argument("code", help="股票代码")
    p.add_argument("--period", default="daily", help="周期: daily|60min|30min|15min|5min")
    p.add_argument("--lookback", type=int, default=120, help="回溯K线数")
    p.set_defaults(func=cmd_analyze)

    # compare
    p = subparsers.add_parser("compare", help="多票对比")
    p.add_argument("codes", help="股票代码(逗号分隔)")
    p.add_argument("--period", default="daily")
    p.add_argument("--lookback", type=int, default=120)
    p.set_defaults(func=cmd_compare)

    # screen
    p = subparsers.add_parser("screen", help="筛选")
    p.add_argument("--universe", default="csi300_csi500", help="标的范围")
    p.add_argument("--mode", default="best_buy",
                   choices=["best_buy", "smart_money", "risk", "custom"])
    p.add_argument("--resonance", default="any", choices=["any", "trend_vpa", "all"])
    p.add_argument("--min_score", type=int, default=50)
    p.add_argument("--top_n", type=int, default=20)
    p.set_defaults(func=cmd_screen)

    # index
    p = subparsers.add_parser("index", help="大盘指数分析")
    p.set_defaults(func=cmd_index)

    # sectors
    p = subparsers.add_parser("sectors", help="行业板块扫描")
    p.set_defaults(func=cmd_sectors)

    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        return

    args.func(args)


if __name__ == "__main__":
    main()
