#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from bs4 import BeautifulSoup

from providers.javhoo_provider import JavHooProvider


class DummyResponse:
    def __init__(self, html: str):
        self.content = html.encode('utf-8')


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
