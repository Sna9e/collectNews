import datetime as dt
import json
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pwg_intelligence.reporter import (  # noqa: E402
    build_daily_brief_markdown,
    build_weekly_opportunity_rows,
    build_weekly_review_markdown,
    load_recent_classified_rows,
    select_daily_rows,
    select_weekly_rows,
    write_daily_brief,
    write_weekly_review,
)


REPORT_DATE = dt.date(2026, 6, 9)
GENERATED_AT = dt.datetime(2026, 6, 9, 12, 0, 0, tzinfo=dt.timezone.utc)


def _row(
    title,
    category,
    score,
    source_level="A",
    maturity="M4",
    collected_at="2026-06-09T10:00:00Z",
    source_url=None,
    summary=None,
    needs_manual_review="false",
    demo_flag="",
):
    return {
        "card_id": title.replace(" ", "-")[:30],
        "published_date": collected_at[:10],
        "event_date": collected_at[:10],
        "collected_at": collected_at,
        "source_type": "official",
        "source_level": source_level,
        "source_name": "Molex",
        "title": title,
        "source_url": source_url or f"https://example.com/{title.replace(' ', '-').lower()}",
        "original_language": "en",
        "main_track": "产品",
        "application_scene": "车载光互连",
        "keywords": "polymer optical waveguide；PMT connector",
        "factual_summary": summary or f"{title} 披露了聚合物光波导相关样品、接口结构和应用方向，信息包含产品动作、应用场景和可验证来源。",
        "key_parameters": f"pwg_category={category}",
        "maturity_level": maturity,
        "evidence_strength": "high",
        "fpc_relevance": "与FPC端口保护、柔性载体、补强结构和可靠性验证直接相关。",
        "recommended_action": "联系来源方确认样品规格、可获得性和客户验证窗口。",
        "owner": "",
        "next_review_date": "2026-06-23",
        "demo_flag": demo_flag,
        "pwg_category": category,
        "opportunity_score": score,
        "scoring_reason": "客户痛点20/30，FPC能力匹配20/25，公开产品证据15/20，技术可实现性10/15，竞争可进入性8/10。",
        "needs_manual_review": needs_manual_review,
        "classification_reason": "命中测试规则。",
        "source_level_reason": "命中公司官网来源。",
        "maturity_reason": "命中样品或Datasheet信号。",
    }


def test_daily_brief_filters_dedupes_and_omits_empty_sections():
    rows = [
        _row("PMT connector sample", "connector", 82, maturity="M4"),
        _row(
            "Camera optical link validation",
            "automotive",
            66,
            maturity="M3",
            summary="车载Camera输出链路披露新的光互连验证信息，重点涉及域控连接、链路减重和车规可靠性观察点。",
        ),
        _row("Duplicate PMT connector sample", "connector", 80, source_url="https://example.com/duplicate-pmt"),
        _row("Duplicate PMT connector sample copy", "connector", 79, source_url="https://example.com/duplicate-pmt"),
        _row("Low score material update", "material_process", 30),
        _row("D level repost", "company_update", 90, source_level="D"),
        _row("Demo row", "connector", 90, demo_flag="DEMO"),
        _row("Banned summary", "connector", 90, summary="公开材料暂未披露更多细节。"),
    ]

    selected = select_daily_rows(rows, report_date=REPORT_DATE)
    assert len(selected) == 3

    markdown = build_daily_brief_markdown(rows, report_date=REPORT_DATE, generated_at=GENERATED_AT)
    assert "# PWG每日简报（2026-06-09）" in markdown
    assert "## 新产品与样品" in markdown
    assert "## 车载应用" in markdown
    assert "## 材料与工艺" not in markdown
    assert "事实摘要：" in markdown
    assert "原文链接：" in markdown
    assert "来源等级：" in markdown
    assert "产品成熟度：" in markdown
    assert "与FPC的关系：" in markdown
    assert "下一步动作：" in markdown
    assert "公开材料暂未披露更多细节" not in markdown
    assert "Demo row" not in markdown
    assert markdown.count("https://example.com/duplicate-pmt") == 1


def test_daily_brief_writes_expected_filename():
    rows = [_row("CPO optical engine sample", "cpo_datacenter", 78)]
    with tempfile.TemporaryDirectory() as tmpdir:
        output = write_daily_brief(rows, report_date=REPORT_DATE, output_dir=tmpdir, generated_at=GENERATED_AT)
        assert output.name == "PWG_daily_brief_2026-06-09.md"
        text = output.read_text(encoding="utf-8")
        assert "CPO optical engine sample" in text


def test_weekly_review_dedupes_limits_and_includes_required_sections():
    categories = ["company_update", "automotive", "cpo_datacenter", "connector", "material_process", "standard", "patent", "paper", "exhibition"]
    rows = []
    for index in range(25):
        category = categories[index % len(categories)]
        rows.append(
            _row(
                f"Weekly clue {index:02d}",
                category,
                95 - index,
                maturity="M4" if index % 3 else "M2",
                collected_at="2026-06-08T08:00:00Z",
            )
        )
    rows.append(dict(rows[0]))
    rows[-1]["title"] = "Duplicate URL should be removed"

    selected = select_weekly_rows(rows, end_date=REPORT_DATE)
    assert len(selected) == 20
    assert len({row["source_url"] for row in selected}) == 20

    markdown = build_weekly_review_markdown(rows, end_date=REPORT_DATE, generated_at=GENERATED_AT)
    assert "# PWG周报（2026-W24）" in markdown
    for section in (
        "本周新增硬证据",
        "竞品动作",
        "应用机会变化",
        "技术路线变化",
        "值得验证的样件",
        "需要联系的厂商、供应商或高校",
        "仍然缺少的证据",
    ):
        assert f"## {section}" in markdown
    assert "Weekly clue 00" in markdown
    assert "Weekly clue 24" not in markdown


def test_weekly_opportunity_rows_and_workbook_update():
    rows = [
        _row("Automotive optical harness sample", "automotive", 84, maturity="M4"),
        _row("CPO light supply routing", "cpo_datacenter", 76, maturity="M5"),
        _row("Low opportunity", "paper", 48, maturity="M1"),
    ]
    opportunities = build_weekly_opportunity_rows(rows, end_date=REPORT_DATE)
    assert len(opportunities) == 2
    assert opportunities[0]["opportunity_id"].startswith("PWG-OPP-2026-W24-")
    assert opportunities[0]["demo_flag"] == ""

    with tempfile.TemporaryDirectory() as tmpdir:
        result = write_weekly_review(
            rows,
            end_date=REPORT_DATE,
            output_dir=tmpdir,
            workbook_path=Path(tmpdir) / "pwg_intelligence.xlsx",
            generated_at=GENERATED_AT,
        )
        md_path = Path(result["output_markdown"])
        workbook_path = Path(result["output_workbook"])
        assert md_path.name == "PWG_weekly_review_2026-W24.md"
        assert md_path.exists()
        assert workbook_path.exists()
        assert result["opportunity_count"] == 2

        with zipfile.ZipFile(workbook_path) as archive:
            shared_strings = archive.read("xl/sharedStrings.xml").decode("utf-8")
        assert "Automotive optical harness sample" in shared_strings
        assert "CPO light supply routing" in shared_strings
        assert "PWG-OPP-2026-W24-001" in shared_strings


def test_load_recent_classified_rows_reads_week_window_json_files():
    with tempfile.TemporaryDirectory() as tmpdir:
        raw_dir = Path(tmpdir)
        recent_payload = {
            "generated_at": "2026-06-09T08:00:00Z",
            "classified_rows": [_row("Recent clue", "connector", 80)],
        }
        old_payload = {
            "generated_at": "2026-05-20T08:00:00Z",
            "classified_rows": [_row("Old clue", "connector", 80, collected_at="2026-05-20T08:00:00Z")],
        }
        (raw_dir / "daily_scan_2026-06-09.json").write_text(json.dumps(recent_payload, ensure_ascii=False), encoding="utf-8")
        (raw_dir / "daily_scan_2026-05-20.json").write_text(json.dumps(old_payload, ensure_ascii=False), encoding="utf-8")

        rows = load_recent_classified_rows(raw_dir, end_date=REPORT_DATE, days=7)
        assert len(rows) == 1
        assert rows[0]["title"] == "Recent clue"


def run_all():
    tests = [
        test_daily_brief_filters_dedupes_and_omits_empty_sections,
        test_daily_brief_writes_expected_filename,
        test_weekly_review_dedupes_limits_and_includes_required_sections,
        test_weekly_opportunity_rows_and_workbook_update,
        test_load_recent_classified_rows_reads_week_window_json_files,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")


if __name__ == "__main__":
    run_all()
