# -*- coding: utf-8 -*-
from __future__ import annotations

import difflib
import json
import re
from typing import Callable, Iterable, List, Optional, Tuple

from openai import OpenAI
from pydantic import BaseModel, Field

from news_app.agents.deep_analyst import map_reduce_analysis
from news_app.agents.timeline_agent import generate_timeline
from news_app.tools.finance_engine import fetch_financial_data
from news_app.tools.search_engine import search_web, safe_run_async_crawler

LogFn = Optional[Callable[[str], None]]


class AI_Driver:
    def __init__(self, api_key: str, model_id: str):
        self.valid = False
        self.model_id = model_id
        if api_key:
            try:
                self.client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
                self.valid = True
            except Exception:
                self.valid = False

    def analyze_structural(self, prompt: str, structure_class: type[BaseModel]):
        if not self.valid:
            return None

        sys_prompt = (
            "请严格按 JSON 格式返回，不要包含多余文字或思考过程。"
            "JSON Schema 如下:\n"
            f"{json.dumps(structure_class.model_json_schema(), ensure_ascii=False)}"
        )

        try:
            res = self.client.chat.completions.create(
                model=self.model_id,
                messages=[
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
                max_tokens=4096,
            )
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
            print(f"[AI] structured parse failed: {e}")
            return None


class FinanceCatalysts(BaseModel):
    policy: str = Field(description="政策发布（<=40字）")
    earnings: str = Field(description="财报表现（<=40字）")
    landmark: str = Field(description="产业标志（<=40字）")
    style: str = Field(description="市场风格轮动（<=40字）")


def get_finance_catalysts(ai_driver: AI_Driver, topic: str, news_text: str):
    prompt = (
        "你是资深投研分析师。请基于以下关于"
        f"“{topic}”的新闻，提炼近期二级市场的核心催化剂：\n{news_text}"
    )
    return ai_driver.analyze_structural(prompt, FinanceCatalysts)


def _normalize_title(title: str) -> str:
    if not title:
        return ""
    title = title.strip().lower()
    title = re.sub(r"[\W_]+", "", title, flags=re.UNICODE)
    return title


def dedupe_news_items(
    items: Iterable,
    similarity_threshold: float = 0.82,
    max_compare: int = 60,
) -> List:
    deduped: List = []
    seen_norm = set()
    seen_titles: List[str] = []

    for item in items:
        title = getattr(item, "title", "") or ""
        norm = _normalize_title(title)
        if norm and norm in seen_norm:
            continue

        compare_pool = seen_titles[-max_compare:]
        too_similar = any(
            difflib.SequenceMatcher(None, title, s).ratio() > similarity_threshold
            for s in compare_pool
        )
        if too_similar:
            continue

        deduped.append(item)
        if norm:
            seen_norm.add(norm)
        seen_titles.append(title)

    return deduped


def _build_full_text(raw_results: List[dict], urls_to_scrape: List[str], jina_key: str) -> str:
    full_text_data, _ = safe_run_async_crawler(urls=urls_to_scrape, jina_key=jina_key)
    if len(full_text_data) >= 500:
        return full_text_data

    snippets = [
        f"标题:{r.get('title')} | 内容:{r.get('content')} | 链接:{r.get('url')}"
        for r in raw_results
    ]
    return "\n\n".join(snippets)


def process_company_topic(
    topic: str,
    index: int,
    *,
    ai: AI_Driver,
    sites_text: str,
    time_limit: str,
    time_label: str,
    current_date: str,
    tavily_key: str,
    jina_key: str,
    mem_manager=None,
    enable_catalysts: bool = True,
    log: LogFn = None,
) -> Tuple[int, Optional[dict], Optional[dict]]:
    if log:
        log(f"[company] start: {topic}")

    finance_data = fetch_financial_data(ai, topic)
    raw_results = search_web(topic, sites_text, time_limit, max_results=30, tavily_key=tavily_key)
    if not raw_results:
        if log:
            log(f"[company] no results: {topic}")
        return index, None, None

    timeline_events = generate_timeline(ai, raw_results, topic, current_date, time_label)
    urls_to_scrape = [r.get("url") for r in raw_results if r.get("url")][:12]
    past_memories = mem_manager.get_topic_history(topic) if mem_manager else ""

    full_text_data = _build_full_text(raw_results, urls_to_scrape, jina_key)
    final_news_list, new_insight = map_reduce_analysis(
        ai, topic, full_text_data, current_date, time_label, past_memories
    )

    deep_data_res = None
    if final_news_list:
        deduped_news = dedupe_news_items(final_news_list)
        if deduped_news:
            if (
                enable_catalysts
                and finance_data.get("is_public")
                and finance_data.get("data_ok")
            ):
                news_summary_text = "\n".join([n.summary for n in deduped_news])
                cats = get_finance_catalysts(ai, topic, news_summary_text)
                if cats:
                    finance_data["catalysts"] = cats.model_dump()

            deep_data_res = {"topic": topic, "data": deduped_news, "finance": finance_data}
            if new_insight and mem_manager:
                mem_manager.add_topic_memory(topic, current_date, new_insight)

    t_data_res = {"topic": topic, "events": timeline_events} if timeline_events else None
    if log:
        log(f"[company] done: {topic}")
    return index, deep_data_res, t_data_res


def process_industry_topic(
    topic_cfg: dict,
    index: int,
    *,
    ai: AI_Driver,
    search_domain: str,
    time_limit: str,
    time_label: str,
    current_date: str,
    tavily_key: str,
    jina_key: str,
    log: LogFn = None,
) -> Tuple[int, Optional[dict], Optional[dict]]:
    title = topic_cfg["title"]
    if log:
        log(f"[industry] start: {title}")

    all_raw_results: List[dict] = []
    seen_urls = set()
    for query in topic_cfg["queries"]:
        res = search_web(query, search_domain, time_limit, max_results=15, tavily_key=tavily_key)
        if res:
            for r in res:
                url = r.get("url")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    all_raw_results.append(r)

    if not all_raw_results:
        if log:
            log(f"[industry] no results: {title}")
        return index, None, None

    top_results = all_raw_results[:20]
    timeline_events = generate_timeline(ai, top_results, title, current_date, time_label)
    urls_to_scrape = [r.get("url") for r in top_results if r.get("url")][:12]
    full_text_data = _build_full_text(top_results, urls_to_scrape, jina_key)

    strict_topic_prompt = f"{title}。核心提取要求：{topic_cfg['desc']}"
    final_news_list, _ = map_reduce_analysis(
        ai, strict_topic_prompt, full_text_data, current_date, time_label, ""
    )

    deep_data_res = None
    if final_news_list:
        deduped_news = dedupe_news_items(final_news_list)
        if deduped_news:
            deep_data_res = {"topic": title, "data": deduped_news}

    t_data_res = {"topic": title, "events": timeline_events} if timeline_events else None
    if log:
        log(f"[industry] done: {title}")
    return index, deep_data_res, t_data_res
