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


def test_request_provider_creates_default_session_when_missing():
    provider = JavHooProvider(log=lambda *a, **k: None, session=None, anti_crawl=None, stop_requested=lambda: False)

    session = provider._get_session()

    assert session is provider.session
    assert session.headers.get('User-Agent')
    assert session.headers.get('Accept-Language') == 'ja,en-US;q=0.9,en;q=0.8'


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
