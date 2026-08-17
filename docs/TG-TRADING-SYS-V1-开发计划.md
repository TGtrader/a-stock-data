# TG-TRADING-SYS-V1 开发计划

> **关联文档**：[设计文档](TG-TRADING-SYS-V1-设计文档.md)
> **最后更新**：2026-08-08

---

## 总览

| 阶段 | 名称 | 预估工期 | 核心交付 |
|------|------|---------|---------|
| **P0** | 基础设施搭建 | 2-3天 | 项目骨架/数据库/配置/行业映射 |
| **P1** | 数据基础层（L1+L2） | 5-7天 | 5个数据适配器 + 日度增量汇总管线 |
| **P2** | 分析计算层（L3七模块） | 15-20天 | stock_daily_snapshot + 7模块并行计算 |
| **P3** | 应用层 MVP（L4） | 10-15天 | 决策森林 + 趋势 + 国家队 + 缠论指数报告 |
| **P4** | 报告与交付 | 10-15天 | 静态HTML + 交互SPA + FastAPI后端 + PDF |

**总预估**：42-60天（全职），按业余开发节奏约 2-3 个月。

---

## P0：基础设施搭建（Day 1-3）

### 目标
项目骨架就绪，数据库建表，配置文件可用，行业映射入库。

### 任务清单

| # | 任务 | 产出文件 | 预估 |
|---|------|---------|------|
| 0.1 | 创建项目目录结构 | `TG-TRADING-SYS-V1/` 全部子目录 | 0.5h |
| 0.2 | 配置系统 | `config.yaml` + `config.py` 加载器 | 2h |
| 0.3 | 数据库初始化 | DDL 建表脚本 + `database.py` | 3h |
| 0.4 | 申万SW2021行业映射 | `l1_data/sw2021_loader.py` — 调用 `index_member_all` 全量拉取，存本地 JSON + SQLite | 3h |
| 0.5 | 日志系统 | 统一 logging 配置 | 1h |
| 0.6 | 调度器骨架 | `l3_analysis/scheduler.py` — 7模块编排框架 + 依赖图 | 3h |
| 0.7 | 单元测试骨架 | `tests/` + pytest 配置 | 1h |

### 依赖
- Tushare Token 可用（复用 V4.0 Config）
- Python 3.10+ 环境已就绪

### 验收
- `config.yaml` 可加载
- `tg_trading_v1.db` 建表成功（`stock_daily_snapshot` + `valuation_detail` + `industry_valuation`）
- SW2021 三级行业数据入库，任意股票可查到 L1/L2/L3

---

## P1：数据基础层 L1 + L2（Day 4-10）

### 目标
所有原始数据源适配完成，日度增量汇总管线跑通。

### 任务清单

#### P1.1 L1 数据适配器

| # | 任务 | 产出 | 复用基础 | 预估 |
|---|------|------|---------|------|
| 1.1 | Tushare适配器 | `l1_data/adapters/tushare_adapter.py` | SKILL.md Tushare端点 + V4.0 cache.py | 5h |
| 1.2 | mootdx适配器 | `l1_data/adapters/mootdx_adapter.py` | SKILL.md mootdx端点 | 3h |
| 1.3 | 东财适配器 | `l1_data/adapters/eastmoney_adapter.py` | SKILL.md 东财端点（研报/龙虎榜/打板） | 4h |
| 1.4 | 同花顺适配器 | `l1_data/adapters/ths_adapter.py` | SKILL.md 一致预期端点 | 2h |
| 1.5 | 腾讯适配器 | `l1_data/adapters/tencent_adapter.py` | SKILL.md 实时行情端点 | 1h |

**适配器统一接口**：
```python
class BaseAdapter:
    def fetch(self, **params) -> pd.DataFrame: ...
    def cache_to_db(self, df: pd.DataFrame, table_name: str): ...
```

#### P1.2 L2 汇总管线

| # | 任务 | 产出 | 预估 |
|---|------|------|------|
| 1.6 | 日K线增量汇总 | `l2_aggregation/daily_aggregator.py` — 判断最近日期 → 拉新数据 → REPLACE INTO | 4h |
| 1.7 | 分钟K线汇总 | 同上流程，5min + 30min双级别 | 3h |
| 1.8 | 财报汇总（季度触发） | `l2_aggregation/financial_aggregator.py` — 检测最新财报期 → 自动拉取三表 | 4h |
| 1.9 | 研报汇总 | `l2_aggregation/research_aggregator.py` — 东财reportapi + 同花顺一致预期 | 3h |
| 1.10 | 资金流+融资融券汇总 | 集成到 `daily_aggregator.py` | 2h |
| 1.11 | 筹码数据汇总 | 集成到 `daily_aggregator.py`（Tushare cyq_perf + cyq_chips） | 2h |
| 1.12 | 打板数据汇总 | 集成到 `daily_aggregator.py` | 2h |
| 1.13 | 端到端管线测试 | 跑通一次完整的日度汇总流程 | 3h |

### 验收
- 5个适配器各自可独立拉取数据并写入数据库
- 日度汇总管线一次性跑通（`python -m l2_aggregation.daily_aggregator`）
- `daily_kline` `minute_kline` `financial_statements` `research_reports` `moneyflow_daily` `chip_perf_daily` 表均有最新交易日数据

---

## P2：分析计算层 L3（Day 11-30）

### 目标
七模块全部实现，`stock_daily_snapshot` 宽表每日自动填充。

### P2.1 估值模块（Day 11-14）

| # | 任务 | 产出 | 复用 | 预估 |
|---|------|------|------|------|
| 2.1.1 | 估值引擎包装 | `l3_analysis/valuation/valuation_calc.py` — 封装 V4.0 的 DCF/WACC/PEG/PB-ROE/研报共识为 L3 统一接口 | `TG_trading_sys/valuation/` | 6h |
| 2.1.2 | 综合估值计算 | 同上文件 — 4方法加权（有/无研报两种权重）+ 金融股/亏损股特殊处理 | - | 4h |
| 2.1.3 | 自历史估值分位 | 查询 `stock_daily_snapshot` 历史记录，计算当前估值在1Y/3Y分位 | - | 3h |
| 2.1.4 | 行业估值计算 | `l3_analysis/valuation/industry_val.py` — SW2021 L1/L2/L3 三层市值加权 | - | 5h |
| 2.1.5 | 增量更新逻辑 | 检测变化 → 局部重算（股价变/财报变/研报变） | - | 4h |
| 2.1.6 | 估值报告生成 | `l3_analysis/valuation/valuation_report.py` — 单票HTML + 行业汇总HTML | 复用 V4.0 val_report.py HTML模板 | 3h |

### P2.2 技术面模块（Day 15-17）

| # | 任务 | 产出 | 预估 |
|---|------|------|------|
| 2.2.1 | 技术指标批量计算 | `l3_analysis/technical/indicator_calc.py` — stockstats 封裝，全市场日频批量计算 → 写入 snapshot | 4h |
| 2.2.2 | 信号检测引擎 | `l3_analysis/technical/signal_detect.py` — 14种信号规则匹配 | 6h |
| 2.2.3 | 均线排列+距离 | 同上文件 — 多头/空头/缠绕判定 + MA偏离% | 2h |
| 2.2.4 | 因子扩展接口 | 预留从 vibe-trading Alpha Zoo 引入因子的接口 | 1h |

### P2.3 量价关系模块（Day 18-20）

| # | 任务 | 产出 | 复用 | 预估 |
|---|------|------|------|------|
| 2.3.1 | VPA多级别适配 | `l3_analysis/volume_price/vpa_runner.py` — 将日线VPA引擎适配到5min/30min，调整MA窗口参数 | `功能模块代码/量价分析/vpa_signals.py` `vpa_trend.py` | 8h |
| 2.3.2 | 量价特征提取 | `l3_analysis/volume_price/vp_features.py` — 三级背离/量价配合/异常检测 | 复用 `vpa_signals.py:detect_sequence_signals()` | 4h |
| 2.3.3 | VPA评分写入 | 三级VPA评分 → `stock_daily_snapshot` | - | 2h |
| 2.3.4 | VPA HTML报告（按需） | 复用 `vpa_render.py` 模板 | `vpa_render.py` | 2h |

### P2.4 资金流向模块（Day 21-24）

| # | 任务 | 产出 | 预估 |
|---|------|------|------|
| 2.4.1 | 四维资金分析 | `l3_analysis/money_flow/flow_four_dim.py` — 存量/流量/交易/进阶因子四维度计算 | 8h |
| 2.4.2 | 量化因子计算 | `l3_analysis/money_flow/flow_factors.py` — 主买特异性/虹吸效应/引力场 | 5h |
| 2.4.3 | 保险资金跟踪 | `l3_analysis/money_flow/insurance_tracker.py` — 前十大股东识别保险资金 + ETF持仓穿透 | 4h |
| 2.4.4 | 行业资金轮动 | 同上，按SW2021汇总行业级资金流 | 3h |
| 2.4.5 | 指数级资金流 | 同上，上证/深证/创业板/科创50/沪深300/中证500/中证1000级别 | 2h |

### P2.5 筹码分析模块（Day 25-26）

| # | 任务 | 产出 | 预估 |
|---|------|------|------|
| 2.5.1 | 筹码指标计算 | `l3_analysis/chip/chip_calc.py` — 从 `cyq_perf` 计算基础+衍生指标 | 4h |
| 2.5.2 | 筹码峰形态识别 | `l3_analysis/chip/chip_score.py` — 从 `cyq_chips` 直方图识别单峰/双峰/多峰 | 3h |
| 2.5.3 | 筹码评分 | 同上 — 0-10评分规则 | 2h |
| 2.5.4 | 筹码数据清理 | 60日滚动窗口，自动清理过期 `cyq_chips` 明细 | 1h |

### P2.6 市场情绪模块（Day 27-28）

| # | 任务 | 产出 | 预估 |
|---|------|------|------|
| 2.6.1 | 综合情绪指数 | `l3_analysis/sentiment/sentiment_index.py` — 12指标 Z-score 等权合成 | 5h |
| 2.6.2 | 分项指标明细 | `l3_analysis/sentiment/sentiment_detail.py` — 各分项独立记录 | 3h |
| 2.6.3 | 情绪写入快照 | 指数级情绪 → 指数快照表；个股继承所属板块情绪 | 2h |

### P2.7 缠论模块（Day 29-30）

| # | 任务 | 产出 | 预估 |
|---|------|------|------|
| 2.7.1 | 缠论批量运行器 | `l3_analysis/czsc_analysis/czsc_runner.py` — 全市场日线 + 流动性筛选30min/5min | 6h |
| 2.7.2 | 买卖点筛选 | `l3_analysis/czsc_analysis/czsc_buy_points.py` — 全部买卖点检测 + 背离识别 | 4h |
| 2.7.3 | 写入快照 | 指数缠论状态 + 个股买点/背离 → `stock_daily_snapshot` | 2h |

### P2.8 L3 调度器集成（Day 30）

| # | 任务 | 产出 | 预估 |
|---|------|------|------|
| 2.8.1 | 调度器完善 | `l3_analysis/scheduler.py` — 6模块并行（估值/技术面/量价/资金流/筹码/缠论）→ 情绪最后 | 3h |
| 2.8.2 | 端到端测试 | 完整运行一次每日L3计算 → 检查 `stock_daily_snapshot` 覆盖率 | 3h |

### 验收
- 7模块全部运行成功
- `stock_daily_snapshot` 所有字段非空率 > 95%（部分字段如研报覆盖天然为空）
- 完整运行一次 < 30分钟（L3总量~5000只股票）

### P2.9 消息舆情模块（Day 30-32）

| # | 任务 | 产出 | 复用 | 预估 |
|---|------|------|------|------|
| 2.9.1 | 新闻适配器 | `l1_data/adapters/news_adapter.py` — 封装5端点 | SKILL.md 新闻/舆情/公告层 | 3h |
| 2.9.2 | 新闻汇总 | `l2_aggregation/news_aggregator.py` — 去重入 `news_items` | - | 3h |
| 2.9.3 | 规则筛选打分 | `l3_analysis/news/news_calc.py` — 词典打分+标的匹配+影响度 | - | 6h |
| 2.9.4 | LLM精评 | `l3_analysis/news/news_llm.py` — 薄接口 `assess(news)` + provider适配 | - | 4h |
| 2.9.5 | 评估入库 | 写入 `news_assessment` 表 + 文本情绪指标 | - | 2h |

---

## P3：应用层 MVP L4（Day 31-45）

### P3.1 决策森林选股（Day 31-36）

| # | 任务 | 产出 | 预估 |
|---|------|------|------|
| 3.1.1 | 筛选器 | `l4_application/decision_forest/df_screener.py` — 5步筛选流程（ST/流动性/涨跌幅/因子打分/排序） | 6h |
| 3.1.2 | 打分引擎 | `l4_application/decision_forest/df_scorer.py` — 13因子加权评分 + 申万L1/L2行业中性化 | 6h |
| 3.1.3 | 权重配置 | `config/decision_forest_weights.yaml` — YAML可编辑权重 | 2h |
| 3.1.4 | 回测引擎 | `l4_application/decision_forest/df_backtest.py` — 基于历史 snapshot 的选股回测（复用 `scripts/slippage_model.py` 成本/滑点模型） | 8h |
| 3.1.5 | 参数优化 | `l4_application/decision_forest/df_optimizer.py` — 网格搜索/贝叶斯优化权重 | 6h |
| 3.1.6 | 选股报告 | `l4_application/decision_forest/df_report.py` — Top50 HTML 汇总表 + 单票详情 | 5h |

### P3.2 趋势分析（Day 37-39）

| # | 任务 | 产出 | 预估 |
|---|------|------|------|
| 3.2.1 | 趋势判定引擎 | `l4_application/trend/trend_analyzer.py` — 均线斜率法+高低点法，三级趋势判定 | 6h |
| 3.2.2 | 共振矩阵 | 同上 — 三级趋势共振判定（强共振多/空/分歧） | 3h |
| 3.2.3 | 趋势报告 | `l4_application/trend/trend_report.py` — HTML趋势矩阵表格 + 共振标注 | 4h |

### P3.3 国家队跟踪（Day 40-41）

| # | 任务 | 产出 | 预估 |
|---|------|------|------|
| 3.3.1 | 调度封装 | `l4_application/national_team/nt_scheduler.py` — 统一调度 national-team-position + Resonance | 3h |
| 3.3.2 | 信号汇总 | 同上 — 两系统信号统一写入 `national_team_signals` 表 | 2h |
| 3.3.3 | 仪表盘 | `l4_application/national_team/nt_dashboard.py` — HTML看板（ETF份额图表 + 信号状态） | 4h |

### P3.4 缠论指数报告（Day 42-43）

| # | 任务 | 产出 | 预估 |
|---|------|------|------|
| 3.4.1 | 指数日线缠论 | `l4_application/czsc_report/czsc_daily.py` — 7指数日线缠论分析 + 自然语言描述 | 5h |
| 3.4.2 | 走势示意图 | 使用 czsc `to_html()` 生成HTML图表 | 3h |

### P3.5 行业估值全景（Day 44-45）

| # | 任务 | 产出 | 预估 |
|---|------|------|------|
| 3.5.1 | 行业估值热力图 | `l4_application/industry_research/` — SW2021 L1/L2 行业PE/PB/综合估值横向对比 | 5h |
| 3.5.2 | 资金轮动图 | 行业资金流入流出排名 + 趋势图 | 4h |

### 验收
- `python -m l4_application.decision_forest.df_screener` 输出 Top50 选股列表
- 回测引擎可在历史数据上评估策略收益
- 7指数日线缠论报告可读
- 行业估值热力图可查看

### P3.6 消息预警与舆情参考（Day 45-47）

| # | 任务 | 产出 | 预估 |
|---|------|------|------|
| 3.6.1 | 持仓/板块预警 | `l4_application/news_alert/news_alert.py` — 分级预警 + `news_alerts` 表 | 4h |
| 3.6.2 | 市场要闻摘要 | `l4_application/news_alert/news_digest.py` — 每日摘要 HTML/JSON | 4h |
| 3.6.3 | 舆情参考视图 | 单票时间线 + 行业聚合（复用 7.5/7.6 报告组件） | 3h |

---

## P4：报告与交付（Day 46-60）

### P4.1 静态HTML报告系统（Day 46-50）

| # | 任务 | 产出 | 预估 |
|---|------|------|------|
| 4.1.1 | 报告模板系统 | `reports/templates/` — Jinja2 基础模板 + 通用组件（表格/图表/指标卡） | 8h |
| 4.1.2 | 每日综合报告 | 一键生成每日全套静态HTML（估值/技术/量价/资金/筹码/情绪/趋势总览） | 6h |
| 4.1.3 | PDF导出 | wkhtmltopdf 或 Calibre 将 HTML 转 PDF | 3h |
| 4.1.4 | 单票深度报告 | 按需生成单只股票的综合分析报告 | 4h |

### P4.2 交互SPA（Day 51-54）

| # | 任务 | 产出 | 预估 |
|---|------|------|------|
| 4.2.1 | 选股看板SPA | `reports/spa/` — Petite-Vue 单页应用：决策森林结果浏览/排序/筛选 | 8h |
| 4.2.2 | 持仓管理SPA | 同上 — 手动添加持仓/设止损止盈/仓位计划调整/笔记 | 8h |
| 4.2.3 | JSON数据API | 为SPA提供 `stock_daily_snapshot` JSON查询接口 | 4h |

### P4.3 后端Web服务（Day 55-60）

| # | 任务 | 产出 | 预估 |
|---|------|------|------|
| 4.3.1 | FastAPI后端 | `l4_application/web/` — RESTful API（选股/趋势/缠论/估值/行业） | 8h |
| 4.3.2 | React前端 | 参考 Resonance 架构，监控看板 + 历史回查 | 12h |
| 4.3.3 | 定时任务 | cron/scheduler 每日自动运行全管线 | 4h |

### 验收
- 每日 `python run_daily.py` → 全管线运行 → 生成全套 HTML 报告
- SPA 可浏览器打开，交互查看选股结果和管理持仓
- FastAPI 服务可启动，API 返回 JSON 数据

---

## P5：后续迭代（P4之后，持续）

| # | 功能 | 预估 |
|---|------|------|
| 5.1 | 深度财报分析（L4-7.5）— 杜邦分析/现金流质量/盈利质量 | 8h |
| 5.2 | 行业研究分析（L4-7.6）— 行业景气度/机构配置 | 8h |
| 5.3 | 更多技术因子（从 Alpha Zoo 引入） | 按需 |
| 5.4 | 分钟级实时监控（盘中信号） | 待评估 |
| 5.5 | 策略模拟交易（paper trading） | 待评估 |
| 5.6 | 通知推送（微信/钉钉/邮件） | 按需 |

---

## 依赖关系图

```
P0(基础设施) ──→ P1(数据层) ──→ P2(L3七模块) ──→ P3(L4应用) ──→ P4(报告交付)
                                      │
                                      ├─ 2.1 估值 ←── V4.0估值引擎
                                      ├─ 2.3 量价 ←── VPA引擎
                                      ├─ 2.4 资金 ←── Tushare moneyflow
                                      ├─ 2.5 筹码 ←── Tushare cyq系列
                                      └─ 2.7 缠论 ←── czsc库

P3应用层：
  3.1 决策森林 ─── 依赖 P2全部7模块
  3.2 趋势分析 ─── 依赖 P2.2技术面 + P2.3量价
  3.3 国家队 ──── 独立（复用 national-team-position + Resonance）
  3.4 缠论报告 ── 依赖 P2.7
  3.5 行业估值 ── 依赖 P2.1
```

---

## 风险与应对

| 风险 | 概率 | 应对 |
|------|------|------|
| Tushare 积分不足（部分API需更高级别） | 低 | 你5000+积分够用，cyq系列已验证；如有意外用降级方案（估算替代） |
| 东财API间歇风控 | 中 | SKILL.md 已内置限流+指数退避重试，沿用即可 |
| czsc DLL加载失败（Windows） | 低 | CLAUDE.md 已记录 VC++ Redistributable 修复方案 |
| mootdx 分钟K线数据缺失（部分小票无分钟线） | 中 | 自动跳过，标记为数据不可用 |
| 全市场计算耗时超预期 | 中 | 并行化（多进程）+ 只算流动性筛选股票，按需降级 |
| 筹码数据 cyq_chips 单次限制6000行 | 高 | 分批拉取（每只股票单独调用），注意限流 |

---

## 首日启动清单

按顺序执行：

1. **创建目录结构**（P0.1）
2. **config.yaml** — 确定 DB路径/数据源开关/Tushare Token
3. **数据库DDL** — 建表脚本跑通
4. **SW2021行业映射** — 拉取 `index_member_all`，验证几只股票可查到L1/L2/L3
5. **验证现有引擎可import** — 确保 V4.0 估值 + VPA + czsc 在当前环境正常加载
6. **第一个适配器** — 从 Tushare 适配器开始，跑通 fetch → cache → DB 流程

完成后进入 P1。
