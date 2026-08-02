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


def test_anime_release_group_filename_should_skip_as_non_jav_media():
    decision = route_provider(
        'auto_all',
        '[Erai-raws] Ousama Ranking - 07 [v0][1080p][Multiple Subtitle][815C2038].mkv',
        'erai-raws',
    )

    assert decision['action'] == 'skip'
    assert decision['reason'] == 'non-jav-anime-release'


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


def test_mgstage_code_auto_routes_to_exact_censored_source_chain():
    decision = route_provider('auto_all', '300MIUM-1366.mp4', '300mium-1366')

    assert decision['provider'] == 'libredmm'
    assert decision['candidates'] == ['libredmm', 'mgstage']
    assert decision['reason'] == 'auto-all-mgstage:300mium'


def test_full_auto_routes_fc2_and_tokyo_hot_to_uncensored():
    for filename, query, marker in (
        ('fc2ppv_2386297.mp4', 'fc2-ppv-2386297', 'fc2'),
        ('n0904.mkv', 'tokyo-hot-n0904', 'tokyo-hot'),
    ):
        decision = route_provider('auto_all', filename, query)

        assert decision['provider'] == 'uncensored'
        assert decision['reason'] == f'auto-all-marker:{marker}'


def test_full_auto_routes_fc2_ppt_typo_to_uncensored():
    decision = route_provider('auto_all', 'FC2-PPT-2386297.mp4', 'fc2-ppv-2386297')

    assert decision['provider'] == 'uncensored'
    assert decision['candidates'] == ['uncensored']


def test_madou_codes_use_exact_madou_source_without_censored_source_roundtrip():
    for strategy in ('auto_all', 'auto_uncensored'):
        decision = route_provider(strategy, 'MDHG-0020.mp4', 'mdhg-0020')

        assert decision['provider'] == 'madouqu'
        assert decision['candidates'] == ['madouqu']
        assert 'madou-exact-code' in decision['reason']


def test_full_auto_routes_art_context_to_artvideo_before_generic_sources():
    decision = route_provider(
        'auto_all',
        '1754 淫乱美麗奴倶楽部.wmv',
        'ART VIDEO 1754 淫乱美麗奴倶楽部',
    )

    assert decision['provider'] == 'artvideo'
    assert decision['candidates'] == ['artvideo']
    assert decision['reason'] == 'auto-all-art-video'


def test_full_auto_routes_night24_to_safe_recognizer_instead_of_generic_sources():
    decision = route_provider('auto_all', '1216.mp4', 'DMS-NIGHT24-1216')

    assert decision['provider'] == 'uncensored'
    assert decision['candidates'] == ['uncensored']
    assert decision['reason'] == 'auto-all-marker:night24'


def test_full_auto_routes_413instv_to_exact_mgstage_chain():
    decision = route_provider('auto_all', '413INSTV-721.mp4', '413instv-721')

    assert decision['provider'] == 'libredmm'
    assert decision['candidates'] == ['libredmm', 'mgstage']
    assert decision['reason'] == 'auto-all-mgstage:413instv'


def test_gana_uses_exact_mgstage_chain_in_full_auto_and_auto_censored():
    for strategy in ('auto_all', 'auto_censored'):
        decision = route_provider(strategy, 'GANA-3218.mp4', 'gana-3218')

        assert decision['provider'] == 'libredmm'
        assert decision['candidates'] == ['libredmm', 'mgstage']
        assert decision['reason'] == f'{strategy.replace("_", "-")}-mgstage:gana'


def test_200gana_source_code_uses_same_exact_mgstage_chain():
    decision = route_provider('auto_all', '200GANA-3218.mp4', 'gana-3218')

    assert decision['provider'] == 'libredmm'
    assert decision['candidates'] == ['libredmm', 'mgstage']


def test_specified_uncensored_does_not_switch_for_general_code():
    decision = route_provider('uncensored', 'STARS-239_Uncen.mp4', 'stars-239')

    assert decision['provider'] == 'uncensored'
    assert decision['reason'] == 'specified-provider'
    assert decision['auto_routed'] is False


def test_full_auto_general_priority_keeps_censored_sources_before_uncensored():
    decision = route_provider('auto_all', 'STARS-239.mp4', 'stars-239')

    assert decision['provider'] == 'javbus'
    assert decision['candidates'] == [
        'javbus', 'javhoo', 'libredmm', 'r18dev', 'uncensored'
    ]


def test_auto_censored_and_auto_uncensored_have_separate_candidate_chains():
    censored = route_provider('auto_censored', 'ABF-139.mp4', 'abf-139')
    uncensored = route_provider('auto_uncensored', 'ABF-139.mp4', 'abf-139')

    assert censored['candidates'] == ['javbus', 'javhoo', 'libredmm', 'r18dev']
    assert uncensored['candidates'] == ['uncensored']


def test_r18dev_can_still_be_selected_explicitly():
    decision = route_provider('r18dev', 'RBD-353.mp4', 'rbd-353')

    assert decision['candidates'] == ['r18dev']
    assert decision['reason'] == 'specified-provider'
