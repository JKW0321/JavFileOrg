#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from bs4 import BeautifulSoup
import requests

from providers.javhoo_provider import JavHooProvider


class DummyResponse:
    def __init__(self, html: str):
        self.content = html.encode('utf-8')

    def raise_for_status(self):
        return None


def test_javhoo_detail_page_prefers_real_cover_over_language_flags():
    html = '''
    <html><body>
      <h1>ABF-217 SEX力を鍛えて差をつけろ エロ過ぎ小悪魔トレーナー 涼森れむ【限定特典映像30分付き】</h1>
      <img src="https://pics.javhoo.net/logo.png" />
      <img class="qtranxs-flag" alt="中文" src="https://www.javhoo.com/wp-content/plugins/qtranslate-xt/flags/tw.png" />
      <img class="qtranxs-flag" alt="English" src="https://www.javhoo.com/wp-content/plugins/qtranslate-xt/flags/gb.png" />
      <img class="alignnone size-full" alt="ABF-217" src="https://pics.javhoo.net/2025/07/ABF-217_b.jpg" />
      <img class="thumb" src="https://pics.javhoo.net/2025/12/HMN-777.jpg" />
    </body></html>
    '''
    provider = JavHooProvider(log=lambda *a, **k: None, session=None, anti_crawl=None, stop_requested=lambda: False)
    provider._request = lambda url: DummyResponse(html)
    title, image_url = provider._fetch_detail_page('https://www.javhoo.com/abf-217')
    assert title.startswith('ABF-217 ')
    assert image_url == 'https://pics.javhoo.net/2025/07/ABF-217_b.jpg'


def test_request_provider_success_result_includes_query_detail_and_referer():
    search_html = '''
    <html><body>
      <article>
        <h2><a href="/abf-217">ABF-217 Search Title</a></h2>
        <img src="https://pics.javhoo.net/search-thumb.jpg" />
      </article>
    </body></html>
    '''
    detail_html = '''
    <html><body>
      <h1>ABF-217 Detail Title</h1>
      <img class="alignnone size-full" alt="ABF-217" src="https://pics.javhoo.net/2025/07/ABF-217_b.jpg" />
    </body></html>
    '''

    provider = JavHooProvider(log=lambda *a, **k: None, session=None, anti_crawl=None, stop_requested=lambda: False)
    seen_urls = []

    def fake_request(url):
        seen_urls.append(url)
        if url.endswith('/abf-217'):
            return DummyResponse(detail_html)
        return DummyResponse(search_html)

    provider._request = fake_request
    result = provider.search('abf-217')

    assert result.ok is True
    assert result.query == 'abf-217'
    assert result.title == 'ABF-217 Detail Title'
    assert result.image_url == 'https://pics.javhoo.net/2025/07/ABF-217_b.jpg'
    assert result.detail_url == 'https://www.javhoo.com/abf-217'
    assert result.referer == 'https://www.javhoo.com/search/abf-217'
    assert seen_urls[0] == result.referer


def test_javhoo_does_not_treat_longer_prefix_as_exact_code_match():
    search_html = '''
    <html><body>
      <article>
        <h2><a href="/en/mifd-153">MIFD-153 Wrong Result</a></h2>
        <img src="https://pics.javhoo.net/mifd-153.jpg" />
      </article>
    </body></html>
    '''
    soup = BeautifulSoup(search_html, 'html.parser')
    provider = JavHooProvider(log=lambda *a, **k: None)

    detail_url = provider._find_detail_url(
        soup,
        'https://www.javhoo.com/search/fd-153',
        'fd-153',
    )

    assert detail_url == 'https://www.javhoo.com/fd-153'


def test_javhoo_does_not_accept_extra_numeric_detail_suffix():
    search_html = '''
    <html><body>
      <article>
        <h2><a href="/en/ntrd-021-2">NTRD-021-2 Wrong Result</a></h2>
        <img src="https://pics.javhoo.net/ntrd-021-2.jpg" />
      </article>
    </body></html>
    '''
    soup = BeautifulSoup(search_html, 'html.parser')
    provider = JavHooProvider(log=lambda *a, **k: None)

    detail_url = provider._find_detail_url(
        soup,
        'https://www.javhoo.com/search/ntrd-021',
        'ntrd-021',
    )

    assert detail_url == 'https://www.javhoo.com/ntrd-021'


def test_javhoo_keyword_search_opens_the_returned_candidate_detail():
    search_html = '''
    <html><body>
      <article>
        <h2><a href="/mird-876">MIRD-876 監禁凌辱作品 三浦亜沙妃</a></h2>
        <img src="https://pics.javhoo.net/mird-876.jpg" />
      </article>
    </body></html>
    '''
    soup = BeautifulSoup(search_html, 'html.parser')
    provider = JavHooProvider(log=lambda *a, **k: None)

    detail_url = provider._find_detail_url(
        soup,
        'https://www.javhoo.com/search/監禁凌辱作品',
        '監禁凌辱作品 三浦亜沙妃',
    )

    assert detail_url == 'https://www.javhoo.com/mird-876'


def test_javhoo_falls_back_to_direct_detail_when_search_page_returns_500():
    detail_html = '''
    <html><body>
      <h1>SONE-753 Detail Title</h1>
      <img class="alignnone size-full" alt="SONE-753" src="https://pics.javhoo.net/2026/01/SONE-753_b.jpg" />
    </body></html>
    '''

    provider = JavHooProvider(log=lambda *a, **k: None, session=None, anti_crawl=None, stop_requested=lambda: False)
    seen_urls = []

    def fake_request(url):
        seen_urls.append(url)
        if '/search/' in url:
            raise requests.exceptions.RetryError('too many 500 error responses')
        return DummyResponse(detail_html)

    provider._request = fake_request
    result = provider.search('SONE-753')

    assert result.ok is True
    assert result.query == 'SONE-753'
    assert result.title == 'SONE-753 Detail Title'
    assert result.image_url == 'https://pics.javhoo.net/2026/01/SONE-753_b.jpg'
    assert result.detail_url == 'https://www.javhoo.com/sone-753'
    assert result.referer == 'https://www.javhoo.com/search/SONE-753'
    assert seen_urls == [
        'https://www.javhoo.com/search/SONE-753',
        'https://www.javhoo.com/sone-753',
    ]


def test_javhoo_reports_server_error_when_search_and_detail_both_return_500():
    provider = JavHooProvider(log=lambda *a, **k: None, session=None, anti_crawl=None, stop_requested=lambda: False)
    seen_urls = []

    def fake_request(url):
        seen_urls.append(url)
        raise requests.exceptions.RetryError('too many 500 error responses')

    provider._request = fake_request
    result = provider.search('SONE-753')

    assert result.ok is False
    assert result.error_type == 'server-error'
    assert result.detail_url == 'https://www.javhoo.com/sone-753'
    assert 'detail fallback also failed' in result.message
    assert seen_urls == [
        'https://www.javhoo.com/search/SONE-753',
        'https://www.javhoo.com/sone-753',
    ]


def test_request_provider_creates_default_session_when_missing():
    provider = JavHooProvider(log=lambda *a, **k: None, session=None, anti_crawl=None, stop_requested=lambda: False)

    session = provider._get_session()

    assert session is provider.session
    assert session.headers.get('User-Agent')
    assert session.headers.get('Accept-Language') == 'ja,en-US;q=0.9,en;q=0.8'
    assert provider._request_timeout() == (8, 25)
    assert provider.retry_network_errors == 2


def test_javhoo_rejects_search_results_title_and_logo_without_detail_request():
    search_html = '''
    <html><head><title>Search Results    jbd-102 - JAVHOO</title></head><body>
      <img src="https://pics.javhoo.net/logo.png" />
      <article><h2><a href="/en/jbd-102">Search Results    jbd-102</a></h2></article>
    </body></html>
    '''

    provider = JavHooProvider(log=lambda *a, **k: None, session=None, anti_crawl=None, stop_requested=lambda: False)
    seen_urls = []

    def fake_request(url):
        seen_urls.append(url)
        if url.endswith('/en/jbd-102'):
            raise requests.exceptions.HTTPError('404 Client Error')
        return DummyResponse(search_html)

    provider._request = fake_request
    result = provider.search('jbd-102')

    assert result.ok is False
    assert result.error_type == 'invalid-result'
    assert result.title == 'Search Results    jbd-102'
    assert result.image_url == 'https://pics.javhoo.net/logo.png'
    assert 'search-results-title' in result.message
    assert 'placeholder-image' in result.message
    assert seen_urls == ['https://www.javhoo.com/search/jbd-102']


def test_javhoo_rejects_uniform_thumb_placeholder_even_with_valid_title():
    search_html = '''
    <html><body>
      <article>
        <h2><a href="/gana-3218">GANA-3218 Valid Looking Title</a></h2>
        <img src="https://pics.javhoo.net/thumb.png" />
      </article>
    </body></html>
    '''
    detail_html = '''
    <html><body>
      <h1>GANA-3218 Valid Looking Title</h1>
      <img src="https://pics.javhoo.net/thumb.png" />
    </body></html>
    '''
    provider = JavHooProvider(log=lambda *a, **k: None)
    provider._request = lambda url: DummyResponse(
        detail_html if url.endswith('/gana-3218') else search_html
    )

    result = provider.search('gana-3218')

    assert result.ok is False
    assert result.error_type == 'invalid-result'
    assert 'placeholder-image' in result.message


def test_request_provider_retries_transient_timeout_once():
    provider = JavHooProvider(log=lambda *a, **k: None, session=None, anti_crawl=None, stop_requested=lambda: False)
    provider.retry_network_errors = 1
    provider.retry_backoff = 0

    class FlakySession:
        def __init__(self):
            self.calls = []
            self.headers = {}
            from requests.cookies import RequestsCookieJar
            self.cookies = RequestsCookieJar()

        def get(self, url, timeout=None):
            self.calls.append((url, timeout))
            if len(self.calls) == 1:
                raise requests.exceptions.ReadTimeout('slow network')
            return DummyResponse('<html><head><title>OK</title></head><body><img src="https://pics.javhoo.net/ok.jpg"></body></html>')

    session = FlakySession()
    provider.session = session

    response = provider._request('https://www.javhoo.com/search/SONE-753')

    assert response.content
    assert session.calls == [
        ('https://www.javhoo.com/search/SONE-753', (8, 25)),
        ('https://www.javhoo.com/search/SONE-753', (8, 25)),
    ]
