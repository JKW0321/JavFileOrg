#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Manifest / run-summary helpers for safe batch processing."""
from __future__ import annotations

import json
import os
from datetime import datetime

VIDEO_EXTENSIONS = {'.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.rmvb'}
SKIP_SCAN_DIRS = {'Finish', 'JFO_Logs', '.jfo_transactions', '__MACOSX'}
SKIP_SCAN_DIRS_NORMALIZED = {name.lower() for name in SKIP_SCAN_DIRS}
DEFAULT_MINIMUM_VIDEO_SIZE_BYTES = 16 * 1024


def build_manifest_from_entries(folder_path: str, entries: list[dict]) -> dict:
    return {
        'folder': folder_path,
        'generated_at': datetime.now().isoformat(),
        'total_files': len(entries),
        'entries': sorted(entries, key=lambda item: item.get('name') or ''),
    }


def scan_video_files(folder_path: str, *, video_extensions: set[str] | None = None,
                     minimum_video_size_bytes: int = DEFAULT_MINIMUM_VIDEO_SIZE_BYTES,
                     include_subdirectories: bool = True) -> dict:
    """Scan a source folder once and return workflow-ready file lists plus manifest entries.

    Uses os.scandir recursively so remote filesystems can reuse DirEntry metadata and
    avoid the extra path work from os.walk + os.stat for every file.
    """
    video_extensions = {ext.lower() for ext in (video_extensions or VIDEO_EXTENSIONS)}
    result = {
        'accepted': [],
        'skipped_hidden': [],
        'skipped_small': [],
        'manifest_entries': [],
        'file_sizes': {},
        'total_files': 0,
    }

    def visit(abs_dir: str, rel_dir: str = ''):
        try:
            with os.scandir(abs_dir) as iterator:
                dir_entries = list(iterator)
        except OSError:
            return

        for entry in dir_entries:
            name = entry.name
            rel_path = f'{rel_dir}/{name}' if rel_dir else name
            try:
                is_dir = entry.is_dir(follow_symlinks=False)
            except OSError:
                continue
            if is_dir:
                if name.startswith('.') or name.lower() in SKIP_SCAN_DIRS_NORMALIZED:
                    continue
                if include_subdirectories:
                    visit(entry.path, rel_path)
                continue

            try:
                st = entry.stat(follow_symlinks=False)
            except OSError:
                continue
            result['total_files'] += 1
            _, ext = os.path.splitext(name.lower())
            entry_payload = {
                'name': rel_path,
                'size': st.st_size,
                'mtime': st.st_mtime,
                'extension': ext,
                'is_hidden': name.startswith('.'),
                'is_video': ext in VIDEO_EXTENSIONS,
            }
            result['manifest_entries'].append(entry_payload)
            if name.startswith('._') or name.startswith('.'):
                result['skipped_hidden'].append(rel_path)
                continue
            if ext not in video_extensions:
                continue
            if st.st_size < minimum_video_size_bytes:
                result['skipped_small'].append(rel_path)
                continue
            result['accepted'].append(rel_path)
            result['file_sizes'][rel_path] = st.st_size

    visit(folder_path)
    result['accepted'].sort()
    result['skipped_hidden'].sort()
    result['skipped_small'].sort()
    return result


def scan_folder_manifest(folder_path: str, *, include_subdirectories: bool = True) -> dict:
    scan = scan_video_files(
        folder_path,
        video_extensions=VIDEO_EXTENSIONS,
        minimum_video_size_bytes=0,
        include_subdirectories=include_subdirectories,
    )
    return build_manifest_from_entries(folder_path, scan['manifest_entries'])


def write_json_report(path: str, payload: dict) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return path


def build_run_summary(*, version: str, website: str, folder: str, total_files: int,
                      success_count: int, failed_count: int,
                      skipped_hidden: int, skipped_small: int, skipped_provider: int,
                      dry_run: bool, log_path: str | None,
                      before_manifest_path: str | None,
                      after_manifest_path: str | None,
                      after_manifest_status: str | None = None,
                      routed_counts: dict | None = None,
                      file_results_path: str | None = None,
                      planned_count: int = 0,
                      needs_review_count: int = 0,
                      cancelled_count: int = 0,
                      image_success_count: int = 0,
                      image_failed_count: int = 0,
                      file_result_counts: dict | None = None,
                      filename_rule_candidates_path: str | None = None,
                      timing_summary: dict | None = None) -> dict:
    return {
        'generated_at': datetime.now().isoformat(),
        'version': version,
        'website': website,
        'folder': folder,
        'dry_run': dry_run,
        'counts': {
            'total_files': total_files,
            'success_count': success_count,
            'failed_count': failed_count,
            'planned_count': planned_count,
            'needs_review_count': needs_review_count,
            'cancelled_count': cancelled_count,
            'skipped_hidden': skipped_hidden,
            'skipped_small': skipped_small,
            'skipped_provider': skipped_provider,
            'image_success_count': image_success_count,
            'image_failed_count': image_failed_count,
            'file_result_counts': file_result_counts or {},
        },
        'routed_counts': routed_counts or {},
        'timings': timing_summary or {},
        'artifacts': {
            'log_path': log_path,
            'before_manifest_path': before_manifest_path,
            'after_manifest_path': after_manifest_path,
            'after_manifest_status': after_manifest_status or ('written' if after_manifest_path else 'not-written'),
            'file_results_path': file_results_path,
            'filename_rule_candidates_path': filename_rule_candidates_path,
        },
    }
