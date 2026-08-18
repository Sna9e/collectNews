import datetime as dt
import json
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pwg_intelligence.collector import (  # noqa: E402
    RAW_RESULT_COLUMNS,
    collect_pwg_daily_scan,
    filter_pwg_raw_results,
    normalize_pwg_url,
)
from tools.pwg_query_packs import load_pwg_query_config  # noqa: E402


FIXED_NOW = dt.datetime(2026, 6, 9, 12, 0, 0, tzinfo=dt.timezone.utc)


def _relevance_terms():
    config = load_pwg_query_config()
    terms = []
    for payload in (config["keywords"].get("categories", {}) or {}).values():
        terms.extend(payload.get("terms", []) or [])
    return terms


def test_normalize_pwg_url_removes_tracking_and_fragments():
    url = normalize_pwg_url("HTTPS://Example.com:443/path/?utm_source=x&keep=1#section")
    assert url == "https://example.com/path?keep=1"


def test_filter_pwg_raw_results_dedupes_and_filters():
    fetched_at = FIXED_NOW.isoformat().replace("+00:00", "Z")
    raw_results = [
        {
            "query": "polymer optical waveguide automotive",
            "fetched_at": fetched_at,
            "search_provider": "exa",
            "item": {
                "title": "Supplier launches polymer optical waveguide for automotive camera link",
                "url": "https://good.example.com/news/pwg-camera?utm_source=news",
                "source": "good.example.com",
                "published_date": "2026-06-08T08:00:00Z",
                "snippet": "The product uses polymer optical waveguide and camera optical link packaging.",
                "search_provider": "exa",
            },
        },
        {
            "query": "polymer optical waveguide automotive",
            "fetched_at": fetched_at,
            "search_provider": "exa",
            "item": {
                "title": "Supplier launches polymer optical waveguide for automotive camera link",
                "url": "https://another.example.com/copy",
                "source": "another.example.com",
                "published_date": "2026-06-08T09:00:00Z",
                "snippet": "Duplicate title about polymer optical waveguide.",
            },
        },
        {
            "query": "polymer optical waveguide automotive",
            "fetched_at": fetched_at,
            "search_provider": "exa",
            "item": {
                "title": "Another PWG connector update",
                "url": "https://good.example.com/news/second",
                "source": "good.example.com",
                "published_date": "2026-06-08T10:00:00Z",
                "snippet": "MPO and PMT connector routing for polymer optical waveguide.",
            },
        },
        {
            "query": "polymer optical waveguide automotive",
            "fetched_at": fetched_at,
            "search_provider": "exa",
            "item": {
                "title": "Old polymer optical waveguide result",
                "url": "https://old.example.com/news/old",
                "source": "old.example.com",
                "published_date": "2026-05-01T08:00:00Z",
                "snippet": "Old polymer optical waveguide article.",
            },
        },
        {
            "query": "polymer optical waveguide automotive",
            "fetched_at": fetched_at,
            "search_provider": "exa",
            "item": {
                "title": "General smartphone discount roundup",
                "url": "https://irrelevant.example.com/deals",
                "source": "irrelevant.example.com",
                "published_date": "2026-06-08T08:00:00Z",
                "snippet": "A deal article with no optical interconnect substance.",
            },
        },
        {
            "query": "polymer optical waveguide automotive",
            "fetched_at": fetched_at,
            "search_provider": "exa",
            "item": {
                "title": "Missing timestamp polymer optical waveguide",
                "url": "https://missing-date.example.com/news",
                "source": "missing-date.example.com",
                "snippet": "polymer optical waveguide",
            },
        },
    ]

    records, stats, dropped = filter_pwg_raw_results(
        raw_results,
        now=FIXED_NOW,
        lookback_days=7,
        relevance_terms=_relevance_terms(),
    )

    assert len(records) == 1
    assert records[0].url == "https://good.example.com/news/pwg-camera"
    assert stats["dropped_duplicate_title_count"] == 1
    assert stats["dropped_duplicate_domain_count"] == 1
    assert stats["dropped_time_window_count"] == 1
    assert stats["dropped_irrelevant_count"] == 1
    assert stats["dropped_missing_timestamp_count"] == 1
    assert dropped


def test_collect_pwg_daily_scan_dry_run_does_not_call_search():
    def failing_search(*args, **kwargs):
        raise AssertionError("dry-run must not call search")

    payload = collect_pwg_daily_scan(
        max_queries=3,
        dry_run=True,
        now=FIXED_NOW,
        search_fn=failing_search,
    )

    assert payload["dry_run"] is True
    assert payload["mode"] == "daily_scan"
    assert payload["query_count"] == 3
    assert len(payload["queries"]) == 3


def test_collect_pwg_daily_scan_writes_json_and_xlsx_outputs():
    calls = []

    def fake_search(query, sites_text, timelimit, max_results=8, tavily_key="", provider="hybrid", exa_key="", exa_settings=None):
        calls.append((query, timelimit, provider))
        return [
            {
                "title": f"{query} supplier update",
                "url": f"https://source{len(calls)}.example.com/pwg?utm_campaign=test",
                "source": f"source{len(calls)}.example.com",
                "published_date": "2026-06-08T08:00:00Z",
                "snippet": "polymer optical waveguide and optical circuit board product signal",
                "search_provider": "exa",
            }
        ]

    with tempfile.TemporaryDirectory() as tmpdir:
        payload = collect_pwg_daily_scan(
            max_queries=2,
            results_per_query=3,
            provider="exa",
            exa_key="fake",
            output_dir=tmpdir,
            workbook_path=Path(tmpdir) / "pwg_intelligence.xlsx",
            now=FIXED_NOW,
            search_fn=fake_search,
        )

        assert len(calls) == 2
        assert all(call[1] == "w" for call in calls)
        assert payload["lookback_days"] == 7
        assert payload["raw_result_count"] == 2
        assert payload["kept_count"] == 2
        assert payload["classified_count"] == 2
        assert payload["rule_coverage"]["scoring_rule_coverage"] == 1
        assert Path(payload["output_workbook"]).exists()

        json_path = Path(payload["output_json"])
        xlsx_path = Path(payload["output_xlsx"])
        assert json_path.name == "daily_scan_2026-06-09.json"
        assert xlsx_path.name == "daily_scan_2026-06-09.xlsx"
        assert json_path.exists()
        assert xlsx_path.exists()

        data = json.loads(json_path.read_text(encoding="utf-8"))
        assert data["records"]
        for column in RAW_RESULT_COLUMNS:
            assert column in data["records"][0]

        with zipfile.ZipFile(xlsx_path) as archive:
            shared_strings = archive.read("xl/sharedStrings.xml").decode("utf-8")
        assert "raw_results" not in shared_strings
        assert "polymer optical waveguide" in shared_strings
        for column in RAW_RESULT_COLUMNS:
            assert column in shared_strings


def run_all():
    tests = [
        test_normalize_pwg_url_removes_tracking_and_fragments,
        test_filter_pwg_raw_results_dedupes_and_filters,
        test_collect_pwg_daily_scan_dry_run_does_not_call_search,
        test_collect_pwg_daily_scan_writes_json_and_xlsx_outputs,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")


if __name__ == "__main__":
    run_all()
