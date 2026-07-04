#!/usr/bin/env python3
"""
测试 Chrome 窗口是否能正确弹出
"""

import os
import sys
import tempfile

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from selenium_javlibrary import SeleniumJAVLibrary

def test_chrome_window():
    print("=" * 60)
    print("测试 Chrome 窗口启动")
    print("=" * 60)
    
    # 清理旧的用户数据目录
    user_data_dir = os.path.join(tempfile.gettempdir(), 'selenium_jav_chrome')
    if os.path.exists(user_data_dir):
        print(f"⚠️  发现旧的用户数据目录: {user_data_dir}")
        print("💡 建议删除: rm -rf /tmp/selenium_jav_chrome")
    
    # 强制使用可见窗口模式
    print("\n🚀 启动 Selenium（可见窗口模式）...")
    helper = SeleniumJAVLibrary(headless=False)
    
    # 启动浏览器
    if helper.start_browser():
        print("\n✅ 浏览器已启动")
        print("👀 请检查是否有新的 Chrome 窗口弹出")
        print("\n⏳ 等待 10 秒...")
        
        import time
        time.sleep(10)
        
        print("\n🔒 关闭浏览器...")
        helper.stop_browser()
        print("✅ 测试完成")
    else:
        print("\n❌ 浏览器启动失败")

if __name__ == "__main__":
    test_chrome_window()
