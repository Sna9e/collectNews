import argparse
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

try:
    import yaml
except ImportError as exc:  # pragma: no cover - covered by runtime environment checks.
    yaml = None
    _YAML_IMPORT_ERROR = exc
else:
    _YAML_IMPORT_ERROR = None


CONFIG_DIR = Path(__file__).resolve().parents[1] / "pwg_intelligence" / "config"
KEYWORDS_FILE = "keywords.yaml"
COMPANIES_FILE = "companies.yaml"
APPLICATION_MAP_FILE = "application_map.yaml"


@dataclass(frozen=True)
class PWGQueryRecord:
    query: str
    mode: str
    query_type: str
    priority: int = 3
    language: str = "auto"
    source_scope: str = "web"
    tags: list[str] = field(default_factory=list)

    def to_dict(self):
        return asdict(self)


def _load_yaml(path):
    if yaml is None:
        raise RuntimeError("PyYAML is required to load PWG YAML config files.") from _YAML_IMPORT_ERROR
    with Path(path).open("r", encoding="utf-8") as file_obj:
        data = yaml.safe_load(file_obj) or {}
    if not isinstance(data, dict):
        raise ValueError(f"YAML root must be a mapping: {path}")
    return data


def load_pwg_query_config(config_dir=None):
    base = Path(config_dir) if config_dir else CONFIG_DIR
    return {
        "keywords": _load_yaml(base / KEYWORDS_FILE),
        "companies": _load_yaml(base / COMPANIES_FILE),
        "application_map": _load_yaml(base / APPLICATION_MAP_FILE),
        "config_dir": str(base),
    }


def _dedupe(items, limit=None):
    merged = []
    seen = set()
    for item in items or []:
        value = str(item or "").strip()
        if not value:
            continue
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        merged.append(value)
        if limit and len(merged) >= limit:
            break
    return merged


def _contains_cjk(text):
    return bool(re.search(r"[\u4e00-\u9fff]", str(text or "")))


def _language_for_query(query):
    return "zh" if _contains_cjk(query) else "en"


def _keyword_terms_by_category(keyword_config):
    categories = keyword_config.get("categories", {}) or {}
    result = {}
    for category_id, payload in categories.items():
        result[category_id] = _dedupe((payload or {}).get("terms", []) or [])
    return result


def _keyword_pool_for_placeholder(keyword_config, placeholder):
    category_terms = _keyword_terms_by_category(keyword_config)
    group_map = keyword_config.get("placeholder_groups", {}) or {}
    category_ids = group_map.get(placeholder, []) or []
    terms = []
    for category_id in category_ids:
        terms.extend(category_terms.get(category_id, []))
    return _dedupe(terms)


def _iter_company_payloads(company_config):
    groups = company_config.get("company_groups", {}) or {}
    for group_id, group in groups.items():
        for company in (group or {}).get("companies", []) or []:
            payload = dict(company or {})
            payload["group_id"] = group_id
            payload["group_title"] = (group or {}).get("title", group_id)
            yield payload


def _company_matches(company, requested):
    requested_tokens = {str(item or "").strip().lower() for item in requested or [] if str(item or "").strip()}
    if not requested_tokens:
        return True
    names = [company.get("name", "")] + list(company.get("aliases", []) or [])
    normalized_names = {str(name or "").strip().lower() for name in names if str(name or "").strip()}
    return bool(requested_tokens & normalized_names)


def _company_pool(company_config, target_companies=None):
    companies = [
        company for company in _iter_company_payloads(company_config)
        if _company_matches(company, target_companies)
    ]
    companies.sort(key=lambda item: (str(item.get("priority", "P9")), str(item.get("name", ""))))
    names = []
    watch_terms = []
    for company in companies:
        names.append(company.get("name", ""))
        names.extend(company.get("aliases", []) or [])
        watch_terms.extend(company.get("watch_terms", []) or [])
    return _dedupe(names), _dedupe(watch_terms)


def _iter_application_payloads(application_config):
    for scene in application_config.get("application_scenes", []) or []:
        yield dict(scene or {})


def _application_matches(scene, requested):
    requested_tokens = {str(item or "").strip().lower() for item in requested or [] if str(item or "").strip()}
    if not requested_tokens:
        return True
    names = [scene.get("scene_id", ""), scene.get("name", "")] + list(scene.get("aliases", []) or [])
    normalized_names = {str(name or "").strip().lower() for name in names if str(name or "").strip()}
    return bool(requested_tokens & normalized_names)


def _application_pool(application_config, application_scenes=None):
    scenes = [
        scene for scene in _iter_application_payloads(application_config)
        if _application_matches(scene, application_scenes)
    ]
    scenes.sort(key=lambda item: (str(item.get("priority", "P9")), str(item.get("scene_id", ""))))
    names = []
    terms = []
    standards = []
    for scene in scenes:
        names.append(scene.get("name", ""))
        names.extend(scene.get("aliases", []) or [])
        terms.extend(scene.get("query_terms", []) or [])
        standards.extend(scene.get("standard_refs", []) or [])
    return _dedupe(names), _dedupe(terms), _dedupe(standards)


def _placeholder_pools(config, target_companies=None, application_scenes=None):
    keyword_config = config["keywords"]
    company_names, company_terms = _company_pool(config["companies"], target_companies=target_companies)
    application_names, application_terms, standard_terms = _application_pool(
        config["application_map"],
        application_scenes=application_scenes,
    )
    placeholders = set(keyword_config.get("placeholder_groups", {}) or {})
    pools = {
        placeholder: _keyword_pool_for_placeholder(keyword_config, placeholder)
        for placeholder in placeholders
    }
    pools.update(
        {
            "company": company_names,
            "company_terms": company_terms,
            "application": application_names,
            "application_terms": application_terms,
            "standard": _dedupe(standard_terms + pools.get("standard", [])),
        }
    )
    return pools


def get_supported_pwg_query_modes(config_dir=None):
    config = load_pwg_query_config(config_dir=config_dir)
    templates = config["keywords"].get("query_templates", {}) or {}
    return sorted(templates.keys())


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
    query = template
    for placeholder, value in values.items():
        query = query.replace("{" + placeholder + "}", value)
    query = re.sub(r"\s+", " ", query).strip()
    if "{" in query or "}" in query:
        return "", []
    return query, tags


def build_pwg_query_pack(
    mode,
    target_companies=None,
    application_scenes=None,
    max_queries=None,
    config_dir=None,
):
    config = load_pwg_query_config(config_dir=config_dir)
    keyword_config = config["keywords"]
    mode_key = str(mode or "").strip()
    templates = (keyword_config.get("query_templates", {}) or {}).get(mode_key)
    if not templates:
        supported = ", ".join(get_supported_pwg_query_modes(config_dir=config_dir))
        raise ValueError(f"Unsupported PWG query mode: {mode_key}. Supported modes: {supported}")

    mode_settings = (keyword_config.get("mode_settings", {}) or {}).get(mode_key, {}) or {}
    resolved_max = int(max_queries or mode_settings.get("max_queries") or 40)
    variants_per_template = max(1, int(mode_settings.get("variants_per_template") or 4))
    pools = _placeholder_pools(
        config,
        target_companies=target_companies,
        application_scenes=application_scenes,
    )

    records = []
    seen = set()
    for template_index, template in enumerate(templates):
        for variant_index in range(variants_per_template):
            query, tags = _fill_template(str(template or ""), pools, variant_index + template_index)
            if not query:
                continue
            key = query.lower()
            if key in seen:
                continue
            seen.add(key)
            records.append(
                PWGQueryRecord(
                    query=query,
                    mode=mode_key,
                    query_type=f"template_{template_index + 1:02d}",
                    priority=template_index + 1,
                    language=_language_for_query(query),
                    source_scope="web",
                    tags=tags,
                )
            )
            if len(records) >= resolved_max:
                return records
    return records


def build_pwg_example_queries(limit_per_mode=5, config_dir=None):
    examples = {}
    for mode in get_supported_pwg_query_modes(config_dir=config_dir):
        records = build_pwg_query_pack(mode, max_queries=limit_per_mode, config_dir=config_dir)
        examples[mode] = [record.query for record in records[:limit_per_mode]]
    return examples


def main(argv=None):
    parser = argparse.ArgumentParser(description="Build PWG query packs from YAML config.")
    parser.add_argument("--mode", default="", help="One mode to build. If omitted, print examples for all modes.")
    parser.add_argument("--limit", type=int, default=5, help="Maximum query count.")
    parser.add_argument("--company", action="append", default=[], help="Optional company name or alias filter.")
    parser.add_argument("--application", action="append", default=[], help="Optional application scene id/name/alias filter.")
    args = parser.parse_args(argv)

    if args.mode:
        records = build_pwg_query_pack(
            args.mode,
            target_companies=args.company,
            application_scenes=args.application,
            max_queries=args.limit,
        )
        payload = [record.to_dict() for record in records]
    else:
        payload = build_pwg_example_queries(limit_per_mode=args.limit)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
