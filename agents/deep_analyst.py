import json
import concurrent.futures
import re
from pydantic import BaseModel, Field
from typing import List
from langchain_text_splitters import RecursiveCharacterTextSplitter

from tools.search_engine import assess_news_source_quality, event_validity_score, is_high_quality_news_result


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
        description="深度商业分析。必须严格分段并包含：【事件核心】、【深度细节/数据支撑】、【行业深远影响】，总中文篇幅不少于380字。",
    )
    url: str = Field(default="", description="该新闻的原文链接 URL（必须从原始数据中提取）")
    importance: int = Field(default=3, description="重要性 1-5")
    chart_info: ChartData = Field(default_factory=ChartData, description="自动化图表数据提取")
    confidence_level: str = Field(default="", description="频道三事件可信度 confirmed/likely")
    independent_source_count: int = Field(default=0, description="频道三独立来源数量")
    evidence_sources: List[str] = Field(default_factory=list, description="频道三主要证据来源")
    evidence_urls: List[str] = Field(default_factory=list, description="频道三证据来源链接")
    verified_event_summary: str = Field(default="", description="频道三已验证事件摘要")
    event_time_window: str = Field(default="", description="频道三事件时间窗口 today/24h/72h/7d")


class MapReport(BaseModel):
    news: List[NewsItem] = Field(default_factory=list, description="提取的新闻列表，如果没有符合条件的，返回空数组 []")


class NewsReport(BaseModel):
    overall_insight: str = Field(default="近期无重大异动", description="200字以内的全局核心摘要，概括本次所有情报的最核心结论")
    news: List[NewsItem] = Field(default_factory=list, description="新闻列表")


_ALNUM_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_SUMMARY_LOW_SIGNAL_RE = re.compile(
    r"(share|more ai .* news|related articles|recommended for you|subscribe|newsletter|follow us|"
    r"all rights reserved|privacy policy|terms of service|相关推荐|相关阅读|热门推荐|本网页已闲置|点击空白处)",
    re.IGNORECASE,
)
_SUMMARY_NOISY_FOLLOWUP_RE = re.compile(
    r"^(进一步看|更进一步|补充判断：围绕)[，,:：]?.*$",
    re.IGNORECASE,
)
_SUMMARY_TIME_RE = re.compile(r"^\d+\s*(m|min|mins|minute|minutes|h|hr|hrs|hour|hours|d|day|days)\s+ago$", re.IGNORECASE)
_SUMMARY_RATING_RE = re.compile(r"^\d+(\.\d+)?$")
_ASCII_TITLEISH_RE = re.compile(r"^[A-Za-z0-9 '&:/().,-]{18,}$")
_SOURCE_LABEL_RE = re.compile(
    r"(补充来源(?:还)?(?:显示|提到)|第三方报道补充称)[:：，,]?",
    re.IGNORECASE,
)
_GENERIC_SOURCE_SHOW_RE = re.compile(r"[^，。；;\n]{0,24}等来源显示[，,:：]?", re.IGNORECASE)
_DISCLAIMER_SUMMARY_RE = re.compile(
    r"(公开材料显示|该线索(?:于[^，。]{0,30})?由[^，。]{0,30}披露|该线索由某网站披露|"
    r"材料没有提供足够细节|材料没有提供足够可直接引用的中文细节|暂不能确认更多参数|"
    r"时间线仅记录已披露|仅记录已披露的动作|不补充未披露的数据|"
    r"免责声明|占位|暂无详情)",
    re.IGNORECASE,
)


def _is_patch_line(text):
    cleaned = str(text or "").strip()
    return bool(re.match(r"^(进一步看|更进一步|补充判断：围绕)[，,:：]?", cleaned, flags=re.IGNORECASE))


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
        cleaned = _SOURCE_LABEL_RE.sub("", cleaned).strip()
        cleaned = _GENERIC_SOURCE_SHOW_RE.sub("当前材料显示，", cleaned).strip()
        lower = cleaned.lower()
        if _SUMMARY_TIME_RE.match(lower):
            continue
        if _SUMMARY_RATING_RE.match(lower):
            continue
        if _SUMMARY_LOW_SIGNAL_RE.search(lower):
            continue
        if _DISCLAIMER_SUMMARY_RE.search(cleaned):
            continue
        if _SUMMARY_NOISY_FOLLOWUP_RE.search(cleaned):
            continue
        if _is_patch_line(cleaned):
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


def _news_item_quality_payload(news_item):
    return {
        "title": getattr(news_item, "title", "") or "",
        "url": getattr(news_item, "url", "") or "",
        "content": getattr(news_item, "summary", "") or "",
        "snippet": getattr(news_item, "summary", "") or "",
        "source": getattr(news_item, "source", "") or "",
        "author": getattr(news_item, "author", "") if hasattr(news_item, "author") else "",
        "published_date": getattr(news_item, "date_check", "") or "",
        "published": getattr(news_item, "date_check", "") or "",
    }


def _is_valid_final_news_item(news_item, raw_search_results=None):
    if not news_item:
        return False
    title = str(getattr(news_item, "title", "") or "").strip()
    source = str(getattr(news_item, "source", "") or "").strip()
    date_text = str(getattr(news_item, "date_check", "") or "").strip()
    url = str(getattr(news_item, "url", "") or "").strip()
    summary = str(getattr(news_item, "summary", "") or "").strip()
    if not (title and source and date_text and url and summary):
        return False
    if _DISCLAIMER_SUMMARY_RE.search(summary):
        return False
    if _count_cjk_chars(summary) < 80:
        return False

    quality_payload = _news_item_quality_payload(news_item)
    matched_source = None
    for result in raw_search_results or []:
        if url and url == str((result or {}).get("url") or "").strip():
            matched_source = dict(result or {})
            break
    if matched_source:
        quality_payload.update(
            {
                "title": matched_source.get("title") or title,
                "content": matched_source.get("content") or summary,
                "snippet": matched_source.get("snippet") or matched_source.get("content") or summary,
                "author": matched_source.get("author", ""),
                "published_date": matched_source.get("published_at_resolved") or matched_source.get("published_date") or date_text,
                "published": matched_source.get("published_at_resolved") or matched_source.get("published") or date_text,
            }
        )
    if not is_high_quality_news_result(quality_payload, min_content_chars=60):
        return False
    validity_count, _ = event_validity_score({"title": title, "content": summary})
    return validity_count >= 2


def _dedupe_news(news_items, event_blueprints, max_count=5):
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
    return ordered[:max_count]


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


def _clean_source_sentence_text(text):
    cleaned = str(text or "").replace("\r", "\n")
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    cleaned = re.sub(r"https?://\S+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip(" -:：;；,，")


def _pick_news_lead_sentences(text, min_sentences=3, max_sentences=5, max_chars=220):
    cleaned = _clean_source_sentence_text(text)
    if not cleaned or _DISCLAIMER_SUMMARY_RE.search(cleaned):
        return ""
    candidates = []
    for sentence in re.findall(r"[^。！？!?；;\n]+[。！？!?；;]?", cleaned):
        sentence = sentence.strip()
        if not sentence or _SUMMARY_LOW_SIGNAL_RE.search(sentence.lower()):
            continue
        if _DISCLAIMER_SUMMARY_RE.search(sentence):
            continue
        if _count_cjk_chars(sentence) < 8:
            continue
        if not re.search(r"[。！？!?；;]$", sentence):
            sentence += "。"
        candidates.append(sentence)
    selected = []
    for sentence in candidates:
        proposed = "".join(selected) + sentence
        if len(proposed) > max_chars and len(selected) >= min_sentences:
            break
        selected.append(sentence)
        if len(selected) >= max_sentences:
            break
    if len(selected) < min_sentences:
        return ""
    return "".join(selected).strip()


def _build_fallback_summary(topic, blueprint, supporting_results):
    primary = dict(supporting_results[0]) if supporting_results else {}
    title = primary.get("title") or blueprint.get("event", "") or "近期动态"
    snippet = primary.get("content") or primary.get("snippet") or ""
    keywords = "、".join((blueprint.get("keywords", []) or [])[:4])
    lead = _pick_news_lead_sentences(f"{title}。{snippet}", min_sentences=3, max_sentences=5, max_chars=260)
    if not lead:
        return ""

    detail = _trim_text(snippet, 620)
    if not detail or _DISCLAIMER_SUMMARY_RE.search(detail) or _count_cjk_chars(detail) < 40:
        return ""
    impact_terms = keywords or topic

    parts = [
        f"【事件核心】\n{lead}",
        f"【深度细节/数据支撑】\n{detail}",
        f"【行业深远影响】\n这条新闻的直接影响集中在{impact_terms}相关产品、业务节奏或供应链安排上。"
        "对研发和供应链团队而言，后续需要关注产品节点、客户验证、产能安排和同业竞争动作的变化。",
    ]
    return "\n".join([part for part in parts if part])


def _collect_supporting_results(blueprint, raw_search_results, limit=3):
    scored_results = []
    for result in raw_search_results or []:
        if not is_high_quality_news_result(result, min_content_chars=60):
            continue
        score = _supporting_result_score(blueprint, result)
        if score >= 0.24:
            scored_results.append((score, result))
    scored_results.sort(
        key=lambda item: (item[0], item[1].get("published_at_resolved") or item[1].get("published_date") or ""),
        reverse=True,
    )
    return [item[1] for item in scored_results[:limit]]


def _expand_short_summary(summary_text, topic, blueprint, supporting_results):
    return _sanitize_generated_summary(summary_text)


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
        if not supporting_results:
            continue

        primary = supporting_results[0] if supporting_results else {}
        fallback_summary = _build_fallback_summary(topic, blueprint, supporting_results)
        if not fallback_summary:
            continue
        fallback_news = NewsItem(
            event_id=event_id,
            title=event_title or primary.get("title", "未命名情报"),
            source=primary.get("source") or blueprint.get("source", "综合报道"),
            date_check=_format_result_date(primary, blueprint.get("date", "近期")),
            summary=fallback_summary,
            url=primary.get("url") or blueprint.get("source_url", ""),
            importance=4 if supporting_results else 3,
        )
        if not _is_valid_final_news_item(fallback_news, raw_search_results=supporting_results):
            continue
        existing_items.append(fallback_news)
        if event_id:
            covered_ids.add(event_id)
        if event_title:
            covered_titles.add(_normalize_text(event_title))

    return existing_items[:max_count]



def _finalize_news_output(
    final_report,
    event_blueprints,
    valid_event_ids,
    raw_search_results,
    topic,
    min_count=4,
    max_count=5,
):
    if not final_report:
        fallback_news = _supplement_news_from_blueprints(
            [],
            event_blueprints,
            raw_search_results,
            topic,
            min_count=min_count,
            max_count=max_count,
        )
        return fallback_news, ""

    final_report.news = [
        item for item in [_sanitize_news_item(item) for item in (final_report.news or [])]
        if _is_valid_final_news_item(item, raw_search_results=raw_search_results)
    ]
    final_news = _backfill_event_ids(final_report.news, event_blueprints)
    final_news = _normalize_invalid_event_ids(final_news, valid_event_ids)
    final_news = _dedupe_news(final_news, event_blueprints, max_count=max_count)
    final_news = _supplement_news_from_blueprints(
        final_news,
        event_blueprints,
        raw_search_results,
        topic,
        min_count=min_count,
        max_count=max_count,
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
    final_news = [
        item for item in final_news
        if _is_valid_final_news_item(item, raw_search_results=raw_search_results)
    ][:max_count]
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
    min_news_count=4,
    max_news_count=5,
):
    if not full_text or len(full_text) < 100:
        return _supplement_news_from_blueprints(
            [],
            event_blueprints,
            raw_search_results,
            topic,
            min_count=min_news_count,
            max_count=max_news_count,
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
    elif source_mode == "consumer_daily_digest":
        source_mode_note = (
            "当前输入是频道三消费电子日报的当日搜索卡片，已经按当天日期和专题相关性过滤。"
            "请只依据卡片中的标题、摘要、发布时间、来源和链接成稿；不要把网页推荐流、旧背景日期或泛行业历史数据当作当天新闻。"
            "目标读者是中国科技制造业、消费电子、FPC/PCB、光学显示、智能硬件相关从业者。"
            "中国国内新闻和中国公司动态优先，海外新闻作为重要补充；不要把海外新闻写成唯一主线。"
            "优先提取硬件参数、市场销量/份额、价格、供应链环节、量产/订单/渠道和公司动作。"
        )
    elif source_mode == "consumer_daily_verified_events":
        source_mode_note = (
            "当前输入是频道三《科技消费电子日报》的 VerifiedNewsPackage，已经过事件聚类、多源交叉验证、时间窗口校验和来源分级。"
            "你只能基于输入中的 confirmed_events 和 likely_events 成稿，禁止新增输入中不存在的新闻、公司动作、参数或数据。"
            "likely 事件必须在正文中标注“待核实”；weak、rumor、stale、rejected 只可作为剔除背景，不得写入正式新闻正文。"
            "watchlist_events 只能作为待跟踪线索背景，不得作为正式主新闻输出。"
            "每条新闻必须保留独立来源数量和主要来源，不能根据单一网页扩写成已确认事实。"
            "目标读者是中国科技制造业、消费电子、FPC/PCB、光学显示、智能硬件相关从业者。"
            "中国国内新闻和中国公司动态优先，海外重大新闻作为补充；内容必须落到产品、参数、硬件、市场、供应链、量产、价格、渠道或公司动作。"
        )
    elif source_mode == "consumer_daily_full_pipeline":
        source_mode_note = (
            "当前输入是频道三《科技消费电子日报》的全流程材料，包含已验证事件包、频道一式事件主档和 Jina/网页直连/搜索摘要兜底抓取材料。"
            "你只能围绕已验证事件主档中的 confirmed_events 和 likely_events 成稿；原文抓取材料只能用于补充事件细节、参数、市场信息和供应链背景。"
            "禁止新增输入中不存在的新闻、公司动作、参数、价格、销量、供应链或发布时间。"
            "如果搜索卡片与原文抓取材料冲突，以原文抓取内容和发布时间审查为准；信息不足时必须写“需进一步核实”。"
            "likely 事件必须在正文中标注“待核实”；weak、rumor、stale、rejected 不得写入正式新闻正文。"
            "每条新闻必须保留独立来源数量和主要来源，不能根据单一网页扩写成已确认事实。"
            "目标读者是中国科技制造业、消费电子、FPC/PCB、光学显示、智能硬件、智能汽车、机器人/具身智能相关从业者。"
        )
    else:
        source_mode_note = (
            "当前输入不是全文抓取，而是搜索摘要降级模式。禁止伪造原文引语、精细动作、独家细节或未出现的数据；"
            "信息不足时要明确写成‘现有摘要显示’。"
        )
    guidance_block = f"\n        【专题聚焦要求】：\n        {guidance}\n" if guidance else ""
    event_core_requirements = (
        "【事件核心】必须比普通摘要更完整：至少交代主体、产品/业务对象、关键动作、时间窗口、地区或目标市场、"
        "涉及供应链/客户/产线/政策/并购中的哪一类，以及它为什么值得研发部门关注。"
        "不要只写一句标题改写，也不要把背景和影响全部推到后两段。"
    )

    event_constraint_text = ""
    if has_event_blueprints and source_mode in {"consumer_daily_verified_events", "consumer_daily_full_pipeline"}:
        event_constraint_text = f"""
        【已验证事件主档】：
        {blueprint_json}

        你只能围绕这些 event_id 提取候选事件。
        1. 每条候选必须填写已有 event_id，不得留空。
        2. 不得新建虚构 event_id。
        3. 同一个 event_id 在一个切片中最多保留一条候选。
        4. 输入中没有的事件不得进入 news。
        """
    elif has_event_blueprints:
        event_constraint_text = f"""
        【统一事件主档】：
        {blueprint_json}

        你应当优先围绕这些 event_id 提取候选事件。
        1. 能明确映射时，优先填写已有 event_id。
        2. 如果某条候选明显属于【{topic}】在当前时间窗口内的重要事件，但一时无法可靠映射，可暂时留空 event_id，不要直接丢弃。
        3. 不得新建虚构 event_id。
        4. 同一个 event_id 在一个切片中最多保留一条候选；event_id 为空的候选也要避免重复。
        """

    minimum_summary_chars = 320 if source_mode in {"consumer_daily_digest", "consumer_daily_verified_events", "consumer_daily_full_pipeline"} else 380

    consumer_daily_rules = ""
    if source_mode in {"consumer_daily_digest", "consumer_daily_verified_events", "consumer_daily_full_pipeline"}:
        consumer_daily_rules = """
        【频道三专用红线】：
        1. 你是科技消费电子日报编辑，不是泛泛评论员。输出必须落到公司、产品、模型、参数、价格、渠道、销量、供应链、量产、订单或政策事件。
        2. 每条新闻必须可追溯到输入卡片中的来源 URL；没有明确来源的数据写“公开信息未披露”或“需进一步核实”。
        3. 同一专题内先保留中国国内动态，再保留海外重大补充；不要让单一海外大厂新闻挤掉国内主线。
        4. AR/VR/XR/AI眼镜专题必须聚焦智能眼镜、AI眼镜、AR/VR/XR、近眼显示、光波导、LCoS、Micro OLED/MicroLED、供应商或相关产品；普通手机和折叠 iPhone 不得混入。
        5. 折叠屏/显示专题必须偏显示技术、折叠铰链、面板、近眼显示和供应链，不要塞入普通手机泛新闻。
        6. 机器人/具身智能专题必须聚焦人形机器人、具身模型、工业/协作机器人、关节模组、减速器、伺服、灵巧手、传感器、控制器、量产、订单、工厂部署和融资；玩具机器人、扫地机器人促销、概念视频和单纯股价不得混入。
        7. 不要输出“进一步阅读”“相关推荐”“大家都在看”“热门文章”“补充判断：围绕……”等网页噪声或空泛补丁句。
        8. 对 verified events，正式正文只允许写 confirmed / likely；likely 必须写“待核实”，不得把 weak、rumor、stale、rejected 当新闻扩写。
        9. 正文中必须出现“独立来源”和“主要来源”的证据链信息，但不要输出内部 event_id。
        10. 每个专题原则上输出 3-5 条主新闻；如果输入 confirmed+likely 不足 3 条，不得编造补足，只说明“待跟踪线索”由系统在 PPT 中单独列示。
        """

    if source_mode in {"consumer_daily_verified_events", "consumer_daily_full_pipeline"}:
        detail_prompt = (
            "要求每条新闻总中文篇幅不少于 320 字，建议控制在 340 到 480 字。"
            "必须按【事件】【为什么重要】【已确认信息】【证据来源】【仍需核实】组织正文。"
            "【事件】至少 90 字，【已确认信息】至少 130 字，必须包含来源数量、主要来源、关键参数/价格/市场/供应链信息；"
            "【仍需核实】只写输入中明确存在但未完全确认的部分，没有则写“暂无”。"
        )
    elif source_mode == "consumer_daily_digest":
        detail_prompt = (
            "要求每条新闻总中文篇幅不少于 320 字，建议控制在 340 到 460 字。"
            "【事件核心】至少 120 字，【深度细节/数据支撑】至少 150 字，【行业深远影响】至少 70 字。"
            "必须优先写硬件参数、市场销量/份额、价格、供应链、量产、订单、渠道或公司动作；"
            "如果卡片没有这些信息，要明确写‘当前卡片未披露’，不得编造。"
        )
    elif source_mode == "search_summary_fallback":
        detail_prompt = (
            "要求每条新闻总中文篇幅不少于 380 字，建议控制在 410 到 540 字。"
            "【事件核心】至少 130 字，【深度细节/数据支撑】至少 180 字，【行业深远影响】至少 80 字。"
            "只能基于现有搜索摘要做事实概括和行业判断，不得伪造原文直接引语、微观动作或超细颗粒数据。"
        )
    elif source_mode == "mixed_fallback":
        detail_prompt = (
            "要求每条新闻总中文篇幅不少于 400 字，建议控制在 450 到 650 字。"
            "【事件核心】至少 140 字，【深度细节/数据支撑】至少 200 字，【行业深远影响】至少 90 字。"
            "可以结合全文和网页抽取做分析，但对直接引语、超细颗粒数字和过度确定的因果判断要保守表达。"
        )
    elif "24" in time_opt:
        detail_prompt = (
            "要求每条新闻总中文篇幅不少于 400 字，建议控制在 450 到 610 字。"
            "【事件核心】至少 140 字，【深度细节/数据支撑】至少 200 字，【行业深远影响】至少 90 字。"
            "优先保留能支撑判断的具体数字、核心动作、原话要点和业务影响；不要为了控制篇幅而把摘要压成过短版本。"
        )
    else:
        detail_prompt = (
            "要求每条新闻总中文篇幅不少于 400 字，建议控制在 450 到 590 字。"
            "【事件核心】至少 140 字，【深度细节/数据支撑】至少 200 字，【行业深远影响】至少 90 字。"
            "侧重于宏观趋势、战略意图和行业影响的完整分析。"
        )

    event_reduce_text = ""
    if has_event_blueprints and source_mode in {"consumer_daily_verified_events", "consumer_daily_full_pipeline"}:
        event_reduce_text = f"""
        【已验证事件主档】：
        {blueprint_json}

        输出规则：
        1. 最终 news 必须填写上方已验证事件主档中的 event_id。
        2. 每个 event_id 最多保留一条最终新闻，避免同一事件重复展开。
        3. 不得保留 event_id 为空或不在主档中的新闻。
        4. confirmed 可作为正式新闻；likely 必须标注“待核实”。
        5. 不得新增输入中没有的公司动作、参数、价格、销量、供应链或发布时间。
        """
    elif has_event_blueprints:
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
        {consumer_daily_rules}

        任务：
        1. 仅基于以上材料，提炼并深度扩写关于【{topic}】的 {min_news_count} 到 {max_news_count} 条真正重要的近期新闻。
        2. 终极剔除旧闻与无关陪衬事件，遇到同一事件必须合并。
        3. {detail_prompt}
        3.1 严禁把网页导航、分享按钮、相关推荐、时间标签、评分、订阅提示、栏目列表当作正文细节写入摘要。
        3.2 任何一条 news.summary 如果中文正文不足 {minimum_summary_chars} 字，视为不合格，需要继续补足细节和影响分析。
        3.3 不要在正文中写“补充来源显示”“补充来源还显示”“第三方报道补充称”等来源补丁式标签；需要补充的信息应直接并入事件核心或深度细节。
        3.4 {event_core_requirements}
        3.5 每条新闻必须包含标题、日期、来源、原文链接，并在【事件核心】开头用 3 到 5 句自然中文新闻导语写清楚主体、时间、动作、产品/功能/政策/业务变化和关键事实。
        3.6 禁止写“公开材料显示”“该线索由某网站披露”“材料没有提供足够细节”“暂不能确认更多参数”“时间线仅记录已披露动作”等免责声明式摘要；材料不足的候选应删除，不要凑数。
        4. 如果今天的新情报与历史记忆存在延续、推进或反转，请在【事件核心】中明确写出“前情回顾”。
        5. 如果新闻中出现明显的数据对比，请尽量准确提取到 chart_info 中，但不要为了图表牺牲 summary 的完整叙述。
        6. 优先填写统一事件主档中的 event_id；如无法可靠映射但事件确实重要，可将 event_id 留空。
        7. 优先保留 {min_news_count} 到 {max_news_count} 条彼此不同的重要事件，不要为了稳妥把多条新闻压成 1 到 2 条。
        8. 除专有名词外，尽量用中文表述，不要直接把英文标题、侧栏栏目名或站点 slogan 粘进【深度细节/数据支撑】。
        """
        direct_report = ai_driver.analyze_structural(direct_prompt, NewsReport)
        return _finalize_news_output(
            direct_report,
            event_blueprints,
            valid_event_ids,
            raw_search_results,
            topic,
            min_count=min_news_count,
            max_count=max_news_count,
        )

    def process_single_doc(doc):
        map_prompt = f"""
        【时间锚点】：今天是 **{current_date}**。要求范围：【{time_opt}】。
        任务：提取关于【{topic}】的新闻情报候选。
        红线：发现早于要求时间的旧闻直接丢弃！【{topic}】必须是绝对主角！无符合条件必须返回空的 news 数组。
        如果同一切片里存在 2 到 3 条彼此不同、且都足够重要的事件，请尽量都保留下来，不要过度合并。
        {source_mode_note}
        {guidance_block}
        {consumer_daily_rules}
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
            min_count=min_news_count,
            max_count=max_news_count,
        ), ""

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
        {consumer_daily_rules}

        任务：
        1. 终极剔除旧闻。2. 合并同事件新闻。
        3. 深度扩写排版：
        {detail_prompt}
        4. 严禁把网页导航、分享按钮、相关推荐、时间标签、评分、订阅提示、栏目列表、站点 slogan 当作正文细节写入摘要。
        4.1 任何一条 news.summary 如果中文正文不足 {minimum_summary_chars} 字，视为不合格，需要继续补足事实、细节和影响分析。
        4.2 不要在正文中写“补充来源显示”“补充来源还显示”“第三方报道补充称”等来源补丁式标签；需要补充的信息应直接并入事件核心或深度细节。
        4.3 {event_core_requirements}
        4.4 每条新闻必须包含标题、日期、来源、原文链接，并在【事件核心】开头用 3 到 5 句自然中文新闻导语写清楚主体、时间、动作、产品/功能/政策/业务变化和关键事实。
        4.5 禁止写“公开材料显示”“该线索由某网站披露”“材料没有提供足够细节”“暂不能确认更多参数”“时间线仅记录已披露动作”等免责声明式摘要；材料不足的候选应删除，不要凑数。
        5. 如果今天的新情报与【你的历史记忆库】存在延续性、推进或重大反转，请务必在【事件核心】中以“前情回顾”的口吻明确指出并进行对比。
        6. 如果新闻中出现了明显的数据对比（如金额、份额、增速等），请务必准确提取到 chart_info 中，但不得为了图表而压缩正文篇幅。
        7. 提炼 overall_insight（200字以内），记录今天的核心结论。
        8. 优先保留 {min_news_count} 到 {max_news_count} 条真正重要的新闻；只有当今天确实不足 {min_news_count} 条时，才允许少于 {min_news_count} 条。
        9. 不要因为“映射不够完美”而过度删减，只要事件真实、近期、重要、且【{topic}】是主角，就应尽量保留。
        10. 如果存在 {min_news_count} 到 {max_news_count} 条彼此不同的重要事件，请不要把它们过度合并成 1 到 2 条大而空的新闻。
        11. 除专有名词外，尽量用中文表述，不要直接粘贴英文标题和页面噪音。
    """

    final_report = ai_driver.analyze_structural(reduce_prompt, NewsReport)
    return _finalize_news_output(
        final_report,
        event_blueprints,
        valid_event_ids,
        raw_search_results,
        topic,
        min_count=min_news_count,
        max_count=max_news_count,
    )
