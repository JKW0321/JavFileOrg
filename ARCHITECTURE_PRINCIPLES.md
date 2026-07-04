# JAVFileOrganizer Architecture Principles

This document captures the project rules for future maintenance. These principles outrank convenience, speed, and UI polish.

## 1. Source Safety Comes First

The source video file is the user's asset. The application must never leave the user with a lost file, a partial output, or an unclear state.

Every processing run should preserve enough audit evidence to answer:

- Which files were considered?
- Which files were skipped?
- Which provider was used?
- Which network and parsing results were returned?
- Which output paths were planned?
- Which files were committed?
- Which files were rolled back or left untouched?

## 2. Strict Per-Video Transaction Semantics

For each video file, processing has only two acceptable final states:

1. Success: the video is moved/renamed correctly, the image is present and valid, and the final filename is correct.
2. No change: the original source file remains in place, and no partial output remains.

Partial success should not be treated as success. If image finalization fails after video movement, the video should be rolled back. If rollback fails, that must be logged as a critical file-safety event.

If a provider returns no image URL, the storage layer must not move the source video. The workflow may report this as a provider/content failure and leave the source unchanged.

Committed video and image files should be flushed to disk, and parent directory entries should be flushed after moves, finalization, cleanup, or rollback where the platform supports it.

Series groups may share one image, but each video still needs a clear file-level result. The group transaction can be all-or-nothing when using a shared image.

## 3. Cache Carefully

Caching can improve speed, but it must not weaken transaction safety or correctness.

Allowed cache candidates:

- Provider metadata by normalized query and provider name.
- Successful image bytes only after validation.
- Short-lived search results inside a single run.

Cache requirements:

- Include provider name, query, timestamp, and source URL.
- Never cache failed or partial file operations as success.
- Never skip final file validation because cache exists.
- Never let cached metadata silently overwrite user-visible audit details.

Cache should be introduced only after transaction behavior is covered by tests.

## 4. Providers Are Pluggable, Not Magical

The user manually selects the provider. The app should first make each selected provider work reliably before adding automatic routing.

Current provider rule:

- `JavHoo`, `JavBus`, and `JAVLibrary` share a common interface.
- Providers return metadata only: title, image URL, provider, query, detail URL, referer, and structured error details.
- Providers do not move files, write images, mutate manifests, or update GUI state.
- Provider mismatch detection may warn, but should not automatically switch providers unless the user explicitly opts into that behavior in a future version.

## 5. Filename Logic Stays Independent

Filename parsing and sanitization belong in `filename_utils.py`.

Rules:

- Add regression tests before changing filename behavior.
- Keep functions pure: no GUI, network, filesystem writes, or logging side effects.
- Prefer small, explicit cases over broad regex changes that may damage valid filenames.
- Unknown filename patterns may be analyzed into candidate rules, but low-confidence candidates must stay audit-only and must not drive file moves or renames automatically.
- Runtime rule-learning observations are written as audit artifacts; promoting a pattern into an automatic rule requires tests.

## 6. File Storage Is Core Infrastructure

Downloading, image validation, moving, renaming, collision handling, rollback, and cleanup are shared by all providers. This layer should be treated as core infrastructure.

Storage requirements:

- Use temporary files for downloads.
- Validate downloaded images before moving videos.
- Plan target paths before committing.
- Detect collisions deterministically.
- Verify final video size after movement.
- Roll back on any required step failure.
- Report structured file-level outcomes.

Network conditions to handle:

- Timeout
- HTTP error
- Empty response
- Corrupt image
- Interrupted run
- Provider returns no image
- Remote server blocks hotlinking
- Partial local write

## 7. Audit Is Required

Each run should produce durable audit artifacts:

- Human-readable log
- Before manifest
- After manifest
- Run summary
- File-level result report

Dry Run should produce planned operations without downloading images or moving files.

## 8. TDD Workflow

Use test-driven development for behavior changes.

Default order:

1. Write or update a failing test that captures the intended behavior.
2. Implement the smallest change that makes it pass.
3. Run the focused test.
4. Run the default offline regression.
5. Update docs only when behavior or release status changes.

Priority test areas:

- Atomic file/image transaction behavior
- Rollback failures and audit reporting
- Filename parsing regressions
- Provider metadata parsing
- Network/download failure handling
- GUI thread handoff without touching Tkinter from worker threads

## 9. UI Can Improve Later

The current interface is usable but not polished. UI redesign is valuable, but should wait until transaction safety, provider boundaries, and storage behavior are stable.

Future UI should make these states obvious:

- Dry Run vs real commit
- Selected provider
- Planned operations
- Files skipped and why
- Files failed and whether rollback succeeded
- Location of logs/manifests
