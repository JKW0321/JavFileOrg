#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from providers.javlibrary_provider import JavLibraryProvider


class DummySeleniumJavLibrary:
    def __init__(self, result, last_error_type='', last_error_message=''):
        self.result = result
        self.calls = []
        self.last_error_type = last_error_type
        self.last_error_message = last_error_message

    def search_by_id(self, query):
        self.calls.append(query)
        return self.result


class AntiCrawl:
    def __init__(self, selenium_javlibrary=None):
        self.selenium_javlibrary = selenium_javlibrary


def test_javlibrary_provider_success_returns_unified_audit_fields():
    selenium = DummySeleniumJavLibrary({
        'title': 'SSIS-001 JAVLibrary Title',
        'cover_url': 'https://pics.example/ssis001.jpg',
        'url': 'https://www.javlibrary.com/cn/?v=javmezzbqu',
    })
    provider = JavLibraryProvider(
        log=lambda *a, **k: None,
        anti_crawl=AntiCrawl(selenium),
        stop_requested=lambda: False,
    )

    result = provider.search('SSIS-001')

    assert result.ok is True
    assert result.provider == 'javlibrary'
    assert result.query == 'SSIS-001'
    assert result.title == 'SSIS-001 JAVLibrary Title'
    assert result.image_url == 'https://pics.example/ssis001.jpg'
    assert result.detail_url == 'https://www.javlibrary.com/cn/?v=javmezzbqu'
    assert result.referer == 'https://www.javlibrary.com/tw/vl_searchbyid.php?keyword=SSIS-001'
    assert result.raw_meta['cover_url'].endswith('ssis001.jpg')
    assert selenium.calls == ['SSIS-001']


def test_javlibrary_provider_uppercases_query_for_selenium_and_tw_referer():
    selenium = DummySeleniumJavLibrary({
        'title': 'JBD-101 蛇縛のレズリンチ 3',
        'cover_url': 'https://pics.example/jbd101.jpg',
        'detail_url': 'https://www.javlibrary.com/tw/?v=javexample',
    })
    provider = JavLibraryProvider(
        log=lambda *a, **k: None,
        anti_crawl=AntiCrawl(selenium),
        stop_requested=lambda: False,
    )

    result = provider.search('jbd-101')

    assert result.ok is True
    assert result.query == 'jbd-101'
    assert result.referer == 'https://www.javlibrary.com/tw/vl_searchbyid.php?keyword=JBD-101'
    assert selenium.calls == ['JBD-101']


def test_javlibrary_provider_stop_during_selenium_request_returns_cancelled():
    stop = {'value': False}

    class StopAfterSearchSelenium(DummySeleniumJavLibrary):
        def search_by_id(self, query):
            self.calls.append(query)
            stop['value'] = True
            return {
                'title': 'JBD-101 Title',
                'cover_url': 'https://pics.example/jbd101.jpg',
            }

    selenium = StopAfterSearchSelenium(None)
    provider = JavLibraryProvider(
        log=lambda *a, **k: None,
        anti_crawl=AntiCrawl(selenium),
        stop_requested=lambda: stop['value'],
    )

    result = provider.search('jbd-101')

    assert result.ok is False
    assert result.error_type == 'cancelled'
    assert result.message == 'user stopped during browser request'
    assert selenium.calls == ['JBD-101']


def test_javlibrary_provider_rejects_partial_selenium_result():
    selenium = DummySeleniumJavLibrary({
        'title': 'JBD-101 蛇縛のレズリンチ 3',
        'detail_url': 'https://www.javlibrary.com/tw/?v=javexample',
    })
    provider = JavLibraryProvider(
        log=lambda *a, **k: None,
        anti_crawl=AntiCrawl(selenium),
        stop_requested=lambda: False,
    )

    result = provider.search('jbd-101')

    assert result.ok is False
    assert result.error_type == 'parse-error'
    assert result.title == 'JBD-101 蛇縛のレズリンチ 3'
    assert result.image_url == ''
    assert 'missing title or cover_url' in result.message


def test_javlibrary_provider_preserves_selenium_failure_reason():
    selenium = DummySeleniumJavLibrary(
        None,
        last_error_type='verification-timeout',
        last_error_message='JAVLibrary verification timed out, title: 請稍候...',
    )
    provider = JavLibraryProvider(
        log=lambda *a, **k: None,
        anti_crawl=AntiCrawl(selenium),
        stop_requested=lambda: False,
    )

    result = provider.search('abf-217')

    assert result.ok is False
    assert result.error_type == 'verification-timeout'
    assert result.message == 'JAVLibrary verification timed out, title: 請稍候...'
    assert result.referer == 'https://www.javlibrary.com/tw/vl_searchbyid.php?keyword=ABF-217'


def test_javlibrary_provider_without_selenium_is_structured_failure():
    provider = JavLibraryProvider(
        log=lambda *a, **k: None,
        anti_crawl=AntiCrawl(None),
        stop_requested=lambda: False,
    )

    result = provider.search('SSIS-001')

    assert result.ok is False
    assert result.provider == 'javlibrary'
    assert result.query == 'SSIS-001'
    assert result.referer == 'https://www.javlibrary.com/tw/vl_searchbyid.php?keyword=SSIS-001'
    assert result.error_type == 'provider-error'
