"""Rule-based PWG result classification."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field


PWG_CATEGORIES = (
    "automotive",
    "connector",
    "cpo_datacenter",
    "material_process",
    "standard",
    "patent",
    "paper",
    "exhibition",
    "company_update",
)

CATEGORY_PATTERNS = {
    "patent": [
        "patent", "patents", "patent application", "claim", "claims", "invention",
        "uspto", "wipo", "espacenet", "google patents", "专利", "权利要求", "公开",
    ],
    "paper": [
        "paper", "journal", "doi", "arxiv", "optica", "spie", "ieee xplore",
        "conference paper", "springer nature", "link.springer.com", "photoniX",
        "论文", "期刊", "学术", "研究论文",
    ],
    "standard": [
        "standard", "specification", "working group", "ieee 802.3cz", "open alliance",
        "oif", "iec", "tia", "ipc", "标准", "工作组", "规范",
    ],
    "exhibition": [
        "exhibition", "expo", "trade show", "booth", "showcase", "ofc", "ecoc",
        "cioe", "ces", "display week", "展会", "展台", "展示", "参展",
    ],
    "automotive": [
        "automotive", "vehicle", "car", "ecu", "zonal controller", "camera optical link",
        "automotive optical ethernet", "automotive optical harness", "open alliance tc7",
        "车载", "汽车", "域控", "摄像头", "线束", "座舱",
    ],
    "connector": [
        "connector", "pmt", "mpo", "mt ferrule", "fiber array", "optical header",
        "board edge", "fiber stub", "45-degree mirror", "microlens",
        "连接器", "插芯", "光纤阵列", "板边", "微透镜",
    ],
    "cpo_datacenter": [
        "cpo", "co-packaged optics", "obo", "npo", "optical engine",
        "external laser source", "els", "optical rdl", "optical interposer",
        "optical backplane", "pic coupling", "datacenter", "data center", "800g", "1.6t",
        "数据中心", "光引擎", "外置光源", "先进封装",
    ],
    "material_process": [
        "siloxane", "photocurable", "acrylate", "photolithography", "imprint",
        "mosquito method", "direct writing", "bending loss", "roughness loss",
        "reliability", "polymer material", "材料", "工艺", "光刻", "压印", "可靠性", "弯曲损耗",
    ],
    "company_update": [
        "launch", "launched", "release", "released", "announce", "announced", "product",
        "datasheet", "sample", "shipping", "commercial", "partner", "customer",
        "发布", "推出", "宣布", "样品", "产品", "合作", "客户", "出货",
    ],
}

CATEGORY_PRIORITY = (
    "patent",
    "paper",
    "standard",
    "exhibition",
    "automotive",
    "cpo_datacenter",
    "connector",
    "material_process",
    "company_update",
)

CATEGORY_SCENE = {
    "automotive": "车载光互连",
    "connector": "PMT/MPO/MT接口件",
    "cpo_datacenter": "CPO/数据中心光互连",
    "material_process": "材料与工艺",
    "standard": "标准跟踪",
    "patent": "专利布局",
    "paper": "论文验证",
    "exhibition": "展会资料",
    "company_update": "厂商动态",
}

MAIN_TRACK = {
    "automotive": "应用",
    "connector": "产品",
    "cpo_datacenter": "应用",
    "material_process": "技术",
    "standard": "标准",
    "patent": "专利",
    "paper": "论文",
    "exhibition": "展会",
    "company_update": "厂商动态",
}


@dataclass(frozen=True)
class PWGClassification:
    category: str
    confidence: float
    matched_terms: list[str] = field(default_factory=list)
    classification_reason: str = ""

    def to_dict(self):
        return asdict(self)


def _text_blob(record):
    return " ".join(
        str(getattr(record, key, "") or "")
        for key in ("query", "title", "source_name", "snippet", "url")
    )


def _term_matches(term, text, lowered):
    term_text = str(term or "").strip()
    if not term_text:
        return False
    if re.search(r"[\u3040-\u30ff\u3400-\u9fff]", term_text):
        return term_text in text
    return term_text.lower() in lowered


def classify_pwg_result(record):
    text = _text_blob(record)
    lowered = text.lower()
    category_hits = {}
    for category, patterns in CATEGORY_PATTERNS.items():
        hits = [term for term in patterns if _term_matches(term, text, lowered)]
        if hits:
            category_hits[category] = hits

    if not category_hits:
        return PWGClassification(
            category="company_update",
            confidence=0.2,
            matched_terms=[],
            classification_reason="未命中明确类别规则，暂按厂商动态低置信度归类。",
        )

    cpo_hits = category_hits.get("cpo_datacenter", [])
    if any(term in lowered for term in ("cpo", "co-packaged optics", "optical engine", "external laser source")):
        return PWGClassification(
            category="cpo_datacenter",
            confidence=round(min(0.95, 0.5 + len(cpo_hits) * 0.12), 3),
            matched_terms=(cpo_hits or ["CPO"])[:8],
            classification_reason=f"命中 CPO/数据中心强规则：{', '.join((cpo_hits or ['CPO'])[:6])}。",
        )

    best_category = ""
    best_score = -1
    for category in CATEGORY_PRIORITY:
        hits = category_hits.get(category, [])
        if not hits:
            continue
        priority_bonus = len(CATEGORY_PRIORITY) - CATEGORY_PRIORITY.index(category)
        score = len(hits) * 10 + priority_bonus
        if score > best_score:
            best_category = category
            best_score = score

    matched = category_hits[best_category]
    confidence = min(0.95, 0.35 + len(matched) * 0.15)
    if best_category in {"patent", "paper", "standard"}:
        confidence = min(0.98, confidence + 0.1)
    return PWGClassification(
        category=best_category,
        confidence=round(confidence, 3),
        matched_terms=matched[:8],
        classification_reason=f"命中 {best_category} 规则词：{', '.join(matched[:6])}。",
    )


def category_to_scene(category):
    return CATEGORY_SCENE.get(category, "厂商动态")


def category_to_track(category):
    return MAIN_TRACK.get(category, "厂商动态")
