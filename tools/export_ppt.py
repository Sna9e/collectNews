import datetime
import math
import os
import re
import tempfile
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt

TIMELINE_CHUNK_SIZE = 6
FINANCE_CHART_LEFT = 6.85
FINANCE_CHART_TOP = 1.15
FINANCE_CHART_WIDTH = 5.45



def _get(item, key, default=""):
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)



def _fmt_number(value, digits=2):
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return "N/A" if value is None else str(value)



def _to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _ensure_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]



def _shorten(text, limit=110):
    text = str(text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
_PARENS_URL_RE = re.compile(r"\([^)]*https?://[^)]*\)", re.IGNORECASE)


def _clean_display_text(text):
    cleaned = str(text or "").strip()
    cleaned = _PARENS_URL_RE.sub("", cleaned)
    cleaned = _URL_RE.sub("", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip(" -:：;；,，")


def _estimate_line_units(text, chars_per_line=34):
    weighted_length = 0.0
    for ch in str(text or ""):
        if "\u4e00" <= ch <= "\u9fff":
            weighted_length += 1.0
        elif ord(ch) < 128:
            weighted_length += 0.55
        else:
            weighted_length += 0.8
    return max(1, int(math.ceil(weighted_length / max(chars_per_line, 1))))


def _make_entry(text, font_size=13, bold=False, color=None, space_after=6, hyperlink=None):
    return {
        "text": str(text or "").strip(),
        "font_size": font_size,
        "bold": bold,
        "color": color,
        "space_after": space_after,
        "hyperlink": hyperlink,
    }


_SECTION_LINE_RE = re.compile(r"^(【[^】]+】)\s*(.*)$")


def _normalize_summary_blocks(summary_text):
    normalized_lines = []
    current_body = []

    def flush_body():
        nonlocal current_body
        if current_body:
            merged = " ".join(part.strip() for part in current_body if str(part or "").strip())
            merged = re.sub(r"\s+", " ", merged).strip()
            if merged:
                normalized_lines.append(merged)
            current_body = []

    for raw_line in str(summary_text or "").split("\n"):
        line = str(raw_line or "").strip()
        if not line:
            flush_body()
            continue
        if _SECTION_LINE_RE.match(line):
            flush_body()
            normalized_lines.append(line)
            continue
        current_body.append(line)

    flush_body()
    return normalized_lines


def _append_summary_entries(entries, summary_text, body_font=13, space_after=6):
    indent = "　　"
    for line in _normalize_summary_blocks(summary_text):
        if not line:
            continue
        match = _SECTION_LINE_RE.match(line)
        if match:
            section_title, section_body = match.groups()
            entries.append(
                _make_entry(
                    section_title,
                    font_size=body_font,
                    bold=True,
                    color=(0, 51, 102),
                    space_after=2,
                )
            )
            if section_body.strip():
                entries.append(
                    _make_entry(
                        indent + section_body.strip(),
                        font_size=body_font,
                        bold=False,
                        color=(32, 32, 32),
                        space_after=space_after,
                    )
                )
            continue

        entries.append(
            _make_entry(
                indent + line,
                font_size=body_font,
                bold=False,
                color=(32, 32, 32),
                space_after=space_after,
            )
        )


def _entry_units(entry, chars_per_line=34):
    text = str(entry.get("text", "") or "").strip()
    if not text:
        return 0
    units = _estimate_line_units(text, chars_per_line=chars_per_line)
    units += 1 if int(entry.get("font_size", 13) or 13) >= 14 else 0
    return units


def _total_units(entries, chars_per_line=34):
    return sum(_entry_units(entry, chars_per_line=chars_per_line) for entry in entries)


def _paginate_entries(entries, max_units=24):
    pages = []
    current = []
    current_units = 0

    for entry in entries:
        text = str(entry.get("text", "") or "").strip()
        if not text:
            continue
        chars_per_line = 30 if int(entry.get("font_size", 13) or 13) >= 13 else 36
        units = _estimate_line_units(text, chars_per_line=chars_per_line)
        units += 1 if int(entry.get("font_size", 13) or 13) >= 14 else 0
        if current and current_units + units > max_units:
            pages.append(current)
            current = []
            current_units = 0
        current.append(entry)
        current_units += units

    if current:
        pages.append(current)
    return pages or [[_make_entry("暂无详情", font_size=13)]]


def _fit_entries_to_single_page(entries, max_units=28, chars_per_line=34):
    adjusted = [dict(entry) for entry in entries if str(entry.get("text", "") or "").strip()]
    if not adjusted:
        return [_make_entry("暂无详情", font_size=13)]

    def total_units():
        dynamic_total = 0
        for entry in adjusted:
            font_size = int(entry.get("font_size", 13) or 13)
            dynamic_chars = chars_per_line + max(0, 13 - font_size) * 3
            dynamic_total += _entry_units(entry, chars_per_line=dynamic_chars)
        return dynamic_total

    if total_units() <= max_units:
        return adjusted

    removable_prefixes = ["原因:", "抓取概况:", "注意:", "⏱️ 承接时间线:"]
    while total_units() > max_units:
        removable_idx = next(
            (idx for idx in range(len(adjusted) - 1, -1, -1)
             if any(adjusted[idx]["text"].startswith(prefix) for prefix in removable_prefixes)),
            None,
        )
        if removable_idx is not None:
            adjusted.pop(removable_idx)
            continue
        break

    return adjusted


def _render_entries(text_frame, entries):
    text_frame.word_wrap = True
    text_frame.margin_left = 0
    text_frame.margin_right = 0
    text_frame.margin_top = 0
    text_frame.margin_bottom = 0
    for idx, entry in enumerate(entries):
        p = text_frame.paragraphs[0] if idx == 0 else text_frame.add_paragraph()
        p.text = entry["text"]
        p.font.size = Pt(entry.get("font_size", 13))
        p.font.bold = bool(entry.get("bold", False))
        p.space_after = Pt(entry.get("space_after", 6))
        color = entry.get("color")
        if color:
            p.font.color.rgb = RGBColor(*color)
        hyperlink = entry.get("hyperlink")
        if hyperlink and p.runs:
            p.runs[0].hyperlink.address = hyperlink


def _build_news_entries(news, extraction_stats, section_warnings, compact=False):
    meta_font = 12
    stat_font = 9
    warn_font = 10
    body_font = 13
    title_ref_limit = 22 if compact else 28
    reason_limit = 58 if compact else 95
    timeline_ref_limit = 1 if compact else 2
    entries = [
        _make_entry(
            f"📌 来源: {_get(news, 'source', '未知来源')}  |  🕒 {_get(news, 'date_check', '近期')}  |  🔥 热度: {'⭐' * int(_get(news, 'importance', 3) or 3)}",
            font_size=meta_font,
            color=(128, 128, 128),
            space_after=6,
        )
    ]

    event_id = _get(news, "event_id", "")
    if event_id:
        entries.append(_make_entry(f"🧷 事件ID: {event_id}", font_size=stat_font + 1, color=(100, 100, 100), space_after=5))

    if extraction_stats:
        entries.append(
            _make_entry(
                f"抓取概况: {_format_extraction_stats(extraction_stats)}",
                font_size=stat_font,
                color=(100, 100, 100),
                space_after=4,
            )
        )

    section_warnings = _ensure_list(section_warnings)
    if section_warnings:
        entries.append(
            _make_entry(
                f"注意: {section_warnings[0]}",
                font_size=warn_font,
                bold=True,
                color=(192, 102, 0),
                space_after=4,
            )
        )

    timeline_refs = _ensure_list(_get(news, "timeline_refs", []))
    for ref in timeline_refs[:timeline_ref_limit]:
        entries.append(
            _make_entry(
                f"⏱️ 承接时间线: [{_get(ref, 'date', '近期')}] {_shorten(_clean_display_text(_get(ref, 'event', '')), title_ref_limit)}",
                font_size=stat_font + 1,
                bold=True,
                color=(192, 102, 0),
                space_after=3,
            )
        )
        entries.append(
            _make_entry(
                f"原因: {_shorten(_clean_display_text(_get(ref, 'reason', '')), reason_limit)}",
                font_size=stat_font,
                color=(124, 45, 18),
                space_after=4,
            )
        )

    _append_summary_entries(
        entries,
        _get(news, "summary", "暂无详情"),
        body_font=body_font,
        space_after=6,
    )

    news_url = _get(news, "url", "")
    if news_url:
        entries.append(
            _make_entry(
                "🔗 溯源查证: 点击查看原文",
                font_size=11,
                color=(0, 112, 192),
                hyperlink=news_url,
            )
        )

    return entries


def _format_extraction_stats(stats):
    stats = stats or {}
    return (
        f"Jina全文 {int(stats.get('jina_count', 0) or 0)} | "
        f"网页直连 {int(stats.get('direct_html_count', 0) or 0)} | "
        f"摘要兜底 {int(stats.get('snippet_count', 0) or 0)}"
    )


def _resolve_report_title(data, timeline_data):
    scope_keys = {
        str(_get(section, "report_scope_key", "") or "").strip()
        for section in list(data or []) + list(timeline_data or [])
        if str(_get(section, "report_scope_key", "") or "").strip()
    }
    if len(scope_keys) == 1:
        only_key = next(iter(scope_keys))
        if only_key == "weekly_7d":
            return "《FPC-RD 科技周报》"
        if only_key == "monthly_30d":
            return "《FPC-RD 科技月度观察》"
    return "《FPC-RD 科技资讯》"



def clear_placeholders(slide):
    for shape in list(slide.shapes):
        if shape.is_placeholder:
            sp = shape.element
            sp.getparent().remove(sp)



def generate_ppt(data, timeline_data, filename, model_name):
    current_dir = Path(__file__).resolve().parent
    candidate_paths = [
        Path.cwd() / "template.pptx",
        current_dir.parent / "template.pptx",
    ]
    template_path = next((path for path in candidate_paths if path.exists()), None)
    if template_path and template_path.exists():
        try:
            prs = Presentation(template_path)
        except Exception:
            prs = Presentation()
    else:
        prs = Presentation()

    slide = prs.slides.add_slide(prs.slide_layouts[0])
    clear_placeholders(slide)
    title_box = slide.shapes.add_textbox(Inches(1), Inches(2), Inches(8), Inches(1))
    title_box.text_frame.paragraphs[0].text = _resolve_report_title(data, timeline_data)
    title_box.text_frame.paragraphs[0].font.size = Pt(32)
    title_box.text_frame.paragraphs[0].font.bold = True
    title_box.text_frame.paragraphs[0].alignment = PP_ALIGN.CENTER

    subtitle_box = slide.shapes.add_textbox(Inches(1), Inches(3.5), Inches(8), Inches(1))
    subtitle_box.text_frame.paragraphs[0].text = f"生成日期: {datetime.date.today()}"
    subtitle_box.text_frame.paragraphs[0].font.size = Pt(16)
    subtitle_box.text_frame.paragraphs[0].alignment = PP_ALIGN.CENTER

    if timeline_data:
        for t_data in timeline_data:
            events = _ensure_list(_get(t_data, "events", []))
            if not events:
                continue

            chunk_size = TIMELINE_CHUNK_SIZE
            for i in range(0, len(events), chunk_size):
                chunk = events[i:i + chunk_size]
                slide = prs.slides.add_slide(prs.slide_layouts[1] if len(prs.slide_layouts) > 1 else prs.slide_layouts[0])
                clear_placeholders(slide)

                title_box = slide.shapes.add_textbox(Inches(0.5), Inches(0.55), Inches(12.2), Inches(0.8))
                title_box.text_frame.paragraphs[0].text = f"⏱️ {_get(t_data, 'topic', '未命名专题')} - 核心时间线"
                title_box.text_frame.paragraphs[0].font.size = Pt(24)
                title_box.text_frame.paragraphs[0].font.bold = True

                meta_parts = []
                focus_tags = _ensure_list(_get(t_data, "focus_tags", []))
                if focus_tags:
                    meta_parts.append(f"重点标签: {'、'.join(focus_tags[:6])}")
                extraction_stats = _get(t_data, "extraction_stats", {})
                if extraction_stats:
                    meta_parts.append(_format_extraction_stats(extraction_stats))
                if meta_parts:
                    meta_box = slide.shapes.add_textbox(Inches(0.5), Inches(1.0), Inches(12.2), Inches(0.35))
                    meta_p = meta_box.text_frame.paragraphs[0]
                    meta_p.text = " | ".join(meta_parts)
                    meta_p.font.size = Pt(10)
                    meta_p.font.color.rgb = RGBColor(100, 100, 100)

                body_box = slide.shapes.add_textbox(Inches(0.5), Inches(1.45), Inches(12.2), Inches(5.45))
                tf = body_box.text_frame
                tf.word_wrap = True
                tf.margin_left = 0
                tf.margin_right = 0
                for idx, item in enumerate(chunk):
                    p = tf.add_paragraph() if idx > 0 else tf.paragraphs[0]
                    appears_later = bool(_get(item, "appears_in_later_news", False))
                    history_status = _get(item, "history_status", "")
                    prefix = "★ " if appears_later else ""
                    if history_status == "followup":
                        prefix = "◆ " + prefix
                    display_event = _shorten(_clean_display_text(_get(item, "event", "未命名事件")), 42)
                    display_source = _shorten(_clean_display_text(_get(item, "source", "未知来源")), 18)
                    p.text = f"{prefix}[{_get(item, 'date', '近期')}] {display_event} ({display_source})"
                    p.font.size = Pt(14)
                    p.space_after = Pt(4)
                    if appears_later:
                        p.font.bold = True
                        p.font.color.rgb = RGBColor(192, 102, 0)
                    elif history_status == "followup":
                        p.font.bold = True
                        p.font.color.rgb = RGBColor(15, 118, 110)

                    if history_status == "followup":
                        p_hist = tf.add_paragraph()
                        p_hist.text = (
                            f"  ↳ 历史追踪: 首次记录 {_get(item, 'first_seen', '未知')} / "
                            f"累计 {int(_get(item, 'seen_count', 1) or 1)} 次"
                        )
                        p_hist.font.size = Pt(10)
                        p_hist.font.color.rgb = RGBColor(15, 118, 110)
                        p_hist.space_after = Pt(5)

                    if appears_later:
                        p_link = tf.add_paragraph()
                        matched_title = _shorten(_clean_display_text(_get(item, "matched_news_title", "")), 34)
                        p_link.text = f"  ↳ 后文承接：{matched_title or '该事件已在深度新闻中展开'}"
                        p_link.font.size = Pt(10)
                        p_link.font.color.rgb = RGBColor(124, 45, 18)
                        p_link.space_after = Pt(6)

    for section in data:
        news_items = _ensure_list(_get(section, "data", []))
        if not news_items:
            continue

        finance = _get(section, "finance", {}) or {}
        section_warnings = _ensure_list(_get(section, "warnings", []))
        extraction_stats = _get(section, "extraction_stats", {})
        focus_tags = _ensure_list(_get(section, "focus_tags", []))
        summary_title = str(_get(section, "topic_summary_title", "") or "").strip()
        overall_insight = str(_get(section, "overall_insight", "") or "").strip()

        if summary_title and overall_insight:
            summary_slide = prs.slides.add_slide(prs.slide_layouts[1] if len(prs.slide_layouts) > 1 else prs.slide_layouts[0])
            clear_placeholders(summary_slide)

            title_box = summary_slide.shapes.add_textbox(Inches(0.45), Inches(0.52), Inches(12.35), Inches(0.82))
            title_box.text_frame.paragraphs[0].text = f"🧭 {_get(section, 'topic', '未命名专题')} - {summary_title}"
            title_box.text_frame.paragraphs[0].font.size = Pt(22)
            title_box.text_frame.paragraphs[0].font.bold = True

            meta_parts = []
            report_window_label = str(_get(section, "report_window_label", "") or "").strip()
            if report_window_label:
                meta_parts.append(report_window_label)
            if focus_tags:
                meta_parts.append(f"重点标签: {'、'.join(focus_tags[:6])}")
            if extraction_stats:
                meta_parts.append(_format_extraction_stats(extraction_stats))
            if meta_parts:
                meta_box = summary_slide.shapes.add_textbox(Inches(0.45), Inches(1.05), Inches(12.35), Inches(0.3))
                meta_p = meta_box.text_frame.paragraphs[0]
                meta_p.text = " | ".join(meta_parts)
                meta_p.font.size = Pt(9.5)
                meta_p.font.color.rgb = RGBColor(100, 100, 100)

            summary_entries = []
            _append_summary_entries(summary_entries, overall_insight, body_font=15, space_after=8)
            fitted_summary = _fit_entries_to_single_page(summary_entries, max_units=22, chars_per_line=48)
            body_box = summary_slide.shapes.add_textbox(Inches(0.45), Inches(1.55), Inches(12.1), Inches(4.7))
            _render_entries(body_box.text_frame, fitted_summary)

        if finance.get("is_public"):
            finance_slide = prs.slides.add_slide(prs.slide_layouts[1] if len(prs.slide_layouts) > 1 else prs.slide_layouts[0])
            clear_placeholders(finance_slide)

            title_box = finance_slide.shapes.add_textbox(Inches(0.5), Inches(0.4), Inches(12.2), Inches(0.8))
            title_box.text_frame.paragraphs[0].text = f"📊 {_get(section, 'topic', '未命名专题')} ({finance.get('ticker', '')}) - 量化面与事件催化"
            title_box.text_frame.paragraphs[0].font.size = Pt(22)
            title_box.text_frame.paragraphs[0].font.bold = True

            if focus_tags or extraction_stats:
                meta_box = finance_slide.shapes.add_textbox(Inches(0.5), Inches(0.9), Inches(12.2), Inches(0.3))
                meta_p = meta_box.text_frame.paragraphs[0]
                meta_parts = []
                if focus_tags:
                    meta_parts.append(f"重点标签: {'、'.join(focus_tags[:6])}")
                if extraction_stats:
                    meta_parts.append(_format_extraction_stats(extraction_stats))
                meta_p.text = " | ".join(meta_parts)
                meta_p.font.size = Pt(9)
                meta_p.font.color.rgb = RGBColor(100, 100, 100)

            body_box = finance_slide.shapes.add_textbox(Inches(0.5), Inches(1.2), Inches(3.2), Inches(3.35))
            tf = body_box.text_frame
            tf.margin_left = 0
            tf.margin_right = 0
            tf.margin_top = 0
            tf.margin_bottom = 0

            data_available = finance.get("data_available", True)
            if not data_available:
                msg = finance.get("msg", "Financial data temporarily unavailable.")
                p_msg = tf.paragraphs[0]
                p_msg.text = msg
                p_msg.font.size = Pt(14)
                p_msg.font.color.rgb = RGBColor(128, 128, 128)
            else:
                change_pct_raw = finance.get("change_pct")
                change_pct = _to_float(change_pct_raw)
                if change_pct is None:
                    trend_icon = "⏺"
                    color = RGBColor(90, 90, 90)
                    change_pct_text = "N/A"
                elif change_pct > 0:
                    trend_icon = "🔺"
                    color = RGBColor(192, 0, 0)
                    change_pct_text = f"{change_pct:.2f}"
                elif change_pct < 0:
                    trend_icon = "🔻"
                    color = RGBColor(0, 150, 0)
                    change_pct_text = f"{change_pct:.2f}"
                else:
                    trend_icon = "⏺"
                    color = RGBColor(90, 90, 90)
                    change_pct_text = "0.00"

                current_price = _fmt_number(finance.get("current_price"))
                currency = finance.get("currency", "")
                p_price = tf.paragraphs[0]
                p_price.text = f"{current_price} {currency}  {trend_icon} {change_pct_text}%"
                p_price.font.size = Pt(22)
                p_price.font.bold = True
                p_price.font.color.rgb = color

                metrics = [
                    f"▪ 估值水平 / 风险溢价: {finance.get('pe_pb', 'N/A')} | {finance.get('erp', 'N/A')}",
                    f"▪ 总市值: {finance.get('market_cap', 'N/A')}",
                    f"▪ 成交量 / 10日均量: {finance.get('volume', 'N/A')} | {finance.get('avg_volume_10d', 'N/A')}",
                    f"▪ 成交额: {finance.get('turnover_value', 'N/A')}",
                    f"▪ 分析师评级: {finance.get('analyst_rating_summary', 'N/A')}",
                ]
                for metric in metrics:
                    p = tf.add_paragraph()
                    p.text = metric
                    p.font.size = Pt(10)
                    p.space_before = Pt(4)
                    p.space_after = Pt(2)

                chart_path = finance.get("chart_path")
                if chart_path and os.path.exists(chart_path):
                    finance_slide.shapes.add_picture(
                        chart_path,
                        Inches(FINANCE_CHART_LEFT),
                        Inches(FINANCE_CHART_TOP),
                        width=Inches(FINANCE_CHART_WIDTH),
                    )

            catalysts = finance.get("catalysts", {})
            boxes_data = [
                ("🏛️ 政策与监管", catalysts.get("policy", "近期无重大政策催化")),
                ("💰 财报与盈利", catalysts.get("earnings", "未见核心财报数据")),
                ("🚀 产业标志事件", catalysts.get("landmark", "产业层级平稳")),
                ("🔄 市场风格轮动", catalysts.get("style", "风格未见明显切换")),
            ]

            box_positions = [
                (0.5, 4.75),
                (6.45, 4.75),
                (0.5, 5.6),
                (6.45, 5.6),
            ]
            for i, (title, content) in enumerate(boxes_data):
                x_pos, y_pos = box_positions[i]
                content_box = finance_slide.shapes.add_textbox(Inches(x_pos), Inches(y_pos), Inches(5.75), Inches(0.72))
                content_tf = content_box.text_frame
                content_tf.word_wrap = True
                content_tf.margin_left = 0
                content_tf.margin_right = 0
                content_tf.margin_top = 0
                content_tf.margin_bottom = 0
                p_title = content_tf.paragraphs[0]
                p_title.text = title
                p_title.font.size = Pt(10)
                p_title.font.bold = True
                p_title.font.color.rgb = RGBColor(0, 51, 102)
                p_content = content_tf.add_paragraph()
                p_content.text = _shorten(content, 92)
                p_content.font.size = Pt(8.5)
                p_content.space_before = Pt(2)

            analyst_firm_views = _ensure_list(finance.get("analyst_firm_views", []))
            analyst_price_targets = finance.get("analyst_price_targets", "N/A")
            analyst_segments = []
            if analyst_price_targets and analyst_price_targets != "N/A":
                analyst_segments.append(f"目标价: {analyst_price_targets}")
            if analyst_firm_views:
                analyst_segments.append(f"大行观点: {_shorten('；'.join(analyst_firm_views[:3]), 150)}")
            if analyst_segments:
                analyst_box = finance_slide.shapes.add_textbox(Inches(0.5), Inches(6.42), Inches(12.2), Inches(0.32))
                analyst_tf = analyst_box.text_frame
                analyst_tf.word_wrap = True
                analyst_tf.margin_left = 0
                analyst_tf.margin_right = 0
                analyst_tf.margin_top = 0
                analyst_tf.margin_bottom = 0
                analyst_title = analyst_tf.paragraphs[0]
                analyst_title.text = "🏦 分析师观点"
                analyst_title.font.size = Pt(9.5)
                analyst_title.font.bold = True
                analyst_title.font.color.rgb = RGBColor(0, 51, 102)
                analyst_body = analyst_tf.add_paragraph()
                analyst_body.text = " | ".join(analyst_segments)
                analyst_body.font.size = Pt(8.5)
                analyst_body.space_before = Pt(2)

            footer_parts = []
            if extraction_stats:
                footer_parts.append(f"抓取概况: {_format_extraction_stats(extraction_stats)}")
            if section_warnings:
                footer_parts.append(f"注意: {_shorten(section_warnings[0], 90)}")
            if footer_parts:
                footer_box = finance_slide.shapes.add_textbox(Inches(0.5), Inches(6.88), Inches(12.2), Inches(0.24))
                footer_tf = footer_box.text_frame
                footer_tf.margin_left = 0
                footer_tf.margin_right = 0
                footer_tf.margin_top = 0
                footer_tf.margin_bottom = 0
                footer_p = footer_tf.paragraphs[0]
                footer_p.text = " | ".join(footer_parts)
                footer_p.font.size = Pt(8)
                footer_p.font.color.rgb = RGBColor(128, 128, 128)

        for news in news_items:
            entries = _build_news_entries(news, extraction_stats, section_warnings, compact=False)
            fitted_entries = _fit_entries_to_single_page(entries, max_units=36, chars_per_line=52)

            slide = prs.slides.add_slide(prs.slide_layouts[1] if len(prs.slide_layouts) > 1 else prs.slide_layouts[0])
            clear_placeholders(slide)

            title_box = slide.shapes.add_textbox(Inches(0.45), Inches(0.52), Inches(12.35), Inches(0.82))
            title_text = _shorten(_get(news, "title", "未命名情报"), 60)
            title_box.text_frame.paragraphs[0].text = title_text
            title_box.text_frame.paragraphs[0].font.size = Pt(22)
            title_box.text_frame.paragraphs[0].font.bold = True

            body_box = slide.shapes.add_textbox(Inches(0.45), Inches(1.3), Inches(12.35), Inches(5.95))
            _render_entries(body_box.text_frame, fitted_entries)

    path = f"{filename}.pptx"
    prs.save(path)
    return path
