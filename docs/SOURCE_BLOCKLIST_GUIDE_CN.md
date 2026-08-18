# 信息源屏蔽操作指南

## 1. 作用范围

信息源门禁是搜索供应商无关的公共能力，适用于：

- 频道一公司追踪及最终标题二次搜索；
- 频道二行业扫描；
- 频道三消费电子检索及事件验证搜索；
- 频道四 PWG 情报采集；
- 应变片 / 六轴力传感器专题。

它不修改 Exa、Tavily 的选择逻辑，也不改变各频道后续的时间、相关性、来源等级和数量规则。

## 2. 三层门禁

1. 内置域名规则：`tools/source_blocklist.json` 保存自动聚合、低可信转载入口和非正文平台。
2. 手动域名规则：Streamlit 侧栏可按当前运行需要增加域名。
3. 自动内容声明：结果标题或摘要明确包含“机器人自动生成”“AI 自动生成”“RSS 自动聚合”等强标记时直接剔除。

Exa 和 Tavily 支持域名排除时，系统会在请求中提前发送排除名单；所有返回结果还会再执行一次本地检查，防止供应商忽略参数或返回异常域名。

## 3. 前端添加域名

启动前端：

```powershell
streamlit run agent_app.py
```

在侧栏展开 `信息源屏蔽`，将域名或完整 URL 粘贴到 `手动屏蔽网站`。支持换行、逗号和分号分隔，例如：

```text
spam.example.com
https://robot.example.org/news/123
```

规则会自动移除协议、端口、路径、查询参数、`www.` 和 `*.`。屏蔽 `example.com` 时也会屏蔽 `news.example.com`，但不会误伤 `notexample.com`。无效输入会在界面明确提示并忽略。

## 4. 持久配置

可以在 `.streamlit/secrets.toml` 或环境变量中设置：

```toml
NEWS_BLOCKED_DOMAINS = "spam.example.com,robot.example.org"
```

也可运行 `python setup_api_keys.py` 填写该设置。前端首次打开时会加载持久配置，之后允许在当前 Streamlit 会话中编辑。

## 5. 维护内置名单

内置规则必须在 `tools/source_blocklist.json` 中维护，不要把站点散落硬编码到频道代码。每条规则包含：

- `domain`：规范域名；
- `category`：`automated_aggregator`、`low_trust_republisher`、`low_trust_content_farm` 或 `non_article_platform`；
- `reason`：可审计的屏蔽原因。

新增永久规则前应确认该域名整体属于自动聚合或低可信转载入口。仅个别文章质量差、但站点仍可能发布原始资料时，应继续使用来源降权或人工复核，不宜直接全域封禁。

## 6. 诊断与测试

频道一、二、三完成运行后，“搜索引擎状态”会显示本次拦截总数、主要域名和抽样原因。底层诊断字段为：

```text
diagnostics.source_blocking.blocked_count
diagnostics.source_blocking.by_domain
diagnostics.source_blocking.by_category
diagnostics.source_blocking.samples
```

专项测试：

```powershell
python tests/test_source_blocklist.py
```

测试覆盖域名规范化、子域名边界、手动 URL 粘贴、机器人声明、供应商请求参数、本地复检和前端静态接线。
