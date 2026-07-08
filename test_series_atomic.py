#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Atomic series transaction tests."""
import tempfile
import errno
import threading
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
        assert not (out / '.jfo_transactions').exists()
        assert result['image_downloaded'] is True


def test_atomic_processors_use_isolated_temp_dirs_for_parallel_runs():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src1 = root / 'src1'
        src2 = root / 'src2'
        out1 = root / 'Finish1'
        out2 = root / 'Finish2'
        src1.mkdir()
        src2.mkdir()
        out1.mkdir()
        out2.mkdir()
        f1 = src1 / 'SONE-753.mp4'
        f2 = src2 / 'SONE-753.mp4'
        f1.write_bytes(b'a' * 1024 * 32)
        f2.write_bytes(b'b' * 1024 * 32)

        p1 = AtomicProcessor(_dummy_download, _sanitize)
        p2 = AtomicProcessor(_dummy_download, _sanitize)
        assert p1.temp_dir != p2.temp_dir

        results = []

        def run(processor, file_path, out):
            results.append(processor.process_file_atomic(
                str(file_path),
                'SONE-753 TITLE.mp4',
                'http://example/image.jpg',
                str(out),
            ))

        t1 = threading.Thread(target=run, args=(p1, f1, out1))
        t2 = threading.Thread(target=run, args=(p2, f2, out2))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert len(results) == 2
        assert all(ok for ok, _, _ in results)
        assert (out1 / 'SONE-753 TITLE.mp4').exists()
        assert (out2 / 'SONE-753 TITLE.mp4').exists()
        assert (out1 / 'SONE-753 TITLE.jpg').exists()
        assert (out2 / 'SONE-753 TITLE.jpg').exists()


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


def test_process_file_atomic_preflights_target_disk_space():
    class FullDiskProcessor(AtomicProcessor):
        def _available_bytes(self, path):
            return 1024

        def _same_filesystem(self, source_path, target_dir):
            return False

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src = root / 'src'
        out = root / 'Finish'
        src.mkdir()
        out.mkdir()
        f1 = src / 'SONE-753.mp4'
        f1.write_bytes(b'a' * 1024 * 32)
        p = FullDiskProcessor(_dummy_download, _sanitize)
        ok, result, message = p.process_file_atomic(
            str(f1),
            'SONE-753 TITLE.mp4',
            'http://example/image.jpg',
            str(out),
        )

        assert ok is False
        assert result['status'] == 'failed'
        assert f1.exists()
        assert not (out / 'SONE-753 TITLE.mp4').exists()
        assert not (out / 'SONE-753 TITLE.jpg').exists()
        assert not (out / '.jfo_transactions').exists()
        assert '目标磁盘空间不足' in message


def test_process_file_atomic_marks_active_transaction_during_commit_and_rollback():
    class BrokenAfterMoveProcessor(AtomicProcessor):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.active_during_move = None
            self.active_during_rollback = None

        def _move_video(self, source_path, target_path):
            self.active_during_move = self.has_active_transaction()
            super()._move_video(source_path, target_path)

        def _fsync_committed_path(self, path):
            if str(path).endswith('.mp4') and Path(path).parent.name == 'Finish':
                raise RuntimeError('forced fsync failure')
            return None

        def _rollback_video(self, target_path, original_path):
            self.active_during_rollback = self.has_active_transaction()
            return super()._rollback_video(target_path, original_path)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src = root / 'src'
        out = root / 'Finish'
        src.mkdir()
        out.mkdir()
        f1 = src / 'SONE-753.mp4'
        f1.write_bytes(b'a' * 1024 * 32)
        p = BrokenAfterMoveProcessor(_dummy_download, _sanitize)
        ok, result, message = p.process_file_atomic(
            str(f1),
            'SONE-753 TITLE.mp4',
            'http://example/image.jpg',
            str(out),
        )

        assert ok is False
        assert result['rollback_ok'] is True
        assert p.active_during_move is True
        assert p.active_during_rollback is True
        assert p.has_active_transaction() is False


def test_move_video_cross_filesystem_commits_from_target_temp_file():
    class CrossDeviceProcessor(AtomicProcessor):
        def _rename_video(self, source_path, target_path):
            raise OSError(errno.EXDEV, 'cross-device link')

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src = root / 'src'
        out = root / 'Finish'
        src.mkdir()
        out.mkdir()
        f1 = src / 'SONE-753.mp4'
        target = out / 'SONE-753 TITLE.mp4'
        f1.write_bytes(b'a' * 1024 * 32)
        p = CrossDeviceProcessor(_dummy_download, _sanitize)

        p._move_video(str(f1), str(target))

        assert not f1.exists()
        assert target.read_bytes() == b'a' * 1024 * 32
        assert not list(out.glob('*.jfo-tmp'))


def test_recover_pending_transaction_removes_duplicate_target_and_keeps_source():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src = root / 'src'
        out = root / 'Finish'
        src.mkdir()
        out.mkdir()
        source = src / 'SONE-753.mp4'
        target = out / 'SONE-753 TITLE.mp4'
        source.write_bytes(b'a' * 1024 * 32)
        target.write_bytes(b'a' * 1024 * 32)
        p = AtomicProcessor(_dummy_download, _sanitize)
        journal_path = p._transaction_journal_path(str(source), str(target))
        p._write_transaction_journal(journal_path, {
            'status': 'target-committed',
            'source_path': str(source),
            'target_path': str(target),
            'temp_path': None,
            'source_size': source.stat().st_size,
        })

        actions = p.recover_pending_transactions(str(out))

        assert actions == ['rolled-back-duplicate-target']
        assert source.exists()
        assert not target.exists()
        assert not journal_path.exists()


def test_recover_pending_operation_rolls_back_video_and_image():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src = root / 'src'
        out = root / 'Finish'
        src.mkdir()
        out.mkdir()
        source = src / 'SONE-753.mp4'
        target = out / 'SONE-753 TITLE.mp4'
        final_image = out / 'SONE-753 TITLE.jpg'
        target.write_bytes(b'a' * 1024 * 32)
        final_image.write_bytes(b'partial image')

        p = AtomicProcessor(_dummy_download, _sanitize)
        temp_image = p.temp_dir / 'SONE-753 TITLE.jpg'
        temp_image.write_bytes(b'temp image')
        journal_path = p._operation_journal_path(str(source), str(target))
        p._write_transaction_journal(journal_path, {
            'kind': 'file-operation',
            'status': 'committing',
            'sources': [{
                'source_path': str(source),
                'target_path': str(target),
                'source_size': target.stat().st_size,
            }],
            'temp_image_path': str(temp_image),
            'final_image_path': str(final_image),
        })

        actions = p.recover_pending_transactions(str(out))

        assert actions == ['rolled-back-operation:1']
        assert source.exists()
        assert source.read_bytes() == b'a' * 1024 * 32
        assert not target.exists()
        assert not final_image.exists()
        assert not temp_image.exists()
        assert not journal_path.exists()


def test_recover_pending_operation_keeps_journal_if_final_image_cleanup_fails():
    class BrokenImageCleanupProcessor(AtomicProcessor):
        def _remove_final_image(self, final_image_path):
            return False

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src = root / 'src'
        out = root / 'Finish'
        src.mkdir()
        out.mkdir()
        source = src / 'SONE-753.mp4'
        target = out / 'SONE-753 TITLE.mp4'
        final_image = out / 'SONE-753 TITLE.jpg'
        target.write_bytes(b'a' * 1024 * 32)
        final_image.write_bytes(b'partial image')

        p = BrokenImageCleanupProcessor(_dummy_download, _sanitize)
        journal_path = p._operation_journal_path(str(source), str(target))
        p._write_transaction_journal(journal_path, {
            'kind': 'file-operation',
            'status': 'committing',
            'sources': [{
                'source_path': str(source),
                'target_path': str(target),
                'source_size': target.stat().st_size,
            }],
            'temp_image_path': None,
            'final_image_path': str(final_image),
        })

        actions = p.recover_pending_transactions(str(out))

        assert len(actions) == 1
        assert actions[0].startswith('unresolved-operation:image-remove-failed')
        assert source.exists()
        assert not target.exists()
        assert final_image.exists()
        assert journal_path.exists()


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


def test_process_file_atomic_cancel_after_download_keeps_source():
    stop = {'value': False}

    def download_then_stop(url, dest):
        ok = _dummy_download(url, dest)
        stop['value'] = True
        return ok

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src = root / 'src'
        out = root / 'Finish'
        src.mkdir()
        out.mkdir()
        f1 = src / 'SONE-753.mp4'
        f1.write_bytes(b'a' * 1024 * 32)
        p = AtomicProcessor(download_then_stop, _sanitize, stop_requested=lambda: stop['value'])

        ok, result, message = p.process_file_atomic(
            str(f1),
            'SONE-753 TITLE.mp4',
            'http://example/image.jpg',
            str(out),
        )

        assert ok is False
        assert result['status'] == 'cancelled'
        assert f1.exists()
        assert not (out / 'SONE-753 TITLE.mp4').exists()
        assert not (out / 'SONE-753 TITLE.jpg').exists()
        assert '用户取消' in message


def test_process_file_atomic_cancel_during_download_is_cancelled_not_failed():
    stop = {'value': False}

    def cancelled_download(url, dest):
        stop['value'] = True
        return False

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src = root / 'src'
        out = root / 'Finish'
        src.mkdir()
        out.mkdir()
        f1 = src / 'SONE-753.mp4'
        f1.write_bytes(b'a' * 1024 * 32)
        p = AtomicProcessor(cancelled_download, _sanitize, stop_requested=lambda: stop['value'])

        ok, result, message = p.process_file_atomic(
            str(f1),
            'SONE-753 TITLE.mp4',
            'http://example/image.jpg',
            str(out),
        )

        assert ok is False
        assert result['status'] == 'cancelled'
        assert result['image_downloaded'] is False
        assert f1.exists()
        assert not any(out.iterdir())
        assert '用户取消' in message


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


def test_process_file_atomic_removes_final_image_if_image_fsync_fails():
    class BrokenImageSyncProcessor(AtomicProcessor):
        def _fsync_committed_path(self, path):
            if str(path).endswith('.jpg'):
                raise RuntimeError('image fsync failed')
            return super()._fsync_committed_path(path)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src = root / 'src'
        out = root / 'Finish'
        src.mkdir()
        out.mkdir()
        f1 = src / 'SONE-753.mp4'
        f1.write_bytes(b'a' * 1024 * 32)
        p = BrokenImageSyncProcessor(_dummy_download, _sanitize)
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
        assert result['rollback_ok'] is True


def test_process_file_atomic_keeps_operation_journal_if_final_image_cleanup_fails():
    class BrokenImageCleanupProcessor(AtomicProcessor):
        def _fsync_committed_path(self, path):
            if str(path).endswith('.jpg'):
                raise RuntimeError('image fsync failed')
            return super()._fsync_committed_path(path)

        def _remove_final_image(self, final_image_path):
            return False

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src = root / 'src'
        out = root / 'Finish'
        src.mkdir()
        out.mkdir()
        f1 = src / 'SONE-753.mp4'
        f1.write_bytes(b'a' * 1024 * 32)
        p = BrokenImageCleanupProcessor(_dummy_download, _sanitize)
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
        assert list((out / '.jfo_transactions').glob('op_*.json'))


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


def test_process_series_group_atomic_preflights_target_disk_space():
    class FullDiskProcessor(AtomicProcessor):
        def _available_bytes(self, path):
            return 1024

        def _same_filesystem(self, source_path, target_dir):
            return False

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src = root / 'src'
        out = root / 'Finish'
        src.mkdir()
        out.mkdir()
        f1 = src / 'FC2-PPV-3690078-1.mp4'
        f2 = src / 'FC2-PPV-3690078-2.mp4'
        f1.write_bytes(b'a' * 1024 * 32)
        f2.write_bytes(b'b' * 1024 * 32)
        p = FullDiskProcessor(_dummy_download, _sanitize)
        ok, result, message = p.process_series_group_atomic(
            [(str(f1), '1'), (str(f2), '2')],
            'FC2-PPV-3690078 TITLE',
            'http://example/image.jpg',
            str(out),
        )

        assert ok is False
        assert result['status'] == 'failed'
        assert f1.exists() and f2.exists()
        assert not (out / 'FC2-PPV-3690078 TITLE-1.mp4').exists()
        assert not (out / 'FC2-PPV-3690078 TITLE-2.mp4').exists()
        assert not (out / 'FC2-PPV-3690078 TITLE.jpg').exists()
        assert not (out / '.jfo_transactions').exists()
        assert '目标磁盘空间不足' in message


def test_process_series_group_atomic_cancel_after_one_move_rolls_back_group():
    stop = {'value': False}

    class StopAfterFirstVideoProcessor(AtomicProcessor):
        def _fsync_committed_path(self, path):
            if str(path).endswith('.mp4') and Path(path).parent.name == 'Finish':
                stop['value'] = True

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
        p = StopAfterFirstVideoProcessor(_dummy_download, _sanitize, stop_requested=lambda: stop['value'])

        ok, result, message = p.process_series_group_atomic(
            [(str(f1), '1'), (str(f2), '2')],
            'ABF-139 TITLE',
            'http://example/image.jpg',
            str(out),
        )

        assert ok is False
        assert result['status'] == 'cancelled'
        assert result['rollback_ok'] is True
        assert f1.exists() and f2.exists()
        assert not (out / 'ABF-139 TITLE-1.mp4').exists()
        assert not (out / 'ABF-139 TITLE-2.mp4').exists()
        assert not (out / 'ABF-139 TITLE.jpg').exists()
        assert '用户取消' in message


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
