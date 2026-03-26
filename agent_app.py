import streamlit as st
import datetime
import difflib
import json
import concurrent.futures 
from openai import OpenAI
from pydantic import BaseModel, Field

# 🔴 模块化导入 (已彻底移除多模型，保留最稳定的经典架构)
from tools.search_engine import search_web, safe_run_async_crawler, filter_china_results
from tools.export_word import generate_word
from tools.export_ppt import generate_ppt
from tools.memory_manager import GistMemoryManager 
from agents.deep_analyst import map_reduce_analysis
from agents.timeline_agent import generate_timeline
from tools.finance_engine import fetch_financial_data

st.set_page_config(page_title="DeepSeek 部门情报中心", page_icon="🐳", layout="wide")

if "report_ready" not in st.session_state:
    st.session_state.report_ready = False
    st.session_state.word_path = ""
    st.session_state.ppt_path = ""

# 🌟 极简且极其稳定的单脑驱动
class AI_Driver:
    def __init__(self, api_key, model_id):
        self.valid = False
        if api_key:
            try:
                self.client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
                self.model_id = model_id
                self.valid = True
            except Exception: pass

    def analyze_structural(self, prompt, structure_class):
        if not self.valid: return None
        
        sys_prompt = f"必须严格按 JSON 格式返回，不要带有任何思考过程或多余文字。JSON Schema 如下:\n{json.dumps(structure_class.model_json_schema(), ensure_ascii=False)}"
        
        try:
            res = self.client.chat.completions.create(
                model=self.model_id,
                messages=[{"role": "system", "content": sys_prompt}, {"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.1,  
                max_tokens=4096   
            )
            content = res.choices[0].message.content.strip()
            
            # 🌟 终极安全净化：纯字符串操作，不使用正则，剥离所有可能的 markdown 包裹
            if content.startswith("```"):
                content = content.strip("`").strip()
                if content.lower().startswith("json"):
                    content = content[4:].strip()
            
            data = json.loads(content)
            if isinstance(data, list): data = {list(structure_class.model_fields.keys())[0]: data}
            return structure_class(**data)
        except Exception as e: 
            print(f"⚠️ AI 结构化解析失败: {e}")
            return None 

class FinanceCatalysts(BaseModel):
    policy: str = Field(description="【政策发布】限40字")
    earnings: str = Field(description="【财报表现】限40字")
    landmark: str = Field(description="【产业标志】限40字")
    style: str = Field(description="【市场风格轮动】限40字")

def get_finance_catalysts(ai_driver, topic, news_text):
    prompt = f"你是中金投研分析师。请基于以下关于【{topic}】的新闻，提炼近期二级市场的核心催化剂：\n{news_text}"
    return ai_driver.analyze_structural(prompt, FinanceCatalysts)

def finance_fallback_payload(msg="Finance engine temporarily unavailable"):
    return {
        "is_public": False,
        "data_available": False,
        "data_source": "fallback",
        "ticker": "",
        "currency": "",
        "msg": msg,
        "current_price": "N/A",
        "change_pct": None,
        "open_price": "N/A",
        "prev_close": "N/A",
        "pe_pb": "N/A",
        "erp": "N/A",
        "market_cap": "N/A",
        "range_52w": "N/A",
        "volume": "N/A",
        "chart_path": None,
    }

with st.sidebar:
    st.header("🐳 部门情报控制台")
    try:
        api_key = st.secrets["DEEPSEEK_API_KEY"]
        tavily_key = st.secrets["TAVILY_API_KEY"]
        jina_key = st.secrets.get("JINA_API_KEY", "")
        gh_token = st.secrets.get("GITHUB_TOKEN", "")
        gist_id = st.secrets.get("GIST_ID", "")
        st.success("🔒 部门专属安全引擎已连接")
    except KeyError:
        st.error("⚠️ 未在云端检测到 Secrets 配置，请联系管理员！")
        api_key, tavily_key, jina_key, gh_token, gist_id = "", "", "", "", ""

    st.divider()
    model_id = st.selectbox("核心模型", ["deepseek-chat"], index=0)
    time_opt = st.selectbox("回溯时间线", ["过去 24 小时", "过去 1 周", "过去 1 个月"], index=0)
    time_limit_dict = {"过去 24 小时": "d", "过去 1 周": "w", "过去 1 个月": "m"}
    
    with st.expander("⚙️ 高级搜索源设置"):
        sites = st.text_area("重点搜索源", "techcrunch.com\ntheverge.com\nengadget.com\ncnet.com\nbloomberg.com/technology\nelectrek.co\ninsideevs.com\nroadtovr.com\nuploadvr.com\n36kr.com\nithome.com\nhuxiu.com\ngeekpark.net\nvrtuoluo.cn\nd1ev.com", height=250)
    
    file_name = st.text_input("导出文件名", f"高管战报_{datetime.date.today()}")

st.title("🐳 商业情报战情室 (双轨稳定兜底版)")

if not st.session_state.report_ready:
    tab1, tab2 = st.tabs(["🏢 频道一：公司追踪 (带金融量化)", "🌐 频道二：每日宏观行业早报 (全域扫描)"])

    # ====================================================
    # 频道一：微观公司追踪 
    # ====================================================
    with tab1:
        st.markdown("💡 **操作指南**：输入追踪对象，多个目标请使用 `\` 隔开，系统将并发执行独立分析。")
        query_input = st.text_input("输入追踪对象", "Apple \ Google")
        
        start_btn = st.button("🚀 启动并发战情推演", type="primary", key="btn_company")

        if start_btn and api_key and tavily_key:
            process_container = st.empty()
            with process_container.container():
                topics = [t.strip() for t in query_input.split('\\') if t.strip()]

                ai = AI_Driver(api_key, model_id)
                current_date_str = datetime.date.today().strftime("%Y年%m月%d日")
                
                mem_manager = GistMemoryManager(gh_token, gist_id)
                if gh_token and gist_id: mem_manager.load_memory()

                st.info(f"⚡ 正在启动并发处理引擎 (目标数: {len(topics)})，请稍候...")
                
                def process_company_task(topic, index):
                    try:
                        # 先做搜索，确保关键 API 调用不被 finance 链路阻断
                        raw_results = search_web(topic, sites, time_limit_dict[time_opt], max_results=20, tavily_key=tavily_key)
                        if not raw_results:
                            return index, None, None
                        
                        timeline_events = generate_timeline(ai, raw_results, topic, current_date_str, time_opt)
                        urls_to_scrape = [r.get('url') for r in raw_results if r.get('url')][:10]
                        past_memories = mem_manager.get_topic_history(topic)
                        
                        # 尝试抓取长文本
                        full_text_data, _ = safe_run_async_crawler(urls=urls_to_scrape, jina_key=jina_key)
                        
                        # 🌟 核心救命稻草：如果 Jina 爬虫被墙，强行使用搜索摘要兜底！绝不让文本为空！
                        if len(full_text_data) < 500:
                            print(f"⚠️ {topic} 长文本抓取失败或被拦截，启动摘要降级模式！")
                            snippets = [f"标题:{r.get('title')} | 内容:{r.get('content')} | 链接:{r.get('url')}" for r in raw_results]
                            full_text_data = "\n\n".join(snippets)

                        final_news_list, new_insight = map_reduce_analysis(ai, topic, full_text_data, current_date_str, time_opt, past_memories)
                        
                        deep_data_res = None
                        if final_news_list:
                            deduped_news = []
                            seen_titles = []
                            for n in final_news_list:
                                if not any(difflib.SequenceMatcher(None, n.title, s).ratio() > 0.6 for s in seen_titles):
                                    deduped_news.append(n)
                                    seen_titles.append(n.title)
                            
                            if deduped_news:
                                try:
                                    finance_data = fetch_financial_data(ai, topic) or finance_fallback_payload()
                                except Exception as e:
                                    print(f"⚠️ Finance chain failed for {topic}: {e}")
                                    finance_data = finance_fallback_payload(f"Finance chain failed: {e}")

                                if finance_data.get('is_public'):
                                    news_summary_text = "\n".join([n.summary for n in deduped_news])
                                    cats = get_finance_catalysts(ai, topic, news_summary_text)
                                    if cats: finance_data['catalysts'] = cats.model_dump()
                                
                                deep_data_res = {"topic": topic, "data": deduped_news, "finance": finance_data}
                                if new_insight: mem_manager.add_topic_memory(topic, current_date_str, new_insight)
                                
                        t_data_res = {"topic": topic, "events": timeline_events} if timeline_events else None
                        return index, deep_data_res, t_data_res
                    except Exception as e:
                        print(f"⚠️ Company pipeline failed for {topic}: {e}")
                        return index, None, None

                results = []
                with st.spinner(f"🌪️ 正在并行收集与深度推演中..."):
                    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                        futures = [executor.submit(process_company_task, t, i) for i, t in enumerate(topics)]
                        for future in concurrent.futures.as_completed(futures):
                            try:
                                item = future.result()
                                if item:
                                    results.append(item)
                            except Exception as e:
                                print(f"⚠️ Company worker crashed: {e}")

                results.sort(key=lambda x: x[0])
                all_deep_data = [r[1] for r in results if r[1] is not None]
                all_timeline_data = [r[2] for r in results if r[2] is not None]
                
                st.success("✅ 并发深度分析完成！")
                if gh_token and gist_id: mem_manager.save_memory()

            if all_deep_data or all_timeline_data:
                st.session_state.word_path = generate_word(all_deep_data, all_timeline_data, file_name, model_id)
                st.session_state.ppt_path = generate_ppt(all_deep_data, all_timeline_data, file_name, model_id)
                st.session_state.report_ready = True
                st.rerun()

    # ====================================================
    # 频道二：宏观行业早报
    # ====================================================
    with tab2:
        st.markdown("💡 **本频道专为宏观视野打造**：一键搜集全球6大前沿科技领域最新进展，**多路并发，全域扫描**。")
        use_all_web = st.toggle("🌐 开启全网无界搜索 (打开则无视侧边栏源，进行全球广度覆盖)", value=True)
        search_domain = "" if use_all_web else sites

        cn_sites_default = (
            "36kr.com\n"
            "ithome.com\n"
            "huxiu.com\n"
            "leiphone.com\n"
            "geekpark.net\n"
            "jiqizhixin.com\n"
            "qbitai.com\n"
            "tmtpost.com\n"
            "pedaily.cn\n"
            "cyzone.cn\n"
            "iyiou.com\n"
            "sina.com.cn\n"
            "sohu.com\n"
            "163.com\n"
            "qq.com\n"
            "xinhua.net\n"
            "people.com.cn\n"
            "cnstock.com\n"
            "stcn.com\n"
            "eastmoney.com"
        )
        with st.expander("🇨🇳 中国专项设置（仅中文网站 + 中国公司）", expanded=False):
            china_sites = st.text_area(
                "中文网站白名单（每行一个域名）",
                cn_sites_default,
                height=220,
                key="cn_sites_whitelist"
            )
            china_query_suffix = st.text_input(
                "中国公司限定关键词（自动拼接到每条查询）",
                "中国 初创 公司 创业 融资 订单 本土 国产",
                key="cn_query_suffix"
            )
        
        INDUSTRY_TOPICS = [
            {"title": "AI手机与硬件承载", "queries": ["AI手机 硬件演进 2026", "智能手机内部空间 SLP 类载板", "消费电子 FPC 技术 突破"], "desc": "关注AI手机内部空间极度压缩、SLP与FPC的技术演进。"},
            {"title": "折叠与多维形态变革", "queries": ["三折叠手机 最新发布", "卷轴屏 手机 量产", "无孔化手机 Waterproof Buttonless 设计"], "desc": "关注三折叠手机、卷轴屏、以及无孔化设计的最新突破。"},
            {"title": "6G预研与卫星通讯", "queries": ["6G预研 最新进展", "高通 6G AI 整合芯片", "卫星通讯 手机直连 NTN"], "desc": "重点关注高通6GAI芯片及卫星直连技术(NTN)的进展。"},
            {"title": "AI穿戴与XR设备", "queries": ["超轻量化 AI眼镜 评测", "智能戒指 SmartRing 生态", "XR混合现实 硬件 创新"], "desc": "关注超轻量化AI眼镜、智能戒指的爆款产品。"},
            {"title": "绿色制程与可持续性", "queries": ["消费电子 绿色制程 创新", "欧洲市场 电子产品 碳足迹 法规", "科技巨头 ESG 战略"], "desc": "关注碳足迹硬性要求(ESG)及绿色制程策略。"},
            {"title": "全球机器人产业巡礼", "queries": ["全球 机器人 产业 报告 2026", "特斯拉 宇树科技 机器人 动态", "荣耀机器人 新兴人形机器人 机器人创业公司"], "desc": "考察全球及中国厂商。覆盖大厂及新兴创业厂商。"}
        ]

        def run_industry_pipeline(industry_topics, domain_text, china_mode=False, query_suffix=""):
            process_container = st.empty()
            with process_container.container():
                ai = AI_Driver(api_key, model_id)
                current_date_str = datetime.date.today().strftime("%Y年%m月%d日")

                if china_mode:
                    st.info("⚡ 正在启动中国专项并发引擎（仅中文网站 + 中国公司）...")
                else:
                    st.info("⚡ 正在启动全域多路扫描并发引擎，请耐心等待...")

                def process_industry_task(t, index):
                    try:
                        all_raw_results = []
                        seen_urls = set()
                        for query in t['queries']:
                            actual_query = query
                            if china_mode and query_suffix:
                                actual_query = f"{query} {query_suffix}".strip()

                            res = search_web(actual_query, domain_text, time_limit_dict[time_opt], max_results=12, tavily_key=tavily_key)
                            if china_mode:
                                res = filter_china_results(res, domain_text, require_chinese_text=True)

                            if res:
                                for r in res:
                                    url = r.get('url')
                                    if url and url not in seen_urls:
                                        seen_urls.add(url)
                                        all_raw_results.append(r)
                        
                        if not all_raw_results: return index, None, None
                        
                        top_results = all_raw_results[:20]
                        topic_label = f"{t['title']}（中国专项）" if china_mode else t['title']
                        timeline_topic = f"{t['title']}（仅中国公司）" if china_mode else t['title']
                        timeline_events = generate_timeline(ai, top_results, timeline_topic, current_date_str, time_opt)
                        
                        urls_to_scrape = [r.get('url') for r in top_results if r.get('url')][:12] 
                        full_text_data, _ = safe_run_async_crawler(urls=urls_to_scrape, jina_key=jina_key)
                        
                        # 🌟 核心救命稻草：兜底机制，无论如何给大模型塞数据！
                        if len(full_text_data) < 500:
                            snippets = [f"标题:{r.get('title')} | 内容:{r.get('content')} | 链接:{r.get('url')}" for r in top_results]
                            full_text_data = "\n\n".join(snippets)
                        
                        strict_topic_prompt = f"{t['title']}。核心提取要求：{t['desc']}"
                        if china_mode:
                            strict_topic_prompt += "。仅保留中国公司（优先初创公司）相关事件，来源必须来自中文网站；海外公司或英文站点信息一律剔除。"

                        final_news_list, _ = map_reduce_analysis(ai, strict_topic_prompt, full_text_data, current_date_str, time_opt, "")
                        
                        deep_data_res = None
                        if final_news_list:
                            deduped_news = []
                            seen_titles = []
                            for n in final_news_list:
                                if not any(difflib.SequenceMatcher(None, n.title, s).ratio() > 0.6 for s in seen_titles):
                                    deduped_news.append(n)
                                    seen_titles.append(n.title)
                            
                            if deduped_news:
                                deep_data_res = {"topic": topic_label, "data": deduped_news} 
                                
                        t_data_res = {"topic": topic_label, "events": timeline_events} if timeline_events else None
                        return index, deep_data_res, t_data_res
                    except Exception as e:
                        print(f"⚠️ Industry pipeline failed for {t.get('title', 'unknown')}: {e}")
                        return index, None, None

                results = []
                if china_mode:
                    spinner_msg = "🌪️ 中国专项探针已发射！正在聚合中文站点和中国公司情报..."
                else:
                    spinner_msg = "🌪️ 多路探针已发射！全域数据强力聚合中..."

                with st.spinner(spinner_msg):
                    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                        futures = [executor.submit(process_industry_task, t, i) for i, t in enumerate(industry_topics)]
                        for future in concurrent.futures.as_completed(futures):
                            try:
                                item = future.result()
                                if item:
                                    results.append(item)
                            except Exception as e:
                                print(f"⚠️ Industry worker crashed: {e}")

                results.sort(key=lambda x: x[0]) 
                all_deep_data = [r[1] for r in results if r[1] is not None]
                all_timeline_data = [r[2] for r in results if r[2] is not None]
                return all_deep_data, all_timeline_data

        col_global, col_cn = st.columns(2)
        with col_global:
            start_industry_btn = st.button("🚀 一键并发生成【每日宏观行业早报】", type="primary", key="btn_industry")
        with col_cn:
            start_cn_industry_btn = st.button("🇨🇳 一键并发生成【中国公司中文站点专项】", type="secondary", key="btn_industry_cn")

        if start_industry_btn and api_key and tavily_key:
            all_deep_data, all_timeline_data = run_industry_pipeline(INDUSTRY_TOPICS, search_domain, china_mode=False)
            if all_deep_data or all_timeline_data:
                st.session_state.word_path = generate_word(all_deep_data, all_timeline_data, file_name, model_id)
                st.session_state.ppt_path = generate_ppt(all_deep_data, all_timeline_data, file_name, model_id)
                st.session_state.report_ready = True
                st.rerun()

        if start_cn_industry_btn and api_key and tavily_key:
            all_deep_data, all_timeline_data = run_industry_pipeline(
                INDUSTRY_TOPICS,
                china_sites,
                china_mode=True,
                query_suffix=china_query_suffix
            )
            if all_deep_data or all_timeline_data:
                st.session_state.word_path = generate_word(all_deep_data, all_timeline_data, file_name, model_id)
                st.session_state.ppt_path = generate_ppt(all_deep_data, all_timeline_data, file_name, model_id)
                st.session_state.report_ready = True
                st.rerun()

else:
    st.balloons()
    st.success("🎉 战报圆满完成！")
    col1, col2 = st.columns(2)
    with col1:
        with open(st.session_state.word_path, "rb") as f:
            st.download_button("📝 立即下载深度研报 (Word)", f, file_name=st.session_state.word_path, type="secondary", use_container_width=True)
    with col2:
        with open(st.session_state.ppt_path, "rb") as f:
            st.download_button("📊 立即下载高管简报 (PPT)", f, file_name=st.session_state.ppt_path, type="primary", use_container_width=True)
    st.divider()
    if st.button("🔄 开启新一轮情报探索", use_container_width=True):
        st.session_state.report_ready = False
        st.session_state.word_path = ""
        st.session_state.ppt_path = ""
        st.rerun()
