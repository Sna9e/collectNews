# -*- coding: utf-8 -*-
import json
import concurrent.futures
from typing import List

from pydantic import BaseModel, Field
from langchain_text_splitters import RecursiveCharacterTextSplitter


class ChartData(BaseModel):
    has_chart: bool = Field(
        default=False,
        description="如果新闻中包含明确可对比数据，则设为 True。",
    )
    chart_title: str = Field(default="", description="图表标题")
    labels: List[str] = Field(default_factory=list, description="横轴标签")
    values: List[float] = Field(default_factory=list, description="数值列表")
    chart_type: str = Field(default="bar", description="bar/pie/line")


class NewsItem(BaseModel):
    title: str = Field(default="未命名情报", description="新闻标题（中文）")
    source: str = Field(default="未知来源", description="来源媒体")
    date_check: str = Field(default="近期", description="真实日期 YYYY-MM-DD")
    summary: str = Field(
        default="暂无详情",
        description="深度商业分析，需包含【事件核心】【细节与数据】【行业影响】",
    )
    url: str = Field(default="", description="原文链接 URL")
    importance: int = Field(default=3, description="重要性 1-5")
    chart_info: ChartData = Field(default_factory=ChartData, description="图表数据")


class MapReport(BaseModel):
    news: List[NewsItem] = Field(
        default_factory=list,
        description="切片阶段新闻列表，无则返回空数组",
    )


class NewsReport(BaseModel):
    overall_insight: str = Field(
        default="近期无重大异动",
        description="100字以内的全局摘要",
    )
    news: List[NewsItem] = Field(default_factory=list, description="新闻列表")


def map_reduce_analysis(ai_driver, topic, full_text, current_date, time_opt, past_memories_string=""):
    if not full_text or len(full_text) < 100:
        return [], ""
    if ai_driver is None or (hasattr(ai_driver, "valid") and not ai_driver.valid):
        return [], ""

    docs = RecursiveCharacterTextSplitter(chunk_size=8000, chunk_overlap=1000).create_documents(
        [full_text]
    )
    all_extracted_news: List[NewsItem] = []

    def process_single_doc(doc):
        map_prompt = f"""
【时间锚点】今天是 {current_date}，要求范围：{time_opt}。
任务：提取与“{topic}”直接相关的新闻情报。
红线：早于时间范围的旧闻一律剔除；“{topic}”必须是绝对主角。
如无符合条件内容，返回空的 news 数组。
正文：{doc.page_content}
"""
        return ai_driver.analyze_structural(map_prompt, MapReport)

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(process_single_doc, d) for d in docs]
        for future in concurrent.futures.as_completed(futures):
            try:
                res = future.result()
                if res and res.news:
                    all_extracted_news.extend(res.news)
            except Exception as e:
                print(f"[map] slice failed: {e}")

    if not all_extracted_news:
        return [], ""

    combined_json = json.dumps([item.model_dump() for item in all_extracted_news], ensure_ascii=False)

    if "24" in time_opt:
        detail_prompt = (
            "每条新闻约 600 字，必须包含具体数字（融资金额、股价等）、"
            "关键原话与细节动作。"
        )
    else:
        detail_prompt = "每条新闻约 300 字，侧重趋势与战略意图。"

    reduce_prompt = f"""
【全局时间锚点】今天是 {current_date}。你是顶级科技媒体总编。

【历史记忆库】
{past_memories_string}

【今日新闻碎片】
{combined_json}

任务：
1. 彻底剔除旧闻。
2. 合并同一事件的重复报道。
3. 深度扩写并排版（{detail_prompt}）。
4. 输出 overall_insight（100字以内）。
5. 最多保留最核心的 8 条。

如果今日新闻与历史记忆存在延续、推进或反转，
请在【事件核心】中以“前情回顾”方式明确对比。

如出现明确数据对比（金额、份额、增速等），请准确写入 chart_info。
"""

    final_report = ai_driver.analyze_structural(reduce_prompt, NewsReport)
    if final_report:
        return final_report.news, final_report.overall_insight
    return [], ""
