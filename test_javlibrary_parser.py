#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_javlibrary_parser.py
=========================

纯解析层测试：不启动 Selenium，不访问网络。

覆盖：
1. 当前常见的 JAVLibrary 搜索结果列表页（videothumblist）
2. 旧版详情页（h3.post-title + #video_jacket_img）
3. 图片 URL 归一化

运行：
    pytest test_javlibrary_parser.py -v
"""
import os
import sys

import pytest
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from selenium_javlibrary import SeleniumJAVLibrary


@pytest.fixture
def scraper():
    return SeleniumJAVLibrary(headless=True)


def test_extract_search_results_page(scraper):
    html = '''
    <html><body>
      <div id="rightcolumn">
        <div class="boxtitle">"SSIS-001" 識別碼搜尋結果</div>
        <div class="videothumblist">
          <div class="videos">
            <div class="video">
              <a href="./javmezzbqu.html" title="SSIS-001 一ヶ月間の禁欲の果てに彼女のルームメイト2人と浮気SEXだけに没頭した彼女不在の3日間。 葵つかさ 乙白さやか">
                <div class="id">SSIS-001</div>
                <img src="https://pics.dmm.co.jp/mono/movie/adult/ssis001/ssis001ps.jpg" />
                <div class="title">一ヶ月間の禁欲の果てに彼女のルームメイト2人と浮気SEXだけに没頭した彼女不在の3日間。 葵つかさ 乙白さやか</div>
              </a>
            </div>
          </div>
        </div>
      </div>
    </body></html>
    '''
    soup = BeautifulSoup(html, 'html.parser')

    result = scraper._extract_result_from_soup(soup)

    assert result['title'].startswith('SSIS-001 ')
    assert '一ヶ月間の禁欲の果てに' in result['title']
    assert result['cover_url'] == 'https://pics.dmm.co.jp/mono/movie/adult/ssis001/ssis001ps.jpg'
    assert result['detail_url'] == 'https://www.javlibrary.com/tw/javmezzbqu.html'


def test_extract_detail_page(scraper):
    html = '''
    <html><body>
      <h3 class="post-title">ABF-139 美少女と、貸し切り温泉と、濃密性交と。</h3>
      <img id="video_jacket_img" src="//pics.example.com/abf139.jpg" />
      <span class="star">葵つかさ</span>
      <span class="star">乙白さやか</span>
    </body></html>
    '''
    soup = BeautifulSoup(html, 'html.parser')

    result = scraper._extract_result_from_soup(soup)

    assert result['title'] == 'ABF-139 美少女と、貸し切り温泉と、濃密性交と。'
    assert result['cover_url'] == 'https://pics.example.com/abf139.jpg'
    assert result['actors'] == ['葵つかさ', '乙白さやか']


def test_extract_detail_page_video_title_and_lazy_cover(scraper):
    html = '''
    <html><body>
      <div id="video_title">
        <h3><a href="./?v=javabc">JBD-101 蛇縛のレズリンチ 3</a></h3>
      </div>
      <img id="video_jacket_img" data-src="//pics.dmm.co.jp/mono/movie/adult/jbd101/jbd101pl.jpg" />
    </body></html>
    '''
    soup = BeautifulSoup(html, 'html.parser')

    result = scraper._extract_result_from_soup(soup, jav_id='jbd-101')

    assert result['title'] == 'JBD-101 蛇縛のレズリンチ 3'
    assert result['cover_url'] == 'https://pics.dmm.co.jp/mono/movie/adult/jbd101/jbd101pl.jpg'


def test_extract_search_results_prefers_matching_id(scraper):
    html = '''
    <html><body>
      <div class="videothumblist">
        <div class="video">
          <a href="./wrong.html" title="JBD-100 Wrong">
            <div class="id">JBD-100</div>
            <img src="//pics.example/jbd100.jpg" />
          </a>
        </div>
        <div class="video">
          <a href="./right.html" title="JBD-101 蛇縛のレズリンチ 3">
            <div class="id">JBD-101</div>
            <img data-original="//pics.example/jbd101.jpg" />
          </a>
        </div>
      </div>
    </body></html>
    '''
    soup = BeautifulSoup(html, 'html.parser')

    result = scraper._extract_result_from_soup(soup, jav_id='jbd-101')

    assert result['title'] == 'JBD-101 蛇縛のレズリンチ 3'
    assert result['cover_url'] == 'https://pics.example/jbd101.jpg'
    assert result['detail_url'] == 'https://www.javlibrary.com/tw/right.html'


def test_detects_cloudflare_attention_required_page(scraper):
    html = '<html><title>Attention Required! | Cloudflare</title><body>cf-ray you have been blocked</body></html>'

    assert scraper._is_verification_page('Attention Required! | Cloudflare', html) is True


def test_detects_please_wait_page_even_when_search_url_is_present(scraper):
    html = '''
    <html>
      <head><title>請稍候...</title></head>
      <body>
        <script>
          window.location.href = "/tw/vl_searchbyid.php?keyword=ABF-217";
        </script>
        <p>正在執行安全驗證</p>
      </body>
    </html>
    '''

    assert scraper._is_result_page(html) is False
    assert scraper._is_verification_page('請稍候...', html) is True


def test_please_wait_title_overrides_misleading_body_text(scraper):
    html = '''
    <html>
      <head><title>請稍候...</title></head>
      <body>
        <script>var start = Date.now();</script>
        <p>JAVLibrary is checking your browser before accessing vl_searchbyid.php.</p>
      </body>
    </html>
    '''

    assert scraper._is_result_page(html) is False
    assert scraper._is_verification_page('請稍候...', html) is True


def test_result_page_is_not_treated_as_verification(scraper):
    html = '''
    <html>
      <head><title>"ABF-217" 識別碼搜尋結果 - JAVLibrary</title></head>
      <body>
        <div class="videothumblist">
          <div class="video">
            <a href="./javabc.html" title="ABF-217 Real Title">
              <div class="id">ABF-217</div>
              <img src="//pics.example/abf217.jpg" />
            </a>
          </div>
        </div>
      </body>
    </html>
    '''

    assert scraper._is_result_page(html) is True
    assert scraper._is_verification_page('"ABF-217" 識別碼搜尋結果 - JAVLibrary', html) is False


def test_start_browser_falls_back_to_runtime_profile(monkeypatch, tmp_path):
    scraper = SeleniumJAVLibrary(headless=False)
    scraper.profile_dir = str(tmp_path / 'fixed_profile')
    runtime_profile = str(tmp_path / 'runtime_profile')
    scraper.cookies_file = str(tmp_path / 'missing_cookies.pkl')
    calls = []

    class FakeDriver:
        def execute_cdp_cmd(self, *args, **kwargs):
            return None

        def maximize_window(self):
            return None

    def fake_create_driver(user_data_dir):
        calls.append(user_data_dir)
        if user_data_dir == scraper.profile_dir:
            raise RuntimeError('session not created')
        return FakeDriver()

    monkeypatch.setattr(scraper, '_runtime_profile_dir', lambda: runtime_profile)
    monkeypatch.setattr(scraper, '_create_driver', fake_create_driver)

    assert scraper.start_browser() is True
    assert calls == [scraper.profile_dir, runtime_profile]


def test_start_browser_skips_locked_fixed_profile(monkeypatch, tmp_path):
    scraper = SeleniumJAVLibrary(headless=False)
    profile_dir = tmp_path / 'fixed_profile'
    profile_dir.mkdir()
    (profile_dir / 'SingletonLock').write_text('locked', encoding='utf-8')
    runtime_profile = str(tmp_path / 'runtime_profile')
    scraper.profile_dir = str(profile_dir)
    scraper.cookies_file = str(tmp_path / 'missing_cookies.pkl')
    calls = []

    class FakeDriver:
        def execute_cdp_cmd(self, *args, **kwargs):
            return None

        def maximize_window(self):
            return None

    monkeypatch.setattr(scraper, '_runtime_profile_dir', lambda: runtime_profile)
    monkeypatch.setattr(scraper, '_create_driver', lambda user_data_dir: calls.append(user_data_dir) or FakeDriver())

    assert scraper.start_browser() is True
    assert calls == [runtime_profile]


@pytest.mark.parametrize('raw,expected', [
    ('https://a/b.jpg', 'https://a/b.jpg'),
    ('//a/b.jpg', 'https://a/b.jpg'),
    ('/img/a.jpg', 'https://www.javlibrary.com/img/a.jpg'),
    ('', ''),
])
def test_normalize_cover_url(scraper, raw, expected):
    assert scraper._normalize_cover_url(raw) == expected
