from providers.factory import create_provider
from providers.uncensored_provider import UncensoredProvider
import requests


class DummyResponse:
    def __init__(self, html, url='https://example.test/'):
        self.content = html.encode('utf-8')
        self.url = url

    def raise_for_status(self):
        return None


class DummySession:
    def __init__(self, html):
        self.html = html
        self.calls = []

    def get(self, url, timeout=None):
        self.calls.append((url, timeout))
        return DummyResponse(self.html, url=url)


class MultiResponseSession:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def get(self, url, timeout=None):
        self.calls.append((url, timeout))
        payload = self.responses[url]
        if isinstance(payload, dict):
            return DummyJsonResponse(payload, url=url)
        return DummyResponse(payload, url=url)


class DummyJsonResponse:
    def __init__(self, payload, url='https://example.test/'):
        self.payload = payload
        self.content = b'{}'
        self.url = url

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class RaisingSession:
    def __init__(self, exc):
        self.exc = exc
        self.calls = []

    def get(self, url, timeout=None):
        self.calls.append((url, timeout))
        raise self.exc


class HttpErrorResponse(DummyResponse):
    def raise_for_status(self):
        raise requests.HTTPError('403 Client Error: Forbidden for url')


class HttpErrorSession:
    def __init__(self):
        self.calls = []

    def get(self, url, timeout=None):
        self.calls.append((url, timeout))
        return HttpErrorResponse('<html><body>Forbidden</body></html>', url=url)


class BadJsonResponse(DummyJsonResponse):
    def json(self):
        raise ValueError('invalid json')


class JsonFallbackSession:
    def __init__(self, page_html):
        self.page_html = page_html
        self.calls = []

    def get(self, url, timeout=None):
        self.calls.append((url, timeout))
        if url.endswith('.json'):
            return BadJsonResponse({}, url=url)
        return DummyResponse(self.page_html, url=url)


def test_uncensored_provider_parses_caribbeancom_page():
    html = '''
    <html><head>
      <meta property="og:title" content="Sample Caribbean Title" />
      <meta property="og:image" content="/moviepages/032226-001/images/l_l.jpg" />
    </head><body></body></html>
    '''
    session = DummySession(html)
    provider = UncensoredProvider(log=lambda *a, **k: None, session=session)

    result = provider.search('CARIB-032226-001')

    assert result.ok is True
    assert result.provider == 'uncensored'
    assert result.title == 'CARIB-032226-001 Sample Caribbean Title'
    assert result.detail_url == 'https://www.caribbeancom.com/moviepages/032226-001/index.html'
    assert result.image_url == 'https://www.caribbeancom.com/moviepages/032226-001/images/l_l.jpg'
    assert session.calls == [('https://www.caribbeancom.com/moviepages/032226-001/index.html', (5, 15))]


def test_uncensored_provider_accepts_carib_suffix_query():
    html = '<html><head><title>Title</title></head><body><img src="images/str.jpg" /></body></html>'
    session = DummySession(html)
    provider = UncensoredProvider(log=lambda *a, **k: None, session=session)

    result = provider.search('032226-001-carib')

    assert result.ok is True
    assert result.raw_meta['family'] == 'caribbeancom'
    assert result.raw_meta['code'] == '032226-001'
    assert result.image_url == 'https://www.caribbeancom.com/moviepages/032226-001/images/l_l.jpg'


def test_uncensored_provider_parses_1pondo_page():
    html = '''
    <html><head><title>1Pondo Title - 1pondo.tv</title></head>
    <body><img src="https://www.1pondo.tv/assets/sample/032126_001/str.jpg" /></body></html>
    '''
    session = DummySession(html)
    provider = UncensoredProvider(log=lambda *a, **k: None, session=session)

    result = provider.search('1PONDO-032126-001')

    assert result.ok is True
    assert result.title == '1PONDO-032126-001 1Pondo Title'
    assert result.detail_url == 'https://www.1pondo.tv/movies/032126_001/'
    assert result.image_url == 'https://www.1pondo.tv/assets/sample/032126_001/str.jpg'


def test_uncensored_provider_uses_json_fast_path_when_complete():
    json_url = 'https://www.1pondo.tv/dyn/phpauto/movie_details/movie_id/032126_001.json'
    session = MultiResponseSession({
        json_url: {
            'Title': 'Fast JSON Title',
            'ThumbUltra': 'https://www.1pondo.tv/assets/sample/032126_001/str.jpg',
        },
    })
    provider = UncensoredProvider(log=lambda *a, **k: None, session=session)

    result = provider.search('1PONDO-032126-001')

    assert result.ok is True
    assert result.title == '1PONDO-032126-001 Fast JSON Title'
    assert result.image_url == 'https://www.1pondo.tv/assets/sample/032126_001/str.jpg'
    assert session.calls == [(json_url, (5, 15))]


def test_uncensored_provider_falls_back_when_json_is_invalid():
    html = '''
    <html><head><title>Fallback Page Title - 1pondo.tv</title></head>
    <body><img src="https://www.1pondo.tv/assets/sample/032126_001/str.jpg" /></body></html>
    '''
    session = JsonFallbackSession(html)
    provider = UncensoredProvider(log=lambda *a, **k: None, session=session)

    result = provider.search('1PONDO-032126-001')

    assert result.ok is True
    assert result.title == '1PONDO-032126-001 Fallback Page Title'
    assert len(session.calls) == 2


def test_uncensored_provider_routes_10musume_inside_single_ui_source():
    html = '''
    <html><head><title>10Musume Title - 10musume.com</title></head>
    <body><img src="/moviepages/041619_01/images/l_l.jpg" /></body></html>
    '''
    session = DummySession(html)
    provider = UncensoredProvider(log=lambda *a, **k: None, session=session)

    result = provider.search('10musume-041619-1')

    assert result.ok is True
    assert result.title == '10MUSUME-041619-01 10Musume Title'
    assert result.detail_url == 'https://www.10musume.com/movies/041619_01/'
    assert result.raw_meta['family'] == '10musume'


def test_uncensored_provider_routes_pacopacomama_inside_single_ui_source():
    html = '''
    <html><head><meta property="og:title" content="Pacopacomama Title" /></head>
    <body><img src="/moviepages/032819_059/images/str.jpg" /></body></html>
    '''
    session = DummySession(html)
    provider = UncensoredProvider(log=lambda *a, **k: None, session=session)

    result = provider.search('pacopacomama-032819-059')

    assert result.ok is True
    assert result.title == 'PACOPACOMAMA-032819-059 Pacopacomama Title'
    assert result.detail_url == 'https://www.pacopacomama.com/movies/032819_059/'
    assert result.raw_meta['family'] == 'pacopacomama'


def test_uncensored_provider_reports_known_family_not_implemented():
    provider = UncensoredProvider(log=lambda *a, **k: None, session=DummySession('<html></html>'))

    result = provider.search('japanhdv.17.09.24.maya.sawamura')

    assert result.ok is False
    assert result.error_type == 'unsupported-family'
    assert result.raw_meta['family'] == 'japanhdv'


def test_uncensored_provider_parses_fc2_official_article():
    html = '''
    <html><head>
      <meta property="og:title" content="FC2-PPV-3202758 Sample FC2 Title" />
      <meta property="og:image" content="https://storage.example/fc2.jpg" />
    </head><body></body></html>
    '''
    session = DummySession(html)
    provider = UncensoredProvider(log=lambda *a, **k: None, session=session)

    result = provider.search('FC2-PPV-3202758')

    assert result.ok is True
    assert result.title == 'FC2-PPV-3202758 Sample FC2 Title'
    assert result.image_url == 'https://storage.example/fc2.jpg'
    assert result.detail_url == 'https://adult.contents.fc2.com/article/3202758/'
    assert result.raw_meta['family'] == 'fc2-ppv'


def test_uncensored_provider_reports_fc2_article_not_found():
    html = '<html><head><title>お探しの商品が見つかりませんでした | FC2コンテンツマーケット</title></head></html>'
    provider = UncensoredProvider(log=lambda *a, **k: None, session=DummySession(html))

    result = provider.search('FC2-PPV-1764780')

    assert result.ok is False
    assert result.error_type == 'not-found'
    assert result.raw_meta['family'] == 'fc2-ppv'


def test_uncensored_provider_parses_heyzo_official_page():
    html = '''
    <html><head>
      <meta property="og:title" content="HEYZO Sample Title" />
      <meta property="og:image" content="/contents/3000/3098/images/player_thumbnail.jpg" />
    </head><body></body></html>
    '''
    session = DummySession(html)
    provider = UncensoredProvider(log=lambda *a, **k: None, session=session)

    result = provider.search('heyzo-3098')

    assert result.ok is True
    assert result.title == 'HEYZO-3098 HEYZO Sample Title'
    assert result.detail_url == 'https://www.heyzo.com/moviepages/3098/index.html'
    assert result.image_url == 'https://www.heyzo.com/contents/3000/3098/images/player_thumbnail.jpg'
    assert result.raw_meta['family'] == 'heyzo'


def test_uncensored_provider_parses_tokyo_hot_page():
    html = '''
    <html><head>
      <title>全動画リスト | Tokyo-Hot</title>
      <meta property="og:image" content="https://my.cdn.tokyo-hot.com/static/images/social.png" />
    </head><body>
      <ul class="list slider cf">
        <li class="detail">
          <a href="/product/21087/" class="rm">
            <img src="https://my.cdn.tokyo-hot.com/media/21087/list_image/n0839 1280x720/220x124_default.jpg" alt="n0839" />
            <div class="description2">
              <div class="title">Misunderstanding 18</div>
              <div class="actor">(Product ID: n0839)</div>
            </div>
          </a>
        </li>
      </ul>
    </body></html>
    '''
    session = DummySession(html)
    provider = UncensoredProvider(log=lambda *a, **k: None, session=session)

    result = provider.search('tokyo-hot-n0839')

    assert result.ok is True
    assert result.title == 'TOKYO-HOT-N0839 Misunderstanding 18'
    assert result.detail_url == 'https://my.tokyo-hot.com/product/21087/'
    assert result.image_url == 'https://my.cdn.tokyo-hot.com/media/21087/list_image/n0839 1280x720/820x462_default.jpg'
    assert result.raw_meta['family'] == 'tokyo-hot'


def test_uncensored_provider_parses_mgstage_like_page():
    html = '''
    <html><head>
      <meta property="og:title" content="MGStage Sample Title" />
      <meta property="og:image" content="//image.mgstage.com/images/300mium/1366/pb_e_300mium-1366.jpg" />
    </head><body></body></html>
    '''
    session = DummySession(html)
    provider = UncensoredProvider(log=lambda *a, **k: None, session=session)

    result = provider.search('300MIUM-1366')

    assert result.ok is True
    assert result.title == '300MIUM-1366 MGStage Sample Title'
    assert result.detail_url == 'https://www.mgstage.com/product/product_detail/300MIUM-1366/'
    assert result.image_url == 'https://image.mgstage.com/images/300mium/1366/pb_e_300mium-1366.jpg'
    assert result.raw_meta['family'] == 'mgstage'


def test_uncensored_provider_reports_http_error_as_network_error():
    provider = UncensoredProvider(log=lambda *a, **k: None, session=HttpErrorSession())

    result = provider.search('300MIUM-1366')

    assert result.ok is False
    assert result.error_type == 'network-error'
    assert '403' in result.message


def test_uncensored_provider_reports_timeout_as_network_error():
    session = RaisingSession(requests.Timeout('read timed out'))
    provider = UncensoredProvider(log=lambda *a, **k: None, session=session)

    result = provider.search('HEYZO-3098')

    assert result.ok is False
    assert result.error_type == 'network-error'
    assert 'timed out' in result.message
    assert session.calls == [('https://www.heyzo.com/moviepages/3098/index.html', (5, 15))]


def test_uncensored_provider_reports_connection_error_as_network_error():
    session = RaisingSession(requests.ConnectionError('connection reset'))
    provider = UncensoredProvider(log=lambda *a, **k: None, session=session)

    result = provider.search('CARIB-032226-001')

    assert result.ok is False
    assert result.error_type == 'network-error'
    assert 'connection reset' in result.message


def test_uncensored_provider_respects_stop_before_network_call():
    session = DummySession('<html></html>')
    provider = UncensoredProvider(
        log=lambda *a, **k: None,
        session=session,
        stop_requested=lambda: True,
    )

    result = provider.search('HEYZO-3098')

    assert result.ok is False
    assert result.error_type == 'cancelled'
    assert session.calls == []


def test_tokyo_hot_does_not_accept_site_social_image_without_result_card():
    html = '''
    <html><head>
      <title>全動画リスト | Tokyo-Hot</title>
      <meta property="og:image" content="https://my.cdn.tokyo-hot.com/static/images/social.png" />
    </head><body>
      <p class="num-result"><span>0</span>items found</p>
    </body></html>
    '''
    provider = UncensoredProvider(log=lambda *a, **k: None, session=DummySession(html))

    result = provider.search('tokyo-hot-n0839')

    assert result.ok is False
    assert result.error_type == 'not-found'


def test_uncensored_provider_reports_verification_required():
    html = '<html><head><title>Just a moment...</title></head><body>cf_chl</body></html>'
    provider = UncensoredProvider(log=lambda *a, **k: None, session=DummySession(html))

    result = provider.search('CARIB-032226-001')

    assert result.ok is False
    assert result.error_type == 'verification-required'


def test_uncensored_provider_rejects_unsupported_source():
    provider = UncensoredProvider(log=lambda *a, **k: None, session=DummySession('<html></html>'))

    result = provider.search('japanhdv.17.09.24.maya.sawamura')

    assert result.ok is False
    assert result.error_type == 'unsupported-family'


def test_factory_creates_uncensored_provider():
    provider = create_provider('uncensored', log=lambda *a, **k: None)

    assert isinstance(provider, UncensoredProvider)
