#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_batch_filters.py
=====================

批处理前过滤规则测试：
- 跳过 macOS AppleDouble 文件 `._*`
- 跳过其他隐藏文件 `.xxx`
- 只保留支持的视频扩展名
"""
import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jav_file_organizer as jfo_mod


@pytest.fixture
def organizer():
    obj = jfo_mod.JavFileOrganizer.__new__(jfo_mod.JavFileOrganizer)
    obj.video_extensions = {'.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v'}
    obj.minimum_video_size_bytes = 16 * 1024
    return obj


@pytest.mark.parametrize('filename,expected', [
    ('._ABF-123.mp4', True),
    ('.DS_Store', True),
    ('.hidden.mp4', True),
    ('ABF-123.mp4', False),
    ('movie.mkv', False),
])
def test_should_skip_video_file(organizer, filename, expected):
    assert organizer._should_skip_video_file(filename) is expected


def test_suspicious_small_video(organizer):
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp)
        tiny = p / 'tiny.mp4'
        tiny.write_bytes(b'1' * 4096)
        normal = p / 'normal.mp4'
        normal.write_bytes(b'1' * (20 * 1024))
        assert organizer._is_suspicious_small_video(str(tiny)) is True
        assert organizer._is_suspicious_small_video(str(normal)) is False


def test_collect_video_files_skips_hidden_and_appledouble(organizer):
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp)
        (p / 'ABF-123.mp4').write_bytes(b'1' * (32 * 1024))
        (p / 'movie.mkv').write_bytes(b'1' * (32 * 1024))
        (p / '._ABF-123.mp4').write_bytes(b'1')
        (p / '.hidden.mp4').write_bytes(b'1')
        (p / '.DS_Store').write_text('x')
        (p / 'tiny.mp4').write_bytes(b'1' * 4096)
        (p / 'readme.txt').write_text('x')

        scan = organizer._scan_video_files(str(p))
        result = sorted(scan['accepted'])
        assert result == ['ABF-123.mp4', 'movie.mkv']
        assert '._ABF-123.mp4' in scan['skipped_hidden']
        assert '.hidden.mp4' in scan['skipped_hidden']
        assert 'tiny.mp4' in scan['skipped_small']


def test_run_log_file_written(organizer):
    with tempfile.TemporaryDirectory() as tmp:
        organizer.version = 'v1-test'
        organizer.build_id = 'build-test'
        organizer.run_log_path = None
        organizer._run_log_lock = __import__('threading').Lock()
        path = organizer._start_run_log(tmp, 'javlibrary')
        organizer._write_run_log('[00:00:00] 📝 hello\n')
        organizer._close_run_log()
        content = Path(path).read_text(encoding='utf-8')
        assert '# version: v1-test' in content
        assert '# website: javlibrary' in content
        assert 'hello' in content
        assert '# ended_at:' in content
