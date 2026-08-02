#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from providers.base import ProviderResult
from provider_result_validation import reject_mismatched_provider_result


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


def test_provider_result_rejects_partial_code_match_from_javhoo():
    result = ProviderResult(
        ok=True,
        title='MIFD-153 Wrong Search Result',
        image_url='https://pics.javhoo.net/mifd-153.jpg',
        detail_url='https://www.javhoo.com/en/mifd-153',
        provider='javhoo',
    )

    reject_mismatched_provider_result('FD-153', result)

    assert result.ok is False
    assert result.error_type == 'code-mismatch'
    assert '返回番号 MIFD-153' in result.message
    assert '搜索番号 FD-153' in result.message


def test_provider_result_rejects_conflicting_code_hidden_after_old_name():
    result = ProviderResult(
        ok=True,
        title='N1069 一刀両断 椎名愛莉 MAAN-1069 Wrong Result',
        image_url='https://pics.javhoo.net/maan-1069.jpg',
        detail_url='https://www.javhoo.com/en/maan-1069',
        provider='javhoo',
    )

    reject_mismatched_provider_result('N-1069', result)

    assert result.ok is False
    assert result.error_type == 'code-mismatch'
    assert 'MAAN-1069' in result.message


def test_provider_result_accepts_tokyo_hot_compact_n_code_alias():
    result = ProviderResult(
        ok=True,
        title='N1069 一刀両断 椎名愛莉',
        image_url='https://my.cdn.test/n1069.jpg',
        detail_url='https://my.example.test/movies/n1069',
        provider='uncensored',
    )

    reject_mismatched_provider_result('TOKYO-HOT-N1069', result)

    assert result.ok is True
    assert result.error_type is None


def test_provider_result_accepts_tokyo_hot_image_width_suffix():
    result = ProviderResult(
        ok=True,
        title='N1069 一刀両断 椎名愛莉',
        image_url='https://my.cdn.test/posters/n1069-1280.jpg',
        detail_url='https://my.tokyo-hot.com/product/?q=n1069',
        provider='uncensored',
    )

    reject_mismatched_provider_result('TOKYO-HOT-N1069', result)

    assert result.ok is True
    assert result.error_type is None


def test_provider_result_accepts_caribbeancom_bare_code_urls():
    result = ProviderResult(
        ok=True,
        title='CARIB-050425-001 ダイナマイト',
        image_url='https://www.caribbeancom.com/moviepages/050425-001/images/l_l.jpg',
        detail_url='https://www.caribbeancom.com/moviepages/050425-001/index.html',
        provider='uncensored',
    )

    reject_mismatched_provider_result('050425-001-carib', result)

    assert result.ok is True
    assert result.error_type is None


def test_provider_result_accepts_gana_mgstage_catalog_prefix_and_cover_wrapper():
    result = ProviderResult(
        ok=True,
        title='GANA-3218 Japanese title',
        image_url=(
            'https://image.mgstage.com/images/nanpatv/200gana/3218/'
            'pb_e_200gana-3218.jpg'
        ),
        detail_url='https://www.mgstage.com/product/product_detail/200GANA-3218/',
        provider='libredmm',
    )

    reject_mismatched_provider_result('GANA-3218', result)

    assert result.ok is True
    assert result.error_type is None


def test_provider_result_still_rejects_wrong_gana_number():
    result = ProviderResult(
        ok=True,
        title='GANA-3218 Japanese title',
        image_url=(
            'https://image.mgstage.com/images/nanpatv/200gana/9999/'
            'pb_e_200gana-9999.jpg'
        ),
        detail_url='https://www.mgstage.com/product/product_detail/200GANA-9999/',
        provider='libredmm',
    )

    reject_mismatched_provider_result('GANA-3218', result)

    assert result.ok is False
    assert result.error_type == 'code-mismatch'


def test_provider_result_accepts_dmm_service_wrapper_in_cover_url():
    result = ProviderResult(
        ok=True,
        title='FAD-1470 大胆不敵 破廉恥野外SEX',
        image_url=(
            'https://pics.dmm.co.jp/mono/movie/adult/h_066fad1470r/'
            'h_066fad1470rpl.jpg'
        ),
        detail_url='https://r18.dev/videos/vod/movies/detail/-/dvd_id=fad1470/json',
        provider='r18dev',
    )

    reject_mismatched_provider_result('FAD-1470', result)

    assert result.ok is True
    assert result.error_type is None


def test_provider_result_rejects_wrong_code_in_image_url():
    result = ProviderResult(
        ok=True,
        title='NTRD-021 Correct Looking Title',
        image_url='https://pics.javhoo.net/2026/MIAA-001_b.jpg',
        detail_url='https://www.javhoo.com/ntrd-021',
        provider='javhoo',
    )

    reject_mismatched_provider_result('NTRD-021', result)

    assert result.ok is False
    assert result.error_type == 'code-mismatch'
    assert 'MIAA-001' in result.message


def test_provider_result_rejects_ambiguous_result_without_exact_code():
    result = ProviderResult(
        ok=True,
        title='Search result with no product identifier',
        image_url='https://cdn.example.test/poster.jpg',
        detail_url='https://example.test/detail/opaque-id',
        provider='dummy',
    )

    reject_mismatched_provider_result('NTRD-021', result)

    assert result.ok is False
    assert result.error_type == 'code-mismatch'
    assert '未找到与搜索番号 NTRD-021 精确一致' in result.message
    assert '拒绝模糊匹配' in result.message


def test_provider_result_rejects_wrong_code_in_fallback_image_url():
    result = ProviderResult(
        ok=True,
        title='NTRD-021 Correct Title',
        image_url='https://cdn.example.test/ntrd-021.jpg',
        fallback_images=['https://cdn.example.test/MIAA-001.jpg'],
        detail_url='https://example.test/ntrd-021',
        provider='dummy',
    )

    reject_mismatched_provider_result('NTRD-021', result)

    assert result.ok is False
    assert result.error_type == 'code-mismatch'
    assert 'MIAA-001' in result.message
