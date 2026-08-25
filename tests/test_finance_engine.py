import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import finance_engine  # noqa: E402


class FakeResponse:
    status_code = 200

    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


class InvalidAI:
    valid = False


class FailIfCalledAI:
    valid = True

    def analyze_structural(self, prompt, model):
        raise AssertionError("Known pending-listing companies must not use AI ticker guessing")


def _yahoo_payload(ticker="SPCX"):
    return {
        "chart": {
            "error": None,
            "result": [
                {
                    "meta": {
                        "symbol": ticker,
                        "currency": "USD",
                        "regularMarketPrice": 136.97,
                        "chartPreviousClose": 135.5,
                        "fiftyTwoWeekLow": 128.0,
                        "fiftyTwoWeekHigh": 151.0,
                    },
                    "timestamp": [1787097600, 1787184000, 1787270400, 1787356800],
                    "indicators": {
                        "quote": [
                            {
                                "open": [132.0, 134.0, 135.0, 136.0],
                                "high": [135.0, 136.0, 138.0, 139.0],
                                "low": [131.0, 133.0, 134.5, 135.2],
                                "close": [134.0, 135.0, 136.2, 136.97],
                                "volume": [1000000, 1100000, 980000, 1250000],
                            }
                        ]
                    },
                }
            ],
        }
    }


def test_registry_maps_spacex_and_keeps_future_listings_configurable():
    spacex = finance_engine.resolve_security("SpaceX")
    assert spacex["status"] == "listed"
    assert spacex["ticker"] == "SPCX"
    assert spacex["exchange"] == "NASDAQ"
    assert finance_engine.TOP_COMPANIES["spacex"] == "SPCX"

    openai = finance_engine.resolve_security("OpenAI")
    anthropic = finance_engine.resolve_security("Anthropic")
    assert openai["status"] == "pending_listing" and openai["ticker"] == ""
    assert anthropic["status"] == "pending_listing" and anthropic["ticker"] == ""


def test_pending_listing_does_not_guess_ticker_with_ai():
    for company in ("OpenAI", "Anthropic"):
        payload = finance_engine.fetch_financial_data(FailIfCalledAI(), company, use_cache=False)
        assert payload["is_public"] is False
        assert payload["listing_status"] == "pending_listing"
        assert payload["ticker"] == ""


def test_yahoo_chart_normalization_generates_market_chart():
    original_request = finance_engine._request_response
    finance_engine._request_response = lambda *args, **kwargs: FakeResponse(_yahoo_payload())
    try:
        payload = finance_engine.fetch_from_yahoo_chart("SPCX")
    finally:
        finance_engine._request_response = original_request

    assert payload["data_available"] is True
    assert payload["data_source"] == "yahoo_chart"
    assert payload["ticker"] == "SPCX"
    assert payload["history_points"] == 4
    assert payload["current_price"] == 136.97
    assert payload["prev_close"] == 136.2
    assert payload["change_pct"] == 0.57
    assert payload["chart_path"]
    assert Path(payload["chart_path"]).exists()
    assert Path(payload["chart_path"]).stat().st_size > 1000


def test_provider_failure_falls_back_and_cache_is_reused():
    original_yahoo = finance_engine.fetch_from_yahoo_chart
    original_stooq = finance_engine.fetch_from_stooq
    calls = {"yahoo": 0, "stooq": 0}
    fallback_payload = {
        "is_public": True,
        "data_available": True,
        "data_source": "stooq",
        "ticker": "SPCX",
        "currency": "USD",
        "current_price": 136.0,
        "change_pct": 1.0,
        "chart_path": None,
    }

    def fail_yahoo(ticker):
        calls["yahoo"] += 1
        return None

    def pass_stooq(ticker):
        calls["stooq"] += 1
        return dict(fallback_payload)

    finance_engine.fetch_from_yahoo_chart = fail_yahoo
    finance_engine.fetch_from_stooq = pass_stooq
    finance_engine.clear_finance_cache()
    try:
        first = finance_engine.fetch_financial_data(InvalidAI(), "SpaceX")
        second = finance_engine.fetch_financial_data(InvalidAI(), "SpaceX")
    finally:
        finance_engine.fetch_from_yahoo_chart = original_yahoo
        finance_engine.fetch_from_stooq = original_stooq
        finance_engine.clear_finance_cache()

    assert first["data_source"] == "stooq"
    assert [attempt["provider"] for attempt in first["provider_attempts"]] == ["yahoo_chart", "stooq"]
    assert first["cache_hit"] is False
    assert second["cache_hit"] is True
    assert calls == {"yahoo": 1, "stooq": 1}


def test_matplotlib_chart_fallback_works_without_mplfinance():
    if finance_engine.pd is None or finance_engine.plt is None:
        return "SKIP matplotlib or pandas unavailable"
    frame = finance_engine.pd.DataFrame(
        {
            "Open": [10, 11, 12],
            "High": [12, 13, 14],
            "Low": [9, 10, 11],
            "Close": [11, 12, 13],
            "Volume": [100, 120, 140],
        },
        index=finance_engine.pd.to_datetime(["2026-08-20", "2026-08-21", "2026-08-24"]),
    )
    original_mpf = finance_engine.mpf
    finance_engine.mpf = None
    try:
        chart_path = finance_engine.generate_pro_kline_chart("FALLBACK", frame, "finance_fallback_test.png")
    finally:
        finance_engine.mpf = original_mpf
    assert chart_path
    assert Path(chart_path).exists()
    assert Path(chart_path).stat().st_size > 1000


if __name__ == "__main__":
    tests = [
        test_registry_maps_spacex_and_keeps_future_listings_configurable,
        test_pending_listing_does_not_guess_ticker_with_ai,
        test_yahoo_chart_normalization_generates_market_chart,
        test_provider_failure_falls_back_and_cache_is_reused,
        test_matplotlib_chart_fallback_works_without_mplfinance,
    ]
    for test in tests:
        test()
    print(f"finance engine tests passed: {len(tests)}")
