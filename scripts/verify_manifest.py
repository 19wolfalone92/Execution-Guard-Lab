#!/usr/bin/env python3
"""Verify a SHA-256 manifest without extracting or following unsafe paths."""
from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath
import sys

ROOT = Path(__file__).resolve().parents[1]


def verify(manifest: Path) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    try:
        lines = manifest.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return [f"cannot_read_manifest:{type(exc).__name__}"]
    checked = 0
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            digest, rel = line.split("  ", 1)
        except ValueError:
            errors.append(f"line_{number}:invalid_format")
            continue
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            errors.append(f"line_{number}:invalid_sha256")
            continue
        path = PurePosixPath(rel)
        if path.is_absolute() or ".." in path.parts or not path.parts:
            errors.append(f"line_{number}:unsafe_path")
            continue
        if rel in seen:
            errors.append(f"line_{number}:duplicate_path")
            continue
        seen.add(rel)
        candidate = ROOT / Path(*path.parts)
        if candidate.is_symlink():
            errors.append(f"line_{number}:symlink_not_allowed:{rel}")
            continue
        target = candidate.resolve()
        if ROOT not in target.parents or not target.is_file():
            errors.append(f"line_{number}:missing_or_unsafe_file:{rel}")
            continue
        actual = hashlib.sha256(target.read_bytes()).hexdigest()
        checked += 1
        if actual != digest:
            errors.append(f"line_{number}:sha256_mismatch:{rel}")
    if not checked:
        errors.append("manifest_has_no_verified_files")
    if errors:
        return errors
    print(f"PASS: {manifest.name}: {checked}/{len(seen)} SHA-256 entries verified")
    return []


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python scripts/verify_manifest.py MANIFEST.sha256", file=sys.stderr)
        return 2
    errors = verify((ROOT / sys.argv[1]).resolve())
    for error in errors:
        print(error, file=sys.stderr)
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
