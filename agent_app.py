import streamlit as st
import asyncio
import sys
import json
import os
import datetime
import subprocess
import concurrent.futures
from typing import List

# ================= 0. 核心库引用 =================
from pydantic import BaseModel, Field, ValidationError
from langchain_text_splitters import RecursiveCharacterTextSplitter
from openai import OpenAI  

# ================= 1. 核心网络配置 =================
# 在 Streamlit Cloud 上运行时，其实不需要本地代理
# 为了兼容本地和云端，我们使用 try-except 忽略代理报错
os.environ["http_proxy"] = "http://127.0.0.1:7890"
os.environ["https_proxy"] = "http://127.0.0.1:7890"

# ================= 2. 爬虫与文档库引用 =================
try:
    from ddgs import DDGS
except ImportError:
    from duckduckgo_search import DDGS

from crawl4ai import AsyncWebCrawler
from docx import Document
from docx.shared import RGBColor, Pt
from docx.oxml.ns import qn

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

st.set_page_config(page_title="DeepSeek 科技探员", page_icon="🐳", layout="wide")


# ================= 3. 定义结构化数据 =================
class NewsItem(BaseModel):
    title: str = Field(description="新闻标题（请务必翻译为地道的中文）")
    source: str = Field(description="新闻来源或媒体名称（保留原名即可）")
    date_check: str = Field(description="新闻发生的真实日期，格式 YYYY-MM-DD")
    summary: str = Field(description="详细的深度新闻摘要，需包含事件背景、核心事实、数据支撑以及行业影响。篇幅不少于 400 字。（请务必全部翻译为流畅专业的中文）")
    importance: int = Field(description="重要性评分 1-5，需根据事件对行业的深远影响度进行客观打分")

class NewsReport(BaseModel):
    news: List[NewsItem] = Field(description="提取的新闻列表")


# ================= 4. 内置 DeepSeek 驱动 =================
class EnterpriseDeepSeekDriver:
    def __init__(self, api_key, model_id):
        self.valid = False
        if not api_key:
            return

        try:
            self.client = OpenAI(
                api_key=api_key,
                base_url="https://api.deepseek.com"
            )
            self.model_id = model_id
            self.valid = True
        except Exception as e:
            st.error(f"❌ DeepSeek 初始化失败: {e}")

    def analyze_structural(self, prompt, structure_class):
        if not self.valid: return None

        schema_str = json.dumps(structure_class.model_json_schema(), ensure_ascii=False)
        system_instruction = f"""
        你是一个极其严苛且专业的顶级商业情报分析师。你的任务是提取关键信息并输出严格的 JSON 格式。
        请严格按照以下 JSON Schema 结构返回数据，不要输出任何额外的解释文本：
        {schema_str}
        """

        try:
            response = self.client.chat.completions.create(
                model=self.model_id,
                messages=[
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.1, 
                max_tokens=8192
            )

            raw_text = response.choices[0].message.content.strip()

            try:
                json_obj = json.loads(raw_text)
                if isinstance(json_obj, list):
                    json_obj = {"news": json_obj}
                validated_obj = structure_class(**json_obj)
                return validated_obj
            except (json.JSONDecodeError, ValidationError):
                return None

        except Exception:
            return None


# ================= 5. 业务逻辑函数 =================

def search_web(query, sites_text, timelimit, max_results=15):
    sites = [s.strip() for s in sites_text.split('\n') if s.strip()]
    current_year = datetime.date.today().year
    final_query = f"{query} {current_year} (news OR 最新 OR 商业)"
    if sites:
        final_query += f" ({' OR '.join([f'site:{s}' for s in sites])})"

    results = []
    try:
        # 在云端环境如果 DDGS 报错（通常是被墙或限流），捕获异常防止崩溃
        with DDGS(proxies=None) as ddgs: 
            ddgs_gen = ddgs.text(final_query, max_results=max_results, timelimit=timelimit)
            for r in ddgs_gen: results.append(r)
    except Exception as e:
        pass # 失败静默，交给外部判断

    return results[:max_results]


# 🔴 UI 剥离修复：不再将 Streamlit 的 status 对象传入异步函数
async def crawl_urls_concurrently(urls):
    if not os.path.exists(os.path.join(os.path.expanduser("~"), "AppData", "Local", "ms-playwright")):
        try:
            subprocess.run(["playwright", "install", "chromium"], check=True)
        except: pass

    full_content = ""
    valid_count = 0

    async with AsyncWebCrawler() as crawler:
        tasks = [crawler.arun(url=url) for url in urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for i, res in enumerate(results):
            if isinstance(res, Exception):
                continue
            if res.success:
                valid_count += 1
                markdown_text = res.fit_markdown if hasattr(res, 'fit_markdown') and res.fit_markdown else res.markdown
                if len(markdown_text) > 200:
                    full_content += f"\n\n=== SOURCE START: {urls[i]} ===\n{markdown_text[:20000]}\n=== SOURCE END ===\n"

    return full_content, valid_count


# 🔴 UI 剥离修复：去除线程内部的 UI 更新
def map_reduce_analysis(ai_driver, topic, full_text, current_date, time_opt):
    if not full_text or len(full_text) < 100:
        return []

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=15000, 
        chunk_overlap=1500,
        separators=["\n\n", "\n", "。", "！", "？", " ", ""]
    )
    docs = text_splitter.create_documents([full_text])
    all_extracted_news = []

    def process_single_doc(doc):
        map_prompt = f"""
        今天是 {current_date}。
        当前任务：从以下文本片段中提取关于【{topic}】的新闻情报。
        
        【生死级过滤红线（违反直接淘汰）】：
        1. 核心主角原则：【{topic}】必须是该新闻的**绝对主角**或核心参与方。如果只是文章中顺带提及（例如：“像{topic}一样”、“作为对比，{topic}之前曾……”、“{topic}的竞争对手某某某”），**绝对不要提取！宁可返回空列表！**
        2. 严格时间判定：用户要求的新闻时间范围是：【{time_opt}】。请仔细研判文本中的时间线索（如日期、昨天、几小时前）。如果明显是发生在 {time_opt} 之前的旧闻，或者是网页底部的“历史热文推荐”，**绝对不要提取！**
        
        如果文本中没有完全符合上述两点红线的内容，必须返回 `{{"news": []}}`。
        如果符合，提取并翻译为专业的中文。

        文本片段：
        {doc.page_content}
        """
        res_obj = ai_driver.analyze_structural(map_prompt, NewsReport)
        return res_obj

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        future_to_doc = [executor.submit(process_single_doc, doc) for doc in docs]
        for future in concurrent.futures.as_completed(future_to_doc):
            res_obj = future.result()
            if res_obj and res_obj.news:
                all_extracted_news.extend(res_obj.news)

    if not all_extracted_news:
        return []

    combined_json = json.dumps([item.model_dump() for item in all_extracted_news], ensure_ascii=False)

    reduce_prompt = f"""
    今天是 {current_date}。你是极其严苛的科技媒体总编。以下是初筛后关于【{topic}】的新闻列表数据（JSON格式）。

    【终极审查任务】：
    1. **冷酷清洗**：再次检查！任何发生时间不在【{time_opt}】之内的过期旧闻，统统删掉！任何【{topic}】只是配角的新闻，统统删掉！宁缺毋滥。
    2. **合并去重**：报道同一事件的新闻必须合并为一篇。
    3. **深度专业扩写**：将保留下来的新闻写成具有深度的商业分析报道。每条 summary **必须不少于 400 字**，结构强制包含：【事件核心】、【深度细节/数据支撑】、【行业深远影响】。
    4. **语言**：全部采用极其专业、流畅的中文排版。
    5. **权威排序**：按重要性降序排列，最多只保留最核心的 6 条。

    原始数据：
    {combined_json}
    """

    final_report = ai_driver.analyze_structural(reduce_prompt, NewsReport)
    if final_report:
        return final_report.news
    return []


def generate_word(data, filename, model_name):
    doc = Document()
    
    normal_style = doc.styles['Normal']
    normal_style.font.name = '微软雅黑'
    normal_style._element.rPr.rFonts.set(qn('w:eastAsia'), '微软雅黑')
    normal_style.font.size = Pt(10.5) 

    for i in range(1, 4):
        heading_style = doc.styles[f'Heading {i}']
        heading_style.font.name = '微软雅黑'
        heading_style._element.rPr.rFonts.set(qn('w:eastAsia'), '微软雅黑')

    doc.add_heading("DeepSeek 深度科技研报", 0)
    doc.add_paragraph(f"生成日期: {datetime.date.today()} | 驱动引擎: {model_name}")

    for section in data:
        doc.add_heading(f"专题：{section['topic']}", level=1)
        news_list = section['data']

        if not news_list:
            doc.add_paragraph("在指定时间范围内，未发现该主题的绝对核心级别重大情报。")
            continue

        for news in news_list:
            doc.add_heading(news.title, level=2)
            p = doc.add_paragraph()
            run = p.add_run(f"来源: {news.source}  |  事件真实时间: {news.date_check}  |  热度: {'⭐' * news.importance}")
            run.font.color.rgb = RGBColor(128, 128, 128)
            
            doc.add_paragraph(news.summary)
            doc.add_paragraph("=" * 40)

    real_filename = f"{filename}.docx"
    doc.save(real_filename)
    return real_filename


# ================= 6. 主界面 =================
with st.sidebar:
    st.header("🐳 DeepSeek 核心控制台")

    api_key = st.text_input("DeepSeek API Key", type="password", help="在此输入你的 DeepSeek API 密钥")
    model_id = st.selectbox("模型", ["deepseek-chat"], index=0)

    st.divider()
    
    time_opt = st.selectbox("资讯搜索时间范围", ["过去 24 小时", "过去 1 周", "过去 1 个月", "不限时间"], index=0)
    time_limit_dict = {"过去 24 小时": "d", "过去 1 周": "w", "过去 1 个月": "m", "不限时间": None}
    time_limit = time_limit_dict[time_opt]

    default_sites = (
        "techcrunch.com\n"
        "bloomberg.com/technology\n"
        "ithome.com\n"
        "theverge.com\n"
        "wired.com\n"
        "readhub.cn\n"
        "geekpark.net\n"
        "36kr.com"
    )
    sites = st.text_area("重点搜索源 (每行一个)", default_sites, height=150)
    file_name = st.text_input("生成文件名", f"深度研报_{datetime.date.today()}")

st.title("🐳 DeepSeek 科技情报探员 (云端安全版)")
query_input = st.text_input("输入主题 (用 \\ 隔开，如：苹果 \\ OpenAI)", "谷歌 \\ 微软")
btn = st.button("生成深度研报", type="primary")

if btn:
    if not api_key:
        st.error("❌ 请先在左侧边栏填入 DeepSeek API Key！")
    elif not query_input:
        st.warning("请输入关键词")
    else:
        topics = [t.strip() for t in query_input.split('\\') if t.strip()]
        all_data = []

        status = st.status("🚀 系统启动，情报网已撒出...", expanded=True)
        ai = EnterpriseDeepSeekDriver(api_key, model_id)
        current_date_str = datetime.date.today().strftime("%Y年%m月%d日")

        for topic in topics:
            status.write(f"🔵 **正在追踪主题: {topic}**")

            links = search_web(topic, sites, time_limit)
            if not links:
                status.warning(f"⚠️ {topic} 无搜索结果 (海外搜索 API 在云端可能受限，请放宽条件)")
                continue

            status.write(f"⚡ 启动并发抓取: {len(links)} 个深度源页面...")
            urls = [r['href'] for r in links]
            
            # 🔴 UI 彻底安全化：不在里面更新任何进度
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            full_text_data, valid_count = loop.run_until_complete(crawl_urls_concurrently(urls))
            loop.close()
            status.write(f"✅ 抓取完成，有效提纯页面: {valid_count}/{len(urls)}")

            if full_text_data:
                # 🔴 UI 彻底安全化：不在多线程里写任何东西到前端
                status.write(f"🧠 {model_id} 正在疯狂研读与去噪提炼 (请耐心等待大约 10-30 秒)...")
                final_news_list = map_reduce_analysis(ai, topic, full_text_data, current_date_str, time_opt)

                if final_news_list:
                    all_data.append({"topic": topic, "data": final_news_list})
                    status.write(f"✅ {topic} 分析完毕！严格提炼出 {len(final_news_list)} 条核心情报。")
                else:
                    status.warning(f"⚠️ {topic} 在选定时间内，未发现其作为核心主角的重大情报。")
            else:
                status.error(f"❌ {topic} 抓取内容为空")

        if all_data:
            path = generate_word(all_data, file_name, model_id)
            status.update(label="研报生成完毕！", state="complete")
            with open(path, "rb") as f:
                st.download_button("📥 立即下载中文深度研报 (Word)", f, file_name=path)
        else:
            status.error("❌ 任务结束。未发现符合严格条件的情报，未能生成研报。")
