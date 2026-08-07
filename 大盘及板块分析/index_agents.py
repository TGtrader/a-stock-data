"""
多角色Agent观点生成模块
======================
四个角色从不同视角分析同一个指数:
  - 趋势跟踪者: 均线+MACD+ADX
  - 反转交易者: RSI+KDJ+布林带
  - 量价分析师: 威科夫VPA方法论(功能模块代码/量价分析)
  - 风控官: 波动率+回撤+VaR
"""
import numpy as np
import sys, os

# Pre-load VPA modules (威科夫量价分析)
_VPA_AVAILABLE = False
_vpa_trend = None
_vpa_signals = None
try:
    _VPA_ROOT = os.path.join(os.getcwd(), '功能模块代码')
    if os.path.exists(_VPA_ROOT) and _VPA_ROOT not in sys.path:
        sys.path.insert(0, _VPA_ROOT)
    from 量价分析.vpa_trend import analyze_trend as _vpa_trend
    from 量价分析.vpa_signals import analyze_signals as _vpa_signals
    _VPA_AVAILABLE = True
except Exception:
    pass


def agent_trend_follower(tech, name=''):
    """趋势跟踪者视角"""
    points = []
    score = 50
    ma_align = tech.get('ma_alignment', '')
    macd = tech.get('macd', {})
    trend = tech.get('trend', {})
    pos = tech.get('position', {})

    # 均线判断
    if ma_align == '多头排列':
        points.append('均线多头排列，趋势向上结构完整')
        score += 15
    elif ma_align == '空头排列':
        points.append('均线空头排列，趋势向下需谨慎')
        score -= 15
    else:
        points.append('均线缠绕，趋势方向不明确')

    # MACD判断
    macd_sig = macd.get('signal', '')
    if macd_sig == '多头':
        points.append('MACD处于多头区域，动能偏多')
        score += 10
    elif macd_sig == '金叉':
        points.append('MACD金叉信号，短期看多')
        score += 15
    elif macd_sig == '死叉':
        points.append('MACD死叉信号，短期看空')
        score -= 15
    else:
        points.append('MACD空头区域，动能偏空')
        score -= 10

    # 多周期趋势一致性
    t60 = trend.get('60日', {})
    t30 = trend.get('30日', {})
    t10 = trend.get('10日', {})
    if t60.get('direction') == t30.get('direction') == t10.get('direction') == '上涨':
        points.append('60/30/10日趋势一致向上，趋势共振')
        score += 10
    elif t60.get('direction') == t30.get('direction') == t10.get('direction') == '下跌':
        points.append('60/30/10日趋势一致向下，下跌趋势强化')
        score -= 10

    # 位置判断
    pos_v = pos.get('verdict', '')
    if pos_v == '低位':
        points.append('处于300日低位区间，中长期配置价值显现')
        score += 5
    elif pos_v == '高位':
        points.append('处于300日高位区间，追高风险较大')
        score -= 5

    score = max(0, min(100, score))
    verdict = '积极做多' if score >= 70 else ('偏多' if score >= 55 else ('观望' if score >= 45 else ('偏空' if score >= 30 else '回避')))
    return {'角色': '趋势跟踪者', '评分': score, '观点': verdict, '分析': '；'.join(points)}


def agent_reversal_trader(tech, name=''):
    """反转交易者视角"""
    points = []
    score = 50
    rsi = tech.get('rsi', 50)
    boll = tech.get('bollinger', {})
    sr = tech.get('sr', {})
    pos = tech.get('position', {})

    # RSI判断
    if rsi > 80:
        points.append(f'RSI={rsi}极度超买，短期回调概率大')
        score -= 20
    elif rsi > 70:
        points.append(f'RSI={rsi}超买区域，注意回调风险')
        score -= 10
    elif rsi < 20:
        points.append(f'RSI={rsi}极度超卖，反弹概率大')
        score += 20
    elif rsi < 30:
        points.append(f'RSI={rsi}超卖区域，关注反弹机会')
        score += 10
    else:
        points.append(f'RSI={rsi}处于中性区间')

    # 布林带
    boll_pos = boll.get('position', 50)
    boll_status = boll.get('status', '')
    if boll_status == '下轨附近':
        points.append('价格触及布林下轨，技术性反弹需求')
        score += 10
    elif boll_status == '上轨附近':
        points.append('价格触及布林上轨，技术性回调需求')
        score -= 10
    bw = boll.get('bandwidth', 5)
    if bw < 5:
        points.append(f'布林带宽{bw}%收窄，变盘临近')
        score += (5 if pos.get('verdict') == '低位' else 0)

    # 支撑阻力
    dist_s = sr.get('dist_support_pct', 10)
    dist_r = sr.get('dist_resistance_pct', 10)
    if dist_s < 3:
        points.append(f'距支撑位仅{dist_s}%，下方支撑较强')
        score += 5
    if dist_r < 3:
        points.append(f'距阻力位仅{dist_r}%，上方压力明显')
        score -= 5

    score = max(0, min(100, score))
    verdict = '超卖反弹' if score >= 70 else ('偏多' if score >= 55 else ('中性' if score >= 45 else ('偏空' if score >= 30 else '超买回调')))
    return {'角色': '反转交易者', '评分': score, '观点': verdict, '分析': '；'.join(points)}


def agent_volume_analyst(df, tech, name=''):
    """量价分析师视角 — 集成威科夫VPA方法论"""
    points = []
    score = 50

    # 使用威科夫VPA引擎（如果可用）
    vpa_ok = False
    try:
        import sys, os
        vpa_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '功能模块代码')
        if not os.path.exists(vpa_path):
            vpa_path = os.path.join(os.getcwd(), '功能模块代码')
        if vpa_path not in sys.path and os.path.exists(vpa_path):
            sys.path.insert(0, vpa_path)


        # VPA需要'volume'列名 + datetime索引
        df_vpa = df.copy()
        if 'vol' in df_vpa.columns and 'volume' not in df_vpa.columns:
            df_vpa = df_vpa.rename(columns={'vol': 'volume'})
        # VPA内部使用.strftime()，需要datetime索引
        if not hasattr(df_vpa.index, 'strftime'):
            import pandas as _pd
            df_vpa.index = _pd.to_datetime(df_vpa.index)

        vpa_t = _vpa_trend(df_vpa)
        vpa_s = _vpa_signals(df_vpa)

        # 威科夫阶段分析
        phase = vpa_t.get('phase', {}).get('phase', '')
        st_dir = vpa_t.get('short_term', {}).get('direction', '')
        st_strength = vpa_t.get('short_term', {}).get('strength', 0)
        alignment = vpa_t.get('alignment', {}).get('state', '')

        # 阶段解读
        phase_map = {
            '吸筹区': ('主力在低位收集筹码，量价特征偏多', 15),
            '上涨趋势': ('处于威科夫拉升阶段，量价配合健康', 20),
            '派发区': ('主力在高位派发筹码，量价背离需警惕', -15),
            '下跌趋势': ('处于威科夫下跌阶段，量价弱势', -20),
            '趋势运行中': ('趋势持续中，量价关系中性', 5),
        }
        phase_info = phase_map.get(phase, (f'威科夫阶段: {phase}', 0))
        points.append(phase_info[0])
        score += phase_info[1]

        # 短期趋势
        if st_dir == '上涨' and st_strength > 30:
            points.append(f'短期强势上涨(强度{st_strength})，量能支撑趋势')
            score += 10
        elif st_dir == '下跌' and st_strength > 30:
            points.append(f'短期趋势下跌(强度{st_strength})，量能偏弱')
            score -= 10
        else:
            points.append(f'短期{st_dir}(强度{st_strength})，方向待明朗')

        # 趋势共振
        if '多头共振' in str(alignment):
            points.append('多周期趋势共振向上，量价信号偏多')
            score += 10
        elif '空头共振' in str(alignment):
            points.append('多周期趋势共振向下，量价信号偏空')
            score -= 10

        # VPA信号分析(去重)
        recent_sigs = vpa_s.get('recent_signals', [])
        anomaly = vpa_s.get('latest_bar', {}).get('is_anomaly', False)
        sig_types = {}
        for s in recent_sigs[:12]:
            t = s['type']
            sig_types[t] = sig_types.get(t, 0) + 1

        reversal_count = sum(v for k, v in sig_types.items() if '反转' in k or '衰竭' in k)
        continue_count = sum(v for k, v in sig_types.items() if '延续' in k or '启动' in k)

        if reversal_count >= 3:
            points.append(f'威科夫信号: 检测到{reversal_count}个反转/衰竭信号，趋势可能转折')
            score -= 10 if reversal_count >= 5 else 5
        if continue_count >= 2:
            points.append(f'威科夫信号: {continue_count}个趋势延续信号，趋势健康')

        if anomaly:
            points.append('最新K线量价异常，威科夫方法提示关注')
            score -= 10

        vpa_ok = True
    except Exception:
        pass  # VPA不可用，回退到基本方法

    # 基本量价分析(威科夫不可用时的fallback或补充)
    if not vpa_ok:
        if len(df) >= 5:
            vol_col = 'volume' if 'volume' in df.columns else 'vol'
            recent5 = df.iloc[-5:]
            price_up_days = sum(1 for i in range(1, len(recent5))
                               if recent5['close'].iloc[i] > recent5['close'].iloc[i-1])
            if price_up_days >= 3:
                points.append('近5日涨多跌少，短期偏强')
                score += 5
            elif price_up_days <= 1:
                points.append('近5日涨少跌多，短期偏弱')
                score -= 5

        if len(df) >= 20:
            vol_col = 'volume' if 'volume' in df.columns else 'vol'
            avg_vol_10 = float(df[vol_col].iloc[-10:].mean())
            avg_vol_20 = float(df[vol_col].iloc[-20:].mean())
            vol_ratio = avg_vol_10 / avg_vol_20 if avg_vol_20 > 0 else 1
            if vol_ratio > 1.3:
                points.append(f'近10日均量放大至20日的{vol_ratio:.1f}倍')
                score += 10 if df['close'].iloc[-1] > df['close'].iloc[-10] else -5
            elif vol_ratio < 0.7:
                points.append(f'近10日均量萎缩至20日的{vol_ratio:.0%}')
                score -= 5

    if not points:
        points.append('量价关系中性，无明显信号')

    score = max(0, min(100, score))
    verdict = '量价健康' if score >= 65 else ('中性' if score >= 45 else ('量价背离' if score >= 30 else '量价恶化'))
    source = '威科夫VPA' if vpa_ok else '基本量价'
    return {'角色': f'量价分析师({source})', '评分': score, '观点': verdict, '分析': '；'.join(points)}


def agent_risk_manager(tech, df, name=''):
    """风控官视角"""
    points = []
    score = 50

    # 波动率
    if len(df) >= 20:
        returns = df['close'].pct_change().dropna()
        vol_20d = float(returns.iloc[-20:].std() * np.sqrt(252) * 100)
        vol_60d = float(returns.iloc[-60:].std() * np.sqrt(252) * 100) if len(returns) >= 60 else vol_20d

        if vol_20d > 40:
            points.append(f'年化波动率{vol_20d:.0f}%极高，风险敞口过大')
            score -= 20
        elif vol_20d > 25:
            points.append(f'年化波动率{vol_20d:.0f}%偏高，注意仓位控制')
            score -= 10
        elif vol_20d < 15:
            points.append(f'年化波动率{vol_20d:.0f}%较低，市场相对平稳')
            score += 5

        if vol_20d > vol_60d * 1.3:
            points.append('近期波动率显著放大，风险在上升')
            score -= 10

    # 最大回撤
    if len(df) >= 60:
        high_60 = df['high'].iloc[-60:].max()
        close = df['close'].iloc[-1]
        dd_60 = (high_60 - close) / high_60 * 100
        if dd_60 > 15:
            points.append(f'60日最大回撤{dd_60:.1f}%，深度回调中')
            score -= 10
        elif dd_60 > 10:
            points.append(f'60日回撤{dd_60:.1f}%，调整幅度较大')
            score -= 5

    # VaR估算
    if len(df) >= 60:
        returns = df['close'].pct_change().dropna().iloc[-60:]
        var95 = float(np.percentile(returns, 5))
        points.append(f'VaR(95%)={var95*100:.2f}%')

    # 位置风险
    pos = tech.get('position', {})
    if pos.get('verdict') == '高位':
        points.append('当前处于高位，下行空间大于上行空间')
        score -= 10

    score = max(0, min(100, score))
    verdict = '低风险' if score >= 65 else ('中等风险' if score >= 45 else ('高风险' if score >= 30 else '极高风险'))
    return {'角色': '风控官', '评分': score, '观点': verdict, '分析': '；'.join(points)}


def run_all_agents(tech, df, name=''):
    """运行全部四个角色"""
    agents = [
        agent_trend_follower(tech, name),
        agent_reversal_trader(tech, name),
        agent_volume_analyst(df, tech, name),
        agent_risk_manager(tech, df, name),
    ]
    # 综合评分
    avg_score = sum(a['评分'] for a in agents) / len(agents)
    return {
        'agents': agents,
        '综合评分': round(avg_score, 1),
        '综合观点': '偏多' if avg_score >= 55 else ('偏空' if avg_score <= 45 else '中性'),
    }
