# HANDOFF.md

## 1. 当前目标

当前目标已经收敛为一件事：先把 `24h` 日报恢复到稳定状态，暂停周报功能推进，并且只对“核心时间线新闻太短”做最小修正。

## 2. 已完成内容

- 已确认本轮应优先处理的是日报失稳，而不是继续做周报细化。
- 已把下列文件回退到更稳定的基线行为：
  - `agents/deep_analyst.py`
  - `tools/report_linker.py`
  - `tools/export_word.py`
- 已在 `agent_app.py` 中撤回本轮新增的日报/周报/观察模式分流，恢复为固定的日报入口：
  - 不再显示“报告模式”；
  - 不再按周报/观察模式动态放大搜索、蓝图和抓取配额；
  - 不再对候选结果做额外的补位扩张；
  - 宏观行业频道按钮恢复为固定的日报文案。
- 已撤回会扰乱日报章节边界的动态分支：
  - `report_scope` 元数据写入；
  - 周报专题总结预览；
  - 额外补长文候选的支持度逻辑。
- 已在 `agents/timeline_agent.py` 中保留唯一的谨慎修改：
  - 核心时间线短新闻从过短的“名词短语”收敛为更完整的一句话短讯；
  - 标题压缩长度略放宽，但没有扩大搜索窗口、候选规模或跨章节补线。
- 已完成本地静态验证：
  - `python -m py_compile agent_app.py agents\timeline_agent.py agents\deep_analyst.py tools\report_linker.py tools\export_word.py tools\export_ppt.py tools\company_query_packs.py tools\intelligence_packs.py`
  - 结果：通过。

## 3. 未完成内容

- 尚未在本地运行副本用真实 key 重新跑一次日报。
- 尚未重新生成并检查新的 PPT，确认 `C:\Users\zwz10\Downloads\FPC-RD科技资讯_2026-04-23 (2).pptx` 中那类“Google 信息跨章节乱窜”的现象是否已消失。
- 尚未确认核心时间线在真实数据下是否已经达到“仍然短讯化，但不再过短”的目标。

## 4. 关键决定

- 当前明确暂停周报，不再继续推进“周报独立化”。
- 当前不再继续扩大时间线条数、候选池、反向补线或规则补位。
- 当前只保留一个最小修改方向：把核心时间线短新闻写得稍微完整一点。
- 当前保留的非本次问题修复包括：
  - `tools/company_query_packs.py` / `tools/intelligence_packs.py` 中已做的硬件化、本地化 query pack 强化；
  - `tools/export_ppt.py` 中已经完成的 K 线图缩小。
- 当前模型链路继续按 DeepSeek 处理，Gemini 不作为本轮回退对象。

## 5. 风险/禁区

- 当前仓库是脏工作树，不要直接做全仓硬回退。
- 不要继续把周报逻辑重新接回 `agent_app.py`，至少在日报重新实跑确认稳定前不要这样做。
- 不要重新打开 `tools/report_linker.py` 的反向补线逻辑，否则很容易再次把专题边界搅乱。
- 不要重新加回 `select_analysis_candidates()` 的额外补位逻辑，否则日报章节很可能再次变得发散。
- `tools/export_ppt.py` 里仍残留部分长周期渲染辅助代码，但当前日报链路不会给它对应元数据；若后续再次做周报，应重新评估，而不是直接恢复旧接线。

## 6. 相关文件

- `agent_app.py`
- `agents/timeline_agent.py`
- `agents/deep_analyst.py`
- `tools/report_linker.py`
- `tools/export_word.py`
- `tools/export_ppt.py`
- `PLANS.md`
- `HANDOFF.md`

## 7. 验证方式

- 启动验证：在本地运行副本执行 `python -m streamlit run agent_app.py`，或使用 `run_local.ps1`。
- 日报验证：至少跑一次 `Google` 或 `Nvidia \ Google` 的日报，确认专题不再跨章节混入。
- 时间线验证：重点看核心时间线短新闻是否比之前更完整，但仍保持短讯风格。
- 导出验证：重新生成 PPT，检查是否还会出现同一家公司新闻散落到不同章节的问题。

## 8. 下一步建议

1. 先把当前修改同步到 `E:\Users\zwz10\PycharmProjects\collectNewslocal`。
2. 用真实 key 跑一次日报，不要先跑周报。
3. 优先检查 `Google` 和 `Nvidia` 两个专题：
   - Google 是否还会在不同章节乱窜；
   - Nvidia 的核心时间线是否仍然只有极短标题。
4. 如果时间线仍偏短，下一步只继续微调 `agents/timeline_agent.py`：
   - 标题长度区间；
   - 标题清洗和截断长度；
   - 短讯表达要求。
5. 在日报重新稳定前，不要再碰周报接线、反向补线和候选扩张。
