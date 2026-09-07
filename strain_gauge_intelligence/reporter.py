"""Markdown reporter for the strain gauge vertical module."""

from __future__ import annotations

import datetime as _dt
import re
from pathlib import Path

import yaml

from . import TECH_MODULES, TECH_MODULE_EN


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT_DIR = PROJECT_ROOT / "data" / "strain_gauge_intelligence" / "reports"
CONFIG_DIR = Path(__file__).resolve().parent / "config"
LOCAL_TZ = _dt.timezone(_dt.timedelta(hours=8))


def _load_report_rules():
    with (CONFIG_DIR / "report_rules.yaml").open("r", encoding="utf-8") as file_obj:
        return yaml.safe_load(file_obj) or {}


def _clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _md_link(label, url):
    clean_url = _clean(url)
    return f"[{label}]({clean_url})" if clean_url else label


def _item_dict(item):
    if hasattr(item, "model_dump"):
        return item.model_dump()
    return dict(item or {})


def _render_news_item(item, index):
    row = _item_dict(item)
    return "\n".join(
        [
            f"### {index}. {_clean(row.get('title'))}",
            f"- 日期：{_clean(row.get('date'))}",
            f"- 来源：{_clean(row.get('source_name'))}",
            f"- 链接：{_md_link('原文', row.get('source_url'))}",
            f"- 摘要：{_clean(row.get('summary'))}",
            f"- 与应变片/六轴力传感器的关系：{_clean(row.get('relation_to_sensor'))}",
        ]
    )


def _render_patent_item(item, index):
    row = _item_dict(item)
    return "\n".join(
        [
            f"### {index}. {_clean(row.get('title'))}",
            f"- 公开号/申请号：{_clean(row.get('publication_number'))}",
            f"- 申请人：{_clean(row.get('applicant'))}",
            f"- 公开日：{_clean(row.get('date'))}",
            f"- 国家/地区：{_clean(row.get('country_or_region'))}",
            f"- 链接：{_md_link('原文', row.get('source_url'))}",
            f"- 核心方案：{_clean(row.get('core_solution'))}",
            f"- 与FPC或应变片制程的关系：{_clean(row.get('fpc_implication'))}",
            f"- 可借鉴点：{_clean(row.get('reference_point'))}",
        ]
    )


def _render_paper_item(item, index):
    row = _item_dict(item)
    return "\n".join(
        [
            f"### {index}. {_clean(row.get('title'))}",
            f"- 作者/机构：{_clean(row.get('authors_or_institutions'))}",
            f"- 年份：{_clean(row.get('date'))}",
            f"- 期刊/会议：{_clean(row.get('venue'))}",
            f"- DOI/链接：{_md_link(_clean(row.get('doi_or_link')) or '原文', row.get('source_url') or row.get('doi_or_link'))}",
            f"- 研究对象：{_clean(row.get('research_object'))}",
            f"- 传感结构：{_clean(row.get('sensing_structure'))}",
            f"- 关键方法/指标：{_clean(row.get('key_methods_metrics'))}",
            f"- 工程化评价：{_clean(row.get('engineering_value'))}",
        ]
    )


def _render_technical_routes():
    rules = _load_report_rules()
    lines = []
    for item in rules.get("technical_routes", []) or []:
        lines.append(f"- **{_clean(item.get('route'))}**：{_clean(item.get('judgement'))}")
    return lines


def _top_conclusions(news, patents, papers, quantity_check):
    lines = []
    counts = quantity_check.get("counts", {})
    lines.append(
        f"本期共保留新闻/公司动态 {counts.get('news', len(news))} 条、专利 {counts.get('patent', len(patents))} 条、论文 {counts.get('paper', len(papers))} 条。"
    )
    if quantity_check.get("passed"):
        lines.append("数量校验已通过，三类信息均达到最低条数要求。")
    else:
        lines.append("数量校验未完全通过，已保留模块并在下方列出不足原因和检索窗口。")
    if patents:
        lines.append("专利侧重点集中在弹性体结构、电桥布线、解耦标定和机器人末端力控集成。")
    if papers:
        lines.append("论文侧重点集中在多轴力传感结构、柔性应变传感、标定矩阵和解耦算法。")
    if news:
        lines.append("公司动态侧重点用于判断力控传感器在人形机器人、协作机器人和灵巧手中的落地节奏。")
    return lines[:5]


def build_strain_gauge_markdown(payload):
    if hasattr(payload, "model_dump"):
        payload = payload.model_dump()
    payload = dict(payload or {})
    news = list(payload.get("news") or [])
    patents = list(payload.get("patents") or [])
    papers = list(payload.get("papers") or [])
    quantity_check = dict(payload.get("quantity_check") or {})
    generated_at = _clean(payload.get("generated_at")) or _dt.datetime.now(LOCAL_TZ).isoformat()
    searched_windows = payload.get("searched_windows") or {}
    warnings = list(payload.get("warnings") or [])

    lines = [
        f"# 专题模块：{TECH_MODULES[0]}",
        "",
        f"英文名称：{TECH_MODULE_EN}",
        f"生成时间：{generated_at}",
        "",
        "## 1. 本期结论",
        "",
    ]
    lines.extend(f"- {item}" for item in _top_conclusions(news, patents, papers, quantity_check))
    if warnings:
        lines.append(f"- 注意：{'；'.join(warnings)}")
    if searched_windows:
        lines.append(f"- 已检索窗口：{searched_windows}")
    lines.extend(["", "## 2. 新闻 / 公司动态", ""])
    if news:
        for index, item in enumerate(news, start=1):
            lines.extend([_render_news_item(item, index), ""])
    else:
        lines.append("在设定检索范围内，未筛选出足够高相关且可核实的新闻/公司动态。")
        lines.append("")

    lines.extend(["## 3. 专利动态", ""])
    if patents:
        for index, item in enumerate(patents, start=1):
            lines.extend([_render_patent_item(item, index), ""])
    else:
        lines.append("在设定检索范围内，未筛选出足够高相关且字段完整的专利动态。")
        lines.append("")

    lines.extend(["## 4. 论文 / 学术进展", ""])
    if papers:
        for index, item in enumerate(papers, start=1):
            lines.extend([_render_paper_item(item, index), ""])
    else:
        lines.append("在设定检索范围内，未筛选出足够高相关且字段完整的论文/学术进展。")
        lines.append("")

    lines.extend(["## 5. 技术路线判断", ""])
    lines.extend(_render_technical_routes())

    lines.extend(
        [
            "",
            "## 6. 对FPC研发的启示",
            "",
            "- 优先关注能把应变片、电桥走线、温度补偿和屏蔽接地集成到柔性线路中的方案。",
            "- 对十字梁、轮辐式、并联梁和 Stewart 平台结构，应进一步拆解弹性体贴片位置、桥路拓扑和线束出口。",
            "- 专利精读应优先覆盖电桥布线、温度补偿、弹性体结构、过载保护和 FPC 一体化封装。",
            "- 论文复现实验应优先选择公开了标定矩阵、解耦误差、灵敏度、温漂和重复性的工作。",
            "- 下一步建议：建立六轴力传感器样件清单，按结构路线拆解 FPC 可集成位置、贴片工艺窗口和标定治具需求。",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def write_strain_gauge_report(payload, output_dir=DEFAULT_REPORT_DIR, report_date=None):
    target = report_date
    if target is None:
        target = _dt.datetime.now(LOCAL_TZ).date()
    elif not isinstance(target, _dt.date):
        target = _dt.date.fromisoformat(str(target)[:10])
    output = Path(output_dir) / f"strain_gauge_force_sensor_report_{target.isoformat()}.md"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(build_strain_gauge_markdown(payload), encoding="utf-8")
    return output

