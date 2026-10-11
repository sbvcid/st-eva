# Research

This directory contains working research material for ST-EVA, such as source captures, experiments, verification artifacts, scripts, and intermediate or final research outputs.

The research directory is distinct from production inputs and code. Runtime features and tests must not depend on files that are present only in a developer's ignored local working data. If a specific evidence file is required to reproduce a supported production or test path, its actual versioned location should be determined by that use rather than by an old directory-plan document.

## Version-control behavior

The root `.gitignore` currently ignores untracked content under `/research/`. This does not remove files already tracked by Git. Some research artifacts also exist in the tracked `experiments/` tree, and production historical P/E inputs are held under `data/historical_pe/`.

These are current repository facts, not a rule that research material must always remain outside version control. Decide the appropriate location from the artifact's purpose, size, reproducibility needs, and the user's current request.

## Typical contents

- Raw source material and capture records.
- Research scripts and proof-of-concept implementations.
- Evidence-verification artifacts and manifests.
- Intermediate analyses and generated research results.