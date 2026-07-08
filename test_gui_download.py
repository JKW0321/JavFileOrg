#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import tempfile
import threading
from pathlib import Path

import download_service
import jav_file_organizer as jfo_mod


class DummyResponse:
    def __init__(self, chunks, raise_error=None):
        self.chunks = chunks
        self.raise_error = raise_error

    def raise_for_status(self):
        if self.raise_error:
            raise self.raise_error

    def iter_content(self, chunk_size=1):
        return iter(self.chunks)


class FailingStreamResponse(DummyResponse):
    def iter_content(self, chunk_size=1):
        yield b'partial'
        raise RuntimeError('stream interrupted')


class RecordingSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.headers = {'User-Agent': 'UA'}

    def get(self, url, headers=None, timeout=None, stream=None):
        self.calls.append({
            'url': url,
            'headers': headers,
            'timeout': timeout,
            'stream': stream,
        })
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class AntiCrawl:
    def __init__(self, session):
        self.session = session


def make_downloader(session):
    obj = jfo_mod.JavFileOrganizer.__new__(jfo_mod.JavFileOrganizer)
    obj.session = session
    obj.anti_crawl = AntiCrawl(session)
    obj.stop_processing = False
    obj._stop_event = threading.Event()
    obj.logs = []
    obj.log = lambda message, level='INFO': obj.logs.append((level, message))
    return obj


def test_download_image_success_writes_chunks():
    session = RecordingSession([DummyResponse([b'ab', b'', b'cd'])])
    obj = make_downloader(session)

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / 'cover.jpg'
        ok = obj.download_image('http://example/cover.jpg', str(path), max_retries=1)

        assert ok is True
        assert path.read_bytes() == b'abcd'
        assert session.calls[0]['timeout'] == (8, 30)
        assert session.calls[0]['stream'] is True
        assert session.calls[0]['headers']['User-Agent'] == 'UA'


def test_download_image_respects_stop_signal_without_network_call():
    session = RecordingSession([DummyResponse([b'ab'])])
    obj = make_downloader(session)
    obj._request_stop()

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / 'cover.jpg'
        ok = obj.download_image('http://example/cover.jpg', str(path), max_retries=1)

        assert ok is False
        assert session.calls == []
        assert not path.exists()


def test_download_image_retry_cleans_partial_file(monkeypatch):
    session = RecordingSession([
        RuntimeError('network down'),
        DummyResponse([b'ok']),
    ])
    obj = make_downloader(session)
    sleeps = []
    monkeypatch.setattr(download_service.time, 'sleep', lambda seconds: sleeps.append(seconds))

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / 'cover.jpg'
        path.write_bytes(b'partial')
        ok = obj.download_image('http://example/cover.jpg', str(path), max_retries=2)

        assert ok is True
        assert path.read_bytes() == b'ok'
        assert len(session.calls) == 2
        assert sleeps == [0.25, 0.25, 0.25, 0.25]
        assert any('尝试 1/2' in message for _, message in obj.logs)


def test_download_image_final_failure_cleans_partial_file():
    session = RecordingSession([RuntimeError('network down')])
    obj = make_downloader(session)

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / 'cover.jpg'
        path.write_bytes(b'partial')
        ok = obj.download_image('http://example/cover.jpg', str(path), max_retries=1)

        assert ok is False
        assert not path.exists()
        assert any('所有候选均不可用' in message for _, message in obj.logs)


def test_download_image_retries_when_stream_breaks_mid_download(monkeypatch):
    session = RecordingSession([
        FailingStreamResponse([]),
        DummyResponse([b'complete']),
    ])
    obj = make_downloader(session)
    sleeps = []
    monkeypatch.setattr(download_service.time, 'sleep', lambda seconds: sleeps.append(seconds))

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / 'cover.jpg'
        ok = obj.download_image('http://example/cover.jpg', str(path), max_retries=2)

        assert ok is True
        assert path.read_bytes() == b'complete'
        assert len(session.calls) == 2
        assert sleeps == [0.25, 0.25, 0.25, 0.25]
        assert any('stream interrupted' in message for _, message in obj.logs)


def test_download_image_final_stream_failure_leaves_no_partial(monkeypatch):
    session = RecordingSession([FailingStreamResponse([])])
    obj = make_downloader(session)
    monkeypatch.setattr(download_service.time, 'sleep', lambda seconds: None)

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / 'cover.jpg'
        ok = obj.download_image('http://example/cover.jpg', str(path), max_retries=1)

        assert ok is False
        assert not path.exists()


def test_download_image_uses_provider_context_and_fallback_without_retrying_403(monkeypatch):
    session = RecordingSession([
        DummyResponse([], raise_error=RuntimeError('403 Client Error: Forbidden')),
        DummyResponse([b'fallback-ok']),
    ])
    obj = make_downloader(session)
    sleeps = []
    monkeypatch.setattr(download_service.time, 'sleep', lambda seconds: sleeps.append(seconds))

    image_task = {
        'image_url': 'https://cdn.example/primary.jpg',
        'fallback_images': ['https://cdn.example/fallback.jpg'],
        'referer': 'https://provider.example/detail/1',
        'provider': 'tokyo-hot',
    }
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / 'cover.jpg'
        ok = obj.download_image(image_task, str(path), max_retries=2)

        assert ok is True
        assert path.read_bytes() == b'fallback-ok'
        assert [call['url'] for call in session.calls] == [
            'https://cdn.example/primary.jpg',
            'https://cdn.example/fallback.jpg',
        ]
        assert all(call['headers']['Referer'] == 'https://provider.example/detail/1' for call in session.calls)
        assert all(call['headers']['Origin'] == 'https://provider.example' for call in session.calls)
        assert sleeps == []


def test_download_image_retry_wait_can_be_cancelled(monkeypatch):
    session = RecordingSession([
        RuntimeError('connection reset'),
        DummyResponse([b'should-not-run']),
    ])
    obj = make_downloader(session)
    sleeps = []

    def stop_during_sleep(seconds):
        sleeps.append(seconds)
        obj._request_stop()

    monkeypatch.setattr(download_service.time, 'sleep', stop_during_sleep)

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / 'cover.jpg'
        path.write_bytes(b'partial')
        ok = obj.download_image('http://example/cover.jpg', str(path), max_retries=2)

        assert ok is False
        assert len(session.calls) == 1
        assert sleeps == [0.25]
        assert not path.exists()
        assert any('重试等待期间收到停止请求' in message for _, message in obj.logs)


def test_connection_probe_downloads_with_provider_aware_image_task():
    class Provider:
        def search(self, query):
            return {
                'ok': True,
                'title': 'TOKYO-HOT n0839',
                'image_url': 'https://cdn.example/primary.jpg',
                'provider': 'uncensored',
                'detail_url': 'https://my.tokyo-hot.com/product/21087/',
                'referer': 'https://my.tokyo-hot.com/product/?q=n0839',
                'fallback_images': ['https://cdn.example/fallback.jpg'],
            }

    obj = jfo_mod.JavFileOrganizer.__new__(jfo_mod.JavFileOrganizer)
    obj._build_provider_factory = lambda: (lambda name: Provider())
    captured = []
    obj.download_image = lambda image_task, save_path, max_retries=3: captured.append(image_task) or True

    result = obj._run_connection_probe('uncensored', 'n0839')

    assert result['ok'] is True
    assert captured == [{
        'image_url': 'https://cdn.example/primary.jpg',
        'referer': 'https://my.tokyo-hot.com/product/?q=n0839',
        'detail_url': 'https://my.tokyo-hot.com/product/21087/',
        'provider': 'uncensored',
        'fallback_images': ['https://cdn.example/fallback.jpg'],
    }]
