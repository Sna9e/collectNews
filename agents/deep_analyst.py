import json
import concurrent.futures
from pydantic import BaseModel, Field
from typing import List, Optional
from langchain_text_splitters import RecursiveCharacterTextSplitter

# 🌟 专门用于捕捉图表对比数据的结构 (加入 default 兜底，防止验证崩溃)
class ChartData(BaseModel):
    has_chart: bool = Field(default=False, description="如果新闻中包含2个及以上的具体对比数据，设为True；否则设为False。")
    chart_title: str = Field(default="", description="图表的标题，例如：2024各厂AI模型参数量对比")
    labels: List[str] = Field(default_factory=list, description="横坐标标签，例如：['OpenAI', 'Google', 'Meta']")
    values: List[float] = Field(default_factory=list, description="纵坐标对应的纯数字，例如：[175, 540, 70]")
    chart_type: str = Field(default="bar", description="从 'bar', 'pie', 'line' 中选一个最合适的")

class NewsItem(BaseModel):
    title: str = Field(default="未命名情报", description="新闻标题（务必翻译为中文）")
    source: str = Field(default="未知网络", description="来源媒体")
    date_check: str = Field(default="近期", description="真实日期 YYYY-MM-DD")
    summary: str = Field(default="暂无详情", description="深度商业分析。必须严格分段并包含：【事件核心】、【深度细节/数据支撑】、【行业深远影响】。")
    url: str = Field(default="", description="该新闻的原文链接 URL（必须从原始数据中提取）")
    importance: int = Field(default=3, description="重要性 1-5")
    chart_info: ChartData = Field(default_factory=ChartData, description="自动化图表数据提取")

# 🌟 修复核心1：为 Map 切片阶段专门设计的宽松结构 (去掉 overall_insight，防止 Pydantic 报错)
class MapReport(BaseModel):
    news: List[NewsItem] = Field(default_factory=list, description="提取的新闻列表，如果没有符合条件的，返回空数组 []")

# 🌟 最终汇报结构
class NewsReport(BaseModel):
    overall_insight: str = Field(default="近期无重大异动", description="200字以内的全局核心摘要，概括本次所有情报的最核心结论")
    news: List[NewsItem] = Field(default_factory=list, description="新闻列表")

def map_reduce_analysis(ai_driver, topic, full_text, current_date, time_opt, past_memories_string=""):
    if not full_text or len(full_text) < 100: return [], ""
    
    docs = RecursiveCharacterTextSplitter(chunk_size=8000, chunk_overlap=1000).create_documents([full_text])
    all_extracted_news = []

    def process_single_doc(doc):
        map_prompt = f"""
        【时间锚点】：今天是 **{current_date}**。要求范围：【{time_opt}】。
        任务：提取关于【{topic}】的新闻情报。
        红线：发现早于要求时间的旧闻直接丢弃！【{topic}】必须是绝对主角！无符合条件必须返回空的 news 数组。
        文本：{doc.page_content}
        """
        # 🌟 强制使用宽松的 MapReport，保底不崩
        return ai_driver.analyze_structural(map_prompt, MapReport)

    # 🌟 修复核心2：将 max_workers 降为 2，防止与外层叠加触发 API 429 熔断
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        for future in concurrent.futures.as_completed([executor.submit(process_single_doc, d) for d in docs]):
            try:
                res = future.result()
                if res and res.news: 
                    all_extracted_news.extend(res.news)
            except Exception as e:
                print(f"切片提取失败: {e}")

    if not all_extracted_news: return [], ""
    
    # 将 Map 提取的所有碎片化新闻转为 JSON 传给最终汇总层
    combined_json = json.dumps([item.model_dump() for item in all_extracted_news], ensure_ascii=False)

    if "24" in time_opt:
        detail_prompt = "要求每条新闻约 600 字。必须强行提取：具体的数字（融资金额、股价等）、核心原话、微小动作细节。事件概述不少于200字，不得少于整体篇幅的1/3."
    else:
        detail_prompt = "要求每条新闻约 300 字。侧重于宏观趋势、战略意图的分析。"

    reduce_prompt = f"""
        【全局时间锚点】：今天是 **{current_date}**。你是顶级科技媒体总编。
        
        【🧠 你的历史记忆库】：
        {past_memories_string}
        
        【📰 今天的新情报碎片】：
        {combined_json}
        
        任务：
        1. 终极剔除旧闻。2. 合并同事件新闻。
        3. 深度扩写排版：
        {detail_prompt}
        ⚠️ 极其重要：如果今天的新情报与【你的历史记忆库】存在延续性、推进或重大反转，请务必在【事件核心】中以“前情回顾”的口吻明确指出并进行对比！
        📊 极其重要：如果新闻中出现了明显的数据对比（如金额、份额、增速等），请务必准确提取到 chart_info 中，我们将利用这些数据调用可视化 API 进行画图！
        4. 提炼 overall_insight（200字以内），记录今天的核心结论。
        5. 最多保留最核心的5条。
    """
    
    # 🌟 最终层使用 NewsReport 严格输出
    final_report = ai_driver.analyze_structural(reduce_prompt, NewsReport)
    if final_report:
        return final_report.news, final_report.overall_insight
        
    return [], ""
