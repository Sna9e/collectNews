# -*- coding: utf-8 -*-
import concurrent.futures
import datetime

import streamlit as st

from news_app.config import DEFAULT_SITES_TEXT, INDUSTRY_TOPICS, TIME_LIMIT_DICT
from news_app.core.pipeline import AI_Driver, process_company_topic, process_industry_topic
from news_app.tools.export_ppt import generate_ppt
from news_app.tools.export_word import generate_word
from news_app.tools.memory_manager import GistMemoryManager


st.set_page_config(page_title="DeepSeek 情报中心", layout="wide")

if "report_ready" not in st.session_state:
    st.session_state.report_ready = False
    st.session_state.word_path = ""
    st.session_state.ppt_path = ""


with st.sidebar:
    st.header("情报控制台")
    try:
        api_key = st.secrets["DEEPSEEK_API_KEY"]
        tavily_key = st.secrets["TAVILY_API_KEY"]
        jina_key = st.secrets.get("JINA_API_KEY", "")
        gh_token = st.secrets.get("GITHUB_TOKEN", "")
        gist_id = st.secrets.get("GIST_ID", "")
        st.success("Secrets 加载成功")
    except KeyError:
        st.error("未检测到 Secrets 配置，请检查 Streamlit Settings。")
        api_key, tavily_key, jina_key, gh_token, gist_id = "", "", "", "", ""

    st.divider()
    model_id = st.selectbox("模型", ["deepseek-chat"], index=0)
    time_label = st.selectbox("时间范围", list(TIME_LIMIT_DICT.keys()), index=0)

    with st.expander("高级搜索源设置"):
        sites = st.text_area("重点搜索源", DEFAULT_SITES_TEXT, height=250)

    file_name = st.text_input("导出文件名", f"高管战报_{datetime.date.today()}")


st.title("商业情报战情室")

if not st.session_state.report_ready:
    tab1, tab2 = st.tabs(
        [
            "频道一：公司跟踪（含金融量化）",
            "频道二：宏观行业早报（全域扫描）",
        ]
    )

    with tab1:
        st.markdown("输入追踪对象，多个目标使用 `\\` 分隔。")
        query_input = st.text_input("追踪对象", "Apple \\ Google")
        start_btn = st.button("启动并发分析", type="primary", key="btn_company")

        if start_btn and api_key and tavily_key:
            process_container = st.empty()
            with process_container.container():
                topics = [t.strip() for t in query_input.split("\\") if t.strip()]

                ai = AI_Driver(api_key, model_id)
                current_date_str = datetime.date.today().strftime("%Y-%m-%d")
                time_limit = TIME_LIMIT_DICT[time_label]

                mem_manager = GistMemoryManager(gh_token, gist_id)
                if gh_token and gist_id:
                    mem_manager.load_memory()

                st.info(f"并发处理启动中，目标数: {len(topics)}")

                results = []
                with st.spinner("并发收集与深度推演中..."):
                    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                        futures = [
                            executor.submit(
                                process_company_topic,
                                t,
                                i,
                                ai=ai,
                                sites_text=sites,
                                time_limit=time_limit,
                                time_label=time_label,
                                current_date=current_date_str,
                                tavily_key=tavily_key,
                                jina_key=jina_key,
                                mem_manager=mem_manager,
                            )
                            for i, t in enumerate(topics)
                        ]
                        for future in concurrent.futures.as_completed(futures):
                            results.append(future.result())

                results.sort(key=lambda x: x[0])
                all_deep_data = [r[1] for r in results if r[1] is not None]
                all_timeline_data = [r[2] for r in results if r[2] is not None]

                st.success("并发分析完成")
                if gh_token and gist_id:
                    mem_manager.save_memory()

            if all_deep_data or all_timeline_data:
                st.session_state.word_path = generate_word(
                    all_deep_data, all_timeline_data, file_name, model_id
                )
                st.session_state.ppt_path = generate_ppt(
                    all_deep_data, all_timeline_data, file_name, model_id
                )
                st.session_state.report_ready = True
                st.rerun()

    with tab2:
        st.markdown("宏观行业多路扫描，一键生成日报。")
        use_all_web = st.toggle("开启全网搜索", value=True)
        search_domain = "" if use_all_web else sites

        start_industry_btn = st.button("生成宏观行业日报", type="primary", key="btn_industry")

        if start_industry_btn and api_key and tavily_key:
            process_container = st.empty()
            with process_container.container():
                ai = AI_Driver(api_key, model_id)
                current_date_str = datetime.date.today().strftime("%Y-%m-%d")
                time_limit = TIME_LIMIT_DICT[time_label]

                st.info("全域扫描启动中，请稍候...")

                results = []
                with st.spinner("多路探针聚合中..."):
                    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                        futures = [
                            executor.submit(
                                process_industry_topic,
                                t,
                                i,
                                ai=ai,
                                search_domain=search_domain,
                                time_limit=time_limit,
                                time_label=time_label,
                                current_date=current_date_str,
                                tavily_key=tavily_key,
                                jina_key=jina_key,
                            )
                            for i, t in enumerate(INDUSTRY_TOPICS)
                        ]
                        for future in concurrent.futures.as_completed(futures):
                            results.append(future.result())

                results.sort(key=lambda x: x[0])
                all_deep_data = [r[1] for r in results if r[1] is not None]
                all_timeline_data = [r[2] for r in results if r[2] is not None]

            if all_deep_data or all_timeline_data:
                st.session_state.word_path = generate_word(
                    all_deep_data, all_timeline_data, file_name, model_id
                )
                st.session_state.ppt_path = generate_ppt(
                    all_deep_data, all_timeline_data, file_name, model_id
                )
                st.session_state.report_ready = True
                st.rerun()

else:
    st.success("战报生成完成")
    col1, col2 = st.columns(2)
    with col1:
        with open(st.session_state.word_path, "rb") as f:
            st.download_button(
                "下载 Word 报告",
                f,
                file_name=st.session_state.word_path,
                type="secondary",
                use_container_width=True,
            )
    with col2:
        with open(st.session_state.ppt_path, "rb") as f:
            st.download_button(
                "下载 PPT 报告",
                f,
                file_name=st.session_state.ppt_path,
                type="primary",
                use_container_width=True,
            )
    st.divider()
    if st.button("开启新一轮分析", use_container_width=True):
        st.session_state.report_ready = False
        st.session_state.word_path = ""
        st.session_state.ppt_path = ""
        st.rerun()
