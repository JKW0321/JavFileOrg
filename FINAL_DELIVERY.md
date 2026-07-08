# JAV File Organizer 历史交付记录

**历史交付版本**: v1.5.0
**当前 Git 维护版本**: v1.5.6
**构建标识**: baseline-v1.5.6
**交付日期**: 2026-07-08

---

> 说明：本文保留 v1.5.0 桌面基线的交付记录。当前源码维护说明以 `README.md`、`DELIVERY.md`、`TEST_GUIDE.md` 和 `MAINTENANCE.md` 为准。

## ✅ v1.5.0 基线已解决的问题

### 运行与 GUI
1. ✅ Tk 8.5 / system Python 下 ttk 黑屏问题 → 改为 Tk9 打包基线
2. ✅ Tk9 `trace('w', ...)` 兼容问题 → 改为 `trace_add('write', ...)`
3. ✅ windowed / PyInstaller 环境 stdin EOF 问题 → 启动失败路径加保护

### 抓取与网站兼容
4. ✅ JavHoo 搜索 URL 失效 → 改为 `/search/{query}`
5. ✅ JavHoo 支持详情页升级，优先拿更准确标题 / 更高清封面
6. ✅ JAVLibrary Cloudflare 繁中验证页识别
7. ✅ JAVLibrary 搜索结果页解析（新版列表页）
8. ✅ PyInstaller 打包遗漏 Selenium 子模块

### 文件整理
9. ✅ 网站名前缀 / 水印清理统一
10. ✅ 带完整标题的序列文件正确识别
11. ✅ 共享封面 + `-1/-2/-3` 输出修复

---

## 🎯 当前三网站机制

### JavHoo
- requests 直接访问
- 搜索 URL: `/search/{query}`
- 支持搜索页 → 详情页升级

### JavBus
- requests + 反爬虫 session
- 速度中等，内容丰富

### JAVLibrary
- Selenium + Chrome
- 首次可能需要 Cloudflare 人工验证
- 验证后复用 profile / cookie

---

## 🚀 使用说明

### macOS 正式包

```text
JAVFileOrganizer-v1.5.6.app
```

### 启动成功标志

```text
✅ JAV 文件整理工具 v1.5.6 启动完成 | baseline-v1.5.6 | 2026-07-08
```

### JAVLibrary 首次使用

1. 选择 `JAVLibrary`
2. 点 `测试连接`
3. 弹出 Chrome 后完成 Cloudflare 验证
4. 验证通过后再次测试连接或直接开始处理

---

## 📁 当前文档策略

- `README.md` / `QUICKSTART.md` / `TEST_GUIDE.md` / `MAINTENANCE.md`：当前维护文档
- `BUGFIX_*.md` / `PERFORMANCE_*.md` / `TEST_REPORT*.md`：历史修复与测试记录

当前正式源码维护说明以 `README.md` 和 `MAINTENANCE.md` 为准。
