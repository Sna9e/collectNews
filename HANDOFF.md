# HANDOFF.md

## 0J. 2026-06-18 更新：频道四 PWG Streamlit 前端入口上线验证

本次将已完成的 PWG 情报系统接入现有 Streamlit 前端，作为独立“频道四：PWG技术情报”。保持最小改动；没有修改频道一、频道二、频道三的处理链路，没有修改 `tools/search_engine.py` 接口行为，也没有把 PWG 输出混入原有 Word/PPT 报告状态机。

已完成：
- `agent_app.py`
  - 将首页 tab 从 3 个扩展为 4 个，新增 `🧪 频道四：PWG技术情报`。
  - 频道四调用现有 `pwg_intelligence.collector.collect_pwg_daily_scan()`，固定使用 Exa，不调用 Tavily。
  - 支持设置 query 数、每 query 结果数、回溯天数、报告日期和是否写入 `pwg_intelligence.xlsx`。
  - 支持一键执行 daily_scan 并生成日报/周报。
  - 支持基于最近 raw JSON 重新生成日报/周报，不重新消耗搜索额度。
  - 前端显示 Raw 结果数、过滤后数量、分类评分数量、人工复核数量和周报机会数。
  - 前端提供 Raw JSON、Raw Excel、PWG Excel、日报 Markdown、周报 Markdown 下载入口。
- `pwg_intelligence/reporter.py`
  - 报告层新增英文摘要中文化展示逻辑。原始 `factual_summary` 仍保留在 JSON/Excel 中，日报/周报展示时优先输出中文事实句。
  - 对英文摘要提取技术关键词和明确数字，例如 `Micro LED`、`CPO`、`USD 848 million`、`2030`，避免直接把英文 Exa 摘要原句写入中文报告。
- `PLANS.md`
  - 标记频道四前端入口和前端真实跑通完成。

本地真实前端验证：
- 启动临时 Streamlit：`http://127.0.0.1:8504`。
- 浏览器确认 `🧪 频道四：PWG技术情报` tab 可见，内容区、执行按钮和重建按钮可见，无导入错误。
- 前端按钮触发真实 Exa daily_scan：
  - query 数：10。
  - 每 query 结果数：6。
  - 回溯：7 天。
  - Raw 结果：60 条。
  - 过滤后：40 条。
  - 分类评分：34 条。
  - 人工复核：32 条。
- 前端重建报告按钮验证：
  - 可基于最近 raw JSON 重新生成日报和周报。
  - Raw/过滤/分类统计能正确回填，不再显示 0。

本次输出：
- `data/pwg_intelligence/raw/daily_scan_2026-06-18.json`
- `data/pwg_intelligence/raw/daily_scan_2026-06-18.xlsx`
- `data/pwg_intelligence/pwg_intelligence.xlsx`
- `data/pwg_intelligence/reports/PWG_daily_brief_2026-06-18.md`
- `data/pwg_intelligence/reports/PWG_weekly_review_2026-W25.md`

已执行验证：
- `python -m py_compile agent_app.py pwg_intelligence\reporter.py`
- `python -m py_compile agent_app.py pwg_intelligence\__init__.py pwg_intelligence\models.py pwg_intelligence\excel_store.py pwg_intelligence\collector.py pwg_intelligence\classifier.py pwg_intelligence\pwg_source_policy.py pwg_intelligence\pwg_scoring.py pwg_intelligence\reporter.py tools\pwg_query_packs.py`
- `python tests\test_pwg_intelligence_phase1.py`
- `python tests\test_pwg_query_packs.py`
- `python tests\test_pwg_collector.py`
- `python tests\test_pwg_phase4_rules.py`
- `python tests\test_pwg_reports.py`

验证说明：
- 本机未安装 `pytest`，因此按项目现有方式直接执行测试脚本。
- 本次前端入口没有调用 DeepSeek；DeepSeek 仍用于离线质量复核，不进入频道四前端 daily_scan 主流程。
- 本次没有调用 Tavily。

剩余风险：
- 当前 PWG 前端仍是第一版操作台，没有用户权限、历史批次对比和 Excel 增量合并。
- `pwg_intelligence.xlsx` 仍按现有写入逻辑重建 DEMO 骨架 + 本轮入选行，尚未实现历史正式数据增量合并。
- 报告中文化摘要是规则化展示，不是 LLM 翻译；复杂英文标题仍可能保留产品名、机构名和英文技术术语。

## 0I. 2026-06-09 更新：PWG 本地 Exa + DeepSeek 真实输出验证与改进

本次按要求使用本地 `.streamlit/secrets.toml` 中的 `EXA_API_KEY` 和 `DEEPSEEK_API_KEY` 做了一轮真实验证。没有打印或泄露密钥；没有修改频道一、频道二、频道三，也没有改 `tools/search_engine.py` 接口行为。

真实验证链路：
- Exa：执行 PWG `daily_scan`，`max_queries=10`，`results_per_query=6`，最近 7 天。
- Collector 输出：
  - `data/pwg_intelligence/raw/daily_scan_2026-06-09.json`
  - `data/pwg_intelligence/raw/daily_scan_2026-06-09.xlsx`
  - `data/pwg_intelligence/pwg_intelligence.xlsx`
- Reporter 输出：
  - `data/pwg_intelligence/reports/PWG_daily_brief_2026-06-09.md`
  - `data/pwg_intelligence/reports/PWG_weekly_review_2026-W24.md`
- DeepSeek：对日报和周报做 JSON 质量审查，审查结果保存：
  - `data/pwg_intelligence/reports/pwg_validation_2026-06-09.json`
  - `data/pwg_intelligence/reports/pwg_validation_after_fix_2026-06-09.json`
  - `data/pwg_intelligence/reports/pwg_validation_final_2026-06-09.json`

首轮结果：
- Exa raw result：60 条。
- 基础过滤后：35 条。
- 分类后：33 条。
- DeepSeek 首轮评价：`usable`。
- 主要问题：
  - 周报同一线索在多个章节重复。
  - 二手标准媒体被误判为 A 级原始信源。
  - 论文页被归入竞品动作，FPC 关系不准。
  - Hakusan 产品页摘要含网页导航噪声。

已按反馈改进：
- `pwg_intelligence/pwg_source_policy.py`
  - 收紧 A 级来源：标准、专利、论文只有命中原文/权威域名才判 A。
  - 将 `convergedigest.com` 作为专业媒体 C 级来源处理。
- `pwg_intelligence/classifier.py`
  - 增加论文域名/出版平台信号，例如 `link.springer.com`、`springer nature`、`PhotoniX`。
  - 增加 CPO 强规则：标题/摘要明确包含 `CPO`、`co-packaged optics`、`optical engine` 等时优先归入 `cpo_datacenter`，避免被 `fiber array` 误归为 connector。
- `pwg_intelligence/pwg_scoring.py`
  - 调整成熟度：普通 `mass production/量产` 归为 M6；只有 `stable/volume production/稳定量产/规模化生产` 才归为 M7。
- `pwg_intelligence/reporter.py`
  - 周报章节改为单条线索只进入一个分析章节，减少重复。
  - 日报高价值阈值从 55 调整为 50，仍过滤 D 级、DEMO、占位和低置信度线索。
  - 清理网页摘要噪声，如 `Internal Control Policy`、导航型 `Product - ...` 片段。
  - C 级来源在报告中显示为 `C（间接证据，需核实原始来源）`。
  - FPC 关系按分类补充验证关注点。

最终输出观察：
- 日报高价值线索：2 条。
  - Largan CPO / fiber array pilot line：C 级间接证据，M5。
  - Hakusan PMT / MT ferrule 产品页：A 级，公司产品页，M6。
- 周报入选重要线索：2 条。
- 周报机会行：2 条，已写入 `opportunities` 工作表。
- DeepSeek 最终评价：整体良好，但仍建议后续继续细化 FPC 关系和摘要完整度。

已执行验证：
- `python tests\test_pwg_intelligence_phase1.py`
- `python tests\test_pwg_query_packs.py`
- `python tests\test_pwg_collector.py`
- `python tests\test_pwg_phase4_rules.py`
- `python tests\test_pwg_reports.py`
- `python -m py_compile pwg_intelligence\__init__.py pwg_intelligence\models.py pwg_intelligence\excel_store.py pwg_intelligence\collector.py pwg_intelligence\classifier.py pwg_intelligence\pwg_source_policy.py pwg_intelligence\pwg_scoring.py pwg_intelligence\reporter.py tools\pwg_query_packs.py tests\test_pwg_intelligence_phase1.py tests\test_pwg_query_packs.py tests\test_pwg_collector.py tests\test_pwg_phase4_rules.py tests\test_pwg_reports.py`

剩余风险：
- 当前仍基于 Exa 返回摘要和页面片段，未接入 crawler 抓正文，摘要可能不完整。
- 周报/日报阈值和分类映射仍是 Python 规则，尚未 YAML 化。
- `pwg_intelligence.xlsx` 仍是 DEMO 骨架 + 本轮入选行重建，不做历史正式数据增量合并。

## 0H. 2026-06-09 更新：频道四 PWG 第五阶段日报和周报输出

本次继续保持频道四独立开发；没有修改 `agent_app.py`，没有修改频道一、频道二、频道三流程，也没有改 `tools/search_engine.py`。第五阶段新增 Markdown 报告输出和周报机会漏斗更新。

已完成：
- 新增 `pwg_intelligence/reporter.py`
  - 从第四阶段 raw JSON 的 `classified_rows` 生成报告。
  - 默认读取 `data/pwg_intelligence/raw/daily_scan_*.json`。
  - 不调用搜索 API，不调用大模型。
- 日报输出：
  - 文件名：`PWG_daily_brief_YYYY-MM-DD.md`
  - 默认输出目录：`data/pwg_intelligence/reports/`
  - 命令：
    - `python -m pwg_intelligence.reporter --mode daily --date 2026-06-09`
    - `python -m pwg_intelligence.reporter --mode daily --input-json data/pwg_intelligence/raw/daily_scan_2026-06-09.json --date 2026-06-09`
  - 只保留新增高价值线索，剔除 D 级来源、DEMO、低分、低置信度和占位/免责声明文本。
  - 分类输出：
    - 新产品与样品
    - 厂商动态
    - 车载应用
    - CPO与数据中心
    - 连接器与接口
    - 材料与工艺
    - 标准、专利与论文
  - 空分类直接省略。
- 周报输出：
  - 文件名：`PWG_weekly_review_YYYY-WXX.md`
  - 命令：
    - `python -m pwg_intelligence.reporter --mode weekly --date 2026-06-09`
    - `python -m pwg_intelligence.reporter --mode weekly --date 2026-06-09 --no-workbook`
  - 合并最近 7 天 raw JSON，去重后按机会评分、来源等级和时间排序，最多保留 20 条。
  - 包含：
    - 本周新增硬证据
    - 竞品动作
    - 应用机会变化
    - 技术路线变化
    - 值得验证的样件
    - 需要联系的厂商、供应商或高校
    - 仍然缺少的证据
- 更新 `pwg_intelligence/excel_store.py`
  - `create_pwg_intelligence_workbook()` 和 `write_pwg_intelligence_rows()` 支持 `extra_opportunity_rows`。
  - 周报默认生成机会漏斗行，并更新 `opportunities` 工作表。
- 新增 `data/pwg_intelligence/reports/.gitkeep`。
- 更新 `docs/PWG_INTELLIGENCE_GUIDE_CN.md`
  - 增加第五阶段日报、周报、命令和 opportunities 更新说明。
- 更新 `PLANS.md`
  - 标记第五阶段日报、周报和机会表更新完成。
- 新增 `tests/test_pwg_reports.py`
  - 验证日报过滤、去重、字段完整和空分类省略。
  - 验证日报文件名。
  - 验证周报 7 天窗口、去重、Top 20 和必需章节。
  - 验证周报机会行生成和 `opportunities` 写入。

已执行验证：
- `python tests\test_pwg_reports.py`
- `python -m py_compile pwg_intelligence\reporter.py pwg_intelligence\excel_store.py tests\test_pwg_reports.py`

待完成：
- 尚未用真实 Exa/Tavily 搜索结果生成日报/周报。
- 周报更新 Excel 当前仍是 DEMO 骨架 + 本轮入选行重建，不做历史正式数据增量合并；需要保留历史正式数据时应先备份旧 Excel。
- 尚未接入 Streamlit 频道四入口。
- 尚未把日报/周报阈值和分类映射迁移为 YAML 配置。

## 0G. 2026-06-09 更新：频道四 PWG 第四阶段分类、来源等级、成熟度和机会评分

本次继续保持频道四独立开发；没有修改 `agent_app.py`，没有修改频道一、频道二、频道三流程，也没有改 `tools/search_engine.py` 的既有行为。第四阶段只在 PWG 模块内增加规则分类、来源策略、成熟度判断和机会评分。

已完成：
- 新增 `pwg_intelligence/classifier.py`
  - 支持分类：`automotive`、`connector`、`cpo_datacenter`、`material_process`、`standard`、`patent`、`paper`、`exhibition`、`company_update`。
  - 输出 `classification_reason` 和匹配关键词。
- 新增 `pwg_intelligence/pwg_source_policy.py`
  - 自动标记来源等级 A-D。
  - A：标准原文、公司官网、Datasheet、论文原文、专利原文。
  - B：官方会议 PPT、协会材料、展会官方资料、公司访谈。
  - C：专业媒体、行业研报和普通专业来源。
  - D：转载、自媒体、聚合站、内容不完整来源。
  - 输出 `source_level_reason`。
- 新增 `pwg_intelligence/pwg_scoring.py`
  - 自动判断成熟度 M0-M7。
  - 明确限制：论文最高 M1、专利最高 M2、概念图/概念材料不得直接判断为量产。
  - 计算 100 分机会评分：
    - 客户痛点 30
    - FPC能力匹配 25
    - 公开产品证据 20
    - 技术可实现性 15
    - 竞争可进入性 10
  - 输出 `scoring_reason`。
- 更新 `pwg_intelligence/collector.py`
  - raw 结果通过基础过滤后，进入分类、来源等级、成熟度和机会评分。
  - 默认丢弃 D 级来源；如果整批没有 A-C 来源，则保留 D 级作为低可信线索，并强制 `needs_manual_review=true`。
  - JSON 输出新增：
    - `classified_rows`
    - `rule_coverage`
    - `manual_review_list`
  - 默认将分类/评分后的保留结果写入 `data/pwg_intelligence/pwg_intelligence.xlsx`。
  - 新增 CLI：
    - `--workbook-path`
    - `--no-workbook`
    - `--drop-all-d`
- 更新 `pwg_intelligence/models.py` 和 `pwg_intelligence/excel_store.py`
  - `daily_intelligence` 新增字段：
    - `pwg_category`
    - `opportunity_score`
    - `scoring_reason`
    - `needs_manual_review`
    - `classification_reason`
    - `source_level_reason`
    - `maturity_reason`
  - 重新生成 `data/pwg_intelligence/pwg_intelligence.xlsx`，保留 DEMO 数据并包含第四阶段字段。
- 更新 `docs/PWG_INTELLIGENCE_GUIDE_CN.md`
  - 增加第四阶段分类、来源等级、成熟度、机会评分和人工复核说明。
- 更新 `PLANS.md`
  - 标记第四阶段规则分类、评分和主工作簿写入已完成。
- 新增 `tests/test_pwg_phase4_rules.py`
  - 覆盖九类分类。
  - 覆盖 A-D 来源等级。
  - 覆盖论文/专利/概念不能直接判量产。
  - 覆盖机会评分五个分项和 `scoring_reason`。
  - 覆盖 D 级默认丢弃和低可信 fallback。
  - 覆盖分类结果写入 `pwg_intelligence.xlsx`。

已执行验证：
- `python tests\test_pwg_phase4_rules.py`
- `python tests\test_pwg_collector.py`
- `python tests\test_pwg_intelligence_phase1.py`
- `python tests\test_pwg_query_packs.py`
- `python -m py_compile pwg_intelligence\classifier.py pwg_intelligence\pwg_source_policy.py pwg_intelligence\pwg_scoring.py pwg_intelligence\collector.py pwg_intelligence\excel_store.py pwg_intelligence\models.py tests\test_pwg_phase4_rules.py tests\test_pwg_collector.py`
- `python -m pwg_intelligence.collector --mode daily_scan --dry-run --max-queries 3`
- `python -m pwg_intelligence.excel_store`

待完成：
- 尚未执行真实 Exa/Tavily 搜索后的第四阶段入库验证。
- 尚未接入 crawler 获取正文，当前分类和评分基于标题、摘要、URL、来源名称和 query。
- 尚未把评分权重迁移为 YAML 配置。
- 尚未实现正式 Excel 增量 upsert；当前写入主工作簿会用 DEMO 骨架加本轮分类行重建工作簿。
- 尚未接入 Streamlit 频道四入口。

## 0F. 2026-06-09 更新：频道四 PWG 第三阶段每日搜索与原始结果入库

本次继续保持频道四独立开发；没有修改 `agent_app.py`，没有修改频道一、频道二、频道三流程，也没有改 `tools/search_engine.py` 的既有行为。第三阶段仅新增 PWG raw collector，复用现有 `search_web()`。

已完成：
- 新增 `pwg_intelligence/collector.py`
  - 当前支持 `daily_scan` 模式。
  - 默认 `lookback_days=7`，调用搜索时使用 `timelimit=w`，不是只看当天。
  - 默认输出目录：`data/pwg_intelligence/raw/`。
  - 输出 `daily_scan_YYYY-MM-DD.json` 和 `daily_scan_YYYY-MM-DD.xlsx`；若同日文件已存在且未传 `--overwrite`，自动追加时间后缀，避免覆盖上一轮原始结果。
  - 每条保留记录包含：`query`、`title`、`url`、`source_name`、`published_date`、`snippet`、`fetched_at`、`search_provider`。
  - 第一版不调用大模型，不生成长摘要，不写入 `daily_intelligence` 正式情报卡。
- 过滤逻辑：
  - URL 规范化：去除 fragment、常见 `utm_*`、`fbclid`、`gclid` 等 tracking 参数。
  - URL 去重。
  - 标题去重。
  - 域名去重：每个域名默认保留首条通过过滤的结果。
  - 时间过滤：默认保留最近 7 天结果，允许未来 6 小时容忍；缺少可解析发布时间的结果会被剔除。
  - 明显无关过滤：依据 PWG YAML 配置中的关键词、公司、应用场景、标准引用和 query token 判断。
- 命令行入口：
  - `python -m pwg_intelligence.collector --mode daily_scan`
  - `python -m pwg_intelligence.collector --mode daily_scan --dry-run --max-queries 5`
  - `--provider` 支持 `exa`、`tavily`、`hybrid`。
  - `--exa-key` 默认读取 `EXA_API_KEY`；`--tavily-key` 默认读取 `TAVILY_API_KEY`。
- 更新 `docs/PWG_INTELLIGENCE_GUIDE_CN.md`
  - 增加第三阶段运行命令、输出字段、过滤规则和注意事项。
- 更新 `PLANS.md`
  - 标记 PWG `daily_scan` raw collection、基础过滤、CLI 与 dry-run 已完成。
- 新增 `tests/test_pwg_collector.py`
  - 验证 URL 规范化。
  - 验证标题/域名/时间/无关结果过滤。
  - 验证 dry-run 不调用搜索函数。
  - 验证本地 fake search 可写出 JSON 和 XLSX，且字段完整。

已执行验证：
- `python tests\test_pwg_collector.py`
- `python -m pwg_intelligence.collector --mode daily_scan --dry-run --max-queries 3`
- `python -m py_compile pwg_intelligence\collector.py tools\pwg_query_packs.py pwg_intelligence\models.py pwg_intelligence\excel_store.py tests\test_pwg_collector.py tests\test_pwg_query_packs.py tests\test_pwg_intelligence_phase1.py`

待完成：
- 尚未执行真实 Exa/Tavily 搜索写入 raw 目录；本次只做本地 fake search 与 dry-run 验证。
- 尚未扩展到 `weekly_deep_scan`、`company_watch`、`standard_watch`、`patent_watch`、`paper_watch` 采集。
- 尚未接入 crawler 获取正文。
- 尚未实现 PWG 来源评分、机会评分、结构化抽取 agent、正式 Excel upsert 和 Streamlit 频道四入口。

## 0E. 2026-06-09 更新：频道四 PWG 第二阶段关键词矩阵、公司与应用配置

本次继续保持频道四独立开发；没有修改 `agent_app.py`，没有接入现有频道一、频道二、频道三流程，也没有改搜索引擎、PPT/Word 导出、金融补链或 `tools/report_linker.py`。

已完成：
- 新增三份面向非程序人员维护的 YAML 配置：
  - `pwg_intelligence/config/keywords.yaml`
    - 分类包含核心术语、接口与连接器、车载应用、数据中心与 CPO、材料与工艺。
    - 包含 `daily_scan`、`weekly_deep_scan`、`company_watch`、`standard_watch`、`patent_watch`、`paper_watch` 六种模式的 `query_templates`。
    - 包含 `placeholder_groups`，用于把模板占位符映射到关键词类别。
  - `pwg_intelligence/config/companies.yaml`
    - 覆盖 Hakusan、Sumitomo Bakelite、Sumitomo Electric、Yazaki、Molex、Amphenol、TE Connectivity、Aptiv、Leoni、Broadcom、Marvell。
    - 增加国内光模块、光器件、PCB、FPC、封装企业示例，包括中际旭创、新易盛、光迅科技、天孚通信、鹏鼎控股、东山精密、深南电路、沪电股份、胜宏科技、长电科技、通富微电、华天科技等。
  - `pwg_intelligence/config/application_map.yaml`
    - 覆盖车载 ECU 板边接口、Camera 输出链路、Display 链路、车载光线束分支节点、光模块内光路重排、PMT/MPO/MT 接口件、45 度微镜与 90 度转向、CPO 供光、PIC 到 FA 扇出、optical RDL、光电混合 FPC。
- 新增 `tools/pwg_query_packs.py`
  - 从 YAML 读取关键词、公司、应用场景和 query 模板。
  - 输出 `PWGQueryRecord` 查询记录。
  - 支持公司过滤和应用场景过滤。
  - 提供 CLI 示例输出：`python -m tools.pwg_query_packs --limit 5`。
- 更新 `docs/PWG_INTELLIGENCE_GUIDE_CN.md`
  - 增加第二阶段 YAML 配置、支持模式和维护说明。
- 更新 `PLANS.md`
  - 标记第二阶段关键词矩阵、公司配置、应用配置和 query pack 已完成。
- `requirements.txt` 增加 `pyyaml`，用于读取 YAML；本地环境已检测可用。
- 新增 `tests/test_pwg_query_packs.py`
  - 验证必需关键词、公司、应用场景存在。
  - 验证六种 query mode 均可生成查询。
  - 验证公司和应用过滤有效。
  - 验证临时修改 YAML 中的唯一关键词会进入生成 query，确保逻辑配置驱动而非关键词硬编码。

待执行/待完成：
- 尚未接入真实搜索 pipeline。
- 尚未实现 PWG 来源评分、机会评分、结构化抽取和 Excel 增量写入。
- 尚未接入 Streamlit 频道四 UI。

## 0D. 2026-06-09 更新：频道四 PWG 情报系统第一阶段数据模型和 Excel 骨架

本次按“独立模块、最小接入面”实现频道四第一阶段；没有修改频道一、频道二、频道三流程，没有改 `agent_app.py`、搜索引擎、PPT/Word 导出、金融补链或 `tools/report_linker.py`。

已完成：
- 新增 `pwg_intelligence/` 独立模块。
  - `models.py`：新增标准化情报卡模型 `PWGIntelligenceCard`。
  - `excel_store.py`：定义 Excel 工作表 schema、DEMO 演示数据和 `create_pwg_intelligence_workbook()`。
  - `__init__.py`：仅导出 PWG 模型常量，避免运行 Excel 生成模块时触发导入副作用。
- 新增 Excel 数据库骨架：
  - `data/pwg_intelligence/pwg_intelligence.xlsx`
  - 工作表：`daily_intelligence`、`companies`、`opportunities`、`standards`、`keyword_library`。
  - 每个工作表均包含 3-5 条 `DEMO` 演示数据。
  - `daily_intelligence` 包含 `card_id`、`published_date`、`event_date`、`collected_at`、`source_type`、`source_level`、`source_name`、`title`、`source_url`、`original_language`、`main_track`、`application_scene`、`keywords`、`factual_summary`、`key_parameters`、`maturity_level`、`evidence_strength`、`fpc_relevance`、`recommended_action`、`owner`、`next_review_date`、`demo_flag`。
- 新增中文字段指南：
  - `docs/PWG_INTELLIGENCE_GUIDE_CN.md`
  - 解释 daily_intelligence 字段、`M0-M7` 成熟度等级、`A-D` 来源等级，以及其余四个工作表用途。
- 新增 `PLANS.md`，记录频道四第一阶段完成项和后续阶段任务。
- `requirements.txt` 补充 `xlsxwriter`，用于生成 `.xlsx` 文件；本地环境已存在该库。
- 新增最小测试：
  - `tests/test_pwg_intelligence_phase1.py`
  - 使用标准库解析 `.xlsx` 内部 XML，不依赖 `pytest` 或 `openpyxl`。

已执行验证：
- `python -m pwg_intelligence.excel_store`
- `python -m py_compile pwg_intelligence\__init__.py pwg_intelligence\models.py pwg_intelligence\excel_store.py tests\test_pwg_intelligence_phase1.py`
- `python tests\test_pwg_intelligence_phase1.py`

验证结果：
- 新增测试 3 项通过：
  - `PWGIntelligenceCard` 接受合法 `source_level=A-D`、`maturity_level=M0-M7`，拒绝非法等级。
  - DEMO payload 覆盖五个工作表，且每个工作表 3-5 条 DEMO 数据。
  - 生成的 Excel 包含五个要求工作表、daily_intelligence 必需字段、DEMO 标记、合法来源等级和成熟度等级。

未完成：
- 尚未接入 Streamlit 频道四 UI。
- 尚未实现真实检索、PWG 来源评分、机会评分、增量写入和去重。
- 尚未执行真实 API 验证；第一阶段仅为模型与 Excel 骨架。

## 0C. 2026-06-09 更新：修复时间线免责声明摘要、来源质量门禁和详细新闻有效性

本次检查了新闻检索、来源排序、时间线摘要、详细新闻生成、标题二次审查和 Streamlit HTML 预览输出链路。页面整体结构保持不变，仅在核心时间线卡片中补充展示已有 `event_summary`。

根因：
- `agents/timeline_agent.py` 的英文材料兜底会生成“公开材料显示……该线索由某网站披露……材料没有提供足够细节……”这类免责声明模板。
- 详细新闻 `_supplement_news_from_blueprints()` 会为了达到数量下限，从事件主档和搜索摘要生成 fallback 长新闻，存在低信息量补齐风险。
- 公司搜索排序缺少统一来源质量判断，聚合站、低正文量页面和低阅读量页面没有在排序前被剔除。
- 标题二次审查只看标题相似度，中文成稿标题与英文原文标题不一致时，可能误删同 URL 的有效新闻。

已完成：
- `tools/search_engine.py`
  - 新增来源质量评估：优先官方/监管/主流媒体/成熟垂直媒体；排除低质量域名、明显聚合/SEO/转载噪声、无标题/无日期/正文不足、公开阅读量低于 100 的非原始信源。
  - 新增事件有效性校验：主体、动作、产品/功能/政策/业务变化三项至少满足两项。
  - 标题二次审查增加同 URL 通过逻辑：二次搜索命中原文 URL 且时间在窗口内时，不因中英文标题差异误删。
- `tools/company_query_packs.py`
  - 公司检索结果排序前接入来源质量门禁，并对官方/优先媒体加权。
- `agents/timeline_agent.py`
  - 删除免责声明式中文结构化兜底；材料不足时返回空摘要，并在最终时间线中剔除该事件。
  - 禁止 `event_summary` 出现“公开材料显示”“该线索由某网站披露”“材料没有提供足够细节”“暂不能确认更多参数”“时间线仅记录已披露动作”等模板句。
  - 摘要规则调整为 3-5 句、100-220 字自然中文新闻导语。
- `agents/deep_analyst.py`
  - 最终详细新闻输出前增加字段完整性、来源质量、事件三要素和免责声明摘要过滤。
  - 补充详细新闻时只使用高质量且内容足够的搜索结果；材料不足时不再用事件标题硬造长新闻。
  - Prompt 明确要求每条详细新闻包含标题、日期、来源、原文链接，并在【事件核心】开头提供 3-5 句自然中文导语。
- `agent_app.py`
  - Streamlit HTML 时间线卡片展示 `event_summary`；摘要为空时不显示占位。
  - 频道一详细新闻少于 2 条时在 warnings 中提示：“在设定时间范围内，未检索到足够多可核实且具有信息增量的高质量新闻。”
- `tools/export_ppt.py`
  - 移除频道一时间线空摘要占位，只有存在有效摘要时才展示摘要和原文链接。
- 测试更新：
  - 增加免责声明摘要被拒绝、短英文材料不生成摘要、低质量来源被剔除、同 URL 标题审查通过、最终详细新闻剔除免责声明条目的 stub 测试。

已执行验证：
- `python -m py_compile agent_app.py agents\timeline_agent.py agents\deep_analyst.py tools\search_engine.py tools\company_query_packs.py tools\export_ppt.py tools\export_word.py tools\report_linker.py`
- `python tests\test_channel1_timeline_summary.py`
- `python tests\test_channel1_news_cleanup_and_title_gate.py`
- `python tests\test_consumer_daily_validation.py`
- `python tests\test_consumer_daily_exa_breadth.py`
- `python tests\test_consumer_daily_channel1_pipeline.py`

真实 API 验证：
- 使用本地 `Exa + DeepSeek + Jina` 跑 Apple / Google / Tesla 精简频道一链路，未使用 Tavily。
- 输出文件：
  - `E:\Users\zwz10\PycharmProjects\collectNews\collectNews-main\validation_company_quality_real.json`
  - `E:\Users\zwz10\PycharmProjects\collectNews\collectNews-main\validation_company_quality_real.html`
- 结果：
  - Apple：时间线 8 条，详细新闻 3 条。
  - Google：时间线 8 条，详细新闻 2 条。
  - Tesla：时间线 8 条，详细新闻 4 条。
  - 自动抽查显示所有详细新闻均有 URL，摘要均未出现禁用免责声明模板。

风险点：
- 来源质量门禁比旧逻辑更严格，低质量来源不会再用于凑数量；极端情况下某主题详细新闻会少于 2 条，但会显示明确 warning。
- 标题二次审查仍保留时效窗口，旧闻和未来异常新闻不会因 URL 命中绕过时间过滤。

## 0B. 2026-06-05 更新：频道一核心时间线摘要扩展为 4-5 句短新闻

本次只优化频道一核心时间线 `event_summary` 的内容长度和完整度；不调用 Tavily，不使用真实 API Key，不修改频道二、频道三、详细新闻、金融补链、PPT 模板、`tools/report_linker.py`、搜索引擎配置或时间线分页规则。

根因：
- 上次修复后的 `event_summary` 目标仍是 50-100 字，`_trim_event_summary()` 默认只保留前两句。
- `_build_event_summary_from_result()` 的 fallback 也沿用短摘要截取逻辑，材料足够时仍会输出一两句话。
- PPT 展示层保留了旧的 100/118 字截断上限，导致即使上游生成更长摘要，也无法完整显示在频道一时间线页。

已完成：
- `agents/timeline_agent.py`
  - 将 `event_summary` 目标调整为 140-220 个中文字符，通常 4-5 个完整句子。
  - 更新 `EventDraft` / `TimelineEvent` 字段说明和 `build_event_blueprints()` prompt，要求摘要覆盖主体、动作、对象、关键细节和直接影响，只能基于输入搜索摘要生成，不得编造或使用空泛补句。
  - `_trim_event_summary()` 改为优先抽取 3-5 个清洗后的有效句子，不再简单截取前 50-100 字。
  - `_build_event_summary_from_result()` 在中文材料不足但存在英文材料时，生成中文结构化兜底描述，不直接复制短英文摘要；无可靠材料时仍使用“公开材料暂未披露更多细节，建议后续继续跟踪。”
  - `_event_summary_quality()` 按 140-220 字和 4-5 句优先级重新评分，重复事件合并时更倾向保留完整短新闻。
- `tools/export_ppt.py`
  - 仅放宽频道一 `event_summary` 的展示截断上限，保留原有摘要位置、字体 Pt(10)、深灰色、每页最多 3 条和 `↳ 详见后文：《标题》` 格式。
- `tests/test_channel1_timeline_summary.py`
  - Apple stub 摘要更新为 140-220 字、4-5 句。
  - 自动检查正常摘要为中文、4-5 句、140-220 字，不出现空泛补丁句或短英文残句。
  - 继续检查 4 条时间线拆为 2 页、每页最多 3 条、空摘要 fallback、长 `match_reason` 不展示，并增加基于文本行数的无明显溢出检查。

已执行验证：
- `python tests\test_channel1_timeline_summary.py`
- `python -m py_compile agent_app.py agents\timeline_agent.py tools\export_ppt.py tools\export_word.py tools\report_linker.py`
- `python tests\test_channel1_news_cleanup_and_title_gate.py`

验证输出：
- 本地 stub PPT：`E:\Users\zwz10\PycharmProjects\collectNews\collectNews-main\stub_validation_channel1_timeline_apple.pptx`
- 自动检查显示 Apple 时间线页为 2 页，第一页 3 条、第二页 1 条；正常摘要满足 140-220 字和 4-5 句要求。
- 本机未检测到 LibreOffice / soffice，未完成图片渲染检查；已完成 python-pptx 自动结构检查和文本行数溢出检查。

未完成：
- 本次按要求未执行真实 Exa / Tavily / DeepSeek API 验证。

## 0A. 2026-06-05 更新：修复频道一核心时间线 PPT 实际摘要缺失/英文摘要问题

本次只修复频道一核心时间线，不调用 Tavily，不使用真实 API Key，不修改频道二、频道三、详细新闻、金融补链、PPT 模板、`tools/report_linker.py` 匹配逻辑和搜索引擎配置。

根因：
- `build_event_blueprints()` 的原有 prompt 没有强制模型一次性生成 `event_summary`。
- `_rewrite_event_dicts()` 在绑定最佳搜索结果并更新标题、日期、来源、URL 时，会用搜索结果 fallback 覆盖已有摘要；当搜索结果是英文时，最终 PPT 可能显示很短英文原始片段。
- PPT 展示层虽然有摘要段落，但缺少对“短英文摘要/非中文摘要”的最后防线。

已完成：
- `agents/timeline_agent.py`
  - 在 `EventDraft` / `EventBlueprint` / `TimelineEvent` 中保留 `event_summary` 字段，描述统一为“50到100字中文短新闻摘要，说明主体、动作、对象和关键影响，不得编造。”
  - 在 `build_event_blueprints()` 的同一次 LLM prompt 中强制每条事件填写中文 `event_summary`，要求 50-100 字、基于输入摘要、不得复制英文、不得出现空泛补丁句。
  - `_rewrite_event_dicts()` 更新标题/日期/来源/URL 时不再覆盖已有合格中文摘要，只在缺失或 fallback 更好时替换。
  - `_merge_event_dict()` 合并重复事件时按中文程度和长度质量选择更好的摘要，不拼接两段摘要。
  - `_fallback_event_blueprints()` / `_finalize_event_blueprints()` / `generate_timeline()` 均保证 `event_summary` 不丢失；无可靠材料时使用“公开材料暂未披露更多细节，建议后续继续跟踪。”
- `tools/export_ppt.py`
  - 频道一核心时间线每条标题下方实际渲染摘要段落，字体 Pt(10)，深灰色。
  - 频道一时间线 `chunk_size` 为 3，每页最多 3 条。
  - 频道一关联详细新闻仅显示 `↳ 详见后文：《详细新闻标题》`，不再展示长 `match_reason`。
  - 展示层增加防御：非中文或很短英文片段不显示，改为诚实 fallback。
- `tests/test_channel1_timeline_summary.py`
  - 生成本地 Apple stub PPT：`stub_validation_channel1_timeline_apple.pptx`。
  - 自动检查 Apple 核心时间线页存在、4 条事件拆分为 2 页、每页最多 3 条、标题下方有摘要、正常摘要为 50-100 字中文、摘要字体 Pt(10)/Pt(11)、不出现短英文片段、补丁句、长 `match_reason`，空摘要显示诚实 fallback。
  - 增加 FakeAI stub，验证 `build_event_blueprints()` → `generate_timeline()` → `generate_ppt()` 字段完整透传，不调用 Tavily、不读取真实 API Key。

已执行验证：
- `python -m py_compile agent_app.py agents\timeline_agent.py tools\export_ppt.py tools\export_word.py tools\report_linker.py`
- `python tests\test_channel1_timeline_summary.py`
- `python tests\test_channel1_news_cleanup_and_title_gate.py`
- `python tests\test_consumer_daily_validation.py`
- `python tests\test_consumer_daily_exa_breadth.py`
- `python tests\test_consumer_daily_channel1_pipeline.py`

验证输出：
- 本地 stub PPT：`E:\Users\zwz10\PycharmProjects\collectNews\collectNews-main\stub_validation_channel1_timeline_apple.pptx`
- 本机未检测到 LibreOffice / soffice，未完成图片渲染检查；已完成 python-pptx 自动检查。

未完成：
- 本次按要求未执行真实 Exa / Tavily / DeepSeek API 验证。

## 0. 2026-06-04 更新：频道一核心时间线短摘要

本次只增强频道一核心时间线展示，目标是让每条时间线除短标题外，再带一段复用原始搜索结果生成的 50-100 字短新闻摘要；不新增搜索调用，不新增 LLM 调用，不修改频道二、频道三、详细新闻生成逻辑、PPT 模板/封面/金融页或 `tools/report_linker.py`。

已完成：
- `agent_app.py`
  - 仅在频道一公司追踪产出的 deep/timeline 数据中加入 `report_style="company_tracking"`，供导出层识别频道一时间线。
- `agents/timeline_agent.py`
  - `EventDraft` / `EventBlueprint` / `TimelineEvent` 增加 `event_summary` 字段。
  - 新增 `_clean_event_summary_text()`、`_build_event_summary_from_result()` 等摘要清洗与生成函数。
  - 在 `_rewrite_event_dicts()` 使用 `_find_best_result_for_event()` 找到的原始搜索结果生成摘要。
  - `_merge_event_dict()` 合并重复事件时保留更完整且非 fallback 的摘要，不拼接多段摘要。
  - 真实 Exa 验证时发现英文搜索摘要会原样进入中文时间线；已最小修正为：若摘要候选不含中文且事件标题已有中文，则跳过英文候选，退回中文事件标题/诚实 fallback；同时清理 `[...]` 片段噪声。
- `tools/export_ppt.py`
  - 仅对 `report_style="company_tracking"` 的频道一核心时间线，将每页事件数从 5 条改为 3 条。
  - 仅对频道一核心时间线增加独立短摘要段，空摘要显示“公开材料暂未披露更多细节。”。
  - 仅对频道一核心时间线，关联详细新闻时只显示 `↳ 详见后文：《详细新闻标题》`，不再展示长 `match_reason`。
- `tools/export_word.py`
  - Word 已有频道一核心时间线输出时，同步在事件标题下增加 `event_summary`。
- `tests/test_channel1_timeline_summary.py`
  - 覆盖正常摘要生成、网页噪声清理、补丁句删除、空材料 fallback、重复事件合并摘要保留、PPT 摘要展示、PPT 每页最多 3 条时间线、PPT 关联提示格式。

已执行验证：
- `python -m py_compile agent_app.py agents\timeline_agent.py tools\export_ppt.py tools\export_word.py tools\report_linker.py`
- `python tests\test_channel1_timeline_summary.py`
- 真实 `Exa + DeepSeek` 小规模频道一链路已通过，主题 `NVIDIA`，时间窗 `过去1个月`：
  - Exa 初始搜索 4 个查询，真实请求成功；
  - DeepSeek 生成事件主档和详细新闻；
  - 标题二次审查后导出 PPT/Word；
  - PPT 检查通过：频道一核心时间线每页最多 3 条、每条有摘要、关联提示为 `↳ 详见后文：《详细新闻标题》`。

未完成：
- `Tavily + DeepSeek` 真实链路未通过。当前 `.streamlit/secrets.toml` 中存在 `TAVILY_API_KEY` 字段，但 Tavily API 对该 key 返回 `401 Unauthorized: missing or invalid API key`；已用当前代码的 body `api_key` 方式和 Bearer header 方式分别探测，均返回 401。需要更换有效 Tavily key 后重跑。

风险点：
- `timeline_agent.py` 是频道一和频道二共用的事件主档模块，新增字段会随共用模型存在；导出展示通过频道一专用 `report_style="company_tracking"` 标记收紧，避免改动频道二、频道三可见输出。
- 摘要严格复用现有搜索结果，不调用 LLM 翻译或扩写；当原始材料是英文或信息极短时，摘要可能短于 50 字或保留原始语言片段。
- `PLANS.md` 在当前仓库中未找到，本次只读取并更新了 `HANDOFF.md`。

## 1. 当前目标

恢复日报主链稳定性：固定 Tavily 搜索与 DeepSeek 生成，修复信息跨章节乱窜、PPT 主图/封面与本次报告不匹配、核心时间线过短的问题。

## 2. 已完成内容

- 已确认跨章节乱窜的主要风险点在上游搜索结果和模型成稿输入，不在 `tools/report_linker.py` 的跨 topic 匹配；链接器当前只会连接相同 topic 的时间线和长新闻。
- 已在 `agent_app.py` 增加专题门禁：
  - 搜索结果进入事件主档前做 topic focus 过滤；
  - 核心时间线生成后做 topic focus 过滤；
  - 深度新闻生成并去重后做 topic focus 过滤；
  - 公司流门禁更严格，行业流门禁更宽。
- 已在 `tools/export_ppt.py` 修复模板旧页问题：
  - 加载 `template.pptx` 后删除模板内已有幻灯片；
  - 保留模板母版和布局；
  - 再生成本次日报封面、时间线页、金融页和深度新闻页。
- 已修正核心时间线过短问题：
  - 时间线专题门禁至少保留 7 条才会实际过滤，否则回退原时间线；
  - 事件主档生成后若不足 8 条，会从已召回 Tavily 搜索标题中补线；
  - 补线不额外调用 LLM，避免明显增加 token 使用量。
- 已执行源仓库语法检查，关键文件通过。
- 已执行 PPT 烟测，生成文件第一张幻灯片为《FPC-RD 科技资讯》，不再被旧模板页抢占。
- 已用 stub AI 做无 API 烟测，确认模型只返回 1 条事件时，最终事件主档可补到 8 条。

## 3. 未完成内容

- 尚未完成真实 Tavily + DeepSeek 端到端日报跑数。
- 阻塞真实跑数的原因：本地运行副本当前缺少实际 `.streamlit/secrets.toml`，当前 shell 环境也未检测到 `TAVILY_API_KEY` / `DEEPSEEK_API_KEY`。

## 4. 关键决定

- 当前不继续推进周报。
- 当前不整仓回退。
- 当前不恢复 Exa / Hybrid fallback。
- 串章先用轻量门禁控制，不引入额外 LLM 分类，以避免明显增加 token 成本。
- PPT 修复选择“清空模板旧页但保留母版布局”，而不是完全弃用模板。

## 5. 风险/禁区

- 不要声称已经完成真实日报端到端验证，除非密钥恢复后实际跑过。
- 不要把模板旧页重新保留在生成 PPT 前面，否则主图不匹配会复发。
- 不要把门禁改成过强的硬过滤，否则核心时间线可能再次变得过短。
- 不要删除 Tavily 标题补线；这是当前避免核心时间线过短的低 token 成本兜底。
- 不要重新接回周报入口、周报标题或主题总结页。
- 不要提交真实密钥、临时 PPT/Word、日志或缓存。

## 6. 相关文件

- `agent_app.py`
- `tools/export_ppt.py`
- `tools/report_linker.py`
- `tools/company_query_packs.py`
- `tools/intelligence_packs.py`
- `agents/timeline_agent.py`
- `PLANS.md`
- `HANDOFF.md`

## 7. 验证方式

- 已完成：
  - `python -m py_compile agent_app.py tools\export_ppt.py tools\report_linker.py agents\deep_analyst.py`
  - PPT 烟测确认第一张幻灯片文本为《FPC-RD 科技资讯》。
  - 已同步到 `E:\Users\zwz10\PycharmProjects\collectNewslocal`，四个关键文件哈希一致。
  - 已在本地运行副本执行 `py_compile`，关键文件通过。
  - 已在本地运行副本执行 Streamlit `AppTest`，无异常；页面 selectbox 为核心模型、回溯时间线、Tavily 搜索深度、Tavily 结果主题、Tavily 原文片段模式。
  - 已在本地运行副本执行 PPT 烟测，第一张幻灯片为《FPC-RD 科技资讯》。
  - 已用 stub AI 验证事件主档兜底补线：1 条模型事件 + 12 条搜索结果可输出 8 条事件。
- 待完成：
  - 密钥恢复后运行一次 `Google \ Nvidia` 或 `Nvidia \ Google` 日报；
  - 下载 PPT 检查：Apple/Google/Nvidia 核心时间线是否达到 7-8 条，Google/Nvidia 信息不跨章节乱窜，主图/封面与本次报告匹配，K 线图不压文字。

## 8. 下一步建议

1. 恢复 `collectNewslocal\.streamlit\secrets.toml` 后跑一次双公司日报。
2. 下载 PPT 后先看 Apple/Google/Nvidia 核心时间线是否仍过短，再看 Google/Nvidia 是否仍跨章节串章，最后看封面/主图是否仍被旧模板影响。
3. 如果仍有串章，优先检查被保留的 Tavily 原始结果标题和摘要，而不是先改 DeepSeek prompt。
