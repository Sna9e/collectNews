from copy import deepcopy
import difflib
import re

from tools.search_engine import assess_news_source_quality, is_high_quality_news_result


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


DEFAULT_COMPANY_TOPICS = [
    "Apple",
    "Google",
    "Amazon",
    "OpenAI",
    "Meta",
    "Nvidia",
    "Tesla",
    "特朗普",
    "Anthropic",
    "SpaceX",
]


MEGACAP_QUERY_PACKS = {
    "apple": {
        "aliases": ["apple", "苹果", "aapl", "iphone", "ios", "mac", "vision pro"],
        "domains": [
            "apple.com", "macrumors.com", "9to5mac.com", "appleinsider.com",
            "theverge.com", "techcrunch.com", "bloomberg.com", "cnbc.com", "reuters.com",
        ],
        "keywords": [
            "iphone", "ios", "ipad", "mac", "vision pro", "app store", "wwdc",
            "siri", "apple intelligence", "supply chain", "chip", "silicon"
        ],
        "priority_terms": [
            "launch", "release", "ai", "siri", "wwdc", "chip", "supply chain",
            "vision pro", "data center", "earnings", "guidance"
        ],
        "deprioritize_terms": ["privacy", "lawsuit", "court", "judge", "lawyer", "epic", "antitrust"],
        "queries": [
            "{topic}",
            "{topic} iPhone iOS Mac latest",
            "{topic} Apple Intelligence Siri WWDC latest",
            "{topic} chip supply chain Vision Pro latest",
            "{topic} earnings guidance China latest",
            "{topic} App Store privacy regulation latest",
        ],
    },
    "google": {
        "aliases": ["google", "alphabet", "谷歌", "gemini", "android", "pixel"],
        "domains": [
            "blog.google", "blog.google.com", "9to5google.com", "androidauthority.com",
            "theverge.com", "techcrunch.com", "bloomberg.com", "cnbc.com", "reuters.com",
        ],
        "keywords": [
            "gemini", "android", "pixel", "search", "chrome", "waymo",
            "youtube", "cloud", "tpu", "data center"
        ],
        "priority_terms": [
            "launch", "release", "gemini", "android", "pixel", "cloud", "tpu",
            "data center", "waymo", "ai", "earnings", "guidance"
        ],
        "deprioritize_terms": ["privacy", "lawsuit", "lawyer", "court", "judge", "fine", "antitrust", "ban"],
        "queries": [
            "{topic}",
            "{topic} Gemini Search Chrome AI latest",
            "{topic} Android Pixel latest",
            "{topic} Cloud TPU data center latest",
            "{topic} Waymo autonomous driving latest",
            "{topic} earnings privacy antitrust latest",
        ],
    },
    "amazon": {
        "aliases": ["amazon", "亚马逊", "aws", "kuiper", "prime"],
        "domains": [
            "aboutamazon.com", "amazon.com", "cnbc.com", "techcrunch.com",
            "bloomberg.com", "theverge.com", "reuters.com",
        ],
        "keywords": [
            "aws", "bedrock", "prime", "retail", "logistics", "kuiper",
            "fulfillment", "data center", "satellite"
        ],
        "priority_terms": [
            "aws", "bedrock", "data center", "satellite", "kuiper", "launch",
            "partnership", "earnings", "guidance", "logistics"
        ],
        "deprioritize_terms": ["lawsuit", "union", "court", "judge", "complaint", "antitrust"],
        "queries": [
            "{topic}",
            "{topic} AWS Bedrock data center AI latest",
            "{topic} Kuiper satellite latest",
            "{topic} Prime retail logistics latest",
            "{topic} earnings guidance ad business latest",
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
        ],
        "keywords": [
            "llama", "quest", "reality labs", "ray-ban", "smart glasses",
            "ads", "threads", "instagram", "data center"
        ],
        "priority_terms": [
            "llama", "quest", "smart glasses", "reality labs", "launch", "release",
            "ads", "data center", "chips", "earnings"
        ],
        "deprioritize_terms": ["privacy", "lawsuit", "court", "judge", "ban", "antitrust"],
        "queries": [
            "{topic}",
            "{topic} Llama AI model latest",
            "{topic} Quest smart glasses latest",
            "{topic} data center chips latest",
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
        ],
        "keywords": [
            "fsd", "robotaxi", "autopilot", "deliveries", "megapack", "optimus",
            "energy", "china", "berlin", "austin"
        ],
        "priority_terms": [
            "robotaxi", "fsd", "autonomy", "optimus", "energy", "megapack",
            "deliveries", "earnings", "launch", "robotics"
        ],
        "deprioritize_terms": ["lawsuit", "court", "judge", "recall", "probe"],
        "queries": [
            "{topic}",
            "{topic} FSD robotaxi latest",
            "{topic} Optimus robotics latest",
            "{topic} energy Megapack latest",
            "{topic} deliveries earnings margins latest",
            "{topic} recall regulation latest",
        ],
    },
    "trump": {
        "aliases": ["trump", "donald trump", "特朗普", "川普", "trump administration"],
        "domains": ["whitehouse.gov", "reuters.com", "apnews.com", "cnbc.com", "bloomberg.com", "wsj.com"],
        "keywords": ["tariff", "white house", "executive order", "trade policy", "chips", "china", "autos"],
        "priority_terms": ["tariff", "trade", "chips", "ai", "autos", "executive order", "policy"],
        "deprioritize_terms": ["lawsuit", "court", "lawyer", "campaign", "speech"],
        "queries": [
            "{topic}",
            "{topic} tariff trade policy latest",
            "{topic} chips AI policy latest",
            "{topic} autos China tariff latest",
            "{topic} executive order latest",
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


COMPANY_CONTENT_PROFILES = {
    "apple": {
        "summary_focus": [
            "产品或系统版本、发布时间、覆盖设备和开放范围",
            "Apple Intelligence、Siri、自研芯片的功能变化、端云分工和隐私机制",
            "iPhone、Mac、Vision Pro的销量、备货、关键零部件和中国供应链节奏",
            "对开发者生态、终端硬件规格及FPC/PCB/光学链条的直接影响",
        ],
        "high_value_signals": [
            "正式发布", "开发者测试", "量产", "供应商订单", "Apple Silicon", "折叠设备", "AI基础设施",
        ],
        "additional_domains": ["developer.apple.com", "investor.apple.com"],
        "additional_queries": [
            "{topic} Newsroom developer release hardware AI latest",
            "{topic} iPhone Mac Vision Pro production supplier China latest",
            "苹果 iPhone Mac AI 芯片 供应链 最新",
        ],
    },
    "google": {
        "summary_focus": [
            "Gemini或Gemma的模型版本、上下文、模态、API价格和开放范围",
            "Search、Chrome、Android、Pixel的功能入口、推送节奏和覆盖用户",
            "Cloud、TPU、数据中心资本开支及企业客户部署",
            "Waymo商业运营区域、车队规模、监管节点和合作伙伴",
        ],
        "high_value_signals": [
            "模型发布", "API降价", "正式推送", "TPU", "数据中心投资", "Waymo商业运营", "重大监管决定",
        ],
        "additional_domains": ["developers.googleblog.com", "cloud.google.com", "abc.xyz"],
        "additional_queries": [
            "{topic} Gemini Gemma API pricing benchmark release latest",
            "{topic} TPU Cloud capex data center customer latest",
            "谷歌 Gemini Android Pixel TPU 数据中心 最新",
        ],
    },
    "amazon": {
        "summary_focus": [
            "AWS、Bedrock、Trainium、Inferentia的产品版本、价格、客户和区域上线",
            "数据中心、自研芯片、电力与网络基础设施投入",
            "Kuiper发射、卫星数量、终端设备和商用节点",
            "仓储机器人、履约网络、零售与广告业务的直接经营变化",
        ],
        "high_value_signals": [
            "AWS正式发布", "大客户合同", "Trainium", "数据中心投资", "Kuiper商用", "物流自动化", "财务指引",
        ],
        "additional_domains": ["aws.amazon.com", "ir.aboutamazon.com"],
        "additional_queries": [
            "{topic} AWS Bedrock Trainium enterprise customer pricing latest",
            "{topic} warehouse robotics fulfillment automation latest",
            "亚马逊 AWS 自研芯片 Kuiper 物流机器人 最新",
        ],
    },
    "openai": {
        "summary_focus": [
            "模型或产品名称、能力边界、上下文、模态、API价格和开放对象",
            "ChatGPT、Codex、Agents及企业功能的上线范围和使用限制",
            "Stargate、芯片、数据中心、云合作及算力供应",
            "融资、组织或合作变化对产品节奏和商业化的直接影响",
        ],
        "high_value_signals": [
            "新模型发布", "API价格调整", "企业版上线", "Agent平台", "算力合同", "数据中心", "重大融资",
        ],
        "additional_domains": ["platform.openai.com", "help.openai.com"],
        "additional_queries": [
            "{topic} model API pricing context agents release latest",
            "{topic} Codex ChatGPT enterprise customer latest",
            "OpenAI 模型 API 智能体 算力 数据中心 最新",
        ],
    },
    "meta": {
        "summary_focus": [
            "Llama模型版本、开源许可、参数、推理部署和开发者生态",
            "Ray-Ban智能眼镜、Quest及Reality Labs硬件功能、销量和上市节点",
            "推荐广告、Instagram、WhatsApp和Threads的AI产品变化",
            "自研芯片、数据中心、资本开支与供应链需求",
        ],
        "high_value_signals": [
            "Llama发布", "智能眼镜新品", "Quest量产", "广告产品升级", "自研芯片", "数据中心投资", "重大合作",
        ],
        "additional_domains": ["ai.meta.com", "investor.atmeta.com"],
        "additional_queries": [
            "{topic} Llama open source model inference latest",
            "{topic} Ray-Ban smart glasses Quest shipment latest",
            "Meta Llama 智能眼镜 Quest 自研芯片 数据中心 最新",
        ],
    },
    "nvidia": {
        "summary_focus": [
            "GPU、CPU、网络和整机平台的型号、性能、功耗、上市和量产节奏",
            "Blackwell、Rubin、NVLink、Spectrum-X及AI机架的客户验证和交付",
            "HBM、先进封装、服务器板卡、液冷和电力供应链变化",
            "云厂商、主权AI、机器人和汽车平台的订单与落地",
        ],
        "high_value_signals": [
            "新架构发布", "量产交付", "云客户订单", "HBM", "先进封装", "AI机架", "出口限制", "机器人平台",
        ],
        "additional_domains": ["developer.nvidia.com", "investor.nvidia.com"],
        "additional_queries": [
            "{topic} Blackwell Rubin NVLink AI rack shipment latest",
            "{topic} HBM CoWoS liquid cooling supply chain latest",
            "英伟达 GPU AI服务器 HBM 先进封装 液冷 最新",
        ],
    },
    "tesla": {
        "summary_focus": [
            "车型、工厂、产量、交付、价格和关键零部件变化",
            "FSD、Robotaxi的版本、覆盖区域、车队规模、安全员和监管许可",
            "Optimus的样机、工厂部署、产能、供应链和商业销售节点",
            "Megapack、储能、电池及充电业务的订单和量产节奏",
        ],
        "high_value_signals": [
            "新车型量产", "Robotaxi商业运营", "FSD正式推送", "Optimus工厂部署", "电池产能", "Megapack订单", "交付指引",
        ],
        "additional_domains": ["ir.tesla.com"],
        "additional_queries": [
            "{topic} factory production deliveries battery supply chain latest",
            "{topic} Robotaxi fleet permit FSD rollout latest",
            "特斯拉 Robotaxi FSD Optimus 储能 量产 最新",
        ],
    },
    "trump": {
        "summary_focus": [
            "白宫、商务部、USTR或监管机构发布政策的具体日期和法律动作",
            "关税、出口管制、芯片、AI、汽车、能源和航天政策的适用对象",
            "税率、豁免、实施期限、受影响国家或企业等已确认条款",
            "对科技公司、制造业投资和供应链迁移的直接影响；排除泛竞选与个人争议",
        ],
        "high_value_signals": [
            "行政命令", "正式关税", "出口管制", "芯片政策", "AI监管", "汽车政策", "重大豁免", "生效日期",
        ],
        "additional_domains": ["federalregister.gov", "commerce.gov", "ustr.gov"],
        "additional_queries": [
            "{topic} White House technology executive order tariff effective date latest",
            "{topic} semiconductor AI export control auto policy latest",
            "特朗普 芯片 AI 汽车 关税 出口管制 最新政策",
        ],
    },
    "anthropic": {
        "summary_focus": [
            "Claude模型版本、上下文、工具调用、基准、API价格和开放范围",
            "Claude Code、Agent、企业产品和重点客户部署",
            "AWS、Google、芯片与数据中心合作形成的算力路径",
            "融资、安全政策或合作变化对模型发布和商业化的直接影响",
        ],
        "high_value_signals": [
            "Claude发布", "API价格调整", "Claude Code", "企业客户", "Agent能力", "算力合作", "重大融资",
        ],
        "additional_domains": ["docs.anthropic.com"],
        "additional_queries": [
            "{topic} Claude model API pricing context tools release latest",
            "{topic} Claude Code agents enterprise customer latest",
            "Anthropic Claude 模型 API 智能体 算力合作 最新",
        ],
    },
    "spacex": {
        "summary_focus": [
            "Starship试飞时间、任务阶段、发动机、回收结果和下一次监管节点",
            "Starlink卫星数量、用户、容量、资费、Direct-to-Cell和终端产品",
            "NASA、国防与商业发射合同的金额、任务和交付时间",
            "发射许可、频谱和供应链变化对发射节奏及商业化的直接影响",
        ],
        "high_value_signals": [
            "Starship试飞", "成功回收", "FAA许可", "Starlink商用", "Direct-to-Cell", "NASA合同", "国防合同", "发射纪录",
        ],
        "additional_domains": ["nasa.gov", "fcc.gov", "faa.gov"],
        "additional_queries": [
            "{topic} Starship flight test FAA license recovery latest",
            "{topic} Starlink subscribers capacity direct-to-cell latest",
            "SpaceX 星舰 星链 直连手机 NASA 合同 最新",
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
            profile = deepcopy(COMPANY_CONTENT_PROFILES.get(pack_name, {}))
            payload["domains"] = _dedupe(
                list(payload.get("domains", []) or []) + list(profile.pop("additional_domains", []) or [])
            )
            payload["queries"] = _dedupe(
                list(payload.get("queries", []) or []) + list(profile.pop("additional_queries", []) or [])
            )
            payload.update(profile)
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
            "launch", "release", "product", "ai", "chip", "supply chain",
            "data center", "partnership", "earnings", "guidance"
        ],
        "deprioritize_terms": ["lawsuit", "court", "judge", "lawyer", "privacy", "ban"],
        "summary_focus": [
            "事件主体、动作、产品或业务对象、已披露数据和直接影响",
            "发布时间、开放范围、客户、市场和供应链节点",
        ],
        "high_value_signals": ["正式发布", "量产", "重大合同", "客户验证", "监管生效"],
        "queries": [
            "{topic}",
            "{topic} product launch partnership latest",
            "{topic} AI chip data center latest",
            "{topic} earnings guidance latest",
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
    summary_focus = _format_hint_list(pack.get("summary_focus", []), 6)
    high_value_signals = _format_hint_list(pack.get("high_value_signals", []), 10)

    lines = [
        "只保留目标主体是绝对主角的事件，删除仅提及该主体的陪衬新闻。",
        "优先覆盖产品发布、AI、芯片、数据中心、供应链、自动驾驶、商业化等不同技术与业务方向。",
        "不要让同一官司、同一隐私争议或同一法庭进展拆成多条近似事件。",
        "法律、隐私、诉讼、律师、法庭、社会政策类如果不是当天绝对主线，最多保留 1 条。",
    ]
    if aliases:
        lines.append(f"优先识别别名与产品线：{aliases}")
    if keywords:
        lines.append(f"优先识别业务与产品关键词：{keywords}")
    if priority_terms:
        lines.append(f"优先保留高价值事件类型：{priority_terms}")
    if deprioritize_terms:
        lines.append(f"以下主题默认降权：{deprioritize_terms}")
    if summary_focus:
        lines.append(f"短新闻摘要和详细新闻应优先交代：{summary_focus}")
    if high_value_signals:
        lines.append(
            f"以下实质节点可提高新闻重要度并用于重点高亮：{high_value_signals}；"
            "只有材料明确披露时才能提高，不得因关键词出现就虚构重大进展"
        )
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
        if not is_high_quality_news_result(item, min_content_chars=60):
            continue
        quality = assess_news_source_quality(item, min_content_chars=60)
        score, category = _score_result_against_company_pack(item, pack)
        score += min(float(quality.get("score", 0) or 0) * 0.35, 3.2)
        if quality.get("is_original"):
            score += 1.2
        elif quality.get("is_preferred"):
            score += 0.8
        if score <= 0.4:
            continue
        recency = str(item.get("published_at_resolved") or item.get("published_date") or "")
        enriched = dict(item)
        enriched["_company_pack_score"] = score
        enriched["_company_category"] = category
        enriched["_source_quality"] = quality
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
