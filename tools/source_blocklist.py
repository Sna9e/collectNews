"""Configurable source-domain and automated-content blocking.

The policy is provider-neutral: search providers receive the effective domain
list when supported, and every returned result is checked again locally.
"""

from __future__ import annotations

import ipaddress
import datetime
import json
import os
import re
import tempfile
import urllib.parse
import urllib.request
from functools import lru_cache
from pathlib import Path


DEFAULT_BLOCKLIST_PATH = Path(__file__).with_name("source_blocklist.json")
DEFAULT_USER_BLOCKLIST_PATH = Path(__file__).resolve().parents[1] / "data" / "source_blocklist.user.json"
USER_BLOCKLIST_GIST_FILENAME = "source_blocklist.user.json"
_DOMAIN_LABEL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$", re.IGNORECASE)
_TOKEN_SPLIT_RE = re.compile(r"[\s,;，；]+")


def _candidate_host(value):
    raw = str(value or "").strip().strip("'\"`[](){}<>")
    if not raw or raw.startswith("#"):
        return ""
    if raw.startswith("*."):
        raw = raw[2:]
    if raw.startswith("."):
        raw = raw[1:]

    try:
        if "://" in raw:
            parsed = urllib.parse.urlsplit(raw)
        else:
            parsed = urllib.parse.urlsplit(f"//{raw}")
        host = parsed.hostname or ""
    except (TypeError, ValueError):
        return ""
    return host.rstrip(".").lower()


def normalize_domain_rule(value):
    """Return a canonical hostname or an empty string for invalid input."""
    host = _candidate_host(value)
    if host.startswith("www."):
        host = host[4:]
    if not host:
        return ""

    try:
        ipaddress.ip_address(host)
        return host
    except ValueError:
        pass

    try:
        ascii_host = host.encode("idna").decode("ascii").lower()
    except (UnicodeError, ValueError):
        return ""
    if len(ascii_host) > 253 or "." not in ascii_host:
        return ""
    labels = ascii_host.split(".")
    if any(not _DOMAIN_LABEL_RE.fullmatch(label) for label in labels):
        return ""
    return ascii_host


def _raw_domain_tokens(value):
    if value is None:
        return []
    if isinstance(value, str):
        lines = []
        for line in value.splitlines() or [value]:
            clean_line = line.split("#", 1)[0].strip()
            if clean_line:
                lines.extend(token for token in _TOKEN_SPLIT_RE.split(clean_line) if token)
        return lines
    if isinstance(value, (list, tuple, set, frozenset)):
        return [str(item or "").strip() for item in value if str(item or "").strip()]
    return [str(value).strip()]


def parse_blocked_domains(value):
    domains = []
    seen = set()
    for token in _raw_domain_tokens(value):
        domain = normalize_domain_rule(token)
        if not domain or domain in seen:
            continue
        seen.add(domain)
        domains.append(domain)
    return domains


def parse_manual_blocklist(value):
    """Parse editable UI text and return both valid domains and invalid tokens."""
    domains = []
    invalid = []
    seen = set()
    for token in _raw_domain_tokens(value):
        domain = normalize_domain_rule(token)
        if not domain:
            invalid.append(token)
            continue
        if domain in seen:
            continue
        seen.add(domain)
        domains.append(domain)
    return domains, invalid


def domain_matches_rule(host, rule):
    canonical_host = normalize_domain_rule(host)
    canonical_rule = normalize_domain_rule(rule)
    if not canonical_host or not canonical_rule:
        return False
    return canonical_host == canonical_rule or canonical_host.endswith(f".{canonical_rule}")


@lru_cache(maxsize=8)
def _load_source_blocklist_cached(path_text):
    path = Path(path_text)
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        payload = {}

    rules = []
    seen = set()
    for raw_rule in payload.get("blocked_domains", []) or []:
        if isinstance(raw_rule, str):
            raw_rule = {"domain": raw_rule}
        if not isinstance(raw_rule, dict):
            continue
        domain = normalize_domain_rule(raw_rule.get("domain"))
        if not domain or domain in seen:
            continue
        seen.add(domain)
        rules.append(
            {
                "domain": domain,
                "category": str(raw_rule.get("category") or "configured_block").strip(),
                "reason": str(raw_rule.get("reason") or "内置信息源屏蔽规则").strip(),
            }
        )

    markers = []
    marker_seen = set()
    for raw_marker in payload.get("automated_content_markers", []) or []:
        if isinstance(raw_marker, str):
            raw_marker = {"marker": raw_marker}
        if not isinstance(raw_marker, dict):
            continue
        marker = str(raw_marker.get("marker") or "").strip().lower()
        if not marker or marker in marker_seen:
            continue
        marker_seen.add(marker)
        markers.append(
            {
                "marker": marker,
                "reason": str(raw_marker.get("reason") or "检测到自动生成或自动聚合声明").strip(),
            }
        )

    return {
        "version": payload.get("version", 0),
        "policy_name": str(payload.get("policy_name") or "source blocklist"),
        "rules": tuple(rules),
        "markers": tuple(markers),
        "config_path": str(path),
        "config_loaded": bool(payload),
    }


def load_source_blocklist(config_path=None):
    path = Path(config_path or DEFAULT_BLOCKLIST_PATH).resolve()
    return _load_source_blocklist_cached(str(path))


def clear_source_blocklist_cache():
    _load_source_blocklist_cached.cache_clear()
    _read_local_user_blocklist_cached.cache_clear()


def _parse_user_blocklist_payload(payload):
    if isinstance(payload, list):
        return parse_blocked_domains(payload)
    if not isinstance(payload, dict):
        return []
    return parse_blocked_domains(payload.get("blocked_domains", []))


@lru_cache(maxsize=8)
def _read_local_user_blocklist_cached(path_text):
    path = Path(path_text)
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return ()
    return tuple(_parse_user_blocklist_payload(payload))


def _read_local_user_blocklist(local_path=None):
    path = Path(local_path or DEFAULT_USER_BLOCKLIST_PATH).resolve()
    return list(_read_local_user_blocklist_cached(str(path)))


def _user_blocklist_payload(domains):
    return {
        "version": 1,
        "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "blocked_domains": parse_blocked_domains(domains),
    }


def _write_local_user_blocklist(domains, local_path=None):
    path = Path(local_path or DEFAULT_USER_BLOCKLIST_PATH).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _user_blocklist_payload(domains)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=str(path.parent),
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(str(temporary_path), str(path))
        _read_local_user_blocklist_cached.cache_clear()
    finally:
        if temporary_path and temporary_path.exists():
            try:
                temporary_path.unlink()
            except OSError:
                pass
    return path


def _load_gist_user_blocklist(github_token, gist_id, urlopen=None):
    opener = urlopen or urllib.request.urlopen
    request = urllib.request.Request(
        f"https://api.github.com/gists/{gist_id}",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {github_token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "collectNews-source-policy",
        },
    )
    response = opener(request, timeout=10).read().decode("utf-8")
    gist_payload = json.loads(response)
    file_payload = (gist_payload.get("files") or {}).get(USER_BLOCKLIST_GIST_FILENAME) or {}
    content = str(file_payload.get("content") or "").strip()
    if not content:
        return None
    return _parse_user_blocklist_payload(json.loads(content))


def load_user_source_blocklist(github_token="", gist_id="", local_path=None, urlopen=None):
    """Load the editable blocklist, preferring the configured Gist copy."""
    local_domains = _read_local_user_blocklist(local_path)
    result = {
        "domains": local_domains,
        "source": "local" if local_domains else "empty",
        "local_path": str(Path(local_path or DEFAULT_USER_BLOCKLIST_PATH).resolve()),
        "remote_configured": bool(github_token and gist_id),
        "warnings": [],
    }
    if not github_token or not gist_id:
        return result

    try:
        remote_domains = _load_gist_user_blocklist(github_token, gist_id, urlopen=urlopen)
    except Exception as exc:
        result["warnings"].append(f"Gist 永久名单读取失败，已使用本地副本：{exc}")
        return result

    if remote_domains is None:
        result["source"] = "local" if local_domains else "empty"
        return result

    result["domains"] = remote_domains
    result["source"] = "gist"
    try:
        _write_local_user_blocklist(remote_domains, local_path)
    except OSError as exc:
        result["warnings"].append(f"Gist 名单已加载，但本地镜像写入失败：{exc}")
    return result


def save_user_source_blocklist(domains, github_token="", gist_id="", local_path=None, urlopen=None):
    """Atomically save editable domains locally and, when configured, to Gist."""
    normalized = parse_blocked_domains(domains)
    result = {
        "domains": normalized,
        "local_saved": False,
        "remote_configured": bool(github_token and gist_id),
        "remote_saved": False,
        "local_path": str(Path(local_path or DEFAULT_USER_BLOCKLIST_PATH).resolve()),
        "warnings": [],
    }
    try:
        _write_local_user_blocklist(normalized, local_path)
        result["local_saved"] = True
    except OSError as exc:
        result["warnings"].append(f"本地永久名单保存失败：{exc}")

    if not github_token or not gist_id:
        return result

    opener = urlopen or urllib.request.urlopen
    content = json.dumps(_user_blocklist_payload(normalized), ensure_ascii=False, indent=2)
    payload = {"files": {USER_BLOCKLIST_GIST_FILENAME: {"content": content}}}
    request = urllib.request.Request(
        f"https://api.github.com/gists/{gist_id}",
        data=json.dumps(payload).encode("utf-8"),
        method="PATCH",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {github_token}",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "collectNews-source-policy",
        },
    )
    try:
        opener(request, timeout=10).read()
        result["remote_saved"] = True
    except Exception as exc:
        result["warnings"].append(f"Gist 永久名单保存失败，本次仅保存在当前服务器：{exc}")
    return result


def get_builtin_block_rules(config_path=None):
    return [dict(rule) for rule in load_source_blocklist(config_path)["rules"]]


def get_effective_blocked_domains(manual_domains=None, config_path=None, user_config_path=None):
    merged = []
    seen = set()
    configured = [rule["domain"] for rule in load_source_blocklist(config_path)["rules"]]
    persistent = _read_local_user_blocklist(user_config_path)
    environment = parse_blocked_domains(os.getenv("NEWS_BLOCKED_DOMAINS", ""))
    manual = parse_blocked_domains(manual_domains)
    for domain in configured + persistent + environment + manual:
        if domain in seen:
            continue
        seen.add(domain)
        merged.append(domain)
    return merged


def _result_host(result):
    result = dict(result or {})
    for value in (
        result.get("url"),
        result.get("source_url"),
        result.get("source"),
        result.get("source_name"),
    ):
        domain = normalize_domain_rule(value)
        if domain:
            return domain
    return ""


def evaluate_search_result(result, manual_domains=None, config_path=None, user_config_path=None):
    policy = load_source_blocklist(config_path)
    host = _result_host(result)

    for domain in _read_local_user_blocklist(user_config_path):
        if domain_matches_rule(host, domain):
            return {
                "blocked": True,
                "domain": host,
                "matched_rule": domain,
                "category": "user_persistent_blocklist",
                "reason": "命中前端保存的永久屏蔽域名",
            }

    manual_rules = parse_blocked_domains(manual_domains)
    environment_rules = parse_blocked_domains(os.getenv("NEWS_BLOCKED_DOMAINS", ""))
    for domain in manual_rules + environment_rules:
        if domain_matches_rule(host, domain):
            return {
                "blocked": True,
                "domain": host,
                "matched_rule": domain,
                "category": "manual_blocklist",
                "reason": "命中前端或环境变量配置的手动屏蔽域名",
            }

    for rule in policy["rules"]:
        if domain_matches_rule(host, rule["domain"]):
            return {
                "blocked": True,
                "domain": host,
                "matched_rule": rule["domain"],
                "category": rule["category"],
                "reason": rule["reason"],
            }

    result = dict(result or {})
    content_blob = " ".join(
        str(result.get(field) or "")
        for field in ("title", "content", "snippet", "raw_content", "description")
    ).lower()
    for marker_rule in policy["markers"]:
        if marker_rule["marker"] in content_blob:
            return {
                "blocked": True,
                "domain": host,
                "matched_rule": marker_rule["marker"],
                "category": "automated_content_marker",
                "reason": marker_rule["reason"],
            }

    return {
        "blocked": False,
        "domain": host,
        "matched_rule": "",
        "category": "",
        "reason": "",
    }


def filter_blocked_search_results(
    results,
    manual_domains=None,
    config_path=None,
    user_config_path=None,
):
    kept = []
    blocked = []
    for result in results or []:
        decision = evaluate_search_result(
            result,
            manual_domains=manual_domains,
            config_path=config_path,
            user_config_path=user_config_path,
        )
        if decision["blocked"]:
            blocked.append({**decision, "title": str((result or {}).get("title") or "")[:160]})
            continue
        kept.append(result)
    return kept, blocked
