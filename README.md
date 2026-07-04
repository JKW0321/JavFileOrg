# JAV File Organizer v1.5.0-Selenium

## 📦 基线版本说明

**当前基线版本：v1.5.0-Selenium**  
**基线日期：2026-07-04**

这是当前统一后的正式基线版本，已经整合并验证以下能力：

1. **JAVLibrary Selenium 接入**：可见窗口完成 Cloudflare 验证，后续复用 profile / cookie
2. **JavHoo 搜索修复**：搜索 URL 改为 `/search/{query}`，支持详情页升级
3. **文件名清理修复**：下载站前缀 / 网站名水印统一清理
4. **序列文件识别修复**：`-1/-2/-3` 与 `a/b/c` 支持完整标题、下载站前缀、共享封面
5. **macOS GUI 修复**：Tk9 + PyInstaller 打包，界面正常显示
6. **版本统一**：界面、状态栏、启动日志、构建信息统一使用 `v1.5.0-Selenium`

---

## 📋 系统要求

- **操作系统**：macOS / Windows / Linux
- **Python 版本**：Python 3.8+
- **浏览器**：Chrome 或 Chromium

---

## 🚀 运行方式

### 源码运行

```bash
pip3 install -r requirements.txt
python3 jav_file_organizer.py
```

### macOS 可执行文件

当前桌面正式基线包：

```text
JAVFileOrganizer-v1.5.0.app
```

---

## 📖 使用说明

### 1. 数据源选择

- **JavHoo**：速度快，适合作为默认选择
- **JavBus**：内容丰富，适合作为备选
- **JAVLibrary**：信息完整、封面质量高，首次可能需要 Cloudflare 验证

### 2. JAVLibrary 首次使用

1. 选择 `JAVLibrary`
2. 点击 **测试连接** 或 **开始处理**
3. 程序会弹出 Chrome 浏览器窗口
4. 如果遇到 Cloudflare，请手动完成验证
5. 验证通过后程序会继续，并保存 profile / cookie
6. 后续再次使用通常不需要反复验证

### 3. 序列文件行为

对于这类文件：

```text
ABF-139-1 美少女 第1話.mp4
ABF-139-2 美少女 第2話.mp4
ABF-139-3 美少女 第3話.mp4
```

输出结果会是：

```text
ABF-139 ...-1.mp4
ABF-139 ...-2.mp4
ABF-139 ...-3.mp4
ABF-139 ....jpg   ← 共享封面，仅 1 张
```

---

## 🔍 当前基线核心文件

1. `jav_file_organizer.py` — 主程序 / GUI / 工作流控制
2. `filename_utils.py` — 文件名与番号提取纯函数
3. `selenium_javlibrary.py` — JAVLibrary Selenium 抓取与验证逻辑
4. `atomic_processor_v11.py` — 原子文件移动与图片下载

---

## ⚠️ 常见问题

### Q1: 测试 JAVLibrary 时提示验证未完成？
这是 Cloudflare 安全验证页，不是网站配置错误。请在弹出的浏览器里完成验证后重试。

### Q2: 出现 `_1` 文件？
说明目标文件名已存在，程序为避免覆盖旧文件自动加 `_1` 后缀。属于保守去重行为。

### Q3: JavHoo 没命中某些番号？
JavHoo 本身并不收录所有番号，属于网站内容范围问题，不一定是程序故障。

---

## 📝 当前基线识别字符串

启动时会显示：

```text
✅ JAV 文件整理工具 v1.5.0-Selenium 启动完成 | baseline-unified-tk9-selenium | 2026-07-04
```

如果你看到的是其他版本号，说明运行的不是当前统一后的基线版本。

---

## 📚 文档说明

本仓库中还保留了若干 `BUGFIX_*.md` / `TEST_REPORT*.md` / `PERFORMANCE_*.md` 文档，
它们用于记录历史修复过程。**正式当前版本说明以本文档和 `JAVFileOrganizer-v1.5.0.app` 为准。**
