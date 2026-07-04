#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_baseline_tests.py
=====================

一键回归测试入口，覆盖当前 v1.5.0-Selenium 基线的核心能力：

- 纯函数/文件名规则（pytest）
- JAVLibrary 解析层（pytest）
- 序列文件端到端（本地、无网络）
- 修复前 vs 修复后 对比
- 可选：JavHoo 真实网络测试

用法：
    python run_baseline_tests.py
    python run_baseline_tests.py --include-live-network

说明：
- 默认不跑 live-network，保证稳定可重复
- live-network 仅用于人工验证外站当前可达性，不应作为 CI 阻塞项
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PY = sys.executable


def run_step(name: str, cmd: list[str], *, allow_failure: bool = False) -> tuple[bool, str]:
    print("\n" + "=" * 78)
    print(f"[TEST] {name}")
    print("=" * 78)
    print("$", " ".join(cmd))
    p = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
    if p.stdout:
        print(p.stdout.rstrip())
    if p.stderr:
        print("--- stderr ---")
        print(p.stderr.rstrip())

    ok = p.returncode == 0 or allow_failure
    print(f"=> exit={p.returncode} {'OK' if ok else 'FAIL'}")
    return ok, f"{name}: exit={p.returncode}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--include-live-network', action='store_true', help='包含 test_javhoo_live.py')
    args = parser.parse_args()

    steps: list[tuple[str, list[str], bool]] = [
        (
            'Pure utility regression (pytest)',
            [PY, '-m', 'pytest', 'test_filename_utils.py', 'test_javlibrary_parser.py', 'test_batch_filters.py', 'test_manifest_utils.py', 'test_provider_router.py', 'test_dry_run.py', 'test_series_atomic.py', 'test_workflow_service.py', '-q'],
            False,
        ),
        (
            'Series e2e regression (local)',
            [PY, 'test_e2e_series_e2e.py'],
            False,
        ),
        (
            'Before/after comparison regression',
            [PY, 'test_before_after.py'],
            False,
        ),
        (
            'GUI worker walkthrough (mocked, no network)',
            [PY, 'test_gui_walkthrough.py'],
            False,
        ),
    ]

    if args.include_live_network:
        steps.append(
            (
                'JavHoo live-network smoke',
                [PY, 'test_javhoo_live.py'],
                True,
            )
        )

    summary = []
    failed = 0
    for name, cmd, allow_failure in steps:
        ok, line = run_step(name, cmd, allow_failure=allow_failure)
        summary.append((name, ok, allow_failure))
        if not ok:
            failed += 1

    print("\n" + "#" * 78)
    print("# SUMMARY")
    print("#" * 78)
    for name, ok, allow_failure in summary:
        if ok and allow_failure:
            status = 'PASS (non-blocking)'
        elif ok:
            status = 'PASS'
        else:
            status = 'FAIL'
        print(f"- {name}: {status}")

    print(f"\nBlocking failures: {failed}")
    return 1 if failed else 0


if __name__ == '__main__':
    os.chdir(ROOT)
    raise SystemExit(main())
