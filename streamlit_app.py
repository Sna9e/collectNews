# -*- coding: utf-8 -*-
import concurrent.futures
import datetime
import os
import traceback

import streamlit as st

from news_app.config import DEFAULT_SITES_TEXT, INDUSTRY_TOPICS, TIME_LIMIT_DICT
from news_app.core.pipeline import AI_Driver, process_company_topic, process_industry_topic
from news_app.tools.export_ppt import generate_ppt
from news_app.tools.export_word import generate_word
from news_app.tools.memory_manager import GistMemoryManager

PAGE_TITLE = "DeepSeek 情报中心"
DEFAULT_MODEL = "deepseek-chat"
INVALID_FILENAME_CHARS = '<>:"/\\|?*'


def _init_state():
    if "run_status" not in st.session_state:
        st.session_state.run_status = "idle"
    if "run_mode" not in st.session_state:
        st.session_state.run_mode = ""
    if "word_path" not in st.session_state:
        st.session_state.word_path = ""
    if "ppt_path" not in st.session_state:
        st.session_state.ppt_path = ""
    if "last_error" not in st.session_state:
        st.session_state.last_error = ""
    if "errors" not in st.session_state:
        st.session_state.errors = []
    if "last_started_at" not in st.session_state:
        st.session_state.last_started_at = ""
    if "last_finished_at" not in st.session_state:
        st.session_state.last_finished_at = ""
    if "last_stats" not in st.session_state:
        st.session_state.last_stats = {}


def _reset_state():
    st.session_state.run_status = "idle"
    st.session_state.run_mode = ""
    st.session_state.word_path = ""
    st.session_state.ppt_path = ""
    st.session_state.last_error = ""
    st.session_state.errors = []
    st.session_state.last_started_at = ""
    st.session_state.last_finished_at = ""
    st.session_state.last_stats = {}


def _safe_filename(name: str) -> str:
    if not name:
        return "report"
    cleaned = "".join("_" if ch in INVALID_FILENAME_CHARS else ch for ch in name)
    cleaned = cleaned.strip().strip(".")
    return cleaned[:80] or "report"


def _get_keys():
    api_key = st.secrets.get("DEEPSEEK_API_KEY", os.getenv("DEEPSEEK_API_KEY", ""))
    tavily_key = st.secrets.get("TAVILY_API_KEY", os.getenv("TAVILY_API_KEY", ""))
    jina_key = st.secrets.get("JINA_API_KEY", os.getenv("JINA_API_KEY", ""))
    gh_token = st.secrets.get("GITHUB_TOKEN", os.getenv("GITHUB_TOKEN", ""))
    gist_id = st.secrets.get("GIST_ID", os.getenv("GIST_ID", ""))
    return api_key, tavily_key, jina_key, gh_token, gist_id


def _start_run(mode: str):
    _reset_state()
    st.session_state.run_status = "running"
    st.session_state.run_mode = mode
    st.session_state.last_started_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _finish_run(status: str):
    st.session_state.run_status = status
    st.session_state.last_finished_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _update_status(status_obj, label, state=None, expanded=None):
    if not status_obj:
        return
    kwargs = {"label": label}
    if state:
        kwargs["state"] = state
    if expanded is not None:
        kwargs["expanded"] = expanded
    status_obj.update(**kwargs)


def _render_download(label, path, button_type):
    if not path:
        return False
    if not os.path.exists(path):
        st.warning(f"{label}文件不存在：{path}")
        return False
    with open(path, "rb") as f:
        st.download_button(
            label,
            data=f,
            file_name=os.path.basename(path),
            type=button_type,
            use_container_width=True,
        )
    return True


def _run_company(
    topics,
    *,
    api_key,
    tavily_key,
    jina_key,
    gh_token,
    gist_id,
    model_id,
    sites,
    time_label,
    file_name,
    max_workers,
    enable_finance,
    enable_word,
    enable_ppt,
):
    _start_run("company")
    status = st.status("任务启动中...", expanded=True) if hasattr(st, "status") else None

    try:
        ai = AI_Driver(api_key, model_id)
        current_date_str = datetime.date.today().strftime("%Y-%m-%d")
        time_limit = TIME_LIMIT_DICT[time_label]

        mem_manager = GistMemoryManager(gh_token, gist_id)
        if gh_token and gist_id:
            mem_manager.load_memory()

        _update_status(status, f"并发处理启动中，目标数: {len(topics)}")

        results = []
        errors = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
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
                    enable_finance=enable_finance,
                )
                for i, t in enumerate(topics)
            ]
            for future in concurrent.futures.as_completed(futures):
                try:
                    results.append(future.result())
                except Exception as e:
                    errors.append(str(e))

        results.sort(key=lambda x: x[0])
        all_deep_data = [r[1] for r in results if r[1] is not None]
        all_timeline_data = [r[2] for r in results if r[2] is not None]

        if gh_token and gist_id:
            mem_manager.save_memory()

        st.session_state.errors = errors
        st.session_state.last_stats = {
            "topics": len(topics),
            "deep": len(all_deep_data),
            "timeline": len(all_timeline_data),
        }

        if not all_deep_data and not all_timeline_data:
            _update_status(status, "未生成任何有效结果", state="warning", expanded=True)
            _finish_run("done")
            return

        safe_name = _safe_filename(file_name)
        if enable_word:
            try:
                st.session_state.word_path = generate_word(
                    all_deep_data, all_timeline_data, safe_name, model_id
                )
            except Exception as e:
                errors.append(f"Word 生成失败: {e}")
        if enable_ppt:
            try:
                st.session_state.ppt_path = generate_ppt(
                    all_deep_data, all_timeline_data, safe_name, model_id
                )
            except Exception as e:
                errors.append(f"PPT 生成失败: {e}")

        st.session_state.errors = errors
        _update_status(status, "并发分析完成", state="complete", expanded=False)
        _finish_run("done")
    except Exception as e:
        st.session_state.last_error = "".join(
            traceback.format_exception(type(e), e, e.__traceback__)
        )
        _update_status(status, "执行失败", state="error", expanded=True)
        _finish_run("error")
        st.exception(e)


def _run_industry(
    *,
    api_key,
    tavily_key,
    jina_key,
    model_id,
    search_domain,
    time_label,
    file_name,
    max_workers,
    enable_word,
    enable_ppt,
):
    _start_run("industry")
    status = st.status("任务启动中...", expanded=True) if hasattr(st, "status") else None

    try:
        ai = AI_Driver(api_key, model_id)
        current_date_str = datetime.date.today().strftime("%Y-%m-%d")
        time_limit = TIME_LIMIT_DICT[time_label]

        _update_status(status, "全域扫描启动中，请稍候...")

        results = []
        errors = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
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
                try:
                    results.append(future.result())
                except Exception as e:
                    errors.append(str(e))

        results.sort(key=lambda x: x[0])
        all_deep_data = [r[1] for r in results if r[1] is not None]
        all_timeline_data = [r[2] for r in results if r[2] is not None]

        st.session_state.errors = errors
        st.session_state.last_stats = {
            "topics": len(INDUSTRY_TOPICS),
            "deep": len(all_deep_data),
            "timeline": len(all_timeline_data),
        }

        if not all_deep_data and not all_timeline_data:
            _update_status(status, "未生成任何有效结果", state="warning", expanded=True)
            _finish_run("done")
            return

        safe_name = _safe_filename(file_name)
        if enable_word:
            try:
                st.session_state.word_path = generate_word(
                    all_deep_data, all_timeline_data, safe_name, model_id
                )
            except Exception as e:
                errors.append(f"Word 生成失败: {e}")
        if enable_ppt:
            try:
                st.session_state.ppt_path = generate_ppt(
                    all_deep_data, all_timeline_data, safe_name, model_id
                )
            except Exception as e:
                errors.append(f"PPT 生成失败: {e}")

        st.session_state.errors = errors
        _update_status(status, "行业早报生成完成", state="complete", expanded=False)
        _finish_run("done")
    except Exception as e:
        st.session_state.last_error = "".join(
            traceback.format_exception(type(e), e, e.__traceback__)
        )
        _update_status(status, "执行失败", state="error", expanded=True)
        _finish_run("error")
        st.exception(e)


def _render_summary_panel():
    status_map = {
        "idle": "待机",
        "running": "运行中",
        "done": "完成",
        "error": "失败",
    }
    status_label = status_map.get(st.session_state.run_status, "未知")

    col1, col2, col3 = st.columns(3)
    col1.metric("当前状态", status_label)
    col2.metric("上次开始", st.session_state.last_started_at or "-")
    col3.metric("上次结束", st.session_state.last_finished_at or "-")

    if st.session_state.last_stats:
        st.caption(
            f"目标数: {st.session_state.last_stats.get('topics', 0)} | "
            f"深度数据: {st.session_state.last_stats.get('deep', 0)} | "
            f"时间线: {st.session_state.last_stats.get('timeline', 0)}"
        )


def _render_results_panel():
    if st.session_state.run_status == "idle":
        return

    st.divider()
    if st.session_state.run_status == "running":
        st.info("任务正在执行，请勿刷新页面。")
        return

    if st.session_state.run_status == "error":
        st.error("执行失败，请查看侧边栏诊断信息。")
        return

    st.success("战报生成完成")

    if st.session_state.errors:
        with st.expander(f"子任务错误（{len(st.session_state.errors)}）"):
            for err in st.session_state.errors:
                st.write(f"- {err}")

    col1, col2 = st.columns(2)
    with col1:
        _render_download("下载 Word 报告", st.session_state.word_path, "secondary")
    with col2:
        _render_download("下载 PPT 报告", st.session_state.ppt_path, "primary")

    if st.button("开启新一轮分析", use_container_width=True):
        _reset_state()


st.set_page_config(page_title=PAGE_TITLE, layout="wide")
_init_state()

with st.sidebar:
    st.header("情报控制台")

    api_key, tavily_key, jina_key, gh_token, gist_id = _get_keys()
    key_ready = bool(api_key and tavily_key)

    if key_ready:
        st.success("API 配置已就绪")
    else:
        st.warning("缺少 API Key（DEEPSEEK / TAVILY）")

    st.divider()
    model_id = st.selectbox("模型", [DEFAULT_MODEL], index=0)
    time_label = st.selectbox("时间范围", list(TIME_LIMIT_DICT.keys()), index=0)

    with st.expander("高级搜索源设置"):
        sites = st.text_area("重点搜索源", DEFAULT_SITES_TEXT, height=220)

    file_name = st.text_input("导出文件名", f"高管战报_{datetime.date.today()}")

    st.divider()
    with st.expander("运行参数", expanded=False):
        safe_mode = st.toggle("安全模式（单线程/禁用金融量化）", value=False)
        max_workers = st.slider("并发度", 1, 4, 3, disabled=safe_mode)
        enable_finance = st.toggle("启用金融量化", value=True, disabled=safe_mode)
        enable_word = st.toggle("导出 Word", value=True)
        enable_ppt = st.toggle("导出 PPT", value=True)

    if safe_mode:
        max_workers = 1
        enable_finance = False

    with st.expander("诊断信息"):
        if st.session_state.last_error:
            st.code(st.session_state.last_error)
        elif st.session_state.errors:
            st.write(f"子任务错误数: {len(st.session_state.errors)}")
        else:
            st.write("暂无错误记录")

st.title("商业情报战情室")
st.caption("企业追踪与宏观行业日报，统一入口与可追溯导出。")

_render_summary_panel()

tab1, tab2 = st.tabs(
    [
        "频道一：公司跟踪（含金融量化）",
        "频道二：宏观行业早报（全域扫描）",
    ]
)

with tab1:
    st.markdown("输入追踪对象，多个目标使用 `\\` 分隔。")
    with st.form("company_form"):
        query_input = st.text_input("追踪对象", "Apple \\ Google")
        start_btn = st.form_submit_button(
            "启动并发分析",
            type="primary",
            disabled=not key_ready,
        )

    if start_btn:
        topics = [t.strip() for t in query_input.split("\\") if t.strip()]
        if not topics:
            st.warning("请至少输入一个追踪对象。")
        else:
            _run_company(
                topics,
                api_key=api_key,
                tavily_key=tavily_key,
                jina_key=jina_key,
                gh_token=gh_token,
                gist_id=gist_id,
                model_id=model_id,
                sites=sites,
                time_label=time_label,
                file_name=file_name,
                max_workers=max_workers,
                enable_finance=enable_finance,
                enable_word=enable_word,
                enable_ppt=enable_ppt,
            )

with tab2:
    st.markdown("宏观行业多路扫描，一键生成日报。")
    with st.form("industry_form"):
        use_all_web = st.toggle("开启全网搜索", value=True)
        start_industry_btn = st.form_submit_button(
            "生成宏观行业日报",
            type="primary",
            disabled=not key_ready,
        )

    if start_industry_btn:
        search_domain = "" if use_all_web else sites
        _run_industry(
            api_key=api_key,
            tavily_key=tavily_key,
            jina_key=jina_key,
            model_id=model_id,
            search_domain=search_domain,
            time_label=time_label,
            file_name=file_name,
            max_workers=max_workers,
            enable_word=enable_word,
            enable_ppt=enable_ppt,
        )

_render_results_panel()
