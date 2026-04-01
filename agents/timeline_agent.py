from pydantic import BaseModel, Field
from typing import List
import difflib
import re


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


class TimelineEvent(BaseModel):
    event_id: str = Field(default="", description="对应统一事件ID")
    date: str = Field(description="新闻爆出的真实近期日期（格式：MM月DD日）。")
    source: str = Field(description="信息来源网站名")
    event: str = Field(description="15字以内的一句话极简干货概括")
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
        ratio * 0.52
        + overlap * 0.28
        + substring_bonus
        + (0.08 if same_date else 0.0)
        + (0.06 if same_source else 0.0),
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


def _finalize_event_blueprints(events):
    deduped_events = []
    for event in events or []:
        event_dict = event.model_dump() if hasattr(event, "model_dump") else dict(event)
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
            if signature == existing_signature or score >= 0.78:
                duplicate_index = idx
                break

        if duplicate_index is not None:
            deduped_events[duplicate_index] = _merge_event_dict(deduped_events[duplicate_index], event_dict)
            continue

        deduped_events.append(event_dict)

    finalized = []
    for event_dict in deduped_events[:20]:
        event_dict["event_id"] = f"E{len(finalized) + 1:02d}"
        finalized.append(EventBlueprint(**event_dict))
    return finalized


def _fallback_event_blueprints(raw_search_results):
    events = []
    for result in raw_search_results[:15]:
        title = (result.get("title") or "未命名事件").strip()
        if len(title) > 30:
            title = title[:30]
        events.append(
            EventDraft(
                date="近期",
                source=result.get("url", "") or "未知来源",
                event=title,
                source_url=result.get("url", ""),
                keywords=[],
            )
        )
    return _finalize_event_blueprints(events)


def build_event_blueprints(ai_driver, raw_search_results, topic, current_date, time_opt, history_hint="", guidance=""):
    if not raw_search_results:
        return []

    snippets = []
    for r in raw_search_results:
        snippets.append(
            f"发布时间:{r.get('published_at_resolved') or r.get('published_date') or ''} | "
            f"标题:{r.get('title')} | 摘要:{r.get('content')} | 来源URL:{r.get('url')}"
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
    1. 先做事件规范化，尽量保留 6 到 12 条真正的核心事件主档；如果当天事件密集，最多允许输出 20 条，按事件爆出时间从过去到现在排序。
    2. 【{topic}】必须是绝对主角；混入竞品、泛科技晨报、无关公司的一律删除。
    3. 遇到多篇报道说的是同一件事，必须合并成一条规范化事件，不要重复。
    4. date 填新闻爆出的真实近期时间，不要把未来预测日期当成事件日期。
    5. event 保持一句话短讯风格，15字以内；keywords 提炼 3 到 6 个关键词；source_url 必须尽量填写对应原始 URL。
    6. 只保留要求时间窗口内的近期事件。
    7. 如果当前事件明显是历史事件图谱中某个老事件的推进，请尽量保持表述连续，便于后续复用历史 event_id。
    """
    report = ai_driver.analyze_structural(prompt, EventBlueprintReport)
    if not report or not report.events:
        return _fallback_event_blueprints(raw_search_results)
    return _finalize_event_blueprints(report.events)


def generate_timeline(event_blueprints):
    timeline = []
    for event in event_blueprints or []:
        event_dict = event.model_dump() if hasattr(event, "model_dump") else dict(event)
        timeline.append(TimelineEvent(**event_dict))
    return timeline
