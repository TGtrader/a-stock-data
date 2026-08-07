"""科创综指 (589680) 右侧趋势策略 v2。

核心认知:
  科创综指是次新 ETF(2025-04 上市), 信号稀疏 — 16 个月仅 4 个 ACCUMULATE 日。
  历史教训:
  1. 买太早: 2026-07-17 ACCUMULATE 日买入@1.516, 实际是暴跌集群开端
     7-17~7-20 连续 2 个 ACCUMULATE, 之后继续跌到 7-30 @1.374(-9.4%)
     → 集群中禁止左侧, 等右侧反弹确认
  2. 份额数据极弱(单日 ±0.05~1.25亿), 方向可用但幅度无意义
     → 右侧确认用 sd>0 做方向过滤, 但主证据是涨幅+量比+价格位置
  3. 阴跌底部(2025-11-21 @1.189, pp15 vr0.78 无信号日)靠"极低位+低量"识别
     → 保留极低位路径(卖压耗尽), 但必须非集群

算法:
  买入(4路径):
    P1 单日极端恐慌: 跌≥10%+ACCUMULATE+pp≤40+非集群 → 左侧买 (2025-04-07 -12.24%)
    P2 低位孤立吸筹: ACCUMULATE+pp≤35+非集群+距60日高点≥15天 → 左侧买
       (下跌末期才左侧, 2026-07-17 距高点仅13天被拦截)
    极低位: pp≤15+上市≥60天+非集群+vr<1.0 → 左侧买 (2025-11-21, 低量=卖压耗尽)
    P3 暴跌集群右侧: 10天≥2个ACCUMULATE → 等反弹确认
       反弹需: 涨≥2%+vr≥1.2+pp≤45+份额方向净流入, 跌破前低则作废
       (2026-07 集群, 避免集群中段入场和假反弹)
  卖出(1规则, 不用S1首日冲顶 — 5/20 pp100 冲顶后仍涨14%, 首日逃过早):
    S2 集群出货确认: DISTRIBUTE累计≥阈值(量价记忆)+当日份额净流出 → 卖
       (8/19, 6/22 两次成功, 需次数+资金流出双确认)
"""

import math

KC_CODE = "589680"

BUY_PP_MAX = 35
PANIC_DROP = -10.0
PANIC_PP_MAX = 40
EXTREME_PP = 15
EXTREME_VR_MAX = 1.0

SELL_PP_MIN = 80
SELL_VR_MIN = 1.4

CLUSTER_ACCUM = 2
CLUSTER_WINDOW = 10
HIGH_LOOKBACK = 60
DROP_EARLY_DAYS = 15
BOUNCE_CHG = 2.0
BOUNCE_VR = 1.2
BOUNCE_PP_MAX = 45

MIN_HOLD = 5
COOLDOWN = 3
VOL_LOOKBACK = 20
MIN_ETF_AGE = 60
TRADE_START = "2025-04-01"


def _count_accum(rows: list[dict], idx: int, window: int = CLUSTER_WINDOW) -> int:
    return sum(1 for j in range(max(0, idx - window + 1), idx + 1)
               if rows[j].get("trade_direction") == "ACCUMULATE")


def _days_since_60d_high(rows: list[dict], idx: int) -> int:
    lo = max(0, idx - HIGH_LOOKBACK + 1)
    high_close = max((rows[j].get("close_price") or 0) for j in range(lo, idx + 1))
    for j in range(idx, lo - 1, -1):
        if (rows[j].get("close_price") or 0) == high_close:
            return idx - j
    return HIGH_LOOKBACK


def run_kc_strategy(rows: list[dict]) -> dict:
    n = len(rows)
    if n < 30:
        return {"code": KC_CODE, "trades": [], "metrics": {}, "holding": False}

    closes = [r.get("close_price") or 0.0 for r in rows]
    etf_birth_idx = next((i for i, r in enumerate(rows) if r["date"] >= TRADE_START), 0)

    trades = []
    position = 0.0
    hold_days = 0
    cooldown = COOLDOWN
    sell_threshold = 1
    dist_count = 0
    waiting_reversal = False
    wait_low = None

    for i in range(n):
        row = rows[i]
        d = row["date"]
        close = closes[i]
        pp = row.get("price_position")
        td = row.get("trade_direction")
        vr = row.get("volume_ratio") or 0
        chg = row.get("change_pct") or 0
        sd = row.get("shares_delta_yi")

        if d < TRADE_START:
            continue

        cooldown += 1
        action = None
        reason = ""

        # ---- 买入 ----
        if position == 0 and cooldown >= COOLDOWN:
            is_accum = td == "ACCUMULATE"
            accum_count = _count_accum(rows, i)
            pp_low = pp is not None and pp <= BUY_PP_MAX
            days_high = _days_since_60d_high(rows, i)

            # P1: 单日极端恐慌 (非集群中, 左侧)
            if (is_accum and chg <= PANIC_DROP
                    and pp is not None and pp <= PANIC_PP_MAX
                    and accum_count < CLUSTER_ACCUM):
                action = "BUY"
                reason = f"恐慌抄底: 跌{chg:.1f}%+pp{pp:.0f}"

            # P2: 低位孤立吸筹 (下跌末期才左侧)
            elif (is_accum and pp_low and accum_count < CLUSTER_ACCUM
                  and days_high >= DROP_EARLY_DAYS):
                action = "BUY"
                reason = f"低位吸筹: pp{pp:.0f}+距高点{days_high}天"

            # 极低位: 低量=卖压耗尽 (KC特有, 需上市满60天 + 非集群)
            elif (pp is not None and pp <= EXTREME_PP and vr < EXTREME_VR_MAX
                  and (i - etf_birth_idx) >= MIN_ETF_AGE
                  and accum_count < CLUSTER_ACCUM):
                action = "BUY"
                reason = f"极低位: pp{pp:.0f}(卖压耗尽)"

            # P3: 暴跌集群 → 等待右侧确认
            elif accum_count >= CLUSTER_ACCUM:
                waiting_reversal = True
                wait_low = min((rows[j].get("close_price") or 0)
                               for j in range(max(0, i - CLUSTER_WINDOW + 1), i + 1))

        # ---- P3 右侧确认 ----
        if position == 0 and waiting_reversal and wait_low is not None:
            if close < wait_low:
                # 跌破前低 → 假反弹, 本次集群作废
                waiting_reversal = False
                wait_low = None
            else:
                accum_count = _count_accum(rows, i)
                cluster_ended = accum_count < CLUSTER_ACCUM or td != "ACCUMULATE"
                prev_chg = rows[i - 1].get("change_pct") or 0 if i > 0 else 0
                pp_ok = pp is not None and pp <= BOUNCE_PP_MAX
                money_ok = sd is not None and sd > 0  # 方向过滤: 份额净流入

                strong_bounce = (chg >= BOUNCE_CHG and vr >= BOUNCE_VR
                                 and pp_ok and money_ok)
                two_day_up = (cluster_ended and chg > 0 and prev_chg > 0
                              and vr > 1.0 and pp_ok and money_ok)

                if strong_bounce or two_day_up:
                    action = "BUY"
                    reason = (f"右侧反弹: 涨{chg:.1f}%+vr{vr:.1f}+份额{sd:.2f}亿"
                              if strong_bounce else
                              f"右侧连涨: 2天+放量+份额{sd:.2f}亿")
                    waiting_reversal = False
                    wait_low = None
                elif pp is not None and pp > 55:
                    waiting_reversal = False  # 价格回升太多, 重置
                    wait_low = None

        # ---- 卖出 ----
        if position == 1:
            hold_days += 1
            is_dist = td == "DISTRIBUTE"
            pp_high = pp is not None and pp >= SELL_PP_MIN
            vr_high = vr >= SELL_VR_MIN

            if is_dist and pp_high and vr_high:
                dist_count += 1

            # S2: 次数(量价记忆)+份额净流出 双确认
            if (hold_days >= MIN_HOLD and is_dist
                    and dist_count >= sell_threshold
                    and sd is not None and sd < 0):
                reason = (f"出货确认({dist_count}/{sell_threshold})"
                          f"+pp{pp:.0f}+份额{sd:.2f}亿流出")
                action = "SELL"

        if action == "BUY":
            position = 1.0
            hold_days = 0
            cooldown = 0
            dist_count = 0
            waiting_reversal = False
            wait_low = None
            vol = row.get("volume") or 0
            prev_vols = [rows[j].get("volume") or 0
                         for j in range(max(0, i - VOL_LOOKBACK), i)]
            avg_vol = sum(prev_vols) / len(prev_vols) if prev_vols else 1
            ratio = vol / avg_vol if avg_vol > 0 else 1.0
            sell_threshold = max(2, math.ceil(2 + ratio * 0.55))
            trades.append({"date": d, "action": "BUY", "price": close,
                           "reason": f"{reason} [阈值{sell_threshold}]"})
        elif action == "SELL":
            position = 0.0
            cooldown = 0
            trades.append({"date": d, "action": "SELL", "price": close,
                           "reason": reason})

    metrics = _calc_metrics(trades, closes[-1] if closes else 0, position)
    return {"code": KC_CODE, "trades": trades, "metrics": metrics,
            "holding": position > 0}


def _calc_metrics(trades: list[dict], last_close: float,
                  position: float) -> dict:
    rounds = []
    buy_price = None
    buy_date = None
    for t in trades:
        if t["action"] == "BUY":
            buy_price = t["price"]
            buy_date = t["date"]
        elif t["action"] == "SELL" and buy_price is not None:
            ret = (t["price"] - buy_price) / buy_price * 100
            rounds.append({
                "buy_date": buy_date, "sell_date": t["date"],
                "buy_price": buy_price, "sell_price": t["price"],
                "return_pct": round(ret, 2)})
            buy_price = None

    if position > 0 and buy_price is not None:
        ret = (last_close - buy_price) / buy_price * 100
        rounds.append({
            "buy_date": buy_date, "sell_date": None,
            "buy_price": buy_price, "sell_price": last_close,
            "return_pct": round(ret, 2)})

    total_ret = 1.0
    wins = 0
    for r in rounds:
        total_ret *= (1 + r["return_pct"] / 100)
        if r["return_pct"] > 0:
            wins += 1

    return {
        "rounds": rounds,
        "total_return_pct": round((total_ret - 1) * 100, 2),
        "round_count": len(rounds),
        "win_count": wins,
        "win_rate": round(wins / len(rounds) * 100, 1) if rounds else 0,
        "trade_count": len(trades),
    }
