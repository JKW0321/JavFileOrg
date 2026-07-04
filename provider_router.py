#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Simple provider router for mixed-source video filenames."""
from __future__ import annotations

NON_JAVLIB_MARKERS = {
    'carib', '1pon', 'nyoshin', '10musume', 'pacopacomama', 'muramura',
    '300mium', '393otim', '420hpt', '420sth', '546erofv', '583erkr', '328cnstv',
    '476mla', '253kaku'
}


def route_provider(preferred_provider: str, filename: str, search_query: str) -> dict:
    normalized_filename = (filename or '').lower()
    normalized_query = (search_query or '').lower()

    if normalized_filename.startswith('._') or normalized_filename.startswith('.'):
        return {
            'action': 'skip',
            'provider': None,
            'reason': 'hidden-file',
        }

    mismatch_reason = None
    if preferred_provider == 'javlibrary':
        for marker in sorted(NON_JAVLIB_MARKERS):
            if marker in normalized_filename or marker in normalized_query:
                mismatch_reason = f'marker:{marker}'
                break

    return {
        'action': 'process',
        'provider': preferred_provider,
        'reason': mismatch_reason or 'preferred-provider',
        'warning_only': bool(mismatch_reason),
    }
