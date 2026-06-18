# PWG 聚合物光波导技术与产品情报系统字段指南

本文档说明频道四第一阶段 Excel 数据库骨架和标准化情报卡字段。当前生成的工作簿位于：

`data/pwg_intelligence/pwg_intelligence.xlsx`

所有初始样例均为演示数据，字段中使用 `DEMO` 明确标识，不代表真实情报结论。

## 1. daily_intelligence：每日情报流水表

`daily_intelligence` 是频道四的主表，每一行对应一张标准化 `PWGIntelligenceCard`。

| 字段 | 含义 |
| --- | --- |
| card_id | 情报卡唯一编号。演示数据以 `DEMO-PWG-...` 开头；正式数据建议使用 `PWG-YYYYMMDD-序号`。 |
| published_date | 来源页面、论文、专利或标准文件的公开发布日期。 |
| event_date | 事件实际发生日期，例如产品发布、专利公开、论文发表、标准会议日期。 |
| collected_at | 系统采集时间，建议使用 ISO 时间格式。 |
| source_type | 来源类型，例如 `official`、`patent`、`paper`、`standard`、`media`、`market`。 |
| source_level | 来源可信等级，限定为 `A-D`。 |
| source_name | 来源名称，例如公司官网、Google Patents、IEEE、IEC、SPIE。 |
| title | 情报标题，正式数据应避免泛泛标题。 |
| source_url | 原始来源链接。 |
| original_language | 原文语言，例如 `zh`、`en`、`ja`、`de`。 |
| main_track | 主赛道，例如产品、应用、专利、论文、标准、厂商动态、机会。 |
| application_scene | 应用场景，例如 AR 眼镜、数据中心光互连、车载光互连、板级互连。 |
| keywords | 关键词，Excel 中用 `；` 分隔。 |
| factual_summary | 事实摘要，只写来源明确披露的信息，不补充未证实推测。 |
| key_parameters | 关键参数，例如损耗、波长、材料、工艺、尺寸、测试条件。Excel 中以 `key=value` 形式保存。 |
| maturity_level | 成熟度等级，限定为 `M0-M7`。 |
| evidence_strength | 证据强度，可用 `high`、`medium`、`low` 或中文说明。 |
| fpc_relevance | 与 FPC 厂商能力、工艺、客户或产品机会的相关性。 |
| recommended_action | 建议动作，例如持续跟踪、专利检索、样品拆解、客户访谈、工艺预研。 |
| owner | 内部负责人。 |
| next_review_date | 下一次复核日期。 |
| demo_flag | 演示数据标记。正式数据可留空。 |
| pwg_category | 第四阶段规则分类，例如 `automotive`、`connector`、`cpo_datacenter`。 |
| opportunity_score | 机会评分，满分 100 分。 |
| scoring_reason | 自动评分理由，保留五个分项和规则依据。 |
| needs_manual_review | 是否需要人工复核，低置信度、D 级来源或低分线索会标记为 `true`。 |
| classification_reason | 分类规则命中说明。 |
| source_level_reason | 来源等级规则命中说明。 |
| maturity_reason | 成熟度判断规则说明。 |

## 2. 成熟度等级 M0-M7

| 等级 | 建议含义 |
| --- | --- |
| M0 | 概念或需求线索，缺少可验证技术样例。 |
| M1 | 论文、实验室验证或早期专利阶段。 |
| M2 | 已有专利组合、样件描述或初步工程方案。 |
| M3 | 样件、demo 或小批量验证阶段。 |
| M4 | 客户验证、标准讨论或工程验证阶段。 |
| M5 | 小批量试产或特定客户导入阶段。 |
| M6 | 量产导入，供应链和工艺窗口基本清晰。 |
| M7 | 成熟规模化产品，已有稳定客户和明确竞争格局。 |

## 3. 来源等级 A-D

| 等级 | 建议含义 |
| --- | --- |
| A | 原始/权威信源：公司官网、官方博客、监管机构、专利局、标准组织、论文出版平台。 |
| B | 高质量专业信源：成熟专业媒体、会议材料、行业研究机构、可追溯作者的技术文章。 |
| C | 普通行业报道或二手整理，信息有参考价值但需要交叉验证。 |
| D | 低可信线索、社区转述、聚合页面或信息不完整页面。正式数据库原则上不应作为结论依据。 |

## 4. companies：竞品与供应链地图

记录 PWG 生态中的材料、波导制程、光机、模组、FPC、测试、终端客户等主体。第一版用于建立观察对象，不做真实排名。

## 5. opportunities：产品机会漏斗

记录 FPC 厂商可能切入的机会方向，包括目标应用、所需能力、PWG 关联、成熟度、优先级和下一步动作。

## 6. standards：标准跟踪表

记录标准组织、工作组、标准范围、状态和 PWG 相关性。第一版用于避免只看新闻而忽视标准和测试方法变化。

## 7. keyword_library：关键词库

维护中英文关键词、相关词、检索意图和优先级。后续频道四检索模块应优先从该表和 `pwg_intelligence` 模块中的关键词包派生查询。

## 8. 第二阶段配置文件

频道四第二阶段新增三份面向非程序人员的 YAML 配置文件。业务关键词、公司、应用场景和 Query 模板都应优先在 YAML 中维护，不应硬编码到 Python 逻辑里。

| 文件 | 用途 |
| --- | --- |
| `pwg_intelligence/config/keywords.yaml` | 维护关键词矩阵、占位符映射、扫描模式和 Query 模板。 |
| `pwg_intelligence/config/companies.yaml` | 维护重点公司、别名、区域、生态角色、优先级和 watch terms。 |
| `pwg_intelligence/config/application_map.yaml` | 维护应用场景、别名、标准引用、检索词和 FPC 机会说明。 |

当前支持的 Query 模式：

| 模式 | 用途 |
| --- | --- |
| `daily_scan` | 日常快速扫描产品、应用、公司和工艺动态。 |
| `weekly_deep_scan` | 周度深挖，组合技术路线、应用场景、公司和标准/专利线索。 |
| `company_watch` | 指定或默认重点公司监控。 |
| `standard_watch` | 标准、工作组和测试方法跟踪。 |
| `patent_watch` | 专利公开、同族专利和权利要求方向跟踪。 |
| `paper_watch` | 论文、会议、实验室研究和可靠性数据跟踪。 |

示例命令：

```bash
python -m tools.pwg_query_packs --limit 5
python -m tools.pwg_query_packs --mode company_watch --company Hakusan --limit 8
python -m tools.pwg_query_packs --mode daily_scan --application CPO供光 --limit 8
```

维护注意事项：

- 新增关键词时，优先放入 `keywords.yaml` 的合适类别。
- 新增公司时，放入 `companies.yaml` 的相应 group，并维护 `aliases` 与 `watch_terms`。
- 新增应用场景时，放入 `application_map.yaml`，并维护 `query_terms`、`standard_refs` 和 `fpc_opportunity`。
- 如果要改变 query 组合方式，优先修改 `keywords.yaml` 中的 `query_templates` 和 `mode_settings`。
- YAML 缩进建议使用 2 个空格，不使用制表符。

## 9. 第三阶段每日搜索与原始结果入库

第三阶段新增 `pwg_intelligence/collector.py`，用于执行 PWG `daily_scan` 检索并保存原始搜索结果。该模块复用现有 `tools/search_engine.py` 的 `search_web()`，不改动频道一、频道二、频道三的搜索流程。

默认规则：

- 当前仅支持 `daily_scan`。
- 默认搜索最近 7 天，对应搜索引擎 `timelimit=w`。
- 第一版不调用大模型，不生成长摘要。
- 输出目录为 `data/pwg_intelligence/raw/`。
- 首次运行输出 `daily_scan_YYYY-MM-DD.json` 和 `daily_scan_YYYY-MM-DD.xlsx`。
- 如果当天文件已存在且未使用 `--overwrite`，会自动追加时分秒后缀，避免覆盖上一轮原始结果。

命令示例：

```bash
python -m pwg_intelligence.collector --mode daily_scan
python -m pwg_intelligence.collector --mode daily_scan --provider exa --max-queries 24
python -m pwg_intelligence.collector --mode daily_scan --dry-run --max-queries 5
```

API Key 读取：

- `--provider` 支持 `exa`、`tavily`、`hybrid`。
- `--exa-key` 默认读取环境变量 `EXA_API_KEY`。
- `--tavily-key` 默认读取环境变量 `TAVILY_API_KEY`。
- `--dry-run` 只输出计划 Query，不访问搜索 API，也不写入 raw 文件。

原始结果字段：

| 字段 | 含义 |
| --- | --- |
| query | 触发该结果的 PWG 查询语句。 |
| title | 搜索结果标题。 |
| url | 规范化后的 URL，默认去除 fragment 和常见 tracking 参数。 |
| source_name | 来源名称，优先使用搜索结果 source，缺失时使用域名。 |
| published_date | 搜索结果可解析发布时间，保存为 UTC ISO 字符串。 |
| snippet | 搜索摘要或正文片段。 |
| fetched_at | 本轮采集时间，UTC ISO 字符串。 |
| search_provider | 搜索服务来源，例如 `exa` 或 `tavily`。 |

第一版过滤逻辑：

- URL 规范化与 URL 去重。
- 标题去重。
- 域名去重，每个域名默认只保留首条通过过滤的结果。
- 时间过滤，默认保留最近 7 天内结果，并容忍未来 6 小时的搜索时间误差。
- 明显无关结果过滤，依据 PWG YAML 配置中的关键词、公司、应用场景、标准和 query token 判断。

注意事项：

- 第三阶段输出仍是“原始搜索结果库”，不是最终情报卡。
- 结果进入 `daily_intelligence` 之前，还需要后续阶段的来源评分、机会评分、结构化抽取和人工/自动复核。
- 如果搜索 API 没有返回发布时间，当前版本会剔除该结果，因为无法完成 7 天窗口校验。

## 10. 第四阶段分类、来源等级、成熟度和机会评分

第四阶段新增三个规则模块：

| 文件 | 用途 |
| --- | --- |
| `pwg_intelligence/classifier.py` | 将结果归入 PWG 情报类别，并保留分类命中原因。 |
| `pwg_intelligence/pwg_source_policy.py` | 判断来源等级 A-D、来源类型和低可信信号。 |
| `pwg_intelligence/pwg_scoring.py` | 判断成熟度 M0-M7，并计算 100 分机会评分。 |

当前自动分类类别：

- `automotive`
- `connector`
- `cpo_datacenter`
- `material_process`
- `standard`
- `patent`
- `paper`
- `exhibition`
- `company_update`

来源等级规则：

| 等级 | 规则 |
| --- | --- |
| A | 标准原文、公司官网、Datasheet、论文原文、专利原文。 |
| B | 官方会议 PPT、协会材料、展会官方资料、公司访谈。 |
| C | 专业媒体、行业研报和普通专业来源。 |
| D | 转载、自媒体、聚合站、内容不完整来源。 |

默认处理：

- D 级来源默认不写入正式 `daily_intelligence`。
- 如果整批结果没有任何 A-C 来源，才允许 D 级结果作为“低可信线索”进入主表，并强制 `needs_manual_review=true`。
- 所有保留结果都会写入 `scoring_reason`。

成熟度规则：

| 等级 | 含义 |
| --- | --- |
| M0 | 概念。 |
| M1 | 论文验证。 |
| M2 | 专利布局。 |
| M3 | 实验室样件。 |
| M4 | 公司样品或 Datasheet。 |
| M5 | 联合开发或客户验证。 |
| M6 | 商业销售。 |
| M7 | 稳定量产。 |

限制规则：

- 论文来源最高按 M1 处理。
- 专利来源最高按 M2 处理。
- 概念图、路线图或概念材料不得直接判断为量产。

机会评分满分 100 分：

| 分项 | 分值 |
| --- | --- |
| 客户痛点 | 30 |
| FPC能力匹配 | 25 |
| 公开产品证据 | 20 |
| 技术可实现性 | 15 |
| 竞争可进入性 | 10 |

`python -m pwg_intelligence.collector --mode daily_scan` 现在会在完成 raw JSON/XLSX 后，把分类和评分后的保留结果写入 `data/pwg_intelligence/pwg_intelligence.xlsx`。JSON 输出中会包含：

- `rule_coverage`：规则覆盖率、分类分布、来源等级分布、成熟度分布。
- `manual_review_list`：需要人工复核的记录清单。

如果只想生成 raw 文件，不写入主工作簿：

```bash
python -m pwg_intelligence.collector --mode daily_scan --no-workbook
```

## 11. 第五阶段日报和周报输出

第五阶段新增 `pwg_intelligence/reporter.py`，基于第四阶段 `classified_rows` 生成 Markdown 报告。报告默认读取 `data/pwg_intelligence/raw/` 下的 `daily_scan_*.json`，不调用搜索 API，也不调用大模型。

输出目录：

`data/pwg_intelligence/reports/`

### 11.1 日报

日报文件名：

`PWG_daily_brief_YYYY-MM-DD.md`

生成命令：

```bash
python -m pwg_intelligence.reporter --mode daily --date 2026-06-09
python -m pwg_intelligence.reporter --mode daily --input-json data/pwg_intelligence/raw/daily_scan_2026-06-09.json --date 2026-06-09
```

日报规则：

- 只输出最近新增的高价值线索。
- 默认剔除 D 级来源、DEMO 数据、低分线索、需要人工复核但评分不足的线索。
- 对 URL、标题和摘要做去重。
- 没有有效信息的分类直接省略。
- 不输出空洞免责声明、占位文字或重复摘要。

日报分类顺序：

1. 新产品与样品
2. 厂商动态
3. 车载应用
4. CPO与数据中心
5. 连接器与接口
6. 材料与工艺
7. 标准、专利与论文

每条线索包含：

- 事实摘要
- 原文链接
- 来源等级
- 产品成熟度
- 与 FPC 的关系
- 下一步动作

### 11.2 周报

周报文件名：

`PWG_weekly_review_YYYY-WXX.md`

生成命令：

```bash
python -m pwg_intelligence.reporter --mode weekly --date 2026-06-09
python -m pwg_intelligence.reporter --mode weekly --date 2026-06-09 --no-workbook
```

周报规则：

- 汇总截至指定日期最近 7 天新增信息。
- 合并多个 `daily_scan_*.json`。
- 去重后按机会评分、来源等级和时间排序。
- 最多保留 20 条重要线索；如果有效线索不足 10 条，不使用低质量内容凑数。

周报包含：

- 本周新增硬证据
- 竞品动作
- 应用机会变化
- 技术路线变化
- 值得验证的样件
- 需要联系的厂商、供应商或高校
- 仍然缺少的证据

### 11.3 opportunities 工作表更新

周报默认会把本周高价值应用/产品线索转成机会漏斗行，并重写 `data/pwg_intelligence/pwg_intelligence.xlsx`：

- `daily_intelligence`：写入周报入选线索。
- `opportunities`：写入本周识别出的机会行。
- 其他工作表继续使用 DEMO 骨架数据。

当前仍是第一版工作簿写入逻辑：会用 DEMO 骨架 + 本轮入选行重建工作簿，不做历史增量合并。需要保留历史正式数据时，先备份旧版 Excel。

## 12. 本地真实验证记录

2026-06-09 已完成一轮本地真实验证：

- 使用本地 `.streamlit/secrets.toml` 中的 `EXA_API_KEY` 执行 `daily_scan`。
- 使用本地 `DEEPSEEK_API_KEY` 对日报和周报做结构化质量审查。
- 未打印或保存 API Key 明文。

验证输出：

| 文件 | 用途 |
| --- | --- |
| `data/pwg_intelligence/raw/daily_scan_2026-06-09.json` | Exa raw 结果、过滤统计、分类结果和规则覆盖率。 |
| `data/pwg_intelligence/raw/daily_scan_2026-06-09.xlsx` | 原始搜索结果 Excel。 |
| `data/pwg_intelligence/reports/PWG_daily_brief_2026-06-09.md` | PWG 日报。 |
| `data/pwg_intelligence/reports/PWG_weekly_review_2026-W24.md` | PWG 周报。 |
| `data/pwg_intelligence/reports/pwg_validation_2026-06-09.json` | DeepSeek 首轮质量反馈。 |
| `data/pwg_intelligence/reports/pwg_validation_after_fix_2026-06-09.json` | 规则修改后的复核反馈。 |
| `data/pwg_intelligence/reports/pwg_validation_final_2026-06-09.json` | 最终复核反馈。 |

本轮根据输出反馈做过的规则改进：

- 收紧 A 级来源判定，避免二手媒体报道被误判为标准/论文/专利原文。
- 增加 CPO 强分类规则，避免 `fiber array` 把 CPO 线索误归入连接器。
- 优化论文来源识别。
- 将周报章节改为单条线索只进入一个分析章节，减少重复。
- 清理网页导航型摘要噪声。
- C 级来源在报告中明确标注为“间接证据，需核实原始来源”。
- FPC 关系增加分类对应的验证关注点。
