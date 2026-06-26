# PLANS.md

## 频道四：PWG 聚合物光波导技术与产品情报系统

### 第一阶段：数据模型和 Excel 骨架

- [x] 新建 `pwg_intelligence/` 独立模块，不接入频道一、频道二、频道三运行链路。
- [x] 新建标准化情报卡模型 `PWGIntelligenceCard`。
- [x] 约束 `maturity_level` 为 `M0-M7`。
- [x] 约束 `source_level` 为 `A-D`。
- [x] 生成 `data/pwg_intelligence/pwg_intelligence.xlsx`。
- [x] Excel 包含 `daily_intelligence`、`companies`、`opportunities`、`standards`、`keyword_library` 五个工作表。
- [x] 每个工作表填入 3-5 条 `DEMO` 演示数据。
- [x] 新建 `docs/PWG_INTELLIGENCE_GUIDE_CN.md`，解释字段含义、成熟度等级和来源等级。
- [x] 增加最小单元测试，验证模型约束、工作表结构、字段和演示数据标记。

### 后续阶段建议

- [x] 新建 PWG 专属关键词矩阵、重点公司和应用场景配置，覆盖产品、应用、专利、论文、标准、厂商动态和 FPC 机会。
- [x] 新建 `tools/pwg_query_packs.py`，从 YAML 生成 `daily_scan`、`weekly_deep_scan`、`company_watch`、`standard_watch`、`patent_watch`、`paper_watch` 查询包。
- [x] 新建 PWG `daily_scan` 原始检索 pipeline，复用底层 `search_web()`，默认最近 7 天，输出 JSON/XLSX 到 `data/pwg_intelligence/raw/`。
- [x] 增加 PWG raw collector 的 URL 规范化、标题去重、域名去重、时间过滤和明显无关过滤。
- [x] 增加 `python -m pwg_intelligence.collector --mode daily_scan` 命令行入口和 `--dry-run` 模式。
- [x] 新增 PWG 规则分类、来源等级、成熟度和机会评分模块。
- [x] 支持 `automotive`、`connector`、`cpo_datacenter`、`material_process`、`standard`、`patent`、`paper`、`exhibition`、`company_update` 分类。
- [x] 将分类和评分后的保留结果写入 `data/pwg_intelligence/pwg_intelligence.xlsx`，并输出规则覆盖率与人工复核清单。
- [x] 新增 PWG 日报输出 `PWG_daily_brief_YYYY-MM-DD.md`，按产品、厂商、车载、CPO、连接器、材料、标准/专利/论文分类。
- [x] 新增 PWG 周报输出 `PWG_weekly_review_YYYY-WXX.md`，合并最近 7 天线索、去重并保留 Top 10-20 重要项。
- [x] 周报生成机会漏斗行并更新 `opportunities` 工作表。
- [x] 使用本地 Exa + DeepSeek 完成一次真实输出验证，并按反馈修正规则分类、来源等级、摘要清理和周报去重。
- [ ] 扩展 PWG 检索 pipeline 到 `weekly_deep_scan`、`company_watch`、`standard_watch`、`patent_watch`、`paper_watch`。
- [ ] 接入 crawler 获取正文，但不复用频道新闻质量门禁。
- [ ] 将来源等级、成熟度和机会评分规则迁移为可配置策略文件，便于非程序人员调整权重。
- [ ] 新建 PWG 结构化抽取 agent，输出 Excel 可直接 upsert 的字段。
- [x] 在 `agent_app.py` 增加频道四独立入口，避免影响现有频道。
- [x] 通过 Streamlit 前端触发一次 PWG `daily_scan`，生成 raw JSON/XLSX、PWG Excel、日报和周报。
- [x] 报告层增加英文摘要中文化展示，避免日报/周报直接输出英文 Exa 摘要。
- [ ] 增加 Excel 历史正式数据增量合并/去重测试。

## 独立技术专题：应变片与机器人六轴力传感器

- [x] 新建 `strain_gauge_intelligence/` 独立模块，不并入 Apple、Google、Tesla 等日更公司主题。
- [x] 增加 `TECH_MODULES = ["应变片与机器人六轴力传感器"]`。
- [x] 新增配置化关键词、公司/机构、专利申请人和信源域名。
- [x] 新增 `tools/strain_gauge_query_packs.py`，从 YAML 生成新闻、专利、论文 query。
- [x] 新增 collector，复用现有 `search_web()`，并按新闻/专利/论文分别执行时间窗口扩展。
- [x] 新增数量校验：新闻至少 2 条、专利至少 3 条、论文至少 3 条；不足时保留模块并写明原因。
- [x] 新增 Markdown 专题报告输出。
- [x] 新增 Streamlit 独立 tab：`🧲 应变片/六轴力传感器专题`。
- [x] 新增 stub 测试，覆盖配置、数量校验、字段完整性和报告禁用语。
- [x] 使用本地 Exa 执行一次真实验证。
- [x] 收紧摘要和来源过滤：禁止免责声明式摘要，排除明显低质量/泛产品页，避免英文搜索片段直接进入报告正文。
- [ ] 专利检索接入稳定专利 API 或专利库解析器，解决普通搜索对专利条目召回不足的问题。
- [ ] 对新闻源增加更严格来源等级，降低聚合站、低质量站和泛机器人文章权重。
- [ ] 对论文条目增加作者/机构、实验指标和 DOI 抽取增强。
