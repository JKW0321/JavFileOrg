import json

import requests

from provider_result_validation import reject_mismatched_provider_result
from providers.factory import create_provider
from providers.r18dev_provider import R18DevProvider


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


def test_r18dev_returns_exact_dmm_large_cover_and_audit_fields():
    url = 'https://r18.dev/videos/vod/movies/detail/-/dvd_id=rbd353/json'
    session = RecordingSession([_response(200, {
        'content_id': 'rbd00353',
        'title': 'S***e-Colored Stage 21',
        'images': {'jacket_image': {
            'large': ' ',
            'large2': 'https://pics.dmm.co.jp/digital/video/rbd00353/rbd00353pl.jpg',
        }},
    }, url)])
    provider = R18DevProvider(log=lambda *a, **k: None, session=session)

    result = provider.search('RBD-353')

    assert result.ok is True
    assert result.provider == 'r18dev'
    assert result.query == 'RBD-353'
    assert result.title == 'RBD-353 S***e-Colored Stage 21'
    assert result.image_url.endswith('/rbd00353pl.jpg')
    assert result.detail_url == url
    assert result.referer == 'https://r18.dev/'
    assert session.calls[0][0] == url
    assert reject_mismatched_provider_result('RBD-353', result.to_dict())['ok'] is True


def test_r18dev_accepts_dmm_numeric_prefix_and_rental_suffix():
    url = 'https://r18.dev/videos/vod/movies/detail/-/dvd_id=3rcn002/json'
    session = RecordingSession([_response(200, {
        'content_id': '513rcn002r',
        'title': '',
        'images': {'jacket_image': {
            'large2': 'https://pics.dmm.co.jp/mono/movie/513rcn002r/513rcn002rpl.jpg',
        }},
    }, url)])

    result = R18DevProvider(log=lambda *a, **k: None, session=session).search('3RCN-002')

    assert result.ok is True
    assert result.title == '3RCN-002'
    assert result.raw_meta['content_id'] == '513rcn002r'


def test_r18dev_accepts_dmm_service_prefix_before_exact_catalog_code():
    url = 'https://r18.dev/videos/vod/movies/detail/-/dvd_id=fad1470/json'
    session = RecordingSession([_response(200, {
        'content_id': 'h_066fad1470r',
        'dvd_id': '',
        'title': '大胆不敵 破廉恥野外SEX',
        'images': {'jacket_image': {
            'large2': 'https://pics.dmm.co.jp/mono/movie/adult/h_066fad1470r/h_066fad1470rpl.jpg',
        }},
    }, url)])

    result = R18DevProvider(log=lambda *a, **k: None, session=session).search('FAD-1470')

    assert result.ok is True
    assert result.title.startswith('FAD-1470 ')


def test_r18dev_dmm_service_prefix_does_not_make_mifd_match_fd():
    url = 'https://r18.dev/videos/vod/movies/detail/-/dvd_id=fd153/json'
    session = RecordingSession([_response(200, {
        'content_id': 'mifd00153',
        'title': 'Different catalog',
        'images': {'jacket_image': {
            'large2': 'https://pics.dmm.co.jp/digital/video/mifd00153/mifd00153pl.jpg',
        }},
    }, url)])

    result = R18DevProvider(log=lambda *a, **k: None, session=session).search('FD-153')

    assert result.ok is False
    assert result.error_type == 'code-mismatch'


def test_r18dev_rejects_fuzzy_number_mismatch_before_cover_can_be_used():
    url = 'https://r18.dev/videos/vod/movies/detail/-/dvd_id=smt030/json'
    session = RecordingSession([_response(200, {
        'content_id': 'smt00003',
        'title': 'Wrong title',
        'images': {'jacket_image': {
            'large2': 'https://pics.dmm.co.jp/digital/video/smt00003/smt00003pl.jpg',
        }},
    }, url)])

    result = R18DevProvider(log=lambda *a, **k: None, session=session).search('SMT-030')

    assert result.ok is False
    assert result.error_type == 'code-mismatch'
    assert result.image_url is None


def test_r18dev_rejects_a_different_letter_suffix_as_another_movie():
    url = 'https://r18.dev/videos/vod/movies/detail/-/dvd_id=abc123/json'
    session = RecordingSession([_response(200, {
        'content_id': 'abc00123a',
        'title': 'Different suffix movie',
        'images': {'jacket_image': {
            'large2': 'https://pics.dmm.co.jp/digital/video/abc00123a/abc00123apl.jpg',
        }},
    }, url)])

    result = R18DevProvider(log=lambda *a, **k: None, session=session).search('ABC-123')

    assert result.ok is False
    assert result.error_type == 'code-mismatch'
    assert result.image_url is None


def test_r18dev_skips_title_only_queries_without_network_request():
    session = RecordingSession([])

    result = R18DevProvider(log=lambda *a, **k: None, session=session).search('問答無用 124')

    assert result.ok is False
    assert result.error_type == 'unsupported-query'
    assert session.calls == []


def test_factory_creates_r18dev_provider():
    assert create_provider('r18dev', log=lambda *a, **k: None).name == 'r18dev'
