from pathlib import Path
import unicodedata

import pytest
from PIL import Image

from atomic_processor_v11 import AtomicProcessor
from filename_utils import clean_filename_for_search, sanitize_filename
import inspection_service as inspection_mod
from inspection_service import InspectionService
from providers.base import ProviderResult


class FakeProvider:
    def search(self, query):
        code = query.upper()
        return ProviderResult(
            ok=True,
            title=f'{code} Fixed Title',
            image_url=f'https://example.test/{query}.jpg',
            detail_url=f'https://example.test/{query}',
            referer=f'https://example.test/{query}',
        )


def _valid_image(path, color=(40, 100, 180)):
    Image.new('RGB', (12, 16), color).save(path)


def _pattern_image(path, invert=False):
    image = Image.new('RGB', (32, 32), (255, 255, 255))
    pixels = image.load()
    for x in range(32):
        for y in range(32):
            dark = x > y
            if invert:
                dark = not dark
            pixels[x, y] = (20, 20, 20) if dark else (235, 235, 235)
    image.save(path)


def _video(path, size=64 * 1024):
    path.write_bytes(b'v' * size)


def _service(tmp_path, events=None, duplicate_image_similarity_threshold=6):
    events = events if events is not None else []

    def download(_image_source, save_path):
        _valid_image(save_path)
        return True

    atomic = AtomicProcessor(download, sanitize_filename)
    return InspectionService(
        log=lambda message, level='INFO': events.append((level, message)),
        provider_factory=lambda _name: FakeProvider(),
        atomic_processor=atomic,
        clean_filename_for_search=clean_filename_for_search,
        sanitize_filename=sanitize_filename,
        smart_truncate_filename=lambda title, _filename, _max_length: title[:_max_length],
        minimum_video_size_bytes=16 * 1024,
        duplicate_image_similarity_threshold=duplicate_image_similarity_threshold,
    )


def _deep_service(*, provider, reference_invert=False, events=None):
    events = events if events is not None else []

    def download(_image_source, save_path):
        _pattern_image(save_path, invert=reference_invert)
        return True

    atomic = AtomicProcessor(download, sanitize_filename)
    return InspectionService(
        log=lambda message, level='INFO': events.append((level, message)),
        provider_factory=lambda _name: provider,
        atomic_processor=atomic,
        clean_filename_for_search=clean_filename_for_search,
        sanitize_filename=sanitize_filename,
        smart_truncate_filename=lambda title, _filename, _max_length: title[:_max_length],
        minimum_video_size_bytes=16 * 1024,
        duplicate_image_similarity_threshold=6,
    )


def test_deep_cover_validation_reports_mismatch_without_modifying_local_files(tmp_path):
    video = tmp_path / 'NTRD-021 Fixed Title.mp4'
    cover = tmp_path / 'NTRD-021 Fixed Title.jpg'
    _video(video)
    _pattern_image(cover)
    original_video = video.read_bytes()
    original_cover = cover.read_bytes()

    class ExactProvider:
        def __init__(self):
            self.calls = []

        def search(self, query):
            self.calls.append(query)
            return ProviderResult(
                ok=True,
                provider='javbus',
                title='NTRD-021 Exact Title',
                image_url='https://example.test/NTRD-021.jpg',
                detail_url='https://example.test/NTRD-021',
            )

    provider = ExactProvider()
    result = _deep_service(provider=provider, reference_invert=True).run(
        folder_path=str(tmp_path),
        website='javbus',
        deep_cover_validation=True,
        deep_cover_selected_files=[video.name],
        deep_cover_similarity_threshold=6,
    )

    assert result['needs_review_count'] == 1
    assert result['normal_count'] == 0
    item = result['file_results'][0]
    assert item['reason'].startswith('inspection-cover-content-mismatch:')
    assert item['cover_content_verified'] is True
    assert item['cover_hash_distance'] > item['cover_hash_threshold']
    assert video.read_bytes() == original_video
    assert cover.read_bytes() == original_cover
    assert provider.calls == ['ntrd-021']


def test_deep_cover_validation_reuses_one_reference_for_video_group(tmp_path):
    videos = [
        tmp_path / 'ABF-217 Fixed Title_A.mp4',
        tmp_path / 'ABF-217 Fixed Title_B.mp4',
    ]
    cover = tmp_path / 'ABF-217 Fixed Title.jpg'
    for video in videos:
        _video(video)
    _pattern_image(cover)

    class ExactProvider:
        def __init__(self):
            self.calls = []

        def search(self, query):
            self.calls.append(query)
            return ProviderResult(
                ok=True,
                provider='javbus',
                title='ABF-217 Exact Title',
                image_url='https://example.test/ABF-217.jpg',
                detail_url='https://example.test/ABF-217',
            )

    provider = ExactProvider()
    result = _deep_service(provider=provider).run(
        folder_path=str(tmp_path),
        website='javbus',
        deep_cover_validation=True,
        deep_cover_selected_files=[video.name for video in videos],
        deep_cover_similarity_threshold=6,
    )

    assert result['normal_count'] == 2
    assert result['unverified_count'] == 0
    assert provider.calls == ['abf-217']
    assert all(item.get('cover_content_verified') for item in result['file_results'])
    assert sum(bool(item.get('cover_reference_cache_hit')) for item in result['file_results']) == 1


def test_deep_cover_validation_separates_unavailable_reference_from_normal(tmp_path):
    video = tmp_path / 'ABF-217 Fixed Title.mp4'
    cover = tmp_path / 'ABF-217 Fixed Title.jpg'
    _video(video)
    _pattern_image(cover)

    class OfflineProvider:
        def search(self, _query):
            return ProviderResult(
                ok=False,
                provider='javbus',
                error_type='network-error',
                message='temporary timeout',
            )

    result = _deep_service(provider=OfflineProvider()).run(
        folder_path=str(tmp_path),
        website='javbus',
        deep_cover_validation=True,
        deep_cover_selected_files=[video.name],
    )

    assert result['normal_count'] == 0
    assert result['unverified_count'] == 1
    assert result['needs_review_count'] == 0
    item = result['file_results'][0]
    assert item['status'] == 'skipped'
    assert item['reason'] == 'inspection-cover-content-unverified'
    assert '本地文件保持原样' in item['reason_text']


def test_inspection_repairs_corrupt_cover_without_moving_video(tmp_path):
    video = tmp_path / 'ABF-217 Fixed Title.mp4'
    cover = tmp_path / 'ABF-217 Fixed Title.jpg'
    events = []
    _video(video)
    cover.write_text('not an image', encoding='utf-8')

    result = _service(tmp_path, events).run(folder_path=str(tmp_path), website='javbus')

    assert result['success_count'] == 1
    assert result['file_results'][0]['size'] == 64 * 1024
    assert any('巡检修复成功' in message and 'ABF-217 Fixed Title.mp4' in message for _level, message in events)
    assert video.exists()
    assert cover.exists()
    with Image.open(cover) as image:
        assert image.size == (12, 16)
    assert (tmp_path / '01.wip' / 'ABF-217 Fixed Title.jpg').exists()


def test_inspection_cleans_only_safe_dot_metadata_files(tmp_path):
    (tmp_path / '.DS_Store').write_bytes(b'metadata')
    (tmp_path / '._ABF-217.mp4').write_bytes(b'apple-double')
    important = tmp_path / '.important'
    important.write_text('keep', encoding='utf-8')

    result = _service(tmp_path).run(folder_path=str(tmp_path), website='javbus')

    assert result['total_files'] == 0
    assert not (tmp_path / '.DS_Store').exists()
    assert not (tmp_path / '._ABF-217.mp4').exists()
    assert important.read_text(encoding='utf-8') == 'keep'


@pytest.mark.parametrize(
    ('video_name', 'cover_name', 'expected_video_name', 'expected_normal', 'expected_success'),
    [
        (
            'DASS-592 Long Organized Title-c.mp4',
            'DASS-592 Long Organized Title.jpg',
            'DASS-592 Long Organized Title-c.mp4',
            1,
            0,
        ),
        (
            'DV-1544 Human Business_1.avi',
            'DV-1544 Human Business.jpg',
            'DV-1544 Human Business.avi',
            0,
            1,
        ),
        (
            'STAR-534 Actress Title.mkv',
            'STAR-534 Title Actress.jpg',
            'STAR-534 Actress Title.mkv',
            1,
            0,
        ),
    ],
)
def test_inspection_pairs_cover_by_exact_code_when_titles_or_suffixes_differ(
    tmp_path,
    video_name,
    cover_name,
    expected_video_name,
    expected_normal,
    expected_success,
):
    video = tmp_path / video_name
    cover = tmp_path / cover_name
    _video(video)
    _valid_image(cover)

    result = _service(tmp_path).run(folder_path=str(tmp_path), website='javbus')

    assert result['normal_count'] == expected_normal
    assert result['success_count'] == expected_success
    assert result['needs_review_count'] == 0
    assert (tmp_path / expected_video_name).exists()
    assert video.exists() is (video_name == expected_video_name)
    assert cover.exists()
    assert not (tmp_path / '01.wip').exists()
    item = result['file_results'][0]
    assert item['target_image_path'] == str(cover)
    assert item['reason'] == (
        'inspection-ok-no-action'
        if expected_normal
        else 'inspection-single-sequence-normalized'
    )


def test_inspection_does_not_pair_partial_or_conflicting_codes(tmp_path):
    video = tmp_path / 'MIFD-153 Organized Title.mp4'
    wrong_cover = tmp_path / 'FD-153 Different Product.jpg'
    _video(video)
    _valid_image(wrong_cover)

    result = _service(tmp_path).run(folder_path=str(tmp_path), website='javbus')

    orphan = next(
        item for item in result['file_results']
        if item.get('reason') == 'inspection-orphan-image-moved-to-wip'
    )
    assert orphan['source_name'] == wrong_cover.name
    assert not wrong_cover.exists()
    assert (tmp_path / '01.wip' / wrong_cover.name).exists()


def test_cover_repair_does_not_move_same_corrupt_path_twice(tmp_path, monkeypatch):
    video = tmp_path / 'ABP-721 Organized Title.mp4'
    cover = tmp_path / 'ABP-721 Organized Title.jpg'
    _video(video)
    cover.write_text('corrupt', encoding='utf-8')
    moves = []
    original_move = inspection_mod.shutil.move

    def counted_move(source, target):
        moves.append((str(source), str(target)))
        return original_move(source, target)

    monkeypatch.setattr(inspection_mod.shutil, 'move', counted_move)

    result = _service(tmp_path).run(folder_path=str(tmp_path), website='javbus')

    old_cover_moves = [source for source, _target in moves if source == str(cover)]
    assert old_cover_moves == [str(cover)]
    assert result['success_count'] == 1
    assert cover.exists()


def test_cover_commit_failure_is_one_file_failure_and_restores_old_cover(tmp_path):
    first_video = tmp_path / 'ABP-721 Organized Title.mp4'
    first_cover = tmp_path / 'ABP-721 Organized Title.jpg'
    second_video = tmp_path / 'ABP-722 Organized Title.mp4'
    second_cover = tmp_path / 'ABP-722 Organized Title.jpg'
    _video(first_video)
    _video(second_video)
    first_cover.write_text('corrupt', encoding='utf-8')
    _valid_image(second_cover)

    service = _service(tmp_path)
    original_commit = service.atomic_processor._move_temp_image_to_final

    def fail_first_commit(temp_path, final_path):
        if str(final_path) == str(first_cover):
            raise FileNotFoundError(2, 'network share path unavailable', str(final_path))
        return original_commit(temp_path, final_path)

    service.atomic_processor._move_temp_image_to_final = fail_first_commit
    result = service.run(folder_path=str(tmp_path), website='javbus')

    assert result['failed_count'] == 1
    assert result['normal_count'] == 1
    failed = next(item for item in result['file_results'] if item['status'] == 'failed')
    assert failed['reason'].startswith('inspection-cover-commit-failed:')
    assert failed['rollback_ok'] is True
    assert first_cover.exists()
    assert first_cover.read_text(encoding='utf-8') == 'corrupt'
    assert second_cover.exists()


def test_inspection_notifies_ui_before_after_manifest_scan(tmp_path, monkeypatch):
    video = tmp_path / 'ABF-217 Fixed Title.mp4'
    cover = tmp_path / 'ABF-217 Fixed Title.jpg'
    logs = tmp_path / 'JFO_Logs'
    _video(video)
    _valid_image(cover)
    order = []

    original_scan = inspection_mod.scan_folder_manifest

    def observed_scan(*args, **kwargs):
        order.append('after-manifest-scan')
        return original_scan(*args, **kwargs)

    monkeypatch.setattr(inspection_mod, 'scan_folder_manifest', observed_scan)
    service = _service(tmp_path)
    service.finalizing_callback = lambda result, dry_run=False: order.append('ui-finalizing')

    result = service.run(
        folder_path=str(tmp_path),
        website='javbus',
        logs_dir=str(logs),
    )

    assert result['normal_count'] == 1
    assert order[:2] == ['ui-finalizing', 'after-manifest-scan']


def test_inspection_reuses_scanned_video_size_without_restating_network_file(
    tmp_path,
    monkeypatch,
):
    video = tmp_path / 'ABF-217 Fixed Title.mp4'
    cover = tmp_path / 'ABF-217 Fixed Title.jpg'
    _video(video)
    _valid_image(cover)

    service = _service(tmp_path)
    service._scan_current_dir = lambda _folder: ([video], [cover])
    original_stat = Path.stat

    def guarded_stat(path, *args, **kwargs):
        if path == video:
            raise AssertionError('cached network video size must avoid Path.stat')
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'stat', guarded_stat)

    result = service.run(
        folder_path=str(tmp_path),
        website='javbus',
        known_video_sizes={video.name: 64 * 1024},
    )

    assert result['normal_count'] == 1
    assert result['failed_count'] == 0


def test_sequence_cover_context_uses_prefix_index_in_large_folder(
    tmp_path,
    monkeypatch,
):
    videos = [
        tmp_path / f'VID-{index:04d} Unrelated Title.mp4'
        for index in range(80)
    ]
    images = [
        tmp_path / f'IMG-{index:04d} Different Cover.jpg'
        for index in range(80)
    ]
    for image in images:
        image.touch()

    calls = 0
    original_split = inspection_mod.split_sequence_suffix

    def counted_split(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original_split(*args, **kwargs)

    monkeypatch.setattr(inspection_mod, 'split_sequence_suffix', counted_split)

    result = _service(tmp_path)._shared_cover_stems_for_sequences(videos, images)

    assert result == {}
    assert calls <= len(videos) + len(images)


def test_inspection_routes_uncensored_marker_to_uncensored_provider_for_cover_repair(tmp_path):
    video = tmp_path / 'CARIB-011126-001 Sample Title.mp4'
    cover = tmp_path / 'CARIB-011126-001 Sample Title.jpg'
    calls = []
    events = []

    _video(video)
    cover.write_text('not an image', encoding='utf-8')

    class NamedProvider:
        def __init__(self, name):
            self.name = name

        def search(self, query):
            calls.append((self.name, query))
            return ProviderResult(
                ok=True,
                provider=self.name,
                title=f'{query.upper()} Fixed Title',
                image_url=f'https://example.test/{self.name}/{query}.jpg',
                detail_url=f'https://example.test/{self.name}/{query}',
                referer=f'https://example.test/{self.name}/{query}',
            )

    def download(_image_source, save_path):
        _valid_image(save_path)
        return True

    atomic = AtomicProcessor(download, sanitize_filename)
    service = InspectionService(
        log=lambda message, level='INFO': events.append((level, message)),
        provider_factory=lambda name: NamedProvider(name),
        atomic_processor=atomic,
        clean_filename_for_search=clean_filename_for_search,
        sanitize_filename=sanitize_filename,
        smart_truncate_filename=lambda title, _filename, _max_length: title[:_max_length],
    )

    result = service.run(folder_path=str(tmp_path), website='auto_all')

    assert result['success_count'] == 1
    assert calls == [('uncensored', 'carib-011126-001')]
    assert result['file_results'][0]['provider'] == 'uncensored'
    assert any('auto_all -> uncensored' in message for _level, message in events)
    assert any('巡检数据源策略: 全自动' in message for _level, message in events)


def test_inspection_keeps_specified_uncensored_source_for_general_code(tmp_path):
    original = tmp_path / 'STARS-239_Uncen.mp4'
    calls = []
    _video(original)

    class NamedProvider(FakeProvider):
        def __init__(self, name):
            self.name = name

        def search(self, query):
            calls.append((self.name, query))
            return super().search(query)

    def download(_image_source, save_path):
        _valid_image(save_path)
        return True

    events = []
    service = InspectionService(
        log=lambda message, level='INFO': events.append((level, message)),
        provider_factory=lambda name: NamedProvider(name),
        atomic_processor=AtomicProcessor(download, sanitize_filename),
        clean_filename_for_search=clean_filename_for_search,
        sanitize_filename=sanitize_filename,
        smart_truncate_filename=lambda title, _filename, _max_length: title[:_max_length],
    )

    result = service.run(folder_path=str(tmp_path), website='uncensored')

    assert calls == [('uncensored', 'stars-239')]
    assert result['success_count'] == 1
    assert result['file_results'][0]['provider'] == 'uncensored'


def test_inspection_processes_unprocessed_video_in_place(tmp_path):
    original = tmp_path / 'hhd800.com@MIDA-588.mp4'
    _video(original)

    result = _service(tmp_path).run(folder_path=str(tmp_path), website='javbus')

    assert result['success_count'] == 1
    assert not original.exists()
    assert (tmp_path / 'MIDA-588 Fixed Title.mp4').exists()
    assert (tmp_path / 'MIDA-588 Fixed Title.jpg').exists()


def test_inspection_rejects_provider_result_for_different_code(tmp_path):
    original = tmp_path / 'fd-153.mp4'
    events = []
    _video(original)

    class WrongProvider:
        def search(self, _query):
            return ProviderResult(
                ok=True,
                provider='javhoo',
                title='MIFD-153 Wrong Search Result',
                image_url='https://pics.javhoo.net/mifd-153.jpg',
                detail_url='https://www.javhoo.com/en/mifd-153',
            )

    service = InspectionService(
        log=lambda message, level='INFO': events.append((level, message)),
        provider_factory=lambda _name: WrongProvider(),
        atomic_processor=AtomicProcessor(
            lambda _source, save_path: (_valid_image(save_path) or True),
            sanitize_filename,
        ),
        clean_filename_for_search=clean_filename_for_search,
        sanitize_filename=sanitize_filename,
        smart_truncate_filename=lambda title, _filename, _max_length: title[:_max_length],
    )

    result = service.run(folder_path=str(tmp_path), website='javhoo')

    assert result['failed_count'] == 1
    assert original.exists()
    assert not list(tmp_path.glob('MIFD-153*'))
    item = result['file_results'][0]
    assert item['reason'].startswith('provider:code-mismatch:')
    assert '返回番号 MIFD-153' in item['reason_text']
    assert any('已拒绝自动修改' in message for _level, message in events)


def test_inspection_does_not_treat_temporarily_unavailable_video_as_small(tmp_path):
    ghost_video = tmp_path / 'DASD-948 Title.mp4'
    paired_cover = tmp_path / 'DASD-948 Title.jpg'
    _valid_image(paired_cover)
    service = _service(tmp_path)
    service._scan_current_dir = lambda _folder: ([ghost_video], [paired_cover])

    result = service.run(folder_path=str(tmp_path), website='javbus')

    assert result['needs_review_count'] == 0
    assert result['failed_count'] == 0
    assert result['file_results'][0]['status'] == 'skipped'
    assert result['file_results'][0]['reason'] == 'inspection-video-deferred'
    assert '延后' in result['file_results'][0]['reason_text']
    assert paired_cover.exists()
    assert not (tmp_path / '01.wip').exists()


def test_inspection_reports_healthy_paired_video_as_skipped_without_log_noise(tmp_path):
    video = tmp_path / 'ABF-217 Fixed Title.mp4'
    cover = tmp_path / 'ABF-217 Fixed Title.jpg'
    events = []
    results = []

    _video(video)
    _valid_image(cover)

    service = _service(tmp_path, events)
    service.file_result_callback = lambda item: results.append(item)
    result = service.run(folder_path=str(tmp_path), website='javbus')

    assert result['file_result_counts']['skipped'] == 1
    assert result['normal_count'] == 1
    assert results[0]['status'] == 'skipped'
    assert results[0]['reason'] == 'inspection-ok-no-action'
    assert not any('巡检跳过' in message for _level, message in events)
    assert video.exists()
    assert cover.exists()


def test_inspection_healthy_pair_does_not_create_provider(tmp_path):
    video = tmp_path / 'ABF-217 Fixed Title.mp4'
    cover = tmp_path / 'ABF-217 Fixed Title.jpg'

    _video(video)
    _valid_image(cover)

    atomic = AtomicProcessor(lambda *_args: True, sanitize_filename)
    service = InspectionService(
        log=lambda *_args, **_kwargs: None,
        provider_factory=lambda _name: (_ for _ in ()).throw(AssertionError('provider should not be created')),
        atomic_processor=atomic,
        clean_filename_for_search=clean_filename_for_search,
        sanitize_filename=sanitize_filename,
        smart_truncate_filename=lambda title, _filename, _max_length: title[:_max_length],
    )

    result = service.run(folder_path=str(tmp_path), website='javbus')

    assert result['file_result_counts']['skipped'] == 1
    assert result['normal_count'] == 1
    assert result['file_results'][0]['reason'] == 'inspection-ok-no-action'


def test_inspection_emits_explicit_file_lifecycle_states(tmp_path):
    video = tmp_path / 'ABF-217 Fixed Title.mp4'
    cover = tmp_path / 'ABF-217 Fixed Title.jpg'
    lifecycle = []
    _video(video)
    _valid_image(cover)

    service = _service(tmp_path)
    service.file_status_callback = (
        lambda source_name, status, stage='': lifecycle.append(
            (source_name, status, stage)
        )
    )

    result = service.run(folder_path=str(tmp_path), website='javbus')

    assert result['normal_count'] == 1
    assert lifecycle == [
        (video.name, 'prechecking', 'small-video'),
        (video.name, 'prechecked', 'small-video'),
        (video.name, 'checking', 'cover-health'),
    ]


def test_inspection_emits_duplicate_stage_progress(tmp_path):
    progress = []
    for code in ('ABF-217', 'ABF-218'):
        video = tmp_path / f'{code} Fixed Title.mp4'
        cover = tmp_path / f'{code} Fixed Title.jpg'
        _video(video)
        _valid_image(cover)

    service = _service(tmp_path)
    service.progress_callback = lambda completed, total, label='': progress.append((completed, total, label))
    result = service.run(folder_path=str(tmp_path), website='javbus')

    assert result['normal_count'] == 2
    assert any(label.startswith('巡检重复 ') for _completed, _total, label in progress)
    assert any(total >= 8 for _completed, total, _label in progress)


def test_inspection_emits_repair_stage_progress_for_file_changes(tmp_path):
    progress = []
    events = []
    small = tmp_path / 'BAD-001.mp4'
    small_cover = tmp_path / 'BAD-001.jpg'

    _video(small, size=4 * 1024)
    _valid_image(small_cover)

    service = _service(tmp_path, events)
    service.progress_callback = lambda completed, total, label='': progress.append((completed, total, label))
    result = service.run(folder_path=str(tmp_path), website='javbus')

    assert result['needs_review_count'] == 1
    item = result['file_results'][0]
    assert item['reason'] == 'inspection-small-video-moved-to-wip'
    assert '实际 4.0 KB' in item['reason_text']
    assert '阈值 16.0 KB' in item['reason_text']
    assert '疑似下载不完整或占位文件' in item['reason_text']
    assert any(
        '视频文件过小（实际 4.0 KB，小于阈值 16.0 KB）' in message
        and 'inspection-small-video-moved-to-wip' not in message
        for _level, message in events
    )
    assert any(label.startswith('修复小视频 ') for _completed, _total, label in progress)


def test_inspection_does_not_validate_non_duplicate_covers_in_duplicate_prefilter(tmp_path):
    for code in ('ABF-217', 'ABF-218', 'ABF-219'):
        video = tmp_path / f'{code} Fixed Title.mp4'
        cover = tmp_path / f'{code} Fixed Title.jpg'
        _video(video)
        _valid_image(cover)

    service = _service(tmp_path)
    original_is_image_valid = service._is_image_valid
    calls = []

    def counted_is_image_valid(path):
        calls.append(Path(path).name)
        return original_is_image_valid(path)

    service._is_image_valid = counted_is_image_valid
    service._image_dhash = lambda path: (_ for _ in ()).throw(AssertionError(f'unexpected hash for {path}'))
    result = service.run(folder_path=str(tmp_path), website='javbus')

    assert result['file_result_counts']['skipped'] == 3
    assert sorted(calls) == [
        'ABF-217 Fixed Title.jpg',
        'ABF-218 Fixed Title.jpg',
        'ABF-219 Fixed Title.jpg',
    ]


def test_inspection_moves_small_videos_orphan_and_duplicate_images_to_wip(tmp_path):
    small = tmp_path / 'BAD-001.mp4'
    small_pair = tmp_path / 'BAD-001.jpg'
    orphan = tmp_path / 'ORPHAN-001.jpg'
    video = tmp_path / 'ABF-100 Fixed Title.mp4'
    cover = tmp_path / 'ABF-100 Fixed Title.jpg'
    duplicate = tmp_path / 'ABF-100 Fixed Title.png'

    _video(small, size=4 * 1024)
    _valid_image(small_pair)
    _valid_image(orphan)
    _video(video)
    _valid_image(cover)
    _valid_image(duplicate, color=(90, 40, 100))

    result = _service(tmp_path).run(folder_path=str(tmp_path), website='javbus')

    wip = tmp_path / '01.wip'
    assert result['skipped_small'] == 3
    assert (wip / small.name).exists()
    assert (wip / small_pair.name).exists()
    assert (wip / orphan.name).exists()
    assert (wip / duplicate.name).exists()
    assert cover.exists()
    assert video.exists()


def test_inspection_moves_duplicate_video_pair_suffix_to_wip(tmp_path):
    original = tmp_path / 'ABF-217 Fixed Title.mp4'
    original_cover = tmp_path / 'ABF-217 Fixed Title.jpg'
    duplicate = tmp_path / 'ABF-217 Fixed Title_1.mp4'
    duplicate_cover = tmp_path / 'ABF-217 Fixed Title_1.jpg'
    events = []

    _video(original)
    _valid_image(original_cover)
    _video(duplicate)
    _valid_image(duplicate_cover)

    result = _service(tmp_path, events).run(folder_path=str(tmp_path), website='javbus')

    wip = tmp_path / '01.wip'
    assert result['needs_review_count'] == 1
    assert original.exists()
    assert original_cover.exists()
    assert not duplicate.exists()
    assert not duplicate_cover.exists()
    assert (wip / duplicate.name).exists()
    assert (wip / duplicate_cover.name).exists()
    assert any('duplicate-video-pair' in message for _level, message in events)
    assert not any('duplicate-keep-normalized' in item.get('reason', '') for item in result['file_results'])


def test_inspection_matches_duplicate_suffix_with_unicode_normalized_stems(tmp_path):
    title_nfc = unicodedata.normalize('NFC', 'DASS-930 ガール')
    title_nfd = unicodedata.normalize('NFD', 'DASS-930 ガール')
    original = tmp_path / f'{title_nfc}.mp4'
    original_cover = tmp_path / f'{title_nfc}.jpg'
    duplicate = tmp_path / f'{title_nfd}_1.mp4'
    duplicate_cover = tmp_path / f'{title_nfd}_1.jpg'

    _video(original)
    _valid_image(original_cover)
    _video(duplicate)
    _valid_image(duplicate_cover)

    result = _service(tmp_path).run(folder_path=str(tmp_path), website='javbus')

    wip = tmp_path / '01.wip'
    assert result['needs_review_count'] == 1
    assert original.exists()
    assert original_cover.exists()
    assert not duplicate.exists()
    assert not duplicate_cover.exists()
    assert any(path.name == duplicate.name for path in wip.iterdir())
    assert any(path.name == duplicate_cover.name for path in wip.iterdir())
    assert 'duplicate-video-pair-moved-to-wip' in result['file_results'][0]['reason']


def test_inspection_keeps_sequence_parts_with_dash_suffix(tmp_path):
    first = tmp_path / 'ABF-139-1 Fixed Title.mp4'
    first_cover = tmp_path / 'ABF-139-1 Fixed Title.jpg'
    second = tmp_path / 'ABF-139-2 Fixed Title.mp4'
    second_cover = tmp_path / 'ABF-139-2 Fixed Title.jpg'

    for path in (first, second):
        _video(path)
    for path in (first_cover, second_cover):
        _valid_image(path)

    result = _service(tmp_path).run(folder_path=str(tmp_path), website='javbus')

    assert result['needs_review_count'] == 0
    assert first.exists()
    assert first_cover.exists()
    assert second.exists()
    assert second_cover.exists()
    assert not (tmp_path / '01.wip').exists()


@pytest.mark.parametrize("suffixes", [
    ("-1", "-2", "-3"),
    ("_1", "_2", "_3"),
    ("a", "b", "c"),
    ("(1)", "(2)", "(3)"),
    ("（1）", "（2）", "（3）"),
    ("【1】", "【2】", "【3】"),
    (" CD1", " CD2", " CD3"),
    (" 第1集", " 第2集", " 第3集"),
])
def test_inspection_preserves_one_shared_cover_for_organized_sequence_group(
    tmp_path,
    suffixes,
):
    videos = [
        tmp_path / f'ABF-139 Fixed Title{suffix}.mp4'
        for suffix in suffixes
    ]
    shared_cover = tmp_path / 'ABF-139 Fixed Title.jpg'

    for video in videos:
        _video(video)
    _valid_image(shared_cover)

    atomic = AtomicProcessor(lambda *_args: True, sanitize_filename)
    service = InspectionService(
        log=lambda *_args, **_kwargs: None,
        provider_factory=lambda _name: (_ for _ in ()).throw(
            AssertionError('healthy sequence group must not download per-part covers')
        ),
        atomic_processor=atomic,
        clean_filename_for_search=clean_filename_for_search,
        sanitize_filename=sanitize_filename,
        smart_truncate_filename=lambda title, _filename, _max_length: title[:_max_length],
    )

    result = service.run(folder_path=str(tmp_path), website='javbus')

    assert result['file_result_counts']['skipped'] == 3
    assert all(video.exists() for video in videos)
    assert shared_cover.exists()
    assert not (tmp_path / '01.wip').exists()
    assert sorted(path.name for path in tmp_path.glob('*.jpg')) == [shared_cover.name]
    assert {
        item['target_image_path']
        for item in result['file_results']
    } == {str(shared_cover)}


@pytest.mark.parametrize("suffixes", [
    ("_1", "_2", "_3"),
    (" (1)", " (2)", " (3)"),
])
def test_inspection_does_not_treat_sequence_suffixes_as_duplicate_copies(
    tmp_path,
    suffixes,
):
    videos = [
        tmp_path / f'ABF-139 Fixed Title{suffix}.mp4'
        for suffix in suffixes
    ]
    shared_cover = tmp_path / 'ABF-139 Fixed Title.jpg'

    for video in videos:
        _video(video)
        _valid_image(video.with_suffix('.jpg'))
    _valid_image(shared_cover)

    result = _service(tmp_path).run(folder_path=str(tmp_path), website='javbus')

    assert all(video.exists() for video in videos)
    assert shared_cover.exists()
    assert not any(
        'duplicate-video-pair-moved-to-wip' in item.get('reason', '')
        for item in result['file_results']
    )


@pytest.mark.parametrize("suffixes", [
    ("-1", "-2", "-3"),
    ("a", "b", "c"),
    ("（1）", "（2）", "（3）"),
])
def test_inspection_moves_redundant_per_part_covers_when_shared_cover_exists(
    tmp_path,
    suffixes,
):
    videos = [
        tmp_path / f'ABF-139 Fixed Title{suffix}.mp4'
        for suffix in suffixes
    ]
    per_part_covers = [video.with_suffix('.jpg') for video in videos]
    shared_cover = tmp_path / 'ABF-139 Fixed Title.jpg'

    for video in videos:
        _video(video)
    _valid_image(shared_cover)
    for cover in per_part_covers:
        _valid_image(cover)

    atomic = AtomicProcessor(lambda *_args: True, sanitize_filename)
    events = []
    service = InspectionService(
        log=lambda message, level='INFO': events.append((level, message)),
        provider_factory=lambda _name: (_ for _ in ()).throw(
            AssertionError('healthy shared cover must not trigger provider access')
        ),
        atomic_processor=atomic,
        clean_filename_for_search=clean_filename_for_search,
        sanitize_filename=sanitize_filename,
        smart_truncate_filename=lambda title, _filename, _max_length: title[:_max_length],
    )

    result = service.run(folder_path=str(tmp_path), website='javbus')

    assert shared_cover.exists()
    assert all(video.exists() for video in videos)
    assert all(not cover.exists() for cover in per_part_covers)
    assert all((tmp_path / '01.wip' / cover.name).exists() for cover in per_part_covers)
    assert sum(
        item.get('reason') == 'inspection-redundant-sequence-cover-moved-to-wip'
        for item in result['file_results']
    ) == 3
    assert result['success_count'] == 3
    assert result['needs_review_count'] == 0
    assert result['normal_count'] == 0
    assert sum(
        level == 'SUCCESS'
        and '巡检修复成功' in message
        and '已保留共享封面' in message
        and '冗余分集封面移入 01.wip' in message
        for level, message in events
    ) == 3


def test_inspection_rechecks_redundant_part_covers_after_creating_shared_cover(
    tmp_path,
):
    videos = [
        tmp_path / f'PPT-059 Fixed Title ({sequence}).mp4'
        for sequence in (1, 2, 3, 4)
    ]
    per_part_covers = [video.with_suffix('.jpg') for video in videos]
    shared_cover = tmp_path / 'PPT-059 Fixed Title.jpg'

    for video in videos:
        _video(video)
    for cover in per_part_covers:
        _valid_image(cover)

    result = _service(tmp_path).run(
        folder_path=str(tmp_path),
        website='javbus',
    )

    assert all(video.exists() for video in videos)
    assert shared_cover.exists()
    assert sorted(path.name for path in tmp_path.glob('*.jpg')) == [
        shared_cover.name
    ]
    assert not per_part_covers[0].exists()
    assert all(
        (tmp_path / '01.wip' / cover.name).exists()
        for cover in per_part_covers[1:]
    )
    assert sum(
        item.get('reason') == 'inspection-redundant-sequence-cover-moved-to-wip'
        for item in result['file_results']
    ) == 3


def test_inspection_keeps_per_part_covers_that_differ_from_shared_cover(tmp_path):
    videos = [
        tmp_path / f'ABF-139 Fixed Title-{sequence}.mp4'
        for sequence in (1, 2)
    ]
    per_part_covers = [video.with_suffix('.jpg') for video in videos]
    shared_cover = tmp_path / 'ABF-139 Fixed Title.jpg'

    for video in videos:
        _video(video)
    _pattern_image(shared_cover, invert=False)
    for cover in per_part_covers:
        _pattern_image(cover, invert=True)

    result = _service(tmp_path).run(folder_path=str(tmp_path), website='javbus')

    assert shared_cover.exists()
    assert all(video.exists() for video in videos)
    assert all(cover.exists() for cover in per_part_covers)
    assert not any(
        item.get('reason') == 'inspection-redundant-sequence-cover-moved-to-wip'
        for item in result['file_results']
    )


def test_inspection_repairs_one_shared_cover_for_sequence_group(tmp_path):
    videos = [
        tmp_path / f'ABF-139 Fixed Title-{sequence}.mp4'
        for sequence in (1, 2, 3)
    ]
    shared_cover = tmp_path / 'ABF-139 Fixed Title.jpg'
    provider_calls = []

    for video in videos:
        _video(video)

    class CountingProvider(FakeProvider):
        def search(self, query):
            provider_calls.append(query)
            return super().search(query)

    def download(_image_source, save_path):
        _valid_image(save_path)
        return True

    service = InspectionService(
        log=lambda *_args, **_kwargs: None,
        provider_factory=lambda _name: CountingProvider(),
        atomic_processor=AtomicProcessor(download, sanitize_filename),
        clean_filename_for_search=clean_filename_for_search,
        sanitize_filename=sanitize_filename,
        smart_truncate_filename=lambda title, _filename, _max_length: title[:_max_length],
    )

    result = service.run(folder_path=str(tmp_path), website='javbus')

    assert result['file_result_counts']['success'] == 1
    assert result['file_result_counts']['skipped'] == 2
    assert provider_calls == ['abf-139']
    assert shared_cover.exists()
    assert sorted(path.name for path in tmp_path.glob('*.jpg')) == [shared_cover.name]
    assert {
        item['target_image_path']
        for item in result['file_results']
    } == {str(shared_cover)}


def test_inspection_repairs_uncensored_sequence_group_with_one_shared_cover(tmp_path):
    videos = [
        tmp_path / f'CARIB-011126-001 Fixed Title-{sequence}.mp4'
        for sequence in (1, 2, 3)
    ]
    shared_cover = tmp_path / 'CARIB-011126-001 Fixed Title.jpg'
    calls = []

    for video in videos:
        _video(video)

    class NamedProvider(FakeProvider):
        def __init__(self, name):
            self.name = name

        def search(self, query):
            calls.append((self.name, query))
            return super().search(query)

    def download(_image_source, save_path):
        _valid_image(save_path)
        return True

    service = InspectionService(
        log=lambda *_args, **_kwargs: None,
        provider_factory=lambda name: NamedProvider(name),
        atomic_processor=AtomicProcessor(download, sanitize_filename),
        clean_filename_for_search=clean_filename_for_search,
        sanitize_filename=sanitize_filename,
        smart_truncate_filename=lambda title, _filename, _max_length: title[:_max_length],
    )

    result = service.run(folder_path=str(tmp_path), website='auto_all')

    assert calls == [('uncensored', 'carib-011126-001')]
    assert shared_cover.exists()
    assert sorted(path.name for path in tmp_path.glob('*.jpg')) == [shared_cover.name]
    assert sum(item['status'] == 'success' for item in result['file_results']) == 1
    assert sum(item['status'] == 'skipped' for item in result['file_results']) == 2


def test_inspection_does_not_move_duplicate_video_when_covers_are_not_similar(tmp_path):
    original = tmp_path / 'ABF-217 Fixed Title.mp4'
    original_cover = tmp_path / 'ABF-217 Fixed Title.jpg'
    duplicate = tmp_path / 'ABF-217 Fixed Title_1.mp4'
    duplicate_cover = tmp_path / 'ABF-217 Fixed Title_1.jpg'

    _video(original)
    _pattern_image(original_cover, invert=False)
    _video(duplicate)
    _pattern_image(duplicate_cover, invert=True)

    result = _service(tmp_path).run(folder_path=str(tmp_path), website='javbus')

    assert result['needs_review_count'] == 1
    assert duplicate.exists()
    assert duplicate_cover.exists()
    assert not (tmp_path / '01.wip').exists()
    assert 'duplicate-video-needs-review' in result['file_results'][0]['reason']


def test_inspection_duplicate_similarity_threshold_controls_auto_move(tmp_path):
    original = tmp_path / 'ABF-217 Fixed Title.mp4'
    original_cover = tmp_path / 'ABF-217 Fixed Title.jpg'
    duplicate = tmp_path / 'ABF-217 Fixed Title_1.mp4'
    duplicate_cover = tmp_path / 'ABF-217 Fixed Title_1.jpg'

    _video(original)
    _pattern_image(original_cover, invert=False)
    _video(duplicate)
    _pattern_image(duplicate_cover, invert=True)

    result = _service(tmp_path, duplicate_image_similarity_threshold=64).run(
        folder_path=str(tmp_path),
        website='javbus',
    )

    assert result['needs_review_count'] == 1
    assert not duplicate.exists()
    assert not duplicate_cover.exists()
    assert (tmp_path / '01.wip' / duplicate.name).exists()
    assert 'cover-distance-' in result['file_results'][0]['reason']


def test_inspection_keeps_larger_duplicate_video_and_moves_smaller_original(tmp_path):
    original = tmp_path / 'ABF-217 Fixed Title.mp4'
    original_cover = tmp_path / 'ABF-217 Fixed Title.jpg'
    larger_duplicate = tmp_path / 'ABF-217 Fixed Title_1.mp4'
    larger_duplicate_cover = tmp_path / 'ABF-217 Fixed Title_1.jpg'
    events = []

    _video(original, size=64 * 1024)
    _valid_image(original_cover)
    _video(larger_duplicate, size=256 * 1024)
    _valid_image(larger_duplicate_cover)

    result = _service(tmp_path, events).run(folder_path=str(tmp_path), website='javbus')

    wip = tmp_path / '01.wip'
    assert result['needs_review_count'] == 1
    assert original.exists()
    assert original.stat().st_size == 256 * 1024
    assert original_cover.exists()
    assert not larger_duplicate.exists()
    assert not larger_duplicate_cover.exists()
    assert (wip / original.name).exists()
    assert (wip / original_cover.name).exists()
    assert any(item.get('reason') == 'inspection-duplicate-keep-normalized' for item in result['file_results'])
    assert any('已规范重复保留文件名' in message for _level, message in events)


def test_inspection_removes_sequence_marker_from_single_video_and_cover(tmp_path):
    legacy = tmp_path / 'ABF-217 Fixed Title_1.mp4'
    legacy_cover = tmp_path / 'ABF-217 Fixed Title_1.jpg'
    expected_video = tmp_path / 'ABF-217 Fixed Title.mp4'
    expected_cover = tmp_path / 'ABF-217 Fixed Title.jpg'

    _video(legacy)
    _valid_image(legacy_cover)

    result = _service(tmp_path).run(folder_path=str(tmp_path), website='javbus')

    assert result['success_count'] == 1
    assert not legacy.exists()
    assert expected_video.exists()
    assert expected_cover.exists()
    assert not legacy_cover.exists()
    assert not (tmp_path / '01.wip').exists()
    assert result['file_results'][0]['reason'] == 'inspection-single-sequence-normalized'
    assert result['file_results'][0]['target_video_path'] == str(expected_video)


def test_inspection_removes_fullwidth_five_from_lone_umso_video(tmp_path):
    title = 'UMSO-482 Fixed Title'
    legacy = tmp_path / f'{title}（5）.mp4'
    shared_cover = tmp_path / f'{title}.jpg'
    expected_video = tmp_path / f'{title}.mp4'
    _video(legacy)
    _valid_image(shared_cover)

    result = _service(tmp_path).run(folder_path=str(tmp_path), website='javbus')

    assert not legacy.exists()
    assert expected_video.exists()
    assert shared_cover.exists()
    assert result['success_count'] == 1
    item = next(
        item for item in result['file_results']
        if item.get('reason') == 'inspection-single-sequence-normalized'
    )
    assert item['target_video_path'] == str(expected_video)
    assert item['target_image_path'] == str(shared_cover)


def test_inspection_preserves_parenthesized_age_in_single_video_title(tmp_path):
    title = 'HDKA-166 はだかの主婦 練馬区在住松永さな（30）'
    video = tmp_path / f'{title}.mp4'
    cover = tmp_path / f'{title}.jpg'
    _video(video)
    _valid_image(cover)

    result = _service(tmp_path).run(folder_path=str(tmp_path), website='javbus')

    assert result['success_count'] == 0
    assert result['normal_count'] == 1
    assert video.exists()
    assert cover.exists()
    assert not (tmp_path / 'HDKA-166 はだかの主婦 練馬区在住松永さな.mp4').exists()


@pytest.mark.parametrize('code', ['KNAM-064', 'KNMB-052'])
def test_inspection_does_not_reprocess_organized_title_containing_at_sign(tmp_path, code):
    title = f'{code} 完ナマSTYLE@のあ 既に整理済みのタイトル'
    video = tmp_path / f'{title}.mp4'
    cover = tmp_path / f'{title}.jpg'
    _video(video)
    _valid_image(cover)

    result = _service(tmp_path).run(folder_path=str(tmp_path), website='javbus')

    assert result['success_count'] == 0
    assert result['normal_count'] == 1
    assert video.exists()
    assert cover.exists()


def test_inspection_removes_lone_suffix_once_without_readding_it_for_at_title(tmp_path):
    title = 'KNAM-064 完ナマSTYLE@のあ 既に整理済みのタイトル'
    legacy_video = tmp_path / f'{title}_1.mp4'
    legacy_cover = tmp_path / f'{title}_1.jpg'
    expected_video = tmp_path / f'{title}.mp4'
    expected_cover = tmp_path / f'{title}.jpg'
    _video(legacy_video)
    _valid_image(legacy_cover)

    result = _service(tmp_path).run(folder_path=str(tmp_path), website='javbus')

    assert result['success_count'] == 1
    assert expected_video.exists()
    assert expected_cover.exists()
    assert not legacy_video.exists()
    assert not legacy_cover.exists()
    assert not (tmp_path / f'{title}_2.mp4').exists()
    assert [item['reason'] for item in result['file_results']].count(
        'inspection-single-sequence-normalized'
    ) == 1


def test_inspection_does_not_reprocess_or_truncate_title_with_embedded_later_code(tmp_path):
    title = 'N1069 一刀両断 椎名愛莉 MAAN-1069 unrelated metadata'
    video = tmp_path / f'{title}.wmv'
    cover = tmp_path / f'{title}.jpg'
    _video(video)
    _valid_image(cover)

    result = _service(tmp_path).run(folder_path=str(tmp_path), website='auto_all')

    assert result['success_count'] == 0
    assert result['normal_count'] == 1
    assert result['file_results'][0]['query'] == 'tokyo-hot-n1069'
    assert video.exists()
    assert cover.exists()


def test_inspection_defers_transient_video_stat_failure_without_counting_problem(tmp_path, monkeypatch):
    video = tmp_path / 'ABF-217 Fixed Title.mp4'
    cover = tmp_path / 'ABF-217 Fixed Title.jpg'
    _video(video)
    _valid_image(cover)
    original_stat = Path.stat
    calls = {'count': 0}

    def unavailable_stat(path, *args, **kwargs):
        if path == video and calls['count'] < 2:
            calls['count'] += 1
            raise OSError('temporary NAS read failure')
        return original_stat(path, *args, **kwargs)

    service = _service(tmp_path)
    service._scan_current_dir = lambda _folder: ([video], [cover])
    monkeypatch.setattr(Path, 'stat', unavailable_stat)
    result = service.run(folder_path=str(tmp_path), website='javbus')

    assert result['failed_count'] == 0
    assert result['needs_review_count'] == 0
    deferred = next(item for item in result['file_results'] if item['reason'] == 'inspection-video-deferred')
    assert deferred['status'] == 'skipped'
    assert video.exists()
    assert cover.exists()


def test_inspection_defers_source_that_disappears_before_atomic_commit(tmp_path):
    video = tmp_path / 'hhd800.com@ABF-217.mp4'
    _video(video)

    class DisappearingProvider(FakeProvider):
        def search(self, query):
            video.unlink()
            return super().search(query)

    def download(_image_source, save_path):
        _valid_image(save_path)
        return True

    service = InspectionService(
        log=lambda *_args, **_kwargs: None,
        provider_factory=lambda _name: DisappearingProvider(),
        atomic_processor=AtomicProcessor(download, sanitize_filename),
        clean_filename_for_search=clean_filename_for_search,
        sanitize_filename=sanitize_filename,
        smart_truncate_filename=lambda title, _filename, _max_length: title,
        minimum_video_size_bytes=16 * 1024,
    )
    result = service.run(folder_path=str(tmp_path), website='javbus')

    assert result['failed_count'] == 0
    deferred = next(item for item in result['file_results'] if item['reason'] == 'inspection-video-deferred')
    assert deferred['status'] == 'skipped'


@pytest.mark.parametrize(
    ('video_name', 'expected_cover_name'),
    [
        ('DV-1544 Human Business_1.avi', 'DV-1544 Human Business.jpg'),
        ('ABF-217 Fixed Title (1).mp4', 'ABF-217 Fixed Title.jpg'),
        ('ABF-219 Fixed Title 第2集.mp4', 'ABF-219 Fixed Title.jpg'),
    ],
)
def test_inspection_repairs_single_sequence_file_with_shared_cover_name(
    tmp_path, video_name, expected_cover_name
):
    video = tmp_path / video_name
    _video(video)

    result = _service(tmp_path).run(folder_path=str(tmp_path), website='javbus')

    expected_cover = tmp_path / expected_cover_name
    expected_video = expected_cover.with_suffix(video.suffix)
    assert result['success_count'] == 2
    assert not video.exists()
    assert expected_video.exists()
    assert expected_cover.exists()
    assert not video.with_suffix('.jpg').exists()
    repair_item = next(
        item for item in result['file_results']
        if item.get('reason') == 'inspection-cover-repaired'
    )
    assert repair_item['target_video_path'] == str(expected_video)
    assert repair_item['target_image_path'] == str(expected_cover)


@pytest.mark.parametrize(
    'stem',
    [
        'ABP-532 Real Title 1',
        'ABP-600 Real Title 17',
        'APNS-165 Real Title-C',
        'NSFS-157 Real Title VOL.3',
        'SGKI-062 Real Title R-20',
        'TKI-052 MASOTRONIX 12',
        'ABF-218 Real Title Part A',
    ],
)
def test_inspection_does_not_treat_ambiguous_lone_title_suffix_as_video_group(
    tmp_path, stem
):
    video = tmp_path / f'{stem}.mp4'
    cover = tmp_path / f'{stem}.jpg'
    _video(video)
    _valid_image(cover)

    result = _service(tmp_path).run(folder_path=str(tmp_path), website='javbus')

    assert result['normal_count'] == 1
    assert result['success_count'] == 0
    assert video.exists()
    assert cover.exists()
    assert result['file_results'][0]['reason'] == 'inspection-ok-no-action'


def test_inspection_sequence_cover_normalization_preserves_original_unicode(tmp_path):
    base = unicodedata.normalize('NFD', 'DASS-592 ペニス下さい！！ 椎名心春')
    video = tmp_path / f'{base}_1.mp4'
    cover = tmp_path / f'{base}_1.jpg'
    expected_video = tmp_path / f'{base}.mp4'
    expected_cover = tmp_path / f'{base}.jpg'
    _video(video)
    _valid_image(cover)

    result = _service(tmp_path).run(folder_path=str(tmp_path), website='javbus')

    assert result['success_count'] == 1
    assert not video.exists()
    assert expected_video.exists()
    assert expected_cover.exists()
    assert not cover.exists()
    assert result['file_results'][0]['target_image_path'] == str(expected_cover)


def test_inspection_stop_request_stops_before_full_batch(tmp_path):
    for code in ('ABF-217', 'ABF-218', 'ABF-219'):
        video = tmp_path / f'{code} Fixed Title.mp4'
        cover = tmp_path / f'{code} Fixed Title.jpg'
        _video(video)
        _valid_image(cover)

    events = []
    stopped = {'value': False}
    service = _service(tmp_path, events)
    service.progress_callback = lambda *_args: stopped.__setitem__('value', True)
    service.stop_requested = lambda: stopped['value']

    result = service.run(folder_path=str(tmp_path), website='javbus')

    assert result['cancelled_count'] == 1
    assert result['total_files'] < 3
    assert any('巡检已停止' in message for _level, message in events)


def test_inspection_cancel_skips_after_manifest_scan_for_fast_stop(tmp_path):
    logs_dir = tmp_path / 'JFO_Logs'
    logs_dir.mkdir()
    for code in ('ABF-217', 'ABF-218'):
        video = tmp_path / f'{code} Fixed Title.mp4'
        cover = tmp_path / f'{code} Fixed Title.jpg'
        _video(video)
        _valid_image(cover)

    events = []
    service = _service(tmp_path, events)
    service.stop_requested = lambda: True
    result = service.run(
        folder_path=str(tmp_path),
        website='javbus',
        log_path=str(logs_dir / 'JFO_RUN.log'),
        logs_dir=str(logs_dir),
    )

    assert result['cancelled_count'] == 1
    assert result['after_manifest_path'] is None
    assert result['file_results_path']
    assert not list(logs_dir.glob('inspection_manifest_after_*.json'))
    assert any('跳过处理后清单扫描以加快停止' in message for _level, message in events)


def test_inspection_stop_request_is_latched_after_first_seen(tmp_path):
    for code in ('ABF-217', 'ABF-218', 'ABF-219'):
        video = tmp_path / f'{code} Fixed Title.mp4'
        cover = tmp_path / f'{code} Fixed Title.jpg'
        _video(video)
        _valid_image(cover)

    calls = {'count': 0}

    def stop_once_then_clear():
        calls['count'] += 1
        return calls['count'] == 2

    result = _service(tmp_path).run(
        folder_path=str(tmp_path),
        website='javbus',
    )
    assert result['cancelled_count'] == 0

    events = []
    service = _service(tmp_path, events)
    service.stop_requested = stop_once_then_clear
    result = service.run(folder_path=str(tmp_path), website='javbus')

    assert result['cancelled_count'] == 1
    assert result['total_files'] < 3
    assert any('巡检已停止' in message for _level, message in events)
