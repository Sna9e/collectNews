import difflib
import re
from copy import deepcopy


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
    news_title = _get(news_dict, "title", "") or ""
    news_summary = _get(news_dict, "summary", "") or ""
    news_summary_head = news_summary[:240]

    event_norm = _normalize_text(event_text)
    title_norm = _normalize_text(news_title)
    summary_norm = _normalize_text(news_summary_head)

    if not event_norm or not (title_norm or summary_norm):
        return 0.0, [], 0.0, 0.0

    title_ratio = difflib.SequenceMatcher(None, event_norm, title_norm).ratio() if title_norm else 0.0
    summary_ratio = difflib.SequenceMatcher(None, event_norm, summary_norm).ratio() if summary_norm else 0.0

    event_tokens = _tokenize(event_text)
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


def _build_reason(event_dict, news_dict, shared_tokens, title_ratio, summary_ratio, exact_event_id=False):
    parts = []
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
        + "，因此可以判断这是同一条事件。核心时间线保留的是一句话短讯，后续长新闻则是在抓取原文或摘要后补充了细节、背景和影响分析。"
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
        for news in source_news:
            news_dict = _to_dict(news)
            news_dict["timeline_refs"] = []
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
            event_dict["match_reason"] = ""
            event_dict["match_score"] = 0.0
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

        news_by_event_id = {
            item.get("event_id", ""): item
            for item in news_items
            if item.get("event_id")
        }

        for event_dict in timeline_section.get("events", []):
            exact_match = None
            exact_event_id = event_dict.get("event_id", "")
            if exact_event_id:
                exact_match = news_by_event_id.get(exact_event_id)

            if exact_match:
                score, shared_tokens, title_ratio, summary_ratio = _match_score(event_dict, exact_match)
                score = max(score, 0.99)
                reason = _build_reason(
                    event_dict,
                    exact_match,
                    shared_tokens,
                    title_ratio,
                    summary_ratio,
                    exact_event_id=True,
                )
                event_dict["appears_in_later_news"] = True
                event_dict["matched_news_title"] = exact_match.get("title", "")
                event_dict["match_reason"] = reason
                event_dict["match_score"] = score
                exact_match["timeline_refs"].append(
                    {
                        "event_id": exact_event_id,
                        "date": event_dict.get("date", ""),
                        "event": event_dict.get("event", ""),
                        "source": event_dict.get("source", ""),
                        "reason": reason,
                        "match_score": score,
                    }
                )
                continue

            best_match = None
            best_score = 0.0
            best_tokens = []
            best_title_ratio = 0.0
            best_summary_ratio = 0.0

            for news_dict in news_items:
                score, shared_tokens, title_ratio, summary_ratio = _match_score(event_dict, news_dict)
                if score > best_score:
                    best_match = news_dict
                    best_score = score
                    best_tokens = shared_tokens
                    best_title_ratio = title_ratio
                    best_summary_ratio = summary_ratio

            if not best_match or best_score < match_threshold:
                continue

            reason = _build_reason(
                event_dict,
                best_match,
                best_tokens,
                best_title_ratio,
                best_summary_ratio,
                exact_event_id=False,
            )
            event_dict["appears_in_later_news"] = True
            event_dict["matched_news_title"] = best_match.get("title", "")
            event_dict["match_reason"] = reason
            event_dict["match_score"] = best_score
            best_match["timeline_refs"].append(
                {
                    "event_id": event_dict.get("event_id", ""),
                    "date": event_dict.get("date", ""),
                    "event": event_dict.get("event", ""),
                    "source": event_dict.get("source", ""),
                    "reason": reason,
                    "match_score": best_score,
                }
            )

        for news_dict in news_items:
            news_dict["timeline_refs"].sort(
                key=lambda item: item.get("match_score", 0.0),
                reverse=True,
            )

    return normalized_deep_sections, normalized_timeline_sections
