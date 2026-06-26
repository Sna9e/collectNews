import datetime as dt
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from strain_gauge_intelligence.collector import collect_strain_gauge_module, validate_module_counts  # noqa: E402
from strain_gauge_intelligence.reporter import build_strain_gauge_markdown  # noqa: E402
from tools.strain_gauge_query_packs import build_strain_gauge_query_pack, load_strain_gauge_query_config  # noqa: E402


NOW = dt.datetime(2026, 6, 22, 8, 0, tzinfo=dt.timezone.utc)


def _fake_search(query, sites_text, timelimit, max_results=20, tavily_key="", provider="exa", exa_key="", exa_settings=None):
    q = query.lower()
    if "patent" in q or "专利" in query:
        return [
            {
                "title": "CN118765432A 六维力传感器弹性体和应变片全桥布线结构",
                "url": "https://patents.google.com/patent/CN118765432A/en",
                "source_name": "Google Patents",
                "published_date": "2025-11-18",
                "content": "申请人 ATI Industrial Automation。方案在十字梁弹性体上布置 strain gauge full bridge，并通过 temperature compensation and decoupling matrix 降低六轴力串扰。",
            },
            {
                "title": "US20250123456A1 Robot wrist force torque sensor with Wheatstone bridge",
                "url": "https://patents.google.com/patent/US20250123456A1/en",
                "source_name": "Google Patents",
                "published_date": "2025-04-03",
                "content": "Applicant Kistler. The patent describes robot wrist force/torque sensor, Wheatstone bridge routing, overload protection and calibration matrix.",
            },
            {
                "title": "WO2024123456A1 Flexible printed circuit strain gauge for multi-axis force sensor",
                "url": "https://patentscope.wipo.int/search/en/detail.jsf?docId=WO2024123456",
                "source_name": "WIPO Patentscope",
                "published_date": "2024-06-20",
                "content": "Applicant Nissha. The invention integrates FPC strain gauge traces with multi-axis force sensor elastomer and temperature compensation.",
            },
        ]
    if "paper" in q or "论文" in query or "calibration matrix" in q:
        return [
            {
                "title": "Design and calibration of a six-axis force/torque sensor based on strain gauges",
                "url": "https://ieeexplore.ieee.org/document/10000001",
                "source_name": "IEEE Transactions on Instrumentation and Measurement",
                "published_date": "2025",
                "content": "2025 paper from a robotics laboratory. It studies six-axis force/torque sensor, cross beam elastomer, strain gauge bridge, calibration matrix and decoupling error.",
            },
            {
                "title": "Flexible strain sensor array for robotic tactile feedback and dexterous hand force control",
                "url": "https://www.mdpi.com/1424-8220/25/1/100",
                "source_name": "MDPI Sensors",
                "published_date": "2025",
                "content": "2025 Sensors paper. It reports flexible strain sensor, robotic tactile sensor, hysteresis test, repeatability and dexterous hand force feedback experiments.",
            },
            {
                "title": "Decoupling algorithm for spoke-type six-dimensional force sensor in robot end-effector",
                "url": "https://www.sciencedirect.com/science/article/pii/S026322412400001X",
                "source_name": "Measurement",
                "published_date": "2024",
                "content": "2024 Measurement paper with spoke-type force sensor, strain gauge full bridge, decoupling algorithm, calibration matrix and robot end-effector validation.",
            },
        ]
    return [
        {
            "title": "ATI updates robot wrist six-axis force/torque sensor line for force control",
            "url": "https://www.ati-ia.com/company/news/robot-wrist-force-torque-sensor-2026",
            "source_name": "ATI Industrial Automation",
            "published_date": "2026-06-10",
            "content": "ATI Industrial Automation introduced updates to robot wrist force/torque sensor products. The sensor uses strain gauge bridge measurement for cobot assembly, polishing and force feedback.",
        },
        {
            "title": "坤维科技发布面向人形机器人腕部的六维力传感器样品",
            "url": "https://www.example.com/kunwei-six-axis-force-sensor",
            "source_name": "机器人产业媒体",
            "published_date": "2026-06-12",
            "content": "坤维科技发布面向人形机器人腕部力控的六维力传感器样品，方案涉及应变片、电桥采集、弹性体结构和标定矩阵，目标应用包括灵巧手和末端执行器。",
        },
    ]


def test_query_config_contains_required_terms_and_modes():
    config = load_strain_gauge_query_config()
    zh_terms = config["keywords"]["keywords"]["chinese"]
    en_terms = config["keywords"]["keywords"]["english"]
    assert "应变片" in zh_terms
    assert "六轴力传感器" in zh_terms
    assert "strain gauge" in en_terms
    assert "six-axis force/torque sensor" in en_terms

    records = build_strain_gauge_query_pack(item_type="all", max_queries_per_type=3)
    assert {item.item_type for item in records} == {"news", "patent", "paper"}
    assert any("patent" in item.query.lower() or "专利" in item.query for item in records)
    assert any("paper" in item.query.lower() or "论文" in item.query for item in records)


def test_collect_strain_gauge_module_with_stub_outputs_required_counts():
    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir) / "raw"
        report_dir = Path(tmpdir) / "reports"
        payload = collect_strain_gauge_module(
            provider="exa",
            exa_key="stub",
            max_queries_per_type=3,
            results_per_query=5,
            output_dir=output_dir,
            report_dir=report_dir,
            now=NOW,
            search_fn=_fake_search,
            overwrite=True,
        )

        assert len(payload["news"]) >= 2
        assert len(payload["patents"]) >= 3
        assert len(payload["papers"]) >= 3
        assert payload["quantity_check"]["passed"] is True
        assert Path(payload["output_json"]).exists()
        assert Path(payload["output_xlsx"]).exists()
        assert Path(payload["output_markdown"]).exists()

        for item in payload["patents"]:
            assert item["publication_number"]
            assert item["applicant"]
            assert item["date"]
            assert item["core_solution"]
        for item in payload["papers"]:
            assert item["authors_or_institutions"]
            assert item["venue"]
            assert item["doi_or_link"]
            assert item["engineering_value"]
        for section in ("news", "patents", "papers"):
            for item in payload[section]:
                assert item["summary"]
                assert "需要进一步核实结构细节" not in item["summary"]
                assert "公开材料显示" not in item["summary"]
                assert "资料未提供足够细节" not in item["summary"]
        assert "introduced updates to robot wrist force/torque sensor products" not in payload["news"][0]["summary"]


def test_report_has_required_sections_and_no_banned_template_text():
    with tempfile.TemporaryDirectory() as tmpdir:
        payload = collect_strain_gauge_module(
            provider="exa",
            exa_key="stub",
            max_queries_per_type=2,
            results_per_query=5,
            output_dir=Path(tmpdir) / "raw",
            report_dir=Path(tmpdir) / "reports",
            now=NOW,
            search_fn=_fake_search,
            overwrite=True,
        )
        markdown = build_strain_gauge_markdown(payload)
        assert "专题模块：应变片与机器人六轴力传感器" in markdown
        assert "## 2. 新闻 / 公司动态" in markdown
        assert "## 3. 专利动态" in markdown
        assert "## 4. 论文 / 学术进展" in markdown
        assert "## 5. 技术路线判断" in markdown
        assert "## 6. 对FPC研发的启示" in markdown
        for banned in ("公开材料显示", "资料未提供足够细节", "暂不能确认更多参数", "仅记录已披露动作"):
            assert banned not in markdown
        assert "需要进一步核实结构细节" not in markdown
        assert "introduced updates to robot wrist force/torque sensor products" not in markdown


def test_quantity_validator_reports_shortage_without_silent_skip():
    result = validate_module_counts(news=[1], patents=[1, 2, 3], papers=[])
    assert result["passed"] is False
    assert result["shortages"]["news"]["actual"] == 1
    assert result["shortages"]["paper"]["required"] == 3


def run_all():
    tests = [
        test_query_config_contains_required_terms_and_modes,
        test_collect_strain_gauge_module_with_stub_outputs_required_counts,
        test_report_has_required_sections_and_no_banned_template_text,
        test_quantity_validator_reports_shortage_without_silent_skip,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")


if __name__ == "__main__":
    run_all()
