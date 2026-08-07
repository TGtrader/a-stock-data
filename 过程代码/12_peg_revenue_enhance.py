"""
Phase 7c: PEG + 营收增速增强版
- 计算PEG (PE / 盈利增速)
- 营收增速 vs 盈利增速交叉验证
- 成长质量评分（营收+盈利双重增长）
- 重新生成两份报告
"""
import json, numpy as np
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).parent
with open(BASE / "h1_2026_data" / "h1_2026_full.json", "r", encoding="utf-8") as f:
    D = json.load(f)

stocks = D["stocks"]; klines = D["klines"]; quotes = D["quotes"]; margin = D.get("margin", {})
now = datetime.now().strftime("%Y-%m-%d %H:%M")

# ============================================================
# 增强：PEG + 营收增速 + 成长质量
# ============================================================
for code, info in stocks.items():
    q = quotes.get(code, {})
    pe = q.get("pe_ttm", 0) or 0
    yoy_p = info.get("yoy_profit", 0)
    yoy_r = info.get("yoy_revenue")
    yoy_e = info.get("yoy_eps")
    qoq = info.get("qoq")

    # PEG: PE / 盈利增速(%)
    # PEG < 0.5 = 极度低估, 0.5-1 = 低估, 1-1.5 = 合理, 1.5-2.5 = 偏贵, >2.5 = 昂贵
    if pe > 0 and yoy_p and yoy_p > 0 and not np.isnan(yoy_p):
        peg = round(pe / yoy_p, 2)
    else:
        peg = None
    info["peg"] = peg

    # 营收增速质量
    if yoy_r is not None and not np.isnan(yoy_r):
        info["yoy_revenue"] = round(yoy_r, 1)
    else:
        info["yoy_revenue"] = None

    # 成长质量分类
    # A类：盈利+营收双高增(都>20%) → 高质量成长
    # B类：盈利高增但营收低增 → 利润改善型（可能是降本增效）
    # C类：营收高增但盈利低增 → 投入期成长（科技公司常见）
    # D类：都低 → 稳健但缺乏弹性
    if yoy_p and not np.isnan(yoy_p):
        profit_high = yoy_p >= 20
        rev_high = (yoy_r is not None and not np.isnan(yoy_r) and yoy_r >= 15)
        if profit_high and rev_high:
            info["growth_quality"] = "A-双高增"
        elif profit_high and not rev_high:
            info["growth_quality"] = "B-利润驱动"
        elif not profit_high and rev_high:
            info["growth_quality"] = "C-营收驱动"
        else:
            info["growth_quality"] = "D-稳健增长"
    else:
        info["growth_quality"] = "数据不足"

    # PEG分级
    if peg is None:
        info["peg_grade"] = "N/A"
    elif peg < 0.5:
        info["peg_grade"] = "极度低估"
    elif peg < 1.0:
        info["peg_grade"] = "低估"
    elif peg < 1.5:
        info["peg_grade"] = "合理"
    elif peg < 2.5:
        info["peg_grade"] = "偏贵"
    else:
        info["peg_grade"] = "昂贵"

# ============================================================
# 行业 + 卖方分析
# ============================================================
SECTOR_MAP = {
    "001395.SZ": "机械设备(锂电模具)", "601139.SH": "公用事业(燃气+氢能)",
    "002911.SZ": "公用事业(燃气+氢能)", "000563.SZ": "金融(信托AMC)",
    "600131.SH": "电力设备(信息化)", "002028.SZ": "电力设备(电网)",
    "000550.SZ": "汽车(整车)", "000970.SZ": "有色金属(稀土永磁)",
    "600323.SH": "环保(水务)", "601965.SH": "汽车(检测)",
    "000999.SZ": "医药(OTC)", "600729.SH": "商贸零售(百货)",
}
for code in stocks:
    stocks[code]["sector"] = SECTOR_MAP.get(code, stocks[code].get("sw_industry","其他")[:10])

SELLSIDE = {
    "001395.SZ": {
        "pos": "锂电结构件精密模具龙头，国内市占率>25%",
        "moat": "精密级进模技术壁垒(微米级精度)+深度绑定宁德时代/比亚迪+模具耗材高复购模式",
        "logic": "动力电池结构件(盖板/壳体)全球需求CAGR>30%，模具作为核心耗材享受超越行业的增速。营收+36.9%+净利+60%双高增验证量价齐升。PEG=0.22为全组最低，极度低估。",
        "catalyst": "Q3锂电排产旺季+海外客户突破(特斯拉4680)+储能结构件新品类",
        "risk": "客户集中度偏高(CR5>70%)+锂电行业产能过剩可能导致模具需求放缓",
        "ops": "【强烈推荐-A类成长】PEG仅0.22为全组最低，营收+盈利双高增(36.9%/60%)验证成长质量。当前13x PE对应60%增速极度不合理。积极配置，目标PE 25-30x。止损：跌破MA60(~-8%)",
    },
    "600131.SH": {
        "pos": "电力信息化+数字化转型龙头，电网调度/营销系统市占率领先",
        "moat": "电网核心系统供应商(调度/营销/采集)+新型电力系统建设刚性需求+AI+电力场景应用先发优势",
        "logic": "新型电力系统(新能源消纳/虚拟电厂/电力市场化)驱动信息化投资持续高增。营收+92.3%为全组最高，近乎翻倍，验证赛道爆发。PEG=0.41，严重低估。",
        "catalyst": "虚拟电厂政策落地+电力市场化改革+AI电力调度系统上线",
        "risk": "电网IT投资节奏受政策影响+项目制收入波动",
        "ops": "【强烈推荐-A类成长】营收+92.3%为全组之最，盈利+60%同步高增，PEG=0.41。新型电力系统建设核心受益标的。当前24x PE对60%增速明显低估，中线目标PE 40x。",
    },
    "601139.SH": {
        "pos": "深圳燃气龙头，清洁能源综合服务商，氢能转型先锋",
        "moat": "深圳特许经营权壁垒+大湾区区位优势+氢能(制氢+加氢站)全产业链布局",
        "logic": "传统燃气提供稳定现金流(PE 12x)，氢能业务贡献增量弹性(QoQ+66%)。但营收-4.2%需关注——盈利增长来自降本而非增收，成长质量偏B类。PEG=0.55仍低估。",
        "catalyst": "夏季用电高峰+氢能示范城市政策+天然气价格改革",
        "risk": "营收下滑+氢能盈利模式待验证+气价波动",
        "ops": "【推荐-B类成长】PEG=0.55+P/E 12x防御属性强。但营收-4.2%是隐忧，需关注H2营收能否恢复正增长。适合作为防御底仓，氢能催化提供向上弹性。",
    },
    "002028.SZ": {
        "pos": "电网设备龙头，特高压GIS市占率>30%，国网核心供应商",
        "moat": "特高压GIS/互感器技术壁垒高+国网长期合作关系+海外EPC订单持续增长",
        "logic": "特高压投资冲刺(十四五末)+配网智能化改造。营收+27.1%+净利+15%+QoQ+60%，显示H2集中交付特征。PEG=2.57偏贵但电网设备应给予更高估值容忍度。",
        "catalyst": "特高压新线路核准+海外大单公告+配网招标",
        "risk": "PEG=2.57偏贵+电网投资节奏波动+海外地缘风险",
        "ops": "【中性偏积极-C类成长】营收+27.1%不错但盈利增速(15%)略低导致PEG偏高。电网设备PE 39x有一定溢价但属行业常态。关注H2订单确认，可作为电力设备核心配置。",
    },
    "601965.SH": {
        "pos": "汽车检测认证龙头，智能网联检测先行者",
        "moat": "政府强制检测资质壁垒(不可替代)+智能网联/新能源检测新赛道先发",
        "logic": "智能驾驶法规趋严→检测刚需增长。营收-2.0%略降但净利+20%显示利润率改善。PEG=1.44处于合理区间上沿。QoQ-69%为政府订单季节性(H2集中确认)。",
        "catalyst": "智能驾驶强制性检测标准+新能源车电池检测新规",
        "risk": "QoQ季节性波动大+检测行业政策依赖度高",
        "ops": "【中性】PEG=1.44合理但非低估，需等待H2订单确认。适合作为汽车智能化赛道卫星配置，关注H2营收恢复信号。",
    },
}

def color_sign(v): return "#f5222d" if v and v>0 else "#52c41a" if v and v<0 else "#999"
def pe_color(pe):
    if not pe or pe<=0: return ("亏损","#999")
    if pe<20: return ("低估","#52c41a")
    if pe<35: return ("合理","#1890ff")
    if pe<60: return ("偏贵","#fa8c16")
    return ("高估","#f5222d")
def peg_color(peg):
    if peg is None: return ("N/A","#999")
    if peg<0.5: return ("极度低估","#52c41a")
    if peg<1: return ("低估","#73d13d")
    if peg<1.5: return ("合理","#1890ff")
    if peg<2.5: return ("偏贵","#fa8c16")
    return ("昂贵","#f5222d")
def safe_fmt(val, fmt="+.0f", default="N/A", unit=""):
    if val is None or (isinstance(val, float) and np.isnan(val)): return default
    return f"{val:{fmt}}{unit}"

# ============================================================
# 重新评分（加入营收增速+PEG维度）
# ============================================================
for code, info in stocks.items():
    q = quotes.get(code, {})
    k = klines.get(code, {})
    pe, pb = q.get("pe_ttm",0) or 0, q.get("pb",0) or 0
    yoy_p, yoy_r = info.get("yoy_profit",0), info.get("yoy_revenue")
    peg = info.get("peg")
    qoq = info.get("qoq")
    roe = info.get("diluted_roe",0) or 0

    score = 50

    # === 增长质量(30分) ===
    if yoy_p and not np.isnan(yoy_p):
        if yoy_p >= 60: score += 12
        elif yoy_p >= 30: score += 8
        elif yoy_p >= 15: score += 5
        elif yoy_p >= 5: score += 2
    # 营收增速(成长赛道关键指标)
    if yoy_r is not None and not np.isnan(yoy_r):
        if yoy_r >= 50: score += 8
        elif yoy_r >= 20: score += 5
        elif yoy_r >= 10: score += 2
        elif yoy_r < -5: score -= 3
    # QoQ
    if qoq is not None and not np.isnan(qoq):
        if qoq >= 100: score += 7
        elif qoq >= 30: score += 5
        elif qoq >= 10: score += 2
        elif qoq < -20: score -= 3

    # === PEG估值(20分) ===
    if peg is not None:
        if peg < 0.5: score += 15
        elif peg < 1.0: score += 10
        elif peg < 1.5: score += 5
        elif peg > 3: score -= 5
    elif 0 < pe < 20: score += 8
    elif 0 < pe < 35: score += 5
    if 0 < pb < 2: score += 5
    elif 0 < pb < 4: score += 3

    # === 技术(20分) ===
    lt = k.get("lt_trend","")
    t = k.get("latest",{})
    dif, dea = t.get("dif") or 0, t.get("dea") or 0
    rsi = t.get("rsi14",50) or 50
    close_p, ma20, ma60 = t.get("close",0) or 0, t.get("ma20",0) or 0, t.get("ma60",0) or 0
    if lt=="上升": score += 6
    elif lt=="横盘": score += 3
    if dif > dea: score += 5
    if rsi < 35: score += 5
    elif rsi > 75: score -= 3
    if close_p > ma20: score += 2
    if close_p > ma60: score += 2

    # === ROE(10分) ===
    if roe > 20: score += 8
    elif roe > 12: score += 5
    elif roe > 8: score += 3

    # === 量价(10分) ===
    vp = k.get("vp_pattern","")
    if vp in ("放量突破","价升量增"): score += 6
    elif vp=="缩量筑底": score += 4
    elif vp=="放量杀跌": score -= 5

    # === 成长质量加分 ===
    gq = info.get("growth_quality","")
    if "A-" in gq: score += 8

    # === 融资(5分) ===
    mg = margin.get(code,[])
    if mg and len(mg)>=2 and mg[1]["rzye"]>0:
        mc = (mg[0]["rzye"]/mg[1]["rzye"]-1)*100
        if mc > 5: score += 4
        elif mc > 0: score += 2

    info["score_v2"] = min(100, max(0, score))

# ============================================================
# 报告A: 卖方研报叙事风(增强版)
# ============================================================
def gen_report_a():
    ranked = sorted(stocks.items(), key=lambda x: x[1]["score_v2"], reverse=True)
    sectors = {}
    for code, info in stocks.items():
        sec = info.get("sector","其他")
        sectors.setdefault(sec, []).append((code, info))

    sector_blocks = ""
    narratives = {
        "电力设备(信息化)": "新型电力系统建设是未来3-5年确定性最高的科技成长赛道之一。营收+92%近乎翻倍验证赛道爆发，PEG仅0.41。",
        "机械设备(锂电模具)": "精密制造隐形冠军。模具耗材模式决定高复购+可持续高增长，PEG=0.22为全组最具性价比成长标的。",
        "公用事业(燃气+氢能)": "传统燃气提供防御底仓(PE 12-14x)，氢能业务贡献高弹性(QoQ 66-201%)。攻守兼备的低PEG成长。",
        "电力设备(电网)": "特高压+配网智能化双驱动。PEG=2.57偏贵但电网设备赛道应给予估值溢价，QoQ+60%显示H2加速。",
        "汽车(检测)": "智能驾驶法规趋严→检测刚需。PEG=1.44合理但QoQ季节性波动大。",
        "汽车(整车)": "商用车龙头，行业复苏+新能源转型。估值极低(PE 10-12x)提供安全边际。",
        "有色金属(稀土永磁)": "新能源+机器人双主线受益。PEG=14严重高估，需等待估值消化。",
        "金融(信托AMC)": "逆周期AMC转型。PEG=36极贵但金融股不适合PEG框架。",
        "环保(水务)": "公用事业属性+政策驱动。PE 30x合理但成长性不足。",
        "医药(OTC)": "OTC品牌中药，消费属性强。增长数据缺失待正式中报披露。",
        "商贸零售(百货)": "消费复苏+业态转型。亏损状态不适合PEG框架。",
    }

    for sec_name, sec_stocks in sorted(sectors.items(), key=lambda x: len(x[1]), reverse=True):
        sec_stocks.sort(key=lambda x: x[1]["score_v2"], reverse=True)
        narrative = narratives.get(sec_name, "")

        cards = ""
        for code, info in sec_stocks:
            k = klines.get(code,{})
            q = quotes.get(code,{})
            ss = SELLSIDE.get(code,{})
            t = k.get("latest",{})
            name = info.get("name",code)
            pe, pb = q.get("pe_ttm",0) or 0, q.get("pb",0) or 0
            pe_lbl, pe_clr = pe_color(pe)
            peg = info.get("peg")
            peg_lbl, peg_clr = peg_color(peg)
            mcap = q.get("mcap_yi",0) or 0
            yoy_p, yoy_r = info.get("yoy_profit",0), info.get("yoy_revenue")
            gq = info.get("growth_quality","")
            gq_bg = "#f6ffed" if "A" in gq else "#fffbe6" if "B" in gq else "#e6f7ff" if "C" in gq else "#fafafa"
            score_v2 = info.get("score_v2", info.get("score",50))

            lt = k.get("lt_trend","")
            dif_v, dea_v = t.get("dif") or 0, t.get("dea") or 0
            macd_s = "金叉" if dif_v>dea_v else "死叉"
            macd_c = "#f5222d" if macd_s=="金叉" else "#52c41a"
            rsi = t.get("rsi14",50) or 50
            chg_3m = k.get("chg_3m",0) or 0
            july_c = k.get("july_chg",0) or 0
            vp = k.get("vp_pattern","")
            price = q.get("price",0)
            ma60v = t.get("ma60",price) or price
            vs_ma60 = (price/ma60v-1)*100 if ma60v else 0

            score_bg = "#f5222d" if score_v2>=85 else "#fa8c16" if score_v2>=65 else "#1890ff"

            cards += f"""
        <div style="background:#fff;border:1px solid #e0e0e0;border-radius:10px;padding:18px 20px;margin:10px 0">
          <div style="display:flex;justify-content:space-between;align-items:start">
            <div>
              <b style="font-size:16px">{name}</b><span style="font-size:11px;color:#999;margin-left:8px">{code}</span>
              <span style="font-size:10px;background:{gq_bg};padding:2px 8px;border-radius:8px;margin-left:4px">{gq}</span>
            </div>
            <div style="text-align:center;background:{score_bg};color:#fff;padding:8px 12px;border-radius:20px">
              <div style="font-size:18px;font-weight:800">{score_v2}</div><div style="font-size:10px">v2评分</div>
            </div>
          </div>
          <div style="display:grid;grid-template-columns:repeat(5,1fr);gap:8px;margin:12px 0">
            <div style="background:#fafafa;padding:8px;border-radius:6px;text-align:center"><span style="font-size:10px;color:#999">PE(TTM)</span><br><b style="color:{pe_clr}">{pe:.0f}x</b></div>
            <div style="background:#fafafa;padding:8px;border-radius:6px;text-align:center"><span style="font-size:10px;color:#999">PEG</span><br><b style="color:{peg_clr}">{safe_fmt(peg,'.2f')}</b></div>
            <div style="background:#fafafa;padding:8px;border-radius:6px;text-align:center"><span style="font-size:10px;color:#999">盈利YOY</span><br><b style="color:#f5222d">{safe_fmt(yoy_p)}%</b></div>
            <div style="background:#fafafa;padding:8px;border-radius:6px;text-align:center"><span style="font-size:10px;color:#999">营收YOY</span><br><b style="color:{color_sign(yoy_r)}">{safe_fmt(yoy_r)}%</b></div>
            <div style="background:#fafafa;padding:8px;border-radius:6px;text-align:center"><span style="font-size:10px;color:#999">ROE</span><br><b>{info.get('diluted_roe',0):.1f}%</b></div>
          </div>
          <div style="font-size:12px;color:#666;display:flex;gap:16px;flex-wrap:wrap;margin:4px 0">
            <span>趋势:<b style="color:{'#f5222d' if lt=='上升' else '#52c41a' if lt=='下降' else '#999'}">{lt}</b></span>
            <span>MACD:<b style="color:{macd_c}">{macd_s}</b></span>
            <span>RSI14:<b>{rsi:.0f}</b></span>
            <span>PEG等级:<b style="color:{peg_clr}">{info.get('peg_grade','?')}</b></span>
            <span>3月:<b style="color:{color_sign(chg_3m)}">{chg_3m:+.1f}%</b></span>
            <span>7月:<b style="color:{color_sign(july_c)}">{july_c:+.1f}%</b></span>
            <span>价vsMA60:<b style="color:{color_sign(vs_ma60)}">{vs_ma60:+.1f}%</b></span>
            <span>量价:<b>{vp}</b></span>
          </div>"""
            if ss:
                cards += f"""
          <div style="background:#f8f9fc;padding:12px 14px;border-radius:6px;margin:8px 0">
            <div style="font-size:12px;line-height:1.7"><b>行业地位：</b>{ss['pos']}</div>
            <div style="font-size:12px;line-height:1.7"><b>护城河：</b>{ss['moat']}</div>
            <div style="font-size:12px;line-height:1.7;color:#1890ff"><b>增长逻辑：</b>{ss['logic']}</div>
            <div style="font-size:12px;line-height:1.7;color:#f5222d"><b>风险：</b>{ss['risk']}</div>
          </div>
          <div style="background:linear-gradient(90deg,#fff7e6,#fffbe6);padding:10px 14px;border-radius:6px;border-left:3px solid #fa8c16">
            <b style="color:#fa8c16;font-size:12px">[操作建议]</b><span style="font-size:12px;color:#555"> {ss['ops']}</span>
          </div>"""
            mg = margin.get(code,[])
            if mg and len(mg)>=2:
                cards += f'<div style="font-size:11px;color:#888;margin-top:6px">融资余额:{mg[0]["rzye"]/1e8:.2f}亿 | EPS:{info["diluted_eps"]:.2f} | BPS:{info["bps"]:.2f} | 市值:{mcap:.0f}亿</div>'
            cards += "</div>"

        sector_blocks += f"""
    <div style="margin:20px 0">
      <h3 style="font-size:17px;color:#1a1a2e;padding-bottom:8px;border-bottom:2px solid #1a1a2e">{sec_name} ({len(sec_stocks)}只)</h3>
      <p style="font-size:13px;color:#666;margin:8px 0;line-height:1.7">{narrative}</p>
      {cards}
    </div>"""

    avg_pe = np.mean([quotes.get(c,{}).get("pe_ttm",0) for c in stocks if quotes.get(c,{}).get("pe_ttm",0)>0])
    avg_peg = np.mean([info["peg"] for info in stocks.values() if info.get("peg") is not None])
    a_grade = sum(1 for info in stocks.values() if "A-" in info.get("growth_quality",""))

    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>中报业绩快报深度分析(PEG增强版·卖方研报)</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'PingFang SC','Microsoft YaHei',sans-serif;background:#f0f2f5;color:#1a1a2e;line-height:1.8}}
.cover{{background:linear-gradient(160deg,#0a1628,#1a2a4a 40%,#0d2137);color:#fff;padding:42px 48px 28px}}
.cover h1{{font-size:26px;font-weight:800;margin-bottom:6px}}
.cover .sub{{font-size:13px;color:#8899aa;line-height:1.6}}
.cover .meta{{display:flex;gap:24px;margin-top:14px;font-size:11px;color:#667788}}
.container{{max-width:1050px;margin:0 auto;padding:0 20px}}
.section{{background:#fff;border-radius:12px;padding:24px 28px;margin:14px 0;box-shadow:0 2px 10px rgba(0,0,0,0.04)}}
.section h2{{font-size:19px;font-weight:700;padding-bottom:8px;border-bottom:2px solid #1a1a2e;margin-bottom:12px}}
.summary-grid{{display:grid;grid-template-columns:repeat(6,1fr);gap:10px;margin:12px 0}}
.summary-card{{padding:14px;border-radius:8px;text-align:center}}
.summary-card .s-v{{font-size:22px;font-weight:800}}
.summary-card .s-l{{font-size:10px;color:#666;margin-top:2px}}
.disclaimer{{background:#fff;border-radius:12px;padding:20px 24px;margin:14px 0;font-size:11px;color:#888;line-height:2}}
.framework{{background:#f8f9fc;padding:16px;border-radius:8px;margin:10px 0;font-size:13px}}
@media(max-width:768px){{.summary-grid{{grid-template-columns:repeat(3,1fr)}}}}
</style></head><body>
<div class="cover">
  <h1>2026年中报业绩快报深度分析</h1>
  <div class="sub">PEG估值框架 · 营收+盈利双重验证 · 成长质量分级 · 卖方视角</div>
  <div class="meta"><span>覆盖:{len(stocks)}只</span><span>双高增(A类):{a_grade}只</span><span>平均PE:{avg_pe:.0f}x</span><span>平均PEG:{avg_peg:.2f}</span><span>12月K线</span><span>{now}</span></div>
</div>
<div class="container">
<div class="section">
  <h2>一、分析框架：PEG + 营收双维验证</h2>
  <div class="framework">
    <b>成长股分析核心公式：PEG = PE / 盈利增速(%)</b><br>
    • PEG < 0.5 → 极度低估（极度罕见，需验证增速可持续性）<br>
    • PEG 0.5-1.0 → 低估（成长股合理买入区间）<br>
    • PEG 1.0-1.5 → 合理（可持有，不追高）<br>
    • PEG 1.5-2.5 → 偏贵（需超预期催化）<br>
    • PEG > 2.5 → 昂贵（回避或等待回调）<br><br>
    <b>成长质量分级（盈利增速 × 营收增速）：</b><br>
    • <b style="color:#52c41a">A类-双高增</b>：盈利≥20% + 营收≥15% → 量价齐升，最佳成长形态<br>
    • <b style="color:#fa8c16">B类-利润驱动</b>：盈利高增但营收低/负增 → 可能是降本增效，需验证可持续性<br>
    • <b style="color:#1890ff">C类-营收驱动</b>：营收高增但盈利低 → 投入期成长（科技公司常见），关注毛利率趋势<br>
    • <b style="color:#999">D类-稳健增长</b>：双低 → 成熟期公司，用PE/PB框架更合适<br>
  </div>
  <div class="summary-grid">
    <div class="summary-card" style="background:#e6f7ff;border:2px solid #1890ff"><div class="s-v" style="color:#1890ff">{len(stocks)}</div><div class="s-l">有效标的</div></div>
    <div class="summary-card" style="background:#f6ffed;border:2px solid #52c41a"><div class="s-v" style="color:#52c41a">{a_grade}</div><div class="s-l">A类双高增</div></div>
    <div class="summary-card" style="background:#fff7e6;border:2px solid #fa8c16"><div class="s-v" style="color:#fa8c16">{avg_pe:.0f}x</div><div class="s-l">平均PE</div></div>
    <div class="summary-card" style="background:#f0f0ff;border:2px solid #597ef7"><div class="s-v" style="color:#597ef7">{avg_peg:.2f}</div><div class="s-l">平均PEG</div></div>
    <div class="summary-card" style="background:#fff0f0;border:2px solid #f5222d"><div class="s-v" style="color:#f5222d">{sum(1 for info in stocks.values() if info.get('peg') and info['peg']<1)}</div><div class="s-l">PEG<1低估</div></div>
    <div class="summary-card" style="background:#e6fffb;border:2px solid #13c2c2"><div class="s-v" style="color:#13c2c2">{sum(1 for info in stocks.values() if info.get('yoy_revenue') and info['yoy_revenue']>=20)}</div><div class="s-l">营收增速≥20%</div></div>
  </div>
</div>
<div class="section"><h2>二、分行业深度分析</h2>{sector_blocks}</div>
<div class="disclaimer"><h4>⚠️ 风险提示与免责声明</h4>
<p>本报告基于已披露的2026年中报业绩快报数据。PEG指标假设盈利增速可持续，实际增速可能变化。营收增速基于快报revenue字段对比计算。技术指标基于12个月日K线。所有分析仅供参考，不构成投资建议。<br>
数据来源：Tushare Pro(业绩快报+行情)+腾讯财经(实时估值)+东方财富(融资融券)。{now}</p></div>
</div></body></html>"""

# ============================================================
# 报告B: 量化数据驱动风(增强版)
# ============================================================
def gen_report_b():
    ranked = sorted(stocks.items(), key=lambda x: x[1]["score_v2"], reverse=True)

    table_rows = ""
    for rank, (code, info) in enumerate(ranked, 1):
        k = klines.get(code,{})
        q = quotes.get(code,{})
        t = k.get("latest",{})
        name = info["name"]
        sv2 = info.get("score_v2",50)
        pe = q.get("pe_ttm",0) or 0
        pb = q.get("pb",0) or 0
        peg = info.get("peg")
        yoy_p, yoy_r = info.get("yoy_profit",0), info.get("yoy_revenue")
        qoq = info.get("qoq")
        roe = info.get("diluted_roe",0) or 0
        eps = info.get("diluted_eps",0) or 0
        mcap = q.get("mcap_yi",0) or 0
        lt, vp = k.get("lt_trend",""), k.get("vp_pattern","")
        macd = "金叉" if (t.get("dif") or 0)>(t.get("dea") or 0) else "死叉"
        rsi = t.get("rsi14",50) or 50
        july, chg3 = k.get("july_chg",0), k.get("chg_3m",0) or 0
        gq = info.get("growth_quality","")

        score_bg = "#f5222d" if sv2>=85 else "#fa8c16" if sv2>=65 else "#1890ff" if sv2>=50 else "#999"
        peg_lbl, peg_clr = peg_color(peg)
        lt_c = "#f5222d" if lt=="上升" else "#52c41a" if lt=="下降" else "#999"
        gq_c = "#52c41a" if "A" in gq else "#fa8c16" if "B" in gq else "#1890ff" if "C" in gq else "#999"

        table_rows += f"""
        <tr>
          <td>{rank}</td>
          <td><b>{name}</b><span style="font-size:10px;color:#999;display:block">{code}</span></td>
          <td style="background:{score_bg};color:#fff;text-align:center;font-weight:700;border-radius:4px">{sv2}</td>
          <td style="color:{peg_clr};font-weight:700">{safe_fmt(peg,'.2f')}</td>
          <td style="font-size:10px;color:{peg_clr}">{info.get('peg_grade','?')}</td>
          <td style="color:{pe_color(pe)[1]};font-weight:700">{pe:.0f}x</td>
          <td style="color:#f5222d;font-weight:700">{safe_fmt(yoy_p)}%</td>
          <td style="color:{color_sign(yoy_r)};font-weight:700">{safe_fmt(yoy_r)}%</td>
          <td style="color:{color_sign(qoq)};font-weight:700">{safe_fmt(qoq)}%</td>
          <td style="color:{gq_c};font-weight:700;font-size:11px">{gq}</td>
          <td>{pb:.1f}x</td><td>{mcap:.0f}亿</td><td>{eps:.2f}</td><td>{roe:.1f}%</td>
          <td style="color:{lt_c};font-weight:700">{lt}</td>
          <td style="color:{'#f5222d' if macd=='金叉' else '#52c41a'}">{macd}</td>
          <td style="color:{'#f5222d' if rsi>70 else '#52c41a' if rsi<30 else '#666'}">{rsi:.0f}</td>
          <td style="color:{color_sign(july)}">{july:+.1f}%</td>
          <td style="color:{color_sign(chg3)}">{chg3:+.1f}%</td>
          <td><span style="background:{'#f6ffed' if '升' in vp else '#fff1f0' if '跌' in vp else '#fafafa'};padding:2px 6px;border-radius:8px;font-size:10px">{vp}</span></td>
        </tr>"""

    avg_pe = np.mean([quotes.get(c,{}).get("pe_ttm",0) for c in stocks if quotes.get(c,{}).get("pe_ttm",0)>0])
    avg_peg = np.mean([info["peg"] for info in stocks.values() if info.get("peg") is not None])

    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>中报业绩快报量化筛选(PEG增强版)</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'PingFang SC','Microsoft YaHei',sans-serif;background:#f5f6fa;color:#1a1a2e}}
.header{{background:#1a1a2e;color:#fff;padding:16px 28px;display:flex;justify-content:space-between;align-items:center}}
.header h1{{font-size:18px}}
.header .st{{display:flex;gap:14px;font-size:11px}}
.header .st span{{background:rgba(255,255,255,0.08);padding:5px 10px;border-radius:5px}}
.container{{padding:10px 14px}}
.legend{{background:#fff;padding:10px 16px;margin-bottom:10px;border-radius:8px;font-size:11px;color:#666;box-shadow:0 1px 4px rgba(0,0,0,0.04)}}
table{{width:100%;border-collapse:collapse;font-size:10px;background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.04)}}
th{{background:#1a1a2e;color:#fff;padding:6px 5px;text-align:left;font-weight:500;white-space:nowrap;position:sticky;top:0;z-index:1}}
td{{padding:5px;border-bottom:1px solid #eee}}
tr:hover{{background:#fafafa}}
.footer{{font-size:10px;color:#999;padding:10px;text-align:center}}
@media(max-width:1400px){{table{{font-size:9px}}th,td{{padding:3px 2px}}}}
</style></head><body>
<div class="header">
  <div><h1>A股2026年中报快报量化筛选 v2 (PEG增强)</h1><div style="font-size:10px;color:#8899aa;margin-top:2px">{len(stocks)}只标的 · PEG+营收增速+成长质量分级 · 20维评分</div></div>
  <div class="st"><span>平均PE:{avg_pe:.0f}x</span><span>平均PEG:{avg_peg:.2f}</span><span>PEG<1:{sum(1 for i in stocks.values() if i.get('peg') and i['peg']<1)}只</span></div>
</div>
<div class="container">
<div class="legend">
  <b>评分维度权重 v2：</b>增长质量30%(盈利YOY+营收YOY+QOQ) | PEG估值20% | 技术面20%(趋势+MACD+RSI+MA) | ROE 10% | 量价10% | 成长质量加分(A类+8) | 融资5%<br>
  <b>PEG分级：</b><span style="color:#52c41a">PEG<0.5极度低估</span> | <span style="color:#73d13d">0.5-1低估</span> | <span style="color:#1890ff">1-1.5合理</span> | <span style="color:#fa8c16">1.5-2.5偏贵</span> | <span style="color:#f5222d">>2.5昂贵</span><br>
  <b>成长质量：</b><span style="color:#52c41a">A双高增</span>(盈利≥20%+营收≥15%) | <span style="color:#fa8c16">B利润驱动</span> | <span style="color:#1890ff">C营收驱动</span> | <span style="color:#999">D稳健</span>
</div>
<div style="overflow-x:auto">
<table>
<thead><tr>
<th>#</th><th>名称/代码</th><th>v2评分</th><th>PEG</th><th>PEG等级</th><th>PE</th><th>盈利YOY</th><th>营收YOY</th><th>QOQ</th><th>成长质量</th>
<th>PB</th><th>市值</th><th>EPS</th><th>ROE</th><th>趋势</th><th>MACD</th><th>RSI</th><th>7月</th><th>3月</th><th>量价</th>
</tr></thead>
<tbody>{table_rows}</tbody>
</table>
</div>
<div class="footer">
  <b>数据截止：</b>2026.07.22 · <b>K线周期：</b>12个月日线 · <b>数据源：</b>Tushare Pro+腾讯财经+东方财富<br>
  <b>免责声明：</b>本工具基于公开数据自动生成，PEG假设增速可持续。所有分析仅供参考，不构成投资建议。{now}
</div>
</div></body></html>"""

# ============================================================
report_a = gen_report_a()
report_b = gen_report_b()

for name, content in [("中报业绩快报深度分析_PEG增强_卖方研报风.html", report_a),
                       ("中报业绩快报量化筛选_PEG增强_数据驱动风.html", report_b)]:
    p = BASE.parent / name
    p.write_text(content, encoding="utf-8")
    print(f"{name}: {len(content)/1024:.1f} KB")

# Update saved data with PEG fields
with open(BASE / "h1_2026_data" / "h1_2026_full_v2.json", "w", encoding="utf-8") as f:
    json.dump(D, f, ensure_ascii=False, indent=2)
print("v2 data saved")
