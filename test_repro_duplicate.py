#!/usr/bin/env python3
"""
test_repro_duplicate.py — 复现 _1 占位 bug 的候选场景

策略：mock 各种失败路径，看哪个能复现"图片完整 + 视频占位"
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path
from PIL import Image
sys.path.insert(0, '.')

from atomic_processor_v11 import AtomicProcessor


def make_jpg(p):
    Image.new('RGB', (1, 1), color=(255, 0, 0)).save(p, 'JPEG')


def show_finish(finish_dir, label):
    print(f"\n--- {label} ---")
    for f in sorted(os.listdir(finish_dir)):
        size = (Path(finish_dir) / f).stat().st_size
        marker = " ← 占位!" if size < 1000 else ""
        print(f"  {f}  ({size} bytes){marker}")


def scenario_video_move_fails_after_image_downloaded():
    """场景 A: 图片下载成功 + 验证通过，但视频 rename 抛异常
       → 看 atomic_processor 怎么处理
    """
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / 'src'
        finish = Path(tmp) / 'Finish'
        src.mkdir()
        finish.mkdir()

        # 准备
        real_video = src / 'ABF-139.mp4'
        real_video.write_bytes(b'\x00' * 1024 * 1024)

        dummy_jpg = Path(tmp) / 'src.jpg'
        make_jpg(str(dummy_jpg))

        # mock download_image: 成功 + 写一张有效 jpg
        def download(url, dest):
            shutil.copy(str(dummy_jpg), dest)
            return True

        # mock sanitize_filename: 原样返回
        def sanitize(name):
            return name

        processor = AtomicProcessor(download, sanitize)

        # 先让目标位置已存在一个视频（触发冲突）
        existing_video = finish / 'ABF-139.mp4'
        existing_video.write_bytes(b'\x00' * 100)  # 100 字节占位
        print(f"预设: Finish/ABF-139.mp4 = {existing_video.stat().st_size} 字节")

        success, info, msg = processor.process_file_atomic(
            str(real_video), 'ABF-139.mp4', 'http://fake/img.jpg', str(finish)
        )
        print(f"success={success}, msg={msg}")
        print(f"info={info}")
        show_finish(finish, "场景 A 结束后")


def scenario_source_video_is_small():
    """场景 B: 源视频文件本身就是 100 字节（用户场景里那个'占位视频'）"""
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / 'src'
        finish = Path(tmp) / 'Finish'
        src.mkdir()
        finish.mkdir()

        # 源文件本身就只有 100 字节
        real_video = src / 'ABF-139.mp4'
        real_video.write_bytes(b'\x00' * 100)
        print(f"source/ABF-139.mp4 = {real_video.stat().st_size} 字节（用户场景的'占位视频'）")

        dummy_jpg = Path(tmp) / 'src.jpg'
        make_jpg(str(dummy_jpg))

        def download(url, dest):
            shutil.copy(str(dummy_jpg), dest)
            return True
        def sanitize(name):
            return name

        processor = AtomicProcessor(download, sanitize)

        success, info, msg = processor.process_file_atomic(
            str(real_video), 'ABF-139.mp4', 'http://fake/img.jpg', str(finish)
        )
        print(f"success={success}, msg={msg}")
        show_finish(finish, "场景 B 结束后")


if __name__ == '__main__':
    print("=" * 70)
    print("复现 _1 占位 bug")
    print("=" * 70)

    print("\n### 场景 A: 目标位置已有同名视频 ###")
    scenario_video_move_fails_after_image_downloaded()

    print("\n\n### 场景 B: source 里源文件本身就小 ###")
    scenario_source_video_is_small()
