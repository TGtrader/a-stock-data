"""
V3 深度分析 HTML 报告生成器
=============================
叙事结构报告，按读者逻辑展开：
  执行摘要 → 业务深度 → 财务诊断 → 估值定价 → 技术资金面 → 综合结论

V3 新增:
  - 研报对照表（机构评级/目标价/EPS预测 vs 我们的估值）
  - 量价关系卡片（量比/放量缩量/背离）
  - 资金流趋势仪表（主力/大单/小单结构）
  - 综合结论与六维度评级
"""
import sys, os, io, json
os.environ['PYTHONIOENCODING'] = 'utf-8'
sys.path.insert(0, '.')
if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from datetime import datetime

# Load V3 collected data
DATA_FILE = 'data/deep_reports/all_reports_v3.json'
if not os.path.exists(DATA_FILE):
    # Fallback to V2
    DATA_FILE = 'data/deep_reports/all_reports.json'
    print(f"V3数据不存在，使用V2: {DATA_FILE}")

with open(DATA_FILE, 'r', encoding='utf-8') as f:
    all_reports = json.load(f)

DATE = datetime.now().strftime('%Y-%m-%d')

# ═══════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════

def verdict_color(verdict):
    if '强烈做多' in str(verdict): return '#00e676'
    if '做多' in str(verdict): return '#69f0ae'
    if '偏多' in str(verdict): return '#ffd740'
    if '观望' in str(verdict): return '#90a4ae'
    if '偏空' in str(verdict): return '#ff9100'
    if '做空' in str(verdict): return '#ff5252'
    return '#90a4ae'

def mos_color(mos):
    if mos is None: return '#90a4ae'
    if mos > 20: return '#00e676'
    if mos > 5: return '#69f0ae'
    if mos > -10: return '#ffd740'
    if mos > -25: return '#ff9100'
    return '#ff5252'

def pe_color(pe):
    if pe <= 0: return '#90a4ae'
    if pe < 15: return '#00e676'
    if pe < 25: return '#69f0ae'
    if pe < 40: return '#ffd740'
    return '#ff5252'

def flow_color(val, unit='亿'):
    if val > 1: return '#00e676'
    if val > 0: return '#69f0ae'
    if val > -1: return '#ffd740'
    if val > -5: return '#ff9100'
    return '#ff5252'

def safe_num(v, default='N/A', fmt='.1f'):
    if v is None: return default
    try: return f'{float(v):{fmt}}'
    except: return str(v)

def safe_pct(v):
    if v is None: return 'N/A'
    try: return f'{float(v):+.1f}%'
    except: return str(v)

def safe_int(v, default='N/A'):
    if v is None: return default
    try: return f'{int(v)}'
    except: return str(v)

def _vpa_phase_desc(phase, direction):
    """将VPA通用阶段名映射为结合趋势方向的具体描述"""
    dir_text = direction if direction else ""
    mapping = {
        "趋势运行中": f"{dir_text}趋势持续中" if dir_text else "趋势运行中",
        "accumulation": f"底部吸筹（{dir_text}）" if dir_text else "底部吸筹阶段",
        "distribution": f"高位派发（{dir_text}）" if dir_text else "高位派发阶段",
        "markup": f"主升浪拉升中（{dir_text}）" if dir_text else "拉升阶段",
        "markdown": f"下跌趋势中（{dir_text}）" if dir_text else "下跌阶段",
        "trending": f"{dir_text}趋势延续" if dir_text else "趋势延续",
    }
    return mapping.get(str(phase), f"{dir_text}{phase}" if dir_text else str(phase))

# ═══════════════════════════════════════════════
# Stock card builder
# ═══════════════════════════════════════════════

def build_stock_card(code, r):
    basic = r.get('basic', {})
    tech = r.get('technical', {})
    val = r.get('valuation', {})
    risk = r.get('risk', {})
    research = r.get('research', {})
    mf = r.get('moneyflow', {})

    price = basic.get('price', 0)
    pe = basic.get('pe_ttm', 0)
    pb = basic.get('pb', 0)
    mcap = basic.get('mcap_yi', 0)
    verdict = tech.get('verdict', 'N/A')
    mos = val.get('margin_of_safety_pct')
    mos_v = val.get('margin_verdict', '')

    # 研报摘要
    r_stats = (research or {}).get('stats') or {}
    r_badge = ''
    if r_stats:
        total = r_stats.get('total', 0)
        buys = r_stats.get('rating_dist', {}).get('买入', 0)
        target = r_stats.get('target_mean')
        r_badge = f'<span class="tag">研报{total}篇</span>'
        if buys: r_badge += f'<span class="tag tag-buy">{buys}家买入</span>'
        if target: r_badge += f'<span class="tag">目标{target:.0f}</span>'

    # 资金流摘要
    mf_stats = (mf or {}).get('stats') or {}
    mf_badge = ''
    if mf_stats:
        mf_badge = f'<span class="tag">主力{mf_stats.get("direction","")}{abs(mf_stats.get("main_net_20d_yi",0)):.1f}亿</span>'

    eps_data = r.get('consensus', {})
    var95 = risk.get('var_95_pct', 0)
    vol = risk.get('annual_vol', 0)

    return f'''
    <div class="stock-card" id="card-{code}">
        <div class="card-header">
            <span class="stock-code">{code}</span>
            <span class="stock-name">{r['name']}</span>
            <span class="stock-sw2">{r['sw2']}</span>
        </div>
        <div class="card-body">
            <div class="card-metrics">
                <div class="metric">
                    <div class="metric-value" style="color:{pe_color(pe)}">{price:.2f}</div>
                    <div class="metric-label">现价</div>
                </div>
                <div class="metric">
                    <div class="metric-value" style="color:{pe_color(pe)}">{pe:.1f}</div>
                    <div class="metric-label">PE(TTM)</div>
                </div>
                <div class="metric">
                    <div class="metric-value">{pb:.2f}</div>
                    <div class="metric-label">PB</div>
                </div>
                <div class="metric">
                    <div class="metric-value">{mcap:.0f}亿</div>
                    <div class="metric-label">市值</div>
                </div>
                <div class="metric">
                    <div class="metric-value" style="color:{verdict_color(verdict)}">{verdict}</div>
                    <div class="metric-label">择时信号</div>
                </div>
                <div class="metric">
                    <div class="metric-value" style="color:{mos_color(mos)}">{safe_pct(mos)}</div>
                    <div class="metric-label">安全边际</div>
                </div>
            </div>
            <div class="card-tags">
                {r_badge}
                {mf_badge}
                {f'<span class="tag tag-verdict">{mos_v}</span>' if mos_v else ''}
                {f'<span class="tag">波动率{vol:.0f}%</span>' if vol else ''}
            </div>
            <a href="#detail-{code}" class="card-link">查看深度分析 →</a>
        </div>
    </div>'''


# ═══════════════════════════════════════════════
# Detail section builder (V3 Narrative Structure)
# ═══════════════════════════════════════════════

def build_detail_section(code, r):
    basic = r.get('basic', {})
    tech = r.get('technical', {})
    val = r.get('valuation', {})
    fin = r.get('financials', {})
    risk = r.get('risk', {})
    wacc_d = r.get('wacc', {})
    eps_d = r.get('consensus', {})
    research = r.get('research', {})
    biz_data = r.get('business', {})
    mf = r.get('moneyflow', {})
    vpa = r.get('vpa', {})          # VPA引擎输出
    vp = vpa.get('simple', r.get('volume_price', {}))  # 简化指标（兜底）

    price = basic.get('price', 0)
    pe = basic.get('pe_ttm', 0)
    pb = basic.get('pb', 0)
    mcap = basic.get('mcap_yi', 0)

    verdict = tech.get('verdict', 'N/A')
    ma_score = tech.get('ma_score', 0)
    ma_align = tech.get('ma_alignment', '')

    final_val = val.get('final_value')
    mos = val.get('margin_of_safety_pct')
    mos_v = val.get('margin_verdict', '')
    dcf_val = val.get('dcf_per_share')
    peg = val.get('peg_value', {})
    pb_roe = val.get('pb_roe_value', {})
    scenarios = val.get('scenarios', {})
    research_cons = val.get('research_consensus', {})

    key_metrics = fin.get('key_metrics', {})
    balance = fin.get('balance', {})

    var95 = risk.get('var_95_pct', 0)
    cvar95 = risk.get('cvar_95_pct', 0)
    annual_vol = risk.get('annual_vol', 0)

    # 研报数据
    r_stats = (research or {}).get('stats') or {}
    r_reports = research.get('reports', [])

    # 资金流数据
    mf_stats = (mf or {}).get('stats') or {}

    sections = ''

    # ═══════════════════════════════════════════
    # 3.0 执行摘要
    # ═══════════════════════════════════════════
    # 生成一句话结论
    conclusion_parts = []
    # 估值判断
    if mos is not None:
        if mos > 10:
            conclusion_parts.append(f"估值层面处于<span style='color:#00e676'>低估区间</span>（安全边际{mos:.0f}%）")
        elif mos > -10:
            conclusion_parts.append(f"估值层面处于<span style='color:#ffd740'>合理区间</span>（安全边际{mos:.0f}%）")
        else:
            conclusion_parts.append(f"估值层面处于<span style='color:#ff5252'>高估区间</span>（安全边际{mos:.0f}%）")
    # 技术判断
    if '做多' in str(verdict):
        conclusion_parts.append(f"技术面<span style='color:#69f0ae'>{verdict}</span>")
    elif '偏多' in str(verdict):
        conclusion_parts.append(f"技术面<span style='color:#ffd740'>{verdict}</span>")
    elif '空' in str(verdict):
        conclusion_parts.append(f"技术面<span style='color:#ff5252'>{verdict}</span>")
    else:
        conclusion_parts.append(f"技术面<span style='color:#90a4ae'>{verdict}</span>")
    # 资金判断
    if mf_stats:
        direction = mf_stats.get('direction', '')
        net20 = mf_stats.get('main_net_20d_yi', 0)
        if abs(net20) > 1:
            conclusion_parts.append(f"近20日主力<span style='color:{flow_color(net20)}'>{direction}{abs(net20):.1f}亿</span>")

    conclusion_html = '；'.join(conclusion_parts) if conclusion_parts else '数据不足，无法生成综合结论'
    summary_verdict = mos_v if mos_v else '待评估'

    # 六维度快速评级标签
    def dim_tag(label, value, verdict, color):
        return f'<span class="dim-tag" style="border-color:{color};color:{color}">{label}: {verdict}</span>'

    mos_tag = dim_tag('估值', mos, f'安全边际{mos:+.0f}%' if mos else '待评估', mos_color(mos))
    tech_tag = dim_tag('技术', tech.get('verdict_score', 50),
                       f'{tech.get("verdict", "中性")} {tech.get("verdict_score", 50)}分',
                       '#00e676' if tech.get('verdict_score', 50) > 65 else ('#ffd740' if tech.get('verdict_score', 50) > 40 else '#ff5252'))
    mf_dir = mf_stats.get('direction', '') if mf_stats else ''
    mf_net = mf_stats.get('main_net_20d_yi', 0) if mf_stats else 0
    mf_color = '#00e676' if mf_net > 1 else ('#ffd740' if mf_net > -1 else '#ff5252')
    mf_tag = dim_tag('资金', mf_net, f'主力{mf_dir}{abs(mf_net):.1f}亿/20日', mf_color)

    growth_data = r.get('growth', {})
    freq = r.get("moneyflow_tushare", {}).get("频率统计", {})
    np_w = growth_data.get('np_weighted', 0)
    grow_tag = dim_tag('成长', np_w, f'利润环比加权{np_w:+.1f}%', '#00e676' if np_w > 15 else ('#ffd740' if np_w > 5 else '#ff5252'))

    debt_r = balance.get('debt_ratio') if balance else None
    qual_tag = dim_tag('质量', debt_r, f'负债率{debt_r:.0f}%' if debt_r else '待评估', '#00e676' if debt_r and debt_r < 30 else ('#ffd740' if debt_r and debt_r < 60 else '#ff5252'))

    risk_tag = dim_tag('风险', annual_vol, f'年化波动{annual_vol:.0f}%', '#00e676' if annual_vol < 30 else ('#ffd740' if annual_vol < 50 else '#ff5252'))

    dim_tags = f'<div class="dim-tags-row">{mos_tag}{tech_tag}{mf_tag}{grow_tag}{qual_tag}{risk_tag}</div>'

    sections += f'''
    <div class="exec-summary">
        <div class="exec-left">
            <div class="exec-verdict" style="color:{mos_color(mos)}">{summary_verdict}</div>
            <div class="exec-price">{price:.2f}<span style="font-size:14px;color:#8b949e"> 元</span></div>
            <div class="exec-target">目标价: {safe_num(final_val, 'N/A', '.2f')} 元</div>
        </div>
        <div class="exec-right">
            <div class="exec-conclusion">{conclusion_html}</div>
            <div class="dim-tags-container">{dim_tags}</div>
        </div>
    </div>'''

    # ═══════════════════════════════════════════
    # 3.1 公司业务深度
    # ═══════════════════════════════════════════
    f10_text = biz_data.get('f10_summary', '')
    biz_source = biz_data.get('source', '')
    annual_reports = biz_data.get('annual_reports', [])

    # 优先使用F10（非空且非纯空白），否则用硬编码
    f10_usable = f10_text and f10_text.strip() and len(f10_text.strip()) > 10 and '所属行业' not in f10_text
    biz_display = f10_text if f10_usable else r.get('biz_hardcoded', '')
    biz_source = biz_data.get('source', '') if f10_usable else '分析团队整理'
    comp_display = r.get('comp_hardcoded', '') if not f10_usable else ''

    sections += f'''
    <div class="detail-block">
        <h3>🏭 公司业务深度</h3>
        <div class="block-content">
            <div class="biz-section">
                <div class="biz-label">主营业务</div>
                <div class="biz-text">{biz_display}</div>
                {f'<div class="biz-source">数据来源: {biz_source}</div>' if biz_source else ''}
            </div>'''

    if comp_display:
        sections += f'''
            <div class="biz-section" style="margin-top:16px">
                <div class="biz-label">行业竞争格局</div>
                <div class="biz-text">{comp_display}</div>
            </div>'''

    # F10 最新提示（年报摘要补充）
    f10_tips = biz_data.get('f10_tips', '')
    f10_events = biz_data.get('f10_events', '')
    if f10_tips and len(f10_tips) > 50:
        sections += f'''
            <div class="biz-section" style="margin-top:16px">
                <div class="biz-label">F10 最新提示</div>
                <div class="biz-text" style="font-size:13px;max-height:300px;overflow-y:auto">{f10_tips[:1500]}</div>
            </div>'''
    if f10_events and len(f10_events) > 50:
        sections += f'''
            <div class="biz-section" style="margin-top:12px">
                <div class="biz-label">近期大事</div>
                <div class="biz-text" style="font-size:12px;max-height:200px;overflow-y:auto;color:#8b949e">{f10_events[:1000]}</div>
            </div>'''

    # 年报链接
    if annual_reports:
        sections += '''
            <div class="biz-section" style="margin-top:16px">
                <div class="biz-label">最新年报</div>
                <div class="biz-text">'''
        for ar in annual_reports[:2]:
            sections += f'<div><a href="{ar["url"]}" target="_blank" style="color:#58a6ff">{ar["title"]}</a> <span style="color:#8b949e;font-size:12px">({ar["date"]})</span></div>'
        sections += '</div></div>'

    sections += '''
        </div>
    </div>'''

    # ═══════════════════════════════════════════
    # 3.2 财务健康诊断
    # ═══════════════════════════════════════════
    report_period = key_metrics.get('report_period', '') or fin.get('analysis_date', '')
    report_period_label = f'最新报告期: {report_period}' if report_period else ''

    rev_str = f'{key_metrics.get("revenue", 0)/10000:.1f}亿' if key_metrics.get('revenue') else 'N/A'
    np_str = f'{key_metrics.get("net_profit", 0)/10000:.1f}亿' if key_metrics.get('net_profit') else 'N/A'
    ta_str = f'{balance.get("total_assets", 0)/10000:.1f}亿' if balance.get('total_assets') else 'N/A'
    eq_str = f'{balance.get("equity", 0)/10000:.1f}亿' if balance.get('equity') else 'N/A'
    debt_ratio = balance.get('debt_ratio')
    cash_str = f'{balance.get("cash", 0)/10000:.1f}亿' if balance.get('cash') else 'N/A'
    roe = safe_num(key_metrics.get('net_profit', 0) / balance.get('equity', 1) * 100 if balance.get('equity') else None, 'N/A', '.1f')

    fin_health = ''
    if debt_ratio is not None:
        if debt_ratio < 30:
            fin_health = '低负债，<span style="color:#00e676">财务结构稳健</span>'
        elif debt_ratio < 60:
            fin_health = '中等负债，<span style="color:#ffd740">财务结构合理</span>'
        else:
            fin_health = '高负债，<span style="color:#ff5252">需关注偿债压力</span>'

    sections += f'''
    <div class="detail-block">
        <h3>📊 财务健康诊断 <span style="font-size:12px;color:#8b949e;font-weight:normal">({report_period_label})</span></h3>
        <p class="section-summary">{fin_health} | 数据来源: 新浪财报三表</p>
        <div class="fin-grid">
            <div class="fin-card">
                <div class="fin-card-title">收入规模</div>
                <div class="fin-card-val">{rev_str}</div>
                <div class="fin-card-sub">营业收入</div>
            </div>
            <div class="fin-card">
                <div class="fin-card-title">盈利能力</div>
                <div class="fin-card-val">{np_str}</div>
                <div class="fin-card-sub">归母净利润 | ROE {roe}%</div>
            </div>
            <div class="fin-card">
                <div class="fin-card-title">资产规模</div>
                <div class="fin-card-val">{ta_str}</div>
                <div class="fin-card-sub">总资产 | 净资产 {eq_str}</div>
            </div>
            <div class="fin-card">
                <div class="fin-card-title">偿债能力</div>
                <div class="fin-card-val" style="color:{'#00e676' if debt_ratio and debt_ratio < 40 else ('#ffd740' if debt_ratio and debt_ratio < 60 else '#ff5252')}">{safe_num(debt_ratio, 'N/A', '.1f')}%</div>
                <div class="fin-card-sub">资产负债率 | 现金 {cash_str}</div>
            </div>
        </div>
        <p style="color:#8b949e;font-size:12px;margin-top:12px">数据来源: 新浪财报三表(利润表/资产负债表/现金流量表)，共 {fin.get('lrb',{}).get('reports',0)} 期</p>
    </div>'''

    # ═══════════════════════════════════════════
    # 3.3 估值定价
    # ═══════════════════════════════════════════
    sections += f'''
    <div class="detail-block">
        <h3>💰 估值定价</h3>
        <p class="section-summary">综合估值 <strong style="color:{mos_color(mos)}">{safe_num(final_val, 'N/A', '.2f')} 元</strong>，当前价 {price:.2f} 元，安全边际 <strong style="color:{mos_color(mos)}">{safe_pct(mos)}</strong> — {mos_v}</p>

        <div class="val-grid">
            <div class="val-card">
                <div class="val-title">DCF 估值</div>
                <div class="val-number">{safe_num(dcf_val, 'N/A', '.2f')} 元</div>
                <div class="val-sub">WACC {safe_num(wacc_d.get('wacc',0)*100, 'N/A', '.1f')}%</div>
            </div>
            <div class="val-card">
                <div class="val-title">PE-PEG 估值</div>
                <div class="val-number">{safe_num(peg.get('fair_value'), 'N/A', '.2f')} 元</div>
                <div class="val-sub">{peg.get('verdict', '')}</div>
            </div>
            <div class="val-card">
                <div class="val-title">PB-ROE 估值</div>
                <div class="val-number">{safe_num(pb_roe.get('fair_value'), 'N/A', '.2f')} 元</div>
                <div class="val-sub">ROE {safe_num(pb_roe.get('roe_pct'), 'N/A', '.1f')}% | 合理PB {safe_num(pb_roe.get('fair_pb'), 'N/A', '.1f')}</div>
            </div>
            <div class="val-card">
                <div class="val-title">机构一致目标价</div>
                <div class="val-number">{safe_num(research_cons.get('avg_target') or (r_stats.get('target_mean') if r_stats else None), 'N/A', '.2f')} 元</div>
                <div class="val-sub">{research_cons.get('count', r_stats.get('total', 0) if r_stats else 0)}家机构覆盖</div>
            </div>
        </div>'''

    # 情景分析
    if scenarios:
        sections += '<div class="scenario-row">'
        for sname, sdata in scenarios.items():
            cv = sdata.get('composite_value', 'N/A')
            up = sdata.get('upside_pct')
            up_str = f'{up:+.1f}%' if up is not None else 'N/A'
            sections += f'''
            <div class="scenario-card">
                <div class="sc-title">{sname}</div>
                <div class="sc-value">{safe_num(cv, 'N/A', '.2f')}</div>
                <div class="sc-upside">{up_str}</div>
            </div>'''
        sections += '</div>'

    # ── 研报观点综合 ──
    research_synth = research.get('synthesis')
    if research_synth:
        narrative = research_synth.get('narrative', '')
        viewpoint_groups = research_synth.get('viewpoint_groups', {})
        implied = research_synth.get('implied_targets', {})

        # 主要叙事
        sections += f'''
        <div class="research-synthesis">
            <div class="section-subtitle">📝 券商研报综合分析</div>
            <div class="synth-narrative">{narrative}</div>'''

        # 隐含目标价
        if implied.get('total_estimates', 0) > 0:
            pe_used = implied.get('pe_used', 0)
            pe_source = implied.get('pe_source', '')
            upside = implied.get('upside_pct')
            upside_str = f'（上涨空间{upside:+.1f}%）' if upside is not None else ''
            sections += f'''
            <div class="implied-target-box">
                <div class="implied-target-main">
                    <div>机构综合目标价</div>
                    <div class="implied-big">{implied.get("target_mean", "N/A")}元</div>
                    <div>区间 {implied.get("target_low", "-")}～{implied.get("target_high", "-")}元 {upside_str}</div>
                </div>
                <div class="implied-target-detail">
                    <div>明确目标价: {implied.get("explicit_count", 0)}篇</div>
                    <div>EPS推算: {implied.get("total_estimates", 0) - implied.get("explicit_count", 0)}篇</div>
                    <div>推算PE: {pe_used}x（{pe_source}）</div>
                </div>
            </div>'''

        # 观点分组
        for group_name, items in viewpoint_groups.items():
            if items:
                items_html = ''.join([f'<span class="viewpoint-tag">{item}</span>' for item in items[:8]])
                sections += f'''
                <div class="viewpoint-group">
                    <span class="viewpoint-group-name">{group_name}</span>
                    <div class="viewpoint-tags">{items_html}</div>
                </div>'''

        # 最近研报结构化观点
        recent_views = research_synth.get('recent_views', [])
        if recent_views:
            sections += '''
            <div class="section-subtitle" style="margin-top:16px">📄 近期研报观点摘录</div>
            <div class="synth-views">'''
            for rv in recent_views[:6]:
                drivers_str = ' | '.join(rv.get('growth_drivers', [])[:3]) if rv.get('growth_drivers') else ''
                earnings = rv.get('earnings_signal', '')
                sections += f'''
                <div class="synth-view-item">
                    <div class="synth-view-header">
                        <span class="synth-view-org">{rv.get("org", "")}</span>
                        <span class="synth-view-date">{rv.get("date", "")}</span>
                        <span class="synth-view-rating">[{rv.get("rating", "")}]</span>
                        {f'<span class="synth-view-signal">{earnings}</span>' if earnings else ''}
                    </div>
                    <div class="synth-view-title">"{rv.get('clean_title', '')}"</div>
                    {f'<div class="synth-view-drivers">{drivers_str}</div>' if drivers_str else ''}
                </div>'''
            sections += '</div>'
        sections += '</div>'

    # ── 研报PDF正文摘录 ──
    pdf_extracts = research.get('pdf_extracts', [])
    pdf_with_content = [p for p in pdf_extracts if p.get('core_summary') or p.get('full_text')]
    if pdf_with_content:
        sections += '''
        <div class="section-subtitle" style="margin-top:20px">📄 研报原文摘录（PDF提取）</div>
        <div class="pdf-extracts">'''
        for pdf_item in pdf_with_content[:3]:
            core = pdf_item.get('core_summary', '') or pdf_item.get('full_text', '')[:1500]
            if core:
                sections += f'''
                <div class="pdf-extract-item">
                    <div class="pdf-extract-header">
                        <span class="synth-view-org">{pdf_item.get("org", "")}</span>
                        <span class="synth-view-date">{pdf_item.get("date", "")}</span>
                        <span class="synth-view-rating">{pdf_item.get("title", "")[:60]}</span>
                    </div>
                    <div class="pdf-extract-text">{core[:1200]}</div>
                </div>'''
        sections += '</div>'

    # ── 研报对照表 ──
    if r_reports:
        sections += '''
        <div class="research-table-wrap">
            <div class="section-subtitle">📋 近期券商研报明细</div>
            <table class="research-table">
                <thead><tr>
                    <th>机构</th><th>日期</th><th>评级</th><th>目标价</th><th>2026E EPS</th><th>2027E EPS</th>
                </tr></thead><tbody>'''
        for rep in r_reports[:10]:
            target_str = f'{rep["target_price"]:.0f}' if rep.get('target_price') else '-'
            eps26_str = f'{rep["eps_2025"]:.2f}' if rep.get('eps_2025', 0) > 0 else '-'
            eps27_str = f'{rep["eps_2026"]:.2f}' if rep.get('eps_2026', 0) > 0 else '-'
            rating = rep.get('rating', '-')
            rating_style = 'color:#00e676' if '买入' in str(rating) else ('color:#ffd740' if '增持' in str(rating) else '')
            sections += f'''
                <tr>
                    <td>{rep.get('org', '-')}</td>
                    <td style="color:#8b949e">{rep.get('date', '-')}</td>
                    <td style="{rating_style}">{rating}</td>
                    <td>{target_str}</td>
                    <td>{eps26_str}</td>
                    <td>{eps27_str}</td>
                </tr>'''
        sections += '</tbody></table>'

        # 对比行
        if r_stats:
            our_val = final_val
            their_val = r_stats.get('target_mean')
            if our_val and their_val and their_val > 0:
                diff = (our_val - their_val) / their_val * 100
                diff_str = f'{"高" if diff > 0 else "低"}于机构均值{abs(diff):.0f}%'
            else:
                diff_str = 'N/A'
            sections += f'''
            <div class="research-compare">
                <span>📌 机构一致目标价均值: <strong>{safe_num(their_val, 'N/A', '.2f')} 元</strong></span>
                <span style="margin:0 16px">|</span>
                <span>我们的估值: <strong style="color:{mos_color(mos)}">{safe_num(our_val, 'N/A', '.2f')} 元</strong></span>
                <span style="margin:0 16px">|</span>
                <span>偏差: {diff_str}</span>
            </div>'''
        sections += '</div>'

    sections += '</div>'

    # ═══════════════════════════════════════════
    # 3.4 一致预期
    # ═══════════════════════════════════════════
    if eps_d:
        eps_hist = eps_d.get('hist_eps', [])
        hist_str = ' → '.join([f'{h["year"]}: {h["eps"]}' for h in eps_hist]) if eps_hist else ''
        current_yr = datetime.now().year
        eps_curr = eps_d.get(f'eps_{current_yr}', 0)
        eps_next = eps_d.get(f'eps_{current_yr+1}', 0)
        forward_pe = mcap * 10000 / (eps_curr * 10000) if eps_curr > 0 else 0

        sections += f'''
        <div class="detail-block">
            <h3>🔮 盈利预测与一致预期</h3>
            <div class="metric-row">
                <div class="mini-metric"><span class="mm-val">{eps_curr:.2f}</span><span class="mm-label">{current_yr}E EPS</span></div>
                <div class="mini-metric"><span class="mm-val">{eps_next:.2f}</span><span class="mm-label">{current_yr+1}E EPS</span></div>
                <div class="mini-metric"><span class="mm-val">{forward_pe:.1f}x</span><span class="mm-label">{current_yr}E PE</span></div>
                <div class="mini-metric"><span class="mm-val" style="font-size:14px">{hist_str}</span><span class="mm-label">历史EPS</span></div>
            </div>
            <p style="color:#8b949e;font-size:12px;margin-top:8px">数据来源: 同花顺一致预期 + 东财研报EPS（含异常检测）</p>
        </div>'''

    # ═══════════════════════════════════════════
    # 3.5 技术面与资金面
    # ═══════════════════════════════════════════
    sections += f'''
    <div class="detail-block">
        <h3>📈 技术面与资金面</h3>

        <!-- 均线系统 -->
        <div class="section-subtitle">均线形态</div>
        <div class="metric-row">
            <div class="mini-metric"><span class="mm-val" style="color:{verdict_color(verdict)}">{verdict}</span><span class="mm-label">综合信号</span></div>
            <div class="mini-metric"><span class="mm-val">{tech.get('verdict_score', 0)}/100</span><span class="mm-label">技术评分</span></div>
            <div class="mini-metric"><span class="mm-val">{ma_score}/100</span><span class="mm-label">均线评分</span></div>
            <div class="mini-metric"><span class="mm-val">{ma_align}</span><span class="mm-label">均线排列</span></div>
        </div>'''

    # ── VPA 量价分析（三维评级）──
    if vpa.get('vpa_available'):
        vpa_rating = vpa.get('rating', {})
        vpa_trend = vpa.get('trend', {})
        vpa_signals = vpa.get('signals', {})
        vpa_mf = vpa.get('money_flow_vpa') or {}

        rating_color = {'趋势做多': '#00e676', '偏多': '#69f0ae', '观望': '#ffd740', '偏空': '#ff9100', '持币/做空': '#ff5252'}
        r_color = rating_color.get(vpa_rating.get('rating', ''), '#90a4ae')

        # VPA 三维评级卡片
        sections += f'''
        <div class="section-subtitle" style="margin-top:16px">VPA 量价分析（Anna Coulling 方法论）</div>
        <div class="vpa-rating-card">
            <div class="vpa-main-rating">
                <div class="vpa-big-rating" style="color:{r_color}">{vpa_rating.get('rating', '-')}</div>
                <div class="vpa-score">{vpa_rating.get('score', '-')}/100 分</div>
            </div>
            <div class="vpa-dims">
                <div class="vpa-dim"><span>趋势</span><div class="vpa-dim-bar"><div style="width:{vpa_rating.get('trend_score',50)}%;background:#58a6ff"></div></div><span>{vpa_rating.get('trend_score',50)}</span></div>
                <div class="vpa-dim"><span>量价</span><div class="vpa-dim-bar"><div style="width:{vpa_rating.get('vpa_score',50)}%;background:#3fb950"></div></div><span>{vpa_rating.get('vpa_score',50)}</span></div>
                <div class="vpa-dim"><span>资金</span><div class="vpa-dim-bar"><div style="width:{vpa_rating.get('flow_score',50)}%;background:#ffd740"></div></div><span>{vpa_rating.get('flow_score',50)}</span></div>
            </div>
        </div>'''

        # 趋势详情
        st = vpa_trend.get('short_term', {})
        mt = vpa_trend.get('medium_term', {})
        al = vpa_trend.get('alignment', {})
        ph = vpa_trend.get('phase', {})
        sr = vpa_trend.get('sr_levels', {})
        supports = ', '.join([f'{s:.2f}' for s in (sr.get('support', []) or [])[:2]]) if sr.get('support') else '-'
        resists = ', '.join([f'{s:.2f}' for s in (sr.get('resistance', []) or [])[:2]]) if sr.get('resistance') else '-'

        sections += f'''
        <div class="vpa-detail-grid">
            <div class="vpa-detail-item">
                <div class="vpa-detail-label">短期趋势</div>
                <div class="vpa-detail-val">{st.get('direction', '-')} (强度{st.get('strength', '-')})</div>
                <div class="vpa-detail-sub">{st.get('summary', '')[:60]}</div>
            </div>
            <div class="vpa-detail-item">
                <div class="vpa-detail-label">中期趋势</div>
                <div class="vpa-detail-val">{mt.get('direction', '-')} (强度{mt.get('strength', '-')})</div>
                <div class="vpa-detail-sub">{mt.get('summary', '')[:60]}</div>
            </div>
            <div class="vpa-detail-item">
                <div class="vpa-detail-label">趋势共振</div>
                <div class="vpa-detail-val">{al.get('state', '-')}</div>
                <div class="vpa-detail-sub">{al.get('signal', '')}</div>
            </div>
            <div class="vpa-detail-item">
                <div class="vpa-detail-label">威科夫阶段</div>
                <div class="vpa-detail-val">{_vpa_phase_desc(ph.get('phase', ''), st.get('direction', ''))}</div>
                <div class="vpa-detail-sub">支撑: {supports} | 阻力: {resists}</div>
            </div>
        </div>'''

        # 近期信号（去重合并）
        recent_sigs = vpa_signals.get('recent_signals', [])
        signal_type_counts = {}
        if recent_sigs:
            for s in recent_sigs[:12]:
                t = s['type']
                if t not in signal_type_counts:
                    signal_type_counts[t] = {'desc': s['description'][:50], 'count': 1}
                else:
                    signal_type_counts[t]['count'] += 1
            sig_tags = ''.join([
                f'<span class="vpa-sig-tag vpa-sig-{t[:2]}">{t}{"×"+str(v["count"]) if v["count"]>1 else ""}: {v["desc"]}</span>'
                for t, v in signal_type_counts.items()
            ])
            sections += f'<div class="vpa-signals-row">{sig_tags}</div>'

        # 最新K线异常
        latest = vpa_signals.get('latest_bar', {})
        if latest.get('is_anomaly'):
            sections += f'''
            <div class="vpa-anomaly-warn">
                ⚠ 最新K线异常: {latest.get('anomaly_reason', '')} (量级: {latest.get('volume_level', '')}, 形态: {latest.get('candle_pattern', '')})
            </div>'''

        # 资金流VPA补充
        if vpa_mf and vpa_mf.get('available'):
            smart = vpa_mf.get('smart_retail', {})
            resonance = '共振看多' if vpa_mf.get('resonance_type') == 'bullish' else ('共振看空' if vpa_mf.get('resonance_type') == 'bearish' else '无共振')
            sections += f'''
            <div class="vpa-mf-extra">
                <span>VPA资金流: 连续{vpa_mf.get("continuous_flow",{}).get("direction","-")} | 最大流入{vpa_mf.get("continuous_flow",{}).get("max_in",0)}日/流出{vpa_mf.get("continuous_flow",{}).get("max_out",0)}日</span>
                {f'<span style="margin-left:16px">主力散户: {smart.get("type","")} {smart.get("desc","")}</span>' if smart.get('type') else ''}
                <span style="margin-left:16px">趋势共振: {resonance}</span>
            </div>'''

    # ── 简化量价关系（兜底 + 补充）──
    elif vp:
        vol_trend_color = '#00e676' if vp.get('vol_trend') == '放量' else ('#ff5252' if vp.get('vol_trend') == '缩量' else '#ffd740')
        divergence = vp.get('divergence', [])
        div_warning = f'<span style="color:#ff5252">⚠ 量价背离: {"; ".join(divergence)}</span>' if divergence else ''

        sections += f'''
        <div class="section-subtitle" style="margin-top:16px">量价关系</div>
        <div class="vp-card">
            <div class="vp-row">
                <div class="vp-item">
                    <div class="vp-val">{safe_int(vp.get('vol_5d_avg'))}</div>
                    <div class="vp-label">近5日均量(手)</div>
                </div>
                <div class="vp-item">
                    <div class="vp-val">{safe_int(vp.get('vol_20d_avg'))}</div>
                    <div class="vp-label">近20日均量(手)</div>
                </div>
                <div class="vp-item">
                    <div class="vp-val" style="color:{vol_trend_color}">{vp.get('vol_ratio_5v20', 1):.1f}x</div>
                    <div class="vp-label">量比 (5日/20日)</div>
                </div>
                <div class="vp-item">
                    <div class="vp-val" style="color:{vol_trend_color}">{vp.get('vol_trend', '-')}</div>
                    <div class="vp-label">量能趋势</div>
                </div>
            </div>
            <div class="vp-row" style="margin-top:12px">
                <div class="vp-item">
                    <div class="vp-val" style="color:#69f0ae">{vp.get('surge_up_days', 0)}天</div>
                    <div class="vp-label">放量上涨(近20日)</div>
                </div>
                <div class="vp-item">
                    <div class="vp-val" style="color:#ff5252">{vp.get('shrink_down_days', 0)}天</div>
                    <div class="vp-label">缩量下跌(近20日)</div>
                </div>
                <div class="vp-item" style="flex:2"></div>
            </div>
            {f'<div style="margin-top:10px;font-size:13px">{div_warning}</div>' if div_warning else ''}
        </div>'''

    # ── 资金流趋势 ──
    if mf_stats:
        net5 = mf_stats.get('main_net_5d_yi', 0)
        net20 = mf_stats.get('main_net_20d_yi', 0)
        net60 = mf_stats.get('main_net_60d_yi', 0)
        cons_in = mf_stats.get('consecutive_in', 0)
        cons_out = mf_stats.get('consecutive_out', 0)
        large_pct = mf_stats.get('large_order_pct', 0)
        direction = mf_stats.get('direction', '')

        cons_str = ''
        if cons_in >= 3:
            cons_str = f'主力连续<span style="color:#00e676">{cons_in}日净流入</span>'
        elif cons_out >= 3:
            cons_str = f'主力连续<span style="color:#ff5252">{cons_out}日净流出</span>'
        else:
            cons_str = '主力进出交错，无明显趋势'

        sections += f'''
        <div class="section-subtitle" style="margin-top:20px">资金流趋势（东财120日数据）</div>
        <div class="mf-dashboard">
            <div class="mf-main">
                <div class="mf-big-num" style="color:{flow_color(net20)}">{net20:+.2f}亿</div>
                <div class="mf-big-label">近20日主力净{direction}</div>
                <div class="mf-cons">{cons_str}</div>
            </div>
            <div class="mf-detail">
                <div class="mf-row">
                    <span>近5日</span>
                    <span style="color:{flow_color(net5)}">{net5:+.2f}亿</span>
                </div>
                <div class="mf-row">
                    <span>近20日</span>
                    <span style="color:{flow_color(net20)}">{net20:+.2f}亿</span>
                </div>
                <div class="mf-row">
                    <span>近60日</span>
                    <span style="color:{flow_color(net60)}">{net60:+.2f}亿</span>
                </div>
                <div class="mf-row">
                    <span>大单占比</span>
                    <span>{large_pct}%</span>
                </div>
            </div>
        </div>'''

    # ── VaR 风险度量 ──
    vol_level = '极高' if annual_vol > 60 else ('偏高' if annual_vol > 40 else ('中等' if annual_vol > 25 else '较低'))
    sections += f'''
        <div class="section-subtitle" style="margin-top:20px">风险度量</div>
        <div class="metric-row">
            <div class="mini-metric">
                <span class="mm-val" style="color:#ff9100">{var95:.1f}%</span>
                <span class="mm-label">VaR日(95%)</span>
            </div>
            <div class="mini-metric">
                <span class="mm-val" style="color:#ff5252">{cvar95:.1f}%</span>
                <span class="mm-label">CVaR日(95%)</span>
            </div>
            <div class="mini-metric">
                <span class="mm-val" style="color:#ff9100">{annual_vol:.0f}%</span>
                <span class="mm-label">年化波动率({vol_level})</span>
            </div>
            <div class="mini-metric">
                <span class="mm-val">{wacc_d.get('beta', 0):.2f}</span>
                <span class="mm-label">Beta系数</span>
            </div>
        </div>
        <div class="risk-explain">
            <strong>理解这些指标：</strong><br>
            <strong>VaR {var95:.1f}%</strong> = 95%概率下，持有一股该股票，单日亏损不超过{var95:.1f}%（约{price*var95/100:.2f}元）。<br>
            <strong>CVaR {cvar95:.1f}%</strong> = 当亏损已超过VaR时，平均会亏{cvar95:.1f}%。代表"尾部风险"。<br>
            <strong>波动率 {annual_vol:.0f}%</strong> = 年化标准差。A股科技股通常40-60%。<br>
            <strong>Beta {wacc_d.get('beta', 0):.2f}</strong> = 相对沪深300的波动倍数。
        </div>
    </div>'''

    # ═══════════════════════════════════════════
    # 3.6 六维度深度分析
    # ═══════════════════════════════════════════
    growth_data = r.get('growth', {})
    mf_tushare = r.get('moneyflow_tushare', {})

    sections += f'''
    <div class="detail-block">
        <h3>📐 六维度深度分析</h3>

        <!-- 估值维度 -->
        <div class="sixdim-card">
            <div class="sixdim-header" style="background:#1a237e44">💰 估值定价</div>
            <div class="sixdim-body">
                <p><strong>综合估值:</strong> {safe_num(final_val, 'N/A', '.2f')} 元 | 现价 {price:.2f} | 安全边际 {safe_pct(mos)} | <span style="color:{mos_color(mos)}">{mos_v}</span></p>
                <table class="sixdim-table">
                    <tr><th>方法</th><th>估值(元)</th><th>权重</th><th>说明</th></tr>'''

    for comp in val.get('estimate_components', []):
        sections += f'<tr><td>{comp["method"]}</td><td>{safe_num(comp["value"], "-", ".2f")}</td><td>{comp["weight"]}</td><td>{"DCF终值纠偏已启用" if comp["method"]=="DCF" else ("CAGR×合理PE" if comp["method"]=="PE-PEG" else ("ROE/Ke模型" if comp["method"]=="PB-ROE" else "机构一致预期"))}</td></tr>'

    sections += f'''
                </table>
                <p style="font-size:12px;color:#8b949e;margin-top:8px">
                DCF参数: WACC={safe_num(val.get("dcf", {}).get("wacc",0) if isinstance(val.get("dcf"), dict) else 0, "?", ".1f")}% | 永续g={safe_num(val.get("dcf", {}).get("terminal_growth",0) if isinstance(val.get("dcf"), dict) else 0, "?", ".1f")}% | 终值占比={safe_num(val.get("dcf", {}).get("terminal_value_ratio",0) if isinstance(val.get("dcf"), dict) else 0, "?", ".1f")}%
                {f'| ⚠{val.get("dcf", {}).get("terminal_value_warning","")}' if isinstance(val.get("dcf"), dict) and val.get("dcf", {}).get("terminal_value_warning") else ''}
                </p>
            </div>
        </div>

        <!-- 技术维度 -->
        <div class="sixdim-card">
            <div class="sixdim-header" style="background:#1b5e20 44">📈 技术分析</div>
            <div class="sixdim-body">
                <p><strong>综合信号:</strong> {verdict} (评分{tech.get("verdict_score",50)}/100, 置信度{tech.get("confidence",0)}%) |
                均线排列: {ma_align}</p>'''

    # VPA评分拆解
    if vpa.get('vpa_available'):
        vr = vpa.get('rating', {})
        sections += f'''
                <table class="sixdim-table">
                    <tr><th>VPA维度</th><th>评分</th><th>权重</th><th>含义</th></tr>
                    <tr><td>趋势分析</td><td>{vr.get("trend_score","-")}/100</td><td>40%</td><td>短期+中期趋势方向与强度，威科夫阶段判断</td></tr>
                    <tr><td>量价信号</td><td>{vr.get("vpa_score","-")}/100</td><td>30%</td><td>K线形态+成交量验证+序列信号(去重后{len(signal_type_counts) if signal_type_counts else 0}类)</td></tr>
                    <tr><td>资金流</td><td>{vr.get("flow_score","-")}/100</td><td>30%</td><td>连续资金流向+主力散户背离+趋势共振</td></tr>
                    <tr><td><strong>综合</strong></td><td><strong>{vr.get("score","-")}/100</strong></td><td>100%</td><td><strong>{vr.get("rating","-")}</strong></td></tr>
                </table>
                <p style="font-size:12px;color:#8b949e;margin-top:4px">趋势: {vpa.get("trend",{}).get("short_term",{}).get("direction","-")} |
                威科夫阶段: {_vpa_phase_desc(vpa.get("trend",{}).get("phase",{}).get("phase",""), vpa.get("trend",{}).get("short_term",{}).get("direction",""))}
                </p>'''
    else:
        sections += f'''
                <p style="font-size:12px;color:#8b949e">VPA量价引擎未覆盖此标的(数据不足)</p>'''

    sections += f'''
            </div>
        </div>

        <!-- 资金维度 -->
        <div class="sixdim-card">
            <div class="sixdim-header" style="background:#e6510044">💵 资金流向</div>
            <div class="sixdim-body">'''

    # 东财资金流
    if mf_stats:
        sections += f'''
                <p><strong>东财主力(120日):</strong> 5日净{mf_stats.get("main_net_5d_yi",0):.2f}亿 | 20日净{mf_stats.get("main_net_20d_yi",0):.2f}亿 | 连续流入{mf_stats.get("consecutive_in",0)}天/流出{mf_stats.get("consecutive_out",0)}天 | 大单占比{mf_stats.get("large_order_pct",0):.0f}%</p>'''

    # Tushare资金流
    mf_t = mf_tushare.get('trend', {})
    if mf_t:
        sections += f'''
                <p><strong>Tushare主力(统计期: {mf_tushare.get("统计期","")}):</strong></p>
                <table class="sixdim-table">
                    <tr><th>指标</th><th>数值</th><th>说明</th></tr>
                    <tr><td>统计天数</td><td>{freq.get("统计天数",0)}天</td><td>数据覆盖交易日数</td></tr>
                    <tr><td>主力净流入天数</td><td style="color:{'#00e676' if freq.get("主力净流入天数",0)>freq.get("主力净流出天数",0) else '#ff5252'}">{freq.get("主力净流入天数",0)}天</td><td>大单+特大单净买入>0的天数</td></tr>
                    <tr><td>主力净流出天数</td><td>{freq.get("主力净流出天数",0)}天</td><td>主力净卖出>0的天数</td></tr>
                    <tr><td>主力流入占比</td><td style="color:{'#00e676' if float(freq.get("主力流入占比","0%").replace("%",""))>50 else '#ff5252'}">{freq.get("主力流入占比","0%")}</td><td>流入天数/总天数</td></tr>
                    <tr><td>主力累计净额</td><td style="color:{'#00e676' if float(freq.get("主力累计净额_万",0))>0 else '#ff5252'}">{freq.get("主力累计净额_万",0):.0f}万</td><td>统计期主力净买入总额</td></tr>
                    <tr><td>近5日主力净额</td><td style="color:{'#00e676' if float(freq.get("近5日主力净额_万",0))>0 else '#ff5252'}">{freq.get("近5日主力净额_万",0):.0f}万</td><td>短期主力动向</td></tr>
                    <tr><td>趋势一致性</td><td>{freq.get("趋势一致性","-")}</td><td>5日与20日主力方向是否一致</td></tr>
                    <tr><td>主力流入强度</td><td>{freq.get("主力流入强度","0%")}</td><td>主力净额/期间总成交</td></tr>
                </table>
                <p style="font-size:12px;color:#8b949e;margin-top:4px">东财5日: 大单{float(mf_t.get("大单净额5日_万",0)):.0f}万 特大单{float(mf_t.get("特大单净额5日_万",0)):.0f}万 散户{float(mf_t.get("散户净额5日_万",0)):.0f}万 | 资金-价格共振: {mf_tushare.get("flow_price_signal","neutral")} | {mf_tushare.get("verdict","-")}</p>'''

    sections += f'''
            </div>
        </div>

        <!-- 成长维度 -->
        <div class="sixdim-card">
            <div class="sixdim-header" style="background:#1b5e2044">📈 成长趋势</div>
            <div class="sixdim-body">'''

    if growth_data:
        sections += f'''
                <table class="sixdim-table">
                    <tr><th>指标</th><th>最新QoQ</th><th>前季QoQ</th><th>前前季QoQ</th><th>最早QoQ</th><th>加权均值</th><th>判断</th></tr>
                    <tr><td>营收环比</td>
                        <td style="color:{'#00e676' if growth_data.get('rev_qoq1',0)>0 else '#ff5252'}">{growth_data.get('rev_qoq1',0):+.1f}%</td>
                        <td style="color:{'#00e676' if growth_data.get('rev_qoq2',0)>0 else '#ff5252'}">{growth_data.get('rev_qoq2',0):+.1f}%</td>
                        <td>{growth_data.get('rev_qoq3',0):+.1f}%</td>
                        <td>{growth_data.get('rev_qoq4',0):+.1f}%</td>
                        <td><strong>{growth_data.get('rev_weighted',0):+.1f}%</strong></td>
                        <td>{'加速中' if growth_data.get('rev_qoq1',0)>growth_data.get('rev_qoq2',0) else '减速'}</td></tr>
                    <tr><td>利润环比</td>
                        <td style="color:{'#00e676' if growth_data.get('np_qoq1',0)>0 else '#ff5252'}">{growth_data.get('np_qoq1',0):+.1f}%</td>
                        <td style="color:{'#00e676' if growth_data.get('np_qoq2',0)>0 else '#ff5252'}">{growth_data.get('np_qoq2',0):+.1f}%</td>
                        <td>{growth_data.get('np_qoq3',0):+.1f}%</td>
                        <td>{growth_data.get('np_qoq4',0):+.1f}%</td>
                        <td><strong>{growth_data.get('np_weighted',0):+.1f}%</strong></td>
                        <td>{'加速中' if growth_data.get('np_qoq1',0)>growth_data.get('np_qoq2',0) else '减速'}</td></tr>
                </table>'''
    if growth_data.get('fc_type'):
        sections += f'''
                <p style="font-size:12px;color:#58a6ff;margin-top:4px">📋 业绩预告: {growth_data["fc_type"]} {growth_data.get("fc_p_min","")}%~{growth_data.get("fc_p_max","")}%</p>'''

    sections += f'''
            </div>
        </div>

        <!-- 质量维度 -->
        <div class="sixdim-card">
            <div class="sixdim-header" style="background:#4a148c44">🏭 经营质量</div>
            <div class="sixdim-body">
                <table class="sixdim-table">
                    <tr><th>指标</th><th>数值</th><th>行业参考</th><th>判断</th></tr>
                    <tr><td>毛利率</td><td>{safe_num(growth_data.get('gross_margin'), 'N/A', '.1f')}%</td><td>科技>30%优</td><td style="color:{'#00e676' if (growth_data.get('gross_margin') or 0)>30 else '#ffd740'}">{'优秀' if (growth_data.get('gross_margin') or 0)>30 else '一般'}</td></tr>
                    <tr><td>ROE</td><td>{safe_num(growth_data.get('roe'), 'N/A', '.1f')}%</td><td>>15%优</td><td style="color:{'#00e676' if (growth_data.get('roe') or 0)>15 else '#ffd740'}">{'优秀' if (growth_data.get('roe') or 0)>15 else '一般'}</td></tr>
                    <tr><td>现金比率</td><td>{safe_num(growth_data.get('cash_ratio'), 'N/A', '.2f')}</td><td>>0.5稳健</td><td style="color:{'#00e676' if (growth_data.get('cash_ratio') or 0)>0.5 else '#ffd740'}">{'稳健' if (growth_data.get('cash_ratio') or 0)>0.5 else '偏紧'}</td></tr>
                    <tr><td>负债率</td><td>{safe_num(growth_data.get('debt_to_assets'), 'N/A', '.1f')}%</td><td><30%优</td><td style="color:{'#00e676' if (growth_data.get('debt_to_assets') or 100)<30 else ('#ff5252' if (growth_data.get('debt_to_assets') or 0)>70 else '#ffd740')}">{'低负债' if (growth_data.get('debt_to_assets') or 100)<30 else ('高负债⚠' if (growth_data.get('debt_to_assets') or 0)>70 else '中等')}</td></tr>
                </table>
            </div>
        </div>

        <!-- 风险维度 -->
        <div class="sixdim-card">
            <div class="sixdim-header" style="background:#b71c1c44">⚠ 风险度量</div>
            <div class="sixdim-body">
                <table class="sixdim-table">
                    <tr><th>指标</th><th>数值</th><th>说明</th></tr>
                    <tr><td>VaR(95%)</td><td>{safe_pct(var95)}</td><td>95%置信度下日最大亏损比例</td></tr>
                    <tr><td>CVaR(95%)</td><td>{safe_pct(cvar95)}</td><td>超出VaR的尾部平均亏损</td></tr>
                    <tr><td>年化波动率</td><td>{safe_num(annual_vol, 'N/A', '.1f')}%</td><td>>50%高风险, 30-50%中等, <30%低风险</td></tr>'''

    # 情景分析
    if scenarios:
        sections += f'''
                    <tr><td colspan="3"><strong>情景压力测试:</strong></td></tr>'''
        for s_name, s_data in scenarios.items():
            sections += f'''
                    <tr><td>{s_name}情景</td><td>{safe_num(s_data.get("composite_value"),"-",".2f")}元</td><td>涨跌幅{safe_pct(s_data.get("upside_pct"))}</td></tr>'''

    sections += f'''
                </table>
            </div>
        </div>

    </div>'''

    # ═══════════════════════════════════════════
    # 3.7 综合结论与风险提示
    # ═══════════════════════════════════════════
    # 综合建议
    signals = []
    if mos is not None:
        if mos > 15: signals.append(('估值', '低估', '#00e676'))
        elif mos > 0: signals.append(('估值', '略低估', '#69f0ae'))
        elif mos > -10: signals.append(('估值', '合理', '#ffd740'))
        else: signals.append(('估值', '高估', '#ff5252'))
    if '做多' in str(verdict): signals.append(('技术', verdict, '#69f0ae'))
    elif '偏多' in str(verdict): signals.append(('技术', verdict, '#ffd740'))
    elif '空' in str(verdict): signals.append(('技术', verdict, '#ff5252'))
    else: signals.append(('技术', '中性', '#90a4ae'))
    if mf_stats:
        net20 = mf_stats.get('main_net_20d_yi', 0)
        if net20 > 1: signals.append(('资金', '流入', '#00e676'))
        elif net20 > 0: signals.append(('资金', '小幅流入', '#69f0ae'))
        elif net20 > -1: signals.append(('资金', '小幅流出', '#ffd740'))
        else: signals.append(('资金', '流出', '#ff5252'))

    sig_html = ''.join([f'<span class="conclusion-tag" style="background:{s[2]}22;color:{s[2]};border:1px solid {s[2]}44">{s[0]}: {s[1]}</span>' for s in signals])

    risk_text = r.get('risk_hardcoded', '')
    edge_text = r.get('edge_hardcoded', '')
    plan_text = r.get('plan_hardcoded', '')

    sections += f'''
    <div class="detail-block">
        <h3>🎯 综合结论</h3>
        <div class="conclusion-box">
            <div class="conclusion-signals">{sig_html}</div>
            <div class="conclusion-text">{conclusion_html}</div>
        </div>
    </div>

    <div class="detail-block" style="border-color:#ff5252">
        <h3 style="color:#ff5252">⚠ 风险提示</h3>
        <div class="block-content">
            <p>{risk_text}</p>
            {f'<div style="margin-top:12px"><strong>核心优势：</strong></div><ol>{"".join(f"<li>{e.strip()}</li>" for e in edge_text.split(")") if e.strip())}</ol>' if edge_text else ''}
            {f'<div style="margin-top:12px"><strong>发展计划：</strong><p>{plan_text}</p></div>' if plan_text else ''}
            <p style="margin-top:16px;color:#8b949e;font-size:12px">
                WACC: {safe_num(wacc_d.get("wacc",0)*100, "N/A", ".1f")}% |
                Ke: {safe_num(wacc_d.get("ke",0)*100, "N/A", ".1f")}% |
                Beta: {safe_num(wacc_d.get("beta",0), "N/A", ".2f")} |
                数据日期: {r.get("analysis_date", DATE)}
            </p>
        </div>
    </div>'''

    return f'''
    <div class="detail-section" id="detail-{code}">
        <div class="detail-header">
            <span class="detail-code">{code}</span>
            <span class="detail-name">{r['name']}</span>
            <span class="detail-sw2">{r['sw2']}</span>
            <span style="color:#8b949e">|</span>
            <span style="font-size:18px;color:{pe_color(pe)}">{price:.2f}</span>
            <span style="color:#8b949e">| PE {pe:.1f} | PB {pb:.2f} | 市值 {mcap:.0f}亿</span>
            <a href="#top" class="back-link">↑ 回顶部</a>
        </div>
        {sections}
    </div>'''


# ═══════════════════════════════════════════════
# Full HTML
# ═══════════════════════════════════════════════

cards_html = ''.join([build_stock_card(c, r) for c, r in all_reports.items()])
details_html = ''.join([build_detail_section(c, r) for c, r in all_reports.items()])
n_stocks = len(all_reports)

# Collect stats for header
total_research = sum(len(r.get('research', {}).get('reports', [])) for r in all_reports.values())
stocks_with_mf = sum(1 for r in all_reports.values() if r.get('moneyflow', {}).get('stats'))

html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>A股科技成长板块 — V3 深度分析报告</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif; background:#0d1117; color:#c9d1d9; line-height:1.6; }}
.container {{ max-width:1200px; margin:0 auto; padding:20px; }}

/* Header */
.page-header {{ background: linear-gradient(135deg, #161b22, #1a2332); border-radius:16px; padding:40px; margin-bottom:30px; text-align:center; border:1px solid #30363d; }}
.page-header h1 {{ font-size:32px; background: linear-gradient(90deg, #58a6ff, #3fb950); -webkit-background-clip:text; -webkit-text-fill-color:transparent; margin-bottom:10px; }}
.page-header .subtitle {{ color:#8b949e; font-size:16px; }}
.page-header .stats {{ display:flex; justify-content:center; gap:30px; margin-top:20px; flex-wrap:wrap; }}
.page-header .stat {{ text-align:center; }}
.page-header .stat-num {{ font-size: 28px; font-weight:bold; color:#58a6ff; }}
.page-header .stat-label {{ font-size:13px; color:#8b949e; }}

.section-title {{ font-size:22px; color:#58a6ff; margin:40px 0 20px 0; padding-bottom:10px; border-bottom:1px solid #30363d; }}

/* Stock cards */
.cards-grid {{ display:grid; grid-template-columns: repeat(auto-fill, minmax(360px, 1fr)); gap:18px; margin-bottom:30px; }}
.stock-card {{ background:#161b22; border:1px solid #30363d; border-radius:12px; overflow:hidden; transition: transform .15s, border-color .15s; }}
.stock-card:hover {{ transform:translateY(-2px); border-color:#58a6ff; }}
.card-header {{ background:#1a2332; padding:14px 18px; display:flex; align-items:center; gap:12px; }}
.stock-code {{ font-family:'SF Mono','Consolas',monospace; font-size:14px; color:#58a6ff; font-weight:bold; }}
.stock-name {{ font-size:16px; font-weight:600; }}
.stock-sw2 {{ font-size:12px; color:#8b949e; background:#21262d; padding:2px 8px; border-radius:10px; margin-left:auto; }}
.card-body {{ padding:18px; }}
.card-metrics {{ display:grid; grid-template-columns: repeat(3, 1fr); gap:12px; margin-bottom:14px; }}
.metric {{ text-align:center; }}
.metric-value {{ font-size:20px; font-weight:bold; }}
.metric-label {{ font-size:11px; color:#8b949e; margin-top:2px; }}
.card-tags {{ display:flex; flex-wrap:wrap; gap:6px; margin-bottom:12px; }}
.tag {{ font-size:11px; background:#21262d; color:#8b949e; padding:3px 10px; border-radius:10px; }}
.tag-buy {{ background:#1a3a2a; color:#3fb950; }}
.tag-verdict {{ background:#1a3a2a; color:#3fb950; }}
.card-link {{ display:block; text-align:center; color:#58a6ff; text-decoration:none; font-size:13px; padding:6px; border-top:1px solid #21262d; }}
.card-link:hover {{ color:#79c0ff; }}

/* Detail sections */
.detail-section {{ background:#161b22; border:1px solid #30363d; border-radius:16px; margin-bottom:30px; overflow:hidden; }}
.detail-header {{ background:#1a2332; padding:18px 24px; display:flex; align-items:center; gap:10px; font-size:14px; flex-wrap:wrap; }}
.detail-code {{ font-family:'SF Mono','Consolas',monospace; font-size:15px; color:#58a6ff; font-weight:bold; }}
.detail-name {{ font-size:18px; font-weight:600; }}
.detail-sw2 {{ font-size:12px; color:#8b949e; background:#21262d; padding:2px 10px; border-radius:10px; }}
.back-link {{ margin-left:auto; color:#58a6ff; text-decoration:none; font-size:13px; }}

.detail-block {{ padding:20px 24px; border-bottom:1px solid #21262d; }}

/* Dim tags (6-dimension quick summary) */
.dim-tags-container {{ margin-top:12px; }}
.dim-tags-row {{ display:flex; gap:8px; flex-wrap:wrap; }}
.dim-tag {{ font-size:12px; padding:5px 12px; border-radius:14px; border:1px solid; font-weight:600; }}

/* Six-dimension cards */
.sixdim-card {{ margin-bottom:16px; border:1px solid #21262d; border-radius:10px; overflow:hidden; }}
.sixdim-header {{ padding:10px 16px; font-size:14px; font-weight:bold; color:#c9d1d9; }}
.sixdim-body {{ padding:14px 16px; background:#0d1117; font-size:13px; color:#c9d1d9; line-height:1.7; }}
.sixdim-table {{ width:100%; border-collapse:collapse; font-size:12px; margin-top:8px; }}
.sixdim-table th {{ text-align:left; padding:6px 8px; color:#8b949e; border-bottom:1px solid #21262d; font-weight:normal; }}
.sixdim-table td {{ padding:6px 8px; border-bottom:1px solid #1a1a2e; }}
.detail-block:last-child {{ border-bottom:none; }}
.detail-block h3 {{ font-size:16px; color:#c9d1d9; margin-bottom:12px; }}
.block-content {{ color:#c9d1d9; font-size:14px; }}
.block-content p {{ margin-bottom:6px; }}
.block-content ol {{ padding-left:20px; }}
.block-content li {{ margin-bottom:4px; color:#c9d1d9; }}

.section-summary {{ font-size:14px; color:#8b949e; margin-bottom:14px; line-height:1.6; }}
.section-subtitle {{ font-size:14px; color:#58a6ff; font-weight:600; margin-bottom:10px; }}

/* Executive Summary */
.exec-summary {{ display:flex; gap:24px; padding:20px 0; border-bottom:1px solid #21262d; }}
.exec-left {{ flex:0 0 180px; text-align:center; }}
.exec-verdict {{ font-size:22px; font-weight:bold; margin-bottom:4px; }}
.exec-price {{ font-size:32px; font-weight:bold; color:#c9d1d9; }}
.exec-target {{ font-size:13px; color:#8b949e; margin-top:4px; }}
.exec-right {{ flex:1; }}
.exec-conclusion {{ font-size:14px; color:#c9d1d9; line-height:1.8; margin-bottom:14px; }}
.dim-bars {{ display:flex; flex-direction:column; gap:6px; }}
.dim-item {{ display:flex; align-items:center; gap:10px; }}
.dim-label {{ width:50px; font-size:12px; color:#8b949e; text-align:right; }}
.dim-bar-track {{ flex:1; height:6px; background:#21262d; border-radius:3px; overflow:hidden; }}
.dim-bar-fill {{ height:100%; border-radius:3px; transition: width .6s; }}

/* Business section */
.biz-section {{ }}
.biz-label {{ font-size:12px; color:#58a6ff; font-weight:600; margin-bottom:6px; text-transform:uppercase; }}
.biz-text {{ font-size:14px; color:#c9d1d9; line-height:1.8; white-space:pre-wrap; }}
.biz-source {{ font-size:11px; color:#8b949e; margin-top:6px; }}

/* Financial grid */
.fin-grid {{ display:grid; grid-template-columns: repeat(4, 1fr); gap:12px; }}
.fin-card {{ background:#0d1117; border:1px solid #21262d; border-radius:8px; padding:16px; text-align:center; }}
.fin-card-title {{ font-size:11px; color:#8b949e; margin-bottom:4px; text-transform:uppercase; }}
.fin-card-val {{ font-size:22px; font-weight:bold; color:#58a6ff; }}
.fin-card-sub {{ font-size:11px; color:#8b949e; margin-top:4px; }}

/* Valuation grid */
.val-grid {{ display:grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap:12px; margin-bottom:16px; }}
.val-card {{ background:#0d1117; border-radius:8px; padding:16px; text-align:center; border:1px solid #21262d; }}
.val-title {{ font-size:12px; color:#8b949e; margin-bottom:6px; }}
.val-number {{ font-size:24px; font-weight:bold; }}
.val-sub {{ font-size:11px; color:#8b949e; margin-top:4px; }}

.scenario-row {{ display:flex; gap:12px; margin-bottom:16px; }}
.scenario-card {{ flex:1; background:#0d1117; border-radius:8px; padding:14px; text-align:center; border:1px solid #21262d; }}
.sc-title {{ font-size:12px; color:#8b949e; }}
.sc-value {{ font-size:20px; font-weight:bold; color:#ffd740; margin:6px 0; }}
.sc-upside {{ font-size:13px; }}

/* Research synthesis */
.research-synthesis {{ background:#0d1117; border:1px solid #30363d; border-radius:8px; padding:18px; margin-top:16px; }}
.synth-summary {{ font-size:14px; color:#c9d1d9; line-height:1.8; margin-bottom:12px; }}
.synth-themes {{ display:flex; gap:6px; flex-wrap:wrap; margin-bottom:12px; }}
.research-theme-tag {{ font-size:11px; background:#1a2332; color:#58a6ff; padding:3px 10px; border-radius:12px; border:1px solid #58a6ff44; }}
.synth-detail {{ font-size:13px; color:#8b949e; margin-bottom:10px; }}
.synth-views {{ margin-top:10px; }}
.synth-view-item {{ padding:8px 12px; border-bottom:1px solid #21262d; font-size:13px; display:flex; gap:10px; align-items:baseline; flex-wrap:wrap; }}
.synth-view-org {{ color:#58a6ff; font-weight:600; white-space:nowrap; }}
.synth-view-date {{ color:#8b949e; font-size:11px; white-space:nowrap; }}
.synth-view-rating {{ font-size:11px; white-space:nowrap; }}
.synth-view-text {{ color:#c9d1d9; flex:1; min-width:200px; }}

/* Enhanced synthesis */
.synth-narrative {{ font-size:15px; color:#c9d1d9; line-height:2; margin-bottom:16px; padding:14px 16px; background:#1a2332; border-radius:8px; border-left:3px solid #58a6ff; }}
.implied-target-box {{ display:flex; gap:20px; background:linear-gradient(135deg,#1a2332,#0d1117); border:1px solid #30363d; border-radius:8px; padding:16px; margin:12px 0; }}
.implied-target-main {{ flex:0 0 200px; text-align:center; font-size:13px; color:#8b949e; }}
.implied-big {{ font-size:28px; font-weight:bold; color:#3fb950; margin:4px 0; }}
.implied-target-detail {{ flex:1; display:flex; flex-direction:column; justify-content:center; gap:4px; font-size:13px; color:#8b949e; }}
.viewpoint-group {{ display:flex; align-items:flex-start; gap:10px; margin:8px 0; }}
.viewpoint-group-name {{ font-size:12px; color:#58a6ff; font-weight:600; white-space:nowrap; min-width:60px; }}
.viewpoint-tags {{ display:flex; gap:6px; flex-wrap:wrap; }}
.viewpoint-tag {{ font-size:12px; background:#0d1117; color:#c9d1d9; padding:3px 10px; border-radius:10px; border:1px solid #30363d; }}
.synth-view-signal {{ font-size:11px; padding:1px 6px; border-radius:8px; margin-left:6px; }}
.synth-view-title {{ font-size:13px; color:#c9d1d9; margin-top:4px; font-style:italic; }}
.synth-view-drivers {{ font-size:11px; color:#8b949e; margin-top:2px; }}
.synth-view-header {{ display:flex; gap:8px; align-items:center; flex-wrap:wrap; }}

/* PDF extracts */
.pdf-extracts {{ display:flex; flex-direction:column; gap:14px; margin-top:10px; }}
.pdf-extract-item {{ background:#0d1117; border:1px solid #30363d; border-radius:8px; padding:14px; }}
.pdf-extract-header {{ display:flex; gap:10px; align-items:center; margin-bottom:8px; font-size:12px; }}
.pdf-extract-text {{ font-size:13px; color:#8b949e; line-height:1.8; max-height:360px; overflow-y:auto; white-space:pre-wrap; }}

/* Research table */
.research-table-wrap {{ margin-top:20px; }}
.research-table {{ width:100%; border-collapse:collapse; font-size:13px; margin-top:10px; }}
.research-table th {{ text-align:left; color:#8b949e; font-size:11px; padding:8px 10px; border-bottom:1px solid #30363d; }}
.research-table td {{ padding:8px 10px; border-bottom:1px solid #21262d; }}
.research-table tr:hover td {{ background:#1a2332; }}
.research-compare {{ background:#1a2332; border-radius:8px; padding:12px 16px; margin-top:12px; font-size:14px; color:#c9d1d9; }}

/* Volume-Price card */
.vp-card {{ background:#0d1117; border:1px solid #21262d; border-radius:8px; padding:18px; }}
.vp-row {{ display:flex; gap:16px; }}
.vp-item {{ flex:1; text-align:center; }}
.vp-val {{ font-size:20px; font-weight:bold; color:#58a6ff; }}
.vp-label {{ font-size:11px; color:#8b949e; margin-top:4px; }}

/* VPA Rating Card */
.vpa-rating-card {{ display:flex; gap:24px; background:#0d1117; border:1px solid #21262d; border-radius:8px; padding:18px; margin-top:10px; align-items:center; }}
.vpa-main-rating {{ flex:0 0 140px; text-align:center; }}
.vpa-big-rating {{ font-size:24px; font-weight:bold; }}
.vpa-score {{ font-size:13px; color:#8b949e; margin-top:4px; }}
.vpa-dims {{ flex:1; display:flex; flex-direction:column; gap:8px; }}
.vpa-dim {{ display:flex; align-items:center; gap:8px; font-size:12px; color:#8b949e; }}
.vpa-dim-bar {{ flex:1; height:6px; background:#21262d; border-radius:3px; overflow:hidden; }}
.vpa-dim-bar div {{ height:100%; border-radius:3px; transition:width .6s; }}

.vpa-detail-grid {{ display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin-top:12px; }}
.vpa-detail-item {{ background:#0d1117; border:1px solid #21262d; border-radius:8px; padding:12px; }}
.vpa-detail-label {{ font-size:11px; color:#58a6ff; margin-bottom:4px; }}
.vpa-detail-val {{ font-size:15px; font-weight:bold; color:#c9d1d9; }}
.vpa-detail-sub {{ font-size:11px; color:#8b949e; margin-top:4px; }}

.vpa-signals-row {{ display:flex; gap:6px; flex-wrap:wrap; margin-top:12px; }}
.vpa-sig-tag {{ font-size:11px; padding:4px 10px; border-radius:12px; background:#1a2332; color:#8b949e; border:1px solid #30363d; }}
.vpa-sig-趋势 {{ border-color:#3fb95044; color:#3fb950; }}
.vpa-sig-趋势延 {{ border-color:#3fb95044; color:#3fb950; }}
.vpa-sig-趋势启 {{ border-color:#3fb95044; color:#3fb950; }}
.vpa-sig-趋势衰 {{ border-color:#ff525244; color:#ff5252; }}
.vpa-sig-反转 {{ border-color:#ffd74044; color:#ffd740; }}

.vpa-anomaly-warn {{ margin-top:12px; padding:10px 14px; background:#ff52521a; border:1px solid #ff525244; border-radius:8px; font-size:13px; color:#ff5252; }}
.vpa-mf-extra {{ margin-top:12px; padding:10px 14px; background:#0d1117; border:1px solid #21262d; border-radius:8px; font-size:12px; color:#8b949e; }}

/* Money flow dashboard */
.mf-dashboard {{ display:flex; gap:20px; background:#0d1117; border:1px solid #21262d; border-radius:8px; padding:18px; margin-top:10px; }}
.mf-main {{ flex:0 0 240px; text-align:center; border-right:1px solid #21262d; padding-right:20px; }}
.mf-big-num {{ font-size:32px; font-weight:bold; }}
.mf-big-label {{ font-size:13px; color:#8b949e; margin-top:4px; }}
.mf-cons {{ font-size:12px; color:#8b949e; margin-top:10px; }}
.mf-detail {{ flex:1; display:flex; flex-direction:column; gap:8px; }}
.mf-row {{ display:flex; justify-content:space-between; font-size:14px; padding:4px 8px; }}

/* Risk explain */
.risk-explain {{ background:#1a2332; border-radius:8px; padding:12px; margin-top:12px; font-size:13px; color:#8b949e; line-height:1.8; }}

/* Conclusion */
.conclusion-box {{ }}
.conclusion-signals {{ display:flex; gap:10px; margin-bottom:12px; flex-wrap:wrap; }}
.conclusion-tag {{ padding:6px 14px; border-radius:20px; font-size:13px; font-weight:600; }}
.conclusion-text {{ font-size:14px; color:#c9d1d9; line-height:1.8; }}

/* Misc */
.metric-row {{ display:flex; gap:16px; flex-wrap:wrap; }}
.mini-metric {{ flex:1; min-width:120px; background:#0d1117; border-radius:8px; padding:14px; text-align:center; border:1px solid #21262d; }}
.mm-val {{ display:block; font-size:20px; font-weight:bold; color:#58a6ff; }}
.mm-label {{ display:block; font-size:11px; color:#8b949e; margin-top:4px; }}

.page-footer {{ text-align:center; color:#484f58; font-size:12px; padding:40px 0; }}
.page-footer a {{ color:#58a6ff; }}
.nav-top {{ position:fixed; bottom:30px; right:30px; background:#238636; color:#fff; width:44px; height:44px; border-radius:50%; display:flex; align-items:center; justify-content:center; text-decoration:none; font-size:20px; box-shadow:0 4px 12px rgba(0,0,0,.4); z-index:100; }}
.nav-top:hover {{ background:#2ea043; }}

@media (max-width:768px) {{
    .cards-grid {{ grid-template-columns:1fr; }}
    .val-grid, .fin-grid {{ grid-template-columns:1fr 1fr; }}
    .metric-row {{ flex-direction:column; }}
    .scenario-row {{ flex-direction:column; }}
    .exec-summary {{ flex-direction:column; }}
    .mf-dashboard {{ flex-direction:column; }}
    .mf-main {{ border-right:none; border-bottom:1px solid #21262d; padding:0 0 16px 0; }}
    .vp-row {{ flex-wrap:wrap; }}
}}
</style>
</head>
<body id="top">
<div class="container">

<!-- ═══════════ HEADER ═══════════ -->
<div class="page-header">
    <h1>A股科技成长板块 · V3 深度分析报告</h1>
    <div class="subtitle">TG-trading-sys V4.0 全模块分析 | 研报驱动 + 量价资金 + 业务深度 | {DATE}</div>
    <div class="stats">
        <div class="stat"><div class="stat-num">{n_stocks}</div><div class="stat-label">精选标的</div></div>
        <div class="stat"><div class="stat-num">11</div><div class="stat-label">分析模块</div></div>
        <div class="stat"><div class="stat-num">{total_research}</div><div class="stat-label">券商研报</div></div>
        <div class="stat"><div class="stat-num">{stocks_with_mf}/{n_stocks}</div><div class="stat-label">资金流覆盖</div></div>
    </div>
</div>

<!-- ═══════════ 筛选说明 ═══════════ -->
<div class="detail-block" style="border-radius:12px;margin-bottom:30px;background:#161b22;">
    <h3>🔬 筛选流程</h3>
    <div class="block-content">
        <p><strong>第一轮</strong>：全市场5533只 → 12个科技行业 → <strong>2293只</strong></p>
        <p><strong>第二轮</strong>：5期财报QoQ环比分析 + 业绩预告信号 + 现金流健康 + 负债惩罚 + 营收利润双改善加分 → <strong>Top 124只</strong></p>
        <p><strong>第三轮</strong>：综合估值定价(DCF+PEG+PB-ROE+研报目标价) + 安全边际评分 → <strong>低估精选</strong></p>
        <p><strong>第四轮（本报告）</strong>：11模块深度分析 = 业务深度(F10/年报) + 财务诊断 + 估值定价 + 技术面(均线+VPA量价) + 资金面(主力流+Tushare) + VaR风控 + 六维度综合结论</p>
    </div>
</div>

<!-- ═══════════ 快速概览卡片 ═══════════ -->
<h2 class="section-title">📊 {n_stocks}只精选 — 快速概览</h2>
<div class="cards-grid">
{cards_html}
</div>

<!-- ═══════════ 深度分析 ═══════════ -->
<h2 class="section-title">📋 逐只深度分析</h2>
{details_html}

<!-- ═══════════ 免责声明 ═══════════ -->
<div class="detail-block" style="border-radius:12px;margin-top:30px;background:#161b22;">
    <h3 style="color:#ff5252">📢 免责声明</h3>
    <div class="block-content" style="color:#8b949e;font-size:13px;">
        <p>本报告由 TG-trading-sys V4.0 系统自动生成，仅供研究参考，不构成任何投资建议。</p>
        <p>数据来源：东财reportapi(研报评级/目标价)、同花顺(一致预期EPS)、Tushare/mootdx(K线行情)、新浪财经(财报三表)、腾讯财经(实时行情)、东财push2his(资金流)、mootdx F10(公司概况)、巨潮cninfo(年报信息)。</p>
        <p>估值模型(DCF/PEG/PB-ROE)基于公开财务数据和市场参数假设，存在模型风险和参数不确定性。技术面与资金面分析基于历史数据，不保证未来走势。</p>
        <p>投资有风险，入市需谨慎。请结合自身情况独立判断。</p>
    </div>
</div>

<div class="page-footer">
    TG-trading-sys V4.0 · V3深度分析报告 · {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ·
    <a href="https://github.com/A-STOCK-DATA/a-stock-data">GitHub</a>
</div>

</div>
<a href="#top" class="nav-top">↑</a>
</body>
</html>'''

# Write HTML
output_path = 'data/deep_reports/A股科技成长_V3_深度分析.html'
os.makedirs('data/deep_reports', exist_ok=True)
with open(output_path, 'w', encoding='utf-8') as f:
    f.write(html)

size_kb = os.path.getsize(output_path) / 1024
print(f'V3 HTML报告已生成: {output_path} ({size_kb:.0f} KB)')
print(f'共 {n_stocks} 只标的, 每只含执行摘要+业务+财务+估值+研报对照+量价+资金流+综合结论')
