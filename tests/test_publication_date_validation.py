import datetime
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.search_engine import (  # noqa: E402
    audit_recent_news_results,
    extract_result_datetime,
    resolve_result_publication_datetime,
)


NOW = datetime.datetime(2026, 8, 24, 12, 0, tzinfo=datetime.timezone.utc)


def _result(url, published="2026-08-24T08:00:00Z", raw_content="", content="公司宣布产品更新。"):
    return {
        "title": "公司发布新产品",
        "url": url,
        "content": content,
        "snippet": content,
        "raw_content": raw_content,
        "provider_published_date": published,
        "published_date": published,
    }


def test_old_url_date_overrides_incorrect_recent_provider_timestamp():
    row = _result("https://example.com/2024/05/01/recycled-story")
    parsed, source_key, details = resolve_result_publication_datetime(row)
    assert parsed.date() == datetime.date(2024, 5, 1)
    assert source_key == "url_path_date"
    assert details["confidence"] == "corroborated"
    assert details["conflict"] is True

    kept, stats, warnings = audit_recent_news_results([row], now=NOW, enabled=True)
    assert kept == []
    assert stats["dropped_stale_count"] == 1
    assert stats["date_conflict_count"] == 1
    assert stats["dropped_timestamp_conflict_count"] == 1
    assert warnings


def test_jsonld_publication_date_is_preferred_and_kept_when_recent():
    row = _result(
        "https://example.com/news/product",
        published="2026-08-24T08:00:00Z",
        raw_content=(
            '<script type="application/ld+json">'
            '{"@type":"NewsArticle","datePublished":"2026-08-23T18:30:00+00:00"}'
            "</script>"
        ),
    )
    kept, stats, _ = audit_recent_news_results([row], now=NOW, enabled=True)
    assert len(kept) == 1
    assert kept[0]["publication_date_confidence"] == "verified_page"
    assert "jsonld_datePublished" in kept[0]["published_at_source_key"]
    assert stats["provider_timestamp_only_count"] == 0


def test_live_page_date_check_rejects_republished_old_article():
    row = _result("https://unknown.example/story")

    def fake_page_date_fetcher(url):
        assert url == row["url"]
        return {
            "published_at": "2025-12-01T10:00:00Z",
            "source_key": "fetched_page:meta:article:published_time",
        }

    kept, stats, warnings = audit_recent_news_results(
        [row],
        now=NOW,
        enabled=True,
        verify_page_dates=True,
        max_page_checks=1,
        page_date_fetcher=fake_page_date_fetcher,
    )
    assert kept == []
    assert stats["page_date_checked_count"] == 1
    assert stats["page_date_verified_count"] == 1
    assert stats["date_conflict_count"] == 1
    assert stats["dropped_timestamp_conflict_count"] == 1
    assert any("发布时间复核" in warning for warning in warnings)


def test_missing_and_future_dates_are_rejected():
    missing = _result("https://example.com/no-date", published="")
    future = _result("https://example.com/future", published="2026-08-25T12:01:00Z")
    kept, stats, _ = audit_recent_news_results([missing, future], now=NOW, enabled=True)
    assert kept == []
    assert stats["dropped_missing_timestamp_count"] == 1
    assert stats["dropped_future_count"] == 1


def test_unlabeled_historical_date_in_story_body_does_not_override_publication():
    row = _result(
        "https://example.com/news/new-product",
        content="公司在2024年完成原型验证，并于本周宣布新产品开始交付。",
    )
    parsed, source_key = extract_result_datetime(row)
    assert parsed.date() == datetime.date(2026, 8, 24)
    assert source_key in {"published_date", "provider_published_date"}


if __name__ == "__main__":
    tests = [
        test_old_url_date_overrides_incorrect_recent_provider_timestamp,
        test_jsonld_publication_date_is_preferred_and_kept_when_recent,
        test_live_page_date_check_rejects_republished_old_article,
        test_missing_and_future_dates_are_rejected,
        test_unlabeled_historical_date_in_story_body_does_not_override_publication,
    ]
    for test in tests:
        test()
    print(f"publication date validation tests passed: {len(tests)}")
