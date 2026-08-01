#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Safety checks shared by ordinary processing and inspection providers."""
from __future__ import annotations

import re
from urllib.parse import unquote, urlparse

from filename_utils import extract_code_from_text


def _display_code(value: str | None) -> str | None:
    text = str(value or '')
    code = extract_code_from_text(text)
    if code:
        return code
    match = re.search(
        r'(?<![A-Z0-9])([A-Z][A-Z0-9]{0,11}[-_]\d{2,6})(?![A-Z0-9])',
        text,
        re.IGNORECASE,
    )
    return match.group(1).replace('_', '-').upper() if match else None


def _explicit_display_codes(value: str | None) -> list[str]:
    """Return every explicit standard code, including codes after an old name."""
    text = str(value or '')
    return [
        match.group(1).replace('_', '-').upper()
        for match in re.finditer(
            r'(?<![A-Z0-9])([A-Z][A-Z0-9]{1,11}[-_]\d{2,6})(?![A-Z0-9])',
            text,
            re.IGNORECASE,
        )
    ]


def _canonical_code(value: str | None) -> str:
    code = _display_code(value)
    return re.sub(r'[^A-Z0-9]', '', code.upper()) if code else ''


def _canonical_aliases(value: str | None) -> set[str]:
    display = _display_code(value)
    canonical = re.sub(r'[^A-Z0-9]', '', str(display or '').upper())
    aliases = {canonical} if canonical else set()
    match = re.fullmatch(r'TOKYO-HOT-(N\d{4,6})', str(display or ''), re.IGNORECASE)
    if match:
        aliases.add(match.group(1).upper())
    compact = re.fullmatch(r'N-?(\d{4,6})', str(display or ''), re.IGNORECASE)
    if compact:
        aliases.add(f'TOKYOHOTN{compact.group(1)}')
    return aliases


_COMMON_IMAGE_DIMENSIONS = {
    '480', '540', '640', '720', '800', '960', '1024', '1080', '1200',
    '1280', '1440', '1600', '1920', '2048', '2160', '2560', '3840', '4096',
}


def _is_expected_code_with_image_dimension(
    explicit_display: str,
    expected_aliases: set[str],
) -> bool:
    """Treat ``N1069-1280`` as image sizing, not a second product code."""
    match = re.fullmatch(r'(.+?)[-_](\d{3,4})', str(explicit_display or ''))
    if not match or match.group(2) not in _COMMON_IMAGE_DIMENSIONS:
        return False
    return not expected_aliases.isdisjoint(_canonical_aliases(match.group(1)))


def _field_text(field: str, value: str) -> str:
    if field.endswith('_url'):
        return unquote(urlparse(value).path)
    return value


def _is_expected_family_url_alias(field: str, value: str, expected_display: str) -> bool:
    """Accept official URLs that omit a source prefix from the product id."""
    if not field.endswith('_url'):
        return False
    expected = str(expected_display or '').upper()
    match = re.fullmatch(r'CARIB-(\d{6})-(\d{2,5})', expected)
    if not match:
        return False
    parsed = urlparse(str(value or ''))
    hostname = (parsed.hostname or '').lower()
    if not (hostname == 'caribbeancom.com' or hostname.endswith('.caribbeancom.com')):
        return False
    product_id = f'{match.group(1)}-{match.group(2)}'
    return bool(re.search(
        rf'(?<!\d){re.escape(product_id)}(?!\d)',
        unquote(parsed.path),
        re.IGNORECASE,
    ))


def _contains_exact_code(text: str, code: str) -> bool:
    candidates = [str(code or '')]
    tokyo_hot = re.fullmatch(r'TOKYO-HOT-(N\d{4,6})', str(code or ''), re.IGNORECASE)
    if tokyo_hot:
        candidates.append(tokyo_hot.group(1))
    for candidate in candidates:
        atoms = re.findall(r'[A-Z]+|\d+', candidate.upper())
        if not atoms:
            continue
        pattern = re.compile(
            r'(?<![A-Z0-9])' + r'[-_]?'.join(map(re.escape, atoms)) +
            r'(?![A-Z0-9]|[-_]\d)',
            re.IGNORECASE,
        )
        if pattern.search(text):
            return True
    return False


def _identity_fields(result):
    fields = [
        ('title', str(result.get('title') or '')),
        ('detail_url', str(result.get('detail_url') or '')),
        ('image_url', str(result.get('image_url') or '')),
    ]
    raw_meta = result.get('raw_meta') or {}
    fallbacks = result.get('fallback_images') or (
        raw_meta.get('fallback_images') if isinstance(raw_meta, dict) else []
    ) or []
    fields.extend(('fallback_image_url', str(value or '')) for value in fallbacks)
    return fields


def provider_result_code_mismatch(query: str, result) -> dict | None:
    """Return details when a provider result is not an exact code match."""
    expected_display = _display_code(query)
    expected = _canonical_code(query)
    expected_aliases = _canonical_aliases(query)
    if not expected:
        return None

    exact_fields = []
    for field, value in _identity_fields(result):
        comparable = _field_text(field, value)
        family_url_alias = _is_expected_family_url_alias(
            field,
            value,
            expected_display,
        )
        contains_expected = (
            _contains_exact_code(comparable, expected_display)
            or family_url_alias
        )
        if contains_expected:
            exact_fields.append(field)
        for explicit_display in _explicit_display_codes(comparable):
            explicit_aliases = _canonical_aliases(explicit_display)
            explicit = re.sub(r'[^A-Z0-9]', '', explicit_display.upper())
            if expected_aliases.isdisjoint(explicit_aliases):
                if _is_expected_code_with_image_dimension(
                    explicit_display,
                    expected_aliases,
                ):
                    continue
                # A general regex may see the first two atoms of a valid
                # multi-segment code (CARIB-011126 inside
                # CARIB-011126-001). The full exact occurrence remains safe.
                if contains_expected and expected.startswith(explicit):
                    continue
                return {
                    'expected': expected_display or str(query or '').upper(),
                    'returned': explicit_display,
                    'field': field,
                    'kind': 'conflicting-code',
                }
        returned_display = _display_code(comparable)
        returned = _canonical_code(comparable)
        returned_aliases = _canonical_aliases(comparable)
        if returned and expected_aliases.isdisjoint(returned_aliases):
            if family_url_alias:
                continue
            if _is_expected_code_with_image_dimension(
                returned_display or '',
                expected_aliases,
            ):
                continue
            # Some multi-part codes are truncated by the general extractor;
            # an explicit full exact occurrence is still safe.
            if contains_expected and expected.startswith(returned):
                continue
            return {
                'expected': expected_display or str(query or '').upper(),
                'returned': returned_display or str(value),
                'field': field,
                'kind': 'conflicting-code',
            }
    if not exact_fields:
        return {
            'expected': expected_display or str(query or '').upper(),
            'returned': '未发现精确番号',
            'field': 'result',
            'kind': 'missing-exact-code',
        }
    return None


def reject_mismatched_provider_result(query: str, result):
    """Turn an otherwise successful mismatched result into a safe failure."""
    if not result or not result.get('ok'):
        return result
    mismatch = provider_result_code_mismatch(query, result)
    if not mismatch:
        return result

    if mismatch.get('kind') == 'missing-exact-code':
        message = (
            f'数据源结果中未找到与搜索番号 {mismatch["expected"]} '
            '精确一致的标识，已拒绝模糊匹配和自动修改'
        )
    else:
        message = (
            f'数据源返回番号 {mismatch["returned"]} 与搜索番号 '
            f'{mismatch["expected"]} 不一致，已拒绝自动修改'
        )
    raw_meta = result.get('raw_meta') or {}
    if not isinstance(raw_meta, dict):
        raw_meta = {}
    raw_meta['code_validation'] = mismatch

    updates = {
        'ok': False,
        'error_type': 'code-mismatch',
        'message': message,
        'raw_meta': raw_meta,
    }
    if isinstance(result, dict):
        result.update(updates)
    else:
        for key, value in updates.items():
            setattr(result, key, value)
    return result
