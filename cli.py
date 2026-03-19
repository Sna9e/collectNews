# -*- coding: utf-8 -*-
import concurrent.futures
import datetime
import os
from typing import List, Tuple

from news_app.config import DEFAULT_SITES_TEXT, INDUSTRY_TOPICS, TIME_LIMIT_DICT
from news_app.core.pipeline import AI_Driver, process_company_topic, process_industry_topic
from news_app.tools.export_ppt import generate_ppt
from news_app.tools.export_word import generate_word
from news_app.tools.memory_manager import GistMemoryManager


def _prepare_keys_from_env() -> Tuple[str, str, str, str, str]:
    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    tavily_key = os.getenv("TAVILY_API_KEY", "")
    jina_key = os.getenv("JINA_API_KEY", "")
    gh_token = os.getenv("GITHUB_TOKEN", "")
    gist_id = os.getenv("GIST_ID", "")
    return api_key, tavily_key, jina_key, gh_token, gist_id


def run_company_mode():
    print("=== 频道一：公司跟踪（含金融量化） ===")
    api_key, tavily_key, jina_key, gh_token, gist_id = _prepare_keys_from_env()

    if not api_key:
        api_key = input("请输入 DEEPSEEK_API_KEY（留空退出）：").strip()
        if not api_key:
            print("未提供 API Key，退出。")
            return
    if not tavily_key:
        tavily_key = input("请输入 TAVILY_API_KEY（必需）：").strip()
        if not tavily_key:
            print("未提供 Tavily Key，无法搜索，退出。")
            return

    print("\n当前搜索源：")
    print(DEFAULT_SITES_TEXT)

    print("\n可选时间范围：")
    for i, k in enumerate(TIME_LIMIT_DICT.keys(), start=1):
        print(f"{i}. {k}")
    time_choice = input("请选择时间范围编号（默认 1）：").strip()
    try:
        idx = int(time_choice) - 1
        time_label = list(TIME_LIMIT_DICT.keys())[idx]
    except Exception:
        time_label = list(TIME_LIMIT_DICT.keys())[0]
    time_limit = TIME_LIMIT_DICT[time_label]

    query_input = input("请输入追踪对象（用 '\\' 分隔多个）：").strip()
    if not query_input:
        print("未输入任何对象，退出。")
        return

    topics: List[str] = [t.strip() for t in query_input.split("\\") if t.strip()]
    print(f"\n将并发分析 {len(topics)} 个对象：{topics}")

    ai = AI_Driver(api_key, "deepseek-chat")
    current_date_str = datetime.date.today().strftime("%Y-%m-%d")

    mem_manager = GistMemoryManager(gh_token, gist_id)
    if gh_token and gist_id:
        mem_manager.load_memory()

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures = [
            executor.submit(
                process_company_topic,
                t,
                i,
                ai=ai,
                sites_text=DEFAULT_SITES_TEXT,
                time_limit=time_limit,
                time_label=time_label,
                current_date=current_date_str,
                tavily_key=tavily_key,
                jina_key=jina_key,
                mem_manager=mem_manager,
                log=print,
            )
            for i, t in enumerate(topics)
        ]
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())

    results.sort(key=lambda x: x[0])
    all_deep_data = [r[1] for r in results if r[1] is not None]
    all_timeline_data = [r[2] for r in results if r[2] is not None]

    if gh_token and gist_id:
        mem_manager.save_memory()

    if not all_deep_data and not all_timeline_data:
        print("\n未生成任何有效战报数据。")
        return

    file_name = input("\n请输入导出文件名（默认 高管战报_YYYY-MM-DD）：").strip()
    if not file_name:
        file_name = f"高管战报_{datetime.date.today()}"

    word_path = generate_word(all_deep_data, all_timeline_data, file_name, "deepseek-chat")
    ppt_path = generate_ppt(all_deep_data, all_timeline_data, file_name, "deepseek-chat")

    print("\n并发分析完成")
    print(f"Word 路径：{os.path.abspath(word_path)}")
    print(f"PPT 路径：{os.path.abspath(ppt_path)}")


def run_industry_mode():
    print("=== 频道二：宏观行业早报 ===")
    api_key, tavily_key, jina_key, gh_token, gist_id = _prepare_keys_from_env()

    if not api_key:
        api_key = input("请输入 DEEPSEEK_API_KEY（留空退出）：").strip()
        if not api_key:
            print("未提供 API Key，退出。")
            return
    if not tavily_key:
        tavily_key = input("请输入 TAVILY_API_KEY（必需）：").strip()
        if not tavily_key:
            print("未提供 Tavily Key，无法搜索，退出。")
            return

    use_all_web = input("是否开启全网搜索？(y/N)：").strip().lower() == "y"
    search_domain = "" if use_all_web else DEFAULT_SITES_TEXT

    print("\n可选时间范围：")
    for i, k in enumerate(TIME_LIMIT_DICT.keys(), start=1):
        print(f"{i}. {k}")
    time_choice = input("请选择时间范围编号（默认 1）：").strip()
    try:
        idx = int(time_choice) - 1
        time_label = list(TIME_LIMIT_DICT.keys())[idx]
    except Exception:
        time_label = list(TIME_LIMIT_DICT.keys())[0]
    time_limit = TIME_LIMIT_DICT[time_label]

    ai = AI_Driver(api_key, "deepseek-chat")
    current_date_str = datetime.date.today().strftime("%Y-%m-%d")

    print("\n本次将分析以下主题：")
    for t in INDUSTRY_TOPICS:
        print(f"- {t['title']}：{t['desc']}")

    results = []
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
                log=print,
            )
            for i, t in enumerate(INDUSTRY_TOPICS)
        ]
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())

    results.sort(key=lambda x: x[0])
    all_deep_data = [r[1] for r in results if r[1] is not None]
    all_timeline_data = [r[2] for r in results if r[2] is not None]

    if not all_deep_data and not all_timeline_data:
        print("\n未生成任何有效战报数据。")
        return

    file_name = input("\n请输入导出文件名（默认 宏观行业早报_YYYY-MM-DD）：").strip()
    if not file_name:
        file_name = f"宏观行业早报_{datetime.date.today()}"

    word_path = generate_word(all_deep_data, all_timeline_data, file_name, "deepseek-chat")
    ppt_path = generate_ppt(all_deep_data, all_timeline_data, file_name, "deepseek-chat")

    print("\n行业早报生成完成")
    print(f"Word 路径：{os.path.abspath(word_path)}")
    print(f"PPT 路径：{os.path.abspath(ppt_path)}")


def main():
    print("====== 部门情报中心 · 命令行版 ======")
    print("1. 公司跟踪（含金融量化）")
    print("2. 宏观行业早报")
    choice = input("请选择模式（1/2，其它退出）：").strip()
    if choice == "1":
        run_company_mode()
    elif choice == "2":
        run_industry_mode()
    else:
        print("已退出。")


if __name__ == "__main__":
    main()
