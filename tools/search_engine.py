import concurrent.futures
import datetime
import difflib
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
_TIME_ONLY_RE = re.compile(r"^\d+\s*(m|min|mins|minute|minutes|h|hr|hrs|hour|hours|d|day|days)\s+ago$", re.IGNORECASE)
_RATING_ONLY_RE = re.compile(r"^\d+(\.\d+)?$")
_EXA_SEARCH_TYPES = {"auto", "fast", "instant", "deep", "deep-reasoning", "neural"}
_EXA_CATEGORY_BLOCKS_DATE_FILTERS = {"company", "people"}
_TAVILY_DEFAULT_EXCLUDE_DOMAINS = [
    "youtube.com",
    "youtu.be",
    "facebook.com",
    "instagram.com",
    "pinterest.com",
    "reddit.com",
    "x.com",
    "twitter.com",
    "linkedin.com",
]
_PREFERRED_NEWS_DOMAINS = {
    "reuters.com",
    "bloomberg.com",
    "apnews.com",
    "ft.com",
    "wsj.com",
    "cnbc.com",
    "theverge.com",
    "techcrunch.com",
    "arstechnica.com",
    "wired.com",
    "engadget.com",
    "9to5mac.com",
    "9to5google.com",
    "macrumors.com",
    "electrek.co",
    "insideevs.com",
    "autohome.com.cn",
    "gasgoo.com",
    "ithome.com",
    "36kr.com",
    "huxiu.com",
    "geekpark.net",
    "leiphone.com",
    "jiqizhixin.com",
    "qbitai.com",
    "apple.com",
    "blog.google",
    "blog.google.com",
    "tesla.com",
    "nvidia.com",
    "nvidianews.nvidia.com",
    "openai.com",
    "anthropic.com",
    "aboutamazon.com",
    "about.fb.com",
    "meta.com",
    "whitehouse.gov",
    "sec.gov",
    "ftc.gov",
    "justice.gov",
    "europa.eu",
}
_OFFICIAL_OR_REGULATORY_DOMAINS = {
    "apple.com",
    "blog.google",
    "blog.google.com",
    "tesla.com",
    "nvidia.com",
    "nvidianews.nvidia.com",
    "openai.com",
    "anthropic.com",
    "aboutamazon.com",
    "about.fb.com",
    "meta.com",
    "whitehouse.gov",
    "sec.gov",
    "ftc.gov",
    "justice.gov",
    "europa.eu",
}
_LOW_QUALITY_DOMAIN_TERMS = (
    "blogspot.",
    "wordpress.",
    "medium.com",
    "substack.com",
    "newsbreak.com",
    "biztoc.com",
    "investing.com",
    "marketscreener.com",
    "tipranks.com",
    "benzinga.com",
    "aol.com",
    "msn.com",
    "yahoo.com",
)
_SOURCE_QUALITY_NOISE_RE = re.compile(
    r"(sponsored|press release distribution|pr newswire|globenewswire|affiliate links?|"
    r"coupon|deal|promo code|roundup|live updates|market wrap|stock to watch|"
    r"相关推荐|相关阅读|热门推荐|大家都在看|优惠券|促销|广告|转载)",
    re.IGNORECASE,
)
_VIEW_COUNT_RE = re.compile(
    r"(?:(?:views?|reads?|阅读量|浏览量|阅读|浏览)\s*[:：]?\s*|"
    r"(\d[\d,]*)\s*(?:views?|reads?)|"
    r"(\d[\d,]*)\s*(?:次阅读|次浏览))(\d[\d,]*)?",
    re.IGNORECASE,
)
_EVENT_SUBJECT_RE = re.compile(
    r"(Apple|Google|Alphabet|Tesla|NVIDIA|OpenAI|Anthropic|Meta|Amazon|Microsoft|SpaceX|"
    r"苹果|谷歌|特斯拉|英伟达|微软|亚马逊|华为|小鹏|比亚迪|小米|荣耀|OPPO|vivo|蔚来|理想|"
    r"公司|车企|厂商|监管机构|法院|政府|官方|客户|供应商)",
    re.IGNORECASE,
)
_EVENT_ACTION_RE = re.compile(
    r"(发布|推出|宣布|更新|升级|收购|投资|合作|签署|上线|开售|量产|交付|召回|调查|批准|禁止|"
    r"起诉|达成|披露|公布|报告|财报|业绩|下调|上调|launch(?:ed|es)?|release(?:d|s)?|announce(?:d|s)?|"
    r"unveil(?:ed|s)?|update(?:d|s)?|partner(?:ed|s)?|invest(?:ed|s)?|acquire(?:d|s)?|"
    r"ship(?:ped|s)?|deliver(?:ed|s)?|approve(?:d|s)?|ban(?:ned|s)?|probe(?:d|s)?)",
    re.IGNORECASE,
)
_EVENT_OBJECT_RE = re.compile(
    r"(iPhone|iOS|Mac|Vision Pro|Apple Intelligence|Gemini|Android|Pixel|Waymo|FSD|Robotaxi|"
    r"Optimus|Megapack|Blackwell|Vera Rubin|GPU|TPU|AI|芯片|模型|系统|应用|功能|产品|"
    r"业务|政策|法规|供应链|订单|产能|数据中心|自动驾驶|机器人|电池|屏幕|摄像头|"
    r"财报|业绩|营收|利润|毛利率|guidance|revenue|margin|earnings)",
    re.IGNORECASE,
)
_TAVILY_DEFAULT_FOCUS_TERMS = [
    "硬件", "供应链", "制造", "量产", "产能", "材料", "新品", "参数", "发布", "政策", "并购", "收购",
    "hardware", "supply", "manufacturing", "supplier", "policy", "acquisition",
]
_TAVILY_DEFAULT_DEPRIORITIZE_TERMS = [
    "lawsuit", "court", "attorney", "copyright", "privacy", "security", "breach", "malware", "crime",
    "诉讼", "法庭", "律师", "版权", "隐私", "安全漏洞", "黑客", "犯罪",
]
_CONSUMER_DAILY_CHINA_DOMAINS = [
    "ithome.com",
    "mydrivers.com",
    "cnmo.com",
    "zol.com.cn",
    "pconline.com.cn",
    "36kr.com",
    "huxiu.com",
    "geekpark.net",
    "leiphone.com",
    "jiqizhixin.com",
    "qbitai.com",
    "tmtpost.com",
    "elecfans.com",
    "ofweek.com",
    "gasgoo.com",
    "d1ev.com",
    "c114.com.cn",
    "ijiwei.com",
    "cls.cn",
    "yicai.com",
    "jiemian.com",
    "thepaper.cn",
    "stcn.com",
    "cnstock.com",
    "21jingji.com",
    "eeo.com.cn",
    "trendforce.cn",
    "laoyaoba.com",
]
_CONSUMER_DAILY_IMPORTANCE_TERMS = [
    "今日", "最新", "发布", "推出", "开售", "上市", "官宣", "新品", "参数", "升级", "量产", "供应链",
    "订单", "产能", "价格", "售价", "销量", "份额", "交付", "渠道", "投产", "融资", "芯片", "影像", "屏幕", "电池", "快充", "散热", "折叠", "AI", "端侧AI",
    "大模型", "智能驾驶", "座舱", "OTA", "激光雷达", "光波导", "LCoS", "Micro OLED", "MicroLED",
    "FPC", "柔性电路", "模组", "传感器", "收购", "并购", "政策",
]
_CONSUMER_DAILY_CHINA_TERMS = [
    "中国", "国内", "国产", "本土", "大陆", "华为", "小米", "荣耀", "vivo", "OPPO", "一加",
    "比亚迪", "小鹏", "理想", "蔚来", "鸿蒙智行", "问界", "智界", "享界", "尊界",
    "豆包", "DeepSeek", "阿里", "百度", "腾讯", "字节", "通义", "文心", "混元",
    "雷鸟", "Rokid", "XREAL", "京东方", "维信诺", "TCL华星", "舜宇", "欧菲光", "鹏鼎", "东山精密",
]
_CONSUMER_DAILY_NOISE_TERMS = [
    "lawsuit", "court", "attorney", "copyright", "privacy", "security", "breach", "malware", "crime",
    "stock", "share price", "analyst rating", "wall street", "deal", "coupon", "discount",
    "诉讼", "法庭", "律师", "版权", "隐私", "安全漏洞", "黑客", "犯罪", "股价", "股票", "评级",
    "分析师", "优惠券", "促销", "折扣", "macos", "相关推荐", "大家都在看", "热门文章", "进一步阅读",
]
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


def _host_matches(host, domains):
    host = str(host or "").lower()
    return any(host == domain or host.endswith(f".{domain}") for domain in domains or [])


def _extract_public_view_count(text):
    raw = str(text or "")
    for match in _VIEW_COUNT_RE.finditer(raw):
        value = match.group(1) or match.group(2) or match.group(3)
        if not value:
            continue
        try:
            return int(value.replace(",", ""))
        except ValueError:
            continue
    return None


def event_validity_score(item):
    blob = f"{(item or {}).get('title', '')} {(item or {}).get('content', '')} {(item or {}).get('snippet', '')}"
    checks = {
        "subject": bool(_EVENT_SUBJECT_RE.search(blob)),
        "action": bool(_EVENT_ACTION_RE.search(blob)),
        "object": bool(_EVENT_OBJECT_RE.search(blob)),
    }
    return sum(1 for hit in checks.values() if hit), checks


def assess_news_source_quality(item, min_content_chars=80):
    item = dict(item or {})
    title = str(item.get("title") or "").strip()
    content = str(item.get("content") or item.get("snippet") or "").strip()
    url = str(item.get("url") or "").strip()
    host = _extract_host(url)
    author = str(item.get("author") or "").strip()
    published = str(
        item.get("published_at_resolved")
        or item.get("published_date")
        or item.get("published")
        or item.get("date")
        or ""
    ).strip()
    blob = f"{title} {content} {url}"
    is_preferred = _host_matches(host, _PREFERRED_NEWS_DOMAINS)
    is_original = _host_matches(host, _OFFICIAL_OR_REGULATORY_DOMAINS)
    low_quality_domain = any(term in host for term in _LOW_QUALITY_DOMAIN_TERMS)
    public_views = _extract_public_view_count(blob)
    validity_count, validity_checks = event_validity_score(item)

    score = 0
    reasons = []
    if is_original:
        score += 6
        reasons.append("原始/官方信源")
    elif is_preferred:
        score += 4
        reasons.append("优先媒体")
    if author:
        score += 1
    if published:
        score += 2
    if len(content) >= min_content_chars:
        score += 2
    elif len(content) >= 40:
        score += 1
    if validity_count >= 2:
        score += 2
    if low_quality_domain:
        score -= 5
        reasons.append("低质量域名")
    if _SOURCE_QUALITY_NOISE_RE.search(blob):
        score -= 3
        reasons.append("页面噪声/聚合特征")
    if public_views is not None and public_views < 100 and not is_original:
        score -= 5
        reasons.append("公开阅读量低于100")

    missing_required = []
    if not title:
        missing_required.append("标题")
    if not published:
        missing_required.append("发布时间")
    if len(content) < min_content_chars and not is_original:
        missing_required.append("正文/摘要不足")
    if validity_count < 2:
        missing_required.append("事件要素不足")

    return {
        "score": score,
        "host": host,
        "is_preferred": is_preferred,
        "is_original": is_original,
        "public_views": public_views,
        "validity_count": validity_count,
        "validity_checks": validity_checks,
        "missing_required": missing_required,
        "reasons": reasons,
    }


def is_high_quality_news_result(item, min_content_chars=80):
    quality = assess_news_source_quality(item, min_content_chars=min_content_chars)
    if quality["missing_required"]:
        return False
    return quality["score"] >= 3



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
        "snippet": content,
        "published_date": published,
        "published": published,
        "published_at": published,
        "published_at_resolved": published,
        "source": host or "exa.ai",
        "author": str(item.get("author") or "").strip(),
        "score": item.get("score", 0),
        "provider": "exa",
        "search_provider": "exa",
        "search_type": str(item.get("searchType") or fallback_search_type or "auto"),
        "topic": "",
        "region_hint": "cn" if (host.endswith(".cn") or contains_chinese_text(f"{title} {content}")) else "global",
    }


def _split_search_filter_terms(value):
    normalized = _normalize_exa_text_filter_value(value)
    if not normalized:
        return []
    return [
        term.strip().lower()
        for term in re.split(r"[\s,;|]+", normalized)
        if term.strip()
    ][:5]


def _dedupe_terms(terms, limit=16):
    merged = []
    seen = set()
    for term in terms or []:
        token = str(term or "").strip().lower()
        if not token or token in seen:
            continue
        seen.add(token)
        merged.append(token)
        if len(merged) >= limit:
            break
    return merged


def _tavily_focus_terms(settings):
    settings = dict(settings or {})
    return _dedupe_terms(
        _split_search_filter_terms(settings.get("include_text")) + _TAVILY_DEFAULT_FOCUS_TERMS,
        limit=16,
    )


def _tavily_deprioritize_terms(settings):
    settings = dict(settings or {})
    return _dedupe_terms(
        _split_search_filter_terms(settings.get("exclude_text")) + _TAVILY_DEFAULT_DEPRIORITIZE_TERMS,
        limit=16,
    )


def _build_tavily_query(query, settings):
    settings = dict(settings or {})
    include_terms = _tavily_focus_terms(settings)
    exclude_terms = _tavily_deprioritize_terms(settings)[:8]
    parts = [str(query or "").strip()]
    if include_terms:
        parts.append(" ".join(include_terms[:8]))
    if exclude_terms:
        parts.append(" ".join(f"-{term}" for term in exclude_terms))
    enhanced = " ".join(part for part in parts if part).strip()
    return enhanced[:380] if len(enhanced) > 380 else enhanced


def _build_tavily_general_query(query, settings):
    settings = dict(settings or {})
    include_terms = _tavily_focus_terms(settings)
    parts = [str(query or "").strip()]
    if include_terms:
        parts.append(" ".join(include_terms[:10]))
    broad = " ".join(part for part in parts if part).strip()
    return broad[:360] if len(broad) > 360 else broad


def _normalize_tavily_result(item):
    title = str(item.get("title") or "").strip()
    url = str(item.get("url") or "").strip()
    published = str(item.get("published_date") or item.get("published") or item.get("date") or "").strip()
    host = _extract_host(url)
    content = str(item.get("content") or "").strip()
    raw_content = str(item.get("raw_content") or "").strip()
    if raw_content and len(content) < 700:
        raw_excerpt = _compress_source_text(raw_content, max_chars=1800)
        if raw_excerpt and _normalize_candidate_line(raw_excerpt) not in _normalize_candidate_line(content):
            content = f"{content}\n{raw_excerpt}".strip() if content else raw_excerpt

    return {
        "title": title,
        "url": url,
        "content": content,
        "snippet": content,
        "published_date": published,
        "published": published,
        "published_at": published,
        "published_at_resolved": published,
        "source": host or str(item.get("source") or "tavily.ai").strip(),
        "author": str(item.get("author") or "").strip(),
        "score": item.get("score", 0),
        "provider": "tavily",
        "search_provider": "tavily",
        "search_type": "advanced_news",
        "topic": "",
        "region_hint": "cn" if (host.endswith(".cn") or contains_chinese_text(f"{title} {content}")) else "global",
    }


def _count_filter_hits(text, terms):
    haystack = str(text or "").lower()
    return sum(1 for term in terms or [] if term and str(term).lower() in haystack)


def _rank_tavily_results(results, settings):
    settings = dict(settings or {})
    include_terms = _tavily_focus_terms(settings)
    exclude_terms = _tavily_deprioritize_terms(settings)
    ranked = []
    for index, raw_item in enumerate(results or []):
        item = _normalize_tavily_result(raw_item)
        blob = f"{item.get('title', '')} {item.get('content', '')} {item.get('url', '')}".lower()
        include_hits = _count_filter_hits(blob, include_terms)
        exclude_hits = _count_filter_hits(blob, exclude_terms)
        try:
            base_score = float(item.get("score", 0) or 0)
        except (TypeError, ValueError):
            base_score = 0.0
        freshness_bonus = 0.05 if item.get("published_date") else 0.0
        hardware_bonus = 0.18 if include_hits >= 2 else 0.0
        rank_score = base_score + include_hits * 0.10 + hardware_bonus - exclude_hits * 0.24 + freshness_bonus
        ranked.append(
            {
                "item": item,
                "score": rank_score,
                "exclude_hits": exclude_hits,
                "original_index": index,
            }
        )

    if exclude_terms:
        clean_ranked = [row for row in ranked if row["exclude_hits"] == 0]
        if len(clean_ranked) >= 3:
            ranked = clean_ranked

    ranked.sort(key=lambda row: (row["score"], -row["original_index"]), reverse=True)
    return _dedupe_search_results([row["item"] for row in ranked])


def _tavily_time_range_for_timelimit(timelimit):
    if timelimit == "d":
        return "day"
    if timelimit == "w":
        return "week"
    if timelimit == "m":
        return "month"
    return ""


def _build_tavily_payloads(query, sites, timelimit, max_results, tavily_key, settings):
    resolved_max = max(1, min(20, int(max_results or 10)))
    base_payload = {
        "api_key": tavily_key,
        "search_depth": "advanced",
        "chunks_per_source": 3,
        "include_answer": False,
        "include_images": False,
        "include_raw_content": True,
        "max_results": resolved_max,
    }
    if sites:
        base_payload["include_domains"] = sites
    else:
        base_payload["exclude_domains"] = _TAVILY_DEFAULT_EXCLUDE_DOMAINS

    news_payload = dict(base_payload)
    news_payload.update(
        {
            "query": _build_tavily_query(query, settings),
            "topic": "news",
        }
    )
    if timelimit == "d":
        # We audit freshness again downstream with a 24h +/- 6h window.
        # Querying 2 days here avoids missing late-previous-day items that are still in-window.
        news_payload["days"] = 2
    elif timelimit == "w":
        news_payload["days"] = 7
        news_payload["time_range"] = "week"
    elif timelimit == "m":
        news_payload["days"] = 30
        news_payload["time_range"] = "month"

    payloads = [("news", news_payload)]

    # Tavily news is fresh but can be narrower than Exa. A smaller general pass
    # recovers company blogs, technical releases, and specialist sites.
    general_max = max(4, min(8, resolved_max // 2 or 4))
    time_range = _tavily_time_range_for_timelimit(timelimit)
    general_payload = dict(base_payload)
    general_payload.update(
        {
            "query": _build_tavily_general_query(query, settings),
            "topic": "general",
            "max_results": general_max,
            "include_raw_content": False,
        }
    )
    if time_range:
        general_payload["time_range"] = time_range
    general_payload.pop("days", None)
    payloads.append(("general", general_payload))

    return payloads


def _run_tavily_payload(label, payload, query):
    try:
        req = urllib.request.Request(
            "https://api.tavily.com/search",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", **_DEFAULT_HTTP_HEADERS},
        )
        resp = json.loads(urllib.request.urlopen(req, timeout=24).read().decode("utf-8"))
        results = resp.get("results", []) or []
        _record_search_diagnostic("tavily", "success", result_count=len(results), query=f"{label}:{query}")
        return results
    except urllib.error.HTTPError as e:
        try:
            error_body = e.read().decode("utf-8", errors="ignore")
        except Exception:
            error_body = ""
        print(f"Tavily Search Failed ({label}): {e} | body={error_body}")
        _record_search_diagnostic("tavily", "failure", detail=f"{label}: {e} | {error_body}", query=query)
        return []
    except Exception as e:
        print(f"Tavily Search Failed ({label}): {e}")
        _record_search_diagnostic("tavily", "failure", detail=f"{label}: {e}", query=query)
        return []



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



def _search_web_tavily(query, sites_text, timelimit, max_results=20, tavily_key="", exa_settings=None):
    if not tavily_key:
        return []
    settings = dict(exa_settings or {})
    sites = parse_sites_text(sites_text)
    raw_results = []
    for label, payload in _build_tavily_payloads(query, sites, timelimit, max_results, tavily_key, settings):
        raw_results.extend(_run_tavily_payload(label, payload, query))
    return _rank_tavily_results(raw_results, settings)


def _dedupe_preserve_order(items, limit=None):
    merged = []
    seen = set()
    for item in items or []:
        value = str(item or "").strip()
        if not value:
            continue
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        merged.append(value)
        if limit and len(merged) >= limit:
            break
    return merged


def _format_consumer_date_terms(target_date=None):
    if not target_date:
        return []
    target = _coerce_target_date(target_date)
    return [
        target.isoformat(),
        f"{target.year}年{target.month}月{target.day}日",
        f"{target.month}月{target.day}日",
        f"{target.month:02d}月{target.day:02d}日",
    ]


CONSUMER_DAILY_SEARCH_DEPTH_CONFIG = {
    "light": {"max_queries": 18, "results_per_query": 8, "candidate_limit": 60},
    "normal": {"max_queries": 36, "results_per_query": 8, "candidate_limit": 90},
    "wide": {"max_queries": 60, "results_per_query": 8, "candidate_limit": 120},
}


def normalize_consumer_daily_search_depth(value):
    key = str(value or "wide").strip().lower()
    return key if key in CONSUMER_DAILY_SEARCH_DEPTH_CONFIG else "wide"


def _consumer_query_record(query, topic_id, query_type, language="zh", priority=3):
    return {
        "query": re.sub(r"\s+", " ", str(query or "")).strip(),
        "topic_id": topic_id,
        "query_type": query_type,
        "language": language,
        "priority": int(priority or 3),
    }


def _add_query(records, query, topic_id, query_type, language="zh", priority=3, seen=None):
    text = re.sub(r"\s+", " ", str(query or "")).strip()
    if not text:
        return
    key = text.lower()
    if seen is not None:
        if key in seen:
            return
        seen.add(key)
    records.append(_consumer_query_record(text, topic_id, query_type, language=language, priority=priority))


def build_exa_consumer_daily_queries(topic_pack, target_date=None, time_window="72h", search_depth="wide", query_suffix=""):
    topic_pack = dict(topic_pack or {})
    topic_id = str(topic_pack.get("id") or topic_pack.get("title") or "").strip()
    topic_name = str(topic_pack.get("topic_name") or topic_pack.get("title") or "").strip()
    suffix = str(query_suffix or "").strip()
    target = _coerce_target_date(target_date)
    date_terms = _format_consumer_date_terms(target)
    recency_hint = "本周" if str(time_window).lower() == "7d" or topic_id == "ai_weekly" else "今日"
    date_hint = f"{target.month}月{target.day}日"

    depth = normalize_consumer_daily_search_depth(search_depth)
    max_queries = CONSUMER_DAILY_SEARCH_DEPTH_CONFIG[depth]["max_queries"]
    records = []
    seen = set()

    daily_queries = list(topic_pack.get("daily_queries", []) or []) + list(topic_pack.get("queries", []) or [])
    domestic = _dedupe_preserve_order(topic_pack.get("domestic_company_terms", []) or [], limit=18)
    global_terms = _dedupe_preserve_order(topic_pack.get("global_company_terms", []) or [], limit=12)
    products = _dedupe_preserve_order(topic_pack.get("product_terms", []) or [], limit=16)
    technologies = _dedupe_preserve_order(
        list(topic_pack.get("technology_terms", []) or [])
        + list(topic_pack.get("boost_terms", []) or [])
        + list(topic_pack.get("keywords", []) or []),
        limit=24,
    )
    supply_chain = _dedupe_preserve_order(topic_pack.get("supply_chain_terms", []) or [], limit=16)
    actions = _dedupe_preserve_order(
        list(topic_pack.get("action_terms", []) or [])
        + ["发布", "更新", "参数", "价格", "供应链", "开售", "量产", "订单", "融资", "销量"],
        limit=16,
    )
    synonyms = _dedupe_preserve_order(topic_pack.get("synonym_terms", []) or [], limit=12)
    english_terms = _dedupe_preserve_order(topic_pack.get("english_terms", []) or [], limit=10)
    media_domains = _dedupe_preserve_order(topic_pack.get("media_domains", []) or [], limit=28)

    for query in daily_queries[:8]:
        _add_query(records, f"{query} {suffix}", topic_id, "core", priority=1, seen=seen)
        _add_query(records, f"{query} {date_hint} {recency_hint} 最新", topic_id, "core_date", priority=1, seen=seen)

    for company in domestic[:10]:
        _add_query(records, f"{recency_hint} {company} {topic_name} {' '.join(actions[:4])} {' '.join(technologies[:4])}", topic_id, "company_cn", priority=1, seen=seen)
    for company in global_terms[:8]:
        _add_query(records, f"{company} {topic_name} latest update today specs launch supply chain", topic_id, "company_global", language="en", priority=2, seen=seen)
    for product in products[:10]:
        _add_query(records, f"{recency_hint} {product} {topic_name} 参数 发布 更新 价格", topic_id, "product", priority=2, seen=seen)
    for tech in technologies[:12]:
        _add_query(records, f"{recency_hint} {topic_name} {tech} 技术 路线 供应链 参数 新闻", topic_id, "technology", priority=2, seen=seen)
    for term in supply_chain[:10]:
        _add_query(records, f"{recency_hint} {topic_name} {term} 供应链 量产 订单 价格", topic_id, "supply_chain", priority=2, seen=seen)
    for term in synonyms[:8]:
        _add_query(records, f"{recency_hint} {term} {topic_name} 最新 发布 参数", topic_id, "synonym", priority=3, seen=seen)
    for query in english_terms[:8]:
        _add_query(records, query, topic_id, "english", language="en", priority=3, seen=seen)

    media_base_terms = _dedupe_preserve_order(domestic[:4] + global_terms[:3] + technologies[:4] + products[:3], limit=10)
    media_base = " ".join(media_base_terms) or topic_name
    for domain in media_domains[:12]:
        _add_query(records, f"{media_base} {recency_hint} site:{domain}", topic_id, "media_site", priority=3, seen=seen)

    for company in (domestic[:5] + global_terms[:4]):
        _add_query(records, f"{company} 官方 {topic_name} 发布 更新 {target.year}", topic_id, "official", priority=2, seen=seen)

    records.sort(key=lambda item: (item["priority"], item["query_type"], item["query"]))
    return records[:max_queries]


def build_consumer_daily_queries(topic_pack, query_suffix="", max_queries=6, target_date=None):
    topic_pack = dict(topic_pack or {})
    topic_title = str(topic_pack.get("title", "") or "").strip()
    suffix = str(query_suffix or "").strip()
    companies = _dedupe_preserve_order(topic_pack.get("companies", []), limit=10)
    keywords = _dedupe_preserve_order(topic_pack.get("keywords", []), limit=12)
    tags = _dedupe_preserve_order(topic_pack.get("tags", []), limit=8)
    date_terms = _format_consumer_date_terms(target_date)
    date_hint = " ".join(date_terms[1:3])

    domestic_terms = " ".join(_CONSUMER_DAILY_CHINA_TERMS[:16])
    importance_terms = " ".join(_CONSUMER_DAILY_IMPORTANCE_TERMS[:18])
    company_text = " ".join(companies[:8])
    keyword_text = " ".join(keywords[:8])
    tag_text = " ".join(tags[:6])

    candidates = []
    for query in list(topic_pack.get("daily_queries", []) or []) + list(topic_pack.get("queries", []) or []):
        base = str(query or "").strip()
        if not base:
            continue
        candidates.append(f"{base} {suffix}".strip())
        if date_hint:
            candidates.append(f"{base} {date_hint} 今日 最新".strip())
        candidates.append(f"{base} 中国 国内 今日 最新 重要 {company_text}".strip())

    candidates.extend(
        [
            f"{topic_title} {company_text} 今日 最新 重要 科技新闻 中国 国内",
            f"{topic_title} {keyword_text} {tag_text} 新品 参数 供应链 量产 国内",
            f"{topic_title} {domestic_terms} {importance_terms}",
        ]
    )

    return _dedupe_preserve_order(candidates, limit=max_queries)


def _term_in_blob(term, blob):
    token = str(term or "").strip()
    if not token:
        return False
    lower_blob = str(blob or "").lower()
    lower_token = token.lower()
    if re.fullmatch(r"[a-z0-9]{1,3}", lower_token):
        return bool(re.search(rf"(?<![a-z0-9]){re.escape(lower_token)}(?![a-z0-9])", lower_blob))
    return lower_token in lower_blob


def _consumer_required_hits(result, topic_pack):
    required_terms = list((topic_pack or {}).get("required_terms", []) or [])
    if not required_terms:
        return 1
    blob = f"{result.get('title', '')} {result.get('content', '')} {result.get('url', '')}"
    return sum(1 for term in required_terms if _term_in_blob(term, blob))


def _is_consumer_china_domain(host, topic_pack):
    host = str(host or "").lower()
    china_domains = (
        list(CN_DOMAIN_PRESET)
        + list(_CONSUMER_DAILY_CHINA_DOMAINS)
        + list((topic_pack or {}).get("china_domains", []) or [])
    )
    return host.endswith(".cn") or _domain_in_allowlist(host, china_domains)


def _consumer_region_hint(result, topic_pack):
    item = dict(result or {})
    host = _extract_host(item.get("url", ""))
    display_blob = f"{item.get('title', '')} {item.get('content', '')} {item.get('snippet', '')}"
    if _is_consumer_china_domain(host, topic_pack) or contains_chinese_text(display_blob):
        return "cn"
    return "global"


def _standardize_consumer_daily_result(result, topic_pack):
    item = dict(result or {})
    provider = str(item.get("provider") or item.get("search_provider") or "").strip().lower()
    if not provider:
        item = _normalize_tavily_result(item)
        provider = item.get("search_provider", "tavily")
    if provider not in {"tavily", "exa"}:
        provider = "tavily"

    snippet = str(item.get("snippet") or item.get("content") or "").strip()
    item["content"] = snippet
    item["snippet"] = snippet
    item["provider"] = provider
    item["search_provider"] = provider
    if not item.get("published_at"):
        item["published_at"] = item.get("published_at_resolved") or item.get("published_date") or item.get("published") or ""
    item["topic"] = str((topic_pack or {}).get("title", "") or item.get("topic", "") or "").strip()
    item["region_hint"] = _consumer_region_hint(item, topic_pack)
    if not item.get("source"):
        item["source"] = _extract_host(item.get("url", "")) or provider
    return item


def _consumer_daily_result_score(result, topic_pack):
    topic_pack = dict(topic_pack or {})
    item = _standardize_consumer_daily_result(result, topic_pack)
    host = _extract_host(item.get("url", ""))
    title = str(item.get("title", "") or "")
    content = str(item.get("content", "") or "")
    url = str(item.get("url", "") or "")
    blob = f"{title} {content} {url}".lower()
    display_blob = f"{title} {content}"

    try:
        score = float(item.get("score", 0) or 0) * 0.15
    except (TypeError, ValueError):
        score = 0.0

    for keyword in topic_pack.get("keywords", []) or []:
        if keyword and str(keyword).lower() in blob:
            score += 1.35
    for tag in topic_pack.get("tags", []) or []:
        if tag and str(tag).lower() in blob:
            score += 1.15
    for company in topic_pack.get("companies", []) or []:
        if company and _term_in_blob(company, blob):
            score += 2.1
    for term in topic_pack.get("boost_terms", []) or []:
        if term and _term_in_blob(term, blob):
            score += 1.05
    for term in topic_pack.get("domestic_company_terms", []) or []:
        if term and _term_in_blob(term, blob):
            score += 1.65
    for term in topic_pack.get("global_company_terms", []) or []:
        if term and _term_in_blob(term, blob):
            score += 0.75

    required_hits = _consumer_required_hits(item, topic_pack)
    if topic_pack.get("required_terms"):
        if required_hits <= 0:
            score -= 8.0
        else:
            score += min(required_hits, 5) * 1.4

    if contains_chinese_text(display_blob):
        score += 3.2
    if _is_consumer_china_domain(host, topic_pack):
        score += 4.2
    elif any(domain and domain.lower() in host for domain in topic_pack.get("domains", []) or []):
        score += 0.8

    china_hits = _count_filter_hits(display_blob, _CONSUMER_DAILY_CHINA_TERMS)
    importance_hits = _count_filter_hits(display_blob, _CONSUMER_DAILY_IMPORTANCE_TERMS)
    noise_hits = _count_filter_hits(blob, _CONSUMER_DAILY_NOISE_TERMS + list(topic_pack.get("deprioritize_terms", []) or []))
    score += min(china_hits, 6) * 0.8
    score += min(importance_hits, 7) * 0.65
    score -= min(noise_hits, 5) * 2.2
    negative_hits = _count_filter_hits(blob, topic_pack.get("negative_terms", []) or [])
    score -= min(negative_hits, 4) * 2.0

    if item.get("region_hint") == "cn":
        score += 1.25
    if item.get("provider") == "exa":
        score += 0.2

    published_dt, _ = extract_result_datetime(item)
    if published_dt:
        score += 0.65
        now = datetime.datetime.now(datetime.timezone.utc)
        age_hours = (now - published_dt.astimezone(datetime.timezone.utc)).total_seconds() / 3600.0
        if age_hours <= 24:
            score += 1.2
        elif age_hours <= 36:
            score += 0.9
        elif age_hours <= 96:
            score += 0.35
        elif age_hours <= 168:
            score += 0.15
    elif any(term in display_blob for term in ("今日", "今天", "最新", "发布", "开售", "官宣")):
        score += 0.35

    if "stock" in blob or "股价" in blob or "股票" in blob:
        if importance_hits < 2 and china_hits < 1:
            score -= 3.0
    if "macos" in blob and not any(term in blob for term in ("iphone", "ios", "手机", "端侧", "ai")):
        score -= 4.0

    return round(score, 4)


def _coerce_target_date(target_date):
    if isinstance(target_date, datetime.datetime):
        return target_date.date()
    if isinstance(target_date, datetime.date):
        return target_date
    raw = str(target_date or "").strip()
    if raw:
        for candidate in (raw[:10], raw.replace("/", "-")[:10]):
            try:
                return datetime.date.fromisoformat(candidate)
            except ValueError:
                pass
    return datetime.datetime.now(datetime.timezone.utc).date()


def text_mentions_local_day(text, target_date):
    target = _coerce_target_date(target_date)
    blob = str(text or "")
    if not blob:
        return False

    full_patterns = {
        target.strftime("%Y-%m-%d"),
        target.strftime("%Y/%m/%d"),
        f"{target.year}年{target.month}月{target.day}日",
        f"{target.year}年{target.month:02d}月{target.day:02d}日",
    }
    if any(pattern in blob for pattern in full_patterns):
        return True

    explicit_dates = re.findall(r"(20\d{2})[年/-](\d{1,2})[月/-](\d{1,2})", blob)
    if explicit_dates:
        return any(
            int(year) == target.year and int(month) == target.month and int(day) == target.day
            for year, month, day in explicit_dates
        )

    month_day_patterns = {
        f"{target.month}月{target.day}日",
        f"{target.month:02d}月{target.day:02d}日",
        f"{target.month}.{target.day}",
        f"{target.month:02d}.{target.day:02d}",
    }
    return any(pattern in blob for pattern in month_day_patterns)


def filter_results_to_local_day(results, target_date, tzinfo=None, allow_text_date=True):
    target = _coerce_target_date(target_date)
    timezone = tzinfo or datetime.timezone(datetime.timedelta(hours=8))
    filtered = []
    stats = {
        "enabled": True,
        "input_count": len(results or []),
        "audited_count": 0,
        "kept_count": 0,
        "dropped_missing_timestamp_count": 0,
        "dropped_not_today_count": 0,
        "kept_by_text_date_count": 0,
        "target_date": target.isoformat(),
        "window_label": f"当日新闻（{target.isoformat()}，按本地时区）",
    }
    dropped_samples = []

    for item in results or []:
        stats["audited_count"] += 1
        published_dt, used_key = extract_result_datetime(item)
        if published_dt:
            local_dt = published_dt.astimezone(timezone)
            if local_dt.date() != target:
                stats["dropped_not_today_count"] += 1
                if len(dropped_samples) < 5:
                    dropped_samples.append(f"非当日 {local_dt.date().isoformat()}：{item.get('title', '未命名结果')}")
                continue
            enriched_item = dict(item)
            enriched_item["published_at_resolved"] = local_dt.isoformat()
            enriched_item["published_at_source_key"] = used_key
            filtered.append(enriched_item)
            continue

        text_blob = f"{item.get('title', '')} {item.get('content', '')}"
        if allow_text_date and text_mentions_local_day(text_blob, target):
            enriched_item = dict(item)
            enriched_item["published_at_resolved"] = target.isoformat()
            enriched_item["published_at_source_key"] = "text_date"
            filtered.append(enriched_item)
            stats["kept_by_text_date_count"] += 1
            continue

        stats["dropped_missing_timestamp_count"] += 1
        if len(dropped_samples) < 5:
            dropped_samples.append(f"缺少当日时间戳：{item.get('title', '未命名结果')}")

    stats["kept_count"] = len(filtered)
    warnings = []
    dropped_total = stats["dropped_not_today_count"] + stats["dropped_missing_timestamp_count"]
    if dropped_total:
        warnings.append(
            f"频道三当日过滤：原始 {stats['input_count']} 条，保留 {stats['kept_count']} 条，"
            f"剔除非当日 {stats['dropped_not_today_count']} 条、缺少当日时间戳 {stats['dropped_missing_timestamp_count']} 条。"
        )
    if dropped_samples:
        warnings.append("样例：" + "；".join(dropped_samples))
    return filtered, stats, warnings


def rank_consumer_daily_results(results, topic_pack, limit=None, strict_required=True):
    ranked = []
    for index, raw_item in enumerate(results or []):
        item = dict(raw_item or {})
        if "search_provider" not in item and "provider" not in item:
            item = _normalize_tavily_result(item)
        item = _standardize_consumer_daily_result(item, topic_pack)
        if strict_required and topic_pack.get("required_terms") and _consumer_required_hits(item, topic_pack) <= 0:
            continue
        score = _consumer_daily_result_score(item, topic_pack)
        ranked.append((score, index, item))

    if any(score >= 6 for score, _, _ in ranked):
        ranked = [row for row in ranked if row[0] >= 1.5]

    ranked.sort(key=lambda row: (-row[0], row[1]))
    deduped = _dedupe_search_results([row[2] for row in ranked])
    if limit:
        return deduped[:limit]
    return deduped


def _resolve_consumer_daily_provider(provider, tavily_key="", exa_key=""):
    provider_key = _normalize_search_provider(provider)
    if provider_key == "hybrid":
        if tavily_key and exa_key:
            return "hybrid"
        if exa_key:
            return "exa"
        if tavily_key:
            return "tavily"
        return ""
    if provider_key == "exa":
        if exa_key:
            return "exa"
        return ""
    if tavily_key:
        return "tavily"
    if exa_key:
        return "exa"
    return ""


def _build_consumer_daily_provider_settings(topic_pack, exa_settings=None, max_results_per_query=14):
    topic_pack = dict(topic_pack or {})
    include_terms = _dedupe_preserve_order(
        list(topic_pack.get("boost_terms", []) or [])
        + list(topic_pack.get("keywords", []) or [])
        + list(topic_pack.get("tags", []) or [])
        + _CONSUMER_DAILY_IMPORTANCE_TERMS,
        limit=18,
    )
    exclude_terms = _dedupe_preserve_order(
        list(topic_pack.get("negative_terms", []) or [])
        + list(topic_pack.get("deprioritize_terms", []) or [])
        + _CONSUMER_DAILY_NOISE_TERMS,
        limit=18,
    )

    tavily_settings = {
        "include_text": " ".join(include_terms[:12]),
        "exclude_text": " ".join(exclude_terms[:12]),
    }

    exa_runtime_settings = dict(exa_settings or {})
    exa_runtime_settings.update(
        {
            "search_type": "auto",
            "category": "news",
            "num_results": max(8, min(24, int(max_results_per_query or 8))),
            "content_mode": "highlights",
            "highlights_max_characters": max(2200, int(exa_runtime_settings.get("highlights_max_characters") or 2200)),
            "text_max_characters": max(4000, int(exa_runtime_settings.get("text_max_characters") or 4000)),
            # Exa 的 includeText 是硬过滤，频道三要先保广度，因此依靠 query + 排序加权，不强制 includeText。
            "include_text": "",
            "exclude_text": " ".join(exclude_terms[:5]),
        }
    )
    return tavily_settings, exa_runtime_settings


def search_consumer_daily(
    topic_pack,
    sites_text,
    timelimit,
    tavily_key="",
    provider="hybrid",
    exa_key="",
    exa_settings=None,
    query_suffix="",
    max_results_per_query=14,
    max_queries=6,
    broad_query_count=2,
    target_date=None,
    search_depth="wide",
    discovery_candidate_limit=None,
    strict_required=False,
):
    resolved_provider = _resolve_consumer_daily_provider(provider, tavily_key=tavily_key, exa_key=exa_key)
    if not resolved_provider:
        return []

    topic_pack = dict(topic_pack or {})
    merged_sites_text = merge_sites_text(
        sites_text,
        (
            list(CN_DOMAIN_PRESET)
            + list(_CONSUMER_DAILY_CHINA_DOMAINS)
            + list(topic_pack.get("china_domains", []) or [])
            + list(topic_pack.get("domains", []) or [])
        ),
    )
    china_broad_sites_text = merge_sites_text(
        "",
        list(CN_DOMAIN_PRESET) + list(_CONSUMER_DAILY_CHINA_DOMAINS) + list(topic_pack.get("china_domains", []) or []),
    )
    depth_key = normalize_consumer_daily_search_depth(search_depth)
    depth_config = CONSUMER_DAILY_SEARCH_DEPTH_CONFIG[depth_key]
    if resolved_provider == "exa":
        query_records = build_exa_consumer_daily_queries(
            topic_pack,
            target_date=target_date,
            time_window=timelimit,
            search_depth=depth_key,
            query_suffix=query_suffix,
        )
        if max_queries:
            query_records = query_records[:max(max_queries, depth_config["max_queries"])]
        queries = [item["query"] for item in query_records]
        query_meta = {item["query"]: item for item in query_records}
        max_results_per_query = max_results_per_query or depth_config["results_per_query"]
    else:
        queries = build_consumer_daily_queries(
            topic_pack,
            query_suffix=query_suffix,
            max_queries=max_queries,
            target_date=target_date,
        )
        query_meta = {query: _consumer_query_record(query, topic_pack.get("id") or topic_pack.get("title") or "", "legacy") for query in queries}
    if not queries:
        return []

    tavily_settings, exa_runtime_settings = _build_consumer_daily_provider_settings(
        topic_pack,
        exa_settings=exa_settings,
        max_results_per_query=max_results_per_query,
    )
    merged_results = []
    seen_urls = set()
    use_exa = resolved_provider in {"exa", "hybrid"}
    use_tavily = resolved_provider in {"tavily", "hybrid"}

    def append_results(batch, query_text=""):
        for result in batch or []:
            result = _standardize_consumer_daily_result(result, topic_pack)
            meta = query_meta.get(query_text, {})
            if meta:
                result["query"] = meta.get("query", query_text)
                result["query_type"] = meta.get("query_type", "")
                result["query_language"] = meta.get("language", "")
                result["query_priority"] = meta.get("priority", "")
            url = str(result.get("url") or "").strip()
            key = url.lower() if url else re.sub(r"\s+", " ", str(result.get("title") or "").strip().lower())
            if key and key in seen_urls:
                continue
            if key:
                seen_urls.add(key)
            merged_results.append(result)

    for query_index, query in enumerate(queries):
        if use_exa:
            append_results(
                _search_web_exa(
                    query,
                    merged_sites_text,
                    timelimit,
                    max_results=max_results_per_query,
                    exa_key=exa_key,
                    exa_settings=exa_runtime_settings,
                ),
                query,
            )
        if use_tavily:
            append_results(
                _search_web_tavily(
                    query,
                    merged_sites_text,
                    timelimit,
                    max_results=max_results_per_query,
                    tavily_key=tavily_key,
                    exa_settings=tavily_settings,
                ),
                query,
            )

        if resolved_provider != "exa" and query_index < broad_query_count:
            broad_query = f"{query} 中国 国内 中文 科技 媒体 重要".strip()
            if use_exa:
                append_results(
                    _search_web_exa(
                        broad_query,
                        china_broad_sites_text,
                        timelimit,
                        max_results=max(8, min(14, max_results_per_query)),
                        exa_key=exa_key,
                        exa_settings=exa_runtime_settings,
                    ),
                    broad_query,
                )
            if use_tavily:
                append_results(
                    _search_web_tavily(
                        broad_query,
                        china_broad_sites_text,
                        timelimit,
                        max_results=max(8, min(14, max_results_per_query)),
                        tavily_key=tavily_key,
                        exa_settings=tavily_settings,
                    ),
                    broad_query,
                )

    candidate_limit = int(discovery_candidate_limit or depth_config["candidate_limit"] or 80)
    return rank_consumer_daily_results(
        merged_results,
        topic_pack,
        limit=max(30, min(160, candidate_limit)),
        strict_required=strict_required,
    )


def search_consumer_daily_tavily(
    topic_pack,
    sites_text,
    timelimit,
    tavily_key="",
    query_suffix="",
    max_results_per_query=14,
    max_queries=6,
    broad_query_count=2,
    target_date=None,
):
    return search_consumer_daily(
        topic_pack,
        sites_text,
        timelimit,
        tavily_key=tavily_key,
        provider="tavily",
        exa_key="",
        exa_settings=None,
        query_suffix=query_suffix,
        max_results_per_query=max_results_per_query,
        max_queries=max_queries,
        broad_query_count=broad_query_count,
        target_date=target_date,
        strict_required=True,
    )



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
                exa_settings=exa_settings,
            )
        )
        return _dedupe_search_results(merged)

    return _search_web_tavily(
        query,
        sites_text,
        timelimit,
        max_results=max_results,
        tavily_key=tavily_key,
        exa_settings=exa_settings,
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


def _news_item_value(item, key, default=""):
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def _title_review_window_hours(time_flag):
    key = str(time_flag or "").strip().lower()
    if key in {"d", "day", "24h", "today", "过去 24 小时", "过去24小时"}:
        return 30
    if key in {"w", "week", "7d", "过去 1 周", "过去1周"}:
        return 24 * 7
    if key in {"m", "month", "30d", "过去 1 个月", "过去1个月"}:
        return 24 * 30
    return 30


def _title_review_tokens(text):
    raw = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", str(text or "").lower())
    words = {token for token in raw.split() if len(token) >= 2}
    chars = re.findall(r"[\u4e00-\u9fff]", raw)
    cjk_tokens = {"".join(chars[idx:idx + 2]) for idx in range(max(0, len(chars) - 1))}
    return words | cjk_tokens


def _title_review_normalize(text):
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", str(text or "").lower())


def _title_match_score(news_title, topic, result):
    news_title = str(news_title or "").strip()
    candidate_title = str((result or {}).get("title", "") or "").strip()
    candidate_text = f"{candidate_title} {str((result or {}).get('content', '') or '')[:260]}"
    if not news_title or not candidate_text.strip():
        return 0.0

    news_norm = _title_review_normalize(news_title)
    candidate_title_norm = _title_review_normalize(candidate_title)
    candidate_norm = _title_review_normalize(candidate_text)
    if not news_norm or not candidate_norm:
        return 0.0

    title_ratio = difflib.SequenceMatcher(None, news_norm, candidate_title_norm).ratio() if candidate_title_norm else 0.0
    corpus_ratio = difflib.SequenceMatcher(None, news_norm, candidate_norm[: max(len(news_norm) * 2, 80)]).ratio()
    title_tokens = _title_review_tokens(news_title)
    candidate_tokens = _title_review_tokens(candidate_text)
    overlap = len(title_tokens & candidate_tokens) / max(len(title_tokens), 1)
    substring_bonus = 0.30 if news_norm in candidate_norm or (candidate_title_norm and candidate_title_norm in news_norm) else 0.0

    topic_tokens = _title_review_tokens(topic)
    topic_bonus = 0.0
    if topic_tokens:
        topic_overlap = len(topic_tokens & candidate_tokens) / max(len(topic_tokens), 1)
        topic_bonus = min(topic_overlap * 0.08, 0.08)

    return round(max(title_ratio, corpus_ratio * 0.82) * 0.48 + overlap * 0.42 + substring_bonus + topic_bonus, 4)


def _title_review_drop_reason(stats, result_count):
    if result_count <= 0:
        return "搜索无结果"
    if not stats:
        return "未通过时效审查"
    if int(stats.get("dropped_missing_timestamp_count", 0) or 0) >= result_count:
        return "搜索结果缺少可解析时间戳"
    if int(stats.get("dropped_future_count", 0) or 0) > 0 and int(stats.get("kept_count", 0) or 0) <= 0:
        return "搜索结果存在未来时间异常"
    if int(stats.get("dropped_stale_count", 0) or 0) > 0 and int(stats.get("kept_count", 0) or 0) <= 0:
        return "搜索结果发布时间超出当前回溯窗口"
    return "窗口内搜索结果与标题不匹配"


def verify_selected_news_by_title_search(
    news_items,
    topic,
    time_flag,
    tavily_key="",
    provider="tavily",
    exa_key="",
    exa_settings=None,
    now=None,
    search_fn=None,
    max_results_per_query=8,
    title_match_threshold=0.34,
):
    """Verify final channel-1 news by searching its title again."""
    search_callable = search_fn or search_web
    kept_items = []
    warnings = []
    max_age_hours = _title_review_window_hours(time_flag)

    for item in news_items or []:
        item_index = len(kept_items) + len(warnings) + 1
        title = str(_news_item_value(item, "title", "") or "").strip()
        item_url = str(_news_item_value(item, "url", "") or "").strip().lower()
        event_id = str(_news_item_value(item, "event_id", "") or "").strip()
        item_label = f"第{item_index}条详细新闻" + (f"（event_id={event_id}）" if event_id else "")
        if not title:
            warnings.append(f"标题二次审查剔除{item_label}：缺少标题。")
            continue

        queries = [
            f'"{title}" {topic}'.strip(),
            f"{title} {topic} 最新 发布".strip(),
        ]
        merged_results = []
        seen_urls = set()
        for query in queries:
            try:
                batch = search_callable(
                    query,
                    "",
                    time_flag,
                    max_results=max_results_per_query,
                    tavily_key=tavily_key,
                    provider=provider,
                    exa_key=exa_key,
                    exa_settings=exa_settings,
                ) or []
            except TypeError:
                batch = search_callable(query) or []
            for result in batch:
                url = str((result or {}).get("url") or "").strip().lower()
                key = url or re.sub(r"\s+", " ", str((result or {}).get("title") or "").strip().lower())
                if key and key in seen_urls:
                    continue
                if key:
                    seen_urls.add(key)
                merged_results.append(dict(result or {}))

        if not merged_results:
            warnings.append(f"标题二次审查剔除{item_label}：搜索无结果。")
            continue

        fresh_results, freshness_stats, _ = audit_recent_news_results(
            merged_results,
            now=now,
            max_age_hours=max_age_hours,
            future_tolerance_hours=6,
            enabled=True,
        )
        if item_url and any(item_url == str((result or {}).get("url") or "").strip().lower() for result in fresh_results):
            kept_items.append(item)
            continue
        matched = [
            result for result in fresh_results
            if _title_match_score(title, topic, result) >= title_match_threshold
        ]
        if matched:
            kept_items.append(item)
            continue

        reason = _title_review_drop_reason(freshness_stats, len(merged_results))
        warnings.append(
            f"标题二次审查剔除{item_label}：{reason}；"
            f"搜索 {len(merged_results)} 条，时效保留 {int(freshness_stats.get('kept_count', 0) or 0)} 条。"
        )

    return kept_items, warnings



def _normalize_candidate_line(line):
    cleaned = _WHITESPACE_RE.sub(" ", str(line or "").strip())
    cleaned = cleaned.replace("\u00a0", " ").strip()
    cleaned = _MARKDOWN_HEADING_RE.sub("", cleaned).strip(" -|>")
    return cleaned.strip()


def _is_probably_low_signal_line(line):
    cleaned = _normalize_candidate_line(line)
    if not cleaned:
        return True
    lower = cleaned.lower()
    if _LOW_SIGNAL_LINE_RE.match(lower):
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
        key = chunk.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(chunk)

    filtered = []
    for index, chunk in enumerate(deduped):
        lower = chunk.lower()
        has_sentence_punct = bool(re.search(r"[。！？.!?;；:：]", chunk))
        if index == 0:
            filtered.append(chunk)
            continue
        if _LOW_SIGNAL_FRAGMENT_RE.search(lower):
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
