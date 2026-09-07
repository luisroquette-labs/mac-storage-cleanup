# Changelog

All notable changes to this product are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] - 2026-09-07

### Added
- `scan_deep.py` — read-only, pressure-tiered scanner. Reports disk usage as
  one of five tiers (tranquilo <75%, atenção 75-85%, aperto 85-93%, crítico
  93-97%, emergência >97%) and walks the full home tree — including
  dotfolders (`.codex`, `.claude`, `.npm`, `.vscode`, ...) — for artifact
  directories instead of a fixed known-junk list. Classifies every hit into
  `auto_safe`, `needs_review`, `live_project`, `referenced_by_symlink`, or
  `skip_active`, and prints the exact ready-to-run `safe_generated_cleanup.py
  --dry-run` command for the safe bucket. At crítico/emergência tiers it also
  flags user-owned processes over 80% CPU with more than an hour elapsed as
  runaway candidates (never killed automatically).
- `safe_generated_cleanup.py` now recognizes 12 generated-artifact directory
  names across five ecosystems instead of two: `.next`, `node_modules`,
  `dist`, `build`, `target`, `.venv`, `venv`, `.turbo`, `.parcel-cache`,
  `.pytest_cache`, `.gradle`, `Pods` (JS/TS, Python, Rust, Java/Gradle, iOS).
- `--allow-live-project` flag — required to delete a target whose project
  root is not a git worktree or scratch checkout, so a continuously
  developed main repo is never swept into an unattended `--apply` just
  because its dev server happened to be stopped.
- `--allow-breaking-symlinks` flag and exit code `5` — refuses to delete a
  target that another git worktree's own `node_modules`/`.next`/etc. is
  symlinked to, closing a real incident where deleting a stale worktree's
  real directory silently broke a sibling worktree pointing at it.
- Exit code `6` — an approved target vanished (removed by a concurrent
  process) between validation and staging; nothing is touched, rerun the
  scan.
- Manifest boundary detection expanded from npm-only (`package.json` +
  lockfiles) to 15 manifest files across JS/Python/Rust/Java/iOS
  (`Cargo.toml`, `requirements.txt`, `pyproject.toml`, `setup.py`,
  `Pipfile`, `build.gradle`, `build.gradle.kts`, `pom.xml`, `Podfile`, ...).
- This CHANGELOG and Semantic Versioning tags (`v1.0.0`, `v1.1.0`).
- Unpacked `mac-storage-cleanup/` source tree tracked in git alongside the
  `.skill` zip, so future changes are reviewable as a diff instead of only
  a binary artifact.

### Fixed
- **TOCTOU crash on `du -sh`.** A concurrent process (git worktree prune, a
  build tool's own cleanup) could remove a target between discovery and
  sizing, crashing the whole scan mid-run with a raw traceback. Both
  `scan_deep.py` (returns `None`, skips the entry) and
  `safe_generated_cleanup.py` (prints an error and returns exit code 6)
  now treat "target vanished mid-run" as an expected race, not a crash.
- **TOCTOU crash on manifest hashing.** `sha256()` could raise
  `FileNotFoundError`/`PermissionError` if a manifest file (e.g.
  `package.json`) disappeared between the `is_file()` check and the actual
  read (mid `npm install` rewrite, worktree deleted concurrently). Now
  caught and treated as "no manifest here", matching the existing
  empty-hash sentinel used everywhere else in the script.
- **Process-match false negatives.** Exact process-name matching missed
  versioned interpreters (`python3.11`, `python3.12`) and renamed
  long-running children (Next.js's own server process reports as
  `next-server`, not `next` — confirmed live against a running dev server).
  Matching now uses prefix rules instead of an exact-name set, while still
  excluding unrelated processes that happen to start with the same
  substring (e.g. `nextcloud` no longer false-matches `next`).
- **`project_root()` unbounded outside `$HOME`.** For an external-disk move
  (no `$HOME` anchor to stop at), the ancestor walk could climb all the way
  to `/` and mis-attribute an unrelated ancestor directory as the project
  root if it happened to contain a manifest file. Capped to 6 levels when
  the target is outside `$HOME`.
- **APFS filename length limit.** Deeply nested monorepo/Vercel-function
  paths, once flattened into a single staging filename, could exceed
  APFS's 255-byte single-component limit and fail with `ENAMETOOLONG`.
  Staging names longer than 200 bytes are now SHA-256-truncated.

### Changed
- `SKILL.md` rewritten around the new pressure-tiered, wider-scope workflow:
  when to run `scan_deep.py` first, how the five-bucket classification maps
  to approval requirements, and the full exit-code table (`2`/`3`/`4`/`5`/`6`).
- `README.md` "Core architecture" and "Quick usage" sections updated to
  describe the expanded artifact scope and the two-script workflow
  (`scan_deep.py` for discovery, `safe_generated_cleanup.py` for the
  destructive step) instead of implying a single fixed `.next`/`node_modules`
  target list.

## [1.0.0] - 2026-08-14

Initial public release. See the [v1.0.0 tag](../../releases/tag/v1.0.0) for
the full snapshot: guard-first cleanup workflow scoped to `.next` and
`node_modules`, dry-run hard gate, active-process and manifest/hash
boundary checks, recoverable `~/.Trash` staging, and the duplicate-file
discovery tool.

[1.1.0]: ../../compare/v1.0.0...v1.1.0
[1.0.0]: ../../releases/tag/v1.0.0
