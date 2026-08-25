# PLANS.md

## 2026-08-24：永久信息源屏蔽、发布时间复核与金融链可靠性

- [x] 将前端信息源屏蔽拆分为“永久名单”和“本次运行临时名单”；永久名单支持直接增删后保存。
- [x] 永久名单采用 `data/source_blocklist.user.json` 原子写入，并在已配置 `GITHUB_TOKEN + GIST_ID` 时同步独立 Gist 文件；新 Streamlit 会话会自动恢复并建立本地镜像。
- [x] 将 `bitrss.com`、`dev.to`、`vocus.cc`、`jethrojeff.com` 加入内置硬屏蔽规则，搜索请求预排除和返回结果本地复检同时生效。
- [x] 增加发布时间多证据解析：网页 JSON-LD、`article:published_time` 等 meta、带标签的发布时间、URL 日期路径和供应商时间戳。
- [x] 时间证据冲突时优先采用网页/URL 原始证据；频道一过去 24 小时初筛对前 18 条候选并发抓取公开页面日期，最终标题二次审查继续复核。
- [x] 新增时间审查诊断：网页检查数、页面日期提取数、时间证据冲突数、仅供应商时间戳数及因冲突被剔除数。
- [x] 新增 `tools/finance_registry.json`，将公司上市状态、代码、交易所、币种和别名从 Python 硬编码迁出。
- [x] 将 SpaceX 登记为 `NASDAQ: SPCX`；OpenAI、Anthropic 保留为 `pending_listing`，正式代码未获交易所/监管确认前禁止模型猜测。
- [x] 金融行情链改为市场自适应多源：美股 `Yahoo Chart → Stooq → Tencent → yfinance`，A/H 股优先 Tencent；移除依赖 Cookie 的雪球运行路径。
- [x] 增加有限重试、15 分钟缓存、OHLCV 统一校验、供应商尝试诊断，以及 `mplfinance` 失败时的 Matplotlib 图表降级。
- [x] 修复 Yahoo `chartPreviousClose` 被误作上一交易日收盘价的问题；缺少 `previousClose` 时从日线倒数第二条严格计算日涨跌幅。
- [x] 真实公开行情验证：`SPCX` 由 `yahoo_chart` 返回 23 个交易日并生成有效 K 线图；金融 stub PPT 成功嵌入图片，渲染检查无越界。
- [x] 完成全量回归：16 个测试脚本、113 个测试函数全部通过，相关模块 `py_compile` 通过。
- [ ] 更新 Streamlit Secrets 中失效的 GitHub Gist 凭据；当前本地永久名单有效，但本机实测 Gist 同步返回 HTTP 401，云端跨重启持久化需凭据恢复后再确认。

## 频道一：参考 News-main_0818 的短新闻、长新闻对应与重点高亮优化

- [x] 只读扫描 `E:\Users\zwz10\PycharmProjects\News-main_0818\News-main` 全部文件，并对 24 个 Python 文件完成 AST/函数/类级静态审查；参考仓库与当前仓库的频道一核心文件经哈希比较没有可直接搬运的差异。
- [x] 将频道一默认追踪对象扩展并固定为 `Apple / Google / Amazon / OpenAI / Meta / Nvidia / Tesla / 特朗普 / Anthropic / SpaceX`。
- [x] 为十个主题分别补充产品、模型、硬件、供应链、政策或商业化关注点、重点信号、权威来源域名及中英文查询，不把内容要求散落到页面 Prompt。
- [x] 将短新闻摘要统一为自然中文 `3-4` 句、建议 `100-180` 字；fallback 从原始搜索内容中按事件相关性挑选句子，不再机械截取最前面的网页摘要。
- [x] 优化详细新闻 `event_id` 回填：规范化原文 URL 优先，可纠正模型返回的错误 ID；无 URL 时再使用事件语义评分。
- [x] 将短新闻到详细新闻的最终映射改为：同一规范化 URL → 经语义校验的 event_id → 一对一语义匹配，避免多个短新闻错误指向同一详细新闻。
- [x] 为每个详细新闻生成主题内编号，并透传 `matched_news_index`、`matched_news_importance`、`match_method` 与 `highlight_level`；内部 `match_reason` 继续保留供调试。
- [x] 频道一 PPT、Word 和 HTML 预览区分两级高亮：`importance >= 4` 为橙色重点新闻，普通已展开新闻为深蓝色；短新闻和详细页统一显示“详细新闻 N”，频道一不再展示长匹配原因和内部事件 ID。
- [x] 新增专项测试，覆盖十个主题内容包、相关句选择、URL 优先回填、一对一关联、编号以及橙/蓝两级 PPT 高亮。
- [x] 生成 `validation_outputs/channel1_reference_optimized_stub.pptx`，用 `python-pptx` 复查字段与颜色，并完成逐页图片渲染；`slides_test.py` 未发现页面越界。
- [x] 完成全量回归：14 个测试脚本、102 个测试函数通过，`compileall` 通过；Streamlit 完整重启后浏览器检查正常。
- [ ] 使用有效 Exa/OpenRouter Key 执行十主题真实频道一端到端验证，重点抽查模型 `importance` 分级、搜索结果质量和 URL 缺失场景；本次未读取真实 API Key。

## Streamlit Secrets 与 OpenRouter 单一前端

- [x] API Key 仅从 `st.secrets`、服务器环境变量或本地服务端配置读取，删除业务页面的 Key 输入和清除控件。
- [x] OpenRouter Base URL 固定为 `https://openrouter.ai/api/v1`，删除前端地址输入并忽略旧 `OPENROUTER_BASE_URL` 设置。
- [x] 删除 Gemini 主模型、轻任务模型、预设按钮和对应运行参数；当前 Streamlit 业务链只构建 OpenRouter 模型栈。
- [x] 删除前端 reasoning 设置，保留服务端默认/配置；前端只保留可搜索模型目录和自定义模型 ID。
- [x] 将 Gemini Key 与旧 OpenRouter Base URL 在本地配置脚本中降为禁用历史项，保留已有值但不参与运行。
- [x] 更新 README、静态安全回归和交接文档，并完成 Streamlit 浏览器验证。
- [x] 完成语法、专项和全量回归：13 个测试脚本、97 个测试函数通过；未调用真实模型 API。

## 全局垃圾与机器人网站屏蔽

- [x] 审查频道一、二、三、PWG、应变片专题的搜索入口、复搜路径、来源规则和 Streamlit 配置传递。
- [x] 新增独立 `tools/source_blocklist.json`，集中维护自动聚合、低可信转载入口和非正文平台，不把名单散落到各频道。
- [x] 新增域名规范化、完整 URL 解析、精确/子域名匹配和无效输入识别，避免字符串包含式误伤。
- [x] 增加机器人/AI 自动生成及 RSS 自动聚合强标记过滤。
- [x] Exa 使用 `excludeDomains`、Tavily 使用 `exclude_domains` 做请求前排除，并对所有返回结果执行本地二次门禁。
- [x] 增加可审计诊断：拦截总数、域名、类别、原因和标题样本。
- [x] Streamlit 侧栏增加永久/临时屏蔽网站输入、保存状态、内置名单预览和无效域名提示；规则覆盖当前五个频道及频道一标题二次搜索。
- [x] 支持 `NEWS_BLOCKED_DOMAINS` 持久设置和环境变量，`setup_api_keys.py` 可写入配置。
- [x] 增加专项测试并完成相关频道回归与前端浏览器检查。
- [ ] 根据实际运行诊断定期复核内置名单；只有站点整体属于自动聚合或低可信转载入口时才升级为永久硬屏蔽。

## OpenRouter 通用多模型适配

- [x] 联网核对 OpenRouter Models API、`supported_parameters`、结构化输出、reasoning 和 provider routing 官方规则。
- [x] 新增 `OpenRouterModelInfo` 标准模型元数据，记录模型 ID、名称、上下文、最大输出、输入/输出模态、支持参数和到期时间。
- [x] 通过 `/api/v1/models?output_modalities=text&sort=most-popular` 动态加载文本模型目录，不再将前端模型选择限制在 Qwen 预设。
- [x] 保留任意自定义模型 ID；模型目录不可用或自定义代理没有 `/models` 时，业务调用仍可继续。
- [x] 按 `supported_parameters` 自适应发送 `temperature`、`max_tokens`、`reasoning`、`response_format` 和严格 `structured_outputs`。
- [x] 结构化输出采用三级策略：严格 JSON Schema → JSON mode → Prompt JSON + 本地 Pydantic 校验。
- [x] 根据 `top_provider.max_completion_tokens` 自动限制输出长度，避免切换到小输出模型后请求越界。
- [x] 对目录未知或端点能力变化的模型，仅在明确参数兼容错误时逐项关闭不支持参数后重试；不静默切换到其他模型。
- [x] DeepSeek 直连接口继续禁用，即使显式传入 DeepSeek Base URL 也不能创建 driver；OpenRouter 目录中的模型不按厂商品牌过滤。
- [x] 前端、Gemini 回退提示、频道三运行提示和 Word 报告标题改为供应商中性文案。
- [x] `setup_api_keys.py` 继续支持任意 `OPENROUTER_MODEL_ID`，推理设置扩展为 `auto/none/minimal/low/medium/high/xhigh`。
- [x] 本地公共目录验证解析出 414 个文本模型，并验证 Qwen3.7 Flash 与不支持 reasoning/JSON mode 的模型均能正确识别能力。
- [x] 多模型专项测试与全部现有测试通过；Streamlit 浏览器完成默认模型和非 Qwen 模型切换检查。
- [ ] 配置有效 `OPENROUTER_API_KEY` 后，分别选取一个支持严格 JSON Schema 的模型和一个仅支持普通文本输出的模型执行真实端到端生成。

## 主模型迁移：DeepSeek 暂停，切换 Qwen Flash

- [x] 审查 `agent_app.py`、各 agent、API Key 脚本、导出层和前端中的 DeepSeek 运行时耦合点。
- [x] 联网核验 OpenRouter 官方目录和公开 Models API，确认模型 ID 为 `qwen/qwen3.7-flash`，上下文 1M，最大输出 65536 token。
- [x] 新增独立 `tools/llm_driver.py`，通过 OpenRouter OpenAI 兼容接口接入 Qwen3.7 Flash。
- [x] Qwen 结构化任务使用 JSON mode、`provider.require_parameters=true` 和 OpenRouter 统一 `reasoning` 参数，默认 `effort=none`。
- [x] OpenRouter 请求增加 120 秒超时、2 次 SDK 重试、8192 输出 token 上限和结构化输出兼容回退。
- [x] `agent_app.py` 停止读取 `DEEPSEEK_API_KEY`，不再包含 DeepSeek provider 或自动回退路径。
- [x] Streamlit 前端替换为 OpenRouter Qwen 模型选择、推理强度和可编辑 API Base URL。
- [x] `setup_api_keys.py` 支持 `OPENROUTER_API_KEY`、`OPENROUTER_MODEL_ID`、`OPENROUTER_BASE_URL`、`OPENROUTER_REASONING_EFFORT`；旧 DeepSeek/DashScope Key 仅保留，不参与运行。
- [x] Word 报告标题切换为 Qwen；PWG 当前“不调用大模型”的状态提示同步更新。
- [x] 增加 Qwen stub 单元测试，并执行全部现有测试脚本和 Streamlit 浏览器检查。
- [ ] 在本地配置有效 `OPENROUTER_API_KEY` 后执行一次真实 Qwen3.7 Flash 结构化调用和频道一端到端生成验证。

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
