# PLANS.md

## 1. Goal

把当前日报链路收敛到“DeepSeek 成稿 + Tavily 主搜 + 展示结构稳定”的状态，重点修复两个现象：

- 公司或主题信息跨章节乱窜，例如 Google 信息出现在 Nvidia / Amazon 等不对应章节；
- PPT 主图或封面与本次报告内容不匹配，疑似沿用了模板内旧页。
- 核心时间线仍然过短，Apple / Google 等专题只剩 1 条短讯，无法满足日报广度要求。

本轮不继续推进周报，不做大规模回退，不重新打开 Exa / Hybrid 搜索分支。

## 2. Context

- 当前 Git 同步仓库：`E:\Users\zwz10\PycharmProjects\_collectNews_publish_verify`
- 本地运行副本：`E:\Users\zwz10\PycharmProjects\collectNewslocal`
- 用户当前关注日报稳定性，周报功能先忽略。
- 当前口径：Tavily 是唯一搜索入口，DeepSeek 是主要生成模型，Gemini 暂不作为排障重点。
- 本地运行副本当前没有实际 `.streamlit/secrets.toml`，也未检测到 `TAVILY_API_KEY` / `DEEPSEEK_API_KEY` 环境变量，因此真实联网端到端验证仍受阻。

## 3. Relevant files

- `agent_app.py`
- `tools/export_ppt.py`
- `tools/report_linker.py`
- `tools/company_query_packs.py`
- `tools/intelligence_packs.py`
- `agents/timeline_agent.py`
- `PLANS.md`
- `HANDOFF.md`

## 4. Constraints

- 不继续推进周报功能。
- 不整仓硬回退，避免覆盖用户已有改动。
- 不重新引入 Exa / Hybrid fallback。
- 不修改真实密钥、本地产物、`.venv/`、`.idea/`、`__pycache__/`。
- 只做小范围防串章和导出版式修复，避免再次扰乱日报主链。

## 5. Steps

1. 已完成：确认 `tools/report_linker.py` 只按相同 topic 连接时间线和长新闻，跨章节乱窜更可能来自上游搜索结果和模型成稿阶段，而不是链接器跨 topic 匹配。
2. 已完成：在 `agent_app.py` 增加轻量专题门禁：
   - 对 Tavily 搜索结果按专题主实体、别名、关键词做过滤；
   - 对模型生成的核心时间线做同一门禁；
   - 对模型生成的深度新闻做同一门禁；
   - 门禁不足以保留最低数量时回退原列表，避免误杀导致空报告。
3. 已完成：公司流使用较严格门禁，要求主实体命中或多个专题关键词命中。
4. 已完成：行业流使用较宽门禁，避免因行业主题宽泛导致过度过滤。
5. 已完成：在 `tools/export_ppt.py` 加载 `template.pptx` 后移除模板自带旧幻灯片，只保留母版/布局，再生成本次报告页面。
6. 已完成：执行语法检查：`python -m py_compile agent_app.py tools\export_ppt.py tools\report_linker.py agents\deep_analyst.py`。
7. 已完成：执行 PPT 烟测，确认生成文件第一张幻灯片为《FPC-RD 科技资讯》，不再被模板旧页抢占。
8. 已完成：同步关键文件到本地运行副本，并核对 `agent_app.py`、`tools/export_ppt.py`、`PLANS.md`、`HANDOFF.md` 哈希一致。
9. 已完成：在本地运行副本再次执行 `py_compile` 与 Streamlit `AppTest` 页面烟测，页面无异常。
10. 已完成：在本地运行副本执行 PPT 烟测，确认第一张幻灯片为本次生成标题页。
11. 已完成：修正时间线过短问题：
   - 时间线阶段的专题门禁改为至少保留 7 条才生效，避免只剩 1 条；
   - 事件主档增加无额外 LLM token 的 Tavily 标题兜底补线；
   - 当模型只返回少量事件时，从已召回搜索结果补足到约 8 条。
12. 已完成：使用 stub AI 做无 API 烟测，确认模型只返回 1 条事件时，最终事件主档可补到 8 条。
13. 待完成：实际密钥恢复后跑一次 Tavily + DeepSeek 日报，下载 PPT 检查是否仍有串章、主图不匹配或时间线过短。

## 6. Risks

- 专题门禁是轻量规则，不是强语义分类；如果新闻同时涉及多个公司，仍可能被保留在其中一个相关章节。
- 如果某公司新闻本身很少，门禁会在低于最低保留量时回退原列表，以避免时间线过短；这意味着极低召回场景下仍可能残留噪声。
- 兜底补线直接使用 Tavily 标题，不额外消耗模型 token；标题可读性依赖搜索结果标题质量。
- 当前仍未完成真实 Tavily + DeepSeek 端到端跑数，因为本地运行副本缺少实际密钥。
- PPT 使用 `python-pptx` 的私有 slide list API 清理模板旧页，已通过烟测，但后续如果模板结构大改，需要复测。

## 7. Done when

- Tavily 是唯一搜索入口。
- 页面和导出不再出现周报入口或旧周报标题。
- PPT 第一页是本次生成的《FPC-RD 科技资讯》，没有旧模板主图抢占。
- 同一专题的核心时间线和深度新闻不明显串到其他公司章节。
- 常规公司专题核心时间线优先保持 7-8 条以上，除非搜索召回本身不足。
- 本地运行副本关键文件已同步，并通过语法检查、页面烟测和 PPT 烟测。
- 真实密钥恢复后完成一次日报端到端跑数与 PPT 下载检查。
