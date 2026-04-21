from copy import deepcopy
import difflib
import re


GENERIC_NOISE_TERMS = [
    "stocks to watch",
    "market wrap",
    "market open",
    "live updates",
    "newsletter",
    "week in review",
    "podcast",
    "roundup",
    "what to know",
    "top stories",
]

FRONTIER_TERMS = [
    "ai", "model", "chip", "gpu", "tpu", "cuda", "blackwell", "server", "silicon",
    "product", "launch", "release", "hardware", "supply chain", "data center", "cloud",
    "android", "pixel", "iphone", "ios", "mac", "vision pro", "siri", "gemini",
    "waymo", "robotaxi", "autonomous", "robotics", "api", "enterprise", "satellite",
    "starlink", "starship", "kuiper", "headset", "smart glasses", "xr", "vr"
]

BUSINESS_TERMS = [
    "earnings", "guidance", "partnership", "acquisition", "funding", "contract",
    "order", "orders", "deliveries", "revenue", "margin", "customer", "deal"
]

LEGAL_TERMS = [
    "lawsuit", "legal", "lawyer", "attorney", "court", "judge", "trial", "appeal",
    "verdict", "settlement", "fine", "penalty", "complaint", "privacy", "antitrust",
    "doj", "ftc", "litigation", "class action", "injunction"
]

POLICY_TERMS = [
    "regulation", "regulator", "policy", "government", "ban", "probe", "investigation",
    "compliance", "enforcement", "white house", "executive order"
]

SOCIAL_TERMS = [
    "adult", "teen", "children", "social media", "creator", "election", "speech",
    "content moderation", "misinformation", "ban on"
]

STOPWORDS = {
    "latest", "news", "today", "update", "company", "inc", "corp", "group", "shares",
    "says", "report", "reported", "reportedly"
}


MEGACAP_QUERY_PACKS = {
    "apple": {
        "aliases": ["apple", "苹果", "aapl", "iphone", "ios", "mac", "vision pro"],
        "domains": [
            "apple.com", "macrumors.com", "9to5mac.com", "appleinsider.com",
            "theverge.com", "techcrunch.com", "bloomberg.com", "cnbc.com", "reuters.com",
            "ithome.com", "ijiwei.com", "36kr.com",
        ],
        "keywords": [
            "iphone", "ios", "ipad", "mac", "vision pro", "app store", "wwdc",
            "siri", "apple intelligence", "supply chain", "chip", "silicon",
            "foldable", "folding iphone", "iphone fold", "hinge", "utg",
            "cover window", "modem", "packaging", "camera module", "china"
        ],
        "priority_terms": [
            "launch", "release", "ai", "siri", "wwdc", "chip", "supply chain",
            "vision pro", "data center", "foldable", "hinge", "utg",
            "modem", "camera module", "earnings", "guidance"
        ],
        "deprioritize_terms": ["privacy", "lawsuit", "court", "judge", "lawyer", "epic", "antitrust"],
        "queries": [
            "{topic}",
            "{topic} iPhone iOS Mac latest",
            "{topic} Apple Intelligence Siri WWDC hardware latest",
            "{topic} foldable iPhone hinge UTG supply chain latest",
            "{topic} chip modem packaging camera module latest",
            "{topic} Vision Pro display optics supply chain latest",
            "{topic} China supply chain manufacturing latest",
        ],
    },
    "google": {
        "aliases": ["google", "alphabet", "谷歌", "gemini", "android", "pixel"],
        "domains": [
            "blog.google", "blog.google.com", "9to5google.com", "androidauthority.com",
            "theverge.com", "techcrunch.com", "bloomberg.com", "cnbc.com", "reuters.com",
            "ithome.com", "36kr.com", "tomshardware.com",
        ],
        "keywords": [
            "gemini", "android", "pixel", "search", "chrome", "waymo",
            "youtube", "cloud", "tpu", "data center", "tensor", "ironwood",
            "trillium", "tpupod", "accelerator", "pixel fold", "hardware"
        ],
        "priority_terms": [
            "launch", "release", "gemini", "android", "pixel", "cloud", "tpu",
            "tensor", "ironwood", "trillium", "data center", "waymo",
            "pixel fold", "hardware", "earnings", "guidance"
        ],
        "deprioritize_terms": ["privacy", "lawsuit", "lawyer", "court", "judge", "fine", "antitrust", "ban"],
        "queries": [
            "{topic}",
            "{topic} Gemini Search Chrome hardware latest",
            "{topic} Android Pixel Tensor Pixel Fold latest",
            "{topic} Cloud TPU Ironwood Trillium data center latest",
            "{topic} TPU server accelerator capex latest",
            "{topic} Waymo autonomous driving latest",
            "{topic} earnings privacy antitrust latest",
        ],
    },
    "amazon": {
        "aliases": ["amazon", "亚马逊", "aws", "kuiper", "prime"],
        "domains": [
            "aboutamazon.com", "amazon.com", "cnbc.com", "techcrunch.com",
            "bloomberg.com", "theverge.com", "reuters.com", "36kr.com",
        ],
        "keywords": [
            "aws", "bedrock", "prime", "retail", "logistics", "kuiper",
            "fulfillment", "data center", "satellite", "trainium",
            "inferentia", "warehouse robotics", "sortation", "terminal"
        ],
        "priority_terms": [
            "aws", "bedrock", "data center", "satellite", "kuiper", "launch",
            "trainium", "inferentia", "warehouse robotics", "logistics",
            "partnership", "earnings", "guidance"
        ],
        "deprioritize_terms": ["lawsuit", "union", "court", "judge", "complaint", "antitrust"],
        "queries": [
            "{topic}",
            "{topic} AWS Trainium Inferentia data center latest",
            "{topic} Kuiper satellite terminal launch latest",
            "{topic} warehouse robotics logistics automation latest",
            "{topic} earnings guidance capex latest",
            "{topic} antitrust labor regulation latest",
        ],
    },
    "openai": {
        "aliases": ["openai", "open ai", "chatgpt", "gpt"],
        "domains": [
            "openai.com", "techcrunch.com", "theverge.com", "venturebeat.com",
            "wired.com", "bloomberg.com", "cnbc.com", "reuters.com",
        ],
        "keywords": [
            "chatgpt", "gpt", "api", "enterprise", "model release",
            "microsoft", "stargate", "data center", "chips"
        ],
        "priority_terms": [
            "launch", "release", "api", "enterprise", "model", "chips",
            "data center", "funding", "partnership", "acquisition"
        ],
        "deprioritize_terms": ["copyright", "lawsuit", "court", "judge", "legal", "policy"],
        "queries": [
            "{topic}",
            "{topic} ChatGPT GPT API enterprise latest",
            "{topic} model release latest",
            "{topic} chips data center latest",
            "{topic} funding Microsoft partnership latest",
            "{topic} policy copyright latest",
        ],
    },
    "meta": {
        "aliases": ["meta", "facebook", "脸书", "llama", "quest", "instagram", "threads"],
        "domains": [
            "about.fb.com", "meta.com", "theverge.com", "techcrunch.com",
            "uploadvr.com", "roadtovr.com", "bloomberg.com", "cnbc.com", "reuters.com",
            "ithome.com", "36kr.com",
        ],
        "keywords": [
            "llama", "quest", "reality labs", "ray-ban", "smart glasses",
            "ads", "threads", "instagram", "data center", "orion",
            "ar glasses", "custom silicon", "display", "optics"
        ],
        "priority_terms": [
            "llama", "quest", "smart glasses", "reality labs", "launch", "release",
            "orion", "custom silicon", "data center", "chips", "earnings"
        ],
        "deprioritize_terms": ["privacy", "lawsuit", "court", "judge", "ban", "antitrust"],
        "queries": [
            "{topic}",
            "{topic} Llama AI model latest",
            "{topic} Quest Ray-Ban smart glasses hardware latest",
            "{topic} Orion AR display optics latest",
            "{topic} data center custom silicon latest",
            "{topic} ad business earnings latest",
            "{topic} privacy regulation latest",
        ],
    },
    "nvidia": {
        "aliases": ["nvidia", "英伟达", "nvda", "blackwell", "vera rubin", "rubin", "cuda", "黄仁勋"],
        "domains": [
            "nvidianews.nvidia.com", "nvidia.com", "tomshardware.com", "anandtech.com",
            "theverge.com", "cnbc.com", "bloomberg.com", "reuters.com",
        ],
        "keywords": [
            "blackwell", "vera rubin", "rubin", "gpu", "cuda", "h200", "b200", "data center",
            "server", "robotics", "automotive", "cloud"
        ],
        "priority_terms": [
            "gpu", "blackwell", "vera rubin", "rubin", "server", "data center", "cloud", "launch",
            "release", "partnership", "robotics", "automotive", "earnings"
        ],
        "deprioritize_terms": ["lawsuit", "court", "judge", "fine", "investigation"],
        "queries": [
            "{topic}",
            "{topic} GPU Blackwell AI server latest",
            "{topic} Vera Rubin AI rack latest",
            "{topic} data center cloud partnership latest",
            "{topic} robotics automotive latest",
            "{topic} earnings guidance latest",
            "{topic} export restriction regulation latest",
        ],
    },
    "tesla": {
        "aliases": ["tesla", "特斯拉", "tsla", "fsd", "robotaxi", "optimus", "megapack"],
        "domains": [
            "tesla.com", "electrek.co", "insideevs.com", "cnbc.com", "reuters.com", "bloomberg.com",
            "gasgoo.com", "d1ev.com", "36kr.com", "wallstreetcn.com",
        ],
        "keywords": [
            "fsd", "robotaxi", "autopilot", "deliveries", "megapack", "optimus",
            "energy", "china", "berlin", "austin", "fsd china", "china rollout",
            "approval", "pilot", "city navigation", "supervised fsd", "shanghai"
        ],
        "priority_terms": [
            "robotaxi", "fsd", "autonomy", "optimus", "energy", "megapack",
            "deliveries", "earnings", "launch", "robotics", "china rollout",
            "approval", "pilot", "local deployment", "shanghai"
        ],
        "deprioritize_terms": ["lawsuit", "court", "judge", "recall", "probe"],
        "queries": [
            "{topic}",
            "{topic} FSD China rollout approval pilot latest",
            "{topic} China supervised FSD city navigation latest",
            "{topic} Optimus robotics supply chain latest",
            "{topic} energy Megapack Shanghai factory latest",
            "{topic} deliveries earnings margins China latest",
            "{topic} recall regulation latest",
        ],
    },
    "trump": {
        "aliases": ["trump", "donald trump", "特朗普", "川普", "trump administration"],
        "domains": [
            "whitehouse.gov", "reuters.com", "apnews.com", "cnbc.com", "bloomberg.com", "wsj.com",
            "axios.com", "politico.com", "ft.com", "aljazeera.com",
        ],
        "focus_lines": [
            "优先覆盖关税、贸易、芯片政策、白宫行政令、中东局势、能源、制裁、外交和国防等不同方向。",
            "如果当天主线在中东、制裁、油价或外交，不要因为它们不属于硬件新闻就删掉。",
        ],
        "keywords": [
            "tariff", "white house", "executive order", "trade policy", "chips", "china", "autos",
            "middle east", "israel", "iran", "gaza", "red sea", "oil", "sanctions", "ceasefire", "defense"
        ],
        "priority_terms": [
            "tariff", "trade", "chips", "ai", "autos", "executive order", "policy",
            "middle east", "israel", "iran", "gaza", "oil", "sanctions", "defense", "ceasefire"
        ],
        "deprioritize_terms": ["lawsuit", "court", "lawyer", "campaign", "speech"],
        "queries": [
            "{topic}",
            "{topic} tariff trade policy latest",
            "{topic} chips AI policy latest",
            "{topic} autos China tariff latest",
            "{topic} executive order White House latest",
            "{topic} Middle East Israel Iran Gaza latest",
            "{topic} oil sanctions defense ceasefire latest",
            "{topic} lawsuit court latest",
        ],
    },
    "anthropic": {
        "aliases": ["anthropic", "claude", "anthropic ai", "克劳德"],
        "domains": [
            "anthropic.com", "techcrunch.com", "theverge.com", "venturebeat.com",
            "bloomberg.com", "cnbc.com", "reuters.com",
        ],
        "keywords": ["claude", "model", "enterprise", "api", "amazon", "google", "data center", "chips"],
        "priority_terms": ["claude", "model", "launch", "release", "enterprise", "api", "chips", "partnership", "funding"],
        "deprioritize_terms": ["lawsuit", "court", "judge", "policy", "copyright"],
        "queries": [
            "{topic}",
            "{topic} Claude model latest",
            "{topic} enterprise API latest",
            "{topic} chips data center partnership latest",
            "{topic} Amazon Google funding latest",
            "{topic} policy legal latest",
        ],
    },
    "spacex": {
        "aliases": ["spacex", "space x", "星链", "starlink", "starship"],
        "domains": ["spacex.com", "spacenews.com", "satnews.com", "teslarati.com", "cnbc.com", "reuters.com"],
        "keywords": ["starship", "starlink", "direct-to-cell", "launch", "nasa", "defense", "contract", "satellite"],
        "priority_terms": ["launch", "starship", "starlink", "satellite", "contract", "nasa", "defense", "funding", "valuation"],
        "deprioritize_terms": ["lawsuit", "court", "judge", "license dispute"],
        "queries": [
            "{topic}",
            "{topic} Starship launch latest",
            "{topic} Starlink direct-to-cell latest",
            "{topic} NASA defense contract latest",
            "{topic} valuation funding latest",
            "{topic} launch license regulation latest",
        ],
    },
}


def _dedupe(items):
    merged = []
    seen = set()
    for item in items or []:
        value = str(item or "").strip()
        if not value:
            continue
        key = value.lower()
        if key in seen:
            continue
        merged.append(value)
        seen.add(key)
    return merged


def _normalize_topic(topic):
    return str(topic or "").strip().lower()


def _normalize_text(text):
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", (text or "").lower().strip())


def _extract_cjk_bigrams(text):
    chars = [ch for ch in (text or "") if re.match(r"[\u4e00-\u9fff]", ch)]
    if len(chars) < 2:
        return set(chars)
    return {"".join(chars[idx:idx + 2]) for idx in range(len(chars) - 1)}


def _tokenize(text):
    words = {token.lower() for token in re.findall(r"[a-z0-9]{2,}", text or "") if token.lower() not in STOPWORDS}
    return words | _extract_cjk_bigrams(text)


def _format_hint_list(values, limit):
    return "、".join(_dedupe(values)[:limit])


def get_company_query_pack(topic):
    normalized = _normalize_topic(topic)
    for pack_name, pack in MEGACAP_QUERY_PACKS.items():
        aliases = [_normalize_topic(alias) for alias in pack.get("aliases", [])]
        if normalized == pack_name or normalized in aliases:
            payload = deepcopy(pack)
            payload["id"] = pack_name
            payload["topic"] = topic
            payload["display_name"] = topic
            return payload

    return {
        "id": "generic",
        "topic": topic,
        "display_name": topic,
        "aliases": [topic],
        "domains": [],
        "keywords": [topic],
        "priority_terms": [
            "launch", "release", "product", "hardware", "ai", "chip", "supply chain",
            "manufacturing", "data center", "partnership", "earnings", "guidance",
            "china rollout", "pilot", "capex"
        ],
        "deprioritize_terms": ["lawsuit", "court", "judge", "lawyer", "privacy", "ban"],
        "queries": [
            "{topic}",
            "{topic} product hardware launch latest",
            "{topic} AI chip data center latest",
            "{topic} supply chain manufacturing China latest",
            "{topic} earnings guidance capex latest",
            "{topic} regulation lawsuit latest",
        ],
    }


def _contains_cjk(text):
    return bool(re.search(r"[\u4e00-\u9fff]", str(text or "")))


def _get_primary_aliases(pack):
    configured = [str(item or "").strip() for item in pack.get("primary_aliases", []) if str(item or "").strip()]
    if configured:
        return _dedupe(configured)

    topic_value = str(pack.get("topic", "") or pack.get("display_name", "") or "").strip()
    aliases = [str(item or "").strip() for item in pack.get("aliases", []) if str(item or "").strip()]
    keyword_norms = {_normalize_topic(token) for token in pack.get("keywords", []) or []}
    primary = []
    for alias in aliases:
        alias_norm = _normalize_topic(alias)
        if alias_norm and alias_norm not in keyword_norms:
            primary.append(alias)
    if topic_value:
        primary.insert(0, topic_value)
    primary.insert(0, pack.get("id", ""))
    primary = [item for item in _dedupe(primary) if item]
    return primary[:5] if primary else aliases[:3]


def _resolve_query_topic(topic, pack):
    topic_value = str(topic or "").strip()
    if not _contains_cjk(topic_value):
        return topic_value

    primary_aliases = _get_primary_aliases(pack)
    for alias in primary_aliases:
        alias_text = str(alias or "").strip()
        if alias_text and not _contains_cjk(alias_text):
            return alias_text
    for alias in pack.get("aliases", []):
        alias_text = str(alias or "").strip()
        if alias_text and not _contains_cjk(alias_text):
            return alias_text
    return topic_value


def build_company_queries_from_pack(topic, pack):
    topic_value = _resolve_query_topic(topic, pack)
    queries = []
    for template in pack.get("queries", []):
        queries.append(str(template).format(topic=topic_value))
    return _dedupe(queries)


def build_company_focus_hint(pack):
    aliases = _format_hint_list(pack.get("aliases", []), 8)
    keywords = _format_hint_list(pack.get("keywords", []), 12)
    priority_terms = _format_hint_list(pack.get("priority_terms", []), 10)
    domains = _format_hint_list(pack.get("domains", []), 8)
    deprioritize_terms = _format_hint_list(pack.get("deprioritize_terms", []), 8)

    custom_focus_lines = [str(item or "").strip() for item in pack.get("focus_lines", []) if str(item or "").strip()]
    lines = ["只保留目标主体是绝对主角的事件，删除仅提及该主体的陪衬新闻。"]
    if custom_focus_lines:
        lines.extend(custom_focus_lines)
    else:
        lines.append("优先覆盖产品发布、终端形态、硬件规格、芯片、数据中心、供应链、量产节奏、中国落地、自动驾驶、商业化等不同方向。")
    lines.extend([
        "不要让同一官司、同一隐私争议或同一法庭进展拆成多条近似事件。",
        "法律、隐私、诉讼、律师、法庭、社会政策类如果不是当天绝对主线，最多保留 1 条。",
    ])
    if aliases:
        lines.append(f"优先识别别名与产品线：{aliases}")
    if keywords:
        lines.append(f"优先识别业务与产品关键词：{keywords}")
    if priority_terms:
        lines.append(f"优先保留高价值事件类型：{priority_terms}")
    if deprioritize_terms:
        lines.append(f"以下主题默认降权：{deprioritize_terms}")
    if domains:
        lines.append(f"优先参考权威来源域名：{domains}")
    return "；".join(lines)


def _count_hits(text, tokens):
    total = 0
    for token in tokens or []:
        normalized = str(token or "").strip().lower()
        if normalized and normalized in text:
            total += 1
    return total


def _classify_result_category(result, pack):
    title = str(result.get("title", "") or "").lower()
    content = str(result.get("content", "") or "").lower()
    blob = f"{title} {content}"

    frontier_hits = _count_hits(blob, pack.get("priority_terms", [])) + _count_hits(blob, FRONTIER_TERMS)
    business_hits = _count_hits(blob, BUSINESS_TERMS)
    legal_hits = _count_hits(blob, LEGAL_TERMS) + _count_hits(blob, pack.get("deprioritize_terms", []))
    policy_hits = _count_hits(blob, POLICY_TERMS)
    social_hits = _count_hits(blob, SOCIAL_TERMS)

    if frontier_hits >= max(2, legal_hits + 1, policy_hits + 1, social_hits + 1):
        return "frontier"
    if legal_hits >= 2:
        return "legal"
    if policy_hits >= 2:
        return "policy"
    if social_hits >= 2:
        return "social"
    if business_hits >= 2:
        return "business"
    if frontier_hits >= 1:
        return "frontier"
    return "generic"


def _category_bias(category):
    return {
        "frontier": 2.8,
        "business": 0.9,
        "generic": 0.0,
        "policy": -0.9,
        "legal": -1.8,
        "social": -2.2,
    }.get(category, 0.0)


def _score_result_against_company_pack(result, pack):
    title = str(result.get("title", "") or "").lower()
    content = str(result.get("content", "") or "").lower()
    url = str(result.get("url", "") or "").lower()
    blob = f"{title} {content} {url}"

    primary_aliases = _get_primary_aliases(pack)
    all_aliases = list(pack.get("aliases", []) or [])
    secondary_aliases = [alias for alias in all_aliases if str(alias or "").strip() not in primary_aliases]

    primary_alias_hits_title = _count_hits(title, primary_aliases)
    primary_alias_hits_body = _count_hits(f"{content} {url}", primary_aliases)
    secondary_alias_hits_title = _count_hits(title, secondary_aliases)
    secondary_alias_hits_body = _count_hits(f"{content} {url}", secondary_aliases)
    keyword_hits_title = _count_hits(title, pack.get("keywords", []))
    keyword_hits_body = _count_hits(content, pack.get("keywords", []))
    priority_hits_title = _count_hits(title, pack.get("priority_terms", []))
    priority_hits_body = _count_hits(content, pack.get("priority_terms", []))
    deprioritize_hits_title = _count_hits(title, pack.get("deprioritize_terms", []))
    deprioritize_hits_body = _count_hits(content, pack.get("deprioritize_terms", []))
    domain_hits = _count_hits(url, pack.get("domains", []))
    noise_hits = _count_hits(f"{title} {content}", GENERIC_NOISE_TERMS)
    category = _classify_result_category(result, pack)

    score = 0.0
    score += primary_alias_hits_title * 4.0
    score += primary_alias_hits_body * 1.9
    score += secondary_alias_hits_title * 1.0
    score += secondary_alias_hits_body * 0.55
    score += keyword_hits_title * 1.9
    score += keyword_hits_body * 0.9
    score += priority_hits_title * 1.8
    score += priority_hits_body * 0.9
    score += domain_hits * 1.0
    score -= deprioritize_hits_title * 1.5
    score -= deprioritize_hits_body * 0.7
    score -= noise_hits * 1.6
    score += _category_bias(category)

    if primary_alias_hits_title == 0 and domain_hits == 0:
        score -= 4.2
    if primary_alias_hits_title == 0 and primary_alias_hits_body == 0:
        score -= 2.3
    if primary_alias_hits_title == 0 and primary_alias_hits_body == 0 and domain_hits == 0:
        score -= 1.8
    if primary_alias_hits_title == 0 and primary_alias_hits_body == 0 and keyword_hits_title == 0:
        score -= 1.4

    return round(score, 4), category


def _result_match_score(left, right):
    left_url = str(left.get("url", "") or "").strip().lower()
    right_url = str(right.get("url", "") or "").strip().lower()
    if left_url and right_url and left_url == right_url:
        return 1.0

    left_title = str(left.get("title", "") or "")
    right_title = str(right.get("title", "") or "")
    left_norm = _normalize_text(left_title)
    right_norm = _normalize_text(right_title)
    if not left_norm or not right_norm:
        return 0.0

    ratio = difflib.SequenceMatcher(None, left_norm, right_norm).ratio()
    left_tokens = _tokenize(f"{left_title} {str(left.get('content', '') or '')[:120]}")
    right_tokens = _tokenize(f"{right_title} {str(right.get('content', '') or '')[:120]}")
    overlap = len(left_tokens & right_tokens) / max(min(len(left_tokens), len(right_tokens)) or 1, 1)
    same_date = bool(
        (left.get("published_at_resolved") or left.get("published_date") or "")
        and (left.get("published_at_resolved") or left.get("published_date") or "")
        == (right.get("published_at_resolved") or right.get("published_date") or "")
    )
    return round(ratio * 0.58 + overlap * 0.32 + (0.1 if same_date else 0.0), 4)


def _build_category_caps(limit, pack):
    custom_caps = deepcopy(pack.get("category_caps", {}))
    if custom_caps:
        return custom_caps
    base_limit = max(int(limit or 40), 1)
    return {
        "frontier": max(18, base_limit // 2),
        "business": max(6, base_limit // 5),
        "generic": max(8, base_limit // 4),
        "policy": 1,
        "legal": 1,
        "social": 1,
    }


def _select_diversified_results(scored_rows, limit, pack):
    limit = int(limit or len(scored_rows) or 0)
    if limit <= 0:
        return []

    caps = _build_category_caps(limit, pack)
    selected = []
    deferred = []
    category_counts = {}

    for row in scored_rows:
        category = row["category"]
        duplicate_hit = any(_result_match_score(row["item"], picked["item"]) >= 0.78 for picked in selected)
        if duplicate_hit:
            continue

        if category_counts.get(category, 0) >= caps.get(category, limit):
            deferred.append(row)
            continue

        selected.append(row)
        category_counts[category] = category_counts.get(category, 0) + 1
        if len(selected) >= limit:
            return selected

    for row in deferred:
        duplicate_hit = any(_result_match_score(row["item"], picked["item"]) >= 0.82 for picked in selected)
        if duplicate_hit:
            continue
        selected.append(row)
        if len(selected) >= limit:
            break

    return selected


def rank_results_by_company_pack(results, pack, limit=None):
    scored_rows = []
    for idx, item in enumerate(results or []):
        score, category = _score_result_against_company_pack(item, pack)
        if score <= 0.4:
            continue
        recency = str(item.get("published_at_resolved") or item.get("published_date") or "")
        enriched = dict(item)
        enriched["_company_pack_score"] = score
        enriched["_company_category"] = category
        scored_rows.append({
            "score": score,
            "category": category,
            "recency": recency,
            "index": -idx,
            "item": enriched,
        })

    scored_rows.sort(key=lambda row: (row["score"], row["recency"], row["index"]), reverse=True)
    selected_rows = _select_diversified_results(scored_rows, limit or len(scored_rows), pack)
    return [row["item"] for row in selected_rows]
