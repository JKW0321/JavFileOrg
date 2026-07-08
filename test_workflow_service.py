#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Workflow service tests."""
import tempfile
import json
from pathlib import Path

from PIL import Image

from atomic_processor_v11 import AtomicProcessor
from filename_utils import clean_filename_for_search, extract_series_info
from workflow_service import WorkflowService


class DummyProvider:
    def __init__(self, title_prefix='TITLE'):
        self.title_prefix = title_prefix
        self.calls = []

    def search(self, query):
        self.calls.append(query)
        return {
            'ok': True,
            'title': f'{query.upper()} {self.title_prefix}',
            'image_url': 'http://example/image.jpg',
            'provider': 'dummy',
            'detail_url': f'http://example/detail/{query}',
            'referer': f'http://example/search/{query}',
            'error_type': None,
            'message': None,
        }


class FailingProvider:
    def __init__(self):
        self.calls = []

    def search(self, query):
        self.calls.append(query)
        return {
            'ok': False,
            'title': f'Search Results    {query}',
            'image_url': 'https://pics.javhoo.net/logo.png',
            'provider': 'javhoo',
            'detail_url': f'https://www.javhoo.com/{query.lower()}',
            'referer': f'https://www.javhoo.com/search/{query}',
            'error_type': 'invalid-result',
            'message': 'javhoo invalid result: search-results-title,placeholder-image',
        }


class VerificationThenSuccessProvider:
    def __init__(self):
        self.calls = []

    def search(self, query):
        self.calls.append(query)
        if len(self.calls) == 1:
            return {
                'ok': False,
                'title': None,
                'image_url': None,
                'provider': 'javlibrary',
                'detail_url': None,
                'referer': f'https://www.javlibrary.com/tw/vl_searchbyid.php?keyword={query}',
                'error_type': 'verification-timeout',
                'message': 'JAVLibrary verification timed out, title: 請稍候...',
            }
        return {
            'ok': True,
            'title': 'JBD-131 プライベート調教ドキュメント 真性M奴隷日記',
            'image_url': 'http://example/jbd131.jpg',
            'provider': 'javlibrary',
            'detail_url': 'https://www.javlibrary.com/tw/?v=javjbd131',
            'referer': f'https://www.javlibrary.com/tw/vl_searchbyid.php?keyword={query}',
            'error_type': None,
            'message': None,
        }


def _download(url, dest):
    Image.new('RGB', (1, 1), color=(255, 100, 50)).save(dest, 'JPEG')
    return True


def _sanitize(name):
    return name


def _series_info(stem):
    if stem.startswith('ABF-139-1'):
        return ('ABF-139', '1')
    if stem.startswith('ABF-139-2'):
        return ('ABF-139', '2')
    return (None, None)


def _detect_series_from_filename_utils(files):
    series_groups = {}
    standalone = []
    for file_path in files:
        base, sequence = extract_series_info(Path(file_path).stem)
        if base:
            series_groups.setdefault(base, []).append((file_path, sequence))
        else:
            standalone.append(file_path)
    for base in series_groups:
        series_groups[base].sort(key=lambda item: int(item[1]))
    return series_groups, standalone


def test_workflow_dry_run_keeps_source_files():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        logs = root / 'JFO_Logs'
        (root / 'ABF-139-1.mp4').write_bytes(b'a' * 32768)
        (root / 'SONE-753.mp4').write_bytes(b'b' * 32768)
        provider = DummyProvider()
        svc = WorkflowService(
            log=lambda *a, **k: None,
            provider_factory=lambda name: provider,
            atomic_processor=AtomicProcessor(_download, _sanitize),
            clean_filename_for_search=lambda n: Path(n).stem.lower(),
            sanitize_filename=_sanitize,
            detect_series_files=lambda files: ({}, files),
            smart_truncate_filename=lambda title, original, max_length: title,
            stop_requested=lambda: False,
            minimum_video_size_bytes=16384,
        )
        result = svc.run(
            folder_path=str(root),
            finish_folder=str(root / 'Finish'),
            website='javhoo',
            max_length=None,
            batch_count=None,
            dry_run=True,
            logs_dir=str(logs),
        )
        assert result['planned_count'] == 2
        assert (root / 'ABF-139-1.mp4').exists()
        assert (root / 'SONE-753.mp4').exists()
        assert not (root / 'Finish').exists()
        assert result['file_results_path']
        file_results = json.loads(Path(result['file_results_path']).read_text(encoding='utf-8'))
        assert file_results['dry_run'] is True
        assert file_results['counts']['planned'] == 2
        assert {item['status'] for item in file_results['results']} == {'planned'}
        assert {item['source_name'] for item in file_results['results']} == {'ABF-139-1.mp4', 'SONE-753.mp4'}
        assert all(item['provider'] == 'javhoo' for item in file_results['results'])
        assert all(item['detail_url'] is None for item in file_results['results'])
        summary = json.loads(Path(result['summary_path']).read_text(encoding='utf-8'))
        assert summary['counts']['planned_count'] == 2
        assert summary['counts']['file_result_counts'] == {'planned': 2}


def test_workflow_treats_underscore_suffix_as_series_sequence():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        logs = root / 'JFO_Logs'
        f1 = root / 'MIRD-277_1.mp4'
        f3 = root / 'MIRD-277_3.mp4'
        f1.write_bytes(b'a' * 32768)
        f3.write_bytes(b'b' * 32768)
        provider = DummyProvider()
        svc = WorkflowService(
            log=lambda *a, **k: None,
            provider_factory=lambda name: provider,
            atomic_processor=AtomicProcessor(_download, _sanitize),
            clean_filename_for_search=clean_filename_for_search,
            sanitize_filename=_sanitize,
            detect_series_files=_detect_series_from_filename_utils,
            smart_truncate_filename=lambda title, original, max_length: title,
            stop_requested=lambda: False,
            minimum_video_size_bytes=16384,
        )
        result = svc.run(
            folder_path=str(root),
            finish_folder=str(root / 'Finish'),
            website='javbus',
            dry_run=False,
            logs_dir=str(logs),
        )

        assert provider.calls == ['MIRD-277']
        assert result['success_count'] == 2
        assert result['failed_count'] == 0
        assert not f1.exists()
        assert not f3.exists()
        file_results = json.loads(Path(result['file_results_path']).read_text(encoding='utf-8'))
        assert {item['group'] for item in file_results['results']} == {'MIRD-277'}
        assert {item['sequence'] for item in file_results['results']} == {'1', '3'}


def test_workflow_run_summary_uses_injected_app_version():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        logs = root / 'JFO_Logs'
        (root / 'SONE-753.mp4').write_bytes(b'a' * 32768)
        provider = DummyProvider()
        svc = WorkflowService(
            log=lambda *a, **k: None,
            provider_factory=lambda name: provider,
            atomic_processor=AtomicProcessor(_download, _sanitize),
            clean_filename_for_search=clean_filename_for_search,
            sanitize_filename=_sanitize,
            detect_series_files=lambda files: ({}, files),
            smart_truncate_filename=lambda title, original, max_length: title,
            stop_requested=lambda: False,
            minimum_video_size_bytes=16384,
            app_version='v1.5.4',
        )
        result = svc.run(
            folder_path=str(root),
            finish_folder=str(root / 'Finish'),
            website='javhoo',
            dry_run=True,
            logs_dir=str(logs),
        )

        summary = json.loads(Path(result['summary_path']).read_text(encoding='utf-8'))
        assert summary['version'] == 'v1.5.4'


def test_workflow_writes_filename_rule_candidates():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        logs = root / 'JFO_Logs'
        (root / 'FC2-PPV-1234567.mp4').write_bytes(b'a' * 32768)
        (root / 'STUDIOX-20260705-001.mp4').write_bytes(b'b' * 32768)
        provider = DummyProvider()
        svc = WorkflowService(
            log=lambda *a, **k: None,
            provider_factory=lambda name: provider,
            atomic_processor=AtomicProcessor(_download, _sanitize),
            clean_filename_for_search=lambda n: Path(n).stem.lower(),
            sanitize_filename=_sanitize,
            detect_series_files=lambda files: ({}, files),
            smart_truncate_filename=lambda title, original, max_length: title,
            stop_requested=lambda: False,
            minimum_video_size_bytes=16384,
        )
        result = svc.run(
            folder_path=str(root),
            finish_folder=str(root / 'Finish'),
            website='javhoo',
            dry_run=True,
            logs_dir=str(logs),
        )

        assert result['filename_rule_candidates_path']
        payload = json.loads(Path(result['filename_rule_candidates_path']).read_text(encoding='utf-8'))
        assert payload['counts']['total'] == 2
        assert payload['counts']['auto_usable'] == 1
        assert payload['counts']['needs_review'] == 1
        assert {item['rule_id'] for item in payload['candidates']} == {
            'fc2_ppv',
            'generic_multi_segment',
        }
        summary = json.loads(Path(result['summary_path']).read_text(encoding='utf-8'))
        assert summary['artifacts']['filename_rule_candidates_path'] == result['filename_rule_candidates_path']


def test_workflow_skips_low_confidence_filename_rule_candidate():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        logs = root / 'JFO_Logs'
        (root / 'STUDIOX-20260705-001.mp4').write_bytes(b'a' * 32768)
        provider = DummyProvider()
        svc = WorkflowService(
            log=lambda *a, **k: None,
            provider_factory=lambda name: provider,
            atomic_processor=AtomicProcessor(_download, _sanitize),
            clean_filename_for_search=clean_filename_for_search,
            sanitize_filename=_sanitize,
            detect_series_files=lambda files: ({}, files),
            smart_truncate_filename=lambda title, original, max_length: title,
            stop_requested=lambda: False,
            minimum_video_size_bytes=16384,
        )
        result = svc.run(
            folder_path=str(root),
            finish_folder=str(root / 'Finish'),
            website='javhoo',
            dry_run=False,
            logs_dir=str(logs),
        )

        assert provider.calls == []
        assert result['needs_review_count'] == 1
        assert (root / 'STUDIOX-20260705-001.mp4').exists()
        file_results = json.loads(Path(result['file_results_path']).read_text(encoding='utf-8'))
        assert file_results['counts']['needs_review'] == 1
        item = file_results['results'][0]
        assert item['status'] == 'needs_review'
        assert item['filename_rule_candidate']['rule_id'] == 'generic_multi_segment'


def test_workflow_reuses_provider_result_for_duplicate_query():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        logs = root / 'JFO_Logs'
        (root / 'SONE-753 first.mp4').write_bytes(b'a' * 32768)
        (root / 'SONE-753 second.mp4').write_bytes(b'b' * 32768)
        provider = DummyProvider()
        svc = WorkflowService(
            log=lambda *a, **k: None,
            provider_factory=lambda name: provider,
            atomic_processor=AtomicProcessor(_download, _sanitize),
            clean_filename_for_search=clean_filename_for_search,
            sanitize_filename=_sanitize,
            detect_series_files=lambda files: ({}, files),
            smart_truncate_filename=lambda title, original, max_length: title,
            stop_requested=lambda: False,
            minimum_video_size_bytes=16384,
        )
        result = svc.run(
            folder_path=str(root),
            finish_folder=str(root / 'Finish'),
            website='javhoo',
            dry_run=False,
            logs_dir=str(logs),
        )

    assert provider.calls == ['sone-753']
    assert result['success_count'] == 2


def test_workflow_series_provider_invalid_result_keeps_sources_and_audit():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        logs = root / 'JFO_Logs'
        log_entries = []
        f1 = root / 'jbd131-1.mp4'
        f2 = root / 'jbd131-2.mp4'
        f1.write_bytes(b'a' * 32768)
        f2.write_bytes(b'b' * 32768)
        provider = FailingProvider()
        svc = WorkflowService(
            log=lambda message, level='INFO': log_entries.append((level, message)),
            provider_factory=lambda name: provider,
            atomic_processor=AtomicProcessor(_download, _sanitize),
            clean_filename_for_search=clean_filename_for_search,
            sanitize_filename=_sanitize,
            detect_series_files=lambda files: ({'JBD-131': [(str(f1), '1'), (str(f2), '2')]}, []),
            smart_truncate_filename=lambda title, original, max_length: title,
            stop_requested=lambda: False,
            minimum_video_size_bytes=16384,
        )

        result = svc.run(
            folder_path=str(root),
            finish_folder=str(root / 'Finish'),
            website='javhoo',
            dry_run=False,
            logs_dir=str(logs),
        )

        assert result['failed_count'] == 2
        assert provider.calls == ['JBD-131']
        assert f1.exists()
        assert f2.exists()
        assert not (root / 'Finish').exists()
        file_results = json.loads(Path(result['file_results_path']).read_text(encoding='utf-8'))
        failures = [item for item in file_results['results'] if item['status'] == 'failed']
        assert len(failures) == 2
        assert all(item['title'] == 'Search Results    JBD-131' for item in failures)
        assert all(item['image_url'] == 'https://pics.javhoo.net/logo.png' for item in failures)
        assert all(item['target_video_path'] is None for item in failures)
        assert all(item['target_image_path'] is None for item in failures)
        log_text = '\n'.join(message for _, message in log_entries)
        assert '未处理: 序列组 JBD-131 | files=2 | provider=javhoo | query=JBD-131' in log_text
        assert 'provider:invalid-result:javhoo invalid result' in log_text
        assert '源文件保持原样' in log_text
        assert '返回标题: Search Results    JBD-131' in log_text
        assert '返回图片: https://pics.javhoo.net/logo.png' in log_text


def test_workflow_retries_verification_timeout_for_series_before_failing():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        logs = root / 'JFO_Logs'
        f1 = root / 'jbd131-1.mp4'
        f2 = root / 'jbd131-2.mp4'
        f1.write_bytes(b'a' * 32768)
        f2.write_bytes(b'b' * 32768)
        provider = VerificationThenSuccessProvider()
        log_entries = []
        progress = []
        svc = WorkflowService(
            log=lambda message, level='INFO': log_entries.append((level, message)),
            provider_factory=lambda name: provider,
            atomic_processor=AtomicProcessor(_download, _sanitize),
            clean_filename_for_search=clean_filename_for_search,
            sanitize_filename=_sanitize,
            detect_series_files=lambda files: ({'JBD-131': [(str(f1), '1'), (str(f2), '2')]}, []),
            smart_truncate_filename=lambda title, original, max_length: title,
            stop_requested=lambda: False,
            minimum_video_size_bytes=16384,
            progress_callback=lambda completed, total, label='': progress.append((completed, total, label)),
        )

        result = svc.run(
            folder_path=str(root),
            finish_folder=str(root / 'Finish'),
            website='javlibrary',
            dry_run=False,
            logs_dir=str(logs),
        )

        assert provider.calls == ['JBD-131', 'JBD-131']
        assert result['success_count'] == 2
        assert result['failed_count'] == 0
        assert progress[-1] == (2, 2, '序列组 JBD-131')
        log_text = '\n'.join(message for _, message in log_entries)
        assert '遇到可重试的临时错误，重试一次: JBD-131' in log_text
        assert not f1.exists()
        assert not f2.exists()


def test_provider_search_cache_keeps_metadata():
    provider = DummyProvider()
    svc = WorkflowService(
        log=lambda *a, **k: None,
        provider_factory=lambda name: provider,
        atomic_processor=AtomicProcessor(_download, _sanitize),
        clean_filename_for_search=clean_filename_for_search,
        sanitize_filename=_sanitize,
        detect_series_files=lambda files: ({}, files),
        smart_truncate_filename=lambda title, original, max_length: title,
        stop_requested=lambda: False,
    )
    cache = {}

    first = svc._provider_search(cache, 'javhoo', provider, 'sone-753')
    second = svc._provider_search(cache, 'javhoo', provider, 'sone-753')

    assert first is second
    assert provider.calls == ['sone-753']
    entry = cache[('javhoo', 'sone-753')]
    assert entry['provider'] == 'javhoo'
    assert entry['query'] == 'sone-753'
    assert entry['timestamp']
    assert entry['source_url'] == 'http://example/search/sone-753'
    assert entry['result'] is first


def test_provider_search_does_not_cache_retryable_failures():
    class AlwaysVerificationFailureProvider:
        def __init__(self):
            self.calls = []

        def search(self, query):
            self.calls.append(query)
            return {
                'ok': False,
                'title': None,
                'image_url': None,
                'provider': 'javlibrary',
                'detail_url': None,
                'referer': f'https://www.javlibrary.com/tw/vl_searchbyid.php?keyword={query}',
                'error_type': 'verification-timeout',
                'message': 'verification timed out',
            }

    provider = AlwaysVerificationFailureProvider()
    svc = WorkflowService(
        log=lambda *a, **k: None,
        provider_factory=lambda name: provider,
        atomic_processor=AtomicProcessor(_download, _sanitize),
        clean_filename_for_search=clean_filename_for_search,
        sanitize_filename=_sanitize,
        detect_series_files=lambda files: ({}, files),
        smart_truncate_filename=lambda title, original, max_length: title,
        stop_requested=lambda: False,
    )
    cache = {}

    svc._provider_search(cache, 'javlibrary', provider, 'JBD-131')
    svc._provider_search(cache, 'javlibrary', provider, 'JBD-131')

    assert provider.calls == ['JBD-131', 'JBD-131', 'JBD-131', 'JBD-131']
    assert cache == {}


def test_provider_search_does_not_retry_verification_required_immediately():
    class VerificationRequiredProvider:
        def __init__(self):
            self.calls = []

        def search(self, query):
            self.calls.append(query)
            return {
                'ok': False,
                'title': None,
                'image_url': None,
                'provider': 'bestjavporn',
                'detail_url': None,
                'referer': f'https://www.bestjavporn.com/ja/?s={query}',
                'error_type': 'verification-required',
                'message': 'Cloudflare verification page',
            }

    provider = VerificationRequiredProvider()
    logs = []
    svc = WorkflowService(
        log=lambda message, level='INFO': logs.append((level, message)),
        provider_factory=lambda name: provider,
        atomic_processor=AtomicProcessor(_download, _sanitize),
        clean_filename_for_search=clean_filename_for_search,
        sanitize_filename=_sanitize,
        detect_series_files=lambda files: ({}, files),
        smart_truncate_filename=lambda title, original, max_length: title,
        stop_requested=lambda: False,
    )
    cache = {}

    result = svc._provider_search(cache, 'bestjavporn', provider, 'ABF-311')

    assert result['error_type'] == 'verification-required'
    assert provider.calls == ['ABF-311']
    assert cache == {}
    assert not any('重试一次' in message for _, message in logs)


def test_provider_search_retries_transient_network_error_once():
    class FlakyNetworkProvider:
        def __init__(self):
            self.calls = []

        def search(self, query):
            self.calls.append(query)
            if len(self.calls) == 1:
                return {
                    'ok': False,
                    'title': None,
                    'image_url': None,
                    'provider': 'javhoo',
                    'detail_url': None,
                    'referer': None,
                    'error_type': 'network-error',
                    'message': 'connection reset by peer',
                }
            return {
                'ok': True,
                'title': 'ABF-217 TITLE',
                'image_url': 'http://example/image.jpg',
                'provider': 'javhoo',
                'detail_url': 'http://example/detail',
                'referer': 'http://example/search',
                'error_type': None,
                'message': None,
            }

    provider = FlakyNetworkProvider()
    svc = WorkflowService(
        log=lambda *a, **k: None,
        provider_factory=lambda name: provider,
        atomic_processor=AtomicProcessor(_download, _sanitize),
        clean_filename_for_search=clean_filename_for_search,
        sanitize_filename=_sanitize,
        detect_series_files=lambda files: ({}, files),
        smart_truncate_filename=lambda title, original, max_length: title,
        stop_requested=lambda: False,
    )
    cache = {}

    result = svc._provider_search(cache, 'javhoo', provider, 'ABF-217')

    assert result['ok'] is True
    assert provider.calls == ['ABF-217', 'ABF-217']
    assert ('javhoo', 'ABF-217') in cache


def test_provider_search_does_not_retry_non_transient_network_error():
    class ForbiddenProvider:
        def __init__(self):
            self.calls = []

        def search(self, query):
            self.calls.append(query)
            return {
                'ok': False,
                'title': None,
                'image_url': None,
                'provider': 'uncensored',
                'detail_url': None,
                'referer': None,
                'error_type': 'network-error',
                'message': '403 Client Error: Forbidden',
            }

    provider = ForbiddenProvider()
    svc = WorkflowService(
        log=lambda *a, **k: None,
        provider_factory=lambda name: provider,
        atomic_processor=AtomicProcessor(_download, _sanitize),
        clean_filename_for_search=clean_filename_for_search,
        sanitize_filename=_sanitize,
        detect_series_files=lambda files: ({}, files),
        smart_truncate_filename=lambda title, original, max_length: title,
        stop_requested=lambda: False,
    )
    cache = {}

    result = svc._provider_search(cache, 'uncensored', provider, '300MIUM-1366')

    assert result['error_type'] == 'network-error'
    assert provider.calls == ['300MIUM-1366']
    assert cache == {}


def test_workflow_cancelled_files_are_audited():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        logs = root / 'JFO_Logs'
        (root / 'SONE-753.mp4').write_bytes(b'a' * 32768)
        (root / 'ABF-139.mp4').write_bytes(b'b' * 32768)
        provider = DummyProvider()
        svc = WorkflowService(
            log=lambda *a, **k: None,
            provider_factory=lambda name: provider,
            atomic_processor=AtomicProcessor(_download, _sanitize),
            clean_filename_for_search=clean_filename_for_search,
            sanitize_filename=_sanitize,
            detect_series_files=lambda files: ({}, files),
            smart_truncate_filename=lambda title, original, max_length: title,
            stop_requested=lambda: True,
            minimum_video_size_bytes=16384,
        )
        result = svc.run(
            folder_path=str(root),
            finish_folder=str(root / 'Finish'),
            website='javhoo',
            dry_run=False,
            logs_dir=str(logs),
        )

        assert result['cancelled_count'] == 2
        assert provider.calls == []
        file_results = json.loads(Path(result['file_results_path']).read_text(encoding='utf-8'))
        assert file_results['counts']['cancelled'] == 2
        assert {item['source_name'] for item in file_results['results']} == {'SONE-753.mp4', 'ABF-139.mp4'}


def test_workflow_all_filtered_files_still_write_audit():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        logs = root / 'JFO_Logs'
        (root / '._ABF-139.mp4').write_bytes(b'a' * 32768)
        (root / 'tiny.mp4').write_bytes(b'b')
        svc = WorkflowService(
            log=lambda *a, **k: None,
            provider_factory=lambda name: DummyProvider(),
            atomic_processor=AtomicProcessor(_download, _sanitize),
            clean_filename_for_search=clean_filename_for_search,
            sanitize_filename=_sanitize,
            detect_series_files=lambda files: ({}, files),
            smart_truncate_filename=lambda title, original, max_length: title,
            stop_requested=lambda: False,
            minimum_video_size_bytes=16384,
        )
        result = svc.run(
            folder_path=str(root),
            finish_folder=str(root / 'Finish'),
            website='javhoo',
            dry_run=False,
            logs_dir=str(logs),
        )

        assert result['total_files'] == 0
        assert result['file_results_path']
        file_results = json.loads(Path(result['file_results_path']).read_text(encoding='utf-8'))
        assert file_results['counts'] == {'skipped': 2}
        assert {item['reason'] for item in file_results['results']} == {'hidden-file', 'small-video'}


def test_workflow_series_uses_atomic_group_processing():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        finish = root / 'Finish'
        logs = root / 'JFO_Logs'
        finish.mkdir()
        f1 = root / 'ABF-139-1.mp4'
        f2 = root / 'ABF-139-2.mp4'
        f1.write_bytes(b'a' * 32768)
        f2.write_bytes(b'b' * 32768)
        provider = DummyProvider('SERIES')
        svc = WorkflowService(
            log=lambda *a, **k: None,
            provider_factory=lambda name: provider,
            atomic_processor=AtomicProcessor(_download, _sanitize),
            clean_filename_for_search=lambda n: Path(n).stem.lower(),
            sanitize_filename=_sanitize,
            detect_series_files=lambda files: ({'ABF-139': [(str(f1), '1'), (str(f2), '2')]}, []),
            smart_truncate_filename=lambda title, original, max_length: title,
            stop_requested=lambda: False,
            minimum_video_size_bytes=16384,
        )
        result = svc.run(
            folder_path=str(root),
            finish_folder=str(finish),
            website='javhoo',
            max_length=None,
            batch_count=None,
            dry_run=False,
            logs_dir=str(logs),
        )
        assert result['success_count'] == 2
        assert (finish / 'ABF-139 SERIES-1.mp4').exists()
        assert (finish / 'ABF-139 SERIES-2.mp4').exists()
        assert (finish / 'ABF-139 SERIES.jpg').exists()
        file_results = json.loads(Path(result['file_results_path']).read_text(encoding='utf-8'))
        assert file_results['counts']['success'] == 2
        assert {item['status'] for item in file_results['results']} == {'success'}
        assert all(item['group'] == 'ABF-139' for item in file_results['results'])
        assert all(item['target_image_path'].endswith('ABF-139 SERIES.jpg') for item in file_results['results'])
        assert all(item['detail_url'] == 'http://example/detail/ABF-139' for item in file_results['results'])
        assert all(item['referer'] == 'http://example/search/ABF-139' for item in file_results['results'])
        assert all(item['image_downloaded'] is True for item in file_results['results'])
        assert file_results['timings']['providers']['javhoo']['count'] == 2
        assert file_results['timings']['providers']['javhoo']['status_counts'] == {'success': 2}
        assert file_results['timings']['providers']['javhoo']['metrics']['provider_elapsed_seconds']['count'] == 2
        assert result['image_success_count'] == 1
        summary = json.loads(Path(result['summary_path']).read_text(encoding='utf-8'))
        assert summary['counts']['success_count'] == 2
        assert summary['counts']['image_success_count'] == 1
        assert summary['counts']['file_result_counts'] == {'success': 2}
        assert summary['timings']['providers']['javhoo']['count'] == 2
        assert summary['timings']['slowest_files']


def test_workflow_file_results_record_provider_failure():
    class FailingProvider:
        def search(self, query):
            return {
                'ok': False,
                'title': None,
                'image_url': None,
                'provider': 'dummy',
                'detail_url': None,
                'referer': None,
                'error_type': 'not-found',
                'message': 'missing',
            }

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        finish = root / 'Finish'
        logs = root / 'JFO_Logs'
        (root / 'SONE-753.mp4').write_bytes(b'a' * 32768)
        svc = WorkflowService(
            log=lambda *a, **k: None,
            provider_factory=lambda name: FailingProvider(),
            atomic_processor=AtomicProcessor(_download, _sanitize),
            clean_filename_for_search=lambda n: Path(n).stem.lower(),
            sanitize_filename=_sanitize,
            detect_series_files=lambda files: ({}, files),
            smart_truncate_filename=lambda title, original, max_length: title,
            stop_requested=lambda: False,
            minimum_video_size_bytes=16384,
        )
        result = svc.run(
            folder_path=str(root),
            finish_folder=str(finish),
            website='javhoo',
            dry_run=False,
            logs_dir=str(logs),
        )
        assert result['failed_count'] == 1
        assert (root / 'SONE-753.mp4').exists()
        file_results = json.loads(Path(result['file_results_path']).read_text(encoding='utf-8'))
        assert file_results['counts']['failed'] == 1
        item = file_results['results'][0]
        assert item['status'] == 'failed'
        assert item['reason'] == 'provider:not-found:missing'
        assert item['source_name'] == 'SONE-753.mp4'
        summary = json.loads(Path(result['summary_path']).read_text(encoding='utf-8'))
        assert summary['counts']['failed_count'] == 1
        assert summary['counts']['file_result_counts'] == {'failed': 1}


def test_workflow_uncensored_network_error_keeps_source_and_audit():
    class NetworkFailingUncensoredProvider:
        def __init__(self):
            self.calls = []

        def search(self, query):
            self.calls.append(query)
            return {
                'ok': False,
                'title': None,
                'image_url': None,
                'provider': 'uncensored',
                'detail_url': 'https://www.heyzo.com/moviepages/3098/index.html',
                'referer': 'https://www.heyzo.com/moviepages/3098/index.html',
                'error_type': 'network-error',
                'message': 'read timed out',
            }

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        finish = root / 'Finish'
        logs = root / 'JFO_Logs'
        source = root / 'HEYZO-HD-3098.mp4'
        source.write_bytes(b'a' * 32768)
        provider = NetworkFailingUncensoredProvider()
        svc = WorkflowService(
            log=lambda *a, **k: None,
            provider_factory=lambda name: provider,
            atomic_processor=AtomicProcessor(_download, _sanitize),
            clean_filename_for_search=clean_filename_for_search,
            sanitize_filename=_sanitize,
            detect_series_files=lambda files: ({}, files),
            smart_truncate_filename=lambda title, original, max_length: title,
            stop_requested=lambda: False,
            minimum_video_size_bytes=16384,
        )

        result = svc.run(
            folder_path=str(root),
            finish_folder=str(finish),
            website='uncensored',
            dry_run=False,
            logs_dir=str(logs),
        )

        assert result['failed_count'] == 1
        assert source.exists()
        assert not finish.exists()
        assert provider.calls == ['heyzo-3098', 'heyzo-3098']
        file_results = json.loads(Path(result['file_results_path']).read_text(encoding='utf-8'))
        item = file_results['results'][0]
        assert item['status'] == 'failed'
        assert item['provider'] == 'uncensored'
        assert item['query'] == 'heyzo-3098'
        assert item['reason'] == 'provider:network-error:read timed out'
        assert item['detail_url'] == 'https://www.heyzo.com/moviepages/3098/index.html'


def test_workflow_passes_provider_aware_image_request_to_atomic_processor():
    class ProviderWithFallbackImage:
        def search(self, query):
            return {
                'ok': True,
                'title': 'TOKYO-HOT-N0839 TITLE',
                'image_url': 'https://cdn.example/primary.jpg',
                'fallback_images': ['https://cdn.example/fallback.jpg'],
                'provider': 'uncensored',
                'detail_url': 'https://my.tokyo-hot.com/product/21087/',
                'referer': 'https://my.tokyo-hot.com/product/?q=n0839',
                'error_type': None,
                'message': None,
            }

    class RecordingAtomic:
        def __init__(self):
            self.image_request = None

        def process_file_atomic(self, file_path, new_filename, image_request, finish_folder):
            self.image_request = image_request
            finish = Path(finish_folder)
            finish.mkdir(exist_ok=True)
            video_path = finish / new_filename
            image_path = finish / f'{Path(new_filename).stem}.jpg'
            Path(file_path).rename(video_path)
            image_path.write_bytes(b'jpg')
            return True, {
                'status': 'success',
                'reason': '',
                'rollback_ok': None,
                'video_path': str(video_path),
                'image_path': str(image_path),
                'image_downloaded': True,
            }, 'ok'

        def process_series_group_atomic(self, files, title, image_request, finish_folder):
            raise AssertionError('not used')

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        logs = root / 'JFO_Logs'
        source = root / 'TOKYO-HOT-N0839.mp4'
        source.write_bytes(b'a' * 32768)
        atomic = RecordingAtomic()
        svc = WorkflowService(
            log=lambda *a, **k: None,
            provider_factory=lambda name: ProviderWithFallbackImage(),
            atomic_processor=atomic,
            clean_filename_for_search=clean_filename_for_search,
            sanitize_filename=_sanitize,
            detect_series_files=lambda files: ({}, files),
            smart_truncate_filename=lambda title, original, max_length: title,
            stop_requested=lambda: False,
            minimum_video_size_bytes=16384,
        )

        result = svc.run(
            folder_path=str(root),
            finish_folder=str(root / 'Finish'),
            website='uncensored',
            dry_run=False,
            logs_dir=str(logs),
        )

        assert result['success_count'] == 1
        assert atomic.image_request == {
            'image_url': 'https://cdn.example/primary.jpg',
            'referer': 'https://my.tokyo-hot.com/product/?q=n0839',
            'detail_url': 'https://my.tokyo-hot.com/product/21087/',
            'provider': 'uncensored',
            'fallback_images': ['https://cdn.example/fallback.jpg'],
        }


def test_workflow_cleans_empty_finish_after_atomic_failure():
    class SuccessfulProvider:
        def search(self, query):
            return {
                'ok': True,
                'title': 'SONE-753 TITLE',
                'image_url': 'http://example/image.jpg',
                'provider': 'javhoo',
                'detail_url': None,
                'referer': None,
                'error_type': None,
                'message': None,
            }

    class FailingAtomic:
        def process_file_atomic(self, file_path, new_filename, image_url, finish_folder):
            return False, {
                'status': 'failed',
                'reason': 'simulated atomic failure',
                'rollback_ok': True,
                'image_downloaded': False,
            }, 'simulated atomic failure'

        def process_series_group_atomic(self, files, title, image_url, finish_folder):
            raise AssertionError('not used')

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        logs = root / 'JFO_Logs'
        (root / 'SONE-753.mp4').write_bytes(b'a' * 32768)
        svc = WorkflowService(
            log=lambda *a, **k: None,
            provider_factory=lambda name: SuccessfulProvider(),
            atomic_processor=FailingAtomic(),
            clean_filename_for_search=clean_filename_for_search,
            sanitize_filename=_sanitize,
            detect_series_files=lambda files: ({}, files),
            smart_truncate_filename=lambda title, original, max_length: title,
            stop_requested=lambda: False,
            minimum_video_size_bytes=16384,
        )

        result = svc.run(
            folder_path=str(root),
            finish_folder=str(root / 'Finish'),
            website='javhoo',
            dry_run=False,
            logs_dir=str(logs),
        )

        assert result['failed_count'] == 1
        assert not (root / 'Finish').exists()
