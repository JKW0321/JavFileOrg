#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
filename_utils.py
=================

v1.4.4: 从 jav_file_organizer.py 拆出的纯函数工具集。

设计原则：
- 所有函数都是 **模块级纯函数**，不带 self、不依赖 tkinter、不打日志
- 主程序保留同名方法作为 thin wrapper（方便 self.log() 记录 + AtomicProcessor 传引用）
- 这样以后改清理规则只改这一处，GUI 主程序零修改

暴露的纯函数：
- strip_site_markers(name)         移除所有形态的网站名前缀/水印
- extract_code_from_text(filename) 从完整标题中提取番号
- clean_filename_for_search(name)  生成搜索词
- sanitize_filename(name)          生成最终文件名
"""

import os
import re

__all__ = [
    'strip_site_markers',
    'extract_code_from_text',
    'clean_filename_for_search',
    'sanitize_filename',
    'extract_series_info',
    'analyze_unknown_filename',
]


# ---------------------------------------------------------------------------
# v1.4.4 新增：统一的网站名清理函数
# ---------------------------------------------------------------------------

# 这些是已知的"良性"片段，允许在 strip 后保留（避免误伤）。
# 例如 "javscript" 含 "jav" 但跟 javbus 无关 → 靠单词边界匹配避开
_SITE_NAMES = ('javbus', 'javhoo')

# 下载站前缀模式：4k2.com@, hhd800.com@, 169bbs.com@, javbus.com@, some-site.org@ 等
# 匹配规则：开头、至少一个 . 或 - 分隔的字母数字段、紧跟 @
_DOWNLOAD_SITE_PREFIX = re.compile(r'^[\w][\w.-]*@')


def strip_site_markers(name: str) -> str:
    """移除文件名中的所有网站名痕迹（下载站前缀、JavBus/JavHoo 水印等）。

    处理场景（按顺序）：
    1. 下载站前缀: 4k2.com@ / hhd800.com@ / 169bbs.com@ / javbus.com@ / *.org@
    2. 带括号/方括号的站点名: [javbus] / (javbus) / 【javbus】
    3. 带连字符的站点名: javbus - xxx / javbus—xxx
    4. 末尾独立的站点名: xxx javbus
    5. 开头独立的站点名: javbus xxx

    返回清理后的字符串。不修改大小写（交给上层决定）。
    """
    if not name:
        return name

    # 1) 下载站前缀（出现位置几乎都在最前面）
    name = _DOWNLOAD_SITE_PREFIX.sub('', name)

    for site in _SITE_NAMES:
        site_re = re.compile(re.escape(site), re.IGNORECASE)

        # 2) 带方括号/圆括号/【】的: [javbus] / (javbus) / 【javbus】
        name = re.sub(
            r'[\[\(【]\s*' + re.escape(site) + r'\s*[\]\)】]',
            ' ', name, flags=re.IGNORECASE
        )

        # 3) 带连字符的: "javbus - xxx" / "xxx - javbus" / "javbus—xxx"
        name = re.sub(
            r'(^|\s)' + re.escape(site) + r'\s*[-—–]\s*',
            r'\1', name, flags=re.IGNORECASE
        )
        name = re.sub(
            r'\s*[-—–]\s*' + re.escape(site) + r'($|\s|[,.\[\(])',
            r'\1', name, flags=re.IGNORECASE
        )

        # 4) 末尾独立的 javbus / javhoo 单词（前面空格一起吃掉；后面允许 . [ ( 等标点作为边界）
        name = re.sub(
            r'\s+' + re.escape(site) + r'(?=$|\s|[.\[\(\]])',
            '', name, flags=re.IGNORECASE
        )

        # 5) 开头独立的 javbus / javhoo 单词（要求后面必须跟空格，避免误伤 "javbus.mp4" 这类纯 javbus 文件名）
        #    例外：整串只有 javbus/javhoo 时也清掉
        if name.strip().lower() in (s.lower() for s in _SITE_NAMES):
            name = ''
        else:
            name = re.sub(
                r'^' + re.escape(site) + r'(?=\s)',
                '', name, flags=re.IGNORECASE
            )

    # 5) 兜底：清理 @ 前缀之后可能残留的孤立域名片段 (如 ".com" "/www.xxx.com")
    # 但要小心别误伤 "example.com" 出现在番号前 — 1) 已经把整个 prefix 吃掉了，这里通常无残留
    name = re.sub(r'\s+', ' ', name).strip()

    return name


# ---------------------------------------------------------------------------
# 序列文件识别（v1.4.4 修复：从 jav_file_organizer.py 抽出，支持完整标题）
# ---------------------------------------------------------------------------

# 序列模式：
#   模式 0: ABC-123-1, ABC-123-2 (有连字符 + 数字尾段)
#   模式 1: ABC-123a, ABC-123b (有连字符 + 字母尾段)
#   模式 2: ABC123-1, ABC123-2 (无连字符 + 数字尾段)
#   模式 3: ABC123a, ABC123b (无连字符 + 字母尾段)
#
# 注意：v1.4.4 修复：去掉 ^ 和 $ 锚点，用 re.search 匹配整个 stem 的某一段。
# 修复前：'ABF-139-1 美少女 第1話' 完全识别不到序列（因为正则要求整个 stem 就是番号）
# 修复后：能从 stem 中提取 ABC-123 基础番号 + 1 序列号，即使后面还跟完整标题
_SERIES_PATTERNS = [
    # 0: ABC-123-1
    (re.compile(r'\b([a-zA-Z]{2,10}-\d{2,5})-(\d+)\b'), False),
    # 1: ABC-123a
    (re.compile(r'\b([a-zA-Z]{2,10}-\d{2,5})([a-zA-Z])\b'), True),
    # 2: ABC123-1
    (re.compile(r'\b([a-zA-Z]{2,10}\d{2,5})-(\d+)\b'), False),
    # 3: ABC123a
    (re.compile(r'\b([a-zA-Z]{2,10}\d{2,5})([a-zA-Z])\b'), True),
]


def _stem_for_filename_analysis(filename: str) -> str:
    cleaned = strip_site_markers(filename)
    if '.' in cleaned:
        stem = cleaned.rsplit('.', 1)[0]
    else:
        stem = cleaned
    return strip_site_markers(stem).strip()


def _extract_series_info_from_stem(stem: str):
    for pattern, is_alpha_seq in _SERIES_PATTERNS:
        match = pattern.search(stem)
        if match:
            base_raw = match.group(1)
            # 标准化：字母数字之间加连字符 (RBD011 -> RBD-011)
            base_normalized = re.sub(r'([a-zA-Z]+)(\d+)', r'\1-\2', base_raw).upper()

            if is_alpha_seq:
                letter = match.group(2).lower()
                sequence = str(ord(letter) - ord('a') + 1)
            else:
                sequence = match.group(2)

            return base_normalized, sequence
    return None, None


def extract_series_info(filename):
    """从文件名中提取序列文件信息。

    支持格式（输入 → (base, sequence)）：
    - 'ABF-139-1.mp4'                       -> ('ABF-139', '1')
    - 'ABF-139-10.mp4'                      -> ('ABF-139', '10')
    - 'ABF-139a.mp4'                        -> ('ABF-139', '1')
    - 'RBD011a.mp4'                         -> ('RBD-011', '1')    无连字符自动加
    - 'ABF-139-1 美少女 第1話.mp4'           -> ('ABF-139', '1')   v1.4.4: 支持完整标题
    - 'ABF-139-1 美少女.mp4'                 -> ('ABF-139', '1')   v1.4.4
    - '4k2.com@ABF-139-1 美少女.mp4'        -> ('ABF-139', '1')   v1.4.4: 支持下载站前缀
    - 'ABF-139.mp4'                         -> (None, None)       非序列文件
    - 'random.mp4'                          -> (None, None)

    返回: (base_code, sequence_str) 或 (None, None)
    """
    if not filename:
        return None, None

    # v1.4.4: 先 strip 网站名前缀 (4k2.com@, hhd800.com@ 等含 . 的域名)
    # 再做扩展名处理 — 顺序反了会截错，例如 '4k2.com@ABF-139-1 美少女'
    # 直接 rsplit('.', 1)[0] 会得到 '4k2'。
    stem = _stem_for_filename_analysis(filename)

    base, sequence = _extract_series_info_from_stem(stem)
    if base:
        return base, sequence

    candidate = analyze_unknown_filename(filename)
    if candidate and candidate.get('usable_for_search') and candidate.get('sequence'):
        return candidate.get('normalized_code'), candidate.get('sequence')

    return None, None


# ---------------------------------------------------------------------------
# 番号提取（从 jav_file_organizer.py 抽出）
# ---------------------------------------------------------------------------

# 常见版本后缀清理 (-C, -c, -U, -u, -uc, -UC, -ch, -CH, -AI, -ai)
_SUFFIX_PATTERN = re.compile(r'[-_]?(ch|CH|[cCuU]|uc|UC|ai|AI)$')

# 番号提取的正则模式（按优先级）
_CODE_PATTERNS = [
    # 1. 序列格式: ABC-123-1, SONE-123-2
    r'\b([a-zA-Z]{2,10}[-_]\d{2,5}[-_]\d+)\b',
    # 2. 字母后缀: ABC-123a
    r'\b([a-zA-Z]{2,10}[-_]\d{2,5}[a-zA-Z])\b',
    # 3. 标准格式: ABC-123
    r'\b([a-zA-Z]{2,10}[-_]\d{2,5})\b',
    # 4. 方括号: [ABC-123]
    r'\[([a-zA-Z]{2,10}[-_]\d{2,5}[a-zA-Z]?)\]',
    # 5. 圆括号: (ABC-123)
    r'\(([a-zA-Z]{2,10}[-_]\d{2,5}[a-zA-Z]?)\)',
    # 6. 无连字符: ABC123 (后面跟空格或结尾)
    r'\b([a-zA-Z]{2,10}\d{2,5}[a-zA-Z]?)(?=\s|$)',
]


def _prepare_name_for_code_extract(filename: str) -> str:
    name = os.path.splitext(filename)[0]
    name = strip_site_markers(name)
    name = re.sub(r'_\[4K[}\]]', '', name)
    return _SUFFIX_PATTERN.sub('', name)


def _normalize_extracted_code(code: str) -> str:
    if '-' not in code and '_' not in code:
        code = re.sub(r'([a-zA-Z]+)(\d+)', r'\1-\2', code)
    return code.replace('_', '-').upper()


def _extract_code_from_prepared_name(name: str):
    for pattern in _CODE_PATTERNS:
        match = re.search(pattern, name, re.IGNORECASE)
        if match:
            return _normalize_extracted_code(match.group(1))
    return None


def _candidate(rule_id, filename, normalized_code, *, confidence, usable_for_search,
               reason, sequence=None, pattern_shape=None):
    return {
        'rule_id': rule_id,
        'source_name': os.path.basename(filename) if filename else filename,
        'normalized_code': normalized_code,
        'sequence': sequence,
        'confidence': confidence,
        'usable_for_search': usable_for_search,
        'reason': reason,
        'pattern_shape': pattern_shape or rule_id,
    }


def analyze_unknown_filename(filename: str):
    """分析现有规则未覆盖的文件名，并返回可审计的候选规则。

    返回值是 dict 或 None。高置信候选 (`usable_for_search=True`) 会被
    `extract_code_from_text` / `clean_filename_for_search` 使用；低置信候选只
    用于写入候选规则库，避免把误判带入真实移动/重命名事务。
    """
    if not filename:
        return None

    stem = _stem_for_filename_analysis(filename)
    if not stem:
        return None

    standard_base, _standard_seq = _extract_series_info_from_stem(stem)
    if standard_base:
        return None
    if _extract_code_from_prepared_name(_prepare_name_for_code_extract(filename)):
        return None

    compact = re.sub(r'[\[\]()【】]', ' ', stem)

    fc2 = re.search(
        r'\bFC2[-_\s]*(?:PPV[-_\s]*)?(\d{5,8})(?:[-_\s]+(\d{1,3}))?\b',
        compact,
        re.IGNORECASE,
    )
    if fc2:
        return _candidate(
            'fc2_ppv',
            filename,
            f"FC2-PPV-{fc2.group(1)}",
            sequence=fc2.group(2),
            confidence=0.95,
            usable_for_search=True,
            reason='matched FC2/FC2-PPV numeric code',
            pattern_shape='FC2[-_ ]PPV?[-_ ]<5-8 digits>[-_ ]<optional sequence>',
        )

    tokyo_hot = re.search(
        r'\bTOKYO[-_\s]*HOT[-_\s]*([A-Z]\d{3,6})(?:[-_\s]+(\d{1,3}))?\b',
        compact,
        re.IGNORECASE,
    )
    if tokyo_hot:
        return _candidate(
            'tokyo_hot',
            filename,
            f"TOKYO-HOT-{tokyo_hot.group(1).upper()}",
            sequence=tokyo_hot.group(2),
            confidence=0.93,
            usable_for_search=True,
            reason='matched TOKYO-HOT code',
            pattern_shape='TOKYO[-_ ]HOT[-_ ]<letter+digits>[-_ ]<optional sequence>',
        )

    known_multi = re.search(
        r'\b(1PONDO|10MUSUME|CARIB|CARIBBEANCOM|PACOPACOM)'
        r'[-_\s]+([A-Z]?\d{4,8})[-_\s]+(\d{2,5})(?:[-_\s]+(\d{1,3}))?\b',
        compact,
        re.IGNORECASE,
    )
    if known_multi:
        prefix = known_multi.group(1).upper()
        normalized = f"{prefix}-{known_multi.group(2).upper()}-{known_multi.group(3)}"
        return _candidate(
            'known_multi_segment',
            filename,
            normalized,
            sequence=known_multi.group(4),
            confidence=0.9,
            usable_for_search=True,
            reason='matched known multi-segment code family',
            pattern_shape='<known prefix>[-_ ]<date/id digits>[-_ ]<part digits>[-_ ]<optional sequence>',
        )

    generic = re.search(
        r'\b([A-Z][A-Z0-9]{2,12})[-_\s]+(\d{6,8})[-_\s]+(\d{2,5})\b',
        compact,
        re.IGNORECASE,
    )
    if generic:
        normalized = f"{generic.group(1).upper()}-{generic.group(2)}-{generic.group(3)}"
        return _candidate(
            'generic_multi_segment',
            filename,
            normalized,
            confidence=0.72,
            usable_for_search=False,
            reason='possible multi-segment code, needs confirmation before auto-use',
            pattern_shape='<alpha/alnum prefix>[-_ ]<6-8 digits>[-_ ]<2-5 digits>',
        )

    return None


def extract_code_from_text(filename: str):
    """从文件名中提取番号。返回大写标准格式 (如 'ABF-139')，找不到返回 None。

    支持格式（输入 → 输出）：
    - "ABF-139 美少女.mp4"        -> "ABF-139"
    - "ABF139 标题.mp4"           -> "ABF-139"
    - "[ABF-139] 标题.mp4"        -> "ABF-139"
    - "(ABF-139) 标题.mp4"        -> "ABF-139"
    - "标题 ABF-139.mp4"          -> "ABF-139"
    - "4k2.com@ABF-139 标题.mp4"  -> "ABF-139"   (v1.4.4: 现在走 strip 后能干净提取)
    - "ABF-139-1 标题.mp4"        -> "ABF-139-1"
    - "ABF-139a 标题.mp4"         -> "ABF-139A"
    """
    if not filename:
        return None

    name = _prepare_name_for_code_extract(filename)
    extracted = _extract_code_from_prepared_name(name)
    if extracted:
        return extracted

    candidate = analyze_unknown_filename(filename)
    if candidate and candidate.get('usable_for_search'):
        return candidate.get('normalized_code')

    return None


# ---------------------------------------------------------------------------
# 文件名清理（搜索版 + 最终版）
# ---------------------------------------------------------------------------


def clean_filename_for_search(filename: str) -> str:
    """生成用于搜索的清理后的字符串（小写）。

    流程 (v1.4.4 修复)：
    1. **优先**调用 extract_series_info 识别序列文件 → 命中时返回基础番号
       （修复前：序列号 -1/-2 被当成 search term，导致每集搜索到不同结果、命名错乱）
    2. 否则调用 extract_code_from_text 提取番号
    3. 提取失败时降级到 strip + 移除后缀 + 标准化
    """
    if not filename:
        return ''

    # v1.4.4: 优先识别序列文件，避免 -1/-2/-a 等被错误地编入搜索词
    base, _seq = extract_series_info(filename)
    if base:
        return base.lower()

    # 降级到番号提取
    extracted = extract_code_from_text(filename)
    if extracted:
        return extracted.lower()

    candidate = analyze_unknown_filename(filename)
    if candidate and not candidate.get('usable_for_search'):
        return ''

    # 降级路径
    name = os.path.splitext(filename)[0]
    name = strip_site_markers(name)
    name = re.sub(r'_\[4K[}\]]', '', name)

    # 移除常见后缀 (-ch, -C, -c, -U, -u, -uc, -UC, -AI)
    name = _SUFFIX_PATTERN.sub('', name)

    # 加连字符
    if '-' not in name:
        name = re.sub(r'([a-zA-Z]+)(\d+)', r'\1-\2', name)

    # 清理特殊字符，保留连字符
    name = re.sub(r'[^\w\-\s]', '', name)
    name = re.sub(r'\s+', ' ', name).strip()
    name = re.sub(r'-+', '-', name)

    if ' ' in name:
        name = name.split()[0]

    return name.lower()


def sanitize_filename(filename: str) -> str:
    """生成最终文件名：清理网站名 + 移除 Windows 非法字符 + 长度限制。

    与 clean_filename_for_search 的区别：
    - 不做番号提取（保留原始 title 用于显示）
    - 不强制小写（保留原始大小写）
    - 不移除质量标记 [_4K]（保留画质信息）
    - 做 Windows 兼容性处理
    """
    if not filename or not filename.strip():
        return 'unnamed'

    if '.' in filename:
        name, ext = filename.rsplit('.', 1)
        ext = '.' + ext
    else:
        name, ext = filename, ''

    # v1.4.4: 统一调用 strip_site_markers，覆盖 @ 前缀/[javbus]/javbus - xxx 等所有场景
    name = strip_site_markers(name)
    name = re.sub(r'\s+', ' ', name).strip()

    # Windows 非法字符 → 下划线
    name = re.sub(r'[<>:"/\\|?*]', '_', name)
    # 控制字符
    name = re.sub(r'[\x00-\x1f]', '', name)
    # 末尾空格/点
    name = name.rstrip('. ')

    # Windows 保留字
    reserved = {
        'CON', 'PRN', 'AUX', 'NUL',
        'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
        'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9',
    }
    if name.upper() in reserved:
        name = f"_{name}_"

    if not name or name.strip() == '':
        name = 'unnamed'

    result = name + ext

    # 长度限制（Windows 路径兼容）
    if len(result) > 200:
        max_name_len = 200 - len(ext)
        if max_name_len > 0:
            result = name[:max_name_len] + ext
        else:
            result = name[:200]

    return result
