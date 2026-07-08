#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from providers.javbus_provider import JavBusProvider


class DummyResponse:
    def __init__(self, html: str):
        self.content = html.encode('utf-8')

    def raise_for_status(self):
        return None


class RecordingSession:
    def __init__(self, html: str):
        self.html = html
        self.calls = []

    def get(self, url, timeout=None):
        self.calls.append((url, timeout))
        return DummyResponse(self.html)


class AntiCrawl:
    def __init__(self, session):
        self.session = session


def test_javbus_uses_anti_crawl_session_and_returns_audit_fields():
    html = '''
    <html><body>
      <h3>SONE-753 JavBus Title</h3>
      <a class="bigImage" href="/pics/cover.jpg">
        <img src="//pics.javbus.com/cover/sone753.jpg" />
      </a>
    </body></html>
    '''
    direct_session = RecordingSession('<html><body>wrong</body></html>')
    anti_session = RecordingSession(html)
    provider = JavBusProvider(
        log=lambda *a, **k: None,
        session=direct_session,
        anti_crawl=AntiCrawl(anti_session),
        stop_requested=lambda: False,
    )

    result = provider.search('SONE-753')

    assert result.ok is True
    assert result.provider == 'javbus'
    assert result.query == 'SONE-753'
    assert result.title == 'SONE-753 JavBus Title'
    assert result.image_url == 'https://pics.javbus.com/cover/sone753.jpg'
    assert result.detail_url == 'https://www.javbus.com/SONE-753'
    assert result.referer == 'https://www.javbus.com/SONE-753'
    assert direct_session.calls == []
    assert anti_session.calls == [('https://www.javbus.com/SONE-753', (5, 10))]


def test_javbus_rejects_age_verification_page():
    html = '<html><head><title>Age Verification JavBus</title></head><body></body></html>'
    provider = JavBusProvider(log=lambda *a, **k: None, session=RecordingSession(html))

    result = provider.search('ABF-217')

    assert result.ok is False
    assert result.error_type == 'invalid-result'
    assert result.message == 'javbus invalid result: age-verification-title,missing-image'


def test_javbus_rejects_missing_image():
    html = '<html><head><title>ABF-217 Valid Looking Title</title></head><body></body></html>'
    provider = JavBusProvider(log=lambda *a, **k: None, session=RecordingSession(html))

    result = provider.search('ABF-217')

    assert result.ok is False
    assert result.error_type == 'invalid-result'
    assert result.message == 'javbus invalid result: missing-image'
