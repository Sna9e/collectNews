import argparse
import datetime as _dt
import getpass
import os
import shutil
import sys
import tomllib
from pathlib import Path


SECRET_KEYS = [
    "DEEPSEEK_API_KEY",
    "TAVILY_API_KEY",
    "EXA_API_KEY",
    "JINA_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "GITHUB_TOKEN",
    "GIST_ID",
]

SETTING_KEYS = {
    "CONSUMER_DAILY_SEARCH_PROVIDER": {
        "default": "exa",
        "choices": {"exa", "tavily", "hybrid"},
    },
    "CONSUMER_DAILY_SEARCH_DEPTH": {
        "default": "wide",
        "choices": {"wide", "normal", "light"},
    },
    "CONSUMER_DAILY_TIME_WINDOW": {
        "default": "72h",
        "choices": {"72h", "24h", "today", "7d"},
    },
}


def _default_secret_path() -> Path:
    return Path(__file__).resolve().parent / ".streamlit" / "secrets.toml"


def _read_existing(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        raise SystemExit(f"Failed to read existing secrets file: {path}\n{exc}") from exc
    if not isinstance(data, dict):
        return {}
    return {str(key): "" if value is None else str(value) for key, value in data.items()}


def _mask(value: str) -> str:
    value = str(value or "")
    if not value:
        return "missing"
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"


def _toml_escape(value: str) -> str:
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
    )


def _write_toml(path: Path, values: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Local Streamlit secrets for collectNews.",
        "# Do not commit this file.",
        "",
    ]

    for key in SECRET_KEYS:
        value = values.get(key, "")
        if value:
            lines.append(f'{key} = "{_toml_escape(value)}"')

    for key, spec in SETTING_KEYS.items():
        value = values.get(key, spec["default"])
        if value:
            lines.append(f'{key} = "{_toml_escape(value)}"')

    content = "\n".join(lines).rstrip() + "\n"
    if path.exists():
        current = path.read_text(encoding="utf-8-sig")
        if current == content:
            return
        stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_path = path.with_suffix(path.suffix + f".bak-{stamp}")
        shutil.copy2(path, backup_path)
        print(f"Backed up existing secrets to: {backup_path}")
    path.write_text(content, encoding="utf-8")


def _prompt_secret(key: str, current: str) -> str:
    prompt = f"{key} [{_mask(current)}] (blank=keep, '-'=clear): "
    entered = getpass.getpass(prompt).strip()
    if entered == "":
        return current
    if entered == "-":
        return ""
    return entered


def _prompt_setting(key: str, current: str, default: str, choices: set[str]) -> str:
    current = current or default
    choice_text = "/".join(sorted(choices))
    while True:
        entered = input(f"{key} [{current}] ({choice_text}, blank=keep): ").strip().lower()
        if entered == "":
            return current
        if entered in choices:
            return entered
        print(f"Invalid value. Allowed values: {choice_text}")


def _apply_env(values: dict) -> dict:
    merged = dict(values)
    for key in list(SECRET_KEYS) + list(SETTING_KEYS):
        env_value = os.getenv(key, "").strip()
        if env_value:
            merged[key] = env_value
    return merged


def _print_status(values: dict, path: Path) -> None:
    print(f"Secrets file: {path}")
    for key in SECRET_KEYS:
        print(f"{key}: {_mask(values.get(key, ''))}")
    for key, spec in SETTING_KEYS.items():
        print(f"{key}: {values.get(key, spec['default']) or spec['default']}")

    print("")
    if not values.get("DEEPSEEK_API_KEY") and not values.get("GEMINI_API_KEY") and not values.get("GOOGLE_API_KEY"):
        print("Warning: no model API key is configured.")
    if not values.get("EXA_API_KEY"):
        print("Warning: channel 3 currently requires EXA_API_KEY in this codebase.")
    if not values.get("TAVILY_API_KEY"):
        print("Warning: Tavily-dependent validation runs require TAVILY_API_KEY.")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create or update .streamlit/secrets.toml for the collectNews app."
    )
    parser.add_argument(
        "--path",
        default=str(_default_secret_path()),
        help="Target secrets.toml path.",
    )
    parser.add_argument(
        "--from-env",
        action="store_true",
        help="Read supported keys from environment variables before prompting.",
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Do not prompt; only write existing/default values plus --from-env values.",
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="Show configured/missing status without printing secret values.",
    )
    args = parser.parse_args()

    path = Path(args.path).resolve()
    values = _read_existing(path)
    if args.from_env:
        values = _apply_env(values)

    if args.show:
        _print_status(values, path)
        return 0

    if not args.non_interactive:
        print("Configure API keys for collectNews.")
        print("Input is hidden for secrets. Leave blank to keep the existing value.")
        print("Enter '-' to clear an existing secret.")
        print("")
        for key in SECRET_KEYS:
            values[key] = _prompt_secret(key, values.get(key, ""))
        print("")
        for key, spec in SETTING_KEYS.items():
            values[key] = _prompt_setting(
                key,
                values.get(key, spec["default"]),
                spec["default"],
                spec["choices"],
            )
    else:
        for key, spec in SETTING_KEYS.items():
            values.setdefault(key, spec["default"])

    _write_toml(path, values)
    print(f"Wrote secrets file: {path}")
    print("")
    _print_status(values, path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
