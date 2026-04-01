import datetime
import os

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt

import tools.chart_generator as cg



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



def _shorten(text, limit=110):
    text = str(text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"



def _format_extraction_stats(stats):
    stats = stats or {}
    return (
        f"Jina全文 {int(stats.get('jina_count', 0) or 0)} | "
        f"网页直连 {int(stats.get('direct_html_count', 0) or 0)} | "
        f"摘要兜底 {int(stats.get('snippet_count', 0) or 0)}"
    )



def clear_placeholders(slide):
    for shape in list(slide.shapes):
        if shape.is_placeholder:
            sp = shape.element
            sp.getparent().remove(sp)



def generate_ppt(data, timeline_data, filename, model_name):
    template_path = "template.pptx"
    if os.path.exists(template_path):
        try:
            prs = Presentation(template_path)
        except Exception:
            prs = Presentation()
    else:
        prs = Presentation()

    slide = prs.slides.add_slide(prs.slide_layouts[0])
    clear_placeholders(slide)
    title_box = slide.shapes.add_textbox(Inches(1), Inches(2), Inches(8), Inches(1))
    title_box.text_frame.paragraphs[0].text = "高管战报：前沿情报深度分析"
    title_box.text_frame.paragraphs[0].font.size = Pt(32)
    title_box.text_frame.paragraphs[0].font.bold = True
    title_box.text_frame.paragraphs[0].alignment = PP_ALIGN.CENTER

    subtitle_box = slide.shapes.add_textbox(Inches(1), Inches(3.5), Inches(8), Inches(1))
    subtitle_box.text_frame.paragraphs[0].text = f"生成日期: {datetime.date.today()}"
    subtitle_box.text_frame.paragraphs[0].font.size = Pt(16)
    subtitle_box.text_frame.paragraphs[0].alignment = PP_ALIGN.CENTER

    if timeline_data:
        for t_data in timeline_data:
            events = _get(t_data, "events", [])
            if not events:
                continue

            chunk_size = 5
            for i in range(0, len(events), chunk_size):
                chunk = events[i:i + chunk_size]
                slide = prs.slides.add_slide(prs.slide_layouts[1] if len(prs.slide_layouts) > 1 else prs.slide_layouts[0])
                clear_placeholders(slide)

                title_box = slide.shapes.add_textbox(Inches(0.5), Inches(0.55), Inches(9), Inches(0.8))
                title_box.text_frame.paragraphs[0].text = f"⏱️ {_get(t_data, 'topic', '未命名专题')} - 核心时间线"
                title_box.text_frame.paragraphs[0].font.size = Pt(24)
                title_box.text_frame.paragraphs[0].font.bold = True

                meta_parts = []
                focus_tags = _get(t_data, "focus_tags", [])
                if focus_tags:
                    meta_parts.append(f"重点标签: {'、'.join(focus_tags[:6])}")
                extraction_stats = _get(t_data, "extraction_stats", {})
                if extraction_stats:
                    meta_parts.append(_format_extraction_stats(extraction_stats))
                if meta_parts:
                    meta_box = slide.shapes.add_textbox(Inches(0.5), Inches(1.0), Inches(9), Inches(0.35))
                    meta_p = meta_box.text_frame.paragraphs[0]
                    meta_p.text = " | ".join(meta_parts)
                    meta_p.font.size = Pt(10)
                    meta_p.font.color.rgb = RGBColor(100, 100, 100)

                body_box = slide.shapes.add_textbox(Inches(0.5), Inches(1.45), Inches(9), Inches(5.45))
                tf = body_box.text_frame
                tf.word_wrap = True
                for idx, item in enumerate(chunk):
                    p = tf.add_paragraph() if idx > 0 else tf.paragraphs[0]
                    appears_later = bool(_get(item, "appears_in_later_news", False))
                    history_status = _get(item, "history_status", "")
                    prefix = "★ " if appears_later else ""
                    if history_status == "followup":
                        prefix = "◆ " + prefix
                    p.text = f"{prefix}[{_get(item, 'date', '近期')}] {_get(item, 'event', '未命名事件')} ({_get(item, 'source', '未知来源')})"
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
                        p_reason = tf.add_paragraph()
                        p_reason.text = (
                            f"  ↳ 在《{_shorten(_get(item, 'matched_news_title', ''), 32)}》中展开："
                            f"{_shorten(_get(item, 'match_reason', ''), 90)}"
                        )
                        p_reason.font.size = Pt(10)
                        p_reason.font.color.rgb = RGBColor(124, 45, 18)
                        p_reason.space_after = Pt(8)

    for section in data:
        news_items = _get(section, "data", [])
        if not news_items:
            continue

        finance = _get(section, "finance", {}) or {}
        section_warnings = _get(section, "warnings", [])
        extraction_stats = _get(section, "extraction_stats", {})
        focus_tags = _get(section, "focus_tags", [])

        if finance.get("is_public"):
            finance_slide = prs.slides.add_slide(prs.slide_layouts[1] if len(prs.slide_layouts) > 1 else prs.slide_layouts[0])
            clear_placeholders(finance_slide)

            title_box = finance_slide.shapes.add_textbox(Inches(0.5), Inches(0.4), Inches(9), Inches(0.8))
            title_box.text_frame.paragraphs[0].text = f"📊 {_get(section, 'topic', '未命名专题')} ({finance.get('ticker', '')}) - 量化面与事件催化"
            title_box.text_frame.paragraphs[0].font.size = Pt(22)
            title_box.text_frame.paragraphs[0].font.bold = True

            if focus_tags or extraction_stats:
                meta_box = finance_slide.shapes.add_textbox(Inches(0.5), Inches(0.9), Inches(9), Inches(0.3))
                meta_p = meta_box.text_frame.paragraphs[0]
                meta_parts = []
                if focus_tags:
                    meta_parts.append(f"重点标签: {'、'.join(focus_tags[:6])}")
                if extraction_stats:
                    meta_parts.append(_format_extraction_stats(extraction_stats))
                meta_p.text = " | ".join(meta_parts)
                meta_p.font.size = Pt(9)
                meta_p.font.color.rgb = RGBColor(100, 100, 100)

            body_box = finance_slide.shapes.add_textbox(Inches(0.5), Inches(1.2), Inches(4.0), Inches(2.8))
            tf = body_box.text_frame

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
                p_price.font.size = Pt(24)
                p_price.font.bold = True
                p_price.font.color.rgb = color

                metrics = [
                    f"▪ 估值水平: {finance.get('pe_pb', 'N/A')}",
                    f"▪ 股权风险溢价: {finance.get('erp', 'N/A')}",
                    f"▪ 总市值: {finance.get('market_cap', 'N/A')}",
                ]
                for metric in metrics:
                    p = tf.add_paragraph()
                    p.text = metric
                    p.font.size = Pt(13)
                    p.space_before = Pt(12)

                chart_path = finance.get("chart_path")
                if chart_path and os.path.exists(chart_path):
                    finance_slide.shapes.add_picture(chart_path, Inches(4.5), Inches(1.2), width=Inches(5.0))

            catalysts = finance.get("catalysts", {})
            boxes_data = [
                ("🏛️ 政策与监管", catalysts.get("policy", "近期无重大政策催化")),
                ("💰 财报与盈利", catalysts.get("earnings", "未见核心财报数据")),
                ("🚀 产业标志事件", catalysts.get("landmark", "产业层级平稳")),
                ("🔄 市场风格轮动", catalysts.get("style", "风格未见明显切换")),
            ]

            for i, (title, content) in enumerate(boxes_data):
                x_pos = 0.5 + (i * 2.2)
                content_box = finance_slide.shapes.add_textbox(Inches(x_pos), Inches(4.5), Inches(2.1), Inches(2.5))
                content_tf = content_box.text_frame
                content_tf.word_wrap = True
                p_title = content_tf.paragraphs[0]
                p_title.text = title
                p_title.font.size = Pt(12)
                p_title.font.bold = True
                p_title.font.color.rgb = RGBColor(0, 51, 102)
                p_content = content_tf.add_paragraph()
                p_content.text = content
                p_content.font.size = Pt(11)
                p_content.space_before = Pt(6)

            if extraction_stats:
                stat_box = finance_slide.shapes.add_textbox(Inches(0.5), Inches(6.65), Inches(9.0), Inches(0.3))
                stat_p = stat_box.text_frame.paragraphs[0]
                stat_p.text = f"抓取概况: {_format_extraction_stats(extraction_stats)}"
                stat_p.font.size = Pt(9)
                stat_p.font.color.rgb = RGBColor(100, 100, 100)
            if section_warnings:
                warn_box = finance_slide.shapes.add_textbox(Inches(0.5), Inches(7.0), Inches(9.0), Inches(0.5))
                warn_p = warn_box.text_frame.paragraphs[0]
                warn_p.text = f"注意: {section_warnings[0]}"
                warn_p.font.size = Pt(10)
                warn_p.font.bold = True
                warn_p.font.color.rgb = RGBColor(192, 102, 0)

        for news in news_items:
            slide = prs.slides.add_slide(prs.slide_layouts[1] if len(prs.slide_layouts) > 1 else prs.slide_layouts[0])
            clear_placeholders(slide)

            title_box = slide.shapes.add_textbox(Inches(0.5), Inches(0.6), Inches(9), Inches(0.8))
            title_box.text_frame.paragraphs[0].text = _get(news, "title", "未命名情报")
            title_box.text_frame.paragraphs[0].font.size = Pt(22)
            title_box.text_frame.paragraphs[0].font.bold = True

            chart_info = _get(news, "chart_info", {})
            has_chart = bool(_get(chart_info, "has_chart", False) and len(_get(chart_info, "labels", [])) > 0)
            text_width = 5.2 if has_chart else 9.0

            body_box = slide.shapes.add_textbox(Inches(0.5), Inches(1.4), Inches(text_width), Inches(5.2))
            tf = body_box.text_frame
            tf.word_wrap = True

            meta = tf.paragraphs[0]
            meta.text = (
                f"📌 来源: {_get(news, 'source', '未知来源')}  |  "
                f"🕒 {_get(news, 'date_check', '近期')}  |  "
                f"🔥 热度: {'⭐' * int(_get(news, 'importance', 3) or 3)}"
            )
            meta.font.size = Pt(12)
            meta.font.color.rgb = RGBColor(128, 128, 128)
            meta.space_after = Pt(8)

            event_id = _get(news, "event_id", "")
            if event_id:
                p_event = tf.add_paragraph()
                p_event.text = f"🧷 事件ID: {event_id}"
                p_event.font.size = Pt(11)
                p_event.font.color.rgb = RGBColor(100, 100, 100)
                p_event.space_after = Pt(6)

            if extraction_stats:
                p_stat = tf.add_paragraph()
                p_stat.text = f"抓取概况: {_format_extraction_stats(extraction_stats)}"
                p_stat.font.size = Pt(9)
                p_stat.font.color.rgb = RGBColor(100, 100, 100)
                p_stat.space_after = Pt(6)

            if section_warnings:
                p_warn = tf.add_paragraph()
                p_warn.text = f"注意: {section_warnings[0]}"
                p_warn.font.size = Pt(10)
                p_warn.font.bold = True
                p_warn.font.color.rgb = RGBColor(192, 102, 0)
                p_warn.space_after = Pt(6)

            timeline_refs = _get(news, "timeline_refs", [])
            if timeline_refs:
                for ref in timeline_refs[:2]:
                    p_ref = tf.add_paragraph()
                    p_ref.text = f"⏱️ 承接时间线: [{_get(ref, 'date', '近期')}] {_shorten(_get(ref, 'event', ''), 32)}"
                    p_ref.font.size = Pt(11)
                    p_ref.font.bold = True
                    p_ref.font.color.rgb = RGBColor(192, 102, 0)
                    p_ref.space_after = Pt(3)

                    p_reason = tf.add_paragraph()
                    p_reason.text = f"原因: {_shorten(_get(ref, 'reason', ''), 95)}"
                    p_reason.font.size = Pt(10)
                    p_reason.font.color.rgb = RGBColor(124, 45, 18)
                    p_reason.space_after = Pt(6)

            for line in str(_get(news, "summary", "暂无详情")).split("\n"):
                line = line.strip()
                if not line:
                    continue
                p = tf.add_paragraph()
                p.text = line
                p.font.size = Pt(13)
                p.space_after = Pt(6)
                if line.startswith("【"):
                    p.font.bold = True
                    p.font.color.rgb = RGBColor(0, 51, 102)

            news_url = _get(news, "url", "")
            if news_url:
                p_link = tf.add_paragraph()
                p_link.text = "🔗 溯源查证: 点击查看原文"
                p_link.font.size = Pt(11)
                p_link.font.color.rgb = RGBColor(0, 112, 192)
                p_link.runs[0].hyperlink.address = news_url

            if has_chart:
                try:
                    chart_img = cg.generate_and_download_chart(
                        _get(chart_info, "chart_title", ""),
                        _get(chart_info, "labels", []),
                        _get(chart_info, "values", []),
                        _get(chart_info, "chart_type", "bar"),
                    )
                    if chart_img and os.path.exists(chart_img):
                        slide.shapes.add_picture(chart_img, Inches(5.8), Inches(1.5), width=Inches(3.8))
                except Exception:
                    pass

    path = f"{filename}.pptx"
    prs.save(path)
    return path
