"""PWG source-level policy rules."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from urllib.parse import urlsplit


A_STANDARD_DOMAINS = {
    "standards.ieee.org",
    "ieee.org",
    "openalliance.org",
    "oiforum.com",
    "iec.ch",
    "tiaonline.org",
    "ipc.org",
    "iso.org",
}

A_PATENT_DOMAINS = {
    "patents.google.com",
    "uspto.gov",
    "wipo.int",
    "worldwide.espacenet.com",
    "epo.org",
    "j-platpat.inpit.go.jp",
    "cnipa.gov.cn",
}

A_PAPER_DOMAINS = {
    "ieeexplore.ieee.org",
    "opg.optica.org",
    "optica.org",
    "spiedigitallibrary.org",
    "nature.com",
    "sciencedirect.com",
    "springer.com",
    "arxiv.org",
    "mdpi.com",
}

A_COMPANY_DOMAINS = {
    "hakusan-mfg.co.jp",
    "sumibe.co.jp",
    "sumitomoelectric.com",
    "yazaki-group.com",
    "molex.com",
    "amphenol.com",
    "te.com",
    "aptiv.com",
    "leoni.com",
    "broadcom.com",
    "marvell.com",
    "coherent.com",
    "lumentum.com",
    "avaryholding.com",
    "dsbj.com",
    "shennan.com",
    "wuscn.com",
    "jcetglobal.com",
}

B_DOMAINS = {
    "ofcconference.org",
    "ecocexhibition.com",
    "cioe.cn",
    "optica.org",
    "spie.org",
    "opencompute.org",
    "semi.org",
}

C_PROFESSIONAL_DOMAINS = {
    "lightwaveonline.com",
    "optics.org",
    "eetimes.com",
    "eenewseurope.com",
    "yolegroup.com",
    "trendforce.com",
    "semianalysis.com",
    "semiconductor-today.com",
    "laserfocusworld.com",
    "electronicdesign.com",
    "convergedigest.com",
    "reuters.com",
    "bloomberg.com",
    "cnbc.com",
    "techcrunch.com",
    "theverge.com",
    "arstechnica.com",
    "wired.com",
    "engadget.com",
    "9to5mac.com",
    "macrumors.com",
    "electrek.co",
    "ijiwei.com",
    "elecfans.com",
    "ofweek.com",
    "c114.com.cn",
}

D_LOW_TRUST_DOMAIN_TERMS = (
    "blogspot.",
    "wordpress.",
    "medium.com",
    "substack.com",
    "msn.com",
    "yahoo.com",
    "aol.com",
    "marketscreener.com",
    "stocktitan.net",
    "benzinga.com",
    "prnewswire.com",
    "globenewswire.com",
    "newsbreak.com",
)


@dataclass(frozen=True)
class PWGSourceAssessment:
    source_level: str
    source_type: str
    source_level_reason: str
    is_low_trust: bool = False
    needs_manual_review: bool = False

    def to_dict(self):
        return asdict(self)


def _domain(url):
    netloc = urlsplit(str(url or "")).netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    return netloc


def _domain_matches(domain, candidates):
    if not domain:
        return False
    return any(domain == candidate or domain.endswith("." + candidate) for candidate in candidates)


def _blob(record):
    return " ".join(
        str(getattr(record, key, "") or "")
        for key in ("title", "source_name", "snippet", "url")
    )


def _has_any(text, terms):
    lowered = str(text or "").lower()
    return any(str(term or "").lower() in lowered for term in terms)


def assess_pwg_source(record, category=""):
    domain = _domain(getattr(record, "url", ""))
    text = _blob(record)
    lowered = text.lower()
    snippet = str(getattr(record, "snippet", "") or "").strip()

    if not getattr(record, "title", "") or not getattr(record, "url", "") or len(snippet) < 20:
        return PWGSourceAssessment("D", "incomplete", "标题、URL 或摘要不完整，按 D 级低可信线索处理。", True, True)

    if any(term in domain for term in D_LOW_TRUST_DOMAIN_TERMS) or _has_any(
        text, ["转载", "聚合", "自媒体", "sponsored", "affiliate", "coupon", "deal roundup"]
    ):
        return PWGSourceAssessment("D", "low_trust", f"域名或文本存在低可信/聚合信号：{domain}。", True, True)

    if _domain_matches(domain, A_PATENT_DOMAINS):
        return PWGSourceAssessment("A", "patent", f"命中专利原文/专利库来源：{domain}。")

    if _domain_matches(domain, A_STANDARD_DOMAINS):
        return PWGSourceAssessment("A", "standard", f"命中标准组织或标准原文来源：{domain}。")

    if _domain_matches(domain, A_PAPER_DOMAINS):
        return PWGSourceAssessment("A", "paper", f"命中论文原文或出版平台来源：{domain}。")

    if _domain_matches(domain, A_COMPANY_DOMAINS):
        source_type = "datasheet" if _has_any(text, ["datasheet", "data sheet", "specification", ".pdf"]) else "official"
        return PWGSourceAssessment("A", source_type, f"命中公司官网或 Datasheet 来源：{domain}。")

    if _domain_matches(domain, B_DOMAINS) or _has_any(text, ["official presentation", "slides", "ppt", "webinar", "interview", "协会", "访谈", "官方会议"]):
        return PWGSourceAssessment("B", "official_material", f"命中官方会议、协会、展会资料或访谈规则：{domain}。")

    if _domain_matches(domain, C_PROFESSIONAL_DOMAINS) or _has_any(text, ["industry report", "market report", "analysis", "专业媒体", "研报"]):
        return PWGSourceAssessment("C", "professional_media", f"命中专业媒体或行业研报来源：{domain}。", False, False)

    if re.search(r"\.pdf($|\?)", lowered):
        return PWGSourceAssessment("B", "document", f"未知机构 PDF 文档，暂按 B 级资料处理并建议复核：{domain}。", False, True)

    return PWGSourceAssessment("C", "media", f"未命中 A/B 原始信源或 D 级低质规则，暂按 C 级普通专业来源处理：{domain}。", False, True)
