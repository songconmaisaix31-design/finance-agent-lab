import hashlib
import json
import os
from datetime import datetime
from pathlib import Path


def sha256_file(filepath: str) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def file_info(filepath: str) -> dict:
    path = Path(filepath)
    stat = path.stat()
    return {
        "name": path.name,
        "path": str(path.resolve()),
        "size_bytes": stat.st_size,
        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        "sha256": sha256_file(filepath),
    }


def create_manifest(input_files: list[str], output_dir: str) -> dict:
    entries = {}
    for fp in input_files:
        entries[os.path.basename(fp)] = file_info(fp)
    manifest = {
        "created_at": datetime.now().isoformat(),
        "files": entries,
    }
    manifest_path = os.path.join(output_dir, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    return manifest


def verify_manifest(manifest_path: str) -> dict:
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    results = []
    all_ok = True
    for name, info in manifest["files"].items():
        current_hash = sha256_file(info["path"])
        ok = current_hash == info["sha256"]
        all_ok = all_ok and ok
        results.append({
            "file": name,
            "hash_unchanged": ok,
            "original_hash": info["sha256"],
            "current_hash": current_hash,
        })

    manifest["verified_at"] = datetime.now().isoformat()
    manifest["all_unchanged"] = all_ok
    manifest["verification"] = results

    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    return manifest
