import concurrent.futures
import datetime
import html
import json
import re
import threading
import urllib.error
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
_NUMERIC_SEGMENT_RE = re.compile(r"\d")
_MARKDOWN_HEADING_RE = re.compile(r"^#{1,6}\s*")
_LOW_SIGNAL_LINE_RE = re.compile(
    r"^(share|shares?|related|recommended|more news|latest news|newsletter|sign up|subscribe|login|log in|"
    r"cookie|privacy policy|terms of service|advertisement|sponsored|follow us|all rights reserved)$",
    re.IGNORECASE,
)
_LOW_SIGNAL_FRAGMENT_RE = re.compile(
    r"(more ai .* news|related articles|recommended for you|sign up for .* newsletter|follow us on|"
    r"subscribe to .* newsletter|copyright \d{4}|all rights reserved|terms of service|privacy policy|cookie settings|share this|"
    r"minute read|read more|latest posts)",
    re.IGNORECASE,
)
_LOW_SIGNAL_CN_LINE_RE = re.compile(
    r"^(微信扫一扫|微信扫一扫关注|打开微信扫一扫|扫一扫|扫码下载|扫码下载查看详情|扫码查看详情|"
    r"手机有色|掌上有色|今日有色|服务时间|分享至|我要入驻|媒体品牌|企业服务|政府服务|"
    r"投资人服务|创业者服务|创投平台|ai测评网)$",
    re.IGNORECASE,
)
_LOW_SIGNAL_CN_FRAGMENT_RE = re.compile(
    r"(微信扫一扫|微信扫一扫关注|打开微信扫一扫|扫一扫|扫码下载|扫码下载查看详情|扫码查看详情|"
    r"手机有色|掌上有色|今日有色|app-smm|官方出品|热点资讯|深度解析|独家调研|服务时间|"
    r"分享至|关注公众号|下载查看更多|查看详情|资讯公众号|公众号|上海有色网|有色网)",
    re.IGNORECASE,
)
_TIME_ONLY_RE = re.compile(r"^\d+\s*(m|min|mins|minute|minutes|h|hr|hrs|hour|hours|d|day|days)\s+ago$", re.IGNORECASE)
_RATING_ONLY_RE = re.compile(r"^\d+(\.\d+)?$")
_EXA_SEARCH_TYPES = {"auto", "fast", "instant", "deep", "deep-reasoning", "neural"}
_EXA_CATEGORY_BLOCKS_DATE_FILTERS = {"company", "people"}
_DEFAULT_HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}
_SEARCH_DIAGNOSTICS_LOCK = threading.Lock()
_SEARCH_DIAGNOSTICS = {
    "total_requests": 0,
    "providers": {},
    "failures": [],
}


def reset_search_diagnostics():
    global _SEARCH_DIAGNOSTICS
    with _SEARCH_DIAGNOSTICS_LOCK:
        _SEARCH_DIAGNOSTICS = {
            "total_requests": 0,
            "providers": {},
            "failures": [],
        }


def _record_search_diagnostic(provider, status, result_count=0, detail="", query=""):
    provider_key = str(provider or "unknown").strip().lower() or "unknown"
    with _SEARCH_DIAGNOSTICS_LOCK:
        provider_stats = _SEARCH_DIAGNOSTICS["providers"].setdefault(
            provider_key,
            {"success": 0, "failure": 0, "result_count": 0},
        )
        _SEARCH_DIAGNOSTICS["total_requests"] += 1
        if status == "success":
            provider_stats["success"] += 1
            provider_stats["result_count"] += max(0, int(result_count or 0))
        else:
            provider_stats["failure"] += 1
            _SEARCH_DIAGNOSTICS["failures"].append(
                {
                    "provider": provider_key,
                    "detail": str(detail or ""),
                    "query": str(query or "")[:160],
                }
            )


def get_search_diagnostics():
    with _SEARCH_DIAGNOSTICS_LOCK:
        return json.loads(json.dumps(_SEARCH_DIAGNOSTICS))



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



def _normalize_search_provider(provider):
    provider_key = str(provider or "tavily").strip().lower()
    if provider_key in {"exa", "hybrid", "tavily"}:
        return provider_key
    return "tavily"



def _normalize_exa_text_filter_value(value):
    raw = str(value or "").replace("，", ",").replace("；", ";").strip()
    if not raw:
        return ""

    candidates = [segment.strip() for segment in re.split(r"[\n,;|]+", raw) if segment.strip()]
    if not candidates:
        candidates = [raw]

    for candidate in candidates:
        words = [word for word in candidate.split() if word]
        if 1 <= len(words) <= 5:
            return " ".join(words)
        if words:
            return " ".join(words[:5])
        if candidate:
            return candidate
    return ""



def _build_recent_window_for_timelimit(timelimit, now=None):
    baseline = now or datetime.datetime.now(datetime.timezone.utc)
    future_tolerance = datetime.timedelta(hours=6)
    if timelimit == "d":
        start = baseline - datetime.timedelta(hours=30)
        end = baseline + future_tolerance
    elif timelimit == "w":
        start = baseline - datetime.timedelta(days=7)
        end = baseline + future_tolerance
    elif timelimit == "m":
        start = baseline - datetime.timedelta(days=30)
        end = baseline + future_tolerance
    else:
        return "", ""
    return start.isoformat().replace("+00:00", "Z"), end.isoformat().replace("+00:00", "Z")



def _normalize_exa_result(item, fallback_search_type="auto"):
    title = str(item.get("title") or "").strip()
    url = str(item.get("url") or "").strip()
    published = str(item.get("publishedDate") or item.get("published_date") or "").strip()
    host = _extract_host(url)

    highlight_text = " ".join(
        str(segment or "").strip() for segment in (item.get("highlights") or []) if str(segment or "").strip()
    ).strip()
    summary_text = str(item.get("summary") or "").strip()
    full_text = str(item.get("text") or "").strip()
    content = highlight_text or summary_text or full_text

    return {
        "title": title,
        "url": url,
        "content": content,
        "published_date": published,
        "published": published,
        "published_at_resolved": published,
        "source": host or "exa.ai",
        "author": str(item.get("author") or "").strip(),
        "search_provider": "exa",
        "search_type": str(item.get("searchType") or fallback_search_type or "auto"),
    }



def _dedupe_search_results(results):
    deduped = []
    seen_keys = set()
    for item in results or []:
        url = str(item.get("url") or "").strip().lower()
        if url:
            key = ("url", url)
        else:
            title = re.sub(r"\s+", " ", str(item.get("title") or "").strip().lower())
            published = str(item.get("published_date") or item.get("published") or "")[:10]
            key = ("title", title, published)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        deduped.append(item)
    return deduped



def _search_web_tavily(query, sites_text, timelimit, max_results=20, tavily_key=""):
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
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json", **_DEFAULT_HTTP_HEADERS},
        )
        resp = json.loads(urllib.request.urlopen(req, timeout=15).read().decode("utf-8"))
        results = resp.get("results", [])
        _record_search_diagnostic("tavily", "success", result_count=len(results), query=query)
        return results
    except urllib.error.HTTPError as e:
        try:
            error_body = e.read().decode("utf-8", errors="ignore")
        except Exception:
            error_body = ""
        print(f"Tavily Search Failed: {e} | body={error_body}")
        _record_search_diagnostic("tavily", "failure", detail=f"{e} | {error_body}", query=query)
        return []
    except Exception as e:
        print(f"Tavily Search Failed: {e}")
        _record_search_diagnostic("tavily", "failure", detail=str(e), query=query)
        return []



def _search_web_exa(query, sites_text, timelimit, max_results=20, exa_key="", exa_settings=None):
    if not exa_key:
        return []

    settings = dict(exa_settings or {})
    sites = parse_sites_text(sites_text)
    search_type = str(settings.get("search_type") or "auto").strip().lower()
    if search_type not in _EXA_SEARCH_TYPES:
        search_type = "auto"

    configured_results = int(settings.get("num_results") or max_results or 10)
    resolved_results = max(1, min(100, min(max_results or configured_results, configured_results)))
    category = str(settings.get("category") or "news").strip().lower()
    if category in {"", "auto", "none", "默认"}:
        category = ""

    content_mode = str(settings.get("content_mode") or "highlights").strip().lower()
    highlight_chars = max(400, int(settings.get("highlights_max_characters") or 2200))
    text_chars = max(800, int(settings.get("text_max_characters") or 5000))

    contents = {}
    if content_mode in {"highlights", "highlights_text"}:
        contents["highlights"] = {"maxCharacters": highlight_chars}
    if content_mode in {"text", "highlights_text"}:
        contents["text"] = {"maxCharacters": text_chars}
    if not contents:
        contents["highlights"] = {"maxCharacters": highlight_chars}

    payload = {
        "query": query,
        "type": search_type,
        "numResults": resolved_results,
        "contents": contents,
    }

    if category:
        payload["category"] = category

    if sites:
        payload["includeDomains"] = sites

    include_text = str(settings.get("include_text") or "").strip()
    exclude_text = str(settings.get("exclude_text") or "").strip()
    if include_text:
        normalized_include_text = _normalize_exa_text_filter_value(include_text)
        if normalized_include_text:
            payload["includeText"] = [normalized_include_text]
    if exclude_text:
        normalized_exclude_text = _normalize_exa_text_filter_value(exclude_text)
        if normalized_exclude_text:
            payload["excludeText"] = [normalized_exclude_text]

    if settings.get("moderation"):
        payload["moderation"] = True

    if category not in _EXA_CATEGORY_BLOCKS_DATE_FILTERS:
        start_published, end_published = _build_recent_window_for_timelimit(timelimit)
        if start_published:
            payload["startPublishedDate"] = start_published
        if end_published:
            payload["endPublishedDate"] = end_published

    try:
        req = urllib.request.Request(
            "https://api.exa.ai/search",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "accept": "application/json",
                "x-api-key": exa_key,
                **_DEFAULT_HTTP_HEADERS,
            },
        )
        resp = json.loads(urllib.request.urlopen(req, timeout=20).read().decode("utf-8"))
        results = [
            _normalize_exa_result(item, fallback_search_type=resp.get("searchType") or search_type)
            for item in resp.get("results", []) or []
        ]
        _record_search_diagnostic("exa", "success", result_count=len(results), query=query)
        return results
    except urllib.error.HTTPError as e:
        try:
            error_body = e.read().decode("utf-8", errors="ignore")
        except Exception:
            error_body = ""
        print(f"Exa Search Failed: {e} | body={error_body}")
        _record_search_diagnostic("exa", "failure", detail=f"{e} | {error_body}", query=query)
        return []
    except Exception as e:
        print(f"Exa Search Failed: {e}")
        _record_search_diagnostic("exa", "failure", detail=str(e), query=query)
        return []



def search_web(
    query,
    sites_text,
    timelimit,
    max_results=20,
    tavily_key="",
    provider="tavily",
    exa_key="",
    exa_settings=None,
):
    resolved_provider = _normalize_search_provider(provider)

    if resolved_provider == "exa":
        return _search_web_exa(
            query,
            sites_text,
            timelimit,
            max_results=max_results,
            exa_key=exa_key,
            exa_settings=exa_settings,
        )

    if resolved_provider == "hybrid":
        merged = []
        merged.extend(
            _search_web_exa(
                query,
                sites_text,
                timelimit,
                max_results=max_results,
                exa_key=exa_key,
                exa_settings=exa_settings,
            )
        )
        merged.extend(
            _search_web_tavily(
                query,
                sites_text,
                timelimit,
                max_results=max_results,
                tavily_key=tavily_key,
            )
        )
        return _dedupe_search_results(merged)

    return _search_web_tavily(
        query,
        sites_text,
        timelimit,
        max_results=max_results,
        tavily_key=tavily_key,
    )



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



def _normalize_candidate_line(line):
    cleaned = _WHITESPACE_RE.sub(" ", str(line or "").strip())
    cleaned = cleaned.replace("\u00a0", " ").strip()
    cleaned = _MARKDOWN_HEADING_RE.sub("", cleaned).strip(" -|>")
    cleaned = _remove_low_signal_fragments(cleaned)
    return cleaned.strip()


def _normalize_text_key(text):
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", str(text or "").lower())


def _remove_low_signal_fragments(text):
    cleaned = str(text or "")
    cleaned = _LOW_SIGNAL_FRAGMENT_RE.sub(" ", cleaned)
    cleaned = _LOW_SIGNAL_CN_FRAGMENT_RE.sub(" ", cleaned)
    cleaned = re.sub(r"\s*[-—|｜]+\s*$", " ", cleaned)
    cleaned = re.sub(r"[，,]{2,}", "，", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned.strip(" ，,;；。.!?！？")


def _is_probably_low_signal_line(line):
    cleaned = _normalize_candidate_line(line)
    if not cleaned:
        return True
    lower = cleaned.lower()
    normalized_cn = cleaned.replace(" ", "")
    if _LOW_SIGNAL_LINE_RE.match(lower):
        return True
    if _LOW_SIGNAL_CN_LINE_RE.match(normalized_cn):
        return True
    if _TIME_ONLY_RE.match(lower):
        return True
    if _RATING_ONLY_RE.match(lower):
        return True
    if len(cleaned) <= 2:
        return True
    if cleaned.count("|") >= 3:
        return True
    if lower.startswith(("### ", "## ", "# ")):
        return True
    if _LOW_SIGNAL_FRAGMENT_RE.search(lower) and len(cleaned) < 90:
        return True
    if _LOW_SIGNAL_CN_FRAGMENT_RE.search(normalized_cn) and len(cleaned) < 140:
        return True
    if re.search(r"(关注[\s:：-]*[\d-]{6,}|工作日\s*\d{1,2}:\d{2}|服务时间[:：]?)", cleaned):
        return True
    if re.search(r"(公众号|查看详情|下载查看更多)", cleaned):
        return True
    if cleaned.startswith(("上一篇", "下一篇", "相关阅读", "相关推荐", "延伸阅读")):
        return True
    return False


def _extract_clean_segments(body):
    raw_text = str(body or "").replace("\r", "\n")
    raw_text = raw_text.replace("\u00a0", " ")
    raw_text = raw_text.replace("=== SOURCE START", "\n=== SOURCE START")
    chunks = []
    for block in raw_text.splitlines():
        cleaned = _normalize_candidate_line(block)
        if not cleaned:
            continue
        if _is_probably_low_signal_line(cleaned):
            continue
        chunks.append(cleaned)

    if not chunks:
        fallback_chunks = []
        for sentence in re.split(r"(?<=[。！？.!?])\s+", _WHITESPACE_RE.sub(" ", raw_text).strip()):
            cleaned = _normalize_candidate_line(sentence)
            if not cleaned or _is_probably_low_signal_line(cleaned):
                continue
            fallback_chunks.append(cleaned)
        chunks = fallback_chunks

    deduped = []
    seen = set()
    for chunk in chunks:
        key = _normalize_text_key(chunk)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(chunk)

    filtered = []
    for index, chunk in enumerate(deduped):
        lower = chunk.lower()
        normalized_cn = chunk.replace(" ", "")
        has_sentence_punct = bool(re.search(r"[。！？.!?;；:：]", chunk))
        if index == 0:
            filtered.append(chunk)
            continue
        if _LOW_SIGNAL_FRAGMENT_RE.search(lower):
            continue
        if _LOW_SIGNAL_CN_FRAGMENT_RE.search(normalized_cn):
            continue
        if len(chunk) < 55 and not has_sentence_punct and not _NUMERIC_SEGMENT_RE.search(chunk):
            continue
        filtered.append(chunk)

    return filtered


def _compress_source_text(body, max_chars=2400):
    cleaned_segments = _extract_clean_segments(body)
    raw = "\n".join(cleaned_segments).strip() if cleaned_segments else _WHITESPACE_RE.sub(" ", str(body or "").strip())
    if len(raw) <= max_chars:
        return raw

    head_limit = min(1500, max_chars)
    pieces = [raw[:head_limit].rstrip()]
    used = len(pieces[0])

    segments = []
    source_segments = cleaned_segments or re.split(r"[\r\n]+|(?<=[。！？.!?])\s+", str(body or ""))
    for segment in source_segments:
        cleaned = _normalize_candidate_line(segment)
        if len(cleaned) < 50:
            continue
        if _is_probably_low_signal_line(cleaned):
            continue
        if _NUMERIC_SEGMENT_RE.search(cleaned) or any(
            keyword in cleaned.lower()
            for keyword in ("ai", "chip", "gpu", "server", "cloud", "revenue", "guidance", "订单", "发布", "量产")
        ):
            segments.append(cleaned)

    for segment in segments:
        if segment in pieces[0]:
            continue
        extra = f"\n{segment}"
        if used + len(extra) > max_chars:
            break
        pieces.append(extra)
        used += len(extra)

    compressed = "".join(pieces).strip()
    if len(compressed) < max_chars * 0.72:
        compressed = raw[:max_chars].rstrip()
    return compressed



def _format_source_block(url, method, body, max_chars=2400):
    content = _compress_source_text(body, max_chars=max_chars)
    if not content:
        return ""
    return (
        f"\n\n=== SOURCE START [{method}] : {url} ===\n"
        f"{content}\n"
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
    text = re.sub(r"</(p|div|section|article|li|h[1-6]|br|tr)>", "\n", text, flags=re.IGNORECASE)
    text = _TAG_RE.sub(" ", text)
    text = html.unescape(text)
    text = re.sub(r"\n{2,}", "\n", text)
    lines = []
    for line in text.splitlines():
        cleaned = _normalize_candidate_line(line)
        if not cleaned or _is_probably_low_signal_line(cleaned):
            continue
        lines.append(cleaned)
    return "\n".join(lines).strip()



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



def fetch_single_url_with_fallback(url, jina_key="", title_text="", snippet_text="", max_chars_per_source=2400):
    jina_text = fetch_single_url_with_jina(url, jina_key=jina_key)
    if jina_text:
        return {"text": _format_source_block(url, "jina", jina_text, max_chars=max_chars_per_source), "method": "jina"}

    direct_text = fetch_single_url_direct(url)
    if direct_text:
        return {"text": _format_source_block(url, "direct_html", direct_text, max_chars=max_chars_per_source), "method": "direct_html"}

    fallback_text = _build_snippet_fallback(url, title_text=title_text, snippet_text=snippet_text)
    if fallback_text:
        return {"text": _format_source_block(url, "search_snippet", fallback_text, max_chars=max_chars_per_source), "method": "search_snippet"}

    return {"text": "", "method": "failed"}



def safe_run_async_crawler(urls, jina_key="", snippet_lookup=None, title_lookup=None, max_chars_per_source=2400):
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
                max_chars_per_source,
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
