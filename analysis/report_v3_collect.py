"""
V3 深度分析: 增强数据采集（11模块）
=================================
V2基础上新增:
  A. 研报数据 — 东财reportapi (评级/目标价/三年EPS)
  B. 业务描述 — mootdx F10 "公司概况" + 巨潮年报
  C. 资金流   — 东财 push2his 120日主力/大单/中单/小单
  D. 量价分析 — 集成 功能模块代码/量价分析 VPA引擎
     (Anna Coulling方法论: 趋势×量价信号×资金流 三维评级)
"""
import sys, os, io, json, time
os.environ['PYTHONIOENCODING'] = 'utf-8'
sys.path.insert(0, '.')
# VPA模块路径
_vpa_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '功能模块代码')
if os.path.isdir(_vpa_path):
    sys.path.insert(0, _vpa_path)

from TG_trading_sys.data.cache import DataCache
from datetime import datetime
import numpy as np
import pandas as pd

# ── 标的池（沿用V2的12只精选）──
PICKS = [
    ("300456","赛微电子","半导体-制造","MEMS微机电系统芯片制造，全球领先的纯MEMS代工厂，瑞典Silex+北京FAB3双产线","全球MEMS代工CR3>70%，纯代工模式差异化竞争，国内MEMS代工绝对龙头","1)全球稀缺MEMS纯代工产能 2)瑞典技术+中国产能双轮驱动 3)北京FAB3量产爬坡 4)客户粘性极高","北京FAB3 3000-30000片/月，硅光子/生物医疗MEMS新品类","下游消费电子周期、中美科技脱钩、产能爬坡不及预期"),
    ("688332","中科蓝讯","半导体-数字IC","无线音频SoC芯片，RISC-V架构出货量国内第一，TWS耳机/蓝牙音箱/智能手表","TWS SoC: 恒玄(高端)/中科蓝讯(放量)/杰理(白牌)，RISC-V差异化","1)RISC-V先发优势免ARM费 2)出货量国内第一规模效应 3)白牌-品牌升级 4)22nm-12nm降功耗","品牌渗透率30%-60%，AI降噪/语音唤醒，智能手表/车载新品类","TWS市场饱和、价格战压缩毛利、RISC-V生态不及ARM"),
    ("688636","智明达","元件-军工电子","军用嵌入式计算机，机载/弹载/舰载/车载，核心客户中航工业/中国电科/兵器集团","军工嵌入式计算机壁垒极高(军工四证+5-10年定型周期)，格局稳定","1)军工嵌入式计算机完整资质 2)绑定多型重点型号 3)国产化率100%替代逻辑","从嵌入式计算机-综合任务系统，无人机/智能弹药新领域","军品采购节奏不确定、型号定型延迟、单一客户依赖"),
    ("688080","映翰通","通信-工业物联网","工业物联网通信设备，工业路由器/边缘网关/云平台，电力/交通/零售等行业","工业物联网通信市场分散，公司在电力巡检和交通领域有差异化优势","1)工业物联网端到端方案 2)电力巡检细分龙头 3)边缘计算+AI融合","电力物联网渗透率提升，交通/零售行业拓展，边缘AI网关新品","行业竞争加剧、电力集采降价、新产品推广周期长"),
    ("003019","宸展光电","元件-显示模组","商用显示及触控一体机，POS/自助终端/数字标牌/智能健身镜/医疗显示","全球POS ODM龙头(市占率~15%)，ODM+自有品牌双轮驱动","1)全球POS ODM龙头 2)智能健身镜/医疗显示新品类 3)自有品牌提升毛利","自有品牌15%-30%，医疗显示认证，东南亚制造基地","POS电子化替代风险、ODM毛利率天花板、海外关税"),
    ("000725","京东方A","元件-面板","全球半导体显示龙头，LCD/OLED/MLED全品类覆盖，智能手机/TV/IT/车载","LCD双寡头(京东方+TCL华星)，OLED追赶三星，行业集中度持续提升","1)LCD全球出货量第一 2)OLED产能爬坡进入苹果链 3)物联网转型第二曲线","OLED从刚性-柔性-折叠，MLED量产，智慧医工/智慧金融新业务","面板价格周期性、OLED良率爬坡、巨额资本开支"),
    ("000100","TCL科技","元件-面板","半导体显示+新能源光伏双主业，TCL华星(LCD/OLED)+中环股份(光伏硅片)","LCD双寡头之一，光伏硅片双龙头(中环+隆基)，双主业协同","1)LCD面板龙头+光伏硅片龙头双引擎 2)中环G12大硅片领先 3)垂直整合优势","T9产线量产扩大IT面板份额，中环G12产能翻倍，海外产能布局","面板周期+光伏产能过剩双重风险、债务压力、双主业管理复杂度"),
    ("301195","北路智控","软件-工业","智能矿山工业软件，煤矿智能化管控平台/UWB精确定位/AI视频分析","煤矿智能化: 北路(定位/通信)/梅安森(监测)/龙软(GIS)/科达(自动化)","1)煤矿智能化政策强制推动 2)UWB精确定位技术领先 3)中煤科工集团背景","煤矿智能化覆盖率30%-60%，AI+矿山大模型，化工园区新市场","煤炭资本开支周期、政策推进不及预期、客户集中于大矿"),
    ("300303","聚飞光电","半导体-封装","LED封装及Mini LED背光，产品覆盖TV背光/手机背光/车载LED/不可见光","国内LED封装第二梯队(次于木林森/国星)，Mini LED背光差异化竞争","1)Mini LED背光先发优势 2)车载LED认证周期长壁垒高 3)不可见光新品类","Mini LED TV渗透率从5%-15%，车载LED从国内-海外，不可见光量产","LED行业产能过剩、Mini LED推广不及预期、价格竞争"),
    ("301608","博实结","通信-设备","物联网通信模组及终端，蜂窝模组/WiFi模组/定位终端/车联网","物联网模组CR3>50%(移远/广和通/日海)，公司在特定垂直行业有差异化","1)车联网前装市场准入壁垒 2)海外市场拓展(东南亚/中东) 3)从模组-终端-方案升级","车联网从后装-前装，海外收入占比从20%-40%，边缘AI模组","模组价格战、芯片供应风险、海外市场不确定性"),
    ("600288","大恒科技","元件-光学","精密光学元件及系统，机器视觉/激光光学/太赫兹安检/数字放映","光学元件格局分散，公司在激光光学和太赫兹领域差异化，太赫兹安检A股稀缺标的","1)太赫兹技术稀缺性 2)中科院光机所背景 3)机器视觉行业高景气","太赫兹安检轨交-法院/医院，激光光学-半导体设备配套，机器视觉-3D检测","太赫兹商业化进度不确定、光学元件竞争加剧、应收账款较大"),
    ("001308","康冠科技","元件-显示模组","智能显示终端ODM，智能电视/电竞显示器/会议平板/教育白板，全球ODM出货前列","全球TV ODM CR3~40%(冠捷/TCL/康冠)，公司在电竞显示和会议平板细分领先","1)全球TV ODM前三 2)电竞显示器高增长赛道 3)智能会议平板新品类放量","电竞显示器自有品牌(MK)培育，智能会议平板从ODM-品牌，东南亚工厂","TV需求下滑、面板价格波动、ODM模式低毛利"),
]

# ═══════════════════════════════════════════════════
# 新增模块 A: 研报数据（东财 reportapi）
# ═══════════════════════════════════════════════════
def collect_research(code, cache=None):
    """拉取研报列表 + 统计汇总"""
    if cache is None:
        cache = DataCache()
    try:
        reports = cache.get_research_targets(code, limit=30)
        if not reports:
            return {"reports": [], "stats": None}

        # 评级分布
        rating_dist = {}
        for r in reports:
            rt = r.get("rating", "")
            if rt:
                rating_dist[rt] = rating_dist.get(rt, 0) + 1

        # 目标价统计
        targets = [r["target_price"] for r in reports if r.get("target_price")]
        eps_26_list = [r["eps_2025"] for r in reports if r.get("eps_2025", 0) > 0]
        eps_27_list = [r["eps_2026"] for r in reports if r.get("eps_2026", 0) > 0]

        stats = {
            "total": len(reports),
            "with_target": len(targets),
            "rating_dist": rating_dist,
            "target_mean": round(np.mean(targets), 2) if targets else None,
            "target_high": round(max(targets), 2) if targets else None,
            "target_low": round(min(targets), 2) if targets else None,
            "target_median": round(np.median(targets), 2) if targets else None,
            "eps_2026_mean": round(np.mean(eps_26_list), 2) if eps_26_list else None,
            "eps_2027_mean": round(np.mean(eps_27_list), 2) if eps_27_list else None,
            "latest_date": reports[0]["date"] if reports else "",
        }
        return {"reports": reports[:20], "stats": stats}
    except Exception as e:
        print(f"    研报ERROR: {e}")
        return {"reports": [], "stats": None}


def synthesize_research(reports_data, current_price=None, pe_ttm=None, industry_pe=None):
    """
    研报观点深度综合分析 — 语义级标题解析 + 隐含目标价推算。

    三步分析：
    1. 逐篇解析标题 → 提取业绩信号/增长逻辑/催化剂/风险
    2. 跨报告交叉对比 → 共识主题 + 分歧点
    3. 隐含目标价 ← 从EPS推算（当机构未给明确目标价时）
    """
    reports = reports_data.get("reports", [])
    stats = reports_data.get("stats", {})

    if not reports or not stats:
        return None

    total = stats.get("total", 0)
    rating_dist = stats.get("rating_dist", {})

    # ═══════════════════════════════════
    # 1. 逐篇语义解析
    # ═══════════════════════════════════
    parsed_reports = []
    for r in reports:
        title = r.get("title", "")
        if not title or len(title) < 5:
            continue
        parsed = _parse_report_title(title)
        parsed["org"] = r.get("org", "")
        parsed["date"] = r.get("date", "")
        parsed["rating"] = r.get("rating", "")
        parsed["target_price"] = r.get("target_price")
        parsed["eps_26"] = r.get("eps_2025", 0)
        parsed["eps_27"] = r.get("eps_2026", 0)
        parsed_reports.append(parsed)

    if not parsed_reports:
        return None

    # ═══════════════════════════════════
    # 2. 跨报告交叉分析
    # ═══════════════════════════════════

    # 2a. 业绩信号汇总
    earnings_signals = [p["earnings_signal"] for p in parsed_reports if p["earnings_signal"]]
    if earnings_signals:
        beats = sum(1 for s in earnings_signals if "增" in s or "超" in s or "扭" in s or "高" in s)
        misses = sum(1 for s in earnings_signals if "降" in s or "承压" in s or "下滑" in s)
        if beats > misses * 2:
            earnings_consensus = f"业绩趋势向好（{beats}/{len(earnings_signals)}篇持正面判断）"
        elif misses > beats * 2:
            earnings_consensus = f"业绩面临压力（{misses}/{len(earnings_signals)}篇表达担忧）"
        else:
            earnings_consensus = f"业绩判断分化（正面{beats}篇/负面{misses}篇）"
    else:
        earnings_consensus = ""

    # 2b. 增长驱动聚类
    driver_counts = {}
    for p in parsed_reports:
        for driver in p["growth_drivers"]:
            normalized = _normalize_driver(driver)
            driver_counts[normalized] = driver_counts.get(normalized, 0) + 1

    # 按提及频次排序
    top_drivers = sorted(driver_counts.items(), key=lambda x: -x[1])
    major_drivers = [d for d, c in top_drivers if c >= 2]  # 至少2家提及
    minor_drivers = [d for d, c in top_drivers if c == 1]

    # 2c. 风险关注聚类
    risk_counts = {}
    for p in parsed_reports:
        for risk in p["risks"]:
            normalized = _normalize_driver(risk)
            risk_counts[normalized] = risk_counts.get(normalized, 0) + 1
    top_risks = sorted(risk_counts.items(), key=lambda x: -x[1])

    # 2d. 公司定性评价
    quality_signals = [p["quality_signal"] for p in parsed_reports if p["quality_signal"]]
    quality_unique = list(set(quality_signals))[:5]

    # ═══════════════════════════════════
    # 3. 隐含目标价推算
    # ═══════════════════════════════════
    implied_targets = _calc_implied_targets(reports, parsed_reports, current_price, pe_ttm, industry_pe)

    # ═══════════════════════════════════
    # 4. 评级共识
    # ═══════════════════════════════════
    buys = rating_dist.get("买入", 0)
    holds = rating_dist.get("增持", 0) + rating_dist.get("持有", 0) + rating_dist.get("中性", 0)
    if total > 0:
        buy_ratio = buys / total
        if buy_ratio >= 0.8:
            rating_consensus = "强烈看多"
        elif buy_ratio >= 0.5:
            rating_consensus = "偏乐观"
        elif buy_ratio >= 0.3:
            rating_consensus = "中性偏多"
        else:
            rating_consensus = "分歧较大"
    else:
        rating_consensus = ""

    # ═══════════════════════════════════
    # 5. EPS预测趋势
    # ═══════════════════════════════════
    eps_26_mean = stats.get("eps_2026_mean")
    eps_27_mean = stats.get("eps_2027_mean")
    if eps_26_mean and eps_27_mean and eps_26_mean > 0:
        change = (eps_27_mean - eps_26_mean) / eps_26_mean * 100
        if change > 20:
            eps_trend = f"分析师预期2027年EPS增长{change:.0f}%，高速成长"
        elif change > 5:
            eps_trend = f"分析师预期2027年EPS增长{change:.0f}%，稳健增长"
        elif change > -5:
            eps_trend = f"分析师预期EPS基本持平（{change:+.0f}%）"
        else:
            eps_trend = f"分析师预期EPS下滑{abs(change):.0f}%"
    else:
        eps_trend = ""

    # ═══════════════════════════════════
    # 6. 生成综合叙事
    # ═══════════════════════════════════
    latest_date = parsed_reports[0]["date"] if parsed_reports else ""

    # 叙事段落
    narrative_parts = []
    # 评级
    if rating_consensus:
        narrative_parts.append(f"{total}家机构覆盖，评级共识为「{rating_consensus}」（买入{buys}家/增持+持有{holds}家）")

    # 业绩
    if earnings_consensus:
        narrative_parts.append(earnings_consensus)

    # 增长驱动
    if major_drivers:
        driver_str = "、".join(major_drivers[:4])
        narrative_parts.append(f"核心增长逻辑集中在：{driver_str}")

    # 目标价
    all_targets = implied_targets.get("all_targets", [])
    if all_targets:
        narrative_parts.append(f"综合目标价区间{implied_targets['target_low']:.1f}～{implied_targets['target_high']:.1f}元（均值{implied_targets['target_mean']:.1f}元）")
        if implied_targets.get("explicit_count", 0) < len(all_targets):
            narrative_parts.append(f"（注：其中{len(all_targets) - implied_targets['explicit_count']}篇目标价由EPS×合理PE推算）")

    # 风险
    if top_risks:
        risk_str = "、".join([r for r, c in top_risks[:3]])
        narrative_parts.append(f"共同关注的风险：{risk_str}")

    narrative = "。".join(narrative_parts) + "。"

    # ═══════════════════════════════════
    # 7. 分类观点整理
    # ═══════════════════════════════════
    viewpoint_groups = {
        "业绩判断": earnings_signals[:6] if earnings_signals else [],
        "增长驱动": major_drivers[:6] if major_drivers else [],
        "公司质地": quality_unique[:4] if quality_unique else [],
        "关注风险": [r for r, c in top_risks[:4]] if top_risks else [],
    }

    return {
        "narrative": narrative,
        "viewpoint_groups": viewpoint_groups,
        "major_drivers": major_drivers,
        "top_risks": [r for r, c in top_risks[:4]],
        "rating_consensus": rating_consensus,
        "earnings_consensus": earnings_consensus,
        "eps_trend": eps_trend,
        "implied_targets": implied_targets,
        "latest_date": latest_date,
        "recent_views": [
            {"date": p["date"], "org": p["org"], "rating": p["rating"],
             "clean_title": p["clean_title"],
             "earnings_signal": p["earnings_signal"],
             "growth_drivers": p["growth_drivers"][:3]}
            for p in parsed_reports[:8]
        ],
    }


def _parse_report_title(title):
    """
    语义解析一篇中文研报标题。

    识别结构： [前缀：]核心判断[——补充]
    前缀类型：首次覆盖/年报点评/半年报点评/深度报告/Q3业绩/...
    """
    result = {
        "clean_title": title,
        "report_type": "",
        "earnings_signal": "",
        "growth_drivers": [],
        "risks": [],
        "quality_signal": "",
        "catalysts": [],
    }

    clean = title.strip()

    # ── 剥离报告类型前缀 ──
    prefixes = [
        ("首次覆盖：", "首次覆盖"), ("年报点评：", "年报点评"), ("半年报点评：", "半年报点评"),
        ("公司深度报告：", "深度报告"), ("深度报告：", "深度报告"),
        ("2025年年报点评：", "年报点评"), ("2024年年报点评：", "年报点评"),
        ("2025年半年报点评：", "半年报点评"), ("2024年半年报点评：", "半年报点评"),
        ("公司跟踪报告：", "跟踪报告"), ("公司动态研究报告：", "动态研究"),
        ("公司点评：", "公司点评"), ("公司研究：", "公司研究"),
    ]
    for prefix, ptype in prefixes:
        if clean.startswith(prefix):
            result["report_type"] = ptype
            clean = clean[len(prefix):]
            break

    # 移除 "xxx：" 格式的公司名前缀
    for sep in ["：", ":"]:
        if sep in clean:
            before = clean.split(sep)[0]
            if len(before) <= 12 and ("证券" not in before):
                # 可能是公司名，检查不含标点
                pass  # keep it, could be part of content

    result["clean_title"] = clean

    # ── 业绩信号提取 ──
    earnings_patterns = [
        (["利润大增", "业绩大幅增长", "业绩高增", "盈利大幅提升", "利润高增",
          "超预期", "好于预期", "超市场预期", "大增", "暴增"], "业绩大幅增长"),
        (["扭亏为盈", "扭亏", "实现盈利", "转正"], "扭亏为盈"),
        (["稳健增长", "稳步增长", "持续增长", "稳定增长", "业绩稳健",
          "稳增长", "稳中有升", "稳中向好", "稳步提升"], "业绩稳健增长"),
        (["利润增长", "业绩增长", "盈利增长", "同比增长", "增长强劲"], "业绩增长"),
        (["恢复增长", "景气回升", "边际改善", "环比改善", "逐季改善"], "业绩边际改善"),
        (["下滑", "下降", "承压", "低于预期", "不及预期", "亏损", "压力"], "业绩承压/下滑"),
        (["高增", "增加", "提升", "改善", "向好"], "经营向好"),
    ]
    for keywords, signal in earnings_patterns:
        if any(kw in clean for kw in keywords):
            result["earnings_signal"] = signal
            break

    # ── 增长驱动/业务逻辑提取 ──
    driver_patterns = [
        # AI/科技
        (["AI", "人工智能", "大模型", "端侧", "边缘计算", "推理", "智能"], "AI/智能化布局"),
        (["AIOT", "物联网", "IoT", "智能家居", "可穿戴"], "AIOT/物联网扩展"),
        # 产品/产能
        (["新品", "新产品", "产品矩阵", "品类扩张", "产品线"], "产品矩阵扩张"),
        (["产能爬坡", "产能扩张", "量产", "扩产", "产线", "产能释放"], "产能扩张/爬坡"),
        (["技术突破", "技术升级", "研发", "自主可控", "国产替代", "国产化"], "技术/国产替代"),
        (["认证", "进入", "导入", "突破"], "客户/认证突破"),
        # 市场/品牌
        (["品牌", "品牌客户", "品牌升级", "品牌化"], "品牌升级"),
        (["海外", "出海", "全球化", "国际"], "海外/全球化拓展"),
        (["市占率", "份额", "渗透率", "渗透"], "市场份额提升"),
        # 业务结构
        (["双轮驱动", "双引擎", "双主业", "多元化"], "双轮/多元驱动"),
        (["第二曲线", "新增长", "新动能", "新引擎", "新业务"], "新增长曲线"),
        (["龙头", "领先", "优势", "壁垒", "护城河", "稀缺"], "行业龙头/领先地位"),
        # 行业
        (["景气", "周期向上", "复苏", "回暖", "拐点", "底部反转"], "行业景气/拐点"),
        # 盈利质量
        (["毛利率", "净利率", "盈利质量", "盈利能力"], "盈利能力改善"),
        (["降本", "增效", "效率", "优化"], "降本增效"),
        # 订单/需求
        (["订单", "需求旺盛", "供不应求", "满产"], "订单/需求旺盛"),
        # 新能源/光伏/面板
        (["OLED", "AMOLED", "柔性", "折叠"], "OLED升级"),
        (["LCD", "面板", "显示"], "LCD/面板"),
        (["光伏", "硅片", "新能源", "储能"], "光伏/新能源"),
        (["MEMS", "传感器", "射频", "滤波器"], "MEMS/射频"),
        (["半导体", "芯片", "集成电路", "晶圆"], "半导体"),
        (["军工", "军用", "机载", "弹载", "装备"], "军工/国防"),
        (["汽车", "车载", "车规", "自动驾驶"], "汽车/车载电子"),
    ]
    for keywords, driver in driver_patterns:
        if any(kw in clean for kw in keywords):
            result["growth_drivers"].append(driver)

    # ── 风险提取 ──
    risk_patterns = [
        (["周期", "周期性", "波动"], "行业周期波动"),
        (["竞争", "价格战", "内卷"], "竞争加剧"),
        (["下滑", "需求不足", "需求疲软"], "需求疲软"),
        (["良率", "爬坡不及预期", "进度不及预期"], "进度不及预期"),
        (["关税", "贸易", "制裁", "脱钩"], "地缘/贸易风险"),
        (["债务", "杠杆", "负债"], "财务杠杆风险"),
    ]
    for keywords, risk in risk_patterns:
        if any(kw in clean for kw in keywords):
            result["risks"].append(risk)

    # ── 公司质地信号 ──
    quality_patterns = [
        (["龙头", "领先", "第一"], "行业龙头"),
        (["稀缺", "唯一", "独家", "垄断"], "稀缺标的"),
        (["稳健", "确定性", "防御"], "经营稳健"),
        (["高成长", "高增长", "快速成长"], "高成长性"),
        (["平台型", "生态", "系统级", "综合"], "平台型企业"),
    ]
    for keywords, quality in quality_patterns:
        if any(kw in clean for kw in keywords):
            result["quality_signal"] = quality
            break

    # ── 催化剂提取 ──
    catalyst_patterns = [
        ("落地", "新产品/技术落地"), ("放量", "产品放量"),
        ("量产", "进入量产"), ("突破", "技术/客户突破"),
        ("首次", "首次突破/覆盖"), ("加速", "增长加速"),
    ]
    for kw, cat in catalyst_patterns:
        if kw in clean:
            result["catalysts"].append(cat)

    return result


def _normalize_driver(driver):
    """统一增长驱动/风险的表述"""
    # 合并相似表述
    mapping = {
        "AI/智能化布局": "AI/AIOT布局",
        "AIOT/物联网扩展": "AI/AIOT布局",
        "产品矩阵扩张": "产品矩阵扩张",
        "产能扩张/爬坡": "产能扩张",
        "技术/国产替代": "技术/国产替代",
        "品牌升级": "品牌升级",
        "海外/全球化拓展": "海外拓展",
        "市场份额提升": "份额提升",
        "双轮/多元驱动": "多元驱动",
        "新增长曲线": "新增长极",
        "行业龙头/领先地位": "龙头地位",
        "行业景气/拐点": "行业景气",
    }
    return mapping.get(driver, driver)


def _calc_implied_targets(reports, parsed_reports, current_price, pe_ttm, industry_pe):
    """
    推算机构隐含目标价。

    方法：
    1. 有明确目标价的研报 → 直接使用，同时反推其隐含PE = target / eps_2026
    2. 无目标价但有EPS的研报 → 目标价 = 隐含PE中位数 × EPS
    3. 使用合理PE（优先：其他机构隐含PE > 个股TTM PE > 行业PE）
    """
    explicit_targets = []
    implicit_pe_list = []

    for r in reports:
        tp = r.get("target_price")
        eps = r.get("eps_2025", 0)
        if tp and eps and eps > 0:
            explicit_targets.append(tp)
            implicit_pe_list.append(tp / eps)

    # 确定推算用的PE
    if implicit_pe_list:
        implied_pe = float(np.median(implicit_pe_list))
        pe_source = f"机构隐含PE中位数({implied_pe:.1f}x)"
    elif pe_ttm and pe_ttm > 0:
        implied_pe = pe_ttm
        pe_source = f"当前TTM PE({pe_ttm:.1f}x)"
    elif industry_pe and industry_pe > 0:
        implied_pe = industry_pe
        pe_source = f"行业PE({industry_pe:.1f}x)"
    else:
        implied_pe = 20  # A股科技股通用参考PE
        pe_source = f"默认参考PE(20x)"

    # 为没有目标价的研报推算
    all_targets = list(explicit_targets)
    for r in reports:
        tp = r.get("target_price")
        eps = r.get("eps_2025", 0)
        if not tp and eps and eps > 0:
            estimated = round(eps * implied_pe, 2)
            all_targets.append(estimated)

    if all_targets:
        target_mean = round(float(np.mean(all_targets)), 2)
        target_high = round(float(np.max(all_targets)), 2)
        target_low = round(float(np.min(all_targets)), 2)
        target_median = round(float(np.median(all_targets)), 2)

        upside = None
        if current_price and current_price > 0 and target_mean > 0:
            upside = round((target_mean - current_price) / current_price * 100, 1)

        return {
            "explicit_count": len(explicit_targets),
            "total_estimates": len(all_targets),
            "target_mean": target_mean,
            "target_median": target_median,
            "target_high": target_high,
            "target_low": target_low,
            "upside_pct": upside,
            "pe_used": round(implied_pe, 1),
            "pe_source": pe_source,
            "all_targets": all_targets,
        }

    return {
        "explicit_count": 0, "total_estimates": 0,
        "target_mean": None, "upside_pct": None,
        "pe_used": round(implied_pe, 1), "pe_source": pe_source,
        "all_targets": [],
    }


# ═══════════════════════════════════════════════════
# 新增模块 B: 业务描述（mootdx F10 + 巨潮年报）
# ═══════════════════════════════════════════════════
def collect_business(code, cache=None):
    """从 mootdx F10 提取公司概况文本，fallback到巨潮和腾讯"""
    if cache is None:
        cache = DataCache()
    result = {"f10_summary": "", "annual_reports": [], "source": ""}

    # 来源1: mootdx F10 "公司概况"
    try:
        from mootdx.quotes import Quotes
        client = Quotes.factory(market='std')
        text = client.F10(symbol=code, name='公司概况')
        if text and len(text) > 50:
            result["f10_summary"] = text[:1500]  # 取前1500字
            result["source"] = "mootdx F10"
    except Exception as e:
        print(f"    F10不可用: {e}")

    # 来源2: 巨潮最新年报标题（使用正确的orgId映射）
    if not result["f10_summary"]:
        try:
            import requests
            pure_code = code.zfill(6)
            # 使用巨潮官方 orgId 映射表
            org_id = _get_cninfo_orgid(pure_code)
            url = "https://www.cninfo.com.cn/new/hisAnnouncement/query"
            payload = {
                "stock": f"{pure_code},{org_id}",
                "tabName": "fulltext",
                "pageSize": "5",
                "pageNum": "1",
                "category": "category_ndbg_szsh",  # 年报
                "seDate": "",
            }
            r = requests.post(url, data=payload, timeout=10,
                headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.cninfo.com.cn/"})
            data = r.json()
            anns = data.get("announcements", []) or []
            if anns:
                result["source"] = "巨潮年报"
                for a in anns[:2]:
                    from datetime import datetime as _dt
                    ts = a.get("announcementTime", 0)
                    try:
                        date_str = _dt.fromtimestamp(int(ts)/1000).strftime("%Y-%m-%d") if ts else ""
                    except:
                        date_str = str(ts)[:10] if ts else ""
                    result["annual_reports"].append({
                        "title": a.get("announcementTitle", ""),
                        "date": date_str,
                        "url": f"https://www.cninfo.com.cn/new/disclosure/detail?annoId={a.get('announcementId','')}"
                    })
        except Exception as e:
            pass  # 静默失败，fallback到硬编码

    # 注意：不再生成虚假的"所属行业: "占位文本。
    # 当所有数据源都失败时，f10_summary保持空字符串，
    # HTML报告会使用PICKS中的biz_hardcoded作为fallback。

    return result


# ── 巨潮 orgId 映射缓存 ──
_CNINFO_ORGID_MAP = {}

def download_and_extract_reports(code, reports, max_pdfs=3):
    """
    下载研报PDF并提取正文文本。

    只下载最近max_pdfs篇（默认3篇），缓存到 data/research_pdfs/{code}/
    """
    import io as _io

    pdf_dir = os.path.join('data', 'research_pdfs', code)
    os.makedirs(pdf_dir, exist_ok=True)

    extracted = []
    for i, rep in enumerate(reports):
        if i >= max_pdfs:
            break
        info_code = rep.get('info_code', '')
        if not info_code:
            continue

        pdf_path = os.path.join(pdf_dir, f'{info_code}.txt')
        text = None

        # 检查缓存
        if os.path.exists(pdf_path):
            try:
                with open(pdf_path, 'r', encoding='utf-8') as f:
                    text = f.read()
            except:
                pass

        # 下载+提取
        if not text:
            try:
                import requests as _req
                import pdfplumber as _pdf

                pdf_url = f'https://pdf.dfcfw.com/pdf/H3_{info_code}_1.pdf'
                r = _req.get(pdf_url, timeout=30,
                    headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://data.eastmoney.com/'})

                if r.status_code == 200 and len(r.content) > 1000:
                    with _pdf.open(_io.BytesIO(r.content)) as pdf:
                        text_parts = []
                        for page in pdf.pages[:6]:  # 前6页（通常含摘要+核心观点）
                            page_text = page.extract_text()
                            if page_text:
                                text_parts.append(page_text)
                        text = '\n'.join(text_parts)

                    # 缓存
                    if text:
                        with open(pdf_path, 'w', encoding='utf-8') as f:
                            f.write(text)
            except Exception:
                pass

        if text:
            # 提取核心段落（投资要点/盈利预测部分）
            core = _extract_report_core(text)
            extracted.append({
                'org': rep.get('org', ''),
                'date': rep.get('date', ''),
                'title': rep.get('title', ''),
                'full_text': text[:3000],
                'core_summary': core,
                'pages': rep.get('attach_pages', 0),
            })
        else:
            extracted.append({
                'org': rep.get('org', ''),
                'date': rep.get('date', ''),
                'title': rep.get('title', ''),
                'full_text': '',
                'core_summary': '',
                'pages': rep.get('attach_pages', 0),
            })

    return extracted


def _extract_report_core(text):
    """从研报PDF文本中提取核心观点段落"""
    if not text:
        return ''

    lines = text.split('\n')
    core_lines = []
    in_core = False

    # 关键章节标记
    section_markers = [
        '投资要点', '投资建议', '核心观点', '盈利预测', '投资逻辑',
        '事件点评', '事件', '主要内容', '报告摘要', '业绩点评',
        '事件概述', '点评', '分析与判断', '结论', '风险提示',
        '投资要件', '关键假设', '区别于市场的观点',
    ]

    for line in lines:
        line_stripped = line.strip()
        if not line_stripped:
            continue

        # 检测章节标题
        for marker in section_markers:
            if marker in line_stripped and len(line_stripped) < 30:
                in_core = True
                core_lines.append(f'【{line_stripped}】')
                break
        else:
            if in_core and len(line_stripped) > 20:
                # 遇到下一个短标题就停止
                if len(line_stripped) < 15 and ('。' not in line_stripped):
                    in_core = False
                    continue
                core_lines.append(line_stripped)

    # 如果没找到章节标记，取前1000字
    if not core_lines:
        return text[:1000]

    result = '\n'.join(core_lines[:30])  # 最多30行
    return result[:2000]


def collect_f10_summary(code):
    """
    从 mootdx F10 获取公司基本面文本摘要。

    尝试: 最新提示 → 公司大事 → 业内点评
    作为年报/公告内容摘要的补充来源。
    """
    result = {'latest_tips': '', 'company_events': '', 'industry_comments': ''}
    try:
        from mootdx.quotes import Quotes
        client = Quotes.factory(market='std')

        for name in ['最新提示', '公司大事', '业内点评']:
            try:
                text = client.F10(symbol=code, name=name)
                if text and len(text) > 50:
                    key = {'最新提示': 'latest_tips', '公司大事': 'company_events',
                           '业内点评': 'industry_comments'}[name]
                    result[key] = text[:2000]
            except:
                pass
    except:
        pass
    return result


# ── 巨潮 orgId 映射缓存 ──
def _get_cninfo_orgid(code: str) -> str:
    """查股票真实 orgId（巨潮官方映射表，6198只股票）"""
    global _CNINFO_ORGID_MAP
    if not _CNINFO_ORGID_MAP:
        try:
            import requests
            r = requests.get("http://www.cninfo.com.cn/new/data/szse_stock.json",
                             headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
            _CNINFO_ORGID_MAP = {s["code"]: s["orgId"]
                                 for s in r.json().get("stockList", [])}
        except Exception:
            pass
    org = _CNINFO_ORGID_MAP.get(code)
    if org:
        return org
    # fallback
    if code.startswith("6"): return f"gssh0{code}"
    elif code.startswith("8") or code.startswith("4"): return f"gsbj0{code}"
    return f"gssz0{code}"


# ═══════════════════════════════════════════════════
# 新增模块 C: 资金流（东财 push2his 120日）
# ═══════════════════════════════════════════════════
def collect_moneyflow(code):
    """拉取120日资金流 + 统计指标（含重试+降级）"""
    try:
        import requests
        import time
        pure_code = code.zfill(6)
        market_code = 1 if pure_code.startswith("6") else 0

        url = "https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get"
        params = {
            "secid": f"{market_code}.{pure_code}",
            "fields1": "f1,f2,f3,f7",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65",
            "lmt": "120",
        }
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                   "Referer": "https://quote.eastmoney.com/"}

        # 【修复】指数退避重试（1s/2s/4s），最多3次
        klines = None
        for attempt in range(3):
            try:
                r = requests.get(url, params=params, timeout=15, headers=headers)
                d = r.json()
                klines = d.get("data", {}).get("klines", [])
                if klines is not None:
                    break
            except (requests.exceptions.ConnectionError,
                    requests.exceptions.ReadTimeout,
                    requests.exceptions.ChunkedEncodingError):
                if attempt < 2:
                    time.sleep(2 ** attempt)  # 1s, 2s, 4s
            except Exception:
                break

        # 【降级】push2his失败，尝试东财summary接口
        if klines is None:
            try:
                summary_url = "https://push2.eastmoney.com/api/qt/stock/get"
                summary_params = {
                    "secid": f"{market_code}.{pure_code}",
                    "fields": "f162,f164,f166,f168,f170,f172,f174,f176,f178,f180,f182,f184",
                }
                r2 = requests.get(summary_url, params=summary_params, timeout=10, headers=headers)
                d2 = r2.json()
                flow_data = d2.get("data", {})
                if flow_data:
                    klines = []
            except Exception:
                pass

        if not klines:
            return {"flow_data": [], "stats": None}

        rows = []
        for line in klines:
            parts = line.split(",")
            if len(parts) >= 7:
                rows.append({
                    "date": parts[0],
                    "main_net": float(parts[1]) if parts[1] != "-" else 0,
                    "small_net": float(parts[2]) if parts[2] != "-" else 0,
                    "mid_net": float(parts[3]) if parts[3] != "-" else 0,
                    "large_net": float(parts[4]) if parts[4] != "-" else 0,
                    "super_net": float(parts[5]) if parts[5] != "-" else 0,
                })

        # 统计
        recent_5 = rows[-5:] if len(rows) >= 5 else rows
        recent_20 = rows[-20:] if len(rows) >= 20 else rows
        recent_60 = rows[-60:] if len(rows) >= 60 else rows

        main_5 = sum(r["main_net"] for r in recent_5)
        main_20 = sum(r["main_net"] for r in recent_20)
        main_60 = sum(r["main_net"] for r in recent_60)

        # 主力连续流入/流出天数
        consecutive_in = 0
        consecutive_out = 0
        for r in reversed(rows):
            if r["main_net"] > 0:
                if consecutive_out == 0:
                    consecutive_in += 1
                else:
                    break
            elif r["main_net"] < 0:
                if consecutive_in == 0:
                    consecutive_out += 1
                else:
                    break
            else:
                break

        # 大单占比趋势
        recent_20_large = sum(r["large_net"] + r["super_net"] for r in recent_20)
        recent_20_small = sum(r["small_net"] for r in recent_20)
        large_pct = abs(recent_20_large) / (abs(recent_20_large) + abs(recent_20_small) + 1) * 100

        stats = {
            "data_days": len(rows),
            "main_net_5d_yi": round(main_5 / 1e8, 2),
            "main_net_20d_yi": round(main_20 / 1e8, 2),
            "main_net_60d_yi": round(main_60 / 1e8, 2),
            "consecutive_in": consecutive_in,
            "consecutive_out": consecutive_out,
            "large_order_pct": round(large_pct, 1),
            "direction": "流入" if main_20 > 0 else "流出",
        }

        return {"flow_data": rows, "stats": stats}
    except Exception as e:
        print(f"    资金流ERROR: {e}")
        return {"flow_data": [], "stats": None}


# ═══════════════════════════════════════════════════
# 新增模块 D: VPA 量价分析（集成 功能模块代码/量价分析 引擎）
# Anna Coulling方法论: 趋势 × 量价信号 × 资金流 三维评级
# ═══════════════════════════════════════════════════

# VPA导入（优雅降级）
VPA_AVAILABLE = False
try:
    from 量价分析.vpa_trend import analyze_trend as _vpa_trend
    from 量价分析.vpa_signals import analyze_signals as _vpa_signals
    from 量价分析.vpa_moneyflow import analyze_moneyflow as _vpa_mf
    from 量价分析.vpa_moneyflow import assess_flow_trend_resonance as _vpa_resonance
    VPA_AVAILABLE = True
except ImportError:
    pass


def analyze_volume_price_vpa(kline_df, moneyflow_rows=None, float_mv=0):
    """
    VPA三维量价分析: 趋势(40%) × 量价信号(30%) × 资金流(30%)

    输出:
        vpa_available: bool
        trend: {short_term, medium_term, alignment, phase, sr_levels}
        signals: {latest_bar, recent_signals, signal_summary}
        money_flow_vpa: {continuous_flow, flow_ratios, smart_retail, resonance}
        rating: {rating, score, trend_score, vpa_score, flow_score}
        simple: 简化版量价指标(兜底)
    """
    result = {
        "vpa_available": False,
        "trend": None, "signals": None, "money_flow_vpa": None,
        "rating": None, "simple": _simple_volume_price(kline_df),
    }

    if not VPA_AVAILABLE or kline_df is None or len(kline_df) < 20:
        return result

    try:
        df = kline_df.copy()
        for col in ['open', 'high', 'low', 'close', 'volume']:
            if col not in df.columns:
                return result

        # 1. 趋势分析
        trend = _vpa_trend(df)
        result["trend"] = {
            "short_term": {"direction": trend.get("short_term", {}).get("direction", ""),
                           "strength": trend.get("short_term", {}).get("strength", 50),
                           "summary": trend.get("short_term", {}).get("summary", "")},
            "medium_term": {"direction": trend.get("medium_term", {}).get("direction", ""),
                            "strength": trend.get("medium_term", {}).get("strength", 50),
                            "summary": trend.get("medium_term", {}).get("summary", "")},
            "alignment": {"state": trend.get("alignment", {}).get("alignment", ""),
                          "signal": trend.get("alignment", {}).get("signal", "")},
            "phase": {"phase": trend.get("phase", {}).get("phase", ""),
                      "description": str(trend.get("phase", {}).get("description", ""))},
            "sr_levels": {"support": trend.get("sr_levels", {}).get("support", []),
                          "resistance": trend.get("sr_levels", {}).get("resistance", [])},
        }

        # 2. 量价信号检测
        signals = _vpa_signals(df)
        recent = signals.get("recent_signals", [])
        recent = [s for s in recent if s.get("bar_index", 999) >= len(df) - 20]
        result["signals"] = {
            "latest_bar": {"volume_level": signals.get("latest_bar", {}).get("volume_level", ""),
                           "candle_pattern": signals.get("latest_bar", {}).get("candle_pattern", ""),
                           "is_anomaly": signals.get("latest_bar", {}).get("is_anomaly", False),
                           "anomaly_reason": signals.get("latest_bar", {}).get("anomaly_reason", "")},
            "recent_signals": [{"type": s.get("type", ""), "description": s.get("description", ""),
                                "strength": s.get("strength", ""), "date": str(s.get("date", ""))}
                               for s in recent[:8]],
            "signal_summary": signals.get("signal_summary", ""),
        }

        # 3. 资金流分析
        flow_trend = {"resonance": False, "signal_strength": 50, "summary": ""}
        if moneyflow_rows and len(moneyflow_rows) >= 10:
            try:
                mf_df = pd.DataFrame(moneyflow_rows)
                if 'main_net' in mf_df.columns:
                    mf_df['net_mf_amount'] = mf_df['main_net']
                    mf_result = _vpa_mf(mf_df, float_mv)
                    flow_trend = _vpa_resonance(trend, mf_result)
                    result["money_flow_vpa"] = {
                        "available": mf_result.get("available", False),
                        "continuous_flow": {
                            "direction": mf_result.get("continuous", {}).get("direction", ""),
                            "max_in": mf_result.get("continuous", {}).get("max_consecutive_in", 0),
                            "max_out": mf_result.get("continuous", {}).get("max_consecutive_out", 0)},
                        "smart_retail": {
                            "type": mf_result.get("smart_retail", {}).get("divergence_type", ""),
                            "desc": mf_result.get("smart_retail", {}).get("description", "")},
                        "resonance": flow_trend.get("resonance", False),
                        "resonance_type": flow_trend.get("resonance_type", ""),
                    }
            except Exception:
                pass

        # 4. 三维综合评级
        trend_dir = trend.get("short_term", {}).get("direction", "")
        trend_raw = trend.get("short_term", {}).get("strength", 50)
        t_score = trend_raw if trend_dir == "上涨" else (100 - trend_raw if trend_dir == "下跌" else 50)

        v_score = 50
        if recent:
            cont = sum(1 for s in recent if "趋势延续" in str(s.get("type", "")) or "趋势启动" in str(s.get("type", "")))
            exha = sum(1 for s in recent if "趋势衰竭" in str(s.get("type", "")))
            if cont > 0 and exha == 0: v_score = 80
            elif cont > exha: v_score = 65
            elif exha > cont: v_score = 30
            elif exha > 0: v_score = 20
        if signals.get("latest_bar", {}).get("is_anomaly"): v_score -= 15

        f_score = flow_trend.get("signal_strength", 50)
        overall = int(t_score * 0.40 + v_score * 0.30 + f_score * 0.30)

        rating_map = [(75, "趋势做多"), (55, "偏多"), (35, "观望"), (20, "偏空")]
        rating = next((r for threshold, r in rating_map if overall >= threshold), "持币/做空")

        result["rating"] = {"rating": rating, "score": overall,
                            "trend_score": t_score, "vpa_score": v_score, "flow_score": f_score}
        result["vpa_available"] = True

    except Exception:
        pass  # 降级到 simple

    return result


def _simple_volume_price(kline_df):
    """简化版量价指标（VPA不可用时兜底）"""
    if kline_df is None or len(kline_df) < 20:
        return None
    try:
        close = kline_df["close"].values
        volume = kline_df["volume"].values
        vol_5d = np.mean(volume[-5:]) if len(volume) >= 5 else np.mean(volume)
        vol_20d = np.mean(volume[-20:]) if len(volume) >= 20 else np.mean(volume)
        vol_ratio = vol_5d / vol_20d if vol_20d > 0 else 1.0
        surge = sum(1 for i in range(-min(20, len(close)-1), 0)
                    if volume[i] > vol_20d * 1.5 and close[i] > close[i-1])
        shrink = sum(1 for i in range(-min(20, len(close)-1), 0)
                     if volume[i] < vol_20d * 0.7 and close[i] < close[i-1])
        return {"vol_5d_avg": round(float(vol_5d), 0), "vol_20d_avg": round(float(vol_20d), 0),
                "vol_ratio_5v20": round(float(vol_ratio), 2),
                "vol_trend": "放量" if vol_ratio > 1.3 else ("缩量" if vol_ratio < 0.7 else "平稳"),
                "surge_up_days": surge, "shrink_down_days": shrink}
    except:
        return None


# ═══════════════════════════════════════════════════
# 主采集逻辑 — 已移至 run_v3_full.py
# 本文件仅供导入函数和常量
# ═══════════════════════════════════════════════════
