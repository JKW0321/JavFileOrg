from pathlib import Path
import unicodedata

import pytest
from PIL import Image

from atomic_processor_v11 import AtomicProcessor
from filename_utils import clean_filename_for_search, sanitize_filename
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

    service = InspectionService(
        log=lambda *_args, **_kwargs: None,
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
    small = tmp_path / 'BAD-001.mp4'
    small_cover = tmp_path / 'BAD-001.jpg'

    _video(small, size=4 * 1024)
    _valid_image(small_cover)

    service = _service(tmp_path)
    service.progress_callback = lambda completed, total, label='': progress.append((completed, total, label))
    result = service.run(folder_path=str(tmp_path), website='javbus')

    assert result['needs_review_count'] == 1
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
    service = InspectionService(
        log=lambda *_args, **_kwargs: None,
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


def test_inspection_normalizes_healthy_legacy_duplicate_suffix_without_duplicate(tmp_path):
    legacy = tmp_path / 'ABF-217 Fixed Title_1.mp4'
    legacy_cover = tmp_path / 'ABF-217 Fixed Title_1.jpg'
    expected = tmp_path / 'ABF-217 Fixed Title.mp4'
    expected_cover = tmp_path / 'ABF-217 Fixed Title.jpg'

    _video(legacy)
    _valid_image(legacy_cover)

    result = _service(tmp_path).run(folder_path=str(tmp_path), website='javbus')

    assert result['success_count'] == 1
    assert expected.exists()
    assert expected_cover.exists()
    assert not legacy.exists()
    assert not legacy_cover.exists()
    assert not (tmp_path / '01.wip').exists()
    assert result['file_results'][0]['reason'] == 'inspection-duplicate-keep-normalized'


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
