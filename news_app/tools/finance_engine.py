# -*- coding: utf-8 -*-
import time
from typing import Optional

import pandas as pd
import matplotlib

matplotlib.use("Agg")
import mplfinance as mpf
import requests
import yfinance as yf
from pydantic import BaseModel, Field


TOP_COMPANIES = {
    "apple": "AAPL",
    "苹果": "AAPL",
    "google": "GOOGL",
    "谷歌": "GOOGL",
    "alphabet": "GOOGL",
    "meta": "META",
    "facebook": "META",
    "microsoft": "MSFT",
    "微软": "MSFT",
    "amazon": "AMZN",
    "亚马逊": "AMZN",
    "tesla": "TSLA",
    "特斯拉": "TSLA",
    "nvidia": "NVDA",
    "英伟达": "NVDA",
    "amd": "AMD",
    "intel": "INTC",
    "openai": None,
    "anthropic": None,
    "字节跳动": None,
    "bytedance": None,
}


class TickerResult(BaseModel):
    is_public: bool = Field(description="是否上市")
    ticker: str = Field(description="股票代码")
    currency: str = Field(description="货币")


def format_number(num):
    if num is None or pd.isna(num) or num == 0:
        return "N/A"
    try:
        num = float(num)
        if num >= 1e12:
            return f"{num / 1e12:.2f}万亿"
        if num >= 1e8:
            return f"{num / 1e8:.2f}亿"
        if num >= 1e4:
            return f"{num / 1e4:.2f}万"
        return str(round(num, 2))
    except Exception:
        return "N/A"


def _safe_float(val) -> Optional[float]:
    try:
        if val is None or val == "":
            return None
        return float(val)
    except Exception:
        return None


def generate_pro_kline_chart(ticker, hist_df, filename):
    if hist_df is None or hist_df.empty:
        return None
    try:
        mc = mpf.make_marketcolors(
            up="r", down="g", edge="inherit", wick="inherit", volume="in"
        )
        style = mpf.make_mpf_style(marketcolors=mc, gridstyle=":", y_on_right=False)
        mpf.plot(
            hist_df,
            type="candle",
            volume=True,
            mav=(5, 10, 20),
            style=style,
            figsize=(6.5, 3.8),
            title=f"{ticker} 1-Month K-Line",
            tight_layout=True,
            savefig=filename,
        )
        return filename
    except Exception as e:
        print(f"[finance] kline failed: {e}")
        return None


def fetch_from_tencent(ticker_code):
    try:
        symbol = ticker_code.upper()
        if symbol.endswith(".HK"):
            t_sym = "hk" + symbol.replace(".HK", "").zfill(5)
        elif symbol.endswith(".SS"):
            t_sym = "sh" + symbol.replace(".SS", "")
        elif symbol.endswith(".SZ"):
            t_sym = "sz" + symbol.replace(".SZ", "")
        else:
            t_sym = "us" + symbol

        url = (
            "http://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
            f"?param={t_sym},day,,,30,qfq"
        )
        res = requests.get(url, timeout=5).json()
        if res.get("code") != 0 or t_sym not in res.get("data", {}):
            return None

        data_dict = res["data"][t_sym]
        k_list = data_dict.get("day", []) or data_dict.get("qfqday", [])
        if not k_list:
            return None

        df_data = []
        for row in k_list:
            df_data.append(
                {
                    "Date": pd.to_datetime(row[0]),
                    "Open": float(row[1]),
                    "Close": float(row[2]),
                    "High": float(row[3]),
                    "Low": float(row[4]),
                    "Volume": float(row[5]),
                }
            )
        hist_df = pd.DataFrame(df_data).set_index("Date")

        qt_url = f"http://qt.gtimg.cn/q={t_sym}"
        qt_res = requests.get(qt_url, timeout=5).text
        parts = qt_res.split("~")
        if len(parts) < 46:
            return None

        current_price = _safe_float(parts[3])
        prev_close = _safe_float(parts[4])
        open_price = _safe_float(parts[5])
        change_pct = _safe_float(parts[32])

        volume = _safe_float(parts[36]) or 0.0
        if not t_sym.startswith("us"):
            volume = volume * 100

        market_cap = _safe_float(parts[45])
        market_cap = market_cap * 100000000 if market_cap else 0

        pe = _safe_float(parts[39])
        pb = _safe_float(parts[46]) if len(parts) > 46 else None

        erp = f"{((1 / pe) - 0.042) * 100:.2f}%" if pe and pe > 0 else "N/A"
        currency = "USD" if t_sym.startswith("us") else ("HKD" if t_sym.startswith("hk") else "CNY")

        chart_path = generate_pro_kline_chart(ticker_code, hist_df, f"kline_{ticker_code}.png")
        return {
            "is_public": True,
            "data_ok": True,
            "ticker": ticker_code,
            "currency": currency,
            "current_price": round(current_price, 2) if current_price is not None else "N/A",
            "change_pct": round(change_pct, 2) if change_pct is not None else 0.0,
            "open_price": round(open_price, 2) if open_price is not None else "N/A",
            "prev_close": round(prev_close, 2) if prev_close is not None else "N/A",
            "pe_pb": f"PE: {pe:.2f}x | PB: {pb:.2f}x" if pe else "N/A",
            "erp": erp,
            "market_cap": format_number(market_cap),
            "range_52w": f"{parts[34]} - {parts[33]}",
            "volume": format_number(volume),
            "chart_path": chart_path,
        }
    except Exception as e:
        print(f"[tencent] failed: {e}")
        return None


def fetch_from_xueqiu(ticker_code):
    try:
        symbol = ticker_code.upper()
        if symbol.endswith(".HK"):
            symbol = symbol.replace(".HK", "").zfill(5)
        elif symbol.endswith(".SS"):
            symbol = "SH" + symbol.replace(".SS", "")
        elif symbol.endswith(".SZ"):
            symbol = "SZ" + symbol.replace(".SZ", "")

        session = requests.Session()
        session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        session.get("https://xueqiu.com/", timeout=5)

        q_res = session.get(
            f"https://stock.xueqiu.com/v5/stock/quote.json?symbol={symbol}", timeout=5
        ).json()
        quote = q_res.get("data", {}).get("quote", {})
        if not quote:
            return None

        ts = int(time.time() * 1000)
        k_res = session.get(
            "https://stock.xueqiu.com/v5/stock/chart/kline.json"
            f"?symbol={symbol}&begin={ts}&period=day&type=before&count=-30&indicator=kline",
            timeout=5,
        ).json()

        df_data = []
        for item in k_res.get("data", {}).get("item", []):
            df_data.append(
                {
                    "Date": pd.to_datetime(item[0], unit="ms"),
                    "Open": item[2],
                    "High": item[3],
                    "Low": item[4],
                    "Close": item[5],
                    "Volume": item[1],
                }
            )
        hist_df = pd.DataFrame(df_data).set_index("Date")

        pe = quote.get("pe_ttm")
        erp = f"{((1 / pe) - 0.042) * 100:.2f}%" if pe and pe > 0 else "N/A"
        chart_path = generate_pro_kline_chart(ticker_code, hist_df, f"kline_{ticker_code}.png")

        return {
            "is_public": True,
            "data_ok": True,
            "ticker": ticker_code,
            "currency": quote.get("currency", "USD"),
            "current_price": round(quote.get("current", 0), 2),
            "change_pct": round(quote.get("percent", 0), 2),
            "open_price": round(quote.get("open", 0), 2),
            "prev_close": round(quote.get("last_close", 0), 2),
            "pe_pb": f"PE: {pe:.2f}x | PB: {quote.get('pb', 0):.2f}x" if pe else "N/A",
            "erp": erp,
            "market_cap": format_number(quote.get("market_capital")),
            "range_52w": f"{quote.get('low52w', 'N/A')} - {quote.get('high52w', 'N/A')}",
            "volume": format_number(quote.get("volume")),
            "chart_path": chart_path,
        }
    except Exception as e:
        print(f"[xueqiu] failed: {e}")
        return None


def fetch_from_yahoo(ticker_code):
    try:
        ticker = yf.Ticker(ticker_code)
        hist = ticker.history(period="1mo", interval="1d", auto_adjust=False)
        if hist is None or hist.empty:
            return None

        info = {}
        try:
            info = ticker.fast_info or {}
        except Exception:
            info = {}
        if not info:
            try:
                info = ticker.info or {}
            except Exception:
                info = {}

        current_price = _safe_float(hist["Close"].iloc[-1])
        prev_close = info.get("previousClose")
        if prev_close is None and len(hist) > 1:
            prev_close = _safe_float(hist["Close"].iloc[-2])
        open_price = _safe_float(hist["Open"].iloc[-1])

        change_pct = None
        if current_price is not None and prev_close:
            change_pct = (current_price - prev_close) / prev_close * 100

        pe = info.get("trailingPE") or info.get("forwardPE")
        pb = info.get("priceToBook")
        market_cap = info.get("marketCap")
        currency = info.get("currency", "USD")
        range_52w = f"{info.get('fiftyTwoWeekLow', 'N/A')} - {info.get('fiftyTwoWeekHigh', 'N/A')}"

        hist_df = hist[["Open", "High", "Low", "Close", "Volume"]].copy()
        hist_df.index.name = "Date"
        chart_path = generate_pro_kline_chart(ticker_code, hist_df, f"kline_{ticker_code}.png")

        return {
            "is_public": True,
            "data_ok": True,
            "ticker": ticker_code,
            "currency": currency,
            "current_price": round(current_price, 2) if current_price is not None else "N/A",
            "change_pct": round(change_pct, 2) if change_pct is not None else 0.0,
            "open_price": round(open_price, 2) if open_price is not None else "N/A",
            "prev_close": round(prev_close, 2) if prev_close is not None else "N/A",
            "pe_pb": f"PE: {pe:.2f}x | PB: {pb:.2f}x" if pe else "N/A",
            "erp": "N/A",
            "market_cap": format_number(market_cap),
            "range_52w": range_52w,
            "volume": format_number(hist["Volume"].iloc[-1] if "Volume" in hist else None),
            "chart_path": chart_path,
        }
    except Exception as e:
        print(f"[yahoo] failed: {e}")
        return None


def fetch_financial_data(ai_driver, company_name):
    company_key = company_name.lower().strip()
    ticker_code = ""

    if company_key in TOP_COMPANIES:
        ticker_code = TOP_COMPANIES[company_key]
        if ticker_code is None:
            return {"is_public": False, "data_ok": False, "msg": "known private company"}
    else:
        prompt = (
            f"判断“{company_name}”是否上市。若上市，请给出 Yahoo Ticker"
            "（美股直接写，A股加 .SS/.SZ，港股加 .HK）。若未上市，is_public=false。"
        )
        try:
            res = ai_driver.analyze_structural(prompt, TickerResult)
            if not res or not res.is_public or not res.ticker:
                return {"is_public": False, "data_ok": False, "msg": "model says not public"}
            ticker_code = res.ticker
        except Exception:
            return {"is_public": False, "data_ok": False, "msg": "ticker parse failed"}

    if not ticker_code:
        return {"is_public": False, "data_ok": False, "msg": "no ticker"}

    print(f"[finance] try yahoo for {ticker_code}")
    data = fetch_from_yahoo(ticker_code)
    if data:
        return data

    print(f"[finance] yahoo failed, try tencent for {ticker_code}")
    data = fetch_from_tencent(ticker_code)
    if data:
        return data

    print(f"[finance] tencent failed, try xueqiu for {ticker_code}")
    data = fetch_from_xueqiu(ticker_code)
    if data:
        return data

    print("[finance] all sources failed")
    return {
        "is_public": True,
        "data_ok": False,
        "ticker": ticker_code,
        "msg": "all sources failed",
        "chart_path": None,
    }
