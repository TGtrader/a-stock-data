"""
Stage 2: 生成 9 只 A 类科技股的 HTML 深度分析报告
"""
import sys, os, io, json
os.environ['PYTHONIOENCODING'] = 'utf-8'
sys.path.insert(0, '.')
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from datetime import datetime

# Load collected data
with open('data/deep_reports/all_reports.json', 'r', encoding='utf-8') as f:
    all_reports = json.load(f)

DATE = datetime.now().strftime('%Y-%m-%d')

# ═══════════════════════════════════════════════
# Color helpers
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

def safe_num(v, default='N/A', fmt='.1f'):
    if v is None: return default
    try:
        return f'{float(v):{fmt}}'
    except (ValueError, TypeError):
        return str(v)

def safe_pct(v):
    if v is None: return 'N/A'
    try:
        return f'{float(v):+.1f}%'
    except: return str(v)

# ═══════════════════════════════════════════════
# Stock card builder (for index page)
# ═══════════════════════════════════════════════

def build_stock_card(code, r):
    basic = r.get('basic', {})
    tech = r.get('technical', {})
    val = r.get('valuation', {})
    fin = r.get('financials', {})
    risk = r.get('risk', {})

    price = basic.get('price', 0)
    pe = basic.get('pe_ttm', 0)
    pb = basic.get('pb', 0)
    mcap = basic.get('mcap_yi', 0)

    verdict = tech.get('verdict', 'N/A')
    vscore = tech.get('verdict_score', 0)
    final_val = val.get('final_value')
    mos = val.get('margin_of_safety_pct')
    mos_v = val.get('margin_verdict', '')

    eps_data = r.get('consensus', {})
    eps26 = eps_data.get('eps_2026', 0)

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
                {f'<span class="tag">2026E EPS {eps26:.2f}</span>' if eps26 else ''}
                {f'<span class="tag">VaR95 {var95:.1f}%</span>' if var95 else ''}
                {f'<span class="tag">波动率 {vol:.0f}%</span>' if vol else ''}
                {f'<span class="tag tag-verdict">{mos_v}</span>' if mos_v else ''}
            </div>
            <a href="#detail-{code}" class="card-link">查看深度分析 →</a>
        </div>
    </div>'''

# ═══════════════════════════════════════════════
# Detail section builder
# ═══════════════════════════════════════════════

def build_detail_section(code, r):
    basic = r.get('basic', {})
    tech = r.get('technical', {})
    val = r.get('valuation', {})
    fin = r.get('financials', {})
    risk = r.get('risk', {})
    wacc_d = r.get('wacc', {})
    eps_d = r.get('consensus', {})
    regime = r.get('market_regime', {})

    price = basic.get('price', 0)
    pe = basic.get('pe_ttm', 0)
    pb = basic.get('pb', 0)
    mcap = basic.get('mcap_yi', 0)

    verdict = tech.get('verdict', 'N/A')
    ma_verdict = tech.get('ma_verdict', '')
    ma_score = tech.get('ma_score', 0)
    ma_align = tech.get('ma_alignment', '')

    final_val = val.get('final_value')
    mos = val.get('margin_of_safety_pct')
    mos_v = val.get('margin_verdict', '')
    dcf_val = val.get('dcf_per_share')
    dcf_wacc = safe_num(val.get('dcf_wacc'), 'N/A', '.1f')
    dcf_tg = safe_num(val.get('dcf_terminal_g'), 'N/A', '.1f')
    dcf_tvr = safe_num(val.get('dcf_tv_ratio'), 'N/A', '.0f')
    peg = val.get('peg_value', {})
    pb_roe = val.get('pb_roe_value', {})

    scenarios = val.get('scenarios', {})
    earnings = val.get('earnings', {})

    key_metrics = fin.get('key_metrics', {})
    balance = fin.get('balance', {})

    var95 = risk.get('var_95_pct', 0)
    cvar95 = risk.get('cvar_95_pct', 0)
    annual_vol = risk.get('annual_vol', 0)

    # EPS data
    eps26 = eps_d.get('eps_2026', 0)
    eps27 = eps_d.get('eps_2027', 0)

    # Industry section
    sections = ''

    # -- 公司概览 --
    sections += f'''
    <div class="detail-block">
        <h3>📋 公司概览</h3>
        <div class="block-content">
            <p><strong>主营业务：</strong>{r.get('biz', '')}</p>
        </div>
    </div>'''

    # -- 行业竞争格局 --
    sections += f'''
    <div class="detail-block">
        <h3>🏭 行业竞争格局</h3>
        <div class="block-content">
            <p>{r.get('comp', '')}</p>
        </div>
    </div>'''

    # -- 竞争优势 --
    sections += f'''
    <div class="detail-block">
        <h3>⭐ 核心竞争优势</h3>
        <div class="block-content">
            <ol>{''.join(f'<li>{e.strip()}</li>' for e in r.get('edge','').split(')') if e.strip())}</ol>
        </div>
    </div>'''

    # -- 发展计划 --
    sections += f'''
    <div class="detail-block">
        <h3>🎯 发展计划</h3>
        <div class="block-content">
            <p>{r.get('plan', '')}</p>
        </div>
    </div>'''

    # -- 财务概览 --
    rev_str = f'{key_metrics.get("revenue", 0)/10000:.1f}亿' if key_metrics.get('revenue') else 'N/A'
    np_str = f'{key_metrics.get("net_profit", 0)/10000:.1f}亿' if key_metrics.get('net_profit') else 'N/A'
    sections += f'''
    <div class="detail-block">
        <h3>📊 财务概览 (最新一期)</h3>
        <div class="metric-row">
            <div class="mini-metric"><span class="mm-val">{rev_str}</span><span class="mm-label">营业收入</span></div>
            <div class="mini-metric"><span class="mm-val">{np_str}</span><span class="mm-label">归母净利润</span></div>
            <div class="mini-metric"><span class="mm-val">{safe_num(balance.get('total_assets',0)/10000, 'N/A', '.1f')}亿</span><span class="mm-label">总资产</span></div>
            <div class="mini-metric"><span class="mm-val">{safe_num(balance.get('debt_ratio'), 'N/A', '.1f')}%</span><span class="mm-label">资产负债率</span></div>
        </div>
        <p style="color:#888;font-size:13px;margin-top:8px">数据来源: 新浪财报三表(利润表/资产负债表/现金流量表)，共 {fin.get('lrb',{}).get('reports',0)} 期</p>
    </div>'''

    # -- 估值分析 --
    sections += f'''
    <div class="detail-block">
        <h3>💰 估值分析</h3>
        <div class="val-grid">
            <div class="val-card">
                <div class="val-title">综合估值</div>
                <div class="val-number" style="color:{mos_color(mos)}">{safe_num(final_val, 'N/A', '.2f')} 元</div>
                <div class="val-sub">安全边际 {safe_pct(mos)} · {mos_v}</div>
            </div>
            <div class="val-card">
                <div class="val-title">DCF 估值</div>
                <div class="val-number">{safe_num(dcf_val, 'N/A', '.2f')} 元</div>
                <div class="val-sub">WACC {dcf_wacc}% · g {dcf_tg}% · 终值占比 {dcf_tvr}%</div>
            </div>
            <div class="val-card">
                <div class="val-title">PE-PEG 估值</div>
                <div class="val-number">{safe_num(peg.get('fair_value'), 'N/A', '.2f')} 元</div>
                <div class="val-sub">{peg.get('detail', '')} · {peg.get('verdict', '')}</div>
            </div>
            <div class="val-card">
                <div class="val-title">PB-ROE 估值</div>
                <div class="val-number">{safe_num(pb_roe.get('fair_value'), 'N/A', '.2f')} 元</div>
                <div class="val-sub">ROE {safe_num(pb_roe.get('roe_pct'), 'N/A', '.1f')}% · 合理PB {safe_num(pb_roe.get('fair_pb'), 'N/A', '.1f')}</div>
            </div>
        </div>'''

    # Scenarios
    if scenarios:
        sections += '''
        <div class="scenario-row">'''
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
    sections += '</div>'

    # -- 一致预期 --
    if eps_d:
        hist_eps = eps_d.get('hist_eps', [])
        hist_str = ' → '.join([f'{h["year"]}: {h["eps"]}' for h in hist_eps]) if hist_eps else ''
        sections += f'''
        <div class="detail-block">
            <h3>🔮 一致预期 (同花顺)</h3>
            <div class="metric-row">
                <div class="mini-metric"><span class="mm-val">{eps26:.2f}</span><span class="mm-label">2026E EPS</span></div>
                <div class="mini-metric"><span class="mm-val">{eps27:.2f}</span><span class="mm-label">2027E EPS</span></div>
                <div class="mini-metric"><span class="mm-val">{mcap*10000/(eps26*10000):.1f}x</span><span class="mm-label">2026E PE</span></div>
                <div class="mini-metric"><span class="mm-val">{hist_str}</span><span class="mm-label">历史EPS</span></div>
            </div>
        </div>'''

    # -- 技术分析 --
    sections += f'''
    <div class="detail-block">
        <h3>📈 技术分析</h3>
        <div class="metric-row">
            <div class="mini-metric"><span class="mm-val" style="color:{verdict_color(verdict)}">{verdict}</span><span class="mm-label">择时信号</span></div>
            <div class="mini-metric"><span class="mm-val">{tech.get("verdict_score", 0)}/100</span><span class="mm-label">综合评分</span></div>
            <div class="mini-metric"><span class="mm-val">{ma_score}/100</span><span class="mm-label">均线评分</span></div>
            <div class="mini-metric"><span class="mm-val">{ma_align}</span><span class="mm-label">均线排列</span></div>
        </div>
        {f'<p style="color:#ff9100;margin-top:8px">⚠ 冲突: {"; ".join(tech.get("conflicts",[]))}</p>' if tech.get('conflicts') else ''}
        {f'<p style="color:#888;margin-top:4px">置信度: {tech.get("confidence","")} · 仓位建议: {tech.get("position_advice","")}</p>'}
    </div>'''

    # -- 风险度量 --
    # 计算日VaR对应的金额含义
    price = basic.get('price', 0)
    daily_var_amount = price * var95 / 100 if var95 and price else 0
    var_explain = f'含义：持有一日，95%概率最大亏损不超过 {var95:.1f}%（约每股{price*var95/100:.2f}元）' if var95 and price else ''
    vol_level = '极高' if annual_vol > 60 else ('偏高' if annual_vol > 40 else ('中等' if annual_vol > 25 else '较低'))
    sections += f'''
    <div class="detail-block">
        <h3>🛡 风险度量（基于历史日收益率的统计模型）</h3>
        <div class="metric-row">
            <div class="mini-metric">
                <span class="mm-val" style="color:#ff9100">{var95:.1f}%</span>
                <span class="mm-label">VaR 日(95%置信)</span>
                <span style="font-size:10px;color:#8b949e;display:block;margin-top:4px">每日最大亏损率</span>
            </div>
            <div class="mini-metric">
                <span class="mm-val" style="color:#ff5252">{cvar95:.1f}%</span>
                <span class="mm-label">CVaR 日(95%置信)</span>
                <span style="font-size:10px;color:#8b949e;display:block;margin-top:4px">超出VaR的平均亏损</span>
            </div>
            <div class="mini-metric">
                <span class="mm-val" style="color:#ff9100">{annual_vol:.0f}%</span>
                <span class="mm-label">年化波动率 ({vol_level})</span>
                <span style="font-size:10px;color:#8b949e;display:block;margin-top:4px">日波动×√252</span>
            </div>
            <div class="mini-metric">
                <span class="mm-val">{wacc_d.get('beta', 0):.2f}</span>
                <span class="mm-label">Beta 系数</span>
                <span style="font-size:10px;color:#8b949e;display:block;margin-top:4px">相对大盘波动倍数</span>
            </div>
        </div>
        <div style="background:#1a2332;border-radius:8px;padding:12px;margin-top:12px;font-size:13px;color:#8b949e;line-height:1.8">
            <strong style="color:#c9d1d9">📖 如何理解这些指标：</strong><br>
            <strong>VaR (风险价值)</strong>：基于过去一年日收益率分布，在95%置信度下，<span style="color:#ff9100">持有一股该股票，一天内亏损超过 <strong>{var95:.1f}%</strong>（约{price*var95/100:.2f}元）的概率仅为5%</span>。换句话说，100个交易日中约有5天亏损会超过这个比例。<br>
            <strong>CVaR (条件风险价值)</strong>：当亏损已经超过VaR阈值时，<span style="color:#ff5252">平均会亏 <strong>{cvar95:.1f}%</strong></span>。CVaR总是大于等于VaR，代表"尾部风险"的严重程度。<br>
            <strong>年化波动率 {annual_vol:.0f}%</strong>：股价年化标准差。<span style="color:#ff9100">波动率越高，股价涨跌越剧烈</span>。一般A股科技股年化波动在40-60%属于常态，{'>60%偏高，反映近期剧烈波动' if annual_vol > 60 else ('40-60%正常范围' if annual_vol > 40 else '<40%相对温和')}。<br>
            <strong>Beta {wacc_d.get('beta', 0):.2f}</strong>：相对沪深300的波动倍数。Beta=1表示与大盘同步，Beta>1表示弹性更大（涨跌都更猛），Beta<1表示防御性更强。
        </div>
    </div>'''

    # -- WACC 参数 --
    sections += f'''
    <div class="detail-block">
        <h3>⚙ WACC 参数</h3>
        <div class="metric-row">
            <div class="mini-metric"><span class="mm-val">{wacc_d.get('wacc', 0)*100:.1f}%</span><span class="mm-label">WACC</span></div>
            <div class="mini-metric"><span class="mm-val">{wacc_d.get('ke', 0)*100:.1f}%</span><span class="mm-label">Ke (股权成本)</span></div>
            <div class="mini-metric"><span class="mm-val">{wacc_d.get('kd', 0)*100:.1f}%</span><span class="mm-label">Kd (税后)</span></div>
            <div class="mini-metric"><span class="mm-val">{wacc_d.get('d_e_ratio', 0):.2f}</span><span class="mm-label">D/E 比率</span></div>
        </div>
    </div>'''

    # -- 风险提示 --
    sections += f'''
    <div class="detail-block" style="border-color:#ff5252">
        <h3 style="color:#ff5252">⚠ 风险提示</h3>
        <div class="block-content">
            <p>{r.get('risk', '')}</p>
            {f'<p style="margin-top:8px;color:#888">大盘环境: {regime.get("verdict","")} (评分{regime.get("score",0)}/100) · {regime.get("transition","")}</p>' if regime else ''}
        </div>
    </div>'''

    return f'''
    <div class="detail-section" id="detail-{code}">
        <div class="detail-header">
            <span class="detail-code">{code}</span>
            <span class="detail-name">{r['name']}</span>
            <span class="detail-sw2">{r['sw2']}</span>
            <span style="color:#888">|</span>
            <span style="font-size:18px;color:{pe_color(pe)}">{price:.2f}</span>
            <span style="color:#888">| PE {pe:.1f} | PB {pb:.2f} | 市值 {mcap:.0f}亿</span>
            <a href="#top" class="back-link">↑ 回顶部</a>
        </div>
        {sections}
    </div>'''

# ═══════════════════════════════════════════════
# Full HTML
# ═══════════════════════════════════════════════

cards_html = ''.join([build_stock_card(c, r) for c, r in all_reports.items()])
details_html = ''.join([build_detail_section(c, r) for c, r in all_reports.items()])

html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>A股科技成长板块 — 超跌/低估精选深度分析</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif; background:#0d1117; color:#c9d1d9; line-height:1.6; }}
.container {{ max-width:1200px; margin:0 auto; padding:20px; }}

/* Header */
.page-header {{ background: linear-gradient(135deg, #161b22, #1a2332); border-radius:16px; padding:40px; margin-bottom:30px; text-align:center; border:1px solid #30363d; }}
.page-header h1 {{ font-size:32px; background: linear-gradient(90deg, #58a6ff, #3fb950); -webkit-background-clip:text; -webkit-text-fill-color:transparent; margin-bottom:10px; }}
.page-header .subtitle {{ color:#8b949e; font-size:16px; }}
.page-header .stats {{ display:flex; justify-content:center; gap:30px; margin-top:20px; }}
.page-header .stat {{ text-align:center; }}
.page-header .stat-num {{ font-size: 28px; font-weight:bold; color:#58a6ff; }}
.page-header .stat-label {{ font-size:13px; color:#8b949e; }}

/* Section titles */
.section-title {{ font-size:22px; color:#58a6ff; margin:40px 0 20px 0; padding-bottom:10px; border-bottom:1px solid #30363d; }}

/* Stock cards grid */
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
.detail-block:last-child {{ border-bottom:none; }}
.detail-block h3 {{ font-size:16px; color:#c9d1d9; margin-bottom:12px; }}
.block-content {{ color:#8b949e; font-size:14px; }}
.block-content p {{ margin-bottom:6px; }}
.block-content ol {{ padding-left:20px; }}
.block-content li {{ margin-bottom:4px; color:#c9d1d9; }}

.metric-row {{ display:flex; gap:16px; flex-wrap:wrap; }}
.mini-metric {{ flex:1; min-width:120px; background:#0d1117; border-radius:8px; padding:14px; text-align:center; border:1px solid #21262d; }}
.mm-val {{ display:block; font-size:20px; font-weight:bold; color:#58a6ff; }}
.mm-label {{ display:block; font-size:11px; color:#8b949e; margin-top:4px; }}

.val-grid {{ display:grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap:12px; margin-bottom:16px; }}
.val-card {{ background:#0d1117; border-radius:8px; padding:16px; text-align:center; border:1px solid #21262d; }}
.val-title {{ font-size:12px; color:#8b949e; margin-bottom:6px; }}
.val-number {{ font-size:24px; font-weight:bold; }}
.val-sub {{ font-size:11px; color:#8b949e; margin-top:4px; }}

.scenario-row {{ display:flex; gap:12px; }}
.scenario-card {{ flex:1; background:#0d1117; border-radius:8px; padding:14px; text-align:center; border:1px solid #21262d; }}
.sc-title {{ font-size:12px; color:#8b949e; }}
.sc-value {{ font-size:20px; font-weight:bold; color:#ffd740; margin:6px 0; }}
.sc-upside {{ font-size:13px; }}

/* Footer */
.page-footer {{ text-align:center; color:#484f58; font-size:12px; padding:40px 0; }}
.page-footer a {{ color:#58a6ff; }}

/* Nav */
.nav-top {{ position:fixed; bottom:30px; right:30px; background:#238636; color:#fff; width:44px; height:44px; border-radius:50%; display:flex; align-items:center; justify-content:center; text-decoration:none; font-size:20px; box-shadow:0 4px 12px rgba(0,0,0,.4); z-index:100; }}
.nav-top:hover {{ background:#2ea043; }}

@media (max-width:768px) {{
    .cards-grid {{ grid-template-columns:1fr; }}
    .val-grid {{ grid-template-columns:1fr 1fr; }}
    .metric-row {{ flex-direction:column; }}
    .scenario-row {{ flex-direction:column; }}
}}
</style>
</head>
<body id="top">
<div class="container">

<!-- ═══════════ HEADER ═══════════ -->
<div class="page-header">
    <h1>A股科技成长板块 · 超跌/低估精选</h1>
    <div class="subtitle">基于 TG-trading-sys V4.0 全模块深度分析 | {DATE}</div>
    <div class="stats">
        <div class="stat"><div class="stat-num">9</div><div class="stat-label">A类精选标的</div></div>
        <div class="stat"><div class="stat-num">7</div><div class="stat-label">子行业覆盖</div></div>
        <div class="stat"><div class="stat-num">8</div><div class="stat-label">分析模块</div></div>
        <div class="stat"><div class="stat-num">5533→9</div><div class="stat-label">全市场筛选</div></div>
    </div>
</div>

<!-- ═══════════ 筛选说明 ═══════════ -->
<div class="detail-block" style="border-radius:12px;margin-bottom:30px">
    <h3>🔬 筛选流程</h3>
    <div class="block-content">
        <p><strong>第一轮</strong>：全市场5533只股票 → 选取12个科技相关行业(半导体/软件服务/通信设备/IT设备/互联网/元器件/电气设备/专用机械/电器仪表/医疗保健/化学制药/航空) → <strong>2293只</strong></p>
        <p><strong>第二轮</strong>：行业中性化PE/PB排名 + 市值>10亿 + PE>0 + 流动性过滤 → <strong>1510只 → 80只候选</strong></p>
        <p><strong>第三轮</strong>：120日K线技术分析(RSI/均线/回撤/量能) + 综合评分(价值50%+超跌35%+流动15%) → <strong>9只A/A+级精选</strong></p>
        <p><strong>第四轮（本报告）</strong>：全模块深度分析(估值DCF+PEG+PBROE+情景/择时信号/财务三表/WACC/一致预期/VaR风控/行业竞争格局)</p>
    </div>
</div>

<!-- ═══════════ 快速概览卡片 ═══════════ -->
<h2 class="section-title">📊 9只A类精选 — 快速概览</h2>
<div class="cards-grid">
{cards_html}
</div>

<!-- ═══════════ 深度分析 ═══════════ -->
<h2 class="section-title">📋 逐只深度分析</h2>
{details_html}

<!-- ═══════════ 免责声明 ═══════════ -->
<div class="detail-block" style="border-radius:12px;margin-top:30px">
    <h3 style="color:#ff5252">📢 免责声明</h3>
    <div class="block-content">
        <p>本报告由 TG-trading-sys V4.0 系统自动生成，仅供研究参考，不构成任何投资建议。</p>
        <p>数据来源：Tushare Pro(行情/估值)、同花顺(一致预期)、新浪财经(财报三表)、腾讯财经(实时行情)。</p>
        <p>估值模型(DCF/PEG/PB-ROE)基于公开财务数据和市场参数假设，存在模型风险和参数不确定性。</p>
        <p>技术面分析基于历史价格数据，不保证未来走势。行业分析基于公开信息和合理推断。</p>
        <p>投资有风险，入市需谨慎。请结合自身情况独立判断。</p>
    </div>
</div>

<!-- Footer -->
<div class="page-footer">
    TG-trading-sys V4.0 · 生成时间 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ·
    <a href="https://github.com/A-STOCK-DATA/a-stock-data">GitHub</a>
</div>

</div>
<a href="#top" class="nav-top">↑</a>
</body>
</html>'''

# Write HTML
output_path = 'data/deep_reports/A股科技成长_深度分析报告.html'
with open(output_path, 'w', encoding='utf-8') as f:
    f.write(html)

import os as _os
size_kb = _os.path.getsize(output_path) / 1024
print(f'HTML报告已生成: {output_path} ({size_kb:.0f} KB)')
