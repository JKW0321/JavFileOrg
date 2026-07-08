# 📦 交付清单 - v1.5.6

## 当前正式交付物

### 桌面可执行文件
- **JAVFileOrganizer-v1.5.6.app** — 当前 macOS 基线包，运行时版本为 `v1.5.6`

### 核心源码
- `jav_file_organizer.py`
- `selenium_javlibrary.py`
- `filename_utils.py`
- `atomic_processor_v11.py`
- `workflow_service.py`
- `manifest_utils.py`
- `providers/`
- `requirements.txt`

### 主文档
- `README.md`
- `QUICKSTART.md`
- `TEST_GUIDE.md`
- `MAINTENANCE.md`
- `FINAL_DELIVERY.md`

---

## 本基线版本已包含的能力

1. Selenium 接入 JAVLibrary
2. JavHoo 搜索与详情页升级修复
3. JAVLibrary Cloudflare 识别与结果页解析修复
4. 序列文件识别 / 共享封面修复
5. 网站名前缀清理修复
6. Tk9 + PyInstaller macOS 打包修复
7. Dry Run / manifest / run summary 审计能力
8. Provider 模块化与 JavHoo 封面选择修复

---

## 基线版本信息

- **Git 维护版本**: v1.5.6
- **运行时版本**: v1.5.6
- **构建标识**: baseline-v1.5.6
- **构建日期**: 2026-07-08
- **正式桌面包**: `JAVFileOrganizer-v1.5.6.app`

---

## 验收标志

程序启动日志应显示：

```text
✅ JAV 文件整理工具 v1.5.6 启动完成 | baseline-v1.5.6 | 2026-07-08
```

默认离线回归应通过：

```bash
python3 run_baseline_tests.py
```
