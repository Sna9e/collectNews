import difflib
import json
import os
import re
import threading
import urllib.request
from copy import deepcopy
from typing import Dict, List


_RESERVED_HISTORY_KEY = "__topic_history__"
_RESERVED_EVENT_BANK_KEY = "__event_bank__"
_RESERVED_SCHEMA_KEY = "__schema_version__"
_TEXT_SANITIZE_RE = re.compile(r"[^a-z0-9\u4e00-\u9fff]+", re.IGNORECASE)
_ALNUM_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def _normalize_text(text: str) -> str:
    return _TEXT_SANITIZE_RE.sub("", (text or "").lower().strip())


def _extract_cjk_bigrams(text: str) -> set:
    chars = [ch for ch in (text or "") if _CJK_RE.match(ch)]
    if len(chars) < 2:
        return set(chars)
    return {"".join(chars[idx: idx + 2]) for idx in range(len(chars) - 1)}


def _tokenize(text: str) -> set:
    words = {token.lower() for token in _ALNUM_RE.findall(text or "") if len(token) >= 2}
    return words | _extract_cjk_bigrams(text)


def _short_topic_key(topic: str) -> str:
    topic = re.sub(r"\s*[（(].*?[)）]\s*$", "", topic or "")
    return (topic or "").strip()


def _safe_list(value) -> List:
    if isinstance(value, list):
        return value
    return []


class GistMemoryManager:
    def __init__(self, github_token: str, gist_id: str, local_path: str = ""):
        self.token = github_token
        self.gist_id = gist_id
        self.filename = "history_bank.json"
        self.local_path = local_path or os.path.join(os.getcwd(), "history_bank.local.json")
        self.memory_db = {}
        self._lock = threading.Lock()

    def _default_db(self) -> Dict:
        return {
            _RESERVED_SCHEMA_KEY: 2,
            _RESERVED_HISTORY_KEY: {},
            _RESERVED_EVENT_BANK_KEY: {},
        }

    def _ensure_schema(self):
        if not isinstance(self.memory_db, dict):
            self.memory_db = self._default_db()
            return

        if _RESERVED_HISTORY_KEY in self.memory_db or _RESERVED_EVENT_BANK_KEY in self.memory_db:
            self.memory_db.setdefault(_RESERVED_SCHEMA_KEY, 2)
            self.memory_db.setdefault(_RESERVED_HISTORY_KEY, {})
            self.memory_db.setdefault(_RESERVED_EVENT_BANK_KEY, {})
            return

        migrated = self._default_db()
        for key, value in self.memory_db.items():
            if isinstance(value, list):
                migrated[_RESERVED_HISTORY_KEY][key] = value
        self.memory_db = migrated

    def _load_from_gist(self):
        url = f"https://api.github.com/gists/{self.gist_id}"
        req = urllib.request.Request(
            url,
            headers={
                "Accept": "application/vnd.github.v3+json",
                "Authorization": f"token {self.token}",
            },
        )
        response = urllib.request.urlopen(req, timeout=10).read().decode("utf-8")
        gist_data = json.loads(response)
        files = gist_data.get("files", {})
        if self.filename in files:
            content = files[self.filename].get("content", "")
            self.memory_db = json.loads(content) if content else {}

    def _load_from_local(self):
        if not os.path.exists(self.local_path):
            self.memory_db = self._default_db()
            return
        with open(self.local_path, "r", encoding="utf-8") as f:
            self.memory_db = json.load(f)

    def load_memory(self) -> Dict:
        try:
            if self.token and self.gist_id:
                self._load_from_gist()
            else:
                self._load_from_local()
        except Exception as e:
            print(f"Memory load failed: {e}")
            self.memory_db = self._default_db()

        self._ensure_schema()
        return self.memory_db

    def _save_to_gist(self):
        url = f"https://api.github.com/gists/{self.gist_id}"
        content_str = json.dumps(self.memory_db, ensure_ascii=False, indent=2)
        payload = {"files": {self.filename: {"content": content_str}}}
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            method="PATCH",
            headers={
                "Accept": "application/vnd.github.v3+json",
                "Authorization": f"token {self.token}",
                "Content-Type": "application/json",
            },
        )
        urllib.request.urlopen(req, timeout=10)

    def _save_to_local(self):
        content_str = json.dumps(self.memory_db, ensure_ascii=False, indent=2)
        with open(self.local_path, "w", encoding="utf-8") as f:
            f.write(content_str)

    def save_memory(self):
        self._ensure_schema()
        try:
            self._save_to_local()
        except Exception as e:
            print(f"Local memory save failed: {e}")

        if not self.token or not self.gist_id:
            return

        try:
            self._save_to_gist()
            print("Memory synced to gist.")
        except Exception as e:
            print(f"Gist memory save failed: {e}")

    def _history_store(self) -> Dict:
        self._ensure_schema()
        return self.memory_db[_RESERVED_HISTORY_KEY]

    def _event_bank_store(self) -> Dict:
        self._ensure_schema()
        return self.memory_db[_RESERVED_EVENT_BANK_KEY]

    def _scope_key(self, topic: str) -> str:
        return _short_topic_key(topic)

    def get_topic_history(self, topic: str, limit: int = 4) -> str:
        with self._lock:
            history = list(self._history_store().get(self._scope_key(topic), []))
        if not history:
            return "（该主题暂无历史记忆）"
        lines = [f"[{item['date']}] {item['insight']}" for item in history[-max(int(limit or 1), 1):]]
        return "\n".join(lines)

    def add_topic_memory(self, topic: str, date: str, insight: str):
        if not insight or len(insight) < 5:
            return

        with self._lock:
            topic_key = self._scope_key(topic)
            history_store = self._history_store()
            history_store.setdefault(topic_key, [])

            for item in history_store[topic_key]:
                if item.get("date") == date:
                    item["insight"] = insight
                    return

            history_store[topic_key].append({"date": date, "insight": insight})
            history_store[topic_key] = history_store[topic_key][-8:]

    def _bucket_for_topic(self, topic: str) -> Dict:
        topic_key = self._scope_key(topic)
        event_store = self._event_bank_store()
        event_store.setdefault(topic_key, {"counter": 0, "events": []})
        return event_store[topic_key]

    def _score_event_match(self, event_dict: Dict, record: Dict) -> float:
        event_text = event_dict.get("event", "") or ""
        record_text = " ".join(
            [
                record.get("event", "") or "",
                " ".join(_safe_list(record.get("aliases"))),
                " ".join(_safe_list(record.get("keywords"))),
            ]
        )

        event_norm = _normalize_text(event_text)
        record_norm = _normalize_text(record_text)
        if not event_norm or not record_norm:
            return 0.0

        event_tokens = _tokenize(f"{event_text} {' '.join(event_dict.get('keywords', []) or [])}")
        record_tokens = _tokenize(record_text)
        overlap = len(event_tokens & record_tokens) / max(len(event_tokens), 1)
        ratio = difflib.SequenceMatcher(None, event_norm, record_norm).ratio()

        source_bonus = 0.0
        source = _normalize_text(event_dict.get("source", ""))
        record_sources = {_normalize_text(s) for s in _safe_list(record.get("sources"))}
        if source and source in record_sources:
            source_bonus = 0.08

        url_bonus = 0.0
        source_url = (event_dict.get("source_url", "") or "").strip().lower()
        record_urls = {str(url).strip().lower() for url in _safe_list(record.get("source_urls"))}
        if source_url and source_url in record_urls:
            url_bonus = 0.14

        return ratio * 0.62 + overlap * 0.30 + source_bonus + url_bonus

    def _update_record(self, record: Dict, event_dict: Dict, current_date: str):
        event_text = event_dict.get("event", "") or ""
        if event_text and event_text not in record["aliases"]:
            record["aliases"].append(event_text)

        for keyword in event_dict.get("keywords", []) or []:
            if keyword and keyword not in record["keywords"]:
                record["keywords"].append(keyword)

        source = event_dict.get("source", "") or ""
        if source and source not in record["sources"]:
            record["sources"].append(source)

        source_url = event_dict.get("source_url", "") or ""
        if source_url and source_url not in record["source_urls"]:
            record["source_urls"].append(source_url)

        record["event"] = event_text or record.get("event", "")
        record["last_seen"] = current_date
        record["last_event_date_label"] = event_dict.get("date", "") or record.get("last_event_date_label", "")
        record["seen_count"] = int(record.get("seen_count", 0) or 0) + 1

    def _new_record(self, bucket: Dict, event_dict: Dict, current_date: str) -> Dict:
        bucket["counter"] = int(bucket.get("counter", 0) or 0) + 1
        return {
            "event_id": f"E{bucket['counter']:03d}",
            "event": event_dict.get("event", "") or "",
            "keywords": list(event_dict.get("keywords", []) or []),
            "aliases": [event_dict.get("event", "")] if event_dict.get("event") else [],
            "sources": [event_dict.get("source", "")] if event_dict.get("source") else [],
            "source_urls": [event_dict.get("source_url", "")] if event_dict.get("source_url") else [],
            "first_seen": current_date,
            "last_seen": current_date,
            "last_event_date_label": event_dict.get("date", "") or "",
            "seen_count": 1,
        }

    def get_event_bank_summary(self, topic: str, limit: int = 6) -> str:
        with self._lock:
            bucket = deepcopy(self._bucket_for_topic(topic))
            events = bucket.get("events", [])
        if not events:
            return "（该主题暂无已登记事件）"

        recent_events = sorted(
            events,
            key=lambda item: (item.get("last_seen", ""), item.get("event_id", "")),
            reverse=True,
        )[:limit]
        lines = []
        for record in recent_events:
            lines.append(
                f"[{record.get('event_id', '')}] {record.get('event', '未命名事件')} | "
                f"首次记录:{record.get('first_seen', '未知')} | 最近记录:{record.get('last_seen', '未知')} | "
                f"累计追踪:{record.get('seen_count', 1)}次"
            )
        return "\n".join(lines)

    def get_topic_context(self, topic: str, history_limit: int = 3, event_limit: int = 4) -> str:
        history_text = self.get_topic_history(topic, limit=history_limit)
        event_text = self.get_event_bank_summary(topic, limit=event_limit)
        return f"【历史观察摘要】\n{history_text}\n\n【历史事件图谱】\n{event_text}"

    def bind_event_blueprints(self, topic: str, event_blueprints, current_date: str):
        with self._lock:
            bucket = self._bucket_for_topic(topic)
            records = bucket.get("events", [])
            bound_events = []

            for raw_item in event_blueprints or []:
                event_dict = raw_item.model_dump() if hasattr(raw_item, "model_dump") else deepcopy(raw_item)
                best_record = None
                best_score = 0.0
                for record in records:
                    score = self._score_event_match(event_dict, record)
                    if score > best_score:
                        best_score = score
                        best_record = record

                if best_record and best_score >= 0.6:
                    self._update_record(best_record, event_dict, current_date)
                    event_dict["event_id"] = best_record["event_id"]
                    event_dict["history_status"] = "followup"
                    event_dict["first_seen"] = best_record.get("first_seen", current_date)
                    event_dict["last_seen"] = best_record.get("last_seen", current_date)
                    event_dict["seen_count"] = best_record.get("seen_count", 1)
                else:
                    new_record = self._new_record(bucket, event_dict, current_date)
                    records.append(new_record)
                    event_dict["event_id"] = new_record["event_id"]
                    event_dict["history_status"] = "new"
                    event_dict["first_seen"] = current_date
                    event_dict["last_seen"] = current_date
                    event_dict["seen_count"] = 1

                bound_events.append(event_dict)

            bucket["events"] = records[-200:]
            return bound_events
