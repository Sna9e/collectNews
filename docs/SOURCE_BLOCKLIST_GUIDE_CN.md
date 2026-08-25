# 信息源屏蔽操作指南

## 1. 作用范围

信息源门禁是搜索供应商无关的公共能力，适用于：

- 频道一公司追踪及最终标题二次搜索；
- 频道二行业扫描；
- 频道三消费电子检索及事件验证搜索；
- 频道四 PWG 情报采集；
- 应变片 / 六轴力传感器专题。

它不修改 Exa、Tavily 的选择逻辑，也不改变各频道后续的时间、相关性、来源等级和数量规则。

## 2. 四层门禁

1. 内置域名规则：`tools/source_blocklist.json` 保存自动聚合、低可信转载入口和非正文平台。
2. 永久用户规则：前端保存到 `data/source_blocklist.user.json`，配置 Gist 时同步远端副本。
3. 本次运行临时规则：Streamlit 当前会话可增加域名，也可用 `NEWS_BLOCKED_DOMAINS` 预配置。
4. 自动内容声明：结果标题或摘要明确包含“机器人自动生成”“AI 自动生成”“RSS 自动聚合”等强标记时直接剔除。

Exa 和 Tavily 支持域名排除时，系统会在请求中提前发送排除名单；所有返回结果还会再执行一次本地检查，防止供应商忽略参数或返回异常域名。

## 3. 前端添加域名

启动前端：

```powershell
streamlit run agent_app.py
```

在侧栏展开 `信息源屏蔽`。需要长期保留的域名粘贴到 `永久屏蔽网站`，然后点击 `保存永久名单`；只用于本次页面会话的域名填入 `本次运行临时屏蔽网站`。两者都支持换行、逗号和分号分隔，例如：

```text
spam.example.com
https://robot.example.org/news/123
```

规则会自动移除协议、端口、路径、查询参数、`www.` 和 `*.`。屏蔽 `example.com` 时也会屏蔽 `news.example.com`，但不会误伤 `notexample.com`。无效输入会在界面明确提示并忽略。

删除永久规则时，从文本框删除对应域名并再次点击保存。页面会显示实际保存数量以及本地/Gist 状态；不能只看输入框内容判断是否已保存。

当前内置规则已包含：

```text
bitrss.com
dev.to
vocus.cc
jethrojeff.com
```

## 4. 持久配置与云端恢复

前端永久名单默认原子写入：

```text
data/source_blocklist.user.json
```

本地部署时，该文件可跨 Streamlit 会话和服务重启恢复。若服务器 Secrets 同时配置了 `GITHUB_TOKEN` 与 `GIST_ID`，系统会在同一 Gist 中维护独立文件 `source_blocklist.user.json`，并在新实例启动时优先加载 Gist 后写入本地镜像。Gist 读写失败不会中断检索，但页面会明确显示失败原因。

Streamlit Cloud 的实例文件系统可能重建，因此要实现跨部署/跨实例的永久保存，必须使用具有该 Gist 读写权限的 token。API Key 仍只放在 `App settings → Secrets`，不要粘贴到业务页面。

预配置的临时/服务器规则仍可在 `.streamlit/secrets.toml` 或环境变量中设置：

```toml
NEWS_BLOCKED_DOMAINS = "spam.example.com,robot.example.org"
```

也可运行 `python setup_api_keys.py` 填写该设置。它不会被前端“保存永久名单”覆盖。

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
python tests/test_publication_date_validation.py
```

测试覆盖域名规范化、子域名边界、永久本地/Gist 双写、手动 URL 粘贴、机器人声明、供应商请求参数、本地复检、前端静态接线，以及发布时间证据冲突。

## 7. 发布时间可信度门禁

域名屏蔽之后，频道一最近 24 小时结果还会从以下位置提取发布时间：

1. 实时读取的公开网页 JSON-LD 与 `article:published_time` 等 meta；
2. 搜索结果携带的原始 HTML/正文发布时间标签；
3. URL 中完整的 `YYYY/MM/DD`、`YYYY-MM-DD` 或 `YYYYMMDD` 日期路径；
4. 搜索供应商时间戳。

页面证据优先于供应商时间。相差超过 48 小时会标记 `publication_date_conflict=true`；如果页面或 URL 证据已经超出回溯窗口，该结果会被剔除并写入 warnings。系统只读取公开页面，限制请求数量、超时和响应大小；网站拒绝访问时不会尝试绕过登录、验证码或其他访问控制。

关键诊断字段：

```text
freshness_stats.page_date_checked_count
freshness_stats.page_date_verified_count
freshness_stats.date_conflict_count
freshness_stats.provider_timestamp_only_count
freshness_stats.dropped_timestamp_conflict_count
```
