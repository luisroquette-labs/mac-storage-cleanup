---
name: mac-storage-cleanup
description: Safe, evidence-first macOS storage cleanup for project build artifacts, caches, duplicate media, Downloads, Trash, and external-disk moves. Use when the user wants to free Mac SSD space while preserving source code, credentials, memories, project reports, personal media, and explicitly protected folders.
---

# Mac storage cleanup

Use a one-target-at-a-time workflow. Inventory first, classify the target, obtain explicit scope for personal data, make a recoverable change, and verify the result.

## Non-negotiable protections

- Never touch any directory whose path ends in `Warning/Default`; add other protected paths with the script's repeatable `--protect` option.
- Never empty the whole Trash. Delete only an exact staging folder created by this workflow; preserve existing videos and user items.
- Never delete credentials, browser profiles, Claude memory/tool folders, project reports, source files, extensions, or personal media as “cleanup”.
- Do not stop an active project, test, build, Vite/Electron process, or Python worker without current explicit authorization.
- Treat generated-artifact directories (`node_modules`, `.next`, `dist`, `build`, `target`, `.venv`/`venv`, `.turbo`, `.parcel-cache`, `.pytest_cache`, `.gradle`, `Pods`) as removable only after confirming the exact project path, no active process, no symlink, and a lockfile or clear project boundary.
- Prefer moving to `~/.Trash` and then deleting only the exact staging folder through Finder. Do not use `rm -rf`.

## Workflow

1. **Check pressure first.** Run `scripts/scan_deep.py` before anything else. It reads current disk usage and reports a tier: tranquilo (<75%), atenção (75-85%), aperto (85-93%), crítico (93-97%), emergência (>97%). Below 75% treat it as a no-op and fall back to a manual `du -sh` inventory of whatever the user named. At 75%+ it runs a full scan on its own.
2. **No directory is excluded from discovery for being hidden.** `scan_deep.py` walks the entire home tree, dotfolders included (`.codex`, `.claude`, `.npm`, `.vscode`, anything). This closes the exact blind spot that let 56G of stale `node_modules` sit undetected in `~/.codex/worktrees` while a shelf cleaner only ever looked at its fixed known-junk categories. Only `.git`, `.Trash`, `Library`, and `--protect` paths are skipped from the walk — `Library` gets its own separate, manual review (see Special cases), never an automated sweep.
3. **Classify what the scan finds.** A manifest + no running process only proves "regenerable," not "abandoned" — the user's main, continuously-developed repos pass that same test the instant their dev server happens to be stopped. So the scan buckets every hit into five groups: `auto_safe` (inside a git worktree or `.claude-scratch` checkout, manifest confirmed, no active process, nothing else symlinks to it — genuinely throwaway), `live_project` (same manifest/process check, but the path is a main repo, not a worktree — regenerable in principle, but nuking it forces a slow reinstall/rebuild before the next work session, so it never goes in an unattended apply), `referenced_by_symlink` (another worktree's own `node_modules`/`.next`/etc is a symlink pointing at this exact target — deleting it silently breaks that sibling; a real 2026-09-06 incident), `needs_review` (no manifest boundary found), and `skip_active` (a live process references that project root). Higher tiers change how urgently you surface `auto_safe` findings to the user for approval — at crítico/emergência, lead the response with the ready-to-run apply command instead of burying it — but do not change the approval requirement itself: `auto_safe` still needs the user to say go before `--apply` runs, unless they have already given standing authorization for this specific situation. `needs_review`, `live_project`, `referenced_by_symlink`, and `skip_active` always require a human decision. `safe_generated_cleanup.py --apply` enforces the `live_project` and `referenced_by_symlink` checks itself too — the `auto_safe` bucket printed here is exactly what will pass `--apply` cleanly, not merely a suggestion it might still reject.
4. **Apply generated cleanup.** Feed approved paths to `scripts/safe_generated_cleanup.py --dry-run` first, then `--apply`. It checks active processes, symlinks, protected paths, project manifests (now covering JS/Python/Rust/Java/iOS lockfiles, not just npm), and post-move invariants. A single `--apply` call spanning dozens of large targets can hit a Finder `AppleEvent timeout` deleting the staged batch in one shot — if that happens, delete each staged subfolder one at a time instead of retrying the identical bulk call.
5. **At crítico/emergência, also check for CPU pressure.** `scan_deep.py` flags user-owned processes over 80% CPU with >1h elapsed as runaway candidates — a stuck process can itself stall the Finder-deletion step in point 4. Report the candidate and ask before killing; never kill a build/test/Electron process without the user's current, explicit go-ahead.
6. **Classify non-code data separately.** Duplicate media requires SHA-256 equality and explicit approval to remove extras. Personal videos, course files, Downloads, Documents, and `~/Library/Application Support/*` app data require review; do not infer irrelevance from age or name, and never auto-delete these regardless of tier.
7. **Apply duplicate cleanup.** Run `scripts/find_duplicate_files.py` first; retain one canonical file and stage only explicitly approved byte-identical extras. Rehash staged files against their canonical originals before deletion.
8. **Verify.** Confirm targets are absent, staging is gone, source/lockfile hashes are unchanged, Git status is unchanged, protected paths were not accessed, and report `df -h /`. If Finder deletion fails, stop with the staging folder recoverable.

## Special cases

- If a project process recreates dependencies, stop cleanup and report the process; do not fight the process or repeatedly delete its output.
- A closed app window does not prove its dev server is closed. Check `ps` again immediately before moving files.
- For external-disk moves, preserve originals until the copy is verified by size and SHA-256; never move protected `Default` folders.
- For Mail, Photos, iCloud, or browser data, use the application’s own controls and explain synchronization/recovery impact before changing anything.

## Reusable scripts

Run the pressure-tiered scan first — read-only, prints a ready-to-copy dry-run command for whatever it finds:

```bash
python3 scripts/scan_deep.py
python3 scripts/scan_deep.py --protect /absolute/critical/folder
```

Then use the bundled script for generated project artifacts:

```bash
python3 scripts/safe_generated_cleanup.py --dry-run /absolute/project/.next /absolute/project/node_modules
python3 scripts/safe_generated_cleanup.py --apply --protect /absolute/critical/folder /absolute/project/.next /absolute/project/node_modules
```

The script is intentionally narrow: it refuses arbitrary directories, defaults to dry-run, and `--apply` must only be used after the user has approved the exact dry-run targets. It also refuses — in both `--dry-run` and `--apply` — any target whose project root is not a git worktree or `.claude-scratch` checkout, independently of whatever called it; this is what keeps a live main repo safe even if `safe_generated_cleanup.py` is invoked directly instead of through `scan_deep.py`. Pass `--allow-live-project` only when deliberately cleaning a main repo's own cache with the user's current go-ahead.

It also refuses a target that another worktree's `node_modules`/`.next`/etc symlinks to — a real incident (2026-09-06) deleted a stale worktree's real `node_modules` and silently broke a sibling worktree whose own `node_modules` was a symlink to it, since none of the other checks (manifest, active process, target-is-not-itself-a-symlink) look at what points *at* the target. Pass `--allow-breaking-symlinks` only when the referencing worktree is also being retired. Exit code `2` means active processes blocked the operation; `3` means the recoverable staging/Finder step failed; `4` means a target outside a worktree/scratch checkout was rejected; `5` means a target is still referenced by another worktree's symlink; `6` means an approved target vanished (a concurrent process deleted it) before it could be moved — nothing was touched, just rerun the scan.

For duplicate discovery (read-only):

```bash
python3 scripts/find_duplicate_files.py --min-size 1048576 --protect /absolute/critical/folder /absolute/folder
```

This command is read-only. Never turn its output into a deletion list without a second SHA-256 comparison, canonical-file choice, and explicit approval.

## Session evidence

The prior cleanup pattern and protections are summarized in [references/session-pattern.md](references/session-pattern.md). Load it when continuity with this Mac cleanup is needed; do not treat its historical sizes as current inventory.
