# JAVFileOrganizer Refactor Roadmap

This roadmap turns the architecture principles into an implementation sequence. The goal is not a rewrite. Each phase should be small, tested, and reversible.

## Phase 1: Strict Storage Transactions

Goal: make the file storage layer enforce all-or-nothing behavior for each video.

Status: implemented. `AtomicProcessor` now requires an image URL, rolls back single-file video moves when image finalization fails, and returns structured status/rollback fields. `WorkflowService` records atomic success, failure, and critical rollback outcomes in file-level audit.

Target modules:

- `atomic_processor_v11.py`
- Future optional rename: `storage_service.py`

TDD checklist:

- Add a test where image finalization fails after video movement; expect the video to be rolled back and the operation to fail.
- Add a test where image URL exists but download fails; expect source video unchanged and no output video.
- Add a test where target video path collides; expect deterministic `_1`, `_2` naming and matching image path.
- Add a test where rollback fails; expect a critical structured result instead of silent pass.
- Add a test where provider returns no image URL; expect source video unchanged and no output video.

Design decision:

- Missing image URL is a failed transaction. Source video stays unchanged.

Deliverable:

- Structured result with `status`, `source_path`, `target_video_path`, `target_image_path`, `rollback_ok`, and `reason`.

## Phase 2: File-Level Audit

Goal: every processed or planned file gets a durable record.

Status: implemented. `WorkflowService` writes `file_results_<timestamp>.json` for planned, skipped, failed, successful, and atomic-failure records. Return counters and run summary counters now derive from the file-level result list, including planned, skipped, failed/critical, and unique successful image counts.

Target modules:

- `workflow_service.py`
- `manifest_utils.py`
- New optional: `run_models.py`

TDD checklist:

- Dry Run writes file-level planned operations.
- Failed provider search writes `status=failed` with provider error.
- Skipped hidden/small files are represented with explicit reasons.
- Successful series group records each video plus the shared image.
- Done: summary counts derive from file-level results, not hand-maintained counters.

Deliverable:

```text
JFO_Logs/file_results_<timestamp>.json
```

## Phase 3: Provider Interface Cleanup

Goal: keep manual provider selection reliable and extensible without automatic routing.

Status: implemented for offline behavior. `ProviderResult` now includes stable audit fields (`query`, `detail_url`, `referer`) and request-based/Selenium providers return those fields to file-level audit. Offline tests cover JavHoo cover selection, JavBus anti-crawl session usage, and JAVLibrary structured success/failure results. Release validation should still include manual live-network smoke checks because those depend on current site and anti-crawl behavior.

Target modules:

- `providers/base.py`
- `providers/request_provider.py`
- `providers/javhoo_provider.py`
- `providers/javbus_provider.py`
- `providers/javlibrary_provider.py`

TDD checklist:

- Provider result carries `provider`, `query`, `title`, `image_url`, `detail_url`, `referer`, `error_type`, and `message`.
- JavHoo image parsing avoids logo/flag/thumb images.
- JavBus provider uses the anti-crawl session when selected.
- JAVLibrary returns structured success and failure results through the same contract.
- JAVLibrary stale headless state falls back to visible verification.
- Provider mismatch only warns; it does not switch provider.

Deliverable:

- Stable `ProviderResult` contract.
- No provider writes files or touches GUI.

## Phase 4: GUI Thread Safety

Goal: real Tkinter runtime should only be touched from the main thread.

Status: implemented. Worker result application, messageboxes, and processing-control reset now go through `_run_on_ui_thread()` / `window.after`; `ProcessingRequest` captures Tk-bound inputs on the UI thread before launching the worker; stop requests use a `threading.Event` behind `_is_stop_requested()` while preserving the legacy flag for compatibility. GUI threading tests cover immediate main-thread execution, worker-thread scheduling, request capture, worker launch, stop/reset behavior, and processing-control reset. Legacy GUI business paths were handled in Phase 5.

Target module:

- `jav_file_organizer.py`

TDD checklist:

- Start processing captures UI options on the main thread before launching worker.
- Worker receives plain data only.
- Worker returns a result object.
- GUI updates and messageboxes are scheduled with `window.after`.
- Stop button sets a thread-safe cancellation flag.

Deliverable:

- `JavFileOrganizer` becomes a GUI shell around `WorkflowService`.

## Phase 5: Remove Legacy Paths

Goal: reduce ambiguity by deleting dead or duplicated paths after tests cover replacements.

Status: implemented. Series e2e coverage now runs through `WorkflowService`; legacy GUI helpers `_extract_javlibrary`, `_find_detail_url`, `_fetch_detail_page`, `process_series_group`, and `download_image_batch` have been removed from `jav_file_organizer.py`. Broken `OptimizedAntiCrawlHandler` answer/get/download helpers that referenced `self.anti_crawl` were also removed. The remaining GUI `download_image` and test-connection paths have focused offline coverage, test-connection messageboxes use the UI-thread-safe wrapper, and image downloading is delegated to shared `download_service.ImageDownloader`.

Candidates:

- Done: legacy `_extract_javlibrary` in `jav_file_organizer.py`
- Done: legacy `_find_detail_url` / `_fetch_detail_page` in `jav_file_organizer.py`
- Done: legacy `process_series_group`
- Done: unused image batch helper
- Done: broken `OptimizedAntiCrawlHandler` quiz/page/download helpers
- Covered: GUI `download_image` success, cancellation, and retry cleanup behavior
- Covered: test-connection messageboxes through the UI-thread-safe wrapper
- Done: GUI `download_image` delegates to shared `download_service.ImageDownloader`

TDD checklist:

- Default offline regression stays green after each removal.
- No public GUI command depends on the removed path.

## Phase 6: UI Redesign

Goal: improve usability after core correctness is stable.

Ideas:

- Clear mode indicator: Dry Run vs Commit
- Provider status panel
- Preview table for planned operations
- File-level result table
- Direct buttons to open log/manifest folder
- Dedicated JAVLibrary "reverify browser" control

This phase should wait until storage, audit, provider, and thread-safety work are stable.
