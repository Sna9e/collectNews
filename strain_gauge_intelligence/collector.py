"""Collector for the strain gauge and robotic six-axis force sensor module."""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import html
import json
import os
import re
import tomllib
import urllib.parse
import urllib.request
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import xlsxwriter

from . import TECH_MODULES, TECH_MODULE_EN
from .models import StrainGaugeIntelligenceItem, StrainGaugeModulePayload
from .reporter import DEFAULT_REPORT_DIR, write_strain_gauge_report
from tools.search_engine import extract_result_datetime, search_web
from tools.strain_gauge_query_packs import build_strain_gauge_query_pack, load_strain_gauge_query_config


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RAW_DIR = PROJECT_ROOT / "data" / "strain_gauge_intelligence" / "raw"
LOCAL_TZ = _dt.timezone(_dt.timedelta(hours=8))

MIN_COUNTS = {"news": 2, "patent": 3, "paper": 3}
BANNED_SUMMARY_PHRASES = (
    "公开材料显示",
    "公开资料显示",
    "该线索由某网站披露",
    "材料没有提供足够细节",
    "资料未提供足够细节",
    "暂不能确认更多参数",
    "时间线仅记录已披露动作",
    "仅记录已披露动作",
    "需要进一步核实结构细节",
)
TRACKING_QUERY_PARAMS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "fbclid", "gclid", "ref"}
LOW_QUALITY_DOMAIN_TERMS = (
    "blogspot",
    "medium.com",
    "substack",
    "seo",
    "pressrelease",
    "newswire",
    "openpr",
    "einpresswire",
    "einnews",
    "shuma.taobao.com",
    "dy/article",
    "baijiahao",
    "cndcs.com",
    "xcarspace.com",
    "news.lavx.hu",
    "oracore.dev",
    "boardor.com",
)


def _ensure_utc(value=None):
    if value is None:
        return _dt.datetime.now(_dt.timezone.utc)
    if isinstance(value, _dt.datetime):
        return value.replace(tzinfo=_dt.timezone.utc) if value.tzinfo is None else value.astimezone(_dt.timezone.utc)
    raise TypeError("now must be a datetime or None")


def _clean_text(value):
    text = html.unescape(str(value or ""))
    text = re.sub(r"<script.*?>.*?</script>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<style.*?>.*?</style>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_strain_gauge_url(url):
    raw = str(url or "").strip()
    if not raw:
        return ""
    if "://" not in raw and re.match(r"^[A-Za-z0-9.-]+\.[A-Za-z]{2,}(/|$)", raw):
        raw = "https://" + raw
    parts = urlsplit(raw)
    scheme = (parts.scheme or "https").lower()
    netloc = parts.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    path = re.sub(r"/{2,}", "/", parts.path or "")
    if path != "/":
        path = path.rstrip("/")
    query_pairs = []
    for key, value in parse_qsl(parts.query, keep_blank_values=False):
        key_lower = key.lower()
        if key_lower.startswith("utm_") or key_lower in TRACKING_QUERY_PARAMS:
            continue
        query_pairs.append((key, value))
    return urlunsplit((scheme, netloc, path, urlencode(query_pairs, doseq=True), ""))


def _domain(url):
    return urlsplit(str(url or "")).netloc.lower().removeprefix("www.")


def _date_from_result(result, item_type):
    parsed, _ = extract_result_datetime(result or {})
    if parsed:
        return parsed.astimezone(_dt.timezone.utc).date().isoformat()
    blob = f"{(result or {}).get('title', '')} {(result or {}).get('content', '')} {(result or {}).get('snippet', '')}"
    date_match = re.search(r"\b(20\d{2})[-/.](0?[1-9]|1[0-2])[-/.](0?[1-9]|[12]\d|3[01])\b", blob)
    if date_match:
        year, month, day = date_match.groups()
        return f"{year}-{int(month):02d}-{int(day):02d}"
    year_match = re.search(r"\b(20\d{2})\b", blob)
    if year_match and item_type in {"patent", "paper"}:
        return year_match.group(1)
    return ""


def _date_within_window(date_text, now, window_days, item_type):
    raw = str(date_text or "").strip()
    if not raw:
        return False
    target_date = now.astimezone(_dt.timezone.utc).date()
    try:
        if re.fullmatch(r"20\d{2}", raw):
            year = int(raw)
            min_year = target_date.year - max(1, int(window_days / 365)) - 1
            return min_year <= year <= target_date.year
        parsed = _dt.date.fromisoformat(raw[:10])
    except ValueError:
        return False
    delta_days = (target_date - parsed).days
    return -7 <= delta_days <= int(window_days or 30)


def _timelimit_for_days(days):
    return "m" if int(days or 30) >= 30 else "w"


def _relevance_level(title, snippet, url, config):
    text = f"{title} {snippet} {url}"
    lowered = text.lower()
    terms = ((config.get("keywords") or {}).get("relevance_terms") or {})
    high_hits = [term for term in terms.get("high", []) if str(term).lower() in lowered or str(term) in text]
    medium_hits = [term for term in terms.get("medium", []) if str(term).lower() in lowered or str(term) in text]
    low_hits = [term for term in terms.get("low", []) if str(term).lower() in lowered or str(term) in text]
    if high_hits:
        return "high", f"命中高相关词：{'、'.join(high_hits[:5])}"
    if medium_hits:
        return "medium", f"命中中相关词：{'、'.join(medium_hits[:5])}"
    if low_hits:
        return "low", f"仅命中低相关或泛传感词：{'、'.join(low_hits[:5])}"
    return "low", "未命中六轴力、应变片、电桥、弹性体、机器人力控或触觉核心词。"


def _source_quality(url, item_type, config):
    host = _domain(url)
    target = f"{host} {str(url or '').lower()}"
    companies = config.get("companies", {}) or {}
    if item_type == "patent" and any(host.endswith(domain) for domain in companies.get("patent_domains", []) or []):
        return "patent"
    if item_type == "paper" and any(host.endswith(domain) for domain in companies.get("paper_domains", []) or []):
        return "paper"
    if item_type == "news" and any(host.endswith(domain) for domain in companies.get("preferred_news_domains", []) or []):
        return "official/professional"
    if any(term in target for term in LOW_QUALITY_DOMAIN_TERMS):
        return "low_quality"
    return "review"


def _source_scope_for_type(item_type, config):
    companies = config.get("companies", {}) or {}
    if item_type == "patent":
        return "\n".join(companies.get("patent_domains", []) or [])
    if item_type == "paper":
        return "\n".join(companies.get("paper_domains", []) or [])
    return ""


def _passes_required_evidence(item_type, title, snippet):
    blob = f"{title} {snippet}".lower()
    core_terms = (
        "six-axis",
        "six dimensional",
        "six-dimensional",
        "force/torque",
        "multi-axis force",
        "strain gauge",
        "flexible strain sensor",
        "tactile sensor",
        "force sensor",
        "wheatstone",
        "calibration matrix",
        "decoupling",
        "六轴力",
        "六维力",
        "六分力",
        "应变片",
        "惠斯通",
        "标定矩阵",
        "解耦",
        "弹性体",
    )
    application_terms = (
        "robot",
        "robotic",
        "humanoid",
        "dexterous",
        "wrist",
        "end-effector",
        "tactile",
        "force feedback",
        "机器人",
        "人形",
        "灵巧手",
        "腕部",
        "关节",
        "末端",
        "触觉",
        "力控",
    )
    has_core = any(term in blob for term in core_terms)
    has_application = any(term in blob for term in application_terms)
    if item_type == "paper":
        return has_core and has_application
    if item_type == "news":
        return has_core or ("force sensor" in blob and has_application)
    if item_type == "patent":
        return has_core or ("force sensor" in blob and "patent" in blob)
    return False


def _publication_number(text, url):
    blob = f"{text} {url}"
    patterns = [
        r"/patent/([A-Z]{2}\d{5,}[A-Z]?\d?)(?:/|$)",
        r"\b(CN\d{7,}[A-Z]?)\b",
        r"\b(US\d{4}/\d{6,}[A-Z]?\d?)\b",
        r"\b(US\d{7,}[A-Z]?\d?)\b",
        r"\b(EP\d{7,}[A-Z]?\d?)\b",
        r"\b(WO\d{4}/\d{5,}[A-Z]?\d?)\b",
        r"\b(WO\d{7,}[A-Z]?\d?)\b",
        r"\b(JP\d{4}[-/]?\d{5,}[A-Z]?)\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, blob, flags=re.IGNORECASE)
        if match:
            return match.group(1).upper()
    return ""


def _country_from_publication(number):
    prefix = str(number or "")[:2].upper()
    return {"CN": "中国", "US": "美国", "EP": "欧洲", "WO": "WIPO", "JP": "日本"}.get(prefix, prefix)


def _applicant_from_text(text, config):
    applicants = (config.get("companies") or {}).get("patent_applicants", []) or []
    lowered = str(text or "").lower()
    for applicant in applicants:
        if str(applicant).lower() in lowered:
            return str(applicant)
    return ""


def _fetch_google_patents_results(query, max_results=10):
    encoded_url = urllib.parse.quote("q=" + str(query or ""))
    endpoint = f"https://patents.google.com/xhr/query?url={encoded_url}&exp=&tags="
    request = urllib.request.Request(endpoint, headers={"User-Agent": "Mozilla/5.0"})
    try:
        payload = json.loads(urllib.request.urlopen(request, timeout=20).read().decode("utf-8", errors="ignore"))
    except Exception:
        return []
    rows = []
    for cluster in ((payload.get("results") or {}).get("cluster") or []):
        for result in cluster.get("result", []) or []:
            patent = result.get("patent", {}) or {}
            publication_number = _clean_text(patent.get("publication_number"))
            if not publication_number:
                continue
            title = _clean_text(patent.get("title"))
            snippet = _clean_text(patent.get("snippet"))
            url = "https://patents.google.com/" + str(result.get("id") or f"patent/{publication_number}/en").lstrip("/")
            rows.append(
                {
                    "title": f"{publication_number} {title}".strip(),
                    "url": url,
                    "source_name": "Google Patents",
                    "published_date": _clean_text(patent.get("publication_date") or patent.get("filing_date") or patent.get("priority_date")),
                    "content": snippet,
                    "publication_number": publication_number,
                    "assignee": _clean_text(patent.get("assignee")),
                }
            )
            if len(rows) >= int(max_results or 10):
                return rows
    return rows


def _doi_from_text(text):
    match = re.search(r"\b10\.\d{4,9}/[-._;()/:A-Za-z0-9]+\b", str(text or ""))
    return match.group(0).rstrip(".,;") if match else ""


def _split_sentences(text, limit=3):
    parts = [part.strip(" ;,，。") for part in re.split(r"(?<=[。！？.!?])\s+|[。！？]", _clean_text(text)) if part.strip()]
    return parts[:limit]


def _has_chinese(text):
    return bool(re.search(r"[\u4e00-\u9fff]", str(text or "")))


def _remove_banned_summary_phrases(text):
    clean = str(text or "")
    for phrase in BANNED_SUMMARY_PHRASES:
        clean = clean.replace(phrase, "")
    return re.sub(r"\s+", " ", clean).strip(" ，。；;")


def _technical_focus(title, snippet, item_type):
    blob = f"{title} {snippet}".lower()
    if "wheatstone" in blob or "bridge" in blob or "惠斯通" in blob or "全桥" in blob or "半桥" in blob:
        return "应变电桥、桥路布线和温度补偿"
    if "six-axis" in blob or "force/torque" in blob or "六轴" in blob or "六维" in blob or "六分力" in blob:
        return "机器人六轴/六维力传感器"
    if "cross beam" in blob or "spoke" in blob or "stewart" in blob or "十字梁" in blob or "轮辐" in blob:
        return "弹性体结构、应变片贴装和多轴解耦"
    if "flexible" in blob or "fpc" in blob or "柔性" in blob or "tactile" in blob or "触觉" in blob:
        return "柔性应变传感和机器人触觉反馈"
    if item_type == "patent":
        return "机器人力传感器结构和应变测量方案"
    if item_type == "paper":
        return "机器人力/触觉传感、标定和解耦方法"
    return "机器人力控传感器产品和应用进展"


def _subject_from_title(title):
    clean = _clean_text(title)
    quoted = re.search(r"[「“\"]([^」”\"]{2,40})[」”\"]", clean)
    if quoted:
        return quoted.group(1)
    chinese_match = re.match(r"([\u4e00-\u9fffA-Za-z0-9 /&.-]{2,40}?)(发布|推出|完成|获得|宣布|展示|领投|融资|更新)", clean)
    if chinese_match:
        return chinese_match.group(1).strip(" ，-_|")
    english_match = re.match(
        r"([A-Z][A-Za-z0-9 &'./+-]{2,60}?)(?:\s+(?:raises|announces|introduced|introduces|updates|achieves|completes|showcases|launches|publishes|reports|secures|releases|brings)\b|[:|,-])",
        clean,
        flags=re.IGNORECASE,
    )
    if english_match:
        return english_match.group(1).strip(" -_|")
    return clean.split("|")[0].split(" - ")[0].strip()[:40] or "相关企业或研究团队"


def _action_from_text(title, snippet, item_type):
    title_lower = str(title or "").lower()
    blob = f"{title} {snippet}".lower()
    if item_type == "patent":
        return "围绕专利方案披露了结构设计、电桥布线或标定补偿思路"
    if item_type == "paper":
        return "围绕传感结构、解耦算法或实验验证形成研究进展"
    if any(term in title_lower for term in ("融资", "financing", "funding", "raises", "round", "secures")):
        return "完成融资或资本推进"
    if any(term in title_lower for term in ("发布", "推出", "introduced", "introduces", "launches", "updates", "showcases", "releases", "brings")):
        return "发布、更新或展示产品与样品"
    if any(term in blob for term in ("发布", "推出", "introduced", "introduces", "launches", "updates", "showcases", "releases", "brings")):
        return "发布、更新或展示产品与样品"
    if any(term in blob for term in ("融资", "financing", "funding", "raises", "round", "secures")):
        return "完成融资或资本推进"
    if any(term in blob for term in ("certification", "认证", "qualified")):
        return "取得生产、质量或应用资质进展"
    return "披露了新的产品、应用或产业进展"


def _extract_key_numbers(text, limit=4):
    patterns = [
        r"\b20\d{2}[-/.]\d{1,2}[-/.]\d{1,2}\b",
        r"\b20\d{2}\b",
        r"\b\d+(?:\.\d+)?\s?(?:%|FS|N|Nm|mm|μm|um|kHz|Hz|million|billion|RMB|USD)\b",
        r"[<>≤≥]?\d+(?:\.\d+)?%\s?FS",
        r"\d+(?:\.\d+)?\s?(?:万台|亿元|亿|万元|个月|年)",
    ]
    found = []
    for pattern in patterns:
        for match in re.findall(pattern, str(text or ""), flags=re.IGNORECASE):
            value = match if isinstance(match, str) else "".join(match)
            if value and value not in found:
                found.append(value)
            if len(found) >= limit:
                return found
    return found


def _extract_technical_terms(text, limit=6):
    candidates = [
        ("six-axis force/torque sensor", "six-axis force/torque sensor"),
        ("six-dimensional force sensor", "six-dimensional force sensor"),
        ("multi-axis force sensor", "multi-axis force sensor"),
        ("strain gauge", "strain gauge"),
        ("wheatstone bridge", "Wheatstone bridge"),
        ("full bridge", "full bridge"),
        ("temperature compensation", "temperature compensation"),
        ("decoupling matrix", "decoupling matrix"),
        ("calibration matrix", "calibration matrix"),
        ("cross beam", "cross beam"),
        ("spoke-type", "spoke-type"),
        ("robot wrist", "robot wrist"),
        ("dexterous hand", "dexterous hand"),
        ("tactile sensor", "tactile sensor"),
        ("fpc", "FPC"),
        ("六维力传感器", "六维力传感器"),
        ("六轴力传感器", "六轴力传感器"),
        ("应变片", "应变片"),
        ("惠斯通电桥", "惠斯通电桥"),
        ("温度补偿", "温度补偿"),
        ("解耦", "解耦"),
        ("标定", "标定"),
    ]
    lowered = str(text or "").lower()
    found = []
    for needle, label in candidates:
        if needle.lower() in lowered and label not in found:
            found.append(label)
        if len(found) >= limit:
            break
    return found


def _chinese_fact_sentences(title, snippet, limit=3):
    clean_title = _clean_text(title)
    sentences = []
    for sentence in _split_sentences(snippet, limit=10):
        fact = _remove_banned_summary_phrases(sentence)
        if not fact or not _has_chinese(fact):
            continue
        if fact in clean_title or clean_title in fact:
            continue
        if len(fact) < 12:
            continue
        sentences.append(fact.rstrip("。") + "。")
        if len(sentences) >= limit:
            break
    return sentences


def _summary_from_text(title, snippet, relation, fpc_implication, item_type):
    facts = _chinese_fact_sentences(title, snippet, limit=3)
    lines = []
    if facts:
        lines.extend(facts)
    else:
        subject = _subject_from_title(title)
        action = _action_from_text(title, snippet, item_type)
        focus = _technical_focus(title, snippet, item_type)
        terms = _extract_technical_terms(f"{title} {snippet}")
        numbers = _extract_key_numbers(f"{title} {snippet}")
        if item_type == "news":
            lines.append(f"{subject}围绕{focus}{action}。")
            lines.append("这条信息的核心价值在于判断机器人腕部、关节、末端执行器或灵巧手力反馈方案的产品化节奏。")
        elif item_type == "patent":
            lines.append(f"{subject}披露的专利信息聚焦{focus}。")
            lines.append("该方案需要重点拆解弹性体受力路径、应变片布置、电桥读出和温度补偿之间的对应关系。")
        else:
            lines.append(f"{subject}相关研究聚焦{focus}。")
            lines.append("该工作适合从传感结构、标定矩阵、解耦误差、重复性和机器人实验验证几个维度评估工程价值。")
        if terms:
            lines.append(f"原文关键词包括{'、'.join(terms)}，可用于后续归档到应变测量、机器人力控或触觉反馈路线。")
        if numbers:
            lines.append(f"可提取的关键数字包括{'、'.join(numbers[:4])}，后续可用于比对时间、性能、出货或应用规模。")
    lines.append(_remove_banned_summary_phrases(relation).rstrip("。") + "。")
    if fpc_implication:
        lines.append(_remove_banned_summary_phrases(fpc_implication).rstrip("。") + "。")
    return "".join(line for line in lines[:5] if line)


def _relation_and_fpc(item_type, title, snippet):
    blob = f"{title} {snippet}".lower()
    if any(term in blob for term in ("six-axis", "six dimensional", "six-dimensional", "force/torque", "六轴", "六维", "六分力")):
        relation = "该线索直接关联机器人六维/六轴力或力矩传感器，可用于判断腕部、脚踝、关节或末端执行器力反馈的产品化进展。"
        fpc = "对FPC研发的参考点是多通道应变信号引出、桥路屏蔽、温度补偿网络和传感器小型化封装。"
    elif any(term in blob for term in ("wheatstone", "bridge", "惠斯通", "全桥", "半桥")):
        relation = "该线索直接关联应变电桥测量、桥路布线和温度补偿，是六轴力传感器信号读出的关键环节。"
        fpc = "对FPC研发的启示在于桥路走线、屏蔽接地、温度补偿电阻和柔性引出端可一体化设计。"
    elif any(term in blob for term in ("cross beam", "spoke", "stewart", "elastic", "十字梁", "轮辐", "弹性体")):
        relation = "该线索涉及六维力传感器弹性体结构，应变片贴装位置和解耦矩阵会直接决定测量精度。"
        fpc = "可借鉴弹性体贴片区、引线出口和过载保护结构，评估FPC载体与补强件的集成方式。"
    elif any(term in blob for term in ("flexible", "fpc", "柔性", "tactile", "触觉")):
        relation = "该线索与柔性应变或机器人触觉有关，适合评估灵巧手、曲面触觉和末端执行器力反馈。"
        fpc = "可重点关注柔性基底、导体图形、封装保护和重复弯折后的电阻漂移。"
    else:
        relation = "该线索落在机器人力控传感器或多轴力反馈链路上，可用于跟踪六维力/力矩传感器的产品化和应用节奏。"
        fpc = "对FPC研发的参考点是传感器引出、屏蔽接地、桥路线束和标定接口是否具备柔性化集成空间。"
    return relation, fpc


def _paper_fields(title, snippet, source, url):
    doi = _doi_from_text(f"{title} {snippet} {url}")
    authors = source or "待人工核对作者/机构"
    venue = source or "待人工核对期刊/会议"
    blob = f"{title} {snippet}"
    structure = "应变片/多轴力传感结构" if re.search(r"strain|force|应变|力传感", blob, re.IGNORECASE) else "柔性传感结构"
    methods = "关注标定矩阵、解耦算法、灵敏度、重复性、温度漂移或机器人实验验证。"
    return doi, authors, venue, structure, methods


def _record_from_result(raw, query, item_type, window_days, now, config):
    item = dict(raw or {})
    title = _clean_text(item.get("title") or "")
    url = normalize_strain_gauge_url(item.get("url") or "")
    snippet = _clean_text(item.get("content") or item.get("snippet") or item.get("summary") or "")
    source = _clean_text(item.get("source") or item.get("source_name") or _domain(url))
    if not title or not url:
        return None
    date_text = _date_from_result(item, item_type)
    if not _date_within_window(date_text, now, window_days, item_type):
        return None
    relevance, relevance_reason = _relevance_level(title, snippet, url, config)
    if relevance == "low":
        return None
    if not _passes_required_evidence(item_type, title, snippet):
        return None
    quality = _source_quality(url, item_type, config)
    if item_type == "news" and quality == "low_quality":
        return None
    if item_type == "patent" and quality != "patent":
        return None
    if item_type == "paper" and quality == "low_quality":
        return None
    relation, fpc = _relation_and_fpc(item_type, title, snippet)
    summary = _summary_from_text(title, snippet, relation, fpc, item_type)
    item_id = hashlib.sha1(f"{item_type}|{url or title}".encode("utf-8")).hexdigest()[:16]

    kwargs = {
        "item_id": item_id,
        "item_type": item_type,
        "title": title,
        "date": date_text,
        "source_name": source,
        "source_url": url,
        "summary": summary,
        "relation_to_sensor": relation,
        "fpc_implication": fpc,
        "relevance_level": relevance,
        "relevance_reason": relevance_reason,
        "source_quality": quality,
        "raw_query": query,
        "raw_snippet": snippet[:1200],
    }
    if item_type == "patent":
        number = _clean_text(item.get("publication_number")) or _publication_number(f"{title} {snippet}", url)
        applicant = _clean_text(item.get("assignee")) or _applicant_from_text(f"{title} {snippet}", config) or source
        if not number:
            return None
        kwargs.update(
            {
                "publication_number": number,
                "applicant": applicant,
                "country_or_region": _country_from_publication(number),
                "core_solution": relation,
                "reference_point": fpc,
            }
        )
    elif item_type == "paper":
        doi, authors, venue, structure, methods = _paper_fields(title, snippet, source, url)
        kwargs.update(
            {
                "authors_or_institutions": authors,
                "venue": venue,
                "doi_or_link": doi or url,
                "research_object": "机器人力/触觉传感或六轴力传感相关研究",
                "sensing_structure": structure,
                "key_methods_metrics": methods,
                "engineering_value": fpc,
            }
        )
    return StrainGaugeIntelligenceItem(**kwargs)


def _dedupe_items(items):
    output = []
    seen = set()
    for item in items:
        key = normalize_strain_gauge_url(item.source_url).lower() or re.sub(r"[\W_]+", "", item.title.lower())
        if item.item_type == "patent" and item.publication_number:
            key = item.publication_number.lower()
        if key in seen:
            continue
        seen.add(key)
        output.append(item)
    return output


def _sort_items(items):
    relevance_rank = {"high": 0, "medium": 1, "low": 2}
    return sorted(items, key=lambda item: (relevance_rank.get(item.relevance_level, 9), str(item.date)), reverse=False)


def _collect_type(item_type, config, provider, tavily_key, exa_key, max_queries_per_type, results_per_query, now, search_fn):
    windows = ((config.get("keywords") or {}).get("search_windows_days") or {}).get(item_type, [30])
    min_count = MIN_COUNTS[item_type]
    all_items = []
    raw_results = []
    searched = []
    for window_days in windows:
        searched.append(int(window_days))
        queries = build_strain_gauge_query_pack(
            item_type=item_type,
            window_days=int(window_days),
            max_queries_per_type=max_queries_per_type,
            config_dir=config.get("config_dir"),
        )
        exa_settings = {
            "search_type": "auto",
            "category": "research paper" if item_type == "paper" else ("news" if item_type == "news" else ""),
            "content_mode": "highlights_text",
            "highlights_max_characters": 1200,
            "text_max_characters": 2000,
        }
        for query_record in queries:
            batch = search_fn(
                query_record.query,
                _source_scope_for_type(item_type, config),
                _timelimit_for_days(window_days),
                max_results=int(results_per_query or 8),
                tavily_key=tavily_key,
                provider=provider,
                exa_key=exa_key,
                exa_settings=exa_settings,
            )
            for result in batch or []:
                raw_results.append({"item_type": item_type, "query": query_record.query, "window_days": int(window_days), "item": dict(result or {})})
                record = _record_from_result(result, query_record.query, item_type, int(window_days), now, config)
                if record:
                    all_items.append(record)
        if item_type == "patent":
            all_items = _sort_items(_dedupe_items(all_items))
            if len(all_items) < min_count:
                for query_record in queries[: max(1, int(max_queries_per_type or 4))]:
                    patent_batch = _fetch_google_patents_results(query_record.query, max_results=8)
                    for result in patent_batch:
                        raw_results.append(
                            {
                                "item_type": item_type,
                                "query": query_record.query,
                                "window_days": int(window_days),
                                "source": "google_patents_xhr",
                                "item": dict(result or {}),
                            }
                        )
                        record = _record_from_result(result, query_record.query, item_type, int(window_days), now, config)
                        if record:
                            all_items.append(record)
                    all_items = _sort_items(_dedupe_items(all_items))
                    if len(all_items) >= min_count:
                        break
        all_items = _sort_items(_dedupe_items(all_items))
        if len(all_items) >= min_count:
            break
    return all_items, raw_results, searched


def validate_module_counts(news, patents, papers, searched_windows=None):
    counts = {"news": len(news or []), "patent": len(patents or []), "paper": len(papers or [])}
    shortages = {
        key: {"required": required, "actual": counts[key]}
        for key, required in MIN_COUNTS.items()
        if counts[key] < required
    }
    return {
        "passed": not shortages,
        "counts": counts,
        "required": dict(MIN_COUNTS),
        "shortages": shortages,
        "searched_windows": searched_windows or {},
    }


def _output_paths(output_dir, report_date, overwrite=False):
    base = Path(output_dir or DEFAULT_RAW_DIR)
    base.mkdir(parents=True, exist_ok=True)
    stem = f"strain_gauge_module_{report_date}"
    json_path = base / f"{stem}.json"
    xlsx_path = base / f"{stem}.xlsx"
    if overwrite or (not json_path.exists() and not xlsx_path.exists()):
        return json_path, xlsx_path
    suffix = _dt.datetime.now(LOCAL_TZ).strftime("%H%M%S")
    return base / f"{stem}_{suffix}.json", base / f"{stem}_{suffix}.xlsx"


def _write_json(path, payload):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_xlsx(path, payload):
    workbook = xlsxwriter.Workbook(str(path))
    for sheet_name, rows in (
        ("news", payload.get("news", [])),
        ("patents", payload.get("patents", [])),
        ("papers", payload.get("papers", [])),
    ):
        worksheet = workbook.add_worksheet(sheet_name)
        headers = sorted({key for row in rows for key in row.keys()}) if rows else ["title", "source_url"]
        for col, header in enumerate(headers):
            worksheet.write(0, col, header)
        for row_idx, row in enumerate(rows, start=1):
            for col, header in enumerate(headers):
                worksheet.write(row_idx, col, str(row.get(header, "")))
    worksheet = workbook.add_worksheet("quantity_check")
    for row_idx, (key, value) in enumerate((payload.get("quantity_check") or {}).items()):
        worksheet.write(row_idx, 0, key)
        worksheet.write(row_idx, 1, json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value))
    workbook.close()
    return path


def collect_strain_gauge_module(
    provider="exa",
    tavily_key="",
    exa_key="",
    max_queries_per_type=8,
    results_per_query=6,
    output_dir=DEFAULT_RAW_DIR,
    report_dir=DEFAULT_REPORT_DIR,
    now=None,
    search_fn=search_web,
    overwrite=False,
):
    generated_at = _ensure_utc(now)
    config = load_strain_gauge_query_config()
    all_raw = []
    news, raw, news_windows = _collect_type("news", config, provider, tavily_key, exa_key, max_queries_per_type, results_per_query, generated_at, search_fn)
    all_raw.extend(raw)
    patents, raw, patent_windows = _collect_type("patent", config, provider, tavily_key, exa_key, max_queries_per_type, results_per_query, generated_at, search_fn)
    all_raw.extend(raw)
    papers, raw, paper_windows = _collect_type("paper", config, provider, tavily_key, exa_key, max_queries_per_type, results_per_query, generated_at, search_fn)
    all_raw.extend(raw)
    searched_windows = {"news": news_windows, "patent": patent_windows, "paper": paper_windows}
    quantity_check = validate_module_counts(news, patents, papers, searched_windows=searched_windows)
    warnings = []
    if not quantity_check["passed"]:
        warnings.append("部分类型未达到最低数量，已自动扩大检索窗口并保留不足原因。")

    payload_model = StrainGaugeModulePayload(
        module_name=TECH_MODULES[0],
        module_name_en=TECH_MODULE_EN,
        generated_at=generated_at.astimezone(LOCAL_TZ).isoformat(),
        news=news,
        patents=patents,
        papers=papers,
        quantity_check=quantity_check,
        searched_windows=searched_windows,
        warnings=warnings,
    )
    payload = payload_model.model_dump()
    payload["raw_result_count"] = len(all_raw)
    payload["raw_results"] = all_raw
    payload["search_provider"] = provider

    report_date = generated_at.astimezone(LOCAL_TZ).date().isoformat()
    json_path, xlsx_path = _output_paths(output_dir, report_date, overwrite=overwrite)
    _write_json(json_path, payload)
    _write_xlsx(xlsx_path, payload)
    report_path = write_strain_gauge_report(payload, output_dir=report_dir, report_date=report_date)
    payload["output_json"] = str(json_path)
    payload["output_xlsx"] = str(xlsx_path)
    payload["output_markdown"] = str(report_path)
    _write_json(json_path, payload)
    return payload


def _load_key_from_local_secrets(name):
    value = os.getenv(name, "")
    if value:
        return value
    secrets_path = PROJECT_ROOT / ".streamlit" / "secrets.toml"
    if not secrets_path.exists():
        return ""
    try:
        data = tomllib.loads(secrets_path.read_text(encoding="utf-8-sig"))
    except Exception:
        return ""
    return str(data.get(name) or "")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Collect strain gauge and robotic six-axis force sensor intelligence.")
    parser.add_argument("--provider", default=os.getenv("STRAIN_GAUGE_SEARCH_PROVIDER", "exa"), choices=["exa", "tavily", "hybrid"])
    parser.add_argument("--max-queries-per-type", type=int, default=8)
    parser.add_argument("--results-per-query", type=int, default=6)
    parser.add_argument("--output-dir", default=str(DEFAULT_RAW_DIR))
    parser.add_argument("--report-dir", default=str(DEFAULT_REPORT_DIR))
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)

    payload = collect_strain_gauge_module(
        provider=args.provider,
        tavily_key=_load_key_from_local_secrets("TAVILY_API_KEY"),
        exa_key=_load_key_from_local_secrets("EXA_API_KEY"),
        max_queries_per_type=args.max_queries_per_type,
        results_per_query=args.results_per_query,
        output_dir=args.output_dir,
        report_dir=args.report_dir,
        overwrite=args.overwrite,
    )
    print(json.dumps({
        "output_json": payload.get("output_json"),
        "output_xlsx": payload.get("output_xlsx"),
        "output_markdown": payload.get("output_markdown"),
        "counts": payload.get("quantity_check", {}).get("counts"),
        "passed": payload.get("quantity_check", {}).get("passed"),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
