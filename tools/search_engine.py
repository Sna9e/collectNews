import concurrent.futures
import datetime
import html
import json
import re
import urllib.parse
import urllib.request

CN_DOMAIN_PRESET = [
    "36kr.com",
    "ithome.com",
    "huxiu.com",
    "geekpark.net",
    "leiphone.com",
    "tmtpost.com",
    "jiqizhixin.com",
    "qbitai.com",
    "pedaily.cn",
    "cyzone.cn",
    "iyiou.com",
    "donews.com",
    "sina.com.cn",
    "sohu.com",
    "163.com",
    "qq.com",
    "xinhua.net",
    "people.com.cn",
    "cnstock.com",
    "stcn.com",
    "eastmoney.com",
]

_SCRIPT_RE = re.compile(r"<script.*?>.*?</script>", re.IGNORECASE | re.DOTALL)
_STYLE_RE = re.compile(r"<style.*?>.*?</style>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_WHITESPACE_RE = re.compile(r"\s+")
_DATE_KEY_CANDIDATES = ("published_date", "published", "date", "publishedAt", "pub_date")



def parse_sites_text(sites_text):
    if not sites_text:
        return []

    raw_tokens = re.split(r"[\n,; ]+", sites_text.strip())
    domains = []
    seen = set()
    for token in raw_tokens:
        item = token.strip()
        if not item:
            continue
        if "://" in item:
            item = urllib.parse.urlparse(item).netloc or item
        item = item.split("/")[0].strip().lower()
        if item.startswith("www."):
            item = item[4:]
        if item and item not in seen:
            domains.append(item)
            seen.add(item)
    return domains



def merge_sites_text(base_sites_text, extra_domains):
    merged = []
    seen = set()
    for domain in parse_sites_text(base_sites_text) + list(extra_domains or []):
        item = (domain or "").strip().lower()
        if not item or item in seen:
            continue
        merged.append(item)
        seen.add(item)
    return "\n".join(merged)



def _extract_host(url):
    if not url:
        return ""
    try:
        parsed = urllib.parse.urlparse(url)
        host = (parsed.netloc or "").lower()
        if host.startswith("www."):
            host = host[4:]
        return host
    except Exception:
        return ""



def _domain_in_allowlist(host, allowlist):
    if not host:
        return False
    return any(host == domain or host.endswith(f".{domain}") for domain in allowlist)



def contains_chinese_text(text):
    if not text:
        return False
    return bool(re.search(r"[\u4e00-\u9fff]", text))



def filter_china_results(results, sites_text="", require_chinese_text=True):
    if not results:
        return []

    custom_allowlist = parse_sites_text(sites_text)
    allowlist = custom_allowlist if custom_allowlist else CN_DOMAIN_PRESET

    filtered = []
    seen_urls = set()
    for item in results:
        url = item.get("url", "")
        host = _extract_host(url)
        if not host:
            continue

        is_cn_domain = host.endswith(".cn") or _domain_in_allowlist(host, allowlist)
        if not is_cn_domain:
            continue

        if require_chinese_text:
            text_blob = f"{item.get('title', '')} {item.get('content', '')}"
            if not contains_chinese_text(text_blob):
                continue

        if url and url in seen_urls:
            continue
        if url:
            seen_urls.add(url)
        filtered.append(item)

    return filtered



def search_web(query, sites_text, timelimit, max_results=20, tavily_key=""):
    if not tavily_key:
        return []
    sites = parse_sites_text(sites_text)
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
            # We audit freshness again downstream with a 24h +/- 6h window.
            # Querying 2 days here avoids missing late-previous-day items that are still in-window.
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
        print(f"Tavily Search Failed: {e}")
        return []



def _coerce_datetime(value):
    if not value:
        return None

    raw = str(value).strip()
    if not raw:
        return None

    candidates = [raw, raw.replace("Z", "+00:00"), raw.replace("/", "-")]
    for candidate in candidates:
        try:
            dt = datetime.datetime.fromisoformat(candidate)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=datetime.timezone.utc)
            return dt
        except ValueError:
            pass

    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S GMT",
    ):
        try:
            dt = datetime.datetime.strptime(raw, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=datetime.timezone.utc)
            return dt
        except ValueError:
            continue

    return None



def extract_result_datetime(result):
    for key in _DATE_KEY_CANDIDATES:
        parsed = _coerce_datetime(result.get(key))
        if parsed:
            return parsed, key
    return None, ""



def audit_recent_news_results(results, now=None, max_age_hours=30, future_tolerance_hours=6, enabled=True):
    baseline = now or datetime.datetime.now(datetime.timezone.utc)
    stats = {
        "enabled": bool(enabled),
        "input_count": len(results or []),
        "audited_count": 0,
        "kept_count": 0,
        "dropped_missing_timestamp_count": 0,
        "dropped_stale_count": 0,
        "dropped_future_count": 0,
        "window_label": f"最近24小时（向前放宽至{max_age_hours}小时，向后容忍{future_tolerance_hours}小时）",
        "anchor_time": baseline.isoformat(),
    }

    if not enabled:
        stats["kept_count"] = len(results or [])
        return list(results or []), stats, []

    filtered = []
    dropped_samples = []
    max_age_delta = datetime.timedelta(hours=max_age_hours)
    future_tolerance_delta = datetime.timedelta(hours=future_tolerance_hours)

    for item in results or []:
        stats["audited_count"] += 1
        published_dt, used_key = extract_result_datetime(item)
        if not published_dt:
            stats["dropped_missing_timestamp_count"] += 1
            if len(dropped_samples) < 5:
                dropped_samples.append(f"缺少可解析时间戳：{item.get('title', '未命名结果')}")
            continue

        delta = baseline - published_dt.astimezone(baseline.tzinfo)
        age_hours = delta.total_seconds() / 3600.0
        enriched_item = dict(item)
        enriched_item["published_at_resolved"] = published_dt.isoformat()
        enriched_item["published_at_source_key"] = used_key
        enriched_item["age_hours"] = round(age_hours, 2)

        if delta > max_age_delta:
            stats["dropped_stale_count"] += 1
            if len(dropped_samples) < 5:
                dropped_samples.append(f"超出窗口 {round(age_hours, 1)}h：{item.get('title', '未命名结果')}")
            continue

        if delta < -future_tolerance_delta:
            stats["dropped_future_count"] += 1
            if len(dropped_samples) < 5:
                dropped_samples.append(f"时间异常（未来 {round(abs(age_hours), 1)}h）：{item.get('title', '未命名结果')}")
            continue

        filtered.append(enriched_item)

    stats["kept_count"] = len(filtered)
    warnings = []
    dropped_total = (
        stats["dropped_missing_timestamp_count"]
        + stats["dropped_stale_count"]
        + stats["dropped_future_count"]
    )
    if dropped_total:
        warnings.append(
            "时效审查已启用："
            f"原始 {stats['input_count']} 条，保留 {stats['kept_count']} 条，"
            f"剔除 {stats['dropped_stale_count']} 条超窗新闻、"
            f"{stats['dropped_missing_timestamp_count']} 条缺时间戳新闻、"
            f"{stats['dropped_future_count']} 条时间异常新闻。"
        )
    if dropped_samples:
        warnings.append("样例：" + "；".join(dropped_samples))

    return filtered, stats, warnings



def _format_source_block(url, method, body):
    content = (body or "").strip()
    if not content:
        return ""
    return (
        f"\n\n=== SOURCE START [{method}] : {url} ===\n"
        f"{content[:7000]}\n"
        f"=== SOURCE END ===\n"
    )



def fetch_single_url_with_jina(url, jina_key=""):
    jina_url = f"https://r.jina.ai/{url}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    if jina_key:
        headers["Authorization"] = f"Bearer {jina_key}"

    try:
        req = urllib.request.Request(jina_url, headers=headers)
        response = urllib.request.urlopen(req, timeout=15).read().decode("utf-8", errors="ignore")
        if response and len(response) > 200:
            return response
    except Exception:
        pass
    return ""



def _strip_html_to_text(raw_html):
    if not raw_html:
        return ""
    text = _COMMENT_RE.sub(" ", raw_html)
    text = _SCRIPT_RE.sub(" ", text)
    text = _STYLE_RE.sub(" ", text)
    text = _TAG_RE.sub(" ", text)
    text = html.unescape(text)
    text = _WHITESPACE_RE.sub(" ", text)
    return text.strip()



def fetch_single_url_direct(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as response:
            raw = response.read(600000)
            charset = response.headers.get_content_charset() or "utf-8"
        decoded = raw.decode(charset, errors="ignore")
        text = _strip_html_to_text(decoded)
        if len(text) > 350:
            return text
    except Exception:
        pass
    return ""



def _build_snippet_fallback(url, title_text="", snippet_text=""):
    pieces = []
    if title_text:
        pieces.append(f"标题: {title_text}")
    if snippet_text:
        pieces.append(f"摘要: {snippet_text}")
    if url:
        pieces.append(f"链接: {url}")
    return "\n".join(pieces).strip()



def fetch_single_url_with_fallback(url, jina_key="", title_text="", snippet_text=""):
    jina_text = fetch_single_url_with_jina(url, jina_key=jina_key)
    if jina_text:
        return {"text": _format_source_block(url, "jina", jina_text), "method": "jina"}

    direct_text = fetch_single_url_direct(url)
    if direct_text:
        return {"text": _format_source_block(url, "direct_html", direct_text), "method": "direct_html"}

    fallback_text = _build_snippet_fallback(url, title_text=title_text, snippet_text=snippet_text)
    if fallback_text:
        return {"text": _format_source_block(url, "search_snippet", fallback_text), "method": "search_snippet"}

    return {"text": "", "method": "failed"}



def safe_run_async_crawler(urls, jina_key="", snippet_lookup=None, title_lookup=None):
    snippet_lookup = snippet_lookup or {}
    title_lookup = title_lookup or {}
    full_content = ""
    stats = {
        "jina_count": 0,
        "direct_html_count": 0,
        "snippet_count": 0,
        "failed_count": 0,
    }

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        future_to_url = {
            executor.submit(
                fetch_single_url_with_fallback,
                url,
                jina_key,
                title_lookup.get(url, ""),
                snippet_lookup.get(url, ""),
            ): url
            for url in urls
        }
        for future in concurrent.futures.as_completed(future_to_url):
            result = future.result() or {}
            method = result.get("method", "failed")
            stats_key = {
                "jina": "jina_count",
                "direct_html": "direct_html_count",
                "search_snippet": "snippet_count",
            }.get(method, "failed_count")
            stats[stats_key] += 1

            if result.get("text"):
                full_content += result["text"]

    valid_count = stats["jina_count"] + stats["direct_html_count"] + stats["snippet_count"]
    warnings = []
    if stats["jina_count"] == 0 and stats["direct_html_count"] == 0 and stats["snippet_count"] > 0:
        source_mode = "search_summary_fallback"
        warnings.append(
            "Jina 和网页直连全文抽取都未成功，本专题长新闻已降级为“搜索摘要分析”模式；当前内容不是完整原文级深挖，请谨慎解读细节。"
        )
    elif stats["direct_html_count"] > 0 or stats["snippet_count"] > 0:
        source_mode = "mixed_fallback"
        warnings.append(
            "本专题启用了多级抓取兜底：部分内容来自网页直连抽取或搜索摘要补位，整体可靠性高于纯摘要模式，但仍弱于全量原文级抓取。"
        )
    else:
        source_mode = "full_text"

    return {
        "content": full_content,
        "valid_count": valid_count,
        "source_mode": source_mode,
        "warnings": warnings,
        "stats": stats,
    }
