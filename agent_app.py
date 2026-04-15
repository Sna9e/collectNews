import concurrent.futures
import datetime
import difflib
import html
import json
import os
import re
import subprocess
import sys
import tomllib
import traceback
from pathlib import Path

from agents.deep_analyst import map_reduce_analysis
from agents.timeline_agent import build_event_blueprints, generate_timeline
from tools.export_ppt import generate_ppt
from tools.export_word import generate_word
from tools.finance_engine import fetch_financial_data
from tools.company_query_packs import (
    build_company_focus_hint,
    build_company_queries_from_pack,
    get_company_query_pack,
    rank_results_by_company_pack,
)
from tools.intelligence_packs import (
    build_focus_hint,
    get_default_china_sites_text,
    get_default_sites_text,
    get_industry_topics,
    rank_results_by_pack,
)
from tools.memory_manager import GistMemoryManager
from tools.report_linker import annotate_report_data
from tools.search_engine import (
    audit_recent_news_results,
    filter_china_results,
    get_search_diagnostics,
    merge_sites_text,
    reset_search_diagnostics,
    safe_run_async_crawler,
    search_web,
)

_LOCAL_SECRET_CACHE = None


def _looks_like_placeholder_secret(value):
    normalized = str(value or "").strip().lower()
    if not normalized:
        return True
    return (
        normalized.startswith("your-")
        or normalized.startswith("your_")
        or "placeholder" in normalized
        or normalized in {"changeme", "replace-me", "xxx", "xxxxx"}
    )


def _load_local_secret_fallback():
    global _LOCAL_SECRET_CACHE
    if _LOCAL_SECRET_CACHE is not None:
        return _LOCAL_SECRET_CACHE

    candidates = [
        Path(__file__).resolve().parent / ".streamlit" / "secrets.toml",
        Path(__file__).resolve().parent / ".streamlit" / "secrets.toml.example",
    ]
    merged = {}
    for candidate in candidates:
        if not candidate.exists():
            continue
        try:
            raw_text = candidate.read_text(encoding="utf-8-sig")
            data = tomllib.loads(raw_text)
            if isinstance(data, dict):
                merged.update(data)
        except Exception as exc:
            print(f"⚠️ Failed to load local secrets from {candidate}: {exc}")

    _LOCAL_SECRET_CACHE = merged
    return _LOCAL_SECRET_CACHE

import streamlit as st
from openai import OpenAI
from pydantic import BaseModel, Field


st.set_page_config(page_title="DeepSeek 部门情报中心", page_icon="🧠", layout="wide")

SESSION_DEFAULTS = {
    "report_ready": False,
    "word_path": "",
    "ppt_path": "",
    "report_data": [],
    "timeline_data": [],
    "run_metadata": {},
    "report_celebrated": False,
}

LOCAL_TZ = datetime.timezone(datetime.timedelta(hours=8))
EVENT_BLUEPRINT_INPUT_LIMIT_COMPANY = 18
EVENT_BLUEPRINT_INPUT_LIMIT_INDUSTRY = 16
ANALYSIS_EVENT_LIMIT = 8
COMPANY_CRAWL_URL_LIMIT = 10
INDUSTRY_CRAWL_URL_LIMIT = 8
MAX_SOURCE_CHARS_PER_URL = 2400
DEFAULT_GEMINI_LIGHT_MODEL = "gemini-2.5-flash-lite"
DEFAULT_GEMINI_MAIN_MODEL = "gemini-2.5-flash-lite"
GEMINI_3_FLASH_PREVIEW_MODEL = "gemini-3-flash-preview"
# Inference from Google's public model naming pattern + model catalog entry.
# If a specific account has not exposed this preview string yet, users can
# still override it through the custom model field below.
GEMINI_31_FLASH_LITE_PRESET = "gemini-3.1-flash-lite-preview"
GEMINI_MODEL_OPTIONS = [
    "gemini-2.5-flash-lite",
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-flash-latest",
    GEMINI_3_FLASH_PREVIEW_MODEL,
    "__custom__",
]
DEFAULT_SEARCH_PROVIDER = "exa"
DEFAULT_EXA_SEARCH_TYPE = "auto"
DEFAULT_EXA_CATEGORY = "news"
DEFAULT_EXA_RESULT_LIMIT = 10
DEFAULT_EXA_CONTENT_MODE = "highlights"
DEFAULT_EXA_HIGHLIGHTS_CHARS = 2200
DEFAULT_EXA_TEXT_CHARS = 4000
DEFAULT_EXA_INCLUDE_TEXT = ""
DEFAULT_EXA_EXCLUDE_TEXT = ""
HARDTECH_EXA_INCLUDE_TEXT = "chip datacenter optics robotics satellite"
HARDTECH_EXA_EXCLUDE_TEXT = "lawsuit court attorney privacy antitrust"

SEARCH_UI_DEFAULTS = {
    "search_provider": DEFAULT_SEARCH_PROVIDER,
    "exa_search_type": DEFAULT_EXA_SEARCH_TYPE,
    "exa_category": DEFAULT_EXA_CATEGORY,
    "exa_result_limit": DEFAULT_EXA_RESULT_LIMIT,
    "exa_content_mode": DEFAULT_EXA_CONTENT_MODE,
    "exa_highlights_chars": DEFAULT_EXA_HIGHLIGHTS_CHARS,
    "exa_text_chars": DEFAULT_EXA_TEXT_CHARS,
    "exa_include_text": DEFAULT_EXA_INCLUDE_TEXT,
    "exa_exclude_text": DEFAULT_EXA_EXCLUDE_TEXT,
    "use_gemini_main": False,
    "gemini_main_model": DEFAULT_GEMINI_MAIN_MODEL,
    "gemini_main_model_custom": "",
    "use_gemini_light": False,
    "gemini_light_model": DEFAULT_GEMINI_LIGHT_MODEL,
    "gemini_light_model_custom": "",
}

for session_key, default_value in SESSION_DEFAULTS.items():
    if session_key not in st.session_state:
        st.session_state[session_key] = default_value

for session_key, default_value in SEARCH_UI_DEFAULTS.items():
    if session_key not in st.session_state:
        st.session_state[session_key] = default_value


class AI_Driver:
    def __init__(self, api_key, model_id, provider="deepseek"):
        self.valid = False
        self.provider = provider
        self.model_id = model_id
        self.base_url = self._resolve_base_url(provider)
        if api_key and model_id and self.base_url:
            try:
                self.client = OpenAI(api_key=api_key, base_url=self.base_url)
                self.valid = True
            except Exception:
                pass

    @staticmethod
    def _resolve_base_url(provider):
        provider_key = str(provider or "").strip().lower()
        if provider_key == "gemini":
            return "https://generativelanguage.googleapis.com/v1beta/openai/"
        if provider_key == "deepseek":
            return "https://api.deepseek.com"
        return ""

    @property
    def label(self):
        if self.provider == "gemini":
            return f"Gemini AI Studio/{self.model_id}"
        return f"DeepSeek/{self.model_id}"

    def _request_completion(self, messages, force_plain_json=False):
        request_kwargs = {
            "model": self.model_id,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": 4096,
        }
        if not force_plain_json:
            request_kwargs["response_format"] = {"type": "json_object"}
        return self.client.chat.completions.create(**request_kwargs)

    def analyze_structural(self, prompt, structure_class):
        if not self.valid:
            return None

        sys_prompt = (
            "必须严格按 JSON 格式返回，不要带任何思考过程或多余文字。"
            f"JSON Schema 如下:\n{json.dumps(structure_class.model_json_schema(), ensure_ascii=False)}"
        )

        try:
            messages = [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": prompt},
            ]
            try:
                res = self._request_completion(messages)
            except Exception:
                if self.provider != "gemini":
                    raise
                # Gemini OpenAI compatibility is good enough for this workflow,
                # but some accounts/features can reject json_object. Retry once
                # with plain text JSON instructions so the toggle remains non-breaking.
                res = self._request_completion(messages, force_plain_json=True)
            content = res.choices[0].message.content.strip()
            if content.startswith("```"):
                content = content.strip("`").strip()
                if content.lower().startswith("json"):
                    content = content[4:].strip()

            data = json.loads(content)
            if isinstance(data, list):
                data = {list(structure_class.model_fields.keys())[0]: data}
            return structure_class(**data)
        except Exception as e:
            print(f"⚠️ AI 结构化解析失败: {e}")
            return None


def build_ai_stack(
    deepseek_key,
    deepseek_model,
    use_gemini_light=False,
    gemini_key="",
    gemini_model=DEFAULT_GEMINI_LIGHT_MODEL,
    use_gemini_main=False,
    gemini_main_model=DEFAULT_GEMINI_MAIN_MODEL,
):
    deepseek_driver = AI_Driver(deepseek_key, deepseek_model, provider="deepseek")
    heavy_driver = deepseek_driver
    light_driver = heavy_driver
    notices = []

    if use_gemini_main:
        gemini_heavy_driver = AI_Driver(gemini_key, gemini_main_model, provider="gemini")
        if gemini_heavy_driver.valid:
            heavy_driver = gemini_heavy_driver
            light_driver = heavy_driver
            notices.append(
                f"主模型已切换到 {heavy_driver.label}；当前沿用同一套 Prompt 和输出结构。"
            )
        elif deepseek_driver.valid:
            notices.append(
                "已开启 Gemini AI Studio 主模型，但当前未检测到可用的 GEMINI_API_KEY / GOOGLE_API_KEY；本次自动回退为 DeepSeek。"
            )
        else:
            heavy_driver = gemini_heavy_driver
            light_driver = heavy_driver

    if use_gemini_light:
        gemini_driver = AI_Driver(gemini_key, gemini_model, provider="gemini")
        if gemini_driver.valid:
            if heavy_driver.valid and heavy_driver.provider == "gemini" and heavy_driver.model_id == gemini_model:
                light_driver = heavy_driver
                notices.append(
                    f"轻任务引擎与主模型共用 {light_driver.label}。"
                )
            else:
                light_driver = gemini_driver
                if heavy_driver.provider == "gemini":
                    notices.append(
                        f"主模型使用 {heavy_driver.label}，轻任务使用 {light_driver.label}。"
                    )
                else:
                    notices.append(
                        f"轻任务引擎已切换到 {light_driver.label}；DeepSeek 继续负责最终成稿和金融分析。"
                    )
        else:
            notices.append(
                "已开启 Gemini AI Studio 轻任务引擎，但当前未检测到可用的 GEMINI_API_KEY / GOOGLE_API_KEY；本次自动回退为全 DeepSeek。"
            )

    return heavy_driver, light_driver, notices


def format_model_stack_name(heavy_driver, light_driver):
    if light_driver and light_driver.valid and light_driver.provider != heavy_driver.provider:
        return f"{heavy_driver.label} + {light_driver.label}"
    return heavy_driver.label



def normalize_search_provider(provider):
    provider_key = str(provider or DEFAULT_SEARCH_PROVIDER).strip().lower()
    if provider_key in {"tavily", "exa", "hybrid"}:
        return provider_key
    return DEFAULT_SEARCH_PROVIDER



def format_search_provider_label(provider):
    labels = {
        "tavily": "Tavily",
        "exa": "Exa",
        "hybrid": "Exa + Tavily",
    }
    return labels.get(normalize_search_provider(provider), "Tavily")



def format_search_provider_option(provider):
    labels = {
        "exa": "Exa（推荐默认）",
        "hybrid": "混合（Exa + Tavily）",
        "tavily": "Tavily",
    }
    return labels.get(normalize_search_provider(provider), "Exa（推荐默认）")


def format_gemini_model_option(model_name):
    labels = {
        "gemini-2.5-flash-lite": "Gemini 2.5 Flash-Lite",
        "gemini-2.5-flash": "Gemini 2.5 Flash",
        "gemini-2.5-pro": "Gemini 2.5 Pro",
        "gemini-flash-latest": "Gemini Flash Latest（滚动别名）",
        GEMINI_3_FLASH_PREVIEW_MODEL: "Gemini 3 Flash Preview",
        "__custom__": "自定义模型 ID",
    }
    return labels.get(model_name, model_name)


def resolve_gemini_model_name(selected_model, custom_model, fallback_model):
    if selected_model == "__custom__":
        custom_value = str(custom_model or "").strip()
        return custom_value or fallback_model
    return str(selected_model or fallback_model).strip() or fallback_model



def apply_exa_default_preset():
    st.session_state.search_provider = DEFAULT_SEARCH_PROVIDER
    st.session_state.exa_search_type = DEFAULT_EXA_SEARCH_TYPE
    st.session_state.exa_category = DEFAULT_EXA_CATEGORY
    st.session_state.exa_result_limit = DEFAULT_EXA_RESULT_LIMIT
    st.session_state.exa_content_mode = DEFAULT_EXA_CONTENT_MODE
    st.session_state.exa_highlights_chars = DEFAULT_EXA_HIGHLIGHTS_CHARS
    st.session_state.exa_text_chars = DEFAULT_EXA_TEXT_CHARS
    st.session_state.exa_include_text = DEFAULT_EXA_INCLUDE_TEXT
    st.session_state.exa_exclude_text = DEFAULT_EXA_EXCLUDE_TEXT



def apply_exa_hardtech_preset():
    apply_exa_default_preset()
    st.session_state.search_provider = "exa"
    st.session_state.exa_include_text = HARDTECH_EXA_INCLUDE_TEXT
    st.session_state.exa_exclude_text = HARDTECH_EXA_EXCLUDE_TEXT


def apply_gemini_3_flash_main_preset():
    st.session_state.use_gemini_main = True
    st.session_state.gemini_main_model = GEMINI_3_FLASH_PREVIEW_MODEL
    st.session_state.gemini_main_model_custom = ""


def apply_gemini_31_flash_lite_main_preset():
    st.session_state.use_gemini_main = True
    st.session_state.gemini_main_model = "__custom__"
    st.session_state.gemini_main_model_custom = GEMINI_31_FLASH_LITE_PRESET



def build_run_metadata(requested_provider, resolved_provider, notices, diagnostics):
    diagnostics = diagnostics or {}
    providers = diagnostics.get("providers", {}) or {}
    fallback_triggered = bool(notices)

    if requested_provider == "exa" and providers.get("exa", {}).get("failure", 0) > 0:
        fallback_triggered = True
    if requested_provider == "hybrid":
        exa_failures = providers.get("exa", {}).get("failure", 0)
        tavily_success = providers.get("tavily", {}).get("success", 0)
        if exa_failures > 0 and tavily_success > 0:
            fallback_triggered = True

    return {
        "requested_provider": normalize_search_provider(requested_provider),
        "resolved_provider": normalize_search_provider(resolved_provider),
        "notices": list(notices or []),
        "diagnostics": diagnostics,
        "fallback_triggered": bool(fallback_triggered),
    }



def render_search_runtime_panel(run_metadata):
    meta = dict(run_metadata or {})
    if not meta:
        return

    requested_label = format_search_provider_label(meta.get("requested_provider"))
    resolved_label = format_search_provider_label(meta.get("resolved_provider"))
    diagnostics = meta.get("diagnostics", {}) or {}
    providers = diagnostics.get("providers", {}) or {}

    summary_parts = [
        f"请求引擎：{requested_label}",
        f"实际启用：{resolved_label}",
        f"是否回退：{'是' if meta.get('fallback_triggered') else '否'}",
    ]
    st.markdown("### 搜索引擎状态")
    st.info(" | ".join(summary_parts))

    provider_parts = []
    for provider_key in ("exa", "tavily"):
        stats = providers.get(provider_key, {})
        if not stats:
            continue
        provider_parts.append(
            f"{format_search_provider_label(provider_key)} 成功 {int(stats.get('success', 0) or 0)} 次 / "
            f"失败 {int(stats.get('failure', 0) or 0)} 次 / 结果 {int(stats.get('result_count', 0) or 0)} 条"
        )
    if provider_parts:
        st.caption("；".join(provider_parts))

    for notice in meta.get("notices", []) or []:
        st.warning(notice)

    failures = diagnostics.get("failures", []) or []
    if failures:
        top_failure = failures[0]
        provider_label = format_search_provider_label(top_failure.get("provider"))
        failure_detail = str(top_failure.get("detail", "") or "")[:240]
        st.caption(f"最近一次失败：{provider_label} | {failure_detail}")



def resolve_search_provider(selected_provider, tavily_key, exa_key):
    provider = normalize_search_provider(selected_provider)
    notices = []

    if provider == "hybrid":
        if tavily_key and exa_key:
            return "hybrid", notices
        if exa_key:
            notices.append("已选择 Tavily + Exa 混合搜索，但当前未检测到 TAVILY_API_KEY，本次自动退回为 Exa。")
            return "exa", notices
        if tavily_key:
            notices.append("已选择 Tavily + Exa 混合搜索，但当前未检测到 EXA_API_KEY，本次自动退回为 Tavily。")
            return "tavily", notices
        notices.append("当前既没有 TAVILY_API_KEY，也没有 EXA_API_KEY，本次无法执行搜索。")
        return "", notices

    if provider == "exa":
        if exa_key:
            return "exa", notices
        if tavily_key:
            notices.append("已选择 Exa 搜索，但当前未检测到 EXA_API_KEY，本次自动退回为 Tavily。")
            return "tavily", notices
        notices.append("当前没有 EXA_API_KEY，且无可回退的 Tavily 引擎。")
        return "", notices

    if tavily_key:
        return "tavily", notices
    if exa_key:
        notices.append("已选择 Tavily 搜索，但当前未检测到 TAVILY_API_KEY，本次自动退回为 Exa。")
        return "exa", notices
    notices.append("当前没有 TAVILY_API_KEY，且无可回退的 Exa 引擎。")
    return "", notices


class FinanceCatalysts(BaseModel):
    policy: str = Field(description="【政策发布】限40字")
    earnings: str = Field(description="【财报表现】限40字")
    landmark: str = Field(description="【产业标志】限40字")
    style: str = Field(description="【市场风格轮动】限40字")



def get_finance_catalysts(ai_driver, topic, news_text):
    prompt = (
        f"你是中金投研分析师。请基于以下关于【{topic}】的新闻，"
        f"提炼近期二级市场的核心催化剂：\n{news_text}"
    )
    return ai_driver.analyze_structural(prompt, FinanceCatalysts)



def finance_fallback_payload(msg="Finance engine temporarily unavailable"):
    return {
        "is_public": False,
        "data_available": False,
        "data_source": "fallback",
        "ticker": "",
        "currency": "",
        "msg": msg,
        "current_price": "N/A",
        "change_pct": None,
        "open_price": "N/A",
        "prev_close": "N/A",
        "pe_pb": "N/A",
        "erp": "N/A",
        "market_cap": "N/A",
        "range_52w": "N/A",
        "volume": "N/A",
        "chart_path": None,
    }



def get_value(item, key, default=""):
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)



def format_extraction_stats(stats):
    stats = stats or {}
    return (
        f"Jina全文 {int(stats.get('jina_count', 0) or 0)} | "
        f"网页直连 {int(stats.get('direct_html_count', 0) or 0)} | "
        f"摘要兜底 {int(stats.get('snippet_count', 0) or 0)}"
    )



def format_freshness_stats(stats):
    stats = stats or {}
    if not stats or not stats.get("enabled", False):
        return ""
    return (
        f"时效审查：保留 {int(stats.get('kept_count', 0) or 0)}/{int(stats.get('input_count', 0) or 0)} 条，"
        f"剔除超窗 {int(stats.get('dropped_stale_count', 0) or 0)} 条、"
        f"缺时间戳 {int(stats.get('dropped_missing_timestamp_count', 0) or 0)} 条、"
        f"时间异常 {int(stats.get('dropped_future_count', 0) or 0)} 条"
    )



def audit_results_for_freshness(raw_results, time_flag, current_dt):
    enabled = time_flag == "d"
    return audit_recent_news_results(
        raw_results,
        now=current_dt,
        max_age_hours=30,
        future_tolerance_hours=6,
        enabled=enabled,
    )



def build_lookup_maps(raw_results):
    snippet_lookup = {}
    title_lookup = {}
    for item in raw_results or []:
        url = item.get("url")
        if not url:
            continue
        title_lookup[url] = item.get("title", "")
        published_text = item.get("published_at_resolved") or item.get("published_date") or item.get("published") or ""
        snippet_body = item.get("content", "")
        snippet_lookup[url] = (
            f"发布时间:{published_text} | 摘要:{snippet_body}"
            if published_text else snippet_body
        )
    return title_lookup, snippet_lookup



def dedupe_news_items(news_items):
    deduped_news = []
    seen_event_ids = set()
    seen_urls = set()
    seen_title_keys = []
    for news in news_items or []:
        event_id = getattr(news, "event_id", "") or ""
        url = getattr(news, "url", "") or ""
        title = getattr(news, "title", "") or ""
        date_check = getattr(news, "date_check", "") or ""
        source = getattr(news, "source", "") or ""
        title_key = f"{title}|{date_check}|{source}"

        if event_id and event_id in seen_event_ids:
            continue
        if url and url in seen_urls:
            continue
        if any(difflib.SequenceMatcher(None, title_key, existing).ratio() > 0.82 for existing in seen_title_keys):
            continue

        deduped_news.append(news)
        if event_id:
            seen_event_ids.add(event_id)
        if url:
            seen_urls.add(url)
        seen_title_keys.append(title_key)
    return deduped_news



def sort_results_by_recency(results):
    return sorted(
        list(results or []),
        key=lambda item: item.get("published_at_resolved") or item.get("published_date") or "",
        reverse=True,
    )



def _serialize_event_blueprints(event_blueprints):
    payload = []
    for event in event_blueprints or []:
        if isinstance(event, dict):
            payload.append(dict(event))
        elif hasattr(event, "model_dump"):
            payload.append(event.model_dump())
    return payload



def _normalize_match_text(text):
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", str(text or "").lower().strip())



def _tokenize_match_text(text):
    words = {token.lower() for token in re.findall(r"[a-z0-9]{2,}", str(text or "").lower())}
    chars = [ch for ch in str(text or "") if re.match(r"[\u4e00-\u9fff]", ch)]
    if len(chars) < 2:
        return words | set(chars)
    return words | {"".join(chars[idx:idx + 2]) for idx in range(len(chars) - 1)}



def _score_result_for_event(event_dict, result):
    event_text = str(event_dict.get("event", "") or "")
    keywords = " ".join(event_dict.get("keywords", []) or [])
    title = str(result.get("title", "") or "")
    snippet = str(result.get("content", "") or "")[:220]
    if not event_text.strip():
        return 0.0

    event_norm = _normalize_match_text(event_text)
    title_norm = _normalize_match_text(title)
    ratio = difflib.SequenceMatcher(None, event_norm, title_norm).ratio() if event_norm and title_norm else 0.0
    event_tokens = _tokenize_match_text(f"{event_text} {keywords}")
    result_tokens = _tokenize_match_text(f"{title} {snippet}")
    overlap = len(event_tokens & result_tokens) / max(len(event_tokens), 1)
    keyword_hits = sum(
        1
        for token in event_dict.get("keywords", []) or []
        if token and str(token).lower() in f"{title} {snippet}".lower()
    )
    return round(ratio * 0.52 + overlap * 0.34 + min(keyword_hits * 0.07, 0.21), 4)



def select_analysis_candidates(event_blueprints, raw_results, max_events=ANALYSIS_EVENT_LIMIT, max_urls=COMPANY_CRAWL_URL_LIMIT):
    blueprint_payload = _serialize_event_blueprints(event_blueprints)
    ranked_results = sort_results_by_recency(raw_results)
    if not blueprint_payload or not ranked_results:
        return blueprint_payload[:max_events], ranked_results[:max_urls]

    scored_blueprints = []
    for index, event_dict in enumerate(blueprint_payload):
        scored_results = []
        for result in ranked_results:
            score = _score_result_for_event(event_dict, result)
            if score >= 0.24:
                scored_results.append((score, result))
        if not scored_results:
            continue
        scored_results.sort(
            key=lambda item: (item[0], item[1].get("published_at_resolved") or item[1].get("published_date") or ""),
            reverse=True,
        )
        scored_blueprints.append(
            {
                "index": index,
                "event": event_dict,
                "results": [item[1] for item in scored_results[:2]],
                "support_count": len(scored_results),
                "top_score": scored_results[0][0],
                "latest_time": max(
                    (item[1].get("published_at_resolved") or item[1].get("published_date") or "")
                    for item in scored_results
                ),
            }
        )

    if not scored_blueprints:
        return blueprint_payload[:max_events], ranked_results[:max_urls]

    scored_blueprints.sort(
        key=lambda row: (row["support_count"], row["top_score"], row["latest_time"], -row["index"]),
        reverse=True,
    )
    chosen_rows = scored_blueprints[:max_events]
    chosen_event_ids = {row["event"].get("event_id", "") for row in chosen_rows if row["event"].get("event_id")}
    if chosen_event_ids:
        candidate_events = [
            event_dict for event_dict in blueprint_payload
            if event_dict.get("event_id", "") in chosen_event_ids
        ][:max_events]
    else:
        chosen_indexes = {row["index"] for row in chosen_rows}
        candidate_events = [
            event_dict for idx, event_dict in enumerate(blueprint_payload)
            if idx in chosen_indexes
        ][:max_events]

    selected_results = []
    seen_urls = set()
    for pass_index in range(2):
        for row in chosen_rows:
            if pass_index >= len(row["results"]) or len(selected_results) >= max_urls:
                continue
            result = row["results"][pass_index]
            url = result.get("url", "")
            if url and url in seen_urls:
                continue
            if url:
                seen_urls.add(url)
            selected_results.append(result)
            if len(selected_results) >= max_urls:
                break

    for result in ranked_results:
        if len(selected_results) >= max_urls:
            break
        url = result.get("url", "")
        if url and url in seen_urls:
            continue
        if url:
            seen_urls.add(url)
        selected_results.append(result)

    return candidate_events or blueprint_payload[:max_events], selected_results[:max_urls]



def should_show_matched_title(event_text, matched_title):
    left = str(event_text or "").strip().lower()
    right = str(matched_title or "").strip().lower()
    if not left or not right:
        return bool(right)
    ratio = difflib.SequenceMatcher(None, left, right).ratio()
    return ratio < 0.72 and left not in right and right not in left



def collect_company_search_results(
    topic,
    sites_text,
    time_flag,
    tavily_key,
    company_pack=None,
    search_provider=DEFAULT_SEARCH_PROVIDER,
    exa_key="",
    exa_settings=None,
):
    company_pack = company_pack or get_company_query_pack(topic)
    merged_results = []
    seen_urls = set()
    normalized_sites_text = str(sites_text or "").strip()
    default_sites_text = str(get_default_sites_text() or "").strip()
    use_custom_domain_filter = bool(normalized_sites_text) and normalized_sites_text != default_sites_text
    effective_sites = (
        merge_sites_text(normalized_sites_text, company_pack.get("domains", []))
        if use_custom_domain_filter else ""
    )
    per_query_limit = 18 if company_pack.get("id") != "generic" else 16
    for query in build_company_queries_from_pack(topic, company_pack):
        batch = search_web(
            query,
            effective_sites,
            time_flag,
            max_results=per_query_limit,
            tavily_key=tavily_key,
            provider=search_provider,
            exa_key=exa_key,
            exa_settings=exa_settings,
        )
        for item in batch or []:
            url = item.get("url")
            if url and url in seen_urls:
                continue
            if url:
                seen_urls.add(url)
            merged_results.append(item)
    rank_limit = 60 if company_pack.get("id") != "generic" else 48
    return rank_results_by_company_pack(merged_results, company_pack, limit=rank_limit)



def collect_source_material(raw_results, max_urls, jina_key, max_chars_per_source=MAX_SOURCE_CHARS_PER_URL):
    urls_to_scrape = [item.get("url") for item in raw_results if item.get("url")][:max_urls]
    title_lookup, snippet_lookup = build_lookup_maps(raw_results)
    crawl_result = safe_run_async_crawler(
        urls=urls_to_scrape,
        jina_key=jina_key,
        snippet_lookup=snippet_lookup,
        title_lookup=title_lookup,
        max_chars_per_source=max_chars_per_source,
    )
    if not crawl_result.get("content"):
        fallback_snippets = []
        for item in raw_results[:max_urls]:
            fallback_snippets.append(
                f"发布时间:{item.get('published_at_resolved') or item.get('published_date') or ''} | "
                f"标题:{item.get('title', '')} | 摘要:{item.get('content', '')} | 链接:{item.get('url', '')}"
            )
        crawl_result["content"] = "\n\n".join(fallback_snippets)
        crawl_result["source_mode"] = "search_summary_fallback"
        if not crawl_result.get("warnings"):
            crawl_result["warnings"] = [
                "全文抓取为空，本专题已退回到“搜索摘要分析”模式；当前结果适合看事件脉络，不适合过度解读原文级细节。"
            ]
    return crawl_result



def build_empty_section_payload(topic, warnings=None, freshness_stats=None, focus_tags=None):
    warnings = list(warnings or [])
    freshness_stats = freshness_stats or {}
    focus_tags = list(focus_tags or [])
    empty_deep = {
        "topic": topic,
        "data": [],
        "finance": {},
        "source_mode": "filtered_empty",
        "crawler_valid_count": 0,
        "warnings": warnings,
        "extraction_stats": {},
        "freshness_stats": freshness_stats,
        "focus_tags": focus_tags,
    }
    empty_timeline = {
        "topic": topic,
        "events": [],
        "warnings": warnings,
        "extraction_stats": {},
        "freshness_stats": freshness_stats,
        "focus_tags": focus_tags,
    }
    return empty_deep, empty_timeline



def build_error_section_payload(topic, error_text, freshness_stats=None, focus_tags=None):
    return build_empty_section_payload(
        topic,
        warnings=[f"专题处理失败：{error_text}"],
        freshness_stats=freshness_stats,
        focus_tags=focus_tags,
    )



def store_report_outputs(all_deep_data, all_timeline_data, export_name, model_name, run_metadata=None):
    linked_deep_data, linked_timeline_data = annotate_report_data(all_deep_data, all_timeline_data)
    st.session_state.report_data = linked_deep_data
    st.session_state.timeline_data = linked_timeline_data
    st.session_state.run_metadata = dict(run_metadata or {})
    st.session_state.word_path = generate_word(linked_deep_data, linked_timeline_data, export_name, model_name)
    st.session_state.ppt_path = generate_ppt(linked_deep_data, linked_timeline_data, export_name, model_name)
    st.session_state.report_ready = True
    st.session_state.report_celebrated = False



def reset_report_state():
    st.session_state.report_ready = False
    st.session_state.word_path = ""
    st.session_state.ppt_path = ""
    st.session_state.report_data = []
    st.session_state.timeline_data = []
    st.session_state.run_metadata = {}
    st.session_state.report_celebrated = False



def render_timeline_preview(timeline_data):
    if not timeline_data:
        st.caption("暂无可展示的核心时间线。")
        return

    for section in timeline_data:
        topic = get_value(section, "topic", "未命名专题")
        st.markdown(f"### 专题：{topic}")
        focus_tags = get_value(section, "focus_tags", [])
        if focus_tags:
            st.caption(f"重点标签：{'、'.join(focus_tags[:8])}")
        extraction_stats = get_value(section, "extraction_stats", {})
        if extraction_stats:
            st.caption(f"抓取概况：{format_extraction_stats(extraction_stats)}")
        freshness_stats = get_value(section, "freshness_stats", {})
        if freshness_stats:
            st.caption(format_freshness_stats(freshness_stats))
        for warning_text in get_value(section, "warnings", []):
            st.warning(warning_text)

        events = get_value(section, "events", [])
        if not events:
            st.caption("暂无有效时间线。")
            continue

        for event in events:
            date_text = html.escape(str(get_value(event, "date", "近期")))
            event_text = html.escape(str(get_value(event, "event", "未命名事件")))
            source_text = html.escape(str(get_value(event, "source", "未知来源")))
            appears_later = bool(get_value(event, "appears_in_later_news", False))
            matched_title = html.escape(str(get_value(event, "matched_news_title", "")))
            match_reason = html.escape(str(get_value(event, "match_reason", "")))
            history_status = str(get_value(event, "history_status", "") or "")
            first_seen = html.escape(str(get_value(event, "first_seen", "")))
            seen_count = int(get_value(event, "seen_count", 0) or 0)

            border_color = "#f59e0b" if appears_later else "#cbd5e1"
            background = "#fff7ed" if appears_later else "#f8fafc"
            badge_html = ""
            if appears_later:
                badge_html += (
                    "<span style='display:inline-block;margin-left:8px;padding:2px 8px;"
                    "border-radius:999px;background:#f59e0b;color:#fff;font-size:12px;'>"
                    "后续长新闻已展开</span>"
                )
            if history_status == "followup":
                badge_html += (
                    "<span style='display:inline-block;margin-left:8px;padding:2px 8px;"
                    "border-radius:999px;background:#0f766e;color:#fff;font-size:12px;'>"
                    "历史事件延续</span>"
                )

            history_html = ""
            if history_status == "followup":
                history_html = (
                    f"<div style='margin-top:4px;color:#0f766e;'><strong>历史追踪：</strong>"
                    f"首次记录 {first_seen or '未知'}，累计追踪 {max(seen_count, 1)} 次</div>"
                )

            detail_html = ""
            if appears_later:
                matched_news_line = "已在后续长新闻中展开"
                if should_show_matched_title(event_text, matched_title):
                    matched_news_line = matched_title
                detail_html = (
                    f"<div style='margin-top:8px;color:#7c2d12;'><strong>对应长新闻：</strong>{matched_news_line}</div>"
                    f"<div style='margin-top:4px;color:#7c2d12;'><strong>出现原因：</strong>{match_reason}</div>"
                )

            st.markdown(
                (
                    f"<div style='border-left:4px solid {border_color};background:{background};"
                    "padding:12px 14px;margin:10px 0;border-radius:10px;'>"
                    f"<div style='font-weight:700;color:#0f172a;'>[{date_text}] {event_text}{badge_html}</div>"
                    f"<div style='margin-top:4px;color:#475569;'>来源：{source_text}</div>"
                    f"{history_html}"
                    f"{detail_html}"
                    "</div>"
                ),
                unsafe_allow_html=True,
            )



def render_deep_news_preview(report_data):
    if not report_data:
        st.caption("暂无可展示的深度新闻。")
        return

    for section in report_data:
        topic = get_value(section, "topic", "未命名专题")
        st.markdown(f"### 深度研报：{topic}")
        focus_tags = get_value(section, "focus_tags", [])
        if focus_tags:
            st.caption(f"重点标签：{'、'.join(focus_tags[:8])}")
        extraction_stats = get_value(section, "extraction_stats", {})
        if extraction_stats:
            st.caption(f"抓取概况：{format_extraction_stats(extraction_stats)}")
        freshness_stats = get_value(section, "freshness_stats", {})
        if freshness_stats:
            st.caption(format_freshness_stats(freshness_stats))
        for warning_text in get_value(section, "warnings", []):
            st.warning(warning_text)

        news_items = get_value(section, "data", [])
        if not news_items:
            st.caption("当前专题暂无符合标准的深度新闻。")
            continue

        for news in news_items:
            title = get_value(news, "title", "未命名情报")
            source = get_value(news, "source", "未知来源")
            date_text = get_value(news, "date_check", "近期")
            importance = int(get_value(news, "importance", 3) or 3)
            summary = get_value(news, "summary", "暂无详情")
            news_url = get_value(news, "url", "")
            timeline_refs = get_value(news, "timeline_refs", [])
            event_id = get_value(news, "event_id", "")

            with st.container(border=True):
                st.markdown(f"#### {title}")
                meta_parts = [f"来源：{source}", f"时间：{date_text}", f"热度：{'⭐' * max(1, importance)}"]
                if event_id:
                    meta_parts.append(f"事件ID：{event_id}")
                st.caption(" | ".join(meta_parts))

                if timeline_refs:
                    st.warning("这条长新闻承接了核心时间线中的短新闻，下面是匹配原因：")
                    for ref in timeline_refs:
                        ref_date = get_value(ref, "date", "近期")
                        ref_event = get_value(ref, "event", "未命名事件")
                        ref_reason = get_value(ref, "reason", "")
                        st.markdown(f"- `[{ref_date}]` {ref_event}")
                        if ref_reason:
                            st.caption(f"原因：{ref_reason}")

                st.markdown(summary.replace("\n", "  \n"))
                if news_url:
                    st.markdown(f"[查看原文]({news_url})")


def render_quality_panel(report_data, timeline_data):
    sections = []
    seen_topics = set()
    for collection in (report_data or [], timeline_data or []):
        for section in collection:
            topic = get_value(section, "topic", "未命名专题")
            if topic in seen_topics:
                continue
            sections.append(section)
            seen_topics.add(topic)

    visible_sections = []
    for section in sections:
        extraction_stats = get_value(section, "extraction_stats", {})
        freshness_stats = get_value(section, "freshness_stats", {})
        if extraction_stats or freshness_stats:
            visible_sections.append(section)

    if not visible_sections:
        return

    st.markdown("### 抓取质量面板")
    st.caption("每个专题都会显示 Jina 全文、网页直连、摘要兜底的占比，以及 24h 新鲜度审查结果。")

    for section in visible_sections:
        topic = html.escape(str(get_value(section, "topic", "未命名专题")))
        extraction_stats = get_value(section, "extraction_stats", {})
        freshness_stats = get_value(section, "freshness_stats", {})
        jina_count = int(extraction_stats.get("jina_count", 0) or 0)
        direct_count = int(extraction_stats.get("direct_html_count", 0) or 0)
        snippet_count = int(extraction_stats.get("snippet_count", 0) or 0)
        total = max(jina_count + direct_count + snippet_count, 1)
        freshness_text = html.escape(format_freshness_stats(freshness_stats))
        warning_text = html.escape(str((get_value(section, "warnings", []) or [""])[0]))

        segments = []
        for label, count, color in (
            ("Jina全文", jina_count, "#0f766e"),
            ("网页直连", direct_count, "#2563eb"),
            ("摘要兜底", snippet_count, "#d97706"),
        ):
            width = 0 if total <= 0 else round(count * 100 / total, 1)
            if width <= 0:
                continue
            segments.append(
                f"<div style='height:100%;width:{width}%;background:{color};'></div>"
            )

        legend_html = " ".join([
            f"<span style='margin-right:12px;color:#0f172a;'><strong>Jina全文</strong> {jina_count}</span>",
            f"<span style='margin-right:12px;color:#0f172a;'><strong>网页直连</strong> {direct_count}</span>",
            f"<span style='margin-right:12px;color:#0f172a;'><strong>摘要兜底</strong> {snippet_count}</span>",
        ])

        st.markdown(
            (
                "<div style='border:1px solid #e2e8f0;border-radius:14px;padding:14px 16px;margin:10px 0;background:#ffffff;'>"
                f"<div style='font-weight:700;color:#0f172a;font-size:16px;margin-bottom:8px;'>{topic}</div>"
                f"<div style='height:14px;background:#e5e7eb;border-radius:999px;overflow:hidden;display:flex;margin-bottom:8px;'>{''.join(segments)}</div>"
                f"<div style='font-size:13px;color:#334155;margin-bottom:6px;'>{legend_html}</div>"
                f"<div style='font-size:12px;color:#475569;'>{html.escape(format_extraction_stats(extraction_stats))}</div>"
                + (f"<div style='font-size:12px;color:#475569;margin-top:4px;'>{freshness_text}</div>" if freshness_text else "")
                + (f"<div style='font-size:12px;color:#b45309;margin-top:4px;'>{warning_text}</div>" if warning_text else "")
                + "</div>"
            ),
            unsafe_allow_html=True,
        )


with st.sidebar:
    st.header("🧠 部门情报控制台")
    def _get_runtime_secret(name, default=""):
        try:
            value = st.secrets[name]
            if not _looks_like_placeholder_secret(value):
                return value
        except Exception:
            pass

        env_value = os.getenv(name, "")
        if not _looks_like_placeholder_secret(env_value):
            return env_value

        local_fallback = _load_local_secret_fallback().get(name, "")
        if not _looks_like_placeholder_secret(local_fallback):
            return local_fallback

        return default

    api_key = _get_runtime_secret("DEEPSEEK_API_KEY", "")
    gemini_key = _get_runtime_secret("GEMINI_API_KEY", "") or _get_runtime_secret("GOOGLE_API_KEY", "")
    tavily_key = _get_runtime_secret("TAVILY_API_KEY", "")
    exa_key = _get_runtime_secret("EXA_API_KEY", "")
    jina_key = _get_runtime_secret("JINA_API_KEY", "")
    gh_token = _get_runtime_secret("GITHUB_TOKEN", "")
    gist_id = _get_runtime_secret("GIST_ID", "")
    if (api_key or gemini_key) and (tavily_key or exa_key):
        st.success("🔐 部门专属安全引擎已连接")
    else:
        st.error("⚠️ 未检测到可用的搜索或模型密钥，请补充 API Key。")

    st.divider()
    model_id = st.selectbox("核心模型", ["deepseek-chat"], index=0)
    use_gemini_main = st.toggle(
        "使用 Gemini AI Studio 作为主模型（保留当前 Prompt）",
        key="use_gemini_main",
    )
    gemini_main_preset_col1, gemini_main_preset_col2 = st.columns(2)
    with gemini_main_preset_col1:
        if st.button("切到 Gemini 3 Flash", key="btn_gemini_3_flash_main", disabled=not gemini_key):
            apply_gemini_3_flash_main_preset()
    with gemini_main_preset_col2:
        if st.button("尝试 3.1 Flash-Lite", key="btn_gemini_31_flash_lite_main", disabled=not gemini_key):
            apply_gemini_31_flash_lite_main_preset()
    gemini_main_model_choice = st.selectbox(
        "Gemini 主模型",
        GEMINI_MODEL_OPTIONS,
        key="gemini_main_model",
        disabled=not use_gemini_main,
        format_func=format_gemini_model_option,
    )
    gemini_main_model_custom = st.text_input(
        "Gemini 主模型自定义 ID",
        key="gemini_main_model_custom",
        disabled=(not use_gemini_main or gemini_main_model_choice != "__custom__"),
        placeholder="例如：gemini-3.1-flash-lite-preview",
    )
    gemini_main_model = resolve_gemini_model_name(
        gemini_main_model_choice,
        gemini_main_model_custom,
        DEFAULT_GEMINI_MAIN_MODEL,
    )
    if use_gemini_main:
        if gemini_key:
            st.caption(
                "主模型可切到 Gemini AI Studio；这会复用当前同一套 Prompt、输出结构和页面，不改业务链路。"
                " `Gemini 3.1 Flash-Lite` 这里按公开命名规则做了预设，若你的账号尚未开放该预览 ID，可改回 Gemini 3 Flash 或手动填写。"
            )
        else:
            st.caption("当前未配置 GEMINI_API_KEY 或 GOOGLE_API_KEY，开启后会自动回退为 DeepSeek。")
    use_gemini_light = st.toggle("启用 Gemini AI Studio 轻任务引擎（保留当前主功能）", key="use_gemini_light")
    gemini_light_model_choice = st.selectbox(
        "Gemini 轻任务模型",
        GEMINI_MODEL_OPTIONS,
        key="gemini_light_model",
        disabled=not use_gemini_light,
        format_func=format_gemini_model_option,
    )
    gemini_light_model_custom = st.text_input(
        "Gemini 轻任务自定义 ID",
        key="gemini_light_model_custom",
        disabled=(not use_gemini_light or gemini_light_model_choice != "__custom__"),
        placeholder="例如：gemini-3.1-flash-lite-preview",
    )
    gemini_light_model = resolve_gemini_model_name(
        gemini_light_model_choice,
        gemini_light_model_custom,
        DEFAULT_GEMINI_LIGHT_MODEL,
    )
    if use_gemini_light:
        if gemini_key:
            st.caption("当前按 Google AI Studio 的 OpenAI 兼容接口接入。轻任务包括：事件主档抽取、切片候选提取。最终长新闻成稿仍由 DeepSeek 负责。")
        else:
            st.caption("当前未配置 GEMINI_API_KEY 或 GOOGLE_API_KEY，开启后会自动回退为全 DeepSeek，不影响现有功能。")
    time_opt = st.selectbox("回溯时间线", ["过去 24 小时", "过去 1 周", "过去 1 个月"], index=0)
    search_provider = st.selectbox(
        "搜索引擎",
        ["exa", "hybrid", "tavily"],
        key="search_provider",
        format_func=format_search_provider_option,
    )
    enable_finance_chain = st.toggle("上市公司金融补链（更耗 token）", value=False)
    time_limit_dict = {"过去 24 小时": "d", "过去 1 周": "w", "过去 1 个月": "m"}

    with st.expander("⚙️ 高级搜索源设置"):
        sites = st.text_area("重点搜索源", get_default_sites_text(), height=250)
        preset_col1, preset_col2 = st.columns(2)
        with preset_col1:
            if st.button("恢复 Exa 默认", key="btn_exa_default"):
                apply_exa_default_preset()
        with preset_col2:
            if st.button("硬科技优先预设", key="btn_exa_hardtech"):
                apply_exa_hardtech_preset()

        st.caption("默认已经改为 Exa：`auto + news + highlights`。这套最适合你们当前的科技新闻场景，也更接近 Exa Search 官方支持的稳定参数。")
        exa_search_type = st.selectbox(
            "Exa 搜索类型",
            ["auto", "fast", "instant", "deep"],
            key="exa_search_type",
        )
        exa_category = st.selectbox(
            "Exa 结果类别",
            ["news", "", "financial report", "research paper", "personal site"],
            key="exa_category",
            format_func=lambda item: {
                "news": "news（推荐）",
                "": "自动/不强制",
                "financial report": "financial report",
                "research paper": "research paper",
                "personal site": "personal site",
            }.get(item, item),
        )
        exa_result_limit = st.number_input("Exa 每次查询结果数", min_value=3, max_value=20, step=1, key="exa_result_limit")
        exa_content_mode = st.selectbox(
            "Exa 搜索内容",
            ["highlights", "highlights_text", "text"],
            key="exa_content_mode",
            format_func=lambda item: {
                "highlights": "highlights（推荐，最稳）",
                "highlights_text": "highlights + text（更全，但更贵）",
                "text": "text（不推荐，容易太重）",
            }.get(item, item),
        )
        exa_highlights_chars = st.slider("Exa highlights 最大字符数", min_value=800, max_value=4000, step=200, key="exa_highlights_chars")
        exa_text_chars = st.slider("Exa text 最大字符数", min_value=1200, max_value=8000, step=400, key="exa_text_chars")
        exa_include_text = st.text_input("Exa 必含关键词（可选，1-5词）", key="exa_include_text")
        exa_exclude_text = st.text_input("Exa 排除关键词（可选，1-5词）", key="exa_exclude_text")
        exa_search_settings = {
            "search_type": exa_search_type,
            "category": exa_category,
            "num_results": int(exa_result_limit),
            "content_mode": exa_content_mode,
            "highlights_max_characters": int(exa_highlights_chars),
            "text_max_characters": int(exa_text_chars),
            "include_text": exa_include_text,
            "exclude_text": exa_exclude_text,
        }

    file_name = st.text_input("导出文件名", f"FPC-RD科技资讯_{datetime.date.today()}")

st.title("🧠 商业情报战情室（事件主档统一版）")

if not st.session_state.report_ready:
    tab1, tab2 = st.tabs(["📚 频道一：公司追踪（带金融量化）", "🌐 频道二：每日宏观行业早报（全域扫描）"])

    with tab1:
        st.markdown("💡 **操作指南**：输入追踪对象，多个目标请使用 `\\` 分开，系统会并发执行独立分析。")
        query_input = st.text_input("输入追踪对象", "Apple \\ Google")
        start_btn = st.button("🚀 启动并发战情推演", type="primary", key="btn_company")
        active_search_provider, search_notices = resolve_search_provider(search_provider, tavily_key, exa_key)

        if start_btn and active_search_provider:
            topics = [topic.strip() for topic in query_input.split("\\") if topic.strip()]
            ai, light_ai, ai_notices = build_ai_stack(
                api_key,
                model_id,
                use_gemini_light=use_gemini_light,
                gemini_key=gemini_key,
                gemini_model=gemini_light_model,
                use_gemini_main=use_gemini_main,
                gemini_main_model=gemini_main_model,
            )
            if not ai.valid:
                st.error("当前没有可用的主模型密钥。请配置 DEEPSEEK_API_KEY，或开启 Gemini 主模型并配置 GEMINI_API_KEY / GOOGLE_API_KEY。")
                st.stop()
            current_dt = datetime.datetime.now(LOCAL_TZ)
            current_date_str = current_dt.strftime("%Y年%m月%d日")
            mem_manager = GistMemoryManager(gh_token, gist_id)
            mem_manager.load_memory()
            reset_search_diagnostics()
            st.info(f"🔎 正在启动并发处理引擎，目标数：{len(topics)}")
            for notice in ai_notices:
                st.caption(notice)
            st.caption(f"本次搜索引擎：{format_search_provider_label(active_search_provider)}")
            for notice in search_notices:
                st.caption(notice)

            def process_company_task(topic, index):
                try:
                    company_pack = get_company_query_pack(topic)
                    focus_tags = company_pack.get("keywords", [])[:8]
                    company_focus_hint = build_company_focus_hint(company_pack)
                    raw_results = collect_company_search_results(
                        topic,
                        sites,
                        time_limit_dict[time_opt],
                        tavily_key,
                        company_pack=company_pack,
                        search_provider=active_search_provider,
                        exa_key=exa_key,
                        exa_settings=exa_search_settings,
                    )
                    if not raw_results:
                        empty_warning = f"未召回到符合条件的 {topic} 新闻，请扩大搜索源或放宽时间范围。"
                        deep_empty, timeline_empty = build_empty_section_payload(
                            topic,
                            warnings=[empty_warning],
                            focus_tags=focus_tags,
                        )
                        return index, deep_empty, timeline_empty
                    raw_results, freshness_stats, freshness_warnings = audit_results_for_freshness(
                        raw_results,
                        time_limit_dict[time_opt],
                        current_dt,
                    )
                    raw_results = rank_results_by_company_pack(raw_results, company_pack, limit=40)
                    if not raw_results:
                        deep_empty, timeline_empty = build_empty_section_payload(
                            topic,
                            warnings=freshness_warnings,
                            freshness_stats=freshness_stats,
                            focus_tags=focus_tags,
                        )
                        return index, deep_empty, timeline_empty

                    event_seed_results = raw_results[:EVENT_BLUEPRINT_INPUT_LIMIT_COMPANY]
                    history_hint = mem_manager.get_event_bank_summary(topic, limit=4)
                    event_blueprints = build_event_blueprints(
                        ai,
                        event_seed_results,
                        topic,
                        current_date_str,
                        time_opt,
                        history_hint=history_hint,
                        guidance=company_focus_hint,
                    )
                    event_blueprints = mem_manager.bind_event_blueprints(topic, event_blueprints, current_date_str)
                    timeline_events = generate_timeline(event_blueprints)
                    analysis_events, analysis_results = select_analysis_candidates(
                        event_blueprints,
                        raw_results,
                        max_events=ANALYSIS_EVENT_LIMIT,
                        max_urls=COMPANY_CRAWL_URL_LIMIT,
                    )
                    crawl_result = collect_source_material(
                        analysis_results,
                        max_urls=COMPANY_CRAWL_URL_LIMIT,
                        jina_key=jina_key,
                        max_chars_per_source=MAX_SOURCE_CHARS_PER_URL,
                    )
                    crawl_result["warnings"] = list(crawl_result.get("warnings", [])) + list(freshness_warnings)
                    past_memories = mem_manager.get_topic_context(topic, history_limit=3, event_limit=4)
                    final_news_list, new_insight = map_reduce_analysis(
                        ai,
                        topic,
                        crawl_result["content"],
                        current_date_str,
                        time_opt,
                        past_memories,
                        event_blueprints=analysis_events,
                        source_mode=crawl_result["source_mode"],
                        guidance=company_focus_hint,
                        raw_search_results=analysis_results,
                        map_ai_driver=light_ai,
                    )

                    deep_data_res = None
                    if final_news_list:
                        deduped_news = dedupe_news_items(final_news_list)
                        if deduped_news:
                            finance_data = {}
                            if enable_finance_chain:
                                try:
                                    finance_data = fetch_financial_data(ai, topic) or finance_fallback_payload()
                                except Exception as e:
                                    print(f"⚠️ Finance chain failed for {topic}: {e}")
                                    finance_data = finance_fallback_payload(f"Finance chain failed: {e}")

                                if finance_data.get("is_public"):
                                    news_summary_text = "\n".join([news.summary for news in deduped_news])
                                    cats = get_finance_catalysts(ai, topic, news_summary_text)
                                    if cats:
                                        finance_data["catalysts"] = cats.model_dump()

                            deep_data_res = {
                                "topic": topic,
                                "data": deduped_news,
                                "finance": finance_data,
                                "source_mode": crawl_result["source_mode"],
                                "crawler_valid_count": crawl_result["valid_count"],
                                "warnings": list(crawl_result.get("warnings", [])),
                                "extraction_stats": crawl_result.get("stats", {}),
                                "freshness_stats": freshness_stats,
                                "focus_tags": focus_tags,
                            }
                            if new_insight:
                                mem_manager.add_topic_memory(topic, current_date_str, new_insight)

                    timeline_data_res = {
                        "topic": topic,
                        "events": timeline_events,
                        "warnings": list(crawl_result.get("warnings", [])),
                        "extraction_stats": crawl_result.get("stats", {}),
                        "freshness_stats": freshness_stats,
                        "focus_tags": focus_tags,
                    } if timeline_events else None
                    return index, deep_data_res, timeline_data_res
                except Exception as e:
                    trace_text = traceback.format_exc(limit=8)
                    print(f"⚠️ Company pipeline failed for {topic}: {trace_text}")
                    deep_error, timeline_error = build_error_section_payload(
                        topic,
                        f"{e.__class__.__name__}: {e}",
                        focus_tags=locals().get("focus_tags", []),
                    )
                    return index, deep_error, timeline_error

            results = []
            with st.spinner("🛰️ 正在并行收集与深度推演中..."):
                with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                    futures = [executor.submit(process_company_task, topic, i) for i, topic in enumerate(topics)]
                    for future in concurrent.futures.as_completed(futures):
                        try:
                            item = future.result()
                            if item:
                                results.append(item)
                        except Exception as e:
                            print(f"⚠️ Company worker crashed: {e}")

            results.sort(key=lambda item: item[0])
            all_deep_data = [item[1] for item in results if item[1] is not None]
            all_timeline_data = [item[2] for item in results if item[2] is not None]
            mem_manager.save_memory()
            search_runtime = build_run_metadata(
                requested_provider=search_provider,
                resolved_provider=active_search_provider,
                notices=search_notices,
                diagnostics=get_search_diagnostics(),
            )
            st.success("✅ 并发深度分析完成。")

            if all_deep_data or all_timeline_data:
                store_report_outputs(
                    all_deep_data,
                    all_timeline_data,
                    file_name,
                    format_model_stack_name(ai, light_ai),
                    run_metadata=search_runtime,
                )
                st.rerun()
            else:
                st.error("本次运行没有产出任何有效专题。请查看终端日志，或使用本地调试版查看详细报错。")
        elif start_btn and not active_search_provider:
            st.error("当前没有可用的搜索引擎密钥。请至少配置 TAVILY_API_KEY 或 EXA_API_KEY。")

    with tab2:
        st.markdown(
            "💡 **本频道专为宏观视野打造**：一键搜集全球重点科技赛道最新进展，"
            "**多路并发，全域扫描**。当前已额外强化 PCB/FPC、CPO 光模块、卫星通信、智能车光学与感知。"
        )
        use_all_web = st.toggle("🌐 开启全网无界搜索（打开则无视侧边栏源，进行全球广度覆盖）", value=True)
        search_domain = "" if use_all_web else sites
        cn_sites_default = get_default_china_sites_text()
        with st.expander("🇨🇳 中国专题设置（仅中文网站 + 中国公司）", expanded=False):
            china_sites = st.text_area(
                "中文网站白名单（每行一个域名）",
                cn_sites_default,
                height=220,
                key="cn_sites_whitelist",
            )
            china_query_suffix = st.text_input(
                "中国公司限定关键词（自动拼接到每条查询）",
                "中国 初创 公司 创业 融资 订单 本土 国产",
                key="cn_query_suffix",
            )

        industry_topics = get_industry_topics()
        active_search_provider, search_notices = resolve_search_provider(search_provider, tavily_key, exa_key)

        def run_industry_pipeline(industry_topic_list, domain_text, china_mode=False, query_suffix=""):
            ai, light_ai, ai_notices = build_ai_stack(
                api_key,
                model_id,
                use_gemini_light=use_gemini_light,
                gemini_key=gemini_key,
                gemini_model=gemini_light_model,
                use_gemini_main=use_gemini_main,
                gemini_main_model=gemini_main_model,
            )
            if not ai.valid:
                st.error("当前没有可用的主模型密钥。请配置 DEEPSEEK_API_KEY，或开启 Gemini 主模型并配置 GEMINI_API_KEY / GOOGLE_API_KEY。")
                return [], [], "未启用模型", {}
            current_dt = datetime.datetime.now(LOCAL_TZ)
            current_date_str = current_dt.strftime("%Y年%m月%d日")
            mem_manager = GistMemoryManager(gh_token, gist_id)
            mem_manager.load_memory()
            reset_search_diagnostics()

            if china_mode:
                st.info("🔎 正在启动中国专题并发引擎，仅保留中文网站与中国公司事件。")
            else:
                st.info("🔎 正在启动全域多路扫描并发引擎，请稍候。")
            for notice in ai_notices:
                st.caption(notice)
            st.caption(f"本次搜索引擎：{format_search_provider_label(active_search_provider)}")
            for notice in search_notices:
                st.caption(notice)

            def process_industry_task(topic_pack, index):
                try:
                    topic_key = topic_pack["title"]
                    topic_label = f"{topic_key}（中国专题）" if china_mode else topic_key
                    all_raw_results = []
                    seen_urls = set()
                    extra_domains = topic_pack.get("china_domains", []) if china_mode else topic_pack.get("domains", [])
                    effective_domains = merge_sites_text(domain_text, extra_domains) if domain_text else ""

                    for query in topic_pack["queries"]:
                        actual_query = f"{query} {query_suffix}".strip() if china_mode and query_suffix else query
                        results = search_web(
                            actual_query,
                            effective_domains,
                            time_limit_dict[time_opt],
                            max_results=16,
                            tavily_key=tavily_key,
                            provider=active_search_provider,
                            exa_key=exa_key,
                            exa_settings=exa_search_settings,
                        )
                        if china_mode:
                            results = filter_china_results(results, effective_domains, require_chinese_text=True)
                        results = rank_results_by_pack(results, topic_pack, limit=12)

                        for item in results:
                            url = item.get("url")
                            if url and url not in seen_urls:
                                seen_urls.add(url)
                                all_raw_results.append(item)

                    if not all_raw_results:
                        return index, None, None

                    top_results = rank_results_by_pack(all_raw_results, topic_pack, limit=30)
                    top_results, freshness_stats, freshness_warnings = audit_results_for_freshness(
                        top_results,
                        time_limit_dict[time_opt],
                        current_dt,
                    )
                    top_results = rank_results_by_pack(top_results, topic_pack, limit=30)
                    if not top_results:
                        deep_empty, timeline_empty = build_empty_section_payload(
                            topic_label,
                            warnings=freshness_warnings,
                            freshness_stats=freshness_stats,
                            focus_tags=topic_pack.get("tags", []),
                        )
                        return index, deep_empty, timeline_empty
                    focus_hint = build_focus_hint(topic_pack, china_mode=china_mode)
                    event_seed_results = top_results[:EVENT_BLUEPRINT_INPUT_LIMIT_INDUSTRY]
                    history_hint = mem_manager.get_event_bank_summary(topic_key, limit=4)
                    event_blueprints = build_event_blueprints(
                        ai,
                        event_seed_results,
                        topic_key,
                        current_date_str,
                        time_opt,
                        history_hint=history_hint,
                        guidance=focus_hint,
                    )
                    event_blueprints = mem_manager.bind_event_blueprints(topic_key, event_blueprints, current_date_str)
                    timeline_events = generate_timeline(event_blueprints)
                    analysis_events, analysis_results = select_analysis_candidates(
                        event_blueprints,
                        top_results,
                        max_events=ANALYSIS_EVENT_LIMIT,
                        max_urls=INDUSTRY_CRAWL_URL_LIMIT,
                    )
                    crawl_result = collect_source_material(
                        analysis_results,
                        max_urls=INDUSTRY_CRAWL_URL_LIMIT,
                        jina_key=jina_key,
                        max_chars_per_source=MAX_SOURCE_CHARS_PER_URL,
                    )
                    crawl_result["warnings"] = list(crawl_result.get("warnings", [])) + list(freshness_warnings)
                    past_memories = mem_manager.get_topic_context(topic_key, history_limit=3, event_limit=4)
                    final_news_list, _ = map_reduce_analysis(
                        ai,
                        topic_key,
                        crawl_result["content"],
                        current_date_str,
                        time_opt,
                        past_memories,
                        event_blueprints=analysis_events,
                        source_mode=crawl_result["source_mode"],
                        guidance=(
                            f"{focus_hint}；仅保留中国公司或中国产业链相关事件，来源必须来自中文站点。"
                            if china_mode else focus_hint
                        ),
                        raw_search_results=analysis_results,
                        map_ai_driver=light_ai,
                    )

                    deep_data_res = None
                    if final_news_list:
                        deduped_news = dedupe_news_items(final_news_list)
                        if deduped_news:
                            deep_data_res = {
                                "topic": topic_label,
                                "data": deduped_news,
                                "source_mode": crawl_result["source_mode"],
                                "crawler_valid_count": crawl_result["valid_count"],
                                "warnings": list(crawl_result.get("warnings", [])),
                                "extraction_stats": crawl_result.get("stats", {}),
                                "freshness_stats": freshness_stats,
                                "focus_tags": topic_pack.get("tags", []),
                                "watch_entities": topic_pack.get("companies", []),
                            }

                    timeline_data_res = {
                        "topic": topic_label,
                        "events": timeline_events,
                        "warnings": list(crawl_result.get("warnings", [])),
                        "extraction_stats": crawl_result.get("stats", {}),
                        "freshness_stats": freshness_stats,
                        "focus_tags": topic_pack.get("tags", []),
                    } if timeline_events else None
                    return index, deep_data_res, timeline_data_res
                except Exception as e:
                    topic_label = locals().get("topic_label", topic_pack.get("title", "unknown"))
                    trace_text = traceback.format_exc(limit=8)
                    print(f"⚠️ Industry pipeline failed for {topic_label}: {trace_text}")
                    deep_error, timeline_error = build_error_section_payload(
                        topic_label,
                        f"{e.__class__.__name__}: {e}",
                        freshness_stats=locals().get("freshness_stats", {}),
                        focus_tags=topic_pack.get("tags", []),
                    )
                    return index, deep_error, timeline_error

            results = []
            spinner_msg = (
                "🛰️ 中国专题探针已发射，正在聚合中文站点与中国公司情报..."
                if china_mode else
                "🛰️ 多路探针已发射，正在进行全域情报融合..."
            )
            with st.spinner(spinner_msg):
                with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                    futures = [executor.submit(process_industry_task, topic_pack, i) for i, topic_pack in enumerate(industry_topic_list)]
                    for future in concurrent.futures.as_completed(futures):
                        try:
                            item = future.result()
                            if item:
                                results.append(item)
                        except Exception as e:
                            print(f"⚠️ Industry worker crashed: {e}")

            results.sort(key=lambda item: item[0])
            mem_manager.save_memory()
            all_deep_data = [item[1] for item in results if item[1] is not None]
            all_timeline_data = [item[2] for item in results if item[2] is not None]
            return (
                all_deep_data,
                all_timeline_data,
                format_model_stack_name(ai, light_ai),
                build_run_metadata(
                    requested_provider=search_provider,
                    resolved_provider=active_search_provider,
                    notices=search_notices,
                    diagnostics=get_search_diagnostics(),
                ),
            )

        col_global, col_cn = st.columns(2)
        with col_global:
            start_industry_btn = st.button("🚀 一键并发生成《每日宏观行业早报》", type="primary", key="btn_industry")
        with col_cn:
            start_cn_industry_btn = st.button("🇨🇳 一键并发生成《中国公司中文站点专题》", type="secondary", key="btn_industry_cn")

        if start_industry_btn and active_search_provider:
            all_deep_data, all_timeline_data, active_model_name, search_runtime = run_industry_pipeline(industry_topics, search_domain, china_mode=False)
            if all_deep_data or all_timeline_data:
                store_report_outputs(all_deep_data, all_timeline_data, file_name, active_model_name, run_metadata=search_runtime)
                st.rerun()
            else:
                st.error("本次运行没有产出任何有效专题。请查看终端日志，或使用本地调试版查看详细报错。")
        elif start_industry_btn and not active_search_provider:
            st.error("当前没有可用的搜索引擎密钥。请至少配置 TAVILY_API_KEY 或 EXA_API_KEY。")

        if start_cn_industry_btn and active_search_provider:
            all_deep_data, all_timeline_data, active_model_name, search_runtime = run_industry_pipeline(
                industry_topics,
                china_sites,
                china_mode=True,
                query_suffix=china_query_suffix,
            )
            if all_deep_data or all_timeline_data:
                store_report_outputs(all_deep_data, all_timeline_data, file_name, active_model_name, run_metadata=search_runtime)
                st.rerun()
            else:
                st.error("本次运行没有产出任何有效专题。请查看终端日志，或使用本地调试版查看详细报错。")
        elif start_cn_industry_btn and not active_search_provider:
            st.error("当前没有可用的搜索引擎密钥。请至少配置 TAVILY_API_KEY 或 EXA_API_KEY。")

else:
    if not st.session_state.report_celebrated:
        st.balloons()
        st.session_state.report_celebrated = True

    st.success("🎉 战报生成完成。")
    render_search_runtime_panel(st.session_state.run_metadata)
    report_warnings = []
    for section in st.session_state.report_data:
        report_warnings.extend(get_value(section, "warnings", []))
    if report_warnings:
        st.warning("本次结果中存在时效或抓取审查提示：请结合下方抓取质量面板与专题提示一起阅读结果。")

    col1, col2 = st.columns(2)
    with col1:
        with open(st.session_state.word_path, "rb") as file_obj:
            st.download_button(
                "📑 立即下载深度研报（Word）",
                file_obj,
                file_name=st.session_state.word_path,
                type="secondary",
                use_container_width=True,
            )
    with col2:
        with open(st.session_state.ppt_path, "rb") as file_obj:
            st.download_button(
                "📊 立即下载高管简报（PPT）",
                file_obj,
                file_name=st.session_state.ppt_path,
                type="primary",
                use_container_width=True,
            )

    st.divider()
    render_quality_panel(st.session_state.report_data, st.session_state.timeline_data)
    st.divider()
    preview_tab1, preview_tab2 = st.tabs(["⏱️ 核心时间线预览", "📰 深度新闻预览"])
    with preview_tab1:
        st.caption("橙色高亮表示：这条短新闻会在后续长新闻中继续展开；绿色标签表示：该事件在历史记忆里已被持续跟踪。")
        render_timeline_preview(st.session_state.timeline_data)
    with preview_tab2:
        st.caption("每条长新闻会显示它承接了哪条核心时间线短新闻，以及为什么被判定为同一事件。")
        render_deep_news_preview(st.session_state.report_data)

    st.divider()
    if st.button("📧 开启新一轮情报探索", use_container_width=True):
        reset_report_state()
        st.rerun()









