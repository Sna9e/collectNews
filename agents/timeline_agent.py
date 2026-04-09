from pydantic import BaseModel, Field
from typing import List
import difflib
import json
import re
from urllib.parse import urlparse


FRONTIER_EVENT_TERMS = [
    "ai", "模型", "芯片", "chip", "gpu", "tpu", "服务器", "data center", "云", "cloud",
    "发布", "上线", "升级", "产品", "供应链", "自动驾驶", "waymo", "robotaxi",
    "iphone", "ios", "mac", "pixel", "android", "gemini", "siri", "vision pro",
    "quest", "llama", "starlink", "starship", "机器人", "robotics"
]
BUSINESS_EVENT_TERMS = ["财报", "earnings", "guidance", "合作", "partnership", "订单", "融资", "contract", "客户"]
LEGAL_EVENT_TERMS = ["律师", "法庭", "法院", "判决", "隐私", "诉讼", "lawyer", "court", "judge", "lawsuit", "appeal", "fine", "privacy"]
POLICY_EVENT_TERMS = ["监管", "政策", "regulation", "regulator", "ban", "probe", "investigation", "executive order"]
SOCIAL_EVENT_TERMS = ["未成年人", "社交", "adult", "teen", "children", "social media"]
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


class EventDraft(BaseModel):
    date: str = Field(description="新闻爆出的真实近期日期（格式：MM月DD日）。")
    source: str = Field(description="信息来源网站名")
    event: str = Field(description="15字以内的一句话极简干货概括")
    source_url: str = Field(default="", description="对应原始新闻 URL")
    keywords: List[str] = Field(default_factory=list, description="3到6个核心关键词")


class EventBlueprint(EventDraft):
    event_id: str = Field(default="", description="统一事件ID，格式为 E01、E02")


class EventBlueprintReport(BaseModel):
    events: List[EventDraft] = Field(default_factory=list, description="按时间先后排序的规范化事件列表")


class TimelineTitleDraft(BaseModel):
    event: str = Field(description="中文短讯标题，8到22字，突出动作和主体")


class TimelineTitleReport(BaseModel):
    events: List[TimelineTitleDraft] = Field(default_factory=list, description="按原顺序改写后的中文短讯标题")


class TimelineEvent(BaseModel):
    event_id: str = Field(default="", description="对应统一事件ID")
    date: str = Field(description="新闻爆出的真实近期日期（格式：MM月DD日）。")
    source: str = Field(description="信息来源网站名")
    event: str = Field(description="15字以内的一句话极简干货概括")
    source_url: str = Field(default="", description="对应原始新闻 URL")
    history_status: str = Field(default="", description="历史事件状态，new 或 followup")
    first_seen: str = Field(default="", description="该事件首次进入事件图谱的日期")
    last_seen: str = Field(default="", description="该事件最近一次进入事件图谱的日期")
    seen_count: int = Field(default=0, description="事件累计被跟踪的次数")


def _normalize_signature(date_text, source_text, event_text):
    raw = f"{date_text}|{source_text}|{event_text}".lower().strip()
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", raw)


def _normalize_text(text):
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", (text or "").lower().strip())


def _tokenize(text):
    words = set(re.findall(r"[a-z0-9]{2,}", (text or "").lower()))
    chars = [ch for ch in (text or "") if re.match(r"[\u4e00-\u9fff]", ch)]
    if len(chars) < 2:
        return words | set(chars)
    return words | {"".join(chars[idx:idx + 2]) for idx in range(len(chars) - 1)}


def _count_hits(text, tokens):
    total = 0
    lower = str(text or "").lower()
    for token in tokens or []:
        token_text = str(token or "").lower().strip()
        if token_text and token_text in lower:
            total += 1
    return total


def _classify_event_category(event_dict):
    blob = f"{event_dict.get('event', '')} {' '.join(event_dict.get('keywords', []) or [])}".lower()
    frontier_hits = _count_hits(blob, FRONTIER_EVENT_TERMS)
    business_hits = _count_hits(blob, BUSINESS_EVENT_TERMS)
    legal_hits = _count_hits(blob, LEGAL_EVENT_TERMS)
    policy_hits = _count_hits(blob, POLICY_EVENT_TERMS)
    social_hits = _count_hits(blob, SOCIAL_EVENT_TERMS)

    if frontier_hits >= max(1, legal_hits + 1, policy_hits + 1, social_hits + 1):
        return "frontier"
    if legal_hits >= 1:
        return "legal"
    if policy_hits >= 1:
        return "policy"
    if social_hits >= 1:
        return "social"
    if business_hits >= 1:
        return "business"
    return "generic"


def _event_match_score(left, right):
    left_url = (left.get("source_url", "") or "").strip().lower()
    right_url = (right.get("source_url", "") or "").strip().lower()
    if left_url and right_url and left_url == right_url:
        return 1.0

    left_text = left.get("event", "") or ""
    right_text = right.get("event", "") or ""
    left_norm = _normalize_text(left_text)
    right_norm = _normalize_text(right_text)
    if not left_norm or not right_norm:
        return 0.0

    ratio = difflib.SequenceMatcher(None, left_norm, right_norm).ratio()
    left_tokens = _tokenize(f"{left_text} {' '.join(left.get('keywords', []) or [])}")
    right_tokens = _tokenize(f"{right_text} {' '.join(right.get('keywords', []) or [])}")
    overlap = len(left_tokens & right_tokens) / max(min(len(left_tokens), len(right_tokens)) or 1, 1)
    same_date = bool(left.get("date", "") and left.get("date", "") == right.get("date", ""))
    same_source = bool(left.get("source", "") and left.get("source", "") == right.get("source", ""))
    substring_bonus = 0.14 if left_norm in right_norm or right_norm in left_norm else 0.0
    return round(
        ratio * 0.52 + overlap * 0.28 + substring_bonus + (0.08 if same_date else 0.0) + (0.06 if same_source else 0.0),
        4,
    )


def _merge_event_dict(existing, candidate):
    merged = dict(existing)
    merged_keywords = []
    seen = set()
    for keyword in list(existing.get("keywords", []) or []) + list(candidate.get("keywords", []) or []):
        token = str(keyword or "").strip()
        if not token:
            continue
        key = token.lower()
        if key in seen:
            continue
        seen.add(key)
        merged_keywords.append(token)
    merged["keywords"] = merged_keywords

    if candidate.get("source_url") and not merged.get("source_url"):
        merged["source_url"] = candidate["source_url"]
    if candidate.get("source") and (not merged.get("source") or merged.get("source") == "未知来源"):
        merged["source"] = candidate["source"]
    if candidate.get("date") and (not merged.get("date") or merged.get("date") == "近期"):
        merged["date"] = candidate["date"]

    existing_event = str(existing.get("event", "") or "")
    candidate_event = str(candidate.get("event", "") or "")
    if candidate_event and (not existing_event or len(candidate_event) < len(existing_event)):
        merged["event"] = candidate_event

    return merged


_URL_IN_TEXT_RE = re.compile(r"https?://\S+", re.IGNORECASE)
_PARENS_WITH_URL_RE = re.compile(r"\([^)]*https?://[^)]*\)", re.IGNORECASE)
_SPACE_RE = re.compile(r"\s+")

EVENT_TRANSLATION_HINTS = {
    "tesla": "特斯拉",
    "trump": "特朗普",
    "openai": "OpenAI",
    "google": "谷歌",
    "alphabet": "谷歌",
    "apple": "苹果",
    "meta": "Meta",
    "amazon": "亚马逊",
    "nvidia": "英伟达",
    "anthropic": "Anthropic",
    "spacex": "SpaceX",
    "fsd": "FSD",
    "robotaxi": "Robotaxi",
    "optimus": "Optimus",
    "tariff": "关税",
    "trade": "贸易",
    "policy": "政策",
    "chip": "芯片",
    "robot": "机器人",
    "robotics": "机器人",
    "ipo": "IPO",
    "delivery": "交付",
    "deliveries": "交付",
    "autopilot": "自动驾驶",
    "megapack": "Megapack",
}


def _strip_event_noise(text):
    cleaned = str(text or "").strip()
    cleaned = _PARENS_WITH_URL_RE.sub("", cleaned)
    cleaned = _URL_IN_TEXT_RE.sub("", cleaned)
    cleaned = cleaned.replace("（", "(").replace("）", ")")
    cleaned = re.sub(r"\([^)]{0,18}\)$", "", cleaned).strip()
    cleaned = _SPACE_RE.sub(" ", cleaned)
    return cleaned.strip(" -:：;；,，")


def _replace_known_aliases(text):
    normalized = str(text or "")
    for key, value in EVENT_TRANSLATION_HINTS.items():
        normalized = re.sub(rf"(?i)\b{re.escape(key)}\b", value, normalized)
    return normalized


def _looks_generic_event(text, topic=""):
    cleaned = str(text or "").strip()
    if not cleaned:
        return True
    cleaned = cleaned.rstrip("（）()")
    generic_tokens = ["近期动态", "动态更新", "最新消息", "近期进展", "相关动态"]
    if any(token == cleaned or cleaned.endswith(token) for token in generic_tokens):
        return True
    topic_hint = _topic_translation_hint(topic)
    if topic_hint and cleaned in {topic_hint, f"{topic_hint}动态", f"{topic_hint}近期动态"}:
        return True
    return False


def _topic_translation_hint(topic):
    lower = str(topic or "").lower()
    hints = []
    for key, value in EVENT_TRANSLATION_HINTS.items():
        if key in lower:
            hints.append(value)
    return "、".join(dict.fromkeys(hints))


def _looks_broken_event(text, topic=""):
    cleaned = _strip_event_noise(text)
    if not cleaned:
        return True
    if cleaned.endswith("(") or cleaned.endswith("（") or "()" in cleaned or "（)" in cleaned:
        return True
    if "..." in cleaned or "…" in cleaned:
        return True
    if _looks_generic_event(cleaned, topic):
        return True
    if len(cleaned) < 6:
        return True
    return False


def _format_result_date(result, fallback="近期"):
    raw = str(
        result.get("published_at_resolved")
        or result.get("published_date")
        or result.get("published")
        or ""
    ).strip()
    match = re.search(r"(\d{4})[-/](\d{2})[-/](\d{2})", raw)
    if match:
        return f"{match.group(2)}月{match.group(3)}日"
    match = re.search(r"(\d{2})月(\d{2})日", raw)
    if match:
        return f"{match.group(1)}月{match.group(2)}日"
    return str(fallback or "近期")


def _format_result_source(result, fallback="未知来源"):
    source = str(result.get("source") or "").strip()
    if source:
        return source
    url = str(result.get("url") or "").strip()
    if not url:
        return str(fallback or "未知来源")
    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        host = ""
    host = host.replace("www.", "")
    if not host:
        return str(fallback or "未知来源")
    return host.split(":")[0]


def _clean_title_for_timeline(title, topic="", keywords=None):
    cleaned = _strip_event_noise(title)
    cleaned = re.sub(r"\s*[-|｜]\s*(Reuters|Bloomberg|MacRumors|Yahoo Finance|TipRanks|TechCrunch|The Verge|Android Police|CNBC)$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+\([^)]{0,30}\)$", "", cleaned).strip()
    cleaned = _replace_known_aliases(cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -:：;；,，")
    if not cleaned:
        return _heuristic_localize_event(title, topic=topic, keywords=keywords)
    if _CJK_RE.search(cleaned):
        return cleaned[:26]
    return cleaned[:42]


def _rewrite_titles_with_ai(ai_driver, events, topic):
    if not events or not ai_driver or not getattr(ai_driver, "valid", False):
        return events

    payload = []
    for item in events[:12]:
        payload.append(
            {
                "date": item.get("date", "近期"),
                "source": item.get("source", "未知来源"),
                "event": item.get("event", ""),
                "keywords": item.get("keywords", []),
            }
        )

    prompt = f"""
    你是中文科技新闻编辑。下面是关于【{topic}】的核心时间线标题草稿：
    {json.dumps(payload, ensure_ascii=False)}

    请按相同顺序返回 JSON：{{"events":[{{"event":"..."}}]}}

    严格要求：
    1. 只改写 event，不要补充日期、来源、网址，不要调整顺序。
    2. 每条必须是中文短讯标题，8到22字，最多24字。
    3. 不要出现“近期动态”“最新消息”“相关进展”这种空泛标题。
    4. 不要保留括号链接、URL、英文原文残片。
    5. 若原始标题已是清晰中文，只做轻度压缩即可。
    6. 专有词可保留，如 iPhone、FSD、Robotaxi、Optimus、Gemini、IPO。
    """

    report = ai_driver.analyze_structural(prompt, TimelineTitleReport)
    if not report or not report.events:
        return events

    rewritten = []
    for original, rewritten_item in zip(events, report.events):
        current = dict(original)
        candidate = _strip_event_noise(getattr(rewritten_item, "event", "") or "")
        if _looks_broken_event(candidate, topic):
            candidate = current.get("event", "") or ""
        current["event"] = candidate[:26].strip() if candidate else current.get("event", "")
        rewritten.append(current)

    if len(rewritten) < len(events):
        rewritten.extend(events[len(rewritten):])
    return rewritten


def _find_best_result_for_event(event_dict, raw_search_results):
    best_result = None
    best_score = 0.0
    probe = {
        "event": event_dict.get("event", ""),
        "keywords": event_dict.get("keywords", []) or [],
        "source_url": event_dict.get("source_url", ""),
        "source": event_dict.get("source", ""),
        "date": event_dict.get("date", ""),
    }
    for result in raw_search_results or []:
        candidate = {
            "event": result.get("title", "") or "",
            "keywords": [],
            "source_url": result.get("url", "") or "",
            "source": result.get("source", "") or "",
            "date": _format_result_date(result, ""),
        }
        score = _event_match_score(probe, candidate)
        if score > best_score:
            best_result = result
            best_score = score
    return best_result, best_score


def _heuristic_localize_event(event_text, topic="", keywords=None):
    cleaned = _strip_event_noise(event_text)
    if not cleaned:
        topic_hint = _topic_translation_hint(topic)
        if topic_hint:
            return f"{topic_hint}最新进展"
        return "核心进展更新"
    if _CJK_RE.search(cleaned):
        return cleaned[:28]

    translated = _replace_known_aliases(cleaned)
    translated = re.sub(r"\s+", " ", translated).strip()
    if translated and not _looks_generic_event(translated, topic):
        return translated[:42]

    keyword_hits = []
    for token in list(keywords or []):
        token_text = str(token or "").strip()
        if not token_text:
            continue
        mapped = EVENT_TRANSLATION_HINTS.get(token_text.lower(), token_text)
        keyword_hits.append(mapped)

    topic_hint = _topic_translation_hint(topic)
    keyword_hint = "、".join(dict.fromkeys(keyword_hits[:3]))
    if topic_hint and keyword_hint:
        return f"{topic_hint}{keyword_hint}动态"
    if topic_hint:
        fallback = _replace_known_aliases(cleaned)
        return fallback[:42] if fallback else f"{topic_hint}近期动态"
    if keyword_hint:
        return f"{keyword_hint}动态"
    return cleaned[:28]


def _rewrite_event_dicts(ai_driver, events, topic, raw_search_results=None):
    if not events:
        return events

    rewritten = []
    for event_dict in events:
        current = dict(event_dict)
        current["event"] = _strip_event_noise(current.get("event", ""))
        matched_result, match_score = _find_best_result_for_event(current, raw_search_results or [])
        if matched_result and match_score >= 0.28:
            result_title = _clean_title_for_timeline(
                matched_result.get("title", "") or current.get("event", ""),
                topic=topic,
                keywords=current.get("keywords", []),
            )
            current["date"] = _format_result_date(matched_result, current.get("date", "近期"))
            current["source"] = _format_result_source(matched_result, current.get("source", "未知来源"))
            current["source_url"] = matched_result.get("url") or current.get("source_url", "")
            if _looks_broken_event(current.get("event", ""), topic):
                current["event"] = result_title
            elif result_title and len(result_title) <= len(current.get("event", "") or result_title) + 8:
                current["event"] = result_title
        elif _looks_broken_event(current.get("event", ""), topic):
            current["event"] = _heuristic_localize_event(
                current.get("event", ""),
                topic=topic,
                keywords=current.get("keywords", []),
            )

        current["event"] = _strip_event_noise(current.get("event", ""))
        if not current["event"]:
            current["event"] = _heuristic_localize_event("", topic=topic, keywords=current.get("keywords", []))
        current["date"] = str(current.get("date", "") or "近期")
        current["source"] = str(current.get("source", "") or "未知来源")
        rewritten.append(current)

    return _rewrite_titles_with_ai(ai_driver, rewritten, topic)


def _dedupe_finalized_events(events, max_items=12):
    finalized = []
    for event_dict in events:
        duplicate_index = None
        for idx, existing in enumerate(finalized):
            score = _event_match_score(event_dict, existing)
            same_event = _normalize_text(event_dict.get("event", "")) == _normalize_text(existing.get("event", ""))
            if same_event or score >= 0.82:
                duplicate_index = idx
                break
        if duplicate_index is not None:
            finalized[duplicate_index] = _merge_event_dict(finalized[duplicate_index], event_dict)
            continue
        finalized.append(event_dict)
        if len(finalized) >= max_items:
            break
    return finalized


def _limit_overrepresented_categories(events, target_min=5, hard_limit=12):
    if not events:
        return []

    caps = {
        "frontier": hard_limit,
        "business": max(3, hard_limit // 4),
        "generic": max(4, hard_limit // 3),
        "legal": 1,
        "policy": 1,
        "social": 1,
    }
    selected = []
    deferred = []
    counts = {}

    for event_dict in events:
        category = _classify_event_category(event_dict)
        event_dict["_category"] = category
        if counts.get(category, 0) >= caps.get(category, hard_limit):
            deferred.append(event_dict)
            continue
        selected.append(event_dict)
        counts[category] = counts.get(category, 0) + 1
        if len(selected) >= hard_limit:
            return selected[:hard_limit]

    for event_dict in deferred:
        if len(selected) >= max(target_min, min(hard_limit, len(events))):
            break
        selected.append(event_dict)

    return selected[:hard_limit]


def _finalize_event_blueprints(events, ai_driver=None, topic="", raw_search_results=None):
    deduped_events = []
    for event in events or []:
        event_dict = event.model_dump() if hasattr(event, "model_dump") else dict(event)
        event_dict["event"] = _strip_event_noise(event_dict.get("event", ""))
        signature = _normalize_signature(
            event_dict.get("date", ""),
            event_dict.get("source", ""),
            event_dict.get("event", ""),
        )
        if not signature:
            continue

        duplicate_index = None
        for idx, existing in enumerate(deduped_events):
            existing_signature = _normalize_signature(
                existing.get("date", ""),
                existing.get("source", ""),
                existing.get("event", ""),
            )
            score = _event_match_score(event_dict, existing)
            if signature == existing_signature or score >= 0.76:
                duplicate_index = idx
                break

        if duplicate_index is not None:
            deduped_events[duplicate_index] = _merge_event_dict(deduped_events[duplicate_index], event_dict)
            continue

        deduped_events.append(event_dict)

    diversified_events = _limit_overrepresented_categories(deduped_events, target_min=5, hard_limit=12)
    diversified_events = _rewrite_event_dicts(ai_driver, diversified_events, topic, raw_search_results=raw_search_results)
    diversified_events = _dedupe_finalized_events(diversified_events, max_items=12)

    finalized = []
    for event_dict in diversified_events[:12]:
        event_dict.pop("_category", None)
        event_dict["event_id"] = f"E{len(finalized) + 1:02d}"
        finalized.append(EventBlueprint(**event_dict))
    return finalized


def _fallback_event_blueprints(raw_search_results, ai_driver=None, topic=""):
    events = []
    for result in raw_search_results[:10]:
        title = _clean_title_for_timeline(result.get("title") or "未命名事件", topic=topic)
        events.append(
            EventDraft(
                date=_format_result_date(result, "近期"),
                source=_format_result_source(result, "未知来源"),
                event=title,
                source_url=result.get("url", "") or "",
                keywords=[],
            )
        )
    return _finalize_event_blueprints(events, ai_driver=ai_driver, topic=topic, raw_search_results=raw_search_results)


def build_event_blueprints(ai_driver, raw_search_results, topic, current_date, time_opt, history_hint="", guidance=""):
    if not raw_search_results:
        return []

    snippets = []
    for r in raw_search_results:
        snippet_text = str(r.get("content", "") or "")[:220]
        snippets.append(
            f"发布时间:{r.get('published_at_resolved') or r.get('published_date') or ''} | "
            f"标题:{r.get('title')} | 摘要:{snippet_text} | 来源URL:{r.get('url')}"
        )

    combined_text = "\n".join(snippets)

    history_block = f"\n    【历史事件图谱参考】\n    {history_hint}\n" if history_hint else ""
    guidance_block = f"\n    【专题聚焦要求】\n    {guidance}\n" if guidance else ""

    prompt = f"""
    【全局时间锚点】：今天是 {current_date}。要求的时间范围是：【{time_opt}】。
    以下是全网搜集的关于【{topic}】的最新简讯碎片：
    {combined_text}
    {history_block}
    {guidance_block}

    任务与规则：
    1. 先做事件规范化，优先保留 5 到 8 条真正最值得后续展开的核心事件主档；如果当天事件确实密集，可放宽到 10 条，最多不超过 12 条，按事件爆出时间从过去到现在排序。
    2. 【{topic}】必须是绝对主角；混入竞品、泛科技晨报、无关公司的，一律删除。
    3. 遇到多篇报道说的是同一件事，必须合并成一条规范化事件，不要重复。
    4. date 填新闻爆出的真实近期时间，不要把未来预测日期当成事件日期。
    5. event 保持一句话短讯风格，15字以内；keywords 提炼 3 到 6 个关键词；source_url 必须尽量填写对应原始 URL。
    6. 只保留要求时间窗口内的近期事件。
    7. 如果当前事件明显是历史事件图谱中某个老事件的推进，请尽量保持表述连续，便于后续复用历史 event_id。
    8. 优先覆盖产品、AI、芯片、数据中心、供应链、自动驾驶等不同方向；法律、隐私、诉讼、律师、法庭类如果不是当天主线，最多保留 1 条。
    """
    report = ai_driver.analyze_structural(prompt, EventBlueprintReport)
    if not report or not report.events:
        return _fallback_event_blueprints(raw_search_results, ai_driver=ai_driver, topic=topic)
    return _finalize_event_blueprints(report.events, ai_driver=ai_driver, topic=topic, raw_search_results=raw_search_results)


def generate_timeline(event_blueprints):
    timeline = []
    for event in event_blueprints or []:
        event_dict = event.model_dump() if hasattr(event, "model_dump") else dict(event)
        timeline.append(TimelineEvent(**event_dict))
    return timeline
