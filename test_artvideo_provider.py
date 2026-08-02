import requests

from providers.artvideo_provider import ArtVideoProvider
from providers.factory import create_provider


class DummyResponse:
    def __init__(self, html, url):
        self.content = html.encode('utf-8')
        self.url = url
        self.status_code = 200

    def raise_for_status(self):
        return None


class RecordingSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.headers = {}

    def get(self, url, timeout=None, headers=None):
        self.calls.append((url, timeout, headers))
        return self.responses.pop(0)


SEARCH_HTML = '''
<html><body>
  <a href="/user_data/sp_artist_product_detail.php?mid=3&amp;pid=126018314000">
    淫乱美麗奴倶楽部
  </a>
</body></html>
'''

DETAIL_HTML = '''
<html><head><title>ピュアアダルト 淫乱美麗奴倶楽部</title></head><body>
  <a class="example-image-link" href="/user_data/sp_images/gazou/126018/126018314000.jpg">
    <img src="/user_data/sp_images/gazou/126018/126018314000.jpg" />
  </a>
  <table class="prd_detail_box">
    <tr><td><b>タイトル</b></td><td>淫乱美麗奴倶楽部</td></tr>
    <tr><td><b>AV女優</b></td><td>出演者一</td></tr>
    <tr><td><b>商品コード</b></td><td>126018314000</td></tr>
    <tr><td><b>メーカー</b></td><td>ＡＲＴ　ＶＩＤＥＯ</td></tr>
  </table>
</body></html>
'''


def test_artvideo_provider_requires_art_maker_and_returns_verified_network_cover():
    search_url = (
        'https://pureadult.co.jp/user_data/sp_search_result.php?'
        'km=2&kw=%E6%B7%AB%E4%B9%B1%E7%BE%8E%E9%BA%97%E5%A5%B4%E5%80%B6%E6%A5%BD%E9%83%A8'
    )
    detail_url = (
        'https://pureadult.co.jp/user_data/'
        'sp_artist_product_detail.php?mid=3&pid=126018314000'
    )
    session = RecordingSession([
        DummyResponse(SEARCH_HTML, search_url),
        DummyResponse(DETAIL_HTML, detail_url),
    ])
    provider = ArtVideoProvider(log=lambda *a, **k: None, session=session)

    result = provider.search('ART VIDEO 1754 淫乱美麗奴倶楽部')

    assert result.ok is True
    assert result.provider == 'artvideo'
    assert result.title == 'ART-1754 淫乱美麗奴倶楽部 出演者一'
    assert result.image_url == (
        'https://pureadult.co.jp/user_data/sp_images/gazou/126018/126018314000.jpg'
    )
    assert result.raw_meta['maker'] == 'ART VIDEO'
    assert [call[0] for call in session.calls] == [search_url, detail_url]


def test_artvideo_provider_rejects_same_title_from_wrong_maker():
    wrong_detail = DETAIL_HTML.replace('ＡＲＴ　ＶＩＤＥＯ', '別メーカー')
    session = RecordingSession([
        DummyResponse(SEARCH_HTML, 'https://pureadult.co.jp/search'),
        DummyResponse(wrong_detail, 'https://pureadult.co.jp/detail'),
    ])

    result = ArtVideoProvider(log=lambda *a, **k: None, session=session).search(
        'ART VIDEO 1754 淫乱美麗奴倶楽部'
    )

    assert result.ok is False
    assert result.error_type == 'not-found'


def test_artvideo_provider_does_not_search_numeric_only_legacy_id():
    session = RecordingSession([])

    result = ArtVideoProvider(log=lambda *a, **k: None, session=session).search(
        'ART VIDEO 2090'
    )

    assert result.ok is False
    assert result.error_type == 'insufficient-context'
    assert session.calls == []


def test_artvideo_provider_uses_japanese_title_fallback_but_still_verifies_detail():
    empty_search = '<html><body>no exact result</body></html>'
    fallback_search = '''
    <html><body>
      <a href="/user_data/sp_artist_product_detail.php?mid=3&amp;pid=999">爆イキ 10</a>
    </body></html>
    '''
    detail = DETAIL_HTML.replace('淫乱美麗奴倶楽部', '爆イキ 10')
    session = RecordingSession([
        DummyResponse(empty_search, 'https://pureadult.co.jp/search-full'),
        DummyResponse(empty_search, 'https://pureadult.co.jp/search-no-parens'),
        DummyResponse(fallback_search, 'https://pureadult.co.jp/search-japanese'),
        DummyResponse(detail, 'https://pureadult.co.jp/detail'),
    ])

    result = ArtVideoProvider(log=lambda *a, **k: None, session=session).search(
        'ART VIDEO Extreme Sexual Torture アートビデオ 爆イキ 10 (2008) - 三浦亜沙妃 (Asahi Miura)'
    )

    assert result.ok is True
    assert result.title.startswith('爆イキ 10')
    assert result.raw_meta['search_term'] == '爆イキ 10'
    assert '%E7%88%86%E3%82%A4%E3%82%AD%2010' in session.calls[2][0]


def test_artvideo_provider_rejects_broad_one_word_partial_title():
    assert ArtVideoProvider._title_matches("乱舞 '06-2-3673", '乱舞') is False


def test_artvideo_provider_rejects_same_series_with_different_explicit_issue_number():
    assert ArtVideoProvider._title_matches(
        '奴隷通信 No.11 倉持遥子',
        '奴隷通信 No.28',
    ) is False
    assert ArtVideoProvider._title_matches(
        '奴隷通信 No.14 吉永ひかるこ',
        '奴隷通信 No.14',
    ) is True


def test_artvideo_provider_reports_network_errors_without_modifying_files():
    class FailingSession(RecordingSession):
        def get(self, url, timeout=None, headers=None):
            raise requests.ConnectionError('offline')

    result = ArtVideoProvider(
        log=lambda *a, **k: None,
        session=FailingSession([]),
    ).search('ART VIDEO 1754 淫乱美麗奴倶楽部')

    assert result.ok is False
    assert result.error_type == 'network-error'


def test_factory_creates_artvideo_provider():
    assert create_provider('artvideo', log=lambda *a, **k: None).name == 'artvideo'
