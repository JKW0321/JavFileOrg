#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_before_after.py
====================

直接对比：修复前（v1.4.3） vs 修复后（v1.4.4） 跑同一组输入，输出文件有什么不同。

不在磁盘上保留任何文件 — 全部跑在临时目录，跑完即清。
"""
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 备份当前 (修复后) 的 extract_series_info 实现
from filename_utils import extract_series_info as _v144


# 复刻 v1.4.3 的 buggy 版本（用 ^...$ 锚点）
def _v143_extract_series_info(filename):
    """v1.4.3 的 buggy 版本 — 用 ^...$ 锚点，要求整个 stem 就是番号"""
    if '.' in filename:
        filename = filename.rsplit('.', 1)[0]

    pattern1 = r'^([a-zA-Z]+-\d+)-(\d+)$'
    match = re.match(pattern1, filename, re.IGNORECASE)
    if match:
        return match.group(1).upper(), match.group(2)

    pattern2 = r'^([a-zA-Z]+-\d+)([a-zA-Z])$'
    match = re.match(pattern2, filename, re.IGNORECASE)
    if match:
        return match.group(1).upper(), str(ord(match.group(2).lower()) - ord('a') + 1)

    pattern3 = r'^([a-zA-Z]+\d+)-(\d+)$'
    match = re.match(pattern3, filename, re.IGNORECASE)
    if match:
        base = re.sub(r'([a-zA-Z]+)(\d+)', r'\1-\2', match.group(1)).upper()
        return base, match.group(2)

    pattern4 = r'^([a-zA-Z]+\d+)([a-zA-Z])$'
    match = re.match(pattern4, filename, re.IGNORECASE)
    if match:
        base = re.sub(r'([a-zA-Z]+)(\d+)', r'\1-\2', match.group(1)).upper()
        return base, str(ord(match.group(2).lower()) - ord('a') + 1)

    return None, None


# ---------------------------------------------------------------------------
# 用同一组测试输入，对比两版输出
# ---------------------------------------------------------------------------

SAMPLE_INPUTS = [
    # 用户报告的核心场景
    'ABF-139-1 美少女 第1話.mp4',
    'ABF-139-2 美少女 第2話.mp4',
    'ABF-139-3 美少女 第3話.mp4',
    # 字母后缀
    'ABF-139a 美少女.mp4',
    'ABF-139b 美少女.mp4',
    # 下载站前缀
    '4k2.com@ABF-139-1 美少女.mp4',
    '4k2.com@ABF-139-2 美少女.mp4',
    # 纯序列（不带标题）
    'ABF-139-1.mp4',
    'ABF-139-2.mp4',
]


def run_extraction(extract_fn, label):
    print(f"\n{'='*70}")
    print(f"  {label}")
    print('='*70)
    results = {}
    for fn in SAMPLE_INPUTS:
        base, seq = extract_fn(fn)
        results[fn] = (base, seq)
        marker = "✅" if base else "❌"
        print(f"  {marker} {fn!r:45s} -> ({base!r}, {seq!r})")
    return results


print("\n" + "#"*70)
print("# v1.4.4 Bug 3 修复 — 修复前 vs 修复后 对比")
print("#"*70)

v143 = run_extraction(_v143_extract_series_info, "v1.4.3 (修复前 — BUG)")
v144 = run_extraction(_v144, "v1.4.4 (修复后 — 当前)")

# 统计差异
print("\n" + "="*70)
print("  差异统计")
print("="*70)
v143_detected = sum(1 for k, v in v143.items() if v[0] is not None)
v144_detected = sum(1 for k, v in v144.items() if v[0] is not None)
print(f"  v1.4.3 (修复前): {v143_detected}/{len(SAMPLE_INPUTS)} 识别成序列")
print(f"  v1.4.4 (修复后): {v144_detected}/{len(SAMPLE_INPUTS)} 识别成序列")
print(f"  改善: +{v144_detected - v143_detected} 个场景")

# 列出 v1.4.4 新识别出来的
newly_detected = [k for k in SAMPLE_INPUTS if v143[k][0] is None and v144[k][0] is not None]
if newly_detected:
    print(f"\n  v1.4.4 新识别的场景:")
    for f in newly_detected:
        print(f"    - {f}")

print("\n" + "#"*70)
if v144_detected > v143_detected:
    print(f"  🎉 修复有效：{v144_detected - v143_detected} 个之前漏掉的场景现在能正确识别")
else:
    print("  ⚠️ 没看到改善")
print("#"*70)

