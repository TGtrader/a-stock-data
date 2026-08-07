# CLAUDE.md

## 数据源优先级
- **首选 Tushare Pro**（K线/PE/PB/市值/利润表/资产负债表/资金流/指数/两融）
- mootdx/腾讯 → 实时行情/盘口/分时（不封IP，Tushare 无分钟级数据时的补充）
- 东财 → 仅用于独有数据（龙虎榜/研报/大宗/股东户数/分红/打板/期权/舆情）
- 所有东财调用走 `em_get()`，内置 ≥1s 串行限流 + 随机抖动

## 环境
- Python: `/c/Python314/python`（Windows）
- 项目根: `D:/github/A-STOCK-DATA/a-stock-data`
- 核心依赖: `tushare mootdx requests pandas stockstats`，零数据封装中间层（无 akshare）
- 不加新依赖，除非用户明确要求

## 编码风格
- Ponytail full mode（hook 自动注入）：最短可用方案，stdlib 优先，不写未请求的抽象
- 修改 settings/permissions/hooks 前先提议，不直接改

## 项目结构
- `SKILL.md` — 主 Skill（A股全栈数据工具包，10层40端点）
- `TG_trading_sys/` — V4.0 投资决策系统（估值/因子/择时/组合/风控/大盘，9模块70+文件）
- `vibe-trading-repo/` — 交易 Agent 子项目（90+ Skill：技术分析/基本面/期权/加密货币/回测）
- `大盘及板块分析/` — 指数分析 + 板块个股排名（7文件1400行）
- `Resonance/` — ETF 国家队共振监控（同频：五指标共振信号 + FastAPI后端 + React前端 + CLI）
- `national-team-position/` — 国家队宽基 ETF 份额追踪 Skill（上交所6宽基 + AKShare）
- `scripts/` — 独立分析脚本目录（缠论、选股等单文件脚本放这里）

## 缠论分析 (czsc)
- **环境**：Python ≥ 3.10，依赖 `czsc>=0.10`（核心基于 Rust `rs-czsc`，用 PyPI 预编译包，不源码编译）
- **安装**：`pip install czsc -U`（如报 `ModuleNotFoundError` 自动执行）
- **若 `ImportError: DLL load failed`**：提示用户安装 [VC++ Redistributable](https://aka.ms/vs/17/release/vc_redist.x64.exe)

### 编码规范
- **禁止** `python -c "..."` 执行复杂缠论逻辑，必须写入 `scripts/` 目录独立 `.py` 文件后执行
- 执行后反馈 stdout/stderr，报错自动修正，最多重试 3 次
- 若生成了 HTML 图表，告知文件路径，不尝试在终端渲染

### Tushare Token
- 通过 `TG_trading_sys.core.config.Config.get_tushare_token()` 获取
- 或环境变量 `TUSHARE_TOKEN`

### 标准代码模板
```python
import sys
sys.path.append('.')
from czsc import CZSC, Freq, RawBar
from TG_trading_sys.core.config import Config
import tushare as ts

ts.set_token(Config.get_tushare_token())

# 数据获取后转换为 RawBar 列表
bars = [RawBar(symbol='000001', dt=row['trade_date'], open=row['open'],
               high=row['high'], low=row['low'], close=row['close'],
               vol=row['vol'], freq=Freq.D) for _, row in df.iterrows()]

cz = CZSC(bars)
print(f"标的: {cz.symbol}, K线: {len(cz.bars)}根, 笔: {len(cz.bi_list)}根")
if cz.bi_list:
    last_bi = cz.bi_list[-1]
    print(f"最新一笔方向: {'上涨' if last_bi.direction == 'up' else '下跌'}")

# 可视化: cz.to_html('output.html')
```