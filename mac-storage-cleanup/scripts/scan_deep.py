#!/usr/bin/env python3
"""Pressure-tiered deep scan for hidden generated-artifact directories.

Read-only. Never deletes anything — classifies candidates and prints the
exact `safe_generated_cleanup.py --apply` command for the ones confirmed
safe. Widens scope as disk pressure rises: no directory is excluded from
discovery just for being a dotfolder (that blind spot is what let 56G of
stale node_modules hide in ~/.codex/worktrees undetected).
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from safe_generated_cleanup import (  # noqa: E402
    ALLOWED_NAMES, find_worktree_symlinks, looks_like_worktree, manifest_hashes,
    process_matches, project_root, reject_protected,
)

# Directories that are never artifact discovery targets themselves. Two
# different reasons live here, don't conflate them:
#   - noise/danger: Library, .Trash, .git internals.
#   - live tool infrastructure, not a disposable project checkout: deleting
#     node_modules/__pycache__ *inside* a running tool's own runtime cache
#     (.9router, .npm, .cache/codex-runtimes, .claude, .vscode) can break that
#     tool. This is deliberately narrower than the old blanket dotfolder
#     exclusion — `.codex` itself and any `*worktrees*` directory stay IN
#     scope, because that's exactly where stale project checkouts hide.
SKIP_DIR_NAMES = {
    ".git", ".Trash", "Library",
    ".9router", ".npm", ".npm-global", ".cache", ".claude", ".vscode",
}

TIERS = [
    (0, 75, "tranquilo"),
    (75, 85, "atenção"),
    (85, 93, "aperto"),
    (93, 97, "crítico"),
    (97, 101, "emergência"),
]


def tier_for(percent_used: float) -> str:
    for low, high, label in TIERS:
        if low <= percent_used < high:
            return label
    return "emergência"


def disk_percent_used(path: Path) -> float:
    usage = shutil.disk_usage(path)
    return usage.used / (usage.used + usage.free) * 100


def find_candidates(root: Path, protected: tuple[Path, ...]) -> list[Path]:
    found = []
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            entries = list(current.iterdir())
        except (PermissionError, OSError):
            continue
        for entry in entries:
            if entry.is_symlink():
                continue
            if not entry.is_dir():
                continue
            if entry.name in SKIP_DIR_NAMES:
                continue
            try:
                reject_protected(entry, protected)
            except ValueError:
                continue
            if entry.name in ALLOWED_NAMES:
                found.append(entry)
                continue  # don't descend into a matched artifact dir
            stack.append(entry)
    return found


def classify(target: Path, symlink_index: dict[Path, list[Path]]) -> dict | None:
    # A full-home scan takes long enough (minutes, against ~100+ worktrees)
    # that the filesystem keeps changing underneath it — another process
    # (git worktree prune, a build tool's own cleanup) can remove a
    # candidate between discovery and classification. Confirmed live: `du`
    # crashed the whole scan mid-run when exactly this happened. Nothing to
    # report on a target that's already gone — skip it, don't crash.
    if not target.exists():
        return None
    root = project_root(target)
    try:
        size = subprocess.check_output(["du", "-sh", str(target)], text=True, stderr=subprocess.DEVNULL).split()[0]
    except (subprocess.CalledProcessError, FileNotFoundError, IndexError):
        return None
    hashes = manifest_hashes(root)
    active = process_matches(root)
    referencing = symlink_index.get(target, [])
    if active:
        status = "skip_active"
    elif referencing:
        # Matches safe_generated_cleanup.py --apply's own reverse-symlink
        # guard exactly, so a bucket printed here as auto_safe is genuinely
        # appliable as-is — see that script's find_worktree_symlinks for the
        # 2026-09-06 incident this closes.
        status = "referenced_by_symlink"
    elif not looks_like_worktree(root):
        status = "live_project"  # regenerable, but this is a main repo — never bundle into apply
    elif hashes:
        status = "auto_safe"
    else:
        status = "needs_review"
    return {
        "path": str(target),
        "root": str(root),
        "size": size,
        "status": status,
        "manifests": len(hashes),
        "referenced_by": [str(link) for link in referencing],
    }


def runaway_processes() -> list[str]:
    result = subprocess.run(["ps", "-Ao", "pid,user,%cpu,etime,comm"], check=True, capture_output=True, text=True)
    flagged = []
    for line in result.stdout.splitlines()[1:]:
        parts = line.split(None, 4)
        if len(parts) != 5:
            continue
        pid, user, cpu, etime, comm = parts
        try:
            cpu_val = float(cpu.replace(",", "."))
        except ValueError:
            continue
        # Only user-owned processes are ours to flag/kill; root daemons
        # (WindowServer, fseventsd, mobileassetd...) are expected to run hot.
        if user == "root" or cpu_val < 80:
            continue
        if "-" not in etime and ":" in etime and etime.count(":") == 1:
            continue  # under an hour, not yet suspicious
        flagged.append(f"PID {pid} ({user}) {cpu}% CPU, elapsed {etime}: {comm}")
    return flagged


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protect", action="append", default=[], type=Path)
    parser.add_argument("--root", type=Path, default=Path.home())
    args = parser.parse_args()
    args.root = args.root.expanduser().resolve()
    protected = tuple(p.expanduser().resolve() for p in args.protect)

    percent = disk_percent_used(args.root)
    tier = tier_for(percent)
    print(f"PRESSÃO DE DISCO: {percent:.1f}% usado — nível: {tier}")

    if tier == "tranquilo":
        print("Abaixo do limiar de varredura profunda (75%). Nada a fazer.")
        return 0

    print(f"\nVarrendo {args.root} por diretórios de artefato (sem excluir dotfolders)...")
    candidates = find_candidates(args.root, protected)
    symlink_index = find_worktree_symlinks()
    results = [r for c in candidates if (r := classify(c, symlink_index)) is not None]
    results.sort(key=lambda r: r["path"])

    auto_safe = [r for r in results if r["status"] == "auto_safe"]
    needs_review = [r for r in results if r["status"] == "needs_review"]
    skip_active = [r for r in results if r["status"] == "skip_active"]
    live_project = [r for r in results if r["status"] == "live_project"]
    referenced = [r for r in results if r["status"] == "referenced_by_symlink"]

    for label, bucket in (
        ("AUTO-SEGURO (worktree/scratch descartável)", auto_safe),
        ("PRECISA REVISÃO", needs_review),
        ("REPO PRINCIPAL — regenerável, mas NUNCA auto-aplicar", live_project),
        ("REFERENCIADO POR SYMLINK DE OUTRA WORKTREE — apagar quebra quem aponta pra cá", referenced),
        ("PULADO (processo ativo)", skip_active),
    ):
        if not bucket:
            continue
        print(f"\n=== {label} ({len(bucket)}) ===")
        for r in bucket:
            print(f"  {r['size']:>8}  {r['path']}")
            for link in r.get("referenced_by", []):
                print(f"             <- {link}")

    if auto_safe:
        paths = " ".join(f'"{r["path"]}"' for r in auto_safe)
        print("\nComando pronto (dry-run primeiro, sempre):")
        print(f"python3 {Path(__file__).parent / 'safe_generated_cleanup.py'} --dry-run {paths}")

    if tier in ("crítico", "emergência"):
        flagged = runaway_processes()
        if flagged:
            print(f"\n=== PROCESSOS SUSPEITOS DE CPU TRAVADA ({len(flagged)}) ===")
            for line in flagged:
                print(f"  {line}")
            print("Não mato automaticamente — confirme antes de `kill`.")

    print(json.dumps({"tier": tier, "percent_used": round(percent, 1), "auto_safe": len(auto_safe),
                       "needs_review": len(needs_review), "live_project": len(live_project),
                       "referenced_by_symlink": len(referenced), "skip_active": len(skip_active)}))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except OSError as error:
        # Matches safe_generated_cleanup.py's own top-level guard — mainly
        # covers a bad --root (disk_percent_used raises if it doesn't exist).
        print(f"ERRO: {error}", file=sys.stderr)
        raise SystemExit(1)
