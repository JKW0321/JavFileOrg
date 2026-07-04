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


def test_process_file_atomic_success_requires_video_and_image():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src = root / 'src'
        out = root / 'Finish'
        src.mkdir()
        out.mkdir()
        f1 = src / 'SONE-753.mp4'
        f1.write_bytes(b'a' * 1024 * 32)
        p = AtomicProcessor(_dummy_download, _sanitize)
        ok, result, message = p.process_file_atomic(
            str(f1),
            'SONE-753 TITLE.mp4',
            'http://example/image.jpg',
            str(out),
        )
        assert ok is True, message
        assert not f1.exists()
        assert (out / 'SONE-753 TITLE.mp4').exists()
        assert (out / 'SONE-753 TITLE.jpg').exists()
        assert result['image_downloaded'] is True


def test_process_file_atomic_fsyncs_committed_outputs():
    class RecordingProcessor(AtomicProcessor):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.synced = []

        def _fsync_committed_path(self, path):
            self.synced.append(Path(path).name)

        def _fsync_parent_dir(self, path):
            self.synced.append(f"dir:{Path(path).parent.name}")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src = root / 'src'
        out = root / 'Finish'
        src.mkdir()
        out.mkdir()
        f1 = src / 'SONE-753.mp4'
        f1.write_bytes(b'a' * 1024 * 32)
        p = RecordingProcessor(_dummy_download, _sanitize)
        ok, result, message = p.process_file_atomic(
            str(f1),
            'SONE-753 TITLE.mp4',
            'http://example/image.jpg',
            str(out),
        )
        assert ok is True, message
        assert 'SONE-753 TITLE.mp4' in p.synced
        assert 'SONE-753 TITLE.jpg' in p.synced


def test_process_file_atomic_rolls_back_if_fsync_fails():
    class BrokenSyncProcessor(AtomicProcessor):
        def _fsync_committed_path(self, path):
            if str(path).endswith('.mp4') and Path(path).parent.name == 'Finish':
                raise RuntimeError('fsync failed')
            return None

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src = root / 'src'
        out = root / 'Finish'
        src.mkdir()
        out.mkdir()
        f1 = src / 'SONE-753.mp4'
        f1.write_bytes(b'a' * 1024 * 32)
        p = BrokenSyncProcessor(_dummy_download, _sanitize)
        ok, result, message = p.process_file_atomic(
            str(f1),
            'SONE-753 TITLE.mp4',
            'http://example/image.jpg',
            str(out),
        )
        assert ok is False
        assert f1.exists()
        assert not (out / 'SONE-753 TITLE.mp4').exists()
        assert result['rollback_ok'] is True


def test_process_file_atomic_requires_image_url_and_keeps_source():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src = root / 'src'
        out = root / 'Finish'
        src.mkdir()
        out.mkdir()
        f1 = src / 'SONE-753.mp4'
        f1.write_bytes(b'a' * 1024 * 32)
        p = AtomicProcessor(_dummy_download, _sanitize)
        ok, result, message = p.process_file_atomic(
            str(f1),
            'SONE-753 TITLE.mp4',
            None,
            str(out),
        )
        assert ok is False
        assert f1.exists()
        assert not (out / 'SONE-753 TITLE.mp4').exists()
        assert result['video_moved'] is False
        assert result['image_downloaded'] is False
        assert '图片URL' in message


def test_process_file_atomic_rolls_back_if_image_finalize_fails():
    class BrokenProcessor(AtomicProcessor):
        def _move_temp_image_to_final(self, temp_image_path, final_image_path):
            raise RuntimeError('boom')

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src = root / 'src'
        out = root / 'Finish'
        src.mkdir()
        out.mkdir()
        f1 = src / 'SONE-753.mp4'
        f1.write_bytes(b'a' * 1024 * 32)
        p = BrokenProcessor(_dummy_download, _sanitize)
        ok, result, message = p.process_file_atomic(
            str(f1),
            'SONE-753 TITLE.mp4',
            'http://example/image.jpg',
            str(out),
        )
        assert ok is False
        assert f1.exists()
        assert not (out / 'SONE-753 TITLE.mp4').exists()
        assert not (out / 'SONE-753 TITLE.jpg').exists()
        assert result['video_moved'] is False
        assert result['rollback_ok'] is True
        assert '原子操作失败' in message


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


def test_process_series_group_atomic_avoids_duplicate_planned_targets():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src = root / 'src'
        out = root / 'Finish'
        src.mkdir()
        out.mkdir()
        f1 = src / 'ABF-139-1a.mp4'
        f2 = src / 'ABF-139-1b.mp4'
        f1.write_bytes(b'a' * 1024 * 32)
        f2.write_bytes(b'b' * 1024 * 32)
        p = AtomicProcessor(_dummy_download, _sanitize)
        ok, result, message = p.process_series_group_atomic(
            [(str(f1), '1'), (str(f2), '1')],
            'ABF-139 TITLE',
            'http://example/image.jpg',
            str(out),
        )
        assert ok is True, message
        assert not f1.exists() and not f2.exists()
        assert (out / 'ABF-139 TITLE-1.mp4').exists()
        assert (out / 'ABF-139 TITLE-1_1.mp4').exists()
        assert sorted(Path(path).name for path in result['video_paths']) == [
            'ABF-139 TITLE-1.mp4',
            'ABF-139 TITLE-1_1.mp4',
        ]


def test_process_series_group_atomic_requires_image_url_and_keeps_sources():
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
            None,
            str(out),
        )
        assert ok is False
        assert f1.exists() and f2.exists()
        assert not (out / 'ABF-139 TITLE-1.mp4').exists()
        assert not (out / 'ABF-139 TITLE-2.mp4').exists()
        assert result['image_downloaded'] is False
        assert '图片URL' in message


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
