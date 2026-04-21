# HANDOFF.md

## 1. 当前目标

当前任务目标分三段：

- 保持既有文档与交接文件可持续更新；
- 修正导出版式与主题 query pack，使结果更偏硬件、供应链、量产和中国落地；
- 继续拉宽核心时间线，避免时间线只剩会展开成长文的少数事件，尤其补足特朗普专题中的中东/地缘主线。

## 2. 已完成内容

- 已确认当前 Git 同步仓库为 `E:\Users\zwz10\PycharmProjects\_collectNews_publish_verify`。
- 已确认本地带 key 的运行副本为 `E:\Users\zwz10\PycharmProjects\collectNewslocal`。
- 已确认同步仓库中此前不存在 `AGENTS.md`、`PLANS.md`、`HANDOFF.md`。
- 已定位当前任务的关键代码位置：
  - K 线生成：`tools/finance_engine.py`
  - 金融页图表插入：`tools/export_ppt.py`
  - 行业主题包：`tools/intelligence_packs.py`
  - 公司 query pack 与排序：`tools/company_query_packs.py`
- 已新增三份文档，完成规则、计划和交接的基础落盘。
- 已完成主题强化：
  - Apple 增加折叠机、铰链、UTG、模组、供应链、中国制造相关 query/keyword。
  - Google 增加 TPU、Ironwood/Trillium、Tensor、Pixel Fold、算力硬件相关 query/keyword。
  - Tesla 增加 FSD 中国落地、审批/试点、城市导航、上海工厂等 query/keyword。
  - Amazon、Meta 和 generic fallback pack 也同步向硬件/供应链方向收紧。
- 已完成行业扩展主题结构补全：
  - `tools/intelligence_packs.py` 中 6 个扩展主题已补齐 `tags` / `keywords` / `companies` / `domains` / `china_domains`，不再只是 query 文案。
- 已完成核心时间线策略调整：
  - 时间线事件目标数量从偏保守的 5-8 条放宽到 8-12 条，最多 14 条。
  - 时间线事件去重阈值放宽，减少不同事件被过早并掉的情况。
  - 明确要求“时间线不等于深度新闻候选池”，允许保留有意义但不一定进入长文的更新。
- 已完成时间线展示瘦身：
  - Streamlit 预览不再逐条显示长段“匹配原因”。
  - PPT 核心时间线页改为简短“后文承接”提示，不再塞整段匹配解释。
- 已完成 K 线图版式修复：
  - PPT 金融页图表宽度从 `8.2"` 缩到 `5.45"`，并右移到更安全的位置，避免压到下方催化剂文本框。
- 已完成第二轮核心时间线放宽：
  - 时间线目标数量进一步上调到“至少 7 条，常规 8-12 条，最多 16 条”。
  - 时间线输入窗口扩大：公司流蓝图候选从 `18` 提高到 `24`，行业流从 `16` 提高到 `20`。
  - 去重阈值继续放宽，降低不同短讯被误并为同一事件的概率。
  - `policy` / `generic` / `business` 配额提高，避免政策、地缘和市场短讯被过早压掉。
  - 标题回写阶段对低相似度原始结果的强行覆盖阈值提高，减少多条短讯被同一条新闻标题“吸过去”的问题。
- 已完成特朗普专题补强：
  - `tools/company_query_packs.py` 中 `trump` pack 已加入 Middle East / Israel / Iran / Gaza / Red Sea / oil / sanctions / defense / ceasefire 等关键词、优先词和 query。
  - 权威域名范围扩展到 `axios.com`、`politico.com`、`ft.com`、`aljazeera.com`，用于补足传统经贸线之外的地缘与外交线。
  - 特朗普专题的 focus hint 已改成政策 / 关税 / 中东 / 能源 / 制裁 / 外交导向，不再套用硬件公司模板。
- 已完成当前运行模式收敛：
  - 侧边栏已改为默认只走 DeepSeek。
  - Gemini 主模型/轻任务切换在本轮中已临时下线，不再作为当前排障和验证范围。
- 已把上述代码同步到本地运行副本，关键文件哈希一致。

## 3. 未完成内容

- 尚未跑一次带真实搜索/API key 的完整端到端烟测。
- 尚未用真实公司专题确认“第二轮放宽后的核心时间线”是否在数量和相关性上都达到预期。
- 尚未用真实 `Trump` 专题确认中东局势是否已稳定进入核心时间线。
- 尚未检查 Word 导出在长时间线场景下的观感。

## 4. 关键决定

- `AGENTS.md` 只写长期有效、低频更新的稳定规则，不写这次任务的临时细节。
- `PLANS.md` 只记录本轮任务的目标、边界、步骤和风险。
- `HANDOFF.md` 用来承接当前进度，后续每次有实质性实现或验证都应继续更新。
- 真实验证默认在本地运行副本执行；代码修改默认在 Git 同步仓库完成并再同步过去。
- 当前任务不做无关重构，优先改最短路径上的问题点。
- 核心时间线与深度新闻分层处理：
  - 时间线负责保留更完整的“当天值得记住的更新”。
  - 深度新闻继续只展开其中更值得详细分析的子集。
- 时间线优先保证“覆盖面”而不是“每条都能展开成长文”：
  - 对公司、宏观、政策和地缘专题，允许保留更多短讯型更新。
  - 不再把“是否适合写长文”当作时间线保留前提。
- 当前模型链路默认固定为 DeepSeek：
  - Gemini 相关设置暂不纳入本轮验证与故障定位范围。
- PPT 核心时间线页只保留短讯主干和极短承接提示；详细匹配原因留在调试视图或深度新闻链路。

## 5. 风险/禁区

- 当前同步仓库是脏工作树，不要回退或覆盖已有未提交改动。
- 不要修改或提交真实密钥文件，例如 `.streamlit/secrets.toml`。
- 不要默认改动 `.venv/`、`.idea/`、`__pycache__/`、生成产物和日志文件。
- `template.pptx` 属于高风险文件，除非确认问题根因在模板本身，否则不要先动它。
- 当前实现已经完成，但在真实联网跑通前，不要把“效果已验证”写成既成事实。
- 时间线数量放宽后，后续如果发现噪声回升，优先微调去重阈值、输入窗口和 topic pack，不要立刻再收紧回旧逻辑。
- `Trump` 这类政策/地缘专题与 Apple / Google / Tesla 这类科技公司专题不同：
  - 评估时要接受更高比例的政策、能源、外交和制裁类短讯。
  - 不要再用“硬件导向”标准去错误过滤这类专题的主线新闻。

## 6. 相关文件

- `agent_app.py`
- `tools/export_ppt.py`
- `tools/intelligence_packs.py`
- `tools/company_query_packs.py`
- `agents/timeline_agent.py`
- `.streamlit/secrets.toml.example`
- `AGENTS.md`
- `PLANS.md`
- `HANDOFF.md`

## 7. 验证方式

- 启动验证：在带 key 的本地运行副本中执行 `python -m streamlit run agent_app.py`，或使用副本中的 `run_local.ps1`。
- 功能验证：至少跑一次公司追踪流，确认新闻抓取、分析、金融补链和导出链路能走通。
- 版式验证：重点检查金融页 K 线图与文字区域是否重叠、是否压缩失真、是否越界。
- 时间线验证：抽查 Apple / Google / Tesla / Trump 等专题，确认核心时间线不再只剩会写成长文的少数事件，并且总量通常能达到 7-8 条左右。
- 主题验证：抽查苹果、谷歌、特斯拉及行业流结果，确认输出不再主要被泛 AI、隐私、诉讼类信息占据，而能看到硬件、供应链、量产和中国落地。
- Trump 专题验证：重点确认中东局势、关税、制裁、能源、白宫行政令等是否能同时进入时间线，而不是只剩单一经贸线。
- 结果记录：若外部接口失败或额度不足，需把失败点和未验证项明确记入交接说明。

补充说明：

- 已完成本地静态验证：`py_compile` 通过。
- 已完成本地结构烟测：使用本地 `.venv` 生成示例 PPT，确认金融页图表显示尺寸约为 `5.45" x 2.73"`，核心时间线页不再显示长段匹配原因。
- 本轮还需补做真实联网验证；当前文档中的“时间线更广”与“Trump 中东线补足”仍属于已实现、未完全实跑确认状态。

## 8. 下一步建议

1. 在本地运行副本用真实 key 跑一次 `Google \\ Tesla \\ Trump` 的公司追踪流，重点看：
   - 时间线是否比之前更完整；
   - Google 是否明显出现 TPU / Pixel Fold / Tensor；
   - Tesla 是否明显出现 FSD 中国落地；
   - Trump 是否明显出现中东局势 / 制裁 / 关税 / 白宫行政令。
2. 导出真实 PPT 后，重点查看：
   - 金融页 K 线图是否彻底脱离下方文本框；
   - 核心时间线是否仍然过于稀疏；
   - 一页 6 条时间线在真实文本长度下是否仍然可读。
3. 如果真实时间线仍然偏少，优先继续调 `agents/timeline_agent.py`：
   - `TIMELINE_TARGET_MIN` / `TIMELINE_HARD_LIMIT`
   - 去重阈值
   - `_rewrite_event_dicts()` 的原始标题覆盖阈值
   - `policy` / `generic` / `business` 配额
4. 如果 Trump 线仍然不够完整，优先继续补 `tools/company_query_packs.py` 的 `trump` pack，而不是先收紧全局时间线。
5. 如果主题仍然不够硬件化，优先继续补 `tools/company_query_packs.py` 和 `tools/intelligence_packs.py`，不要先动搜索引擎基础设施。
