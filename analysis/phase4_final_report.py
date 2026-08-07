"""
Phase 4: 按申万二级子行业分类 + 精选输出
"""
import sys, os, io
os.environ['PYTHONIOENCODING'] = 'utf-8'
sys.path.insert(0, '.')
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import pandas as pd
import numpy as np

df = pd.read_csv('data/tech_deep_analysis.csv')
print(f'加载 {len(df)} 只分析结果')

# ═══════════════════════════════════════════════════════
# 申万二级子行业映射 (Tushare 证监会行业 → 申万二级)
# ═══════════════════════════════════════════════════════

SW2_MAPPING = {
    # 半导体 → 细分
    '688981': '半导体-晶圆代工',
    '002371': '半导体-设备', '688012': '半导体-设备',
    '002049': '半导体-数字IC', '603986': '半导体-数字IC', '603501': '半导体-数字IC',
    '688008': '半导体-数字IC', '300661': '半导体-模拟IC', '688536': '半导体-模拟IC',
    '688332': '半导体-数字IC', '688252': '半导体-数字IC', '688049': '半导体-数字IC',
    '688525': '半导体-存储', '301308': '半导体-存储', '001309': '半导体-存储',
    '600703': '半导体-化合物', '600360': '半导体-功率',
    '300456': '半导体-制造', '300303': '半导体-封装', '002185': '半导体-封装',
    '603160': '半导体-模拟IC',

    # 元器件 → 细分
    '000100': '元件-面板', '000725': '元件-面板',
    '002241': '元件-声学/光学', '000733': '元件-被动元件',
    '605058': '元件-PCB', '603328': '元件-PCB', '000823': '元件-PCB',
    '003019': '元件-显示模组', '001308': '元件-显示模组',
    '301631': '元件-连接器', '300389': '元件-LED', '600288': '元件-光学',
    '688636': '元件-军工电子', '920701': '元件-声学',

    # 软件服务 → 细分
    '688111': '软件-办公', '002410': '软件-垂直应用', '300674': '软件-金融IT',
    '300454': '软件-安全', '688561': '软件-安全', '002439': '软件-安全',
    '300033': '软件-金融IT', '301195': '软件-工业', '300532': '软件-物流',
    '300773': '软件-支付', '002322': '软件-电力',

    # 通信设备 → 细分
    '600522': '通信-光纤光缆', '000063': '通信-主设备',
    '300502': '通信-光模块', '300308': '通信-光模块', '688498': '通信-光芯片',
    '002296': '通信-轨交信号', '688080': '通信-工业物联网',
    '600498': '通信-设备',

    # IT设备
    '002415': 'IT设备-安防', '002236': 'IT设备-安防',

    # 互联网
    '002624': '互联网-游戏', '002555': '互联网-游戏', '300418': '互联网-平台',
    '300413': '互联网-视频', '603613': '互联网-产业电商',

    # 电气设备 → 细分
    '300750': '锂电池-龙头', '601012': '光伏-硅片', '002459': '光伏-组件',
    '300274': '光伏-逆变器', '688390': '光伏-逆变器',
    '601877': '电气-低压电器', '600089': '电气-变压器', '688819': '电气-电池',
    '601311': '电气-铅酸电池', '688330': '电气-配网', '002546': '电气-用电',
    '002533': '电气-电缆', '002249': '电气-电机', '300444': '电气-配电',
    '300443': '电气-风电铸件', '603218': '电气-风电铸件', '920011': '电气-微电机',

    # 专用机械 → 细分
    '300124': '机械-工控', '002747': '机械-机器人', '688017': '机械-机器人',
    '688169': '机械-家电', '601717': '机械-煤炭', '300724': '机械-光伏设备',
    '603611': '机械-物流装备', '002483': '机械-海工', '600582': '机械-煤炭',
    '600262': '机械-矿车', '002255': '机械-锅炉', '002073': '机械-橡胶',
    '920126': '机械-化工', '002204': '机械-重工', '000551': '机械-环保',

    # 电器仪表 → 细分
    '920029': '仪表-电表', '300360': '仪表-电表', '603556': '仪表-电表',
    '300349': '仪表-燃气表', '301303': '仪表-燃气表', '300259': '仪表-水表',

    # 医疗保健
    '300760': '医疗器械-龙头', '688271': '医疗器械-影像', '603987': '医疗器械-耗材',
    '600587': '医疗器械-消毒', '300358': '医疗器械-制药装备', '002432': '医疗器械-检测',
    '603102': '医疗-保健品',

    # 化学制药 + 生物制药
    '603259': '医药-CXO', '300759': '医药-CXO', '300122': '医药-疫苗',
    '002393': '医药-化药', '600062': '医药-化药', '600380': '医药-化药',
    '600216': '医药-维生素', '603367': '医药-化药', '600739': '医药-生物药',

    # 航空
    '600760': '军工-航空装备', '600893': '军工-发动机', '002025': '军工-航天电子',
    '002111': '军工-地面装备', '600765': '军工-航空锻件',
}

# Apply mapping
df['sw2_sector'] = df['symbol'].apply(lambda x: SW2_MAPPING.get(str(x).zfill(6), ''))
# For unmapped, use the 证监会 industry
df['sw2_sector'] = df.apply(lambda r: r['sw2_sector'] if r['sw2_sector'] else f'{r["industry"]}-其他', axis=1)

# ═══════════════════════════════════════════════════════
# 精选标准
# ═══════════════════════════════════════════════════════

# Score buckets
df['quality'] = 'C'
df.loc[(df['composite_final'] >= 75) & (df['pe_ttm'] < 40) & (df['mcap_yi'] > 20), 'quality'] = 'B'
df.loc[(df['composite_final'] >= 80) & (df['pe_ttm'] < 30) & (df['mcap_yi'] > 30), 'quality'] = 'A'
df.loc[(df['composite_final'] >= 85) & (df['pe_ttm'] < 20), 'quality'] = 'A+'

# ═══════════════════════════════════════════════════════
# 按申万二级分组输出
# ═══════════════════════════════════════════════════════

# Group by sw2_sector
grouped = df.groupby('sw2_sector', sort=False)

# Sort groups by their best stock
group_best = grouped['composite_final'].max().sort_values(ascending=False)

print(f'\n{"="*130}')
print(f'  A股科技成长板块 — 超跌/低估精选池')
print(f'  筛选日期: 2026-07-28 | 总候选: {len(df)} 只 | 覆盖 {len(grouped)} 个申万二级子行业')
print(f'{"="*130}')

for sector in group_best.index:
    subset = df[df['sw2_sector'] == sector].sort_values('composite_final', ascending=False)
    if len(subset) == 0:
        continue

    # Show top 3 per sub-sector, or all if quality A/A+
    top_n = min(3, len(subset))

    print(f'\n  ┌{"─"*126}┐')
    print(f'  │ {sector} ({len(subset)}只候选)')
    print(f'  ├{"─"*126}┤')

    for _, r in subset.head(top_n).iterrows():
        q = r['quality']
        q_icon = {'A+':'★★★','A':'★★','B':'★','C':' '}.get(q, ' ')

        # Signal description
        signals = []
        if r['rsi14'] < 30: signals.append(f'RSI={r["rsi14"]:.0f}(超卖)')
        if r['ret_20d'] < -10: signals.append(f'20日跌{r["ret_20d"]:.0f}%')
        if r['pct_from_60h'] < -20: signals.append(f'距60高{r["pct_from_60h"]:.0f}%')
        if r['pe_ttm'] < 15: signals.append(f'PE仅{r["pe_ttm"]:.1f}')
        if r['price_vs_ma20'] < -5: signals.append(f'破MA20({r["price_vs_ma20"]:.0f}%)')

        mcap_str = f'{r["mcap_yi"]:.0f}亿'

        print(f'  │ {q_icon} {r["symbol"]:<8} {r["name"]:<10}  '
              f'现价{r["close"]:>7.2f} | PE{r["pe_ttm"]:>5.1f} | PB{r["pb"]:>5.2f} | '
              f'市值{mcap_str:>8} | 综合{r["composite_final"]:>5.1f}分 | '
              f'{" | ".join(signals)}')

    print(f'  └{"─"*126}┘')

# ═══════════════════════════════════════════════════════
# A/A+ 级精选 TOP 15
# ═══════════════════════════════════════════════════════

print(f'\n\n{"="*130}')
print(f'  ★★★ A/A+ 级精选池 (深度低估 + 显著超跌 + 基本面扎实)')
print(f'{"="*130}')

top_quality = df[df['quality'].isin(['A+', 'A'])].sort_values('composite_final', ascending=False)
print(f'  {"#":<3} {"评级":<4} {"代码":<8} {"名称":<10} {"申万二级":<22} {"价格":>7} {"PE":>5} {"PB":>5} {"市值":>8} {"20日":>6} {"RSI":>4} {"综合":>5}')
print(f'  {"─"*110}')

for i, (_, r) in enumerate(top_quality.head(15).iterrows()):
    print(f'  {i+1:<3} {r["quality"]:<4} {r["symbol"]:<8} {r["name"]:<10} {r["sw2_sector"]:<22} '
          f'{r["close"]:>7.2f} {r["pe_ttm"]:>5.1f} {r["pb"]:>5.2f} {r["mcap_yi"]:>6.0f}亿 '
          f'{r["ret_20d"]:>+5.1f}% {r["rsi14"]:>4.0f} {r["composite_final"]:>5.1f}')

# ═══════════════════════════════════════════════════════
# Summary stats
# ═══════════════════════════════════════════════════════

print(f'\n\n{"="*130}')
print(f'  统计摘要')
print(f'{"="*130}')
print(f'  总分析标的: {len(df)} 只')
print(f'  A+级(极优): {len(df[df["quality"]=="A+"])} 只')
print(f'  A级(优秀):  {len(df[df["quality"]=="A"])} 只')
print(f'  B级(良好):  {len(df[df["quality"]=="B"])} 只')
print(f'  C级(候选):  {len(df[df["quality"]=="C"])} 只')
print(f'')
print(f'  行业覆盖: {len(grouped)} 个申万二级子行业')
print(f'  PE中位数: {df["pe_ttm"].median():.1f}')
print(f'  PB中位数: {df["pb"].median():.2f}')
print(f'  RSI<30(超卖): {len(df[df["rsi14"]<30])} 只')
print(f'  20日跌幅>20%: {len(df[df["ret_20d"]<-20])} 只')
print(f'  距60日高点>30%: {len(df[df["pct_from_60h"]<-30])} 只')
print(f'{"="*130}')

# Save final
final_cols = ['quality','symbol','name','sw2_sector','industry','close','pe_ttm','pb','mcap_yi',
              'turnover','ret_5d','ret_20d','price_vs_ma20','pct_from_60h','rsi14',
              'ma_score','value_score','oversold_score','composite_final']
df[final_cols].sort_values('composite_final', ascending=False).to_csv(
    'data/tech_final_picks.csv', index=False, encoding='utf-8-sig')
print(f'\n最终结果已保存到 data/tech_final_picks.csv')
