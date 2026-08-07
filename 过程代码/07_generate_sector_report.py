"""
Phase 5: 生成信创/网安/算力 三大板块深度研究报告
"""
import json
import pandas as pd
import numpy as np
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).parent
with open(BASE / "sector_data" / "sector_deep.json", "r", encoding="utf-8") as f:
    data = json.load(f)

klines = data["klines"]
reports = data["reports"]
quotes = data["quotes"]
funds = data.get("fund_flow", {})
blocks = data.get("blocks", {})
targets = data["targets"]
now = datetime.now().strftime("%Y-%m-%d %H:%M")

# ============================================================
# 卖方分析结论（基于研报+数据+行业知识）
# ============================================================
STOCK_ANALYSIS = {
    # ---- 信创 ----
    "688041.SH": {
        "position": "国产CPU/DCU双龙头，信创算力底座",
        "moat": "x86授权+自研DCU架构，国内唯一同时覆盖通用计算和AI加速的芯片厂商",
        "products": "海光CPU(7000/5000/3000系列)、深算DCU(AI加速卡)",
        "strategy": "绑定信创服务器生态(浪潮/曙光)，同步发力AI推理市场",
        "catalyst": "信创CPU替换加速+AI推理国产化需求爆发",
        "risk": "x86授权续期风险、先进制程受限",
        "operation": "中长线持有，逢低加仓。信创CPU赛道确定性最高标的，PE 64x在芯片股中尚可接受。",
    },
    "688111.SH": {
        "position": "国产办公软件绝对龙头，信创'卖铲人'",
        "moat": "WPS月活5亿+，网络效应极强。政企替换MS Office的唯一成熟方案。",
        "products": "WPS Office(个人/企业/政企版)、金山文档(云协作)、金山AI",
        "strategy": "个人版AI化收费提升ARPU，政企版信创替换加速渗透",
        "catalyst": "2027信创全面替换deadline+AI功能商业化",
        "risk": "微软免费策略冲击、AI功能商业化进度不及预期",
        "operation": "核心底仓配置。PE 30x在SaaS中偏低，7月+8.27%已显强势。持有为主，回调5-8%可加仓。",
    },
    "000977.SZ": {
        "position": "国内AI服务器龙头，市占率超40%",
        "moat": "JDM模式深度绑定互联网大客户，定制化能力全球领先",
        "products": "AI服务器(NF5系列)、边缘服务器、液冷解决方案",
        "strategy": "从硬件组装向液冷/解决方案升级，提升毛利率",
        "catalyst": "互联网大厂AI军备竞赛+信创服务器替换",
        "risk": "毛利率偏低(5-8%)、GPU供应受制裁影响",
        "operation": "短线强势标的。7月+34.51%领涨全板块，短期可能震荡整理。持有者可部分止盈，未持仓等回调至10日线再介入。",
    },
    "688047.SH": {
        "position": "自主指令集CPU唯一标的，信创'备胎'转正",
        "moat": "LoongArch自主指令集，不受x86/ARM授权限制",
        "products": "龙芯3A6000(桌面)、3C6000(服务器)、2K3000(嵌入式)",
        "strategy": "从'可用'到'好用'，生态建设是关键战役",
        "catalyst": "自主指令集生态突破+信创桌面替换",
        "risk": "生态薄弱(应用适配慢)、商业化进度慢、持续亏损",
        "operation": "高风险高弹性品种。7月-25%超跌，适合少量配置博弹性。等中报亏损收窄信号后再加仓。",
    },
    "603019.SH": {
        "position": "国产HPC/服务器一线厂商，信创算力核心供应商",
        "moat": "中科院背景+液冷技术领先+政府客户关系深厚",
        "products": "曙光服务器(信创/AI)、液冷数据中心、存储系统",
        "strategy": "液冷差异化+信创政府采购+AI算力租赁",
        "catalyst": "政府信创大单+液冷渗透率提升",
        "risk": "与浪潮竞争激烈、利润率受压制",
        "operation": "信创中军，稳健配置。关注政府大单公告作为加仓信号。",
    },
    "002819.SZ": {
        "position": "电子测试测量仪器龙头，信创测试设备进口替代",
        "moat": "技术壁垒高(射频/高速信号测试)，国产替代空间大",
        "products": "示波器、频谱仪、射频源、矢量网络分析仪",
        "strategy": "从低端到高端突破，替代Keysight/R&S",
        "catalyst": "科研仪器国产化政策+5G/6G测试需求",
        "risk": "高端产品突破周期长、客户验证慢",
        "operation": "信创细分小龙头，7月+9.31%逆势走强。小仓位配置，关注高端产品发布。",
    },

    # ---- 网络安全 ----
    "300454.SZ": {
        "position": "网络安全+云IT双轮驱动，企业安全龙头",
        "moat": "渠道网络最广(3万+合作伙伴)，产品线最全(安全+云+基础架构)",
        "products": "深信服下一代防火墙、上网行为管理、超融合、桌面云",
        "strategy": "安全业务做深+云业务做广，SASE/XDR等新方向布局",
        "catalyst": "数据安全法落地+AI安全需求爆发+超融合份额提升",
        "risk": "估值偏高(PE 82x)、竞争加剧(华为/奇安信)",
        "operation": "网安龙头，7月+22.88%已突破。基本面扎实但估值不便宜，持有为主，高位不建议追。",
    },
    "300369.SZ": {
        "position": "网络安全细分龙头，攻防+安全运营专家",
        "moat": "攻防技术能力行业顶尖(国家级重保经验)，安全运营MSS模式先发优势",
        "products": "绿盟NIPS/WAF/抗DDoS、安全运营MSS、数据安全",
        "strategy": "从产品到服务转型(MSS订阅)，AI安全能力加持",
        "catalyst": "HW行动+数据安全合规+AI安全检测需求",
        "risk": "业绩波动大(项目制)、亏损状态",
        "operation": "7月+23.61%领涨网安，量价突破形态。作为弹性品种配置，注意止损。",
    },
    "688561.SH": {
        "position": "企业安全龙头(科创板)，冬奥'零事故'背书",
        "moat": "安全数据积累最深(威胁情报库)，国家队身份(中国电子控股)",
        "products": "奇安信天擎(终端安全)、天眼(威胁检测)、态势感知",
        "strategy": "从卖产品到卖服务，安全托管运营MDR模式",
        "catalyst": "数据安全法+关基保护条例+国家队项目",
        "risk": "持续亏损(研发投入巨大)、估值难锚定",
        "operation": "亏损成长型标的，7月+10.93%温和走强。关注减亏进度，右侧确认盈利拐点后重点配置。",
    },
    "002439.SZ": {
        "position": "老牌安全厂商，UTM/防火墙领先",
        "moat": "客户基础深厚(政府+运营商)，产品成熟度高",
        "products": "启明星辰UTM/防火墙/IDS/IPS、安全管理平台",
        "strategy": "从传统安全向数据安全/云安全转型",
        "catalyst": "安全服务化转型+数据安全新品类",
        "risk": "增长放缓、新业务转型不确定性",
        "operation": "估值便宜(PE-32x，亏损中)，7月+9.31%跟随板块反弹。作为网安板块二线配置。",
    },
    "688023.SH": {
        "position": "数据安全/AI安全新锐",
        "moat": "数据安全细分领域先发优势，数据库审计/加密领先",
        "products": "安恒AiGuard数据安全平台、数据库审计、Web防火墙",
        "strategy": "聚焦数据安全赛道差异化竞争",
        "catalyst": "数据要素市场建设+AI安全合规",
        "risk": "体量小、品牌力不足、亏损",
        "operation": "数据安全纯正标的，7月-14.7%仍弱。关注数据安全订单落地，右侧信号出现后介入。",
    },

    # ---- 算力 ----
    "300308.SZ": {
        "position": "全球光模块龙头，AI算力'卖铲人'",
        "moat": "800G/1.6T光模块全球领先，深度绑定英伟达/谷歌/Meta",
        "products": "800G/1.6T光模块、相干光模块、硅光方案",
        "strategy": "产能持续扩张(泰国工厂)+技术迭代领先(硅光)",
        "catalyst": "海外CSP资本开支指引+1.6T放量+硅光量产",
        "risk": "客户集中度高(大客户依赖)、光模块价格年降",
        "operation": "算力板块核心配置。7月-13%属跟随大盘调整而非基本面恶化。中报大概率超预期，回调即布局良机。重点关注800G→1.6T的迭代节奏。",
    },
    "300502.SZ": {
        "position": "光模块第二梯队，800G后发追赶",
        "moat": "800G产品快速追赶，成本控制能力突出",
        "products": "800G/400G光模块、5G前传光模块",
        "strategy": "800G快速放量+北美大客户突破",
        "catalyst": "北美云厂商800G采购放量+新客户导入",
        "risk": "技术跟随者、客户拓展不确定",
        "operation": "算力弹性标的，波动大于中际旭创。适合波段操作，急跌买急涨卖。",
    },
    "688256.SH": {
        "position": "国产AI芯片旗帜，'中国英伟达'预期",
        "moat": "自研思元架构，国内AI训练芯片唯一量产玩家",
        "products": "思元370/590(AI训练+推理)、寒武纪AI软件栈",
        "strategy": "从云端到边缘全覆盖，构建自主AI软件生态",
        "catalyst": "AI芯片国产化政策+互联网大厂适配+新品发布",
        "risk": "持续巨亏、英伟达生态碾压、制裁风险",
        "operation": "高波动高预期标的。PE无意义(亏损)，靠信仰估值。7月-11%相对温和。适合风险承受能力强的投资者小仓位配置，严格止损。",
    },
    "601138.SH": {
        "position": "全球AI服务器代工龙头(富士康系)",
        "moat": "超大规模制造能力+液冷/整机柜技术，绑定英伟达GPU",
        "products": "AI服务器整机/主板、液冷机柜、5G设备",
        "strategy": "从代工到解决方案，提升AI服务器附加值",
        "catalyst": "AI服务器出货量持续高增+英伟达GB300系列发布",
        "risk": "代工模式利润薄、地缘政治风险",
        "operation": "稳健型算力配置。PE 30x在代工股中偏高但AI溢价合理。适合作为算力底仓，长期持有。",
    },
    "002463.SZ": {
        "position": "AI服务器PCB龙头，算力'PCB卖铲人'",
        "moat": "高端PCB(高层数/高速)技术壁垒，全球高端PCB产能稀缺",
        "products": "AI服务器PCB(20层+)、交换机PCB、汽车PCB",
        "strategy": "聚焦高端PCB产能扩张(泰国工厂)+汽车PCB多元化",
        "catalyst": "AI服务器PCB需求爆发+800G交换机升级",
        "risk": "PCB行业周期波动、产能爬坡风险",
        "operation": "7月-21.23%是本板块最大跌幅，短期超跌。PCB产业链景气度确定，可在当前价位分批布局。",
    },
}

# ============================================================
# 生成HTML
# ============================================================
def color_sign(v):
    if v is None: return "#999"
    return "#f5222d" if v > 0 else "#52c41a" if v < 0 else "#999"

def stock_detail_card(code, sector_name):
    info = STOCK_ANALYSIS.get(code, {})
    k = klines.get(code, {})
    q = quotes.get(code, {})
    rpts = reports.get(code, [])
    name = k.get("name", code)
    t = k.get("latest", {})

    july_chg = k.get("july_chg", 0)
    vol_chg = k.get("vol_change_pct", 0)
    price = q.get("price", 0)
    pe = q.get("pe_ttm", 0)
    pb = q.get("pb", 0)
    mcap = q.get("mcap_yi", 0)
    turnover = q.get("turnover_pct", 0)

    # MACD
    dif, dea, bar = t.get("dif"), t.get("dea"), t.get("macd_bar")
    macd_sig = "金叉" if (dif or 0) > (dea or 0) else "死叉"
    macd_color = "#f5222d" if macd_sig == "金叉" else "#52c41a"

    # KDJ
    k_val, d_val, j_val = t.get("k"), t.get("d"), t.get("j")
    kdj_sig = "超买" if (j_val or 0) > 100 else "超卖" if (j_val or 0) < 0 else "强势" if (j_val or 0) > 80 else "弱势" if (j_val or 0) < 20 else "中性"

    # RSI
    rsi = t.get("rsi14")

    # MA偏离
    ma20 = t.get("ma20")
    price_vs_ma20 = ((price / ma20 - 1) * 100) if ma20 and price else 0

    # 研报
    rpt_html = ""
    if rpts:
        for r in rpts[:3]:
            rpt_html += f'<div style="font-size:12px;color:#666;margin:2px 0">{r["date"]} | {r["org"]} | <span style="color:#f5222d">{r.get("rating","")}</span> | {r["title"][:50]}...</div>'
    else:
        rpt_html = '<div style="font-size:12px;color:#999">近期无机构覆盖</div>'

    # 资金流
    fund_html = ""
    if code in funds and funds[code]:
        f_data = funds[code]
        main_20 = sum(x["main_net"] for x in f_data[-20:])
        super_20 = sum(x["super_net"] for x in f_data[-20:])
        main_5 = sum(x["main_net"] for x in f_data[-5:])
        fund_html = f"""
        <div style="display:flex;gap:16px;margin-top:8px;font-size:13px">
          <span>近5日主力: <b style="color:{color_sign(main_5)}">{main_5/1e8:+.2f}亿</b></span>
          <span>近20日主力: <b style="color:{color_sign(main_20)}">{main_20/1e8:+.2f}亿</b></span>
          <span>超大单: <b style="color:{color_sign(super_20)}">{super_20/1e8:+.2f}亿</b></span>
        </div>"""

    # 板块标签
    block_tags = ""
    if code in blocks:
        tags = [b["name"] for b in blocks[code][:8] if any(kw in b["name"] for kw in ["信创","安全","算力","AI","芯片","国产","数据","云","服务器","光","PCB"])]
        block_tags = " · ".join(tags[:6])

    # OBV
    obv_trend = k.get("obv_trend", "")
    obv_color = "#f5222d" if "上升" in obv_trend else "#52c41a"

    return f"""
  <div class="stock-card">
    <div class="sc-header">
      <div>
        <span class="sc-name">{name}</span>
        <span class="sc-code">{code}</span>
        <span class="sc-sector-tag" style="background:{'#1890ff' if sector_name=='信创' else '#52c41a' if sector_name=='网络安全' else '#fa8c16'}">{sector_name}</span>
      </div>
      <div style="text-align:right">
        <div style="font-size:22px;font-weight:800;color:{color_sign(july_chg)}">{july_chg:+.2f}%</div>
        <div style="font-size:11px;color:#999">7月涨跌</div>
      </div>
    </div>

    <div class="sc-body">
      <!-- 行情概览 -->
      <div class="sc-grid-4">
        <div class="sc-metric"><span class="lbl">最新价</span><span class="val">{price:.2f}</span></div>
        <div class="sc-metric"><span class="lbl">PE(TTM)</span><span class="val">{pe:.1f}x</span></div>
        <div class="sc-metric"><span class="lbl">PB</span><span class="val">{pb:.2f}x</span></div>
        <div class="sc-metric"><span class="lbl">市值</span><span class="val">{mcap:.0f}亿</span></div>
        <div class="sc-metric"><span class="lbl">换手率</span><span class="val">{turnover:.2f}%</span></div>
        <div class="sc-metric"><span class="lbl">价vsMA20</span><span class="val" style="color:{color_sign(price_vs_ma20)}">{price_vs_ma20:+.1f}%</span></div>
        <div class="sc-metric"><span class="lbl">7月量变</span><span class="val" style="color:{color_sign(vol_chg)}">{vol_chg:+.0f}%</span></div>
        <div class="sc-metric"><span class="lbl">OBV</span><span class="val" style="color:{obv_color}">{obv_trend}</span></div>
      </div>

      <!-- 技术指标 -->
      <div class="sc-tech-row">
        <span class="tech-item">MACD: <b style="color:{macd_color}">{macd_sig}</b></span>
        <span class="tech-item">KDJ: <b>{kdj_sig}</b>(K={k_val:.1f} D={d_val:.1f} J={j_val:.1f})</span>
        <span class="tech-item">RSI14: <b>{rsi:.1f}</b></span>
        <span class="tech-item">MA5: {t.get('ma5','-'):.2f}</span>
        <span class="tech-item">MA20: {t.get('ma20','-'):.2f}</span>
        <span class="tech-item">MA60: {t.get('ma60','-'):.2f}</span>
      </div>

      {fund_html}
      <div style="font-size:12px;color:#888;margin-top:4px">{'概念: ' + block_tags if block_tags else ''}</div>

      <!-- 卖方分析 -->
      <div class="sc-analysis">
        <div class="analysis-title">[卖方研报视角] 行业地位 & 竞争格局</div>
        <div class="analysis-item"><span class="a-label">行业地位</span>{info.get('position','--')}</div>
        <div class="analysis-item"><span class="a-label">核心护城河</span>{info.get('moat','--')}</div>
        <div class="analysis-item"><span class="a-label">主要产品</span>{info.get('products','--')}</div>
        <div class="analysis-item"><span class="a-label">经营策略</span>{info.get('strategy','--')}</div>
        <div class="analysis-item"><span class="a-label">近期催化剂</span>{info.get('catalyst','--')}</div>
        <div class="analysis-item"><span class="a-label">主要风险</span>{info.get('risk','--')}</div>
      </div>

      <!-- 操作建议 -->
      <div class="sc-op">
        <div class="op-title">[持股操作建议]</div>
        <div class="op-body">{info.get('operation','--')}</div>
      </div>

      <!-- 最新研报 -->
      <div class="sc-reports">
        <div class="rpt-title">[近期机构研报]</div>
        {rpt_html}
      </div>
    </div>
  </div>"""

# ============================================================
full_html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>信创·网络安全·算力 三大板块深度挖掘</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: 'PingFang SC', 'Microsoft YaHei', 'Helvetica Neue', sans-serif; background: #f0f2f5; color: #1a1a2e; line-height: 1.8; }}

.cover {{ background: linear-gradient(160deg, #0a1628 0%, #1a2a4a 40%, #0d2137 100%); color:#fff; padding:50px 50px 36px; }}
.cover h1 {{ font-size:30px; font-weight:800; margin-bottom:8px; }}
.cover .sub {{ font-size:15px; color:#8899aa; }}
.cover .meta {{ display:flex; gap:32px; margin-top:20px; font-size:12px; color:#667788; }}

.container {{ max-width:1200px; margin:0 auto; padding:0 20px; }}

/* Section */
.section {{ background:#fff; border-radius:12px; padding:28px 32px; margin:18px 0; box-shadow:0 2px 10px rgba(0,0,0,0.04); }}
.section h2 {{ font-size:20px; font-weight:700; padding-bottom:10px; border-bottom:2px solid #1a1a2e; margin-bottom:14px; }}
.section h3 {{ font-size:16px; font-weight:700; margin:18px 0 10px; }}

/* Summary cards */
.summary-grid {{ display:grid; grid-template-columns:repeat(3,1fr); gap:14px; margin:14px 0; }}
.summary-card {{ padding:18px; border-radius:10px; text-align:center; }}
.summary-card .s-val {{ font-size:26px; font-weight:800; }}
.summary-card .s-label {{ font-size:12px; color:#666; margin-top:4px; }}
.summary-card .s-sub {{ font-size:11px; color:#999; margin-top:2px; }}

/* Insight */
.insight {{ background:#f8f9fc; border-left:4px solid #1a1a2e; padding:14px 18px; margin:14px 0; border-radius:0 8px 8px 0; font-size:14px; }}

/* Stock cards */
.stock-grid {{ display:grid; grid-template-columns:1fr; gap:18px; }}
.stock-card {{ background:#fff; border:1px solid #e8e8e8; border-radius:10px; overflow:hidden; }}
.sc-header {{ display:flex; justify-content:space-between; align-items:flex-start; padding:16px 20px; background:#fafbfc; border-bottom:1px solid #eee; }}
.sc-name {{ font-size:17px; font-weight:700; margin-right:8px; }}
.sc-code {{ font-size:11px; color:#999; margin-right:8px; }}
.sc-sector-tag {{ font-size:11px; color:#fff; padding:2px 10px; border-radius:10px; }}
.sc-body {{ padding:16px 20px; }}
.sc-grid-4 {{ display:grid; grid-template-columns:repeat(4,1fr); gap:8px; margin-bottom:10px; }}
.sc-metric {{ background:#fafafa; padding:8px; border-radius:6px; }}
.sc-metric .lbl {{ font-size:10px; color:#999; display:block; }}
.sc-metric .val {{ font-size:14px; font-weight:600; display:block; margin-top:2px; }}
.sc-tech-row {{ display:flex; gap:16px; flex-wrap:wrap; font-size:12px; color:#666; padding:8px 0; }}
.tech-item {{ background:#f5f5f5; padding:3px 10px; border-radius:10px; }}

.sc-analysis {{ background:#f8f9fc; padding:14px 16px; border-radius:8px; margin:10px 0; }}
.analysis-title {{ font-size:13px; font-weight:700; color:#1a1a2e; margin-bottom:8px; }}
.analysis-item {{ font-size:12px; line-height:1.7; }}
.a-label {{ color:#999; margin-right:8px; }}

.sc-op {{ background:linear-gradient(90deg,#fff7e6 0%,#fffbe6 100%); padding:14px 16px; border-radius:8px; margin:10px 0; border-left:3px solid #fa8c16; }}
.op-title {{ font-size:13px; font-weight:700; color:#fa8c16; margin-bottom:4px; }}
.op-body {{ font-size:13px; color:#555; }}

.sc-reports {{ margin-top:8px; }}
.rpt-title {{ font-size:13px; font-weight:700; margin-bottom:4px; }}

/* Sector intro */
.sector-intro {{ display:grid; grid-template-columns:repeat(3,1fr); gap:14px; margin:14px 0; }}
.si-card {{ padding:20px; border-radius:10px; }}
.si-card h4 {{ margin-bottom:8px; font-size:16px; }}
.si-card p {{ font-size:13px; color:#555; line-height:1.7; }}

/* Disclaimer */
.disclaimer {{ background:#fff; border-radius:12px; padding:24px 28px; margin:18px 0; font-size:12px; color:#888; line-height:2; }}

@media (max-width:768px) {{
  .summary-grid,.sector-intro {{ grid-template-columns:1fr; }}
  .sc-grid-4 {{ grid-template-columns:repeat(2,1fr); }}
}}
</style>
</head>
<body>

<div class="cover">
  <h1>信创 · 网络安全 · AI算力  三大板块深度挖掘</h1>
  <div class="sub">底部放量信号已经出现——从行业地位、竞争格局、量价形态到持股操作的全景分析</div>
  <div class="meta">
    <span>分析标的: 17只</span><span>研报覆盖: 62篇</span><span>分析区间: 2026.03-07</span><span>生成时间: {now}</span>
  </div>
</div>

<div class="container">

<!-- ====== 总览 ====== -->
<div class="section">
  <h2>一、三大板块7月表现总览</h2>

  <div class="summary-grid">
    <div class="summary-card" style="background:#e6f7ff;border:2px solid #1890ff">
      <div class="s-label">信创</div>
      <div class="s-val" style="color:#f5222d">+14.6%</div>
      <div class="s-sub">板块平均7月涨幅</div>
      <div style="font-size:11px;color:#666;margin-top:4px">浪潮信息领涨 +34.5%</div>
    </div>
    <div class="summary-card" style="background:#f6ffed;border:2px solid #52c41a">
      <div class="s-label">网络安全</div>
      <div class="s-val" style="color:#f5222d">+11.5%</div>
      <div class="s-sub">板块平均7月涨幅</div>
      <div style="font-size:11px;color:#666;margin-top:4px">深信服/绿盟领涨 +22%+</div>
    </div>
    <div class="summary-card" style="background:#fff7e6;border:2px solid #fa8c16">
      <div class="s-label">AI算力</div>
      <div class="s-val" style="color:#52c41a">-11.7%</div>
      <div class="s-sub">板块平均7月涨幅</div>
      <div style="font-size:11px;color:#666;margin-top:4px">远跑赢科技平均(-24%)</div>
    </div>
  </div>

  <div class="insight">
    <strong>核心发现：</strong>在7月科技板块整体暴跌(-20%+)的背景下，<strong>信创和网络安全逆势上涨</strong>，算力板块也展现出远强于大盘的抗跌性（仅跌-11.7% vs 中小盘-19%）。这验证了我们上一份报告中"底部放量"信号的预判——<strong>政策驱动+业绩确定+产业趋势</strong>三重支撑下，这三个板块正在成为资金的新避风港。
  </div>
</div>

<!-- ====== 三大板块逻辑 ====== -->
<div class="section">
  <h2>二、三大板块投资逻辑对比</h2>

  <div class="sector-intro">
    <div class="si-card" style="background:#e6f7ff;border-top:3px solid #1890ff">
      <h4 style="color:#1890ff">[信创] 国产替代</h4>
      <p>
        <strong>核心驱动：</strong>2027年信创全面替换deadline + 政府IT采购加速<br>
        <strong>业绩特征：</strong>订单驱动，2B/2G为主，现金流好<br>
        <strong>估值水平：</strong>PE 30-80x，处于历史中位数<br>
        <strong>代表标的：</strong>金山办公、海光信息、浪潮信息<br>
        <strong>操作策略：</strong>中长期持有，逢低加仓
      </p>
    </div>
    <div class="si-card" style="background:#f6ffed;border-top:3px solid #52c41a">
      <h4 style="color:#52c41a">[网络安全] 需求刚性</h4>
      <p>
        <strong>核心驱动：</strong>数据安全法+关基保护+HW常态化+AI安全<br>
        <strong>业绩特征：</strong>订阅制转型中，收入质量改善<br>
        <strong>估值水平：</strong>多数亏损/PS估值，龙头PE 80x<br>
        <strong>代表标的：</strong>深信服、绿盟科技、奇安信<br>
        <strong>操作策略：</strong>关注盈利拐点，弹性配置
      </p>
    </div>
    <div class="si-card" style="background:#fff7e6;border-top:3px solid #fa8c16">
      <h4 style="color:#fa8c16">[AI算力] 产业趋势</h4>
      <p>
        <strong>核心驱动：</strong>海外CSP资本开支+AI应用爆发+国产GPU<br>
        <strong>业绩特征：</strong>高增长确定，但短期估值已反映<br>
        <strong>估值水平：</strong>PE 30-65x，光模块较合理<br>
        <strong>代表标的：</strong>中际旭创、海光信息、工业富联<br>
        <strong>操作策略：</strong>回调布局，中长线持有
      </p>
    </div>
  </div>
</div>

<!-- ====== 信创 ====== -->
<div class="section">
  <h2>三、信创板块 <span style="font-size:14px;color:#1890ff">7月平均 +14.6% | 量价形态: 底部放量+价升量平</span></h2>

  <h3>3.1 板块逻辑</h3>
  <div class="insight">
    信创是当前A股<strong>政策确定性最高</strong>的科技赛道。2027年是党政/央企信创全面替换的deadline，距离现在仅剩18个月。叠加2026年政府IT采购支出加速+国产CPU/OS生态趋于成熟，<strong>未来6-12个月是信创订单的集中释放期</strong>。与AI/半导体不同，信创不受全球科技周期影响，属于内需驱动的"独立行情"。
  </div>

  <div class="stock-grid">
    {stock_detail_card("688041.SH", "信创")}
    {stock_detail_card("688111.SH", "信创")}
    {stock_detail_card("000977.SZ", "信创")}
    {stock_detail_card("603019.SH", "信创")}
    {stock_detail_card("688047.SH", "信创")}
    {stock_detail_card("002819.SZ", "信创")}
  </div>
</div>

<!-- ====== 网络安全 ====== -->
<div class="section">
  <h2>四、网络安全板块 <span style="font-size:14px;color:#52c41a">7月平均 +11.5% | 量价形态: 放量突破+价升量平</span></h2>

  <h3>4.1 板块逻辑</h3>
  <div class="insight">
    网络安全是<strong>"政策+事件"双驱动</strong>的典型赛道。2026年数据安全法实施细则落地、关基保护条例升级、以及7月重大安全事件催化，使得网安板块在科技股普跌中走出独立行情。<strong>更深层的逻辑是AI带来的安全需求升级</strong>——AI生成的攻击向量需要AI驱动的防御体系，网络安全市场正在从千亿向万亿扩容。
  </div>

  <div class="stock-grid">
    {stock_detail_card("300454.SZ", "网络安全")}
    {stock_detail_card("300369.SZ", "网络安全")}
    {stock_detail_card("688561.SH", "网络安全")}
    {stock_detail_card("002439.SZ", "网络安全")}
    {stock_detail_card("688023.SH", "网络安全")}
  </div>
</div>

<!-- ====== 算力 ====== -->
<div class="section">
  <h2>五、AI算力板块 <span style="font-size:14px;color:#fa8c16">7月平均 -11.7% | 量价形态: 缩量回调(强势整理)</span></h2>

  <h3>5.1 板块逻辑</h3>
  <div class="insight">
    算力板块7月虽然下跌，但<span style="background:#fffbe6;font-weight:700">-11.7%的跌幅远跑赢科技平均-24%</span>，本质上属于"前期涨幅过大后的获利回吐"，而非基本面恶化。海外CSP(Capital Spending)最新指引显示AI投资仍在加速，<strong>光模块/服务器/PCB的订单可见度普遍在6-12个月以上</strong>。当前回调提供了更好的入场价位，重点关注7月底-8月的中报验证。
  </div>

  <div class="stock-grid">
    {stock_detail_card("300308.SZ", "算力")}
    {stock_detail_card("300502.SZ", "算力")}
    {stock_detail_card("688041.SH", "算力")}
    {stock_detail_card("688256.SH", "算力")}
    {stock_detail_card("601138.SH", "算力")}
    {stock_detail_card("002463.SZ", "算力")}
  </div>
</div>

<!-- ====== 六、持仓策略 ====== -->
<div class="section">
  <h2>六、综合持仓策略与操作节奏</h2>

  <h3>6.1 三维配置矩阵</h3>
  <table style="width:100%;border-collapse:collapse;font-size:13px;margin:12px 0">
    <thead>
      <tr style="background:#1a1a2e;color:#fff">
        <th style="padding:10px;text-align:left">配置角色</th>
        <th style="padding:10px;text-align:left">标的</th>
        <th style="padding:10px;text-align:left">仓位建议</th>
        <th style="padding:10px;text-align:left">持有周期</th>
        <th style="padding:10px;text-align:left">操作节奏</th>
      </tr>
    </thead>
    <tbody>
      <tr style="border-bottom:1px solid #eee">
        <td style="padding:10px;font-weight:700;color:#f5222d">核心底仓</td>
        <td style="padding:10px">金山办公、中际旭创、海光信息</td>
        <td style="padding:10px">30-40%</td>
        <td style="padding:10px">6-12个月</td>
        <td style="padding:10px;font-size:12px">持有为主，回调5-8%加仓</td>
      </tr>
      <tr style="border-bottom:1px solid #eee">
        <td style="padding:10px;font-weight:700;color:#fa8c16">弹性配置</td>
        <td style="padding:10px">浪潮信息、深信服、新易盛</td>
        <td style="padding:10px">20-30%</td>
        <td style="padding:10px">1-3个月</td>
        <td style="padding:10px;font-size:12px">波段操作，急涨止盈急跌加仓</td>
      </tr>
      <tr style="border-bottom:1px solid #eee">
        <td style="padding:10px;font-weight:700;color:#1890ff">逆向布局</td>
        <td style="padding:10px">奇安信、龙芯中科、沪电股份</td>
        <td style="padding:10px">10-20%</td>
        <td style="padding:10px">3-6个月</td>
        <td style="padding:10px;font-size:12px">分批低吸，等右侧确认加仓</td>
      </tr>
      <tr>
        <td style="padding:10px;font-weight:700;color:#52c41a">观察待机</td>
        <td style="padding:10px">寒武纪、安恒信息、东方中科</td>
        <td style="padding:10px">0-10%</td>
        <td style="padding:10px">--</td>
        <td style="padding:10px;font-size:12px">等待催化剂或右侧信号</td>
      </tr>
    </tbody>
  </table>

  <h3>6.2 操作纪律</h3>
  <div style="display:grid;grid-template-columns:repeat(2,1fr);gap:14px;margin:14px 0">
    <div style="background:#fff1f0;padding:16px;border-radius:8px">
      <div style="font-weight:700;color:#f5222d;margin-bottom:6px">止损纪律</div>
      <div style="font-size:13px;color:#555">
        • 单票亏损超-8%，无条件减半仓<br>
        • 单票亏损超-15%，清仓出局<br>
        • 板块整体跌破7月低点，总仓位降至5成以下
      </div>
    </div>
    <div style="background:#f6ffed;padding:16px;border-radius:8px">
      <div style="font-weight:700;color:#52c41a;margin-bottom:6px">加仓纪律</div>
      <div style="font-size:13px;color:#555">
        • 中报业绩确认后，核心标的可加至目标仓位<br>
        • MACD金叉+放量站上MA20为右侧加仓信号<br>
        • 单日暴跌5%+但基本面未变：逆向加仓机会
      </div>
    </div>
  </div>

  <h3>6.3 关键时间节点</h3>
  <div style="display:flex;gap:12px;flex-wrap:wrap;margin:12px 0">
    <div style="background:#f0f0f0;padding:10px 16px;border-radius:8px;font-size:13px"><b>7月底-8月中</b><br>中报密集披露期</div>
    <div style="background:#f0f0f0;padding:10px 16px;border-radius:8px;font-size:13px"><b>8月下旬</b><br>华为/苹果秋季发布会</div>
    <div style="background:#f0f0f0;padding:10px 16px;border-radius:8px;font-size:13px"><b>9月</b><br>信创采购招标旺季</div>
    <div style="background:#f0f0f0;padding:10px 16px;border-radius:8px;font-size:13px"><b>Q4</b><br>GDP冲刺+财政支出加速</div>
    <div style="background:#f0f0f0;padding:10px 16px;border-radius:8px;font-size:13px"><b>2027年</b><br>信创全面替换deadline</div>
  </div>
</div>

<!-- ====== 风险提示 ====== -->
<div class="disclaimer">
  <h4>风险提示与免责声明</h4>
  <p>
  <strong>主要风险因素：</strong><br>
  ① <strong>信创政策风险：</strong>2027年deadline若延期，板块逻辑将受到重大冲击。<br>
  ② <strong>业绩不及预期：</strong>中报季（7-8月）为关键验证窗口。信创/网安多数公司Q2为淡季，单季波动不代表全年趋势。<br>
  ③ <strong>AI投资降速：</strong>若海外CSP缩减AI资本开支，光模块/服务器产业链将直接承压。<br>
  ④ <strong>制裁升级：</strong>美国若进一步收紧芯片出口管制，海光信息/寒武纪等将受到冲击。<br>
  ⑤ <strong>估值风险：</strong>部分标的前期涨幅较大（浪潮信息+34%），短期存在技术性回调需要。<br>
  ⑥ <strong>流动性风险：</strong>若整体市场继续下行，强势板块也可能补跌。<br><br>
  <strong>免责声明：</strong>本报告基于公开数据和机构研报整理，行业地位/竞争格局分析参考券商研报观点，量价数据来自Tushare/东方财富/腾讯财经。所有分析仅供参考，不构成投资建议。投资有风险，入市需谨慎。
  </p>
</div>

</div>
</body>
</html>"""

# ============================================================
report_path = BASE.parent / "信创_网络安全_AI算力_三大板块深度挖掘.html"
with open(report_path, "w", encoding="utf-8") as f:
    f.write(full_html)

print(f"Report: {report_path}")
print(f"Size: {len(full_html)/1024:.1f} KB")
