import json
from dataclasses import dataclass

import requests
from openai import OpenAI


DEFAULT_OPENROUTER_MODEL = "qwen/qwen3.7-flash"
DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_REASONING_EFFORTS = (
    "auto",
    "none",
    "minimal",
    "low",
    "medium",
    "high",
    "xhigh",
)
DEFAULT_OPENROUTER_REASONING_EFFORT = "none"
DEFAULT_OPENROUTER_MAX_TOKENS = 8192
DEFAULT_REQUEST_TIMEOUT_SECONDS = 120.0
DEFAULT_REQUEST_RETRIES = 2
DEFAULT_MODEL_CATALOG_TIMEOUT_SECONDS = 8.0


def normalize_model_base_url(base_url):
    value = str(base_url or "").strip().rstrip("/")
    suffix = "/chat/completions"
    if value.lower().endswith(suffix):
        value = value[: -len(suffix)].rstrip("/")
    return value


def _positive_int(value):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


@dataclass(frozen=True)
class OpenRouterModelInfo:
    model_id: str
    name: str
    context_length: int | None
    max_completion_tokens: int | None
    supported_parameters: tuple[str, ...]
    input_modalities: tuple[str, ...]
    output_modalities: tuple[str, ...]
    expiration_date: str = ""

    @classmethod
    def from_api(cls, payload):
        payload = payload if isinstance(payload, dict) else {}
        architecture = payload.get("architecture") or {}
        top_provider = payload.get("top_provider") or {}
        model_id = str(payload.get("id") or "").strip()
        name = str(payload.get("name") or model_id).strip() or model_id
        supported_parameters = tuple(
            sorted(
                {
                    str(parameter).strip()
                    for parameter in payload.get("supported_parameters") or []
                    if str(parameter).strip()
                }
            )
        )
        input_modalities = tuple(
            str(modality).strip().lower()
            for modality in architecture.get("input_modalities") or []
            if str(modality).strip()
        )
        output_modalities = tuple(
            str(modality).strip().lower()
            for modality in architecture.get("output_modalities") or []
            if str(modality).strip()
        )
        return cls(
            model_id=model_id,
            name=name,
            context_length=_positive_int(payload.get("context_length")),
            max_completion_tokens=_positive_int(top_provider.get("max_completion_tokens")),
            supported_parameters=supported_parameters,
            input_modalities=input_modalities,
            output_modalities=output_modalities,
            expiration_date=str(payload.get("expiration_date") or "").strip(),
        )

    def supports(self, parameter):
        return str(parameter or "").strip() in self.supported_parameters

    @property
    def accepts_text(self):
        return not self.input_modalities or "text" in self.input_modalities

    @property
    def returns_text(self):
        return not self.output_modalities or "text" in self.output_modalities


def fetch_openrouter_model_catalog(
    base_url=DEFAULT_OPENROUTER_BASE_URL,
    api_key="",
    timeout_seconds=DEFAULT_MODEL_CATALOG_TIMEOUT_SECONDS,
    http_get=requests.get,
):
    normalized_base_url = normalize_model_base_url(base_url) or DEFAULT_OPENROUTER_BASE_URL
    headers = {
        "Accept": "application/json",
        "User-Agent": "collectNews-openrouter-model-catalog/1.0",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    response = http_get(
        f"{normalized_base_url}/models",
        headers=headers,
        params={"output_modalities": "text", "sort": "most-popular"},
        timeout=float(timeout_seconds),
    )
    response.raise_for_status()
    payload = response.json()
    rows = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise ValueError("OpenRouter models response does not contain a data list.")

    catalog = []
    seen_model_ids = set()
    for row in rows:
        model_info = OpenRouterModelInfo.from_api(row)
        if not model_info.model_id or model_info.model_id in seen_model_ids:
            continue
        if not model_info.accepts_text or not model_info.returns_text:
            continue
        seen_model_ids.add(model_info.model_id)
        catalog.append(model_info)
    if not catalog:
        raise ValueError("OpenRouter returned no text chat models.")
    return tuple(catalog)


def build_openrouter_model_options(model_catalog, configured_model=DEFAULT_OPENROUTER_MODEL):
    options = []
    seen = set()

    def add(model_id):
        normalized = str(model_id or "").strip()
        if normalized and normalized not in seen and normalized != "__custom__":
            seen.add(normalized)
            options.append(normalized)

    add(configured_model)
    add(DEFAULT_OPENROUTER_MODEL)
    for model_info in model_catalog or ():
        add(getattr(model_info, "model_id", ""))
    options.append("__custom__")
    return tuple(options)


def find_openrouter_model_info(model_catalog, model_id):
    normalized_model_id = str(model_id or "").strip()
    for model_info in model_catalog or ():
        if model_info.model_id == normalized_model_id:
            return model_info
    return None


class AI_Driver:
    def __init__(
        self,
        api_key,
        model_id,
        provider="openrouter",
        base_url="",
        reasoning_effort=DEFAULT_OPENROUTER_REASONING_EFFORT,
        model_info=None,
        timeout_seconds=DEFAULT_REQUEST_TIMEOUT_SECONDS,
        max_retries=DEFAULT_REQUEST_RETRIES,
        client_factory=OpenAI,
    ):
        self.valid = False
        self.provider = str(provider or "").strip().lower()
        self.model_id = str(model_id or "").strip()
        self.base_url = self._resolve_base_url(self.provider, base_url)
        normalized_effort = str(reasoning_effort or "none").strip().lower()
        self.reasoning_effort = (
            normalized_effort if normalized_effort in OPENROUTER_REASONING_EFFORTS else "none"
        )
        self.model_info = (
            model_info
            if isinstance(model_info, OpenRouterModelInfo) and model_info.model_id == self.model_id
            else None
        )
        self.supported_parameters = (
            frozenset(self.model_info.supported_parameters) if self.model_info else None
        )
        self.max_completion_tokens = (
            self.model_info.max_completion_tokens if self.model_info else None
        )
        self.client = None
        if api_key and self.model_id and self.base_url:
            try:
                self.client = client_factory(
                    api_key=api_key,
                    base_url=self.base_url,
                    timeout=float(timeout_seconds),
                    max_retries=int(max_retries),
                )
                self.valid = True
            except Exception as exc:
                print(f"AI client initialization failed for {self.provider}: {exc}")

    @staticmethod
    def _resolve_base_url(provider, base_url=""):
        if provider not in {"openrouter", "gemini"}:
            return ""
        explicit_url = normalize_model_base_url(base_url)
        if explicit_url:
            return explicit_url
        if provider == "openrouter":
            return DEFAULT_OPENROUTER_BASE_URL
        return "https://generativelanguage.googleapis.com/v1beta/openai"

    @property
    def label(self):
        if self.provider == "openrouter":
            return f"OpenRouter/{self.model_id}"
        if self.provider == "gemini":
            return f"Gemini AI Studio/{self.model_id}"
        return f"{self.provider or 'Unknown'}/{self.model_id}"

    def _parameter_supported(self, parameter):
        if self.provider != "openrouter" or self.supported_parameters is None:
            return True
        return parameter in self.supported_parameters

    def _effective_max_tokens(self, requested_max_tokens):
        requested = _positive_int(requested_max_tokens) or DEFAULT_OPENROUTER_MAX_TOKENS
        if self.max_completion_tokens:
            return min(requested, self.max_completion_tokens)
        return requested

    def _build_request_kwargs(
        self,
        messages,
        force_plain_json=False,
        temperature=0.1,
        max_tokens=None,
        json_schema=None,
        schema_name="structured_response",
        disabled_parameters=None,
    ):
        disabled_parameters = set(disabled_parameters or ())
        if max_tokens is None:
            max_tokens = DEFAULT_OPENROUTER_MAX_TOKENS if self.provider == "openrouter" else 4096
        request_kwargs = {
            "model": self.model_id,
            "messages": messages,
        }

        if "temperature" not in disabled_parameters and self._parameter_supported("temperature"):
            request_kwargs["temperature"] = temperature
        if "max_tokens" not in disabled_parameters and self._parameter_supported("max_tokens"):
            request_kwargs["max_tokens"] = self._effective_max_tokens(max_tokens)

        if self.provider == "openrouter":
            extra_body = {"provider": {"require_parameters": True}}
            if (
                self.reasoning_effort != "auto"
                and "reasoning" not in disabled_parameters
                and self._parameter_supported("reasoning")
            ):
                extra_body["reasoning"] = {
                    "effort": self.reasoning_effort,
                    "exclude": True,
                }
            request_kwargs["extra_body"] = extra_body

        if not force_plain_json:
            supports_strict_schema = (
                self.provider == "openrouter"
                and self.supported_parameters is not None
                and "structured_outputs" in self.supported_parameters
            )
            if (
                json_schema
                and supports_strict_schema
                and "structured_outputs" not in disabled_parameters
            ):
                request_kwargs["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": str(schema_name or "structured_response"),
                        "strict": True,
                        "schema": json_schema,
                    },
                }
            elif (
                "response_format" not in disabled_parameters
                and self._parameter_supported("response_format")
            ):
                request_kwargs["response_format"] = {"type": "json_object"}
        return request_kwargs

    @staticmethod
    def _present_optional_parameters(request_kwargs):
        present = {
            parameter for parameter in ("temperature", "max_tokens") if parameter in request_kwargs
        }
        response_format = request_kwargs.get("response_format") or {}
        if response_format.get("type") == "json_schema":
            present.add("structured_outputs")
        elif response_format:
            present.add("response_format")
        extra_body = request_kwargs.get("extra_body") or {}
        if "reasoning" in extra_body:
            present.add("reasoning")
        return present

    @staticmethod
    def _select_unsupported_parameter(exc, request_kwargs):
        message = str(exc or "").lower()
        present = AI_Driver._present_optional_parameters(request_kwargs)
        aliases = {
            "structured_outputs": (
                "structured_outputs",
                "structured output",
                "response_format",
                "json_schema",
                "json schema",
                "strict",
            ),
            "response_format": ("response_format", "json_object", "structured output", "structured_outputs"),
            "reasoning": ("reasoning", "thinking"),
            "temperature": ("temperature",),
            "max_tokens": ("max_tokens", "maximum tokens"),
        }
        for parameter, markers in aliases.items():
            if parameter in present and any(marker in message for marker in markers):
                return parameter

        generic_markers = (
            "unsupported parameter",
            "parameter is not supported",
            "does not support all parameters",
            "no endpoints found that support",
            "require_parameters",
        )
        if any(marker in message for marker in generic_markers):
            for parameter in (
                "reasoning",
                "structured_outputs",
                "response_format",
                "temperature",
                "max_tokens",
            ):
                if parameter in present:
                    return parameter
        return ""

    def _request_completion(
        self,
        messages,
        force_plain_json=False,
        temperature=0.1,
        max_tokens=None,
        json_schema=None,
        schema_name="structured_response",
    ):
        disabled_parameters = set()
        while True:
            request_kwargs = self._build_request_kwargs(
                messages,
                force_plain_json=force_plain_json,
                temperature=temperature,
                max_tokens=max_tokens,
                json_schema=json_schema,
                schema_name=schema_name,
                disabled_parameters=disabled_parameters,
            )
            try:
                return self.client.chat.completions.create(**request_kwargs)
            except Exception as exc:
                unsupported_parameter = self._select_unsupported_parameter(exc, request_kwargs)
                if not unsupported_parameter or unsupported_parameter in disabled_parameters:
                    raise
                disabled_parameters.add(unsupported_parameter)
                print(
                    f"AI request compatibility retry for {self.label}: "
                    f"disabled unsupported parameter {unsupported_parameter}."
                )

    @staticmethod
    def _parse_json_content(content):
        text = str(content or "").strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].strip().lower() in {"```", "```json"}:
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            decoder = json.JSONDecoder()
            for index, char in enumerate(text):
                if char not in "[{":
                    continue
                try:
                    value, _ = decoder.raw_decode(text[index:])
                    return value
                except json.JSONDecodeError:
                    continue
            raise

    def analyze_structural(self, prompt, structure_class):
        if not self.valid:
            return None

        sys_prompt = (
            "必须严格按 JSON 格式返回，不要带任何思考过程或多余文字。"
            f"JSON Schema 如下:\n{json.dumps(structure_class.model_json_schema(), ensure_ascii=False)}"
        )
        messages = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": prompt},
        ]

        try:
            response = self._request_completion(
                messages,
                json_schema=structure_class.model_json_schema(),
                schema_name=structure_class.__name__,
            )
            content = response.choices[0].message.content
            data = self._parse_json_content(content)
            if isinstance(data, list):
                data = {list(structure_class.model_fields.keys())[0]: data}
            return structure_class(**data)
        except Exception as exc:
            print(f"AI structured output failed for {self.label}: {exc}")
            return None

    def complete_text(self, messages, temperature=0.3, max_tokens=1024):
        if not self.valid:
            return ""
        response = self._request_completion(
            messages,
            force_plain_json=True,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return str(response.choices[0].message.content or "").strip()


def build_ai_stack(
    openrouter_key,
    openrouter_model,
    openrouter_base_url=DEFAULT_OPENROUTER_BASE_URL,
    openrouter_reasoning_effort=DEFAULT_OPENROUTER_REASONING_EFFORT,
    openrouter_model_info=None,
    use_gemini_light=False,
    gemini_key="",
    gemini_model="gemini-2.5-flash-lite",
    use_gemini_main=False,
    gemini_main_model="gemini-2.5-flash-lite",
):
    openrouter_driver = AI_Driver(
        openrouter_key,
        openrouter_model,
        provider="openrouter",
        base_url=openrouter_base_url,
        reasoning_effort=openrouter_reasoning_effort,
        model_info=openrouter_model_info,
    )
    heavy_driver = openrouter_driver
    light_driver = heavy_driver
    notices = []

    if use_gemini_main:
        gemini_heavy_driver = AI_Driver(gemini_key, gemini_main_model, provider="gemini")
        if gemini_heavy_driver.valid:
            heavy_driver = gemini_heavy_driver
            light_driver = heavy_driver
            notices.append(f"主模型已切换到 {heavy_driver.label}；当前沿用同一套 Prompt 和输出结构。")
        elif openrouter_driver.valid:
            notices.append(
                "已开启 Gemini AI Studio 主模型，但未检测到可用的 GEMINI_API_KEY / GOOGLE_API_KEY；"
                "本次回退为当前 OpenRouter 主模型。"
            )
        else:
            heavy_driver = gemini_heavy_driver
            light_driver = heavy_driver

    if use_gemini_light:
        gemini_driver = AI_Driver(gemini_key, gemini_model, provider="gemini")
        if gemini_driver.valid:
            if heavy_driver.valid and heavy_driver.provider == "gemini" and heavy_driver.model_id == gemini_model:
                light_driver = heavy_driver
                notices.append(f"轻任务引擎与主模型共用 {light_driver.label}。")
            else:
                light_driver = gemini_driver
                if heavy_driver.provider == "gemini":
                    notices.append(f"主模型使用 {heavy_driver.label}，轻任务使用 {light_driver.label}。")
                else:
                    notices.append(
                        f"轻任务引擎已切换到 {light_driver.label}；"
                        "当前 OpenRouter 模型继续负责最终成稿和金融分析。"
                    )
        else:
            notices.append(
                "已开启 Gemini AI Studio 轻任务引擎，但未检测到可用的 GEMINI_API_KEY / GOOGLE_API_KEY；"
                "本次回退为全 OpenRouter 模型栈。"
            )

    return heavy_driver, light_driver, notices


def format_model_stack_name(heavy_driver, light_driver):
    if light_driver and light_driver.valid and light_driver.provider != heavy_driver.provider:
        return f"{heavy_driver.label} + {light_driver.label}"
    return heavy_driver.label
