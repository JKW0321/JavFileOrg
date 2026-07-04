#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_provider_router.py
=======================

provider routing 基础测试。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from provider_router import route_provider


def test_hidden_file_should_skip():
    decision = route_provider('javlibrary', '._ABF-123.mp4', 'abf-123')
    assert decision['action'] == 'skip'
    assert decision['reason'] == 'hidden-file'


def test_standard_jav_code_keeps_javlibrary():
    decision = route_provider('javlibrary', 'SDAB-351.mp4', 'sdab-351')
    assert decision['action'] == 'process'
    assert decision['provider'] == 'javlibrary'


def test_carib_like_code_warns_but_keeps_manual_provider():
    decision = route_provider('javlibrary', '032226-001-CARIB.mp4', '032226-001-carib')
    assert decision['action'] == 'process'
    assert decision['provider'] == 'javlibrary'
    assert decision['reason'].startswith('marker:')
    assert decision['warning_only'] is True


def test_1pon_like_code_warns_but_keeps_manual_provider():
    decision = route_provider('javlibrary', '031726_001-1PON.mp4', '031726_001-1pon')
    assert decision['provider'] == 'javlibrary'
    assert decision['warning_only'] is True


def test_siro_like_code_warns_but_keeps_manual_provider():
    decision = route_provider('javlibrary', '300MIUM-1366.mp4', '300mium-1366')
    assert decision['provider'] == 'javlibrary'
    assert decision['warning_only'] is True
