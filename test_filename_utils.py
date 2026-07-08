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
    analyze_unknown_filename,
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


class TestAdaptiveFilenameRules:
    def test_fc2_ppv_candidate_is_auto_usable(self):
        candidate = analyze_unknown_filename("FC2-PPV-1234567.mp4")

        assert candidate['rule_id'] == 'fc2_ppv'
        assert candidate['normalized_code'] == 'FC2-PPV-1234567'
        assert candidate['usable_for_search'] is True
        assert clean_filename_for_search("FC2-PPV-1234567.mp4") == "fc2-ppv-1234567"

    def test_fc2_ppv_series_candidate(self):
        base, seq = extract_series_info("FC2-PPV-1234567-2.mp4")

        assert base == "FC2-PPV-1234567"
        assert seq == "2"

    def test_known_multi_segment_candidate_is_auto_usable(self):
        candidate = analyze_unknown_filename("1pondo-010123_001.mp4")

        assert candidate['rule_id'] == 'known_multi_segment'
        assert candidate['normalized_code'] == '1PONDO-010123-001'
        assert candidate['usable_for_search'] is True
        assert clean_filename_for_search("1pondo-010123_001.mp4") == "1pondo-010123-001"

    def test_10musume_single_digit_part_is_auto_usable(self):
        candidate = analyze_unknown_filename("10Musume-041619_1 素人AV面接.mp4")

        assert candidate['rule_id'] == 'known_multi_segment'
        assert candidate['normalized_code'] == '10MUSUME-041619-1'
        assert candidate['usable_for_search'] is True
        assert clean_filename_for_search("10Musume-041619_1 素人AV面接.mp4") == "10musume-041619-1"

    def test_pacopacomama_candidate_is_auto_usable(self):
        candidate = analyze_unknown_filename("Pacopacomama-032819_059 熟女.mp4")

        assert candidate['rule_id'] == 'known_multi_segment'
        assert candidate['normalized_code'] == 'PACOPACOMAMA-032819-059'
        assert candidate['usable_for_search'] is True
        assert clean_filename_for_search("Pacopacomama-032819_059 熟女.mp4") == "pacopacomama-032819-059"

    def test_caribbeancom_suffix_candidate_is_auto_usable(self):
        candidate = analyze_unknown_filename("032226-001-CARIB.mp4")

        assert candidate['rule_id'] == 'carib_suffix'
        assert candidate['normalized_code'] == 'CARIB-032226-001'
        assert candidate['usable_for_search'] is True
        assert clean_filename_for_search("032226-001-CARIB.mp4") == "carib-032226-001"

    def test_1pondo_suffix_candidate_is_auto_usable(self):
        candidate = analyze_unknown_filename("032126_001-1PON.mp4")

        assert candidate['rule_id'] == '1pondo_suffix'
        assert candidate['normalized_code'] == '1PONDO-032126-001'
        assert candidate['usable_for_search'] is True
        assert clean_filename_for_search("032126_001-1PON.mp4") == "1pondo-032126-001"

    def test_heyzo_candidate_is_auto_usable(self):
        candidate = analyze_unknown_filename("HEYZO-HD-3098.mp4")

        assert candidate['rule_id'] == 'heyzo'
        assert candidate['normalized_code'] == 'HEYZO-3098'
        assert candidate['usable_for_search'] is True
        assert clean_filename_for_search("HEYZO-HD-3098.mp4") == "heyzo-3098"

    def test_tokyo_hot_candidate_is_auto_usable(self):
        candidate = analyze_unknown_filename("Tokyo-Hot-n0839.mp4")

        assert candidate['rule_id'] == 'tokyo_hot'
        assert candidate['normalized_code'] == 'TOKYO-HOT-N0839'
        assert candidate['usable_for_search'] is True
        assert clean_filename_for_search("Tokyo-Hot-n0839.mp4") == "tokyo-hot-n0839"

    def test_mgstage_uncensored_candidate_is_auto_usable(self):
        candidate = analyze_unknown_filename("300MIUM-1366.mp4")

        assert candidate['rule_id'] == 'mgstage_uncensored'
        assert candidate['normalized_code'] == '300MIUM-1366'
        assert candidate['usable_for_search'] is True
        assert clean_filename_for_search("300MIUM-1366.mp4") == "300mium-1366"

    def test_japanhdv_candidate_is_auto_usable(self):
        candidate = analyze_unknown_filename("japanhdv.17.09.24.maya.sawamura.mp4")

        assert candidate['rule_id'] == 'japanhdv'
        assert candidate['normalized_code'] == 'JAPANHDV-170924-MAYA-SAWAMURA'
        assert candidate['usable_for_search'] is True
        assert clean_filename_for_search("japanhdv.17.09.24.maya.sawamura.mp4") == "japanhdv-170924-maya-sawamura"

    def test_urabukkake_candidate_is_auto_usable(self):
        candidate = analyze_unknown_filename("urabukkake-116 2016-05-08 KanameAss.mp4")

        assert candidate['rule_id'] == 'urabukkake'
        assert candidate['normalized_code'] == 'URABUKKAKE-116-KANAMEASS'
        assert candidate['usable_for_search'] is True
        assert clean_filename_for_search("urabukkake-116 2016-05-08 KanameAss.mp4") == "urabukkake-116-kanameass"

    def test_s_cute_candidate_keeps_base_and_sequence(self):
        candidate = analyze_unknown_filename("s-cute-593_maria_04.mp4")

        assert candidate['rule_id'] == 's_cute'
        assert candidate['normalized_code'] == 'S-CUTE-593-MARIA'
        assert candidate['sequence'] == '04'
        assert candidate['usable_for_search'] is True
        assert clean_filename_for_search("s-cute-593_maria_04.mp4") == "s-cute-593-maria"

    def test_night24_candidate_can_use_parent_path_context(self):
        candidate = analyze_unknown_filename("DMS Night24 013 (5013) 高田弘美/013.avi")

        assert candidate['rule_id'] == 'night24_dms'
        assert candidate['normalized_code'] == 'DMS-NIGHT24-013'
        assert candidate['usable_for_search'] is True
        assert clean_filename_for_search("DMS Night24 013 (5013) 高田弘美/013.avi") == "dms-night24-013"

    def test_mesubuta_candidate_is_auto_usable(self):
        candidate = analyze_unknown_filename("mesubuta_120111_466_01-HD.wmv")

        assert candidate['rule_id'] == 'mesubuta'
        assert candidate['normalized_code'] == 'MESUBUTA-120111-466'
        assert candidate['sequence'] == '01'
        assert candidate['usable_for_search'] is True
        assert clean_filename_for_search("mesubuta_120111_466_01-HD.wmv") == "mesubuta-120111-466"

    def test_heydouga_candidate_is_auto_usable(self):
        candidate = analyze_unknown_filename("heydouga-4030-1644.mp4")

        assert candidate['rule_id'] == 'heydouga'
        assert candidate['normalized_code'] == 'HEYDOUGA-4030-1644'
        assert candidate['usable_for_search'] is True
        assert clean_filename_for_search("heydouga-4030-1644.mp4") == "heydouga-4030-1644"

    def test_generic_multi_segment_candidate_needs_review(self):
        candidate = analyze_unknown_filename("STUDIOX-20260705-001.mp4")

        assert candidate['rule_id'] == 'generic_multi_segment'
        assert candidate['normalized_code'] == 'STUDIOX-20260705-001'
        assert candidate['usable_for_search'] is False
        assert clean_filename_for_search("STUDIOX-20260705-001.mp4") == ""

    def test_standard_rule_does_not_create_candidate(self):
        assert analyze_unknown_filename("ABF-139.mp4") is None

    def test_quality_suffix_name_is_not_treated_as_series_code(self):
        assert extract_series_info("337-AyaKomatsu-2160p.mp4") == (None, None)
        assert extract_code_from_text("337-AyaKomatsu-2160p.mp4") is None


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
        ("MIRD-277_3.mp4",                      "MIRD-277", "3"),
        ("MIRD_277_3.mp4",                      "MIRD-277", "3"),
        # ---- 字母尾段 ----
        ("ABF-139a.mp4",                        "ABF-139", "1"),
        ("ABF-139b.mp4",                        "ABF-139", "2"),
        # ---- 无连字符 ----
        ("RBD011a.mp4",                         "RBD-011", "1"),
        ("RBD011b.mp4",                         "RBD-011", "2"),
        ("RBD011-1.mp4",                        "RBD-011", "1"),
        ("RBD011_3.mp4",                        "RBD-011", "3"),
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
        ("MIRD-277_3.mp4",                    "mird-277"),
        ("MIRD_277_3.mp4",                    "mird-277"),
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
