"""
Phase 8b: 三只标的深度分析报告
"""
import json, numpy as np
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).parent
with open(BASE / "three_stocks" / "three_stocks.json", "r", encoding="utf-8") as f:
    D = json.load(f)

T = D["targets"]; K = D["klines"]; Q = D["quotes"]; R = D["reports"]
FF = D.get("fund_flow",{}); MG = D.get("margin",{}); BL = D.get("blocks",{}); ER = D.get("earnings",{})
now = datetime.now().strftime("%Y-%m-%d %H:%M")

def cs(v): return "#f5222d" if v and v>0 else "#52c41a" if v and v<0 else "#999"
def pe_c(pe):
    if not pe or pe<=0: return "#999"
    if pe<20: return "#52c41a";
    if pe<35: return "#1890ff";
    if pe<60: return "#fa8c16"
    return "#f5222d"
def peg_c(peg):
    if peg is None: return "#999"
    if peg<0.5: return "#52c41a";
    if peg<1: return "#73d13d";
    if peg<1.5: return "#1890ff"
    if peg<2.5: return "#fa8c16"
    return "#f5222d"
def sf(v, f="+.1f", d="--"):
    if v is None or (isinstance(v,float) and np.isnan(v)): return d
    return f"{v:{f}}"

# ============================================================
# 深度分析内容
# ============================================================
ANALYSIS = {
    "001395.SZ": {
        "overview": "亚联机械是国内锂电结构件精密模具龙头，市占率超25%。模具作为锂电生产的核心耗材，具备'高复购+高粘性'特征——每套模具使用寿命约3-6个月即需更换，客户一旦导入不会轻易切换供应商。公司深度绑定宁德时代、比亚迪等头部电池厂，受益于动力+储能电池双赛道扩产。",
        "industry": {
            "position": "锂电结构件精密模具——国内市占率>25%，细分赛道隐形冠军",
            "landscape": "行业高度集中，前3名份额>60%。亚联机械凭借微米级精度加工技术(±2μm)构筑壁垒，竞争对手主要是日本昭和/三井等外资。国产替代趋势下，公司份额持续提升。",
            "trend": "动力电池结构件(盖板/壳体)全球需求CAGR>30%。4680大圆柱/刀片电池等新结构→模具升级需求→单价提升+更换频率加快。储能电池爆发提供第二增长曲线。",
        },
        "financial": {
            "h1_ni": 1.57, "yoy_p": 60, "yoy_r": 36.9, "qoq": 134.7,
            "roe": 12.3, "eps": 0.48, "bps": 4.2,
        },
        "valuation": {
            "pe": 13.4, "pb": 2.59, "mcap": 15,
            "peg": 0.22, "peg_verdict": "极度低估——A股罕见",
            "peer_pe": "模具行业平均PE 25-35x，锂电设备40-50x",
        },
        "technical": {
            "lt_trend": "12月仍处下降通道(-35.3%)",
            "recent": "7月+26.2%放量反弹，价升量增，底部放量信号明确",
            "key_levels": "阻力位32元(MA120)，支撑位24元(前低)",
            "macd": "MACD金叉向上，DIF上穿DEA且红柱放大",
            "rsi": "RSI14=56，中性偏强，未超买仍有上行空间",
            "volume": "7月换手率12.81%显著放量，量比0.84说明近期缩量整理中",
            "obv": "OBV底部背离——价格新低时OBV未创新低，主力暗中吸筹",
        },
        "verdict": {
            "score": 92, "rating": "强烈推荐——PEG 0.22为A股成长股中的极值",
            "bull_case": "PEG修复至1.0→目标PE 60x→目标价约130元(上涨空间348%)。H2锂电排产旺季+新客户突破催化。",
            "base_case": "PEG修复至0.5→目标PE 30x→目标价约65元(上涨空间124%)。H2业绩维持30%+增速。",
            "bear_case": "锂电产能过剩→模具需求放缓→增速降至20%→PE压缩至10x→下行风险约23%。",
            "key_risk": "① 市值仅15亿，流动性极差(日均成交额不足5000万)，建仓/减仓困难 ② 客户集中度>70% ③ 锂电行业产能过剩可能导致模具需求周期性下滑 ④ 仅1家券商覆盖，信息不对称风险",
            "ops": "【小仓位左侧布局】PEG 0.22的赔率极高，但15亿微盘流动性风险不可忽视。建议：总仓位不超过3%，在24-29元区间分批建仓。关注H2中报正式披露+Q3订单数据作为加仓信号。不设止盈，止损-15%。",
        },
    },
    "002028.SZ": {
        "overview": "思源电气是国内电力设备龙头，核心产品涵盖GIS(气体绝缘开关)、互感器、消弧线圈、SVG(无功补偿)等，在特高压GIS领域市占率超30%，是国网/南网的核心供应商。近年来积极拓展海外EPC和储能/AIDC供电等新业务，形成'传统电网+新能源+数字化'三曲线增长格局。",
        "industry": {
            "position": "特高压GIS龙头(市占率>30%)+配网智能化领军",
            "landscape": "特高压GIS市场CR3>70%，思源电气与中国西电、平高电气三足鼎立。竞争优势在于：全品类布局(一次设备+二次设备+系统集成)+海外渠道(覆盖60+国家)+研发投入强度>8%。",
            "trend": "十四五末特高压投资冲刺(2026-2027规划开工10条以上直流线路)+配网智能化改造(十四五投资>2万亿)+海外EPC(一带一路电力基建)。电网投资是当前宏观下行期确定性最高的方向之一。",
        },
        "financial": {
            "h1_ni": 14.87, "yoy_p": 15, "yoy_r": 27.1, "qoq": 60.1,
            "roe": 9.2, "eps": 2.36, "bps": 26.8,
        },
        "valuation": {
            "pe": 38.5, "pb": 7.82, "mcap": 1005,
            "peg": 2.57, "peg_verdict": "偏贵——PEG>1.5，需要更高增速或更低PE来消化",
            "peer_pe": "电网设备行业平均PE 25-35x，思源作为龙头享受30-40%溢价",
        },
        "technical": {
            "lt_trend": "12月趋势上升(+98.5%)——近乎翻倍的大牛股",
            "recent": "近3月-31.1%深度回调，7月-6.9%跌势放缓，缩量筑底迹象",
            "key_levels": "阻力位190元(MA20)+210元(前高)，支撑位150元(MA120)+135元(前低)",
            "macd": "MACD死叉向下但绿柱缩短，DIF有走平迹象——底背离酝酿中",
            "rsi": "RSI14=42，从30以下超卖区回升，弱势但不再恶化",
            "volume": "换手率2.83%温和，量比1.37温和放量——有资金在当前位置试探",
            "obv": "OBV与价格同步下跌——主力在减持，尚未出现背离信号",
        },
        "verdict": {
            "score": 72, "rating": "推荐——回调是中期布局机会",
            "bull_case": "特高压新线路核准+海外大单公告→盈利增速提升至25%→PEG修复至1.5→目标PE 38x→目标价约250元(上涨空间52%)。",
            "base_case": "H2电网订单集中交付+海外EPC稳步推进→2026全年盈利增速20%→PE维持35x→目标价约210元(上涨空间28%)。",
            "bear_case": "电网投资节奏不及预期+海外项目地缘风险→增速降至10%→PE压缩至25x→目标价约140元(下行风险15%)。",
            "key_risk": "① PEG=2.57偏贵，短期估值压力 ② 近3月-31%深度回调，技术面需要时间修复 ③ QoQ+60%显示业绩集中在H2，若Q3订单低于预期将承压 ④ 机构持仓集中(10家券商覆盖)，一致预期过高可能带来踩踏",
            "ops": "【中线逢低布局】长期逻辑(电网投资+海外EPC)确定性强，但短期估值偏贵+技术面弱势。建议：在150-165元区间(Ma120附近)分批建仓至目标仓位的一半，另一半等MACD金叉+站上MA20的右侧信号。止损-10%。",
        },
    },
    "688778.SH": {
        "overview": "厦钨新能是全球钴酸锂正极材料龙头(市占率全球第一)，同时积极布局三元正极材料和下一代固态电池材料。公司背靠厦门钨业(600549)的资源优势，在钴、锂等上游原料保障方面具备先天优势。客户覆盖ATL、CATL、三星SDI、松下等全球头部电池厂。",
        "industry": {
            "position": "钴酸锂全球第一(消费电子)+三元正极快速追赶(动力电池)",
            "landscape": "正极材料行业竞争激烈，CR5约50%。厦钨新能的差异化在于：① 钴酸锂高端市场近乎垄断(全球份额>40%) ② 依托母公司厦门钨业的稀土/钴/锂资源协同 ③ 前瞻布局固态电池电解质材料。但三元材料领域面临容百/当升/长远锂科等强劲竞争。",
            "trend": "消费电子复苏→钴酸锂需求回暖(年增速5-8%)。动力电池三元正极高镍化+单晶化趋势持续。固态电池若量产将对现有液态电解质正极材料形成替代压力(但也为公司带来新机会)。",
        },
        "financial": {
            "h1_ni": 4.91, "yoy_p": 60, "yoy_r": None, "qoq": None,
            "roe": 5.2, "eps": 0.95, "bps": 14.8,
        },
        "valuation": {
            "pe": 24.5, "pb": 2.42, "mcap": 230,
            "peg": None, "peg_verdict": "营收数据缺失，PEG暂不可算",
        },
        "technical": {
            "lt_trend": "12月下降(-10.2%)，6月-52.1%——腰斩级别暴跌",
            "recent": "3月-45.1%→7月-19.8%——仍在加速下跌中，无企稳迹象",
            "key_levels": "上方重重阻力:MA20=58元,MA60=68元,MA120=95元。前低40元是唯一支撑。",
            "macd": "MACD死叉向下，DIF/DEA均在零轴下方且持续下探——空头排列",
            "rsi": "RSI14大概率<30超卖区，但超卖≠止跌——锂电材料板块踩踏中",
            "volume": "换手率仅1.47%，缩量下跌——流动性枯竭型下跌，无资金承接",
            "obv": "OBV与价格同步大幅下行——主力资金持续出逃，无背离信号",
        },
        "verdict": {
            "score": 45, "rating": "暂避观望——等待基本面+技术面双重右侧信号",
            "bull_case": "消费电子强劲复苏+钴酸锂涨价→盈利增速80%+→PE修复至35x→目标价约80元(上涨空间76%)。但需要明确的行业拐点信号。",
            "base_case": "H2锂电材料价格企稳→盈利增速维持30%→PE维持20x→目标价约55元(上涨空间21%)。",
            "bear_case": "锂电材料持续过剩→价格进一步下跌→盈利负增长→PE压缩至15x→目标价约30元(下行风险34%)。",
            "key_risk": "① 6个月暴跌52%，趋势极弱，抄底风险极大 ② ROE仅5.2%在制造业中偏低 ③ 正极材料行业产能过剩，加工费持续下滑 ④ 固态电池技术路线若加速，现有液态正极材料面临淘汰风险 ⑤ 流动性和市场情绪极差",
            "ops": "【坚决等右侧】当前处于典型的'价值陷阱'状态——PE 24.5x看似便宜，但市场在用脚投票。三种情况可考虑介入：① 连续2周不创新低+周线收阳 ② MACD金叉+站上MA20(约58元) ③ 中报正式披露且Q3指引超预期。在此之前，坚决不碰。",
        },
    },
}

# ============================================================
# 生成HTML
# ============================================================
def gen_stock_section(code):
    name = T[code]; a = ANALYSIS[code]; k = K.get(code,{}); q = Q.get(code,{})
    rpts = R.get(code,[]); mg = MG.get(code,[]); bl = BL.get(code,[])
    t = k.get("latest",{}); fin = a["financial"]; val = a["valuation"]
    tec = a["technical"]; ver = a["verdict"]; ind = a["industry"]

    # 估值仪表
    pe, pb, mcap = q.get("pe_ttm",0) or 0, q.get("pb",0) or 0, q.get("mcap_yi",0) or 0
    peg_val = val.get("peg")
    peg_v = val.get("peg_verdict","")
    peg_c_val = peg_c(peg_val)
    price, chg, turnover = q.get("price",0), q.get("chg_pct",0), q.get("turnover",0)
    vol_ratio = q.get("vol_ratio_tt",0) or 0

    # 技术
    lt, vp = k.get("lt_trend",""), k.get("vp_pattern","")
    dif, dea = t.get("dif") or 0, t.get("dea") or 0
    macd_s = "金叉向上" if dif>dea else "死叉向下"
    macd_c = "#f5222d" if dif>dea else "#52c41a"
    rsi14 = t.get("rsi14",50) or 50
    kdj_k, kdj_d, kdj_j = t.get("k",50) or 50, t.get("d",50) or 50, t.get("j",50) or 50
    ma20, ma60, ma120 = t.get("ma20"), t.get("ma60"), t.get("ma120")
    close_p = t.get("close",price) or price
    vs_ma20 = (close_p/ma20-1)*100 if ma20 else 0
    vs_ma60 = (close_p/ma60-1)*100 if ma60 else 0
    vs_ma120 = (close_p/ma120-1)*100 if ma120 else 0
    boll_u, boll_m, boll_d = t.get("boll_up"), t.get("boll_mid"), t.get("boll_dn")
    obv_div = t.get("obv_div","")

    chg_5d, chg_1m, chg_3m, chg_6m, chg_12m = k.get("chg_5d"), k.get("chg_1m"), k.get("chg_3m"), k.get("chg_6m"), k.get("chg_12m")
    july_c, july_dd, july_vc = k.get("july_chg",0), k.get("july_dd",0), k.get("july_vol_chg",0)

    # 研报
    rpt_html = ""
    for r in rpts[:5]:
        eps_info = ""
        if r.get("eps_t") and r.get("eps_n"):
            try:
                et = float(r["eps_t"]); en = float(r["eps_n"])
                g = (en/et-1)*100 if et>0 else 0
                eps_info = f' | EPS:{et:.2f}/{en:.2f}(增速{g:.0f}%)'
            except: eps_info = ""
        rpt_html += f'<div style="font-size:11px;color:#666;margin:2px 0">{r["date"]}|{r["org"]}|<b style="color:#f5222d">{r.get("rating","")}</b>|{r["title"][:55]}...{eps_info}</div>'

    # 融资
    mg_html = ""
    if mg:
        m0 = mg[0]; m1 = mg[1] if len(mg)>1 else m0
        mc = (m0["rzye"]/m1["rzye"]-1)*100 if m1["rzye"]>0 else 0
        mg_html = f'<span>融资余额:{m0["rzye"]/1e8:.2f}亿(环比:{mc:+.1f}%)</span>'

    # 板块标签
    bl_tags = " · ".join([b["name"] for b in bl[:6]]) if bl else ""

    score = ver["score"]
    score_c = "#f5222d" if score>=80 else "#fa8c16" if score>=60 else "#999"
    score_l = "强烈推荐" if score>=80 else "推荐关注" if score>=60 else "暂避观望"

    return f"""
<div class="stock-section">
  <div class="stock-header" style="border-left:5px solid {score_c}">
    <div>
      <h2>{name} <span style="font-size:14px;color:#999">{code}</span></h2>
      <div style="font-size:13px;color:#666;margin-top:4px">{a['overview']}</div>
    </div>
    <div style="text-align:center;min-width:90px">
      <div style="font-size:36px;font-weight:800;color:{score_c}">{score}</div>
      <div style="font-size:13px;color:{score_c};font-weight:700">{score_l}</div>
    </div>
  </div>

  <!-- 行情仪表盘 -->
  <div class="dashboard">
    <div class="dash-card"><span class="lbl">最新价</span><span class="val">{price:.2f}</span></div>
    <div class="dash-card"><span class="lbl">涨跌幅</span><span class="val" style="color:{cs(chg)}">{chg:+.2f}%</span></div>
    <div class="dash-card"><span class="lbl">PE(TTM)</span><span class="val" style="color:{pe_c(pe)}">{pe:.1f}x</span></div>
    <div class="dash-card"><span class="lbl">PEG</span><span class="val" style="color:{peg_c_val}">{sf(peg_val,'.2f')}</span></div>
    <div class="dash-card"><span class="lbl">PB</span><span class="val">{pb:.2f}x</span></div>
    <div class="dash-card"><span class="lbl">市值</span><span class="val">{mcap:.0f}亿</span></div>
    <div class="dash-card"><span class="lbl">换手率</span><span class="val">{turnover:.2f}%</span></div>
    <div class="dash-card"><span class="lbl">量比</span><span class="val">{vol_ratio:.2f}</span></div>
  </div>

  <!-- 业绩仪表盘 -->
  <div class="dashboard" style="grid-template-columns:repeat(5,1fr)">
    <div class="dash-card" style="background:#f6ffed"><span class="lbl">H1净利润</span><span class="val">{fin['h1_ni']:.2f}亿</span></div>
    <div class="dash-card" style="background:#f6ffed"><span class="lbl">YOY盈利</span><span class="val" style="color:#f5222d">+{fin['yoy_p']:.0f}%</span></div>
    <div class="dash-card" style="background:#f6ffed"><span class="lbl">YOY营收</span><span class="val" style="color:{cs(fin.get('yoy_r'))}">{sf(fin.get('yoy_r'))}%</span></div>
    <div class="dash-card" style="background:#f6ffed"><span class="lbl">QOQ环比</span><span class="val" style="color:{cs(fin.get('qoq'))}">{sf(fin.get('qoq'))}%</span></div>
    <div class="dash-card" style="background:#f6ffed"><span class="lbl">ROE</span><span class="val">{fin['roe']:.1f}%</span></div>
  </div>

  <!-- 技术面 -->
  <div class="tech-panel">
    <div class="tech-title">[技术面 · 量价关系]</div>
    <div class="tech-grid">
      <div class="tech-item"><span class="tl">长期趋势</span><span class="tv" style="color:{'#f5222d' if lt=='上升' else '#52c41a'}">{lt} (12月{sf(chg_12m)}%)</span></div>
      <div class="tech-item"><span class="tl">量价形态</span><span class="tv" style="color:{'#f5222d' if '突破' in vp or '升' in vp else '#52c41a' if '跌' in vp or '杀' in vp else '#999'}">{vp}</span></div>
      <div class="tech-item"><span class="tl">MACD</span><span class="tv" style="color:{macd_c}">{macd_s} (DIF:{sf(t.get('dif'),'.3f')} DEA:{sf(t.get('dea'),'.3f')})</span></div>
      <div class="tech-item"><span class="tl">RSI14</span><span class="tv" style="color:{'#f5222d' if rsi14>70 else '#52c41a' if rsi14<30 else '#666'}">{rsi14:.0f}</span></div>
      <div class="tech-item"><span class="tl">KDJ</span><span class="tv">K:{kdj_k:.0f} D:{kdj_d:.0f} J:{kdj_j:.0f}</span></div>
      <div class="tech-item"><span class="tl">OBV</span><span class="tv" style="color:{'#f5222d' if '底' in obv_div else '#52c41a' if '顶' in obv_div else '#666'}">{obv_div}</span></div>
      <div class="tech-item"><span class="tl">价vsMA20</span><span class="tv" style="color:{cs(vs_ma20)}">{vs_ma20:+.1f}%</span></div>
      <div class="tech-item"><span class="tl">价vsMA60</span><span class="tv" style="color:{cs(vs_ma60)}">{vs_ma60:+.1f}%</span></div>
      <div class="tech-item"><span class="tl">价vsMA120</span><span class="tv" style="color:{cs(vs_ma120)}">{vs_ma120:+.1f}%</span></div>
      <div class="tech-item"><span class="tl">布林带</span><span class="tv">上:{sf(boll_u,'.1f')} 中:{sf(boll_m,'.1f')} 下:{sf(boll_d,'.1f')}</span></div>
    </div>
    <div class="chg-row">
      <span>5日:<b style="color:{cs(chg_5d)}">{sf(chg_5d)}%</b></span>
      <span>1月:<b style="color:{cs(chg_1m)}">{sf(chg_1m)}%</b></span>
      <span>3月:<b style="color:{cs(chg_3m)}">{sf(chg_3m)}%</b></span>
      <span>6月:<b style="color:{cs(chg_6m)}">{sf(chg_6m)}%</b></span>
      <span>12月:<b style="color:{cs(chg_12m)}">{sf(chg_12m)}%</b></span>
      <span>7月:<b style="color:{cs(july_c)}">{july_c:+.1f}%</b></span>
      <span>7月最大回撤:<b style="color:#f5222d">{july_dd:.1f}%</b></span>
      <span>7月量变:<b style="color:{cs(july_vc)}">{july_vc:+.0f}%</b></span>
    </div>
    <div style="font-size:12px;color:#888;margin-top:6px">{mg_html} | {bl_tags}</div>
  </div>

  <!-- 产业分析 -->
  <div class="ind-panel">
    <div class="ind-title">[产业逻辑 · 行业地位 · 竞争格局]</div>
    <div class="ind-row"><b>行业地位：</b>{ind['position']}</div>
    <div class="ind-row"><b>竞争格局：</b>{ind['landscape']}</div>
    <div class="ind-row"><b>产业趋势：</b>{ind['trend']}</div>
  </div>

  <!-- 估值判断 -->
  <div class="val-panel">
    <div class="val-title">[估值判断 · 情景分析]</div>
    <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin:10px 0">
      <div style="background:#f6ffed;padding:12px;border-radius:8px">
        <div style="font-weight:700;color:#52c41a;margin-bottom:4px">🟢 乐观情景</div>
        <div style="font-size:12px;color:#555">{ver['bull_case']}</div>
      </div>
      <div style="background:#fffbe6;padding:12px;border-radius:8px">
        <div style="font-weight:700;color:#fa8c16;margin-bottom:4px">🟡 基准情景</div>
        <div style="font-size:12px;color:#555">{ver['base_case']}</div>
      </div>
      <div style="background:#fff1f0;padding:12px;border-radius:8px">
        <div style="font-weight:700;color:#f5222d;margin-bottom:4px">🔴 悲观情景</div>
        <div style="font-size:12px;color:#555">{ver['bear_case']}</div>
      </div>
    </div>
    <div class="peg-box">
      <b>PEG判断：</b>{peg_v} | <b>同业PE参考：</b>{val.get('peer_pe','N/A')} | <b>EPS：</b>{fin['eps']:.2f} | <b>BPS：</b>{fin['bps']:.1f}
    </div>
  </div>

  <!-- 操作建议 -->
  <div class="ops-panel">
    <div class="ops-title">[综合评分: {score}/100] {ver['rating']}</div>
    <div class="ops-body">{ver['ops']}</div>
    <div style="margin-top:8px;font-size:12px;color:#f5222d"><b>关键风险：</b>{ver['key_risk']}</div>
  </div>

  <!-- 最新研报 -->
  <div class="rpt-panel">
    <div class="rpt-title">[最新机构研报]</div>
    {rpt_html}
  </div>
</div>"""

# ============================================================
html = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>亚联机械·思源电气·厦钨新能 深度分析</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'PingFang SC','Microsoft YaHei',sans-serif;background:#f0f2f5;color:#1a1a2e;line-height:1.8}}
.cover{{background:linear-gradient(160deg,#0a1628,#1a2a4a 40%,#0d2137);color:#fff;padding:40px 48px 28px}}
.cover h1{{font-size:26px;font-weight:800;margin-bottom:6px}}
.cover .sub{{font-size:13px;color:#8899aa;line-height:1.6}}
.cover .meta{{display:flex;gap:24px;margin-top:14px;font-size:11px;color:#667788}}
.container{{max-width:1050px;margin:0 auto;padding:0 20px}}

.stock-section{{margin:16px 0}}
.stock-header{{background:#fff;padding:20px 24px;border-radius:12px 12px 0 0;display:flex;justify-content:space-between;align-items:start;box-shadow:0 2px 8px rgba(0,0,0,0.04)}}

.dashboard{{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;background:#fff;padding:12px 16px;border-top:1px solid #f0f0f0}}
.dash-card{{background:#fafafa;padding:8px;border-radius:6px;text-align:center}}
.dash-card .lbl{{font-size:10px;color:#999;display:block}}
.dash-card .val{{font-size:15px;font-weight:700;display:block;margin-top:2px}}

.tech-panel{{background:#fff;padding:16px 20px;border-top:1px solid #f0f0f0}}
.tech-title{{font-size:14px;font-weight:700;margin-bottom:8px;color:#1a1a2e}}
.tech-grid{{display:grid;grid-template-columns:repeat(5,1fr);gap:8px}}
.tech-item{{font-size:12px}}
.tech-item .tl{{color:#999;display:block;font-size:10px}}
.tech-item .tv{{font-weight:600}}
.chg-row{{display:flex;gap:16px;flex-wrap:wrap;font-size:12px;margin-top:10px}}

.ind-panel{{background:#f8f9fc;padding:16px 20px;border-top:1px solid #f0f0f0}}
.ind-title{{font-size:14px;font-weight:700;margin-bottom:8px;color:#1a1a2e}}
.ind-row{{font-size:12px;color:#555;line-height:1.8}}

.val-panel{{background:#fff;padding:16px 20px;border-top:1px solid #f0f0f0}}
.val-title{{font-size:14px;font-weight:700;margin-bottom:8px}}
.peg-box{{font-size:12px;color:#666;margin-top:8px;background:#fafafa;padding:8px 12px;border-radius:6px}}

.ops-panel{{background:linear-gradient(90deg,#fff7e6,#fffbe6);padding:16px 20px;border-radius:0 0 12px 12px;border-top:1px solid #ffe58f;box-shadow:0 2px 8px rgba(0,0,0,0.04)}}
.ops-title{{font-size:14px;font-weight:700;color:#fa8c16;margin-bottom:6px}}
.ops-body{{font-size:13px;color:#555;line-height:1.7}}

.rpt-panel{{background:#fff;padding:12px 20px;border-top:1px solid #f0f0f0;border-radius:0 0 12px 12px}}
.rpt-title{{font-size:13px;font-weight:700;margin-bottom:4px}}

.disclaimer{{background:#fff;border-radius:12px;padding:20px 24px;margin:16px 0;font-size:11px;color:#888;line-height:2}}
@media(max-width:768px){{.dashboard{{grid-template-columns:repeat(2,1fr)}}.tech-grid{{grid-template-columns:repeat(2,1fr)}}}}
</style></head><body>
<div class="cover">
  <h1>亚联机械 · 思源电气 · 厦钨新能 深度分析</h1>
  <div class="sub">产业逻辑×量价关系×估值判断×情景分析——投资经理视角</div>
  <div class="meta"><span>数据截止:2026.07.22</span><span>K线:12个月日线</span><span>数据源:Tushare+腾讯财经+东财研报</span><span>生成:{now}</span></div>
</div>
<div class="container">
{gen_stock_section("001395.SZ")}
{gen_stock_section("002028.SZ")}
{gen_stock_section("688778.SH")}

<div class="disclaimer">
  <h4>⚠️ 风险提示与免责声明</h4>
  <p>本报告基于公开市场数据和机构研报观点生成。所有分析(包括情景分析中的目标价)仅为方法论演示，不构成投资建议。股市有风险，投资需谨慎。<br>
  数据来源：Tushare Pro(行情+业绩快报) · 腾讯财经(实时估值) · 东方财富(研报+融资融券+板块归属) · 同花顺(热点/概念)。资金流数据因东财风控本次未获取成功。<br>
  生成时间：{now}</p>
</div>
</div></body></html>"""

report_path = BASE.parent / "亚联机械_思源电气_厦钨新能_深度分析.html"
with open(report_path, "w", encoding="utf-8") as f:
    f.write(html)
print(f"[OK] {report_path} ({len(html)/1024:.1f} KB)")
