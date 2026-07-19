#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_manifest_utils.py
======================

manifest / summary 工具的基础测试。
"""
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from manifest_utils import build_manifest_from_entries, build_run_summary, scan_folder_manifest, scan_video_files, write_json_report


def test_scan_folder_manifest_marks_hidden_and_video():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp)
        (p / 'ABF-123.mp4').write_bytes(b'a' * 32)
        (p / '._ABF-123.mp4').write_bytes(b'a' * 4)
        (p / 'note.txt').write_text('hello', encoding='utf-8')

        manifest = scan_folder_manifest(str(p))
        assert manifest['folder'] == str(p)
        entries = {e['name']: e for e in manifest['entries']}
        assert entries['ABF-123.mp4']['is_video'] is True
        assert entries['ABF-123.mp4']['is_hidden'] is False
        assert entries['._ABF-123.mp4']['is_hidden'] is True
        assert entries['note.txt']['is_video'] is False
        assert manifest['total_files'] == 3


def test_scan_folder_manifest_recurses_and_skips_output_dirs():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp)
        (p / 'nested').mkdir()
        (p / 'nested' / 'FC2-PPV-1234567.rmvb').write_bytes(b'a' * 32)
        (p / 'Finish').mkdir()
        (p / 'Finish' / 'already-done.mp4').write_bytes(b'a' * 32)
        (p / 'JFO_Logs').mkdir()
        (p / 'JFO_Logs' / 'run.log').write_text('log', encoding='utf-8')

        manifest = scan_folder_manifest(str(p))
        entries = {e['name']: e for e in manifest['entries']}

        assert 'nested/FC2-PPV-1234567.rmvb' in entries
        assert entries['nested/FC2-PPV-1234567.rmvb']['is_video'] is True
        assert 'Finish/already-done.mp4' not in entries
        assert 'JFO_Logs/run.log' not in entries


def test_scan_video_files_can_skip_subdirectories_but_still_skip_finish():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp)
        (p / 'root.mp4').write_bytes(b'a' * 32768)
        (p / 'nested').mkdir()
        (p / 'nested' / 'child.mp4').write_bytes(b'b' * 32768)
        (p / 'Finish').mkdir()
        (p / 'Finish' / 'done.mp4').write_bytes(b'c' * 32768)

        current_only = scan_video_files(str(p), include_subdirectories=False)
        recursive = scan_video_files(str(p), include_subdirectories=True)

        assert current_only['accepted'] == ['root.mp4']
        assert 'nested/child.mp4' not in current_only['accepted']
        assert 'Finish/done.mp4' not in current_only['accepted']
        assert recursive['accepted'] == ['nested/child.mp4', 'root.mp4']
        assert 'Finish/done.mp4' not in recursive['accepted']


def test_scan_video_files_skips_finish_case_insensitively():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp)
        (p / 'root.mp4').write_bytes(b'a' * 32768)
        (p / 'finish').mkdir()
        (p / 'finish' / 'done.mp4').write_bytes(b'b' * 32768)

        scan = scan_video_files(str(p), include_subdirectories=True)

        assert scan['accepted'] == ['root.mp4']


def test_build_manifest_from_entries_sorts_without_rescanning():
    manifest = build_manifest_from_entries('/tmp/source', [
        {'name': 'b.mp4', 'size': 2, 'mtime': 2, 'extension': '.mp4', 'is_hidden': False, 'is_video': True},
        {'name': 'a.txt', 'size': 1, 'mtime': 1, 'extension': '.txt', 'is_hidden': False, 'is_video': False},
    ])

    assert manifest['folder'] == '/tmp/source'
    assert manifest['total_files'] == 2
    assert [entry['name'] for entry in manifest['entries']] == ['a.txt', 'b.mp4']


def test_write_json_report_roundtrip():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / 'report.json'
        payload = {'ok': True, 'count': 3}
        write_json_report(str(path), payload)
        assert json.loads(path.read_text(encoding='utf-8')) == payload


def test_build_run_summary_contains_core_fields():
    summary = build_run_summary(
        version='v1.5.4',
        website='javlibrary',
        folder='/tmp/x',
        total_files=10,
        success_count=7,
        failed_count=2,
        skipped_hidden=1,
        skipped_small=3,
        skipped_provider=4,
        dry_run=False,
        log_path='/tmp/log.txt',
        before_manifest_path='/tmp/before.json',
        after_manifest_path='/tmp/after.json',
    )
    assert summary['version'] == 'v1.5.4'
    assert summary['website'] == 'javlibrary'
    assert summary['counts']['total_files'] == 10
    assert summary['counts']['success_count'] == 7
    assert summary['counts']['skipped_hidden'] == 1
    assert summary['artifacts']['log_path'] == '/tmp/log.txt'
