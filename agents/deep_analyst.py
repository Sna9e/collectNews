import json
import concurrent.futures
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


def _serialize_event_blueprints(event_blueprints):
    payload = []
    for event in event_blueprints or []:
        if hasattr(event, "model_dump"):
            payload.append(event.model_dump())
        elif isinstance(event, dict):
            payload.append(dict(event))
    return payload


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

        if best_id and best_score >= 0.42:
            item.event_id = best_id

    return news_items


def map_reduce_analysis(
    ai_driver,
    topic,
    full_text,
    current_date,
    time_opt,
    past_memories_string="",
    event_blueprints=None,
    source_mode="full_text",
):
    if not full_text or len(full_text) < 100:
        return [], ""

    blueprint_payload = _serialize_event_blueprints(event_blueprints)
    blueprint_json = json.dumps(blueprint_payload, ensure_ascii=False)
    has_event_blueprints = bool(blueprint_payload)
    valid_event_ids = [item.get("event_id", "") for item in blueprint_payload if item.get("event_id")]
    docs = RecursiveCharacterTextSplitter(chunk_size=8000, chunk_overlap=1000).create_documents([full_text])
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

    event_constraint_text = ""
    if has_event_blueprints:
        event_constraint_text = f"""
        【统一事件主档】：
        {blueprint_json}

        你只能提取与这些 event_id 对应的事件。
        1. 每条 news 都必须填写 event_id，且必须直接引用上面已有的 event_id。
        2. 不得新建 event_id，不得输出主档之外的新事件。
        3. 同一个 event_id 在一个切片中最多保留一条候选。
        """

    def process_single_doc(doc):
        map_prompt = f"""
        【时间锚点】：今天是 **{current_date}**。要求范围：【{time_opt}】。
        任务：提取关于【{topic}】的新闻情报候选。
        红线：发现早于要求时间的旧闻直接丢弃！【{topic}】必须是绝对主角！无符合条件必须返回空的 news 数组。
        {source_mode_note}
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
        return [], ""

    combined_json = json.dumps([item.model_dump() for item in all_extracted_news], ensure_ascii=False)

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
            "要求每条新闻约 600 字。必须尽量提取具体数字（融资金额、股价等）、核心原话、"
            "微小动作细节。事件概述不少于200字，不得少于整体篇幅的1/3。"
        )
    else:
        detail_prompt = "要求每条新闻约 300 字。侧重于宏观趋势、战略意图的分析。"

    event_reduce_text = ""
    if has_event_blueprints:
        event_reduce_text = f"""
        【统一事件主档】：
        {blueprint_json}

        输出规则：
        1. 最终 news 中每条都必须填写 event_id，并且必须来自统一事件主档。
        2. 每个 event_id 最多保留一条最终长新闻，避免同一事件重复展开。
        3. 如果候选新闻无法映射到统一事件主档，必须删除。
        4. 最终新闻顺序要和统一事件主档顺序一致。
        """

    reduce_prompt = f"""
        【全局时间锚点】：今天是 **{current_date}**。你是顶级科技媒体总编。

        【🧠 你的历史记忆库】：
        {past_memories_string}

        【📰 今天的新情报碎片】：
        {combined_json}

        {event_reduce_text}
        {source_mode_note}

        任务：
        1. 终极剔除旧闻。2. 合并同事件新闻。
        3. 深度扩写排版：
        {detail_prompt}
        4. 如果今天的新情报与【你的历史记忆库】存在延续性、推进或重大反转，请务必在【事件核心】中以“前情回顾”的口吻明确指出并进行对比。
        5. 如果新闻中出现了明显的数据对比（如金额、份额、增速等），请务必准确提取到 chart_info 中。
        6. 提炼 overall_insight（200字以内），记录今天的核心结论。
        7. 最多保留最核心的5条。
    """

    final_report = ai_driver.analyze_structural(reduce_prompt, NewsReport)
    if not final_report:
        return [], ""

    final_news = _backfill_event_ids(final_report.news, event_blueprints)
    final_news = _dedupe_news(final_news, event_blueprints)
    if valid_event_ids:
        final_news = [item for item in final_news if getattr(item, "event_id", "") in valid_event_ids]

    return final_news, final_report.overall_insight
