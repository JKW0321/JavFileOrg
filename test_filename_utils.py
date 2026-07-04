#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_filename_utils.py
======================

v1.4.4 新增的 pytest 测试套件。覆盖：
1. strip_site_markers       (网站名清理 — Bug 修复核心)
2. extract_code_from_text   (番号提取)
3. clean_filename_for_search (搜索词生成)
4. sanitize_filename        (最终文件名清理)

运行方式：
    pip install pytest
    pytest test_filename_utils.py -v

不依赖 tkinter / GUI，可在 CI 环境直接运行。
"""

import os
import sys

import pytest

# 确保从同目录导入 filename_utils
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from filename_utils import (
    strip_site_markers,
    extract_code_from_text,
    clean_filename_for_search,
    sanitize_filename,
    extract_series_info,
)


# =========================================================================
# strip_site_markers — v1.4.4 bug 修复核心
# =========================================================================

class TestStripSiteMarkers:
    """网站名清理测试。修复前很多场景残留网站名前缀。"""

    # ---- 下载站 @ 前缀（修复前 100% 漏掉） ----
    @pytest.mark.parametrize("inp,expected", [
        ("4k2.com@ABF-139-C.mp4",                "ABF-139-C.mp4"),
        ("hhd800.com@SONE-753-C_[4K].mp4",       "SONE-753-C_[4K].mp4"),
        ("169bbs.com@RBD011a.mp4",               "RBD011a.mp4"),
        ("javbus.com@START321.mp4",              "START321.mp4"),
        ("some-site.org@ABC-123.mp4",            "ABC-123.mp4"),
    ])
    def test_download_site_prefix(self, inp, expected):
        assert strip_site_markers(inp) == expected

    # ---- 带括号的站点名（修复前漏掉） ----
    @pytest.mark.parametrize("inp,expected", [
        ("[javbus] ABF-139.mp4",     "ABF-139.mp4"),
        ("(javbus) ABF-139.mp4",     "ABF-139.mp4"),
        ("【javhoo】 ABC-123.mp4",    "ABC-123.mp4"),
        ("[JAVBUS] ABC-123.mp4",     "ABC-123.mp4"),  # 大写
    ])
    def test_bracketed_site_names(self, inp, expected):
        assert strip_site_markers(inp) == expected

    # ---- 带连字符的站点名 ----
    @pytest.mark.parametrize("inp,expected", [
        ("javbus - START-321.mp4",   "START-321.mp4"),
        ("START-321 - javbus.mp4",   "START-321.mp4"),
        ("javbus-START-321.mp4",     "START-321.mp4"),
    ])
    def test_hyphenated_site_names(self, inp, expected):
        assert strip_site_markers(inp) == expected

    # ---- 独立单词形式的站点名（v1.9.2 老逻辑支持） ----
    @pytest.mark.parametrize("inp,expected", [
        ("ABF-139 javbus.mp4",       "ABF-139.mp4"),
        ("javbus ABF-139.mp4",       "ABF-139.mp4"),
        ("JAVBUS ABF-139.mp4",       "ABF-139.mp4"),
        ("ABF-139 javhoo.mp4",       "ABF-139.mp4"),
    ])
    def test_standalone_site_names(self, inp, expected):
        assert strip_site_markers(inp) == expected

    # ---- 多种形态叠加 ----
    def test_combined(self):
        assert strip_site_markers("[javbus] (javbus) javbus - ABF-139.mp4") == "ABF-139.mp4"

    # ---- 误伤防护 ----
    @pytest.mark.parametrize("inp", [
        "java-tutorial.mp4",         # java ≠ javbus
        "javascript-basics.mp4",
        "ABC-123.mp4",               # 正常文件
        "javbus.mp4",                # 纯 javbus 文件名（合法）
        "javhoo.txt",
    ])
    def test_no_false_positive(self, inp):
        assert strip_site_markers(inp) == inp

    # ---- 边界 ----
    def test_empty_string(self):
        assert strip_site_markers("") == ""

    def test_pure_javbus_string(self):
        """整串只有 'javbus' 时被清空（不是合法文件名）"""
        assert strip_site_markers("javbus") == ""


# =========================================================================
# extract_code_from_text — 番号提取
# =========================================================================

class TestExtractCode:
    @pytest.mark.parametrize("inp,expected", [
        # v1.3.2 文档承诺的所有格式
        ("ABF-139 美少女と、貸し切り温泉.mp4",  "ABF-139"),
        ("ABF139 标题.mp4",                     "ABF-139"),
        ("[ABF-139] 标题.mp4",                  "ABF-139"),
        ("(ABF-139) 标题.mp4",                  "ABF-139"),
        ("标题 ABF-139.mp4",                    "ABF-139"),
        # v1.4.4 新增：下载站前缀也能正确提取
        ("4k2.com@ABF-139 标题.mp4",            "ABF-139"),
        ("4k2.com@ABF-139-C_[4K].mp4",          "ABF-139"),  # 后缀被剥
        # 序列文件
        ("ABF-139-1 标题.mp4",                  "ABF-139-1"),
        ("ABF-139a 标题.mp4",                   "ABF-139A"),
        ("169bbs.com@RBD011a.mp4",              "RBD-011A"),
        # 后缀清理
        ("START-321-C.mp4",                     "START-321"),
        ("SONE-753-U.mp4",                      "SONE-753"),
    ])
    def test_extract(self, inp, expected):
        assert extract_code_from_text(inp) == expected

    @pytest.mark.parametrize("inp", [
        "",
        "random-file-without-code.mp4",
        "javbus.mp4",                  # 纯 javbus 文件名
    ])
    def test_no_match(self, inp):
        assert extract_code_from_text(inp) is None


# =========================================================================
# clean_filename_for_search — 搜索词生成
# =========================================================================

class TestCleanFilenameForSearch:
    @pytest.mark.parametrize("inp,expected", [
        # 提取路径
        ("ABF-139 美少女.mp4",                  "abf-139"),
        ("4k2.com@ABF-139 标题.mp4",            "abf-139"),
        # 后缀清理
        ("ABF-139-C.mp4",                       "abf-139"),
        ("ABF-139-C_[4K].mp4",                  "abf-139"),
        # v1.4.4: 序列文件返回基础番号 (不返回 rbd-011a，避免按 a/b 单独搜索)
        ("RBD011a.mp4",                         "rbd-011"),
        ("169bbs.com@RBD011a.mp4",              "rbd-011"),
    ])
    def test_clean(self, inp, expected):
        assert clean_filename_for_search(inp) == expected

    def test_empty(self):
        assert clean_filename_for_search("") == ""


# =========================================================================
# sanitize_filename — 最终文件名清理（核心修复场景）
# =========================================================================

class TestSanitizeFilename:
    """v1.4.4 修复的最终命名场景。修复前文件整理后名前仍有网站前缀。"""

    @pytest.mark.parametrize("inp,expected", [
        # ---- 修复前 100% 漏掉的场景 ----
        ("4k2.com@ABF-139-C.mp4",                "ABF-139-C.mp4"),
        ("hhd800.com@SONE-753-C_[4K].mp4",       "SONE-753-C_[4K].mp4"),
        ("javbus.com@START321.mp4",              "START321.mp4"),
        ("[javbus] (javbus) javbus - ABF-139.mp4", "ABF-139.mp4"),
        ("ABF-139 javbus.mp4",                   "ABF-139.mp4"),
        ("javbus - START-321.mp4",               "START-321.mp4"),
        # ---- Windows 兼容（保留原行为） ----
        ('ABF-139<>:"/\\|?*.mp4',                "ABF-139_________.mp4"),  # 9 个非法字符
    ])
    def test_sanitize(self, inp, expected):
        assert sanitize_filename(inp) == expected

    @pytest.mark.parametrize("inp", [
        "",
        "   ",
    ])
    def test_empty_returns_unnamed(self, inp):
        assert sanitize_filename(inp) == "unnamed"

    def test_pure_javbus_filename(self):
        """'javbus.mp4' 会被 strip 成 '.mp4' → name 空 → unnamed.mp4
        这是有意行为：宁可改成 unnamed 也不留网站名。
        如果有用户反馈想保留，单独开个开关即可。
        """
        assert sanitize_filename("javbus.mp4") == "unnamed.mp4"


# =========================================================================
# extract_series_info — 序列文件识别（v1.4.4 bug 修复核心 #2）
# =========================================================================

class TestExtractSeriesInfo:
    """v1.4.4 修复：原版正则 ^...$ 要求整个 stem 就是番号，
    导致带完整标题的序列文件（最常见的真实文件名）识别不到。
    """

    @pytest.mark.parametrize("inp,expected_base,expected_seq", [
        # ---- 数字尾段（最常见） ----
        ("ABF-139-1.mp4",                       "ABF-139", "1"),
        ("ABF-139-2.mp4",                       "ABF-139", "2"),
        ("ABF-139-10.mp4",                      "ABF-139", "10"),   # 双位数
        # ---- 字母尾段 ----
        ("ABF-139a.mp4",                        "ABF-139", "1"),
        ("ABF-139b.mp4",                        "ABF-139", "2"),
        # ---- 无连字符 ----
        ("RBD011a.mp4",                         "RBD-011", "1"),
        ("RBD011b.mp4",                         "RBD-011", "2"),
        ("RBD011-1.mp4",                        "RBD-011", "1"),
        # ---- v1.4.4 修复场景：带完整标题 ----
        ("ABF-139-1 美少女 第1話.mp4",            "ABF-139", "1"),
        ("ABF-139-2 美少女 第2話.mp4",            "ABF-139", "2"),
        ("ABF-139-3 美少女 第3話.mp4",            "ABF-139", "3"),
        ("ABF-139-10 美少女.mp4",                "ABF-139", "10"),
        ("ABF-139a 美少女.mp4",                  "ABF-139", "1"),
        # ---- v1.4.4 修复场景：下载站前缀 ----
        ("4k2.com@ABF-139-1 美少女.mp4",         "ABF-139", "1"),
        ("4k2.com@ABF-139-2 美少女.mp4",         "ABF-139", "2"),
        ("javbus.com@ABF-139-1 美少女.mp4",      "ABF-139", "1"),
        ("javbus.com@ABF-139-2 美少女.mp4",      "ABF-139", "2"),
    ])
    def test_series_detected(self, inp, expected_base, expected_seq):
        base, seq = extract_series_info(inp)
        assert base == expected_base
        assert seq == expected_seq

    @pytest.mark.parametrize("inp", [
        "ABF-139.mp4",                    # 非序列
        "random-file.mp4",
        "",
        "no-extension",                   # 无点号
    ])
    def test_not_a_series(self, inp):
        base, seq = extract_series_info(inp)
        assert base is None
        assert seq is None


class TestCleanFilenameForSearchSeries:
    """v1.4.4 修复：clean_filename_for_search 在能识别序列时返回基础番号，
    而不是带 -1/-2/-a 的完整词 — 避免每集搜索到不同结果。
    """

    @pytest.mark.parametrize("inp,expected", [
        # 序列文件：返回基础番号
        ("ABF-139-1 美少女 第1話.mp4",        "abf-139"),
        ("ABF-139-2 美少女 第2話.mp4",        "abf-139"),
        ("ABF-139-10 美少女.mp4",             "abf-139"),
        ("ABF-139a 美少女.mp4",               "abf-139"),
        ("RBD011a 美少女.mp4",                "rbd-011"),
        ("4k2.com@ABF-139-1 美少女.mp4",     "abf-139"),
        # 非序列文件：走 extract_code_from_text
        ("ABF-139 美少女.mp4",                "abf-139"),
        ("ABF-139.mp4",                       "abf-139"),
    ])
    def test_search_term(self, inp, expected):
        assert clean_filename_for_search(inp) == expected


class TestDetectSeriesFiles:
    """端到端验证 detect_series_files 的分组结果"""

    def test_pure_series(self):
        from filename_utils import extract_series_info  # noqa
        # 通过 JavFileOrganizer 的实例方法走完整路径
        import sys
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import jav_file_organizer as jfo_mod
        obj = jfo_mod.JavFileOrganizer.__new__(jfo_mod.JavFileOrganizer)
        obj.log = lambda *a, **kw: None

        files = ['ABF-139-1.mp4', 'ABF-139-2.mp4', 'ABF-139-3.mp4']
        groups, standalone = obj.detect_series_files(files)
        assert 'ABF-139' in groups
        assert len(groups['ABF-139']) == 3
        assert standalone == []

    def test_series_with_full_title(self):
        """用户报告的 bug 场景：带完整标题的序列文件必须被识别成组"""
        import jav_file_organizer as jfo_mod
        obj = jfo_mod.JavFileOrganizer.__new__(jfo_mod.JavFileOrganizer)
        obj.log = lambda *a, **kw: None

        files = [
            'ABF-139-1 美少女 第1話.mp4',
            'ABF-139-2 美少女 第2話.mp4',
            'ABF-139-3 美少女 第3話.mp4',
        ]
        groups, standalone = obj.detect_series_files(files)
        assert 'ABF-139' in groups, f"期望识别成序列组，实际 groups={groups}, standalone={standalone}"
        assert len(groups['ABF-139']) == 3

    def test_mixed_series_and_standalone(self):
        import jav_file_organizer as jfo_mod
        obj = jfo_mod.JavFileOrganizer.__new__(jfo_mod.JavFileOrganizer)
        obj.log = lambda *a, **kw: None

        files = [
            'ABF-139-1 美少女.mp4',
            'ABF-139-2 美少女.mp4',
            'SONE-753 美少女.mp4',  # 独立文件
        ]
        groups, standalone = obj.detect_series_files(files)
        assert 'ABF-139' in groups
        assert 'SONE-753 美少女.mp4' in standalone

    def test_download_site_prefix_with_series(self):
        """下载站前缀 + 完整标题 + 序列号 — 最棘手的组合"""
        import jav_file_organizer as jfo_mod
        obj = jfo_mod.JavFileOrganizer.__new__(jfo_mod.JavFileOrganizer)
        obj.log = lambda *a, **kw: None

        files = [
            '4k2.com@ABF-139-1 美少女.mp4',
            '4k2.com@ABF-139-2 美少女.mp4',
        ]
        groups, standalone = obj.detect_series_files(files)
        assert 'ABF-139' in groups, f"期望识别成序列组，实际 groups={groups}, standalone={standalone}"


