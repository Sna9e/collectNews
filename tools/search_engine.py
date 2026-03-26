import json
import urllib.request
import urllib.parse
import concurrent.futures
import re

CN_DOMAIN_PRESET = [
    "36kr.com",
    "ithome.com",
    "huxiu.com",
    "geekpark.net",
    "leiphone.com",
    "tmtpost.com",
    "jiqizhixin.com",
    "qbitai.com",
    "pedaily.cn",
    "cyzone.cn",
    "iyiou.com",
    "donews.com",
    "sina.com.cn",
    "sohu.com",
    "163.com",
    "qq.com",
    "xinhua.net",
    "people.com.cn",
    "cnstock.com",
    "stcn.com",
    "eastmoney.com",
]


def parse_sites_text(sites_text):
    if not sites_text:
        return []

    raw_tokens = re.split(r"[\n,; ]+", sites_text.strip())
    domains = []
    seen = set()

    for token in raw_tokens:
        t = token.strip()
        if not t:
            continue
        if "://" in t:
            t = urllib.parse.urlparse(t).netloc or t
        t = t.split("/")[0].strip().lower()
        if t.startswith("www."):
            t = t[4:]
        if t and t not in seen:
            domains.append(t)
            seen.add(t)
    return domains


def _extract_host(url):
    if not url:
        return ""
    try:
        parsed = urllib.parse.urlparse(url)
        host = (parsed.netloc or "").lower()
        if host.startswith("www."):
            host = host[4:]
        return host
    except Exception:
        return ""


def _domain_in_allowlist(host, allowlist):
    if not host:
        return False
    return any(host == domain or host.endswith(f".{domain}") for domain in allowlist)


def contains_chinese_text(text):
    if not text:
        return False
    return bool(re.search(r"[\u4e00-\u9fff]", text))


def filter_china_results(results, sites_text="", require_chinese_text=True):
    if not results:
        return []

    custom_allowlist = parse_sites_text(sites_text)
    allowlist = custom_allowlist if custom_allowlist else CN_DOMAIN_PRESET

    filtered = []
    seen_urls = set()
    for item in results:
        url = item.get("url", "")
        host = _extract_host(url)
        if not host:
            continue

        is_cn_domain = host.endswith(".cn") or _domain_in_allowlist(host, allowlist)
        if not is_cn_domain:
            continue

        if require_chinese_text:
            text_blob = f"{item.get('title', '')} {item.get('content', '')}"
            if not contains_chinese_text(text_blob):
                continue

        if url and url in seen_urls:
            continue
        if url:
            seen_urls.add(url)
        filtered.append(item)

    return filtered

def search_web(query, sites_text, timelimit, max_results=20, tavily_key=""):
    if not tavily_key: return []
    sites = parse_sites_text(sites_text)
    try:
        url = "https://api.tavily.com/search"
        payload = {
            "api_key": tavily_key,
            "query": query, 
            "search_depth": "advanced",
            "topic": "news", 
            "max_results": max_results
        }
        if sites: payload["include_domains"] = sites
        if timelimit == "d": payload["days"] = 2 
        elif timelimit == "w": payload["days"] = 7
        elif timelimit == "m": payload["days"] = 30

        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
        resp = json.loads(urllib.request.urlopen(req, timeout=15).read().decode('utf-8'))
        return resp.get('results', [])
    except Exception as e:
        print(f"Tavily Search Failed: {e}")
        return []

# 🔴 核心升级：传入 jina_key，解锁完全体并发与防屏蔽
def fetch_single_url_with_jina(url, jina_key=""):
    jina_url = f"https://r.jina.ai/{url}"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    
    # 如果用户填了 Jina Key，就带上授权头，享受 VIP 待遇
    if jina_key:
        headers['Authorization'] = f'Bearer {jina_key}'
        
    try:
        req = urllib.request.Request(jina_url, headers=headers)
        response = urllib.request.urlopen(req, timeout=15).read().decode('utf-8')
        if response and len(response) > 200:
            return f"\n\n=== SOURCE START: {url} ===\n{response[:6000]}\n=== SOURCE END ===\n"
    except Exception:
        pass
    return ""

def safe_run_async_crawler(urls, jina_key=""):
    full_content = ""
    valid_count = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        future_to_url = {executor.submit(fetch_single_url_with_jina, url, jina_key): url for url in urls}
        for future in concurrent.futures.as_completed(future_to_url):
            res = future.result()
            if res:
                full_content += res
                valid_count += 1
    return full_content, valid_count
