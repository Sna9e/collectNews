# PLANS.md

## 1. Goal

在不影响 `24h` 日报的前提下，撤回本轮已经把日报打乱的周报/时间线扩张改动，恢复稳定日报链路，并且只对“核心时间线新闻太短”做最小修正。

## 2. Context

- 当前 Git 同步仓库：`E:\Users\zwz10\PycharmProjects\_collectNews_publish_verify`
- 本地运行副本（带 key，适合真实检查）：`E:\Users\zwz10\PycharmProjects\collectNewslocal`
- 当前坏样本 PPT：`C:\Users\zwz10\Downloads\FPC-RD科技资讯_2026-04-23 (2).pptx`
- 用户反馈的核心问题不是“周报不够好”，而是“日报已经被打乱”，表现为：
  - Google 等专题的内容跨章节乱窜；
  - 核心时间线和后续长新闻之间的关系变得混乱；
  - 日报整体失去原来稳定的章节边界。
- 当前最合理的任务版本不是继续做周报，而是先回到“核心时间线改造之前”的稳定日报状态。
- 当前允许保留的唯一谨慎增量修改，是让核心时间线短新闻不要过短，避免只剩 10 来个字的名词短语。

## 3. Relevant files

- `agent_app.py`
- `agents/timeline_agent.py`
- `agents/deep_analyst.py`
- `tools/report_linker.py`
- `tools/export_word.py`
- `tools/export_ppt.py`
- `PLANS.md`
- `HANDOFF.md`

补充说明：

- `tools/export_ppt.py` 本轮主要作为导出验证目标，不作为核心改动入口。
- `tools/company_query_packs.py` 与 `tools/intelligence_packs.py` 本轮不继续扩改，避免再引入新变量。

## 4. Constraints

- 不继续推进周报功能，先把日报恢复稳定。
- 默认最小改动，不做无关重构。
- 不覆盖当前仓库中已有的未提交用户改动。
- 不修改或提交真实密钥、本地产物、`.venv/`、`.idea/`、`__pycache__/`。
- 真实验证优先在本地运行副本中完成，因为那里具备可用 key。
- 当前模型链路继续按 DeepSeek 处理，Gemini 不作为本轮排障目标。
- 不伪造启动结果、抓取结果、导出结果或验证结论。

## 5. Steps

1. 已完成：回看当前日报链路，确认本轮真正需要停止的是“周报模式接线”“时间线额外补位/反向补线”和候选扩张，而不是继续堆更多功能。
2. 已完成：将 `agents/deep_analyst.py`、`tools/report_linker.py`、`tools/export_word.py` 回退到稳定基线，移除本轮新增的周报和反向补线行为。
3. 已完成：在 `agent_app.py` 中撤回报告模式、动态配额和额外候选补位逻辑，恢复稳定日报入口与固定日报参数。
4. 已完成：在 `agents/timeline_agent.py` 中只保留一项最小修改，把核心时间线短新闻改成长一点、信息完整一点，但不扩大搜索范围和候选规模。
5. 已完成：对关键 Python 文件执行 `py_compile` 语法烟测，确认当前代码可加载。
6. 待完成：将修改同步到本地运行副本，并用真实 key 跑一次日报，检查 PPT 是否恢复正常章节边界。
7. 已完成：更新 `PLANS.md` 与 `HANDOFF.md`，明确当前已暂停周报，后续只围绕日报稳定性继续收敛。

## 6. Risks

- 当前只做了静态回退和语法检查，尚未用真实数据重新生成日报 PPT。
- `tools/export_ppt.py` 里仍保留部分未接线的长周期渲染辅助代码，但只要日报链路不再写入对应元数据，正常日报不会触发这些分支。
- 如果核心时间线在真实跑数后仍偏少，下一步也应继续只调 `agents/timeline_agent.py` 的标题表达和压缩规则，不应再重新打开候选扩张或跨章节补线逻辑。
- 当前仓库是脏工作树，后续若再做大范围回退，容易误伤用户已有改动。

## 7. Done when

- `24h` 日报链路不再携带周报/观察模式的动态分支。
- 日报生成的专题章节不再出现明显“内容乱窜”或跨章节混入。
- 核心时间线短新闻比此前更完整，但仍保持短讯风格，不重新扩大长文候选池。
- `PLANS.md` 和 `HANDOFF.md` 已更新到当前任务语境。
- 已完成至少一次本地真实检查；若本轮尚未执行，则需在交接中明确记录为未验证项。
