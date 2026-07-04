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
        assert session.calls[0]['timeout'] == (10, 60)
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
        assert sleeps == [1]
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
        assert any('已重试 1 次' in message for _, message in obj.logs)
