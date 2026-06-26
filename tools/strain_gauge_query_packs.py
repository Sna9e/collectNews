"""Query pack builder for the strain gauge and robotic six-axis sensor module."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
import re

import yaml


CONFIG_DIR = Path(__file__).resolve().parents[1] / "strain_gauge_intelligence" / "config"


@dataclass(frozen=True)
class StrainGaugeQueryRecord:
    query: str
    item_type: str
    window_days: int
    priority: int = 3
    language: str = "auto"
    tags: list[str] = field(default_factory=list)

    def to_dict(self):
        return asdict(self)


def _load_yaml(path):
    with Path(path).open("r", encoding="utf-8") as file_obj:
        data = yaml.safe_load(file_obj) or {}
    if not isinstance(data, dict):
        raise ValueError(f"YAML root must be a mapping: {path}")
    return data


def load_strain_gauge_query_config(config_dir=None):
    base = Path(config_dir) if config_dir else CONFIG_DIR
    return {
        "keywords": _load_yaml(base / "keywords.yaml"),
        "companies": _load_yaml(base / "companies.yaml"),
        "report_rules": _load_yaml(base / "report_rules.yaml"),
        "config_dir": str(base),
    }


def _contains_cjk(text):
    return bool(re.search(r"[\u4e00-\u9fff]", str(text or "")))


def _language(query):
    return "zh" if _contains_cjk(query) else "en"


def _dedupe(values, limit=None):
    output = []
    seen = set()
    for value in values or []:
        text = str(value or "").strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        output.append(text)
        if limit and len(output) >= limit:
            break
    return output


def _placeholder_values(config, item_type):
    companies = config["companies"]
    if item_type == "patent":
        applicants = _dedupe(companies.get("patent_applicants", []) or [], limit=16)
        return {"applicant": applicants, "company": applicants}
    return {
        "company": _dedupe(companies.get("news_companies", []) or [], limit=20),
        "applicant": _dedupe(companies.get("patent_applicants", []) or [], limit=16),
    }


def _fill_template(template, pools, variant_index):
    placeholders = re.findall(r"{([a-zA-Z0-9_]+)}", template)
    values = {}
    tags = []
    for placeholder in placeholders:
        pool = pools.get(placeholder, []) or []
        if not pool:
            return "", []
        value = pool[variant_index % len(pool)]
        values[placeholder] = value
        tags.append(f"{placeholder}:{value}")
    query = str(template or "")
    for key, value in values.items():
        query = query.replace("{" + key + "}", value)
    query = re.sub(r"\s+", " ", query).strip()
    if "{" in query or "}" in query:
        return "", []
    return query, tags


def build_strain_gauge_query_pack(item_type="all", window_days=None, max_queries_per_type=None, config_dir=None):
    config = load_strain_gauge_query_config(config_dir=config_dir)
    templates_by_type = config["keywords"].get("query_templates", {}) or {}
    windows = config["keywords"].get("search_windows_days", {}) or {}
    requested_types = ["news", "patent", "paper"] if item_type == "all" else [str(item_type)]

    records = []
    for current_type in requested_types:
        templates = templates_by_type.get(current_type, []) or []
        if not templates:
            raise ValueError(f"Unsupported strain gauge item type: {current_type}")
        pools = _placeholder_values(config, current_type)
        default_window = int(window_days or (windows.get(current_type, []) or [30])[0])
        seen = set()
        for template_index, template in enumerate(templates):
            variants = max(1, min(4, int(max_queries_per_type or 12)))
            for variant_index in range(variants):
                query, tags = _fill_template(template, pools, variant_index + template_index)
                if not query:
                    continue
                key = query.lower()
                if key in seen:
                    continue
                seen.add(key)
                records.append(
                    StrainGaugeQueryRecord(
                        query=query,
                        item_type=current_type,
                        window_days=default_window,
                        priority=template_index + 1,
                        language=_language(query),
                        tags=tags,
                    )
                )
                if max_queries_per_type and len([item for item in records if item.item_type == current_type]) >= int(max_queries_per_type):
                    break
            if max_queries_per_type and len([item for item in records if item.item_type == current_type]) >= int(max_queries_per_type):
                break
    return records

