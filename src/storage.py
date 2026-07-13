from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .city_registry import CITY_ORDER, city_catalog_items, get_city_profile, validate_city_profiles
from .result_contract import atomic_write_json


STORAGE_NAMESPACES = ("incoming", "staging", "runs", "exports", "quarantine", "archive")
MARKER_NAME = ".finance-data-namespace.json"


class StorageError(ValueError):
    error_code = "CITY_STORAGE_INVALID"


class StorageEscapeError(StorageError):
    error_code = "CITY_STORAGE_ESCAPE"


class StorageNamespaceMismatchError(StorageError):
    error_code = "CITY_STORAGE_NAMESPACE_MISMATCH"


@dataclass(frozen=True)
class CityStorage:
    city_id: str
    root: Path
    city_root: Path
    incoming: Path
    staging: Path
    runs: Path
    exports: Path
    quarantine: Path
    archive: Path

    def as_dict(self) -> dict[str, str]:
        return {
            "city_root": str(self.city_root),
            "incoming": str(self.incoming),
            "staging": str(self.staging),
            "runs": str(self.runs),
            "exports": str(self.exports),
            "quarantine": str(self.quarantine),
            "archive": str(self.archive),
        }


def finance_data_root_from_env() -> Path:
    value = os.environ.get("FINANCE_DATA_ROOT")
    if not value:
        raise StorageError("FINANCE_DATA_ROOT is not set")
    return Path(value)


def resolve_city_storage(city_id: str, root: Path | None = None) -> CityStorage:
    profile = get_city_profile(city_id)
    resolved_root = _resolve_root(root or finance_data_root_from_env())
    city_root = _safe_child(resolved_root, profile.storage_namespace)
    paths = {name: _safe_child(city_root, name) for name in STORAGE_NAMESPACES}
    return CityStorage(city_id=city_id, root=resolved_root, city_root=city_root, **paths)


def assert_path_in_city_namespace(path: Path, city_id: str, root: Path | None, namespace: str | None = None) -> Path:
    storage = resolve_city_storage(city_id, root)
    resolved = _resolve_no_strict(path)
    base = getattr(storage, namespace) if namespace else storage.city_root
    if not _is_relative_to(resolved, base):
        raise StorageNamespaceMismatchError(f"Path is outside {city_id}/{namespace or ''} namespace")
    _reject_reparse_ancestors(resolved, storage.root)
    return resolved


def initialize_storage(root: Path) -> dict[str, Any]:
    resolved_root = _resolve_root(root)
    resolved_root.mkdir(parents=True, exist_ok=True)
    catalog_dir = _safe_child(resolved_root, "catalog")
    catalog_dir.mkdir(exist_ok=True)

    cities = []
    for city_id in CITY_ORDER:
        storage = resolve_city_storage(city_id, resolved_root)
        storage.city_root.mkdir(exist_ok=True)
        for namespace in STORAGE_NAMESPACES:
            getattr(storage, namespace).mkdir(exist_ok=True)
        _write_marker(storage)
        cities.append(_catalog_item_with_storage(city_id))

    catalog = {
        "schema_version": "1.0",
        "cities": cities,
    }
    atomic_write_json(catalog_dir / "cities.json", catalog)
    _write_readme(resolved_root)
    return validate_storage(root)


def validate_storage(root: Path) -> dict[str, Any]:
    resolved_root = _resolve_root(root)
    issues = []
    if not resolved_root.exists() or not resolved_root.is_dir():
        issues.append({"error_code": "CITY_STORAGE_ROOT_MISSING", "path": str(resolved_root)})
    profile_issues = validate_city_profiles()
    issues.extend(profile_issues)
    for city_id in CITY_ORDER:
        try:
            storage = resolve_city_storage(city_id, resolved_root)
            if storage.city_root.name != city_id:
                issues.append({"city_id": city_id, "error_code": "CITY_STORAGE_NAMESPACE_MISMATCH"})
            for namespace in STORAGE_NAMESPACES:
                path = getattr(storage, namespace)
                if not path.exists() or not path.is_dir():
                    issues.append({"city_id": city_id, "namespace": namespace, "error_code": "CITY_STORAGE_NAMESPACE_MISSING"})
                elif _has_reparse_point(path):
                    issues.append({"city_id": city_id, "namespace": namespace, "error_code": "CITY_STORAGE_ESCAPE"})
        except StorageError as exc:
            issues.append({"city_id": city_id, "error_code": exc.error_code})
    catalog_path = resolved_root / "catalog" / "cities.json"
    if not catalog_path.exists():
        issues.append({"error_code": "CITY_CATALOG_MISSING"})
    return {
        "root": str(resolved_root),
        "city_count": len(CITY_ORDER),
        "valid": not issues,
        "issues": issues,
        "catalog_path": str(catalog_path),
    }


def _catalog_item_with_storage(city_id: str) -> dict[str, Any]:
    item = next(i for i in city_catalog_items() if i["city_id"] == city_id)
    return item


def _write_marker(storage: CityStorage):
    marker = {
        "schema_version": "1.0",
        "city_id": storage.city_id,
        "storage_namespace": storage.city_id,
        "namespaces": list(STORAGE_NAMESPACES),
        "private_local_only": True,
        "contains_business_data": False,
    }
    atomic_write_json(storage.city_root / MARKER_NAME, marker)


def _write_readme(root: Path):
    readme = root / "README.md"
    if readme.exists():
        return
    text = (
        "# Finance Data Root\n\n"
        "This directory is outside the Git repository and stores city-isolated local finance data namespaces.\n\n"
        "Do not commit, copy, archive, or process real finance files automatically from this location.\n"
    )
    readme.write_text(text, encoding="utf-8")


def _resolve_root(root: Path) -> Path:
    resolved = _resolve_no_strict(root)
    if any(part == ".." for part in root.parts):
        raise StorageEscapeError("Data root must not contain path traversal")
    _reject_reparse_ancestors(resolved, resolved)
    return resolved


def _safe_child(parent: Path, name: str) -> Path:
    candidate = parent / name
    resolved = _resolve_no_strict(candidate)
    if Path(name).is_absolute() or any(part in {"..", ""} for part in Path(name).parts):
        raise StorageEscapeError(f"Unsafe namespace path: {name}")
    if not _is_relative_to(resolved, parent):
        raise StorageEscapeError(f"Namespace escapes storage root: {name}")
    return resolved


def _resolve_no_strict(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def _is_relative_to(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def _reject_reparse_ancestors(path: Path, root: Path):
    current = root
    if _has_reparse_point(current):
        raise StorageEscapeError(f"Reparse point rejected: {current}")
    try:
        relative_parts = path.relative_to(root).parts
    except ValueError as exc:
        raise StorageEscapeError("Path escapes storage root") from exc
    for part in relative_parts:
        current = current / part
        if current.exists() and _has_reparse_point(current):
            raise StorageEscapeError(f"Reparse point rejected: {current}")


def _has_reparse_point(path: Path) -> bool:
    if path.is_symlink():
        return True
    if os.name == "nt" and path.exists():
        return bool(path.stat().st_file_attributes & getattr(__import__("stat"), "FILE_ATTRIBUTE_REPARSE_POINT", 0))
    return False
