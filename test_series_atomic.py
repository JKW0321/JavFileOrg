#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Atomic series transaction tests."""
import tempfile
from pathlib import Path

from PIL import Image

from atomic_processor_v11 import AtomicProcessor


def _dummy_download(url, dest):
    Image.new('RGB', (1, 1), color=(255, 100, 50)).save(dest, 'JPEG')
    return True


def _sanitize(name):
    return name


def test_process_series_group_atomic_success():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src = root / 'src'
        out = root / 'Finish'
        src.mkdir()
        out.mkdir()
        f1 = src / 'ABF-139-1.mp4'
        f2 = src / 'ABF-139-2.mp4'
        f1.write_bytes(b'a' * 1024 * 32)
        f2.write_bytes(b'b' * 1024 * 32)
        p = AtomicProcessor(_dummy_download, _sanitize)
        ok, result, message = p.process_series_group_atomic(
            [(str(f1), '1'), (str(f2), '2')],
            'ABF-139 TITLE',
            'http://example/image.jpg',
            str(out),
        )
        assert ok is True, message
        assert not f1.exists() and not f2.exists()
        assert (out / 'ABF-139 TITLE-1.mp4').exists()
        assert (out / 'ABF-139 TITLE-2.mp4').exists()
        assert (out / 'ABF-139 TITLE.jpg').exists()
        assert result['image_downloaded'] is True
        assert len(result['video_paths']) == 2


def test_process_series_group_atomic_rolls_back_if_image_finalize_fails():
    class BrokenProcessor(AtomicProcessor):
        def _move_temp_image_to_final(self, temp_image_path, final_image_path):
            raise RuntimeError('boom')

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src = root / 'src'
        out = root / 'Finish'
        src.mkdir()
        out.mkdir()
        f1 = src / 'ABF-139-1.mp4'
        f2 = src / 'ABF-139-2.mp4'
        f1.write_bytes(b'a' * 1024 * 32)
        f2.write_bytes(b'b' * 1024 * 32)
        p = BrokenProcessor(_dummy_download, _sanitize)
        ok, result, message = p.process_series_group_atomic(
            [(str(f1), '1'), (str(f2), '2')],
            'ABF-139 TITLE',
            'http://example/image.jpg',
            str(out),
        )
        assert ok is False
        assert f1.exists() and f2.exists()
        assert not (out / 'ABF-139 TITLE-1.mp4').exists()
        assert not (out / 'ABF-139 TITLE-2.mp4').exists()
        assert not (out / 'ABF-139 TITLE.jpg').exists()
