#!/usr/bin/env python3
"""
Selenium Cookie获取助手
用于通过真实浏览器获取JAVLibrary的Cloudflare Cookie
"""

import time
import pickle
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


class SeleniumCookieHelper:
    """Selenium Cookie获取助手"""
    
    def __init__(self, log_callback=None):
        """
        初始化
        
        Args:
            log_callback: 日志回调函数，用于显示进度信息
        """
        self.log_callback = log_callback
        self.driver = None
    
    def log(self, message, level="INFO"):
        """记录日志"""
        if self.log_callback:
            self.log_callback(message, level)
        else:
            print(f"[{level}] {message}")
    
    def get_javlibrary_cookies(self, timeout=60):
        """
        打开浏览器，让用户完成Cloudflare验证，然后获取Cookie
        
        Args:
            timeout: 等待验证完成的超时时间（秒）
        
        Returns:
            dict: Cookie字典，如果失败返回None
        """
        try:
            self.log("🌐 正在启动Chrome浏览器...", "INFO")
            
            # 配置Chrome选项
            chrome_options = Options()
            # 不使用无头模式，让用户看到浏览器
            # chrome_options.add_argument('--headless')
            chrome_options.add_argument('--disable-blink-features=AutomationControlled')
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option('useAutomationExtension', False)
            
            # 尝试创建WebDriver
            try:
                self.driver = webdriver.Chrome(options=chrome_options)
            except Exception as e:
                self.log(f"❌ 无法启动Chrome: {e}", "ERROR")
                self.log("💡 请确保已安装Chrome浏览器", "INFO")
                self.log("💡 或者尝试: pip install webdriver-manager", "INFO")
                return None
            
            self.log("✅ Chrome已启动", "INFO")
            self.log("🔗 正在访问JAVLibrary...", "INFO")
            
            # 访问JAVLibrary
            self.driver.get("https://www.javlibrary.com")
            
            self.log("⏳ 请在浏览器中完成Cloudflare验证...", "INFO")
            self.log(f"⏳ 等待最多{timeout}秒...", "INFO")
            
            # 等待验证完成（检测页面标题变化）
            start_time = time.time()
            verified = False
            
            while time.time() - start_time < timeout:
                try:
                    title = self.driver.title
                    
                    # 如果标题不再是"Just a moment..."，说明验证完成
                    if title and "just a moment" not in title.lower():
                        self.log(f"✅ 验证完成！页面标题: {title}", "SUCCESS")
                        verified = True
                        break
                    
                    time.sleep(1)
                    
                except Exception:
                    pass
            
            if not verified:
                self.log("⏰ 验证超时", "WARNING")
                return None
            
            # 等待一下，确保Cookie完全设置
            time.sleep(2)
            
            # 获取所有Cookie
            self.log("🍪 正在获取Cookie...", "INFO")
            cookies = self.driver.get_cookies()
            
            # 转换为字典格式
            cookie_dict = {}
            for cookie in cookies:
                cookie_dict[cookie['name']] = cookie['value']
                self.log(f"  ✓ {cookie['name']}: {cookie['value'][:20]}...", "INFO")
            
            self.log(f"✅ 成功获取{len(cookie_dict)}个Cookie", "SUCCESS")
            
            return cookie_dict
            
        except Exception as e:
            self.log(f"❌ 获取Cookie失败: {e}", "ERROR")
            return None
        
        finally:
            # 关闭浏览器
            if self.driver:
                self.log("🔒 正在关闭浏览器...", "INFO")
                self.driver.quit()
                self.log("✅ 浏览器已关闭", "INFO")
    
    def save_cookies_to_session(self, cookies, session):
        """
        将Cookie保存到requests Session对象
        
        Args:
            cookies: Cookie字典
            session: requests.Session对象
        """
        if not cookies:
            return False
        
        try:
            for name, value in cookies.items():
                # 设置Cookie到session
                if name == 'cf_clearance':
                    session.cookies.set(name, value, domain='javlibrary.com', path='/')
                elif name == 'dm':
                    session.cookies.set(name, value, domain='javlibrary.com', path='/')
                elif name in ['over18', 'timezone']:
                    session.cookies.set(name, value, domain='www.javlibrary.com', path='/')
                else:
                    session.cookies.set(name, value)
            
            return True
        except Exception as e:
            self.log(f"❌ 保存Cookie到session失败: {e}", "ERROR")
            return False


# 测试代码
if __name__ == "__main__":
    print("="*50)
    print("Selenium Cookie获取测试")
    print("="*50)
    
    helper = SeleniumCookieHelper()
    cookies = helper.get_javlibrary_cookies(timeout=120)
    
    if cookies:
        print("\n" + "="*50)
        print("✅ 成功获取Cookie！")
        print("="*50)
        for name, value in cookies.items():
            print(f"  {name}: {value[:30]}...")
    else:
        print("\n" + "="*50)
        print("❌ 获取Cookie失败")
        print("="*50)
