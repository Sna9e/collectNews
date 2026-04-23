import json
import concurrent.futures
import re
from pydantic import BaseModel, Field
from typing import List
from langchain_text_splitters import RecursiveCharacterTextSplitter


class ChartData(BaseModel):
    has_chart: bool = Field(default=False, description="当前版本已关闭新闻图表生成功能，保持为False。")
    chart_title: str = Field(default="", description="保留兼容字段，当前版本不输出新闻图表。")
    labels: List[str] = Field(default_factory=list, description="横坐标标签")
    values: List[float] = Field(default_factory=list, description="纵坐标对应的纯数字")
    chart_type: str = Field(default="bar", description="从 'bar', 'pie', 'line' 中选一个最合适的")


class NewsItem(BaseModel):
    event_id: str = Field(default="", description="必须引用统一事件主档中的 event_id，例如 E01")
    title: str = Field(default="未命名情报", description="新闻标题（务必翻译为中文）")
    source: str = Field(default="未知网络", description="来源媒体")
    date_check: str = Field(default="近期", description="真实日期 YYYY-MM-DD 或 MM月DD日")
    summary: str = Field(
        default="暂无详情",
        description="深度商业分析。必须严格分段并包含：【事件核心】、【深度细节/数据支撑】、【行业深远影响】，总中文篇幅不少于300字。",
    )
    url: str = Field(default="", description="该新闻的原文链接 URL（必须从原始数据中提取）")
    importance: int = Field(default=3, description="重要性 1-5")
    chart_info: ChartData = Field(default_factory=ChartData, description="兼容字段，当前版本固定不生成新闻图表")


class MapReport(BaseModel):
    news: List[NewsItem] = Field(default_factory=list, description="提取的新闻列表，如果没有符合条件的，返回空数组 []")


class NewsReport(BaseModel):
    overall_insight: str = Field(default="近期无重大异动", description="200字以内的全局核心摘要，概括本次所有情报的最核心结论")
    news: List[NewsItem] = Field(default_factory=list, description="新闻列表")


class TranslationPayload(BaseModel):
    text: str = Field(default="暂无详情", description="经翻译和润色后的正式中文摘要")


_ALNUM_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_SUMMARY_LOW_SIGNAL_RE = re.compile(
    r"(share|more ai .* news|related articles|recommended for you|subscribe|newsletter|follow us|"
    r"all rights reserved|privacy policy|terms of service)",
    re.IGNORECASE,
)
_SUMMARY_TIME_RE = re.compile(r"^\d+\s*(m|min|mins|minute|minutes|h|hr|hrs|hour|hours|d|day|days)\s+ago$", re.IGNORECASE)
_SUMMARY_RATING_RE = re.compile(r"^\d+(\.\d+)?$")
_ASCII_TITLEISH_RE = re.compile(r"^[A-Za-z0-9 '&:/().,-]{18,}$")
_ENGLISH_HEAVY_RE = re.compile(r"[A-Za-z]{4,}")
_ENGLISH_WORD_SEQ_RE = re.compile(r"(?:[A-Za-z][A-Za-z0-9'’.-]*\s+){5,}[A-Za-z][A-Za-z0-9'’.-]*")


def _serialize_event_blueprints(event_blueprints):
    payload = []
    for event in event_blueprints or []:
        if hasattr(event, "model_dump"):
            payload.append(event.model_dump())
        elif isinstance(event, dict):
            payload.append(dict(event))
    return payload


def _normalize_text(text):
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", (text or "").lower().strip())


def _tokenize(text):
    words = {token.lower() for token in _ALNUM_RE.findall(text or "") if len(token) >= 2}
    chars = [ch for ch in (text or "") if _CJK_RE.match(ch)]
    if len(chars) < 2:
        return words | set(chars)
    return words | {"".join(chars[idx:idx + 2]) for idx in range(len(chars) - 1)}


def _sanitize_generated_summary(summary_text):
    raw_lines = str(summary_text or "").replace("\r", "\n").splitlines()
    kept = []
    section_hits = {"事件核心": False, "深度细节/数据支撑": False, "行业深远影响": False}

    for line in raw_lines:
        cleaned = line.strip()
        if not cleaned:
            if kept and kept[-1] != "":
                kept.append("")
            continue
        cleaned = re.sub(r"^#{1,6}\s*", "", cleaned).strip()
        lower = cleaned.lower()
        if _SUMMARY_TIME_RE.match(lower):
            continue
        if _SUMMARY_RATING_RE.match(lower):
            continue
        if _SUMMARY_LOW_SIGNAL_RE.search(lower):
            continue
        if len(cleaned) <= 2:
            continue
        if (
            _ASCII_TITLEISH_RE.match(cleaned)
            and not re.search(r"[。！？.!?;；:：]", cleaned)
            and len(cleaned.split()) >= 4
        ):
            continue
        for section_name in list(section_hits.keys()):
            if section_name in cleaned:
                section_hits[section_name] = True
        kept.append(cleaned)

    result = []
    previous = None
    for line in kept:
        if line == "" and previous == "":
            continue
        result.append(line)
        previous = line

    sanitized = "\n".join(result).strip()
    if not sanitized:
        return "暂无详情"
    return sanitized


def _is_english_heavy_line(text):
    cleaned = str(text or "").strip()
    if not cleaned:
        return False
    if cleaned.startswith("【") and cleaned.endswith("】"):
        return False
    english_chars = len(re.findall(r"[A-Za-z]", cleaned))
    cjk_chars = _count_cjk_chars(cleaned)
    if english_chars >= 18 and cjk_chars <= 8:
        return True
    if english_chars >= 28 and cjk_chars < english_chars * 0.25:
        return True
    if _ENGLISH_WORD_SEQ_RE.search(cleaned):
        return True
    if cjk_chars == 0 and _ENGLISH_HEAVY_RE.search(cleaned):
        return True
    return False


def _summary_needs_translation(summary_text):
    lines = [line.strip() for line in str(summary_text or "").splitlines() if line.strip()]
    if not lines:
        return False
    return any(_is_english_heavy_line(line) for line in lines)


def _translate_summary_to_chinese(ai_driver, topic, title, summary_text):
    sanitized = _sanitize_generated_summary(summary_text)
    if not ai_driver or not getattr(ai_driver, "valid", False):
        return sanitized
    if not _summary_needs_translation(sanitized):
        return sanitized

    prompt = f"""
你是中文科技媒体总编。请把下面这条新闻摘要改写成正式、自然、专业的中文。

要求：
1. 必须保留现有结构标签：`【事件核心】`、`【深度细节/数据支撑】`、`【行业深远影响】`。
2. 除专有名词、产品名、机构名外，不得保留完整英文句子或英文段落。
3. 不得新增原文中不存在的事实，只能翻译、压实和中文化现有内容。
4. 译文应适合直接进入 PPT 正文。
5. 如果原文里出现英文引语或英文描述，需翻译成中文表述，不要原样保留。
6. 输出必须以中文为主，不允许出现连续 6 个以上英文单词。
7. 不要保留英文媒体原标题、英文项目说明或英文整句补充说明，必须改写为中文叙述。

专题：{topic}
标题：{title}

待改写摘要：
{sanitized}
"""
    result = ai_driver.analyze_structural(prompt, TranslationPayload)
    translated = _sanitize_generated_summary(getattr(result, "text", "") if result else "")
    if translated and not _summary_needs_translation(translated):
        return translated
    return sanitized


def _count_cjk_chars(text):
    return len(_CJK_RE.findall(str(text or "")))


def _sanitize_news_item(news_item):
    if not news_item:
        return news_item
    title = str(getattr(news_item, "title", "") or "").strip()
    title = re.sub(r"\s*-\s*[A-Z][A-Za-z0-9 '&:/.-]{2,}$", "", title).strip()
    news_item.title = title or "未命名情报"
    news_item.summary = _sanitize_generated_summary(getattr(news_item, "summary", "") or "")
    news_item.chart_info = ChartData()
    return news_item


def _dedupe_news(news_items, event_blueprints):
    if not news_items:
        return []

    event_order = {
        item.get("event_id", ""): index
        for index, item in enumerate(_serialize_event_blueprints(event_blueprints))
    }
    valid_ids = set(event_order.keys())

    picked = {}
    fallback_items = []
    for item in news_items:
        item_id = getattr(item, "event_id", "")
        if item_id and item_id in valid_ids:
            current = picked.get(item_id)
            if current is None:
                picked[item_id] = _sanitize_news_item(item)
                continue

            current_score = (getattr(current, "importance", 0), len(getattr(current, "summary", "")))
            new_score = (getattr(item, "importance", 0), len(getattr(item, "summary", "")))
            if new_score > current_score:
                picked[item_id] = _sanitize_news_item(item)
        else:
            fallback_items.append(_sanitize_news_item(item))

    ordered = [picked[event_id] for event_id in event_order if event_id in picked]
    ordered.extend(fallback_items)
    return ordered[:5]


def _score_event_mapping(news_item, blueprint):
    title = (getattr(news_item, "title", "") or "").lower()
    summary = (getattr(news_item, "summary", "") or "")[:180].lower()
    event_text = (blueprint.get("event", "") or "").lower()
    keywords = " ".join(blueprint.get("keywords", []) or []).lower()
    corpus = f"{title} {summary}"
    reference = f"{event_text} {keywords}".strip()
    if not corpus.strip() or not reference.strip():
        return 0.0
    shared_hits = sum(1 for token in (blueprint.get("keywords", []) or []) if token and token.lower() in corpus)
    keyword_bonus = min(shared_hits * 0.12, 0.36)
    similarity = 0.0
    try:
        import difflib

        similarity = difflib.SequenceMatcher(None, corpus, reference).ratio()
    except Exception:
        similarity = 0.0
    substring_bonus = 0.18 if event_text and event_text in corpus else 0.0
    return similarity * 0.72 + keyword_bonus + substring_bonus


def _backfill_event_ids(news_items, event_blueprints):
    blueprint_payload = _serialize_event_blueprints(event_blueprints)
    if not blueprint_payload:
        return news_items

    for item in news_items or []:
        if getattr(item, "event_id", ""):
            continue

        best_id = ""
        best_score = 0.0
        for blueprint in blueprint_payload:
            score = _score_event_mapping(item, blueprint)
            if score > best_score:
                best_score = score
                best_id = blueprint.get("event_id", "")

        if best_id and best_score >= 0.30:
            item.event_id = best_id

    return news_items


def _normalize_invalid_event_ids(news_items, valid_event_ids):
    valid_set = set(valid_event_ids or [])
    for item in news_items or []:
        event_id = getattr(item, "event_id", "") or ""
        if event_id and event_id not in valid_set:
            item.event_id = ""
    return news_items


def _supporting_result_score(blueprint, result):
    event_text = blueprint.get("event", "") or ""
    event_tokens = _tokenize(f"{event_text} {' '.join(blueprint.get('keywords', []) or [])}")
    title = str(result.get("title", "") or "")
    snippet = str(result.get("content", "") or "")
    corpus = f"{title} {snippet}"
    result_tokens = _tokenize(corpus)
    overlap = len(event_tokens & result_tokens) / max(len(event_tokens), 1)

    title_ratio = 0.0
    event_norm = _normalize_text(event_text)
    title_norm = _normalize_text(title)
    if event_norm and title_norm:
        try:
            import difflib

            title_ratio = difflib.SequenceMatcher(None, event_norm, title_norm).ratio()
        except Exception:
            title_ratio = 0.0

    keyword_hits = sum(
        1 for token in (blueprint.get("keywords", []) or [])
        if token and str(token).lower() in corpus.lower()
    )
    return round(title_ratio * 0.48 + overlap * 0.34 + min(keyword_hits * 0.08, 0.24), 4)


def _trim_text(text, limit):
    raw = str(text or "").strip()
    raw = re.sub(r"(\.\.\.|…)+$", "", raw).strip()
    if len(raw) <= limit:
        return raw
    clipped = raw[:limit].rstrip(" ，,;；。.!?！？")
    sentence_break = max(clipped.rfind("。"), clipped.rfind("！"), clipped.rfind("？"))
    if sentence_break >= max(20, int(limit * 0.45)):
        return clipped[: sentence_break + 1]
    return clipped


def _format_result_date(result, fallback="近期"):
    return (
        result.get("published_at_resolved")
        or result.get("published_date")
        or result.get("published")
        or fallback
    )


def _build_fallback_summary(topic, blueprint, supporting_results):
    primary = dict(supporting_results[0]) if supporting_results else {}
    title = primary.get("title") or blueprint.get("event", "") or "近期动态"
    snippet = primary.get("content") or ""
    secondary = dict(supporting_results[1]) if len(supporting_results) > 1 else {}
    secondary_title = secondary.get("title", "")
    secondary_snippet = secondary.get("content", "")
    tertiary = dict(supporting_results[2]) if len(supporting_results) > 2 else {}
    tertiary_title = tertiary.get("title", "")
    tertiary_snippet = tertiary.get("content", "")
    source = primary.get("source") or blueprint.get("source", "综合报道")
    keywords = "、".join((blueprint.get("keywords", []) or [])[:4])
    influence_hint = keywords or title

    parts = [
        f"【事件核心】\n{source} 等来源显示，{title}。这条动态直接对应"
        f"“{blueprint.get('event', '') or title}”这一事件本身，核心信息聚焦于相关业务推进、产品变化或资本市场信号。"
    ]
    if snippet:
        detail_lines = [_trim_text(snippet, 520)]
        if secondary_title or secondary_snippet:
            detail_lines.append(f"补充来源还显示：{_trim_text(secondary_snippet or secondary_title, 320)}")
        if tertiary_title or tertiary_snippet:
            detail_lines.append(f"第三方报道补充称：{_trim_text(tertiary_snippet or tertiary_title, 260)}")
        parts.append(f"【深度细节/数据支撑】\n{' '.join([line for line in detail_lines if line])}")
    elif blueprint.get("event"):
        fallback_detail = (
            f"现有抓取结果显示，“{blueprint.get('event', '')}”相关信息已出现较明确的主题聚焦，相关关键词包括：{keywords or '暂无更多细节'}。"
            "虽然当前材料不一定全部来自原文级全文，但已足以说明该事件在产品、业务、市场反馈或产业链层面具备持续跟踪价值。"
        )
        if secondary_title or secondary_snippet:
            fallback_detail += f" 补充来源还提到：{_trim_text(secondary_snippet or secondary_title, 260)}"
        parts.append(f"【深度细节/数据支撑】\n{fallback_detail}")
    parts.append(
        f"【行业深远影响】\n这条动态说明【{topic}】在“{influence_hint}”方向仍有新的产品、监管、商业化或生态进展。"
        "如果后续还有更多数据披露、管理层表态、供应链反馈或竞品应对，这件事很可能继续影响市场预期与行业比较框架，"
        "因此值得持续跟踪其后续细节、节奏变化以及外部反应。"
    )
    return "\n".join([part for part in parts if part])


def _collect_supporting_results(blueprint, raw_search_results, limit=3):
    scored_results = []
    for result in raw_search_results or []:
        score = _supporting_result_score(blueprint, result)
        if score >= 0.24:
            scored_results.append((score, result))
    scored_results.sort(
        key=lambda item: (item[0], item[1].get("published_at_resolved") or item[1].get("published_date") or ""),
        reverse=True,
    )
    return [item[1] for item in scored_results[:limit]]


def _expand_short_summary(summary_text, topic, blueprint, supporting_results):
    summary = _sanitize_generated_summary(summary_text)
    if _count_cjk_chars(summary) >= 300:
        return summary

    extra_lines = []
    normalized_summary = _normalize_text(summary)
    for result in supporting_results[:3]:
        candidate = _trim_text(result.get("content") or result.get("title") or "", 260)
        if not candidate:
            continue
        normalized_candidate = _normalize_text(candidate)
        if normalized_candidate and normalized_candidate[:80] in normalized_summary:
            continue
        extra_lines.append(candidate)

    if extra_lines:
        summary += "\n补充来源显示：" + "；".join(extra_lines[:2]).rstrip("；;。") + "。"

    if _count_cjk_chars(summary) < 300:
        focus_hint = "、".join((blueprint.get("keywords", []) or [])[:4]) or blueprint.get("event", "") or topic
        summary += (
            f"\n补充说明：围绕“{focus_hint}”的后续信息仍在持续增加，"
            "后续更值得关注管理层表态、业务执行节奏、市场反馈以及产业链侧是否出现进一步印证。"
        )

    return _sanitize_generated_summary(summary)


def _supplement_news_from_blueprints(news_items, event_blueprints, raw_search_results, topic, min_count=4, max_count=5):
    existing_items = list(news_items or [])
    if len(existing_items) >= min_count:
        return existing_items[:max_count]

    covered_ids = {getattr(item, "event_id", "") for item in existing_items if getattr(item, "event_id", "")}
    covered_titles = {_normalize_text(getattr(item, "title", "") or "") for item in existing_items}

    for blueprint in _serialize_event_blueprints(event_blueprints):
        if len(existing_items) >= min_count or len(existing_items) >= max_count:
            break

        event_id = blueprint.get("event_id", "") or ""
        event_title = blueprint.get("event", "") or ""
        if event_id and event_id in covered_ids:
            continue
        if event_title and _normalize_text(event_title) in covered_titles:
            continue

        supporting_results = _collect_supporting_results(blueprint, raw_search_results, limit=3)
        if not supporting_results and not event_title:
            continue

        primary = supporting_results[0] if supporting_results else {}
        fallback_news = NewsItem(
            event_id=event_id,
            title=event_title or primary.get("title", "未命名情报"),
            source=primary.get("source") or blueprint.get("source", "综合报道"),
            date_check=_format_result_date(primary, blueprint.get("date", "近期")),
            summary=_build_fallback_summary(topic, blueprint, supporting_results),
            url=primary.get("url") or blueprint.get("source_url", ""),
            importance=4 if supporting_results else 3,
        )
        existing_items.append(fallback_news)
        if event_id:
            covered_ids.add(event_id)
        if event_title:
            covered_titles.add(_normalize_text(event_title))

    return existing_items[:max_count]


def _resolve_analysis_profile(report_profile, time_opt):
    profile = {
        "mode_key": "daily_24h",
        "summary_title": "",
        "min_news": 4,
        "max_news": 5,
    }
    raw_profile = dict(report_profile or {})
    if raw_profile:
        profile["mode_key"] = str(raw_profile.get("key") or profile["mode_key"]).strip() or profile["mode_key"]
        profile["summary_title"] = str(raw_profile.get("summary_title") or "").strip()
        try:
            profile["min_news"] = max(3, int(raw_profile.get("analysis_min_news") or profile["min_news"]))
        except Exception:
            pass
        try:
            profile["max_news"] = max(profile["min_news"], int(raw_profile.get("analysis_max_news") or profile["max_news"]))
        except Exception:
            pass

    time_text = str(time_opt or "")
    if profile["mode_key"] == "daily_24h":
        if "1 周" in time_text or "周报" in time_text:
            profile.update({
                "mode_key": "weekly_7d",
                "summary_title": profile["summary_title"] or "本周主题总结",
                "min_news": max(profile["min_news"], 6),
                "max_news": max(profile["max_news"], 8),
            })
        elif "1 个月" in time_text or "月" in time_text:
            profile.update({
                "mode_key": "monthly_30d",
                "summary_title": profile["summary_title"] or "本月主题总结",
                "min_news": max(profile["min_news"], 6),
                "max_news": max(profile["max_news"], 8),
            })
    return profile



def _finalize_news_output(final_report, event_blueprints, valid_event_ids, raw_search_results, topic, ai_driver=None, report_profile=None):
    analysis_profile = _resolve_analysis_profile(report_profile, "")
    target_min = int(analysis_profile.get("min_news", 4) or 4)
    target_max = int(analysis_profile.get("max_news", 5) or 5)
    if not final_report:
        fallback_news = _supplement_news_from_blueprints(
            [],
            event_blueprints,
            raw_search_results,
            topic,
            min_count=target_min,
            max_count=target_max,
        )
        for news_item in fallback_news:
            news_item.summary = _translate_summary_to_chinese(ai_driver, topic, getattr(news_item, "title", ""), getattr(news_item, "summary", "") or "")
        return fallback_news, ""

    final_report.news = [_sanitize_news_item(item) for item in (final_report.news or [])]
    final_news = _backfill_event_ids(final_report.news, event_blueprints)
    final_news = _normalize_invalid_event_ids(final_news, valid_event_ids)
    final_news = _dedupe_news(final_news, event_blueprints)
    final_news = _supplement_news_from_blueprints(
        final_news,
        event_blueprints,
        raw_search_results,
        topic,
        min_count=target_min,
        max_count=target_max,
    )
    blueprint_map = {item.get("event_id", ""): item for item in _serialize_event_blueprints(event_blueprints)}
    for news_item in final_news:
        blueprint = blueprint_map.get(getattr(news_item, "event_id", "") or "", {})
        supporting_results = _collect_supporting_results(blueprint, raw_search_results, limit=3) if blueprint else []
        news_item.summary = _expand_short_summary(
            getattr(news_item, "summary", "") or "",
            topic,
            blueprint,
            supporting_results,
        )
        news_item.summary = _translate_summary_to_chinese(
            ai_driver,
            topic,
            getattr(news_item, "title", "") or "",
            getattr(news_item, "summary", "") or "",
        )
    return final_news, final_report.overall_insight



def map_reduce_analysis(
    ai_driver,
    topic,
    full_text,
    current_date,
    time_opt,
    past_memories_string="",
    event_blueprints=None,
    source_mode="full_text",
    guidance="",
    raw_search_results=None,
    map_ai_driver=None,
    report_profile=None,
):
    analysis_profile = _resolve_analysis_profile(report_profile, time_opt)
    target_min_news = int(analysis_profile.get("min_news", 4) or 4)
    target_max_news = int(analysis_profile.get("max_news", 5) or 5)
    summary_title = str(analysis_profile.get("summary_title", "") or "").strip()
    report_mode_key = str(analysis_profile.get("mode_key", "daily_24h") or "daily_24h")

    if not full_text or len(full_text) < 100:
        return _supplement_news_from_blueprints(
            [],
            event_blueprints,
            raw_search_results,
            topic,
            min_count=target_min_news,
            max_count=target_max_news,
        ), ""

    blueprint_payload = _serialize_event_blueprints(event_blueprints)
    blueprint_json = json.dumps(blueprint_payload, ensure_ascii=False)
    has_event_blueprints = bool(blueprint_payload)
    valid_event_ids = [item.get("event_id", "") for item in blueprint_payload if item.get("event_id")]
    docs = RecursiveCharacterTextSplitter(chunk_size=6000, chunk_overlap=300).create_documents([full_text])
    all_extracted_news = []
    map_driver = map_ai_driver or ai_driver

    if source_mode == "full_text":
        source_mode_note = "当前输入是全文抓取结果，可以做细节归纳，但仍然不得编造文本中不存在的事实。"
    elif source_mode == "mixed_fallback":
        source_mode_note = (
            "当前输入是混合抽取结果，既包含全文，也可能混有网页直连抽取和少量搜索摘要补位。"
            "可以做结构化分析，但对原文引语、极细粒度数据和细节动作要谨慎，信息不足时需明确说明。"
        )
    else:
        source_mode_note = (
            "当前输入不是全文抓取，而是搜索摘要降级模式。禁止伪造原文引语、精细动作、独家细节或未出现的数据；"
            "信息不足时要明确写成‘现有摘要显示’。"
        )
    guidance_block = f"\n        【专题聚焦要求】：\n        {guidance}\n" if guidance else ""
    is_weekly_like = report_mode_key in {"weekly_7d", "monthly_30d"}
    news_count_text = f"{target_min_news} 到 {target_max_news} 条"
    summary_floor_chars = 260 if is_weekly_like else 300
    coverage_instruction = (
        "周报/长周期模式下，优先覆盖这一时间窗口内彼此不同的热点子主题、关键催化和重要来源确认，不要把一周内容过度并成 1 到 2 条大事件。"
        if is_weekly_like else
        "优先保留当前时间窗口内最值得展开的不同事件，不要把本来彼此独立的重要新闻过度合并。"
    )
    summary_instruction = (
        f"提炼 overall_insight（220字以内），作为“{summary_title or '主题总结'}”，必须概括这个时间窗口内的主线变化、次主线、关键催化和后续观察点。"
        if is_weekly_like else
        "提炼 overall_insight（200字以内），记录今天的核心结论。"
    )

    event_constraint_text = ""
    if has_event_blueprints:
        event_constraint_text = f"""
        【统一事件主档】：
        {blueprint_json}

        你应当优先围绕这些 event_id 提取候选事件。
        1. 能明确映射时，优先填写已有 event_id。
        2. 如果某条候选明显属于【{topic}】在当前时间窗口内的重要事件，但一时无法可靠映射，可暂时留空 event_id，不要直接丢弃。
        3. 不得新建虚构 event_id。
        4. 同一个 event_id 在一个切片中最多保留一条候选；event_id 为空的候选也要避免重复。
        """

    if source_mode == "search_summary_fallback":
        if is_weekly_like:
            detail_prompt = (
                "要求每条新闻总中文篇幅不少于 260 字，建议控制在 280 到 420 字。"
                "【事件核心】至少 70 字，【深度细节/数据支撑】至少 120 字，【行业深远影响】至少 70 字。"
                "只能基于现有搜索摘要做事实概括和行业判断，不得伪造原文直接引语、微观动作或超细颗粒数据。"
            )
        else:
            detail_prompt = (
                "要求每条新闻总中文篇幅不少于 300 字，建议控制在 320 到 450 字。"
                "【事件核心】至少 70 字，【深度细节/数据支撑】至少 150 字，【行业深远影响】至少 80 字。"
                "只能基于现有搜索摘要做事实概括和行业判断，不得伪造原文直接引语、微观动作或超细颗粒数据。"
            )
    elif source_mode == "mixed_fallback":
        if is_weekly_like:
            detail_prompt = (
                "要求每条新闻总中文篇幅不少于 280 字，建议控制在 320 到 460 字。"
                "【事件核心】至少 80 字，【深度细节/数据支撑】至少 130 字，【行业深远影响】至少 80 字。"
                "可以结合全文和网页抽取做分析，但对直接引语、超细颗粒数字和过度确定的因果判断要保守表达。"
            )
        else:
            detail_prompt = (
                "要求每条新闻总中文篇幅不少于 320 字，建议控制在 360 到 560 字。"
                "【事件核心】至少 80 字，【深度细节/数据支撑】至少 160 字，【行业深远影响】至少 90 字。"
                "可以结合全文和网页抽取做分析，但对直接引语、超细颗粒数字和过度确定的因果判断要保守表达。"
            )
    elif report_mode_key == "daily_24h":
        detail_prompt = (
            "要求每条新闻总中文篇幅不少于 320 字，建议控制在 360 到 520 字。"
            "【事件核心】至少 80 字，【深度细节/数据支撑】至少 160 字，【行业深远影响】至少 90 字。"
            "优先保留能支撑判断的具体数字、核心动作、原话要点和业务影响；不要为了控制篇幅而把摘要压成过短版本。"
        )
    else:
        detail_prompt = (
            "要求每条新闻总中文篇幅不少于 280 字，建议控制在 320 到 460 字。"
            "【事件核心】至少 80 字，【深度细节/数据支撑】至少 130 字，【行业深远影响】至少 80 字。"
            "侧重于覆盖整个时间窗口内的重要热点，同时总结战略意图、主线变化和行业影响。"
        )

    event_reduce_text = ""
    if has_event_blueprints:
        event_reduce_text = f"""
        【统一事件主档】：
        {blueprint_json}

        输出规则：
        1. 最终 news 应优先填写统一事件主档中的 event_id。
        2. 每个 event_id 最多保留一条最终长新闻，避免同一事件重复展开。
        3. 如果有 1 到 2 条高重要度候选无法可靠映射，但它确实是【{topic}】在当前时间窗口内的重要事件，允许保留并将 event_id 留空。
        4. 不要因为 event_id 不确定就牺牲重要新闻覆盖度，但也不要混入无关事件。
        5. 最终新闻顺序应尽量与统一事件主档顺序一致，无法映射的高价值候选放在后面。
        """

    if len(docs) <= 2:
        direct_prompt = f"""
        【全局时间锚点】：今天是 **{current_date}**。你是顶级科技媒体总编。

        【🧠 你的历史记忆库】：
        {past_memories_string}

        【📰 当前时间窗口的来源材料】：
        {full_text}

        {event_reduce_text}
        {source_mode_note}
        {guidance_block}

        任务：
        1. 仅基于以上材料，提炼并深度扩写关于【{topic}】的 {news_count_text} 条真正重要的近期新闻。
        2. 终极剔除旧闻与无关陪衬事件，遇到同一事件必须合并。
        3. {detail_prompt}
        3.1 严禁把网页导航、分享按钮、相关推荐、时间标签、评分、订阅提示、栏目列表当作正文细节写入摘要。
        3.2 任何一条 news.summary 如果中文正文不足 {summary_floor_chars} 字，视为不合格，需要继续补足细节和影响分析。
        4. 如果当前时间窗口内的新情报与历史记忆存在延续、推进或反转，请在【事件核心】中明确写出“前情回顾”。
        5. 当前版本不生成新闻图表，请忽略 chart_info，保持其默认空值，不要为了图表组织任何内容。
        6. 优先填写统一事件主档中的 event_id；如无法可靠映射但事件确实重要，可将 event_id 留空。
        7. 优先保留 {news_count_text} 条彼此不同的重要事件；只有当当前窗口内确实不足 {target_min_news} 条时，才允许少于 {target_min_news} 条。
        8. 除专有名词外，尽量用中文表述，不要直接把英文标题、侧栏栏目名或站点 slogan 粘进【深度细节/数据支撑】。
        9. {coverage_instruction}
        10. {summary_instruction}
        """
        direct_report = ai_driver.analyze_structural(direct_prompt, NewsReport)
        return _finalize_news_output(
            direct_report,
            event_blueprints,
            valid_event_ids,
            raw_search_results,
            topic,
            ai_driver=ai_driver,
            report_profile=analysis_profile,
        )

    def process_single_doc(doc):
        map_prompt = f"""
        【时间锚点】：今天是 **{current_date}**。要求范围：【{time_opt}】。
        任务：提取关于【{topic}】的新闻情报候选。
        红线：发现早于要求时间的旧闻直接丢弃！【{topic}】必须是绝对主角！无符合条件必须返回空的 news 数组。
        如果同一切片里存在 2 到 3 条彼此不同、且都足够重要的事件，请尽量都保留下来，不要过度合并。
        {source_mode_note}
        {guidance_block}
        {event_constraint_text}
        文本：{doc.page_content}
        """
        return map_driver.analyze_structural(map_prompt, MapReport)

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        for future in concurrent.futures.as_completed([executor.submit(process_single_doc, d) for d in docs]):
            try:
                res = future.result()
                if res and res.news:
                    all_extracted_news.extend(res.news)
            except Exception as e:
                print(f"切片提取失败: {e}")

    if not all_extracted_news:
        return _supplement_news_from_blueprints(
            [],
            event_blueprints,
            raw_search_results,
            topic,
            min_count=target_min_news,
            max_count=target_max_news,
        ), ""

    combined_json = json.dumps([item.model_dump() for item in all_extracted_news], ensure_ascii=False)

    reduce_prompt = f"""
        【全局时间锚点】：今天是 **{current_date}**。你是顶级科技媒体总编。

        【🧠 你的历史记忆库】：
        {past_memories_string}

        【📰 当前时间窗口的新情报碎片】：
        {combined_json}

        {event_reduce_text}
        {source_mode_note}
        {guidance_block}

        任务：
        1. 终极剔除旧闻。2. 合并同事件新闻。
        3. 深度扩写排版：
        {detail_prompt}
        4. 严禁把网页导航、分享按钮、相关推荐、时间标签、评分、订阅提示、栏目列表、站点 slogan 当作正文细节写入摘要。
        4.1 任何一条 news.summary 如果中文正文不足 {summary_floor_chars} 字，视为不合格，需要继续补足事实、细节和影响分析。
        5. 如果当前时间窗口内的新情报与【你的历史记忆库】存在延续性、推进或重大反转，请务必在【事件核心】中以“前情回顾”的口吻明确指出并进行对比。
        6. 当前版本不生成新闻图表，请忽略 chart_info，保持其默认空值，不得为了图表而压缩正文篇幅。
        7. {summary_instruction}
        8. 优先保留 {news_count_text} 条真正重要的新闻；只有当当前窗口内确实不足 {target_min_news} 条时，才允许少于 {target_min_news} 条。
        9. 不要因为“映射不够完美”而过度删减，只要事件真实、近期、重要、且【{topic}】是主角，就应尽量保留。
        10. 如果存在 {news_count_text} 条彼此不同的重要事件，请不要把它们过度合并成 1 到 2 条大而空的新闻。
        11. 除专有名词外，尽量用中文表述，不要直接粘贴英文标题和页面噪音。
        12. {coverage_instruction}
    """

    final_report = ai_driver.analyze_structural(reduce_prompt, NewsReport)
    return _finalize_news_output(
        final_report,
        event_blueprints,
        valid_event_ids,
        raw_search_results,
        topic,
        ai_driver=ai_driver,
        report_profile=analysis_profile,
    )
