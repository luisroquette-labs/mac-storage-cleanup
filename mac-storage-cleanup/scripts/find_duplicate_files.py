#!/usr/bin/env python3
"""Report byte-identical files without modifying anything."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import unicodedata
from collections import defaultdict
from pathlib import Path

def protected(path: Path, extra: tuple[Path, ...]) -> bool:
    resolved = path.resolve()
    normalized = unicodedata.normalize("NFD", str(resolved)).casefold()
    parts = normalized.rstrip("/").split("/")
    if len(parts) >= 2 and parts[-2:] == ["warning", "default"]:
        return True
    return any(normalized == str(p).casefold() or normalized.startswith(str(p).casefold() + "/") for p in extra)


def digest(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def iter_files(root: Path, extra: tuple[Path, ...]):
    """Walk without entering protected directories or following symlinks."""
    for current, dirs, files in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        dirs[:] = [name for name in dirs if not protected(current_path / name, extra)]
        for name in files:
            path = current_path / name
            if not path.is_symlink():
                yield path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("roots", nargs="+", type=Path)
    parser.add_argument("--min-size", type=int, default=1, help="ignore files smaller than this many bytes")
    parser.add_argument("--protect", action="append", default=[], type=Path, help="additional protected path; repeatable")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()
    extra_protected = tuple(path.expanduser().resolve() for path in args.protect)

    by_size: dict[int, list[Path]] = defaultdict(list)
    for raw_root in args.roots:
        root = raw_root.expanduser().resolve()
        if protected(root, extra_protected):
            raise SystemExit(f"ERRO: caminho protegido: {root}")
        if root.is_file():
            candidates = [root]
        elif root.is_dir():
            candidates = iter_files(root, extra_protected)
        else:
            raise SystemExit(f"ERRO: caminho ausente: {root}")
        for path in candidates:
            try:
                size = path.stat().st_size
            except OSError:
                continue
            if size >= args.min_size and not protected(path, extra_protected):
                by_size[size].append(path)

    groups: dict[str, list[str]] = defaultdict(list)
    for paths in by_size.values():
        if len(paths) < 2:
            continue
        for path in paths:
            groups[digest(path)].append(str(path))
    duplicates = {key: sorted(value) for key, value in groups.items() if len(value) > 1}
    if args.as_json:
        print(json.dumps(duplicates, ensure_ascii=False, indent=2))
    else:
        if not duplicates:
            print("Nenhuma duplicata exata encontrada.")
        for key, paths in sorted(duplicates.items()):
            print(f"DUPLICATA {key}")
            for path in paths:
                print(f"  {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
