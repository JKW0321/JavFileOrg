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
