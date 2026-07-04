#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Manifest / run-summary helpers for safe batch processing."""
from __future__ import annotations

import json
import os
from datetime import datetime

VIDEO_EXTENSIONS = {'.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v'}


def scan_folder_manifest(folder_path: str) -> dict:
    entries = []
    for name in sorted(os.listdir(folder_path)):
        path = os.path.join(folder_path, name)
        if not os.path.isfile(path):
            continue
        st = os.stat(path)
        _, ext = os.path.splitext(name.lower())
        entries.append({
            'name': name,
            'size': st.st_size,
            'mtime': st.st_mtime,
            'extension': ext,
            'is_hidden': name.startswith('.'),
            'is_video': ext in VIDEO_EXTENSIONS,
        })
    return {
        'folder': folder_path,
        'generated_at': datetime.now().isoformat(),
        'total_files': len(entries),
        'entries': entries,
    }


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
                      routed_counts: dict | None = None) -> dict:
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
            'skipped_hidden': skipped_hidden,
            'skipped_small': skipped_small,
            'skipped_provider': skipped_provider,
        },
        'routed_counts': routed_counts or {},
        'artifacts': {
            'log_path': log_path,
            'before_manifest_path': before_manifest_path,
            'after_manifest_path': after_manifest_path,
        },
    }
