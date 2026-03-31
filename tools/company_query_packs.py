from copy import deepcopy


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


MEGACAP_QUERY_PACKS = {
    "apple": {
        "aliases": ["apple", "苹果", "aapl", "iphone", "ios", "mac", "vision pro"],
        "domains": [
            "apple.com",
            "macrumors.com",
            "9to5mac.com",
            "appleinsider.com",
            "theverge.com",
            "techcrunch.com",
            "bloomberg.com",
            "cnbc.com",
            "reuters.com",
        ],
        "keywords": [
            "iphone",
            "ios",
            "ipad",
            "mac",
            "vision pro",
            "app store",
            "wwdc",
            "siri",
            "apple intelligence",
            "supply chain",
            "china",
        ],
        "priority_terms": [
            "earnings",
            "guidance",
            "launch",
            "release",
            "antitrust",
            "regulation",
            "ai",
            "data center",
        ],
        "queries": [
            "{topic}",
            "{topic} iPhone iOS App Store latest",
            "{topic} Apple Intelligence Siri WWDC latest",
            "{topic} earnings guidance China latest",
            "{topic} regulation antitrust lawsuit latest",
            "{topic} chip supply chain Vision Pro latest",
        ],
    },
    "google": {
        "aliases": ["google", "alphabet", "谷歌", "gemini", "android", "pixel"],
        "domains": [
            "blog.google",
            "blog.google.com",
            "9to5google.com",
            "androidauthority.com",
            "theverge.com",
            "techcrunch.com",
            "bloomberg.com",
            "cnbc.com",
            "reuters.com",
        ],
        "keywords": [
            "gemini",
            "android",
            "pixel",
            "search",
            "chrome",
            "waymo",
            "youtube",
            "cloud",
            "tpu",
            "antitrust",
        ],
        "priority_terms": [
            "earnings",
            "guidance",
            "launch",
            "release",
            "partnership",
            "doj",
            "regulation",
            "data center",
        ],
        "queries": [
            "{topic}",
            "{topic} Gemini Search Chrome latest",
            "{topic} Android Pixel AI latest",
            "{topic} Cloud TPU data center latest",
            "{topic} DOJ antitrust regulation latest",
            "{topic} earnings Waymo YouTube latest",
        ],
    },
    "amazon": {
        "aliases": ["amazon", "亚马逊", "aws", "kuiper", "prime"],
        "domains": [
            "aboutamazon.com",
            "amazon.com",
            "cnbc.com",
            "techcrunch.com",
            "bloomberg.com",
            "theverge.com",
            "reuters.com",
        ],
        "keywords": [
            "aws",
            "bedrock",
            "prime",
            "retail",
            "logistics",
            "kuiper",
            "ad business",
            "fulfillment",
            "data center",
        ],
        "priority_terms": [
            "earnings",
            "guidance",
            "partnership",
            "antitrust",
            "union",
            "satellite",
            "data center",
        ],
        "queries": [
            "{topic}",
            "{topic} AWS Bedrock data center AI latest",
            "{topic} Prime retail logistics latest",
            "{topic} earnings ad business guidance latest",
            "{topic} FTC antitrust union regulation latest",
            "{topic} Kuiper satellite latest",
        ],
    },
    "openai": {
        "aliases": ["openai", "open ai", "chatgpt", "gpt"],
        "domains": [
            "openai.com",
            "techcrunch.com",
            "theverge.com",
            "venturebeat.com",
            "wired.com",
            "bloomberg.com",
            "cnbc.com",
            "reuters.com",
        ],
        "keywords": [
            "chatgpt",
            "gpt",
            "api",
            "enterprise",
            "model release",
            "microsoft",
            "safety",
            "copyright",
            "data center",
            "stargate",
        ],
        "priority_terms": [
            "launch",
            "release",
            "funding",
            "partnership",
            "acquisition",
            "legal",
            "policy",
            "chips",
        ],
        "queries": [
            "{topic}",
            "{topic} ChatGPT GPT API enterprise latest",
            "{topic} funding Microsoft partnership latest",
            "{topic} model release safety policy latest",
            "{topic} acquisition hiring data center chip latest",
            "{topic} legal copyright regulation latest",
        ],
    },
    "meta": {
        "aliases": ["meta", "facebook", "脸书", "llama", "quest", "instagram", "threads"],
        "domains": [
            "about.fb.com",
            "meta.com",
            "theverge.com",
            "techcrunch.com",
            "uploadvr.com",
            "roadtovr.com",
            "bloomberg.com",
            "cnbc.com",
            "reuters.com",
        ],
        "keywords": [
            "llama",
            "quest",
            "reality labs",
            "ray-ban",
            "smart glasses",
            "ads",
            "threads",
            "instagram",
            "privacy",
            "antitrust",
        ],
        "priority_terms": [
            "earnings",
            "guidance",
            "launch",
            "release",
            "privacy",
            "regulation",
            "data center",
            "chips",
        ],
        "queries": [
            "{topic}",
            "{topic} Llama AI model latest",
            "{topic} Quest Reality Labs smart glasses latest",
            "{topic} ad business earnings guidance latest",
            "{topic} privacy antitrust regulation latest",
            "{topic} data center chip AI latest",
        ],
    },
    "nvidia": {
        "aliases": ["nvidia", "英伟达", "nvda", "blackwell", "cuda", "黄仁勋"],
        "domains": [
            "nvidianews.nvidia.com",
            "nvidia.com",
            "tomshardware.com",
            "anandtech.com",
            "theverge.com",
            "cnbc.com",
            "bloomberg.com",
            "reuters.com",
        ],
        "keywords": [
            "blackwell",
            "gpu",
            "cuda",
            "h200",
            "b200",
            "data center",
            "export restriction",
            "china",
            "robotics",
            "automotive",
        ],
        "priority_terms": [
            "earnings",
            "guidance",
            "launch",
            "release",
            "partnership",
            "export",
            "restriction",
            "server",
        ],
        "queries": [
            "{topic}",
            "{topic} GPU Blackwell AI server latest",
            "{topic} data center cloud partnership latest",
            "{topic} China export restriction regulation latest",
            "{topic} earnings guidance latest",
            "{topic} automotive robotics latest",
        ],
    },
    "tesla": {
        "aliases": ["tesla", "特斯拉", "tsla", "fsd", "robotaxi", "optimus", "megapack"],
        "domains": [
            "tesla.com",
            "electrek.co",
            "insideevs.com",
            "cnbc.com",
            "reuters.com",
            "bloomberg.com",
        ],
        "keywords": [
            "fsd",
            "robotaxi",
            "autopilot",
            "deliveries",
            "margin",
            "megapack",
            "china",
            "berlin",
            "austin",
            "optimus",
            "energy",
        ],
        "priority_terms": [
            "earnings",
            "deliveries",
            "guidance",
            "recall",
            "regulation",
            "launch",
            "autonomy",
            "robotics",
        ],
        "queries": [
            "{topic}",
            "{topic} FSD robotaxi autopilot latest",
            "{topic} deliveries earnings margins latest",
            "{topic} energy megapack latest",
            "{topic} China Europe plant regulation recall latest",
            "{topic} Optimus robotics latest",
        ],
    },
    "trump": {
        "aliases": ["trump", "donald trump", "特朗普", "川普", "trump administration"],
        "domains": [
            "whitehouse.gov",
            "reuters.com",
            "apnews.com",
            "cnbc.com",
            "bloomberg.com",
            "wsj.com",
        ],
        "keywords": [
            "tariff",
            "white house",
            "executive order",
            "trade policy",
            "chips",
            "china",
            "autos",
            "tech regulation",
            "antitrust",
        ],
        "priority_terms": [
            "tariff",
            "policy",
            "executive order",
            "trade",
            "chips",
            "ai",
            "autos",
            "regulation",
        ],
        "queries": [
            "{topic}",
            "{topic} tariff trade policy latest",
            "{topic} White House executive order chips AI latest",
            "{topic} China tariff auto latest",
            "{topic} tech antitrust regulation latest",
            "{topic} market policy latest",
        ],
    },
    "anthropic": {
        "aliases": ["anthropic", "claude", "anthropic ai", "克劳德"],
        "domains": [
            "anthropic.com",
            "techcrunch.com",
            "theverge.com",
            "venturebeat.com",
            "bloomberg.com",
            "cnbc.com",
            "reuters.com",
        ],
        "keywords": [
            "claude",
            "model",
            "enterprise",
            "api",
            "amazon",
            "google",
            "safety",
            "policy",
            "data center",
            "chips",
        ],
        "priority_terms": [
            "funding",
            "partnership",
            "launch",
            "release",
            "enterprise",
            "safety",
            "policy",
            "legal",
        ],
        "queries": [
            "{topic}",
            "{topic} Claude model latest",
            "{topic} Amazon Google funding latest",
            "{topic} enterprise API safety latest",
            "{topic} chips data center partnership latest",
            "{topic} legal policy latest",
        ],
    },
    "spacex": {
        "aliases": ["spacex", "space x", "星链", "starlink", "starship"],
        "domains": [
            "spacex.com",
            "spacenews.com",
            "satnews.com",
            "teslarati.com",
            "cnbc.com",
            "reuters.com",
        ],
        "keywords": [
            "starship",
            "starlink",
            "direct-to-cell",
            "launch",
            "nasa",
            "defense",
            "contract",
            "satellite",
            "valuation",
            "funding",
        ],
        "priority_terms": [
            "launch",
            "contract",
            "license",
            "funding",
            "valuation",
            "nasa",
            "defense",
            "satellite",
        ],
        "queries": [
            "{topic}",
            "{topic} Starship launch latest",
            "{topic} Starlink satellite direct-to-cell latest",
            "{topic} NASA defense contract latest",
            "{topic} valuation funding latest",
            "{topic} regulation launch license latest",
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
            "earnings",
            "guidance",
            "launch",
            "release",
            "partnership",
            "regulation",
            "lawsuit",
            "data center",
        ],
        "queries": [
            "{topic}",
            "{topic} product launch partnership acquisition latest",
            "{topic} earnings guidance regulation lawsuit latest",
            "{topic} chip supply chain developer conference data center latest",
        ],
    }


def build_company_queries_from_pack(topic, pack):
    topic_value = str(topic or "").strip()
    queries = []
    for template in pack.get("queries", []):
        queries.append(str(template).format(topic=topic_value))
    return _dedupe(queries)


def build_company_focus_hint(pack):
    aliases = _format_hint_list(pack.get("aliases", []), 8)
    keywords = _format_hint_list(pack.get("keywords", []), 12)
    priority_terms = _format_hint_list(pack.get("priority_terms", []), 10)
    domains = _format_hint_list(pack.get("domains", []), 8)

    lines = ["只保留目标主体是绝对主角的事件，删除仅提及该主体的陪衬新闻。"]
    if aliases:
        lines.append(f"优先识别别名与产品线：{aliases}")
    if keywords:
        lines.append(f"优先识别业务与产品关键词：{keywords}")
    if priority_terms:
        lines.append(f"优先保留高价值事件类型：{priority_terms}")
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


def _score_result_against_company_pack(result, pack):
    title = str(result.get("title", "") or "").lower()
    content = str(result.get("content", "") or "").lower()
    url = str(result.get("url", "") or "").lower()

    alias_hits_title = _count_hits(title, pack.get("aliases", []))
    alias_hits_body = _count_hits(f"{content} {url}", pack.get("aliases", []))
    keyword_hits_title = _count_hits(title, pack.get("keywords", []))
    keyword_hits_body = _count_hits(content, pack.get("keywords", []))
    priority_hits_title = _count_hits(title, pack.get("priority_terms", []))
    priority_hits_body = _count_hits(content, pack.get("priority_terms", []))
    domain_hits = _count_hits(url, pack.get("domains", []))
    noise_hits = _count_hits(f"{title} {content}", GENERIC_NOISE_TERMS)

    score = 0.0
    score += alias_hits_title * 3.2
    score += alias_hits_body * 1.4
    score += keyword_hits_title * 1.8
    score += keyword_hits_body * 0.8
    score += priority_hits_title * 1.4
    score += priority_hits_body * 0.7
    score += domain_hits * 1.0
    score -= noise_hits * 1.6

    if alias_hits_title == 0 and alias_hits_body == 0 and keyword_hits_title == 0:
        score -= 1.2

    return round(score, 4)


def rank_results_by_company_pack(results, pack, limit=None):
    scored = []
    for idx, item in enumerate(results or []):
        score = _score_result_against_company_pack(item, pack)
        recency = str(item.get("published_at_resolved") or item.get("published_date") or "")
        enriched = dict(item)
        enriched["_company_pack_score"] = score
        scored.append((score, recency, -idx, enriched))

    scored.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
    ranked = [item[3] for item in scored]
    if limit:
        return ranked[:limit]
    return ranked
