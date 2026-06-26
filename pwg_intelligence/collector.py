"""PWG daily search collector.

Phase 3 stores raw search results for PWG intelligence tracking. It is kept
independent from channel-1/channel-3 pipelines and only reuses search_web().
"""

from __future__ import annotations

import argparse
import datetime as _dt
import html
import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import xlsxwriter

from .classifier import category_to_scene, category_to_track, classify_pwg_result
from .excel_store import DEFAULT_WORKBOOK_PATH, write_pwg_intelligence_rows
from .pwg_scoring import assess_pwg_maturity, score_pwg_opportunity
from .pwg_source_policy import assess_pwg_source
from tools.pwg_query_packs import build_pwg_query_pack, load_pwg_query_config
from tools.search_engine import extract_result_datetime, search_web


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RAW_DIR = PROJECT_ROOT / "data" / "pwg_intelligence" / "raw"
DEFAULT_LOOKBACK_DAYS = 7
DEFAULT_RESULTS_PER_QUERY = 8
LOCAL_TZ = _dt.timezone(_dt.timedelta(hours=8))

RAW_RESULT_COLUMNS = [
    "query",
    "title",
    "url",
    "source_name",
    "published_date",
    "snippet",
    "fetched_at",
    "search_provider",
]

TRACKING_QUERY_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "utm_id",
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "igshid",
    "ref",
}

GENERIC_QUERY_TOKENS = {
    "latest",
    "product",
    "release",
    "technology",
    "roadmap",
    "supplier",
    "progress",
    "application",
    "market",
    "update",
    "news",
    "daily",
}


@dataclass(frozen=True)
class PWGRawSearchResult:
    query: str
    title: str
    url: str
    source_name: str
    published_date: str
    snippet: str
    fetched_at: str
    search_provider: str

    def to_dict(self):
        return asdict(self)


def _ensure_utc(value):
    if value is None:
        return _dt.datetime.now(_dt.timezone.utc)
    if isinstance(value, _dt.datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=_dt.timezone.utc)
        return value.astimezone(_dt.timezone.utc)
    raise TypeError("now must be a datetime or None")


def _html_to_text(value):
    text = html.unescape(str(value or ""))
    text = re.sub(r"<script.*?>.*?</script>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<style.*?>.*?</style>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_pwg_url(url):
    raw = str(url or "").strip()
    if not raw:
        return ""
    if "://" not in raw and re.match(r"^[A-Za-z0-9.-]+\.[A-Za-z]{2,}(/|$)", raw):
        raw = "https://" + raw
    parts = urlsplit(raw)
    if not parts.scheme and parts.netloc:
        scheme = "https"
    else:
        scheme = (parts.scheme or "https").lower()
    netloc = parts.netloc.lower()
    if netloc.endswith(":80") and scheme == "http":
        netloc = netloc[:-3]
    if netloc.endswith(":443") and scheme == "https":
        netloc = netloc[:-4]
    path = re.sub(r"/{2,}", "/", parts.path or "")
    if path != "/":
        path = path.rstrip("/")
    query_pairs = []
    for key, value in parse_qsl(parts.query, keep_blank_values=False):
        key_lower = key.lower()
        if key_lower.startswith("utm_") or key_lower in TRACKING_QUERY_PARAMS:
            continue
        query_pairs.append((key, value))
    query = urlencode(query_pairs, doseq=True)
    return urlunsplit((scheme, netloc, path, query, ""))


def _domain_from_url(url):
    netloc = urlsplit(str(url or "")).netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    return netloc


def _normalize_title_key(title):
    text = _html_to_text(title).lower()
    text = re.sub(r"[\W_]+", "", text, flags=re.UNICODE)
    return text


def _iter_config_terms(config):
    keyword_config = (config or {}).get("keywords", {}) or {}
    for payload in (keyword_config.get("categories", {}) or {}).values():
        for term in (payload or {}).get("terms", []) or []:
            yield term

    company_config = (config or {}).get("companies", {}) or {}
    for group in (company_config.get("company_groups", {}) or {}).values():
        for company in (group or {}).get("companies", []) or []:
            yield company.get("name", "")
            for alias in company.get("aliases", []) or []:
                yield alias
            for term in company.get("watch_terms", []) or []:
                yield term

    application_config = (config or {}).get("application_map", {}) or {}
    for scene in application_config.get("application_scenes", []) or []:
        yield scene.get("name", "")
        for alias in scene.get("aliases", []) or []:
            yield alias
        for term in scene.get("query_terms", []) or []:
            yield term
        for term in scene.get("standard_refs", []) or []:
            yield term


def _build_relevance_terms(config):
    terms = []
    seen = set()
    for term in _iter_config_terms(config):
        value = str(term or "").strip()
        if not value:
            continue
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        terms.append(value)
    return terms


def _contains_cjk_or_kana(text):
    return bool(re.search(r"[\u3040-\u30ff\u3400-\u9fff]", str(text or "")))


def _term_in_text(term, text, lowered_text):
    value = str(term or "").strip()
    if not value:
        return False
    if _contains_cjk_or_kana(value):
        return value in text
    return value.lower() in lowered_text


def _meaningful_query_tokens(query):
    tokens = []
    for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9.+-]*|[\u3040-\u30ff\u3400-\u9fff]{2,}", str(query or "")):
        normalized = token.strip().lower()
        if not normalized or normalized in GENERIC_QUERY_TOKENS:
            continue
        if len(normalized) < 3 and not _contains_cjk_or_kana(token):
            continue
        tokens.append(token)
    return tokens


def _is_relevant_result(title, snippet, url, query, relevance_terms):
    text = f"{title} {snippet} {url}"
    lowered = text.lower()
    if any(_term_in_text(term, text, lowered) for term in relevance_terms):
        return True
    query_tokens = _meaningful_query_tokens(query)
    hits = sum(1 for token in query_tokens if _term_in_text(token, text, lowered))
    return hits >= min(2, len(query_tokens)) if query_tokens else False


def _published_date_from_result(item):
    published_dt, _ = extract_result_datetime(dict(item or {}))
    if not published_dt:
        return None, ""
    published_dt = published_dt.astimezone(_dt.timezone.utc)
    return published_dt, published_dt.isoformat().replace("+00:00", "Z")


def _within_lookback_window(published_dt, now, lookback_days, future_tolerance_hours=6):
    if not published_dt:
        return False
    baseline = _ensure_utc(now)
    delta = baseline - published_dt.astimezone(_dt.timezone.utc)
    if delta > _dt.timedelta(days=int(lookback_days or DEFAULT_LOOKBACK_DAYS)):
        return False
    if delta < -_dt.timedelta(hours=future_tolerance_hours):
        return False
    return True


def _normalize_search_result(item, query, fetched_at, fallback_provider):
    item = dict(item or {})
    title = _html_to_text(item.get("title"))
    normalized_url = normalize_pwg_url(item.get("url"))
    source_name = str(item.get("source") or item.get("source_name") or _domain_from_url(normalized_url)).strip()
    snippet = _html_to_text(item.get("snippet") or item.get("content") or item.get("summary"))
    search_provider = str(item.get("search_provider") or item.get("provider") or fallback_provider or "").strip()
    published_dt, published_date = _published_date_from_result(item)
    return {
        "record": PWGRawSearchResult(
            query=str(query or "").strip(),
            title=title,
            url=normalized_url,
            source_name=source_name,
            published_date=published_date,
            snippet=snippet,
            fetched_at=fetched_at,
            search_provider=search_provider,
        ),
        "published_dt": published_dt,
        "domain": _domain_from_url(normalized_url),
        "title_key": _normalize_title_key(title),
    }


def filter_pwg_raw_results(raw_results, now=None, lookback_days=DEFAULT_LOOKBACK_DAYS, relevance_terms=None):
    baseline = _ensure_utc(now)
    terms = list(relevance_terms or [])
    stats = {
        "input_count": len(raw_results or []),
        "kept_count": 0,
        "dropped_missing_core_fields_count": 0,
        "dropped_missing_timestamp_count": 0,
        "dropped_time_window_count": 0,
        "dropped_irrelevant_count": 0,
        "dropped_duplicate_url_count": 0,
        "dropped_duplicate_title_count": 0,
        "dropped_duplicate_domain_count": 0,
    }
    kept = []
    seen_urls = set()
    seen_titles = set()
    seen_domains = set()
    dropped_samples = []

    for item in raw_results or []:
        normalized = _normalize_search_result(
            item.get("item", {}),
            item.get("query", ""),
            item.get("fetched_at", ""),
            item.get("search_provider", ""),
        )
        record = normalized["record"]
        if not record.title or not record.url:
            stats["dropped_missing_core_fields_count"] += 1
            continue
        if not normalized["published_dt"]:
            stats["dropped_missing_timestamp_count"] += 1
            if len(dropped_samples) < 8:
                dropped_samples.append(f"缺少时间戳：{record.title}")
            continue
        if not _within_lookback_window(normalized["published_dt"], baseline, lookback_days):
            stats["dropped_time_window_count"] += 1
            if len(dropped_samples) < 8:
                dropped_samples.append(f"时间超窗：{record.title}")
            continue
        if not _is_relevant_result(record.title, record.snippet, record.url, record.query, terms):
            stats["dropped_irrelevant_count"] += 1
            if len(dropped_samples) < 8:
                dropped_samples.append(f"明显无关：{record.title}")
            continue
        url_key = record.url.lower()
        if url_key in seen_urls:
            stats["dropped_duplicate_url_count"] += 1
            continue
        if normalized["title_key"] and normalized["title_key"] in seen_titles:
            stats["dropped_duplicate_title_count"] += 1
            continue
        if normalized["domain"] and normalized["domain"] in seen_domains:
            stats["dropped_duplicate_domain_count"] += 1
            continue
        seen_urls.add(url_key)
        if normalized["title_key"]:
            seen_titles.add(normalized["title_key"])
        if normalized["domain"]:
            seen_domains.add(normalized["domain"])
        kept.append(record)

    stats["kept_count"] = len(kept)
    return kept, stats, dropped_samples


def _resolve_output_paths(output_dir, mode, output_date, generated_at, overwrite=False):
    base_dir = Path(output_dir or DEFAULT_RAW_DIR)
    base_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{mode}_{output_date}"
    json_path = base_dir / f"{stem}.json"
    xlsx_path = base_dir / f"{stem}.xlsx"
    if overwrite or (not json_path.exists() and not xlsx_path.exists()):
        return json_path, xlsx_path

    suffix = generated_at.astimezone(LOCAL_TZ).strftime("%H%M%S")
    indexed_stem = f"{stem}_{suffix}"
    json_path = base_dir / f"{indexed_stem}.json"
    xlsx_path = base_dir / f"{indexed_stem}.xlsx"
    counter = 2
    while json_path.exists() or xlsx_path.exists():
        json_path = base_dir / f"{indexed_stem}_{counter}.json"
        xlsx_path = base_dir / f"{indexed_stem}_{counter}.xlsx"
        counter += 1
    return json_path, xlsx_path


def write_pwg_raw_json(path, payload):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("w", encoding="utf-8") as file_obj:
        json.dump(payload, file_obj, ensure_ascii=False, indent=2)


def write_pwg_raw_xlsx(path, records):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    workbook = xlsxwriter.Workbook(str(path))
    worksheet = workbook.add_worksheet("raw_results")
    header_fmt = workbook.add_format({"bold": True, "bg_color": "#D9EAF7", "border": 1})
    text_fmt = workbook.add_format({"text_wrap": True, "valign": "top"})
    for col_idx, column in enumerate(RAW_RESULT_COLUMNS):
        worksheet.write(0, col_idx, column, header_fmt)
    for row_idx, record in enumerate(records, start=1):
        row = record.to_dict()
        for col_idx, column in enumerate(RAW_RESULT_COLUMNS):
            worksheet.write(row_idx, col_idx, row.get(column, ""), text_fmt)
    worksheet.freeze_panes(1, 0)
    worksheet.autofilter(0, 0, max(1, len(records)), len(RAW_RESULT_COLUMNS) - 1)
    widths = {
        "query": 36,
        "title": 48,
        "url": 60,
        "source_name": 22,
        "published_date": 24,
        "snippet": 72,
        "fetched_at": 24,
        "search_provider": 16,
    }
    for col_idx, column in enumerate(RAW_RESULT_COLUMNS):
        worksheet.set_column(col_idx, col_idx, widths.get(column, 18))
    workbook.close()


def _detect_language(text):
    value = str(text or "")
    if re.search(r"[\u3040-\u30ff]", value):
        return "ja"
    if re.search(r"[\u3400-\u9fff]", value):
        return "zh"
    return "en"


def _short_text(value, max_chars=320):
    text = _html_to_text(value)
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "..."


def _evidence_strength(source_level, confidence):
    if source_level == "A" and confidence >= 0.65:
        return "high"
    if source_level in {"A", "B"} or confidence >= 0.55:
        return "medium"
    return "low"


def _fpc_relevance_for_category(category):
    mapping = {
        "automotive": "与车载光线束、ECU板边接口、Camera链路和光电混合FPC验证相关。",
        "connector": "与FPC端口保护、连接器装配、补强结构和光纤阵列对位相关。",
        "cpo_datacenter": "与光模块内光路重排、PIC到FA扇出、optical RDL和光电混合载体相关。",
        "material_process": "与FPC贴合、图形化、弯折可靠性、端口污染和工艺窗口评估相关。",
        "standard": "可能影响光电混合FPC测试、接口规格和客户验收口径。",
        "patent": "用于判断FPC可切入结构、工艺边界和潜在专利风险。",
        "paper": "可作为材料、损耗、可靠性和制程可行性的早期技术证据。",
        "exhibition": "用于跟踪厂商样品、展会展示和潜在客户/供应链线索。",
        "company_update": "用于跟踪厂商产品节奏和供应链合作变化。",
    }
    return mapping.get(category, "需人工判断与FPC产品或工艺能力的关联。")


def _recommended_action(score, needs_manual_review, category):
    if needs_manual_review:
        return "人工复核来源、正文和事件真实性后再决定是否进入机会漏斗。"
    if score >= 70:
        return "优先纳入机会漏斗，补充原文、竞品和客户应用信息。"
    if category in {"patent", "standard"}:
        return "加入专题跟踪，整理同族/标准范围和FPC相关约束。"
    return "保留为日常情报线索，后续结合更多来源复核。"


def _next_review_date(fetched_at, needs_manual_review):
    try:
        baseline = _dt.datetime.fromisoformat(str(fetched_at).replace("Z", "+00:00"))
    except ValueError:
        baseline = _dt.datetime.now(_dt.timezone.utc)
    days = 3 if needs_manual_review else 14
    return (baseline.astimezone(LOCAL_TZ).date() + _dt.timedelta(days=days)).isoformat()


def _date_only(value):
    raw = str(value or "").strip()
    return raw[:10] if raw else ""


def _classified_result_to_row(record, classification, source_assessment, maturity_assessment, opportunity, card_id):
    text_for_language = f"{record.title} {record.snippet}"
    needs_manual_review = (
        bool(source_assessment.needs_manual_review)
        or bool(opportunity.needs_manual_review)
        or classification.confidence < 0.45
    )
    return {
        "card_id": card_id,
        "published_date": _date_only(record.published_date),
        "event_date": _date_only(record.published_date),
        "collected_at": record.fetched_at,
        "source_type": source_assessment.source_type,
        "source_level": source_assessment.source_level,
        "source_name": record.source_name,
        "title": record.title,
        "source_url": record.url,
        "original_language": _detect_language(text_for_language),
        "main_track": category_to_track(classification.category),
        "application_scene": category_to_scene(classification.category),
        "keywords": "；".join(classification.matched_terms),
        "factual_summary": _short_text(record.snippet or record.title, max_chars=320),
        "key_parameters": (
            f"pwg_category={classification.category}；"
            f"search_provider={record.search_provider}；"
            f"classification_confidence={classification.confidence}"
        ),
        "maturity_level": maturity_assessment.maturity_level,
        "evidence_strength": _evidence_strength(source_assessment.source_level, classification.confidence),
        "fpc_relevance": _fpc_relevance_for_category(classification.category),
        "recommended_action": _recommended_action(opportunity.opportunity_score, needs_manual_review, classification.category),
        "owner": "",
        "next_review_date": _next_review_date(record.fetched_at, needs_manual_review),
        "demo_flag": "",
        "pwg_category": classification.category,
        "opportunity_score": opportunity.opportunity_score,
        "scoring_reason": opportunity.scoring_reason,
        "needs_manual_review": str(needs_manual_review).lower(),
        "classification_reason": classification.classification_reason,
        "source_level_reason": source_assessment.source_level_reason,
        "maturity_reason": maturity_assessment.maturity_reason,
    }


def classify_and_score_pwg_records(records, fetched_at="", allow_low_trust_fallback=True):
    assessed = []
    for index, record in enumerate(records or [], start=1):
        classification = classify_pwg_result(record)
        source_assessment = assess_pwg_source(record, classification.category)
        maturity_assessment = assess_pwg_maturity(record, classification.category, source_assessment)
        opportunity = score_pwg_opportunity(record, classification, source_assessment, maturity_assessment)
        assessed.append(
            {
                "record": record,
                "classification": classification,
                "source_assessment": source_assessment,
                "maturity_assessment": maturity_assessment,
                "opportunity": opportunity,
                "index": index,
            }
        )

    non_d = [item for item in assessed if item["source_assessment"].source_level != "D"]
    low_trust_fallback_used = False
    if non_d:
        kept = non_d
        dropped_low_trust = len(assessed) - len(non_d)
    elif assessed and allow_low_trust_fallback:
        kept = assessed
        dropped_low_trust = 0
        low_trust_fallback_used = True
    else:
        kept = []
        dropped_low_trust = len(assessed)

    source_level_counts = {}
    category_counts = {}
    maturity_counts = {}
    manual_review = []
    rows = []
    local_date = ""
    if fetched_at:
        try:
            local_date = _dt.datetime.fromisoformat(str(fetched_at).replace("Z", "+00:00")).astimezone(LOCAL_TZ).strftime("%Y%m%d")
        except ValueError:
            local_date = _dt.datetime.now(LOCAL_TZ).strftime("%Y%m%d")
    else:
        local_date = _dt.datetime.now(LOCAL_TZ).strftime("%Y%m%d")

    for output_index, item in enumerate(kept, start=1):
        classification = item["classification"]
        source_assessment = item["source_assessment"]
        maturity_assessment = item["maturity_assessment"]
        opportunity = item["opportunity"]
        source_level_counts[source_assessment.source_level] = source_level_counts.get(source_assessment.source_level, 0) + 1
        category_counts[classification.category] = category_counts.get(classification.category, 0) + 1
        maturity_counts[maturity_assessment.maturity_level] = maturity_counts.get(maturity_assessment.maturity_level, 0) + 1
        card_id = f"PWG-{local_date}-{output_index:03d}"
        row = _classified_result_to_row(
            item["record"],
            classification,
            source_assessment,
            maturity_assessment,
            opportunity,
            card_id,
        )
        rows.append(row)
        if row["needs_manual_review"] == "true":
            manual_review.append(
                {
                    "card_id": card_id,
                    "title": item["record"].title,
                    "url": item["record"].url,
                    "pwg_category": classification.category,
                    "source_level": source_assessment.source_level,
                    "maturity_level": maturity_assessment.maturity_level,
                    "opportunity_score": opportunity.opportunity_score,
                    "reason": "；".join(
                        part for part in [
                            classification.classification_reason,
                            source_assessment.source_level_reason,
                            maturity_assessment.maturity_reason,
                            opportunity.scoring_reason,
                        ] if part
                    ),
                }
            )

    coverage = {
        "input_count": len(records or []),
        "assessed_count": len(assessed),
        "kept_count": len(kept),
        "dropped_low_trust_count": dropped_low_trust,
        "low_trust_fallback_used": low_trust_fallback_used,
        "manual_review_count": len(manual_review),
        "classification_rule_coverage": round(
            sum(1 for item in assessed if item["classification"].matched_terms) / len(assessed),
            4,
        ) if assessed else 0,
        "source_level_rule_coverage": round(
            sum(1 for item in assessed if item["source_assessment"].source_level_reason) / len(assessed),
            4,
        ) if assessed else 0,
        "maturity_rule_coverage": round(
            sum(1 for item in assessed if item["maturity_assessment"].maturity_reason) / len(assessed),
            4,
        ) if assessed else 0,
        "scoring_rule_coverage": round(
            sum(1 for item in assessed if item["opportunity"].scoring_reason) / len(assessed),
            4,
        ) if assessed else 0,
        "category_counts": category_counts,
        "source_level_counts": source_level_counts,
        "maturity_counts": maturity_counts,
    }
    return rows, coverage, manual_review


def collect_pwg_daily_scan(
    mode="daily_scan",
    max_queries=None,
    results_per_query=DEFAULT_RESULTS_PER_QUERY,
    lookback_days=DEFAULT_LOOKBACK_DAYS,
    provider="hybrid",
    tavily_key="",
    exa_key="",
    exa_settings=None,
    output_dir=None,
    workbook_path=DEFAULT_WORKBOOK_PATH,
    write_workbook=True,
    allow_low_trust_fallback=True,
    dry_run=False,
    now=None,
    search_fn=search_web,
    overwrite=False,
):
    mode_key = str(mode or "daily_scan").strip()
    if mode_key != "daily_scan":
        raise ValueError("Phase 3 collector currently supports daily_scan only.")

    generated_at = _ensure_utc(now)
    fetched_at = generated_at.isoformat().replace("+00:00", "Z")
    query_records = build_pwg_query_pack(mode_key, max_queries=max_queries)
    output_date = generated_at.astimezone(LOCAL_TZ).date().isoformat()
    config = load_pwg_query_config()
    relevance_terms = _build_relevance_terms(config)

    if dry_run:
        return {
            "mode": mode_key,
            "dry_run": True,
            "generated_at": fetched_at,
            "lookback_days": int(lookback_days or DEFAULT_LOOKBACK_DAYS),
            "query_count": len(query_records),
            "queries": [record.to_dict() for record in query_records],
            "output_dir": str(Path(output_dir or DEFAULT_RAW_DIR)),
        }

    raw_results = []
    timelimit = "w" if int(lookback_days or DEFAULT_LOOKBACK_DAYS) <= 7 else "m"
    runtime_exa_settings = {
        "category": "news",
        "search_type": "auto",
        "content_mode": "highlights_text",
        "highlights_max_characters": 1400,
        "text_max_characters": 2400,
    }
    runtime_exa_settings.update(dict(exa_settings or {}))

    for query_record in query_records:
        batch = search_fn(
            query_record.query,
            "",
            timelimit,
            max_results=int(results_per_query or DEFAULT_RESULTS_PER_QUERY),
            tavily_key=tavily_key,
            provider=provider,
            exa_key=exa_key,
            exa_settings=runtime_exa_settings,
        )
        for item in batch or []:
            raw_results.append(
                {
                    "query": query_record.query,
                    "query_type": query_record.query_type,
                    "search_provider": str((item or {}).get("search_provider") or (item or {}).get("provider") or provider),
                    "fetched_at": fetched_at,
                    "item": dict(item or {}),
                }
            )

    records, filter_stats, dropped_samples = filter_pwg_raw_results(
        raw_results,
        now=generated_at,
        lookback_days=lookback_days,
        relevance_terms=relevance_terms,
    )
    classified_rows, rule_coverage, manual_review_list = classify_and_score_pwg_records(
        records,
        fetched_at=fetched_at,
        allow_low_trust_fallback=allow_low_trust_fallback,
    )
    json_path, xlsx_path = _resolve_output_paths(output_dir, mode_key, output_date, generated_at, overwrite=overwrite)
    payload = {
        "mode": mode_key,
        "dry_run": False,
        "generated_at": fetched_at,
        "lookback_days": int(lookback_days or DEFAULT_LOOKBACK_DAYS),
        "search_provider": str(provider or ""),
        "query_count": len(query_records),
        "raw_result_count": len(raw_results),
        "kept_count": len(records),
        "classified_count": len(classified_rows),
        "filter_stats": filter_stats,
        "rule_coverage": rule_coverage,
        "manual_review_list": manual_review_list,
        "dropped_samples": dropped_samples,
        "queries": [record.to_dict() for record in query_records],
        "records": [record.to_dict() for record in records],
        "classified_rows": classified_rows,
    }
    write_pwg_raw_json(json_path, payload)
    write_pwg_raw_xlsx(xlsx_path, records)
    if write_workbook:
        workbook_output = write_pwg_intelligence_rows(classified_rows, output_path=workbook_path)
        payload["output_workbook"] = str(workbook_output)
    payload["output_json"] = str(json_path)
    payload["output_xlsx"] = str(xlsx_path)
    return payload


def main(argv=None):
    parser = argparse.ArgumentParser(description="Collect PWG raw search results.")
    parser.add_argument("--mode", default="daily_scan", help="Only daily_scan is supported in phase 3.")
    parser.add_argument("--max-queries", type=int, default=24, help="Maximum generated PWG queries.")
    parser.add_argument("--results-per-query", type=int, default=DEFAULT_RESULTS_PER_QUERY)
    parser.add_argument("--lookback-days", type=int, default=DEFAULT_LOOKBACK_DAYS)
    parser.add_argument("--provider", default=os.getenv("PWG_SEARCH_PROVIDER", "hybrid"), choices=["exa", "tavily", "hybrid"])
    parser.add_argument("--exa-key", default=os.getenv("EXA_API_KEY", ""))
    parser.add_argument("--tavily-key", default=os.getenv("TAVILY_API_KEY", ""))
    parser.add_argument("--output-dir", default=str(DEFAULT_RAW_DIR))
    parser.add_argument("--workbook-path", default=str(DEFAULT_WORKBOOK_PATH))
    parser.add_argument("--no-workbook", action="store_true", help="Do not write classified rows into pwg_intelligence.xlsx.")
    parser.add_argument("--drop-all-d", action="store_true", help="Drop D-level sources even when no A-C result exists.")
    parser.add_argument("--dry-run", action="store_true", help="Print planned queries without calling search APIs.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite daily_scan_YYYY-MM-DD outputs if they already exist.")
    args = parser.parse_args(argv)

    payload = collect_pwg_daily_scan(
        mode=args.mode,
        max_queries=args.max_queries,
        results_per_query=args.results_per_query,
        lookback_days=args.lookback_days,
        provider=args.provider,
        tavily_key=args.tavily_key,
        exa_key=args.exa_key,
        output_dir=args.output_dir,
        workbook_path=args.workbook_path,
        write_workbook=not args.no_workbook,
        allow_low_trust_fallback=not args.drop_all_d,
        dry_run=args.dry_run,
        overwrite=args.overwrite,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
