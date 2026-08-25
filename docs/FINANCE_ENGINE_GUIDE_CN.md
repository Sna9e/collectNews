# 上市公司金融数据与图表操作指南

## 1. 作用范围

金融链只在 Streamlit 频道一启用 `上市公司金融补链` 时运行。新闻检索、摘要生成和短长新闻关联不依赖金融数据；行情源全部失效时，频道一新闻仍可生成，金融页会显示明确的不可用原因。

## 2. 证券注册表

上市状态和代码统一维护在：

```text
tools/finance_registry.json
```

每条记录包含：

| 字段 | 含义 |
|---|---|
| `canonical_name` | 页面与诊断使用的标准公司名 |
| `aliases` | 中英文别名或常用代码 |
| `status` | `listed`、`pending_listing`、`private` |
| `ticker` | 已核验的 Yahoo 兼容代码；未上市时必须为空 |
| `exchange` | 交易所，例如 `NASDAQ` |
| `currency` | 报价币种 |
| `listed_date` | 已确认上市日期，可选 |
| `verification_source` | 交易所或监管文件链接，可选但建议填写 |

当前 SpaceX 配置为 `NASDAQ: SPCX`。OpenAI、Anthropic 为 `pending_listing`，系统不会让模型为已登记的待上市公司猜测代码。

未来公司正式上市后，只在权威来源确认代码后修改对应记录，例如：

```json
{
  "canonical_name": "Example Company",
  "aliases": ["示例公司"],
  "status": "listed",
  "ticker": "EXMP",
  "exchange": "NASDAQ",
  "currency": "USD",
  "listed_date": "YYYY-MM-DD",
  "verification_source": "https://权威来源"
}
```

修改后重启 Streamlit，或在测试中调用 `clear_finance_registry_cache()`。

## 3. 数据源顺序

美股默认：

```text
Yahoo Chart JSON → Stooq CSV → Tencent → yfinance history/fast_info
```

A 股和港股默认：

```text
Tencent → Yahoo Chart JSON → Stooq CSV → yfinance history/fast_info
```

系统不再使用需要首页 Cookie 的雪球接口。每个公开接口执行有限重试和超时；不会绕过登录、验证码、付费墙或访问控制。成功结果缓存 15 分钟，避免同一批报告重复请求。

返回值中的 `provider_attempts` 会记录每个已尝试数据源、是否成功、耗时和简短原因。`data_source` 是最终命中的来源，`cache_hit` 表示是否复用缓存。

## 4. 数据与图表校验

历史行情进入图表前统一执行：

1. 检查 `Open/High/Low/Close` 列；
2. 将价格和成交量转为数值；
3. 将日期转为统一时间索引；
4. 删除无效日期和缺少 OHLC 的行；
5. 按日期排序并删除重复交易日；
6. 最多保留最近 90 条有效记录。

图表默认写入：

```text
data/cache/finance_charts/
```

优先生成蜡烛图、成交量和可用均线。`mplfinance` 不可用或绘图失败时，使用 Matplotlib 生成收盘价与成交量降级图。只有两种方式都失败时，`chart_path` 才为空。

Yahoo 的 `chartPreviousClose` 是查询区间之前的基准价，不是上一交易日收盘价。当前实现只使用真正的 `previousClose`；该字段缺失时，使用有效日线倒数第二条 `Close` 计算日涨跌幅。

## 5. SpaceX 当前验证

截至 2026-08-24，本地真实公开接口验证结果：

- 证券：`SPCX`；
- 命中源：`yahoo_chart`；
- 历史交易日：23 条；
- 图表：`data/cache/finance_charts/kline_SPCX.png`；
- PPT：`validation_outputs/finance_spcx_public_smoke.pptx`。

价格和涨跌幅属于动态市场数据，不应复制为长期静态结论。SpaceX 上市状态依据 SEC 文件与 Nasdaq 官方页面；注册表内保存 SEC 核验链接。

## 6. 验证命令

```powershell
python tests/test_finance_engine.py
python -m py_compile tools/finance_engine.py agent_app.py tools/export_ppt.py
```

真实公共行情烟测不需要模型 Key：

```powershell
python -c "from tools.finance_engine import fetch_financial_data; print(fetch_financial_data(type('A', (), {'valid': False})(), 'SpaceX'))"
```

若 `data_available=false`，先查看 `provider_attempts`，不要通过增加伪造价格或关闭校验来补图。

## 7. 已知边界

- Yahoo、Stooq、Tencent 和 `yfinance` 均没有为本项目提供服务等级承诺；多源降级降低失败概率，但不能保证任何时间都可用。
- 新上市首日、停牌、代码变更、特殊证券和部分地区代码可能缺少足够日线，图表会诚实地保持为空。
- 当前公开接口不稳定提供 PE、PB 和市值。缺失时页面显示 `N/A`，不得根据价格自行推算。
- `pending_listing` 只表示系统需要持续观察，不表示已获批准、已定价或已有正式代码。
