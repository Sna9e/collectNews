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

## 3. 未完成内容

- 尚未修改 K 线图大小或 PPT 中的图表摆放尺寸。
- 尚未调整苹果、谷歌、特斯拉等公司主题的硬件化、本地化方向。
- 尚未调整行业主题包的硬件、供应链和市场催化侧重。
- 尚未在本地带 key 的运行副本中完成真实启动与导出验证。

## 4. 关键决定

- `AGENTS.md` 只写长期有效、低频更新的稳定规则，不写这次任务的临时细节。
- `PLANS.md` 只记录本轮任务的目标、边界、步骤和风险。
- `HANDOFF.md` 用来承接当前进度，后续每次有实质性实现或验证都应继续更新。
- 真实验证默认在本地运行副本执行；代码修改默认在 Git 同步仓库完成并再同步过去。
- 当前任务不做无关重构，优先改最短路径上的问题点。

## 5. 风险/禁区

- 当前同步仓库是脏工作树，不要回退或覆盖已有未提交改动。
- 不要修改或提交真实密钥文件，例如 `.streamlit/secrets.toml`。
- 不要默认改动 `.venv/`、`.idea/`、`__pycache__/`、生成产物和日志文件。
- `template.pptx` 属于高风险文件，除非确认问题根因在模板本身，否则不要先动它。
- 没有真实启动与导出验证前，不要把版式修复或主题修复写成“已完成”。

## 6. 相关文件

- `agent_app.py`
- `tools/finance_engine.py`
- `tools/export_ppt.py`
- `tools/intelligence_packs.py`
- `tools/company_query_packs.py`
- `.streamlit/secrets.toml.example`
- `AGENTS.md`
- `PLANS.md`
- `HANDOFF.md`

## 7. 验证方式

- 启动验证：在带 key 的本地运行副本中执行 `python -m streamlit run agent_app.py`，或使用副本中的 `run_local.ps1`。
- 功能验证：至少跑一次公司追踪流，确认新闻抓取、分析、金融补链和导出链路能走通。
- 版式验证：重点检查金融页 K 线图与文字区域是否重叠、是否压缩失真、是否越界。
- 主题验证：抽查苹果、谷歌、特斯拉及行业流结果，确认输出不再主要被泛 AI、隐私、诉讼类信息占据。
- 结果记录：若外部接口失败或额度不足，需把失败点和未验证项明确记入交接说明。

## 8. 下一步建议

1. 先做图表链路的局部修改，优先检查 `tools/finance_engine.py` 与 `tools/export_ppt.py` 的组合效果。
2. 再做 query pack 和排序逻辑的微调，不要一上来大改所有主题。
3. 修改完成后，立刻在本地运行副本做一次真实烟测，并把结果回写到本文件。
4. 如果发现同步仓库与本地运行副本存在差异，先对齐关键文件，再继续实现与验证。
