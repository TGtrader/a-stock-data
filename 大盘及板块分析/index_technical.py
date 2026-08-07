"""
指数技术分析模块
===============
MA系统 / MACD / RSI / 布林带 / 支撑阻力 / 位置判断
"""
import numpy as np
import pandas as pd


def calc_ma(df, periods=[5, 10, 20, 60, 120, 250]):
    """计算多周期均线"""
    result = {}
    for p in periods:
        if len(df) >= p:
            result[f'MA{p}'] = float(df['close'].iloc[-p:].mean())
            result[f'MA{p}_prev'] = float(df['close'].iloc[-(p+1):-1].mean())
    return result


def ma_alignment(ma_dict):
    """均线排列状态: 多头/空头/缠绕"""
    mas = []
    for k in ['MA5','MA10','MA20','MA60','MA120']:
        if k in ma_dict:
            mas.append(ma_dict[k])
    if len(mas) < 3:
        return '数据不足'
    bullish = all(mas[i] > mas[i+1] for i in range(len(mas)-1))
    bearish = all(mas[i] < mas[i+1] for i in range(len(mas)-1))
    if bullish: return '多头排列'
    elif bearish: return '空头排列'
    else: return '均线缠绕'


def calc_macd(df, fast=12, slow=26, signal=9):
    """MACD计算"""
    close = df['close'].values
    ema_fast = pd.Series(close).ewm(span=fast).mean().values
    ema_slow = pd.Series(close).ewm(span=slow).mean().values
    dif = ema_fast - ema_slow
    dea = pd.Series(dif).ewm(span=signal).mean().values
    macd_bar = 2 * (dif - dea)
    return {
        'dif': round(float(dif[-1]), 2),
        'dea': round(float(dea[-1]), 2),
        'macd': round(float(macd_bar[-1]), 4),
        'dif_prev': round(float(dif[-2]), 2) if len(dif) >= 2 else None,
        'dea_prev': round(float(dea[-2]), 2) if len(dea) >= 2 else None,
        'signal': '金叉' if (dif[-2] < dea[-2] and dif[-1] > dea[-1]) else
                  ('死叉' if (dif[-2] > dea[-2] and dif[-1] < dea[-1]) else
                   ('多头' if dif[-1] > dea[-1] else '空头')),
    }


def calc_rsi(df, period=14):
    """RSI计算"""
    delta = df['close'].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return round(float(rsi.iloc[-1]), 1) if not pd.isna(rsi.iloc[-1]) else 50


def calc_bollinger(df, period=20, std=2):
    """布林带"""
    close = df['close']
    ma = close.rolling(period).mean()
    sigma = close.rolling(period).std()
    upper = ma + std * sigma
    lower = ma - std * sigma
    last_close = float(close.iloc[-1])
    last_upper = float(upper.iloc[-1])
    last_lower = float(lower.iloc[-1])
    last_ma = float(ma.iloc[-1])
    bandwidth = (last_upper - last_lower) / last_ma * 100 if last_ma > 0 else 0
    position = (last_close - last_lower) / (last_upper - last_lower) * 100 if last_upper != last_lower else 50
    return {
        'upper': round(last_upper, 2), 'mid': round(last_ma, 2), 'lower': round(last_lower, 2),
        'bandwidth': round(bandwidth, 1), 'position': round(position, 1),
        'status': '上轨附近' if position > 80 else ('下轨附近' if position < 20 else '中轨附近'),
    }


def support_resistance(df, lookback=60):
    """支撑阻力位识别(基于近期高低点+成交密集区)"""
    recent = df.iloc[-lookback:]
    high = float(recent['high'].max())
    low = float(recent['low'].min())
    close = float(df['close'].iloc[-1])
    # 简单支撑阻力: 近期高低点
    support = round(low, 2)
    resistance = round(high, 2)
    # 距支撑/阻力距离
    dist_support = (close - support) / close * 100 if close > 0 else 0
    dist_resistance = (resistance - close) / close * 100 if close > 0 else 0
    return {
        'support': support, 'resistance': resistance,
        'dist_support_pct': round(dist_support, 1),
        'dist_resistance_pct': round(dist_resistance, 1),
    }


def position_analysis(df):
    """当前价格在300日历史区间的位置"""
    close = float(df['close'].iloc[-1])
    high_300 = float(df['high'].max())
    low_300 = float(df['low'].min())
    range_300 = high_300 - low_300
    position_pct = (close - low_300) / range_300 * 100 if range_300 > 0 else 50
    # 距高点回撤
    drawdown = (high_300 - close) / high_300 * 100 if high_300 > 0 else 0
    return {
        'close': round(close, 2),
        'high_300d': round(high_300, 2),
        'low_300d': round(low_300, 2),
        'position_pct': round(position_pct, 1),
        'drawdown_from_high': round(drawdown, 1),
        'verdict': '高位' if position_pct > 80 else ('低位' if position_pct < 20 else '中位'),
    }


def intraday_pattern(df):
    """当日(最新K线)走势描述"""
    if len(df) < 1: return {}
    last = df.iloc[-1]
    o, h, l, c = float(last['open']), float(last['high']), float(last['low']), float(last['close'])
    if o == 0: return {}
    chg = (c - o) / o * 100
    upper_wick = (h - max(c, o)) / o * 100
    lower_wick = (min(c, o) - l) / o * 100
    body = abs(c - o) / o * 100  # 实体幅度

    # 描述
    if body < 0.3:
        shape = '十字星/窄幅震荡'
    elif c > o and upper_wick < body * 0.3:
        shape = '光头阳线(强势)'
    elif c < o and lower_wick < body * 0.3:
        shape = '光脚阴线(弱势)'
    elif lower_wick > body and c > o:
        shape = '探底回升(长下影)'
    elif upper_wick > body and c < o:
        shape = '冲高回落(长上影)'
    elif c > o:
        shape = '阳线'
    else:
        shape = '阴线'

    return {
        'open': round(o, 2), 'high': round(h, 2), 'low': round(l, 2), 'close': round(c, 2),
        'change_pct': round(chg, 2), 'body_pct': round(body, 2),
        'upper_wick_pct': round(upper_wick, 2), 'lower_wick_pct': round(lower_wick, 2),
        'shape': shape,
        'summary': f'{"高开" if o>df.iloc[-2]["close"] else ("低开" if o<df.iloc[-2]["close"] else "平开")}→{shape}, 振幅{h/l-1:.2%}'.replace('%', '%.2f' % ((h/l-1)*100)) if len(df)>=2 else shape,
    }


def trend_analysis(df):
    """多周期趋势分析(60/30/10/5日)"""
    close = df['close']
    periods = [60, 30, 10, 5]
    trends = {}
    for p in periods:
        if len(close) >= p:
            chg = (close.iloc[-1] - close.iloc[-p]) / close.iloc[-p] * 100
            y = close.iloc[-p:].values
            x = np.arange(p)
            slope = np.polyfit(x, y, 1)[0]
            slope_pct = slope / y.mean() * 100
            direction = '上涨' if slope > 0 else '下跌'
            trends[f'{p}日'] = {
                'change_pct': round(chg, 2),
                'slope_pct': round(slope_pct, 3),
                'direction': direction,
                'strength': '强' if abs(slope_pct) > 0.2 else ('中' if abs(slope_pct) > 0.05 else '弱'),
            }
    return trends


def volume_analysis(df):
    """成交量定量分析(均量对比+量能趋势)"""
    if len(df) < 20: return {}
    vol = df['vol']
    latest_vol = float(vol.iloc[-1])
    avg_5 = float(vol.iloc[-5:].mean())
    avg_20 = float(vol.iloc[-20:].mean())
    avg_60 = float(vol.iloc[-60:].mean()) if len(df) >= 60 else avg_20

    vol_ratio_5 = latest_vol / avg_5 if avg_5 > 0 else 1
    vol_ratio_20 = avg_5 / avg_20 if avg_20 > 0 else 1
    vol_ratio_60 = avg_20 / avg_60 if avg_60 > 0 else 1

    # 量能趋势
    if vol_ratio_20 > 1.3: vol_trend = '显著放量'
    elif vol_ratio_20 > 1.1: vol_trend = '温和放量'
    elif vol_ratio_20 > 0.9: vol_trend = '量能平稳'
    elif vol_ratio_20 > 0.7: vol_trend = '温和缩量'
    else: vol_trend = '显著缩量'

    # 量价配合判断
    close_chg_5 = (df['close'].iloc[-1] - df['close'].iloc[-5]) / df['close'].iloc[-5] * 100 if len(df) >= 5 else 0
    if close_chg_5 > 1 and vol_trend in ('显著放量','温和放量'):
        vol_price = '价涨量增(健康)'
    elif close_chg_5 > 1 and vol_trend in ('显著缩量','温和缩量'):
        vol_price = '价涨量缩(背离)'
    elif close_chg_5 < -1 and vol_trend in ('显著缩量','温和缩量'):
        vol_price = '价跌量缩(正常)'
    elif close_chg_5 < -1 and vol_trend in ('显著放量','温和放量'):
        vol_price = '价跌量增(恐慌抛售)'
    else:
        vol_price = '量价正常'

    return {
        'latest_vol': round(latest_vol, 0),
        'avg_vol_5d': round(avg_5, 0),
        'avg_vol_20d': round(avg_20, 0),
        'vol_ratio_vs_5d': round(vol_ratio_5 * 100, 1),    # 百分比
        'vol_ratio_5vs20': round(vol_ratio_20 * 100, 1),
        'vol_ratio_20vs60': round(vol_ratio_60 * 100, 1),
        'vol_trend': vol_trend,
        'vol_price_signal': vol_price,
    }


def comprehensive_technical(df):
    """综合技术分析"""
    result = {
        'date': str(df.index[-1]) if hasattr(df.index, '__getitem__') else '',
    }
    # MA
    ma = calc_ma(df)
    result['ma'] = ma
    result['ma_alignment'] = ma_alignment(ma)
    # MACD
    result['macd'] = calc_macd(df)
    # RSI
    result['rsi'] = calc_rsi(df)
    # Bollinger
    result['bollinger'] = calc_bollinger(df)
    # S/R
    result['sr'] = support_resistance(df)
    # Position
    result['position'] = position_analysis(df)
    # Intraday
    result['intraday'] = intraday_pattern(df)
    # Trend
    result['trend'] = trend_analysis(df)
    # Volume
    result['volume'] = volume_analysis(df)
    return result
