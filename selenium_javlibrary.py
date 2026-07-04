#!/usr/bin/env python3
"""
Selenium JAVLibrary数据抓取模块
使用真实浏览器绕过Cloudflare保护
"""

import time
import os
import pickle
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup


class SeleniumJAVLibrary:
    """Selenium JAVLibrary数据抓取器"""
    
    def __init__(self, log_callback=None, headless=False):
        """
        初始化
        
        Args:
            log_callback: 日志回调函数
            headless: 是否使用无头模式
        """
        self.log_callback = log_callback
        self.headless = headless
        self.driver = None
        self.cookies_file = os.path.expanduser('~/.jav_organizer/javlibrary_selenium_cookies.pkl')
        self.profile_dir = os.path.expanduser('~/.jav_organizer/javlibrary_chrome_profile')
        self.verified = False
    
    def log(self, message, level="INFO"):
        """记录日志"""
        if self.log_callback:
            self.log_callback(message, level)
        else:
            print(f"[{level}] {message}")
    
    def start_browser(self):
        """启动浏览器"""
        if self.driver:
            return True
        
        try:
            self.log("🌐 正在启动Chrome浏览器...", "INFO")
            
            chrome_options = Options()
            
            # v1.4.3: 设置语言为繁体中文
            chrome_options.add_argument('--lang=zh-TW')
            chrome_options.add_experimental_option('prefs', {
                'intl.accept_languages': 'zh-TW,zh-CN,zh,en'
            })
            
            # v1.4.6: 使用持久化 profile 目录，避免每次启动都像“新浏览器”一样重新挑战 Cloudflare
            os.makedirs(self.profile_dir, exist_ok=True)
            user_data_dir = self.profile_dir
            chrome_options.add_argument(f'--user-data-dir={user_data_dir}')
            
            # 确保完全独立的实例
            chrome_options.add_argument('--no-first-run')
            chrome_options.add_argument('--no-default-browser-check')
            chrome_options.add_argument('--remote-debugging-port=0')  # 禁用远程调试端口复用
            
            # v1.4.3: 禁用 ChromeDriver 日志警告
            chrome_options.add_argument('--log-level=3')  # 只显示严重错误
            # 注意: excludeLogging 在某些 ChromeDriver 版本中不支持，已移除
            
            if self.headless:
                chrome_options.add_argument('--headless')
                self.log("👁️ 使用无头模式", "INFO")
            else:
                # 非无头模式：确保窗口可见
                self.log("👁️ 使用可见窗口模式", "INFO")
                chrome_options.add_argument('--start-maximized')  # 最大化窗口
                chrome_options.add_argument('--disable-infobars')  # 禁用信息栏
            
            chrome_options.add_argument('--disable-blink-features=AutomationControlled')
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option('useAutomationExtension', False)
            
            self.driver = webdriver.Chrome(options=chrome_options)
            
            if not self.headless:
                # 非无头模式：尝试将窗口置于前台
                try:
                    self.driver.maximize_window()
                    self.log("✅ Chrome已启动（窗口可见）", "INFO")
                except Exception:
                    self.log("✅ Chrome已启动", "INFO")
            else:
                self.log("✅ Chrome已启动（无头模式）", "INFO")
            
            # 尝试加载保存的Cookie
            self._load_cookies()
            
            return True
            
        except Exception as e:
            self.log(f"❌ 无法启动Chrome: {e}", "ERROR")
            return False
    
    def stop_browser(self):
        """关闭浏览器"""
        if self.driver:
            try:
                self.driver.quit()
                self.driver = None
                self.log("🔒 浏览器已关闭", "INFO")
            except Exception:
                self.driver = None
                pass

    def _driver_is_usable(self):
        """当前 driver 是否仍然可用。"""
        if not self.driver:
            return False
        try:
            _ = self.driver.current_window_handle
            _ = self.driver.title
            return True
        except Exception:
            return False

    def ensure_browser(self):
        """确保 driver 可用；如果窗口被关掉或 session 失效，则自动重启。"""
        if self._driver_is_usable():
            return True
        if self.driver:
            self.log("⚠️ 检测到 Selenium 窗口已关闭或 session 失效，正在重启浏览器...", "WARNING")
            self.stop_browser()
        return self.start_browser()
    
    def _load_cookies(self):
        """加载保存的Cookie"""
        if not os.path.exists(self.cookies_file):
            return False
        
        try:
            # 先访问网站，才能设置Cookie
            self.driver.get("https://www.javlibrary.com")
            time.sleep(1)
            
            with open(self.cookies_file, 'rb') as f:
                cookies = pickle.load(f)
            
            for cookie in cookies:
                try:
                    self.driver.add_cookie(cookie)
                except Exception:
                    pass
            
            self.log("✅ 已加载保存的Cookie", "INFO")
            self.verified = True
            return True
            
        except Exception as e:
            self.log(f"⚠️ 加载Cookie失败: {e}", "WARNING")
            return False
    
    def _save_cookies(self):
        """保存Cookie"""
        try:
            os.makedirs(os.path.dirname(self.cookies_file), exist_ok=True)
            
            cookies = self.driver.get_cookies()
            with open(self.cookies_file, 'wb') as f:
                pickle.dump(cookies, f)
            
            self.log("✅ Cookie已保存", "INFO")
            return True
            
        except Exception as e:
            self.log(f"⚠️ 保存Cookie失败: {e}", "WARNING")
            return False
    
    def _is_verification_page(self, title='', html=''):
        """检测是否仍停留在 Cloudflare / 安全验证页面。

        规则：结果页优先级高于验证页。
        否则像 "SSIS-001 識別碼搜尋結果 - JAVLibrary" 这种已成功页面，
        只因为 HTML 里还残留 Cloudflare 脚本字段（如 cloudflare / __cf_chl_）
        就会被误判成“仍在验证”。
        """
        title_lower = (title or '').strip().lower()
        html_lower = (html or '').lower()

        # 先认结果页（优先级最高）
        result_title_markers = [
            'javlibrary',
            '識別碼搜尋結果',
            '识别码搜索结果',
            'id search result',
        ]
        if self._is_result_page(html):
            return False
        if ('javlibrary' in title_lower) and any(m.lower() in title_lower for m in result_title_markers[1:]):
            return False

        title_markers = [
            'just a moment',
            'please wait',
            '請稍候',
            '请稍候',
            '安全驗證',
            '安全验证',
        ]
        body_markers = [
            'checking your browser',
            'security verification',
            '安全驗證',
            '安全验证',
            '正在執行安全驗證',
            '正在执行安全验证',
            'enable javascript and cookies to continue',
            '__cf_chl_',
            'cf-challenge',
            'cloudflare',
        ]

        if any(marker.lower() in title_lower for marker in title_markers):
            return True
        if any(marker.lower() in html_lower for marker in body_markers):
            return True
        return False

    def _is_result_page(self, html=''):
        """粗略判断当前页面是否已经进入 JAVLibrary 正常结果页。"""
        html_lower = (html or '').lower()
        markers = [
            'video_jacket_img',
            'post-title',
            'vl_searchbyid.php',
            'video_title',
            'star',
            'videothumblist',
            'class="video"',
        ]
        return any(m in html_lower for m in markers)

    def _normalize_cover_url(self, cover_url):
        """把 JAVLibrary 返回的各种图片地址统一成可下载 URL。"""
        cover_url = (cover_url or '').strip()
        if not cover_url:
            return ''
        if cover_url.startswith('http'):
            return cover_url
        if cover_url.startswith('//'):
            return 'https:' + cover_url
        return 'https://www.javlibrary.com' + cover_url

    def _extract_result_from_soup(self, soup):
        """从 JAVLibrary 页面中提取 title / cover / actors / release_date。

        同时兼容：
        1. 旧版详情页结构 (`h3.post-title`, `#video_jacket_img`)
        2. 当前常见的搜索结果列表页 (`div.videothumblist div.video a`)
        """
        result = {}

        # 搜索结果列表页
        search_result = soup.select_one('div.videothumblist div.video a, div.videos div.video a')
        if search_result:
            code_elem = search_result.select_one('div.id')
            title_elem = search_result.select_one('div.title')
            title_attr = search_result.get('title', '').strip()
            code_text = code_elem.get_text().strip() if code_elem else ''
            title_text = title_elem.get_text().strip() if title_elem else ''

            combined_title = title_attr or title_text
            if combined_title:
                if code_text and not combined_title.upper().startswith(code_text.upper()):
                    combined_title = f"{code_text} {combined_title}".strip()
                result['title'] = combined_title

            img_elem = search_result.select_one('img')
            if img_elem:
                cover_url = img_elem.get('src', '') or img_elem.get('data-src', '')
                normalized = self._normalize_cover_url(cover_url)
                if normalized:
                    result['cover_url'] = normalized

        # 详情页回退
        if 'title' not in result:
            title_elem = soup.find('h3', class_='post-title')
            if title_elem:
                result['title'] = title_elem.get_text().strip()

        if 'cover_url' not in result:
            cover_elem = soup.find('img', id='video_jacket_img')
            if cover_elem:
                normalized = self._normalize_cover_url(cover_elem.get('src', ''))
                if normalized:
                    result['cover_url'] = normalized

        # 详情页才有的扩展字段
        actors = []
        actor_elems = soup.find_all('span', class_='star')
        for elem in actor_elems:
            actor_name = elem.get_text().strip()
            if actor_name:
                actors.append(actor_name)
        if actors:
            result['actors'] = actors

        date_elem = soup.find('td', class_='text', string='Release Date:')
        if date_elem:
            date_value = date_elem.find_next_sibling('td')
            if date_value:
                result['release_date'] = date_value.get_text().strip()

        return result

    def verify_cloudflare(self, timeout=180):
        """
        等待用户完成Cloudflare验证
        
        Args:
            timeout: 超时时间（秒）
        
        Returns:
            bool: 是否验证成功
        """
        if self.verified:
            return True
        
        self.log("⏳ 请在浏览器中完成Cloudflare验证...", "INFO")
        self.log(f"⏳ 等待最多{timeout}秒...", "INFO")
        
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                title = self.driver.title or ''
                html = self.driver.page_source or ''

                # 只要还在验证页，就继续等用户完成挑战
                if not self._is_verification_page(title, html):
                    self.log(f"✅ 验证完成！页面标题: {title}", "SUCCESS")
                    self.verified = True
                    self._save_cookies()
                    return True

                time.sleep(1)

            except Exception:
                pass
        
        self.log("⏰ 验证超时", "WARNING")
        return False
    
    def search_by_id(self, jav_id, _retry_on_window_error=True):
        """
        根据番号搜索JAVLibrary
        
        Args:
            jav_id: 番号
        
        Returns:
            dict: 包含标题、封面等信息的字典，失败返回None
        """
        if not self.ensure_browser():
            return None
        
        try:
            # v1.4.3: 使用繁体中文版本
            url = f"https://www.javlibrary.com/tw/vl_searchbyid.php?keyword={jav_id}"
            self.log(f"🔍 搜索: {jav_id}", "INFO")
            self.log(f"🔗 URL: {url}", "INFO")
            
            self.driver.get(url)
            time.sleep(2)

            # v1.4.5: 检查是否需要验证（英文 + 繁中 + 页面 body 标记）
            page_title = self.driver.title or ''
            page_html = self.driver.page_source or ''
            if self._is_verification_page(page_title, page_html):
                self.log(f"⚠️ 需要完成Cloudflare验证，当前标题: {page_title}", "WARNING")
                if self.headless:
                    self.log("⚠️ 当前是无头模式，无法人工完成验证；请改为可见窗口模式", "WARNING")
                    return None
                if not self.verify_cloudflare():
                    return None
                # v1.4.6: 验证完成后优先复用当前页，避免无条件再次 get(url) 触发二次挑战。
                page_title = self.driver.title or ''
                page_html = self.driver.page_source or ''
                if self._is_verification_page(page_title, page_html):
                    self.driver.get(url)
                    time.sleep(2)
                    page_title = self.driver.title or ''
                    page_html = self.driver.page_source or ''
                if self._is_verification_page(page_title, page_html):
                    self.log("❌ 验证后仍停留在安全验证页面", "ERROR")
                    return None

            # 获取页面HTML
            html = self.driver.page_source
            soup = BeautifulSoup(html, 'html.parser')
            
            # 提取信息（纯 helper，方便测试）
            result = self._extract_result_from_soup(soup)

            if 'title' in result:
                source = '搜索结果页' if soup.select_one('div.videothumblist div.video a, div.videos div.video a') else '详情页'
                self.log(f"📝 标题({source}): {result['title']}", "INFO")
            if 'cover_url' in result:
                source = '搜索结果页' if soup.select_one('div.videothumblist div.video a, div.videos div.video a') else '详情页'
                self.log(f"🖼️ 封面({source}): {result['cover_url']}", "INFO")
            if 'actors' in result:
                self.log(f"👤 演员: {', '.join(result['actors'])}", "INFO")
            if 'release_date' in result:
                self.log(f"📅 发行日期: {result['release_date']}", "INFO")
            
            if result:
                self.log("✅ 数据提取成功", "SUCCESS")
                return result
            else:
                self.log("⚠️ 未找到数据", "WARNING")
                return None
            
        except Exception as e:
            msg = str(e).lower()
            if _retry_on_window_error and (
                'no such window' in msg or
                'web view not found' in msg or
                'invalid session id' in msg
            ):
                self.log("⚠️ Selenium 窗口/session 已失效，自动重启后重试一次...", "WARNING")
                self.stop_browser()
                return self.search_by_id(jav_id, _retry_on_window_error=False)
            self.log(f"❌ 搜索失败: {e}", "ERROR")
            return None


# 测试代码
if __name__ == "__main__":
    print("="*50)
    print("Selenium JAVLibrary测试")
    print("="*50)
    
    scraper = SeleniumJAVLibrary(headless=False)
    
    try:
        result = scraper.search_by_id("start-321")
        
        if result:
            print("\n" + "="*50)
            print("✅ 搜索成功！")
            print("="*50)
            for key, value in result.items():
                print(f"  {key}: {value}")
        else:
            print("\n" + "="*50)
            print("❌ 搜索失败")
            print("="*50)
    finally:
        scraper.stop_browser()
