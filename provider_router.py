#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Simple provider router for mixed-source video filenames."""
from __future__ import annotations

import re

AUTO_ALL = 'auto_all'
AUTO_CENSORED = 'auto_censored'
AUTO_UNCENSORED = 'auto_uncensored'
AUTO_PROVIDER_STRATEGIES = {AUTO_ALL, AUTO_CENSORED, AUTO_UNCENSORED}

JAV_GENERAL_PROVIDERS = {
    'javbus', 'r18dev', 'libredmm', 'javhoo', 'javlibrary', 'bestjavporn'
}

NON_JAV_GENERAL_MARKERS = {
    'carib', '1pon', 'nyoshin', '10musume', 'pacopacomama', 'muramura',
    '300mium', '393otim', '420hpt', '420sth', '546erofv', '583erkr', '328cnstv',
    '328hmdnv', '476mla', '253kaku', '292my', '413instv', 'dpvr', 'fc2',
    'tokyo-hot', 'heyzo', 'heydouga', 'japanhdv', 'urabukkake', 'night24',
    'xxx-av',
}

MADOU_CODE = re.compile(
    r'(?<![a-z0-9])(?:mdhg|mdsr|mdl|md|mm)[-_\s]*\d{1,6}(?!\d)',
    re.IGNORECASE,
)

MGSTAGE_CENSORED_PREFIXES = {
    '300mium', '393otim', '420hpt', '420sth', '546erofv', '583erkr',
    '328cnstv', '328hmdnv', '476mla', '253kaku', '292my', '413instv',
    'gana', '200gana',
}


def _mgstage_prefix(filename: str, search_query: str) -> str | None:
    text = f'{filename or ""} {search_query or ""}'.lower()
    prefixes = '|'.join(
        re.escape(prefix)
        for prefix in sorted(MGSTAGE_CENSORED_PREFIXES, key=len, reverse=True)
    )
    match = re.search(
        rf'(?<![a-z0-9])({prefixes})[-_\s]*\d{{2,6}}(?!\d)',
        text,
        re.IGNORECASE,
    )
    if not match:
        return None
    marker = match.group(1).lower()
    return 'gana' if marker == '200gana' else marker

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

    matched_mgstage = _mgstage_prefix(filename, search_query)
    matched_madou = bool(MADOU_CODE.search(
        f'{filename or ""} {search_query or ""}'
    ))
    matched_marker = None
    for marker in sorted(NON_JAV_GENERAL_MARKERS):
        if marker in normalized_filename or marker in normalized_query:
            matched_marker = marker
            break

    if preferred_provider == AUTO_ALL:
        if normalized_query.startswith('art video '):
            candidates = ['artvideo']
            reason = 'auto-all-art-video'
        elif matched_madou:
            candidates = ['madouqu']
            reason = 'auto-all-madou-exact-code'
        elif matched_mgstage:
            # MGStage products are Japanese censored catalogs. LibreDMM can
            # resolve the public display code without site verification; the
            # official MGStage page remains the exact-source fallback.
            candidates = ['libredmm', 'mgstage']
            reason = f'auto-all-mgstage:{matched_mgstage}'
        elif matched_marker:
            candidates = ['uncensored']
            reason = f'auto-all-marker:{matched_marker}'
        else:
            # 有码链按可靠性回退；全部失败后再交给无码源做最后判断。
            candidates = ['javbus', 'javhoo', 'libredmm', 'r18dev', 'uncensored']
            reason = (
                'auto-all-general-priority'
                if GENERAL_JAV_CODE.fullmatch(normalized_query)
                else 'auto-all-ambiguous-priority'
            )
    elif preferred_provider == AUTO_CENSORED:
        if normalized_query.startswith('art video '):
            candidates = ['artvideo']
            reason = 'auto-censored-art-video'
        elif matched_mgstage:
            candidates = ['libredmm', 'mgstage']
            reason = f'auto-censored-mgstage:{matched_mgstage}'
        else:
            candidates = ['javbus', 'javhoo', 'libredmm', 'r18dev']
            reason = 'auto-censored-priority'
    elif preferred_provider == AUTO_UNCENSORED:
        if matched_madou:
            candidates = ['madouqu']
            reason = 'auto-uncensored-madou-exact-code'
        else:
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
