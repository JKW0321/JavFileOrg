#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Workflow service tests."""
import tempfile
from pathlib import Path

from PIL import Image

from atomic_processor_v11 import AtomicProcessor
from workflow_service import WorkflowService


class DummyProvider:
    def __init__(self, title_prefix='TITLE'):
        self.title_prefix = title_prefix
        self.calls = []

    def search(self, query):
        self.calls.append(query)
        return {
            'ok': True,
            'title': f'{query.upper()} {self.title_prefix}',
            'image_url': 'http://example/image.jpg',
            'provider': 'dummy',
            'error_type': None,
            'message': None,
        }


def _download(url, dest):
    Image.new('RGB', (1, 1), color=(255, 100, 50)).save(dest, 'JPEG')
    return True


def _sanitize(name):
    return name


def _series_info(stem):
    if stem.startswith('ABF-139-1'):
        return ('ABF-139', '1')
    if stem.startswith('ABF-139-2'):
        return ('ABF-139', '2')
    return (None, None)


def test_workflow_dry_run_keeps_source_files():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / 'ABF-139-1.mp4').write_bytes(b'a' * 32768)
        (root / 'SONE-753.mp4').write_bytes(b'b' * 32768)
        provider = DummyProvider()
        svc = WorkflowService(
            log=lambda *a, **k: None,
            provider_factory=lambda name: provider,
            atomic_processor=AtomicProcessor(_download, _sanitize),
            clean_filename_for_search=lambda n: Path(n).stem.lower(),
            sanitize_filename=_sanitize,
            detect_series_files=lambda files: ({}, files),
            smart_truncate_filename=lambda title, original, max_length: title,
            stop_requested=lambda: False,
            minimum_video_size_bytes=16384,
        )
        result = svc.run(
            folder_path=str(root),
            finish_folder=str(root / 'Finish'),
            website='javhoo',
            max_length=None,
            batch_count=None,
            dry_run=True,
        )
        assert result['planned_count'] == 2
        assert (root / 'ABF-139-1.mp4').exists()
        assert (root / 'SONE-753.mp4').exists()
        assert not (root / 'Finish').exists()


def test_workflow_series_uses_atomic_group_processing():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        finish = root / 'Finish'
        finish.mkdir()
        f1 = root / 'ABF-139-1.mp4'
        f2 = root / 'ABF-139-2.mp4'
        f1.write_bytes(b'a' * 32768)
        f2.write_bytes(b'b' * 32768)
        provider = DummyProvider('SERIES')
        svc = WorkflowService(
            log=lambda *a, **k: None,
            provider_factory=lambda name: provider,
            atomic_processor=AtomicProcessor(_download, _sanitize),
            clean_filename_for_search=lambda n: Path(n).stem.lower(),
            sanitize_filename=_sanitize,
            detect_series_files=lambda files: ({'ABF-139': [(str(f1), '1'), (str(f2), '2')]}, []),
            smart_truncate_filename=lambda title, original, max_length: title,
            stop_requested=lambda: False,
            minimum_video_size_bytes=16384,
        )
        result = svc.run(
            folder_path=str(root),
            finish_folder=str(finish),
            website='javhoo',
            max_length=None,
            batch_count=None,
            dry_run=False,
        )
        assert result['success_count'] == 2
        assert (finish / 'ABF-139 SERIES-1.mp4').exists()
        assert (finish / 'ABF-139 SERIES-2.mp4').exists()
        assert (finish / 'ABF-139 SERIES.jpg').exists()
