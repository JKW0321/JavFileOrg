#!/usr/bin/env python3
"""
test_gui_walkthrough.py
=======================

不依赖 tkinter 渲染 — 直接驱动 GUI 后台逻辑 (_process_files_worker)。

模拟用户操作：
  1. 启动 GUI
  2. 选择 JavHoo 数据源
  3. 选择 source 文件夹（3 个带完整标题的序列视频）
  4. 点击 "开始处理"
  5. 程序自动识别序列、搜索 JavHoo、下载封面、移动文件
  6. 收集所有 self.log() 输出，dump 到 stdout

不连网络时跳过 JavHoo 实际抓取，用 mock image 代替，但流程完整跑。
"""
import os
import sys
import shutil
import tempfile
import threading
import time
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

# 让 Selenium 启动快速失败（避免 headless Chrome 拉起阻塞测试）
os.environ.setdefault('DISPLAY', ':99')  # 防止 Selenium 启动真实浏览器

import jav_file_organizer as jfo_mod
from atomic_processor_v11 import AtomicProcessor


# ---------------------------------------------------------------------------
# Mock 替身：GUI 各种 widget
# ---------------------------------------------------------------------------

class FakeText:
    """scrolledtext.ScrolledText 替身"""
    def __init__(self):
        self.content = ""
    def insert(self, idx, s):
        self.content += s
        # 镜像 GUI 日志到 stdout
        sys.stdout.write(s)
        sys.stdout.flush()
    def see(self, *a): pass
    def index(self, *a): return "1.0"
    def delete(self, *a, **kw): pass
    def tag_add(self, *a, **kw): pass
    def tag_config(self, *a, **kw): pass
    def get(self, *a): return self.content


class FakeWindow:
    def __init__(self, log_text):
        self.log_text = log_text
        self.title_calls = []
    def title(self, *args):
        self.title_calls.append(args)
    def update(self): pass
    def update_idletasks(self): pass
    def after(self, ms, fn): fn()
    def protocol(self, *a, **kw): pass


class FakeVar:
    """tkinter.StringVar/IntVar/DoubleVar 替身"""
    def __init__(self, value=None):
        self.value = value
        self._listeners = []
    def get(self): return self.value
    def set(self, v):
        self.value = v
        for cb in self._listeners:
            try: cb()
            except: pass
    def trace_add(self, mode, cb):
        if mode == 'w': self._listeners.append(cb)
    def trace(self, mode, cb):
        # 老接口
        self.trace_add(mode, cb)


class FakeProgressBar:
    def __init__(self):
        self.value = 0
    def __setitem__(self, k, v):
        if k == 'value': self.value = v
    def __getitem__(self, k):
        return self.value


# ---------------------------------------------------------------------------
# Builder：手工构造一个能跑 _process_files_worker 的实例
# ---------------------------------------------------------------------------

def make_organizer(folder_path, finish_path):
    """构造 JavFileOrganizer 实例，绕过 init_gui（不会创建真实 tk widget）"""
    obj = jfo_mod.JavFileOrganizer.__new__(jfo_mod.JavFileOrganizer)

    # window 和 log_text
    log_text = FakeText()
    obj.window = FakeWindow(log_text)
    obj.log_text = log_text
    obj.status_var = FakeVar('就绪')

    # 进度相关
    obj.progress_bar = FakeProgressBar()
    obj.progress_var = FakeVar('🔄 处理中: 0/0')
    obj.progress_percent_var = FakeVar('0%')
    obj.speed_var = FakeVar('⚡ 速度: 0.0 文件/秒')

    # 控制按钮状态
    obj.start_btn = type('FakeBtn', (), {'config': lambda *a, **kw: None})()
    obj.stop_btn = type('FakeBtn', (), {'config': lambda *a, **kw: None})()
    obj.test_btn = type('FakeBtn', (), {'config': lambda *a, **kw: None})()

    # 用户选择
    obj.folder_var = FakeVar(str(folder_path))
    obj.website_var = FakeVar('javhoo')
    obj.search_url_var = FakeVar('https://www.javhoo.com/search/{query}')
    obj.text_selector_var = FakeVar('title')
    obj.image_selector_var = FakeVar('img')
    obj.max_filename_length_var = FakeVar('')
    obj.preserve_actor_var = FakeVar(True)
    obj.batch_count_var = FakeVar('')

    # 网站配置（和真实 GUI 一样）
    obj.website_configs = {
        'javhoo': {
            'name': 'JavHoo - 稳定快速',
            'search_url': 'https://www.javhoo.com/search/{query}',
            'detail_url_pattern': 'https://www.javhoo.com/{code_lower}',
            'title_selectors': ['article h2 a', 'h1', 'title'],
            'image_selectors': ['article img[data-src]', 'img[src*="pics.javhoo.net"]'],
            'requires_verification': False
        },
    }

    # 反爬虫 session（extract_content 会用到 self.anti_crawl.session）
    obj.session = type('FakeSession', (), {})()
    obj.anti_crawl = type('FakeAntiCrawl', (), {'session': obj.session})()

    # 下载图片函数（mock：复制 dummy jpg 到目标）
    dummy_jpg = Path(tempfile.gettempdir()) / 'walkthrough_dummy.jpg'
    if not dummy_jpg.exists():
        Image.new('RGB', (1, 1), color=(255, 100, 50)).save(str(dummy_jpg), 'JPEG')

    def fake_download(url, dest):
        shutil.copy(str(dummy_jpg), dest)
        return True
    obj.download_image = fake_download

    # extract_content mock（不连网络，直接返回固定 title）
    obj.extract_content = lambda q, cfg: (
        f'{q.upper()} 美少女と、貸し切り温泉と、濃密性交と。',
        'http://fake/image.jpg'
    )

    # atomic_processor
    obj.atomic_processor = AtomicProcessor(obj.download_image, obj.sanitize_filename)

    # stop flag
    obj.stop_processing = False

    # version / metadata（兼容 _process_files_worker 的 log）
    obj.version = 'v1.5.0-Selenium'
    obj.build_id = 'baseline-unified-tk9-selenium'
    obj.build_date = '2026-07-04'

    # video_extensions（_process_files_worker 需要）
    obj.video_extensions = {'.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v'}

    # image_download_queue（清理残留任务时用）
    obj.image_download_queue = []

    return obj


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def main():
    print("=" * 70)
    print("JAV 文件整理工具 v1.5.0-Selenium — GUI 完整流程演示")
    print("=" * 70)
    print()
    print("模拟场景：")
    print("  - 用户选择 source 文件夹（3 个带完整标题的序列视频）")
    print("  - 数据源: JavHoo（用 mock 的 extract_content，不连网络）")
    print("  - 点击 '开始处理'")
    print("  - 程序自动：detect 序列 → 搜索 → 下图 → 移动文件")
    print()
    print("-" * 70)
    print("GUI 日志输出（实时）:")
    print("-" * 70)
    print()

    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp) / 'source'
        finish = Path(tmp) / 'Finish'
        folder.mkdir()
        finish.mkdir()

        # 创建 3 个真实视频文件
        video_names = [
            'ABF-139-1 美少女 第1話.mp4',
            'ABF-139-2 美少女 第2話.mp4',
            'ABF-139-3 美少女 第3話.mp4',
        ]
        for n in video_names:
            (folder / n).write_bytes(b'\x00' * (1024 * 1024))  # 1MB

        # 同时放一个独立文件（不是序列）
        (folder / 'SONE-753.mp4').write_bytes(b'\x00' * (512 * 1024))

        organizer = make_organizer(folder, finish)
        # _process_files_worker 从 self.folder_var.get() 读路径，无参数
        organizer._process_files_worker()

        # 在临时目录被销毁前，把 Finish 内容 dump 到永久位置
        import shutil
        demo_finish = Path('/tmp/jav_demo_finish')
        if demo_finish.exists():
            shutil.rmtree(demo_finish)
        shutil.copytree(finish, demo_finish)
        print(f"\n💾 Finish 内容已保存到 {demo_finish}（demo 结束后仍可查看）")

        print()
        print("-" * 70)
        print(f"Finish/ 最终状态:")
        print("-" * 70)
        for f in sorted(os.listdir(finish)):
            size = (finish / f).stat().st_size
            print(f"  {f}  ({size} bytes)")

        print()
        print("=" * 70)
        print("演示完成 — 上面的日志就是你在 GUI 日志框里会看到的实时输出")
        print("=" * 70)

        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(0)


if __name__ == '__main__':
    # 提前把 stdin 替换为空，避开 atomic_processor.__del__ 可能的阻塞调用
    try:
        sys.stdin = open(os.devnull, 'r')
    except Exception:
        pass
    main()
