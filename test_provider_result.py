#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from providers.base import ProviderResult


def test_provider_result_supports_dict_like_get_access():
    result = ProviderResult(
        ok=True,
        title='TITLE',
        image_url='http://example/image.jpg',
        provider='javhoo',
        error_type=None,
        message=None,
    )
    assert result.get('ok') is True
    assert result.get('title') == 'TITLE'
    assert result.get('image_url') == 'http://example/image.jpg'
    assert result.get('missing', 'fallback') == 'fallback'


def test_provider_result_contract_includes_audit_fields():
    result = ProviderResult(
        ok=True,
        title='TITLE',
        image_url='http://example/image.jpg',
        provider='javhoo',
        query='abf-217',
        detail_url='https://www.javhoo.com/abf-217',
        referer='https://www.javhoo.com/search/abf-217',
    )

    assert result.get('query') == 'abf-217'
    assert result.get('detail_url') == 'https://www.javhoo.com/abf-217'
    assert result.get('referer') == 'https://www.javhoo.com/search/abf-217'
    assert result.to_dict()['provider'] == 'javhoo'
