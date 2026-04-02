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
    summary: str = Field(default="暂无详情", description="深度商业分析。必须严格分段并包含：【事件核心】、【深度细节/数据支撑】、【行业深远影响】。")
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
                picked[item_id] = item
                continue

            current_score = (getattr(current, "importance", 0), len(getattr(current, "summary", "")))
            new_score = (getattr(item, "importance", 0), len(getattr(item, "summary", "")))
            if new_score > current_score:
                picked[item_id] = item
        else:
            fallback_items.append(item)

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
    if len(raw) <= limit:
        return raw
    return raw[:limit].rstrip(" ，,;；。") + "..."


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
    source = primary.get("source") or blueprint.get("source", "综合报道")
    keywords = "、".join((blueprint.get("keywords", []) or [])[:4])
    influence_hint = keywords or title

    parts = [f"【事件核心】\n{source} 等来源显示，{title}。"]
    if snippet:
        parts.append(f"【深度细节/数据支撑】\n{_trim_text(snippet, 180)}")
    elif blueprint.get("event"):
        parts.append(f"【深度细节/数据支撑】\n当前抓取结果围绕“{blueprint.get('event', '')}”展开，相关关键词包括：{keywords or '暂无更多细节'}。")
    if secondary_title or secondary_snippet:
        parts.append(f"补充来源还提到：{_trim_text(secondary_title or secondary_snippet, 120)}")
    parts.append(
        f"【行业深远影响】\n这条动态说明【{topic}】在“{influence_hint}”方向仍有新的产品、监管、商业化或生态进展，值得继续跟踪后续细节。"
    )
    return "\n".join([part for part in parts if part])


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

        scored_results = []
        for result in raw_search_results or []:
            score = _supporting_result_score(blueprint, result)
            if score >= 0.24:
                scored_results.append((score, result))
        scored_results.sort(
            key=lambda item: (item[0], item[1].get("published_at_resolved") or item[1].get("published_date") or ""),
            reverse=True,
        )
        supporting_results = [item[1] for item in scored_results[:2]]
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
):
    if not full_text or len(full_text) < 100:
        return _supplement_news_from_blueprints([], event_blueprints, raw_search_results, topic, min_count=4, max_count=5), ""

    blueprint_payload = _serialize_event_blueprints(event_blueprints)
    blueprint_json = json.dumps(blueprint_payload, ensure_ascii=False)
    has_event_blueprints = bool(blueprint_payload)
    valid_event_ids = [item.get("event_id", "") for item in blueprint_payload if item.get("event_id")]
    docs = RecursiveCharacterTextSplitter(chunk_size=6000, chunk_overlap=300).create_documents([full_text])
    all_extracted_news = []

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
            "要求每条新闻约 220 到 350 字。只能基于现有搜索摘要做事实概括和行业判断，"
            "不得伪造原文直接引语、微观动作或超细颗粒数据。"
        )
    elif source_mode == "mixed_fallback":
        detail_prompt = (
            "要求每条新闻约 320 到 520 字。可以结合全文和网页抽取做分析，"
            "但对直接引语、超细颗粒数字和过度确定的因果判断要保守表达。"
        )
    elif "24" in time_opt:
        detail_prompt = (
            "要求每条新闻约 260 到 380 字。优先保留能支撑判断的具体数字、核心动作、"
            "原话要点和业务影响；宁可略短一些，也不要为了篇幅牺牲条数。"
        )
    else:
        detail_prompt = "要求每条新闻约 280 到 320 字。侧重于宏观趋势、战略意图的分析。"

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
        4. 如果今天的新情报与历史记忆存在延续、推进或反转，请在【事件核心】中明确写出“前情回顾”。
        5. 如果新闻中出现明显的数据对比，请尽量准确提取到 chart_info 中。
        6. 优先填写统一事件主档中的 event_id；如无法可靠映射但事件确实重要，可将 event_id 留空。
        7. 优先保留 3 到 5 条彼此不同的重要事件，不要为了稳妥把 3 到 5 条压成 1 到 2 条。
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
        return ai_driver.analyze_structural(map_prompt, MapReport)

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
        4. 如果今天的新情报与【你的历史记忆库】存在延续性、推进或重大反转，请务必在【事件核心】中以“前情回顾”的口吻明确指出并进行对比。
        5. 如果新闻中出现了明显的数据对比（如金额、份额、增速等），请务必准确提取到 chart_info 中。
        6. 提炼 overall_insight（200字以内），记录今天的核心结论。
        7. 优先保留 3 到 5 条真正重要的新闻；只有当今天确实不足 3 条时，才允许少于 3 条。
        8. 不要因为“映射不够完美”而过度删减，只要事件真实、近期、重要、且【{topic}】是主角，就应尽量保留。
        9. 如果存在 3 到 5 条彼此不同的重要事件，请不要把它们过度合并成 1 到 2 条大而空的新闻。
    """

    final_report = ai_driver.analyze_structural(reduce_prompt, NewsReport)
    return _finalize_news_output(final_report, event_blueprints, valid_event_ids, raw_search_results, topic)
