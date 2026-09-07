# Mac Storage Cleanup — paid Codex skill

**Current release: [v1.1.0](CHANGELOG.md#110---2026-09-07)** · [Changelog](CHANGELOG.md)

<p align="center">
  <img src="assets/hero.svg" alt="Mac Storage Cleanup hero" width="900">
</p>

<p align="center">
  <strong>From panic deletion to controlled recovery.</strong><br>
  One command path from 90% guesswork to 100% traceability.
</p>

<p align="center">
  <a href="mac-storage-cleanup.skill">Download release</a> ·
  <a href="docs/index.html">Landing page</a> ·
  <a href="#license">Licensing</a> ·
  <a href="docs/index.html#proof">How it proves results</a>
</p>

## 1) What this is

**Mac Storage Cleanup** is a commercial Codex skill built for creators and teams that need macOS cleanup without irreversible mistakes.

It focuses only on the highest-risk storage waste for developers and power users:

- Project artifacts across five ecosystems that can be regenerated
  (`.next`, `node_modules`, `dist`, `build`, `target`, `.venv`, `venv`,
  `.turbo`, `.parcel-cache`, `.pytest_cache`, `.gradle`, `Pods`)
- Exact duplicate files found by hash
- Recovery-safe staging before final cleanup

It is not a generic “delete-everything” utility.  
It is a **guard-first cleanup workflow**.

## 2) Why people pay for it

- You keep running apps, sessions, and project memory intact.
- You remove huge folders with an auditable, deterministic process.
- You get a clear **before/after signal** with size and safety checks.
- You avoid the classic failure: “I cleaned, then something important disappeared.”

## 3) Core architecture (what makes it non-generic)

### A) Dry-run hard gate
Every action starts as read-only analysis.  
You see exact targets, process state, manifest check, and estimated gain before anything can move.

### B) Multi-layer guardrails
- Active process protection (including dev tooling processes)
- Protected paths (`Warning/Default` and explicit `--protect`)
- Manifest/hash boundary validation (`package.json`, lockfiles, etc.)
- No blanket trash operations; everything goes to recoverable staging

### C) Post-action proof
- Manifest checks run again after the move
- Final delta and execution report is printed
- Any protected/inconsistent state aborts the run

### D) Scope discipline
Only exact, named generated-artifact directories are eligible — 12 across
JS/TS, Python, Rust, Java/Gradle, and iOS. No broad folders, no wildcard
cleanups. A target whose project root is a live, continuously developed
repo (not a git worktree or scratch checkout) is refused unless you pass
`--allow-live-project`. A target still symlinked from another worktree is
refused unless you pass `--allow-breaking-symlinks`.

### E) Pressure-tiered discovery
`scan_deep.py` reads current disk usage first and only widens its sweep as
pressure rises (tranquilo/atenção/aperto/crítico/emergência). It walks the
whole home tree, dotfolders included, and classifies every hit before
anything is proposed for deletion — see [CHANGELOG](CHANGELOG.md) for the
full classification rules.

## 4) Installation (2 minutes)

```bash
mkdir -p ~/.codex/skills
unzip -o mac-storage-cleanup.skill -d ~/.codex/skills
shasum -a 256 mac-storage-cleanup.skill
cat SHA256SUMS
```

## 5) Quick usage

Scan first — read-only, prints a ready-to-copy dry-run command for whatever it finds:

```bash
python3 mac-storage-cleanup/scripts/scan_deep.py
python3 mac-storage-cleanup/scripts/scan_deep.py --protect /absolute/critical/folder
```

Then dry-run the approved targets:

```bash
python3 mac-storage-cleanup/scripts/safe_generated_cleanup.py \
  --dry-run /absolute/project/.next /absolute/project/node_modules
```

Apply with explicit safeguards:

```bash
python3 mac-storage-cleanup/scripts/safe_generated_cleanup.py \
  --apply --protect /absolute/critical/folder \
  /absolute/project/.next /absolute/project/node_modules
```

Exit codes: `2` active process blocked the run · `3` recoverable staging/Finder
step failed · `4` target outside a worktree/scratch checkout (pass
`--allow-live-project` if intentional) · `5` target still referenced by
another worktree's symlink (pass `--allow-breaking-symlinks` if intentional)
· `6` an approved target vanished before it could be moved (rerun the scan).

Discover exact duplicates (read-only):

```bash
python3 mac-storage-cleanup/scripts/find_duplicate_files.py \
  --min-size 1048576 --protect /absolute/critical/folder /absolute/folder
```

## 6) What you are buying

### Included in this release package
- Core skill bundle (`mac-storage-cleanup.skill`)
- Production-safe guard logic
- Verified duplicate discovery tool
- `LICENSE-EULA.md` for paid usage
- `LICENSE-MIT.txt` for demo usage
- Integrity checksum (`SHA256SUMS`)

### License model
- **Paid product:** proprietary EULA in [LICENSE-EULA.md](LICENSE-EULA.md)
- **Demo material:** MIT terms in [LICENSE-MIT.txt](LICENSE-MIT.txt)

## 7) Ideal customer / not for

**Ideal for**
- iOS/iOS-like macOS power users with repeated storage crises
- Freelance/agency developers with many project folders
- Teams managing many temporary build trees and dependencies

**Not for**
- People wanting automatic delete of photos, downloads, or entire drive folders
- Users who want silent background cleanup without explicit approval

## 8) Sales and delivery posture

This repo is positioned as a paid Codex skill product.  
The paid license is commercial; the MIT file is explicitly for demonstration workflows.

If you want this moved into a full checkout flow (Gumroad/Stripe/Paddle), I can integrate it in the next pass:
- custom pricing tiers
- support promises
- invoice automation
- update links in landing + README

## 9) Repository quality contract

- No unrelated changes in release branches
- No blanket trash clearing
- No silent data-risk actions
- No fallback heuristics for ambiguous cleanup targets
- Deterministic hashes and post-run reporting remain mandatory

## 10) Contributing

Only safety, validation, and product-hardening changes are accepted.
If you want a commercial patch, use focused PRs with explicit test and safety notes.

## License

- [EULA (commercial)](LICENSE-EULA.md)
- [MIT (demo)](LICENSE-MIT.txt)

