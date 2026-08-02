import requests

from providers.factory import create_provider
from providers.madouqu_provider import MadouQuProvider


class DummyResponse:
    def __init__(self, html, url='https://madouqu.com/'):
        self.content = html.encode('utf-8')
        self.url = url

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
<article id="post-123">
  <h2><a href="https://madouqu.com/mdhg-0020-title/" title="MDHG-0020 正确标题">结果</a></h2>
</article>
'''

DETAIL_HTML = '''
<article id="post-123"><div class="container">
  <p><img src="https://img.example/MDHG-0020-cover.jpg" /></p>
  <p>番號：MDHG-0020</p>
  <p>片名：正确标题</p>
  <p>女郎：演员甲</p>
</div></article>
'''


def test_madouqu_requires_exact_detail_code_and_returns_cover():
    session = RecordingSession([
        DummyResponse(SEARCH_HTML),
        DummyResponse(DETAIL_HTML, 'https://madouqu.com/mdhg-0020-title/'),
    ])

    result = MadouQuProvider(log=lambda *a, **k: None, session=session).search('mdhg-0020')

    assert result.ok is True
    assert result.title == 'MDHG-0020 正确标题 演员甲'
    assert result.image_url == 'https://img.example/MDHG-0020-cover.jpg'
    assert result.raw_meta['catalog_number'] == 'MDHG-0020'
    assert session.calls[0][0] == 'https://madouqu.com/?s=MDHG-0020'


def test_madouqu_rejects_detail_for_different_code():
    wrong = DETAIL_HTML.replace('MDHG-0020', 'MDHG-0022')
    session = RecordingSession([DummyResponse(SEARCH_HTML), DummyResponse(wrong)])

    result = MadouQuProvider(log=lambda *a, **k: None, session=session).search('MDHG-0020')

    assert result.ok is False
    assert result.error_type == 'not-found'


def test_madouqu_rejects_ambiguous_or_non_madou_query_without_network():
    session = RecordingSession([])
    result = MadouQuProvider(log=lambda *a, **k: None, session=session).search('直播视频')

    assert result.ok is False
    assert result.error_type == 'unsupported-query'
    assert session.calls == []


def test_madouqu_reports_network_failure():
    class FailingSession(RecordingSession):
        def get(self, url, timeout=None, headers=None):
            raise requests.ConnectionError('offline')

    result = MadouQuProvider(
        log=lambda *a, **k: None,
        session=FailingSession([]),
    ).search('MD-0166')

    assert result.ok is False
    assert result.error_type == 'network-error'


def test_factory_creates_madouqu_provider():
    assert create_provider('madouqu', log=lambda *a, **k: None).name == 'madouqu'
