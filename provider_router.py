#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Simple provider router for mixed-source video filenames."""
from __future__ import annotations

import re

AUTO_ALL = 'auto_all'
AUTO_CENSORED = 'auto_censored'
AUTO_UNCENSORED = 'auto_uncensored'
AUTO_PROVIDER_STRATEGIES = {AUTO_ALL, AUTO_CENSORED, AUTO_UNCENSORED}

JAV_GENERAL_PROVIDERS = {'javbus', 'javhoo', 'javlibrary', 'bestjavporn'}

NON_JAV_GENERAL_MARKERS = {
    'carib', '1pon', 'nyoshin', '10musume', 'pacopacomama', 'muramura',
    '300mium', '393otim', '420hpt', '420sth', '546erofv', '583erkr', '328cnstv',
    '328hmdnv', '476mla', '253kaku', '292my', '413instv', 'dpvr', 'fc2',
    'tokyo-hot', 'heyzo', 'heydouga', 'japanhdv', 'urabukkake',
}

GENERAL_JAV_CODE = re.compile(r'^[a-z]{2,10}-\d{2,6}$', re.IGNORECASE)
ANIME_RELEASE_NAME = re.compile(
    r'^\[[^\]]+\]\s+.+?\s+-\s+\d{1,4}\s+(?:\[[^\]]+\]\s*)+\.(?:mkv|mp4|avi|mov)$',
    re.IGNORECASE,
)


def route_provider(preferred_provider: str, filename: str, search_query: str) -> dict:
    normalized_filename = (filename or '').lower()
    normalized_query = (search_query or '').lower()

    if normalized_filename.startswith('._') or normalized_filename.startswith('.'):
        return {
            'action': 'skip',
            'provider': None,
            'reason': 'hidden-file',
        }

    if ANIME_RELEASE_NAME.match(filename or ''):
        return {
            'action': 'skip',
            'provider': None,
            'reason': 'non-jav-anime-release',
        }

    matched_marker = None
    for marker in sorted(NON_JAV_GENERAL_MARKERS):
        if marker in normalized_filename or marker in normalized_query:
            matched_marker = marker
            break

    if preferred_provider == AUTO_ALL:
        if matched_marker:
            candidates = ['uncensored']
            reason = f'auto-all-marker:{matched_marker}'
        else:
            # 有码优先；前两个详细源均失败时，最后交给无码源判断。
            candidates = ['javbus', 'javhoo', 'uncensored']
            reason = (
                'auto-all-general-priority'
                if GENERAL_JAV_CODE.fullmatch(normalized_query)
                else 'auto-all-ambiguous-priority'
            )
    elif preferred_provider == AUTO_CENSORED:
        candidates = ['javbus', 'javhoo']
        reason = 'auto-censored-priority'
    elif preferred_provider == AUTO_UNCENSORED:
        candidates = ['uncensored']
        reason = f'auto-uncensored{":" + matched_marker if matched_marker else ""}'
    else:
        # 详细源是用户的明确选择，不再被文件名规则偷偷改成其他来源。
        candidates = [preferred_provider]
        reason = 'specified-provider'

    provider = candidates[0]
    auto_routed = preferred_provider in AUTO_PROVIDER_STRATEGIES

    return {
        'action': 'process',
        'provider': provider,
        'candidates': candidates,
        'reason': reason,
        'warning_only': False,
        'auto_routed': auto_routed,
    }
