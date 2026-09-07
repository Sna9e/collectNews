import pathlib
import sys
from types import SimpleNamespace

from pydantic import BaseModel


ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.llm_driver import (  # noqa: E402
    AI_Driver,
    DEFAULT_OPENROUTER_BASE_URL,
    DEFAULT_OPENROUTER_MODEL,
    OpenRouterModelInfo,
    build_openrouter_model_options,
    fetch_openrouter_model_catalog,
    find_openrouter_model_info,
    normalize_model_base_url,
)


class StubReport(BaseModel):
    items: list[str]


class FakeCompletions:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=response))]
        )


class FakeClientFactory:
    def __init__(self, responses):
        self.completions = FakeCompletions(responses)
        self.constructor_kwargs = None

    def __call__(self, **kwargs):
        self.constructor_kwargs = kwargs
        return SimpleNamespace(chat=SimpleNamespace(completions=self.completions))


class FakeHttpResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def make_model_info(
    model_id,
    supported_parameters,
    context_length=128000,
    max_completion_tokens=4096,
    name="Test Model",
):
    return OpenRouterModelInfo(
        model_id=model_id,
        name=name,
        context_length=context_length,
        max_completion_tokens=max_completion_tokens,
        supported_parameters=tuple(supported_parameters),
        input_modalities=("text",),
        output_modalities=("text",),
    )


def test_openrouter_defaults_endpoint_normalization_and_arbitrary_model_options():
    custom_model = "vendor/custom-chat-model"
    catalog_model = make_model_info("openai/example-model", ("max_tokens",))

    options = build_openrouter_model_options((catalog_model,), custom_model)

    assert DEFAULT_OPENROUTER_MODEL == "qwen/qwen3.7-flash"
    assert DEFAULT_OPENROUTER_BASE_URL == "https://openrouter.ai/api/v1"
    assert normalize_model_base_url(
        "https://openrouter.ai/api/v1/chat/completions/"
    ) == DEFAULT_OPENROUTER_BASE_URL
    assert options[0] == custom_model
    assert DEFAULT_OPENROUTER_MODEL in options
    assert catalog_model.model_id in options
    assert options[-1] == "__custom__"


def test_openrouter_catalog_parses_capabilities_and_filters_non_text_models():
    http_calls = []

    def fake_http_get(url, **kwargs):
        http_calls.append((url, kwargs))
        return FakeHttpResponse(
            {
                "data": [
                    {
                        "id": "vendor/text-model",
                        "name": "Vendor Text Model",
                        "context_length": 200000,
                        "supported_parameters": ["max_tokens", "response_format", "reasoning"],
                        "architecture": {
                            "input_modalities": ["text", "image"],
                            "output_modalities": ["text"],
                        },
                        "top_provider": {"max_completion_tokens": 12000},
                    },
                    {
                        "id": "vendor/audio-only-model",
                        "name": "Audio Only",
                        "architecture": {
                            "input_modalities": ["audio"],
                            "output_modalities": ["text"],
                        },
                    },
                ]
            }
        )

    catalog = fetch_openrouter_model_catalog(
        api_key="catalog-key",
        http_get=fake_http_get,
    )

    assert len(catalog) == 1
    assert catalog[0].model_id == "vendor/text-model"
    assert catalog[0].context_length == 200000
    assert catalog[0].max_completion_tokens == 12000
    assert catalog[0].supports("reasoning")
    assert find_openrouter_model_info(catalog, "vendor/text-model") == catalog[0]
    assert http_calls[0][0] == "https://openrouter.ai/api/v1/models"
    assert http_calls[0][1]["params"] == {
        "output_modalities": "text",
        "sort": "most-popular",
    }
    assert http_calls[0][1]["headers"]["Authorization"] == "Bearer catalog-key"


def test_capability_aware_structured_request_and_output_limit_clamp():
    model_info = make_model_info(
        DEFAULT_OPENROUTER_MODEL,
        ("max_tokens", "reasoning", "response_format", "temperature", "tools"),
        max_completion_tokens=4096,
        name="Qwen3.7 Flash",
    )
    factory = FakeClientFactory(["```json\n{\"items\": [\"有效新闻\"]}\n```"])
    driver = AI_Driver(
        "test-key",
        DEFAULT_OPENROUTER_MODEL,
        provider="openrouter",
        model_info=model_info,
        client_factory=factory,
    )

    report = driver.analyze_structural("提取新闻并返回 JSON", StubReport)

    assert report.items == ["有效新闻"]
    assert driver.label == "OpenRouter/qwen/qwen3.7-flash"
    assert factory.constructor_kwargs["base_url"] == DEFAULT_OPENROUTER_BASE_URL
    request = factory.completions.calls[0]
    assert request["response_format"] == {"type": "json_object"}
    assert request["extra_body"] == {
        "provider": {"require_parameters": True},
        "reasoning": {"effort": "none", "exclude": True},
    }
    assert request["max_tokens"] == 4096
    assert request["temperature"] == 0.1
    assert "JSON Schema" in request["messages"][0]["content"]


def test_strict_structured_output_is_preferred_then_falls_back_to_json_mode():
    model_id = "vendor/strict-model"
    model_info = make_model_info(
        model_id,
        ("max_tokens", "response_format", "structured_outputs", "temperature"),
    )
    factory = FakeClientFactory(
        [
            ValueError("json_schema strict mode is not supported by the selected endpoint"),
            '{"items": ["JSON mode 回退成功"]}',
        ]
    )
    driver = AI_Driver(
        "test-key",
        model_id,
        provider="openrouter",
        reasoning_effort="auto",
        model_info=model_info,
        client_factory=factory,
    )

    report = driver.analyze_structural("返回 JSON", StubReport)

    assert report.items == ["JSON mode 回退成功"]
    first_format = factory.completions.calls[0]["response_format"]
    second_format = factory.completions.calls[1]["response_format"]
    assert first_format["type"] == "json_schema"
    assert first_format["json_schema"]["strict"] is True
    assert first_format["json_schema"]["schema"] == StubReport.model_json_schema()
    assert second_format == {"type": "json_object"}


def test_known_limited_model_omits_unsupported_parameters_without_retry():
    model_id = "vendor/limited-model"
    model_info = make_model_info(
        model_id,
        ("max_tokens",),
        max_completion_tokens=2048,
    )
    factory = FakeClientFactory(['{"items": ["本地 JSON 校验成功"]}'])
    driver = AI_Driver(
        "test-key",
        model_id,
        provider="openrouter",
        reasoning_effort="high",
        model_info=model_info,
        client_factory=factory,
    )

    report = driver.analyze_structural("返回 JSON", StubReport)

    assert report.items == ["本地 JSON 校验成功"]
    assert len(factory.completions.calls) == 1
    request = factory.completions.calls[0]
    assert request["max_tokens"] == 2048
    assert request["extra_body"] == {"provider": {"require_parameters": True}}
    assert "response_format" not in request
    assert "temperature" not in request


def test_unknown_model_retries_without_rejected_response_format():
    factory = FakeClientFactory(
        [
            ValueError("unsupported parameter: response_format"),
            '{"items": ["回退成功"]}',
        ]
    )
    driver = AI_Driver(
        "test-key",
        "vendor/catalog-miss-model",
        provider="openrouter",
        client_factory=factory,
    )

    report = driver.analyze_structural("返回 JSON", StubReport)

    assert report.items == ["回退成功"]
    assert len(factory.completions.calls) == 2
    assert "response_format" in factory.completions.calls[0]
    assert "response_format" not in factory.completions.calls[1]
    assert "reasoning" in factory.completions.calls[1]["extra_body"]


def test_unknown_model_retries_without_rejected_reasoning():
    factory = FakeClientFactory(
        [
            ValueError("No endpoints found that support reasoning"),
            '{"items": ["无推理参数成功"]}',
        ]
    )
    driver = AI_Driver(
        "test-key",
        "vendor/another-model",
        provider="openrouter",
        reasoning_effort="high",
        client_factory=factory,
    )

    report = driver.analyze_structural("返回 JSON", StubReport)

    assert report.items == ["无推理参数成功"]
    assert "reasoning" in factory.completions.calls[0]["extra_body"]
    assert "reasoning" not in factory.completions.calls[1]["extra_body"]
    assert "response_format" in factory.completions.calls[1]


def test_auto_reasoning_omits_reasoning_parameter_and_xhigh_is_accepted():
    auto_factory = FakeClientFactory(['{"items": ["自动"]}'])
    auto_driver = AI_Driver(
        "test-key",
        "vendor/auto-model",
        provider="openrouter",
        reasoning_effort="auto",
        client_factory=auto_factory,
    )
    xhigh_factory = FakeClientFactory(['{"items": ["极高"]}'])
    xhigh_driver = AI_Driver(
        "test-key",
        "vendor/xhigh-model",
        provider="openrouter",
        reasoning_effort="xhigh",
        client_factory=xhigh_factory,
    )

    assert auto_driver.analyze_structural("返回 JSON", StubReport).items == ["自动"]
    assert xhigh_driver.analyze_structural("返回 JSON", StubReport).items == ["极高"]
    assert "reasoning" not in auto_factory.completions.calls[0]["extra_body"]
    assert xhigh_factory.completions.calls[0]["extra_body"]["reasoning"]["effort"] == "xhigh"


def test_deepseek_provider_stays_disabled_even_with_explicit_base_url():
    factory = FakeClientFactory(['{"items": []}'])
    driver = AI_Driver(
        "legacy-key",
        "deepseek-chat",
        provider="deepseek",
        base_url="https://api.deepseek.com",
        client_factory=factory,
    )

    assert driver.valid is False
    assert driver.base_url == ""
    assert factory.constructor_kwargs is None


def test_frontend_and_outputs_are_openrouter_model_neutral():
    source = (ROOT / "agent_app.py").read_text(encoding="utf-8")
    qa_source = (ROOT / "agents" / "qa_agent.py").read_text(encoding="utf-8")
    setup_source = (ROOT / "setup_api_keys.py").read_text(encoding="utf-8")
    word_source = (ROOT / "tools" / "export_word.py").read_text(encoding="utf-8")

    assert '_get_runtime_secret("DEEPSEEK_API_KEY"' not in source
    assert '_get_runtime_secret("DASHSCOPE_API_KEY"' not in source
    assert '_get_runtime_secret("QWEN_API_KEY"' not in source
    assert 'provider="deepseek"' not in source
    assert '_get_runtime_secret("OPENROUTER_API_KEY"' in source
    assert "OpenRouter 核心模型（可搜索）" in source
    assert "fetch_openrouter_model_catalog" in source
    assert "openrouter_model_info=openrouter_model_info" in source
    assert "OpenRouter Qwen 核心模型" not in source
    assert "Qwen3.7 Flash 主模型暂不可用" not in source
    assert "ai_driver.complete_text(" in qa_source
    assert "ai_driver.client.chat.completions.create(" not in qa_source
    assert '"auto", "none", "minimal", "low", "medium", "high", "xhigh"' in setup_source
    assert "AI 企业级深度科技研报" in word_source


def test_streamlit_uses_server_secrets_fixed_endpoint_and_openrouter_only_ui():
    source = (ROOT / "agent_app.py").read_text(encoding="utf-8")
    setup_source = (ROOT / "setup_api_keys.py").read_text(encoding="utf-8")

    assert 'openrouter_key = _get_runtime_secret("OPENROUTER_API_KEY", "")' in source
    assert "openrouter_base_url = DEFAULT_OPENROUTER_BASE_URL" in source
    assert '_get_runtime_secret("OPENROUTER_BASE_URL"' not in source
    assert '"OpenRouter API Key（仅当前会话）"' not in source
    assert 'key="openrouter_api_key_input"' not in source
    assert '"OpenRouter API 地址"' not in source
    assert '"OpenRouter 模型推理设置"' not in source
    assert '_get_runtime_secret("GEMINI_API_KEY"' not in source
    assert '_get_runtime_secret("GOOGLE_API_KEY"' not in source
    assert 'key="use_gemini_main"' not in source
    assert 'key="use_gemini_light"' not in source
    assert '"Gemini 主模型"' not in source
    assert '"Gemini 轻任务模型"' not in source
    assert '"OpenRouter 核心模型（可搜索）"' in source
    assert "st.write(openrouter_key" not in source
    assert "st.code(openrouter_key" not in source
    assert '"OPENROUTER_BASE_URL": {' not in setup_source
    assert '"OPENROUTER_BASE_URL",' in setup_source


def run_all():
    tests = [
        test_openrouter_defaults_endpoint_normalization_and_arbitrary_model_options,
        test_openrouter_catalog_parses_capabilities_and_filters_non_text_models,
        test_capability_aware_structured_request_and_output_limit_clamp,
        test_strict_structured_output_is_preferred_then_falls_back_to_json_mode,
        test_known_limited_model_omits_unsupported_parameters_without_retry,
        test_unknown_model_retries_without_rejected_response_format,
        test_unknown_model_retries_without_rejected_reasoning,
        test_auto_reasoning_omits_reasoning_parameter_and_xhigh_is_accepted,
        test_deepseek_provider_stays_disabled_even_with_explicit_base_url,
        test_frontend_and_outputs_are_openrouter_model_neutral,
        test_streamlit_uses_server_secrets_fixed_endpoint_and_openrouter_only_ui,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")


if __name__ == "__main__":
    run_all()
