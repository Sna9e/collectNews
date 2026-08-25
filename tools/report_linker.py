import difflib
import re
from copy import deepcopy
from urllib.parse import parse_qsl, urlencode, urlsplit


_ALNUM_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_SANITIZE_RE = re.compile(r"[^a-z0-9\u4e00-\u9fff]+", re.IGNORECASE)


def _get(item, key, default=None):
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def _to_dict(item):
    if item is None:
        return {}
    if isinstance(item, dict):
        return deepcopy(item)
    if hasattr(item, "model_dump"):
        return item.model_dump()
    return deepcopy(getattr(item, "__dict__", {}))


def _normalize_topic(topic):
    return _normalize_text(topic)


def _normalize_text(text):
    text = (text or "").lower().strip()
    return _SANITIZE_RE.sub("", text)


def _normalize_url(url):
    raw = str(url or "").strip()
    if not raw:
        return ""
    try:
        parsed = urlsplit(raw if "://" in raw else f"https://{raw}")
    except ValueError:
        return ""

    host = (parsed.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if not host:
        return ""

    path = re.sub(r"/{2,}", "/", parsed.path or "/").rstrip("/") or "/"
    query_items = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        key_lower = key.lower()
        if key_lower.startswith("utm_") or key_lower in {
            "fbclid", "gclid", "ref", "referrer", "source", "campaign",
        }:
            continue
        query_items.append((key, value))
    query = urlencode(sorted(query_items))
    return f"{host}{path}" + (f"?{query}" if query else "")


def _extract_cjk_bigrams(text):
    chars = [ch for ch in (text or "") if _CJK_RE.match(ch)]
    if len(chars) < 2:
        return set(chars)
    return {"".join(chars[idx:idx + 2]) for idx in range(len(chars) - 1)}


def _tokenize(text):
    words = {token.lower() for token in _ALNUM_RE.findall(text or "") if len(token) >= 2}
    return words | _extract_cjk_bigrams(text)


def _same_source(event_source, news_source):
    left = _normalize_text(event_source)
    right = _normalize_text(news_source)
    if not left or not right:
        return False
    return left == right or left in right or right in left


def _same_date(event_date, news_date):
    left = _normalize_text(event_date)
    right = _normalize_text(news_date)
    if not left or not right:
        return False
    return left == right or left in right or right in left


def _match_score(event_dict, news_dict):
    event_text = _get(event_dict, "event", "") or ""
    event_summary = (_get(event_dict, "event_summary", "") or "")[:220]
    news_title = _get(news_dict, "title", "") or ""
    news_summary = _get(news_dict, "summary", "") or ""
    news_summary_head = news_summary[:320]

    event_norm = _normalize_text(event_text)
    event_summary_norm = _normalize_text(event_summary)
    title_norm = _normalize_text(news_title)
    summary_norm = _normalize_text(news_summary_head)

    if not event_norm or not (title_norm or summary_norm):
        return 0.0, [], 0.0, 0.0

    title_ratio = difflib.SequenceMatcher(None, event_norm, title_norm).ratio() if title_norm else 0.0
    event_to_summary_ratio = difflib.SequenceMatcher(None, event_norm, summary_norm).ratio() if summary_norm else 0.0
    summary_to_summary_ratio = (
        difflib.SequenceMatcher(None, event_summary_norm, summary_norm).ratio()
        if event_summary_norm and summary_norm
        else 0.0
    )
    summary_ratio = max(event_to_summary_ratio, summary_to_summary_ratio)

    event_tokens = _tokenize(f"{event_text} {event_summary}")
    news_tokens = _tokenize(f"{news_title} {news_summary_head}")
    shared_tokens = sorted(event_tokens & news_tokens, key=len, reverse=True)
    overlap_ratio = len(shared_tokens) / max(len(event_tokens), 1)

    substring_bonus = 0.15 if event_norm in title_norm or event_norm in summary_norm else 0.0
    source_bonus = 0.08 if _same_source(_get(event_dict, "source", ""), _get(news_dict, "source", "")) else 0.0
    date_bonus = 0.05 if _same_date(_get(event_dict, "date", ""), _get(news_dict, "date_check", "")) else 0.0

    score = (
        max(title_ratio, summary_ratio * 0.92) * 0.52
        + overlap_ratio * 0.35
        + substring_bonus
        + source_bonus
        + date_bonus
    )
    return round(score, 4), shared_tokens[:3], round(title_ratio, 4), round(summary_ratio, 4)


def _build_reason(
    event_dict,
    news_dict,
    shared_tokens,
    title_ratio,
    summary_ratio,
    exact_event_id=False,
    exact_url=False,
):
    parts = []
    if exact_url:
        parts.append("短新闻和详细新闻指向同一规范化原文链接")
    if exact_event_id and _get(event_dict, "event_id", ""):
        parts.append(f"时间线和长新闻共享统一事件ID {_get(event_dict, 'event_id', '')}")
    if shared_tokens:
        parts.append(f"两者共享关键词“{'、'.join(shared_tokens)}”")
    if title_ratio >= 0.72:
        parts.append("标题与时间线表述高度一致")
    elif title_ratio >= 0.52:
        parts.append("标题和短新闻概括明显重合")
    elif summary_ratio >= 0.55:
        parts.append("长新闻摘要前段与短新闻概括高度相似")

    if _same_source(_get(event_dict, "source", ""), _get(news_dict, "source", "")):
        parts.append(f"来源同样指向 {_get(news_dict, 'source', '同一媒体')}")
    if _same_date(_get(event_dict, "date", ""), _get(news_dict, "date_check", "")):
        parts.append("时间也基本一致")

    if not parts:
        parts.append("事件描述与长新闻核心内容相似度较高")

    return (
        "；".join(parts)
        + "，因此可以判断这是同一条事件。核心时间线保留的是简要短新闻，后续详细新闻则补充了细节、背景和影响分析。"
    )


def _event_id_match_is_credible(event_dict, news_dict, score, title_ratio, summary_ratio):
    if score >= 0.42 or title_ratio >= 0.42 or summary_ratio >= 0.38:
        return True
    same_context = _same_source(
        _get(event_dict, "source", ""),
        _get(news_dict, "source", ""),
    ) or _same_date(
        _get(event_dict, "date", ""),
        _get(news_dict, "date_check", ""),
    )
    return same_context and score >= 0.20


def _fuzzy_match_is_credible(score, title_ratio, summary_ratio, threshold):
    if score < threshold:
        return False
    return title_ratio >= 0.42 or summary_ratio >= 0.34 or score >= max(0.62, threshold)


def _apply_match(
    event_dict,
    news_dict,
    score,
    shared_tokens,
    title_ratio,
    summary_ratio,
    method,
):
    exact_url = method == "source_url"
    exact_event_id = method == "event_id"
    reason = _build_reason(
        event_dict,
        news_dict,
        shared_tokens,
        title_ratio,
        summary_ratio,
        exact_event_id=exact_event_id,
        exact_url=exact_url,
    )
    try:
        importance = int(_get(news_dict, "importance", 3) or 3)
    except (TypeError, ValueError):
        importance = 3
    detail_index = int(_get(news_dict, "detail_index", 0) or 0)

    event_dict["appears_in_later_news"] = True
    event_dict["matched_news_title"] = _get(news_dict, "title", "")
    event_dict["matched_news_index"] = detail_index
    event_dict["matched_news_importance"] = importance
    event_dict["match_reason"] = reason
    event_dict["match_score"] = round(float(score), 4)
    event_dict["match_method"] = method
    event_dict["highlight_level"] = "key" if importance >= 4 else "linked"

    news_dict.setdefault("timeline_refs", []).append(
        {
            "event_id": _get(event_dict, "event_id", ""),
            "date": _get(event_dict, "date", ""),
            "event": _get(event_dict, "event", ""),
            "source": _get(event_dict, "source", ""),
            "reason": reason,
            "match_score": round(float(score), 4),
            "match_method": method,
            "detail_index": detail_index,
        }
    )


def annotate_report_data(deep_sections, timeline_sections, match_threshold=0.5):
    normalized_deep_sections = []
    for section in deep_sections or []:
        section_dict = _to_dict(section)
        section_dict["finance"] = deepcopy(section_dict.get("finance", {}))
        section_dict["warnings"] = list(section_dict.get("warnings", []))
        section_dict["source_mode"] = section_dict.get("source_mode", "full_text")
        section_dict["data"] = []
        source_news = section.get("data", []) if isinstance(section, dict) else _get(section, "data", [])
        for detail_index, news in enumerate(source_news, start=1):
            news_dict = _to_dict(news)
            news_dict["timeline_refs"] = []
            news_dict["detail_index"] = detail_index
            section_dict["data"].append(news_dict)
        normalized_deep_sections.append(section_dict)

    normalized_timeline_sections = []
    for section in timeline_sections or []:
        section_dict = _to_dict(section)
        section_dict["warnings"] = list(section_dict.get("warnings", []))
        section_dict["events"] = []
        source_events = section.get("events", []) if isinstance(section, dict) else _get(section, "events", [])
        for event in source_events:
            event_dict = _to_dict(event)
            event_dict["appears_in_later_news"] = False
            event_dict["matched_news_title"] = ""
            event_dict["matched_news_index"] = 0
            event_dict["matched_news_importance"] = 0
            event_dict["match_reason"] = ""
            event_dict["match_score"] = 0.0
            event_dict["match_method"] = ""
            event_dict["highlight_level"] = "normal"
            section_dict["events"].append(event_dict)
        normalized_timeline_sections.append(section_dict)

    deep_index = {
        _normalize_topic(section.get("topic", "")): section
        for section in normalized_deep_sections
    }

    for timeline_section in normalized_timeline_sections:
        topic_key = _normalize_topic(timeline_section.get("topic", ""))
        deep_section = deep_index.get(topic_key)
        if not deep_section:
            continue

        news_items = deep_section.get("data", [])
        if not news_items:
            continue

        timeline_events = timeline_section.get("events", [])
        matched_event_indexes = set()
        matched_news_indexes = set()

        news_indexes_by_url = {}
        for news_index, news_dict in enumerate(news_items):
            normalized_url = _normalize_url(news_dict.get("url", ""))
            if normalized_url:
                news_indexes_by_url.setdefault(normalized_url, []).append(news_index)

        # Original URLs are the strongest available evidence and override a stale model event_id.
        for event_index, event_dict in enumerate(timeline_events):
            normalized_url = _normalize_url(event_dict.get("source_url", ""))
            if not normalized_url:
                continue
            candidate_indexes = [
                index
                for index in news_indexes_by_url.get(normalized_url, [])
                if index not in matched_news_indexes
            ]
            if not candidate_indexes:
                continue
            news_index = candidate_indexes[0]
            news_dict = news_items[news_index]
            score, shared_tokens, title_ratio, summary_ratio = _match_score(event_dict, news_dict)
            _apply_match(
                event_dict,
                news_dict,
                max(score, 1.0),
                shared_tokens,
                title_ratio,
                summary_ratio,
                "source_url",
            )
            matched_event_indexes.add(event_index)
            matched_news_indexes.add(news_index)

        # A shared event_id is accepted only when title, summary, source or date also supports it.
        for event_index, event_dict in enumerate(timeline_events):
            if event_index in matched_event_indexes:
                continue
            event_id = event_dict.get("event_id", "")
            if not event_id:
                continue
            candidates = []
            for news_index, news_dict in enumerate(news_items):
                if news_index in matched_news_indexes or news_dict.get("event_id", "") != event_id:
                    continue
                score, shared_tokens, title_ratio, summary_ratio = _match_score(event_dict, news_dict)
                if _event_id_match_is_credible(event_dict, news_dict, score, title_ratio, summary_ratio):
                    candidates.append(
                        (score, title_ratio, summary_ratio, news_index, shared_tokens)
                    )
            if not candidates:
                continue
            score, title_ratio, summary_ratio, news_index, shared_tokens = max(candidates)
            news_dict = news_items[news_index]
            _apply_match(
                event_dict,
                news_dict,
                max(score, 0.90),
                shared_tokens,
                title_ratio,
                summary_ratio,
                "event_id",
            )
            matched_event_indexes.add(event_index)
            matched_news_indexes.add(news_index)

        # Remaining matches are assigned globally by score so one detail story cannot absorb
        # several unrelated timeline events.
        fuzzy_candidates = []
        for event_index, event_dict in enumerate(timeline_events):
            if event_index in matched_event_indexes:
                continue
            for news_index, news_dict in enumerate(news_items):
                if news_index in matched_news_indexes:
                    continue
                score, shared_tokens, title_ratio, summary_ratio = _match_score(event_dict, news_dict)
                if not _fuzzy_match_is_credible(score, title_ratio, summary_ratio, match_threshold):
                    continue
                fuzzy_candidates.append(
                    (
                        score,
                        title_ratio,
                        summary_ratio,
                        -event_index,
                        -news_index,
                        event_index,
                        news_index,
                        shared_tokens,
                    )
                )

        for candidate in sorted(fuzzy_candidates, reverse=True):
            score, title_ratio, summary_ratio, _, _, event_index, news_index, shared_tokens = candidate
            if event_index in matched_event_indexes or news_index in matched_news_indexes:
                continue
            _apply_match(
                timeline_events[event_index],
                news_items[news_index],
                score,
                shared_tokens,
                title_ratio,
                summary_ratio,
                "semantic",
            )
            matched_event_indexes.add(event_index)
            matched_news_indexes.add(news_index)

        for news_dict in news_items:
            news_dict["timeline_refs"].sort(
                key=lambda item: item.get("match_score", 0.0),
                reverse=True,
            )

    return normalized_deep_sections, normalized_timeline_sections
