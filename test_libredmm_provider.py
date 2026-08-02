import json

import requests

from provider_result_validation import reject_mismatched_provider_result
from providers.factory import create_provider
from providers.libredmm_provider import LibreDMMProvider


def _response(status, payload, url):
    response = requests.Response()
    response.status_code = status
    response.url = url
    response._content = json.dumps(payload).encode('utf-8')
    response.headers['Content-Type'] = 'application/json'
    return response


class RecordingSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.headers = {}

    def get(self, url, timeout=None, headers=None):
        self.calls.append((url, timeout, headers))
        return self.responses.pop(0)


def test_libredmm_returns_japanese_title_and_full_dmm_cover():
    search_url = 'https://www.libredmm.com/search?q=MIRD-876&format=json'
    detail_url = 'https://www.libredmm.com/movies/MIRD-876.json'
    session = RecordingSession([_response(200, {
        'normalized_id': 'MIRD-876',
        'subtitle': 'mird00876',
        'title': '日本語の商品タイトル',
        'cover_image_url': 'https://pics.dmm.co.jp/digital/video/mird00876/mird00876pl.jpg',
        'url': 'https://www.dmm.co.jp/digital/videoa/-/detail/=/cid=mird00876/',
        'actresses': [{'name': '出演者'}],
    }, detail_url)])
    provider = LibreDMMProvider(log=lambda *a, **k: None, session=session)

    result = provider.search('MIRD-876')

    assert result.ok is True
    assert result.provider == 'libredmm'
    assert result.title == 'MIRD-876 日本語の商品タイトル'
    assert result.image_url.endswith('/mird00876pl.jpg')
    assert result.detail_url == detail_url
    assert result.referer == search_url
    assert result.raw_meta['source_url'].startswith('https://www.dmm.co.jp/')
    assert reject_mismatched_provider_result('MIRD-876', result.to_dict())['ok'] is True


def test_libredmm_accepts_gana_normalized_id_and_mgstage_content_id():
    detail_url = 'https://www.libredmm.com/movies/GANA-3218.json'
    session = RecordingSession([_response(200, {
        'normalized_id': 'GANA-3218',
        'subtitle': '200GANA-3218',
        'title': '日本語の商品タイトル',
        'cover_image_url': (
            'https://image.mgstage.com/images/nanpatv/200gana/3218/'
            'pb_e_200gana-3218.jpg'
        ),
        'url': 'https://www.mgstage.com/product/product_detail/200GANA-3218/',
        'makers': ['ナンパTV'],
    }, detail_url)])

    result = LibreDMMProvider(log=lambda *a, **k: None, session=session).search('GANA-3218')
    payload = result.to_dict()
    reject_mismatched_provider_result('GANA-3218', payload)

    assert payload['ok'] is True
    assert payload['title'] == 'GANA-3218 日本語の商品タイトル'
    assert payload['raw_meta']['content_id'] == '200GANA-3218'


def test_libredmm_short_polls_processing_result_without_long_batch_stall():
    search_url = 'https://www.libredmm.com/search?q=RBD-353&format=json'
    detail_url = 'https://www.libredmm.com/movies/RBD-353.json'
    session = RecordingSession([
        _response(202, {'err': 'processing'}, detail_url),
        _response(200, {
            'normalized_id': 'RBD-353',
            'subtitle': '7rbd353',
            'title': '奴●色のステージ21',
            'cover_image_url': 'https://pics.dmm.co.jp/mono/movie/adult/7rbd353/7rbd353pl.jpg',
        }, detail_url),
    ])
    provider = LibreDMMProvider(log=lambda *a, **k: None, session=session)
    provider.poll_attempts = 2
    provider.poll_interval = 0

    result = provider.search('RBD-353')

    assert result.ok is True
    assert [call[0] for call in session.calls] == [search_url, detail_url]


def test_libredmm_waits_long_enough_for_a_new_dmm_catalog_entry():
    search_url = 'https://www.libredmm.com/search?q=SERO-0028&format=json'
    detail_url = 'https://www.libredmm.com/movies/SERO-028.json'
    session = RecordingSession([
        _response(202, {'err': 'processing'}, detail_url),
        _response(202, {'err': 'processing'}, detail_url),
        _response(202, {'err': 'processing'}, detail_url),
        _response(200, {
            'normalized_id': 'SERO-028',
            'subtitle': 'td041sero00028',
            'title': '日本語の商品タイトル',
            'cover_image_url': (
                'https://pics.dmm.co.jp/digital/video/td041sero00028/'
                'td041sero00028pl.jpg'
            ),
        }, detail_url),
    ])
    provider = LibreDMMProvider(log=lambda *a, **k: None, session=session)
    provider.poll_interval = 0

    result = provider.search('SERO-0028')

    assert result.ok is True
    assert len(session.calls) == 4


def test_libredmm_accepts_numeric_catalog_prefix_removed_by_canonical_id():
    detail_url = 'https://www.libredmm.com/movies/NTR-088.json'
    session = RecordingSession([_response(200, {
        'normalized_id': 'NTR-088',
        'subtitle': 'h_189ntr00088',
        'title': '日本語の商品タイトル',
        'cover_image_url': (
            'https://pics.dmm.co.jp/digital/video/h_189ntr00088/'
            'h_189ntr00088pl.jpg'
        ),
    }, detail_url)])

    result = LibreDMMProvider(log=lambda *a, **k: None, session=session).search('348NTR-088')

    assert result.ok is True
    assert result.raw_meta['normalized_id'] == 'NTR-088'


def test_libredmm_rejects_wrong_normalized_id_and_content_id():
    detail_url = 'https://www.libredmm.com/movies/SMT-003.json'
    session = RecordingSession([_response(200, {
        'normalized_id': 'SMT-003',
        'subtitle': 'smt00003',
        'title': 'Wrong movie',
        'cover_image_url': 'https://pics.dmm.co.jp/digital/video/smt00003/smt00003pl.jpg',
    }, detail_url)])

    result = LibreDMMProvider(log=lambda *a, **k: None, session=session).search('SMT-030')

    assert result.ok is False
    assert result.error_type == 'code-mismatch'
    assert result.image_url is None


def test_libredmm_returns_processing_timeout_after_bounded_polling():
    detail_url = 'https://www.libredmm.com/movies/DADS-229.json'
    session = RecordingSession([
        _response(202, {'err': 'processing'}, detail_url),
        _response(202, {'err': 'processing'}, detail_url),
    ])
    provider = LibreDMMProvider(log=lambda *a, **k: None, session=session)
    provider.poll_attempts = 2
    provider.poll_interval = 0

    result = provider.search('DADS-229')

    assert result.ok is False
    assert result.error_type == 'processing-timeout'
    assert len(session.calls) == 2


def test_libredmm_skips_title_only_queries_without_network_request():
    session = RecordingSession([])

    result = LibreDMMProvider(log=lambda *a, **k: None, session=session).search('問答無用 124')

    assert result.ok is False
    assert result.error_type == 'unsupported-query'
    assert session.calls == []


def test_factory_creates_libredmm_provider():
    assert create_provider('libredmm', log=lambda *a, **k: None).name == 'libredmm'
