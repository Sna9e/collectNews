from copy import deepcopy


GENERAL_SOURCE_DOMAINS = [
    "techcrunch.com",
    "theverge.com",
    "engadget.com",
    "cnet.com",
    "bloomberg.com",
    "electrek.co",
    "insideevs.com",
    "roadtovr.com",
    "uploadvr.com",
    "36kr.com",
    "ithome.com",
    "huxiu.com",
    "geekpark.net",
    "vrtuoluo.cn",
    "d1ev.com",
]


CHINA_BASELINE_DOMAINS = [
    "36kr.com",
    "ithome.com",
    "huxiu.com",
    "leiphone.com",
    "geekpark.net",
    "jiqizhixin.com",
    "qbitai.com",
    "tmtpost.com",
    "pedaily.cn",
    "cyzone.cn",
    "iyiou.com",
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


FOCUS_SECTOR_PACKS = [
    {
        "id": "pcb_fpc",
        "title": "PCB/FPC与高速互连",
        "queries": [
            "PCB FPC HDI 柔性电路板 扩产 订单",
            "ABF 载板 PCB FPC 材料 厂商 最新进展",
            "消费电子 PCB FPC 高速互连 新品 产能",
        ],
        "desc": "重点关注 PCB、FPC、HDI、载板、覆铜板、铜箔、PI 材料、扩产、订单、ASP 变化。",
        "tags": ["PCB", "FPC", "HDI", "ABF载板", "覆铜板", "铜箔", "高速互连"],
        "keywords": [
            "pcb", "fpc", "hdi", "abf", "载板", "覆铜板", "铜箔", "pi", "柔性电路板",
            "slp", "高速互连", "扩产", "订单", "产能", "服务器板", "ai服务器"
        ],
        "companies": [
            "欣兴", "深南电路", "沪电股份", "东山精密", "鹏鼎控股", "胜宏科技",
            "AT&S", "Ibiden", "Unimicron"
        ],
        "domains": ["iconnect007.com", "ipc.org", "elecfans.com", "ijiwei.com", "ofweek.com", "eeworld.com.cn"],
        "china_domains": ["elecfans.com", "ijiwei.com", "ofweek.com", "eeworld.com.cn"],
    },
    {
        "id": "cpo_optics",
        "title": "CPO光模块与硅光互连",
        "queries": [
            "CPO 光模块 1.6T 3.2T 最新进展",
            "硅光 CPO LPO 高速光互连 AI 数据中心",
            "800G 1.6T 光模块 量产 订单",
        ],
        "desc": "重点关注 CPO、LPO、硅光、DSP、CW Laser、EML、800G/1.6T/3.2T 光模块、AI 数据中心互连。",
        "tags": ["CPO", "硅光", "LPO", "800G", "1.6T", "3.2T", "数据中心光互连"],
        "keywords": [
            "cpo", "lpo", "硅光", "co-packaged optics", "1.6t", "3.2t", "800g",
            "光模块", "高速光互连", "cw laser", "dsp", "inphi", "ai数据中心"
        ],
        "companies": [
            "Broadcom", "Marvell", "NVIDIA", "Cisco", "Lumentum", "Coherent",
            "中际旭创", "新易盛", "天孚通信", "光迅科技", "华工科技"
        ],
        "domains": ["lightwaveonline.com", "c-fol.net", "elecfans.com", "ijiwei.com", "ofweek.com"],
        "china_domains": ["c-fol.net", "elecfans.com", "ijiwei.com", "ofweek.com"],
    },
    {
        "id": "satcom_ntn",
        "title": "卫星通信与直连终端",
        "queries": [
            "卫星通信 手机直连 NTN 最新进展",
            "低轨卫星 直连手机 模组 芯片",
            "卫星互联网 卫星通信 终端 模组 订单",
        ],
        "desc": "重点关注卫星通信、NTN、直连手机、低轨星座、终端芯片、模组、相控阵与终端侧落地。",
        "tags": ["卫星通信", "NTN", "直连手机", "低轨卫星", "终端模组", "卫星互联网"],
        "keywords": [
            "卫星通信", "ntn", "direct-to-device", "d2d", "低轨卫星", "leo",
            "直连手机", "相控阵", "卫星互联网", "终端模组", "卫星终端", "non-terrestrial"
        ],
        "companies": [
            "SpaceX", "Starlink", "AST SpaceMobile", "Globalstar", "Lynk",
            "中国卫通", "华力创通", "海格通信", "移远通信", "广和通"
        ],
        "domains": ["spacenews.com", "satnews.com", "c114.com.cn", "elecfans.com", "ijiwei.com"],
        "china_domains": ["c114.com.cn", "elecfans.com", "ijiwei.com"],
    },
    {
        "id": "auto_optics",
        "title": "智能车光学与感知",
        "queries": [
            "智能驾驶 激光雷达 摄像头 光学模组 量产",
            "智能汽车 HUD DMS OMS 车载光学 最新进展",
            "自动驾驶 激光雷达 车载传感器 订单",
        ],
        "desc": "重点关注激光雷达、车载摄像头、HUD、DMS/OMS、红外、车载镜头与感知链条量产进展。",
        "tags": ["激光雷达", "车载摄像头", "HUD", "DMS", "OMS", "车载光学"],
        "keywords": [
            "激光雷达", "lidar", "车载摄像头", "hud", "dms", "oms", "红外",
            "车载镜头", "自动驾驶", "智能驾驶", "感知", "光学模组"
        ],
        "companies": [
            "禾赛科技", "速腾聚创", "图达通", "舜宇光学", "欧菲光",
            "联创电子", "水晶光电", "德赛西威", "Mobileye", "Luminar"
        ],
        "domains": ["gasgoo.com", "d1ev.com", "elecfans.com", "leiphone.com", "ijiwei.com"],
        "china_domains": ["gasgoo.com", "d1ev.com", "elecfans.com", "ijiwei.com"],
    },
]


EXPANDED_TREND_TOPICS = [
    {
        "title": "AI手机与硬件承载",
        "queries": ["AI手机 硬件演进 2026", "智能手机内部空间 SLP 类载板", "消费电子 FPC 技术 突破"],
        "desc": "关注AI手机内部空间极度压缩、SLP与FPC的技术演进。",
    },
    {
        "title": "折叠与多维形态变革",
        "queries": ["三折叠手机 最新发布", "卷轴屏 手机 量产", "无孔化手机 Waterproof Buttonless 设计"],
        "desc": "关注三折叠手机、卷轴屏、以及无孔化设计的最新突破。",
    },
    {
        "title": "6G预研与卫星通讯",
        "queries": ["6G预研 最新进展", "高通 6G AI 整合芯片", "卫星通讯 手机直连 NTN"],
        "desc": "重点关注高通6GAI芯片及卫星直连技术（NTN）的进展。",
    },
    {
        "title": "AI穿戴与XR设备",
        "queries": ["超轻量化 AI眼镜 评测", "智能戒指 SmartRing 生态", "XR混合现实 硬件 创新"],
        "desc": "关注超轻量化AI眼镜、智能戒指的爆款产品。",
    },
    {
        "title": "绿色制程与可持续性",
        "queries": ["消费电子 绿色制程 创新", "欧洲市场 电子产品 碳足迹 法规", "科技巨头 ESG 战略"],
        "desc": "关注碳足迹硬性要求（ESG）及绿色制程策略。",
    },
    {
        "title": "全球机器人产业巡视",
        "queries": ["全球 机器人 产业 报告 2026", "特斯拉 宇树科技 机器人 动态", "人形机器人 创业公司"],
        "desc": "考察全球及中国厂商，覆盖大厂及新兴创业厂商。",
    },
]


CONSUMER_ELECTRONICS_SOURCE_DOMAINS = [
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
    "ijiwei.com",
    "c114.com.cn",
    "gasgoo.com",
    "d1ev.com",
    "ee.ofweek.com",
    "eeo.com.cn",
    "gsmarena.com",
    "androidauthority.com",
    "9to5mac.com",
    "macrumors.com",
    "theverge.com",
    "engadget.com",
    "cnet.com",
    "uploadvr.com",
    "roadtovr.com",
    "electrek.co",
    "insideevs.com",
]


CONSUMER_ELECTRONICS_TOPICS = [
    {
        "title": "消费电子与手机新品",
        "queries": [
            "华为 小米 vivo OPPO 一加 荣耀 手机 新品 参数 今日 发布",
            "中国 智能手机 影像 芯片 屏幕 电池 快充 AI 功能 最新",
            "苹果 三星 iPhone Galaxy 手机 新品 参数 中国 供应链",
            "HarmonyOS HyperOS OriginOS ColorOS iOS Android 手机系统 软件 今日 最新",
        ],
        "desc": "面向 FPC 制造商研发部门，重点关注手机新品参数提升、内部结构变化、影像/屏幕/电池/快充/散热/AI功能、系统软件更新及其对 FPC、连接器、模组和供应链的影响；国内新闻同等重要度优先。",
        "tags": ["手机新品", "消费电子", "FPC", "影像模组", "屏幕", "电池快充", "端侧AI"],
        "keywords": [
            "手机", "新品", "参数", "发布", "影像", "摄像头", "屏幕", "折叠", "电池", "快充",
            "散热", "AI手机", "端侧AI", "FPC", "柔性电路", "供应链", "量产", "产能"
        ],
        "companies": [
            "苹果", "Apple", "三星", "Samsung", "华为", "小米", "vivo", "OPPO", "一加", "荣耀",
            "立讯精密", "鹏鼎控股", "东山精密", "舜宇光学", "欧菲光"
        ],
        "domains": ["gsmarena.com", "androidauthority.com", "9to5mac.com", "macrumors.com", "theverge.com", "engadget.com"],
        "china_domains": ["ithome.com", "mydrivers.com", "cnmo.com", "zol.com.cn", "pconline.com.cn", "36kr.com", "elecfans.com"],
        "deprioritize_terms": ["lawsuit", "court", "attorney", "copyright", "privacy", "security", "breach", "诉讼", "版权", "隐私", "安全漏洞"],
        "china_priority": True,
    },
    {
        "title": "AR/VR与AI眼镜",
        "queries": [
            "雷鸟 Rokid XREAL 华为 小米 AI眼镜 新品 参数 今日 最新",
            "中国 AI眼镜 AR VR 光波导 LCoS Micro OLED 供应链 量产",
            "Meta Ray-Ban Apple Vision Pro AI glasses AR VR 最新 供应商",
            "智能眼镜 摄像头 传感器 显示模组 国内厂商 最新",
        ],
        "desc": "重点关注 AR/VR、AI 眼镜、近眼显示、光波导、MicroLED、LCoS、Micro OLED、摄像头/传感器模组和供应商动态；国内外产品都保留，国内供应链优先。",
        "tags": ["AI眼镜", "AR", "VR", "光波导", "LCoS", "MicroLED", "供应链"],
        "keywords": [
            "AI眼镜", "AR", "VR", "XR", "光波导", "MicroLED", "Micro OLED", "LCoS", "显示模组",
            "摄像头", "传感器", "供应商", "量产", "新品", "参数"
        ],
        "companies": ["Meta", "雷鸟", "Rokid", "Xreal", "Apple", "华为", "小米", "歌尔股份", "水晶光电", "舜宇光学"],
        "domains": ["uploadvr.com", "roadtovr.com", "theverge.com", "cnet.com", "engadget.com"],
        "china_domains": ["ithome.com", "mydrivers.com", "36kr.com", "geekpark.net", "elecfans.com", "ofweek.com"],
        "deprioritize_terms": ["lawsuit", "court", "attorney", "copyright", "privacy", "security", "breach", "诉讼", "版权", "隐私", "安全漏洞"],
        "china_priority": True,
    },
    {
        "title": "AI国内外重要资讯",
        "queries": [
            "豆包 DeepSeek 阿里 通义 百度 文心 腾讯 混元 华为 盘古 今日 最新",
            "中国 AI 大模型 多模态 端侧AI 应用 发布 今日 重要",
            "OpenAI Anthropic Google 大模型 AI 最新 重要",
            "AI 模型 推理 芯片 手机 PC 终端部署 国产 最新",
        ],
        "desc": "重点关注国内外重要 AI 新闻，尤其是豆包、DeepSeek、阿里、百度、腾讯、华为、OpenAI、Anthropic 等模型、端侧部署、多模态、推理成本和硬件结合；国内新闻优先。",
        "tags": ["AI", "大模型", "多模态", "端侧AI", "推理", "国产AI", "硬件部署"],
        "keywords": [
            "AI", "大模型", "多模态", "端侧AI", "推理", "训练", "芯片", "手机", "PC", "应用",
            "豆包", "DeepSeek", "OpenAI", "Anthropic", "国产", "发布"
        ],
        "companies": ["豆包", "字节", "DeepSeek", "阿里", "通义", "百度", "文心", "腾讯", "混元", "华为", "OpenAI", "Anthropic", "Google"],
        "domains": ["theverge.com", "techcrunch.com", "cnbc.com", "bloomberg.com"],
        "china_domains": ["jiqizhixin.com", "qbitai.com", "ithome.com", "36kr.com", "huxiu.com", "geekpark.net", "leiphone.com"],
        "deprioritize_terms": ["lawsuit", "court", "attorney", "copyright", "privacy", "security", "breach", "诉讼", "版权", "隐私", "安全漏洞"],
        "china_priority": True,
    },
    {
        "title": "电动汽车智能科技",
        "queries": [
            "鸿蒙智行 比亚迪 小鹏 理想 蔚来 智能驾驶 座舱 今日 最新",
            "中国 新能源汽车 激光雷达 800V 电池 快充 OTA 供应链 最新",
            "华为 比亚迪 小鹏 智驾 芯片 传感器 新车型 今日 发布",
            "特斯拉 FSD Robotaxi 中国 智能驾驶 电动汽车 最新",
        ],
        "desc": "重点关注智能电动车技术新闻，国内品牌优先，包含鸿蒙智行、比亚迪、小鹏、理想、蔚来、特斯拉等在智能驾驶、座舱、电子电气架构、电池快充和传感器供应链上的进展。",
        "tags": ["电动汽车", "智能驾驶", "座舱", "800V", "电池快充", "传感器", "供应链"],
        "keywords": [
            "电动汽车", "新能源汽车", "智能驾驶", "座舱", "激光雷达", "传感器", "800V", "电池",
            "快充", "OTA", "芯片", "供应链", "量产", "发布"
        ],
        "companies": ["鸿蒙智行", "华为", "比亚迪", "小鹏", "理想", "蔚来", "特斯拉", "Tesla", "Mobileye", "禾赛科技"],
        "domains": ["electrek.co", "insideevs.com", "theverge.com", "cnbc.com"],
        "china_domains": ["d1ev.com", "gasgoo.com", "ithome.com", "mydrivers.com", "36kr.com", "elecfans.com"],
        "deprioritize_terms": ["lawsuit", "court", "attorney", "copyright", "privacy", "security", "breach", "诉讼", "版权", "隐私", "安全漏洞"],
        "china_priority": True,
    },
    {
        "title": "折叠屏与新型显示",
        "queries": [
            "华为 vivo OPPO 小米 荣耀 三星 折叠手机 铰链 屏幕 今日 最新",
            "中国 折叠屏 LTPO UTG CPI 铰链 FPC 供应链 量产 最新",
            "Fast LCD LCoS Micro OLED MicroLED 近眼显示 国内 供应链",
            "苹果 折叠 iPhone 三星 华为 供应链 屏幕 铰链 最新",
        ],
        "desc": "重点关注折叠手机、三折叠、Fast LCD、LCoS、Micro OLED/MicroLED、LTPO、UTG/CPI、铰链和 FPC 相关供应链，覆盖华为、苹果、vivo、OPPO、小米、三星等。",
        "tags": ["折叠屏", "Fast LCD", "LCoS", "Micro OLED", "LTPO", "铰链", "FPC"],
        "keywords": [
            "折叠屏", "折叠手机", "三折叠", "铰链", "LTPO", "UTG", "CPI", "FPC", "柔性电路",
            "Fast LCD", "LCoS", "Micro OLED", "MicroLED", "显示", "供应链"
        ],
        "companies": ["华为", "Apple", "苹果", "vivo", "OPPO", "小米", "三星", "京东方", "维信诺", "TCL华星", "鹏鼎控股"],
        "domains": ["gsmarena.com", "androidauthority.com", "9to5mac.com", "macrumors.com", "theverge.com"],
        "china_domains": ["ithome.com", "mydrivers.com", "cnmo.com", "zol.com.cn", "elecfans.com", "ofweek.com"],
        "deprioritize_terms": ["lawsuit", "court", "attorney", "copyright", "privacy", "security", "breach", "诉讼", "版权", "隐私", "安全漏洞"],
        "china_priority": True,
    },
]


def _dedupe(items):
    merged = []
    seen = set()
    for item in items:
        value = (item or "").strip()
        if not value or value in seen:
            continue
        merged.append(value)
        seen.add(value)
    return merged


def get_default_sites_text():
    sector_domains = []
    for pack in FOCUS_SECTOR_PACKS:
        sector_domains.extend(pack.get("domains", []))
    return "\n".join(_dedupe(GENERAL_SOURCE_DOMAINS + sector_domains))


def get_default_china_sites_text():
    sector_domains = []
    for pack in FOCUS_SECTOR_PACKS:
        sector_domains.extend(pack.get("china_domains", []))
    return "\n".join(_dedupe(CHINA_BASELINE_DOMAINS + sector_domains))


def get_industry_topics():
    return [deepcopy(item) for item in FOCUS_SECTOR_PACKS + EXPANDED_TREND_TOPICS]


def get_consumer_electronics_sites_text():
    china_domains = []
    global_domains = []
    for pack in CONSUMER_ELECTRONICS_TOPICS:
        china_domains.extend(pack.get("china_domains", []))
        global_domains.extend(pack.get("domains", []))
    return "\n".join(_dedupe(CONSUMER_ELECTRONICS_SOURCE_DOMAINS + china_domains + global_domains))


def get_consumer_electronics_topics():
    return [deepcopy(item) for item in CONSUMER_ELECTRONICS_TOPICS]


def build_focus_hint(topic_pack, china_mode=False):
    tags = "、".join(topic_pack.get("tags", [])[:8])
    keywords = "、".join(topic_pack.get("keywords", [])[:12])
    companies = "、".join(topic_pack.get("companies", [])[:10])
    lines = [topic_pack.get("desc", "")]
    if tags:
        lines.append(f"重点标签：{tags}")
    if keywords:
        lines.append(f"优先命中关键词：{keywords}")
    if companies:
        lines.append(f"优先关注公司/主体：{companies}")
    if topic_pack.get("china_priority"):
        lines.append("同等重要度下优先保留中国国内新闻、中国公司动态、国产供应链、量产参数和政策变化；国外新闻只保留确有技术或供应链参考价值的重大事件。")
        lines.append("法律、版权、隐私、安全漏洞、黑客攻击类新闻默认降权，除非直接影响硬件量产、供应链准入或监管政策。")
    if china_mode:
        lines.append("若为中国专题，仅保留中文站点与中国公司相关事件。")
    return "；".join([line for line in lines if line])


def score_result_against_pack(result, topic_pack):
    title = str(result.get("title", "") or "").lower()
    content = str(result.get("content", "") or "").lower()
    url = str(result.get("url", "") or "").lower()
    blob = f"{title} {content} {url}"

    score = 0.0
    for keyword in topic_pack.get("keywords", []):
        if keyword and keyword.lower() in blob:
            score += 1.4
    for company in topic_pack.get("companies", []):
        if company and company.lower() in blob:
            score += 2.0
    for domain in topic_pack.get("domains", []) + topic_pack.get("china_domains", []):
        if domain and domain.lower() in url:
            score += 1.2
    if topic_pack.get("china_priority"):
        if any(domain and domain.lower() in url for domain in topic_pack.get("china_domains", [])):
            score += 2.0
        if any("\u4e00" <= ch <= "\u9fff" for ch in f"{title} {content}"):
            score += 1.0
        if any(term and term.lower() in blob for term in topic_pack.get("deprioritize_terms", [])):
            score -= 2.2
    return round(score, 4)


def rank_results_by_pack(results, topic_pack, limit=None):
    scored = []
    for idx, item in enumerate(results or []):
        score = score_result_against_pack(item, topic_pack)
        scored.append((score, idx, item))

    if any(score > 0 for score, _, _ in scored):
        scored = [item for item in scored if item[0] > 0]

    scored.sort(key=lambda item: (-item[0], item[1]))
    ranked = [item[2] for item in scored]
    if limit:
        return ranked[:limit]
    return ranked
