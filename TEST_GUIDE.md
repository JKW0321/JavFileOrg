# 基线版本测试指南

**版本**: v1.5.0-Selenium  
**测试日期**: 2026-07-04

---

## 🎯 测试目标

验证当前基线版本：
1. GUI 正常显示
2. JavHoo / JavBus / JAVLibrary 能按预期工作
3. 序列文件输出为 1 张共享 jpg + N 个带序号 mp4
4. 版本号显示统一

---

## 📋 测试步骤

### 1. 启动程序

优先使用桌面正式包：

```text
JAVFileOrganizer-v1.5.0.app
```

或源码运行：

```bash
python3 jav_file_organizer.py
```

### 2. 验证版本号

启动日志应包含：

```text
✅ JAV 文件整理工具 v1.5.0-Selenium 启动完成 | baseline-unified-tk9-selenium | 2026-07-04
```

### 3. 基础连接测试

- JavHoo：`SONE-753`
- JavBus：`SONE-753`
- JAVLibrary：`SSIS-001`

### 4. 序列文件测试

准备：

```text
ABF-139-1 美少女 第1話.mp4
ABF-139-2 美少女 第2話.mp4
ABF-139-3 美少女 第3話.mp4
```

预期：

```text
ABF-139 ...-1.mp4
ABF-139 ...-2.mp4
ABF-139 ...-3.mp4
ABF-139 ....jpg
```

### 5. GUI 检查清单

- [ ] 窗口标题显示 `v1.5.0-Selenium`
- [ ] 状态栏显示 `v1.5.0-Selenium`
- [ ] 三个数据源单选可见
- [ ] 测试连接 / 开始处理 / 停止处理按钮可见
- [ ] 日志面板能实时输出

---

## ✅ 当前基线通过标准

- [ ] GUI 可见且可操作
- [ ] JavHoo 测试连接通过
- [ ] JavBus 测试连接通过
- [ ] JAVLibrary 至少能弹出浏览器并识别验证状态
- [ ] 序列文件输出结构正确
- [ ] 版本号统一显示为 `v1.5.0-Selenium`
