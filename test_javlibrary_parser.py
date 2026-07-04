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


@pytest.mark.parametrize('raw,expected', [
    ('https://a/b.jpg', 'https://a/b.jpg'),
    ('//a/b.jpg', 'https://a/b.jpg'),
    ('/img/a.jpg', 'https://www.javlibrary.com/img/a.jpg'),
    ('', ''),
])
def test_normalize_cover_url(scraper, raw, expected):
    assert scraper._normalize_cover_url(raw) == expected
