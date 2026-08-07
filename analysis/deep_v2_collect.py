"""
V2 深度分析: 12只科技股数据采集
"""
import sys, os, io, json, time
os.environ['PYTHONIOENCODING'] = 'utf-8'
sys.path.insert(0, '.')
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from TG_trading_sys.data.cache import DataCache
from datetime import datetime
import numpy as np

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

cache = DataCache()
all_reports = {}

for idx, (code, name, sw2, biz, comp, edge, plan, risk) in enumerate(PICKS):
    print(f'[{idx+1}/{len(PICKS)}] {code} {name}')
    report = {
        'code': code, 'name': name, 'sw2': sw2,
        'biz': biz, 'comp': comp, 'edge': edge, 'plan': plan, 'risk': risk,
        'analysis_date': datetime.now().strftime('%Y-%m-%d'),
    }

    # Basic info
    try:
        basic = cache.get_stock_basic(code, force_refresh=True)
        report['basic'] = {
            'price': basic.get('price',0) if basic else 0,
            'pe_ttm': basic.get('pe_ttm',0) if basic else 0,
            'pb': basic.get('pb',0) if basic else 0,
            'mcap_yi': basic.get('mcap_yi',0) if basic else 0,
        }
    except Exception:
        report['basic'] = {}

    # K-line + Technical
    kline = None
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
                'ma_score': ma.get('score',50),
                'ma_verdict': ma.get('verdict',''),
                'ma_alignment': ma.get('ma_alignment',{}).get('state',''),
                'verdict': verdict.verdict,
                'verdict_score': verdict.score,
                'confidence': verdict.confidence,
                'position_advice': verdict.position_advice,
            }
    except Exception:
        report['technical'] = {}

    # Valuation (tech-style: PE-PEG 40%, PB-ROE 35%, DCF 10%, Research 15%)
    try:
        from TG_trading_sys.valuation.val_report import val_report
        val = val_report(code)
        report['valuation'] = {
            'final_value': val.get('final_value'),
            'current_price': val.get('current_price',0),
            'margin_of_safety_pct': val.get('margin_of_safety_pct'),
            'margin_verdict': val.get('margin_of_safety_verdict',''),
            'dcf_per_share': val.get('dcf',{}).get('per_share_value'),
            'peg_value': val.get('relative',{}).get('peg_value',{}),
            'pb_roe_value': val.get('relative',{}).get('pb_roe_value',{}),
            'scenarios': val.get('scenarios',{}),
            'earnings': val.get('earnings',{}),
        }
        print(f'  估值: 综合={val.get("final_value","N/A")} 安全边际={val.get("margin_of_safety_pct","N/A")}%')
    except Exception as e:
        print(f'  估值ERROR: {e}')
        report['valuation'] = {}

    # Financials (利润表 + 资产负债表关键指标)
    try:
        fin = {}
        from TG_trading_sys.valuation.wacc import _extract_number

        # 利润表 — 找最新年报(12-31)，无年报则取最近一期
        lrb_data = cache.get_financials(code, report_type='lrb', force_refresh=True)
        if lrb_data:
            fin['lrb'] = {'reports': len(lrb_data)}
            annual_lrb = None
            for rec in lrb_data:
                rp = str(rec.get('report_date', ''))
                if '12-31' in rp:
                    annual_lrb = rec
                    break
            if annual_lrb is None:
                annual_lrb = lrb_data[0]  # 兜底：最新一期
            fin['key_metrics'] = {
                'revenue': _extract_number(annual_lrb, '营业收入') or _extract_number(annual_lrb, '营业总收入'),
                'net_profit': _extract_number(annual_lrb, '归属于母公司股东的净利润') or _extract_number(annual_lrb, '净利润'),
                'report_period': annual_lrb.get('report_date', ''),
            }

        # 资产负债表 — 同样找最新年报
        fzb_data = cache.get_financials(code, report_type='fzb', force_refresh=True)
        if fzb_data:
            fin['fzb'] = {'reports': len(fzb_data)}
            annual_fzb = None
            for rec in fzb_data:
                rp = str(rec.get('report_date', ''))
                if '12-31' in rp:
                    annual_fzb = rec
                    break
            if annual_fzb is None:
                annual_fzb = fzb_data[0]
            total_assets = _extract_number(annual_fzb, '资产总计')
            equity = _extract_number(annual_fzb, '归属于母公司股东权益合计') or _extract_number(annual_fzb, '所有者权益合计')
            cash_val = _extract_number(annual_fzb, '货币资金')
            fin['balance'] = {
                'total_assets': total_assets,
                'equity': equity,
                'cash': cash_val,
                'debt_ratio': round((1 - equity / total_assets) * 100, 1) if (total_assets and equity and total_assets > 0) else None,
                'report_period': annual_fzb.get('report_date', ''),
            }

        # 现金流量表
        llb_data = cache.get_financials(code, report_type='llb', force_refresh=True)
        if llb_data:
            fin['llb'] = {'reports': len(llb_data)}

        report['financials'] = fin
        bal = fin.get('balance', {})
        km = fin.get('key_metrics', {})
        rev_yi = (km.get('revenue') or 0) / 10000
        ta_yi = (bal.get('total_assets') or 0) / 10000
        print(f'  财务 [{km.get("report_period","?")}]: 营收={rev_yi:.1f}亿 总资产={ta_yi:.1f}亿 负债率={bal.get("debt_ratio","N/A")}%')
    except Exception as e:
        print(f'  财务ERROR: {e}')
        import traceback; traceback.print_exc()
        report['financials'] = {}

    # Consensus EPS
    try:
        eps = cache.get_consensus_eps(code)
        if eps:
            report['consensus'] = {k:v for k,v in eps.items() if k != 'historical'}
            if eps.get('historical'):
                report['consensus']['hist_eps'] = eps['historical'][-3:]
    except Exception:
        report['consensus'] = {}

    # WACC + Risk
    try:
        from TG_trading_sys.valuation.wacc import estimate_wacc
        w = estimate_wacc(code)
        report['wacc'] = {'wacc': w.get('wacc',0), 'ke': w.get('ke',0), 'beta': w.get('beta',0)}
    except Exception:
        report['wacc'] = {}

    try:
        from TG_trading_sys.risk.var import calc_var
        if kline is not None and len(kline) >= 60:
            rets = kline['close'].pct_change().dropna()
            var95 = calc_var(rets, method='historical', confidence=0.95)
            report['risk'] = {
                'var_95_pct': var95.get('var_pct',0),
                'annual_vol': round(float(rets.std() * np.sqrt(252) * 100), 1),
            }
    except Exception:
        report['risk'] = {}

    all_reports[code] = report
    time.sleep(0.3)

import os as _os
_os.makedirs('data/deep_reports', exist_ok=True)
with open('data/deep_reports/all_reports_v2.json', 'w', encoding='utf-8') as f:
    json.dump(all_reports, f, ensure_ascii=False, indent=2, default=str)
print(f'\n完成 {len(all_reports)}/{len(PICKS)} 份报告')
