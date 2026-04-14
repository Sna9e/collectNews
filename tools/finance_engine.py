import logging
import re
import time
import warnings
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
    matplotlib.use('Agg')
except Exception:
    matplotlib = None

try:
    import mplfinance as mpf
except Exception:
    mpf = None

try:
    import yfinance as yf
except Exception:
    yf = None

# ==========================================
# 屏蔽 yfinance 在 Streamlit 后台的恼人报错
# ==========================================
if yf is not None:
    logging.getLogger('yfinance').setLevel(logging.CRITICAL)

# ==========================================
# 🛡️ 机构级本地高频词典 (防大模型幻觉，秒级映射)
# ==========================================
TOP_COMPANIES = {
    'apple': 'AAPL', '苹果': 'AAPL',
    'google': 'GOOGL', '谷歌': 'GOOGL', 'alphabet': 'GOOGL',
    'meta': 'META', 'facebook': 'META',
    'microsoft': 'MSFT', '微软': 'MSFT',
    'amazon': 'AMZN', '亚马逊': 'AMZN',
    'tesla': 'TSLA', '特斯拉': 'TSLA',
    'nvidia': 'NVDA', '英伟达': 'NVDA',
    'amd': 'AMD', 'intel': 'INTC',
    'openai': None, 'anthropic': None, '字节跳动': None, 'bytedance': None
}

class TickerResult(BaseModel):
    is_public: bool = Field(description="是否上市")
    ticker: str = Field(description="股票代码")
    currency: str = Field(default="", description="货币")

def format_number(num):
    if num is None or num == 0:
        return 'N/A'
    if pd is not None and pd.isna(num):
        return 'N/A'
    try:
        num = float(num)
        if num >= 1e12: return f"{num/1e12:.2f}万亿"
        if num >= 1e8: return f"{num/1e8:.2f}亿"
        if num >= 1e4: return f"{num/1e4:.2f}万"
        return str(round(num, 2))
    except: return 'N/A'

def _safe_float(value):
    try:
        if value is None:
            return None
        if pd is not None and pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None

def _extract_ticker_from_input(company_name: str) -> str:
    raw = (company_name or "").strip()
    if not raw:
        return ""
    upper = raw.upper()
    if re.fullmatch(r"[A-Z]{1,6}(\.[A-Z]{1,2})?", upper) and (raw.isupper() or "." in raw):
        return upper
    if re.fullmatch(r"\d{4,5}\.HK", upper):
        return upper
    m = re.search(r"\(([A-Z]{1,6}(?:\.[A-Z]{1,2})?)\)", raw)
    if m:
        return m.group(1).upper()
    return ""

def fetch_from_yfinance(ticker_code):
    if yf is None:
        return None

    # 使用 try-except 彻底包裹 yfinance，防止 401 错误击穿 Streamlit
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            ticker = yf.Ticker(ticker_code)

            hist_df = ticker.history(period="1mo", interval="1d", auto_adjust=False)
            info = ticker.info or {}

            if (hist_df is None or hist_df.empty) and not info:
                return None

            current_price = _safe_float(info.get("regularMarketPrice"))
            prev_close = _safe_float(info.get("regularMarketPreviousClose"))
            open_price = _safe_float(info.get("regularMarketOpen"))

            if current_price is None and hist_df is not None and not hist_df.empty:
                current_price = _safe_float(hist_df["Close"].iloc[-1])
            if prev_close is None and hist_df is not None and len(hist_df) >= 2:
                prev_close = _safe_float(hist_df["Close"].iloc[-2])

            change_pct = None
            if current_price is not None and prev_close not in (None, 0):
                change_pct = (current_price - prev_close) / prev_close * 100

            pe = _safe_float(info.get("trailingPE") or info.get("forwardPE"))
            pb = _safe_float(info.get("priceToBook"))
            erp = f"{((1 / pe) - 0.042) * 100:.2f}%" if pe and pe > 0 else "N/A"

            market_cap = info.get("marketCap")
            volume = info.get("regularMarketVolume")
            if volume is None and hist_df is not None and not hist_df.empty:
                volume = hist_df["Volume"].iloc[-1]

            low_52w = info.get("fiftyTwoWeekLow", "N/A")
            high_52w = info.get("fiftyTwoWeekHigh", "N/A")
            currency = info.get("currency", "USD")

            chart_path = None
            if hist_df is not None and not hist_df.empty:
                chart_path = generate_pro_kline_chart(ticker_code, hist_df, f"kline_{ticker_code}.png")

            return {
                "is_public": True, "data_available": True, "data_source": "yfinance",
                "ticker": ticker_code, "currency": currency,
                "current_price": round(current_price, 2) if current_price is not None else "N/A",
                "change_pct": round(change_pct, 2) if change_pct is not None else None,
                "open_price": round(open_price, 2) if open_price is not None else "N/A",
                "prev_close": round(prev_close, 2) if prev_close is not None else "N/A",
                "pe_pb": f"PE: {pe:.2f}x | PB: {pb:.2f}x" if pe else "N/A",
                "erp": erp, "market_cap": format_number(market_cap),
                "range_52w": f"{low_52w} - {high_52w}", "volume": format_number(volume),
                "chart_path": chart_path,
            }
    except Exception as e:
        # 静默捕获所有 yfinance 错误 (包括 401 Crumb)，无缝交给下一个引擎
        print(f"yfinance 无响应或报 401 错误，已静默跳过: {ticker_code}")
        return None

def generate_pro_kline_chart(ticker, hist_df, filename):
    if mpf is None:
        return None
    if hist_df is None or not hasattr(hist_df, "empty") or hist_df.empty:
        return None
    try:
        mc = mpf.make_marketcolors(up='r', down='g', edge='inherit', wick='inherit', volume='in')
        s = mpf.make_mpf_style(marketcolors=mc, gridstyle=':', y_on_right=False)
        mpf.plot(hist_df, type='candle', volume=True, mav=(5, 10, 20), style=s, 
                 figsize=(6.5, 3.8), title=f"{ticker} 1-Month PRO K-Line",
                 tight_layout=True, savefig=filename)
        return filename
    except Exception as e:
        print(f"K线生成失败: {e}")
        return None

# ==========================================
# 💥 引擎 1：腾讯财经 (永不封杀的底层神级接口)
# ==========================================
def fetch_from_tencent(ticker_code):
    if pd is None or requests is None:
        return None

    try:
        symbol = ticker_code.upper()
        if symbol.endswith('.HK'): t_sym = 'hk' + symbol.replace('.HK', '').zfill(5)
        elif symbol.endswith('.SS'): t_sym = 'sh' + symbol.replace('.SS', '')
        elif symbol.endswith('.SZ'): t_sym = 'sz' + symbol.replace('.SZ', '')
        else: t_sym = 'us' + symbol

        url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={t_sym},day,,,30,qfq"
        res = requests.get(url, timeout=5).json()
        
        if res['code'] != 0 or t_sym not in res['data']: return None
        
        data_dict = res['data'][t_sym]
        k_list = data_dict.get('day', [])
        if not k_list and 'qfqday' in data_dict: k_list = data_dict['qfqday']
        if not k_list: return None

        df_data = []
        for row in k_list:
            df_data.append({
                "Date": pd.to_datetime(row[0]),
                "Open": float(row[1]), "Close": float(row[2]),
                "High": float(row[3]), "Low": float(row[4]),
                "Volume": float(row[5])
            })
        hist_df = pd.DataFrame(df_data).set_index("Date")

        qt_url = f"https://qt.gtimg.cn/q={t_sym}"
        qt_res = requests.get(qt_url, timeout=5).content.decode("gbk", errors="ignore")
        parts = qt_res.split('~')
        if len(parts) < 47: return None

        current_price = float(parts[3])
        prev_close = float(parts[4])
        open_price = float(parts[5])
        change_pct = float(parts[32])
        
        volume = float(parts[36]) * 100 if not t_sym.startswith('us') else float(parts[36])
        market_cap = float(parts[45]) * 100000000 if parts[45] else 0
        pe = float(parts[39]) if parts[39] else None
        pb = float(parts[46]) if parts[46] else None
        
        erp = f"{((1 / pe) - 0.042) * 100:.2f}%" if pe and pe > 0 else "N/A"
        currency = "USD" if t_sym.startswith('us') else ("HKD" if t_sym.startswith('hk') else "CNY")

        chart_path = generate_pro_kline_chart(ticker_code, hist_df, f"kline_{ticker_code}.png")

        return {
            "is_public": True, "data_available": True, "data_source": "tencent",
            "ticker": ticker_code, "currency": currency,
            "current_price": round(current_price, 2), "change_pct": round(change_pct, 2),
            "open_price": round(open_price, 2), "prev_close": round(prev_close, 2),
            "pe_pb": f"PE: {pe:.2f}x | PB: {pb:.2f}x" if pe else "N/A",
            "erp": erp, "market_cap": format_number(market_cap),
            "range_52w": f"{parts[34]} - {parts[33]}", "volume": format_number(volume),
            "chart_path": chart_path
        }
    except Exception as e:
        print(f"腾讯引擎异常: {e}")
        return None

# ==========================================
# 🛡️ 引擎 2：雪球 (备用通道)
# ==========================================
def fetch_from_xueqiu(ticker_code):
    if pd is None or requests is None:
        return None

    try:
        symbol = ticker_code.upper()
        if symbol.endswith('.HK'): symbol = symbol.replace('.HK', '').zfill(5)
        elif symbol.endswith('.SS'): symbol = 'SH' + symbol.replace('.SS', '')
        elif symbol.endswith('.SZ'): symbol = 'SZ' + symbol.replace('.SZ', '')
        
        session = requests.Session()
        session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        session.get("https://xueqiu.com/", timeout=5) 
        
        q_res = session.get(f"https://stock.xueqiu.com/v5/stock/quote.json?symbol={symbol}", timeout=5).json()
        quote = q_res.get('data', {}).get('quote', {})
        if not quote: return None
        
        ts = int(time.time() * 1000)
        k_res = session.get(f"https://stock.xueqiu.com/v5/stock/chart/kline.json?symbol={symbol}&begin={ts}&period=day&type=before&count=-30&indicator=kline", timeout=5).json()
        
        df_data = []
        for item in k_res.get('data', {}).get('item', []):
            df_data.append({"Date": pd.to_datetime(item[0], unit='ms'), "Open": item[2], "High": item[3], "Low": item[4], "Close": item[5], "Volume": item[1]})
        hist_df = pd.DataFrame(df_data).set_index("Date")
        
        pe = quote.get('pe_ttm')
        erp = f"{((1 / pe) - 0.042) * 100:.2f}%" if pe and pe > 0 else "N/A"
        chart_path = generate_pro_kline_chart(ticker_code, hist_df, f"kline_{ticker_code}.png")
        
        return {
            "is_public": True, "data_available": True, "data_source": "xueqiu",
            "ticker": ticker_code, "currency": quote.get('currency', 'USD'),
            "current_price": round(quote.get('current', 0), 2), "change_pct": round(quote.get('percent', 0), 2),
            "open_price": round(quote.get('open', 0), 2), "prev_close": round(quote.get('last_close', 0), 2),
            "pe_pb": f"PE: {pe:.2f}x | PB: {quote.get('pb', 0):.2f}x" if pe else "N/A",
            "erp": erp, "market_cap": format_number(quote.get('market_capital')),
            "range_52w": f"{quote.get('low52w', 'N/A')} - {quote.get('high52w', 'N/A')}",
            "volume": format_number(quote.get('volume')), "chart_path": chart_path
        }
    except Exception as e:
        print(f"雪球引擎异常: {e}")
        return None

# ==========================================
# 🧠 总调度长：三级降落伞，不死不休
# ==========================================
def fetch_financial_data(ai_driver, company_name):
    company_key = (company_name or "").lower().strip()
    ticker_code = ""

    if company_key in TOP_COMPANIES:
        ticker_code = TOP_COMPANIES[company_key]
        if ticker_code is None:
            return {"is_public": False, "data_available": False, "msg": "Known private company"}
    else:
        ticker_code = _extract_ticker_from_input(company_name)
        if not ticker_code:
            if getattr(ai_driver, "valid", False):
                prompt = (
                    f"Company name: {company_name}\n"
                    "Determine whether the company is publicly traded. "
                    "If public, return the correct Yahoo Finance ticker (US: e.g. AAPL; "
                    "China A-share: 600519.SS/000001.SZ; HK: 0700.HK). "
                    "If not public, set is_public to false."
                )
                try:
                    res = ai_driver.analyze_structural(prompt, TickerResult)
                except Exception as e:
                    print(f"Ticker resolution failed: {e}")
                    res = None
                if not res or not res.is_public or not res.ticker:
                    return {"is_public": False, "data_available": False, "msg": "Unable to resolve ticker"}
                ticker_code = res.ticker
            else:
                return {"is_public": False, "data_available": False, "msg": "Ticker unknown and AI not available"}

    if not ticker_code:
        return {"is_public": False, "data_available": False, "msg": "Ticker missing"}

    ticker_code = ticker_code.upper().strip()

    # 核心修改：将 yfinance 优先级降到最低，全面优先使用腾讯和雪球
    source_chain = [
        ("tencent", fetch_from_tencent),
        ("xueqiu", fetch_from_xueqiu),
        ("yfinance", fetch_from_yfinance), 
    ]

    for name, fn in source_chain:
        print(f"Fetching {ticker_code} via {name} ...")
        data = fn(ticker_code)
        if data:
            return data

    print(f"All data sources unavailable for {ticker_code}.")
    return {
        "is_public": True, "data_available": False, "data_source": "unavailable",
        "ticker": ticker_code, "currency": "", "msg": "No data source available",
        "current_price": "N/A", "change_pct": None, "open_price": "N/A",
        "prev_close": "N/A", "pe_pb": "N/A", "erp": "N/A",
        "market_cap": "N/A", "range_52w": "N/A", "volume": "N/A",
        "chart_path": None,
    }
