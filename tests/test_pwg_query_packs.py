import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.pwg_query_packs import (  # noqa: E402
    CONFIG_DIR,
    build_pwg_example_queries,
    build_pwg_query_pack,
    get_supported_pwg_query_modes,
    load_pwg_query_config,
)


REQUIRED_MODES = {
    "daily_scan",
    "weekly_deep_scan",
    "company_watch",
    "standard_watch",
    "patent_watch",
    "paper_watch",
}


def _all_keyword_terms(config):
    terms = []
    for payload in (config["keywords"].get("categories", {}) or {}).values():
        terms.extend(payload.get("terms", []) or [])
    return set(terms)


def _company_names(config):
    names = []
    for group in (config["companies"].get("company_groups", {}) or {}).values():
        for company in group.get("companies", []) or []:
            names.append(company.get("name", ""))
    return set(names)


def _application_names(config):
    return {scene.get("name", "") for scene in config["application_map"].get("application_scenes", []) or []}


def test_pwg_yaml_configs_include_required_terms_companies_and_applications():
    config = load_pwg_query_config()
    terms = _all_keyword_terms(config)
    for required in (
        "polymer optical waveguide",
        "flexible polymer waveguide",
        "optical circuit board",
        "optical wiring board",
        "聚合物光波导",
        "柔性光波导",
        "光线路板",
        "ポリマー光導波路",
        "光配線板",
        "PMT connector",
        "MPO",
        "MT ferrule",
        "fiber array",
        "automotive optical harness",
        "IEEE 802.3cz",
        "OPEN Alliance TC7",
        "CPO",
        "OBO",
        "NPO",
        "optical RDL",
        "siloxane waveguide",
        "photocurable polymer",
        "mosquito method",
        "bending loss",
    ):
        assert required in terms

    names = _company_names(config)
    for required in (
        "Hakusan",
        "Sumitomo Bakelite",
        "Sumitomo Electric",
        "Yazaki",
        "Molex",
        "Amphenol",
        "TE Connectivity",
        "Aptiv",
        "Leoni",
        "Broadcom",
        "Marvell",
        "Zhongji Innolight",
        "Avary Holding",
        "JCET",
    ):
        assert required in names

    applications = _application_names(config)
    for required in (
        "车载ECU板边接口",
        "Camera输出链路",
        "Display链路",
        "车载光线束分支节点",
        "光模块内光路重排",
        "PMT/MPO/MT接口件",
        "45度微镜与90度转向",
        "CPO供光",
        "PIC到FA扇出",
        "optical RDL",
        "光电混合FPC",
    ):
        assert required in applications


def test_pwg_query_pack_supports_all_required_modes():
    assert set(get_supported_pwg_query_modes()) == REQUIRED_MODES
    for mode in sorted(REQUIRED_MODES):
        records = build_pwg_query_pack(mode, max_queries=12)
        assert records, mode
        assert len(records) <= 12
        for record in records:
            assert record.mode == mode
            assert record.query
            assert "{" not in record.query and "}" not in record.query
            assert record.language in {"zh", "en"}


def test_company_and_application_filters_are_applied():
    company_records = build_pwg_query_pack("company_watch", target_companies=["Hakusan"], max_queries=8)
    assert company_records
    assert all("Hakusan" in record.query or "白山" in record.query or "PMT" in record.query for record in company_records)

    application_records = build_pwg_query_pack(
        "daily_scan",
        application_scenes=["CPO供光"],
        max_queries=10,
    )
    assert application_records
    assert any("CPO供光" in record.query or "external laser source" in record.query or "CPO" in record.query for record in application_records)


def test_query_generation_is_config_driven():
    with tempfile.TemporaryDirectory() as tmpdir:
        temp_config = Path(tmpdir)
        shutil.copytree(CONFIG_DIR, temp_config, dirs_exist_ok=True)
        keywords_path = temp_config / "keywords.yaml"
        text = keywords_path.read_text(encoding="utf-8")
        text = text.replace("polymer optical waveguide", "config-only-polymer-waveguide")
        keywords_path.write_text(text, encoding="utf-8")

        records = build_pwg_query_pack("daily_scan", max_queries=6, config_dir=temp_config)
        assert any("config-only-polymer-waveguide" in record.query for record in records)


def test_example_queries_cover_all_modes():
    examples = build_pwg_example_queries(limit_per_mode=3)
    assert set(examples) == REQUIRED_MODES
    for mode, queries in examples.items():
        assert 1 <= len(queries) <= 3, mode
        assert all(query and "{" not in query for query in queries)


def run_all():
    tests = [
        test_pwg_yaml_configs_include_required_terms_companies_and_applications,
        test_pwg_query_pack_supports_all_required_modes,
        test_company_and_application_filters_are_applied,
        test_query_generation_is_config_driven,
        test_example_queries_cover_all_modes,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")


if __name__ == "__main__":
    run_all()
