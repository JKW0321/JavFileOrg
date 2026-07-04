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
    assert anti_session.calls == [('https://www.javbus.com/SONE-753', (5, 15))]
