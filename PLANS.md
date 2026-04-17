# PLANS.md

## 1. Goal

在不做无关重构的前提下，完成本轮科技资讯搜集应用调整：

- 先为仓库补齐长期规则、当前计划和交接文档；
- 再把 K 线图缩小约三分之一，避免导出时与正文重叠；
- 再把公司/行业主题进一步调整到“硬件、供应链、实质性科技进展、市场催化、中国本地落地”方向。

## 2. Context

- 当前 Git 同步仓库：`E:\Users\zwz10\PycharmProjects\_collectNews_publish_verify`
- 本地运行副本（带 key，适合真实检查）：`E:\Users\zwz10\PycharmProjects\collectNewslocal`
- 当前应用运行在 Streamlit 上，主入口为 `agent_app.py`
- 已定位到的主要相关模块：
  - K 线生成：`tools/finance_engine.py`
  - 金融页图表摆放：`tools/export_ppt.py`
  - 行业主题包：`tools/intelligence_packs.py`
  - 公司查询包与结果排序：`tools/company_query_packs.py`
- 当前同步仓库不是干净工作树，存在用户已有改动，不能直接回退或覆盖。

## 3. Relevant files

- `agent_app.py`
- `tools/finance_engine.py`
- `tools/export_ppt.py`
- `tools/intelligence_packs.py`
- `tools/company_query_packs.py`
- `.streamlit/secrets.toml.example`
- `AGENTS.md`
- `PLANS.md`
- `HANDOFF.md`

补充参考：

- 本地运行副本中的 `run_local.ps1` 可作为带密钥环境下的启动辅助，但不属于当前 Git 同步仓库文件。

## 4. Constraints

- 先生成并更新文档文件，不先做大范围代码调整。
- 默认最小改动，避免无关重构。
- 不覆盖当前仓库中已有的未提交用户改动。
- 不修改或提交真实密钥、本地产物、`.venv/`、`.idea/`、`__pycache__/`。
- 真实验证优先在本地运行副本中完成，因为那里具备可用 key。
- 不伪造启动结果、抓取结果、导出结果或验证结论。

## 5. Steps

1. 已完成：审视仓库结构、入口文件、关键工具模块，以及是否已有 `AGENTS.md` / `PLANS.md` / `HANDOFF.md`。
2. 已完成：根据当前仓库和本次对话，创建三份文档并区分长期规则、当前任务计划、交接摘要。
3. 待完成：精读 K 线生成与 PPT 金融页布局逻辑，判断应同时调整图像尺寸和摆放尺寸，还是只改其中一侧。
4. 待完成：重写或补强公司/行业 query pack，使主题更偏硬件、芯片、终端形态、供应链、量产、订单、资本开支和中国落地。
5. 待完成：在带密钥的本地运行副本中做至少一次启动与导出烟测，确认页面、抓取、金融页和导出结果是否正常。
6. 待完成：把验证结论、残留风险和后续建议更新到 `HANDOFF.md`。

## 6. Risks

- K 线图重叠不一定只由图像原始大小造成，也可能与 `export_ppt.py` 中的图片插入宽度和文本区高度有关。
- 主题过度偏向硬件后，可能误伤本来应保留的高价值商业或监管新闻，需要平衡排序和类别上限。
- Git 同步仓库与本地运行副本可能存在内容漂移，验证前需要确认关键文件一致。
- 外部搜索接口、财经接口和模型服务存在时延、额度和偶发失败，验证结果可能带噪声。
- 当前仓库已有未提交改动，若直接大范围格式化或重构，容易引入冲突。

## 7. Done when

- `AGENTS.md`、`PLANS.md`、`HANDOFF.md` 已建立并与当前仓库一致。
- K 线图在目标导出场景中不再与正文重叠，且视觉尺寸明显小于当前版本。
- 苹果、谷歌、特斯拉等公司主题，以及行业主题，已明显转向硬件、供应链、量产和中国落地。
- 已完成至少一次本地真实检查；若受外部接口阻塞，阻塞原因已记录清楚。
- 交接文件中能直接说明下一位执行者应该从哪里接着做。
