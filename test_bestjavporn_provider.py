#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests

from providers.bestjavporn_provider import BestJavPornProvider
from providers.factory import create_provider


class DummyResponse:
    def __init__(self, html: str):
        self.content = html.encode('utf-8')

    def raise_for_status(self):
        return None


def test_bestjavporn_search_upgrades_to_detail_page():
    search_html = '''
    <html><body>
      <article>
        <h2><a href="/ja/video/abf-311-sample/">ABF-311 Search Title</a></h2>
        <img src="https://www.bestjavporn.com/logo.png" />
      </article>
    </body></html>
    '''
    detail_html = '''
    <html><head>
      <meta property="og:image" content="https://cdn.bestjavporn.com/covers/abf-311.jpg" />
    </head><body>
      <h1 class="entry-title">ABF-311 Detail Title</h1>
    </body></html>
    '''
    provider = BestJavPornProvider(log=lambda *a, **k: None, session=None, anti_crawl=None, stop_requested=lambda: False)
    seen_urls = []

    def fake_request(url):
        seen_urls.append(url)
        if '/ja/video/' in url:
            return DummyResponse(detail_html)
        return DummyResponse(search_html)

    provider._request = fake_request

    result = provider.search('ABF-311')

    assert result.ok is True
    assert result.provider == 'bestjavporn'
    assert result.query == 'ABF-311'
    assert result.title == 'ABF-311 Detail Title'
    assert result.image_url == 'https://cdn.bestjavporn.com/covers/abf-311.jpg'
    assert result.detail_url == 'https://www.bestjavporn.com/ja/video/abf-311-sample/'
    assert result.referer == 'https://www.bestjavporn.com/ja/?s=ABF-311'
    assert seen_urls == [
        'https://www.bestjavporn.com/ja/?s=ABF-311',
        'https://www.bestjavporn.com/ja/video/abf-311-sample/',
    ]


def test_bestjavporn_stop_after_search_response_returns_cancelled_before_detail_fetch():
    search_html = '''
    <html><body>
      <article>
        <h2><a href="/ja/video/abf-311-sample/">ABF-311 Search Title</a></h2>
        <img src="https://cdn.bestjavporn.com/covers/abf-311-small.jpg" />
      </article>
    </body></html>
    '''
    stopped = {'value': False}
    provider = BestJavPornProvider(
        log=lambda *a, **k: None,
        session=None,
        anti_crawl=None,
        stop_requested=lambda: stopped['value'],
    )
    seen_urls = []

    def fake_request(url):
        seen_urls.append(url)
        stopped['value'] = True
        return DummyResponse(search_html)

    provider._request = fake_request

    result = provider.search('ABF-311')

    assert result.ok is False
    assert result.error_type == 'cancelled'
    assert result.message == 'user stopped after network response'
    assert seen_urls == ['https://www.bestjavporn.com/ja/?s=ABF-311']


def test_bestjavporn_stop_during_network_request_returns_cancelled():
    stopped = {'value': False}
    provider = BestJavPornProvider(
        log=lambda *a, **k: None,
        session=None,
        anti_crawl=None,
        stop_requested=lambda: stopped['value'],
    )

    def fake_request(url):
        stopped['value'] = True
        raise requests.Timeout('read timed out')

    provider._request = fake_request

    result = provider.search('ABF-311')

    assert result.ok is False
    assert result.error_type == 'cancelled'
    assert result.message == 'user stopped during network request'


def test_bestjavporn_reports_cloudflare_verification_page():
    html = '''
    <!DOCTYPE html>
    <html><head><title>Just a moment...</title></head>
    <body>
      <script src="/cdn-cgi/challenge-platform/h/b/orchestrate/chl_page/v1"></script>
      <noscript>Enable JavaScript and cookies to continue</noscript>
    </body></html>
    '''
    provider = BestJavPornProvider(log=lambda *a, **k: None, session=None, anti_crawl=None, stop_requested=lambda: False)
    provider._request = lambda url: DummyResponse(html)

    result = provider.search('ABF-311')

    assert result.ok is False
    assert result.provider == 'bestjavporn'
    assert result.error_type == 'verification-required'
    assert 'Cloudflare verification' in result.message
    assert result.referer == 'https://www.bestjavporn.com/ja/?s=ABF-311'


def test_bestjavporn_rejects_placeholder_only_result():
    html = '''
    <html><head><title>Search Results for ABF-311</title></head><body>
      <article>
        <h2><a href="/ja/video/abf-311/">Search Results for ABF-311</a></h2>
        <img src="https://www.bestjavporn.com/assets/logo.png" />
      </article>
    </body></html>
    '''
    provider = BestJavPornProvider(log=lambda *a, **k: None, session=None, anti_crawl=None, stop_requested=lambda: False)
    provider._request = lambda url: DummyResponse(html)

    result = provider.search('ABF-311')

    assert result.ok is False
    assert result.error_type == 'invalid-result'
    assert 'generic-title' in result.message
    assert 'placeholder-image' in result.message


def test_factory_creates_bestjavporn_provider():
    provider = create_provider('bestjavporn', log=lambda *a, **k: None)

    assert isinstance(provider, BestJavPornProvider)
