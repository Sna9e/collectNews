# -*- coding: utf-8 -*-
import argparse
import datetime
import json
import os
import traceback
from typing import List

from news_app.config import DEFAULT_SITES_TEXT, INDUSTRY_TOPICS, TIME_LIMIT_DICT
from news_app.core.pipeline import AI_Driver, process_company_topic, process_industry_topic
from news_app.tools.export_ppt import generate_ppt
from news_app.tools.export_word import generate_word
from news_app.tools.memory_manager import GistMemoryManager

INVALID_FILENAME_CHARS = '<>:"/\\|?*'


def _safe_filename(name: str) -> str:
    if not name:
        return "report"
    cleaned = "".join("_" if ch in INVALID_FILENAME_CHARS else ch for ch in name)
    cleaned = cleaned.strip().strip(".")
    return cleaned[:80] or "report"


def _load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_result(path: str, payload: dict):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def _get_env_keys():
    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    tavily_key = os.getenv("TAVILY_API_KEY", "")
    jina_key = os.getenv("JINA_API_KEY", "")
    gh_token = os.getenv("GITHUB_TOKEN", "")
    gist_id = os.getenv("GIST_ID", "")
    return api_key, tavily_key, jina_key, gh_token, gist_id


def _run_company(cfg: dict) -> dict:
    api_key, tavily_key, jina_key, gh_token, gist_id = _get_env_keys()
    if not api_key or not tavily_key:
        return {"status": "error", "errors": ["缺少 API Key（DEEPSEEK / TAVILY）"]}

    topics: List[str] = cfg.get("topics", [])
    if not topics:
        return {"status": "error", "errors": ["未提供追踪对象"]}

    model_id = cfg.get("model_id", "deepseek-chat")
    time_label = cfg.get("time_label", list(TIME_LIMIT_DICT.keys())[0])
    if time_label not in TIME_LIMIT_DICT:
        time_label = list(TIME_LIMIT_DICT.keys())[0]
    time_limit = TIME_LIMIT_DICT[time_label]

    sites = cfg.get("sites") or DEFAULT_SITES_TEXT
    safe_mode = bool(cfg.get("safe_mode", True))
    max_workers = 1 if safe_mode else int(cfg.get("max_workers", 1))
    enable_finance = False if safe_mode else bool(cfg.get("enable_finance", False))
    enable_word = bool(cfg.get("enable_word", True))
    enable_ppt = bool(cfg.get("enable_ppt", True))
    file_name = _safe_filename(cfg.get("file_name", f"高管战报_{datetime.date.today()}"))

    ai = AI_Driver(api_key, model_id)
    current_date_str = datetime.date.today().strftime("%Y-%m-%d")

    mem_manager = GistMemoryManager(gh_token, gist_id)
    if gh_token and gist_id:
        mem_manager.load_memory()

    results = []
    errors = []

    if max_workers <= 1:
        for i, t in enumerate(topics):
            try:
                results.append(
                    process_company_topic(
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
                )
            except Exception as e:
                errors.append(str(e))
    else:
        import concurrent.futures

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

    word_path = ""
    ppt_path = ""
    if all_deep_data or all_timeline_data:
        if enable_word:
            try:
                word_path = generate_word(all_deep_data, all_timeline_data, file_name, model_id)
            except Exception as e:
                errors.append(f"Word 生成失败: {e}")
        if enable_ppt:
            try:
                ppt_path = generate_ppt(all_deep_data, all_timeline_data, file_name, model_id)
            except Exception as e:
                errors.append(f"PPT 生成失败: {e}")

    status = "done"
    if not all_deep_data and not all_timeline_data:
        status = "empty"

    return {
        "status": status,
        "word_path": word_path,
        "ppt_path": ppt_path,
        "errors": errors,
        "stats": {
            "topics": len(topics),
            "deep": len(all_deep_data),
            "timeline": len(all_timeline_data),
        },
    }


def _run_industry(cfg: dict) -> dict:
    api_key, tavily_key, jina_key, _, _ = _get_env_keys()
    if not api_key or not tavily_key:
        return {"status": "error", "errors": ["缺少 API Key（DEEPSEEK / TAVILY）"]}

    model_id = cfg.get("model_id", "deepseek-chat")
    time_label = cfg.get("time_label", list(TIME_LIMIT_DICT.keys())[0])
    if time_label not in TIME_LIMIT_DICT:
        time_label = list(TIME_LIMIT_DICT.keys())[0]
    time_limit = TIME_LIMIT_DICT[time_label]

    sites = cfg.get("sites") or DEFAULT_SITES_TEXT
    use_all_web = bool(cfg.get("use_all_web", True))
    search_domain = "" if use_all_web else sites
    safe_mode = bool(cfg.get("safe_mode", True))
    max_workers = 1 if safe_mode else int(cfg.get("max_workers", 1))
    enable_word = bool(cfg.get("enable_word", True))
    enable_ppt = bool(cfg.get("enable_ppt", True))
    file_name = _safe_filename(cfg.get("file_name", f"宏观行业早报_{datetime.date.today()}"))

    ai = AI_Driver(api_key, model_id)
    current_date_str = datetime.date.today().strftime("%Y-%m-%d")

    results = []
    errors = []

    if max_workers <= 1:
        for i, t in enumerate(INDUSTRY_TOPICS):
            try:
                results.append(
                    process_industry_topic(
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
                )
            except Exception as e:
                errors.append(str(e))
    else:
        import concurrent.futures

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

    word_path = ""
    ppt_path = ""
    if all_deep_data or all_timeline_data:
        if enable_word:
            try:
                word_path = generate_word(all_deep_data, all_timeline_data, file_name, model_id)
            except Exception as e:
                errors.append(f"Word 生成失败: {e}")
        if enable_ppt:
            try:
                ppt_path = generate_ppt(all_deep_data, all_timeline_data, file_name, model_id)
            except Exception as e:
                errors.append(f"PPT 生成失败: {e}")

    status = "done"
    if not all_deep_data and not all_timeline_data:
        status = "empty"

    return {
        "status": status,
        "word_path": word_path,
        "ppt_path": ppt_path,
        "errors": errors,
        "stats": {
            "topics": len(INDUSTRY_TOPICS),
            "deep": len(all_deep_data),
            "timeline": len(all_timeline_data),
        },
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--result", required=True)
    args = parser.parse_args()

    try:
        cfg = _load_config(args.config)
        mode = cfg.get("mode")
        if mode == "company":
            result = _run_company(cfg)
        elif mode == "industry":
            result = _run_industry(cfg)
        else:
            result = {"status": "error", "errors": ["未知模式"]}
    except Exception as e:
        result = {
            "status": "error",
            "errors": [str(e)],
            "traceback": "".join(traceback.format_exception(type(e), e, e.__traceback__)),
        }

    _write_result(args.result, result)


if __name__ == "__main__":
    main()
