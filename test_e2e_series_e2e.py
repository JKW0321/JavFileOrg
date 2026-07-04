#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_e2e_series_e2e.py
=======================

v1.4.4 Bug 3 修复的端到端验证。

不依赖网络。在 /tmp 下创建 3 个带完整标题的"序列视频文件"（空文件即可），
mock extract_content 返回固定 title + 用 PIL 生成一张真实可用的 jpg，
跑一次完整的 process_series_group，最后断言 Finish/ 目录里有：
  - 恰好 1 张 .jpg
  - 恰好 3 个 .mp4，文件名带 -1/-2/-3
  - 视频源文件全部被移走（不在源目录了）

运行:
    python3 test_e2e_series_e2e.py
"""
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jav_file_organizer as jfo_mod


# ---------------------------------------------------------------------------
# Mock 工厂：构造一个 JavFileOrganizer 实例，但不启动 GUI、不连网络
# ---------------------------------------------------------------------------

class _FakeLog:
    """log_text 的替身 — 收集所有日志条目"""
    def __init__(self):
        self.entries = []
        self._line = 0
    def insert(self, idx, s):
        self.entries.append(s)
    def see(self, *args): pass
    def index(self, *args): return "1.0"
    def tag_add(self, *args, **kwargs): pass
    def tag_config(self, *args, **kwargs): pass
    def delete(self, *args): pass


class _FakeWindow:
    def __init__(self):
        self.log_text = _FakeLog()
    def update(self): pass
    def update_idletasks(self): pass
    def after(self, ms, fn): fn()


def make_mock_organizer():
    """构造一个不依赖 GUI 完整初始化的实例"""
    obj = jfo_mod.JavFileOrganizer.__new__(jfo_mod.JavFileOrganizer)
    obj.window = _FakeWindow()
    obj.log_text = _FakeLog()      # 主程序 self.log_text.insert(...) 直接挂在 obj 上
    obj.stop_processing = False
    return obj


# ---------------------------------------------------------------------------
# 工具：生成一张最小的合法 jpg
# ---------------------------------------------------------------------------

def make_dummy_jpg(path: str):
    """写一张 1x1 像素的 jpg — AtomicProcessor 会用 PIL.open 验证它"""
    img = Image.new('RGB', (1, 1), color=(255, 0, 0))
    img.save(path, 'JPEG')


def make_dummy_video(path: str, size_bytes: int = 1024):
    """写一个伪视频文件（空内容也行，process_series_group 不读内容）"""
    with open(path, 'wb') as f:
        f.write(b'\x00' * size_bytes)


# ---------------------------------------------------------------------------
# 场景 1：用户报告的 bug — 带完整标题的 3 集序列
# ---------------------------------------------------------------------------

def test_series_with_full_title():
    """核心 bug 场景：3 个带完整标题的序列文件，期望 1 张 jpg + 3 个 -N.mp4"""
    obj = make_mock_organizer()

    # 用临时目录
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / 'source'
        finish = Path(tmp) / 'Finish'
        src.mkdir()
        finish.mkdir()

        # 创建 3 个带完整标题的"视频"（最常见的真实文件名）
        video_names = [
            'ABF-139-1 美少女と、貸し切り温泉と、濃密性交と。.mp4',
            'ABF-139-2 美少女と、貸し切り温泉と、濃密性交と。.mp4',
            'ABF-139-3 美少女と、貸し切り温泉と、濃密性交と。.mp4',
        ]
        for name in video_names:
            make_dummy_video(str(src / name))

        # 准备一张 dummy jpg 在固定位置（mock 的 download_image 写到这）
        dummy_jpg_path = str(Path(tmp) / 'fake_image.jpg')
        make_dummy_jpg(dummy_jpg_path)

        # Mock extract_content：返回固定 title + image_url
        def fake_extract_content(search_query, website_config):
            return ('ABF-139 美少女と、貸し切り温泉と、濃密性交と。', 'http://fake/image.jpg')

        # Mock download_image：把 dummy jpg 复制到目标路径
        def fake_download_image(url, dest_path):
            shutil.copy(dummy_jpg_path, dest_path)
            return True

        obj.extract_content = fake_extract_content
        obj.download_image = fake_download_image

        # 初始化 atomic_processor（它要 download_func + sanitize_func）
        from atomic_processor_v11 import AtomicProcessor
        obj.atomic_processor = AtomicProcessor(obj.download_image, obj.sanitize_filename)

        # detect → 应该识别成 1 个序列组，3 个文件
        groups, standalone = obj.detect_series_files([str(src / n) for n in video_names])
        assert 'ABF-139' in groups, f"期望识别成序列组，实际 {groups}"
        assert len(groups['ABF-139']) == 3
        assert standalone == [], f"期望 standalone 为空，实际 {standalone}"
        print(f"  ✅ detect_series_files 正确识别成 1 个序列组")

        # 跑 process_series_group
        website_config = {'name': 'fake'}
        success_count, image_success = obj.process_series_group(
            base_code='ABF-139',
            files=groups['ABF-139'],
            folder_path=str(src),
            finish_folder=str(finish),
            website_config=website_config,
            max_length=None,
        )

        # === 断言 ===
        # 1. 3 个视频全部成功移动
        assert success_count == 3, f"期望 3 个视频成功，实际 {success_count}"
        print(f"  ✅ success_count = 3")

        # 2. Finish 目录里恰好 1 张 jpg + 3 个 mp4
        finish_files = sorted(os.listdir(finish))
        jpgs = [f for f in finish_files if f.endswith('.jpg')]
        mp4s = [f for f in finish_files if f.endswith('.mp4')]
        print(f"  Finish/ 内容: {finish_files}")
        assert len(jpgs) == 1, f"期望 1 张 jpg，实际 {len(jpgs)}: {jpgs}"
        assert len(mp4s) == 3, f"期望 3 个 mp4，实际 {len(mp4s)}: {mp4s}"
        print(f"  ✅ Finish/ 恰好 1 张 jpg + 3 个 mp4")

        # 3. 共享封面命名为 title（process_series_group 第 929 行就是 f"{title}.jpg"）
        assert jpgs[0] == 'ABF-139 美少女と、貸し切り温泉と、濃密性交と。.jpg', \
            f"共享封面命名错: {jpgs[0]}"
        print(f"  ✅ 共享封面命名为 {jpgs[0]!r}（不带序列号）")

        # 4. 视频命名带 -1/-2/-3
        expected_seqs = {'-1', '-2', '-3'}
        for mp4 in mp4s:
            assert any(s in mp4 for s in expected_seqs), f"视频 {mp4!r} 缺少序列号"
        print(f"  ✅ 3 个视频都带 -1/-2/-3 后缀: {mp4s}")

        # 5. 源目录应该被清空
        src_files = os.listdir(src)
        assert src_files == [], f"源目录应该空了，实际还有: {src_files}"
        print(f"  ✅ 源目录已被清空")

        # 6. 检查封面文件名末尾不带 "-N.mp4" 形式的序列号
        # (用户报的现象：'图片-1、视频-1' — 即封面带 -1 后缀)
        # 注：不能用 '-1' in name 这种包含检查，因为 'ABF-139' 也含 '-1' 片段
        for j in jpgs:
            assert not re.search(r'-\d+\.jpg$', j), \
                f"封面不应带 -N.jpg 后缀（用户报的 bug），实际 {j}"
        print(f"  ✅ jpg 不带 -N 序列号后缀（bug 现象消失）")

    print(f"\n  🎉 场景 1 通过：带完整标题的序列被正确识别成组\n")


# ---------------------------------------------------------------------------
# 场景 2：字母后缀 + 下载站前缀（最棘手的组合）
# ---------------------------------------------------------------------------

def test_series_alpha_with_download_site_prefix():
    """4k2.com@RBD011a.mp4 + 4k2.com@RBD011b.mp4 + 4k2.com@RBD011c.mp4"""
    obj = make_mock_organizer()

    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / 'source'
        finish = Path(tmp) / 'Finish'
        src.mkdir()
        finish.mkdir()

        video_names = [
            '4k2.com@RBD011a 美少女.mp4',
            '4k2.com@RBD011b 美少女.mp4',
            '4k2.com@RBD011c 美少女.mp4',
        ]
        for name in video_names:
            make_dummy_video(str(src / name))

        dummy_jpg_path = str(Path(tmp) / 'fake.jpg')
        make_dummy_jpg(dummy_jpg_path)

        def fake_extract_content(q, cfg):
            return ('RBD-011 美少女と、貸し切り温泉', 'http://fake/image.jpg')

        def fake_download_image(url, dest):
            shutil.copy(dummy_jpg_path, dest)
            return True

        obj.extract_content = fake_extract_content
        obj.download_image = fake_download_image

        from atomic_processor_v11 import AtomicProcessor
        obj.atomic_processor = AtomicProcessor(obj.download_image, obj.sanitize_filename)

        # detect
        groups, standalone = obj.detect_series_files([str(src / n) for n in video_names])
        assert 'RBD-011' in groups, f"期望识别成 RBD-011 组，实际 {groups}"
        assert len(groups['RBD-011']) == 3
        print(f"  ✅ 下载站前缀 + 字母后缀被正确识别成组")

        # 处理
        obj.process_series_group(
            base_code='RBD-011',
            files=groups['RBD-011'],
            folder_path=str(src),
            finish_folder=str(finish),
            website_config={'name': 'fake'},
            max_length=None,
        )

        finish_files = sorted(os.listdir(finish))
        jpgs = [f for f in finish_files if f.endswith('.jpg')]
        mp4s = [f for f in finish_files if f.endswith('.mp4')]
        print(f"  Finish/ 内容: {finish_files}")

        assert len(jpgs) == 1
        assert len(mp4s) == 3
        # 视频应有 a/b/c 后缀（字母序列）
        assert any('-a' in m or m.endswith('a.mp4') for m in mp4s) or \
               any(re.search(r'-1\.mp4$', m) for m in mp4s), \
               f"视频应该带 -a/-1/-2/-3 后缀，实际 {mp4s}"
        print(f"  ✅ 视频命名带序列后缀")

        # 检查 jpg 不带网站前缀
        for j in jpgs:
            assert '4k2.com' not in j, f"封面不应该带下载站前缀，实际 {j}"
            assert 'javbus.com' not in j
            assert not re.search(r'-\d+\.jpg$', j)
        print(f"  ✅ jpg 不带下载站前缀和序列号")

    print(f"\n  🎉 场景 2 通过\n")


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    print("=" * 70)
    print("v1.4.4 Bug 3 修复 — 序列文件端到端测试")
    print("=" * 70)
    print()

    failed = 0

    tests = [
        ('场景 1: 带完整标题的 3 集序列', test_series_with_full_title),
        ('场景 2: 字母后缀 + 下载站前缀', test_series_alpha_with_download_site_prefix),
    ]

    for name, fn in tests:
        print(f"\n[{name}]")
        try:
            fn()
        except AssertionError as e:
            print(f"  ❌ FAILED: {e}")
            failed += 1
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"  ❌ ERROR: {e}")
            failed += 1

    print()
    print("=" * 70)
    print(f"结果: {len(tests) - failed}/{len(tests)} 通过")
    print("=" * 70)
    sys.exit(0 if failed == 0 else 1)
