#!/usr/bin/env python3
"""Safely stage approved generated-artifact directories for Finder deletion.

Covers node_modules/.next/dist/build/target/.venv/venv/.turbo/.parcel-cache/
.pytest_cache/.gradle/Pods — anything else is rejected.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import unicodedata
from pathlib import Path

ALLOWED_NAMES = {
    ".next", "node_modules", "dist", "build", "target",
    ".venv", "venv", ".turbo", ".parcel-cache", ".pytest_cache", ".gradle", "Pods",
}
# Exact-name matching misses versioned interpreters (python3.11, python3.12) and
# renamed long-running children (Next.js's own server process shows as
# "next-server", not "next" — confirmed live via `ps aux` against a real
# coesasolar-site dev server while building this script).
PROCESS_NAME_PREFIXES = (
    "node", "npm", "npx", "bun", "deno", "tsx", "vite", "vitest", "next",
    "webpack", "turbo", "electron", "python", "uv", "ruby", "java",
    "cargo", "rustc", "gradle", "xcodebuild", "pod",
)
# These attach version numbers directly with no separator (python3, python3.11,
# java11) — a bare prefix match is needed, but ONLY for these: a bare match on
# "next" would also catch the unrelated Nextcloud client ("nextcloud").
DIRECT_VERSION_SUFFIX_PREFIXES = ("python", "ruby", "java")


def _matches_tool(executable_name: str) -> bool:
    for prefix in PROCESS_NAME_PREFIXES:
        if executable_name == prefix or executable_name.startswith(prefix + "-") or executable_name.startswith(prefix + "."):
            return True
    for prefix in DIRECT_VERSION_SUFFIX_PREFIXES:
        if executable_name.startswith(prefix) and (
            len(executable_name) == len(prefix) or executable_name[len(prefix)].isdigit()
        ):
            return True
    return False


# A manifest + no running process only means "regenerable", not "abandoned".
# The user's main, continuously-developed repos pass that same test the
# instant their dev server happens to be stopped — nuking their
# node_modules/.next is disruptive even though nothing is technically lost.
# Only throwaway checkouts (git worktrees, scratch dirs) are safe without an
# explicit override. This is the canonical definition — scan_deep.py imports
# it from here rather than duplicating it, so there is exactly one place a
# direct `--apply` call (bypassing the scanner entirely) still gets checked.
WORKTREE_PATTERN = re.compile(r"(^|/)(\.?worktrees|[^/]+-worktrees)(/|$)")
MANIFEST_NAMES = (
    "package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "bun.lock", "bun.lockb",
    "Cargo.toml", "requirements.txt", "pyproject.toml", "setup.py", "Pipfile",
    "build.gradle", "build.gradle.kts", "pom.xml", "Podfile",
)


def looks_like_worktree(path: Path) -> bool:
    relative = str(path.relative_to(Path.home())) if path.is_relative_to(Path.home()) else str(path)
    return bool(WORKTREE_PATTERN.search(relative)) or relative.startswith(".claude-scratch/")


def _worktree_container_roots() -> list[Path]:
    """Top-level directories that hold worktree checkouts as children —
    where one worktree's node_modules/.next commonly symlinks to a sibling's
    to skip reinstalling. Bounded on purpose: this is not a $HOME walk."""
    home = Path.home()
    roots = []
    try:
        entries = list(home.iterdir())
    except OSError:
        return roots
    for entry in entries:
        if entry.is_symlink() or not entry.is_dir():
            continue
        if entry.name == ".codex" and (entry / "worktrees").is_dir():
            roots.append(entry / "worktrees")
        elif entry.name.endswith("-worktrees") or entry.name in (".worktrees", ".claude-scratch"):
            roots.append(entry)
        elif (entry / ".worktrees").is_dir():
            roots.append(entry / ".worktrees")
    return roots


def find_worktree_symlinks() -> dict[Path, list[Path]]:
    """One bounded walk of worktree-container directories, mapping each
    live symlink's resolved target back to the symlink(s) pointing at it.
    A real incident (2026-09-06): deleting a stale worktree's real
    node_modules silently broke a sibling worktree whose own node_modules
    was a symlink to it — `--apply`'s own checks (manifest, no active
    process, not itself a symlink) never look at what points *at* the
    target, only at the target itself. This lets `--apply` refuse instead.

    Depth-capped at container/worktree/[subproject/]{name} — the deepest
    real pattern observed, in a monorepo-style worktree. Every directory
    that gets pushed for further recursion still gets its own entries
    inspected once it's popped, so capping *pushes* at depth 2 still finds
    a symlink sitting directly inside a depth-2 subproject dir; it just
    never descends into that subproject's actual source tree (src/,
    components/, ...) looking for more. An unbounded walk does exactly
    that across every worktree's real source files — measured at 27s
    against ~100 real worktrees; capped this way, well under a second."""
    reverse: dict[Path, list[Path]] = {}
    for root in _worktree_container_roots():
        stack = [(root, 0)]
        while stack:
            current, depth = stack.pop()
            try:
                entries = list(current.iterdir())
            except OSError:
                continue
            for entry in entries:
                if entry.is_symlink():
                    if entry.name in ALLOWED_NAMES:
                        try:
                            resolved = entry.resolve()
                        except OSError:
                            continue
                        reverse.setdefault(resolved, []).append(entry)
                    continue
                if depth < 2 and entry.is_dir() and entry.name not in ALLOWED_NAMES and entry.name != ".git":
                    stack.append((entry, depth + 1))
    return reverse


def sha256(path: Path) -> str:
    # A gap between the is_file() check and the actual open() is a real risk
    # on this filesystem specifically — confirmed live (2026-09-06): `du`
    # crashed the whole deep scan when a target vanished mid-walk from a
    # concurrent process. A manifest file disappearing between check and
    # read (mid `npm install` rewrite, worktree deleted concurrently) is the
    # same race. Treat "gone" as "unhashable", not a crash — callers already
    # handle an empty digest as "no manifest here" via manifest_hashes().
    digest = hashlib.sha256()
    if path.is_file():
        try:
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
        except (FileNotFoundError, PermissionError):
            digest = hashlib.sha256()  # discard any partial read — same sentinel as never having existed
    return digest.hexdigest()


def process_matches(project: Path) -> list[str]:
    result = subprocess.run(
        ["ps", "ax", "-o", "pid=,comm=,command="],
        check=True,
        capture_output=True,
        text=True,
    )
    matches = []
    for line in result.stdout.splitlines():
        fields = line.strip().split(None, 2)
        if len(fields) != 3:
            continue
        pid_text, _comm, command = fields
        if pid_text.isdigit() and int(pid_text) == os.getpid():
            continue
        # macOS `comm=` can be truncated (for example `/Library/Framewo`).
        # Use argv[0] from the full command line instead.
        argv0 = command.split(None, 1)[0]
        executable_name = argv0.rsplit("/", 1)[-1].casefold()
        project_text = str(project)
        path_reference = (
            f"{project_text}/" in command
            or f"'{project_text}'" in command
            or f'"{project_text}"' in command
            or command == project_text
        )
        if _matches_tool(executable_name) and path_reference:
            matches.append(line.strip())
    return matches


def normalized(path: Path) -> str:
    return unicodedata.normalize("NFD", str(path.resolve())).casefold().rstrip("/")


def reject_protected(path: Path, extra: tuple[Path, ...]) -> None:
    resolved = path.resolve()
    path_text = normalized(resolved)
    parts = path_text.split("/")
    if len(parts) >= 2 and parts[-2:] == ["warning", "default"]:
        raise ValueError(f"caminho protegido por regra Warning/Default: {resolved}")
    for protected in extra:
        protected_text = normalized(protected)
        if path_text == protected_text or path_text.startswith(protected_text + "/"):
            raise ValueError(f"caminho protegido: {resolved}")


def project_root(target: Path) -> Path:
    current = target.parent
    # Outside $HOME (e.g. an external-disk move) there is no "stop at home"
    # anchor, so an unbounded walk could climb all the way to "/" and
    # mis-attribute an unrelated ancestor as the project root if it happens
    # to contain a manifest file. Cap it to a few levels in that case.
    max_steps = None if target.is_relative_to(Path.home()) else 6
    steps = 0
    while current != current.parent:
        if target.is_relative_to(Path.home()) and current == Path.home():
            break
        if max_steps is not None and steps >= max_steps:
            break
        if any((current / name).is_file() for name in MANIFEST_NAMES):
            return current
        current = current.parent
        steps += 1
    return target.parent


def manifest_hashes(root: Path) -> dict[str, str]:
    return {str(root / name): sha256(root / name) for name in MANIFEST_NAMES if (root / name).is_file()}


def free_bytes() -> int:
    return shutil.disk_usage(Path.home()).free


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    parser.add_argument("--protect", action="append", default=[], type=Path, help="additional protected path; repeatable")
    parser.add_argument(
        "--allow-live-project", action="store_true",
        help="required to delete a target whose project root is not a git worktree or scratch checkout",
    )
    parser.add_argument(
        "--allow-breaking-symlinks", action="store_true",
        help="required to delete a target that another worktree's node_modules/.next symlinks to",
    )
    parser.add_argument("targets", nargs="+", type=Path)
    args = parser.parse_args()
    extra_protected = tuple(path.expanduser().resolve() for path in args.protect)

    targets = []
    for raw in args.targets:
        raw_target = raw.expanduser()
        if raw_target.is_symlink():
            raise ValueError(f"alvo é link simbólico: {raw_target}")
        target = raw_target.resolve()
        reject_protected(target, extra_protected)
        if target.name not in ALLOWED_NAMES:
            raise ValueError(f"somente .next/node_modules são aceitos: {target}")
        if not target.is_dir() or target.is_symlink():
            raise ValueError(f"alvo não é diretório real: {target}")
        if target not in targets:
            targets.append(target)

    projects = {project_root(target) for target in targets}

    if not args.allow_live_project:
        live_projects = sorted(p for p in projects if not looks_like_worktree(p))
        if live_projects:
            print("ERRO: alvo(s) fora de worktree/scratch descartável — repo principal, não abandonado:", file=sys.stderr)
            for p in live_projects:
                print(f"  {p}", file=sys.stderr)
            print("Rode de novo com --allow-live-project se isso é intencional.", file=sys.stderr)
            return 4

    if not args.allow_breaking_symlinks:
        symlink_index = find_worktree_symlinks()
        referenced = [(t, links) for t in targets if (links := symlink_index.get(t))]
        if referenced:
            print("ERRO: alvo(s) ainda referenciado(s) por symlink de outra worktree:", file=sys.stderr)
            for target, links in referenced:
                for link in links:
                    print(f"  {target} <- {link}", file=sys.stderr)
            print(
                "Apagar isso quebra a worktree que aponta pra cá (vai precisar reinstalar). "
                "Rode de novo com --allow-breaking-symlinks se isso é intencional.",
                file=sys.stderr,
            )
            return 5

    active = [line for project in projects for line in process_matches(project)]
    if active:
        print("ERRO: processos ativos encontrados; limpeza bloqueada:", file=sys.stderr)
        print("\n".join(active), file=sys.stderr)
        return 2

    records = []
    for target in targets:
        root = project_root(target)
        records.append((target, root, manifest_hashes(root)))

    for target, root, hashes in records:
        print(f"APROVADO: {target} ({root})")
        # Same race as scan_deep.py hit live (2026-09-06): a concurrent
        # process can remove a target between validation above and this
        # display step. Nothing has been moved yet at this point, so it's
        # safe to just stop cleanly instead of a raw traceback.
        try:
            size = subprocess.check_output(["du", "-sh", str(target)], text=True, stderr=subprocess.DEVNULL).split()[0]
        except (subprocess.CalledProcessError, FileNotFoundError, IndexError):
            print(f"ERRO: alvo desapareceu antes de ser processado (corrida com outro processo): {target}", file=sys.stderr)
            return 6
        print(f"  tamanho: {size}")
        if hashes:
            print(f"  manifestos preservados: {len(hashes)}")
        else:
            print("  AVISO: nenhum manifesto no limite detectado; confirme o limite do projeto.")

    if args.dry_run:
        print(f"ESPAÇO LIVRE ATUAL: {free_bytes()} bytes")
        print("DRY-RUN: nenhum arquivo alterado.")
        return 0

    # Recheck immediately before the destructive move to reduce process races.
    active = [line for project in projects for line in process_matches(project)]
    if active:
        print("ERRO: processos iniciaram após a prévia; nada foi movido:", file=sys.stderr)
        print("\n".join(active), file=sys.stderr)
        return 2

    free_before = free_bytes()
    trash = Path.home() / ".Trash"
    staging = trash / f"mac-storage-cleanup-{time.strftime('%Y%m%d-%H%M%S')}"
    staging.mkdir(parents=False)
    try:
        for target, _root, _hashes in records:
            relative = target.name if target.parent == Path.home() else str(target).lstrip("/").replace("/", "__")
            # APFS caps a single filename component at 255 bytes. Deeply
            # nested monorepo/Vercel-function paths flatten into names long
            # enough to get close (~150 bytes observed in practice) — hash-
            # truncate before that becomes ENAMETOOLONG.
            if len(relative.encode()) > 200:
                digest = hashlib.sha256(relative.encode()).hexdigest()[:16]
                relative = f"{relative[:150]}__{digest}"
            destination = staging / relative
            shutil.move(str(target), str(destination))

        # Never ask Finder to delete a staging folder while any source target
        # or protected manifest has not reached the expected pre-delete state.
        for target, _root, hashes in records:
            if target.exists():
                raise RuntimeError(f"alvo ainda existe antes do Finder: {target}")
            for manifest, expected in hashes.items():
                if sha256(Path(manifest)) != expected:
                    raise RuntimeError(f"manifesto mudou antes do Finder: {manifest}")

        subprocess.run(["osascript", "-e", f'tell application "Finder" to delete POSIX file "{staging}"'], check=True)
        if staging.exists():
            raise RuntimeError(f"Finder não removeu a preparação; mantida para recuperação: {staging}")
    except Exception:
        print(f"ERRO: staging mantido para recuperação: {staging}", file=sys.stderr)
        return 3

    for target, root, hashes in records:
        if target.exists():
            raise RuntimeError(f"alvo ainda existe: {target}")
        for manifest, expected in hashes.items():
            if sha256(Path(manifest)) != expected:
                raise RuntimeError(f"manifesto mudou: {manifest}")
    freed = max(0, free_bytes() - free_before)
    print(json.dumps({"status": "applied", "targets": len(records), "free_bytes_delta": freed}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError) as error:
        print(f"ERRO: {error}", file=sys.stderr)
        raise SystemExit(1)
