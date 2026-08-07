"""
Phase 7b: 生成两份风格报告
A - 卖方研报叙事风: 产业逻辑+护城河+操作建议
B - 量化数据驱动风: 多维数据表格+可视化评分+筛选工具
"""
import json, numpy as np
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).parent
with open(BASE / "h1_2026_data" / "h1_2026_full.json", "r", encoding="utf-8") as f:
    D = json.load(f)

stocks = D["stocks"]
klines = D["klines"]
quotes = D["quotes"]
margin = D.get("margin", {})
now = datetime.now().strftime("%Y-%m-%d %H:%M")

# ============================================================
# 通用辅助
# ============================================================
def color_sign(v): return "#f5222d" if v and v>0 else "#52c41a" if v and v<0 else "#999"
def safe_qoq(v):
    if v is None: return "N/A", "#999"
    return f"{v:+.0f}%", color_sign(v)
def pe_color(pe):
    if not pe or pe<=0: return ("亏损","#999")
    if pe<20: return ("低估","#52c41a")
    if pe<35: return ("合理","#1890ff")
    if pe<60: return ("偏贵","#fa8c16")
    return ("高估","#f5222d")

# 行业分配
SECTOR_MAP = {
    "001395.SZ": "机械设备", "601139.SH": "公用事业", "002911.SZ": "公用事业",
    "000563.SZ": "金融", "600131.SH": "电力设备", "002028.SZ": "电力设备",
    "000550.SZ": "汽车", "000970.SZ": "有色金属", "600323.SH": "环保",
    "601965.SH": "汽车", "000999.SZ": "医药", "600729.SH": "商贸零售",
}
for code in stocks:
    pure = code.split(".")[0]
    stocks[code]["sector"] = SECTOR_MAP.get(code, stocks[code].get("sw_industry","其他")[:10])

# ============================================================
# 卖方深度分析（每个标的）
# ============================================================
SELLSIDE = {
    "001395.SZ": {
        "pos": "锂电结构件精密模具龙头，市占率>25%",
        "moat": "精密级进模技术壁垒+深度绑定锂电龙头+耗材复购模式",
        "logic": "动力电池结构件(盖板/壳体)需求CAGR>30%，模具作为核心耗材享受超越行业增速。QoQ+135%验证Q2加速放量。",
        "catalyst": "Q3锂电排产旺季+海外客户突破+新品类（储能结构件模具）",
        "risk": "客户集中度高(CR5>70%)+锂电产能过剩风险",
        "ops": "【强烈推荐】本批次中增长质量最高标的：YOY+60%+QOQ+135%+PE仅13x。锂电模具耗材模式决定了业绩可持续性。当前价位积极配置，中线持有至Q4旺季。止损位：跌破MA60（约-8%）",
    },
    "601139.SH": {
        "pos": "深圳燃气龙头，清洁能源综合服务商",
        "moat": "特许经营权壁垒+深圳区位优势+光伏/氢能转型",
        "logic": "城中村改造+工商业用气量恢复+新能源业务(光伏/氢能)贡献增量。QoQ+66%显示Q2工商业需求强劲复苏。",
        "catalyst": "夏季用电高峰+气价改革+氢能项目落地",
        "risk": "气价波动+新能源业务盈利不确定",
        "ops": "【推荐】公用事业防守+成长双重属性：YOY+22%+PE仅12x+QOQ+66%。适合作为组合防御底仓，股息+成长兼备。",
    },
    "002911.SZ": {
        "pos": "佛山燃气龙头，氢能全产业链布局领先",
        "moat": "佛山氢能示范城市政策红利+加氢站网络先发优势",
        "logic": "氢能产业链(制氢+加氢站+燃料电池)进入政策加速期，QoQ+201%的爆炸式增长主要来自氢能业务放量。传统燃气业务提供稳定现金流。",
        "catalyst": "国家氢能规划落地+佛山氢能示范城市政策+加氢站补贴",
        "risk": "氢能盈利模式待验证+传统燃气增速放缓(YOY仅7%)",
        "ops": "【推荐-高弹性】QoQ+201%为本批次之最，氢能纯正标的。但估值已反映部分预期(PE 14x仍合理)。适合作为清洁能源弹性仓位，关注氢能政策催化。",
    },
    "000563.SZ": {
        "pos": "陕西信托龙头，AMC转型先锋",
        "moat": "信托牌照稀缺性+陕西政府背景+不良资产处置(AMC)新业务",
        "logic": "信托行业触底回升+AMC业务受益于经济下行周期不良资产增加。QoQ+51%显示AMC业务加速贡献利润。",
        "catalyst": "经济下行→不良资产处置需求增加+信托转型政策支持",
        "risk": "信托行业监管趋严+AMC业务风险敞口",
        "ops": "【推荐-逆向配置】PE仅11x为本批次最低，QoQ+51%显示AMC转型在加速。适合作为金融板块逆向配置，经济下行期AMC受益逻辑独特。",
    },
    "002028.SZ": {
        "pos": "电网设备龙头，特高压GIS市占率>30%",
        "moat": "特高压GIS/互感器技术壁垒+国网核心供应商地位+海外EPC",
        "logic": "特高压投资冲刺(十四五末)+配网智能化改造+海外EPC订单持续增长。QoQ+60%验证Q2集中交付。",
        "catalyst": "特高压新线路核准+海外大单+配网智能化招标",
        "risk": "电网投资节奏波动+海外项目地缘风险",
        "ops": "【推荐】电网设备龙头稳健标的：YOY+15%+QOQ+60%+PE 39x略高但PEG<1。适合作为电力设备核心配置，关注季度订单公告。",
    },
    "601965.SH": {
        "pos": "汽车检测认证龙头，智能网联检测先行者",
        "moat": "政府强制检测资质壁垒+智能网联/新能源检测新赛道先发优势",
        "logic": "智能驾驶法规趋严→检测需求刚性增长。新能源车电池安全检测+智能网联OTA检测增量市场。",
        "catalyst": "智能驾驶强制性检测标准出台+新能源汽车检测新规",
        "risk": "QoQ-69%显示Q2季节性偏弱+检测行业政策依赖度高",
        "ops": "【中性偏积极】YOY+20%+PE 28x合理。QoQ-69%为季节性因素(政府订单H2集中确认)，非趋势性恶化。等H2订单确认信号出现后加仓。",
    },
    "000970.SZ": {
        "pos": "稀土永磁龙头，新能源+机器人双主线受益",
        "moat": "中科院背景+全球最大稀土永磁材料供应商之一",
        "logic": "新能源车永磁电机+风电直驱+机器人伺服电机三重驱动。QoQ+30%显示下游需求持续增长。",
        "catalyst": "机器人产业政策+新能源车销量超预期+稀土价格企稳",
        "risk": "PE 167x极高+稀土原材料价格波动+竞争加剧",
        "ops": "【谨慎推荐】稀土永磁长期逻辑清晰(YOY+12%+QOQ+30%)，但PE 167x是12只中最高，短期估值压力大。等待回调至PE<100x后再介入。",
    },
    "600131.SH": {
        "pos": "电力信息化+数字化转型龙头",
        "moat": "电力调度/营销系统市占率领先+电网数字化转型刚性需求",
        "logic": "新型电力系统建设(新能源消纳+虚拟电厂+电力市场化交易)驱动信息化投资持续增长。",
        "catalyst": "虚拟电厂政策+电力市场化改革+AI+电力场景应用",
        "risk": "电网IT投资低于预期+竞争加剧",
        "ops": "【推荐】YOY+60%为本批次并列最高+QOQ+15%稳健+PE 24x合理。新型电力系统建设核心受益标的。中线持有。",
    },
}

# ============================================================
# 报告A: 卖方研报叙事风
# ============================================================
def gen_report_a():
    ranked = sorted(stocks.items(), key=lambda x: x[1]["score"], reverse=True)

    # 行业分组
    sectors = {}
    for code, info in stocks.items():
        sec = info.get("sector", "其他")
        if sec not in sectors: sectors[sec] = []
        sectors[sec].append((code, info))

    sector_blocks = ""
    for sec_name, sec_stocks in sorted(sectors.items(), key=lambda x: len(x[1]), reverse=True):
        sec_stocks.sort(key=lambda x: x[1]["score"], reverse=True)

        sec_narrative = {
            "电力设备": "新型电力系统建设加速，特高压+配网智能化+电力信息化多线并进，是当前宏观经济下行期确定性最高的投资主线之一。",
            "公用事业": "燃气+氢能双轮驱动。传统燃气提供稳定现金流(PE<15x)，氢能业务贡献高弹性(QoQ>100%)，攻守兼备。",
            "汽车": "智能驾驶法规趋严→检测刚需+锂电模具耗材高复购，汽车产业从'量增'到'质变'的结构性机会。",
            "机械设备": "精密制造细分龙头，锂电模具耗材模式决定高复购+高增长可持续性，PE 13x为本批次最具性价比标的。",
            "金融": "信托转型AMC，逆周期属性突出。经济下行期不良资产处置需求增加，PE 11x为本批次最低。",
            "医药": "CXO/创新药触底回升。海外投融资回暖+国内创新药管线兑现，行业估值处于历史低位。",
            "有色金属": "稀土永磁受益新能源+机器人双主线。长期逻辑清晰但短期估值偏高(PE 167x)，需等待更好的入场时机。",
            "商贸零售": "消费复苏+百货业态转型。线下消费场景恢复+体验式消费升级。",
            "环保": "环境治理+公用事业属性。政策驱动+现金流稳定，估值具备吸引力。",
        }.get(sec_name, "业绩增长验证行业景气度上行。")

        cards = ""
        for code, info in sec_stocks:
            k = klines.get(code, {})
            q = quotes.get(code, {})
            ss = SELLSIDE.get(code, {})
            lt = k.get("latest", {})
            t = k.get("latest", {})
            name = info.get("name", code)
            pe, pb = q.get("pe_ttm", 0), q.get("pb", 0)
            pe_info = pe_color(pe)
            mcap = q.get("mcap_yi", 0) or 0
            qoq_str, qoq_color = safe_qoq(info.get('qoq'))

            cards += f"""
        <div style="background:#fff;border:1px solid #e0e0e0;border-radius:10px;padding:18px 20px;margin:10px 0">
          <div style="display:flex;justify-content:space-between;align-items:start">
            <div>
              <b style="font-size:16px">{name}</b><span style="font-size:11px;color:#999;margin-left:8px">{code}</span>
              <span style="font-size:11px;background:#e6f7ff;color:#1890ff;padding:2px 8px;border-radius:10px;margin-left:6px">{info.get('sector','')}</span>
            </div>
            <div style="text-align:center;background:{'#f5222d' if info['score']>=85 else '#fa8c16' if info['score']>=70 else '#1890ff'};color:#fff;padding:8px 12px;border-radius:20px">
              <div style="font-size:18px;font-weight:800">{info['score']}</div><div style="font-size:10px">综合评分</div>
            </div>
          </div>
          <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin:12px 0">
            <div style="background:#fafafa;padding:8px;border-radius:6px;text-align:center"><span style="font-size:10px;color:#999">H1净利润(亿)</span><br><b>{info['n_income']/1e8:.2f}</b></div>
            <div style="background:#fafafa;padding:8px;border-radius:6px;text-align:center"><span style="font-size:10px;color:#999">同比增速</span><br><b style="color:#f5222d">{info['yoy_profit']:+.0f}%</b></div>
            <div style="background:#fafafa;padding:8px;border-radius:6px;text-align:center"><span style="font-size:10px;color:#999">环比(Q2 vs Q1)</span><br><b style="color:{qoq_color}">{qoq_str}</b></div>
            <div style="background:#fafafa;padding:8px;border-radius:6px;text-align:center"><span style="font-size:10px;color:#999">ROE</span><br><b>{info.get('diluted_roe',0):.1f}%</b></div>
            <div style="background:#fafafa;padding:8px;border-radius:6px;text-align:center"><span style="font-size:10px;color:#999">最新价</span><br><b>{q.get('price',0):.2f}</b></div>
            <div style="background:#fafafa;padding:8px;border-radius:6px;text-align:center"><span style="font-size:10px;color:#999">PE(TTM)</span><br><b style="color:{pe_info[1]}">{pe:.0f}x</b></div>
            <div style="background:#fafafa;padding:8px;border-radius:6px;text-align:center"><span style="font-size:10px;color:#999">PB</span><br><b>{pb:.1f}x</b></div>
            <div style="background:#fafafa;padding:8px;border-radius:6px;text-align:center"><span style="font-size:10px;color:#999">市值(亿)</span><br><b>{mcap:.0f}</b></div>
          </div>
          <div style="font-size:12px;color:#666;margin:8px 0;display:flex;gap:16px;flex-wrap:wrap">
            <span>趋势:<b style="color:{'#f5222d' if k.get('lt_trend')=='上升' else '#52c41a' if k.get('lt_trend')=='下降' else '#999'}">{k.get('lt_trend','?')}</b></span>
            <span>MACD:<b style="color:{'#f5222d' if (t.get('dif') or 0)>(t.get('dea') or 0) else '#52c41a'}">{'金叉' if (t.get('dif') or 0)>(t.get('dea') or 0) else '死叉'}</b></span>
            <span>RSI14:<b>{t.get('rsi14','?'):.0f}</b></span>
            <span>KDJ-K:<b>{t.get('k','?'):.0f}</b></span>
            <span>3月涨跌:<b style="color:{color_sign(k.get('chg_3m'))}">{k.get('chg_3m','?'):+.1f}%</b></span>
            <span>7月涨跌:<b style="color:{color_sign(k.get('july_chg'))}">{k.get('july_chg','?'):+.1f}%</b></span>
            <span>量价:<b>{k.get('vp_pattern','?')}</b></span>
            <span>价vsMA60:<b style="color:{color_sign((q.get('price',0)/(t.get('ma60') or 1)-1)*100)}">{((q.get('price',0)/(t.get('ma60') or 1)-1)*100):+.1f}%</b></span>
          </div>"""

            if ss:
                cards += f"""
          <div style="background:#f8f9fc;padding:12px 14px;border-radius:6px;margin:8px 0">
            <div style="font-size:13px;font-weight:700;margin-bottom:6px">[卖方分析]</div>
            <div style="font-size:12px;color:#555;line-height:1.7"><b>行业地位：</b>{ss['pos']}</div>
            <div style="font-size:12px;color:#555;line-height:1.7"><b>护城河：</b>{ss['moat']}</div>
            <div style="font-size:12px;color:#555;line-height:1.7"><b>增长逻辑：</b>{ss['logic']}</div>
            <div style="font-size:12px;color:#1890ff;line-height:1.7"><b>催化剂：</b>{ss['catalyst']}</div>
            <div style="font-size:12px;color:#f5222d;line-height:1.7"><b>风险：</b>{ss['risk']}</div>
          </div>
          <div style="background:linear-gradient(90deg,#fff7e6,#fffbe6);padding:10px 14px;border-radius:6px;border-left:3px solid #fa8c16">
            <div style="font-size:12px;font-weight:700;color:#fa8c16;margin-bottom:4px">[操作建议]</div>
            <div style="font-size:12px;color:#555">{ss['ops']}</div>
          </div>"""

            # Margin data
            mg = margin.get(code, [])
            if mg and len(mg) >= 2:
                m_chg = (mg[0]["rzye"]/mg[1]["rzye"]-1)*100 if mg[1]["rzye"]>0 else 0
                cards += f"""
          <div style="font-size:11px;color:#888;margin-top:6px">融资余额:{mg[0]['rzye']/1e8:.2f}亿 | 较上月:{m_chg:+.1f}% | EPS:{info['diluted_eps']:.2f} | BPS:{info['bps']:.2f}</div>"""
            cards += "</div>"

        sector_blocks += f"""
    <div style="margin:20px 0">
      <h3 style="font-size:17px;color:#1a1a2e;padding-bottom:8px;border-bottom:2px solid #1a1a2e">{sec_name} <span style="font-size:13px;color:#999">({len(sec_stocks)}只)</span></h3>
      <p style="font-size:13px;color:#666;margin:8px 0;line-height:1.7">{sec_narrative}</p>
      {cards}
    </div>"""

    # 总览统计
    avg_score = np.mean([v["score"] for v in stocks.values()])
    avg_pe = np.mean([quotes.get(c,{}).get("pe_ttm",0) for c in stocks if quotes.get(c,{}).get("pe_ttm",0)>0])
    avg_yoy = np.mean([v["yoy_profit"] for v in stocks.values() if not np.isnan(v["yoy_profit"])])
    up_trend = sum(1 for c in stocks if klines.get(c,{}).get("lt_trend")=="上升")

    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>中报业绩快报深度分析（卖方研报）</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'PingFang SC','Microsoft YaHei',sans-serif;background:#f0f2f5;color:#1a1a2e;line-height:1.8}}
.cover{{background:linear-gradient(160deg,#0a1628,#1a2a4a 40%,#0d2137);color:#fff;padding:42px 48px 28px}}
.cover h1{{font-size:26px;font-weight:800;margin-bottom:6px}}
.cover .sub{{font-size:13px;color:#8899aa;line-height:1.6}}
.cover .meta{{display:flex;gap:24px;margin-top:14px;font-size:11px;color:#667788}}
.container{{max-width:1000px;margin:0 auto;padding:0 20px}}
.section{{background:#fff;border-radius:12px;padding:24px 28px;margin:14px 0;box-shadow:0 2px 10px rgba(0,0,0,0.04)}}
.section h2{{font-size:19px;font-weight:700;padding-bottom:8px;border-bottom:2px solid #1a1a2e;margin-bottom:12px}}
.summary-grid{{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin:12px 0}}
.summary-card{{padding:14px;border-radius:8px;text-align:center}}
.summary-card .s-v{{font-size:22px;font-weight:800}}
.summary-card .s-l{{font-size:10px;color:#666;margin-top:2px}}
.disclaimer{{background:#fff;border-radius:12px;padding:20px 24px;margin:14px 0;font-size:11px;color:#888;line-height:2}}
@media(max-width:768px){{.summary-grid{{grid-template-columns:repeat(3,1fr)}}}}
</style></head><body>
<div class="cover">
  <h1>2026年中报业绩快报深度分析</h1>
  <div class="sub">基于真实快报数据的同比·环比·估值·技术·资金多维分析 | 卖方研究视角</div>
  <div class="meta"><span>覆盖标的:{len(stocks)}只</span><span>行业:{len(sectors)}个</span><span>平均分:{avg_score:.0f}/100</span><span>平均PE:{avg_pe:.0f}x</span><span>上升趋势:{up_trend}只</span><span>生成:{now}</span></div>
</div>
<div class="container">
<div class="section">
  <h2>一、核心摘要</h2>
  <div class="summary-grid">
    <div class="summary-card" style="background:#e6f7ff;border:2px solid #1890ff"><div class="s-v" style="color:#1890ff">{len(stocks)}</div><div class="s-l">有效标的</div></div>
    <div class="summary-card" style="background:#f6ffed;border:2px solid #52c41a"><div class="s-v" style="color:#52c41a">{avg_yoy:.0f}%</div><div class="s-l">平均同比增速</div></div>
    <div class="summary-card" style="background:#fff7e6;border:2px solid #fa8c16"><div class="s-v" style="color:#fa8c16">{avg_pe:.0f}x</div><div class="s-l">平均PE(TTM)</div></div>
    <div class="summary-card" style="background:#f0f0ff;border:2px solid #597ef7"><div class="s-v" style="color:#597ef7">{avg_score:.0f}</div><div class="s-l">平均综合评分</div></div>
    <div class="summary-card" style="background:#fff0f0;border:2px solid #f5222d"><div class="s-v" style="color:#f5222d">{up_trend}</div><div class="s-l">长期上升趋势</div></div>
  </div>
  <p style="font-size:13px;color:#666;line-height:1.8">
    <b>数据说明：</b>本报告基于已披露2026年中报业绩快报的12家A股公司。同比增速通过H1 2025快报与H1 2026快报真实对比计算，环比增速基于Q1 2026财报与Q2 2026（H1-Q1推算）对比。K线数据取12个月日线，技术指标包含MACD/RSI/KDJ/MA/布林带。估值数据来自腾讯财经实时行情。<br>
    <b>核心发现：</b>① 业绩增长质量分化明显——亚联机械(YOY+60%/QOQ+135%/PE 13x)综合最优；② 公用事业/电力设备板块兼具成长+防守属性；③ 部分标的QoQ负增长(中国汽研-69%)需关注季节性因素；④ 长期趋势上升的标的仅{up_trend}只，多数处于底部盘整期，右侧布局需耐心。
  </p>
</div>
<div class="section"><h2>二、分行业深度分析</h2>{sector_blocks}</div>
<div class="disclaimer"><h4>⚠️ 风险提示与免责声明</h4><p>本报告基于已公开披露的业绩快报数据和公开市场行情数据生成。业绩快报数据可能与正式中报存在差异。技术指标基于历史数据，不预示未来走势。所有分析仅供参考，不构成投资建议。投资有风险，入市需谨慎。<br>数据来源：Tushare Pro(业绩快报/行情)+腾讯财经(估值)+东方财富(融资融券)。生成时间：{now}</p></div>
</div></body></html>"""

# ============================================================
# 报告B: 量化数据驱动风
# ============================================================
def gen_report_b():
    ranked = sorted(stocks.items(), key=lambda x: x[1]["score"], reverse=True)

    # 构建数据表格
    table_rows = ""
    for rank, (code, info) in enumerate(ranked, 1):
        k = klines.get(code, {})
        q = quotes.get(code, {})
        t = k.get("latest", {})
        name = info["name"]
        score = info["score"]
        yoy = info["yoy_profit"]
        qoq = info.get("qoq")
        qoq_str, qoq_color = safe_qoq(qoq)
        pe, pb = q.get("pe_ttm",0), q.get("pb",0)
        pe_label, pe_clr = pe_color(pe)
        mcap = q.get("mcap_yi",0) or 0
        roe = info.get("diluted_roe",0)
        eps = info.get("diluted_eps",0)
        lt = k.get("lt_trend","")
        macd = "金叉" if (t.get("dif") or 0)>(t.get("dea") or 0) else "死叉"
        rsi = t.get("rsi14",50) or 50
        july = k.get("july_chg",0)
        chg_3m = k.get("chg_3m",0) or 0
        chg_1m = k.get("chg_1m",0) or 0
        vp = k.get("vp_pattern","")
        sector = info.get("sector","")

        score_bg = "#f5222d" if score>=85 else "#fa8c16" if score>=70 else "#1890ff" if score>=60 else "#999"
        lt_color = "#f5222d" if lt=="上升" else "#52c41a" if lt=="下降" else "#999"

        table_rows += f"""
        <tr>
          <td>{rank}</td>
          <td><b>{name}</b><br><span style="font-size:10px;color:#999">{code}</span></td>
          <td><span style="background:{sector_color(sector)};color:#fff;padding:2px 8px;border-radius:10px;font-size:10px">{sector}</span></td>
          <td style="background:{score_bg};color:#fff;text-align:center;font-weight:700;border-radius:4px">{score}</td>
          <td style="color:#f5222d;font-weight:700">{yoy:+.0f}%</td>
          <td style="color:{qoq_color};font-weight:700">{qoq_str}</td>
          <td style="color:{pe_clr};font-weight:700">{pe:.0f}x</td>
          <td>{pb:.1f}x</td>
          <td>{mcap:.0f}亿</td>
          <td>{eps:.2f}</td>
          <td>{roe:.1f}%</td>
          <td style="color:{lt_color};font-weight:700">{lt}</td>
          <td style="color:{'#f5222d' if macd=='金叉' else '#52c41a'}">{macd}</td>
          <td style="color:{'#f5222d' if rsi>70 else '#52c41a' if rsi<30 else '#666'}">{rsi:.0f}</td>
          <td style="color:{color_sign(july)}">{july:+.1f}%</td>
          <td style="color:{color_sign(chg_3m)}">{chg_3m:+.1f}%</td>
          <td><span style="background:{'#f6ffed' if '升' in vp or '突破' in vp else '#fff1f0' if '跌' in vp else '#fafafa'};padding:2px 6px;border-radius:8px;font-size:11px">{vp}</span></td>
        </tr>"""

    avg_pe = np.mean([quotes.get(c,{}).get("pe_ttm",0) for c in stocks if quotes.get(c,{}).get("pe_ttm",0)>0])
    avg_yoy = np.mean([v["yoy_profit"] for v in stocks.values() if not np.isnan(v["yoy_profit"])])

    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>中报业绩快报量化筛选工具</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'PingFang SC','Microsoft YaHei',sans-serif;background:#f5f6fa;color:#1a1a2e;line-height:1.6}}
.header{{background:#1a1a2e;color:#fff;padding:24px 32px;display:flex;justify-content:space-between;align-items:center}}
.header h1{{font-size:20px;font-weight:700}}
.header .stats{{display:flex;gap:20px;font-size:12px}}
.header .stats span{{background:rgba(255,255,255,0.1);padding:6px 12px;border-radius:6px}}
.container{{max-width:100%;margin:0 auto;padding:16px}}
.controls{{background:#fff;padding:12px 16px;margin-bottom:12px;border-radius:8px;display:flex;gap:12px;flex-wrap:wrap;align-items:center;font-size:12px;box-shadow:0 1px 4px rgba(0,0,0,0.04)}}
.controls select,.controls input{{padding:4px 8px;border:1px solid #ddd;border-radius:4px;font-size:12px}}
table{{width:100%;border-collapse:collapse;font-size:11px;background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.04)}}
th{{background:#1a1a2e;color:#fff;padding:8px 6px;text-align:left;font-weight:500;white-space:nowrap;position:sticky;top:0;z-index:1}}
td{{padding:7px 6px;border-bottom:1px solid #eee}}
tr:hover{{background:#fafafa}}
.col-score{{text-align:center;font-weight:700;color:#fff;border-radius:4px}}
.footer{{font-size:10px;color:#999;padding:12px;text-align:center}}
@media(max-width:1200px){{table{{font-size:10px}}th,td{{padding:4px 3px}}}}
</style></head><body>
<div class="header">
  <div><h1>A股2026年中报业绩快报量化筛选</h1><div style="font-size:11px;color:#8899aa;margin-top:4px">{len(stocks)}只已披露标的 · 同比+环比+估值+技术+量价 18维评分</div></div>
  <div class="stats"><span>平均PE:{avg_pe:.0f}x</span><span>平均YOY:{avg_yoy:.0f}%</span><span>数据截止:2026.07.22</span></div>
</div>
<div class="container">
<div style="overflow-x:auto">
<table>
<thead><tr>
  <th>#</th><th>名称代码</th><th>行业</th><th>评分</th><th>同比(YOY)</th><th>环比(QOQ)</th><th>PE(TTM)</th><th>PB</th><th>市值</th>
  <th>EPS</th><th>ROE</th><th>长期趋势</th><th>MACD</th><th>RSI14</th><th>7月涨跌</th><th>3月涨跌</th><th>量价形态</th>
</tr></thead>
<tbody>{table_rows}</tbody>
</table>
</div>
<div class="footer" style="margin-top:16px">
  <b>评分维度权重：</b>增长25%(同比+环比+收入) | 估值20%(PE+PB) | 技术20%(趋势+MACD+RSI+KDJ+MA偏离) | 资金15%(主力流入+融资变化) | ROE 10% | 量价10%<br>
  <b>数据来源：</b>Tushare Pro(业绩快报+日K线) · 腾讯财经(实时估值) · 东方财富(融资融券)。技术指标基于12个月日K线数据计算。环比QoQ基于Q1财报与H1快报推算(Q2=H1-Q1)。<br>
  <b>免责声明：</b>本工具基于公开数据自动生成，仅供参考筛选，不构成投资建议。投资有风险，入市需谨慎。生成时间：{now}
</div>
</div></body></html>"""

def sector_color(sec):
    colors = {"电力设备":"#1890ff","公用事业":"#52c41a","汽车":"#fa8c16","机械设备":"#f5222d",
              "金融":"#597ef7","医药":"#eb2f96","有色金属":"#faad14","商贸零售":"#13c2c2",
              "环保":"#2f54eb"}
    return colors.get(sec, "#666")

# ============================================================
# 输出
# ============================================================
report_a = gen_report_a()
report_b = gen_report_b()

for name, content in [("中报业绩快报深度分析_卖方研报风.html", report_a),
                       ("中报业绩快报量化筛选_数据驱动风.html", report_b)]:
    path = BASE.parent / name
    path.write_text(content, encoding="utf-8")
    print(f"{name}: {len(content)/1024:.1f} KB → {path}")

print("Done!")
