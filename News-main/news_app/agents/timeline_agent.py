# -*- coding: utf-8 -*-
from typing import List

from pydantic import BaseModel, Field


class TimelineEvent(BaseModel):
    date: str = Field(description="真实日期（MM月DD日 或 YYYY-MM-DD）")
    source: str = Field(description="来源媒体")
    event: str = Field(description="15字以内的事件摘要")


class TimelineReport(BaseModel):
    events: List[TimelineEvent] = Field(description="按时间顺序排列的事件列表")


def generate_timeline(ai_driver, raw_search_results, topic, current_date, time_opt):
    if not raw_search_results:
        return []

    snippets = []
    for r in raw_search_results:
        snippets.append(f"标题:{r.get('title')} | 摘要:{r.get('content')} | 来源:{r.get('url')}")

    combined_text = "\n".join(snippets)
    prompt = f"""
【全局时间锚点】今天是 {current_date}，要求范围：{time_opt}。
以下是关于“{topic}”的最新碎片：
{combined_text}

任务规则：
1. 提取最多 15 条核心事件。
2. “{topic}”必须是绝对主角，非主角事件全部剔除。
3. 若出现未来预测（例如“9月将发布”），日期需填写新闻爆出的时间，而不是未来时间。
4. 剔除明显过期旧闻，合并重复报道。
5. 严格按时间先后排序（过去 -> 现在）。
"""

    report = ai_driver.analyze_structural(prompt, TimelineReport)
    return report.events if report else []
