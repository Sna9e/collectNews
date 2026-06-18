"""PWG daily and weekly Markdown reports."""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

from .collector import LOCAL_TZ, PROJECT_ROOT
from .excel_store import DEFAULT_WORKBOOK_PATH, write_pwg_intelligence_rows


DEFAULT_RAW_DIR = PROJECT_ROOT / "data" / "pwg_intelligence" / "raw"
DEFAULT_REPORT_DIR = PROJECT_ROOT / "data" / "pwg_intelligence" / "reports"

DAILY_SECTION_ORDER = (
    "新产品与样品",
    "厂商动态",
    "车载应用",
    "CPO与数据中心",
    "连接器与接口",
    "材料与工艺",
    "标准、专利与论文",
)

WEEKLY_SECTION_ORDER = (
    "本周新增硬证据",
    "竞品动作",
    "应用机会变化",
    "技术路线变化",
    "值得验证的样件",
    "需要联系的厂商、供应商或高校",
    "仍然缺少的证据",
)

BANNED_REPORT_TEXT = (
    "公开材料暂未披露更多细节",
    "材料没有提供足够细节",
    "暂不能确认更多参数",
    "时间线仅记录已披露动作",
    "占位",
    "DEMO",
)

PRODUCT_TERMS = (
    "datasheet",
    "data sheet",
    "sample",
    "engineering sample",
    "product",
    "commercial",
    "shipping",
    "样品",
    "规格书",
    "产品",
    "出货",
)

SUMMARY_NOISE_PATTERNS = (
    r"\bInternal Control Policy\b.*?(?=Product|PMT|MPO|MT Ferrule|$)",
    r"\bPrivacy Policy\b",
    r"\bTerms of Use\b",
    r"\bContact Us\b",
    r"\bSite Map\b",
    r"\bInd \[\.\.\.\]",
    r"^#+\s*",
)

SUMMARY_FOCUS_TERMS = (
    "polymer", "waveguide", "pmt", "mpo", "mt ferrule", "fiber array",
    "connector", "cpo", "optical engine", "oif", "ieee", "standard",
    "patent", "photonic", "springer", "largan", "hakusan", "fpc",
    "光波导", "连接器", "标准", "专利", "论文", "样品", "量产",
)

FPC_CONTEXT_BY_CATEGORY = {
    "automotive": "验证关注点：车规可靠性、线束减重、摄像头/域控端口保护和弯折寿命。",
    "connector": "验证关注点：FA/PMT/MPO/MT接口与FPC端口固定、被动对准、补强件设计和装配公差。",
    "cpo_datacenter": "验证关注点：CPO/光引擎中的短距光路重排、PIC到FA扇出、光电混合载体和散热边界。",
    "material_process": "验证关注点：贴合、图形化、弯折损耗、粗糙度损耗和温湿可靠性窗口。",
    "standard": "验证关注点：接口、测试项目、链路预算和客户验收标准是否影响FPC设计规则。",
    "patent": "验证关注点：权利要求是否覆盖FPC光路布局、端口结构、转向镜或耦合封装。",
    "paper": "验证关注点：论文参数是否能迁移到FPC材料、制程窗口和可靠性测试矩阵。",
    "exhibition": "验证关注点：展出样件是否可获得、是否存在真实客户验证和可制造性数据。",
    "company_update": "验证关注点：厂商动作是否对应样品、客户导入、供应链合作或可采购产品。",
}


def _now_utc():
    return _dt.datetime.now(_dt.timezone.utc)


def _parse_datetime(value):
    raw = str(value or "").strip()
    if not raw:
        return None
    for candidate in (raw, raw.replace("Z", "+00:00"), raw[:10]):
        try:
            parsed = _dt.datetime.fromisoformat(candidate)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=_dt.timezone.utc)
            return parsed.astimezone(_dt.timezone.utc)
        except ValueError:
            continue
    return None


def _local_date(value):
    parsed = _parse_datetime(value)
    if parsed:
        return parsed.astimezone(LOCAL_TZ).date()
    raw = str(value or "").strip()
    if raw:
        try:
            return _dt.date.fromisoformat(raw[:10])
        except ValueError:
            pass
    return None


def _report_date_from_value(value=None):
    if value:
        if isinstance(value, _dt.date) and not isinstance(value, _dt.datetime):
            return value
        return _dt.date.fromisoformat(str(value)[:10])
    return _dt.datetime.now(LOCAL_TZ).date()


def _score(row):
    try:
        return int(float(row.get("opportunity_score") or 0))
    except (TypeError, ValueError):
        return 0


def _source_rank(row):
    return {"A": 4, "B": 3, "C": 2, "D": 0}.get(str(row.get("source_level") or ""), 1)


def _is_true(value):
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def _clean_text(value):
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text


def _clean_summary_text(value, max_chars=360):
    text = _clean_text(value).replace("[...]", "...")
    for pattern in SUMMARY_NOISE_PATTERNS:
        text = re.sub(pattern, " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+-\s+", " | ", text)
    parts = [part.strip(" |;,.") for part in re.split(r"\s*\|\s*|(?<=[。！？.!?])\s+", text) if part.strip(" |;,.")]
    focused = [
        part for part in parts
        if any(term in part.lower() for term in SUMMARY_FOCUS_TERMS)
    ]
    selected = focused[:5] if focused else parts[:3]
    cleaned = "；".join(selected).strip("； ")
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r"\s+(and|or|but|with|for|to)$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+in\s+[A-Z][a-z]+\s+and$", "", cleaned)
    if len(cleaned) > max_chars:
        cleaned = cleaned[: max_chars - 1].rstrip() + "..."
    return cleaned or text[:max_chars]


def _source_level_text(row):
    level = _clean_text(row.get("source_level"))
    if level == "C":
        return "C（间接证据，需核实原始来源）"
    if level == "D":
        return "D（低可信线索，仅供人工复核）"
    return level


def _fpc_relation_text(row):
    base = _clean_text(row.get("fpc_relevance"))
    category = _clean_text(row.get("pwg_category"))
    context = FPC_CONTEXT_BY_CATEGORY.get(category, "")
    if context and context not in base:
        return f"{base} {context}".strip()
    return base


def _has_banned_text(row):
    blob = " ".join(str(row.get(key, "") or "") for key in ("title", "factual_summary", "fpc_relevance", "recommended_action"))
    return any(term in blob for term in BANNED_REPORT_TEXT)


def _is_valid_report_row(row, min_score=50):
    if not isinstance(row, dict):
        return False
    if row.get("demo_flag") == "DEMO" or _has_banned_text(row):
        return False
    required = ("title", "factual_summary", "source_url", "source_level", "maturity_level", "fpc_relevance", "recommended_action")
    if any(not _clean_text(row.get(field)) for field in required):
        return False
    if len(_clean_summary_text(row.get("factual_summary"), max_chars=500)) < 30:
        return False
    if str(row.get("source_level") or "") == "D":
        return False
    if _score(row) < min_score:
        return False
    if _is_true(row.get("needs_manual_review")) and _score(row) < 70:
        return False
    return True


def _dedupe_rows(rows):
    deduped = []
    seen = set()
    for row in rows or []:
        url = _clean_text(row.get("source_url")).lower()
        title = re.sub(r"[\W_]+", "", _clean_text(row.get("title")).lower(), flags=re.UNICODE)
        summary = re.sub(r"\s+", "", _clean_text(row.get("factual_summary")).lower())[:80]
        key = url or title or summary
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def _sort_rows(rows):
    return sorted(
        rows or [],
        key=lambda row: (
            -_score(row),
            -_source_rank(row),
            str(row.get("published_date") or row.get("collected_at") or ""),
        ),
    )


def _row_blob(row):
    return " ".join(str(row.get(key, "") or "") for key in ("title", "factual_summary", "keywords", "fpc_relevance")).lower()


def _daily_section_for_row(row):
    category = str(row.get("pwg_category") or "").strip()
    blob = _row_blob(row)
    maturity = str(row.get("maturity_level") or "")
    if category in {"standard", "patent", "paper"}:
        return "标准、专利与论文"
    if maturity in {"M4", "M5", "M6", "M7"} or any(term in blob for term in PRODUCT_TERMS):
        return "新产品与样品"
    if category in {"company_update", "exhibition"}:
        return "厂商动态"
    if category == "automotive":
        return "车载应用"
    if category == "cpo_datacenter":
        return "CPO与数据中心"
    if category == "connector":
        return "连接器与接口"
    if category == "material_process":
        return "材料与工艺"
    return "厂商动态"


def select_daily_rows(rows, report_date=None, min_score=50):
    target = _report_date_from_value(report_date)
    candidates = []
    for row in rows or []:
        if not _is_valid_report_row(row, min_score=min_score):
            continue
        collected_date = _local_date(row.get("collected_at"))
        if collected_date and collected_date != target:
            continue
        candidates.append(row)
    return _sort_rows(_dedupe_rows(candidates))


def select_weekly_rows(rows, end_date=None, min_score=45, max_items=20):
    target = _report_date_from_value(end_date)
    start = target - _dt.timedelta(days=6)
    candidates = []
    for row in rows or []:
        if not _is_valid_report_row(row, min_score=min_score):
            continue
        row_date = _local_date(row.get("collected_at")) or _local_date(row.get("published_date"))
        if row_date and not (start <= row_date <= target):
            continue
        candidates.append(row)
    return _sort_rows(_dedupe_rows(candidates))[:max_items]


def _markdown_link(url):
    clean_url = _clean_text(url)
    return f"[原文]({clean_url})" if clean_url else ""


def _render_clue(row):
    return (
        f"### {_clean_text(row.get('title'))}\n"
        f"- 事实摘要：{_clean_summary_text(row.get('factual_summary'))}\n"
        f"- 原文链接：{_markdown_link(row.get('source_url'))}\n"
        f"- 来源等级：{_source_level_text(row)}\n"
        f"- 产品成熟度：{_clean_text(row.get('maturity_level'))}\n"
        f"- 与FPC的关系：{_fpc_relation_text(row)}\n"
        f"- 下一步动作：{_clean_text(row.get('recommended_action'))}\n"
    )


def build_daily_brief_markdown(rows, report_date=None, generated_at=None):
    target = _report_date_from_value(report_date)
    selected = select_daily_rows(rows, report_date=target)
    grouped = {section: [] for section in DAILY_SECTION_ORDER}
    for row in selected:
        grouped[_daily_section_for_row(row)].append(row)

    generated = generated_at or _now_utc()
    lines = [
        f"# PWG每日简报（{target.isoformat()}）",
        "",
        f"生成时间：{generated.astimezone(LOCAL_TZ).isoformat()}",
        f"本期高价值新增线索：{len(selected)} 条",
        "",
    ]
    if not selected:
        lines.append("本期未筛选出符合阈值的新增高价值线索。")
        return "\n".join(lines).rstrip() + "\n"

    for section in DAILY_SECTION_ORDER:
        section_rows = grouped.get(section, [])
        if not section_rows:
            continue
        lines.extend([f"## {section}", ""])
        for row in section_rows:
            lines.append(_render_clue(row))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _weekly_section_rows(rows, section):
    if section == "本周新增硬证据":
        return [row for row in rows if row.get("source_level") in {"A", "B"} and row.get("maturity_level") in {"M2", "M3", "M4", "M5", "M6", "M7"}][:6]
    if section == "竞品动作":
        return [row for row in rows if row.get("pwg_category") in {"company_update", "exhibition"} or row.get("main_track") in {"厂商动态", "展会"}][:6]
    if section == "应用机会变化":
        return [row for row in rows if row.get("pwg_category") in {"automotive", "cpo_datacenter", "connector"}][:6]
    if section == "技术路线变化":
        return [row for row in rows if row.get("pwg_category") in {"material_process", "standard", "patent", "paper"}][:6]
    if section == "值得验证的样件":
        return [row for row in rows if row.get("maturity_level") in {"M3", "M4", "M5"} or any(term in _row_blob(row) for term in PRODUCT_TERMS)][:6]
    return []


def _render_weekly_row(row):
    return (
        f"- **{_clean_text(row.get('title'))}**（{_source_level_text(row)} / "
        f"{_clean_text(row.get('maturity_level'))} / {row.get('opportunity_score', 0)}分）："
        f"{_clean_summary_text(row.get('factual_summary'))} "
        f"FPC关系：{_fpc_relation_text(row)} "
        f"下一步：{_clean_text(row.get('recommended_action'))} "
        f"{_markdown_link(row.get('source_url'))}"
    )


def _domain_from_url(url):
    netloc = urlsplit(str(url or "")).netloc
    return netloc[4:] if netloc.startswith("www.") else netloc


def _contact_targets(rows):
    targets = []
    seen = set()
    for row in rows:
        source = _clean_text(row.get("source_name")) or _domain_from_url(row.get("source_url"))
        if not source:
            continue
        key = source.lower()
        if key in seen:
            continue
        seen.add(key)
        targets.append(f"- {source}：围绕“{_clean_text(row.get('title'))}”确认样品、规格、合作窗口或论文/专利作者信息。")
        if len(targets) >= 8:
            break
    return targets


def _missing_evidence(rows):
    lines = []
    if not any(row.get("source_level") == "A" for row in rows):
        lines.append("- 缺少公司官网、Datasheet、标准原文、专利原文或论文原文级别的 A 级证据。")
    if not any(row.get("maturity_level") in {"M5", "M6", "M7"} for row in rows):
        lines.append("- 缺少客户验证、商业销售或稳定量产证据，当前不能把多数线索视为量产机会。")
    categories = {row.get("pwg_category") for row in rows}
    for category, label in (("automotive", "车载应用"), ("cpo_datacenter", "CPO与数据中心"), ("connector", "连接器与接口")):
        if category not in categories:
            lines.append(f"- {label}方向本周缺少足够强的新证据，需要补充原始信源或供应链访谈。")
    if not lines:
        lines.append("- 仍需补充客户名称、样品可获得性、关键参数、可靠性条件和竞品价格/供货窗口。")
    return lines


def _week_label(end_date):
    target = _report_date_from_value(end_date)
    iso = target.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def build_weekly_review_markdown(rows, end_date=None, generated_at=None):
    target = _report_date_from_value(end_date)
    selected = select_weekly_rows(rows, end_date=target)
    week_label = _week_label(target)
    generated = generated_at or _now_utc()
    lines = [
        f"# PWG周报（{week_label}）",
        "",
        f"统计窗口：{(target - _dt.timedelta(days=6)).isoformat()} 至 {target.isoformat()}",
        f"生成时间：{generated.astimezone(LOCAL_TZ).isoformat()}",
        f"本周入选重要线索：{len(selected)} 条",
        "",
    ]
    assigned = _assign_weekly_sections(selected)
    for section in WEEKLY_SECTION_ORDER:
        lines.extend([f"## {section}", ""])
        if section == "需要联系的厂商、供应商或高校":
            items = _contact_targets(selected)
        elif section == "仍然缺少的证据":
            items = _missing_evidence(selected)
        else:
            items = [_render_weekly_row(row) for row in assigned.get(section, [])]
        if items:
            lines.extend(items)
        else:
            lines.append("- 本周没有筛选出达到阈值且未重复的对应线索。")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _assign_weekly_sections(rows):
    grouped = {section: [] for section in WEEKLY_SECTION_ORDER}
    for row in rows or []:
        if row.get("source_level") in {"A", "B"} and row.get("maturity_level") in {"M2", "M3", "M4", "M5", "M6", "M7"}:
            grouped["本周新增硬证据"].append(row)
        elif row.get("pwg_category") in {"company_update", "exhibition"} or row.get("main_track") in {"厂商动态", "展会"}:
            grouped["竞品动作"].append(row)
        elif row.get("pwg_category") in {"automotive", "cpo_datacenter", "connector"}:
            grouped["应用机会变化"].append(row)
        elif row.get("pwg_category") in {"material_process", "standard", "patent", "paper"}:
            grouped["技术路线变化"].append(row)
        elif row.get("maturity_level") in {"M3", "M4", "M5"} or any(term in _row_blob(row) for term in PRODUCT_TERMS):
            grouped["值得验证的样件"].append(row)
    return grouped


def build_weekly_opportunity_rows(rows, end_date=None, max_items=10):
    target = _report_date_from_value(end_date)
    week_label = _week_label(target)
    selected = [
        row for row in select_weekly_rows(rows, end_date=target, min_score=55, max_items=20)
        if row.get("pwg_category") in {"automotive", "connector", "cpo_datacenter", "material_process", "company_update", "exhibition"}
    ][:max_items]
    output = []
    for index, row in enumerate(selected, start=1):
        score = _score(row)
        priority = "P1" if score >= 75 else ("P2" if score >= 60 else "P3")
        output.append(
            {
                "opportunity_id": f"PWG-OPP-{week_label}-{index:03d}",
                "opportunity_name": _clean_text(row.get("title"))[:120],
                "application_scene": _clean_text(row.get("application_scene")),
                "target_customer_or_segment": _target_segment(row),
                "required_fpc_capability": _required_fpc_capability(row),
                "pwg_linkage": _clean_text(row.get("fpc_relevance")),
                "maturity_level": _clean_text(row.get("maturity_level")),
                "priority": priority,
                "recommended_action": _clean_text(row.get("recommended_action")),
                "owner": "",
                "next_review_date": (target + _dt.timedelta(days=14)).isoformat(),
                "demo_flag": "",
            }
        )
    return output


def _target_segment(row):
    mapping = {
        "automotive": "车载 Tier1、线束供应商、摄像头/域控模组客户",
        "connector": "连接器厂商、光纤阵列供应商、FPC/模组装配客户",
        "cpo_datacenter": "光模块、交换机、CPO光引擎和先进封装客户",
        "material_process": "材料供应商、制程开发团队、可靠性验证客户",
        "company_update": "对应厂商及其潜在供应链/客户",
        "exhibition": "参展厂商、样品供应商和潜在合作客户",
    }
    return mapping.get(row.get("pwg_category"), "待人工确认目标客户或供应链角色")


def _required_fpc_capability(row):
    mapping = {
        "automotive": "车规可靠性、端口保护、柔性连接、板边补强和装配公差控制",
        "connector": "连接器装配、端口防护、精密对位、补强和柔性载体设计",
        "cpo_datacenter": "光电混合载体、短距光路重排、PIC/FA耦合、先进封装协同",
        "material_process": "贴合、图形化、弯折可靠性、污染控制和制程窗口验证",
        "company_update": "样品评估、供应链配合、FPC结构适配和客户验证",
        "exhibition": "样品拆解、供应商访谈、规格确认和可制造性评估",
    }
    return mapping.get(row.get("pwg_category"), "待人工拆解所需FPC能力")


def load_classified_rows_from_json(path):
    with Path(path).open("r", encoding="utf-8") as file_obj:
        payload = json.load(file_obj)
    return list(payload.get("classified_rows") or [])


def find_latest_raw_json(raw_dir=DEFAULT_RAW_DIR):
    files = sorted(Path(raw_dir).glob("daily_scan_*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
    return files[0] if files else None


def load_recent_classified_rows(raw_dir=DEFAULT_RAW_DIR, end_date=None, days=7):
    target = _report_date_from_value(end_date)
    start = target - _dt.timedelta(days=max(1, int(days or 7)) - 1)
    rows = []
    for path in sorted(Path(raw_dir).glob("daily_scan_*.json")):
        try:
            with path.open("r", encoding="utf-8") as file_obj:
                payload = json.load(file_obj)
        except (OSError, json.JSONDecodeError):
            continue
        generated_date = _local_date(payload.get("generated_at"))
        if generated_date and not (start <= generated_date <= target):
            continue
        rows.extend(payload.get("classified_rows") or [])
    return rows


def write_daily_brief(rows, report_date=None, output_dir=DEFAULT_REPORT_DIR, generated_at=None):
    target = _report_date_from_value(report_date)
    output = Path(output_dir) / f"PWG_daily_brief_{target.isoformat()}.md"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(build_daily_brief_markdown(rows, report_date=target, generated_at=generated_at), encoding="utf-8")
    return output


def write_weekly_review(rows, end_date=None, output_dir=DEFAULT_REPORT_DIR, workbook_path=DEFAULT_WORKBOOK_PATH, update_workbook=True, generated_at=None):
    target = _report_date_from_value(end_date)
    week_label = _week_label(target)
    output = Path(output_dir) / f"PWG_weekly_review_{week_label}.md"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(build_weekly_review_markdown(rows, end_date=target, generated_at=generated_at), encoding="utf-8")
    opportunities = build_weekly_opportunity_rows(rows, end_date=target)
    workbook_output = None
    if update_workbook:
        workbook_output = write_pwg_intelligence_rows(
            select_weekly_rows(rows, end_date=target),
            output_path=workbook_path,
            opportunity_rows=opportunities,
        )
    return {
        "output_markdown": str(output),
        "output_workbook": str(workbook_output) if workbook_output else "",
        "opportunity_count": len(opportunities),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Generate PWG daily brief or weekly review.")
    parser.add_argument("--mode", choices=["daily", "weekly"], default="daily")
    parser.add_argument("--input-json", default="", help="Specific raw JSON file for daily report.")
    parser.add_argument("--raw-dir", default=str(DEFAULT_RAW_DIR))
    parser.add_argument("--output-dir", default=str(DEFAULT_REPORT_DIR))
    parser.add_argument("--date", default="", help="Daily report date or weekly end date, YYYY-MM-DD.")
    parser.add_argument("--workbook-path", default=str(DEFAULT_WORKBOOK_PATH))
    parser.add_argument("--no-workbook", action="store_true", help="Do not update opportunities workbook for weekly report.")
    args = parser.parse_args(argv)

    target_date = _report_date_from_value(args.date) if args.date else _report_date_from_value()
    if args.mode == "daily":
        input_path = Path(args.input_json) if args.input_json else find_latest_raw_json(args.raw_dir)
        rows = load_classified_rows_from_json(input_path) if input_path else []
        output = write_daily_brief(rows, report_date=target_date, output_dir=args.output_dir)
        payload = {"mode": "daily", "output_markdown": str(output), "input_json": str(input_path or ""), "row_count": len(rows)}
    else:
        rows = load_recent_classified_rows(args.raw_dir, end_date=target_date, days=7)
        payload = write_weekly_review(
            rows,
            end_date=target_date,
            output_dir=args.output_dir,
            workbook_path=args.workbook_path,
            update_workbook=not args.no_workbook,
        )
        payload.update({"mode": "weekly", "row_count": len(rows)})
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
