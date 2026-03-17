# -*- coding: utf-8 -*-
from __future__ import annotations

"""
集中存放可调整的业务配置，方便后期在不改核心逻辑的情况下快速调参。
"""

DEFAULT_SITES_TEXT = """techcrunch.com
theverge.com
engadget.com
cnet.com
bloomberg.com/technology
electrek.co
insideevs.com
roadtovr.com
uploadvr.com
36kr.com
ithome.com
huxiu.com
geekpark.net
vrtuoluo.cn
d1ev.com"""

TIME_LIMIT_DICT = {
    "过去 24 小时": "d",
    "过去 1 周": "w",
    "过去 1 个月": "m",
}

INDUSTRY_TOPICS = [
    {
        "title": "AI手机与硬件承载",
        "queries": [
            "AI手机 硬件演进 2026",
            "智能手机 内部空间 SLP 类载板",
            "消费电子 FPC 技术 突破",
        ],
        "desc": "关注AI手机内部空间压缩、SLP与FPC的技术演进。",
    },
    {
        "title": "折叠与多维形态变革",
        "queries": [
            "三折叠手机 最新发布",
            "卷轴屏 手机 量产",
            "无孔化手机 Waterproof Buttonless 设计",
        ],
        "desc": "关注三折叠、卷轴屏以及无孔化设计的最新突破。",
    },
    {
        "title": "6G预研与卫星通讯",
        "queries": [
            "6G预研 最新进展",
            "高速 6G AI 整合 芯片",
            "卫星通信 手机 直连 NTN",
        ],
        "desc": "重点关注高速6G AI芯片及卫星直连技术（NTN）的进展。",
    },
    {
        "title": "AI穿戴与XR设备",
        "queries": [
            "超轻量化 AI眼镜 评测",
            "智能戒指 SmartRing 生态",
            "XR混合现实 硬件 创新",
        ],
        "desc": "关注超轻量化AI眼镜、智能戒指等新形态产品。",
    },
    {
        "title": "绿色制程与可持续",
        "queries": [
            "消费电子 绿色制程 创新",
            "欧洲市场 电子产品 碳足迹 法规",
            "科技巨头 ESG 战略",
        ],
        "desc": "关注碳足迹硬性要求（ESG）及绿色制程策略。",
    },
    {
        "title": "全球机器人产业生态",
        "queries": [
            "全球 机器人 产业 报告 2026",
            "特斯拉 宇树科技 机器人 动态",
            "新兴人形机器人 创业公司 2026",
        ],
        "desc": "考察全球与中国厂商，覆盖大厂与新兴创业公司。",
    },
]
