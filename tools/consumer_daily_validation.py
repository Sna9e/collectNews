import datetime
import difflib
import json
import re
import urllib.parse
from dataclasses import asdict, dataclass, field
from pathlib import Path


CONFIRMED_LEVELS = {"confirmed", "likely"}
WATCHLIST_LEVELS = {"weak", "rumor"}
CONSUMER_DAILY_MIN_EVENTS_PER_TOPIC = 3
CONSUMER_DAILY_TARGET_EVENTS_PER_TOPIC = 5
CONSUMER_DAILY_MAX_EVENTS_PER_TOPIC = 6
CONSUMER_DAILY_MIN_CONFIRMED_OR_LIKELY = 3
CONSUMER_DAILY_ALLOW_LIKELY_AS_MAIN = True
CONSUMER_DAILY_ALLOW_WEAK_AS_WATCHLIST = True
CONSUMER_DAILY_WATCHLIST_LIMIT = 2
RUMOR_TERMS = ["爆料", "传闻", "据悉", "消息称", "网传", "leak", "rumor", "reportedly"]
STALE_TERMS = ["回顾", "盘点", "汇总", "历史", "参数整理", "旧款", "去年", "上个月", "此前", "曾经"]
LOW_SIGNAL_TERMS = ["相关推荐", "大家都在看", "热门文章", "进一步阅读", "广告", "优惠券", "点击空白处"]
REPRINT_36KR_PATTERNS = [
    "据36氪",
    "来源：36氪",
    "来源:36氪",
    "转载自36氪",
    "36氪获悉",
    "36氪报道",
]
DEFAULT_TIME_WINDOW_BY_TOPIC = {
    "ai_weekly": "7d",
}


@dataclass
class RawSearchResult:
    title: str
    url: str
    domain: str
    source_name: str | None
    snippet: str | None
    published_at: str | None
    provider: str
    topic_id: str
    query: str
    language: str | None
    region_hint: str | None


@dataclass
class CandidateArticle:
    title: str
    url: str
    canonical_url: str | None
    domain: str
    source_name: str
    source_type: str
    source_tier: int
    provider: str
    published_at_search: str | None
    published_at_page: str | None
    event_time_text: str | None
    cleaned_snippet: str
    extracted_claims: list[str]
    topic_id: str
    company_entities: list[str]
    product_entities: list[str]
    technology_entities: list[str]
    rejection_reasons: list[str] = field(default_factory=list)


@dataclass
class NewsEvent:
    event_id: str
    topic_id: str
    normalized_title: str
    event_summary: str
    companies: list[str]
    products: list[str]
    technologies: list[str]
    event_date: str | None
    first_seen_at: str | None
    latest_seen_at: str | None
    evidence_articles: list[CandidateArticle]
    independent_source_count: int
    official_source_count: int
    domestic_source_count: int
    overseas_source_count: int
    source_domains: list[str]
    source_names: list[str]
    confidence_level: str
    confidence_score: float
    rejection_reasons: list[str]
    time_window: str = ""


@dataclass
class RejectedEventSummary:
    title: str
    topic_id: str
    confidence_level: str
    reasons: list[str]
    source_domains: list[str]


@dataclass
class TopicVerifiedEvents:
    topic_id: str
    topic_name: str
    time_window: str
    confirmed_events: list[NewsEvent]
    likely_events: list[NewsEvent]
    watchlist_events: list[NewsEvent]
    rejected_summary: list[RejectedEventSummary]
    warnings: list[str] = field(default_factory=list)
    expansion_attempts: list[str] = field(default_factory=list)
    insufficient_reason: str = ""


@dataclass
class TopicOutput:
    main_events: list[NewsEvent]
    watchlist_events: list[NewsEvent]
    insufficient_warning: bool
    expansion_attempts: list[str]
    insufficient_reason: str


@dataclass
class VerifiedNewsPackage:
    target_date: str
    time_window: str
    topics: list[TopicVerifiedEvents]
    search_provider: str = "exa"


@dataclass
class QualityReport:
    total_events: int
    confirmed_events: int
    likely_events: int
    weak_events: int
    rejected_events: int
    source_diversity_score: float
    max_single_source_ratio: float
    events_with_36kr_only: list[str]
    stale_events: list[str]
    topics_with_insufficient_events: list[str]
    topic_event_counts: dict[str, int]
    topic_confirmed_counts: dict[str, int]
    topic_likely_counts: dict[str, int]
    topic_watchlist_counts: dict[str, int]
    topics_below_minimum: list[str]
    expansion_attempts: dict[str, list[str]]
    insufficient_reasons: dict[str, str]
    warnings: list[str]


def dataclass_to_dict(value):
    return asdict(value)


def load_source_registry(registry_path=None):
    path = Path(registry_path) if registry_path else Path(__file__).resolve().parent / "source_registry.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        data = {"sources": {}, "source_names": {}}
    data.setdefault("sources", {})
    data.setdefault("source_names", {})
    for key in (
        "official",
        "high_quality_cn",
        "consumer_electronics_cn",
        "ai_cn",
        "auto_cn",
        "semiconductor_display_cn",
        "finance_business_cn",
        "medium_quality_cn",
        "low_quality_or_aggregator",
    ):
        data["sources"].setdefault(key, [])
    high_quality_extensions = []
    for key in ("consumer_electronics_cn", "ai_cn", "auto_cn", "semiconductor_display_cn", "finance_business_cn"):
        high_quality_extensions.extend(data["sources"].get(key, []) or [])
    data["sources"]["high_quality_cn"] = _dedupe_preserve_order(
        list(data["sources"].get("high_quality_cn", []) or []) + high_quality_extensions
    )
    data["sources"].setdefault("same_media_groups", [])
    return data


def _extract_domain(url):
    raw = str(url or "").strip()
    if not raw:
        return ""
    try:
        parsed = urllib.parse.urlparse(raw)
        host = (parsed.netloc or raw).split("/")[0].lower()
    except Exception:
        host = raw.split("/")[0].lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def _domain_matches(domain, candidates):
    domain = str(domain or "").lower()
    return any(domain == item or domain.endswith(f".{item}") for item in candidates or [])


def _clean_text(text, limit=None):
    raw = str(text or "").replace("\r", "\n")
    lines = []
    for line in raw.splitlines():
        cleaned = re.sub(r"\s+", " ", line).strip()
        if not cleaned:
            continue
        lower = cleaned.lower()
        if any(term.lower() in lower for term in LOW_SIGNAL_TERMS):
            continue
        lines.append(cleaned)
    merged = " ".join(lines) if lines else re.sub(r"\s+", " ", raw).strip()
    if limit and len(merged) > limit:
        return merged[:limit].rstrip(" ，,;；。") + "。"
    return merged


def _canonicalize_url(url):
    raw = str(url or "").strip()
    if not raw:
        return ""
    try:
        parsed = urllib.parse.urlparse(raw)
        query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=False)
        filtered = [
            (key, value) for key, value in query
            if not key.lower().startswith("utm_") and key.lower() not in {"spm", "from", "source"}
        ]
        return urllib.parse.urlunparse(
            (parsed.scheme, parsed.netloc.lower(), parsed.path.rstrip("/"), "", urllib.parse.urlencode(filtered), "")
        )
    except Exception:
        return raw


def classify_source(domain, source_name="", registry=None):
    registry = registry or load_source_registry()
    sources = registry.get("sources", {})
    if _domain_matches(domain, sources.get("official", [])):
        return "official", 1
    if _domain_matches(domain, sources.get("high_quality_cn", [])):
        return "vertical_media", 2
    if _domain_matches(domain, sources.get("medium_quality_cn", [])):
        return "primary_media", 3
    if _domain_matches(domain, sources.get("low_quality_or_aggregator", [])):
        return "aggregator", 5
    if "微信" in str(source_name or "") or domain == "mp.weixin.qq.com":
        return "social", 5
    return "unknown", 4


def source_display_name(domain, fallback="", registry=None):
    registry = registry or load_source_registry()
    names = registry.get("source_names", {})
    for candidate, name in names.items():
        if _domain_matches(domain, [candidate]):
            return name
    return str(fallback or domain or "未知来源").strip()


def _contains_chinese(text):
    return bool(re.search(r"[\u4e00-\u9fff]", str(text or "")))


def normalize_time_window(topic_pack, configured_window="72h"):
    configured = str(configured_window or "72h").strip().lower()
    if configured not in {"today", "24h", "72h", "7d"}:
        configured = "72h"
    topic_id = str((topic_pack or {}).get("id") or "").strip()
    if topic_id in DEFAULT_TIME_WINDOW_BY_TOPIC and configured == "72h":
        return DEFAULT_TIME_WINDOW_BY_TOPIC[topic_id]
    return configured


def _window_hours(time_window):
    key = str(time_window or "72h").lower()
    if key == "today":
        return 30
    if key == "24h":
        return 30
    if key == "7d":
        return 24 * 7
    return 72


def _coerce_datetime(value):
    if not value:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    for candidate in (raw, raw.replace("Z", "+00:00"), raw.replace("/", "-")):
        try:
            parsed = datetime.datetime.fromisoformat(candidate[:19] if len(candidate) > 19 and "+" not in candidate and "Z" not in candidate else candidate)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=datetime.timezone.utc)
            return parsed
        except ValueError:
            pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            parsed = datetime.datetime.strptime(raw[:19], fmt)
            return parsed.replace(tzinfo=datetime.timezone.utc)
        except ValueError:
            continue
    return None


def _extract_dates_from_text(text, target_date):
    blob = str(text or "")
    dates = []
    for year, month, day in re.findall(r"(20\d{2})[年/-](\d{1,2})[月/-](\d{1,2})", blob):
        try:
            dates.append(datetime.date(int(year), int(month), int(day)))
        except ValueError:
            pass
    for month, day in re.findall(r"(?<!\d)(\d{1,2})月(\d{1,2})日", blob):
        try:
            dates.append(datetime.date(target_date.year, int(month), int(day)))
        except ValueError:
            pass
    return dates


def _is_stale_article(article, target_date, time_window):
    target = target_date if isinstance(target_date, datetime.date) else datetime.date.fromisoformat(str(target_date)[:10])
    target_dt = datetime.datetime.combine(target, datetime.time(23, 59), tzinfo=datetime.timezone.utc)
    published_dt = _coerce_datetime(article.published_at_page or article.published_at_search)
    if published_dt:
        age_hours = (target_dt - published_dt.astimezone(datetime.timezone.utc)).total_seconds() / 3600.0
        if age_hours > _window_hours(time_window):
            return True, "article_published_at_out_of_window"
        if str(time_window).lower() == "today" and published_dt.date() != target:
            return True, "article_not_published_today"

    text_blob = f"{article.title} {article.cleaned_snippet}"
    explicit_dates = _extract_dates_from_text(text_blob, target)
    if explicit_dates:
        newest = max(explicit_dates)
        age_days = (target - newest).days
        if age_days > max(1, _window_hours(time_window) // 24):
            return True, "event_date_out_of_window"
    if any(term in text_blob for term in STALE_TERMS) and not any(term in text_blob for term in ("今日", "今天", "发布", "推出", "更新", "官宣", "开售", "上市")):
        return True, "stale_or_roundup_article"
    return False, ""


def _match_terms(text, terms):
    blob = str(text or "").lower()
    hits = []
    for term in terms or []:
        token = str(term or "").strip()
        if token and token.lower() in blob:
            hits.append(token)
    return hits


def _topic_mismatch_reasons(article, topic_pack):
    blob = f"{article.title} {article.cleaned_snippet} {article.url}"
    required = list((topic_pack or {}).get("required_terms", []) or [])
    negative = list((topic_pack or {}).get("negative_terms", []) or [])
    reasons = []
    if required and not _match_terms(blob, required):
        reasons.append("topic_required_terms_missing")
    negative_hits = _match_terms(blob, negative)
    if negative_hits:
        reasons.append("topic_negative_terms:" + ",".join(negative_hits[:3]))
    topic_id = str((topic_pack or {}).get("id") or "")
    if topic_id == "ar_vr_ai_glasses" and re.search(r"折叠\s*iPhone|折叠手机|foldable iphone", blob, re.IGNORECASE):
        reasons.append("ar_vr_topic_polluted_by_foldable_phone")
    if topic_id == "foldable_display_supply" and "普通手机" in blob and not _match_terms(blob, required):
        reasons.append("display_topic_polluted_by_generic_phone")
    return reasons


def raw_result_from_search_result(result, topic_pack, query=""):
    item = dict(result or {})
    url = str(item.get("url") or "").strip()
    domain = _extract_domain(url)
    title = str(item.get("title") or "").strip()
    snippet = str(item.get("snippet") or item.get("content") or "").strip()
    published = str(
        item.get("published_at")
        or item.get("published_at_resolved")
        or item.get("published_date")
        or item.get("published")
        or item.get("date")
        or ""
    ).strip()
    provider = str(item.get("provider") or item.get("search_provider") or "unknown").strip().lower()
    language = "zh" if _contains_chinese(f"{title} {snippet}") else "en"
    return RawSearchResult(
        title=title,
        url=url,
        domain=domain,
        source_name=item.get("source") or domain,
        snippet=snippet,
        published_at=published,
        provider=provider,
        topic_id=str((topic_pack or {}).get("id") or (topic_pack or {}).get("title") or ""),
        query=str(item.get("query") or query or ""),
        language=language,
        region_hint=item.get("region_hint") or ("cn" if language == "zh" or domain.endswith(".cn") else "global"),
    )


def candidate_from_raw(raw, topic_pack, target_date, time_window, registry=None):
    registry = registry or load_source_registry()
    source_name = source_display_name(raw.domain, raw.source_name, registry=registry)
    source_type, source_tier = classify_source(raw.domain, source_name, registry=registry)
    snippet = _clean_text(raw.snippet, limit=1200)
    blob = f"{raw.title} {snippet}"
    topic_terms = (
        list((topic_pack or {}).get("companies", []) or [])
        + list((topic_pack or {}).get("domestic_company_terms", []) or [])
        + list((topic_pack or {}).get("global_company_terms", []) or [])
    )
    tech_terms = (
        list((topic_pack or {}).get("keywords", []) or [])
        + list((topic_pack or {}).get("tags", []) or [])
        + list((topic_pack or {}).get("boost_terms", []) or [])
    )
    companies = _dedupe_preserve_order(_match_terms(blob, topic_terms), limit=8)
    technologies = _dedupe_preserve_order(_match_terms(blob, tech_terms), limit=10)
    products = _extract_products(blob)
    claims = _extract_claims(blob)
    event_time_text = _extract_event_time_text(blob, target_date)
    article = CandidateArticle(
        title=raw.title,
        url=raw.url,
        canonical_url=_canonicalize_url(raw.url),
        domain=raw.domain,
        source_name=source_name,
        source_type=source_type,
        source_tier=source_tier,
        provider=raw.provider,
        published_at_search=raw.published_at,
        published_at_page=None,
        event_time_text=event_time_text,
        cleaned_snippet=snippet,
        extracted_claims=claims,
        topic_id=raw.topic_id,
        company_entities=companies,
        product_entities=products,
        technology_entities=technologies,
    )
    article.rejection_reasons.extend(_topic_mismatch_reasons(article, topic_pack))
    stale, stale_reason = _is_stale_article(article, target_date, time_window)
    if stale:
        article.rejection_reasons.append(stale_reason)
    if source_type == "aggregator":
        article.rejection_reasons.append("low_quality_or_aggregator_source")
    if not article.cleaned_snippet and not article.title:
        article.rejection_reasons.append("empty_article")
    return article


def _extract_event_time_text(text, target_date):
    dates = _extract_dates_from_text(text, target_date)
    if dates:
        return max(dates).isoformat()
    if any(term in str(text or "") for term in ("今日", "今天")):
        return target_date.isoformat() if isinstance(target_date, datetime.date) else str(target_date)[:10]
    return ""


def _extract_products(text):
    patterns = [
        r"\b(?:iPhone|Galaxy|Quest|Vision Pro|Ray-Ban Meta|Meta Quest|Model Y|FSD|Robotaxi|HyperOS|HarmonyOS)\b[ A-Za-z0-9+-]*",
        r"[A-Za-z]+ ?\d{1,2}(?: Ultra| Pro| Pro Max| Air| Plus)?",
        r"[\u4e00-\u9fffA-Za-z0-9]+(?:AI眼镜|智能眼镜|折叠屏|折叠手机|大模型|新车|芯片|模组)",
    ]
    hits = []
    for pattern in patterns:
        hits.extend(match.strip() for match in re.findall(pattern, str(text or ""), flags=re.IGNORECASE))
    return _dedupe_preserve_order(hits, limit=8)


def _extract_claims(text):
    claims = []
    for sentence in re.split(r"[。！？!?]\s*", str(text or "")):
        cleaned = re.sub(r"\s+", " ", sentence).strip()
        if len(cleaned) < 12:
            continue
        if any(term in cleaned for term in ("发布", "推出", "开售", "上市", "升级", "更新", "量产", "订单", "销量", "价格", "融资", "收购", "参数", "供应链")):
            claims.append(cleaned)
        if len(claims) >= 5:
            break
    return claims


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


def _tokenize_for_similarity(text):
    raw = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", str(text or "").lower())
    ascii_tokens = {token for token in raw.split() if len(token) >= 2}
    cjk = re.findall(r"[\u4e00-\u9fff]", raw)
    cjk_tokens = {"".join(cjk[idx:idx + 2]) for idx in range(max(0, len(cjk) - 1))}
    return ascii_tokens | cjk_tokens


def _jaccard_similarity(left, right):
    a = _tokenize_for_similarity(left)
    b = _tokenize_for_similarity(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _string_similarity(left, right):
    return difflib.SequenceMatcher(None, str(left or "").lower(), str(right or "").lower()).ratio()


def _same_media_group(domain_a, domain_b, registry=None):
    registry = registry or load_source_registry()
    for group in registry.get("sources", {}).get("same_media_groups", []) or []:
        if _domain_matches(domain_a, group) and _domain_matches(domain_b, group):
            return True
    return False


def _mentions_36kr(article):
    blob = f"{article.title} {article.cleaned_snippet} {article.source_name}"
    return article.domain.endswith("36kr.com") or any(pattern in blob for pattern in REPRINT_36KR_PATTERNS)


def is_independent_source(article_a, article_b, registry=None):
    registry = registry or load_source_registry()
    if not article_a or not article_b:
        return False
    if article_a.canonical_url and article_b.canonical_url and article_a.canonical_url == article_b.canonical_url:
        return False
    if article_a.domain and article_b.domain and article_a.domain == article_b.domain:
        return False
    if article_a.source_name and article_b.source_name and article_a.source_name == article_b.source_name:
        return False
    if _same_media_group(article_a.domain, article_b.domain, registry=registry):
        return False
    if _mentions_36kr(article_a) and _mentions_36kr(article_b):
        return False
    if _string_similarity(article_a.title, article_b.title) > 0.90:
        return False
    if _string_similarity(article_a.cleaned_snippet, article_b.cleaned_snippet) > 0.85:
        return False
    if "通稿" in article_a.cleaned_snippet and "通稿" in article_b.cleaned_snippet:
        return False
    return True


def _cluster_key_similarity(article_a, article_b):
    entity_overlap = bool(
        set(article_a.company_entities) & set(article_b.company_entities)
        or set(article_a.product_entities) & set(article_b.product_entities)
    )
    tech_overlap = bool(set(article_a.technology_entities) & set(article_b.technology_entities))
    title_sim = _jaccard_similarity(article_a.title, article_b.title)
    blob_sim = _jaccard_similarity(
        f"{article_a.title} {article_a.cleaned_snippet[:220]}",
        f"{article_b.title} {article_b.cleaned_snippet[:220]}",
    )
    if entity_overlap and (title_sim >= 0.18 or blob_sim >= 0.16):
        return True
    if entity_overlap and tech_overlap:
        return True
    if title_sim >= 0.42 or blob_sim >= 0.36:
        return True
    return False


def cluster_articles_into_events(articles, topic_pack=None, target_date=None, time_window="72h", registry=None):
    registry = registry or load_source_registry()
    valid_articles = [article for article in articles or [] if not article.rejection_reasons]
    clusters = []
    for article in valid_articles:
        placed = False
        for cluster in clusters:
            if any(_cluster_key_similarity(article, existing) for existing in cluster):
                cluster.append(article)
                placed = True
                break
        if not placed:
            clusters.append([article])
    return [
        _event_from_cluster(cluster, topic_pack, index + 1, target_date, time_window, registry=registry)
        for index, cluster in enumerate(clusters)
    ]


def _event_from_cluster(cluster, topic_pack, index, target_date, time_window, registry=None):
    registry = registry or load_source_registry()
    topic_id = str((topic_pack or {}).get("id") or (topic_pack or {}).get("title") or "")
    sorted_articles = sorted(cluster, key=lambda item: (item.source_tier, item.source_name, item.title))
    primary = sorted_articles[0]
    independent_articles = _select_independent_articles(sorted_articles, registry=registry)
    independent_count = len(independent_articles)
    official_count = sum(1 for item in independent_articles if item.source_type == "official")
    high_quality_count = sum(1 for item in independent_articles if item.source_tier <= 2)
    domestic_count = sum(1 for item in independent_articles if _is_domestic_source(item))
    overseas_count = max(0, independent_count - domestic_count)
    domains = _dedupe_preserve_order([item.domain for item in independent_articles], limit=12)
    names = _dedupe_preserve_order([item.source_name for item in independent_articles], limit=12)
    companies = _dedupe_preserve_order([value for item in cluster for value in item.company_entities], limit=10)
    products = _dedupe_preserve_order([value for item in cluster for value in item.product_entities], limit=10)
    techs = _dedupe_preserve_order([value for item in cluster for value in item.technology_entities], limit=10)
    event_date = _resolve_event_date(cluster, target_date)
    first_seen = _min_datetime_text([item.published_at_page or item.published_at_search for item in cluster])
    latest_seen = _max_datetime_text([item.published_at_page or item.published_at_search for item in cluster])
    reasons = []
    stale_articles = []
    for article in cluster:
        stale, stale_reason = _is_stale_article(article, target_date, time_window)
        if stale:
            stale_articles.append(stale_reason)
    if stale_articles:
        reasons.append("stale:" + ",".join(sorted(set(stale_articles))[:3]))
    if any(_mentions_36kr(item) for item in cluster) and independent_count <= 1:
        reasons.append("36kr_single_source")
    if any(term.lower() in f"{primary.title} {primary.cleaned_snippet}".lower() for term in RUMOR_TERMS):
        reasons.append("rumor_or_unverified_wording")

    confidence_level, confidence_score = _classify_event_confidence(
        independent_count=independent_count,
        official_count=official_count,
        high_quality_count=high_quality_count,
        reasons=reasons,
        cluster=cluster,
    )
    summary = _build_event_summary(primary, independent_articles, companies, products, techs)
    return NewsEvent(
        event_id=f"{topic_id.upper() or 'EVENT'}-{index:03d}",
        topic_id=topic_id,
        normalized_title=_normalize_event_title(primary.title, companies, products, techs),
        event_summary=summary,
        companies=companies,
        products=products,
        technologies=techs,
        event_date=event_date,
        first_seen_at=first_seen,
        latest_seen_at=latest_seen,
        evidence_articles=independent_articles,
        independent_source_count=independent_count,
        official_source_count=official_count,
        domestic_source_count=domestic_count,
        overseas_source_count=overseas_count,
        source_domains=domains,
        source_names=names,
        confidence_level=confidence_level,
        confidence_score=confidence_score,
        rejection_reasons=reasons,
        time_window=str(time_window or ""),
    )


def _is_domestic_source(article):
    if article.domain.endswith(".cn"):
        return True
    if article.source_type in {"official", "vertical_media", "primary_media"} and _contains_chinese(f"{article.title} {article.cleaned_snippet}"):
        return True
    return str(article.source_name or "") in {"IT之家", "财联社", "集微网", "36氪", "量子位", "机器之心", "智东西", "盖世汽车"}


def _select_independent_articles(articles, registry=None):
    selected = []
    for article in articles or []:
        if all(is_independent_source(article, existing, registry=registry) for existing in selected):
            selected.append(article)
    return selected


def _resolve_event_date(cluster, target_date):
    dates = []
    target = target_date if isinstance(target_date, datetime.date) else datetime.date.fromisoformat(str(target_date)[:10])
    for article in cluster:
        if article.event_time_text:
            try:
                dates.append(datetime.date.fromisoformat(article.event_time_text[:10]))
            except ValueError:
                pass
        parsed = _coerce_datetime(article.published_at_page or article.published_at_search)
        if parsed:
            dates.append(parsed.date())
    if not dates:
        return None
    close_dates = [item for item in dates if abs((target - item).days) <= 7]
    return max(close_dates or dates).isoformat()


def _min_datetime_text(values):
    parsed = [_coerce_datetime(value) for value in values if value]
    parsed = [value for value in parsed if value]
    return min(parsed).isoformat() if parsed else None


def _max_datetime_text(values):
    parsed = [_coerce_datetime(value) for value in values if value]
    parsed = [value for value in parsed if value]
    return max(parsed).isoformat() if parsed else None


def _classify_event_confidence(independent_count, official_count, high_quality_count, reasons, cluster):
    score = independent_count * 18 + official_count * 16 + high_quality_count * 10
    if "36kr_single_source" in reasons:
        score -= 30
    if any(reason.startswith("stale") for reason in reasons):
        return "stale", max(0.0, round(score / 100, 3))
    if "rumor_or_unverified_wording" in reasons and independent_count < 2:
        return "rumor", max(0.0, round(score / 100, 3))
    if independent_count >= 3 and (official_count >= 1 or high_quality_count >= 1):
        return "confirmed", min(1.0, round((score + 20) / 100, 3))
    if independent_count >= 2 and official_count >= 1 and high_quality_count >= 2:
        return "confirmed", min(0.94, round((score + 16) / 100, 3))
    if independent_count >= 2:
        return "likely", min(0.86, round((score + 10) / 100, 3))
    if official_count >= 1:
        return "likely", min(0.78, round((score + 8) / 100, 3))
    if high_quality_count >= 2:
        return "likely", min(0.80, round((score + 8) / 100, 3))
    if not cluster:
        return "rejected", 0.0
    return "weak", max(0.05, round(score / 100, 3))


def _build_event_summary(primary, articles, companies, products, techs):
    sources = "、".join(_dedupe_preserve_order([item.source_name for item in articles], limit=4))
    entities = "、".join((companies or products or techs)[:5])
    claim = primary.extracted_claims[0] if primary.extracted_claims else primary.cleaned_snippet[:180]
    if not claim:
        claim = primary.title
    return f"{entities + '：' if entities else ''}{claim}。证据来源包括：{sources or primary.source_name}。"


def _normalize_event_title(title, companies, products, techs):
    pieces = []
    if companies:
        pieces.append("、".join(companies[:2]))
    if products:
        pieces.append("、".join(products[:2]))
    if techs:
        pieces.append("、".join(techs[:2]))
    base = " / ".join(pieces)
    cleaned = _clean_text(title, limit=80)
    return cleaned if not base else f"{base} - {cleaned}"


def build_verification_queries(event, topic_pack, target_date, limit=6):
    companies = event.companies[:3]
    products = event.products[:3]
    techs = event.technologies[:4]
    core_terms = _dedupe_preserve_order(companies + products + techs, limit=6)
    if not core_terms:
        core_terms = _tokenize_for_similarity(event.normalized_title)
        core_terms = list(core_terms)[:4]
    base = " ".join(core_terms)
    year = target_date.year if isinstance(target_date, datetime.date) else str(target_date)[:4]
    queries = [
        f"{base} 今日",
        f"{base} 发布 {year}",
        f"{base} 官方 发布",
        f"{base} IT之家",
        f"{base} 财联社",
        f"{base} 集微网",
        f"{base} 雷科技",
        f"{base} 快科技",
        f"{base} 36氪",
        f"{base} 供应链 参数",
    ]
    for company in event.companies[:2]:
        queries.append(f"{company} 官方 {base} 发布 更新 {year}")
    for product in event.products[:2]:
        queries.append(f"{product} update today specs")
    if any(term.lower() in event.normalized_title.lower() for term in ("rokid", "xreal", "ray-ban", "meta", "glasses")):
        queries.extend([
            f"{base} AI glasses new feature today",
            f"{base} smart glasses update today",
            f"{base} AR glasses feature update",
        ])
    return _dedupe_preserve_order(queries, limit=limit)


def build_expansion_queries(topic_pack, target_date, phase="query_expansion", limit=16):
    topic_pack = topic_pack or {}
    topic_name = str(topic_pack.get("topic_name") or topic_pack.get("title") or "").strip()
    daily_queries = list(topic_pack.get("daily_queries", []) or [])
    domestic = list(topic_pack.get("domestic_company_terms", []) or [])
    global_terms = list(topic_pack.get("global_company_terms", []) or [])
    product_terms = list(topic_pack.get("product_terms", []) or [])
    technology_terms = list(topic_pack.get("technology_terms", []) or [])
    supply_chain_terms = list(topic_pack.get("supply_chain_terms", []) or [])
    action_terms = list(topic_pack.get("action_terms", []) or [])
    boost_terms = list(topic_pack.get("boost_terms", []) or []) + technology_terms + action_terms
    required = list(topic_pack.get("required_terms", []) or [])
    english_terms = list(topic_pack.get("english_terms", []) or [])
    media_domains = list(topic_pack.get("media_domains", []) or [])
    year = target_date.year if isinstance(target_date, datetime.date) else str(target_date)[:4]

    queries = []
    if phase == "source_diversity":
        source_domains = _dedupe_preserve_order(media_domains + [
            "ithome.com", "cls.cn", "ijiwei.com", "qbitai.com", "jiqizhixin.com", "zhidx.com",
            "gasgoo.com", "autohome.com.cn", "dongchedi.com", "mydrivers.com", "cnmo.com",
            "leikeji.com", "ifanr.com", "infoq.cn", "51cto.com", "42how.com", "xchuxing.com",
            "cinno.com.cn", "trendforce.cn", "display.ofweek.com", "laoyaoba.com",
        ], limit=28)
        base = " ".join(_dedupe_preserve_order((domestic[:3] + boost_terms[:4] + required[:3]), limit=8))
        if not base:
            base = topic_name
        queries.extend(f"{base} 今日 site:{domain}" for domain in source_domains)
        queries.extend(f"{company} {topic_name} 官方 发布 {year}" for company in domestic[:4])
        return _dedupe_preserve_order(queries, limit=limit)

    if phase == "time_window_expansion":
        queries.extend(f"近一周 {query}" for query in daily_queries[:8])
        queries.extend(f"{company} {topic_name} 近一周 发布 参数 供应链" for company in domestic[:8])
        queries.extend(f"{product} {topic_name} 近一周 发布 更新 参数" for product in product_terms[:8])
        queries.extend(f"{term} {topic_name} 近一周 价格 销量 量产" for term in (boost_terms + supply_chain_terms)[:10])
        queries.extend(f"{term} {topic_name} latest update this week" for term in (global_terms + english_terms)[:6])
        return _dedupe_preserve_order(queries, limit=limit)

    queries.extend(daily_queries[:8])
    queries.extend(f"今日 {company} {topic_name} 参数 发布 价格 供应链" for company in domestic[:8])
    queries.extend(f"今日 {product} {topic_name} 发布 更新 参数" for product in product_terms[:8])
    queries.extend(f"今日 {term} {topic_name} 硬件 参数 销量 量产" for term in boost_terms[:10])
    queries.extend(f"今日 {term} {topic_name} 供应链 订单 量产" for term in supply_chain_terms[:8])
    queries.extend(f"{term} {topic_name} latest news today specs supply chain" for term in global_terms[:5])
    queries.extend(english_terms[:6])
    queries.extend(f"{term} 今日 {topic_name}" for term in required[:6])
    return _dedupe_preserve_order(queries, limit=limit)


def expand_exa_queries_for_topic(topic_pack, missing_count, target_date, limit=20):
    requested = max(limit, int(missing_count or 1) * 6)
    phase_batches = [
        build_expansion_queries(topic_pack, target_date, phase="query_expansion", limit=requested),
        build_expansion_queries(topic_pack, target_date, phase="source_diversity", limit=requested),
        build_expansion_queries(topic_pack, target_date, phase="time_window_expansion", limit=requested),
    ]
    interleaved = []
    for idx in range(max(len(batch) for batch in phase_batches if batch)):
        for batch in phase_batches:
            if idx < len(batch):
                interleaved.append(batch[idx])
    return _dedupe_preserve_order(interleaved, limit=requested)


def _next_time_window(time_window):
    key = str(time_window or "72h").lower()
    if key in {"today", "24h"}:
        return "72h"
    if key == "72h":
        return "7d"
    return key


def _call_expansion_search(search_fn, query, topic_pack, time_window):
    try:
        return search_fn(query, topic_pack, time_window) or []
    except TypeError:
        return search_fn(query, topic_pack) or []


def event_score(event):
    if not event:
        return 0.0
    level_bonus = {"confirmed": 100, "likely": 70, "weak": 35, "rumor": 20}.get(event.confidence_level, 0)
    source_bonus = min(event.independent_source_count, 5) * 8
    official_bonus = event.official_source_count * 8
    domestic_bonus = min(event.domestic_source_count, 4) * 3
    return level_bonus + source_bonus + official_bonus + domestic_bonus + float(event.confidence_score or 0) * 10


def build_topic_output(
    topic_verified,
    min_events=CONSUMER_DAILY_MIN_EVENTS_PER_TOPIC,
    target_events=CONSUMER_DAILY_TARGET_EVENTS_PER_TOPIC,
    watchlist_limit=CONSUMER_DAILY_WATCHLIST_LIMIT,
):
    confirmed = sorted(topic_verified.confirmed_events or [], key=event_score, reverse=True)
    likely = sorted(topic_verified.likely_events or [], key=event_score, reverse=True)
    main_events = (confirmed + likely)[:target_events]
    watchlist = []
    if len(main_events) < min_events:
        watchlist = sorted(topic_verified.watchlist_events or [], key=event_score, reverse=True)[:watchlist_limit]
    reason = topic_verified.insufficient_reason
    if len(main_events) < min_events and not reason:
        reason = f"当前时间窗内 confirmed + likely 仅 {len(main_events)} 条，低于最低 {min_events} 条。"
    return TopicOutput(
        main_events=main_events,
        watchlist_events=watchlist,
        insufficient_warning=len(main_events) < min_events,
        expansion_attempts=list(topic_verified.expansion_attempts or []),
        insufficient_reason=reason,
    )


def _sort_events(events):
    return sorted(
        events or [],
        key=lambda item: (
            item.confidence_level == "confirmed",
            item.confidence_level == "likely",
            event_score(item),
            item.independent_source_count,
        ),
        reverse=True,
    )


def _assemble_topic_verified_events(
    topic_pack,
    final_events,
    rejected,
    time_window,
    min_events=CONSUMER_DAILY_MIN_EVENTS_PER_TOPIC,
    expansion_attempts=None,
    insufficient_reason="",
):
    final_events = _sort_events(final_events)
    confirmed = [event for event in final_events if event.confidence_level == "confirmed"]
    likely = [event for event in final_events if event.confidence_level == "likely"]
    watchlist = [event for event in final_events if event.confidence_level in WATCHLIST_LEVELS]
    rejected_summary = [
        RejectedEventSummary(
            title=event.normalized_title,
            topic_id=event.topic_id,
            confidence_level=event.confidence_level,
            reasons=event.rejection_reasons or ["evidence_not_enough"],
            source_domains=event.source_domains,
        )
        for event in final_events
        if event.confidence_level not in CONFIRMED_LEVELS
    ]
    rejected_summary.extend((rejected or [])[:30])

    formal_count = len(confirmed) + len(likely)
    warnings = []
    if formal_count < min_events:
        warnings.append(f"本专题 confirmed/likely 事件不足 {min_events} 条，已触发扩搜或提供待跟踪线索。")
    if watchlist and formal_count < min_events:
        warnings.append("待跟踪线索仅用于提示关注，未满足正式多源验证标准。")
    if _topic_primary_36kr_ratio(confirmed + likely) > 0.2:
        warnings.append("source diversity warning：该专题 36氪作为主来源比例超过 20%。")
    if formal_count < min_events and not insufficient_reason:
        insufficient_reason = f"当前时间窗 {time_window} 内 confirmed + likely 仅 {formal_count} 条。"

    return TopicVerifiedEvents(
        topic_id=str(topic_pack.get("id") or topic_pack.get("title") or ""),
        topic_name=str(topic_pack.get("title") or topic_pack.get("topic_name") or ""),
        time_window=str(time_window),
        confirmed_events=confirmed,
        likely_events=likely,
        watchlist_events=watchlist,
        rejected_summary=rejected_summary,
        warnings=warnings,
        expansion_attempts=list(expansion_attempts or []),
        insufficient_reason=insufficient_reason if formal_count < min_events else "",
    )


def _build_topic_verified_from_results(
    topic_pack,
    results,
    target_date,
    time_window,
    registry,
    min_events=CONSUMER_DAILY_MIN_EVENTS_PER_TOPIC,
    expansion_attempts=None,
    insufficient_reason="",
):
    candidates, rejected = _build_candidates(results, topic_pack, target_date, time_window, registry)
    final_events = cluster_articles_into_events(candidates, topic_pack, target_date, time_window, registry=registry)
    return _assemble_topic_verified_events(
        topic_pack,
        final_events,
        rejected,
        time_window,
        min_events=min_events,
        expansion_attempts=expansion_attempts,
        insufficient_reason=insufficient_reason,
    )


def _collect_query_results(search_fn, queries, topic_pack, time_window, seen_urls):
    collected = []
    for query in queries or []:
        try:
            batch = _call_expansion_search(search_fn, query, topic_pack, time_window) or []
        except Exception:
            batch = []
        for result in batch:
            url = str((result or {}).get("url") or "").strip()
            if url and url in seen_urls:
                continue
            if url:
                seen_urls.add(url)
            enriched = dict(result or {})
            enriched["query"] = query
            collected.append(enriched)
    return collected


def ensure_min_events_per_topic(
    topic_pack,
    current_topic_events,
    target_date,
    current_results,
    verification_search_fn=None,
    min_events=CONSUMER_DAILY_MIN_EVENTS_PER_TOPIC,
    target_events=CONSUMER_DAILY_TARGET_EVENTS_PER_TOPIC,
    expansion_query_limit=14,
    registry=None,
):
    if not verification_search_fn:
        return current_topic_events

    registry = registry or load_source_registry()
    combined_results = list(current_results or [])
    seen_urls = {str((result or {}).get("url") or "").strip() for result in combined_results if (result or {}).get("url")}
    topic_verified = current_topic_events
    expansion_attempts = list(topic_verified.expansion_attempts or [])
    effective_window = topic_verified.time_window

    for phase in ("query_expansion", "source_diversity"):
        if len(build_topic_output(topic_verified, min_events=min_events, target_events=target_events).main_events) >= min_events:
            break
        queries = build_expansion_queries(topic_pack, target_date, phase=phase, limit=expansion_query_limit)
        added = _collect_query_results(verification_search_fn, queries, topic_pack, effective_window, seen_urls)
        expansion_attempts.append(f"{phase}: queries={len(queries)}, results={len(added)}, window={effective_window}")
        combined_results.extend(added)
        topic_verified = _build_topic_verified_from_results(
            topic_pack,
            combined_results,
            target_date,
            effective_window,
            registry,
            min_events=min_events,
            expansion_attempts=expansion_attempts,
        )

    if len(build_topic_output(topic_verified, min_events=min_events, target_events=target_events).main_events) < min_events:
        expanded_window = _next_time_window(effective_window)
        if expanded_window != effective_window:
            queries = build_expansion_queries(topic_pack, target_date, phase="time_window_expansion", limit=expansion_query_limit)
            added = _collect_query_results(verification_search_fn, queries, topic_pack, expanded_window, seen_urls)
            expansion_attempts.append(f"time_window_expansion: queries={len(queries)}, results={len(added)}, window={expanded_window}")
            combined_results.extend(added)
            effective_window = expanded_window
            topic_verified = _build_topic_verified_from_results(
                topic_pack,
                combined_results,
                target_date,
                effective_window,
                registry,
                min_events=min_events,
                expansion_attempts=expansion_attempts,
            )

    if len(build_topic_output(topic_verified, min_events=min_events, target_events=target_events).main_events) < min_events:
        reason = f"扩搜后 confirmed + likely 仍不足 {min_events} 条；已保留 weak 作为待跟踪线索。"
        topic_verified.insufficient_reason = reason
        if reason not in topic_verified.warnings:
            topic_verified.warnings.append(reason)
    return topic_verified


def build_verified_topic_events(
    topic_pack,
    discovery_results,
    target_date,
    time_window="72h",
    verification_search_fn=None,
    max_initial_events=8,
    verification_queries_per_event=5,
    min_events=CONSUMER_DAILY_MIN_EVENTS_PER_TOPIC,
    target_events=CONSUMER_DAILY_TARGET_EVENTS_PER_TOPIC,
    expansion_query_limit=14,
):
    registry = load_source_registry()
    resolved_window = normalize_time_window(topic_pack, time_window)
    discovery_candidates, _ = _build_candidates(discovery_results, topic_pack, target_date, resolved_window, registry)
    initial_events = sorted(
        cluster_articles_into_events(discovery_candidates, topic_pack, target_date, resolved_window, registry=registry),
        key=lambda item: (item.confidence_score, item.independent_source_count),
        reverse=True,
    )

    verification_results = []
    if verification_search_fn:
        seen_urls = {item.url for item in discovery_candidates if item.url}
        for event in initial_events[:max_initial_events]:
            queries = build_verification_queries(event, topic_pack, target_date, limit=verification_queries_per_event)
            verification_results.extend(_collect_query_results(verification_search_fn, queries, topic_pack, resolved_window, seen_urls))

    combined_results = list(discovery_results or []) + verification_results
    topic_verified = _build_topic_verified_from_results(
        topic_pack,
        combined_results,
        target_date,
        resolved_window,
        registry,
        min_events=min_events,
    )
    return ensure_min_events_per_topic(
        topic_pack,
        topic_verified,
        target_date,
        combined_results,
        verification_search_fn=verification_search_fn,
        min_events=min_events,
        target_events=target_events,
        expansion_query_limit=expansion_query_limit,
        registry=registry,
    )


def _build_candidates(results, topic_pack, target_date, time_window, registry):
    candidates = []
    rejected = []
    seen = set()
    for result in results or []:
        raw = raw_result_from_search_result(result, topic_pack, query=(result or {}).get("query", ""))
        key = raw.url.lower() if raw.url else raw.title.lower()
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        article = candidate_from_raw(raw, topic_pack, target_date, time_window, registry=registry)
        if article.rejection_reasons:
            rejected.append(
                RejectedEventSummary(
                    title=article.title,
                    topic_id=article.topic_id,
                    confidence_level=(
                        "stale"
                        if any(reason.startswith("stale") or reason.endswith("out_of_window") or "not_published_today" in reason for reason in article.rejection_reasons)
                        else "rejected"
                    ),
                    reasons=article.rejection_reasons,
                    source_domains=[article.domain] if article.domain else [],
                )
            )
            continue
        candidates.append(article)
    return candidates, rejected


def _topic_primary_36kr_ratio(events):
    if not events:
        return 0.0
    primary_36kr = 0
    for event in events:
        primary = event.evidence_articles[0] if event.evidence_articles else None
        if primary and primary.domain.endswith("36kr.com"):
            primary_36kr += 1
    return primary_36kr / max(len(events), 1)


def build_verified_news_package(topic_verified_events, target_date, time_window, search_provider="exa"):
    target = target_date.isoformat() if isinstance(target_date, datetime.date) else str(target_date)[:10]
    return VerifiedNewsPackage(
        target_date=target,
        time_window=str(time_window),
        topics=list(topic_verified_events or []),
        search_provider=str(search_provider or "exa"),
    )


def verified_package_to_deepseek_material(package):
    payload = dataclass_to_dict(package)
    for topic in payload.get("topics", []):
        topic["confirmed_events"] = [_event_for_llm(event) for event in topic.get("confirmed_events", [])]
        topic["likely_events"] = [_event_for_llm(event) for event in topic.get("likely_events", [])]
        topic["watchlist_events"] = [_event_for_llm(event) for event in topic.get("watchlist_events", [])]
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _event_for_llm(event_dict):
    event = dict(event_dict)
    evidence = []
    for article in event.get("evidence_articles", []) or []:
        evidence.append(
            {
                "title": article.get("title"),
                "url": article.get("url"),
                "domain": article.get("domain"),
                "source_name": article.get("source_name"),
                "source_type": article.get("source_type"),
                "source_tier": article.get("source_tier"),
                "published_at": article.get("published_at_page") or article.get("published_at_search"),
                "claims": article.get("extracted_claims", [])[:3],
            }
        )
    event["evidence_articles"] = evidence
    return event


def event_blueprints_from_verified_topic(topic_verified, limit=8, events=None):
    events = list(events) if events is not None else (topic_verified.confirmed_events + topic_verified.likely_events)
    events = events[:limit]
    blueprints = []
    for event in events:
        primary = event.evidence_articles[0] if event.evidence_articles else None
        blueprints.append(
            {
                "event_id": event.event_id,
                "event": event.normalized_title,
                "date": event.event_date or event.latest_seen_at or "",
                "source": primary.source_name if primary else "多源验证",
                "source_url": primary.url if primary else "",
                "keywords": _dedupe_preserve_order(event.companies + event.products + event.technologies, limit=8),
                "confidence_level": event.confidence_level,
                "independent_source_count": event.independent_source_count,
            }
        )
    return blueprints


def raw_results_from_verified_topic(topic_verified, events=None):
    rows = []
    event_list = list(events) if events is not None else (topic_verified.confirmed_events + topic_verified.likely_events)
    for event in event_list:
        for article in event.evidence_articles:
            rows.append(
                {
                    "title": article.title,
                    "url": article.url,
                    "content": article.cleaned_snippet,
                    "source": article.source_name,
                    "published_at_resolved": article.published_at_page or article.published_at_search or event.event_date or "",
                    "provider": article.provider,
                    "event_id": event.event_id,
                    "confidence_level": event.confidence_level,
                    "independent_source_count": event.independent_source_count,
                    "event_time_window": event.time_window,
                }
            )
    return rows


def enrich_news_items_with_verified_events(news_items, events):
    event_map = {event.event_id: event for event in events or []}
    filtered = []
    for item in news_items or []:
        event_id = getattr(item, "event_id", "") if not isinstance(item, dict) else item.get("event_id", "")
        event = event_map.get(event_id)
        if not event or event.confidence_level not in CONFIRMED_LEVELS:
            continue
        evidence_names = event.source_names[:5]
        evidence_urls = [article.url for article in event.evidence_articles[:5] if article.url]
        source_label = " / ".join(evidence_names[:3]) or "多源验证"
        if isinstance(item, dict):
            item["source"] = source_label
            item["date_check"] = event.event_date or item.get("date_check", "")
            item["confidence_level"] = event.confidence_level
            item["independent_source_count"] = event.independent_source_count
            item["evidence_sources"] = evidence_names
            item["evidence_urls"] = evidence_urls
            item["verified_event_summary"] = event.event_summary
            item["event_time_window"] = event.time_window
        else:
            item.source = source_label
            item.date_check = event.event_date or item.date_check
            setattr(item, "confidence_level", event.confidence_level)
            setattr(item, "independent_source_count", event.independent_source_count)
            setattr(item, "evidence_sources", evidence_names)
            setattr(item, "evidence_urls", evidence_urls)
            setattr(item, "verified_event_summary", event.event_summary)
            setattr(item, "event_time_window", event.time_window)
        filtered.append(item)
    return filtered


def validate_consumer_daily_quality(package, min_events_per_topic=CONSUMER_DAILY_MIN_EVENTS_PER_TOPIC):
    topics = package.topics if isinstance(package, VerifiedNewsPackage) else []
    all_events = []
    weak_count = 0
    rejected_count = 0
    stale_events = []
    events_with_36kr_only = []
    topics_with_insufficient = []
    topic_event_counts = {}
    topic_confirmed_counts = {}
    topic_likely_counts = {}
    topic_watchlist_counts = {}
    expansion_attempts = {}
    insufficient_reasons = {}
    warnings = []
    domain_counts = {}

    for topic in topics:
        topic_name = topic.topic_name or topic.topic_id
        output = build_topic_output(topic, min_events=min_events_per_topic)
        formal = output.main_events
        all_events.extend(formal)
        topic_event_counts[topic_name] = len(formal)
        topic_confirmed_counts[topic_name] = sum(1 for event in formal if event.confidence_level == "confirmed")
        topic_likely_counts[topic_name] = sum(1 for event in formal if event.confidence_level == "likely")
        topic_watchlist_counts[topic_name] = len(output.watchlist_events)
        expansion_attempts[topic_name] = list(topic.expansion_attempts or [])
        if len(formal) < min_events_per_topic:
            topics_with_insufficient.append(topic.topic_name)
            insufficient_reasons[topic_name] = topic.insufficient_reason or output.insufficient_reason
        weak_count += len(topic.watchlist_events or [])
        for rejected in topic.rejected_summary:
            if rejected.confidence_level == "stale":
                stale_events.append(rejected.title)
            elif rejected.confidence_level not in WATCHLIST_LEVELS:
                rejected_count += 1
        for event in formal:
            for domain in event.source_domains:
                domain_counts[domain] = domain_counts.get(domain, 0) + 1
            if event.source_domains and all(domain.endswith("36kr.com") for domain in event.source_domains):
                events_with_36kr_only.append(event.normalized_title)

    total_events = len(all_events)
    confirmed_events = sum(1 for event in all_events if event.confidence_level == "confirmed")
    likely_events = sum(1 for event in all_events if event.confidence_level == "likely")
    total_sources = sum(domain_counts.values())
    max_single_source_ratio = max(domain_counts.values(), default=0) / max(total_sources, 1)
    source_diversity_score = 1.0 - max_single_source_ratio if total_sources else 0.0

    if events_with_36kr_only:
        warnings.append("存在 36氪单源事件，已阻止进入正式日报。")
    if topics_with_insufficient:
        warnings.append("部分专题 confirmed/likely 事件不足：" + "、".join(topics_with_insufficient))
    if any(expansion_attempts.values()):
        warnings.append("已对新闻数量不足专题触发自动扩搜；请结合每个专题 expansion_attempts 复核召回质量。")
    if max_single_source_ratio > 0.45:
        warnings.append("来源集中度偏高，需要人工复核 source diversity。")
    if stale_events:
        warnings.append("存在旧闻或时间不一致候选，已降级/剔除。")

    return QualityReport(
        total_events=total_events,
        confirmed_events=confirmed_events,
        likely_events=likely_events,
        weak_events=weak_count,
        rejected_events=rejected_count,
        source_diversity_score=round(source_diversity_score, 4),
        max_single_source_ratio=round(max_single_source_ratio, 4),
        events_with_36kr_only=events_with_36kr_only,
        stale_events=stale_events[:20],
        topics_with_insufficient_events=topics_with_insufficient,
        topic_event_counts=topic_event_counts,
        topic_confirmed_counts=topic_confirmed_counts,
        topic_likely_counts=topic_likely_counts,
        topic_watchlist_counts=topic_watchlist_counts,
        topics_below_minimum=topics_with_insufficient,
        expansion_attempts=expansion_attempts,
        insufficient_reasons=insufficient_reasons,
        warnings=warnings,
    )
