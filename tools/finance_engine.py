from __future__ import annotations

import copy
import io
import json
import logging
import os
import re
import threading
import time
import warnings
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote

from pydantic import BaseModel, Field

try:
    import requests
except Exception:
    requests = None

try:
    import pandas as pd
except Exception:
    pd = None

try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except Exception:
    matplotlib = None
    plt = None

try:
    import mplfinance as mpf
except Exception:
    mpf = None

try:
    import yfinance as yf
except Exception:
    yf = None


if yf is not None:
    logging.getLogger("yfinance").setLevel(logging.CRITICAL)


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_FINANCE_REGISTRY_PATH = Path(__file__).with_name("finance_registry.json")
DEFAULT_CHART_DIR = ROOT_DIR / "data" / "cache" / "finance_charts"
FINANCE_CACHE_TTL_SECONDS = 15 * 60
_FINANCE_CACHE = {}
_FINANCE_CACHE_LOCK = threading.Lock()
_RETRYABLE_HTTP_STATUS = {408, 425, 429, 500, 502, 503, 504}
_MARKET_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9",
}


class TickerResult(BaseModel):
    is_public: bool = Field(description="是否上市")
    ticker: str = Field(description="股票代码")
    currency: str = Field(default="", description="货币")


def format_number(num):
    if num is None or num == 0:
        return "N/A"
    if pd is not None and pd.isna(num):
        return "N/A"
    try:
        value = float(num)
        if value >= 1e12:
            return f"{value / 1e12:.2f}万亿"
        if value >= 1e8:
            return f"{value / 1e8:.2f}亿"
        if value >= 1e4:
            return f"{value / 1e4:.2f}万"
        return str(round(value, 2))
    except (TypeError, ValueError):
        return "N/A"


def _safe_float(value):
    try:
        if value is None:
            return None
        if pd is not None and pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_ticker(value):
    ticker = str(value or "").strip().upper()
    if not ticker or not re.fullmatch(r"[A-Z0-9^][A-Z0-9.^-]{0,14}", ticker):
        return ""
    return ticker


def _extract_ticker_from_input(company_name):
    raw = str(company_name or "").strip()
    if not raw:
        return ""
    upper = raw.upper()
    if (raw.isupper() or "." in raw) and _normalize_ticker(upper):
        return upper
    match = re.search(r"\(([A-Z0-9^][A-Z0-9.^-]{0,14})\)", raw)
    return _normalize_ticker(match.group(1)) if match else ""


@lru_cache(maxsize=4)
def _load_finance_registry_cached(path_text):
    path = Path(path_text)
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        payload = {}

    securities = []
    alias_index = {}
    for raw_security in payload.get("securities", []) or []:
        if not isinstance(raw_security, dict):
            continue
        canonical_name = str(raw_security.get("canonical_name") or "").strip()
        status = str(raw_security.get("status") or "unknown").strip().lower()
        ticker = _normalize_ticker(raw_security.get("ticker"))
        aliases = [canonical_name] + list(raw_security.get("aliases", []) or [])
        normalized_aliases = []
        for alias in aliases:
            normalized = str(alias or "").strip().lower()
            if normalized and normalized not in normalized_aliases:
                normalized_aliases.append(normalized)
        record = {
            **raw_security,
            "canonical_name": canonical_name,
            "status": status,
            "ticker": ticker,
            "aliases": normalized_aliases,
        }
        securities.append(record)
        for alias in normalized_aliases:
            alias_index.setdefault(alias, record)

    return {
        "version": payload.get("version", 0),
        "securities": tuple(securities),
        "alias_index": alias_index,
        "config_path": str(path.resolve()),
    }


def load_finance_registry(registry_path=None):
    path = Path(registry_path or DEFAULT_FINANCE_REGISTRY_PATH).resolve()
    registry = _load_finance_registry_cached(str(path))
    return {
        "version": registry["version"],
        "securities": [dict(item) for item in registry["securities"]],
        "alias_index": {key: dict(value) for key, value in registry["alias_index"].items()},
        "config_path": registry["config_path"],
    }


def clear_finance_registry_cache():
    _load_finance_registry_cached.cache_clear()


def resolve_security(company_name, registry_path=None):
    registry = load_finance_registry(registry_path)
    company_key = str(company_name or "").strip().lower()
    if company_key in registry["alias_index"]:
        return dict(registry["alias_index"][company_key])

    ticker = _extract_ticker_from_input(company_name)
    if ticker:
        return {
            "canonical_name": str(company_name or ticker),
            "aliases": [company_key] if company_key else [],
            "status": "listed",
            "ticker": ticker,
            "exchange": "",
            "currency": "",
            "resolution": "explicit_ticker",
        }
    return None


def _build_top_company_mapping():
    mapping = {}
    registry = load_finance_registry()
    for record in registry["securities"]:
        ticker = record.get("ticker") if record.get("status") == "listed" else None
        for alias in record.get("aliases", []):
            mapping[alias] = ticker
    return mapping


TOP_COMPANIES = _build_top_company_mapping()


def _request_response(url, timeout=8, attempts=3, headers=None):
    if requests is None:
        raise RuntimeError("requests is unavailable")
    merged_headers = {**_MARKET_HEADERS, **dict(headers or {})}
    last_error = None
    for attempt in range(max(int(attempts or 1), 1)):
        try:
            response = requests.get(url, headers=merged_headers, timeout=timeout)
            status = int(getattr(response, "status_code", 200) or 200)
            if status == 200:
                return response
            last_error = RuntimeError(f"HTTP {status}")
            if status not in _RETRYABLE_HTTP_STATUS:
                break
        except Exception as exc:
            last_error = exc
        if attempt + 1 < attempts:
            time.sleep(min(0.4 * (2 ** attempt), 1.6))
    raise RuntimeError(str(last_error or "market data request failed"))


def _validate_history_frame(hist_df):
    if pd is None or hist_df is None or not hasattr(hist_df, "empty") or hist_df.empty:
        return None
    frame = hist_df.copy()
    rename_map = {str(column).strip().lower(): column for column in frame.columns}
    resolved = {}
    for expected in ("Open", "High", "Low", "Close", "Volume"):
        original = rename_map.get(expected.lower())
        if original is not None:
            resolved[original] = expected
    frame = frame.rename(columns=resolved)
    if not {"Open", "High", "Low", "Close"}.issubset(frame.columns):
        return None
    if "Volume" not in frame.columns:
        frame["Volume"] = 0
    for column in ("Open", "High", "Low", "Close", "Volume"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame.index = pd.to_datetime(frame.index, errors="coerce", utc=True).tz_convert(None)
    frame = frame[~frame.index.isna()]
    frame = frame.dropna(subset=["Open", "High", "Low", "Close"])
    frame = frame[~frame.index.duplicated(keep="last")].sort_index()
    if frame.empty:
        return None
    return frame[["Open", "High", "Low", "Close", "Volume"]].tail(90)


def _chart_output_path(ticker, filename=None):
    DEFAULT_CHART_DIR.mkdir(parents=True, exist_ok=True)
    safe_ticker = re.sub(r"[^A-Za-z0-9._-]+", "_", str(ticker or "ticker"))
    output_name = Path(filename).name if filename else f"kline_{safe_ticker}.png"
    if not output_name.lower().endswith(".png"):
        output_name += ".png"
    return DEFAULT_CHART_DIR / output_name


def generate_pro_kline_chart(ticker, hist_df, filename=None):
    frame = _validate_history_frame(hist_df)
    if frame is None:
        return None
    output_path = _chart_output_path(ticker, filename)
    temporary_path = output_path.with_name(f".{output_path.stem}.{os.getpid()}.tmp.png")
    try:
        if mpf is not None:
            market_colors = mpf.make_marketcolors(
                up="r", down="g", edge="inherit", wick="inherit", volume="in"
            )
            style = mpf.make_mpf_style(marketcolors=market_colors, gridstyle=":", y_on_right=False)
            moving_averages = tuple(value for value in (5, 10, 20) if len(frame) >= value)
            plot_options = {
                "type": "candle",
                "volume": True,
                "style": style,
                "figsize": (6.5, 3.8),
                "title": f"{ticker} Market History",
                "tight_layout": True,
                "savefig": str(temporary_path),
            }
            if moving_averages:
                plot_options["mav"] = moving_averages
            mpf.plot(frame, **plot_options)
        elif plt is not None:
            figure, (price_axis, volume_axis) = plt.subplots(
                2, 1, figsize=(6.5, 3.8), sharex=True, gridspec_kw={"height_ratios": [3, 1]}
            )
            price_axis.plot(frame.index, frame["Close"], color="#1F4E79", linewidth=1.8)
            price_axis.set_title(f"{ticker} Market History")
            price_axis.grid(True, linestyle=":", alpha=0.45)
            volume_axis.bar(frame.index, frame["Volume"], color="#7F8C8D", width=0.7)
            volume_axis.grid(True, axis="y", linestyle=":", alpha=0.35)
            figure.tight_layout()
            figure.savefig(temporary_path, dpi=150)
            plt.close(figure)
        else:
            return None
        os.replace(str(temporary_path), str(output_path))
        return str(output_path)
    except Exception as exc:
        logging.warning("Market chart generation failed for %s: %s", ticker, exc)
        return None
    finally:
        if temporary_path.exists():
            try:
                temporary_path.unlink()
            except OSError:
                pass


def _build_finance_payload(ticker, data_source, hist_df, quote_data=None):
    frame = _validate_history_frame(hist_df)
    if frame is None:
        return None
    quote_data = dict(quote_data or {})
    last_row = frame.iloc[-1]
    current_price = _safe_float(quote_data.get("current_price"))
    if current_price is None:
        current_price = _safe_float(last_row.get("Close"))
    previous_close = _safe_float(quote_data.get("prev_close"))
    if previous_close is None and len(frame) >= 2:
        previous_close = _safe_float(frame["Close"].iloc[-2])
    open_price = _safe_float(quote_data.get("open_price"))
    if open_price is None:
        open_price = _safe_float(last_row.get("Open"))
    change_pct = _safe_float(quote_data.get("change_pct"))
    if change_pct is None and current_price is not None and previous_close not in (None, 0):
        change_pct = (current_price - previous_close) / previous_close * 100

    pe = _safe_float(quote_data.get("pe"))
    pb = _safe_float(quote_data.get("pb"))
    pe_pb_parts = []
    if pe is not None:
        pe_pb_parts.append(f"PE: {pe:.2f}x")
    if pb is not None:
        pe_pb_parts.append(f"PB: {pb:.2f}x")
    erp = f"{((1 / pe) - 0.042) * 100:.2f}%" if pe and pe > 0 else "N/A"

    low_52w = _safe_float(quote_data.get("low_52w"))
    high_52w = _safe_float(quote_data.get("high_52w"))
    range_52w = f"{low_52w:.2f} - {high_52w:.2f}" if low_52w is not None and high_52w is not None else "N/A"
    volume = quote_data.get("volume")
    if volume is None:
        volume = last_row.get("Volume")

    chart_path = generate_pro_kline_chart(ticker, frame, f"kline_{ticker}.png")
    return {
        "is_public": True,
        "data_available": True,
        "data_source": data_source,
        "ticker": ticker,
        "currency": str(quote_data.get("currency") or "USD"),
        "current_price": round(current_price, 2) if current_price is not None else "N/A",
        "change_pct": round(change_pct, 2) if change_pct is not None else None,
        "open_price": round(open_price, 2) if open_price is not None else "N/A",
        "prev_close": round(previous_close, 2) if previous_close is not None else "N/A",
        "pe_pb": " | ".join(pe_pb_parts) if pe_pb_parts else "N/A",
        "erp": erp,
        "market_cap": format_number(quote_data.get("market_cap")),
        "range_52w": range_52w,
        "volume": format_number(volume),
        "chart_path": chart_path,
        "history_points": len(frame),
        "as_of": frame.index[-1].isoformat(),
    }


def fetch_from_yahoo_chart(ticker_code):
    if pd is None or requests is None:
        return None
    ticker = _normalize_ticker(ticker_code)
    if not ticker:
        return None
    try:
        url = (
            f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(ticker)}"
            "?range=1mo&interval=1d&events=div%2Csplits&includePrePost=false"
        )
        payload = _request_response(url, timeout=8, attempts=3).json()
        chart = payload.get("chart") or {}
        if chart.get("error"):
            return None
        results = chart.get("result") or []
        if not results:
            return None
        result = results[0]
        timestamps = result.get("timestamp") or []
        quote_rows = ((result.get("indicators") or {}).get("quote") or [{}])[0]
        rows = []
        for index, timestamp in enumerate(timestamps):
            close_value = (quote_rows.get("close") or [None] * len(timestamps))[index]
            if close_value is None:
                continue
            rows.append(
                {
                    "Date": pd.to_datetime(timestamp, unit="s", utc=True),
                    "Open": (quote_rows.get("open") or [None] * len(timestamps))[index] or close_value,
                    "High": (quote_rows.get("high") or [None] * len(timestamps))[index] or close_value,
                    "Low": (quote_rows.get("low") or [None] * len(timestamps))[index] or close_value,
                    "Close": close_value,
                    "Volume": (quote_rows.get("volume") or [0] * len(timestamps))[index] or 0,
                }
            )
        if not rows:
            return None
        hist_df = pd.DataFrame(rows).set_index("Date")
        meta = dict(result.get("meta") or {})
        quote_data = {
            "current_price": meta.get("regularMarketPrice"),
            # chartPreviousClose is the close before the selected range, not the
            # prior trading session. The history fallback below is safer.
            "prev_close": meta.get("previousClose"),
            "currency": meta.get("currency") or "USD",
            "low_52w": meta.get("fiftyTwoWeekLow"),
            "high_52w": meta.get("fiftyTwoWeekHigh"),
            "market_cap": meta.get("marketCap"),
        }
        return _build_finance_payload(ticker, "yahoo_chart", hist_df, quote_data)
    except Exception as exc:
        logging.info("Yahoo chart unavailable for %s: %s", ticker, exc)
        return None


def _stooq_symbol(ticker):
    symbol = _normalize_ticker(ticker)
    if not symbol:
        return ""
    if symbol.endswith(".HK"):
        return symbol.lower()
    if symbol.endswith((".SS", ".SZ")):
        return symbol.split(".", 1)[0].lower() + ".cn"
    if "." not in symbol and not symbol.startswith("^"):
        return symbol.lower() + ".us"
    return symbol.lower()


def fetch_from_stooq(ticker_code):
    if pd is None or requests is None:
        return None
    ticker = _normalize_ticker(ticker_code)
    symbol = _stooq_symbol(ticker)
    if not symbol:
        return None
    try:
        end_date = pd.Timestamp.utcnow().date()
        start_date = end_date - pd.Timedelta(days=120)
        url = (
            "https://stooq.com/q/d/l/"
            f"?s={quote(symbol)}&d1={start_date.strftime('%Y%m%d')}&d2={end_date.strftime('%Y%m%d')}&i=d"
        )
        response = _request_response(
            url,
            timeout=10,
            attempts=2,
            headers={"Accept": "text/csv,*/*;q=0.5"},
        )
        frame = pd.read_csv(io.StringIO(response.text))
        if frame.empty or "Date" not in frame.columns:
            return None
        frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce")
        frame = frame.set_index("Date")
        currency = "HKD" if ticker.endswith(".HK") else ("CNY" if ticker.endswith((".SS", ".SZ")) else "USD")
        return _build_finance_payload(ticker, "stooq", frame, {"currency": currency})
    except Exception as exc:
        logging.info("Stooq unavailable for %s: %s", ticker, exc)
        return None


def _tencent_symbol(ticker):
    symbol = _normalize_ticker(ticker)
    if symbol.endswith(".HK"):
        return "hk" + symbol.replace(".HK", "").zfill(5)
    if symbol.endswith(".SS"):
        return "sh" + symbol.replace(".SS", "")
    if symbol.endswith(".SZ"):
        return "sz" + symbol.replace(".SZ", "")
    return "us" + symbol


def fetch_from_tencent(ticker_code):
    if pd is None or requests is None:
        return None
    ticker = _normalize_ticker(ticker_code)
    if not ticker:
        return None
    try:
        symbol = _tencent_symbol(ticker)
        history_url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={symbol},day,,,30,qfq"
        history_payload = _request_response(history_url, timeout=7, attempts=2).json()
        if history_payload.get("code") != 0 or symbol not in (history_payload.get("data") or {}):
            return None
        history_data = history_payload["data"][symbol]
        raw_rows = history_data.get("day") or history_data.get("qfqday") or []
        rows = [
            {
                "Date": pd.to_datetime(row[0]),
                "Open": row[1],
                "Close": row[2],
                "High": row[3],
                "Low": row[4],
                "Volume": row[5],
            }
            for row in raw_rows
            if len(row) >= 6
        ]
        if not rows:
            return None
        hist_df = pd.DataFrame(rows).set_index("Date")

        quote_response = _request_response(
            f"https://qt.gtimg.cn/q={symbol}", timeout=7, attempts=2, headers={"Accept": "text/plain,*/*"}
        )
        parts = quote_response.content.decode("gbk", errors="ignore").split("~")
        if len(parts) < 47:
            return None
        market_cap = _safe_float(parts[45])
        if market_cap is not None:
            market_cap *= 100000000
        quote_data = {
            "current_price": parts[3],
            "prev_close": parts[4],
            "open_price": parts[5],
            "change_pct": parts[32],
            "low_52w": parts[34],
            "high_52w": parts[33],
            "pe": parts[39],
            "pb": parts[46],
            "market_cap": market_cap,
            "volume": parts[36],
            "currency": "USD" if symbol.startswith("us") else ("HKD" if symbol.startswith("hk") else "CNY"),
        }
        return _build_finance_payload(ticker, "tencent", hist_df, quote_data)
    except Exception as exc:
        logging.info("Tencent market data unavailable for %s: %s", ticker, exc)
        return None


def _fast_info_value(fast_info, key):
    try:
        if hasattr(fast_info, "get"):
            value = fast_info.get(key)
            if value is not None:
                return value
        return getattr(fast_info, key, None)
    except Exception:
        return None


def fetch_from_yfinance(ticker_code):
    if yf is None or pd is None:
        return None
    ticker = _normalize_ticker(ticker_code)
    if not ticker:
        return None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            security = yf.Ticker(ticker)
            hist_df = security.history(period="1mo", interval="1d", auto_adjust=False)
            if hist_df is None or hist_df.empty:
                return None
            try:
                fast_info = security.fast_info
            except Exception:
                fast_info = {}
            quote_data = {
                "current_price": _fast_info_value(fast_info, "last_price"),
                "prev_close": _fast_info_value(fast_info, "previous_close"),
                "currency": _fast_info_value(fast_info, "currency") or "USD",
                "market_cap": _fast_info_value(fast_info, "market_cap"),
                "low_52w": _fast_info_value(fast_info, "year_low"),
                "high_52w": _fast_info_value(fast_info, "year_high"),
            }
            return _build_finance_payload(ticker, "yfinance", hist_df, quote_data)
    except Exception as exc:
        logging.info("yfinance unavailable for %s: %s", ticker, exc)
        return None


def _provider_chain_for_ticker(ticker):
    if ticker.endswith((".HK", ".SS", ".SZ")):
        return [
            ("tencent", fetch_from_tencent),
            ("yahoo_chart", fetch_from_yahoo_chart),
            ("stooq", fetch_from_stooq),
            ("yfinance", fetch_from_yfinance),
        ]
    return [
        ("yahoo_chart", fetch_from_yahoo_chart),
        ("stooq", fetch_from_stooq),
        ("tencent", fetch_from_tencent),
        ("yfinance", fetch_from_yfinance),
    ]


def clear_finance_cache():
    with _FINANCE_CACHE_LOCK:
        _FINANCE_CACHE.clear()


def _get_cached_finance(ticker):
    with _FINANCE_CACHE_LOCK:
        cached = _FINANCE_CACHE.get(ticker)
        if not cached:
            return None
        if time.time() - cached["stored_at"] > FINANCE_CACHE_TTL_SECONDS:
            _FINANCE_CACHE.pop(ticker, None)
            return None
        payload = copy.deepcopy(cached["payload"])
    chart_path = payload.get("chart_path")
    if chart_path and not Path(chart_path).exists():
        return None
    payload["cache_hit"] = True
    return payload


def _store_finance_cache(ticker, payload):
    with _FINANCE_CACHE_LOCK:
        _FINANCE_CACHE[ticker] = {"stored_at": time.time(), "payload": copy.deepcopy(payload)}


def _non_listed_payload(record, fallback_message):
    status = str((record or {}).get("status") or "unknown")
    canonical_name = str((record or {}).get("canonical_name") or "")
    if status == "pending_listing":
        message = f"{canonical_name or '该公司'}已登记为待上市对象，尚未配置可核验交易代码。"
    elif status == "private":
        message = f"{canonical_name or '该公司'}当前登记为非上市公司。"
    else:
        message = fallback_message
    return {
        "is_public": False,
        "data_available": False,
        "listing_status": status,
        "ticker": str((record or {}).get("ticker") or ""),
        "currency": str((record or {}).get("currency") or ""),
        "msg": message,
        "chart_path": None,
    }


def fetch_financial_data(ai_driver, company_name, registry_path=None, use_cache=True):
    record = resolve_security(company_name, registry_path=registry_path)
    if record and record.get("status") != "listed":
        return _non_listed_payload(record, "Company is not listed")

    ticker = _normalize_ticker((record or {}).get("ticker"))
    if not ticker:
        if getattr(ai_driver, "valid", False):
            prompt = (
                f"Company name: {company_name}\n"
                "Determine whether the company is publicly traded. If public, return the verified Yahoo-compatible "
                "ticker. If the listing or ticker cannot be verified, set is_public to false."
            )
            try:
                resolved = ai_driver.analyze_structural(prompt, TickerResult)
            except Exception as exc:
                logging.info("Ticker resolution failed for %s: %s", company_name, exc)
                resolved = None
            if resolved and resolved.is_public:
                ticker = _normalize_ticker(resolved.ticker)
        if not ticker:
            return _non_listed_payload(record, "Unable to resolve a verified ticker")

    if use_cache:
        cached = _get_cached_finance(ticker)
        if cached:
            return cached

    attempts = []
    for provider_name, provider in _provider_chain_for_ticker(ticker):
        started = time.monotonic()
        try:
            payload = provider(ticker)
        except Exception as exc:
            payload = None
            detail = f"{type(exc).__name__}: {exc}"
        else:
            detail = "ok" if payload else "no usable market history"
        attempts.append(
            {
                "provider": provider_name,
                "success": bool(payload),
                "detail": detail[:180],
                "elapsed_ms": int((time.monotonic() - started) * 1000),
            }
        )
        if payload:
            payload["listing_status"] = "listed"
            payload["provider_attempts"] = attempts
            payload["cache_hit"] = False
            if record:
                payload["security_name"] = record.get("canonical_name", "")
                payload["exchange"] = record.get("exchange", "")
            if use_cache:
                _store_finance_cache(ticker, payload)
            return payload

    return {
        "is_public": True,
        "data_available": False,
        "data_source": "unavailable",
        "listing_status": "listed",
        "ticker": ticker,
        "currency": str((record or {}).get("currency") or ""),
        "msg": "已确认上市，但所有公开行情数据源当前均不可用。系统未尝试绕过登录、验证码或访问控制。",
        "current_price": "N/A",
        "change_pct": None,
        "open_price": "N/A",
        "prev_close": "N/A",
        "pe_pb": "N/A",
        "erp": "N/A",
        "market_cap": "N/A",
        "range_52w": "N/A",
        "volume": "N/A",
        "chart_path": None,
        "provider_attempts": attempts,
        "cache_hit": False,
    }
