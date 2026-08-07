"""
深度分析脚本: 对9只A类科技股运行TG-trading-sys全部模块
输出: data/ deep_reports/ 目录下JSON + HTML
"""
import sys, os, io, json, time
os.environ['PYTHONIOENCODING'] = 'utf-8'
sys.path.insert(0, '.')
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import pandas as pd
import numpy as np
from datetime import datetime

# ═══════════════════════════════════════════════
# A-class stocks definition
# ═══════════════════════════════════════════════

A_STOCKS = [
    {"code": "300456", "name": "赛微电子", "sw2": "半导体-制造",
     "biz": "MEMS微机电系统芯片制造，全球领先的纯MEMS代工厂，覆盖加速度计/陀螺仪/压力传感器/硅麦克风等，客户包括意法半导体/博世/惠普等。瑞典产线(FAB1+2)+北京产线(FAB3)，8英寸MEMS量产线。",
     "comp": "全球MEMS代工CR3>70%（博世/意法半导体/Teledyne），公司通过并购Silex进入第一梯队，纯代工模式差异化竞争。国内竞争对手包括美泰科技/微电子所，公司在MEMS纯代工领域国内绝对龙头。",
     "edge": "1)全球稀缺的MEMS纯代工产能 2)瑞典Silex技术+中国产能双轮驱动 3)北京FAB3量产爬坡打开成长天花板 4)客户粘性极高（认证周期2-3年）",
     "plan": "北京FAB3产能从3000片/月→30000片/月，布局硅光子/生物医疗MEMS新品类，瑞典产线向12英寸升级",
     "risk": "下游消费电子周期波动、中美科技脱钩风险、产能爬坡不及预期"},
    {"code": "600288", "name": "大恒科技", "sw2": "元件-光学",
     "biz": "精密光学元件及系统，覆盖机器视觉/激光光学/太赫兹安检/数字放映等。子公司大恒光电在激光晶体和非线性晶体领域行业领先，太赫兹安检仪应用于轨道交通/法院等场景。",
     "comp": "光学元件行业格局分散，高端市场由舜宇光学/凤凰光学/日本腾龙主导。大恒在激光光学和太赫兹领域有差异化优势，太赫兹安检为稀缺A股标的。",
     "edge": "1)太赫兹技术稀缺性（A股唯一太赫兹安检标的）2)中科院光机所技术背景 3)机器视觉行业高景气（>20%增速）",
     "plan": "太赫兹安检仪从轨道交通向法院/医院拓展，激光光学向半导体设备配套延伸，机器视觉向3D检测升级",
     "risk": "太赫兹商业化进度不确定、光学元件竞争加剧、应收账款较大"},
    {"code": "688636", "name": "智明达", "sw2": "元件-军工电子",
     "biz": "军用嵌入式计算机系统，产品覆盖机载/弹载/舰载/车载嵌入式计算机及信号处理模块，核心客户为中航工业/中国电科/兵器集团等军工央企。",
     "comp": "军用嵌入式计算机行业进入壁垒极高（军工四证+型号定型周期5-10年），格局稳定。主要竞争对手包括雷科防务/景嘉微/中科海讯等。公司营收体量较小但绑定核心型号。",
     "edge": "1)军工嵌入式计算机完整资质 2)绑定多型重点型号（歼-XX/运-XX等）3)国产化率100%要求下的替代逻辑 4)型号定型后收入高度可预期",
     "plan": "从嵌入式计算机向综合任务系统升级，拓展无人机/智能弹药新领域，研发新一代VPX架构产品",
     "risk": "军品采购节奏不确定、型号定型延迟、单一客户依赖度较高"},
    {"code": "000733", "name": "振华科技", "sw2": "元件-被动元件",
     "biz": "军用电子元器件龙头，产品覆盖电阻/电容/电感/半导体分立器件/电源模块等，旗下振华新云（钽电容龙头）、振华微（厚膜混合IC）、振华富（MLCC）等子公司均为军工电子核心供应商。",
     "comp": "军工被动元件行业双寡头（振华科技+宏达电子），CR2>60%。民品市场格局分散但公司军工占比>80%，受民品周期影响小。",
     "edge": "1)军工电子元器件平台型公司 2)钽电容国内垄断地位(市占率>70%) 3)国产替代主 beneficiary 4)产品覆盖面最广的军工电子标的",
     "plan": "新型钽电容/高分子电容扩产，厚膜混合IC向系统级封装(SiP)升级，MLCC向高压/高频方向拓展",
     "risk": "军品降价压力、原材料(钽粉)进口依赖、民品业务拖累"},
    {"code": "688332", "name": "中科蓝讯", "sw2": "半导体-数字IC",
     "biz": "无线音频SoC芯片设计公司，产品覆盖TWS耳机/蓝牙音箱/智能手表/车载音频等。RISC-V架构芯片出货量国内第一，客户包括传音/QCY/漫步者/realme等品牌及白牌市场。",
     "comp": "TWS SoC市场格局：恒玄科技(中高端)/中科蓝讯(中低端放量)/杰理科技(白牌)。公司以性价比+快速放量策略抢占份额，2024年出货量超10亿颗。RISC-V路线差异化于ARM阵营。",
     "edge": "1)RISC-V架构先发优势(免ARM授权费) 2)出货量国内第一形成规模效应 3)从白牌向品牌升级(传音/realme等) 4)22nm→12nm制程演进降低功耗",
     "plan": "品牌客户渗透率提升(从30%→60%)，AI降噪/语音唤醒新功能迭代，智能手表/车载新品类拓展",
     "risk": "TWS市场饱和风险、价格战压缩毛利、RISC-V生态完善度不及ARM"},
    {"code": "301631", "name": "壹连科技", "sw2": "元件-连接器",
     "biz": "电连接器及线束组件制造商，产品应用于新能源汽车(高压连接器)/储能/工业控制/医疗设备等。新能源汽车连接器市场份额快速提升，进入比亚迪/宁德时代/特斯拉供应链。",
     "comp": "国内连接器市场格局：立讯精密(消费电子连接器龙头)/瑞可达(新能源连接器)/中航光电(军工连接器)。壹连科技聚焦新能源高压连接器细分赛道，成长性突出。",
     "edge": "1)新能源汽车高压连接器高景气(行业增速>30%) 2)进入头部客户(比亚迪/宁德/特斯拉) 3)从连接器向线束组件延伸提升单车价值 4)储能连接器第二增长曲线",
     "plan": "高压连接器产品线从400V向800V升级，储能连接器产能翻倍，工业/医疗连接器横向拓展",
     "risk": "新能源车销量波动、铜等原材料涨价、客户集中风险"},
    {"code": "301195", "name": "北路智控", "sw2": "软件-工业",
     "biz": "智能矿山工业软件及系统解决方案，产品覆盖煤矿智能化管控平台/精确定位系统/ AI视频分析/综合自动化等。背靠中煤科工集团，煤矿智能化政策驱动成长。",
     "comp": "煤矿智能化市场格局：北路智控(定位/通信)/梅安森(监测监控)/龙软科技(GIS系统)/科达自控(自动化)。公司在精确定位和智能管控平台领域技术领先。",
     "edge": "1)煤矿智能化政策强制推动(2026年大型煤矿全部实现智能化) 2)UWB精确定位技术领先 3)中煤科工集团产业背景 4)从煤矿向非煤矿山/化工园区拓展",
     "plan": "煤矿智能化覆盖率从30%→60%目标，AI+矿山大模型应用落地，化工园区安全管控平台新市场",
     "risk": "煤炭行业资本开支周期、政策推进不及预期、客户集中于大型煤矿"},
    {"code": "003019", "name": "宸展光电", "sw2": "元件-显示模组",
     "biz": "商用显示及触控一体机解决方案，产品覆盖POS/自助终端/数字标牌/智能健身镜/医疗显示等。ODM+自有品牌双轮驱动，客户包括NCR/Diebold/富士通等全球头部POS厂商。",
     "comp": "全球商用显示市场分散，POS终端市场CR3约40%(NCR/Diebold/Toshiba)。公司以ODM模式切入全球供应链，同时培育自有品牌(3R系列)提升毛利率。",
     "edge": "1)全球POS ODM龙头地位(市占率约15%) 2)智能健身镜/医疗显示等新品类放量 3)自有品牌提升毛利率(从20%→30%) 4)在东南亚/印度等新兴市场布局",
     "plan": "自有品牌收入占比从15%→30%，医疗显示认证推进，东南亚制造基地降低关税风险",
     "risk": "POS市场电子化替代风险、ODM毛利率天花板、海外关税政策不确定"},
    {"code": "000551", "name": "创元科技", "sw2": "机械-环保",
     "biz": "环保设备+精密制造双主业。环保板块：垃圾焚烧/危废处理/水处理设备(中环环保)。精密制造：超高压液压件/精密轴承/光学镜头(苏州轴承厂/创元光电)。",
     "comp": "环保设备行业高度分散，公司在垃圾焚烧和危废处理设备细分领域有一定优势。精密制造板块竞争激烈但技术壁垒较高。",
     "edge": "1)双主业分散风险 2)精密轴承国产替代逻辑 3)环保设备受益于无废城市建设 4)国企改革预期(苏州国资旗下)",
     "plan": "环保设备从垃圾焚烧向危废/固废全产业链延伸，精密制造向高端液压件/机器人关节升级",
     "risk": "环保补贴退坡、精密制造规模不经济、双主业协同效应有限"},
]

# ═══════════════════════════════════════════════
# Stage 1: Fetch all data
# ═══════════════════════════════════════════════

from TG_trading_sys.data.cache import DataCache
from TG_trading_sys.data.sync import SyncManager

cache = DataCache()

print(f'{"="*80}')
print(f'  A类科技成长股 — 全模块深度分析')
print(f'  日期: {datetime.now().strftime("%Y-%m-%d")} | 标的: {len(A_STOCKS)} 只')
print(f'{"="*80}')

all_reports = {}

for idx, stock in enumerate(A_STOCKS):
    code = stock['code']
    name = stock['name']
    sw2 = stock['sw2']
    print(f'\n[{idx+1}/{len(A_STOCKS)}] {code} {name} ({sw2})')

    report = {
        'code': code, 'name': name, 'sw2': sw2,
        'biz': stock['biz'], 'comp': stock['comp'], 'edge': stock['edge'],
        'plan': stock['plan'], 'risk': stock['risk'],
        'analysis_date': datetime.now().strftime('%Y-%m-%d'),
    }

    # --- 1. Basic Info & Price ---
    try:
        basic = cache.get_stock_basic(code, force_refresh=True)
        report['basic'] = {
            'price': basic.get('price', 0) if basic else 0,
            'pe_ttm': basic.get('pe_ttm', 0) if basic else 0,
            'pb': basic.get('pb', 0) if basic else 0,
            'mcap_yi': basic.get('mcap_yi', 0) if basic else 0,
            'turnover_pct': basic.get('turnover_pct', 0) if basic else 0,
            'last_close': basic.get('last_close', 0) if basic else 0,
        }
        print(f'  基本信息: 价格={report["basic"]["price"]:.2f} PE={report["basic"]["pe_ttm"]:.1f} PB={report["basic"]["pb"]:.2f}')
    except Exception as e:
        print(f'  基本信息: ERROR {e}')
        report['basic'] = {}

    # --- 2. K-line + Technical ---
    try:
        kline = cache.get_kline(code, lookback=250)
        if kline is not None and len(kline) >= 20:
            from TG_trading_sys.strategy.timing.ma_signals import analyze_ma_system
            from TG_trading_sys.strategy.timing.pattern_signals import detect_patterns
            from TG_trading_sys.strategy.timing.signal_aggregator import aggregate_signals

            ma = analyze_ma_system(kline)
            pat = detect_patterns(kline)
            verdict = aggregate_signals(ma, None, None, pat, None)

            report['technical'] = {
                'kline_rows': len(kline),
                'latest_close': float(kline['close'].iloc[-1]),
                'ma_score': ma.get('score', 50),
                'ma_verdict': ma.get('verdict', ''),
                'ma_alignment': ma.get('ma_alignment', {}).get('state', ''),
                'cross_signals': len(ma.get('cross_signals', [])),
                'patterns': [p['name'] for p in pat.get('patterns', [])] if pat.get('patterns') else [],
                'verdict': verdict.verdict,
                'verdict_score': verdict.score,
                'confidence': verdict.confidence,
                'position_advice': verdict.position_advice,
                'conflicts': verdict.conflicts,
            }
            print(f'  技术面: {verdict.verdict}({verdict.score}/100) 均线:{ma.get("score",50)}/100')
    except Exception as e:
        print(f'  技术面: ERROR {e}')
        report['technical'] = {}

    # --- 3. Valuation (DCF + Relative) ---
    try:
        from TG_trading_sys.valuation.val_report import val_report
        val = val_report(code)
        report['valuation'] = {
            'final_value': val.get('final_value'),
            'current_price': val.get('current_price', 0),
            'margin_of_safety_pct': val.get('margin_of_safety_pct'),
            'margin_verdict': val.get('margin_of_safety_verdict', ''),
            'dcf_per_share': val.get('dcf', {}).get('per_share_value'),
            'dcf_wacc': val.get('dcf', {}).get('wacc'),
            'dcf_terminal_g': val.get('dcf', {}).get('terminal_growth'),
            'dcf_tv_ratio': val.get('dcf', {}).get('terminal_value_ratio'),
            'peg_value': val.get('relative', {}).get('peg_value', {}),
            'pb_roe_value': val.get('relative', {}).get('pb_roe_value', {}),
            'scenarios': val.get('scenarios', {}),
            'earnings': val.get('earnings', {}),
        }
        mos = val.get('margin_of_safety_pct')
        print(f'  估值: 综合={val.get("final_value","N/A")} 安全边际={mos if mos else "N/A"}%')
    except Exception as e:
        print(f'  估值: ERROR {e}')
        report['valuation'] = {}

    # --- 4. Financial Data ---
    try:
        fin_data = {}
        for rt in ['lrb', 'fzb', 'llb']:
            data = cache.get_financials(code, report_type=rt, force_refresh=True)
            if data:
                fin_data[rt] = {
                    'reports': len(data),
                    'latest_period': data[0].get('report_date', '') if data else '',
                }
                # Extract key metrics
                if rt == 'lrb' and data:
                    from TG_trading_sys.valuation.wacc import _extract_number
                    fin_data['key_metrics'] = {
                        'revenue': _extract_number(data[0], '营业收入') or _extract_number(data[0], '营业总收入'),
                        'net_profit': _extract_number(data[0], '归属于母公司股东的净利润') or _extract_number(data[0], '净利润'),
                        'gross_margin': _extract_number(data[0], '毛利率'),
                    }
                if rt == 'fzb' and data:
                    from TG_trading_sys.valuation.wacc import _extract_number
                    fin_data['balance'] = {
                        'total_assets': _extract_number(data[0], '资产总计'),
                        'equity': _extract_number(data[0], '归属于母公司股东权益合计') or _extract_number(data[0], '所有者权益合计'),
                        'cash': _extract_number(data[0], '货币资金'),
                        'debt_ratio': None,
                    }
                    if fin_data['balance']['total_assets'] and fin_data['balance']['equity']:
                        fin_data['balance']['debt_ratio'] = round(
                            (1 - fin_data['balance']['equity'] / fin_data['balance']['total_assets']) * 100, 1)
        report['financials'] = fin_data
        print(f'  财务: LRB={fin_data.get("lrb",{}).get("reports",0)}期 FZB={fin_data.get("fzb",{}).get("reports",0)}期')
    except Exception as e:
        print(f'  财务: ERROR {e}')
        report['financials'] = {}

    # --- 5. Consensus EPS ---
    try:
        eps_data = cache.get_consensus_eps(code)
        if eps_data:
            report['consensus'] = {
                k: v for k, v in eps_data.items() if k != 'historical'
            }
            if eps_data.get('historical'):
                report['consensus']['hist_eps'] = eps_data['historical'][-3:] if len(eps_data['historical']) >= 3 else eps_data['historical']
            print(f'  一致预期: {report["consensus"]}')
        else:
            report['consensus'] = {}
    except Exception as e:
        report['consensus'] = {}

    # --- 6. WACC ---
    try:
        from TG_trading_sys.valuation.wacc import estimate_wacc
        wacc_data = estimate_wacc(code)
        report['wacc'] = {
            'wacc': wacc_data.get('wacc', 0),
            'ke': wacc_data.get('ke', 0),
            'beta': wacc_data.get('beta', 0),
            'kd': wacc_data.get('kd_after_tax', 0),
            'd_e_ratio': wacc_data.get('d_e_ratio', 0),
        }
    except Exception:
        report['wacc'] = {}

    # --- 7. Market Regime Context ---
    try:
        from TG_trading_sys.market.regime import detect_regime, MAJOR_INDICES
        idx_kline = cache.get_kline('000001', lookback=120)  # 上证指数
        if idx_kline is not None and len(idx_kline) >= 40:
            regime = detect_regime(idx_kline)
            report['market_regime'] = {
                'verdict': regime.get('verdict', ''),
                'score': regime.get('score', 0),
                'transition': regime.get('transition_signal', ''),
            }
    except Exception:
        report['market_regime'] = {}

    # --- 8. Risk Metrics ---
    try:
        from TG_trading_sys.risk.var import calc_var
        if kline is not None and len(kline) >= 60:
            returns = kline['close'].pct_change().dropna()
            var95 = calc_var(returns, method='historical', confidence=0.95)
            report['risk'] = {
                'var_95_pct': var95.get('var_pct', 0),
                'cvar_95_pct': var95.get('cvar', 0) * 100,
                'annual_vol': round(float(returns.std() * np.sqrt(252) * 100), 1),
            }
    except Exception:
        report['risk'] = {}

    all_reports[code] = report
    time.sleep(0.3)

# ═══════════════════════════════════════════════
# Save all reports as JSON
# ═══════════════════════════════════════════════

os.makedirs('data/deep_reports', exist_ok=True)
with open('data/deep_reports/all_reports.json', 'w', encoding='utf-8') as f:
    json.dump(all_reports, f, ensure_ascii=False, indent=2, default=str)

print(f'\n{"="*80}')
print(f'  数据采集完成！{len(all_reports)}/{len(A_STOCKS)} 份报告')
print(f'  已保存到 data/deep_reports/all_reports.json')
print(f'{"="*80}')
