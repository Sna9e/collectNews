"""PWG maturity and opportunity scoring rules."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field


MATURITY_ORDER = ("M0", "M1", "M2", "M3", "M4", "M5", "M6", "M7")
MATURITY_INDEX = {level: index for index, level in enumerate(MATURITY_ORDER)}


@dataclass(frozen=True)
class PWGMaturityAssessment:
    maturity_level: str
    maturity_reason: str

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class PWGOpportunityScore:
    opportunity_score: int
    components: dict[str, int] = field(default_factory=dict)
    scoring_reason: str = ""
    needs_manual_review: bool = False

    def to_dict(self):
        return asdict(self)


def _blob(record):
    return " ".join(
        str(getattr(record, key, "") or "")
        for key in ("query", "title", "source_name", "snippet", "url")
    )


def _has_any(text, terms):
    lowered = str(text or "").lower()
    return any(str(term or "").lower() in lowered for term in terms)


def _cap_maturity(level, cap):
    if MATURITY_INDEX[level] <= MATURITY_INDEX[cap]:
        return level
    return cap


def assess_pwg_maturity(record, category, source_assessment):
    text = _blob(record)
    source_type = str(getattr(source_assessment, "source_type", "") or "")
    level = "M0"
    reasons = []

    if _has_any(text, ["concept", "conceptual", "roadmap", "idea", "概念", "路线图"]):
        level = "M0"
        reasons.append("命中概念或路线图信号。")

    if category == "paper" or source_type == "paper":
        level = "M1"
        reasons.append("论文或学术验证来源最高按 M1 处理。")
    elif category == "patent" or source_type == "patent":
        level = "M2"
        reasons.append("专利布局来源最高按 M2 处理。")
    elif _has_any(text, ["prototype", "demonstrator", "lab sample", "proof of concept", "实验室样件", "原型", "验证样件"]):
        level = "M3"
        reasons.append("命中实验室样件或原型验证信号。")
    elif _has_any(text, ["datasheet", "data sheet", "sample", "engineering sample", "product brief", "样品", "规格书"]):
        level = "M4"
        reasons.append("命中公司样品、Datasheet 或产品规格信号。")
    elif _has_any(text, ["joint development", "customer validation", "design win", "pilot", "客户验证", "联合开发", "试点"]):
        level = "M5"
        reasons.append("命中联合开发、客户验证或设计导入信号。")
    elif _has_any(text, ["stable mass production", "volume production", "stable production", "稳定量产", "规模化生产"]):
        level = "M7"
        reasons.append("命中稳定量产或规模化生产信号。")
    elif _has_any(text, ["commercially available", "available now", "shipping", "order", "sales", "commercial launch", "mass production", "量产", "销售", "可订购", "出货", "商业销售"]):
        level = "M6"
        reasons.append("命中商业销售、可订购、出货或量产信号。")

    if category == "paper" or source_type == "paper":
        capped = _cap_maturity(level, "M1")
        if capped != level:
            reasons.append("论文来源不得直接判断为量产，已限制到 M1。")
        level = capped
    if category == "patent" or source_type == "patent":
        capped = _cap_maturity(level, "M2")
        if capped != level:
            reasons.append("专利来源不得直接判断为量产，已限制到 M2。")
        level = capped
    if _has_any(text, ["concept", "conceptual", "概念图", "示意图"]):
        capped = _cap_maturity(level, "M0")
        if capped != level:
            reasons.append("概念图或概念材料不得直接判断为量产，已限制到 M0。")
        level = capped

    if not reasons:
        reasons.append("未命中明确成熟度信号，按 M0 概念线索处理。")

    return PWGMaturityAssessment(level, "；".join(reasons))


def _component_score(text, positive_terms, max_score, base=0):
    hits = sum(1 for term in positive_terms if str(term).lower() in text.lower())
    if hits <= 0:
        return base
    return min(max_score, base + hits * max(3, max_score // 4))


def score_pwg_opportunity(record, classification, source_assessment, maturity_assessment):
    text = _blob(record)
    category = classification.category
    maturity = maturity_assessment.maturity_level
    source_level = source_assessment.source_level

    pain = _component_score(
        text,
        [
            "automotive", "camera", "zonal", "cpo", "datacenter", "data center", "bandwidth",
            "weight", "loss", "reliability", "thermal", "高速", "减重", "可靠性", "损耗", "车载",
        ],
        30,
    )
    if category in {"automotive", "cpo_datacenter"}:
        pain = max(pain, 18)

    fpc_match = _component_score(
        text,
        [
            "fpc", "flexible", "board edge", "optical wiring board", "optical circuit board",
            "connector", "fiber array", "routing", "interposer", "rdl", "柔性", "板边", "光电混合",
        ],
        25,
    )
    if category in {"connector", "material_process"}:
        fpc_match = max(fpc_match, 12)

    evidence_base = {"A": 12, "B": 9, "C": 5, "D": 1}.get(source_level, 3)
    product_evidence = min(
        20,
        evidence_base
        + _component_score(text, ["datasheet", "sample", "product", "commercial", "shipping", "样品", "产品", "出货"], 8),
    )
    if category in {"paper", "patent"}:
        product_evidence = min(product_evidence, 8)

    maturity_bonus = {"M0": 2, "M1": 5, "M2": 6, "M3": 9, "M4": 11, "M5": 13, "M6": 15, "M7": 13}.get(maturity, 2)
    feasibility = min(
        15,
        maturity_bonus
        + (2 if _has_any(text, ["reliability", "loss", "photolithography", "imprint", "可靠性", "损耗", "光刻", "压印"]) else 0),
    )

    entry = 3
    if _has_any(text, ["open standard", "supplier", "multiple", "fpc", "pcb", "connector", "标准", "供应商", "柔性", "连接器"]):
        entry += 4
    if maturity in {"M2", "M3", "M4", "M5"}:
        entry += 3
    elif maturity == "M7":
        entry += 1
    entry = min(10, entry)

    components = {
        "customer_pain": int(min(30, pain)),
        "fpc_capability_match": int(min(25, fpc_match)),
        "public_product_evidence": int(min(20, product_evidence)),
        "technical_feasibility": int(min(15, feasibility)),
        "competitive_entry": int(min(10, entry)),
    }
    total = min(100, sum(components.values()))
    needs_manual_review = (
        source_level == "D"
        or classification.confidence < 0.45
        or total < 35
        or maturity in {"M0", "M1"} and source_level not in {"A", "B"}
    )
    reason = (
        f"客户痛点{components['customer_pain']}/30，"
        f"FPC能力匹配{components['fpc_capability_match']}/25，"
        f"公开产品证据{components['public_product_evidence']}/20，"
        f"技术可实现性{components['technical_feasibility']}/15，"
        f"竞争可进入性{components['competitive_entry']}/10；"
        f"分类={category}，来源等级={source_level}，成熟度={maturity}。"
    )
    return PWGOpportunityScore(total, components, reason, needs_manual_review)
