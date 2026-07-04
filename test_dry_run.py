#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_dry_run.py
===============

Dry-run 模式下：
- 不移动文件
- 不下载图片
- 生成日志文件
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jav_file_organizer as jfo_mod
from test_gui_walkthrough import make_organizer


def test_dry_run_does_not_move_files():
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp) / 'source'
        finish = folder / 'Finish'
        folder.mkdir()
        finish.mkdir()
        (folder / 'ABF-139-1 美少女 第1話.mp4').write_bytes(b'0' * (1024 * 1024))
        (folder / 'SONE-753.mp4').write_bytes(b'0' * (1024 * 1024))

        organizer = make_organizer(folder, finish)
        organizer.dry_run_var.set(True)
        organizer.extract_content = lambda *a, **kw: (_ for _ in ()).throw(AssertionError('dry-run should not call provider'))
        organizer._process_files_worker()

        assert (folder / 'ABF-139-1 美少女 第1話.mp4').exists()
        assert (folder / 'SONE-753.mp4').exists()
        assert not any(f.suffix.lower() == '.jpg' for f in finish.iterdir())
        logs_dir = folder / 'JFO_Logs'
        assert logs_dir.exists()
        assert any(p.suffix == '.log' for p in logs_dir.iterdir())
