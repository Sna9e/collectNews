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
