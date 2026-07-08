#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
JAV File Organizer — 基线统一版本

说明：
- 这个文件历史上混入了多个阶段的版本号（v1.0 / v1.1 / v1.4.0 / v1.4.3 / v1.9.x）
- 从本次起，界面、启动信息、状态栏、构建信息统一使用同一组常量
- 历史注释保留用于追溯修复来源，但“当前版本”只认下方 BASELINE 常量
"""


# 网站 Logo 图标 (Base64 编码)
JAVBUS_ICON = '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'
JAVHOO_ICON = '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'

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import os
import sys
import threading
import time
from dataclasses import dataclass
import re
from datetime import datetime
import json
import shutil

from app_metadata import (
    APP_TITLE,
    BASELINE_BUILD_DATE,
    BASELINE_BUILD_ID,
    BASELINE_VERSION,
    CONFIG_FILENAME,
    STATUS_READY,
)

# 立即导入所有必需模块，避免v1.8的导入问题
try:
    import requests
    from PIL import Image, ImageTk
    print("✅ 所有模块导入成功")
except ImportError as e:
    print(f"❌ 模块导入失败: {e}")
    print("请安装依赖: pip install requests beautifulsoup4 pillow lxml")
    sys.exit(1)


@dataclass(frozen=True)
class ProcessingRequest:
    folder_path: str
    website: str
    website_config: dict
    dry_run: bool
    batch_count_text: str
    max_length_text: str


class OptimizedAntiCrawlHandler:
    """优化的反爬处理器 - 修复版"""
    
    def __init__(self, log_callback=None):
        self.session = requests.Session()
        self.log_callback = log_callback  # v1.4.3: 接收日志回调函数
        
        # v1.4.3: 初始化Selenium JAVLibrary
        self.selenium_javlibrary = None
        try:
            from selenium_javlibrary import SeleniumJAVLibrary
            # v1.5.1: 只要有 cookies 或已有 profile 状态，就优先无头。
            cookies_file = os.path.expanduser('~/.jav_organizer/javlibrary_selenium_cookies.pkl')
            profile_dir = os.path.expanduser('~/.jav_organizer/javlibrary_chrome_profile')
            has_cookies = os.path.exists(cookies_file)
            has_profile = os.path.isdir(profile_dir) and any(os.scandir(profile_dir))
            # Cloudflare 对 Selenium/无头特征很敏感。JAVLibrary 统一使用可见窗口，
            # 仍复用持久化 profile/cookie，但避免无头模式触发更强验证。
            use_headless = False
            self.selenium_javlibrary = SeleniumJAVLibrary(log_callback=self.log, headless=use_headless)
            if has_cookies or has_profile:
                reason = 'Cookie' if has_cookies else 'profile'
                self.log(f"✅ Selenium JAVLibrary已初始化（检测到已保存 {reason} 状态，使用可见窗口模式）", "INFO")
            else:
                self.log("✅ Selenium JAVLibrary已初始化（首次使用，显示浏览器窗口）", "INFO")
        except ImportError:
            self.log("⚠️ Selenium未安装，JAVLibrary将无法使用", "WARNING")
            self.log("💡 安装: pip install selenium", "INFO")
        
        self.setup_session()
    
    def setup_session(self):
        """设置Session配置"""
        # 设置请求头
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })
        
        # v1.4.3: 优化连接池配置
        from urllib3.util.retry import Retry
        
        retry_strategy = Retry(
            total=5,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS", "POST"]
        )
        
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=20,
            pool_maxsize=50,
            max_retries=retry_strategy,
            pool_block=False
        )
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)
    
    def log(self, message, level="INFO"):
        """日志输出（反爬虫处理器）。"""
        if self.log_callback:
            # 如果有回调函数，使用回调
            self.log_callback(message, level)
        else:
            # 否则直接打印
            icons = {
                "INFO": "📝",
                "SUCCESS": "✅",
                "WARNING": "⚠️",
                "ERROR": "❌"
            }
            icon = icons.get(level, "📝")
            print(f"{icon} {message}")


class JavFileOrganizer:
    """JAV File Organizer 基线版本实现。"""
    
    def __init__(self):
        self.version = BASELINE_VERSION
        self.build_date = BASELINE_BUILD_DATE
        self.build_id = BASELINE_BUILD_ID
        self.window = None
        self.session = None
        self.anti_crawl = None  # v1.9.3: 延迟初始化，等待 GUI 创建后
        self.is_processing = False
        self.stop_processing = False
        self._stop_event = threading.Event()
        self.run_log_path = None
        self._run_log_lock = threading.Lock()
        self.minimum_video_size_bytes = 16 * 1024  # 16KB：用于跳过 AppleDouble / 可疑伪视频
        self._progress_started_at = None
        self._progress_last_update_at = None
        self._progress_last_completed = 0
        self._progress_last_item_text = ""
        
        # v1.1 优化: 线程安全和性能优化相关属性
        self.metadata_cache = {}  # 元数据缓存
        self.cache_expire_time = 3600  # 缓存过期时间（秒）
        self.image_download_queue = []  # 图片下载队列
        
        # v1.3 原子操作处理器（在定义 download_image 和 sanitize_filename 方法后初始化）
        self.atomic_processor = None
        
        # 网站配置 - v1.9 修复版
        self.website_configs = {
            'javhoo': {
                'name': 'JavHoo - 稳定快速',
                'search_url': 'https://www.javhoo.com/search/{query}',   # v1.4.4: 改 /en/{query} → /search/{query}（实测新 URL）
                'detail_url_pattern': 'https://www.javhoo.com/{code_lower}',  # v1.4.4 新增：搜索后跳详情页拿高清封面
                'title_selectors': [
                    'article h2 a',  # v1.4.4: 搜索结果里的标题链接（最准）
                    'h1',             # 详情页标题
                    'title',          # 兜底
                ],
                'image_selectors': [
                    'article img[data-src]',      # 搜索结果封面（懒加载）
                    'article .thumbnail img',
                    'img[src*="pics.javhoo.net"]',
                    'a.dt-single-image img',
                    '.movie-poster img',
                ],
                'requires_verification': False
            },
            'javbus': {
                'name': 'JavBus - 内容丰富，智能验证',
                'search_url': 'https://www.javbus.com/{query}',
                'title_selectors': [
                    'title',
                    'h3',
                    '.movie-title',
                    '.title'
                ],
                'image_selectors': [
                    '.bigImage img',
                    'img[title]',
                    '.movie-poster img'
                ],
                'requires_verification': True
            },
            'javlibrary': {
                'name': 'JAVLibrary - 数据完整，高清封面',
                'search_url': 'https://www.javlibrary.com/en/vl_searchbyid.php?keyword={query}',
                'title_selectors': [
                    'title',
                    'h3.post-title',
                    '.post-title'
                ],
                'image_selectors': [
                    '#video_jacket_img',
                    'img#video_jacket_img',
                    '.video-cover img'
                ],
                'requires_verification': True,
                'use_special_handler': True  # v1.4: 使用特殊处理器
            },
            'bestjavporn': {
                'name': 'BestJavPorn - 日文源（实验）',
                'search_url': 'https://www.bestjavporn.com/ja/?s={query}',
                'title_selectors': [
                    'article h2 a',
                    'article .entry-title a',
                    'h1.entry-title',
                    'title',
                ],
                'image_selectors': [
                    'article img[data-src]',
                    'article img[src]',
                    '.post-thumbnail img',
                    '.video-cover img',
                    '.entry-content img',
                ],
                'requires_verification': True
            },
            'uncensored': {
                'name': '无码源 - 自动匹配内部站点（实验）',
                'search_url': 'internal uncensored provider router',
                'title_selectors': [
                    'h1',
                    'meta[property="og:title"]',
                    'title',
                ],
                'image_selectors': [
                    'meta[property="og:image"]',
                    'meta[name="twitter:image"]',
                    'img',
                ],
                'requires_verification': False
            }
        }
        
        # 支持的视频格式
        self.video_extensions = {'.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.rmvb'}
        
        # 初始化GUI
        self.init_gui()
        
        # 初始化网络会话
        self.init_session()
    
    def init_session(self):
        """初始化网络会话。"""
        self.session = requests.Session()
        
        # 设置请求头
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        })
        
        # v1.4.3: 优化连接池配置，提高稳定性和速度
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry
        
        # 配置重试策略 - 优化版：减少重试次数，快速失败
        retry_strategy = Retry(
            total=2,  # 减少重试次数：快速失败
            backoff_factor=0.5,  # 减少退避时间
            status_forcelist=[429, 500, 502, 503, 504],  # 需要重试的状态码
            allowed_methods=["HEAD", "GET", "OPTIONS", "POST"]  # 允许重试的方法
        )
        
        adapter = HTTPAdapter(
            pool_connections=10,  # 连接池大小
            pool_maxsize=20,  # 最大连接数
            max_retries=retry_strategy,
            pool_block=False  # 不阻塞
        )
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)
        
        # v1.3: 初始化原子操作处理器
        from atomic_processor_v11 import AtomicProcessor
        self.atomic_processor = AtomicProcessor(
            self.download_image,
            self.sanitize_filename,
            stop_requested=self._is_stop_requested,
        )
    
    def init_gui(self):
        """初始化 GUI 界面。"""
        self.window = tk.Tk()
        self.window.title(APP_TITLE)
        self.window.geometry("1000x700")
        self.window.resizable(True, True)
        
        # 创建主框架 - 双列布局
        main_frame = ttk.Frame(self.window)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # 左列：配置和设置
        left_frame = ttk.Frame(main_frame)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        
        # 右列：控制和日志
        right_frame = ttk.Frame(main_frame)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(5, 0))
        
        # === 左列内容 ===
        
        # 文件夹选择
        folder_frame = ttk.LabelFrame(left_frame, text="📁 文件夹选择", padding=10)
        folder_frame.pack(fill=tk.X, pady=(0, 10))
        
        folder_input_frame = ttk.Frame(folder_frame)
        folder_input_frame.pack(fill=tk.X)
        
        self.folder_var = tk.StringVar()
        folder_entry = ttk.Entry(folder_input_frame, textvariable=self.folder_var, font=("Arial", 10))
        folder_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        
        folder_btn = ttk.Button(folder_input_frame, text="选择文件夹", command=self.select_folder)
        folder_btn.pack(side=tk.RIGHT)
        
        # 网站选择
        website_frame = ttk.LabelFrame(left_frame, text="🌐 网站选择", padding=10)
        website_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.website_var = tk.StringVar(value='javbus')
        
        # 加载网站 logo
        try:
            import base64
            from PIL import Image, ImageTk
            from io import BytesIO
            
            # JavBus logo
            javbus_data = base64.b64decode(JAVBUS_ICON)
            javbus_img = Image.open(BytesIO(javbus_data))
            self.javbus_photo = ImageTk.PhotoImage(javbus_img)
            
            # JavHoo logo
            javhoo_data = base64.b64decode(JAVHOO_ICON)
            javhoo_img = Image.open(BytesIO(javhoo_data))
            self.javhoo_photo = ImageTk.PhotoImage(javhoo_img)
            
            # 创建单选按钮 - 使用 Grid 布局对齐 logo
            row = 0
            for key, config in self.website_configs.items():
                # 单选按钮
                rb = ttk.Radiobutton(website_frame, text=config['name'], 
                                   variable=self.website_var, value=key)
                rb.grid(row=row, column=0, sticky=tk.W, pady=2)
                
                # Logo 标签(固定在第 1 列)
                if key == 'javhoo':
                    logo_label = ttk.Label(website_frame, image=self.javhoo_photo)
                    logo_label.grid(row=row, column=1, sticky=tk.W, padx=(10, 0))
                elif key == 'javbus':
                    logo_label = ttk.Label(website_frame, image=self.javbus_photo)
                    logo_label.grid(row=row, column=1, sticky=tk.W, padx=(10, 0))
                
                row += 1
        except Exception as e:
            print(f"⚠️ 无法加载网站图标: {e}")
            # 降级方案:只显示文字
            for key, config in self.website_configs.items():
                rb = ttk.Radiobutton(website_frame, text=config['name'], 
                                   variable=self.website_var, value=key)
                rb.pack(anchor=tk.W, pady=2)
        
        # 网站配置
        config_frame = ttk.LabelFrame(left_frame, text="⚙️ 网站配置", padding=10)
        config_frame.pack(fill=tk.X, pady=(0, 10))
        
        # 搜索URL
        ttk.Label(config_frame, text="搜索URL:").pack(anchor=tk.W)
        self.search_url_var = tk.StringVar(value="https://www.javhoo.com/search/{query}")   # v1.4.4
        search_url_entry = ttk.Entry(config_frame, textvariable=self.search_url_var, font=("Arial", 9))
        search_url_entry.pack(fill=tk.X, pady=(2, 5))
        
        # 文字选择器
        ttk.Label(config_frame, text="文字选择器:").pack(anchor=tk.W)
        self.text_selector_var = tk.StringVar(value="title")
        text_selector_entry = ttk.Entry(config_frame, textvariable=self.text_selector_var, font=("Arial", 9))
        text_selector_entry.pack(fill=tk.X, pady=(2, 5))
        
        # 图片选择器
        ttk.Label(config_frame, text="图片选择器:").pack(anchor=tk.W)
        self.image_selector_var = tk.StringVar(value="a.dt-single-image img")
        image_selector_entry = ttk.Entry(config_frame, textvariable=self.image_selector_var, font=("Arial", 9))
        image_selector_entry.pack(fill=tk.X, pady=(2, 10))
        
        # 配置按钮
        config_btn_frame = ttk.Frame(config_frame)
        config_btn_frame.pack(anchor=tk.CENTER)
        
        save_config_btn = ttk.Button(config_btn_frame, text="💾 保存配置", command=self.save_config)
        save_config_btn.pack(side=tk.LEFT, padx=5)
        
        reset_config_btn = ttk.Button(config_btn_frame, text="🔄 重置默认", command=self.reset_config)
        reset_config_btn.pack(side=tk.LEFT, padx=5)
        
        process_frame = ttk.LabelFrame(left_frame, text="🔧 处理设置", padding=10)
        process_frame.pack(fill=tk.X, pady=(0, 10))
        
        # 文件名长度设置
        length_frame = ttk.Frame(process_frame)
        length_frame.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Label(length_frame, text="最大文件名长度:").pack(side=tk.LEFT)
        self.max_filename_length_var = tk.StringVar(value="80")
        length_entry = ttk.Entry(length_frame, textvariable=self.max_filename_length_var, width=10)
        length_entry.pack(side=tk.LEFT, padx=(5, 5))
        ttk.Label(length_frame, text="字符 (留空=不限制)").pack(side=tk.LEFT)
        
        # 演员名保留选项
        self.preserve_actor_var = tk.BooleanVar(value=True)
        preserve_cb = ttk.Checkbutton(process_frame, text="✅ 超出长度时优先保留演员名称", 
                                    variable=self.preserve_actor_var)
        preserve_cb.pack(anchor=tk.W, pady=(0, 5))
        
        # v1.9 简化：只用输入框控制批量处理
        batch_frame = ttk.Frame(process_frame)
        batch_frame.pack(fill=tk.X, pady=(5, 0))
        
        ttk.Label(batch_frame, text="批量处理数量:").pack(side=tk.LEFT)
        self.batch_count_var = tk.StringVar()
        batch_entry = ttk.Entry(batch_frame, textvariable=self.batch_count_var, width=10)
        batch_entry.pack(side=tk.LEFT, padx=(5, 5))
        ttk.Label(batch_frame, text="个文件 (留空=处理全部)").pack(side=tk.LEFT)

        # 安全审计 / Dry Run
        self.dry_run_var = tk.BooleanVar(value=False)
        dry_run_cb = ttk.Checkbutton(process_frame, text="🧪 仅审计（Dry Run，不移动文件不下载图片）",
                                     variable=self.dry_run_var)
        dry_run_cb.pack(anchor=tk.W, pady=(6, 0))
        
        # === 右列内容 ===
        
        # 操作控制
        control_frame = ttk.LabelFrame(right_frame, text="🎮 操作控制", padding=10)
        control_frame.pack(fill=tk.X, pady=(0, 10))
        
        # 控制按钮 - 一行平均分布
        btn_frame = ttk.Frame(control_frame)
        btn_frame.pack(fill=tk.X)
        
        self.test_btn = ttk.Button(btn_frame, text="📡 测试连接", command=self.test_connection)
        self.test_btn.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)
        
        self.start_btn = ttk.Button(btn_frame, text="🚀 开始处理", command=self.start_processing)
        self.start_btn.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)
        
        self.stop_btn = ttk.Button(btn_frame, text="⏹️ 停止处理", command=self.stop_processing_func, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)
        
        clear_log_btn = ttk.Button(btn_frame, text="🗑️ 清空日志", command=self.clear_log)
        clear_log_btn.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)
        
        # 进度显示
        progress_frame = ttk.LabelFrame(right_frame, text="📊 处理进度", padding=10)
        progress_frame.pack(fill=tk.X, pady=(0, 10))
        
        # 进度信息区域
        progress_info_frame = ttk.Frame(progress_frame)
        progress_info_frame.pack(fill=tk.X, pady=(0, 8))
        
        # 左侧：状态文本
        self.progress_var = tk.StringVar(value="🟢 就绪")
        progress_label = ttk.Label(progress_info_frame, textvariable=self.progress_var, 
                                   font=("Arial", 11, "bold"), foreground="#2E7D32")
        progress_label.pack(side=tk.LEFT)
        
        # 右侧：百分比显示
        self.progress_percent_var = tk.StringVar(value="0%")
        percent_label = ttk.Label(progress_info_frame, textvariable=self.progress_percent_var,
                                 font=("Arial", 11, "bold"), foreground="#1976D2")
        percent_label.pack(side=tk.RIGHT)
        
        # 进度条容器（添加边框效果）
        progress_container = ttk.Frame(progress_frame, relief=tk.SUNKEN, borderwidth=1)
        progress_container.pack(fill=tk.X)
        
        # 自定义进度条样式
        style = ttk.Style()
        style.theme_use('clam')  # 使用 clam 主题以支持更多自定义
        style.configure("Custom.Horizontal.TProgressbar",
                       troughcolor='#E0E0E0',      # 背景色（浅灰）
                       background='#4CAF50',        # 进度条颜色（绿色）
                       bordercolor='#BDBDBD',       # 边框颜色
                       lightcolor='#66BB6A',        # 高光色
                       darkcolor='#388E3C',         # 阴影色
                       thickness=25)                # 进度条高度
        
        self.progress_bar = ttk.Progressbar(progress_container, 
                                           mode='determinate',
                                           style="Custom.Horizontal.TProgressbar")
        self.progress_bar.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
        
        # 处理速度显示
        self.speed_var = tk.StringVar(value="")
        speed_label = ttk.Label(progress_frame, textvariable=self.speed_var,
                               font=("Arial", 9), foreground="#757575")
        speed_label.pack(anchor=tk.W, pady=(5, 0))
        
        # 处理日志
        log_frame = ttk.LabelFrame(right_frame, text="📝 处理日志", padding=10)
        log_frame.pack(fill=tk.BOTH, expand=True)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=20, font=("Consolas", 9))
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        # 状态栏
        self.status_var = tk.StringVar(value=STATUS_READY)
        status_bar = ttk.Label(self.window, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        
        # 绑定网站选择变化事件
        # v1.4.5: Tk 9 / Python 3.12+ 下旧式 trace('w', ...) 可能报错：
        #   bad option "variable": must be add, info, or remove
        # 优先用 trace_add，旧版 Tk 再降级到 trace。
        try:
            self.website_var.trace_add('write', lambda *args: self.on_website_change())
        except AttributeError:
            self.website_var.trace('w', self.on_website_change)
        self.on_website_change()  # 初始化配置
        
        # v1.4.3: 初始化反爬虫处理器（GUI 创建后）
        self.anti_crawl = OptimizedAntiCrawlHandler(log_callback=self.log)
        
        # 启动日志
        self.log(f"✅ {APP_TITLE} 启动完成 | {self.build_id} | {self.build_date}", "SUCCESS")
    def _start_run_log(self, folder_path, website_name):
        """为一次批处理创建落地日志文件。"""
        logs_dir = os.path.join(folder_path, 'JFO_Logs')
        os.makedirs(logs_dir, exist_ok=True)
        stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        safe_site = ''.join(ch for ch in website_name if ch.isalnum() or ch in ('-', '_')).strip('_') or 'site'
        self.run_log_path = os.path.join(logs_dir, f'JFO_RUN_{stamp}_{safe_site}.log')
        self._run_log_file = open(self.run_log_path, 'w', encoding='utf-8', buffering=1)
        self._run_log_file.write(f'# {APP_TITLE}\n')
        self._run_log_file.write(f'# version: {self.version}\n')
        self._run_log_file.write(f'# build: {self.build_id}\n')
        self._run_log_file.write(f'# started_at: {datetime.now().isoformat()}\n')
        self._run_log_file.write(f'# folder: {folder_path}\n')
        self._run_log_file.write(f'# website: {website_name}\n\n')
        return self.run_log_path

    def _write_run_log(self, log_entry):
        run_log_path = getattr(self, 'run_log_path', None)
        if not run_log_path:
            return
        try:
            lock = getattr(self, '_run_log_lock', None)
            if lock is None:
                lock = threading.Lock()
                self._run_log_lock = lock
            with lock:
                log_file = getattr(self, '_run_log_file', None)
                if log_file is not None and not log_file.closed:
                    log_file.write(log_entry)
                else:
                    with open(run_log_path, 'a', encoding='utf-8') as f:
                        f.write(log_entry)
        except Exception:
            pass

    def _close_run_log(self):
        run_log_path = getattr(self, 'run_log_path', None)
        if run_log_path:
            try:
                self._write_run_log(f"# ended_at: {datetime.now().isoformat()}\n")
            finally:
                log_file = getattr(self, '_run_log_file', None)
                if log_file is not None:
                    try:
                        log_file.close()
                    except Exception:
                        pass
                self._run_log_file = None
                self.run_log_path = None

    def _build_provider_factory(self):
        from providers import create_provider

        def factory(name):
            return create_provider(
                name,
                log=self.log,
                session=self.session,
                anti_crawl=self.anti_crawl,
                stop_requested=self._is_stop_requested,
            )
        return factory

    def log(self, message, level="INFO"):
        """记录日志（线程安全）。"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        # 根据级别添加图标
        icons = {
            "INFO": "📝",
            "SUCCESS": "✅", 
            "WARNING": "⚠️",
            "ERROR": "❌",
            "PROCESSING": "🔄"
        }
        
        icon = icons.get(level, "📝")
        log_entry = f"[{timestamp}] {icon} {message}\n"
        self._write_run_log(log_entry)
        
        # 在GUI线程中更新日志（实时显示）
        def update_log():
            self.log_text.insert(tk.END, log_entry)
            
            # 根据级别设置颜色
            if level == "ERROR":
                start_line = self.log_text.index(tk.END + "-2l")
                end_line = self.log_text.index(tk.END + "-1l")
                self.log_text.tag_add("error", start_line, end_line)
                self.log_text.tag_config("error", foreground="red")
            elif level == "SUCCESS":
                start_line = self.log_text.index(tk.END + "-2l")
                end_line = self.log_text.index(tk.END + "-1l")
                self.log_text.tag_add("success", start_line, end_line)
                self.log_text.tag_config("success", foreground="green")
            
            self.log_text.see(tk.END)
            self.window.update_idletasks()
        
        # 使用 after 确保在主线程中执行
        if threading.current_thread() == threading.main_thread():
            update_log()
        else:
            self.window.after(0, update_log)
    
    def on_website_change(self, *args):
        """网站选择变化时更新配置。"""
        website = self.website_var.get()
        config = self.website_configs.get(website, {})
        
        # 更新配置字段
        self.search_url_var.set(config.get('search_url', ''))
        
        # v1.9 修复：使用多个选择器中的第一个
        title_selectors = config.get('title_selectors', ['title'])
        self.text_selector_var.set(title_selectors[0])
        
        image_selectors = config.get('image_selectors', ['img'])
        self.image_selector_var.set(image_selectors[0])
        
        self.log(f"🌐 切换到网站: {config.get('name', website)}", "INFO")
    
    def select_folder(self):
        """选择文件夹。"""
        folder = filedialog.askdirectory(title="选择包含视频文件的文件夹")
        if folder:
            self.folder_var.set(folder)
            
            self.analyze_folder(folder)
    
    def analyze_folder(self, folder_path):
        """分析文件夹内容"""
        try:
            scan = self._scan_video_files(folder_path)
            filtered_video_names = scan['accepted']
            file_sizes = scan.get('file_sizes', {})
            video_files = []
            total_size = 0
            skipped_hidden = len(scan['skipped_hidden'])
            skipped_small = len(scan['skipped_small'])
            
            for file in filtered_video_names:
                file_size = file_sizes.get(file, 0)
                video_files.append((file, file_size))
                total_size += file_size
            
            # 显示详细统计
            self.log(f"📁 已选择文件夹: {folder_path}", "SUCCESS")
            self.log(f"📊 文件夹分析结果:", "INFO")
            self.log(f"📝   📁 总文件数: {scan.get('total_files', len(scan.get('manifest_entries', [])))}", "INFO")
            self.log(f"📝   🎬 视频文件数: {len(video_files)}", "INFO")
            if skipped_hidden:
                self.log(f"📝   🙈 已忽略隐藏/AppleDouble 文件: {skipped_hidden}", "INFO")
            if skipped_small:
                min_kb = getattr(self, 'minimum_video_size_bytes', 16 * 1024) // 1024
                self.log(f"📝   🚫 已忽略异常小视频文件(<{min_kb}KB): {skipped_small}", "INFO")
            self.log(f"📝   💾 总大小: {self.format_size(total_size)}", "INFO")
            
            # 显示前几个视频文件
            if video_files:
                self.log(f"📝 视频文件列表:", "INFO")
                for i, (filename, size) in enumerate(video_files[:10], 1):
                    size_str = self.format_size(size)
                    self.log(f"📝    {i}. {filename} ({size_str})", "INFO")
                
                if len(video_files) > 10:
                    self.log(f"📝    ... 还有 {len(video_files) - 10} 个文件", "INFO")
            else:
                self.log("⚠️ 未找到支持的视频文件", "WARNING")
                self.log(f"📝 支持的格式: {', '.join(self.video_extensions)}", "INFO")
            
        except Exception as e:
            self.log(f"❌ 分析文件夹失败: {e}", "ERROR")
    
    def format_size(self, size_bytes):
        """格式化文件大小"""
        if size_bytes == 0:
            return "0 B"
        
        size_names = ["B", "KB", "MB", "GB", "TB"]
        i = 0
        while size_bytes >= 1024 and i < len(size_names) - 1:
            size_bytes /= 1024.0
            i += 1
        
        return f"{size_bytes:.1f} {size_names[i]}"

    def _should_skip_video_file(self, filename):
        """是否跳过该文件。

        规则：
        - macOS AppleDouble 资源叉文件 `._*` 一律跳过
        - 其他隐藏文件（`.xxx`）一律跳过
        """
        if not filename:
            return True
        return filename.startswith('._') or filename.startswith('.')

    def _is_suspicious_small_video(self, file_path):
        """是否是明显可疑的小视频文件。"""
        try:
            min_bytes = getattr(self, 'minimum_video_size_bytes', 16 * 1024)
            return os.path.getsize(file_path) < min_bytes
        except OSError:
            return True

    def _scan_video_files(self, folder_path):
        """扫描可处理的视频文件，并返回过滤统计。"""
        result = {
            'accepted': [],
            'skipped_hidden': [],
            'skipped_small': [],
            'manifest_entries': [],
            'file_sizes': {},
            'total_files': 0,
        }
        skip_dirs = {'Finish', 'JFO_Logs', '.jfo_transactions', '__MACOSX'}
        for dirpath, dirnames, filenames in os.walk(folder_path):
            dirnames[:] = [
                dirname for dirname in dirnames
                if not dirname.startswith('.') and dirname not in skip_dirs
            ]
            for file in filenames:
                file_path = os.path.join(dirpath, file)
                rel_path = os.path.relpath(file_path, folder_path)
                try:
                    st = os.stat(file_path)
                except OSError:
                    continue
                result['total_files'] += 1
                _, ext = os.path.splitext(file.lower())
                is_hidden = file.startswith('.')
                is_video = ext in self.video_extensions
                result['manifest_entries'].append({
                    'name': rel_path,
                    'size': st.st_size,
                    'mtime': st.st_mtime,
                    'extension': ext,
                    'is_hidden': is_hidden,
                    'is_video': is_video,
                })
                if self._should_skip_video_file(file):
                    result['skipped_hidden'].append(rel_path)
                    continue
                if ext not in self.video_extensions:
                    continue
                if st.st_size < getattr(self, 'minimum_video_size_bytes', 16 * 1024):
                    result['skipped_small'].append(rel_path)
                    continue
                result['accepted'].append(rel_path)
                result['file_sizes'][rel_path] = st.st_size
        result['accepted'].sort()
        result['skipped_hidden'].sort()
        result['skipped_small'].sort()
        return result

    def _collect_video_files(self, folder_path):
        """收集可处理的视频文件（已过滤隐藏/AppleDouble/异常小视频）。"""
        return self._scan_video_files(folder_path)['accepted']

    def _resolve_provider(self, preferred_website, filename, search_query):
        """根据文件名/搜索词决定使用哪个 provider。"""
        from provider_router import route_provider

        decision = route_provider(preferred_website, filename, search_query)
        provider = decision.get('provider') or preferred_website
        website_config = dict(self.website_configs.get(provider, {}))

        # 只有当前用户显式选中的 provider 才应用 UI 上的自定义配置。
        if provider == preferred_website:
            website_config['search_url'] = self.search_url_var.get()
            website_config['title_selectors'] = [self.text_selector_var.get()]
            website_config['image_selectors'] = [self.image_selector_var.get()]

        return decision, provider, website_config
    
    def extract_code_from_title(self, filename):
        """从完整标题中提取番号

        thin wrapper around filename_utils.extract_code_from_text, 仅加日志。

        支持格式 (与 v1.3.2 一致):
        - "ABF-139 美少女.mp4"          -> "ABF-139"
        - "ABF139 标题.mp4"             -> "ABF-139"
        - "[ABF-139] 标题.mp4"          -> "ABF-139"
        - "(ABF-139) 标题.mp4"          -> "ABF-139"
        - "标题 ABF-139.mp4"            -> "ABF-139"
        - "4k2.com@ABF-139 标题.mp4"    -> "ABF-139"  (v1.4.4: 走统一的 strip_site_markers)
        - "ABF-139-1 标题.mp4"          -> "ABF-139-1"
        - "ABF-139a 标题.mp4"           -> "ABF-139A"
        """
        from filename_utils import extract_code_from_text
        code = extract_code_from_text(filename)
        if code:
            self.log(f"📝 从标题提取番号: {filename} -> {code}", "INFO")
        return code

    def clean_filename_for_search(self, filename):
        """清理文件名用于搜索 - v1.4.4 改用共享纯函数

        thin wrapper around filename_utils.clean_filename_for_search(), 仅加日志。
        """
        from filename_utils import clean_filename_for_search as _clean
        result = _clean(filename)
        self.log(f"📝 文件名处理: {filename} -> {result}", "INFO")
        return result
    
    def sanitize_filename(self, filename):
        """清理文件名中的非法字符 - v1.4.4 改用共享纯函数

        thin wrapper around filename_utils.sanitize_filename().
        保留为实例方法的原因：AtomicProcessor 需要传 self.sanitize_filename 作为回调。

        行为变更 (v1.4.4)：
        - 下载站前缀 (4k2.com@xxx) 现在能被正确清理
        - [javbus] / (javbus) / javbus - xxx 等格式现在也能清理
        """
        from filename_utils import sanitize_filename as _sanitize
        return _sanitize(filename)
    

    def extract_series_info(self, filename):
        """v1.4.4: thin wrapper around filename_utils.extract_series_info

        修复：原版 4 个正则都用 ^...$，要求 stem 完全是 ABC-123-N 形式。
        实际文件名常常是 ABF-139-1 美少女 第1話.mp4 这种带完整标题的，
        原版一个都识别不到，导致每集都走单文件路径、各自下载封面。

        新版：去掉 ^$ 锚点，用 re.search 匹配 stem 中任意位置的 ABC-123-N。
        """
        from filename_utils import extract_series_info as _extract
        return _extract(filename)
    
    def detect_series_files(self, file_list):
        """检测并分组序列文件。"""
        series_groups = {}
        standalone_files = []
        
        for file_path in file_list:
            filename = os.path.basename(file_path)
            name_without_ext = os.path.splitext(filename)[0]
            base_code, sequence = self.extract_series_info(name_without_ext)
            
            if base_code:
                if base_code not in series_groups:
                    series_groups[base_code] = []
                series_groups[base_code].append((file_path, sequence))
            else:
                standalone_files.append(file_path)
        
        for base_code in series_groups:
            series_groups[base_code].sort(key=lambda x: int(x[1]))
        
        return series_groups, standalone_files
    
    def smart_truncate_filename(self, title, original_filename, max_length):
        """智能截断文件名"""
        if not max_length or max_length <= 0:
            return title
        
        original_name = os.path.splitext(original_filename)[0]
        min_length = max(len(original_name), 10)  # 至少保留原始文件名长度
        
        if max_length < min_length:
            self.log(f"⚠️ 设置长度 {max_length} 小于原始文件名长度 {len(original_name)},调整为 {min_length}", "WARNING")
            max_length = min_length
        
        if len(title) <= max_length:
            return title
        
        # 尝试保留演员名称(通常在最后)
        if self.preserve_actor_var.get():
            # 查找可能的演员名称(日文名字模式)
            actor_pattern = r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]{2,6}$'
            actor_match = re.search(actor_pattern, title)
            
            if actor_match:
                actor_name = actor_match.group()
                # 计算可用长度: 总长度 - 原始文件名 - 演员名 - 2个空格
                available_length = max_length - len(original_name) - len(actor_name) - 2
                
                if available_length > 5:  # 至少保留5个字符的中间内容
                    # 从标题中提取中间部分
                    title_middle = title[len(original_name):title.rfind(actor_name)].strip()
                    
                    # 确保中间部分不超过可用长度
                    if len(title_middle) > available_length:
                        title_middle = title_middle[:available_length-3] + "..."
                    
                    # 组合结果并确保总长度不超过限制
                    result = f"{original_name} {title_middle} {actor_name}".strip()
                    
                    # 最终检查:如果还是超长,强制截断
                    if len(result) > max_length:
                        result = result[:max_length-3] + "..."
                    
                    self.log(f"📝 智能截断: 保留演员名 '{actor_name}'", "INFO")
                    return result
        
        # 简单截断,但确保包含原始文件名
        if len(title) > max_length:
            # 确保原始文件名在开头
            if not title.startswith(original_name):
                title = f"{original_name} {title}"
            
            if len(title) > max_length:
                title = title[:max_length-3] + "..."
        
        return title
    
    def extract_content(self, search_query, website_config):
        """提取网站内容（统一走 provider 接口）。"""
        try:
            if self._is_stop_requested():
                self.log("⏹️ 用户中断，取消网络请求", "WARNING")
                return None, None

            provider_name = None
            for key, cfg in self.website_configs.items():
                if cfg.get('name') == website_config.get('name'):
                    provider_name = key
                    break
            provider_name = provider_name or self.website_var.get()

            provider = self._build_provider_factory()(provider_name)
            result = provider.search(search_query)
            if result.get('ok'):
                return result.get('title'), result.get('image_url')

            self.log(f"❌ Provider 搜索失败: {result.get('error_type')} - {result.get('message')}", "ERROR")
            return None, None
        except Exception as e:
            self.log(f"❌ 搜索提取失败: {e}", "ERROR")
            return None, None
    
    def download_image(self, image_url, save_path, max_retries=3):
        """下载图片：保留 GUI 回调入口，实际逻辑由共享下载服务负责。"""
        from download_service import ImageDownloader

        session = getattr(getattr(self, 'anti_crawl', None), 'session', None) or self.session
        downloader = ImageDownloader(
            session=session,
            log=self.log,
            stop_requested=self._is_stop_requested,
        )
        return downloader.download(image_url, save_path, max_retries=max_retries)
    

    def _run_on_ui_thread(self, callback):
        """Run callback on Tk's main thread."""
        if threading.current_thread() == threading.main_thread():
            callback()
        else:
            self.window.after(0, callback)

    def _ensure_stop_event(self):
        event = getattr(self, '_stop_event', None)
        if event is None:
            event = threading.Event()
            self._stop_event = event
        return event

    def _request_stop(self):
        self.stop_processing = True
        self._ensure_stop_event().set()

    def _reset_stop_signal(self):
        self.stop_processing = False
        self._ensure_stop_event().clear()

    def _is_stop_requested(self):
        event = getattr(self, '_stop_event', None)
        return bool(self.stop_processing or (event is not None and event.is_set()))

    def _has_active_file_transaction(self):
        processor = getattr(self, 'atomic_processor', None)
        checker = getattr(processor, 'has_active_transaction', None)
        if not callable(checker):
            return False
        try:
            return bool(checker())
        except Exception:
            return False

    def _cancel_inflight_network(self):
        """Best-effort cancellation for slow provider/download requests."""
        cancelled = []
        session = getattr(self, 'session', None)
        if session is not None:
            try:
                session.close()
                cancelled.append('requests')
            except Exception as e:
                self.log(f"⚠️ 关闭网络会话失败: {e}", "WARNING")

        anti_crawl = getattr(self, 'anti_crawl', None)
        selenium_javlibrary = getattr(anti_crawl, 'selenium_javlibrary', None) if anti_crawl else None
        if selenium_javlibrary is not None:
            try:
                selenium_javlibrary.stop_browser()
                cancelled.append('browser')
            except Exception as e:
                self.log(f"⚠️ 停止浏览器请求失败: {e}", "WARNING")

        if cancelled:
            self.log(f"⏹️ 已请求快速取消当前网络/浏览器任务: {', '.join(cancelled)}", "WARNING")

    def _capture_processing_request(self):
        """Capture Tk-bound processing inputs on the UI thread."""
        website = self.website_var.get()
        website_config = dict(self.website_configs.get(website, {}))
        website_config['search_url'] = self.search_url_var.get()
        website_config['title_selectors'] = [self.text_selector_var.get()]
        website_config['image_selectors'] = [self.image_selector_var.get()]
        dry_run = self.dry_run_var.get() if hasattr(self, 'dry_run_var') else False
        return ProcessingRequest(
            folder_path=self.folder_var.get(),
            website=website,
            website_config=website_config,
            dry_run=bool(dry_run),
            batch_count_text=self.batch_count_var.get().strip(),
            max_length_text=self.max_filename_length_var.get().strip(),
        )

    def _show_messagebox(self, kind, title, message):
        """Show a messagebox without letting Tk environment failures break processing."""
        try:
            parent = getattr(self, 'window', None)
            if parent is not None and not hasattr(parent, 'tk'):
                self.log(f"📝 跳过提示窗口（非真实 Tk 环境）: {title}", "INFO")
                return
            options = {'parent': parent} if parent is not None else {}
            if kind == 'warning':
                messagebox.showwarning(title, message, **options)
            elif kind == 'error':
                messagebox.showerror(title, message, **options)
            else:
                messagebox.showinfo(title, message, **options)
        except Exception as e:
            message = str(e).splitlines()[0] if str(e) else repr(e)
            self.log(f"⚠️ 无法显示提示窗口: {message}", "WARNING")

    def _close_safe_stop_dialog(self):
        dialog = getattr(self, '_safe_stop_dialog', None)
        if dialog is not None:
            try:
                if dialog.winfo_exists():
                    dialog.destroy()
            except Exception:
                pass
        self._safe_stop_dialog = None
        self._safe_stop_progress = None
        self._safe_stop_message_var = None
        self._safe_stop_detail_var = None
        self._safe_stop_ok_btn = None
        self._safe_stop_requested = False
        self._safe_stop_dialog_done = False
        self._safe_stop_dialog_visible = False

    def _show_safe_stop_dialog(self):
        """Show a small progress window while cancellation waits for a safe boundary."""
        self._safe_stop_requested = True
        self._safe_stop_dialog_done = False
        parent = getattr(self, 'window', None)
        if parent is None or not hasattr(parent, 'tk'):
            self._safe_stop_dialog_visible = True
            return

        dialog = getattr(self, '_safe_stop_dialog', None)
        try:
            if dialog is not None and dialog.winfo_exists():
                dialog.lift()
                return
        except Exception:
            pass

        dialog = tk.Toplevel(parent)
        dialog.title("正在安全停止")
        dialog.resizable(False, False)
        dialog.transient(parent)
        dialog.protocol("WM_DELETE_WINDOW", lambda: None)

        frame = ttk.Frame(dialog, padding=18)
        frame.pack(fill=tk.BOTH, expand=True)

        message_var = tk.StringVar(value="正在安全停止中...")
        detail_var = tk.StringVar(value="等待当前网络请求或文件事务到达安全边界，源文件会保持安全。")
        ttk.Label(frame, textvariable=message_var, font=("Arial", 13, "bold")).pack(anchor=tk.W)
        ttk.Label(frame, textvariable=detail_var, wraplength=360, foreground="#666666").pack(anchor=tk.W, pady=(8, 12))

        progress = ttk.Progressbar(frame, mode='indeterminate', length=360)
        progress.pack(fill=tk.X, pady=(0, 14))
        progress.start(80)

        ok_btn = ttk.Button(frame, text="确定", command=self._close_safe_stop_dialog, state=tk.DISABLED)
        ok_btn.pack(anchor=tk.E)

        self._safe_stop_dialog = dialog
        self._safe_stop_progress = progress
        self._safe_stop_message_var = message_var
        self._safe_stop_detail_var = detail_var
        self._safe_stop_ok_btn = ok_btn

        try:
            dialog.update_idletasks()
            x = parent.winfo_rootx() + max((parent.winfo_width() - dialog.winfo_width()) // 2, 0)
            y = parent.winfo_rooty() + max((parent.winfo_height() - dialog.winfo_height()) // 2, 0)
            dialog.geometry(f"+{x}+{y}")
            dialog.lift()
        except Exception:
            pass

    def _complete_safe_stop_dialog(self, result=None):
        if not getattr(self, '_safe_stop_requested', False):
            return
        self._safe_stop_dialog_done = True
        cancelled_count = 0
        if isinstance(result, dict):
            cancelled_count = result.get('cancelled_count') or 0

        if getattr(self, '_safe_stop_dialog', None) is None:
            self._safe_stop_dialog_visible = True
            return

        detail = "已停止后续任务；已完成的文件保持完成，未完成的文件保持原样。"
        if cancelled_count:
            detail = f"已安全停止，未处理文件数: {cancelled_count}。源文件已保持原样。"

        try:
            if self._safe_stop_progress:
                self._safe_stop_progress.stop()
            if self._safe_stop_message_var:
                self._safe_stop_message_var.set("已安全停止")
            if self._safe_stop_detail_var:
                self._safe_stop_detail_var.set(detail)
            if self._safe_stop_ok_btn:
                self._safe_stop_ok_btn.config(state=tk.NORMAL)
                self._safe_stop_ok_btn.focus_set()
            if self._safe_stop_dialog:
                self._safe_stop_dialog.protocol("WM_DELETE_WINDOW", self._close_safe_stop_dialog)
                self._safe_stop_dialog.lift()
        except Exception:
            pass

    def _finish_processing_ui(self):
        """Reset processing controls on the UI thread."""
        if getattr(self, '_safe_stop_requested', False) and not getattr(self, '_safe_stop_dialog_done', False):
            self._complete_safe_stop_dialog()
        self.is_processing = False
        self._reset_stop_signal()
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(text="⏹️ 停止处理", state=tk.DISABLED)
        self.status_var.set(STATUS_READY)
        self._close_run_log()

    def _apply_stopping_ui(self):
        """Show immediate feedback after a stop request while safe shutdown completes."""
        self._show_safe_stop_dialog()
        self.stop_btn.config(text="⏳ 安全停止中...", state=tk.DISABLED)
        if self._has_active_file_transaction():
            self.status_var.set("正在安全停止：当前文件会在事务边界收口，源文件保持安全")
            self.progress_var.set("⏳ 正在安全停止...")
        else:
            self.status_var.set("正在快速停止：当前无文件落盘事务，正在取消网络请求")
            self.progress_var.set("⏹️ 正在快速停止...")
        current_speed = self.speed_var.get()
        if current_speed:
            self.speed_var.set(f"{current_speed} | 停止请求已提交")
        else:
            if self._has_active_file_transaction():
                self.speed_var.set("停止请求已提交，等待当前网络/文件事务到达安全边界")
            else:
                self.speed_var.set("停止请求已提交，当前无落盘事务，正在取消网络请求")

    def _complete_processing_ui(self, result, dry_run, run_log_path):
        """Apply workflow result to UI and finish the run."""
        try:
            self._apply_processing_result(result, dry_run, run_log_path)
        finally:
            self._finish_processing_ui()

    def _format_duration(self, seconds):
        seconds = max(float(seconds or 0), 0.0)
        if seconds < 60:
            return f"{seconds:.1f}秒"
        minutes, sec = divmod(int(seconds + 0.5), 60)
        if minutes < 60:
            return f"{minutes}分{sec:02d}秒"
        hours, minutes = divmod(minutes, 60)
        return f"{hours}小时{minutes:02d}分"

    def _update_processing_progress(self, completed, total, label=''):
        """Update progress widgets from workflow progress callbacks."""
        total = max(int(total or 0), 0)
        completed = max(min(int(completed or 0), total), 0) if total else 0
        percent = int((completed / total) * 100) if total else 0
        now = time.time()

        if completed == 0 or self._progress_started_at is None:
            self._progress_started_at = now
            self._progress_last_update_at = now
            self._progress_last_completed = completed
            self._progress_last_item_text = ""

        elapsed = now - (self._progress_started_at or now)
        avg_per_file = (elapsed / completed) if completed > 0 else 0
        remaining_files = max(total - completed, 0)
        eta = remaining_files * avg_per_file if completed > 0 else 0

        if completed > getattr(self, '_progress_last_completed', 0):
            self._progress_last_completed = completed
            self._progress_last_update_at = now

        if completed > 0:
            avg_text = f"{self._format_duration(avg_per_file)}/文件"
            eta_text = self._format_duration(eta)
        else:
            avg_text = "计算中"
            eta_text = "计算中"

        timing_text = (
            f"平均: {avg_text} | "
            f"已用时间: {self._format_duration(elapsed)} | "
            f"剩余时间: {eta_text}"
        )

        def apply():
            self.progress_bar['value'] = percent
            if self._is_stop_requested():
                self.progress_var.set(f"⏳ 正在安全停止: {completed}/{total}")
                self.status_var.set("正在安全停止：等待当前网络/文件事务到达安全边界")
                self.stop_btn.config(text="⏳ 安全停止中...", state=tk.DISABLED)
            else:
                self.progress_var.set(f"🔄 处理中: {completed}/{total}")
            self.progress_percent_var.set(f"{percent}%")
            if self._is_stop_requested():
                self.speed_var.set(f"{timing_text} | 停止请求已提交")
            else:
                self.speed_var.set(timing_text)

        self._run_on_ui_thread(apply)

    def _apply_processing_result(self, result, dry_run, run_log_path):
        """Update UI summary and dialogs from a workflow result."""
        total_files = result['total_files']
        success_count = result['success_count']
        failed_count = result['failed_count']
        planned_count = result['planned_count']
        skipped_hidden = result['skipped_hidden']
        skipped_small = result['skipped_small']
        skipped_provider_count = result['skipped_provider_count']
        needs_review_count = result.get('needs_review_count', 0)
        cancelled_count = result.get('cancelled_count', 0)
        image_success_count = result['image_success_count']
        image_failed_count = result['image_failed_count']
        total_time = result['total_time']
        avg_time = total_time / total_files if total_files > 0 else 0
        success_rate = (success_count / total_files * 100) if total_files > 0 else 0
        after_manifest_path = result['after_manifest_path']
        file_results_path = result.get('file_results_path')
        file_results_display = file_results_path or "(未生成)"
        summary_path = result['summary_path']
        filename_rule_candidates_path = result.get('filename_rule_candidates_path')

        self.progress_bar['value'] = 100
        self.progress_var.set("✅ 处理完成！" if not dry_run else "🧪 审计完成")
        self.progress_percent_var.set("100%")
        self.speed_var.set(f"✨ 总用时: {total_time:.1f} 秒 | 平均: {avg_time:.1f} 秒/文件")

        self.log(f"✅ 🎉 {'审计完成' if dry_run else '处理完成！'}", "SUCCESS")
        self.log(f"📝 📊 最终统计:", "INFO")
        self.log(f"📝   📁 总文件数: {total_files}", "INFO")
        self.log(f"📝   ✅ 成功处理: {success_count}", "INFO")
        self.log(f"📝   ❌ 处理失败: {failed_count}", "INFO")
        if dry_run:
            self.log(f"📝   🧪 Dry Run 计划处理: {planned_count}", "INFO")
        if skipped_hidden:
            self.log(f"📝   🙈 跳过隐藏文件: {skipped_hidden}", "INFO")
        if skipped_small:
            self.log(f"📝   🚫 跳过小文件: {skipped_small}", "INFO")
        if skipped_provider_count:
            self.log(f"📝   ⚠️ Provider 警告文件数: {skipped_provider_count}", "INFO")
        if needs_review_count:
            self.log(f"📝   🧠 文件名规则待确认: {needs_review_count}", "WARNING")
        if cancelled_count:
            self.log(f"📝   ⏹️ 用户取消未处理: {cancelled_count}", "WARNING")
        self.log(f"📝   🖼️ 封面成功: {image_success_count} 张", "INFO")
        self.log(f"📝   🖼️ 封面失败: {image_failed_count} 张", "INFO")
        self.log(f"📝   ⏱️ 总用时: {total_time:.1f} 秒", "INFO")
        self.log(f"📝   📈 平均处理时间: {avg_time:.1f} 秒/文件", "INFO")
        self.log(f"📝   📊 成功率: {success_rate:.1f}%", "INFO")
        self.log(f"📝   📄 日志文件: {run_log_path}", "INFO")
        if after_manifest_path:
            self.log(f"📝   🧾 处理后清单: {after_manifest_path}", "INFO")
        if file_results_path:
            self.log(f"📝   🧮 文件级结果: {file_results_path}", "INFO")
        if filename_rule_candidates_path:
            self.log(f"📝   🧠 文件名候选规则: {filename_rule_candidates_path}", "INFO")
        if summary_path:
            self.log(f"📝   📦 运行摘要: {summary_path}", "INFO")

        if getattr(self, '_safe_stop_requested', False):
            self.progress_var.set("⏹️ 已安全停止")
            self.speed_var.set(f"已用时间: {total_time:.1f} 秒 | 未处理: {cancelled_count}")
            self._complete_safe_stop_dialog(result)
            return

        if dry_run:
            self._show_messagebox(
                'info',
                "审计完成",
                f"🧪 Dry Run 审计完成\n\n"
                f"📊 计划处理: {planned_count}/{total_files}\n"
                f"🙈 已忽略隐藏文件: {skipped_hidden}\n"
                f"🚫 已忽略异常小文件: {skipped_small}\n"
                f"⚠️ Provider 警告文件数: {skipped_provider_count}\n"
                f"🧠 文件名规则待确认: {needs_review_count}\n"
                f"⏹️ 用户取消未处理: {cancelled_count}\n"
                f"📄 日志: {run_log_path}\n"
                f"🧮 文件结果: {file_results_display}\n"
                f"📦 摘要: {summary_path}",
            )
        elif failed_count == 0 and needs_review_count == 0 and cancelled_count == 0:
            self._show_messagebox(
                'info',
                "处理完成",
                f"🎉 所有文件处理完成！\n\n"
                f"📊 统计结果:\n"
                f"✅ 成功: {success_count}/{total_files}\n"
                f"🖼️ 封面成功: {image_success_count} 张\n"
                f"⏱️ 用时: {total_time:.1f} 秒\n"
                f"📊 成功率: {success_rate:.1f}%\n\n"
                f"🧮 文件结果: {file_results_display}",
            )
        else:
            self._show_messagebox(
                'warning',
                "处理完成（有错误）",
                f"⚠️ 处理完成，但有部分文件失败\n\n"
                f"📊 统计结果:\n"
                f"✅ 成功: {success_count}/{total_files}\n"
                f"❌ 失败: {failed_count}/{total_files}\n"
                f"🙈 跳过隐藏: {skipped_hidden}\n"
                f"🚫 跳过小文件: {skipped_small}\n"
                f"⚠️ Provider 警告文件数: {skipped_provider_count}\n"
                f"🧠 文件名规则待确认: {needs_review_count}\n"
                f"⏹️ 用户取消未处理: {cancelled_count}\n"
                f"🖼️ 封面成功: {image_success_count} 张\n"
                f"⏱️ 用时: {total_time:.1f} 秒\n"
                f"📊 成功率: {success_rate:.1f}%\n\n"
                f"🧮 文件结果: {file_results_display}\n"
                f"🔍 请查看日志了解失败原因",
            )

    def _process_files_worker(self, request):
        """后台处理线程工作函数。"""
        ui_completion_scheduled = False
        try:
            from workflow_service import WorkflowDependencies, WorkflowService

            self.is_processing = True
            self._reset_stop_signal()
            self.log("🚀 开始处理任务...", "INFO")

            folder_path = request.folder_path
            if not folder_path or not os.path.exists(folder_path):
                self.log("❌ 请先选择有效的文件夹", "ERROR")
                return

            website = request.website
            website_config = request.website_config
            dry_run = request.dry_run

            self.log(f"📝 配置信息:", "INFO")
            self.log(f"   网站: {website_config.get('name', website)}", "INFO")
            self.log(f"   搜索URL: {website_config['search_url']}", "INFO")
            if dry_run:
                self.log("🧪 当前为 Dry Run：只审计，不移动文件、不下载图片", "WARNING")

            run_log_path = self._start_run_log(folder_path, website)
            self.log(f"📝 日志文件: {run_log_path}", "INFO")
            logs_dir = os.path.dirname(run_log_path)

            scan_started = time.time()
            scan = self._scan_video_files(folder_path)
            scan_elapsed = time.time() - scan_started
            self.log(f"⏱️ 文件扫描耗时: {scan_elapsed:.1f}秒", "INFO")
            total_files_preview = len(scan['accepted'])
            batch_count_str = request.batch_count_text
            batch_count = None
            if batch_count_str:
                try:
                    batch_count = int(batch_count_str)
                    if batch_count > 0:
                        total_files_preview = min(total_files_preview, batch_count)
                        self.log(f"📝 批量处理: 限制处理 {total_files_preview} 个文件", "INFO")
                except ValueError:
                    self.log("⚠️ 批量处理数量格式错误，将处理全部文件", "WARNING")

            min_kb = getattr(self, 'minimum_video_size_bytes', 16 * 1024) // 1024
            if scan['skipped_hidden']:
                self.log(f"📝 已忽略隐藏/AppleDouble 文件: {len(scan['skipped_hidden'])}", "INFO")
            if scan['skipped_small']:
                self.log(f"📝 已忽略异常小视频文件(<{min_kb}KB): {len(scan['skipped_small'])}", "WARNING")
            if total_files_preview <= 0:
                self.log("❌ 未找到支持的视频文件", "ERROR")
                return

            finish_folder = os.path.join(folder_path, 'Finish')
            self.log(f"🔄 🚀 开始处理 {total_files_preview} 个文件", "PROCESSING")
            self.log(f"📝 🌐 使用网站: {website_config.get('name', website)}", "INFO")
            self._progress_started_at = None
            self._progress_last_update_at = None
            self._progress_last_completed = 0
            self._progress_last_item_text = ""
            self._update_processing_progress(0, total_files_preview, "准备处理")

            max_length_str = request.max_length_text
            max_length = None
            if max_length_str:
                try:
                    max_length = int(max_length_str)
                    self.log(f"📝 文件名长度限制: {max_length} 字符", "INFO")
                except ValueError:
                    self.log("⚠️ 文件名长度格式错误，将使用完整长度", "WARNING")

            workflow_dependencies = WorkflowDependencies(
                provider_factory=self._build_provider_factory(),
                atomic_processor=self.atomic_processor,
                clean_filename_for_search=self.clean_filename_for_search,
                sanitize_filename=self.sanitize_filename,
                detect_series_files=self.detect_series_files,
                smart_truncate_filename=self.smart_truncate_filename,
                stop_requested=self._is_stop_requested,
                progress_callback=self._update_processing_progress,
            )
            service = WorkflowService(
                log=self.log,
                dependencies=workflow_dependencies,
                minimum_video_size_bytes=getattr(self, 'minimum_video_size_bytes', 16 * 1024),
                app_version=self.version,
            )

            result = service.run(
                folder_path=folder_path,
                finish_folder=finish_folder,
                website=website,
                max_length=max_length,
                batch_count=batch_count,
                dry_run=dry_run,
                log_path=run_log_path,
                logs_dir=logs_dir,
                initial_scan=scan,
                initial_scan_elapsed_seconds=scan_elapsed,
            )

            self._run_on_ui_thread(
                lambda result=result, dry_run=dry_run, run_log_path=run_log_path:
                self._complete_processing_ui(result, dry_run, run_log_path)
            )
            ui_completion_scheduled = True

        except Exception as e:
            self.log(f"❌ 处理过程中出现错误: {e}", "ERROR")
        finally:
            if not ui_completion_scheduled:
                self._run_on_ui_thread(self._finish_processing_ui)

    def _run_connection_probe(self, website, test_query):
        """Run a real provider probe and verify that the cover can be downloaded."""
        if hasattr(self, '_build_provider_factory'):
            provider = self._build_provider_factory()(website)
            result = provider.search(test_query)
            if not result.get('ok'):
                return {
                    'ok': False,
                    'title': result.get('title'),
                    'image_url': result.get('image_url'),
                    'error_type': result.get('error_type') or 'provider-error',
                    'message': result.get('message') or 'provider returned failure',
                    'referer': result.get('referer'),
                    'detail_url': result.get('detail_url'),
                }
            title = result.get('title')
            image_url = result.get('image_url')
            raw_meta = result.get('raw_meta') or {}
            if not isinstance(raw_meta, dict):
                raw_meta = {}
            image_task = {
                'image_url': image_url,
                'referer': result.get('referer') or result.get('detail_url'),
                'detail_url': result.get('detail_url'),
                'provider': result.get('provider') or website,
                'fallback_images': result.get('fallback_images') or raw_meta.get('fallback_images') or [],
            }
        else:
            title, image_url = self.extract_content(test_query, self.website_configs.get(website, {}))
            if not title:
                return {
                    'ok': False,
                    'title': title,
                    'image_url': image_url,
                    'error_type': 'provider-error',
                    'message': 'test probe did not return a title',
                }
            image_task = image_url

        image_ok = True
        if image_url or (isinstance(image_task, dict) and image_task.get('fallback_images')):
            import tempfile
            with tempfile.TemporaryDirectory() as tmp:
                probe_image_path = os.path.join(tmp, 'connection_probe.jpg')
                image_ok = self.download_image(image_task, probe_image_path, max_retries=1)

        return {
            'ok': bool(title and image_ok),
            'title': title,
            'image_url': image_url,
            'error_type': '' if title and image_ok else 'image-download-failed',
            'message': '' if title and image_ok else 'cover image download verification failed',
        }
    
    def test_connection(self):
        """测试当前网站连接。"""
        website = self.website_var.get()
        website_config = self.website_configs.get(website, {})
        
        # 更新配置
        website_config['search_url'] = self.search_url_var.get()
        website_config['title_selectors'] = [self.text_selector_var.get()]
        
        self.log(f"🧪 测试连接到: {website_config.get('name', website)}", "INFO")
        
        # 使用测试查询（v1.4.5: 按站点选择已知更稳的番号）
        test_query_map = {
            'javhoo': 'SONE-753',
            'javbus': 'SONE-753',
            'javlibrary': 'JBD-131',
            'bestjavporn': 'ABF-311',
            'uncensored': 'CARIB-032226-001',
        }
        test_query = test_query_map.get(website, 'SONE-753')
        self.test_btn.config(state=tk.DISABLED)
        self.status_var.set("连接测试中...")
        
        def test_thread():
            result = None
            error_msg = None
            
            try:
                result = self._run_connection_probe(website, test_query)
            except Exception as e:
                error_msg = str(e)
                self.log(f"❌ 连接测试异常: {error_msg}", "ERROR")
            
            # v1.9.8: 改进错误处理 - 在主线程中显示消息框
            if result and result.get('ok'):
                title = result.get('title') or ''
                image_url = result.get('image_url') or ''
                self.log(f"✅ 连接测试成功！", "SUCCESS")
                self.log(f"📝 测试标题: {title[:100]}...", "INFO")
                if image_url:
                    self.log(f"📝 测试图片已验证可下载: {image_url}", "INFO")
                
                self.log("🔧 测试文件名处理功能:", "INFO")
                
                test_filenames = [
                    "rbk-115c.avi",
                    "START321U.mp4", 
                    "rbk111.mkv",
                    "DASS-663.avi"
                ]
                
                for test_file in test_filenames:
                    cleaned = self.clean_filename_for_search(test_file)
                    self.log(f"📝   {test_file} -> {cleaned}", "INFO")
                
                # 使用 after 在主线程中显示消息框
                self.window.after(0, lambda: self._show_messagebox(
                    'info',
                    "测试成功",
                    f"✅ 连接测试成功！\n\n网站: {website_config.get('name', website)}\n测试查询: {test_query}\n提取标题: {title[:50]}..."
                ))
            elif error_msg:
                self.log(f"❌ 连接测试异常: {error_msg}", "ERROR")
                self.window.after(0, lambda: self._show_messagebox(
                    'error',
                    "测试异常",
                    f"❌ 连接测试异常\n\n错误: {error_msg}"
                ))
            else:
                error_type = result.get('error_type') if result else 'unknown'
                message = result.get('message') if result else 'no result'
                self.log(f"❌ 连接测试失败: {error_type} - {message}", "ERROR")
                # v1.4.5: JAVLibrary 常见失败是 Cloudflare 验证页，不是网站配置错。
                if website == 'javlibrary':
                    self.log(f"⚠️ JAVLibrary 测试未通过，通常是 Cloudflare 验证未完成或超时", "WARNING")
                    self.window.after(0, lambda: self._show_messagebox(
                        'warning',
                        "JAVLibrary 需要验证",
                        "⚠️ JAVLibrary 连接测试未通过。\n\n"
                        f"测试查询: {test_query}\n"
                        f"失败原因: {error_type} - {message}\n\n"
                        "请检查是否弹出了 Chrome 浏览器：\n"
                        "1. 在浏览器中完成 Cloudflare 验证\n"
                        "2. 验证通过后，再点一次“测试连接”\n"
                        "3. 如果没有弹出浏览器，请告诉我“JAVLibrary 不弹浏览器”"
                    ))
                else:
                    self.log(f"❌ 连接测试失败：未能提取内容", "ERROR")
                    self.window.after(0, lambda: self._show_messagebox(
                        'error',
                        "测试失败",
                        "❌ 连接测试失败\n\n请检查网站配置和网络连接"
                    ))
            self.window.after(0, lambda: (
                self.test_btn.config(state=tk.NORMAL),
                self.status_var.set(STATUS_READY),
            ))
        
        # 在后台线程中执行测试
        threading.Thread(target=test_thread, daemon=True).start()
    
    def start_processing(self):
        """开始处理。"""
        if self.is_processing:
            self.log("⚠️ 正在处理中，请等待完成", "WARNING")
            return
        
        self.log("🎬 准备开始处理...", "INFO")
        if getattr(self, '_safe_stop_dialog', None) is not None:
            self._close_safe_stop_dialog()
        self._safe_stop_requested = False
        self._safe_stop_dialog_done = False
        self._safe_stop_dialog_visible = False
        request = self._capture_processing_request()
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(text="⏹️ 停止处理", state=tk.NORMAL)
        self.status_var.set("处理中...")
        
        threading.Thread(target=lambda: self._process_files_worker(request), daemon=True).start()
    
    def stop_processing_func(self):
        """停止处理"""
        if self._is_stop_requested():
            return
        active_transaction = self._has_active_file_transaction()
        self._request_stop()
        if not active_transaction:
            self._cancel_inflight_network()
        self._apply_stopping_ui()
        if active_transaction:
            self.log("⏹️ 停止请求已提交：已有文件落盘事务，正在等待事务完成或回滚，源文件会保持安全", "WARNING")
        else:
            self.log("⏹️ 停止请求已提交：当前无文件落盘事务，已请求快速取消网络/浏览器任务，源文件保持原样", "WARNING")
    
    def save_config(self):
        """保存配置"""
        try:
            config = {
                'search_url': self.search_url_var.get(),
                'text_selector': self.text_selector_var.get(),
                'image_selector': self.image_selector_var.get(),
                'max_filename_length': self.max_filename_length_var.get(),
                'preserve_actor': self.preserve_actor_var.get(),
                'batch_count': self.batch_count_var.get(),
                'dry_run': self.dry_run_var.get()
            }
            
            config_path = os.path.join(os.path.dirname(__file__), CONFIG_FILENAME)
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            
            self.log("💾 配置保存成功", "SUCCESS")
            messagebox.showinfo("保存成功", "✅ 配置已保存")
            
        except Exception as e:
            self.log(f"❌ 配置保存失败: {e}", "ERROR")
            messagebox.showerror("保存失败", f"❌ 配置保存失败\n\n错误: {e}")
    
    def reset_config(self):
        """重置配置"""
        website = self.website_var.get()
        config = self.website_configs.get(website, {})
        
        self.search_url_var.set(config.get('search_url', ''))
        title_selectors = config.get('title_selectors', ['title'])
        self.text_selector_var.set(title_selectors[0])
        image_selectors = config.get('image_selectors', ['img'])
        self.image_selector_var.set(image_selectors[0])
        
        self.max_filename_length_var.set('')
        self.preserve_actor_var.set(True)
        self.batch_count_var.set('')
        
        self.log("🔄 配置已重置为默认值", "INFO")
        messagebox.showinfo("重置完成", "✅ 配置已重置为默认值")
    
    def clear_log(self):
        """清空日志"""
        self.log_text.delete(1.0, tk.END)
        self.log("🗑️ 日志已清空", "INFO")
    
    def run(self):
        """运行程序"""
        # v1.4.3: 清理Selenium浏览器
        def on_closing():
            if hasattr(self, "anti_crawl") and self.anti_crawl and \
               hasattr(self.anti_crawl, "selenium_javlibrary") and self.anti_crawl.selenium_javlibrary:
                self.log("🔒 正在关闭Selenium浏览器...", "INFO")
                self.anti_crawl.selenium_javlibrary.stop_browser()
            self.window.destroy()

        self.window.protocol("WM_DELETE_WINDOW", on_closing)

        try:
            self.window.mainloop()
        except KeyboardInterrupt:
            self.log("👋 程序被用户中断", "INFO")
        except Exception as e:
            self.log(f"❌ 程序运行异常: {e}", "ERROR")
def main():
    """主函数"""
    print(f"🚀 启动 {APP_TITLE}")
    print("=" * 50)
    print(f"🏷️ 基线版本: {BASELINE_VERSION}")
    print(f"🧱 构建标识: {BASELINE_BUILD_ID}")
    print(f"📅 构建日期: {BASELINE_BUILD_DATE}")
    print("🆕 当前基线能力:")
    print("  ✅ 支持JAVLibrary数据源")
    print("  ✅ 高清封面图片")
    print("  ✅ 多数据源备用 (JavHoo/JavBus/JAVLibrary)")
    print("  ✅ 从完整标题提取番号")
    print("  ✅ 网站前缀和质量标记移除")
    print("  ✅ 增强序列文件识别")
    print()
    
    try:
        app = JavFileOrganizer()
        app.run()
    except Exception as e:
        print(f"❌ 程序启动失败: {e}")
        # v1.4.5: windowed / PyInstaller 环境没有 stdin，input() 会 EOFError
        try:
            if sys.stdin and sys.stdin.isatty():
                input("按回车键退出...")
        except Exception:
            pass

if __name__ == "__main__":
    main()
