# -*- coding: utf-8 -*-
import datetime
import json
import os
import subprocess
import sys
import tempfile
import traceback
import uuid
from pathlib import Path

import streamlit as st

from news_app.config import DEFAULT_SITES_TEXT, INDUSTRY_TOPICS, TIME_LIMIT_DICT

PAGE_TITLE = "DeepSeek 情报中心"
DEFAULT_MODEL = "deepseek-chat"
JOB_BASE_DIR = Path(tempfile.gettempdir()) / "deepseek_jobs"
LATEST_JOB_FILE = JOB_BASE_DIR / "latest_job.json"
INVALID_FILENAME_CHARS = '<>:"/\\|?*'
STALE_SECONDS = 60 * 60 * 2


def _init_state():
    if "job_status" not in st.session_state:
        st.session_state.job_status = "idle"
    if "job_mode" not in st.session_state:
        st.session_state.job_mode = ""
    if "job_dir" not in st.session_state:
        st.session_state.job_dir = ""
    if "job_log" not in st.session_state:
        st.session_state.job_log = ""
    if "job_result" not in st.session_state:
        st.session_state.job_result = ""
    if "job_started_at" not in st.session_state:
        st.session_state.job_started_at = ""
    if "last_result" not in st.session_state:
        st.session_state.last_result = {}
    if "last_error" not in st.session_state:
        st.session_state.last_error = ""


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


def _write_json(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _tail_lines(path: Path, max_lines: int = 120) -> str:
    if not path.exists():
        return ""
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        return "".join(lines[-max_lines:])
    except Exception:
        return ""


def _load_latest_job():
    if st.session_state.job_dir:
        return
    info = _read_json(LATEST_JOB_FILE)
    if not info:
        return
    job_dir = info.get("job_dir", "")
    if not job_dir:
        return
    st.session_state.job_dir = job_dir
    st.session_state.job_log = info.get("job_log", "")
    st.session_state.job_result = info.get("job_result", "")
    st.session_state.job_mode = info.get("job_mode", "")
    st.session_state.job_started_at = info.get("job_started_at", "")


def _check_job():
    if not st.session_state.job_dir:
        return
    result_path = Path(st.session_state.job_result)
    if result_path.exists():
        st.session_state.last_result = _read_json(result_path)
        st.session_state.job_status = st.session_state.last_result.get("status", "done")
        return

    if st.session_state.job_status in ("running", "idle"):
        started_at = st.session_state.job_started_at
        if started_at:
            try:
                started = datetime.datetime.strptime(started_at, "%Y-%m-%d %H:%M:%S")
                if (datetime.datetime.now() - started).total_seconds() > STALE_SECONDS:
                    st.session_state.job_status = "error"
                    st.session_state.last_error = "任务超时未完成，请查看日志或重试。"
            except Exception:
                pass


def _start_job(mode: str, payload: dict, env: dict):
    job_id = uuid.uuid4().hex
    job_dir = JOB_BASE_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    config_path = job_dir / "config.json"
    result_path = job_dir / "result.json"
    log_path = job_dir / "run.log"

    _write_json(config_path, payload)

    cmd = [
        sys.executable,
        "-m",
        "news_app.tools.job_worker",
        "--config",
        str(config_path),
        "--result",
        str(result_path),
    ]

    with open(log_path, "w", encoding="utf-8") as log_file:
        subprocess.Popen(
            cmd,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            env=env,
            cwd=str(Path(__file__).resolve().parent),
        )

    st.session_state.job_status = "running"
    st.session_state.job_mode = mode
    st.session_state.job_dir = str(job_dir)
    st.session_state.job_log = str(log_path)
    st.session_state.job_result = str(result_path)
    st.session_state.job_started_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    st.session_state.last_result = {}
    st.session_state.last_error = ""

    _write_json(
        LATEST_JOB_FILE,
        {
            "job_dir": st.session_state.job_dir,
            "job_log": st.session_state.job_log,
            "job_result": st.session_state.job_result,
            "job_mode": st.session_state.job_mode,
            "job_started_at": st.session_state.job_started_at,
        },
    )


def _reset_job_state():
    st.session_state.job_status = "idle"
    st.session_state.job_mode = ""
    st.session_state.job_dir = ""
    st.session_state.job_log = ""
    st.session_state.job_result = ""
    st.session_state.job_started_at = ""
    st.session_state.last_result = {}
    st.session_state.last_error = ""


def _render_status_panel():
    status_map = {
        "idle": "待机",
        "running": "运行中",
        "done": "完成",
        "error": "失败",
        "empty": "无结果",
    }
    st.subheader("运行状态")
    st.write(f"当前状态：{status_map.get(st.session_state.job_status, '未知')}")
    if st.session_state.job_started_at:
        st.caption(f"开始时间：{st.session_state.job_started_at}")
    if st.session_state.job_dir:
        st.caption(f"任务目录：{st.session_state.job_dir}")


def _render_result_panel():
    if st.session_state.job_status in ("idle", "running"):
        return

    result = st.session_state.last_result or {}
    if st.session_state.job_status == "error":
        st.error("任务执行失败")
        if st.session_state.last_error:
            st.code(st.session_state.last_error)
        if result.get("traceback"):
            st.code(result.get("traceback"))
        return

    if st.session_state.job_status == "empty":
        st.warning("任务完成，但没有生成任何有效结果。")

    if result.get("errors"):
        with st.expander(f"子任务错误（{len(result.get('errors', []))}）"):
            for err in result.get("errors", []):
                st.write(f"- {err}")

    col1, col2 = st.columns(2)
    with col1:
        word_path = result.get("word_path", "")
        if word_path and os.path.exists(word_path):
            with open(word_path, "rb") as f:
                st.download_button(
                    "下载 Word 报告",
                    data=f,
                    file_name=os.path.basename(word_path),
                    type="secondary",
                    use_container_width=True,
                )
    with col2:
        ppt_path = result.get("ppt_path", "")
        if ppt_path and os.path.exists(ppt_path):
            with open(ppt_path, "rb") as f:
                st.download_button(
                    "下载 PPT 报告",
                    data=f,
                    file_name=os.path.basename(ppt_path),
                    type="primary",
                    use_container_width=True,
                )


def _render_app():
    st.set_page_config(page_title=PAGE_TITLE, layout="wide")
    _init_state()
    _load_latest_job()
    _check_job()

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
        file_name = st.text_input("导出文件名", f"高管战报_{datetime.date.today()}")

        with st.expander("高级搜索源设置"):
            sites = st.text_area("重点搜索源", DEFAULT_SITES_TEXT, height=180)

        st.divider()
        safe_mode = st.toggle("安全模式（推荐）", value=True)
        enable_finance = st.toggle("启用金融量化", value=False, disabled=safe_mode)
        enable_word = st.toggle("导出 Word", value=True)
        enable_ppt = st.toggle("导出 PPT", value=True)
        max_workers = 1 if safe_mode else st.slider("并发度", 1, 4, 2)

        if st.button("刷新任务状态"):
            if hasattr(st, "rerun"):
                st.rerun()
            else:
                st.experimental_rerun()

        if st.button("清理任务状态"):
            _reset_job_state()

        if st.session_state.job_log and Path(st.session_state.job_log).exists():
            with st.expander("最近日志"):
                st.code(_tail_lines(Path(st.session_state.job_log)))

    st.title("商业情报战情室")
    st.caption("前端只负责触发任务，核心逻辑在独立子进程中运行，避免前端崩溃。")

    _render_status_panel()

    mode = st.radio("选择模式", ["公司跟踪（含金融量化）", "宏观行业早报（全域扫描）"])

    if mode.startswith("公司"):
        st.markdown("输入追踪对象，多个目标使用 `\\` 或换行分隔。")
        query_input = st.text_area("追踪对象", "Apple \\ Google", height=120)
        start_btn = st.button("启动并发分析", type="primary", disabled=not key_ready)
        if start_btn:
            if st.session_state.job_status == "running":
                st.warning("当前有任务正在运行，请先等待完成或清理状态。")
            else:
                topics = []
                for line in query_input.splitlines():
                    topics.extend([t.strip() for t in line.split("\\") if t.strip()])
                topics = [t for t in topics if t]
                if not topics:
                    st.warning("请至少输入一个追踪对象。")
                else:
                    payload = {
                        "mode": "company",
                        "topics": topics,
                        "time_label": time_label,
                        "sites": sites,
                        "file_name": _safe_filename(file_name),
                        "model_id": model_id,
                        "max_workers": max_workers,
                        "enable_finance": enable_finance,
                        "enable_word": enable_word,
                        "enable_ppt": enable_ppt,
                        "safe_mode": safe_mode,
                    }
                    env = os.environ.copy()
                    env["DEEPSEEK_API_KEY"] = api_key
                    env["TAVILY_API_KEY"] = tavily_key
                    env["JINA_API_KEY"] = jina_key
                    env["GITHUB_TOKEN"] = gh_token
                    env["GIST_ID"] = gist_id
                    try:
                        _start_job("company", payload, env)
                        st.success("任务已启动，请点击“刷新任务状态”查看进度。")
                    except Exception as e:
                        st.session_state.job_status = "error"
                        st.session_state.last_error = "".join(
                            traceback.format_exception(type(e), e, e.__traceback__)
                        )
                        st.error("任务启动失败，请查看错误信息。")

    else:
        st.markdown("宏观行业多路扫描，一键生成日报。")
        use_all_web = st.toggle("开启全网搜索", value=True)
        with st.expander("本次扫描主题预览"):
            for t in INDUSTRY_TOPICS:
                st.write(f"- {t['title']}：{t['desc']}")
        start_btn = st.button("生成宏观行业日报", type="primary", disabled=not key_ready)
        if start_btn:
            if st.session_state.job_status == "running":
                st.warning("当前有任务正在运行，请先等待完成或清理状态。")
            else:
                payload = {
                    "mode": "industry",
                    "use_all_web": use_all_web,
                    "time_label": time_label,
                    "sites": sites,
                    "file_name": _safe_filename(file_name),
                    "model_id": model_id,
                    "max_workers": max_workers,
                    "enable_word": enable_word,
                    "enable_ppt": enable_ppt,
                    "safe_mode": safe_mode,
                }
                env = os.environ.copy()
                env["DEEPSEEK_API_KEY"] = api_key
                env["TAVILY_API_KEY"] = tavily_key
                env["JINA_API_KEY"] = jina_key
                env["GITHUB_TOKEN"] = gh_token
                env["GIST_ID"] = gist_id
                try:
                    _start_job("industry", payload, env)
                    st.success("任务已启动，请点击“刷新任务状态”查看进度。")
                except Exception as e:
                    st.session_state.job_status = "error"
                    st.session_state.last_error = "".join(
                        traceback.format_exception(type(e), e, e.__traceback__)
                    )
                    st.error("任务启动失败，请查看错误信息。")

    _render_result_panel()


try:
    _render_app()
except Exception as e:
    st.error("应用运行异常，请查看错误信息。")
    st.code("".join(traceback.format_exception(type(e), e, e.__traceback__)))
