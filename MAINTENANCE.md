# JAVFileOrganizer Maintenance Guide

## Current State

- Git maintenance version: `v1.5.5`
- Runtime version: `v1.5.5`
- Main branch: `main`
- Remote: `origin`
- Default non-network regression: `python3 run_baseline_tests.py`
- Architecture principles: `ARCHITECTURE_PRINCIPLES.md`

The visible app version and Git tag are now aligned at `v1.5.5`; the runtime version should remain a plain semantic version without suffixes.

## Before Changing Code

1. Check local state:

```bash
git status --short --branch
```

2. Run the default offline regression:

```bash
python3 run_baseline_tests.py
```

3. Treat live-network tests as manual smoke checks only:

```bash
python3 run_baseline_tests.py --include-live-network
```

## Change Priorities

1. Source file safety first: dry-run, manifest, size validation, rollback behavior.
2. Preserve strict per-video transaction semantics: video, image, and filename all succeed, or the source stays unchanged.
3. Keep provider behavior isolated in `providers/`; manual provider selection remains the default.
4. Keep filename parsing in `filename_utils.py` with regression tests.
5. Keep GUI changes thin; move business logic into `workflow_service.py` or smaller services.
6. Avoid broad refactors unless the current behavior is covered by tests.

## Test Notes

The default offline regression passed on 2026-07-05 using an isolated Python runtime with temporary dependencies:

```text
Pure utility regression: 169 passed
Series e2e regression: PASS
Before/after comparison regression: PASS
GUI worker walkthrough: PASS
Blocking failures: 0
```

In the Codex sandbox, Homebrew `python3` exited with code 137 and `/usr/bin/python3` hit a macOS `_scproxy` library loading issue. The successful run used the Codex bundled Python plus dependencies installed under `/private/tmp/jfo_pydeps`. This was an environment constraint, not a project regression.

## Release Hygiene

For a source-only fix:

1. Update or add focused tests.
2. Run `python3 run_baseline_tests.py`.
3. Update `README.md`, `DELIVERY.md`, or this file only when behavior or release status changes.
4. Tag only after the default offline regression is clean.

For a new macOS app build:

1. Decide the new visible runtime version.
2. Update `BASELINE_VERSION`, `BASELINE_BUILD_ID`, and docs together.
3. Run `./build_release.sh` from the repository root.
4. Verify GUI launch and the default regression.
5. Record the app bundle name in `DELIVERY.md`.
