# Production safety pattern

This reference describes the repeatable workflow; it contains no machine-specific inventory.

- Clean only regenerable artifacts from inactive projects after checking processes, manifests, hashes, and Git status.
- Stage exact targets in the user's Trash, then delete only that staging folder through Finder; never empty an existing Trash.
- Preserve source changes, lockfiles, credentials, browser profiles, memory tooling, extensions, reports, and personal media.
- Remove duplicate media only after SHA-256 equality, canonical-file selection, and explicit approval.
- Protect every path ending in `Warning/Default`, plus any paths supplied through `--protect`.
- A closed app window does not prove its processes stopped; check again immediately before moving files.

The rule is: inventory -> classify -> verify process state -> stage recoverably -> verify hashes/status -> delete exact staging -> report.
