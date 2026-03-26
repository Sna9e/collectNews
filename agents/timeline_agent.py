from pydantic import BaseModel, Field
from typing import List

class TimelineEvent(BaseModel):
    date: str = Field(description="新闻爆出的真实近期日期（格式：MM月DD日）。")
    source: str = Field(description="信息来源网站名")
    event: str = Field(description="15字以内的一句话极简干货概括")

class TimelineReport(BaseModel):
    events: List[TimelineEvent] = Field(description="按时间先后排序的事件列表")

def generate_timeline(ai_driver, raw_search_results, topic, current_date, time_opt):
    if not raw_search_results: return []
    
    snippets = []
    for r in raw_search_results:
        snippets.append(f"标:{r.get('title')} | 摘:{r.get('content')} | 源:{r.get('url')}")
    
    combined_text = "\n".join(snippets)
    
    prompt = f"""
    【全局时间锚点】：今天是 {current_date}。要求的时间范围是：【{time_opt}】。
    以下是全网搜集的关于【{topic}】的最新简讯碎片：
    {combined_text}
    
    任务与规则：
    1. 梳理出最多 15 条核心事件。
    2. 🔴 绝对红线（实体隔离）：你提取的每一个事件，【{topic}】必须是绝对的唯一主角！搜索引擎可能会混入“科技晨报”、“竞品动态”（比如搜苹果，混入了Oppo或沃尔玛的促销新闻）。对于这种非【{topic}】主导的无关事件，必须无情剔除，一条都不能留！
    3. 🔴 时间矫正（极其重要）：很多新闻包含对未来的预测（例如“预计今年9月15日发布新手机”）。此时，发生日期必须填写为【这则新闻爆出的近期时间】（如3月9日），绝对不能写未来的9月15日！事件内容写成“爆料称9月将发布新手机”。
    4. 仅剔除那些明显是去年或几个月前发生的陈年旧闻，合并重复的报道。
    5. 严格按照事件爆出的时间先后顺序（过去 -> 现在）进行排列。
    """
    report = ai_driver.analyze_structural(prompt, TimelineReport)
    return report.events if report else []
