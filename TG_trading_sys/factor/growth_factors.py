"""
成长因子 — EPS增速 / 营收增速 / 盈利加速度 / 扭亏反转 / 营收跃进 / 一致预期CAGR
==================================================================================
重点关注超预期和增速异常：
  - 扭亏反转：上期亏损→本期盈利，行业反转信号
  - 营收跃进：Q1营收/去年全年营收 >30%，尤其一季报说明爆发增长
  - 盈利加速度：本期增速 vs 上期增速差值，正向加速更优
  - 一致预期CAGR：来自同花顺/东财研报的分析师预期
"""

import logging
from typing import List, Optional
import pandas as pd
import numpy as np
from datetime import datetime

from ..data.cache import DataCache

logger = logging.getLogger("tg.factor.growth")


def compute_eps_growth_yoy(codes: List[str], cache: DataCache) -> pd.Series:
    """
    EPS（归母净利润）同比增长率。
    比较最近报告期 vs 去年同期报告期。
    """
    values = {}
    for code in codes:
        try:
            lrb_data = cache.get_financials(code, report_type="lrb")
            if not lrb_data or len(lrb_data) < 2:
                values[code] = np.nan
                continue

            current_np = _find_net_profit(lrb_data[0])
            # 找去年同期（报告期减1年的记录）
            prev_np = None
            current_period = lrb_data[0].get("report_date", "")
            target_year = str(int(current_period[:4]) - 1)
            for record in lrb_data[1:]:
                if record.get("report_date", "").startswith(target_year):
                    prev_np = _find_net_profit(record)
                    break

            if not prev_np:
                # fallback: 取前一期
                prev_np = _find_net_profit(lrb_data[1])

            if current_np and prev_np and prev_np != 0:
                growth = (current_np - prev_np) / abs(prev_np)
                # 限制极端值
                growth = max(-1.0, min(5.0, growth))
                values[code] = growth
            else:
                values[code] = np.nan
        except Exception as e:
            logger.debug(f"EPS增速计算失败 {code}: {e}")
            values[code] = np.nan

    return pd.Series(values, name="eps_growth_yoy")


def compute_revenue_growth_yoy(codes: List[str], cache: DataCache) -> pd.Series:
    """营业收入同比增长率"""
    values = {}
    for code in codes:
        try:
            lrb_data = cache.get_financials(code, report_type="lrb")
            if not lrb_data or len(lrb_data) < 2:
                values[code] = np.nan
                continue

            current_rev = _find_revenue(lrb_data[0])
            current_period = lrb_data[0].get("report_date", "")
            target_year = str(int(current_period[:4]) - 1)

            prev_rev = None
            for record in lrb_data[1:]:
                if record.get("report_date", "").startswith(target_year):
                    prev_rev = _find_revenue(record)
                    break
            if not prev_rev:
                prev_rev = _find_revenue(lrb_data[1])

            if current_rev and prev_rev and prev_rev > 0:
                growth = (current_rev - prev_rev) / prev_rev
                growth = max(-1.0, min(5.0, growth))
                values[code] = growth
            else:
                values[code] = np.nan
        except Exception as e:
            logger.debug(f"营收增速计算失败 {code}: {e}")
            values[code] = np.nan

    return pd.Series(values, name="revenue_growth_yoy")


def compute_earnings_acceleration(codes: List[str], cache: DataCache) -> pd.Series:
    """
    盈利加速度 — 本期增速减去上期增速。
    正值表示盈利在加速（即使增速为负但在收窄也算正向）。
    需要连续3期以上的数据。
    """
    values = {}
    for code in codes:
        try:
            lrb_data = cache.get_financials(code, report_type="lrb")
            if not lrb_data or len(lrb_data) < 3:
                values[code] = np.nan
                continue

            # 计算连续三期的净利润增长率
            growths = []
            for i in range(min(3, len(lrb_data) - 1)):
                np_cur = _find_net_profit(lrb_data[i])
                np_prev = _find_net_profit(lrb_data[i + 1])
                if np_cur and np_prev and np_prev != 0:
                    g = (np_cur - np_prev) / abs(np_prev)
                    growths.append(g)

            if len(growths) >= 2:
                # 加速度 = 最近增速 - 前次增速
                accel = growths[0] - growths[1]
                accel = max(-2.0, min(3.0, accel))
                values[code] = accel
            else:
                values[code] = np.nan
        except Exception as e:
            logger.debug(f"盈利加速度计算失败 {code}: {e}")
            values[code] = np.nan

    return pd.Series(values, name="earnings_acceleration")


def compute_turnaround(codes: List[str], cache: DataCache) -> pd.Series:
    """
    扭亏反转因子 — 识别"从亏转盈"信号。

    逻辑：
      - 上一报告期为亏损（净利润<0），本期盈利 → 得分=1.0（强反转信号）
      - 连续两期为亏损，本期亏损收窄 >50% → 得分=0.5（好转信号）
      - 本期首次盈利（近3期首次） → 得分=0.8
      - 其他 → 0
    """
    values = {}
    for code in codes:
        try:
            lrb_data = cache.get_financials(code, report_type="lrb")
            if not lrb_data or len(lrb_data) < 3:
                values[code] = 0.0
                continue

            recent_nps = []
            for record in lrb_data[:3]:
                np_val = _find_net_profit(record)
                recent_nps.append(np_val if np_val is not None else 0)

            current, prev1, prev2 = recent_nps[0], recent_nps[1], recent_nps[2]

            score = 0.0

            # 场景1：上期亏损 → 本期盈利 = 强扭亏
            if prev1 < 0 and current > 0:
                score = 1.0
            # 场景2：连续亏损但本期大幅收窄
            elif prev1 < 0 and current < 0 and prev2 < 0:
                loss_reduction = (abs(current) - abs(prev1)) / abs(prev1) if prev1 != 0 else 0
                if loss_reduction < -0.3:  # 亏损收窄30%以上
                    score = 0.5
            # 场景3：近3期首次盈利
            elif current > 0 and prev1 <= 0 and prev2 <= 0:
                score = 0.8

            values[code] = score
        except Exception as e:
            logger.debug(f"扭亏检测失败 {code}: {e}")
            values[code] = 0.0

    return pd.Series(values, name="turnaround")


def compute_revenue_leap(codes: List[str], cache: DataCache) -> pd.Series:
    """
    营收跃进因子 — 检测"Q1营收已超去年全年大部分"的爆发信号。

    逻辑：
      - 最新季报（尤其Q1）的单季营收 / 去年全年营收
      - 比例 >30% → 高弹性（尤其适用于Q1，说明单季就干了去年全年30%+）
      - 比例 >50% → 超级爆发
      - Q1达到>25%就是很强信号（季节性因素下Q1通常占比20-25%）

    注意：新浪财报返回的可能是累计值，需要拆分为单季。
    """
    values = {}
    current_year = datetime.now().year

    for code in codes:
        try:
            lrb_data = cache.get_financials(code, report_type="lrb")
            if not lrb_data or len(lrb_data) < 2:
                values[code] = 0.0
                continue

            # 找最新报告期
            latest = lrb_data[0]
            latest_date = latest.get("report_date", "")
            if not latest_date:
                values[code] = 0.0
                continue

            # 提取最新报告期营收
            latest_rev = _find_revenue(latest)
            if not latest_rev or latest_rev <= 0:
                values[code] = 0.0
                continue

            # 找去年同期的年报（全年营收）
            prev_year = str(int(latest_date[:4]) - 1)
            full_year_rev = None
            for record in lrb_data:
                rd = record.get("report_date", "")
                if rd.startswith(prev_year) and rd.endswith("1231"):
                    full_year_rev = _find_revenue(record)
                    break

            if not full_year_rev or full_year_rev <= 0:
                values[code] = 0.0
                continue

            # 如果是单季度报告，直接算比例
            # 如果是累计值，需要减去上年同期季度值
            quarter = int(latest_date[4:6]) if len(latest_date) >= 6 else 0

            # 简化：最新期营收 vs 去年全年营收
            ratio = latest_rev / full_year_rev

            # Q1 特殊处理：>25%就是强信号
            if quarter <= 3:  # Q1 (report_date ends with 0331)
                # 如果是Q1单季就达到了去年全年的25%+
                if ratio > 0.50:
                    score = 1.0    # 超级爆发
                elif ratio > 0.30:
                    score = 0.8    # 强信号
                elif ratio > 0.20:
                    score = 0.5    # 中等信号
                else:
                    score = 0.1
            else:
                # 非Q1
                if ratio > 0.70:
                    score = 0.8
                elif ratio > 0.50:
                    score = 0.5
                elif ratio > 0.30:
                    score = 0.3
                else:
                    score = 0.1

            values[code] = score
        except Exception as e:
            logger.debug(f"营收跃进计算失败 {code}: {e}")
            values[code] = 0.0

    return pd.Series(values, name="revenue_leap")


def compute_consensus_eps_cagr(codes: List[str], cache: DataCache) -> pd.Series:
    """
    一致预期 EPS 3年CAGR — 来自同花顺/东财研报。
    无覆盖的标的返回 NaN。
    """
    from ..valuation.earnings_forecast import get_earnings_forecast

    values = {}
    for code in codes:
        try:
            earnings = get_earnings_forecast(code)
            cagr = earnings.get("cagr_3y", 0)
            if cagr and cagr > -0.5:  # 排除极端负值
                values[code] = cagr
            else:
                values[code] = np.nan
        except Exception:
            values[code] = np.nan

    return pd.Series(values, name="consensus_eps_cagr")


# ── 辅助函数 ──

def _find_net_profit(record: dict) -> Optional[float]:
    """从利润表记录中提取净利润"""
    keys = ["归属于母公司股东的净利润", "归母净利润", "净利润"]
    for key in keys:
        val = record.get(key)
        if val is not None:
            try:
                if isinstance(val, str):
                    val = val.replace(",", "").strip()
                    if "万" in val:
                        val = float(val.replace("万", "")) * 10000
                    elif "亿" in val:
                        val = float(val.replace("亿", "")) * 100000000
                    else:
                        val = float(val)
                val = float(val)
                if abs(val) > 1e10:
                    val = val / 10000
                return val
            except (ValueError, TypeError):
                continue
    return None


def _find_revenue(record: dict) -> Optional[float]:
    """从利润表记录中提取营业收入"""
    keys = ["营业收入", "营业总收入", "一、营业收入", "一、营业总收入"]
    for key in keys:
        val = record.get(key)
        if val is not None:
            try:
                if isinstance(val, str):
                    val = val.replace(",", "").strip()
                    if "万" in val:
                        val = float(val.replace("万", "")) * 10000
                    elif "亿" in val:
                        val = float(val.replace("亿", "")) * 100000000
                    else:
                        val = float(val)
                val = float(val)
                if abs(val) > 1e10:
                    val = val / 10000
                return val
            except (ValueError, TypeError):
                continue
    return None
