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
    "vrtuoluo.cn",
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
        "id": "consumer_phone",
        "topic_name": "消费电子/手机产业",
        "title": "消费电子与手机新品",
        "queries": [
            "华为 小米 vivo OPPO 一加 荣耀 手机 新品 参数 今日 发布",
            "中国 智能手机 影像 芯片 屏幕 电池 快充 AI 功能 最新",
            "苹果 三星 iPhone Galaxy 手机 新品 参数 中国 供应链",
            "HarmonyOS HyperOS OriginOS ColorOS iOS Android 手机系统 软件 今日 最新",
        ],
        "daily_queries": [
            "今日 手机新品 华为 小米 vivo OPPO 荣耀 参数 供应链 市场销量",
            "中国手机市场 今日 旗舰机 销量 影像 屏幕 快充 FPC",
            "消费电子 今日 硬件 新品 发布 供应链 订单 市场份额",
            "今日 手机 AI功能 系统更新 端侧大模型 iOS HarmonyOS HyperOS ColorOS",
            "今日 iPhone Galaxy 华为 小米 vivo OPPO 新机 爆料 参数 价格",
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
        "domestic_company_terms": ["华为", "小米", "Redmi", "vivo", "iQOO", "OPPO", "一加", "荣耀", "realme", "魅族", "传音"],
        "global_company_terms": ["Apple", "iPhone", "Samsung", "Galaxy", "Google Pixel", "Qualcomm", "MediaTek"],
        "boost_terms": ["参数", "价格", "影像", "SoC", "屏幕", "电池", "快充", "散热", "端侧AI", "系统更新", "供应链", "销量", "市场份额"],
        "required_terms": [
            "手机", "智能手机", "iPhone", "Galaxy", "华为", "小米", "vivo", "OPPO", "一加", "荣耀",
            "影像", "快充", "电池", "屏幕", "端侧AI", "FPC", "供应链"
        ],
        "domains": ["gsmarena.com", "androidauthority.com", "9to5mac.com", "macrumors.com", "theverge.com", "engadget.com"],
        "china_domains": ["ithome.com", "mydrivers.com", "cnmo.com", "zol.com.cn", "pconline.com.cn", "36kr.com", "elecfans.com"],
        "deprioritize_terms": ["lawsuit", "court", "attorney", "copyright", "privacy", "security", "breach", "诉讼", "版权", "隐私", "安全漏洞"],
        "negative_terms": ["macOS", "游戏折扣", "优惠券", "股价", "股票", "教程", "壁纸", "二手"],
        "china_priority": True,
    },
    {
        "id": "ar_vr_ai_glasses",
        "topic_name": "AR/VR/XR/AI眼镜",
        "title": "AR/VR与AI眼镜",
        "queries": [
            "雷鸟 Rokid XREAL 华为 小米 AI眼镜 新品 参数 今日 最新",
            "中国 AI眼镜 AR VR 光波导 LCoS Micro OLED 供应链 量产",
            "Meta Ray-Ban Apple Vision Pro AI glasses AR VR 最新 供应商",
            "智能眼镜 摄像头 传感器 显示模组 国内厂商 最新",
        ],
        "daily_queries": [
            "今日 AI眼镜 雷鸟 Rokid XREAL 夸克 小米 华为 新品 参数 市场",
            "中国 智能眼镜 今日 光波导 LCoS Micro OLED 摄像头 传感器 供应链",
            "AI眼镜 今日 销量 市场份额 618 雷鸟 Rokid XREAL Meta Ray-Ban",
            "雷鸟创新 Rokid 阿里夸克 AI眼镜 今日 发布 量产 供应链",
            "近眼显示 今日 光波导 LCoS MicroLED Micro OLED 国内厂商",
            "今日 AR眼镜 VR头显 AI眼镜 价格 发售 渠道 供应商",
            "今日 Ray-Ban Meta Quest Vision Pro XREAL Rokid 雷鸟 智能眼镜",
        ],
        "desc": "重点关注 AR/VR、AI 眼镜、近眼显示、光波导、MicroLED、LCoS、Micro OLED、摄像头/传感器模组和供应商动态；国内外产品都保留，国内供应链优先。",
        "tags": ["AI眼镜", "AR", "VR", "光波导", "LCoS", "MicroLED", "供应链"],
        "keywords": [
            "AI眼镜", "AR", "VR", "XR", "光波导", "MicroLED", "Micro OLED", "LCoS", "显示模组",
            "摄像头", "传感器", "供应商", "量产", "新品", "参数"
        ],
        "companies": ["Meta", "雷鸟", "雷鸟创新", "Rokid", "Xreal", "XREAL", "夸克", "阿里", "Apple", "华为", "小米", "歌尔股份", "水晶光电", "舜宇光学"],
        "domestic_company_terms": ["雷鸟", "雷鸟创新", "Rokid", "XREAL", "夸克", "阿里", "华为", "小米", "歌尔股份", "水晶光电", "舜宇光学"],
        "global_company_terms": ["Meta", "Ray-Ban Meta", "Quest", "Apple Vision Pro", "Google", "Samsung", "Snap"],
        "boost_terms": ["AI眼镜", "智能眼镜", "AR眼镜", "VR头显", "XR", "近眼显示", "光波导", "LCoS", "Micro OLED", "MicroLED", "Birdbath", "摄像头", "传感器", "量产", "销量", "价格"],
        "required_terms": [
            "AI眼镜", "智能眼镜", "AR眼镜", "VR", "XR", "AR", "Vision Pro", "Ray-Ban", "Meta Quest",
            "雷鸟", "Rokid", "XREAL", "夸克", "光波导", "LCoS", "Micro OLED", "MicroLED", "近眼显示", "显示模组"
        ],
        "domains": ["uploadvr.com", "roadtovr.com", "theverge.com", "cnet.com", "engadget.com"],
        "china_domains": ["ithome.com", "mydrivers.com", "36kr.com", "geekpark.net", "elecfans.com", "ofweek.com", "vrtuoluo.cn", "huxiu.com", "qbitai.com"],
        "deprioritize_terms": ["lawsuit", "court", "attorney", "copyright", "privacy", "security", "breach", "诉讼", "版权", "隐私", "安全漏洞"],
        "negative_terms": ["折叠iPhone", "折叠 iPhone", "折叠手机", "手机壳", "macOS", "普通手机", "游戏"],
        "china_priority": True,
    },
    {
        "id": "ai_weekly",
        "topic_name": "AI一周资讯/AI科技动态",
        "title": "AI国内外重要资讯",
        "queries": [
            "豆包 DeepSeek 阿里 通义 百度 文心 腾讯 混元 华为 盘古 今日 最新",
            "中国 AI 大模型 多模态 端侧AI 应用 发布 今日 重要",
            "OpenAI Anthropic Google 大模型 AI 最新 重要",
            "AI 模型 推理 芯片 手机 PC 终端部署 国产 最新",
        ],
        "daily_queries": [
            "今日 国产AI 豆包 DeepSeek 通义 文心 混元 大模型 发布 应用",
            "中国 AI 今日 多模态 端侧AI 手机 PC 硬件部署 芯片 推理",
            "AI 今日 OpenAI Anthropic Google 大模型 发布 监管 市场",
            "今日 豆包 Kimi 智谱 MiniMax 阶跃星辰 讯飞星火 模型 应用",
            "今日 OpenAI Anthropic Gemini Meta AI xAI Perplexity API 价格 产品",
        ],
        "desc": "重点关注国内外重要 AI 新闻，尤其是豆包、DeepSeek、阿里、百度、腾讯、华为、OpenAI、Anthropic 等模型、端侧部署、多模态、推理成本和硬件结合；国内新闻优先。",
        "tags": ["AI", "大模型", "多模态", "端侧AI", "推理", "国产AI", "硬件部署"],
        "keywords": [
            "AI", "大模型", "多模态", "端侧AI", "推理", "训练", "芯片", "手机", "PC", "应用",
            "豆包", "DeepSeek", "OpenAI", "Anthropic", "国产", "发布"
        ],
        "companies": ["豆包", "字节", "DeepSeek", "阿里", "通义", "百度", "文心", "腾讯", "混元", "华为", "OpenAI", "Anthropic", "Google"],
        "domestic_company_terms": ["豆包", "字节", "DeepSeek", "阿里", "通义", "Qwen", "百度", "文心", "腾讯", "混元", "Kimi", "月之暗面", "智谱", "MiniMax", "阶跃星辰", "讯飞星火", "华为盘古"],
        "global_company_terms": ["OpenAI", "Anthropic", "Claude", "Google", "Gemini", "Meta AI", "Microsoft Copilot", "xAI", "Perplexity", "NVIDIA"],
        "boost_terms": ["模型发布", "多模态", "端侧AI", "AI手机", "AI PC", "API", "价格", "推理", "硬件适配", "商业化", "融资", "监管政策"],
        "required_terms": ["AI", "大模型", "多模态", "端侧AI", "推理", "豆包", "DeepSeek", "通义", "文心", "混元", "OpenAI", "Anthropic"],
        "domains": ["theverge.com", "techcrunch.com", "cnbc.com", "bloomberg.com"],
        "china_domains": ["jiqizhixin.com", "qbitai.com", "ithome.com", "36kr.com", "huxiu.com", "geekpark.net", "leiphone.com"],
        "deprioritize_terms": ["lawsuit", "court", "attorney", "copyright", "privacy", "security", "breach", "诉讼", "版权", "隐私", "安全漏洞"],
        "negative_terms": ["AI美女", "头像生成", "壁纸", "提示词教程", "股票评级", "股价"],
        "china_priority": True,
    },
    {
        "id": "smart_ev",
        "topic_name": "电动汽车/智能汽车科技",
        "title": "电动汽车智能科技",
        "queries": [
            "鸿蒙智行 比亚迪 小鹏 理想 蔚来 智能驾驶 座舱 今日 最新",
            "中国 新能源汽车 激光雷达 800V 电池 快充 OTA 供应链 最新",
            "华为 比亚迪 小鹏 智驾 芯片 传感器 新车型 今日 发布",
            "特斯拉 FSD Robotaxi 中国 智能驾驶 电动汽车 最新",
        ],
        "daily_queries": [
            "今日 中国新能源汽车 智能驾驶 比亚迪 小鹏 理想 蔚来 鸿蒙智行 市场销量",
            "今日 智能电动车 硬件 激光雷达 800V 快充 电池 座舱 供应链",
            "华为乾崑 鸿蒙智行 今日 新车 OTA 智驾 芯片 传感器",
            "今日 小米汽车 极氪 阿维塔 零跑 智己 岚图 智驾 OTA 交付",
            "今日 Tesla FSD Robotaxi Rivian Lucid 智能电动车 技术 动态",
        ],
        "desc": "重点关注智能电动车技术新闻，国内品牌优先，包含鸿蒙智行、比亚迪、小鹏、理想、蔚来、特斯拉等在智能驾驶、座舱、电子电气架构、电池快充和传感器供应链上的进展。",
        "tags": ["电动汽车", "智能驾驶", "座舱", "800V", "电池快充", "传感器", "供应链"],
        "keywords": [
            "电动汽车", "新能源汽车", "智能驾驶", "座舱", "激光雷达", "传感器", "800V", "电池",
            "快充", "OTA", "芯片", "供应链", "量产", "发布"
        ],
        "companies": ["鸿蒙智行", "华为", "比亚迪", "小鹏", "理想", "蔚来", "特斯拉", "Tesla", "Mobileye", "禾赛科技"],
        "domestic_company_terms": ["鸿蒙智行", "问界", "智界", "享界", "尊界", "比亚迪", "小鹏", "理想", "蔚来", "小米汽车", "极氪", "阿维塔", "零跑", "智己", "岚图", "吉利", "长安", "广汽", "上汽"],
        "global_company_terms": ["Tesla", "Rivian", "Lucid", "BMW", "Mercedes-Benz", "Volkswagen", "Toyota", "Hyundai"],
        "boost_terms": ["新车发布", "智驾芯片", "激光雷达", "端到端智驾", "座舱芯片", "电池技术", "补能", "800V", "900V", "OTA", "FSD", "Robotaxi", "交付", "销量", "供应链"],
        "required_terms": ["电动汽车", "新能源汽车", "智能驾驶", "智驾", "座舱", "激光雷达", "800V", "快充", "电池", "比亚迪", "小鹏", "鸿蒙智行", "特斯拉"],
        "domains": ["electrek.co", "insideevs.com", "theverge.com", "cnbc.com"],
        "china_domains": ["d1ev.com", "gasgoo.com", "ithome.com", "mydrivers.com", "36kr.com", "elecfans.com"],
        "deprioritize_terms": ["lawsuit", "court", "attorney", "copyright", "privacy", "security", "breach", "诉讼", "版权", "隐私", "安全漏洞"],
        "negative_terms": ["二手车", "车险", "交通事故", "召回", "投诉", "改装", "油车"],
        "china_priority": True,
    },
    {
        "id": "foldable_display_supply",
        "topic_name": "折叠屏/Fast LCD/LCoS/显示供应链",
        "title": "折叠屏与新型显示",
        "queries": [
            "华为 vivo OPPO 小米 荣耀 三星 折叠手机 铰链 屏幕 今日 最新",
            "中国 折叠屏 LTPO UTG CPI 铰链 FPC 供应链 量产 最新",
            "Fast LCD LCoS Micro OLED MicroLED 近眼显示 国内 供应链",
            "苹果 折叠 iPhone 三星 华为 供应链 屏幕 铰链 最新",
        ],
        "daily_queries": [
            "今日 折叠屏 华为 vivo OPPO 小米 荣耀 三星 铰链 屏幕 供应链",
            "中国 新型显示 今日 Fast LCD LCoS Micro OLED MicroLED 近眼显示",
            "今日 显示供应链 京东方 维信诺 TCL华星 LTPO UTG CPI FPC",
            "今日 折叠手机 Fold Flip UTG OLED 柔性屏 铰链 量产",
            "今日 LCoS Micro OLED 光学模组 AR显示 视涯 JBD 供应链",
        ],
        "desc": "重点关注折叠手机、三折叠、Fast LCD、LCoS、Micro OLED/MicroLED、LTPO、UTG/CPI、铰链和 FPC 相关供应链，覆盖华为、苹果、vivo、OPPO、小米、三星等。",
        "tags": ["折叠屏", "Fast LCD", "LCoS", "Micro OLED", "LTPO", "铰链", "FPC"],
        "keywords": [
            "折叠屏", "折叠手机", "三折叠", "铰链", "LTPO", "UTG", "CPI", "FPC", "柔性电路",
            "Fast LCD", "LCoS", "Micro OLED", "MicroLED", "显示", "供应链"
        ],
        "companies": ["华为", "Apple", "苹果", "vivo", "OPPO", "小米", "三星", "京东方", "维信诺", "TCL华星", "鹏鼎控股"],
        "domestic_company_terms": ["华为", "vivo", "OPPO", "小米", "荣耀", "京东方", "维信诺", "TCL华星", "天马", "视涯", "JBD", "鹏鼎控股", "东山精密"],
        "global_company_terms": ["Apple", "Samsung", "Galaxy Fold", "Galaxy Flip", "LG Display"],
        "boost_terms": ["折叠屏", "三折叠", "Fold", "Flip", "铰链", "UTG", "CPI", "OLED", "柔性屏", "Fast LCD", "LCoS", "Micro OLED", "MicroLED", "近眼显示", "光学模组", "面板厂", "量产"],
        "required_terms": ["折叠屏", "折叠手机", "三折叠", "铰链", "屏幕", "显示", "LCoS", "Fast LCD", "Micro OLED", "MicroLED", "LTPO", "UTG", "FPC"],
        "domains": ["gsmarena.com", "androidauthority.com", "9to5mac.com", "macrumors.com", "theverge.com"],
        "china_domains": ["ithome.com", "mydrivers.com", "cnmo.com", "zol.com.cn", "elecfans.com", "ofweek.com"],
        "deprioritize_terms": ["lawsuit", "court", "attorney", "copyright", "privacy", "security", "breach", "诉讼", "版权", "隐私", "安全漏洞"],
        "negative_terms": ["普通手机", "手机系统", "手机壳", "macOS", "游戏", "优惠"],
        "china_priority": True,
    },
    {
        "id": "robotics_embodied_ai",
        "topic_name": "机器人/具身智能",
        "title": "机器人与具身智能",
        "queries": [
            "宇树 智元 优必选 傅利叶 人形机器人 今日 发布 参数",
            "中国 具身智能 机器人 量产 订单 供应链 今日",
            "机器人 关节模组 减速器 伺服 灵巧手 传感器 最新",
            "Tesla Optimus Figure AI humanoid robot embodied AI latest",
        ],
        "daily_queries": [
            "今日 人形机器人 发布 参数 宇树 智元 优必选 傅利叶",
            "今日 具身智能 机器人 新闻 中国 公司 量产 订单",
            "今日 机器人 关节模组 减速器 伺服 控制器 供应链",
            "今日 灵巧手 触觉传感 机器人 VLA 具身模型",
            "今日 工业机器人 协作机器人 产线部署 国产替代",
        ],
        "desc": "重点关注人形机器人、具身智能、工业/协作机器人、机器人基础模型、关节模组、灵巧手、传感器、控制器、减速器、伺服、电机、量产、订单、融资和工厂部署动态；中国国内公司和国产供应链优先。",
        "tags": ["机器人", "具身智能", "人形机器人", "工业机器人", "关节模组", "灵巧手", "供应链"],
        "keywords": [
            "机器人", "具身智能", "人形机器人", "工业机器人", "协作机器人", "机器人基础模型",
            "VLA", "关节模组", "谐波减速器", "RV减速器", "伺服电机", "灵巧手", "传感器",
            "控制器", "量产", "订单", "交付", "工厂部署"
        ],
        "companies": ["宇树科技", "Unitree", "智元机器人", "优必选", "傅利叶智能", "逐际动力", "特斯拉", "Tesla", "Figure AI", "绿的谐波", "汇川技术", "鸣志电器"],
        "domestic_company_terms": ["宇树科技", "Unitree", "智元机器人", "AgiBot", "优必选", "UBTech", "傅利叶智能", "逐际动力", "星海图", "乐聚机器人", "小米机器人", "华为机器人", "埃斯顿", "埃夫特", "新松机器人", "汇川技术", "绿的谐波", "双环传动", "拓普集团", "三花智控", "鸣志电器", "奥比中光"],
        "global_company_terms": ["Tesla Optimus", "Figure AI", "Boston Dynamics", "Agility Robotics", "NVIDIA Isaac", "Apptronik", "1X", "ABB", "FANUC", "Yaskawa", "KUKA"],
        "boost_terms": ["发布", "新品", "量产", "订单", "交付", "工厂部署", "融资", "参数", "关节模组", "减速器", "伺服", "灵巧手", "具身模型", "VLA", "供应链"],
        "required_terms": ["机器人", "具身智能", "人形机器人", "工业机器人", "协作机器人", "关节模组", "灵巧手", "宇树", "智元", "优必选", "傅利叶", "Optimus"],
        "domains": ["therobotreport.com", "roboticsbusinessreview.com", "techcrunch.com", "theverge.com"],
        "china_domains": ["ithome.com", "jiqizhixin.com", "qbitai.com", "zhidx.com", "leiphone.com", "ofweek.com", "elecfans.com", "gongkong.com", "36kr.com"],
        "deprioritize_terms": ["lawsuit", "court", "attorney", "copyright", "privacy", "security", "breach", "诉讼", "版权", "隐私", "安全漏洞"],
        "negative_terms": ["玩具机器人", "扫地机器人促销", "儿童玩具", "概念视频", "股票荐股", "旧款盘点", "单纯股价"],
        "china_priority": True,
    },
]


CONSUMER_DAILY_BREADTH_POOLS = {
    "consumer_phone": {
        "domestic_company_terms": ["华为", "小米", "vivo", "OPPO", "一加", "荣耀", "realme", "魅族", "努比亚", "红魔", "iQOO", "Redmi", "真我"],
        "global_company_terms": ["Apple", "iPhone", "Samsung", "Galaxy", "Google Pixel", "Sony Xperia", "Motorola", "Nothing Phone", "Qualcomm", "MediaTek"],
        "product_terms": ["Mate", "Pura", "Nova", "Xiaomi", "Redmi", "iQOO", "Find", "Reno", "OnePlus", "Magic", "Galaxy S", "Galaxy Z", "iPhone", "iOS", "Android", "HarmonyOS", "HyperOS", "ColorOS", "OriginOS", "MagicOS"],
        "technology_terms": ["SoC", "芯片", "骁龙", "天玑", "麒麟", "A系列芯片", "影像", "潜望长焦", "CMOS", "屏幕", "OLED", "LTPO", "电池", "快充", "散热", "卫星通信", "端侧AI", "AI手机", "大模型", "系统更新", "OTA"],
        "supply_chain_terms": ["OLED", "CMOS", "摄像头模组", "FPC", "连接器", "散热", "电池", "快充芯片", "供应链", "量产", "订单"],
        "action_terms": ["价格", "销量", "发布会", "预售", "开售", "参数", "更新", "OTA", "上市"],
        "synonym_terms": ["智能手机", "新机", "旗舰机", "手机新品", "端侧大模型", "AI功能"],
        "english_terms": ["today smartphone launch specs", "Apple iPhone update specs today", "Samsung Galaxy launch specs today", "Android phone AI feature update today", "smartphone supply chain OLED camera chip today"],
    },
    "ar_vr_ai_glasses": {
        "domestic_company_terms": ["雷鸟", "雷鸟创新", "Rokid", "XREAL", "夸克", "影目", "INMO", "亮亮视野", "李未可", "小派", "Pico", "华为智能眼镜", "小米智能眼镜", "OPPO Air Glass", "vivo MR", "百度", "字节跳动"],
        "global_company_terms": ["Meta", "Ray-Ban Meta", "Quest", "Apple Vision Pro", "Google Android XR", "Samsung XR", "Snap Spectacles", "Vuzix", "Magic Leap", "HTC Vive", "Sony PSVR"],
        "product_terms": ["Ray-Ban Meta", "Meta Quest", "Vision Pro", "Android XR", "Spectacles", "OPPO Air Glass", "AI眼镜", "智能眼镜", "AR眼镜", "XR眼镜", "MR头显", "VR头显"],
        "technology_terms": ["AI眼镜", "智能眼镜", "AR眼镜", "XR眼镜", "MR头显", "VR头显", "近眼显示", "光波导", "衍射光波导", "阵列光波导", "Birdbath", "LCoS", "Micro OLED", "MicroLED", "硅基OLED", "显示模组", "光机", "镜片", "眼动追踪", "SLAM", "摄像头", "语音交互", "端侧AI", "多模态AI", "空间计算"],
        "supply_chain_terms": ["歌尔股份", "舜宇光学", "水晶光电", "蓝特光学", "兆威机电", "韦尔股份", "立讯精密", "长盈精密", "欧菲光", "三利谱", "京东方", "视涯", "JBD", "Lumus", "WaveOptics", "Dispelix"],
        "action_terms": ["发布", "更新", "参数", "价格", "销量", "供应链", "发售", "渠道", "量产", "融资"],
        "synonym_terms": ["AI glasses", "smart glasses", "AR glasses", "near eye display", "waveguide", "optical engine"],
        "english_terms": ["today AI glasses launch update", "Ray-Ban Meta AI glasses update today", "Meta Quest update launch today", "Apple Vision Pro update today", "Android XR smart glasses today", "AR glasses waveguide display supply chain today", "Micro OLED AR glasses supplier today", "LCOS near eye display smart glasses today"],
    },
    "ai_weekly": {
        "domestic_company_terms": ["DeepSeek", "豆包", "字节跳动", "火山引擎", "通义千问", "Qwen", "阿里云", "百度文心", "文心一言", "腾讯混元", "Kimi", "月之暗面", "智谱", "GLM", "MiniMax", "阶跃星辰", "讯飞星火", "华为盘古", "商汤", "百川智能", "零一万物"],
        "global_company_terms": ["OpenAI", "ChatGPT", "GPT", "Anthropic", "Claude", "Google Gemini", "DeepMind", "Meta AI", "Llama", "xAI", "Grok", "Perplexity", "Microsoft Copilot", "NVIDIA AI"],
        "product_terms": ["DeepSeek", "豆包", "Qwen", "通义千问", "Kimi", "GLM", "GPT", "ChatGPT", "Claude", "Gemini", "Llama", "Grok", "Copilot"],
        "technology_terms": ["大模型", "多模态", "推理模型", "AI Agent", "智能体", "端侧AI", "AI搜索", "AI浏览器", "AI手机", "AI PC", "模型开源", "API价格", "模型降价", "上下文窗口", "语音模型", "视频生成", "图像生成", "编程助手", "企业级AI", "算力", "GPU", "推理成本"],
        "supply_chain_terms": ["算力", "GPU", "NVIDIA", "国产算力", "AI芯片", "推理成本", "端侧部署", "AI手机", "AI PC"],
        "action_terms": ["发布", "更新", "开源", "API", "降价", "融资", "商业化", "监管", "产品上线"],
        "synonym_terms": ["生成式AI", "AI模型", "智能体", "推理", "多模态模型", "AI产品"],
        "english_terms": ["this week AI model launch update", "OpenAI Anthropic Google Gemini update this week", "Claude ChatGPT Gemini model update today", "AI agent product launch today", "NVIDIA AI model inference update this week"],
    },
    "smart_ev": {
        "domestic_company_terms": ["鸿蒙智行", "问界", "智界", "享界", "尊界", "比亚迪", "小鹏", "理想", "蔚来", "小米汽车", "极氪", "阿维塔", "智己", "零跑", "岚图", "吉利", "长安", "广汽", "上汽", "奇瑞", "长城"],
        "global_company_terms": ["Tesla", "特斯拉", "Rivian", "Lucid", "BMW", "Mercedes-Benz", "Volkswagen", "Toyota", "Hyundai", "Kia"],
        "product_terms": ["FSD", "Robotaxi", "NOA", "城市NOA", "鸿蒙座舱", "乾崑智驾", "端到端智驾", "800V", "900V", "超充"],
        "technology_terms": ["智驾", "高阶智驾", "端到端", "NOA", "城市NOA", "Robotaxi", "FSD", "自动驾驶", "激光雷达", "毫米波雷达", "800V", "900V", "超充", "固态电池", "电池包", "座舱芯片", "OTA", "车机系统", "鸿蒙座舱"],
        "supply_chain_terms": ["宁德时代", "比亚迪弗迪", "地平线", "黑芝麻智能", "Momenta", "禾赛科技", "速腾聚创", "德赛西威", "华阳集团", "均胜电子", "经纬恒润"],
        "action_terms": ["交付", "销量", "价格", "新车发布", "OTA", "更新", "量产", "订单", "融资"],
        "synonym_terms": ["新能源汽车", "智能电动车", "智能汽车", "自动驾驶", "智能座舱", "补能"],
        "english_terms": ["today Tesla FSD Robotaxi update", "EV autonomous driving update today", "electric vehicle 800V battery charging update today", "smart cockpit chip OTA EV today"],
    },
    "foldable_display_supply": {
        "domestic_company_terms": ["华为", "三星", "苹果", "vivo", "OPPO", "小米", "荣耀", "摩托罗拉", "京东方", "维信诺", "TCL华星", "天马", "深天马", "视涯", "JBD"],
        "global_company_terms": ["Apple", "Samsung", "Motorola", "Galaxy Fold", "Galaxy Flip", "eMagin", "Sony Semiconductor", "LG Display"],
        "product_terms": ["Fold", "Flip", "折叠iPhone", "折叠屏", "折叠手机", "Fast LCD", "LCoS", "Micro OLED", "MicroLED", "硅基OLED"],
        "technology_terms": ["折叠屏", "折叠手机", "Fold", "Flip", "铰链", "UTG", "柔性OLED", "OLED", "LTPO", "Fast LCD", "LCoS", "Micro OLED", "MicroLED", "硅基OLED", "近眼显示", "AR显示", "光机", "显示模组", "面板", "盖板玻璃", "屏幕供应链"],
        "supply_chain_terms": ["京东方", "维信诺", "TCL华星", "天马", "视涯", "JBD", "eMagin", "Sony Semiconductor", "铰链", "UTG", "FPC", "盖板玻璃", "面板厂"],
        "action_terms": ["发布", "参数", "供应链", "量产", "订单", "价格", "销量", "开售", "更新"],
        "synonym_terms": ["foldable phone", "foldable iPhone", "near eye display", "display module", "OLED hinge UTG"],
        "english_terms": ["foldable phone launch specs today", "Apple foldable iPhone supply chain today", "Samsung foldable OLED hinge UTG update", "LCOS near eye display AR glasses today", "Micro OLED AR display supplier today", "Fast LCD display technology update"],
    },
    "robotics_embodied_ai": {
        "domestic_company_terms": ["宇树科技", "Unitree", "智元机器人", "AgiBot", "优必选", "UBTech", "傅利叶智能", "逐际动力", "星海图", "乐聚机器人", "小米机器人", "华为机器人", "埃斯顿", "埃夫特", "新松机器人", "汇川技术", "绿的谐波", "双环传动", "拓普集团", "三花智控", "鸣志电器", "奥比中光"],
        "global_company_terms": ["Tesla Optimus", "Figure AI", "Boston Dynamics", "Agility Robotics", "Sanctuary AI", "NVIDIA Isaac", "Covariant", "Apptronik", "1X", "ABB", "FANUC", "Yaskawa", "KUKA"],
        "product_terms": ["Optimus", "Figure 02", "Atlas", "Digit", "Walker S", "G1", "H1", "GR-1", "灵巧手", "机械臂", "协作机器人", "AMR", "AGV", "机器人关节", "执行器"],
        "technology_terms": ["具身智能", "机器人基础模型", "VLA", "视觉语言动作模型", "模仿学习", "强化学习", "运动控制", "端到端控制", "触觉传感", "六维力传感器", "关节模组", "行星滚柱丝杠", "谐波减速器", "RV减速器", "伺服电机", "编码器", "控制器", "末端执行器", "灵巧手", "SLAM", "3D视觉", "机械臂", "人机协作"],
        "supply_chain_terms": ["绿的谐波", "双环传动", "汇川技术", "鸣志电器", "拓普集团", "三花智控", "柯力传感", "汉威科技", "奥比中光", "禾赛科技", "速腾聚创", "凌云光", "埃斯顿", "新松机器人", "中大力德", "步科股份", "昊志机电"],
        "action_terms": ["发布", "新品", "量产", "订单", "交付", "工厂部署", "融资", "参数", "负载", "续航", "速度", "成本", "供应链"],
        "synonym_terms": ["humanoid robot", "embodied AI", "robotics", "robot foundation model", "dexterous hand", "robot actuator"],
        "english_terms": ["today humanoid robot embodied AI launch", "humanoid robot actuator supply chain today", "robot foundation model VLA update today", "industrial robot collaborative robot deployment today"],
    },
}


CONSUMER_DAILY_MEDIA_DOMAINS = {
    "consumer_electronics_cn": ["ithome.com", "mydrivers.com", "zol.com.cn", "pconline.com.cn", "cnmo.com", "anzhuo.cn", "leikeji.com", "ifanr.com"],
    "ai_cn": ["qbitai.com", "jiqizhixin.com", "51cto.com", "infoq.cn", "zhidx.com", "aibase.com"],
    "auto_cn": ["autohome.com.cn", "dongchedi.com", "gasgoo.com", "d1ev.com", "42how.com", "xchuxing.com", "pcauto.com.cn"],
    "semiconductor_display_cn": ["ijiwei.com", "cinno.com.cn", "trendforce.cn", "oledindustry.com", "display.ofweek.com", "ee.ofweek.com", "laoyaoba.com"],
    "robotics_embodied_cn": ["jiqizhixin.com", "qbitai.com", "zhidx.com", "leiphone.com", "ofweek.com", "elecfans.com", "gongkong.com", "ithome.com", "36kr.com"],
    "finance_business_cn": ["cls.cn", "yicai.com", "stcn.com", "21jingji.com", "jiemian.com", "thepaper.cn"],
    "global_media": ["theverge.com", "engadget.com", "cnet.com", "techcrunch.com", "bloomberg.com", "cnbc.com", "uploadvr.com", "roadtovr.com", "electrek.co", "insideevs.com"],
}


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
    media_domains = []
    for domains in CONSUMER_DAILY_MEDIA_DOMAINS.values():
        media_domains.extend(domains)
    return "\n".join(_dedupe(CONSUMER_ELECTRONICS_SOURCE_DOMAINS + media_domains + china_domains + global_domains))


def get_consumer_electronics_topics():
    topics = []
    for item in CONSUMER_ELECTRONICS_TOPICS:
        topic = deepcopy(item)
        pools = CONSUMER_DAILY_BREADTH_POOLS.get(topic.get("id"), {})
        for key, values in pools.items():
            topic[key] = _dedupe(list(topic.get(key, []) or []) + list(values or []))
        topic["media_domains"] = _dedupe(
            list(topic.get("china_domains", []) or [])
            + list(topic.get("domains", []) or [])
            + [domain for domains in CONSUMER_DAILY_MEDIA_DOMAINS.values() for domain in domains]
        )
        topics.append(topic)
    return topics


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
