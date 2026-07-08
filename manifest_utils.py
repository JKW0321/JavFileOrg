#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Manifest / run-summary helpers for safe batch processing."""
from __future__ import annotations

import json
import os
from datetime import datetime

VIDEO_EXTENSIONS = {'.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.rmvb'}
SKIP_SCAN_DIRS = {'Finish', 'JFO_Logs', '.jfo_transactions', '__MACOSX'}


def build_manifest_from_entries(folder_path: str, entries: list[dict]) -> dict:
    return {
        'folder': folder_path,
        'generated_at': datetime.now().isoformat(),
        'total_files': len(entries),
        'entries': sorted(entries, key=lambda item: item.get('name') or ''),
    }


def scan_folder_manifest(folder_path: str) -> dict:
    entries = []
    for dirpath, dirnames, filenames in os.walk(folder_path):
        dirnames[:] = [
            dirname for dirname in dirnames
            if not dirname.startswith('.') and dirname not in SKIP_SCAN_DIRS
        ]
        for name in filenames:
            file_path = os.path.join(dirpath, name)
            rel_path = os.path.relpath(file_path, folder_path)
            try:
                st = os.stat(file_path)
            except OSError:
                continue
            _, ext = os.path.splitext(name.lower())
            entries.append({
                'name': rel_path,
                'size': st.st_size,
                'mtime': st.st_mtime,
                'extension': ext,
                'is_hidden': name.startswith('.'),
                'is_video': ext in VIDEO_EXTENSIONS,
            })
    return build_manifest_from_entries(folder_path, entries)


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
