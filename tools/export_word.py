from docx import Document
from docx.shared import RGBColor, Pt
from docx.oxml.ns import qn
from docx.enum.text import WD_ALIGN_PARAGRAPH
import datetime

def generate_word(data, timeline_data, filename, model_name):
    doc = Document()
    normal_style = doc.styles['Normal']
    normal_style.font.name = '微软雅黑'
    normal_style._element.rPr.rFonts.set(qn('w:eastAsia'), '微软雅黑')
    normal_style.font.size = Pt(10.5) 
    
    for i in range(1, 4):
        h_style = doc.styles[f'Heading {i}']
        h_style.font.name = '微软雅黑'
        h_style._element.rPr.rFonts.set(qn('w:eastAsia'), '微软雅黑')
        if i == 1: h_style.font.color.rgb = RGBColor(0, 51, 102)

    title = doc.add_heading("DeepSeek 企业级深度科技研报", 0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    meta_p = doc.add_paragraph()
    meta_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    meta_run = meta_p.add_run(f"生成日期: {datetime.date.today()}  |  数据来源: Tavily 商业资讯引擎  |  分析模型: {model_name}")
    meta_run.font.color.rgb = RGBColor(128, 128, 128)
    meta_run.font.size = Pt(9)
    doc.add_paragraph("━" * 50).alignment = WD_ALIGN_PARAGRAPH.CENTER

    # 🌟 插入高管最爱：时间线总览
    if timeline_data:
        doc.add_heading("⏱️ 卷首语：核心大事件时间线", level=1)
        for t_data in timeline_data:
            doc.add_heading(f"专题: {t_data['topic']}", level=2)
            if not t_data['events']:
                doc.add_paragraph("暂无有效时间线。").font.italic = True
                continue
            for item in t_data['events']:
                p = doc.add_paragraph(style='List Bullet')
                p.add_run(f"[{item.date}] ").bold = True
                p.add_run(f"{item.event} ")
                r_source = p.add_run(f"({item.source})")
                r_source.font.color.rgb = RGBColor(128, 128, 128)
        doc.add_paragraph("━" * 50).alignment = WD_ALIGN_PARAGRAPH.CENTER

    # 插入深度研报正文
    for section in data:
        doc.add_heading(f"🔷 深度研报：{section['topic']}", level=1)
        if not section['data']:
            doc.add_paragraph("    在指定时间范围内，未发现符合标准的重大情报。").font.italic = True
            continue
            
        for news in section['data']:
            doc.add_heading(f"🔹 {news.title}", level=2)
            p_info = doc.add_paragraph()
            run_info = p_info.add_run(f"    📌 来源: {news.source}    |    🕒 时间: {news.date_check}    |    🔥 热度: {'⭐'*news.importance}")
            run_info.font.color.rgb = RGBColor(100, 100, 100)
            run_info.font.bold = True
            
            p_summary = doc.add_paragraph(news.summary)
            p_summary.paragraph_format.line_spacing = 1.5 
            p_summary.paragraph_format.first_line_indent = Pt(21) 
            
            divider = doc.add_paragraph("┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈")
            divider.alignment = WD_ALIGN_PARAGRAPH.CENTER
            divider.runs[0].font.color.rgb = RGBColor(200, 200, 200)
    
    path = f"{filename}.docx"
    doc.save(path)
    return path
