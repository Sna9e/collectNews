import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import search_engine  # noqa: E402
from tools.source_blocklist import (  # noqa: E402
    domain_matches_rule,
    evaluate_search_result,
    filter_blocked_search_results,
    get_builtin_block_rules,
    normalize_domain_rule,
    parse_manual_blocklist,
)


def _result(domain, title="有效新闻", content="公司发布新产品并披露关键参数。"):
    return {
        "title": title,
        "url": f"https://{domain}/news/1",
        "source": domain,
        "content": content,
        "snippet": content,
        "published_date": "2026-08-17T08:00:00Z",
    }


def test_domain_normalization_and_subdomain_matching_are_safe():
    assert normalize_domain_rule("https://WWW.Spam.Example.com:443/news?id=1") == "spam.example.com"
    assert normalize_domain_rule("*.Example.com") == "example.com"
    assert normalize_domain_rule("not a domain") == ""
    assert domain_matches_rule("cdn.example.com", "example.com")
    assert not domain_matches_rule("notexample.com", "example.com")


def test_manual_parser_accepts_urls_and_reports_invalid_tokens():
    domains, invalid = parse_manual_blocklist(
        "spam.example.com\nhttps://robot.example.org/path\n*.spam.example.com\nnot-a-domain"
    )
    assert domains == ["spam.example.com", "robot.example.org"]
    assert invalid == ["not-a-domain"]


def test_builtin_and_manual_domain_rules_block_results():
    assert len(get_builtin_block_rules()) >= 20
    builtin_decision = evaluate_search_result(_result("sub.newsbreak.com"))
    assert builtin_decision["blocked"] is True
    assert builtin_decision["category"] == "automated_aggregator"

    manual_decision = evaluate_search_result(
        _result("feeds.robot.example"),
        manual_domains=["robot.example"],
    )
    assert manual_decision["blocked"] is True
    assert manual_decision["category"] == "manual_blocklist"

    similar_domain = evaluate_search_result(_result("notnewsbreak.com"))
    assert similar_domain["blocked"] is False


def test_automated_content_marker_blocks_unknown_domain():
    decision = evaluate_search_result(
        _result(
            "unknown.example.com",
            content="This article was automatically generated from an RSS feed and was not edited.",
        )
    )
    assert decision["blocked"] is True
    assert decision["category"] == "automated_content_marker"


def test_filter_preserves_order_and_returns_audit_decisions():
    rows = [
        _result("reuters.com", title="第一条"),
        _result("biztoc.com", title="聚合条目"),
        _result("manual.example.com", title="手动屏蔽"),
        _result("apple.com", title="第二条"),
    ]
    kept, blocked = filter_blocked_search_results(rows, manual_domains="manual.example.com")
    assert [item["title"] for item in kept] == ["第一条", "第二条"]
    assert {item["domain"] for item in blocked} == {"biztoc.com", "manual.example.com"}


def test_search_web_applies_policy_and_records_diagnostics():
    original = search_engine._search_web_exa

    def fake_exa(query, sites_text, timelimit, max_results=20, exa_key="", exa_settings=None):
        return [
            _result("reuters.com", title="保留"),
            _result("newsbreak.com", title="内置屏蔽"),
            _result("sub.manual.example", title="手动屏蔽"),
            _result(
                "generated.example.com",
                title="机器稿",
                content="本文由机器人自动生成，内容仅供参考。",
            ),
        ]

    search_engine._search_web_exa = fake_exa
    search_engine.reset_search_diagnostics()
    try:
        rows = search_engine.search_web(
            "test",
            "",
            "w",
            provider="exa",
            exa_key="fake",
            blocked_domains="manual.example",
        )
    finally:
        search_engine._search_web_exa = original

    assert [item["title"] for item in rows] == ["保留"]
    diagnostics = search_engine.get_search_diagnostics()["source_blocking"]
    assert diagnostics["blocked_count"] == 3
    assert diagnostics["by_domain"]["newsbreak.com"] == 1
    assert diagnostics["by_category"]["manual_blocklist"] == 1
    assert diagnostics["by_category"]["automated_content_marker"] == 1


def test_provider_payloads_receive_effective_exclusions():
    settings = {"_manual_blocked_domains": ["manual.example"]}
    payloads = search_engine._build_tavily_payloads(
        "test",
        ["reuters.com"],
        "w",
        5,
        "fake-tavily",
        settings,
    )
    for _, payload in payloads:
        assert "manual.example" in payload["exclude_domains"]
        assert "newsbreak.com" in payload["exclude_domains"]
        assert payload["include_domains"] == ["reuters.com"]

    captured = {}
    original_urlopen = search_engine.urllib.request.urlopen

    class FakeResponse:
        def read(self):
            return json.dumps({"results": [], "searchType": "auto"}).encode("utf-8")

    def fake_urlopen(request, timeout=0):
        captured.update(json.loads(request.data.decode("utf-8")))
        return FakeResponse()

    search_engine.urllib.request.urlopen = fake_urlopen
    try:
        search_engine._search_web_exa(
            "test",
            "",
            "w",
            exa_key="fake-exa",
            exa_settings=settings,
        )
    finally:
        search_engine.urllib.request.urlopen = original_urlopen

    assert "manual.example" in captured["excludeDomains"]
    assert "newsbreak.com" in captured["excludeDomains"]


def test_frontend_static_contract_covers_all_search_paths():
    source = (ROOT / "agent_app.py").read_text(encoding="utf-8")
    assert 'with st.expander("🛡️ 信息源屏蔽"' in source
    assert 'key="manual_blocked_domains_text"' in source
    assert source.count("blocked_domains=manual_blocked_domains") >= 7
    assert '"NEWS_BLOCKED_DOMAINS"' in (ROOT / "setup_api_keys.py").read_text(encoding="utf-8")


if __name__ == "__main__":
    tests = [
        test_domain_normalization_and_subdomain_matching_are_safe,
        test_manual_parser_accepts_urls_and_reports_invalid_tokens,
        test_builtin_and_manual_domain_rules_block_results,
        test_automated_content_marker_blocks_unknown_domain,
        test_filter_preserves_order_and_returns_audit_decisions,
        test_search_web_applies_policy_and_records_diagnostics,
        test_provider_payloads_receive_effective_exclusions,
        test_frontend_static_contract_covers_all_search_paths,
    ]
    for test in tests:
        test()
    print(f"source blocklist tests passed: {len(tests)}")
