# HANDOFF.md

## 1. 当前目标

当前任务目标分两段：

- 先建立并更新项目文档：`AGENTS.md`、`PLANS.md`、`HANDOFF.md`；
- 再继续处理两项功能问题：
  - K 线图缩小，避免与正文重叠；
  - 主题与查询策略向硬件、供应链、实质性科技进展、市场消息和中国本地落地方向收敛。

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
- 已把上述代码同步到本地运行副本，关键文件哈希一致。

## 3. 未完成内容

- 尚未跑一次带真实搜索/API key 的完整端到端烟测。
- 尚未用真实公司专题确认“放宽后的核心时间线”是否在数量和相关性上都达到预期。
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
- PPT 核心时间线页只保留短讯主干和极短承接提示；详细匹配原因留在调试视图或深度新闻链路。

## 5. 风险/禁区

- 当前同步仓库是脏工作树，不要回退或覆盖已有未提交改动。
- 不要修改或提交真实密钥文件，例如 `.streamlit/secrets.toml`。
- 不要默认改动 `.venv/`、`.idea/`、`__pycache__/`、生成产物和日志文件。
- `template.pptx` 属于高风险文件，除非确认问题根因在模板本身，否则不要先动它。
- 当前实现已经完成，但在真实联网跑通前，不要把“效果已验证”写成既成事实。
- 时间线数量放宽后，后续如果发现噪声回升，优先微调去重阈值和 topic pack，不要立刻再收紧回旧逻辑。

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
- 时间线验证：抽查 Apple / Google / Tesla 等专题，确认核心时间线不再只剩会写成长文的少数事件。
- 主题验证：抽查苹果、谷歌、特斯拉及行业流结果，确认输出不再主要被泛 AI、隐私、诉讼类信息占据，而能看到硬件、供应链、量产和中国落地。
- 结果记录：若外部接口失败或额度不足，需把失败点和未验证项明确记入交接说明。

补充说明：

- 已完成本地静态验证：`py_compile` 通过。
- 已完成本地结构烟测：使用本地 `.venv` 生成示例 PPT，确认金融页图表显示尺寸约为 `5.45" x 2.73"`，核心时间线页不再显示长段匹配原因。

## 8. 下一步建议

1. 在本地运行副本用真实 key 跑一次 `Google \\ Tesla` 的公司追踪流，重点看：
   - 时间线是否比之前更完整；
   - Google 是否明显出现 TPU / Pixel Fold / Tensor；
   - Tesla 是否明显出现 FSD 中国落地。
2. 导出真实 PPT 后，重点查看：
   - 金融页 K 线图是否彻底脱离下方文本框；
   - 核心时间线是否仍然过于稀疏；
   - 一页 6 条时间线在真实文本长度下是否仍然可读。
3. 如果真实时间线仍然偏少，优先继续调 `agents/timeline_agent.py`：
   - `TIMELINE_HARD_LIMIT`
   - 去重阈值
   - prompt 中“保留范围”的约束
4. 如果主题仍然不够硬件化，优先继续补 `tools/company_query_packs.py` 和 `tools/intelligence_packs.py`，不要先动搜索引擎基础设施。
