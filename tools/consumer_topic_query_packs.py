import datetime
import difflib
import re
from copy import deepcopy
from dataclasses import asdict, dataclass, field

from tools.search_engine import audit_recent_news_results, search_web


CONSUMER_TOPIC_DEFAULT_LIMIT = 120
CONSUMER_TOPIC_RESULTS_PER_QUERY = 8

_NOISE_TERMS = [
    "相关推荐", "大家都在看", "热门文章", "广告合集", "促销软文", "优惠券", "壁纸", "教程",
    "lawsuit", "court", "attorney", "privacy", "copyright", "stock price", "analyst rating",
]


@dataclass
class ConsumerTopicQueryPack:
    topic_id: str
    topic_name: str
    description: str
    aliases: list[str] = field(default_factory=list)
    core_entities: list[str] = field(default_factory=list)
    domestic_entities: list[str] = field(default_factory=list)
    global_entities: list[str] = field(default_factory=list)
    product_terms: list[str] = field(default_factory=list)
    technology_terms: list[str] = field(default_factory=list)
    supply_chain_terms: list[str] = field(default_factory=list)
    priority_terms: list[str] = field(default_factory=list)
    deprioritize_terms: list[str] = field(default_factory=list)
    domains: list[str] = field(default_factory=list)
    high_quality_domains: list[str] = field(default_factory=list)
    queries: list[str] = field(default_factory=list)
    verification_queries: list[str] = field(default_factory=list)
    prompt_focus: str = ""
    time_window: str = "72h"

    def get(self, key, default=None):
        return self.to_topic_dict().get(key, default)

    def to_topic_dict(self):
        payload = asdict(self)
        payload.update(
            {
                "id": self.topic_id,
                "title": self.topic_name,
                "topic_name": self.topic_name,
                "daily_queries": list(self.queries),
                "companies": _dedupe(self.domestic_entities + self.global_entities, limit=80),
                "domestic_company_terms": list(self.domestic_entities),
                "global_company_terms": list(self.global_entities),
                "keywords": _dedupe(
                    self.aliases
                    + self.core_entities
                    + self.product_terms
                    + self.technology_terms
                    + self.supply_chain_terms,
                    limit=120,
                ),
                "boost_terms": _dedupe(self.priority_terms + self.technology_terms + self.supply_chain_terms, limit=120),
                "required_terms": _dedupe(self.aliases + self.core_entities + self.technology_terms, limit=80),
                "negative_terms": list(self.deprioritize_terms),
                "media_domains": _dedupe(self.domains + self.high_quality_domains, limit=120),
                "tags": _dedupe(self.aliases + self.priority_terms, limit=16),
                "prompt_focus": self.prompt_focus,
            }
        )
        return payload


def _dedupe(items, limit=None):
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


def _pack_dict(pack):
    if isinstance(pack, ConsumerTopicQueryPack):
        return pack.to_topic_dict()
    return dict(pack or {})


def _join_terms(terms, limit=4):
    return " ".join(_dedupe(terms, limit=limit))


def _append_query_suffix(query, suffix):
    query = str(query or "").strip()
    suffix = str(suffix or "").strip()
    if not query:
        return ""
    if suffix and _contains_cjk(query):
        return f"{query} {suffix}"
    return query


def _add_query(records, query, query_type="expanded", language=None, priority=3):
    query = str(query or "").strip()
    if not query:
        return
    records.append(
        {
            "query": query,
            "query_type": query_type,
            "language": language or ("zh" if _contains_cjk(query) else "en"),
            "priority": priority,
        }
    )


def build_consumer_topic_query_records_from_pack(pack, query_suffix="", max_queries=None):
    """Build wide Exa discovery queries from static query pack plus entities.

    Discovery should recall broadly and avoid early hard filtering. Strict
    freshness/source validation happens later in consumer_daily_validation.
    """
    payload = _pack_dict(pack)
    records = []
    topic_name = str(payload.get("topic_name") or payload.get("title") or "").strip()
    aliases = _dedupe(payload.get("aliases", []) or [], limit=8)
    core_entities = _dedupe(payload.get("core_entities", []) or aliases, limit=8)
    domestic = _dedupe(payload.get("domestic_entities", []) or payload.get("domestic_company_terms", []) or [], limit=20)
    global_entities = _dedupe(payload.get("global_entities", []) or payload.get("global_company_terms", []) or [], limit=14)
    products = _dedupe(payload.get("product_terms", []) or [], limit=18)
    tech_terms = _dedupe(payload.get("technology_terms", []) or [], limit=22)
    supply_terms = _dedupe(payload.get("supply_chain_terms", []) or [], limit=18)
    priority_terms = _dedupe(payload.get("priority_terms", []) or payload.get("boost_terms", []) or [], limit=18)
    media_domains = _dedupe(payload.get("media_domains", []) or payload.get("domains", []) or [], limit=22)
    high_domains = _dedupe(payload.get("high_quality_domains", []) or [], limit=14)
    suffix = str(query_suffix or "").strip()

    for query in list(payload.get("queries", []) or []) + list(payload.get("daily_queries", []) or []):
        _add_query(records, _append_query_suffix(query, suffix), "base", priority=1)

    topic_core = _join_terms(core_entities or aliases or [topic_name], limit=3)
    product_core = _join_terms(products, limit=3)
    tech_core = _join_terms(tech_terms, limit=3)
    supply_core = _join_terms(supply_terms, limit=3)
    action_core = _join_terms(priority_terms, limit=4)

    if topic_core:
        _add_query(records, _append_query_suffix(f"今日 {topic_core} {action_core}", suffix), "core", "zh", 1)
        _add_query(records, _append_query_suffix(f"过去72小时 {topic_core} {tech_core} {action_core}", suffix), "core", "zh", 2)
    if topic_core and supply_core:
        _add_query(records, _append_query_suffix(f"今日 {topic_core} 供应链 {supply_core}", suffix), "supply_chain", "zh", 2)
    if topic_core and product_core:
        _add_query(records, _append_query_suffix(f"今日 {topic_core} {product_core} 参数 更新", suffix), "product", "zh", 2)

    for entity in domestic[:16]:
        _add_query(records, _append_query_suffix(f"今日 {entity} {topic_core} 发布 参数 更新", suffix), "domestic_company", "zh", 1)
        if tech_core:
            _add_query(records, _append_query_suffix(f"今日 {entity} {tech_core} {action_core}", suffix), "domestic_company", "zh", 2)
    for product in products[:12]:
        _add_query(records, _append_query_suffix(f"今日 {product} {topic_core} 发布 参数 供应链", suffix), "product", "zh", 2)
    for term in tech_terms[:12]:
        _add_query(records, _append_query_suffix(f"今日 {term} {topic_core} 新品 量产 供应链", suffix), "technology", "zh", 2)
    for supplier in supply_terms[:12]:
        _add_query(records, _append_query_suffix(f"今日 {supplier} {topic_core} 订单 量产 供应链", suffix), "supply_chain", "zh", 2)

    for entity in global_entities[:10]:
        _add_query(records, f"{entity} {topic_core or topic_name} launch update today", "global_company", "en", 3)
        if tech_core:
            _add_query(records, f"{entity} {tech_core} supply chain update today", "global_company", "en", 3)

    for domain in media_domains[:12]:
        _add_query(records, _append_query_suffix(f"site:{domain} {topic_core} 今日 {action_core}", suffix), "media", "zh", 1)
    for domain in high_domains[:8]:
        head_entity = domestic[0] if domestic else (global_entities[0] if global_entities else topic_core)
        _add_query(records, f"site:{domain} {head_entity} {topic_core} release update", "official", None, 1)

    # Keep discovery wide but deterministic: base/core/company queries first.
    unique = []
    seen = set()
    for record in sorted(records, key=lambda item: (item["priority"], item["query_type"], item["query"])):
        query = record["query"].strip()
        key = query.lower()
        if not query or key in seen:
            continue
        seen.add(key)
        unique.append(record)
        if max_queries and len(unique) >= max_queries:
            break
    return unique


CONSUMER_TOPIC_QUERY_PACKS = {
    "consumer_phone": ConsumerTopicQueryPack(
        topic_id="consumer_phone",
        topic_name="消费电子 / 手机产业",
        description="追踪国内外手机及消费电子产业的新品发布、参数升级、系统更新、端侧 AI、芯片、影像、屏幕、电池、快充、供应链、价格、销量、渠道和市场变化。",
        aliases=["手机", "智能手机", "消费电子", "手机产业", "smartphone", "mobile phone", "handset", "consumer electronics"],
        core_entities=["手机", "智能手机", "消费电子", "AI手机", "端侧AI"],
        domestic_entities=["华为", "小米", "Redmi", "vivo", "iQOO", "OPPO", "一加", "荣耀", "realme", "真我", "魅族", "努比亚", "红魔", "联想", "摩托罗拉中国"],
        global_entities=["Apple", "iPhone", "Samsung", "Galaxy", "Google Pixel", "Sony Xperia", "Motorola", "Nothing Phone", "Qualcomm", "MediaTek"],
        product_terms=["Mate", "Pura", "Nova", "Xiaomi", "Redmi", "iQOO", "Find", "Reno", "OnePlus", "Ace", "Magic", "Galaxy S", "Galaxy Z", "iPhone", "Pixel", "Xperia", "Android", "iOS", "HarmonyOS", "HyperOS", "ColorOS", "OriginOS", "MagicOS"],
        technology_terms=["SoC", "芯片", "骁龙", "天玑", "麒麟", "A系列芯片", "端侧AI", "AI手机", "大模型", "影像", "CMOS", "潜望长焦", "OLED", "LTPO", "屏幕", "电池", "快充", "散热", "卫星通信", "Wi-Fi 7", "UWB", "OTA", "系统更新", "预售", "开售", "销量", "价格"],
        supply_chain_terms=["Qualcomm", "MediaTek", "索尼半导体", "三星显示", "京东方", "维信诺", "TCL华星", "天马", "舜宇光学", "欧菲光", "立讯精密", "鹏鼎控股"],
        priority_terms=["发布", "新品", "参数", "升级", "开售", "预售", "OTA", "系统更新", "AI功能", "端侧AI", "芯片", "屏幕", "影像", "价格", "销量", "供应链", "量产"],
        deprioritize_terms=["手机壳", "贴膜", "二手报价", "促销软文", "评测汇总", "历史回顾", "旧款盘点", "壁纸", "游戏攻略", "法律纠纷", "隐私诉讼"],
        domains=["ithome.com", "mydrivers.com", "zol.com.cn", "pconline.com.cn", "cnmo.com", "ifanr.com", "leikeji.com", "theverge.com", "androidauthority.com", "gsmarena.com"],
        high_quality_domains=["apple.com", "samsung.com", "huawei.com", "mi.com", "vivo.com.cn", "oppo.com", "oneplus.com", "honor.com", "qualcomm.com", "mediatek.com"],
        queries=[
            "今日 手机 新品 参数 发布",
            "今日 华为 小米 vivo OPPO 一加 新机 参数",
            "今日 iPhone Samsung Galaxy 新品 参数",
            "今日 手机 AI 功能 端侧大模型 系统更新",
            "今日 手机 芯片 屏幕 影像 电池 快充",
            "今日 HarmonyOS HyperOS ColorOS OriginOS MagicOS 更新",
            "今日 手机 预售 开售 价格 销量",
            "今日 手机 供应链 芯片 OLED CMOS",
            "过去72小时 手机新品 参数 发布",
            "过去72小时 中国手机厂商 新品 AI 功能",
            "smartphone launch specs today",
            "iPhone Samsung Galaxy smartphone AI update today",
            "Android phone AI feature chip display battery today",
        ],
        verification_queries=[
            "{company} {product} 发布 参数 今日",
            "{company} {product} 系统更新 OTA 今日",
            "{company} {product} AI 功能 今日",
            "{company} {product} 价格 开售 今日",
            "{company} {product} IT之家",
            "{company} {product} 快科技",
            "{company} {product} 官方",
            "{company} {product} launch specs today",
        ],
        prompt_focus="请重点提取消费电子/手机产业中真实发生的新产品、新参数、新系统更新、新 AI 功能、供应链、价格、销量、开售、预售和市场变化。不要把旧款评测、促销软文、手机壳/配件广告、历史回顾当作新闻。每条新闻必须说明公司、产品、变化点、时间、来源和产业意义。",
    ),
    "ar_vr_ai_glasses": ConsumerTopicQueryPack(
        topic_id="ar_vr_ai_glasses",
        topic_name="AR / VR / XR / AI 眼镜",
        description="追踪国内外 AR、VR、XR、MR、AI 眼镜、智能眼镜、近眼显示、光波导、显示模组、光机、摄像头、语音交互、端侧 AI、空间计算及供应链动态。",
        aliases=["AI眼镜", "智能眼镜", "AR眼镜", "VR头显", "XR眼镜", "MR头显", "smart glasses", "AI glasses", "AR glasses", "XR headset", "VR headset", "near-eye display"],
        core_entities=["AI眼镜", "智能眼镜", "AR眼镜", "VR头显", "XR眼镜", "近眼显示", "光波导"],
        domestic_entities=["雷鸟", "雷鸟创新", "Rokid", "XREAL", "夸克", "影目", "INMO", "亮亮视野", "李未可", "小派", "Pico", "字节跳动", "华为智能眼镜", "小米智能眼镜", "OPPO Air Glass", "vivo MR", "百度"],
        global_entities=["Meta", "Ray-Ban Meta", "Quest", "Apple Vision Pro", "Google Android XR", "Samsung XR", "Snap Spectacles", "Vuzix", "Magic Leap", "HTC Vive", "Sony PSVR"],
        product_terms=["Ray-Ban Meta", "Meta Quest", "Quest 3", "Quest 3S", "Apple Vision Pro", "Android XR", "Galaxy XR", "Rokid Glasses", "XREAL Air", "雷鸟 Air", "雷鸟 V 系列", "夸克 AI 眼镜", "Pico", "PSVR"],
        technology_terms=["AI眼镜", "智能眼镜", "AR", "VR", "XR", "MR", "空间计算", "近眼显示", "光波导", "衍射光波导", "阵列光波导", "Birdbath", "LCoS", "Micro OLED", "MicroLED", "硅基OLED", "光机", "显示模组", "摄像头", "眼动追踪", "SLAM", "手势识别", "语音交互", "多模态AI", "端侧AI"],
        supply_chain_terms=["歌尔股份", "舜宇光学", "水晶光电", "蓝特光学", "兆威机电", "韦尔股份", "立讯精密", "长盈精密", "欧菲光", "三利谱", "京东方", "视涯", "JBD", "Lumus", "WaveOptics", "Dispelix"],
        priority_terms=["发布", "新品", "参数", "更新", "开售", "预售", "量产", "供应商", "光波导", "LCoS", "Micro OLED", "MicroLED", "近眼显示", "AI功能", "多模态", "端侧AI", "空间计算"],
        deprioritize_terms=["折叠手机", "普通手机", "手机壳", "普通蓝牙耳机", "游戏攻略", "旧款评测", "佩戴体验软文", "无参数体验稿", "历史盘点"],
        domains=["ithome.com", "leikeji.com", "ifanr.com", "zhidx.com", "qbitai.com", "jiqizhixin.com", "36kr.com", "mydrivers.com", "uploadvr.com", "roadtovr.com", "theverge.com"],
        high_quality_domains=["meta.com", "apple.com", "xreal.com", "rokid.com", "rayneo.com", "snap.com", "vuzix.com", "magicleap.com"],
        queries=[
            "今日 AI眼镜 发布 参数",
            "今日 智能眼镜 新品 功能 更新",
            "今日 AR眼镜 XR眼镜 近眼显示 新品",
            "今日 雷鸟 Rokid XREAL 夸克 AI眼镜",
            "今日 雷鸟创新 智能眼镜 参数 更新",
            "今日 Rokid 智能眼镜 发布 更新",
            "今日 XREAL AR眼镜 新品 参数",
            "今日 夸克 AI眼镜 功能 更新",
            "今日 Meta Ray-Ban AI glasses update",
            "今日 Apple Vision Pro Meta Quest Android XR 新闻",
            "今日 AR眼镜 光波导 供应链",
            "今日 智能眼镜 LCoS Micro OLED 显示模组",
            "今日 近眼显示 光机 AI眼镜 供应商",
            "过去72小时 AI眼镜 智能眼镜 新品 参数",
            "过去72小时 AR VR XR 头显 发布 更新",
            "today AI glasses launch update",
            "Ray-Ban Meta AI glasses update today",
            "AR glasses waveguide display supply chain today",
            "Micro OLED LCoS near-eye display smart glasses today",
        ],
        verification_queries=[
            "{company} {product} AI眼镜 今日",
            "{company} {product} 智能眼镜 发布 参数",
            "{company} {product} AR眼镜 更新",
            "{company} {product} 官方 发布",
            "{company} {product} IT之家",
            "{company} {product} 雷科技",
            "{company} {product} 量子位",
            "{company} {product} smart glasses update today",
            "{company} {product} AR glasses launch specs",
        ],
        prompt_focus="请重点提取 AR/VR/XR/AI 眼镜领域真实发生的产品发布、功能更新、参数升级、显示方案、光学方案、AI能力、供应链、量产、开售和融资动态。必须避免把普通手机新闻、折叠手机爆料、泛消费电子评论混入本专题。每条新闻必须说明产品形态、关键硬件/软件变化、来源数量、时间窗口和是否已多源确认。",
    ),
    "ai_weekly": ConsumerTopicQueryPack(
        topic_id="ai_weekly",
        topic_name="AI 一周资讯",
        description="追踪国内外 AI 大模型、AI Agent、多模态、端侧 AI、AI 搜索、AI 编程、模型 API、产品更新、商业化、监管政策、算力和应用生态的重要进展。国内 AI 权重高于海外，但海外重大新闻必须保留。",
        aliases=["AI", "人工智能", "大模型", "AI Agent", "智能体", "多模态", "端侧AI", "AI搜索", "LLM", "foundation model", "generative AI"],
        core_entities=["AI", "大模型", "AI Agent", "智能体", "多模态", "端侧AI"],
        domestic_entities=["DeepSeek", "豆包", "字节跳动", "火山引擎", "通义千问", "Qwen", "阿里云", "百度文心", "文心一言", "腾讯混元", "Kimi", "月之暗面", "智谱", "GLM", "MiniMax", "阶跃星辰", "讯飞星火", "华为盘古", "商汤", "百川智能", "零一万物"],
        global_entities=["OpenAI", "ChatGPT", "GPT", "Anthropic", "Claude", "Google Gemini", "DeepMind", "Meta AI", "Llama", "xAI", "Grok", "Perplexity", "Microsoft Copilot", "NVIDIA AI"],
        product_terms=["ChatGPT", "Claude", "Gemini", "DeepSeek", "豆包", "Qwen", "通义千问", "Kimi", "GLM", "混元", "文心一言", "Copilot", "Grok", "Perplexity", "Llama"],
        technology_terms=["大模型", "多模态", "推理模型", "AI Agent", "智能体", "端侧AI", "AI搜索", "AI浏览器", "AI手机", "AI PC", "模型开源", "API价格", "模型降价", "上下文窗口", "语音模型", "视频生成", "图像生成", "编程助手", "企业级AI", "算力", "GPU", "推理成本", "RAG", "MCP"],
        supply_chain_terms=["NVIDIA", "GPU", "算力", "数据中心", "云服务", "推理成本", "AI芯片", "服务器"],
        priority_terms=["发布", "更新", "开源", "API", "降价", "模型升级", "多模态", "推理模型", "Agent", "智能体", "产品上线", "商业化", "融资", "监管", "算力", "企业应用"],
        deprioritize_terms=["教程", "提示词合集", "工具推荐", "课程广告", "AI美女", "娱乐八卦", "旧模型盘点", "观点评论无事实"],
        domains=["qbitai.com", "jiqizhixin.com", "zhidx.com", "infoq.cn", "51cto.com", "aibase.com", "theverge.com", "techcrunch.com", "venturebeat.com"],
        high_quality_domains=["openai.com", "anthropic.com", "deepseek.com", "alibabacloud.com", "cloud.tencent.com", "baidu.com", "microsoft.com", "googleblog.com", "ai.googleblog.com", "meta.com", "nvidia.com"],
        queries=[
            "本周 国内 AI 大模型 发布 更新",
            "今日 DeepSeek 模型 更新 API",
            "今日 豆包 AI 更新 发布",
            "今日 通义千问 Qwen 模型 更新",
            "今日 Kimi 智谱 MiniMax 阶跃星辰 AI 新闻",
            "今日 百度文心 腾讯混元 华为盘古 AI",
            "今日 AI Agent 智能体 国内 发布",
            "今日 AI 搜索 AI 浏览器 国内 新闻",
            "本周 AI 模型 API 降价 开源 多模态",
            "本周 OpenAI Anthropic Gemini 最新",
            "本周 Claude ChatGPT Gemini 模型 更新",
            "本周 NVIDIA AI 算力 推理 成本 新闻",
            "this week AI model launch update",
            "OpenAI Anthropic Google Gemini update this week",
            "Claude ChatGPT Gemini model update today",
            "AI agent product launch this week",
        ],
        verification_queries=[
            "{company} {product} 模型 更新 本周",
            "{company} {product} API 发布",
            "{company} {product} 官方 发布",
            "{company} {product} 多模态 推理模型",
            "{company} {product} 量子位",
            "{company} {product} 机器之心",
            "{company} {product} InfoQ",
            "{company} {product} model update this week",
            "{company} {product} official release",
        ],
        prompt_focus="请重点提取 AI 领域一周内真实发生的重要产品、模型、API、开源、商业化、监管和算力事件。国内 AI 新闻权重应高于海外，但 OpenAI、Anthropic、Gemini、Meta、NVIDIA 等重大事件必须保留。不要输出 AI 工具推荐、教程、泛趋势评论、旧模型盘点。每条新闻必须说明模型/产品名称、发布主体、更新内容、时间、来源和影响。",
        time_window="7d",
    ),
    "ev_smart_car": ConsumerTopicQueryPack(
        topic_id="ev_smart_car",
        topic_name="电动汽车 / 智能汽车科技资讯",
        description="追踪国内外电动汽车和智能汽车领域的新车发布、智能驾驶、座舱、芯片、电池、补能、800V/900V、OTA、FSD、Robotaxi、供应链和市场动态。重点是科技资讯，不是普通汽车销售新闻。",
        aliases=["电动汽车", "新能源汽车", "智能汽车", "智驾", "自动驾驶", "smart EV", "electric vehicle", "autonomous driving", "intelligent vehicle"],
        core_entities=["电动汽车", "新能源汽车", "智能汽车", "智驾", "自动驾驶"],
        domestic_entities=["鸿蒙智行", "问界", "智界", "享界", "尊界", "比亚迪", "小鹏", "理想", "蔚来", "小米汽车", "极氪", "阿维塔", "智己", "零跑", "岚图", "吉利", "长安", "广汽", "上汽", "奇瑞", "长城", "宁德时代"],
        global_entities=["Tesla", "特斯拉", "Rivian", "Lucid", "BMW", "Mercedes-Benz", "Volkswagen", "Toyota", "Hyundai", "Kia"],
        product_terms=["FSD", "Robotaxi", "NOA", "城市NOA", "高阶智驾", "端到端", "鸿蒙座舱", "800V", "900V", "超充", "固态电池", "激光雷达", "毫米波雷达", "OTA", "座舱芯片", "电池包"],
        technology_terms=["智驾", "自动驾驶", "端到端", "高阶智驾", "NOA", "城市NOA", "Robotaxi", "FSD", "激光雷达", "毫米波雷达", "800V", "900V", "超充", "固态电池", "电池包", "座舱芯片", "OTA", "车机系统", "鸿蒙座舱", "辅助驾驶", "域控制器"],
        supply_chain_terms=["宁德时代", "比亚迪弗迪", "地平线", "黑芝麻智能", "Momenta", "禾赛科技", "速腾聚创", "德赛西威", "华阳集团", "均胜电子", "经纬恒润"],
        priority_terms=["发布", "新车", "OTA", "智驾", "端到端", "FSD", "Robotaxi", "电池", "800V", "超充", "芯片", "激光雷达", "供应链", "交付", "销量", "价格", "量产"],
        deprioritize_terms=["二手车报价", "经销商促销", "车主口碑", "事故纠纷", "保险", "改装", "贴膜", "普通试驾体验", "单纯降价促销"],
        domains=["autohome.com.cn", "dongchedi.com", "gasgoo.com", "d1ev.com", "42how.com", "xchuxing.com", "pcauto.com.cn", "cls.cn", "stcn.com", "yicai.com", "electrek.co", "insideevs.com"],
        high_quality_domains=["tesla.com", "byd.com", "nio.com", "xpeng.com", "lixiang.com", "mi.com", "huawei.com"],
        queries=[
            "今日 鸿蒙智行 新车 智驾 发布",
            "今日 问界 智界 享界 尊界 OTA 智驾",
            "今日 比亚迪 智驾 电池 新技术",
            "今日 小鹏 理想 蔚来 OTA 智驾",
            "今日 小米汽车 交付 OTA 智能驾驶",
            "今日 极氪 阿维塔 智己 零跑 智驾 更新",
            "今日 特斯拉 FSD Robotaxi 更新",
            "今日 800V 超充 固态电池 电动车",
            "今日 激光雷达 智驾 供应链",
            "今日 智能座舱 芯片 OTA 新闻",
            "过去72小时 新能源汽车 智驾 OTA 电池",
            "过去72小时 中国智能汽车 新车发布 技术升级",
            "today Tesla FSD Robotaxi update",
            "EV autonomous driving update today",
            "electric vehicle 800V battery charging update today",
            "smart cockpit chip OTA EV today",
        ],
        verification_queries=[
            "{company} {product} 智驾 OTA 今日",
            "{company} {product} 新车 发布 参数",
            "{company} {product} 电池 800V 超充",
            "{company} {product} 官方 发布",
            "{company} {product} 盖世汽车",
            "{company} {product} 汽车之家",
            "{company} {product} 懂车帝",
            "{company} {product} FSD Robotaxi update",
        ],
        prompt_focus="请重点提取电动汽车/智能汽车领域真实发生的科技事件，包括新车技术平台、智能驾驶、OTA、电池、补能、芯片、传感器、Robotaxi、FSD、供应链和量产交付。不要把普通促销、二手车、车主口碑、事故纠纷、普通试驾当作科技新闻。每条新闻必须说明车企、车型/平台、技术变化、时间、来源和产业影响。",
    ),
    "foldable_display_supply_chain": ConsumerTopicQueryPack(
        topic_id="foldable_display_supply_chain",
        topic_name="折叠手机 / Fast LCD / LCoS / 显示与近眼显示供应链",
        description="追踪折叠手机、柔性 OLED、铰链、UTG、Fast LCD、LCoS、Micro OLED、MicroLED、近眼显示、AR 显示模组和面板供应链的新品、技术、量产、订单和市场动态。",
        aliases=["折叠手机", "折叠屏", "柔性OLED", "Fast LCD", "LCoS", "Micro OLED", "MicroLED", "近眼显示", "foldable phone", "foldable display", "near-eye display"],
        core_entities=["折叠手机", "折叠屏", "柔性OLED", "Fast LCD", "LCoS", "Micro OLED", "MicroLED", "近眼显示"],
        domestic_entities=["华为", "小米", "vivo", "OPPO", "荣耀", "京东方", "维信诺", "TCL华星", "天马", "深天马", "视涯", "JBD", "联合光电", "水晶光电", "歌尔股份"],
        global_entities=["Apple", "Samsung", "Galaxy Z", "Motorola", "Sony Semiconductor", "eMagin", "Kopin", "Himax", "LG Display", "BOE", "Visionox"],
        product_terms=["Fold", "Flip", "Mate X", "Galaxy Z Fold", "Galaxy Z Flip", "折叠 iPhone", "UTG", "铰链", "柔性OLED", "LTPO", "Fast LCD", "LCoS", "Micro OLED", "MicroLED", "硅基OLED", "光机", "显示模组", "AR显示"],
        technology_terms=["折叠屏", "柔性OLED", "铰链", "UTG", "盖板玻璃", "LTPO", "OLED", "Fast LCD", "LCoS", "Micro OLED", "MicroLED", "硅基OLED", "近眼显示", "AR显示", "光机", "显示模组", "面板", "像素密度", "亮度", "刷新率", "良率", "量产"],
        supply_chain_terms=["京东方", "维信诺", "TCL华星", "天马", "深天马", "视涯", "JBD", "歌尔股份", "舜宇光学", "水晶光电", "蓝特光学", "三利谱", "兆威机电", "铰链供应商", "面板厂", "模组厂"],
        priority_terms=["发布", "新品", "量产", "订单", "供应链", "面板", "显示模组", "铰链", "UTG", "Micro OLED", "MicroLED", "LCoS", "Fast LCD", "近眼显示", "AR显示"],
        deprioritize_terms=["普通手机评测", "手机壳", "贴膜", "促销", "旧款盘点", "概念图", "无来源爆料", "壁纸", "游戏体验"],
        domains=["ithome.com", "ijiwei.com", "cinno.com.cn", "trendforce.cn", "oledindustry.com", "display.ofweek.com", "ee.ofweek.com", "laoyaoba.com"],
        high_quality_domains=["samsungdisplay.com", "boe.com", "visionox.com", "tclcsot.com", "tianma.com"],
        queries=[
            "今日 折叠手机 新品 参数",
            "今日 华为 三星 小米 vivo OPPO 折叠屏",
            "今日 苹果 折叠 iPhone 供应链",
            "今日 折叠屏 铰链 UTG OLED",
            "今日 折叠手机 面板 供应链",
            "今日 Fast LCD 显示 技术 新闻",
            "今日 LCoS 近眼显示 模组",
            "今日 Micro OLED AR 显示 供应链",
            "今日 MicroLED 近眼显示 AR",
            "今日 京东方 维信诺 TCL华星 天马 折叠屏",
            "今日 视涯 JBD Micro OLED MicroLED",
            "过去72小时 折叠屏 面板 量产 订单",
            "过去72小时 LCoS Micro OLED 近眼显示 供应链",
            "foldable phone launch specs today",
            "Apple foldable iPhone supply chain today",
            "Samsung foldable OLED hinge UTG update",
            "LCOS near-eye display AR glasses today",
            "Micro OLED AR display supplier today",
            "Fast LCD display technology update",
        ],
        verification_queries=[
            "{company} {product} 折叠屏 今日",
            "{company} {product} 面板 供应链",
            "{company} {product} LCoS Micro OLED",
            "{company} {product} 量产 订单",
            "{company} {product} 集微网",
            "{company} {product} CINNO",
            "{company} {product} TrendForce",
            "{company} {product} official display supply chain",
        ],
        prompt_focus="请重点提取折叠手机、显示技术和近眼显示供应链中的真实事件，包括新品、参数、面板供应、铰链、UTG、Fast LCD、LCoS、Micro OLED、MicroLED、量产、订单、供应商和技术路线变化。不要把普通手机评测、无来源概念图、促销信息、旧款盘点当作新闻。每条新闻必须说明公司、产品/技术、供应链环节、时间、来源和产业意义。",
    ),
    "robotics_embodied_ai": ConsumerTopicQueryPack(
        topic_id="robotics_embodied_ai",
        topic_name="机器人 / 具身智能",
        description="追踪国内外人形机器人、具身智能、工业/协作/服务机器人、机器人基础模型、关节模组、灵巧手、传感器、控制器、减速器、伺服、电机、量产、订单、融资和工厂部署动态。",
        aliases=["机器人", "具身智能", "人形机器人", "工业机器人", "协作机器人", "服务机器人", "humanoid robot", "embodied AI", "robotics", "industrial robot"],
        core_entities=["机器人", "具身智能", "人形机器人", "工业机器人", "协作机器人", "机器人基础模型"],
        domestic_entities=["宇树科技", "Unitree", "傅利叶智能", "优必选", "UBTech", "智元机器人", "AgiBot", "逐际动力", "星海图", "乐聚机器人", "小米机器人", "华为机器人", "大疆", "云深处", "梅卡曼德", "节卡机器人", "越疆科技", "埃斯顿", "埃夫特", "新松机器人", "汇川技术", "绿的谐波", "双环传动", "拓普集团", "三花智控", "鸣志电器", "奥比中光", "速腾聚创", "禾赛科技"],
        global_entities=["Tesla Optimus", "Figure AI", "Boston Dynamics", "Agility Robotics", "Sanctuary AI", "NVIDIA Isaac", "Covariant", "Apptronik", "1X", "Google DeepMind Robotics", "Amazon Robotics", "ABB", "FANUC", "Yaskawa", "KUKA"],
        product_terms=["Optimus", "Figure 02", "Atlas", "Digit", "Walker S", "G1", "H1", "R1", "GR-1", "灵巧手", "机械臂", "协作机器人", "AMR", "AGV", "机器人关节", "执行器"],
        technology_terms=["具身智能", "机器人基础模型", "VLA", "视觉语言动作模型", "模仿学习", "强化学习", "运动控制", "端到端控制", "触觉传感", "六维力传感器", "关节模组", "行星滚柱丝杠", "谐波减速器", "RV减速器", "伺服电机", "编码器", "控制器", "末端执行器", "灵巧手", "SLAM", "3D视觉", "机械臂", "人机协作"],
        supply_chain_terms=["绿的谐波", "双环传动", "汇川技术", "鸣志电器", "拓普集团", "三花智控", "柯力传感", "汉威科技", "奥比中光", "禾赛科技", "速腾聚创", "凌云光", "埃斯顿", "新松机器人", "中大力德", "步科股份", "昊志机电"],
        priority_terms=["发布", "新品", "量产", "订单", "交付", "工厂部署", "融资", "参数", "负载", "续航", "速度", "成本", "供应链", "关节模组", "减速器", "伺服", "灵巧手", "具身模型", "VLA"],
        deprioritize_terms=["玩具机器人", "扫地机器人促销", "儿童玩具", "概念视频", "无来源爆料", "股票荐股", "普通展会回顾", "旧款盘点", "单纯股价"],
        domains=["ithome.com", "jiqizhixin.com", "qbitai.com", "zhidx.com", "leiphone.com", "36kr.com", "ofweek.com", "elecfans.com", "gongkong.com", "therobotreport.com", "roboticsbusinessreview.com", "ieee.org", "techcrunch.com", "theverge.com"],
        high_quality_domains=["unitree.com", "ubtrobot.com", "agibot.com", "fftai.com", "deeprobotics.cn", "dobot.cc", "jaka.com", "estun.com", "siasun.com", "tesla.com", "figure.ai", "bostondynamics.com", "agilityrobotics.com", "apptronik.com", "nvidia.com", "abb.com", "fanuc.co.jp", "yaskawa-global.com", "kuka.com"],
        queries=[
            "今日 人形机器人 发布 参数",
            "今日 具身智能 机器人 新闻",
            "今日 宇树 智元 优必选 傅利叶 机器人",
            "今日 人形机器人 量产 订单 交付",
            "今日 机器人 关节模组 减速器 伺服",
            "今日 灵巧手 触觉传感 机器人",
            "今日 机器人 VLA 具身模型",
            "今日 工业机器人 协作机器人 产线部署",
            "今日 机器人 供应链 传感器 控制器",
            "今日 宇树 Unitree 人形机器人 参数",
            "今日 智元机器人 AgiBot 发布 量产",
            "今日 优必选 Walker S 交付 订单",
            "今日 傅利叶 GR-1 机器人 更新",
            "今日 特斯拉 Optimus 机器人 更新",
            "今日 Figure AI humanoid robot update",
            "今日 NVIDIA Isaac 机器人 具身智能",
            "过去72小时 中国 人形机器人 量产 订单",
            "过去72小时 具身智能 机器人 融资 发布",
            "today humanoid robot embodied AI launch",
            "humanoid robot actuator supply chain today",
            "robot foundation model VLA update today",
            "industrial robot collaborative robot deployment today",
        ],
        verification_queries=[
            "{company} {product} 机器人 今日",
            "{company} {product} 人形机器人 发布 参数",
            "{company} {product} 具身智能 更新",
            "{company} {product} 量产 订单 交付",
            "{company} {product} 官方 发布",
            "{company} {product} 机器之心",
            "{company} {product} 量子位",
            "{company} {product} 智东西",
            "{company} {product} humanoid robot update today",
            "{company} {product} embodied AI robotics launch",
        ],
        prompt_focus="请重点提取机器人/具身智能领域真实发生的产品发布、参数升级、工厂部署、量产交付、订单、融资、核心零部件和供应链事件。中国国内机器人公司、国产供应链、关节模组、减速器、伺服、灵巧手、传感器、控制器和具身模型优先。不要把玩具机器人、扫地机器人促销、无来源概念视频、单纯股价和旧展会回顾当作正式新闻。",
    ),
}


def get_consumer_topic_query_pack(topic_id):
    key = str(topic_id or "").strip()
    if key not in CONSUMER_TOPIC_QUERY_PACKS:
        raise KeyError(f"Unknown consumer topic id: {topic_id}")
    return deepcopy(CONSUMER_TOPIC_QUERY_PACKS[key])


def get_all_consumer_topic_query_packs():
    return [deepcopy(pack) for pack in CONSUMER_TOPIC_QUERY_PACKS.values()]


def get_all_consumer_topic_dicts():
    return [pack.to_topic_dict() for pack in get_all_consumer_topic_query_packs()]


def build_consumer_topic_queries_from_pack(pack, query_suffix="", max_queries=None):
    records = build_consumer_topic_query_records_from_pack(
        pack,
        query_suffix=query_suffix,
        max_queries=max_queries,
    )
    return [record["query"] for record in records]


def build_consumer_topic_focus_hint(pack):
    payload = _pack_dict(pack)
    pieces = [
        payload.get("prompt_focus", ""),
        "频道三是六专题科技消费电子日报，不是公司金融分析。",
        "必须优先保留产品、参数、技术路线、供应链、量产、价格、销量、渠道和公司动作。",
        "旧闻回顾、推荐流、促销软文、单纯股价、法律隐私类陪衬新闻默认降权。",
    ]
    priority = "、".join(payload.get("priority_terms", [])[:12])
    if priority:
        pieces.append(f"优先事件类型：{priority}")
    domains = "、".join(payload.get("high_quality_domains", [])[:10])
    if domains:
        pieces.append(f"优先来源：{domains}")
    return "；".join(item for item in pieces if item)


def generate_consumer_topic_event_master(ai_driver, topic_pack, search_results, current_date, time_label, history_context=""):
    from agents.timeline_agent import build_event_blueprints

    payload = _pack_dict(topic_pack)
    return build_event_blueprints(
        ai_driver,
        list(search_results or [])[:30],
        payload.get("title") or payload.get("topic_name") or payload.get("topic_id") or "",
        current_date,
        time_label,
        history_hint=history_context,
        guidance=build_consumer_topic_focus_hint(topic_pack),
    )


def _contains_cjk(text):
    return bool(re.search(r"[\u4e00-\u9fff]", str(text or "")))


def _host(url):
    try:
        from urllib.parse import urlparse

        host = (urlparse(str(url or "")).netloc or "").lower()
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return ""


def _count_hits(text, terms):
    haystack = str(text or "").lower()
    return sum(1 for term in terms or [] if str(term or "").strip().lower() in haystack)


def _normalize_text(text):
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", str(text or "").lower())


def _result_similarity(left, right):
    left_url = str(left.get("url", "") or "").lower()
    right_url = str(right.get("url", "") or "").lower()
    if left_url and right_url and left_url == right_url:
        return 1.0
    left_title = _normalize_text(left.get("title", ""))
    right_title = _normalize_text(right.get("title", ""))
    if not left_title or not right_title:
        return 0.0
    return difflib.SequenceMatcher(None, left_title, right_title).ratio()


def _consumer_result_category(item, payload):
    blob = f"{item.get('title', '')} {item.get('content', '')}".lower()
    if _count_hits(blob, payload.get("supply_chain_terms", [])) >= 1:
        return "supply_chain"
    if _count_hits(blob, payload.get("technology_terms", [])) >= 1:
        return "technology"
    if _count_hits(blob, payload.get("product_terms", [])) >= 1:
        return "product"
    if _count_hits(blob, payload.get("domestic_entities", [])) >= 1:
        return "domestic_company"
    if _count_hits(blob, payload.get("global_entities", [])) >= 1:
        return "global_company"
    return "generic"


def _category_caps(limit):
    base = max(int(limit or CONSUMER_TOPIC_DEFAULT_LIMIT), 1)
    return {
        "supply_chain": max(10, base // 4),
        "technology": max(14, base // 3),
        "product": max(16, base // 3),
        "domestic_company": max(18, base // 3),
        "global_company": max(10, base // 4),
        "generic": max(8, base // 6),
    }


def rank_results_by_consumer_topic_pack(results, topic_pack, limit=CONSUMER_TOPIC_DEFAULT_LIMIT):
    payload = _pack_dict(topic_pack)
    high_domains = [domain.lower() for domain in payload.get("high_quality_domains", []) or []]
    domains = [domain.lower() for domain in payload.get("domains", []) or []]
    scored = []
    for idx, item in enumerate(results or []):
        title = str(item.get("title", "") or "")
        content = str(item.get("content", "") or item.get("snippet", "") or "")
        url = str(item.get("url", "") or "")
        host = _host(url)
        title_l = title.lower()
        blob = f"{title} {content} {url}".lower()

        score = 0.0
        score += _count_hits(title_l, payload.get("core_entities", [])) * 4.2
        score += _count_hits(title_l, payload.get("domestic_entities", [])) * 3.3
        score += _count_hits(title_l, payload.get("global_entities", [])) * 2.1
        score += _count_hits(title_l, payload.get("product_terms", [])) * 2.4
        score += _count_hits(title_l, payload.get("technology_terms", [])) * 2.3
        score += _count_hits(title_l, payload.get("supply_chain_terms", [])) * 2.1
        score += _count_hits(blob, payload.get("priority_terms", [])) * 1.3
        score += _count_hits(blob, payload.get("domestic_entities", [])) * 0.8
        score += _count_hits(blob, payload.get("technology_terms", [])) * 0.65
        score += _count_hits(blob, payload.get("supply_chain_terms", [])) * 0.65
        score -= _count_hits(blob, payload.get("deprioritize_terms", [])) * 2.2
        score -= _count_hits(blob, _NOISE_TERMS) * 1.8
        if any(host == domain or host.endswith(f".{domain}") for domain in high_domains):
            score += 2.5
        elif any(host == domain or host.endswith(f".{domain}") for domain in domains):
            score += 1.2
        if host.endswith(".cn") or _contains_cjk(f"{title} {content}"):
            score += 0.8
        if item.get("published_at_resolved") or item.get("published_date") or item.get("published"):
            score += 0.4
        try:
            score += min(float(item.get("score", 0) or 0), 1.0) * 0.4
        except Exception:
            pass

        category = _consumer_result_category(item, payload)
        enriched = dict(item)
        enriched["_consumer_topic_score"] = round(score, 4)
        enriched["_consumer_topic_category"] = category
        scored.append({"score": score, "category": category, "index": -idx, "item": enriched})

    scored.sort(key=lambda row: (row["score"], row["index"]), reverse=True)
    caps = _category_caps(limit)
    selected = []
    category_counts = {}
    for row in scored:
        if len(selected) >= limit:
            break
        if row["score"] < -4.5:
            continue
        if any(_result_similarity(row["item"], picked["item"]) >= 0.93 for picked in selected):
            continue
        category = row["category"]
        if category_counts.get(category, 0) >= caps.get(category, limit):
            continue
        selected.append(row)
        category_counts[category] = category_counts.get(category, 0) + 1

    if len(selected) < min(limit, 20):
        for row in scored:
            if len(selected) >= limit:
                break
            if row in selected:
                continue
            if any(_result_similarity(row["item"], picked["item"]) >= 0.95 for picked in selected):
                continue
            selected.append(row)
    return [row["item"] for row in selected[:limit]]


def _timelimit_from_window(window):
    value = str(window or "").lower()
    if value in {"today", "24h", "d", "day"}:
        return "d"
    if value in {"72h", "7d", "w", "week"}:
        return "w"
    return "w"


def _max_age_for_window(window):
    value = str(window or "").lower()
    if value == "today":
        return 30
    if value in {"24h", "d", "day"}:
        return 30
    if value == "72h":
        return 78
    if value in {"7d", "w", "week"}:
        return 24 * 7 + 6
    return 78


def collect_consumer_topic_search_results(
    topic_pack,
    lookback_window,
    exa_key="",
    exa_settings=None,
    query_suffix="",
    search_depth="wide",
    max_candidates=CONSUMER_TOPIC_DEFAULT_LIMIT,
):
    if not exa_key:
        raise RuntimeError("EXA_API_KEY is required for channel 3 Exa-only consumer topic search.")

    depth_limits = {"light": 18, "normal": 36, "wide": 60}
    max_queries = depth_limits.get(str(search_depth or "wide").lower(), 60)
    queries = build_consumer_topic_queries_from_pack(topic_pack, query_suffix=query_suffix, max_queries=max_queries)
    timelimit = _timelimit_from_window(lookback_window)
    merged = []
    seen_urls = set()
    for query in queries:
        batch = search_web(
            query,
            "",
            timelimit,
            max_results=CONSUMER_TOPIC_RESULTS_PER_QUERY,
            provider="exa",
            exa_key=exa_key,
            exa_settings=exa_settings,
            tavily_key="",
        )
        for item in batch or []:
            url = str(item.get("url") or "").strip()
            if url and url in seen_urls:
                continue
            if url:
                seen_urls.add(url)
            enriched = dict(item)
            enriched["topic_id"] = _pack_dict(topic_pack).get("topic_id") or _pack_dict(topic_pack).get("id")
            enriched["query"] = query
            merged.append(enriched)
    ranked = rank_results_by_consumer_topic_pack(merged, topic_pack, limit=max_candidates)
    return ranked, {"query_count": len(queries), "raw_result_count": len(merged), "candidate_count": len(ranked)}


def filter_consumer_results_by_freshness(results, topic_pack, lookback_window, current_dt=None):
    now = current_dt or datetime.datetime.now(datetime.timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=datetime.timezone.utc)
    max_age_hours = _max_age_for_window(lookback_window)
    filtered, stats, warnings = audit_recent_news_results(
        results,
        now=now,
        max_age_hours=max_age_hours,
        future_tolerance_hours=6,
        enabled=True,
    )
    stats["topic_id"] = _pack_dict(topic_pack).get("topic_id") or _pack_dict(topic_pack).get("id")
    stats["time_window"] = str(lookback_window or "")
    return filtered, stats, warnings
