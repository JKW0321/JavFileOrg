#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Single source of truth for runtime and release metadata."""

BASELINE_VERSION = "v2.1.4"
BASELINE_BUILD_DATE = "2026-08-02"
BASELINE_BUILD_ID = "baseline-v2.1.4"
APP_TITLE = f"JAV 文件整理工具 {BASELINE_VERSION}"
STATUS_READY = f"就绪 - {BASELINE_VERSION}"
CONFIG_FILENAME = "config.json"

RELEASE_NOTES = (
    "全自动来源补充 MadouQu、MGStage、LibreDMM、R18.dev 与 ART Video，并按文件身份跳过无效的跨站空跑。",
    "修正 HEYDOUGA、1Pondo 日期编号、RED、S2MBD、XXX-AV 等文件名误识别和错误视频组拆分。",
    "ART 批次可在 Finish 目录继续保持厂牌身份；严格校验 No./Vol./Part 期号，禁止同系列不同期数误匹配。",
    "修复桌面包 TLS 证书缺失，并阻止在程序运行期间覆盖应用包。",
    "新增 ART Video 旧片联网核验：仅使用直属 ART 目录识别厂牌，严格核对网络标题与厂牌后规范名称并下载封面，不再把本地配套图当作元数据来源。",
    "FC2-PPV 使用 FC2 官方商品页，并兼容文件名中常见的 FC2-PPT 误写；Night24 数字目录会安全识别并在缺少可靠在线索引时保持源文件。",
    "About 改为独立软件信息页，只展示版本、构建信息与 Release Notes。",
    "新增 LibreDMM 与 R18.dev 结构化数据源，严格核对番号并只接受完整大封面。",
    "全自动先判断有码/无码；有码按 JavBus、JavHoo、LibreDMM、R18.dev 依次回退。",
    "遍历子目录时，若目录内只有一个纯数字视频文件，会结合目录名识别影片信息。",
    "快速巡检完整读取并解码图片；深度巡检额外核验封面内容与影片身份是否一致。",
    "加强视频组共享封面、重复文件、错误封面及占位 Logo 的保护和修复规则。",
)
