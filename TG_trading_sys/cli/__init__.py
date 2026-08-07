"""
TG-trading-sys CLI 命令行入口
=============================
支持：
  python -m TG_trading_sys.cli val 688017           估值分析
  python -m TG_trading_sys.cli val 688017 --html     估值HTML报告
  python -m TG_trading_sys.cli screen --top 20       多因子筛选
  python -m TG_trading_sys.cli screen --mode turnaround  反转信号精选
  python -m TG_trading_sys.cli screen --list-factors  列出所有因子
  python -m TG_trading_sys.cli sync stats            数据库统计
"""

import sys
import os
import argparse
from datetime import datetime

_pkg_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_project_root = os.path.dirname(_pkg_dir)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)


def cmd_val(args):
    """估值分析命令"""
    from TG_trading_sys.valuation.val_report import val_report, print_val_report, generate_html_report

    code = args.code.strip()
    wacc = args.wacc / 100 if args.wacc else None
    terminal_g = args.terminal_growth / 100 if args.terminal_growth else None

    print(f"正在分析 {code} ...")
    report = val_report(code, wacc=wacc, terminal_growth=terminal_g)

    if "error" in report:
        print(f"分析失败: {report['error']}")
        return

    print_val_report(report)

    if args.html:
        output_path = args.output or f"valuation_{code}_{report['date']}.html"
        generate_html_report(report, output_path)
        print(f"HTML报告已保存至: {output_path}")


def cmd_screen(args):
    """多因子筛选命令"""
    from TG_trading_sys.factor.screener import screen, screen_value_growth, screen_turnaround, screen_quality_momentum
    from TG_trading_sys.factor.factor_registry import list_factors

    if args.list_factors:
        df = list_factors(args.factor_category)
        print(f"\n{'='*80}")
        print(f"  已注册因子列表")
        print(f"{'='*80}")
        print(df.to_string(index=False))
        print(f"\n共 {len(df)} 个因子\n")
        return

    # 选择模式
    mode = args.mode
    if mode == "value_growth":
        result = screen_value_growth(top_n=args.top_n)
    elif mode == "turnaround":
        result = screen_turnaround(top_n=args.top_n)
    elif mode == "quality_momentum":
        result = screen_quality_momentum(top_n=args.top_n)
    else:
        result = screen(
            universe=args.universe,
            top_n=args.top_n,
            categories=args.categories.split(",") if args.categories else None,
            neutralize_industry=not args.no_neutralize,
        )

    if result.empty:
        print("无符合条件的标的")
        return

    # 打印
    _print_screen_result(result, mode)

    # 输出
    if args.csv:
        result.to_csv(args.csv, index=False, encoding="utf-8-sig")
        print(f"CSV已保存至: {args.csv}")

    if args.html:
        output_path = args.html_output or f"screen_{mode}_{result.iloc[0].get('score', '')}.html"
        from TG_trading_sys.factor.screener import _generate_html
        _generate_html(result, output_path, args.universe)
        print(f"HTML已保存至: {output_path}")


def cmd_signal(args):
    """多策略择时信号命令"""
    from TG_trading_sys.data.cache import DataCache
    from TG_trading_sys.strategy.timing.ma_signals import analyze_ma_system
    from TG_trading_sys.strategy.timing.pattern_signals import detect_patterns
    from TG_trading_sys.strategy.timing.fund_signals import analyze_fund_signals
    from TG_trading_sys.strategy.timing.event_signals import analyze_event_signals
    from TG_trading_sys.strategy.timing.signal_aggregator import aggregate_signals
    from TG_trading_sys.strategy.timing.trade_plan import generate_trade_plan

    code = args.code.strip()
    cache = DataCache()

    print(f"正在分析 {code} 的多策略择时信号...")

    df = cache.get_kline(code, lookback=200)
    if df is None or len(df) < 40:
        print(f"K线数据不足 ({len(df) if df is not None else 0}根)")
        return

    # 各信号源
    ma_result = analyze_ma_system(df)
    pat_result = detect_patterns(df)
    fund_result = analyze_fund_signals(code, cache)
    evt_result = analyze_event_signals(code, cache)

    # VPA 信号（如果有数据）
    vpa_result = None
    try:
        from 量价分析 import vpa_analyze
        vpa_result = vpa_analyze(code)
    except Exception:
        pass

    # 聚合裁决
    verdict = aggregate_signals(ma_result, vpa_result, fund_result, pat_result, evt_result)

    # 交易计划
    plan = generate_trade_plan(df, verdict)

    # ── 打印 ──
    print(f"\n{'='*60}")
    print(f"  多策略择时信号 — {code}")
    print(f"{'='*60}")

    # 综合裁决
    e = {"强烈做多": "🟢", "做多": "🟢", "偏多": "🟡", "观望": "⚪", "偏空": "🟠", "做空": "🔴", "强烈做空": "🔴"}
    print(f"\n  {e.get(verdict.verdict, '⚪')} 【裁决】{verdict.verdict} (评分{verdict.score}/100) 置信度{verdict.confidence}")
    print(f"  仓位建议: {verdict.position_advice}")
    print(f"  总结: {verdict.summary}")

    # 各信号源评分
    print(f"\n  【信号源评分】")
    names = {"trend": "均线系统", "vpa": "量价VPA", "fund": "资金面", "pattern": "形态识别", "event": "事件驱动"}
    for k, v in verdict.signal_scores.items():
        bar = "█" * (v // 5) + "░" * (20 - v // 5)
        print(f"    {names.get(k, k):<10} {bar} {v}/100")

    # 冲突
    if verdict.conflicts:
        print(f"\n  【冲突警告】")
        for c in verdict.conflicts:
            print(f"    ⚡ {c}")

    # 活跃信号
    if verdict.active_signals:
        print(f"\n  【活跃信号】({len(verdict.active_signals)}个)")
        seen = set()
        for s in verdict.active_signals[:8]:
            key = s.get("signal", "")
            if key not in seen:
                seen.add(key)
                print(f"    {'🟢' if '加仓' in s.get('action','') else '🔴' if '减仓' in s.get('action','') else '⚪'} {s['signal']}")

    # 交易计划
    if plan.get("plan_valid"):
        print(f"\n  【交易计划】")
        for line in plan["detail"].split("\n"):
            print(f"    {line}")
    else:
        print(f"\n  【交易计划】❌ {plan.get('rejection_reason', '')}")

    print(f"{'='*60}\n")


def cmd_portfolio(args):
    """组合管理命令"""
    from TG_trading_sys.factor.screener import screen
    from TG_trading_sys.portfolio.builder import build_portfolio
    from TG_trading_sys.portfolio.backtest_bridge import simple_backtest
    from TG_trading_sys.portfolio.perf_metrics import summary_table
    from TG_trading_sys.portfolio.monitor import (
        get_snapshot, save_portfolio_snapshot, list_portfolios, check_rebalance
    )

    if args.action == "build":
        # 从筛选结果构建组合
        print(f"正在运行筛选...")
        screen_result = screen(
            universe=args.universe,
            top_n=args.top_n,
            neutralize_industry=not args.no_neutralize,
        )
        if screen_result.empty:
            print("筛选结果为空")
            return

        codes = screen_result["code"].tolist()
        print(f"筛选出 {len(codes)} 只候选标的")

        portfolio = build_portfolio(
            codes=codes,
            method=args.method,
            name=args.name or f"portfolio_{datetime.now().strftime('%Y%m%d')}",
        )

        if "error" in portfolio:
            print(f"组合构建失败: {portfolio['error']}")
            return

        # 打印
        _print_portfolio(portfolio)

        # 保存
        if args.save:
            save_portfolio_snapshot(portfolio)
            print(f"组合已保存到数据库: {portfolio['name']}")

    elif args.action == "backtest":
        print(f"运行简化回测...")
        # 从数据取得组合权重
        from TG_trading_sys.portfolio.monitor import get_snapshot
        from TG_trading_sys.data.cache import DataCache

        cache = DataCache()

        if args.codes:
            codes = [c.strip() for c in args.codes.split(",")]
            weights = {c: 1.0 / len(codes) for c in codes}
        else:
            # 从最新组合快照获取
            portfolios = list_portfolios()
            if portfolios:
                pf_name = portfolios[-1]["portfolio_name"]
                snap = get_snapshot(pf_name)
                codes = [h["code"] for h in snap.get("holdings", [])]
                weights = {h["code"]: h["weight"] / 100 for h in snap.get("holdings", [])}
                print(f"使用组合: {pf_name} ({len(codes)}只)")
            else:
                print("无可用组合，请用 --codes 指定标的")
                return

        result = simple_backtest(
            codes=codes, weights=weights,
            start_date=args.start or "2024-01-01",
            capital=args.capital,
            rebalance=args.rebalance,
        )

        if not result.get("success"):
            print(f"回测失败: {result.get('error', '')}")
            return

        print(f"\n{'='*50}")
        print(f"  回测结果")
        print(f"{'='*50}")
        print(summary_table(result["metrics"]))
        print(f"  交易记录: {len(result.get('trades', []))} 条")
        print(f"{'='*50}\n")

    elif args.action == "monitor":
        if args.name:
            pf_name = args.name
        else:
            portfolios = list_portfolios()
            if not portfolios:
                print("无可用组合")
                return
            pf_name = portfolios[-1]["portfolio_name"]

        snap = get_snapshot(pf_name)
        if "error" in snap:
            print(f"监控错误: {snap['error']}")
            return

        print(f"\n{'='*60}")
        print(f"  持仓监控 — {pf_name}")
        print(f"{'='*60}")
        print(f"  日期: {snap['date']}  持仓: {snap['n_holdings']}只")
        print(f"  总成本: {snap['total_cost']:,.0f}  →  当前市值: {snap['total_current_value']:,.0f}")
        pnl = snap['total_pnl']
        pnl_pct = snap['total_pnl_pct']
        print(f"  总盈亏: {'+' if pnl>0 else ''}{pnl:,.0f} ({pnl_pct:+.1f}%)")
        print(f"\n  {'代码':<10} {'名称':<10} {'股数':>8} {'成本':>10} {'现价':>10} {'盈亏':>12} {'权重':>8}")
        print(f"  {'-'*70}")
        for h in snap["holdings"]:
            print(f"  {h['code']:<10} {h['name']:<10} {h['shares']:>8} "
                  f"{h['cost']:>10,.0f} {h['current_price']:>10.2f} "
                  f"{h['pnl']:>+12.0f} {h['weight']:>7.1f}%")

        # 预警
        if snap.get("alerts"):
            print(f"\n  【预警】")
            for a in snap["alerts"]:
                icon = "🔴" if a["level"] == "danger" else "🟡"
                print(f"    {icon} {a['name']}({a['code']}): {a['message']}")

        print(f"{'='*60}\n")

    elif args.action == "list":
        portfolios = list_portfolios()
        if not portfolios:
            print("无保存的组合")
            return
        print(f"\n{'='*60}")
        print(f"  已保存组合")
        print(f"{'='*60}")
        for p in portfolios:
            cost = p.get("cost", 0) or 0
            print(f"  {p['portfolio_name']:<30} {p['n']}只  成本 {cost:,.0f}  {p.get('last_date', '')}")
        print(f"{'='*60}\n")


def _print_portfolio(portfolio: dict):
    """打印组合构建结果"""
    print(f"\n{'='*60}")
    print(f"  组合: {portfolio['name']}")
    print(f"{'='*60}")
    print(f"  方法: {portfolio['method']}  创建: {portfolio['created']}")
    stats = portfolio.get("stats", {})
    print(f"  持仓: {stats.get('n_stocks', 0)}只  "
          f"{stats.get('n_sectors', 0)}个行业  "
          f"Top3: {stats.get('top3_weight', 0)*100:.0f}%  "
          f"Top5: {stats.get('top5_weight', 0)*100:.0f}%")
    print(f"\n  {'代码':<10} {'名称':<10} {'权重':>8} {'行业':<12} {'PE':>8} {'市值':>10}")
    print(f"  {'-'*60}")
    for h in portfolio.get("holdings", []):
        print(f"  {h['code']:<10} {h['name']:<10} {h['weight']*100:>7.1f}% "
              f"{h.get('sector', '')[:12]:<12} {h.get('pe_ttm', 0):>8.1f} {h.get('market_cap_yi', 0):>8.0f}亿")

    # 验证结果
    val = portfolio.get("validation", {})
    if val.get("violations"):
        print(f"\n  ⚡ 约束违规:")
        for v in val["violations"]:
            print(f"     - {v}")
    if val.get("warnings"):
        print(f"\n  ⚠️ 警告:")
        for w in val["warnings"]:
            print(f"     - {w}")

    print(f"{'='*60}\n")


def cmd_sync(args):
    """数据同步命令"""
    from TG_trading_sys.data.sync import SyncManager

    mgr = SyncManager()

    if args.action == "stats":
        mgr.print_stats()
    elif args.action == "kline":
        codes = [c.strip() for c in args.codes.split(",") if c.strip()]
        mgr.sync_kline_batch(codes, lookback=args.lookback)
    elif args.action == "financials":
        codes = [c.strip() for c in args.codes.split(",") if c.strip()]
        mgr.sync_financials_batch(codes)
    else:
        print("支持的操作: stats, kline, financials")


def _print_screen_result(result, mode: str):
    """打印筛选结果"""
    modes_cn = {
        "value_growth": "价值+成长双维精选",
        "turnaround": "反转信号精选（扭亏/营收跃进/加速增长）",
        "quality_momentum": "质量+动量精选",
        "all": "全因子筛选",
    }
    title = modes_cn.get(mode, "多因子筛选结果")
    print(f"\n{'='*80}")
    print(f"  {title} — Top {len(result)}")
    print(f"{'='*80}")
    print(f"  {'排名':<5} {'代码':<10} {'名称':<10} {'行业':<14} {'评分':>8} {'PE':>8} {'市值':>10}")
    print(f"  {'-'*65}")

    for _, r in result.iterrows():
        rank = r.get("rank", "")
        code = r.get("code", "")
        name = r.get("name", "")[:10]
        industry = r.get("industry", "")[:14]
        score = r.get("composite_score", 0)
        pe = r.get("pe_ttm", 0) or 0
        mcap = r.get("market_cap_yi", 0) or 0
        print(f"  {rank:<5} {code:<10} {name:<10} {industry:<14} {score:>8.3f} {pe:>8.1f} {mcap:>8.0f}亿")

    print(f"{'='*80}\n")


def main():
    parser = argparse.ArgumentParser(
        description="TG-trading-sys V4.0 — A股综合投资决策·研究·管理系统",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python -m TG_trading_sys.cli val 688017                   估值分析
  python -m TG_trading_sys.cli val 600519 --html            生成估值HTML报告
  python -m TG_trading_sys.cli signal 688017          多策略择时信号
  python -m TG_trading_sys.cli screen --top 20              多因子筛选Top20
  python -m TG_trading_sys.cli screen --mode turnaround     反转信号精选
  python -m TG_trading_sys.cli screen --list-factors        列出所有因子
  python -m TG_trading_sys.cli portfolio build --top 10     构建组合
  python -m TG_trading_sys.cli portfolio backtest           回测组合
  python -m TG_trading_sys.cli portfolio monitor            监控持仓
  python -m TG_trading_sys.cli sync stats                   查看数据库统计
        """
    )
    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # ── val: 估值分析 ──
    p_val = subparsers.add_parser("val", help="个股估值分析")
    p_val.add_argument("code", help="股票代码（6位数字）")
    p_val.add_argument("--wacc", type=float, default=None,
                       help="折现率%%（如 9.5=9.5%%，默认自动估算）")
    p_val.add_argument("--terminal-growth", type=float, default=None,
                       help="永续增长率%%（如 3.0=3%%，默认3%%）")
    p_val.add_argument("--html", action="store_true", help="生成HTML报告")
    p_val.add_argument("--output", "-o", type=str, default=None, help="HTML输出路径")
    p_val.set_defaults(func=cmd_val)

    # ── screen: 多因子筛选 ──
    p_screen = subparsers.add_parser("screen", help="多因子选股筛选")
    p_screen.add_argument("--mode", type=str, default="all",
                          choices=["all", "value_growth", "turnaround", "quality_momentum"],
                          help="筛选模式 (默认all)")
    p_screen.add_argument("--universe", type=str, default="csi300_csi500",
                          help="标的池 (csi300/csi500/csi300_csi500)")
    p_screen.add_argument("--categories", type=str, default=None,
                          help="限定因子大类（逗号分隔: value,growth,quality,momentum）")
    p_screen.add_argument("--top-n", type=int, default=20, help="返回前N只")
    p_screen.add_argument("--no-neutralize", action="store_true", help="不做行业中性化")
    p_screen.add_argument("--list-factors", action="store_true", help="列出所有因子")
    p_screen.add_argument("--factor-category", type=str, default=None,
                          help="因子查看限定大类")
    p_screen.add_argument("--csv", type=str, default=None, help="CSV输出路径")
    p_screen.add_argument("--html", action="store_true", help="生成HTML报告")
    p_screen.add_argument("--html-output", type=str, default=None, help="HTML输出路径")
    p_screen.set_defaults(func=cmd_screen)

    # ── portfolio: 组合管理 ──
    p_pf = subparsers.add_parser("portfolio", help="组合构建&回测&监控")
    p_pf.add_argument("action", nargs="?", default="list",
                      choices=["build", "backtest", "monitor", "list"],
                      help="操作类型")
    p_pf.add_argument("--name", type=str, default=None, help="组合名称")
    p_pf.add_argument("--universe", type=str, default="csi300_csi500", help="标的池")
    p_pf.add_argument("--top-n", type=int, default=15, help="选股数量")
    p_pf.add_argument("--method", type=str, default="equal_weight",
                      choices=["equal_weight", "market_cap", "inv_volatility",
                               "risk_parity", "min_variance", "max_diversification"],
                      help="权重方法")
    p_pf.add_argument("--no-neutralize", action="store_true", help="不做行业中性化")
    p_pf.add_argument("--save", action="store_true", help="保存到数据库")
    p_pf.add_argument("--codes", type=str, default=None, help="手动指定标的（逗号分隔）")
    p_pf.add_argument("--start", type=str, default=None, help="回测起始日期")
    p_pf.add_argument("--capital", type=float, default=1_000_000, help="初始资金")
    p_pf.add_argument("--rebalance", type=str, default="monthly",
                      choices=["daily", "monthly", "quarterly"], help="再平衡频率")
    p_pf.set_defaults(func=cmd_portfolio)

    # ── signal: 多策略择时信号 ──
    p_signal = subparsers.add_parser("signal", help="多策略择时信号分析")
    p_signal.add_argument("code", help="股票代码（6位数字）")
    p_signal.set_defaults(func=cmd_signal)

    # ── sync: 数据同步 ──
    p_sync = subparsers.add_parser("sync", help="数据同步管理")
    p_sync.add_argument("action", nargs="?", default="stats",
                        choices=["stats", "kline", "financials"],
                        help="操作类型")
    p_sync.add_argument("--codes", type=str, default="",
                        help="股票代码（逗号分隔）")
    p_sync.add_argument("--lookback", type=int, default=250,
                        help="K线回溯天数")
    p_sync.set_defaults(func=cmd_sync)

    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        return

    args.func(args)


if __name__ == "__main__":
    main()
