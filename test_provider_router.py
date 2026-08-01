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


def test_full_auto_routes_carib_like_code_to_uncensored_provider():
    decision = route_provider('auto_all', '032226-001-CARIB.mp4', '032226-001-carib')
    assert decision['action'] == 'process'
    assert decision['provider'] == 'uncensored'
    assert decision['candidates'] == ['uncensored']
    assert decision['reason'].startswith('auto-all-marker:')


def test_specified_javbus_does_not_switch_for_uncensored_marker():
    decision = route_provider('javbus', '420STH-123.mp4', '420sth-123')
    assert decision['action'] == 'process'
    assert decision['provider'] == 'javbus'
    assert decision['candidates'] == ['javbus']
    assert decision['reason'] == 'specified-provider'


def test_1pon_like_code_auto_routes_to_uncensored_provider():
    decision = route_provider('auto_all', '031726_001-1PON.mp4', '031726_001-1pon')
    assert decision['provider'] == 'uncensored'


def test_siro_like_code_auto_routes_to_uncensored_provider():
    decision = route_provider('auto_all', '300MIUM-1366.mp4', '300mium-1366')
    assert decision['provider'] == 'uncensored'


def test_full_auto_routes_fc2_tokyo_hot_and_413instv_to_uncensored():
    for filename, query, marker in (
        ('fc2ppv_2386297.mp4', 'fc2-ppv-2386297', 'fc2'),
        ('n0904.mkv', 'tokyo-hot-n0904', 'tokyo-hot'),
        ('413INSTV-721.mp4', '413instv-721', '413instv'),
    ):
        decision = route_provider('auto_all', filename, query)

        assert decision['provider'] == 'uncensored'
        assert decision['reason'] == f'auto-all-marker:{marker}'


def test_specified_uncensored_does_not_switch_for_general_code():
    decision = route_provider('uncensored', 'STARS-239_Uncen.mp4', 'stars-239')

    assert decision['provider'] == 'uncensored'
    assert decision['reason'] == 'specified-provider'
    assert decision['auto_routed'] is False


def test_full_auto_general_priority_is_javbus_then_javhoo_then_uncensored():
    decision = route_provider('auto_all', 'STARS-239.mp4', 'stars-239')

    assert decision['provider'] == 'javbus'
    assert decision['candidates'] == ['javbus', 'javhoo', 'uncensored']


def test_auto_censored_and_auto_uncensored_have_separate_candidate_chains():
    censored = route_provider('auto_censored', 'ABF-139.mp4', 'abf-139')
    uncensored = route_provider('auto_uncensored', 'ABF-139.mp4', 'abf-139')

    assert censored['candidates'] == ['javbus', 'javhoo']
    assert uncensored['candidates'] == ['uncensored']
