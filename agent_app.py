import streamlit as st
import asyncio
import sys
import json
import os
import datetime
import subprocess
import concurrent.futures
import platform
import urllib.request
import urllib.parse
import re
from typing import List

# ================= 0. 核心库引用 =================
from pydantic import BaseModel, Field, ValidationError
from langchain_text_splitters import RecursiveCharacterTextSplitter
from openai import OpenAI  

# ================= 1. 核心网络配置 =================
if platform.system() == "Windows":
    os.environ["http_proxy"] = "http://127.0.0.1:7890"
    os.environ["https_proxy"] = "http://127.0.0.1:7890"
else:
    os.environ.pop("http_proxy", None)
    os.environ.pop("https_proxy", None)
    os.environ.pop("HTTP_PROXY", None)
    os.environ.pop("HTTPS_PROXY", None)

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
    title: str = Field(description="新闻标题（务必翻译为中文）")
    source: str = Field(description="来源媒体（保留原名）")
    date_check: str = Field(description="真实日期 YYYY-MM-DD")
    summary: str = Field(description="不少于400字的深度分析，包含：事件核心、深度细节、行业影响（纯中文）")
    importance: int = Field(description="重要性 1-5")

class NewsReport(BaseModel):
    news: List[NewsItem] = Field(description="新闻列表")

# ================= 4. 内置 DeepSeek 驱动 =================
class EnterpriseDeepSeekDriver:
    def __init__(self, api_key, model_id):
        self.valid = False
        if not api_key: return
        try:
            self.client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
            self.model_id = model_id
            self.valid = True
        except Exception:
            pass

    def analyze_structural(self, prompt, structure_class):
        if not self.valid: return None
        schema_str = json.dumps(structure_class.model_json_schema(), ensure_ascii=False)
        sys_prompt = f"你是顶级商业情报分析师。必须严格按此 JSON Schema 返回数据，不带任何废话：\n{schema_str}"
        try:
            response = self.client.chat.completions.create(
                model=self.model_id,
                messages=[{"role": "system", "content": sys_prompt}, {"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.1, 
                max_tokens=8192
            )
            raw_text = response.choices[0].message.content.strip()
            try:
                json_obj = json.loads(raw_text)
                if isinstance(json_obj, list): json_obj = {"news": json_obj}
                return structure_class(**json_obj)
            except Exception: return None
        except Exception: return None

# ================= 5. 核心业务函数 =================

@st.cache_resource(show_spinner="☁️ 首次启动：正在云端配置无头浏览器内核 (约需1-2分钟)...")
def check_and_install_playwright():
    try:
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True, capture_output=True)
        if platform.system() != "Windows":
            subprocess.run([sys.executable, "-m", "playwright", "install-deps", "chromium"], check=True, capture_output=True)
        return True
    except Exception:
        return False

# 🔴 终极重构：Python端高速过滤 + 自动保底机制
def search_web(query, sites_text, timelimit, max_results=15):
    sites = [s.strip() for s in sites_text.split('\n') if s.strip()]
    
    # 内部执行函数
    def execute_search(t_limit):
        results = []
        urls_seen = set()
        
        # 1. 尝试 DuckDuckGo (极简查询，防卡死)
        try:
            # 严格设定 10 秒超时，绝不死等！
            with DDGS(timeout=10) as ddgs: 
                # 多抓取一些数据，留给 Python 过滤
                res = ddgs.text(query, max_results=40, timelimit=t_limit)
                for r in res:
                    link = r.get('href', '')
                    # 🔴 Python 本地毫秒级过滤域名
                    if sites and not any(s in link for s in sites):
                        continue
                    if link not in urls_seen:
                        urls_seen.add(link)
                        results.append(r)
                    if len(results) >= max_results:
                        return results
        except Exception:
            pass 

        # 2. 如果DDG受限，尝试 Bing 备用通道
        if not results:
            try:
                bing_query = query
                if sites: # Bing能处理部分 site: 语法
                    bing_query += " " + " OR ".join([f"site:{s}" for s in sites])
                bing_url = f"https://www.bing.com/search?q={urllib.parse.quote(bing_query)}"
                
                headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
                req = urllib.request.Request(bing_url, headers=headers)
                html = urllib.request.urlopen(req, timeout=10).read().decode('utf-8')
                
                links = re.findall(r'href="(https?://[^"]+)"', html)
                for link in links:
                    if "bing.com" not in link and "microsoft.com" not in link:
                        if sites and not any(s in link for s in sites):
                            continue
                        if link not in urls_seen:
                            urls_seen.add(link)
                            results.append({'href': link})
                        if len(results) >= max_results:
                            break
            except Exception:
                pass

        return results

    # 第 1 阶段：按用户指定的时间严格搜索
    final_results = execute_search(timelimit)
    
    # 🔴 第 2 阶段：【智能保底】如果指定时间内真的没新闻，自动放宽时间全网搜！
    if not final_results and timelimit is not None:
        # 给界面发送提示
        st.toast(f"⏳ 【{query}】在选定时间内无结果，已自动启动全时段深度检索以确保情报不断供！")
        final_results = execute_search(None)

    return final_results[:max_results]

async def crawl_urls_concurrently(urls):
    full_content = ""
    valid_count = 0
    async with AsyncWebCrawler() as crawler:
        tasks = [crawler.arun(url=url) for url in urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for i, res in enumerate(results):
            if isinstance(res, Exception): continue
            if res.success:
                valid_count += 1
                markdown_text = res.fit_markdown if hasattr(res, 'fit_markdown') and res.fit_markdown else res.markdown
                if markdown_text and len(markdown_text) > 200:
                    full_content += f"\n\n=== SOURCE START: {urls[i]} ===\n{markdown_text[:15000]}\n=== SOURCE END ===\n"
    return full_content, valid_count

def safe_run_async_crawler(urls):
    new_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(new_loop)
    try:
        return new_loop.run_until_complete(crawl_urls_concurrently(urls))
    finally:
        new_loop.close()

def map_reduce_analysis(ai_driver, topic, full_text, current_date, time_opt):
    if not full_text or len(full_text) < 100: return []
    docs = RecursiveCharacterTextSplitter(chunk_size=15000, chunk_overlap=1500).create_documents([full_text])
    all_extracted_news = []

    def process_single_doc(doc):
        map_prompt = f"""
        今天是 {current_date}。从以下文本提取关于【{topic}】的新闻情报。
        生死红线：
        1. 【{topic}】必须是绝对主角，顺带提及的直接丢弃！
        2. 剔除明显的陈年旧闻，提取与最新动态相关的情报！
        无符合条件的内容必须返回 `{{"news": []}}`。
        文本：{doc.page_content}
        """
        return ai_driver.analyze_structural(map_prompt, NewsReport)

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        for future in concurrent.futures.as_completed([executor.submit(process_single_doc, d) for d in docs]):
            res = future.result()
            if res and res.news: all_extracted_news.extend(res.news)

    if not all_extracted_news: return []
    combined_json = json.dumps([item.model_dump() for item in all_extracted_news], ensure_ascii=False)

    reduce_prompt = f"""
    今天是 {current_date}。你是极其严苛的科技媒体总编。
    任务：
    1. 彻底清洗：剔除毫无营养的旧闻和非主角新闻。
    2. 合并去重。
    3. 扩写：不少于 400 字（包含：事件核心、深度细节、行业影响）。
    4. 纯中文专业排版。
    5. 按重要性降序，最多保留 6 条。
    数据：{combined_json}
    """
    final_report = ai_driver.analyze_structural(reduce_prompt, NewsReport)
    return final_report.news if final_report else []

def generate_word(data, filename, model_name):
    doc = Document()
    normal_style = doc.styles['Normal']
    normal_style.font.name = '微软雅黑'
    normal_style._element.rPr.rFonts.set(qn('w:eastAsia'), '微软雅黑')
    normal_style.font.size = Pt(10.5) 
    for i in range(1, 4):
        h_style = doc.styles[f'Heading {i}']
        h_style.font.name = '微软雅黑'
        h_style._element.rPr.rFonts.set(qn('w:eastAsia'), '微软雅黑')

    doc.add_heading("DeepSeek 深度科技研报", 0)
    doc.add_paragraph(f"生成日期: {datetime.date.today()} | 引擎: {model_name}")

    for section in data:
        doc.add_heading(f"专题：{section['topic']}", level=1)
        if not section['data']:
            doc.add_paragraph("在指定时间范围内，未发现重大情报。")
            continue
        for news in section['data']:
            doc.add_heading(news.title, level=2)
            p = doc.add_paragraph()
            run = p.add_run(f"来源: {news.source} | 时间: {news.date_check} | 热度: {'⭐'*news.importance}")
            run.font.color.rgb = RGBColor(128, 128, 128)
            doc.add_paragraph(news.summary)
            doc.add_paragraph("=" * 40)
    
    path = f"{filename}.docx"
    doc.save(path)
    return path

# ================= 6. 主界面 =================
with st.sidebar:
    st.header("🐳 DeepSeek 控制台")
    api_key = st.text_input("API Key", type="password")
    model_id = st.selectbox("模型", ["deepseek-chat"], index=0)
    st.divider()
    time_opt = st.selectbox("时间范围", ["过去 24 小时", "过去 1 周", "过去 1 个月", "不限时间"], index=0)
    time_limit_dict = {"过去 24 小时": "d", "过去 1 周": "w", "过去 1 个月": "m", "不限时间": None}
    
    st.markdown("**搜外媒请用英文名 (如 Google、Apple)**")
    sites = st.text_area("重点搜索源", "techcrunch.com\nbloomberg.com/technology\nithome.com\ntheverge.com\nreadhub.cn\n36kr.com", height=130)
    file_name = st.text_input("文件名", f"深度研报_{datetime.date.today()}")

st.title("🐳 企业情报探员 (极速出击版)")
query_input = st.text_input("输入主题 (用 \\ 隔开，外媒源建议用英文如：Google \\ Apple)", "Google \\ 微软")
btn = st.button("🚀 开始生成研报", type="primary")

if btn:
    if not api_key:
        st.error("❌ 请填入 API Key！")
    elif not query_input:
        st.warning("请输入关键词！")
    else:
        check_and_install_playwright()
        
        topics = [t.strip() for t in query_input.split('\\') if t.strip()]
        all_data = []
        ai = EnterpriseDeepSeekDriver(api_key, model_id)
        current_date_str = datetime.date.today().strftime("%Y年%m月%d日")

        st.info("🚀 探员已极速出击，正在检索目标...")

        for topic in topics:
            st.markdown(f"#### 🔵 追踪目标: 【{topic}】")
            
            with st.spinner(f"正在闪电搜寻关于【{topic}】的最新线索..."):
                links = search_web(topic, sites, time_limit_dict[time_opt])
            
            if not links: 
                st.warning(f"⚠️ {topic}：所有备用通道均未搜到情报。建议更换为英文名搜索。")
                continue
                
            st.write(f"🔍 成功截获 {len(links)} 个暗网与明网相关网址，启动智能爬虫...")

            with st.spinner(f"正在并发抓取并提纯这 {len(links)} 个网页的正文..."):
                full_text_data, valid_count = safe_run_async_crawler(urls=[r['href'] for r in links])

            if full_text_data:
                st.write(f"🧠 成功提取 {valid_count} 个纯净网页。DeepSeek 正在执行精密分析（约耗时10-30秒）...")
                
                with st.spinner("AI 正在冷酷清洗并提炼精华..."):
                    final_news_list = map_reduce_analysis(ai, topic, full_text_data, current_date_str, time_opt)
                
                if final_news_list:
                    all_data.append({"topic": topic, "data": final_news_list})
                    st.success(f"✅ 【{topic}】分析完毕！已为您锁定 {len(final_news_list)} 条高能商业情报。")
                else:
                    st.warning(f"⚠️ 【{topic}】的内容经 AI 过滤后，均未通过您的“生死红线”标准。")
            else:
                st.error(f"❌ 网页抓取失败或正文均为空，目标网站反爬拦截。")
            
            st.divider()

        if all_data:
            path = generate_word(all_data, file_name, model_id)
            st.balloons()
            st.success("🎉 全链条任务执行完毕！")
            with open(path, "rb") as f:
                st.download_button("📥 立即下载中文深度研报 (Word)", f, file_name=path, type="primary")
        else:
            st.error("❌ 任务结束。本次搜寻未发现符合极端严格条件的情报，请更换关键词重试。")
