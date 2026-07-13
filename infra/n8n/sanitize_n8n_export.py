from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path
from typing import Any


SENSITIVE_HEADER_NAMES = {
    "authorization",
    "cookie",
    "proxy-authorization",
    "x-api-key",
    "x-auth-token",
    "x-csrf-token",
}
SENSITIVE_EXACT_KEYS = {
    "access_token",
    "api_key",
    "apikey",
    "auth",
    "bearer",
    "client_secret",
    "cookie",
    "credentials",
    "encryptionkey",
    "n8n_encryption_key",
    "password",
    "refresh_token",
    "secret",
    "session",
    "token",
}
SENSITIVE_KEY_RE = re.compile(r"(password|secret|token|cookie|credential|authorization|api[_-]?key)", re.I)
AUTH_VALUE_RE = re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]+")
ENV_SECRET_RE = re.compile(r"\$env\.(?:N8N_ENCRYPTION_KEY|[^ \t\n\r\"'}]*(?:TOKEN|SECRET|PASSWORD|COOKIE|API_KEY)[^ \t\n\r\"'}]*)", re.I)


def sanitize_workflow(data: dict[str, Any]) -> dict[str, Any]:
    data.pop("credentials", None)
    data.pop("shared", None)
    data.pop("pinData", None)
    data.pop("staticData", None)
    data.pop("triggerCount", None)
    data.pop("usedCredentials", None)
    for node in data.get("nodes", []):
        node.pop("credentials", None)
        node.pop("pinData", None)
        node.pop("issues", None)
        _sanitize_value(node.get("parameters", {}), parent_key="")
    _sanitize_value(data.get("settings", {}), parent_key="")
    return data


def _sanitize_value(value: Any, *, parent_key: str) -> Any:
    if isinstance(value, dict):
        _sanitize_header_parameter_list(value)
        for key in list(value.keys()):
            normalized = _normalize_key(key)
            if normalized in SENSITIVE_EXACT_KEYS or SENSITIVE_KEY_RE.search(key):
                value[key] = _redacted_value(value[key])
            else:
                value[key] = _sanitize_value(value[key], parent_key=key)
        return value
    if isinstance(value, list):
        for index, item in enumerate(value):
            value[index] = _sanitize_value(item, parent_key=parent_key)
        return value
    if isinstance(value, str):
        value = AUTH_VALUE_RE.sub("REDACTED", value)
        value = ENV_SECRET_RE.sub("$env.REDACTED", value)
        if _normalize_key(parent_key) in SENSITIVE_HEADER_NAMES:
            return "REDACTED"
        return value
    return value


def _sanitize_header_parameter_list(value: dict[str, Any]):
    parameters = value.get("parameters")
    if not isinstance(parameters, list):
        return
    for item in parameters:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip().lower()
        if name in SENSITIVE_HEADER_NAMES or SENSITIVE_KEY_RE.search(name):
            item["value"] = "REDACTED"


def _redacted_value(value: Any) -> Any:
    if value in (None, ""):
        return value
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return 0
    if isinstance(value, list):
        return []
    if isinstance(value, dict):
        return {}
    return "REDACTED"


def _normalize_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]", "", key.lower())


def _safe_filename(name: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip().strip(".")
    return f"{cleaned or 'workflow'}.json"


def _workflow_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root]
    return sorted(root.rglob("*.json"))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Sanitize n8n workflow exports for Git.")
    parser.add_argument("path", nargs="?", default="workflows")
    parser.add_argument("--output-dir", default=None, help="Optional destination directory for sanitized workflows.")
    parser.add_argument("--normalize-filenames", action="store_true", help="Write files as '<workflow name>.json'.")
    args = parser.parse_args(argv)

    root = Path(args.path)
    files = _workflow_files(root)
    output_dir = Path(args.output_dir) if args.output_dir else None
    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    for path in files:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        sanitized = sanitize_workflow(data)
        if output_dir:
            target = output_dir / (_safe_filename(str(sanitized.get("name", path.stem))) if args.normalize_filenames else path.name)
        else:
            target = path
        target.write_text(json.dumps(sanitized, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        written.append(target)

    if output_dir and root.is_dir():
        for path in output_dir.glob("*.tmp"):
            path.unlink()
    print(json.dumps({"sanitized": [str(path) for path in written]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
