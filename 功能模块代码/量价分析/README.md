# VPA 量价分析模块

基于**安娜·库林《量价分析：威科夫的盘口解读方法》**核心理论，结合 Tushare 资金流数据，为趋势交易者打造的三维量价分析系统。

## 架构

```
数据适配层 (vpa_data.py)
    OHLCV: mootdx(TCP)→Tushare→腾讯 三级降级
    资金流: Tushare moneyflow
    
    ↓
┌─────────────────────────────────────────┐
│  信号检测层    趋势分析层    资金流分析层    │
│  (vpa_signals) (vpa_trend) (vpa_moneyflow) │
│        ↓           ↓            ↓         │
│        综合研判引擎 (vpa_engine)            │
│        趋势×量价×资金流 三维评级             │
└─────────────────────────────────────────┘
    ↓
筛选层 (vpa_screener) + 报告层 (vpa_render)
```

## 快速开始

```python
from 量价分析 import vpa_analyze, vpa_screen, print_vpa_report

# 1. 单票三维分析
report = vpa_analyze("688017")
print_vpa_report(report)

# 2. 生成HTML报告
from 量价分析.vpa_render import generate_html_report
html = generate_html_report(report, "report_688017.html")

# 3. 三维筛选
results = vpa_screen(
    universe="csi300",
    trend_patterns=["trend_accel"],
    flow_patterns=["continuous_inflow_5d"],
    resonance_mode="all",
    top_n=10,
)
```

## CLI 使用

```bash
# 单票分析
python vpa_cli.py analyze 688017

# 多票对比
python vpa_cli.py compare 688017,300750,600519

# 最强做多信号筛选
python vpa_cli.py screen --mode best_buy

# 主力吸筹检测
python vpa_cli.py screen --mode smart_money

# 大盘指数
python vpa_cli.py index

# 行业板块
python vpa_cli.py sectors
```

## 核心API

### vpa_analyze(code, period="daily", lookback=120)
单标的完整三维量价分析，返回 `VpaReport` dict。

### vpa_compare(codes, period="daily", lookback=120)
多标的量价对比排名。

### vpa_screen(universe, trend_patterns, vpa_patterns, flow_patterns, resonance_mode)
三维条件筛选。

### vpa_screen_index()
六大指数量价状态。

### vpa_screen_sectors()
行业板块量价扫描。

## 数据源优先级

| 优先级 | 数据源 | 协议 | 封IP风险 | 用途 |
|--------|--------|------|---------|------|
| 1 | mootdx(通达信) | TCP | 不封 | K线首选 |
| 2 | Tushare | HTTP | 低 | K线备选+资金流 |
| 3 | 腾讯财经 | HTTP | 不封 | 实时估值 |
| 4 | 东财 | HTTP | 有风控 | 行业板块 |

Tushare token 自动从 `~/.vibe-trading/.env` 读取。

## 依赖

- Python 3.11+
- numpy, pandas
- mootdx (通达信TCP行情)
- tushare (资金流数据)
- requests (HTTP请求)

## 方法论来源

- 安娜·库林《量价分析：量价分析创始人威科夫的盘口解读方法》(A Complete Guide to Volume Price Analysis)
- 理查德·威科夫三定律（供求/因果/投入产出）
- 查尔斯·道三阶段趋势理论
- 杰西·利弗莫尔盘口解读方法
