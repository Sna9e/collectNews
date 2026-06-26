# 应变片与机器人六轴力传感器专题模块指南

## 1. 模块定位

新增独立技术模块：

```python
TECH_MODULES = [
    "应变片与机器人六轴力传感器"
]
```

英文名称：

```python
"Strain Gauge and Robotic Six-Axis Force/Torque Sensor"
```

该模块不并入 Apple、Google、Tesla 等公司日更主题，不占用频道一或频道三的详细新闻配额。

现有固定主题仍保持：

```python
MANDATORY_TOPICS = [
    "Apple",
    "Google",
    "Amazon",
    "OpenAI",
    "Meta",
    "Nvidia",
    "Tesla",
    "特朗普",
]
```

## 2. 新增文件

- `strain_gauge_intelligence/__init__.py`
- `strain_gauge_intelligence/models.py`
- `strain_gauge_intelligence/collector.py`
- `strain_gauge_intelligence/reporter.py`
- `strain_gauge_intelligence/config/keywords.yaml`
- `strain_gauge_intelligence/config/companies.yaml`
- `strain_gauge_intelligence/config/report_rules.yaml`
- `tools/strain_gauge_query_packs.py`
- `tests/test_strain_gauge_module.py`

## 3. 配置文件

关键词、公司、专利申请人、信源域名和查询模板放在 YAML 中维护，非程序人员可以直接修改：

- `strain_gauge_intelligence/config/keywords.yaml`
- `strain_gauge_intelligence/config/companies.yaml`
- `strain_gauge_intelligence/config/report_rules.yaml`

关键词覆盖：

- 应变片、箔式应变片、薄膜应变片、柔性应变传感器。
- 六轴力传感器、六维力传感器、六分力传感器、力/力矩传感器。
- 机器人腕部力传感器、机器人关节力传感器、灵巧手触觉传感器、人形机器人力控。
- 十字梁、轮辐式、Stewart 平台、惠斯通电桥、全桥、温度补偿、解耦算法、标定矩阵。
- FPC 应变片、柔性电路应变传感器。

## 4. 信息类型和数量校验

模块分三类输出：

| 类型 | 最低数量 | 优先窗口 | 扩展窗口 |
| --- | ---: | --- | --- |
| 新闻 / 公司动态 | 2 | 最近 30 天 | 90 天、180 天 |
| 专利动态 | 3 | 最近 12 个月 | 最近 3 年 |
| 论文 / 学术进展 | 3 | 最近 3 年 | 最近 5 年 |

数量校验逻辑写在：

`strain_gauge_intelligence/collector.py`

如果不足：

- 自动扩大检索窗口；
- 自动补充英文关键词；
- 专利会尝试 Google Patents XHR 兜底；
- 最终仍不足时，报告保留模块并写明不足原因，不静默跳过。

## 5. 运行方式

命令行运行：

```bash
python -m strain_gauge_intelligence.collector --provider exa --max-queries-per-type 6 --results-per-query 6 --overwrite
```

输出目录：

| 文件类型 | 路径 |
| --- | --- |
| raw JSON / raw Excel | `data/strain_gauge_intelligence/raw/` |
| Markdown 专题报告 | `data/strain_gauge_intelligence/reports/` |

前端入口：

`🧲 应变片/六轴力传感器专题`

前端功能：

- 触发独立专题检索；
- 设置每类 query 数和每条 query 结果数；
- 显示新闻、专利、论文数量；
- 显示数量校验是否通过；
- 下载 raw JSON、raw Excel 和 Markdown 专题报告；
- 预览专题报告。

## 6. 输出报告结构

Markdown 报告包含：

1. 本期结论；
2. 新闻 / 公司动态；
3. 专利动态；
4. 论文 / 学术进展；
5. 技术路线判断；
6. 对 FPC 研发的启示。

摘要禁止使用：

- “公开材料显示”
- “公开资料显示”
- “资料未提供足够细节”
- “暂不能确认更多参数”
- “仅记录已披露动作”
- “需要进一步核实结构细节”

当前实现会优先抽取中文事实句；英文搜索摘要不会直接整句进入报告，而是按主体、技术对象、动作、关键数字和 FPC 参考点重组为中文短摘要。明显低质量来源、聚合新闻稿、泛产品页和与机器人力控/触觉无关的论文会被过滤。

## 7. 2026-06-22 真实验证记录

运行命令：

```bash
python -m strain_gauge_intelligence.collector --provider exa --max-queries-per-type 6 --results-per-query 6 --overwrite
```

输出文件：

- `data/strain_gauge_intelligence/raw/strain_gauge_module_2026-06-22.json`
- `data/strain_gauge_intelligence/raw/strain_gauge_module_2026-06-22.xlsx`
- `data/strain_gauge_intelligence/reports/strain_gauge_force_sensor_report_2026-06-22.md`

真实结果：

| 类型 | 数量 |
| --- | ---: |
| 新闻 / 公司动态 | 7 |
| 专利动态 | 0 |
| 论文 / 学术进展 | 4 |

数量校验：未通过。

原因：

- 新闻和论文已超过最低要求。
- 专利普通 Exa 检索召回了 CNIPA 公告、新闻页和 USPTO 通知页，但缺少可解析到具体公开号/申请人/公开日的高相关专利条目。
- Google Patents XHR 兜底在本次运行中出现 503 或无可用结果，因此没有把不足专利硬补为正式条目。
- 由于本次收紧了低质量来源和泛产品页过滤，最终保留数量低于早期宽松版本，但更符合“不凑数”的要求。

后续建议：

- 增加可稳定访问的专利 API 或人工维护的专利检索源，例如 Lens、PatentsView、CNIPA 批量检索或企业专利监控服务。
- 对专利类结果单独开发页面解析器，不再依赖普通新闻搜索返回片段。
- 对新闻源增加更严格质量分级，降低聚合站和泛产业站权重。
- 对论文条目增加作者/机构和实验指标抽取增强，必要时引入正文抓取或 LLM 结构化抽取。
