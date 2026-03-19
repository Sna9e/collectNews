# -*- coding: utf-8 -*-
import json
import urllib.request
import concurrent.futures
from typing import List, Tuple


def search_web(query, sites_text, timelimit, max_results=20, tavily_key=""):
    if not tavily_key:
        return []
    sites_text = sites_text or ""
    sites = [s.strip() for s in sites_text.splitlines() if s.strip()]
    try:
        url = "https://api.tavily.com/search"
        payload = {
            "api_key": tavily_key,
            "query": query,
            "search_depth": "advanced",
            "topic": "news",
            "max_results": max_results,
        }
        if sites:
            payload["include_domains"] = sites
        if timelimit == "d":
            payload["days"] = 2
        elif timelimit == "w":
            payload["days"] = 7
        elif timelimit == "m":
            payload["days"] = 30

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        resp = json.loads(urllib.request.urlopen(req, timeout=15).read().decode("utf-8"))
        return resp.get("results", [])
    except Exception as e:
        print(f"[tavily] search failed: {e}")
        return []


def fetch_single_url_with_jina(url, jina_key=""):
    jina_url = f"https://r.jina.ai/{url}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    if jina_key:
        headers["Authorization"] = f"Bearer {jina_key}"

    try:
        req = urllib.request.Request(jina_url, headers=headers)
        response = urllib.request.urlopen(req, timeout=15).read().decode("utf-8")
        if response and len(response) > 200:
            return f"\n\n=== SOURCE START: {url} ===\n{response[:6000]}\n=== SOURCE END ===\n"
    except Exception:
        pass
    return ""


def safe_run_async_crawler(urls: List[str], jina_key="") -> Tuple[str, int]:
    contents: List[str] = []
    valid_count = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        future_to_url = {executor.submit(fetch_single_url_with_jina, url, jina_key): url for url in urls}
        for future in concurrent.futures.as_completed(future_to_url):
            try:
                res = future.result()
            except Exception:
                continue
            if res:
                contents.append(res)
                valid_count += 1
    return "".join(contents), valid_count
