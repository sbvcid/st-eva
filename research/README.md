# ST-EVA Research Storage

**This directory is the permanent research storage for ST-EVA.**
It is defined by `docs/ST-EVA-PROJECT-STRUCTURE.md`.

## What belongs here

All ST-EVA research data, permanently:

- proofs of concept and their output
- raw source material — SEC filings, SGML headers, filing index pages
- verification artifacts
- manifests, including `RESEARCH-ARCHIVE-MANIFEST.json`
- deterministic outputs and negative-path artifacts
- agent research artifacts and intermediate results
- historical study data

New research is created here directly, at `research/<topic>/`, optionally
`research/<topic>/<issuer>/` or `research/<topic>/verification/`.

## Research is preserved by default

> Research artifacts are preserved by default. Low value does not imply deletion.

Nothing is relocated or removed because a study looks unimportant, small,
superseded, or low-value. Only cache, temporary files, build output, confirmed
duplicate garbage, and invalid empty temporary downloads may be deleted.
"Regenerable" is not by itself a reason to delete anything.

**An existing study should not be moved merely because it is complete.**
Completion is not a reason to relocate. `research/` is already the permanent
destination, so a finished study stays exactly where it is.

## What does not belong here

Production code, methodology, and runtime data live elsewhere:

| Belongs | Lives in |
|---|---|
| Production modules | repo root `*.py` |
| Web application | `web/` |
| Tests | `tests/` |
| Methodology and contracts | `docs/`, `docs/methodology/` |
| Runtime SQLite / canonical application data | `data/` |
| Archive subsystem and migrations | `archive/` |
| Cache and build output | deletable |

## Git

`/research/` is listed in `.gitignore`. This tree is **not tracked by git**.

That is intentional. The research material is large and is preserved as working
material rather than as version-controlled source. Do not add it to git, and do
not run `git add .` in this repository — `.gitignore` excludes `/research/`, but
the tracked legacy files under `experiments/` do not depend on that, and a
careless `git add .` would stage unrelated content.

The 46 legacy tracked research files in `experiments/` are unaffected. They stay
tracked, unmoved, and undeleted.

## Finding research material

Use the directory structure and the archive manifest:

- `research/experiments/` — the relocated Historical P/E research: the AAPL POC,
  the Q4 evidence study, the Amendment 1 verification, and the MSFT contract
  validation, each with its frozen raw inputs, scripts and outputs.
- `research/RESEARCH-ARCHIVE-MANIFEST.json` — records every relocated file's
  relative path, byte size, and SHA-256 at both source and destination, with the
  verification result. It is the authority on what was preserved.

To confirm the archive is intact, compare the files on disk against the manifest
rather than against a remembered count.

---

*Research artifacts are preserved by default. Low value does not imply deletion.*