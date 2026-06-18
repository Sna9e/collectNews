from pydantic import BaseModel, Field
from typing import List
import difflib
import html
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
_EVENT_SUMMARY_FALLBACK = ""
_EVENT_SUMMARY_TARGET_MIN = 100
_EVENT_SUMMARY_TARGET_MAX = 220
_EVENT_SUMMARY_TARGET_SENTENCES = 5
_EVENT_SUMMARY_NOISE_RE = re.compile(
    r"(网页导航|相关推荐|相关阅读|热门推荐|进一步阅读|分享|订阅|newsletter|privacy policy|"
    r"terms of service|read more|related articles|recommended for you|subscribe)",
    re.IGNORECASE,
)
_EVENT_SUMMARY_PATCH_RE = re.compile(
    r"^(进一步看|更进一步|补充判断(?:：围绕)?|值得持续关注|后续仍需关注|"
    r"该事件具有重要意义|相关进展值得跟踪)[，,:：]?.*$",
    re.IGNORECASE,
)
_EVENT_SUMMARY_DISCLAIMER_RE = re.compile(
    r"(公开材料显示|该线索(?:于[^，。]{0,30})?由[^，。]{0,30}披露|该线索由某网站披露|"
    r"材料没有提供足够细节|材料没有提供足够可直接引用的中文细节|暂不能确认更多参数|"
    r"时间线仅记录已披露|仅记录已披露的动作|不补充未披露的数据|"
    r"公开材料暂未披露更多细节|建议后续继续跟踪)",
    re.IGNORECASE,
)
_EVENT_SUMMARY_SENTENCE_RE = re.compile(r"[^。！？!?；;\n]+[。！？!?；;]?")


class EventDraft(BaseModel):
    date: str = Field(description="新闻爆出的真实近期日期（格式：MM月DD日）。")
    source: str = Field(description="信息来源网站名")
    event: str = Field(description="15字以内的一句话极简干货概括")
    event_summary: str = Field(default="", description="100到220字中文短新闻摘要，通常3到5句，说明主体、动作、对象、关键细节和直接影响，不得编造。")
    source_url: str = Field(default="", description="对应原始新闻 URL")
    keywords: List[str] = Field(default_factory=list, description="3到6个核心关键词")


class EventBlueprint(EventDraft):
    event_id: str = Field(default="", description="统一事件ID，格式为 E01、E02")


class EventBlueprintReport(BaseModel):
    events: List[EventDraft] = Field(default_factory=list, description="按时间先后排序的规范化事件列表")


class TimelineTitleDraft(BaseModel):
    event: str = Field(description="中文短讯标题，8到22字，突出动作和主体")


class TimelineTitleReport(BaseModel):
    events: List[TimelineTitleDraft] = Field(default_factory=list, description="与输入顺序一致的中文短讯标题")


class TimelineEvent(BaseModel):
    event_id: str = Field(default="", description="对应统一事件ID")
    date: str = Field(description="新闻爆出的真实近期日期（格式：MM月DD日）。")
    source: str = Field(description="信息来源网站名")
    event: str = Field(description="15字以内的一句话极简干货概括")
    event_summary: str = Field(default="", description="100到220字中文短新闻摘要，通常3到5句，说明主体、动作、对象、关键细节和直接影响，不得编造。")
    source_url: str = Field(default="", description="对应原始新闻 URL")
    history_status: str = Field(default="", description="历史事件状态，new 或 followup")
    first_seen: str = Field(default="", description="该事件首次进入事件图谱的日期")
    last_seen: str = Field(default="", description="该事件最近一次进入事件图谱的日期")
    seen_count: int = Field(default=0, description="事件累计被追踪的次数")


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


def _clean_event_summary_text(text):
    cleaned = html.unescape(str(text or "")).replace("\r", "\n")
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    cleaned = re.sub(r"\[\s*(?:\.\.\.|…)+\s*\]", " ", cleaned)
    cleaned = _PARENS_WITH_URL_RE.sub("", cleaned)
    cleaned = _URL_IN_TEXT_RE.sub("", cleaned)
    cleaned = cleaned.replace("\u00a0", " ")

    kept_lines = []
    for raw_line in cleaned.splitlines():
        line = _SPACE_RE.sub(" ", raw_line).strip(" -:：;；,，")
        if not line:
            continue
        if _EVENT_SUMMARY_PATCH_RE.match(line):
            continue
        line = _EVENT_SUMMARY_NOISE_RE.sub(" ", line)
        line = _SPACE_RE.sub(" ", line).strip(" -:：;；,，")
        if not line:
            continue
        kept_lines.append(line)

    cleaned = " ".join(kept_lines) if kept_lines else _SPACE_RE.sub(" ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -:：;；,，")
    if (
        not cleaned
        or _EVENT_SUMMARY_PATCH_RE.match(cleaned)
        or _EVENT_SUMMARY_NOISE_RE.search(cleaned)
        or _EVENT_SUMMARY_DISCLAIMER_RE.search(cleaned)
    ):
        return ""
    return cleaned


def _ensure_sentence_punctuation(sentence):
    sentence = str(sentence or "").strip()
    if not sentence:
        return ""
    if re.search(r"[。！？!?；;]$", sentence):
        return sentence
    if _CJK_RE.search(sentence):
        return f"{sentence}。"
    return sentence


def _clip_summary_to_max(text, max_chars):
    if len(text) <= max_chars:
        return text
    clipped = text[:max_chars].rstrip(" ，,;；。.!?！？")
    sentence_break = max(clipped.rfind("。"), clipped.rfind("！"), clipped.rfind("？"))
    if sentence_break >= 20:
        return clipped[:sentence_break + 1]
    return clipped


def _trim_event_summary(text, min_chars=_EVENT_SUMMARY_TARGET_MIN, max_chars=_EVENT_SUMMARY_TARGET_MAX):
    cleaned = _clean_event_summary_text(text)
    if not cleaned:
        return ""

    sentences = [
        _ensure_sentence_punctuation(sentence.strip())
        for sentence in _EVENT_SUMMARY_SENTENCE_RE.findall(cleaned)
        if sentence.strip() and not _EVENT_SUMMARY_PATCH_RE.match(sentence.strip())
    ]
    sentences = [sentence for sentence in sentences if sentence]
    selected_parts = []
    for sentence in sentences[:_EVENT_SUMMARY_TARGET_SENTENCES]:
        proposed = "".join(selected_parts) + sentence
        if len(proposed) > max_chars:
            if selected_parts:
                break
            return _clip_summary_to_max(proposed, max_chars)
        selected_parts.append(sentence)

    selected = "".join(selected_parts).strip() if selected_parts else _ensure_sentence_punctuation(cleaned)
    if not selected:
        return ""
    if len(selected) > max_chars:
        return _clip_summary_to_max(selected, max_chars)
    return selected


def _has_substantial_chinese(text):
    cleaned = str(text or "")
    cjk_count = len(_CJK_RE.findall(cleaned))
    return cjk_count >= 10 and cjk_count / max(len(cleaned), 1) >= 0.35


def _normalize_event_summary_text(text, min_chars=_EVENT_SUMMARY_TARGET_MIN, max_chars=_EVENT_SUMMARY_TARGET_MAX):
    cleaned = _trim_event_summary(text, min_chars=min_chars, max_chars=max_chars)
    if not cleaned:
        return ""
    if _is_fallback_event_summary(cleaned):
        return ""
    if _EVENT_SUMMARY_DISCLAIMER_RE.search(cleaned):
        return ""
    if not _has_substantial_chinese(cleaned):
        return ""
    if len(cleaned) < 20:
        return ""
    return cleaned


def _extract_material_terms(text, event_dict=None, max_items=4):
    terms = []
    seen = set()

    def add(token):
        token = str(token or "").strip(" -:：;；,，.。")
        if not token or len(token) > 28:
            return
        key = token.lower()
        if key in {"read", "more", "privacy", "policy", "terms", "service", "news", "article"}:
            return
        mapped = EVENT_TRANSLATION_HINTS.get(key, token)
        mapped_key = mapped.lower()
        if mapped_key in seen:
            return
        seen.add(mapped_key)
        terms.append(mapped)

    for keyword in (event_dict or {}).get("keywords", []) or []:
        add(keyword)
    for token in re.findall(r"\b[A-Z][A-Za-z0-9+\-]{1,24}\b|\b[A-Za-z]+[0-9][A-Za-z0-9+\-]*\b", str(text or "")):
        add(token)
        if len(terms) >= max_items:
            break
    return terms[:max_items]


def _infer_material_action(text):
    lower = str(text or "").lower()
    action_hints = [
        (("launch", "launched", "unveil", "release", "released", "introduce", "introduced", "announce", "announced"), "发布"),
        (("update", "upgrade", "refresh"), "更新"),
        (("expand", "expanded", "roll out", "rolled out"), "推进"),
        (("partner", "partnership", "collaborate", "deal"), "达成合作"),
        (("invest", "funding", "finance"), "投资"),
        (("ship", "delivery", "deliveries"), "交付"),
        (("cut", "reduce", "lower"), "下调"),
        (("raise", "increase", "grow", "growth"), "上调"),
        (("probe", "investigation", "lawsuit", "court"), "面临审查"),
    ]
    for keys, action in action_hints:
        if any(key in lower for key in keys):
            return action
    return "披露"


def _build_event_summary_from_result(result, event_dict, min_chars=_EVENT_SUMMARY_TARGET_MIN, max_chars=_EVENT_SUMMARY_TARGET_MAX):
    source_candidates = [
        (result or {}).get("content", ""),
        (result or {}).get("snippet", ""),
    ]
    for candidate in source_candidates:
        summary = _normalize_event_summary_text(candidate, min_chars=min_chars, max_chars=max_chars)
        if summary:
            return summary
    return ""


def _is_fallback_event_summary(text):
    return _normalize_text(text) == _normalize_text(_EVENT_SUMMARY_FALLBACK)


def _event_summary_quality(text):
    cleaned = _normalize_event_summary_text(text)
    if not cleaned or _is_fallback_event_summary(cleaned):
        return 0
    cjk_count = len(_CJK_RE.findall(cleaned))
    length = len(cleaned)
    sentence_count = len(re.findall(r"[。！？]", cleaned))
    if _EVENT_SUMMARY_TARGET_MIN <= length <= _EVENT_SUMMARY_TARGET_MAX:
        length_score = 260 - abs(180 - length)
    elif 100 <= length < _EVENT_SUMMARY_TARGET_MIN:
        length_score = 170 - (_EVENT_SUMMARY_TARGET_MIN - length)
    elif 60 <= length < 100:
        length_score = 100 - (100 - length)
    else:
        length_score = 40
    sentence_score = min(sentence_count, _EVENT_SUMMARY_TARGET_SENTENCES) * 24
    return length_score + sentence_score + min(cjk_count, 160)


def _select_better_event_summary(existing, candidate):
    existing_clean = _normalize_event_summary_text(existing)
    candidate_clean = _normalize_event_summary_text(candidate)
    if _event_summary_quality(candidate_clean) > _event_summary_quality(existing_clean):
        return candidate_clean
    if existing_clean:
        return existing_clean
    if candidate_clean:
        return candidate_clean
    return ""


def _ensure_event_summary(event_dict, matched_result=None):
    existing = (event_dict or {}).get("event_summary", "")
    fallback = _build_event_summary_from_result(matched_result or {}, event_dict or {})
    selected = _select_better_event_summary(existing, fallback)
    return selected or ""


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

    merged["event_summary"] = (
        _select_better_event_summary(existing.get("event_summary", ""), candidate.get("event_summary", ""))
        or ""
    )

    return merged


_URL_IN_TEXT_RE = re.compile(r"https?://\S+", re.IGNORECASE)
_PARENS_WITH_URL_RE = re.compile(r"\([^)]*https?://[^)]*\)", re.IGNORECASE)
_SPACE_RE = re.compile(r"\s+")
_ASCII_HEAVY_RE = re.compile(r"[A-Za-z]")

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
    return str(fallback or "近期").strip() or "近期"


def _format_result_source(result, fallback="未知来源"):
    source = str(result.get("source", "") or "").strip()
    if source:
        return source
    url = str(result.get("url", "") or "").strip()
    if not url:
        return str(fallback or "未知来源")
    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        return str(fallback or "未知来源")
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
    2. event 必须是中文核心时间线短讯，优先 10 到 20 个字，最长不超过 24 个字。
    3. 必须体现明确动作，如“发布”“推出”“遇阻”“降价”“泄露”“启动”“增长”，不要写“近期动态”“最新进展”这种空话。
    4. 可以保留必要专有名词，如 iPhone、MacBook、Android、Gemini、FSD、IPO。
    5. 不要保留英文整句、网址、括号链接、来源后缀。
    """

    report = ai_driver.analyze_structural(prompt, TimelineTitleReport)
    if not report or not report.events:
        return events

    rewritten = []
    for source_dict, title_item in zip(events, report.events):
        current = dict(source_dict)
        candidate = str(getattr(title_item, "event", "") or "").strip()
        if candidate and not _looks_generic_event(candidate, topic) and not _looks_broken_event(candidate, topic):
            current["event"] = candidate[:24]
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
    if translated and not _looks_generic_event(translated, topic) and not _looks_broken_event(translated, topic):
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
        return f"{topic_hint}{keyword_hint}进展"
    if topic_hint:
        fallback = _replace_known_aliases(cleaned)
        return fallback[:42] if fallback and not _looks_broken_event(fallback, topic) else f"{topic_hint}最新进展"
    if keyword_hint:
        return f"{keyword_hint}进展"
    return cleaned[:28]


def _rewrite_event_dicts(ai_driver, events, topic, raw_search_results=None):
    if not events:
        return events

    rewritten = []
    for event_dict in events:
        current = dict(event_dict)
        current["event"] = _strip_event_noise(current.get("event", ""))

        matched_result, match_score = _find_best_result_for_event(current, raw_search_results or [])
        if matched_result and match_score >= 0.24:
            current["date"] = _format_result_date(matched_result, current.get("date", "近期"))
            current["source"] = _format_result_source(matched_result, current.get("source", "未知来源"))
            current["source_url"] = matched_result.get("url", "") or current.get("source_url", "")
            current["event"] = _clean_title_for_timeline(
                matched_result.get("title", "") or current.get("event", ""),
                topic=topic,
                keywords=current.get("keywords", []),
            )
            current["event_summary"] = _ensure_event_summary(current, matched_result)
        else:
            current["event_summary"] = _ensure_event_summary(current, None)

        if _looks_broken_event(current.get("event", ""), topic):
            current["event"] = _heuristic_localize_event(
                current.get("event", ""),
                topic=topic,
                keywords=current.get("keywords", []),
            )

        current["date"] = str(current.get("date", "") or "近期")
        current["source"] = str(current.get("source", "") or "未知来源")
        current["event_summary"] = _ensure_event_summary(current, matched_result if matched_result and match_score >= 0.24 else None)
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
        event_dict["event_summary"] = _ensure_event_summary(event_dict, None)
        if not event_dict["event_summary"]:
            continue
        finalized.append(EventBlueprint(**event_dict))
    return finalized


def _fallback_event_blueprints(raw_search_results, ai_driver=None, topic=""):
    events = []
    for result in raw_search_results[:10]:
        title = _clean_title_for_timeline(result.get("title") or "未命名事件", topic=topic)
        draft_event = {
            "event": title,
            "source": _format_result_source(result, "未知来源"),
            "source_url": result.get("url", ""),
        }
        events.append(
            EventDraft(
                date=_format_result_date(result, "近期"),
                source=draft_event["source"],
                event=title,
                event_summary=_build_event_summary_from_result(result, draft_event),
                source_url=result.get("url", ""),
                keywords=[],
            )
        )
    return _finalize_event_blueprints(events, ai_driver=ai_driver, topic=topic, raw_search_results=raw_search_results)


def build_event_blueprints(ai_driver, raw_search_results, topic, current_date, time_opt, history_hint="", guidance=""):
    if not raw_search_results:
        return []

    snippets = []
    for r in raw_search_results:
        snippet_text = str(r.get("content", "") or "")[:420]
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
    2. 【{topic}】必须是绝对主角；混入竞品、泛科技晨报、无关公司的一律删除。
    3. 遇到多篇报道说的是同一件事，必须合并成一条规范化事件，不要重复。
    4. date 填新闻爆出的真实近期时间，不要把未来预测日期当成事件日期。
    5. event 保持一句话短讯风格，15字以内；keywords 提炼 3 到 6 个关键词；source_url 必须尽量填写对应原始 URL。
    6. 默认只保留要求时间窗口内的近期事件；如果【专题聚焦要求】明确说明是“宽松日报模式”，可保留搜索结果中缺少标准时间戳但明显为今日/近期的重要新闻，不要因为时间字段缺失把主题清空。
    7. 如果当前事件明显是历史事件图谱中某个老事件的推进，请尽量保持表述连续，便于后续复用历史 event_id。
    8. 优先覆盖产品、AI、芯片、数据中心、供应链、自动驾驶等不同方向；法律、隐私、诉讼、律师、法庭类如果不是当天主线，最多保留 1 条。
    9. 每条事件必须填写 event_summary：必须使用自然中文新闻导语风格，通常为 3 到 5 个完整句子，建议 100 到 220 个中文字符；内容应基于标题、导语和摘要正文，直接写清楚谁、在什么时间、发布或宣布了什么、涉及哪些产品或功能、有哪些关键变化；只能根据上方输入搜索摘要生成，不得编造，不得直接复制英文摘要，不得重复标题，不得解释检索过程，不得使用“公开材料显示”“该线索由某网站披露”“材料没有提供足够细节”“暂不能确认更多参数”“时间线仅记录已披露动作”“进一步看”“补充判断”等免责声明或空泛补句。
    """
    report = ai_driver.analyze_structural(prompt, EventBlueprintReport)
    if not report or not report.events:
        return _fallback_event_blueprints(raw_search_results, ai_driver=ai_driver, topic=topic)
    return _finalize_event_blueprints(report.events, ai_driver=ai_driver, topic=topic, raw_search_results=raw_search_results)


def generate_timeline(event_blueprints):
    timeline = []
    for event in event_blueprints or []:
        event_dict = event.model_dump() if hasattr(event, "model_dump") else dict(event)
        event_dict["event_summary"] = _ensure_event_summary(event_dict, None)
        if not event_dict["event_summary"]:
            continue
        timeline.append(TimelineEvent(**event_dict))
    return timeline
