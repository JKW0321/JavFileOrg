#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Workflow service tests."""
import tempfile
import json
from pathlib import Path

from PIL import Image

import workflow_service as workflow_mod
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


class MismatchedProvider:
    def search(self, _query):
        return {
            'ok': True,
            'title': 'MIFD-153 Wrong Search Result',
            'image_url': 'https://pics.javhoo.net/mifd-153.jpg',
            'provider': 'javhoo',
            'detail_url': 'https://www.javhoo.com/en/mifd-153',
            'referer': 'https://www.javhoo.com/search/fd-153',
            'error_type': None,
            'message': None,
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


def test_workflow_skips_anime_release_without_constructing_auto_provider(tmp_path):
    source = tmp_path / '[Erai-raws] Ousama Ranking - 07 [v0][1080p][Multiple Subtitle][815C2038].mkv'
    source.write_bytes(b'v' * 32768)
    created = []

    def provider_factory(name):
        created.append(name)
        raise AssertionError(f'skipped file must not construct provider: {name}')

    service = WorkflowService(
        log=lambda *_args, **_kwargs: None,
        provider_factory=provider_factory,
        atomic_processor=AtomicProcessor(_download, _sanitize),
        clean_filename_for_search=clean_filename_for_search,
        sanitize_filename=_sanitize,
        detect_series_files=lambda files: ({}, list(files)),
        smart_truncate_filename=lambda title, _filename, _max_length: title,
        minimum_video_size_bytes=16384,
    )

    result = service.run(
        folder_path=str(tmp_path),
        finish_folder=str(tmp_path / 'Finish'),
        website='auto_all',
        logs_dir=str(tmp_path / 'JFO_Logs'),
    )

    assert created == []
    assert result['skipped_provider_count'] == 1
    assert result['file_results'][0]['status'] == 'skipped'
    assert result['file_results'][0]['reason'] == 'non-jav-anime-release'
    assert source.exists()


def test_workflow_rejects_provider_result_for_different_code(tmp_path):
    source = tmp_path / 'fd-153.mp4'
    source.write_bytes(b'v' * 32768)
    logs = tmp_path / 'JFO_Logs'
    service = WorkflowService(
        log=lambda *_args, **_kwargs: None,
        provider_factory=lambda _name: MismatchedProvider(),
        atomic_processor=AtomicProcessor(_download, _sanitize),
        clean_filename_for_search=lambda name: Path(name).stem.lower(),
        sanitize_filename=_sanitize,
        detect_series_files=lambda files: ({}, list(files)),
        smart_truncate_filename=lambda title, _filename, _max_length: title[:_max_length],
    )

    result = service.run(
        folder_path=str(tmp_path),
        finish_folder=str(tmp_path / 'Finish'),
        website='javhoo',
        logs_dir=str(logs),
    )

    assert result['failed_count'] == 1
    assert source.exists()
    assert not list(tmp_path.glob('MIFD-153*'))
    assert '返回番号 MIFD-153' in result['file_results'][0]['reason']


def test_workflow_notifies_ui_before_slow_after_manifest_scan(tmp_path, monkeypatch):
    root = tmp_path
    logs = root / 'JFO_Logs'
    video = root / 'SONE-753.mp4'
    video.write_bytes(b'v' * 32768)
    order = []

    original_scan = workflow_mod.scan_folder_manifest

    def observed_scan(*args, **kwargs):
        order.append('after-manifest-scan')
        return original_scan(*args, **kwargs)

    monkeypatch.setattr(workflow_mod, 'scan_folder_manifest', observed_scan)
    service = WorkflowService(
        log=lambda *_args, **_kwargs: None,
        provider_factory=lambda _name: DummyProvider(),
        atomic_processor=AtomicProcessor(_download, _sanitize),
        clean_filename_for_search=lambda name: Path(name).stem,
        sanitize_filename=_sanitize,
        detect_series_files=lambda files: ({}, files),
        smart_truncate_filename=lambda title, _original, _max_length: title,
        finalizing_callback=lambda result, dry_run=False: order.append('ui-finalizing'),
    )

    result = service.run(
        folder_path=str(root),
        finish_folder=str(root / 'Finish'),
        website='javhoo',
        dry_run=True,
        logs_dir=str(logs),
    )

    assert result['planned_count'] == 1
    assert order[:2] == ['ui-finalizing', 'after-manifest-scan']


def test_workflow_full_auto_routes_known_mgstage_file_to_exact_source_chain():
    created = []

    def provider_factory(name):
        created.append(name)
        return DummyProvider()

    svc = WorkflowService(
        log=lambda *a, **k: None,
        provider_factory=provider_factory,
        atomic_processor=AtomicProcessor(_download, _sanitize),
        clean_filename_for_search=clean_filename_for_search,
        sanitize_filename=_sanitize,
        detect_series_files=lambda files: ({}, files),
        smart_truncate_filename=lambda title, original, max_length: title,
    )

    decision, _provider, provider_name = svc._resolve_provider(
        'auto_all', '420HPT-049.mp4', '420hpt-049'
    )

    assert decision['candidates'] == ['libredmm', 'mgstage']
    assert provider_name == 'libredmm'
    assert created == ['libredmm']


def test_workflow_gana_falls_back_from_libredmm_to_official_mgstage_adapter():
    providers = {
        'libredmm': FailingProvider(),
        'mgstage': DummyProvider('GANA-3218 Japanese title'),
    }
    svc = WorkflowService(
        log=lambda *a, **k: None,
        provider_factory=lambda name: providers[name],
        atomic_processor=AtomicProcessor(_download, _sanitize),
        clean_filename_for_search=clean_filename_for_search,
        sanitize_filename=_sanitize,
        detect_series_files=lambda files: ({}, files),
        smart_truncate_filename=lambda title, original, max_length: title,
    )

    decision, provider, provider_name = svc._resolve_provider(
        'auto_all', 'GANA-3218.mp4', 'gana-3218'
    )
    result, effective_name = svc._provider_search_with_fallback(
        {}, decision, provider_name, provider, 'gana-3218'
    )

    assert result['ok'] is True
    assert effective_name == 'mgstage'
    assert providers['libredmm'].calls == ['gana-3218']
    assert providers['mgstage'].calls == ['gana-3218']


def test_workflow_specified_uncensored_source_is_not_changed():
    created = []

    def provider_factory(name):
        created.append(name)
        return DummyProvider()

    svc = WorkflowService(
        log=lambda *a, **k: None,
        provider_factory=provider_factory,
        atomic_processor=AtomicProcessor(_download, _sanitize),
        clean_filename_for_search=clean_filename_for_search,
        sanitize_filename=_sanitize,
        detect_series_files=lambda files: ({}, files),
        smart_truncate_filename=lambda title, original, max_length: title,
    )

    decision, _provider, provider_name = svc._resolve_provider(
        'uncensored', 'STARS-239_Uncen.mp4', 'stars-239'
    )

    assert decision['reason'] == 'specified-provider'
    assert provider_name == 'uncensored'
    assert created == ['uncensored']


def test_workflow_auto_censored_falls_back_from_javbus_to_javhoo():
    providers = {
        'javbus': FailingProvider(),
        'r18dev': FailingProvider(),
        'libredmm': FailingProvider(),
        'javhoo': DummyProvider('JAVHOO'),
    }
    svc = WorkflowService(
        log=lambda *a, **k: None,
        provider_factory=lambda name: providers[name],
        atomic_processor=AtomicProcessor(_download, _sanitize),
        clean_filename_for_search=clean_filename_for_search,
        sanitize_filename=_sanitize,
        detect_series_files=lambda files: ({}, files),
        smart_truncate_filename=lambda title, original, max_length: title,
    )

    decision, provider, provider_name = svc._resolve_provider(
        'auto_censored', 'ABF-139.mp4', 'abf-139'
    )
    result, effective_name = svc._provider_search_with_fallback(
        {}, decision, provider_name, provider, 'abf-139'
    )

    assert result['ok'] is True
    assert effective_name == 'javhoo'
    assert providers['javbus'].calls == ['abf-139']
    assert providers['javhoo'].calls == ['abf-139']
    assert providers['libredmm'].calls == []
    assert providers['r18dev'].calls == []


def test_auto_keyword_search_discovers_code_then_requires_dmm_verification():
    class KeywordCandidateProvider:
        def __init__(self):
            self.calls = []

        def search(self, query):
            self.calls.append(query)
            return {
                'ok': True,
                'title': 'MIRD-876 監禁凌辱作品 三浦亜沙妃',
                'image_url': 'https://pics.javhoo.net/mird-876.jpg',
                'provider': 'javhoo',
                'detail_url': 'https://www.javhoo.com/mird-876',
                'referer': f'https://www.javhoo.com/search/{query}',
                'error_type': None,
                'message': None,
            }

    class ExactDmmProvider:
        def __init__(self):
            self.calls = []

        def search(self, query):
            self.calls.append(query)
            return {
                'ok': True,
                'title': 'MIRD-876 監禁凌辱作品 三浦亜沙妃',
                'image_url': 'https://pics.dmm.co.jp/digital/video/mird00876/mird00876pl.jpg',
                'provider': 'libredmm',
                'detail_url': 'https://www.libredmm.com/movies/MIRD-876.json',
                'referer': 'https://www.libredmm.com/search?q=MIRD-876&format=json',
                'error_type': None,
                'message': None,
                'raw_meta': {'normalized_id': 'MIRD-876'},
            }

    javhoo = KeywordCandidateProvider()
    libredmm = ExactDmmProvider()
    providers = {
        'javbus': FailingProvider(),
        'javhoo': javhoo,
        'libredmm': libredmm,
        'r18dev': FailingProvider(),
        'uncensored': FailingProvider(),
    }
    svc = WorkflowService(
        log=lambda *a, **k: None,
        provider_factory=lambda name: providers[name],
        atomic_processor=AtomicProcessor(_download, _sanitize),
        clean_filename_for_search=clean_filename_for_search,
        sanitize_filename=_sanitize,
        detect_series_files=lambda files: ({}, files),
        smart_truncate_filename=lambda title, original, max_length: title,
    )
    query = '監禁凌辱作品 三浦亜沙妃'
    decision, provider, provider_name = svc._resolve_provider(
        'auto_all', '三浦亜沙妃.avi', query
    )

    result, effective_name = svc._provider_search_with_fallback(
        {}, decision, provider_name, provider, query
    )

    assert result['ok'] is True
    assert effective_name == 'libredmm'
    assert javhoo.calls == [query]
    assert libredmm.calls == ['mird-876']
    assert result['raw_meta']['keyword_discovery']['candidate_code'] == 'MIRD-876'


def test_auto_keyword_search_rejects_irrelevant_first_candidate_without_dmm_lookup():
    class IrrelevantCandidateProvider:
        def search(self, query):
            return {
                'ok': True,
                'title': 'ABF-217 完全に別の作品',
                'image_url': 'https://pics.javhoo.net/abf-217.jpg',
                'provider': 'javhoo',
                'detail_url': 'https://www.javhoo.com/abf-217',
                'referer': f'https://www.javhoo.com/search/{query}',
                'error_type': None,
                'message': None,
            }

    class RecordingDmm:
        def __init__(self):
            self.calls = []

        def search(self, query):
            self.calls.append(query)
            return {
                'ok': False,
                'provider': 'libredmm',
                'query': query,
                'error_type': 'unsupported-query',
                'message': 'standard code required',
            }

    dmm = RecordingDmm()
    providers = {
        'javbus': FailingProvider(),
        'javhoo': IrrelevantCandidateProvider(),
        'libredmm': dmm,
        'r18dev': FailingProvider(),
        'uncensored': FailingProvider(),
    }
    svc = WorkflowService(
        log=lambda *a, **k: None,
        provider_factory=lambda name: providers[name],
        atomic_processor=AtomicProcessor(_download, _sanitize),
        clean_filename_for_search=clean_filename_for_search,
        sanitize_filename=_sanitize,
        detect_series_files=lambda files: ({}, files),
        smart_truncate_filename=lambda title, original, max_length: title,
    )
    query = '監禁凌辱作品 三浦亜沙妃'
    decision, provider, provider_name = svc._resolve_provider(
        'auto_all', '三浦亜沙妃.avi', query
    )

    result, _effective_name = svc._provider_search_with_fallback(
        {}, decision, provider_name, provider, query
    )

    assert result['ok'] is False
    assert 'abf-217' not in dmm.calls


def test_workflow_keeps_meaningful_general_failure_when_uncensored_is_unsupported():
    class UnsupportedProvider:
        def search(self, query):
            return {
                'ok': False,
                'provider': 'uncensored',
                'query': query,
                'error_type': 'unsupported-source',
                'message': 'source family unsupported',
            }

    providers = {
        'javbus': FailingProvider(),
        'r18dev': FailingProvider(),
        'libredmm': FailingProvider(),
        'javhoo': FailingProvider(),
        'uncensored': UnsupportedProvider(),
    }
    svc = WorkflowService(
        log=lambda *a, **k: None,
        provider_factory=lambda name: providers[name],
        atomic_processor=AtomicProcessor(_download, _sanitize),
        clean_filename_for_search=clean_filename_for_search,
        sanitize_filename=_sanitize,
        detect_series_files=lambda files: ({}, files),
        smart_truncate_filename=lambda title, original, max_length: title,
    )
    decision, provider, provider_name = svc._resolve_provider(
        'auto_all', 'AJ-072.mp4', 'aj-072'
    )

    result, effective_name = svc._provider_search_with_fallback(
        {}, decision, provider_name, provider, 'aj-072'
    )

    assert result['error_type'] == 'invalid-result'
    assert effective_name == 'r18dev'


def test_workflow_auto_routes_uncensored_video_group_as_one_provider_batch(tmp_path):
    first = tmp_path / 'FC2-PPV-2386297-1.mp4'
    second = tmp_path / 'FC2-PPV-2386297-2.mp4'
    _video_size = b'v' * 32768
    first.write_bytes(_video_size)
    second.write_bytes(_video_size)
    providers = {}

    def provider_factory(name):
        providers.setdefault(name, DummyProvider())
        return providers[name]

    svc = WorkflowService(
        log=lambda *a, **k: None,
        provider_factory=provider_factory,
        atomic_processor=AtomicProcessor(_download, _sanitize),
        clean_filename_for_search=clean_filename_for_search,
        sanitize_filename=_sanitize,
        detect_series_files=_detect_series_from_filename_utils,
        smart_truncate_filename=lambda title, original, max_length: title,
        minimum_video_size_bytes=16384,
    )

    result = svc.run(
        folder_path=str(tmp_path),
        finish_folder=str(tmp_path / 'Finish'),
        website='auto_all',
        dry_run=True,
        logs_dir=str(tmp_path / 'JFO_Logs'),
    )

    assert result['planned_count'] == 2
    assert result['routed_counts'] == {'uncensored': 2}
    assert {item['provider'] for item in result['file_results']} == {'uncensored'}


def test_workflow_generalized_video_group_uses_one_search_and_one_cover(tmp_path):
    import jav_file_organizer as jfo_mod

    videos = [
        tmp_path / f'ABF-139 Fixed Title ({sequence}).mp4'
        for sequence in (1, 2, 3)
    ]
    for video in videos:
        video.write_bytes(b'v' * 32768)

    organizer = jfo_mod.JavFileOrganizer.__new__(jfo_mod.JavFileOrganizer)
    organizer.log = lambda *a, **k: None
    provider = DummyProvider()
    svc = WorkflowService(
        log=lambda *a, **k: None,
        provider_factory=lambda _name: provider,
        atomic_processor=AtomicProcessor(_download, _sanitize),
        clean_filename_for_search=clean_filename_for_search,
        sanitize_filename=_sanitize,
        detect_series_files=organizer.detect_series_files,
        smart_truncate_filename=lambda title, original, max_length: title,
        minimum_video_size_bytes=16384,
    )

    result = svc.run(
        folder_path=str(tmp_path),
        finish_folder=str(tmp_path / 'Finish'),
        website='javbus',
        dry_run=False,
        logs_dir=str(tmp_path / 'JFO_Logs'),
    )

    assert result['success_count'] == 3
    assert provider.calls == ['ABF-139']
    assert len(list((tmp_path / 'Finish').glob('*.mp4'))) == 3
    assert len(list((tmp_path / 'Finish').glob('*.jpg'))) == 1


def test_workflow_emits_file_result_callback_as_each_file_finishes():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        logs = root / 'JFO_Logs'
        (root / 'ABF-139.mp4').write_bytes(b'a' * 32768)
        (root / 'SONE-753.mp4').write_bytes(b'b' * 32768)
        emitted = []
        svc = WorkflowService(
            log=lambda *a, **k: None,
            provider_factory=lambda name: DummyProvider(),
            atomic_processor=AtomicProcessor(_download, _sanitize),
            clean_filename_for_search=lambda n: Path(n).stem.lower(),
            sanitize_filename=_sanitize,
            detect_series_files=lambda files: ({}, files),
            smart_truncate_filename=lambda title, original, max_length: title,
            stop_requested=lambda: False,
            minimum_video_size_bytes=16384,
            file_result_callback=lambda item: emitted.append(item),
        )

        result = svc.run(
            folder_path=str(root),
            finish_folder=str(root / 'Finish'),
            website='javhoo',
            dry_run=True,
            logs_dir=str(logs),
        )

        assert result['planned_count'] == 2
        assert [item['source_name'] for item in emitted] == ['ABF-139.mp4', 'SONE-753.mp4']
        assert {item['status'] for item in emitted} == {'planned'}


def test_workflow_processes_series_and_standalone_in_scan_order():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        logs = root / 'JFO_Logs'
        for name in ('SONE-753.mp4', 'ABF-139-1.mp4', 'ABF-139-2.mp4', 'JBD-131.mp4'):
            (root / name).write_bytes(b'a' * 32768)
        emitted = []

        def detect(files):
            by_name = {Path(file_path).name: file_path for file_path in files}
            return {
                'ABF-139': [
                    (by_name['ABF-139-1.mp4'], '1'),
                    (by_name['ABF-139-2.mp4'], '2'),
                ]
            }, [by_name['SONE-753.mp4'], by_name['JBD-131.mp4']]

        svc = WorkflowService(
            log=lambda *a, **k: None,
            provider_factory=lambda name: DummyProvider(),
            atomic_processor=AtomicProcessor(_download, _sanitize),
            clean_filename_for_search=lambda n: Path(n).stem.lower(),
            sanitize_filename=_sanitize,
            detect_series_files=detect,
            smart_truncate_filename=lambda title, original, max_length: title,
            stop_requested=lambda: False,
            minimum_video_size_bytes=16384,
            file_result_callback=lambda item: emitted.append(item),
        )

        result = svc.run(
            folder_path=str(root),
            finish_folder=str(root / 'Finish'),
            website='javhoo',
            dry_run=True,
            logs_dir=str(logs),
            initial_scan={
                'accepted': ['SONE-753.mp4', 'ABF-139-1.mp4', 'ABF-139-2.mp4', 'JBD-131.mp4'],
                'skipped_hidden': [],
                'skipped_small': [],
                'manifest_entries': [],
                'file_sizes': {},
                'total_files': 4,
            },
        )

        assert result['planned_count'] == 4
        assert [item['source_name'] for item in emitted] == [
            'SONE-753.mp4',
            'ABF-139-1.mp4',
            'ABF-139-2.mp4',
            'JBD-131.mp4',
        ]


def test_uncensored_workflow_uses_parent_path_for_dms_night24_query():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        source_dir = root / 'source'
        nested = source_dir / 'U' / 'night24 pack' / 'DMS Night24 013 (5013) 高田弘美'
        nested.mkdir(parents=True)
        video = nested / '013.avi'
        video.write_bytes(b'a' * 32768)
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
            folder_path=str(source_dir),
            finish_folder=str(source_dir / 'Finish'),
            website='uncensored',
        )

        assert result['success_count'] == 1
        assert provider.calls == ['dms-night24-013']


def test_workflow_run_reuses_initial_scan_without_rescanning_folder():
    class NoRescanWorkflowService(WorkflowService):
        def _scan_video_files(self, folder_path):
            raise AssertionError('folder was rescanned')

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / 'SONE-753.mp4').write_bytes(b'a' * 32768)
        provider = DummyProvider()
        svc = NoRescanWorkflowService(
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
            initial_scan={
                'accepted': ['SONE-753.mp4'],
                'skipped_hidden': [],
                'skipped_small': [],
                'manifest_entries': [],
            },
        )

    assert result['planned_count'] == 1
    assert provider.calls == []


def test_workflow_can_process_current_directory_only():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / 'SONE-753.mp4').write_bytes(b'a' * 32768)
        (root / 'nested').mkdir()
        (root / 'nested' / 'ABF-139.mp4').write_bytes(b'b' * 32768)
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
            dry_run=True,
            include_subdirectories=False,
        )

        assert result['planned_count'] == 1
        assert result['total_files'] == 1
        assert provider.calls == []


def test_numeric_single_video_uses_parent_directory_context_for_any_provider(tmp_path):
    movie_dir = tmp_path / 'MIRD-876 監禁凌辱作品'
    movie_dir.mkdir()
    video = movie_dir / '01.mp4'
    video.write_bytes(b'v' * 32768)
    svc = WorkflowService(
        log=lambda *a, **k: None,
        provider_factory=lambda _name: DummyProvider(),
        atomic_processor=AtomicProcessor(_download, _sanitize),
        clean_filename_for_search=clean_filename_for_search,
        sanitize_filename=_sanitize,
        detect_series_files=lambda files: ({}, files),
        smart_truncate_filename=lambda title, original, max_length: title,
    )

    query = svc._search_query_for_file(
        website='javbus',
        filename=video.name,
        file_path=str(video),
        folder_path=str(tmp_path),
        directory_video_count=1,
    )

    assert query == 'mird-876'


def test_directory_context_uses_only_immediate_parent_not_ancestors(tmp_path):
    collection = tmp_path / '上级合集名称'
    movie_dir = collection / 'MIRD-876 監禁凌辱作品'
    movie_dir.mkdir(parents=True)
    video = movie_dir / '01.mp4'
    video.write_bytes(b'v' * 32768)
    svc = WorkflowService(
        log=lambda *a, **k: None,
        provider_factory=lambda _name: DummyProvider(),
        atomic_processor=AtomicProcessor(_download, _sanitize),
        clean_filename_for_search=clean_filename_for_search,
        sanitize_filename=_sanitize,
        detect_series_files=lambda files: ({}, files),
        smart_truncate_filename=lambda title, original, max_length: title,
    )

    query = svc._search_query_for_file(
        website='auto_all',
        filename=video.name,
        file_path=str(video),
        folder_path=str(tmp_path),
        directory_video_count=1,
    )

    assert query == 'mird-876'
    assert '上级合集' not in query


def test_single_weak_video_name_uses_immediate_parent_code(tmp_path):
    movie_dir = tmp_path / 'SERO-0028 絵色千佳'
    movie_dir.mkdir()
    video = movie_dir / 'CD1.avi'
    video.write_bytes(b'v' * 32768)
    svc = WorkflowService(
        log=lambda *a, **k: None,
        provider_factory=lambda _name: DummyProvider(),
        atomic_processor=AtomicProcessor(_download, _sanitize),
        clean_filename_for_search=clean_filename_for_search,
        sanitize_filename=_sanitize,
        detect_series_files=lambda files: ({}, files),
        smart_truncate_filename=lambda title, original, max_length: title,
    )

    query = svc._search_query_for_file(
        website='auto_all',
        filename=video.name,
        file_path=str(video),
        folder_path=str(tmp_path),
        directory_video_count=1,
    )

    assert query == 'sero-0028'


def test_single_title_only_video_combines_immediate_folder_and_filename_keywords(tmp_path):
    movie_dir = tmp_path / 'Extreme Sexual Torture 爆イキ 10'
    movie_dir.mkdir()
    video = movie_dir / '三浦亜沙妃 Asahi Miura.avi'
    video.write_bytes(b'v' * 32768)
    svc = WorkflowService(
        log=lambda *a, **k: None,
        provider_factory=lambda _name: DummyProvider(),
        atomic_processor=AtomicProcessor(_download, _sanitize),
        clean_filename_for_search=clean_filename_for_search,
        sanitize_filename=_sanitize,
        detect_series_files=lambda files: ({}, files),
        smart_truncate_filename=lambda title, original, max_length: title,
    )

    query = svc._search_query_for_file(
        website='auto_all',
        filename=video.name,
        file_path=str(video),
        folder_path=str(tmp_path),
        directory_video_count=1,
    )

    assert query == 'extreme sexual torture 爆イキ 10 三浦亜沙妃 asahi miura'


def test_numeric_file_does_not_borrow_parent_when_directory_contains_multiple_videos(tmp_path):
    movie_dir = tmp_path / 'MIRD-876 監禁凌辱作品'
    movie_dir.mkdir()
    video = movie_dir / '01.mp4'
    video.write_bytes(b'v' * 32768)
    svc = WorkflowService(
        log=lambda *a, **k: None,
        provider_factory=lambda _name: DummyProvider(),
        atomic_processor=AtomicProcessor(_download, _sanitize),
        clean_filename_for_search=clean_filename_for_search,
        sanitize_filename=_sanitize,
        detect_series_files=lambda files: ({}, files),
        smart_truncate_filename=lambda title, original, max_length: title,
    )

    query = svc._search_query_for_file(
        website='javbus',
        filename=video.name,
        file_path=str(video),
        folder_path=str(tmp_path),
        directory_video_count=2,
    )

    assert query == '01'


def test_art_collection_uses_direct_folder_as_catalog_context_even_with_many_videos(tmp_path):
    art_dir = tmp_path / '04. ART'
    art_dir.mkdir()
    first = art_dir / '1754 淫乱美麗奴倶楽部.wmv'
    second = art_dir / 'No.2090.wmv'
    first.write_bytes(b'v' * 32768)
    second.write_bytes(b'v' * 32768)
    service = WorkflowService(
        log=lambda *_args, **_kwargs: None,
        provider_factory=lambda _name: DummyProvider(),
        atomic_processor=AtomicProcessor(_download, _sanitize),
        clean_filename_for_search=clean_filename_for_search,
        sanitize_filename=_sanitize,
        detect_series_files=lambda files: ({}, list(files)),
        smart_truncate_filename=lambda title, original, max_length: title,
    )

    assert service._search_query_for_file(
        website='auto_all',
        filename=first.name,
        file_path=str(first),
        folder_path=str(art_dir),
        directory_video_count=2,
    ) == 'ART VIDEO 1754 淫乱美麗奴倶楽部'
    assert service._search_query_for_file(
        website='auto_all',
        filename=second.name,
        file_path=str(second),
        folder_path=str(art_dir),
        directory_video_count=2,
    ) == 'ART VIDEO 2090'


def test_art_collection_preserves_japanese_diacritics_and_removes_maker_markers(tmp_path):
    art_dir = tmp_path / '04. ART'
    art_dir.mkdir()
    service = WorkflowService(
        log=lambda *_args, **_kwargs: None,
        provider_factory=lambda _name: DummyProvider(),
        atomic_processor=AtomicProcessor(_download, _sanitize),
        clean_filename_for_search=clean_filename_for_search,
        sanitize_filename=_sanitize,
        detect_series_files=lambda files: ({}, list(files)),
        smart_truncate_filename=lambda title, original, max_length: title,
    )

    assert service._art_network_query(
        '[Art Video] アートビデオ 猟奇の檻 12 丸山ゆり.avi',
        str(art_dir / 'sample.avi'),
    ) == 'ART VIDEO 猟奇の檻 12 丸山ゆり'
    assert service._art_network_query(
        '[ArtVideo] Extreme Sexual Torture アートビデオ 爆イキ 10 (2008) - 三浦亜沙妃 (Asahi Miura).avi',
        str(art_dir / 'sample.avi'),
    ) == 'ART VIDEO Extreme Sexual Torture 爆イキ 10 (2008) - 三浦亜沙妃 (Asahi Miura)'
    assert service._art_network_query(
        '奴隷通信 36 アートビデオ みだら縄ただれ縄狂ひ縄 桐島千沙.avi',
        str(art_dir / 'sample.avi'),
    ) == 'ART VIDEO 奴隷通信 36 みだら縄ただれ縄狂ひ縄 桐島千沙'


def test_normalized_art_filename_keeps_catalog_identity_inside_finish(tmp_path):
    finish_dir = tmp_path / 'Finish'
    finish_dir.mkdir()
    video = finish_dir / 'ART-1754 淫乱美麗奴倶楽部.wmv'
    service = WorkflowService(
        log=lambda *_args, **_kwargs: None,
        provider_factory=lambda _name: DummyProvider(),
        atomic_processor=AtomicProcessor(_download, _sanitize),
        clean_filename_for_search=clean_filename_for_search,
        sanitize_filename=_sanitize,
        detect_series_files=lambda files: ({}, list(files)),
        smart_truncate_filename=lambda title, original, max_length: title,
    )

    assert service._search_query_for_file(
        website='auto_all',
        filename=video.name,
        file_path=str(video),
        folder_path=str(finish_dir),
        directory_video_count=45,
    ) == 'ART VIDEO 1754 淫乱美麗奴倶楽部'


def test_normalized_numeric_only_art_filename_uses_art_provider_without_guessing_title(tmp_path):
    finish_dir = tmp_path / 'Finish'
    finish_dir.mkdir()
    video = finish_dir / 'ART-2090.wmv'
    service = WorkflowService(
        log=lambda *_args, **_kwargs: None,
        provider_factory=lambda _name: DummyProvider(),
        atomic_processor=AtomicProcessor(_download, _sanitize),
        clean_filename_for_search=clean_filename_for_search,
        sanitize_filename=_sanitize,
        detect_series_files=lambda files: ({}, list(files)),
        smart_truncate_filename=lambda title, original, max_length: title,
    )

    assert service._search_query_for_file(
        website='auto_all',
        filename=video.name,
        file_path=str(video),
        folder_path=str(finish_dir),
        directory_video_count=45,
    ) == 'ART VIDEO 2090'


def test_art_batch_identity_is_inferred_from_current_directory_not_ancestors(tmp_path):
    finish_dir = tmp_path / 'Unrelated Collection' / 'Finish'
    finish_dir.mkdir(parents=True)
    paths = [
        finish_dir / 'ART-1754 淫乱美麗奴倶楽部.wmv',
        finish_dir / 'ART-1856 異形の淫獣.wmv',
        finish_dir / 'ART-1893 美肉マゾ倶楽部.wmv',
        finish_dir / 'ART-1927 女芯悦獄4.wmv',
        finish_dir / '猟奇の檻11 森口久美 桜台なぎさ.avi',
    ]
    contexts = WorkflowService._art_context_directories([str(path) for path in paths])

    assert contexts == {str(finish_dir.resolve())}

    service = WorkflowService(
        log=lambda *_args, **_kwargs: None,
        provider_factory=lambda _name: DummyProvider(),
        atomic_processor=AtomicProcessor(_download, _sanitize),
        clean_filename_for_search=clean_filename_for_search,
        sanitize_filename=_sanitize,
        detect_series_files=lambda files: ({}, list(files)),
        smart_truncate_filename=lambda title, original, max_length: title,
    )
    assert service._search_query_for_file(
        website='auto_all',
        filename=paths[-1].name,
        file_path=str(paths[-1]),
        folder_path=str(finish_dir),
        directory_video_count=5,
        art_batch_context=True,
    ) == 'ART VIDEO 猟奇の檻11 森口久美 桜台なぎさ'


def test_single_unmarked_title_is_not_reclassified_from_collection_ancestor(tmp_path):
    art_ancestor = tmp_path / 'ART' / 'Finish'
    art_ancestor.mkdir(parents=True)
    video = art_ancestor / '普通标题.avi'

    assert WorkflowService._art_context_directories([str(video)]) == set()


def test_art_collection_requires_verified_network_metadata_and_keeps_local_pair(tmp_path):
    art_dir = tmp_path / '04. ART'
    art_dir.mkdir()
    source_video = art_dir / '1754 淫乱美麗奴倶楽部.wmv'
    source_cover = art_dir / '1754 淫乱美麗奴倶楽部.jpg'
    source_video.write_bytes(b'v' * 32768)
    Image.new('RGB', (640, 900), color=(80, 20, 30)).save(source_cover, 'JPEG')
    created = []
    logs = []

    class ArtNetworkProvider:
        def search(self, query):
            assert query == 'ART VIDEO 1754 淫乱美麗奴倶楽部'
            return {
                'ok': True,
                'title': 'ART-1754 淫乱美麗奴倶楽部 公式題名',
                'image_url': 'https://pureadult.co.jp/user_data/sp_images/gazou/126018/126018314000.jpg',
                'provider': 'artvideo',
                'detail_url': 'https://pureadult.co.jp/user_data/sp_artist_product_detail.php?mid=3&pid=126018314000',
                'referer': 'https://pureadult.co.jp/user_data/sp_search_result.php?km=2',
                'error_type': None,
                'message': None,
                'raw_meta': {'maker': 'ＡＲＴ　ＶＩＤＥＯ'},
            }

    def provider_factory(name):
        created.append(name)
        assert name == 'artvideo'
        return ArtNetworkProvider()

    service = WorkflowService(
        log=lambda message, level='INFO': logs.append((level, message)),
        provider_factory=provider_factory,
        atomic_processor=AtomicProcessor(_download, _sanitize),
        clean_filename_for_search=clean_filename_for_search,
        sanitize_filename=_sanitize,
        detect_series_files=lambda files: ({}, list(files)),
        smart_truncate_filename=lambda title, original, max_length: title,
        minimum_video_size_bytes=16384,
    )

    result = service.run(
        folder_path=str(art_dir),
        finish_folder=str(art_dir / 'Finish'),
        website='auto_all',
        logs_dir=str(art_dir / 'JFO_Logs'),
        include_subdirectories=False,
    )

    target_video = art_dir / 'Finish' / 'ART-1754 淫乱美麗奴倶楽部 公式題名.wmv'
    target_cover = art_dir / 'Finish' / 'ART-1754 淫乱美麗奴倶楽部 公式題名.jpg'
    assert result['success_count'] == 1
    assert created == ['artvideo']
    assert target_video.exists()
    assert target_cover.exists()
    assert not source_video.exists()
    assert source_cover.exists()
    with Image.open(target_cover) as image:
        image.load()
        assert image.size == (1, 1)
    assert result['file_results'][0]['provider'] == 'artvideo'
    assert result['file_results'][0]['query'] == 'ART VIDEO 1754 淫乱美麗奴倶楽部'
    assert not any('复用' in message and '本地配套封面' in message for _level, message in logs)


def test_night24_numeric_collection_is_identified_without_using_generic_number_search(tmp_path):
    night_dir = tmp_path / 'Night24'
    night_dir.mkdir()
    video = night_dir / '1216.mp4'
    video.write_bytes(b'v' * 32768)
    service = WorkflowService(
        log=lambda *_args, **_kwargs: None,
        provider_factory=lambda _name: DummyProvider(),
        atomic_processor=AtomicProcessor(_download, _sanitize),
        clean_filename_for_search=clean_filename_for_search,
        sanitize_filename=_sanitize,
        detect_series_files=lambda files: ({}, list(files)),
        smart_truncate_filename=lambda title, original, max_length: title,
    )

    assert service._search_query_for_file(
        website='auto_all',
        filename=video.name,
        file_path=str(video),
        folder_path=str(night_dir),
        directory_video_count=349,
    ) == 'dms-night24-1216'


def test_meaningful_video_filename_wins_over_parent_directory_context(tmp_path):
    movie_dir = tmp_path / 'Unrelated Folder 999'
    movie_dir.mkdir()
    video = movie_dir / 'ABF-139.mp4'
    video.write_bytes(b'v' * 32768)
    svc = WorkflowService(
        log=lambda *a, **k: None,
        provider_factory=lambda _name: DummyProvider(),
        atomic_processor=AtomicProcessor(_download, _sanitize),
        clean_filename_for_search=clean_filename_for_search,
        sanitize_filename=_sanitize,
        detect_series_files=lambda files: ({}, files),
        smart_truncate_filename=lambda title, original, max_length: title,
    )

    query = svc._search_query_for_file(
        website='auto_all',
        filename=video.name,
        file_path=str(video),
        folder_path=str(tmp_path),
        directory_video_count=1,
    )

    assert query == 'abf-139'


def test_recursive_run_searches_single_numeric_video_with_parent_directory_code(tmp_path):
    movie_dir = tmp_path / 'MIRD-876 監禁凌辱作品'
    movie_dir.mkdir()
    (movie_dir / '01.mp4').write_bytes(b'v' * 32768)
    provider = DummyProvider()
    svc = WorkflowService(
        log=lambda *a, **k: None,
        provider_factory=lambda _name: provider,
        atomic_processor=AtomicProcessor(_download, _sanitize),
        clean_filename_for_search=clean_filename_for_search,
        sanitize_filename=_sanitize,
        detect_series_files=lambda files: ({}, files),
        smart_truncate_filename=lambda title, original, max_length: title,
        minimum_video_size_bytes=16384,
    )

    result = svc.run(
        folder_path=str(tmp_path),
        finish_folder=str(tmp_path / 'Finish'),
        website='javbus',
        dry_run=False,
        include_subdirectories=True,
    )

    assert provider.calls == ['mird-876']
    assert result['success_count'] == 1


def test_selected_numeric_video_does_not_hide_other_videos_in_same_directory(tmp_path):
    movie_dir = tmp_path / 'MIRD-876 監禁凌辱作品'
    movie_dir.mkdir()
    (movie_dir / '01.mp4').write_bytes(b'a' * 32768)
    (movie_dir / '02.mp4').write_bytes(b'b' * 32768)
    provider = DummyProvider()
    svc = WorkflowService(
        log=lambda *a, **k: None,
        provider_factory=lambda _name: provider,
        atomic_processor=AtomicProcessor(_download, _sanitize),
        clean_filename_for_search=clean_filename_for_search,
        sanitize_filename=_sanitize,
        detect_series_files=lambda files: ({}, files),
        smart_truncate_filename=lambda title, original, max_length: title,
        minimum_video_size_bytes=16384,
    )

    result = svc.run(
        folder_path=str(tmp_path),
        finish_folder=str(tmp_path / 'Finish'),
        website='javbus',
        dry_run=False,
        include_subdirectories=True,
        initial_scan={
            'accepted': ['MIRD-876 監禁凌辱作品/01.mp4'],
            'skipped_hidden': [],
            'skipped_small': [],
            'manifest_entries': [],
            'file_sizes': {'MIRD-876 監禁凌辱作品/01.mp4': 32768},
        },
    )

    assert provider.calls == ['01']
    assert result['success_count'] == 1
    assert (movie_dir / '02.mp4').exists()


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


def test_provider_search_caches_network_not_found_failures():
    class MissingPageProvider:
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
                'message': '404 Client Error: Not Found',
            }

    provider = MissingPageProvider()
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

    first = svc._provider_search(cache, 'uncensored', provider, 'FC2-PPV-9999999')
    second = svc._provider_search(cache, 'uncensored', provider, 'FC2-PPV-9999999')

    assert first is second
    assert first['error_type'] == 'network-error'
    assert provider.calls == ['FC2-PPV-9999999']
    assert ('uncensored', 'FC2-PPV-9999999') in cache


def test_provider_search_caches_not_found_failures():
    class NotFoundProvider:
        def __init__(self):
            self.calls = []

        def search(self, query):
            self.calls.append(query)
            return {
                'ok': False,
                'title': None,
                'image_url': None,
                'provider': 'uncensored',
                'detail_url': f'https://example.test/{query}',
                'referer': f'https://example.test/{query}',
                'error_type': 'not-found',
                'message': 'page not found',
            }

    provider = NotFoundProvider()
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

    first = svc._provider_search(cache, 'uncensored', provider, '1pondo-122422-001')
    second = svc._provider_search(cache, 'uncensored', provider, '1pondo-122422-001')

    assert first is second
    assert first['error_type'] == 'not-found'
    assert provider.calls == ['1pondo-122422-001']
    assert ('uncensored', '1pondo-122422-001') in cache


def test_workflow_logs_summary_before_report_phase():
    logs = []
    svc = WorkflowService(
        log=lambda message, level='INFO': logs.append((level, message)),
        provider_factory=lambda name: DummyProvider(),
        atomic_processor=AtomicProcessor(_download, _sanitize),
        clean_filename_for_search=clean_filename_for_search,
        sanitize_filename=_sanitize,
        detect_series_files=lambda files: ({}, files),
        smart_truncate_filename=lambda title, original, max_length: title,
        stop_requested=lambda: False,
    )
    stats = {
        'total_files': 3,
        'success_count': 1,
        'failed_count': 1,
        'planned_count': 0,
        'skipped_provider_count': 1,
        'needs_review_count': 0,
        'cancelled_count': 0,
        'image_success_count': 1,
        'image_failed_count': 0,
    }

    svc._log_pre_report_summary(stats, dry_run=False, logs_dir='/tmp/JFO_Logs')

    assert any('主处理流程完成' in message for _, message in logs)
    assert any('当前统计: 已记录 3/3' in message for _, message in logs)
    assert any('正在生成审计报告' in message for _, message in logs)


def test_workflow_cancelled_files_are_audited(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        logs = root / 'JFO_Logs'
        (root / 'SONE-753.mp4').write_bytes(b'a' * 32768)
        (root / 'ABF-139.mp4').write_bytes(b'b' * 32768)
        manifest_scans = []

        def fake_scan_manifest(folder_path):
            manifest_scans.append(folder_path)
            return {
                'folder': folder_path,
                'generated_at': 'test',
                'total_files': 2,
                'entries': [],
            }

        monkeypatch.setattr(workflow_mod, 'scan_folder_manifest', fake_scan_manifest)
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
        assert result['after_manifest_path'] is None
        assert manifest_scans == []
        file_results = json.loads(Path(result['file_results_path']).read_text(encoding='utf-8'))
        assert file_results['counts']['cancelled'] == 2
        assert {item['source_name'] for item in file_results['results']} == {'SONE-753.mp4', 'ABF-139.mp4'}
        summary = json.loads(Path(result['summary_path']).read_text(encoding='utf-8'))
        assert summary['artifacts']['after_manifest_status'] == 'skipped-cancelled-fast-stop'


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
        assert 'folder_scan_elapsed_seconds' in summary['timings']
        assert 'after_manifest_elapsed_seconds' in summary['timings']


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
            self.max_filename_bytes = None

        def process_file_atomic(self, file_path, new_filename, image_request, finish_folder, **kwargs):
            self.image_request = image_request
            self.max_filename_bytes = kwargs.get('max_filename_bytes')
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

        def process_series_group_atomic(self, files, title, image_request, finish_folder, **kwargs):
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
            max_filename_bytes=180,
        )

        assert result['success_count'] == 1
        assert atomic.max_filename_bytes == 180
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
        def process_file_atomic(self, file_path, new_filename, image_url, finish_folder, **kwargs):
            return False, {
                'status': 'failed',
                'reason': 'simulated atomic failure',
                'rollback_ok': True,
                'image_downloaded': False,
            }, 'simulated atomic failure'

        def process_series_group_atomic(self, files, title, image_url, finish_folder, **kwargs):
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


def test_workflow_does_not_remove_preexisting_empty_finish_after_atomic_failure():
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
        def process_file_atomic(self, file_path, new_filename, image_url, finish_folder, **kwargs):
            return False, {
                'status': 'failed',
                'reason': 'simulated atomic failure',
                'rollback_ok': True,
                'image_downloaded': False,
            }, 'simulated atomic failure'

        def process_series_group_atomic(self, files, title, image_url, finish_folder, **kwargs):
            raise AssertionError('not used')

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        logs = root / 'JFO_Logs'
        finish = root / 'Finish'
        finish.mkdir()
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
            finish_folder=str(finish),
            website='javhoo',
            dry_run=False,
            logs_dir=str(logs),
        )

        assert result['failed_count'] == 1
        assert finish.exists()
