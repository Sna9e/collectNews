# News
collect last news

## 操作文档

- [信息源屏蔽操作指南](docs/SOURCE_BLOCKLIST_GUIDE_CN.md)
- [上市公司金融数据与图表指南](docs/FINANCE_ENGINE_GUIDE_CN.md)
- [PWG 技术情报操作指南](docs/PWG_INTELLIGENCE_GUIDE_CN.md)
- [应变片 / 六轴力传感器专题指南](docs/STRAIN_GAUGE_SENSOR_MODULE_GUIDE_CN.md)

## Streamlit Secrets 与模型选择

部署到 Streamlit Cloud 后，在应用的 `App settings → Secrets` 中一次性保存服务端密钥，例如：

```toml
OPENROUTER_API_KEY = "sk-or-v1-..."
EXA_API_KEY = "..."
TAVILY_API_KEY = "..."
JINA_API_KEY = "..."
GITHUB_TOKEN = "github_pat_..." # 可选：用于永久屏蔽名单和历史记忆的 Gist 同步
GIST_ID = "..."                 # 可选：目标 Gist ID
```

业务页面不提供 API Key 或 API 地址输入框，也不会把 Secrets 回填到浏览器。OpenRouter 接口固定为 `https://openrouter.ai/api/v1`；前端只负责从模型目录选择模型，或填写一个自定义 OpenRouter 模型 ID。

本地开发使用同样的键名写入 `.streamlit/secrets.toml`，也可通过环境变量提供。Gemini、DeepSeek 和 DashScope Key 不参与当前 Streamlit 应用的模型调用。
