# 📦 交付清单 - v2.1.2

## 当前正式交付物

### 桌面可执行文件
- **JAVFileOrganizer-v2.1.2.app** — 当前 macOS 基线包，运行时版本为 `v2.1.2`

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

1. WebView 组件化主界面、设置页和运行报告
2. 全自动、自动有码、自动无码及指定来源路由
3. 多种文件名与番号格式识别
4. 普通处理和巡检中的视频组共享封面
5. 巡检预检、正式巡检及最终结果状态区分
6. 重复视频、孤儿图片、异常小视频及封面健康检查
7. Dry Run / manifest / run summary 审计能力
8. Provider 模块化与事务性文件处理

---

## 基线版本信息

- **Git 维护版本**: v2.1.2
- **运行时版本**: v2.1.2
- **构建标识**: baseline-v2.1.2
- **构建日期**: 2026-08-02
- **正式桌面包**: `JAVFileOrganizer-v2.1.2.app`

---

## 验收标志

程序启动日志应显示：

```text
✅ JAV 文件整理工具 v2.1.2 启动完成 | baseline-v2.1.2 | 2026-08-02
```

默认离线回归应通过：

```bash
python3 run_baseline_tests.py
```
