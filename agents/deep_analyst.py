import json
import concurrent.futures
import re
from pydantic import BaseModel, Field
from typing import List
from langchain_text_splitters import RecursiveCharacterTextSplitter


class ChartData(BaseModel):
    has_chart: bool = Field(default=False, description="如果新闻中包含2个及以上的具体对比数据，设为True；否则设为False。")
    chart_title: str = Field(default="", description="图表的标题，例如：2024各厂AI模型参数量对比")
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
    chart_info: ChartData = Field(default_factory=ChartData, description="自动化图表数据提取")


class MapReport(BaseModel):
    news: List[NewsItem] = Field(default_factory=list, description="提取的新闻列表，如果没有符合条件的，返回空数组 []")


class NewsReport(BaseModel):
    overall_insight: str = Field(default="近期无重大异动", description="200字以内的全局核心摘要，概括本次所有情报的最核心结论")
    news: List[NewsItem] = Field(default_factory=list, description="新闻列表")


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
_META_ANALYSIS_RE = re.compile(
    r"(主轴集中在|当前抓取结果围绕|现有材料显示|补充判断|值得持续跟踪|如果后续还有更多数据披露|"
    r"持续增加|业务推进、产品变化或资本市场信号|所对应的业务推进)",
    re.IGNORECASE,
)


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


def _text_match_score(text, blueprint):
    corpus = str(text or "").lower().strip()
    if not corpus:
        return 0.0
    event_text = (blueprint.get("event", "") or "").lower()
    keywords = " ".join(blueprint.get("keywords", []) or []).lower()
    reference = f"{event_text} {keywords}".strip()
    if not reference:
        return 0.0
    corpus_tokens = _tokenize(corpus)
    ref_tokens = _tokenize(reference)
    overlap = len(corpus_tokens & ref_tokens) / max(len(ref_tokens), 1)
    similarity = 0.0
    try:
        import difflib

        similarity = difflib.SequenceMatcher(None, corpus, reference).ratio()
    except Exception:
        similarity = 0.0
    keyword_hits = sum(1 for token in (blueprint.get("keywords", []) or []) if token and str(token).lower() in corpus)
    substring_bonus = 0.18 if event_text and event_text in corpus else 0.0
    return round(similarity * 0.46 + overlap * 0.36 + min(keyword_hits * 0.07, 0.21) + substring_bonus, 4)


def _contains_meta_analysis(summary_text):
    return bool(_META_ANALYSIS_RE.search(str(summary_text or "")))


def _summary_relevance_score(summary_text, title_text, blueprint):
    summary_tokens = _tokenize(summary_text or "")
    title_tokens = _tokenize(title_text or "")
    ref_tokens = _tokenize(f"{blueprint.get('event', '')} {' '.join(blueprint.get('keywords', []) or [])}")
    if not summary_tokens:
        return 0.0
    title_overlap = len(summary_tokens & title_tokens) / max(len(title_tokens), 1) if title_tokens else 0.0
    ref_overlap = len(summary_tokens & ref_tokens) / max(len(ref_tokens), 1) if ref_tokens else 0.0
    return round(title_overlap * 0.55 + ref_overlap * 0.45, 4)


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


def _count_cjk_chars(text):
    return len(_CJK_RE.findall(str(text or "")))


def _sanitize_news_item(news_item):
    if not news_item:
        return news_item
    title = str(getattr(news_item, "title", "") or "").strip()
    title = re.sub(r"\s*-\s*[A-Z][A-Za-z0-9 '&:/.-]{2,}$", "", title).strip()
    news_item.title = title or "未命名情报"
    news_item.summary = _sanitize_generated_summary(getattr(news_item, "summary", "") or "")
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
    title = str(result.get("title", "") or "")
    snippet = str(result.get("content", "") or "")
    title_score = _text_match_score(title, blueprint)
    snippet_score = _text_match_score(snippet, blueprint)
    return round(title_score * 0.68 + snippet_score * 0.32, 4)


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
    title_score = float(primary.get("_title_score", 0.0) or 0.0)
    snippet_score = float(primary.get("_snippet_score", 0.0) or 0.0)

    core_title = _trim_text(title, 68) or blueprint.get("event", "") or "相关动态"
    primary_fact = _trim_text(snippet, 220) if snippet_score >= 0.34 else ""
    secondary_fact = _trim_text(secondary_snippet or secondary_title, 180) if secondary and float(secondary.get("_snippet_score", 0.0) or 0.0) >= 0.30 else _trim_text(secondary_title, 68)
    tertiary_fact = _trim_text(tertiary_snippet or tertiary_title, 160) if tertiary and float(tertiary.get("_snippet_score", 0.0) or 0.0) >= 0.30 else _trim_text(tertiary_title, 60)

    parts = [
        f"【事件核心】\n据{source}报道，{core_title}。"
        + (f" 公开片段显示，{primary_fact}" if primary_fact else "")
    ]
    if primary_fact or secondary_fact or tertiary_fact:
        detail_lines = []
        if primary_fact:
            detail_lines.append(primary_fact)
        elif title_score >= 0.32:
            detail_lines.append(f"这条报道的核心事实就是“{core_title}”。")
        if secondary_fact:
            detail_lines.append(f"补充报道提到：{secondary_fact}")
        if tertiary_fact:
            detail_lines.append(f"另有来源提到：{tertiary_fact}")
        parts.append(f"【深度细节/数据支撑】\n{' '.join([line for line in detail_lines if line])}")
    elif blueprint.get("event"):
        fallback_detail = (
            f"目前可确认的信息是：这条新闻直接对应“{blueprint.get('event', '')}”这一事件本身。"
            f" 现阶段能提炼出的关键信息主要涉及：{keywords or '暂无更多细节'}。"
        )
        if secondary_title or secondary_snippet:
            fallback_detail += f" 补充来源提到：{_trim_text(secondary_snippet or secondary_title, 220)}"
        parts.append(f"【深度细节/数据支撑】\n{fallback_detail}")
    parts.append(
        f"【行业深远影响】\n这条事件会影响【{topic}】在“{influence_hint}”方向的市场预期、竞争节奏或政策判断。"
        "如果后续继续出现管理层表态、执行细节、供应链反馈或监管动作，相关影响会进一步清晰。"
    )
    return "\n".join([part for part in parts if part])


def _collect_supporting_results(blueprint, raw_search_results, limit=3):
    scored_results = []
    for result in raw_search_results or []:
        title_score = _text_match_score(result.get("title", "") or "", blueprint)
        snippet_score = _text_match_score(result.get("content", "") or "", blueprint)
        score = round(title_score * 0.68 + snippet_score * 0.32, 4)
        if score >= 0.26 and max(title_score, snippet_score) >= 0.20:
            enriched = dict(result)
            enriched["_title_score"] = title_score
            enriched["_snippet_score"] = snippet_score
            scored_results.append((score, enriched))
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
        snippet_score = float(result.get("_snippet_score", 0.0) or 0.0)
        title_score = float(result.get("_title_score", 0.0) or 0.0)
        if snippet_score >= 0.36:
            candidate = _trim_text(result.get("content") or "", 220)
        elif title_score >= 0.55:
            candidate = _trim_text(result.get("title") or "", 72)
        else:
            candidate = ""
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
            f"\n后续最值得继续关注的是“{focus_hint}”相关的新事实、执行动作、监管变化与市场反馈，"
            "这些新增信息将决定这条事件的实际影响范围和持续时间。"
        )

    return _sanitize_generated_summary(summary)


def _should_rebuild_summary(summary_text, news_item, blueprint):
    summary = _sanitize_generated_summary(summary_text)
    if not summary or summary == "暂无详情":
        return True
    if _contains_meta_analysis(summary):
        return True
    lines = [line.strip() for line in summary.splitlines() if line.strip()]
    short_bullet_like = sum(
        1 for line in lines
        if len(line) <= 12 and "【" not in line and not re.search(r"[。！？.!?]", line)
    )
    if short_bullet_like >= 4:
        return True
    title_text = getattr(news_item, "title", "") or blueprint.get("event", "")
    if _summary_relevance_score(summary, title_text, blueprint) < 0.14:
        return True
    return False


def _rebuild_summary_if_needed(news_item, topic, blueprint, supporting_results):
    current_summary = getattr(news_item, "summary", "") or ""
    if not _should_rebuild_summary(current_summary, news_item, blueprint):
        expanded = _expand_short_summary(current_summary, topic, blueprint, supporting_results)
        if not _contains_meta_analysis(expanded):
            return expanded
    rebuilt = _build_fallback_summary(topic, blueprint, supporting_results)
    expanded = _expand_short_summary(rebuilt, topic, blueprint, supporting_results)
    if _contains_meta_analysis(expanded):
        return _sanitize_generated_summary(rebuilt)
    return expanded


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



def _finalize_news_output(final_report, event_blueprints, valid_event_ids, raw_search_results, topic):
    if not final_report:
        fallback_news = _supplement_news_from_blueprints([], event_blueprints, raw_search_results, topic, min_count=4, max_count=5)
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
        min_count=4,
        max_count=5,
    )
    blueprint_map = {item.get("event_id", ""): item for item in _serialize_event_blueprints(event_blueprints)}
    for news_item in final_news:
        blueprint = blueprint_map.get(getattr(news_item, "event_id", "") or "", {})
        supporting_results = _collect_supporting_results(blueprint, raw_search_results, limit=3) if blueprint else []
        news_item.summary = _rebuild_summary_if_needed(
            news_item,
            topic,
            blueprint,
            supporting_results,
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
):
    if not full_text or len(full_text) < 100:
        return _supplement_news_from_blueprints([], event_blueprints, raw_search_results, topic, min_count=4, max_count=5), ""

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
        detail_prompt = (
            "要求每条新闻总中文篇幅不少于 300 字，建议控制在 320 到 450 字。"
            "【事件核心】至少 70 字，【深度细节/数据支撑】至少 150 字，【行业深远影响】至少 80 字。"
            "只能基于现有搜索摘要做事实概括和行业判断，不得伪造原文直接引语、微观动作或超细颗粒数据。"
        )
    elif source_mode == "mixed_fallback":
        detail_prompt = (
            "要求每条新闻总中文篇幅不少于 320 字，建议控制在 360 到 560 字。"
            "【事件核心】至少 80 字，【深度细节/数据支撑】至少 160 字，【行业深远影响】至少 90 字。"
            "可以结合全文和网页抽取做分析，但对直接引语、超细颗粒数字和过度确定的因果判断要保守表达。"
        )
    elif "24" in time_opt:
        detail_prompt = (
            "要求每条新闻总中文篇幅不少于 320 字，建议控制在 360 到 520 字。"
            "【事件核心】至少 80 字，【深度细节/数据支撑】至少 160 字，【行业深远影响】至少 90 字。"
            "优先保留能支撑判断的具体数字、核心动作、原话要点和业务影响；不要为了控制篇幅而把摘要压成过短版本。"
        )
    else:
        detail_prompt = (
            "要求每条新闻总中文篇幅不少于 320 字，建议控制在 360 到 500 字。"
            "【事件核心】至少 80 字，【深度细节/数据支撑】至少 160 字，【行业深远影响】至少 90 字。"
            "侧重于宏观趋势、战略意图和行业影响的完整分析。"
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

        【📰 今天的来源材料】：
        {full_text}

        {event_reduce_text}
        {source_mode_note}
        {guidance_block}

        任务：
        1. 仅基于以上材料，提炼并深度扩写关于【{topic}】的 3 到 5 条真正重要的近期新闻。
        2. 终极剔除旧闻与无关陪衬事件，遇到同一事件必须合并。
        3. {detail_prompt}
        3.1 严禁把网页导航、分享按钮、相关推荐、时间标签、评分、订阅提示、栏目列表当作正文细节写入摘要。
        3.2 任何一条 news.summary 如果中文正文不足 300 字，视为不合格，需要继续补足细节和影响分析。
        3.3 禁止写“主轴集中在”“当前抓取结果围绕”“现有材料显示”“补充判断”等分析过程口吻，必须直接叙述事件事实本身。
        3.4 如果标题与正文片段明显不一致，优先使用标题和高相关片段，只写可确认事实，不要把疑似污染正文写入摘要。
        4. 如果今天的新情报与历史记忆存在延续、推进或反转，请在【事件核心】中明确写出“前情回顾”。
        5. 如果新闻中出现明显的数据对比，请尽量准确提取到 chart_info 中，但不要为了图表牺牲 summary 的完整叙述。
        6. 优先填写统一事件主档中的 event_id；如无法可靠映射但事件确实重要，可将 event_id 留空。
        7. 优先保留 3 到 5 条彼此不同的重要事件，不要为了稳妥把 3 到 5 条压成 1 到 2 条。
        8. 除专有名词外，尽量用中文表述，不要直接把英文标题、侧栏栏目名或站点 slogan 粘进【深度细节/数据支撑】。
        """
        direct_report = ai_driver.analyze_structural(direct_prompt, NewsReport)
        return _finalize_news_output(direct_report, event_blueprints, valid_event_ids, raw_search_results, topic)

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
        return _supplement_news_from_blueprints([], event_blueprints, raw_search_results, topic, min_count=4, max_count=5), ""

    combined_json = json.dumps([item.model_dump() for item in all_extracted_news], ensure_ascii=False)

    reduce_prompt = f"""
        【全局时间锚点】：今天是 **{current_date}**。你是顶级科技媒体总编。

        【🧠 你的历史记忆库】：
        {past_memories_string}

        【📰 今天的新情报碎片】：
        {combined_json}

        {event_reduce_text}
        {source_mode_note}
        {guidance_block}

        任务：
        1. 终极剔除旧闻。2. 合并同事件新闻。
        3. 深度扩写排版：
        {detail_prompt}
        4. 严禁把网页导航、分享按钮、相关推荐、时间标签、评分、订阅提示、栏目列表、站点 slogan 当作正文细节写入摘要。
        4.1 任何一条 news.summary 如果中文正文不足 300 字，视为不合格，需要继续补足事实、细节和影响分析。
        4.2 禁止写“主轴集中在”“当前抓取结果围绕”“现有材料显示”“补充判断”等分析过程口吻，必须直接叙述事件事实本身。
        4.3 如果标题与正文片段明显不一致，优先相信标题和高相关片段，不要把疑似污染页面内容写入摘要。
        5. 如果今天的新情报与【你的历史记忆库】存在延续性、推进或重大反转，请务必在【事件核心】中以“前情回顾”的口吻明确指出并进行对比。
        6. 如果新闻中出现了明显的数据对比（如金额、份额、增速等），请务必准确提取到 chart_info 中，但不得为了图表而压缩正文篇幅。
        7. 提炼 overall_insight（200字以内），记录今天的核心结论。
        8. 优先保留 3 到 5 条真正重要的新闻；只有当今天确实不足 3 条时，才允许少于 3 条。
        9. 不要因为“映射不够完美”而过度删减，只要事件真实、近期、重要、且【{topic}】是主角，就应尽量保留。
        10. 如果存在 3 到 5 条彼此不同的重要事件，请不要把它们过度合并成 1 到 2 条大而空的新闻。
        11. 除专有名词外，尽量用中文表述，不要直接粘贴英文标题和页面噪音。
    """

    final_report = ai_driver.analyze_structural(reduce_prompt, NewsReport)
    return _finalize_news_output(final_report, event_blueprints, valid_event_ids, raw_search_results, topic)
