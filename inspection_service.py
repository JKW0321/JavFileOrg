#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Inspection and repair workflow for already-organized folders."""
from __future__ import annotations

import os
import re
import shutil
import time
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Callable

from PIL import Image

from app_metadata import BASELINE_VERSION
from manifest_utils import scan_folder_manifest, write_json_report
from provider_router import route_provider
from workflow_service import VIDEO_EXTENSIONS

IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp'}
INSPECTION_SKIP_DIRS = {'JFO_Logs', '.jfo_transactions', '__MACOSX', '01.wip'}
DUPLICATE_COPY_SUFFIX_RE = re.compile(r'(?:_\d+|\s\(\d+\)|\s+copy(?:\s+\d+)?)$', re.IGNORECASE)


class InspectionService:
    """Repair common inconsistencies inside a processed output folder."""

    def __init__(
        self,
        *,
        log: Callable,
        provider_factory: Callable,
        atomic_processor,
        clean_filename_for_search: Callable,
        sanitize_filename: Callable,
        smart_truncate_filename: Callable,
        stop_requested: Callable | None = None,
        progress_callback: Callable | None = None,
        file_result_callback: Callable | None = None,
        minimum_video_size_bytes: int = 16 * 1024,
        duplicate_image_similarity_threshold: int = 6,
        app_version: str = BASELINE_VERSION,
    ):
        self.log = log
        self.provider_factory = provider_factory
        self.atomic_processor = atomic_processor
        self.clean_filename_for_search = clean_filename_for_search
        self.sanitize_filename = sanitize_filename
        self.smart_truncate_filename = smart_truncate_filename
        self.stop_requested = stop_requested or (lambda: False)
        self.progress_callback = progress_callback or (lambda completed, total, label='': None)
        self.file_result_callback = file_result_callback or (lambda item: None)
        self.minimum_video_size_bytes = minimum_video_size_bytes
        self.duplicate_image_similarity_threshold = max(0, int(duplicate_image_similarity_threshold))
        self.app_version = app_version
        self._image_valid_cache = {}
        self._image_hash_cache = {}
        self._provider_instances = {}
        self._stop_seen = False

    def _is_stop_requested(self) -> bool:
        if self._stop_seen:
            return True
        try:
            self._stop_seen = bool(self.stop_requested())
            return self._stop_seen
        except Exception:
            return False

    def _path_signature(self, path: Path):
        try:
            stat = path.stat()
            return str(path), int(stat.st_mtime_ns), int(stat.st_size)
        except OSError:
            return str(path), None, None

    def _stem_key(self, stem: str) -> str:
        text = unicodedata.normalize('NFC', str(stem or ''))
        text = re.sub(r'\s+', ' ', text).strip()
        return text.casefold()

    def _images_for_stem(self, image_by_stem: dict, stem: str):
        return image_by_stem.get(self._stem_key(stem), [])

    def _emit_progress(self, completed, total, label=''):
        try:
            self.progress_callback(completed, total, label)
        except Exception as exc:
            self.log(f'⚠️ 巡检进度更新失败: {exc}', 'WARNING')

    def _emit_file_result(self, item, *, log_result=True):
        if log_result:
            self._log_file_result(item or {})
        try:
            self.file_result_callback(dict(item or {}))
        except Exception as exc:
            self.log(f'⚠️ 巡检文件状态更新失败: {exc}', 'WARNING')

    def _get_provider(self, provider_name: str):
        if provider_name not in self._provider_instances:
            self._provider_instances[provider_name] = self.provider_factory(provider_name)
        return self._provider_instances[provider_name]

    def _resolve_provider_for_video(self, preferred_provider: str, video_path: Path, query: str):
        decision = route_provider(preferred_provider, video_path.name, query)
        provider_name = preferred_provider
        reason = decision.get('reason') or ''
        if preferred_provider != 'uncensored' and decision.get('warning_only') and reason.startswith('marker:'):
            provider_name = 'uncensored'
            self.log(
                f'🧭 巡检自动切换数据源: {video_path.name} | {preferred_provider} -> uncensored | {reason}',
                'INFO',
            )
        return self._get_provider(provider_name), provider_name

    def _log_file_result(self, item):
        status = item.get('status') or 'failed'
        name = item.get('source_name') or Path(item.get('source_path') or '').name or 'unknown'
        provider = item.get('provider') or '-'
        query = item.get('query') or '-'
        reason = item.get('reason') or '-'
        after = item.get('after') or ''
        if status == 'success':
            self.log(
                f'✅ 巡检修复成功: {name} | provider={provider} | query={query} | 原因: {reason}',
                'SUCCESS',
            )
        elif status == 'needs_review':
            suffix = f' | {after}' if after else ''
            self.log(
                f'⚠️ 巡检待确认: {name} | 原因: {reason}{suffix}',
                'WARNING',
            )
        elif status == 'skipped':
            self.log(f'🙈 巡检跳过: {name} | 原因: {reason}', 'INFO')
        else:
            self.log(
                f'❌ 巡检未修复: {name} | provider={provider} | query={query} | 原因: {reason} | 源文件保持原样',
                'ERROR',
            )

    def _file_size(self, path: Path) -> int:
        try:
            return int(path.stat().st_size)
        except OSError:
            return 0

    def _is_image_valid(self, path: Path) -> bool:
        key = self._path_signature(path)
        if key in self._image_valid_cache:
            return self._image_valid_cache[key]
        try:
            if not path.exists() or path.stat().st_size <= 0:
                self._image_valid_cache[key] = False
                return False
            with Image.open(path) as image:
                image.load()
                width, height = image.size
            if width <= 0 or height <= 0:
                self._image_valid_cache[key] = False
                return False
            self._image_valid_cache[key] = True
            return True
        except Exception:
            self._image_valid_cache[key] = False
            return False

    def _image_dhash(self, path: Path):
        key = self._path_signature(path)
        if key in self._image_hash_cache:
            return self._image_hash_cache[key]
        if self._is_stop_requested():
            return None
        try:
            with Image.open(path) as image:
                image = image.convert('L').resize((9, 8), Image.Resampling.LANCZOS)
                pixel_data = getattr(image, 'get_flattened_data', image.getdata)
                pixels = list(pixel_data())
            value = 0
            for row in range(8):
                for col in range(8):
                    value <<= 1
                    if pixels[row * 9 + col] > pixels[row * 9 + col + 1]:
                        value |= 1
            self._image_hash_cache[key] = value
            return value
        except Exception:
            self._image_hash_cache[key] = None
            return None

    def _image_hash_distance(self, left: Path | None, right: Path | None):
        if not left or not right:
            return None
        left_hash = self._image_dhash(left)
        right_hash = self._image_dhash(right)
        if left_hash is None or right_hash is None:
            return None
        return (left_hash ^ right_hash).bit_count()

    def _scan_current_dir(self, folder_path: str):
        root = Path(folder_path)
        videos = []
        images = []
        for entry in root.iterdir():
            if self._is_stop_requested():
                break
            if entry.name.startswith('.') or entry.name in INSPECTION_SKIP_DIRS:
                continue
            if entry.is_dir():
                continue
            ext = entry.suffix.lower()
            if ext in VIDEO_EXTENSIONS:
                videos.append(entry)
            elif ext in IMAGE_EXTENSIONS:
                images.append(entry)
        videos.sort(key=lambda p: p.name.lower())
        images.sort(key=lambda p: p.name.lower())
        return videos, images

    def _safe_wip_path(self, folder_path: str, filename: str) -> Path:
        wip = Path(folder_path) / '01.wip'
        wip.mkdir(exist_ok=True)
        target = Path(self.atomic_processor._available_target_path(str(wip), filename))
        return target

    def _move_to_wip(self, path: Path, folder_path: str, reason: str):
        if not path.exists():
            return None
        target = self._safe_wip_path(folder_path, path.name)
        shutil.move(str(path), str(target))
        try:
            self.atomic_processor._fsync_parent_dir(str(target))
            self.atomic_processor._fsync_parent_dir(str(path))
        except Exception:
            pass
        self.log(f'📦 已移入 01.wip: {path.name} | 原因: {reason}', 'WARNING')
        return str(target)

    def _duplicate_identity(self, video_path: Path, query: str):
        if not query:
            return None
        stem = video_path.stem.strip()
        base = DUPLICATE_COPY_SUFFIX_RE.sub('', stem).strip()
        if base == stem:
            return None
        return query.lower(), self._stem_key(base)

    def _duplicate_rank(self, video_path: Path):
        stem = video_path.stem.strip()
        has_copy_suffix = DUPLICATE_COPY_SUFFIX_RE.search(stem) is not None
        return (-self._file_size(video_path), 1 if has_copy_suffix else 0, video_path.name.casefold())

    def _best_valid_image(self, images):
        for image in images:
            if image.exists() and self._is_image_valid(image):
                return image
        return None

    def _move_video_pair_to_wip(self, *, video: Path, images, folder_path: str, reason: str):
        moved = []
        moved_video = self._move_to_wip(video, folder_path, reason)
        if moved_video:
            moved.append(moved_video)
        for image in images:
            moved_image = self._move_to_wip(image, folder_path, reason)
            if moved_image:
                moved.append(moved_image)
        return moved

    def _rename_duplicate_keep_pair(self, *, keep: Path, image_by_stem: dict):
        old_stem = keep.stem.strip()
        new_stem = DUPLICATE_COPY_SUFFIX_RE.sub('', old_stem).strip()
        if not new_stem or new_stem == old_stem or not keep.exists():
            return keep, None

        paired_images = [img for img in self._images_for_stem(image_by_stem, old_stem) if img.exists()]
        renames = [(keep, keep.with_name(f'{new_stem}{keep.suffix}'))]
        renames.extend((img, img.with_name(f'{new_stem}{img.suffix}')) for img in paired_images)

        conflicts = [target for source, target in renames if target.exists() and target != source]
        if conflicts:
            item = {
                'source_path': str(keep),
                'source_name': keep.name,
                'size': self._file_size(keep),
                'status': 'needs_review',
                'provider': '-',
                'query': self.clean_filename_for_search(keep.name) or '-',
                'reason': 'inspection-duplicate-keep-normalize-skipped:target-exists',
                'after': f'标准文件名已存在: {conflicts[0].name}',
                'rollback_ok': True,
            }
            return keep, item

        committed = []
        try:
            for source, target in renames:
                os.rename(source, target)
                committed.append((source, target))
            for source, target in committed:
                self.atomic_processor._fsync_parent_dir(str(source))
                self.atomic_processor._fsync_parent_dir(str(target))
        except Exception as exc:
            for source, target in reversed(committed):
                try:
                    if target.exists() and not source.exists():
                        os.rename(target, source)
                except Exception:
                    pass
            item = {
                'source_path': str(keep),
                'source_name': keep.name,
                'size': self._file_size(keep),
                'status': 'failed',
                'provider': '-',
                'query': self.clean_filename_for_search(keep.name) or '-',
                'reason': f'inspection-duplicate-keep-normalize-failed:{exc}',
                'after': '重复副本已移动，但保留文件标准化重命名失败',
                'rollback_ok': False,
            }
            return keep, item

        new_keep = renames[0][1]
        image_by_stem.pop(self._stem_key(old_stem), None)
        image_by_stem[self._stem_key(new_stem)] = [target for _source, target in renames[1:]]
        item = {
            'source_path': str(keep),
            'source_name': keep.name,
            'size': self._file_size(new_keep),
            'status': 'success',
            'provider': '-',
            'query': self.clean_filename_for_search(new_keep.name) or '-',
            'reason': 'inspection-duplicate-keep-normalized',
            'after': new_keep.name,
            'target_video_path': str(new_keep),
            'target_image_path': str(renames[1][1]) if len(renames) > 1 else None,
            'rollback_ok': True,
        }
        self.log(f'✅ 已规范重复保留文件名: {keep.name} -> {new_keep.name}', 'SUCCESS')
        return new_keep, item

    def _prune_duplicate_video_pairs(self, *, normal_videos, image_by_stem, folder_path: str, moved_paths: set, progress_state=None):
        progress_state = progress_state or {'completed': 0, 'total': 1}
        grouped = {}
        metadata = {}
        for video in normal_videos:
            if self._is_stop_requested():
                return normal_videos, [], set(), True
            progress_state['completed'] = int(progress_state.get('completed') or 0) + 1
            self._emit_progress(
                progress_state['completed'],
                max(int(progress_state.get('total') or 1), 1),
                f'巡检重复 {video.name}',
            )
            query = self.clean_filename_for_search(video.name)
            identity = self._duplicate_identity(video, query)
            if not identity:
                continue
            paired_images = [img for img in self._images_for_stem(image_by_stem, video.stem) if img.exists()]
            if not paired_images or not any(self._is_image_valid(img) for img in paired_images):
                continue
            grouped.setdefault(identity, []).append(video)
            metadata[str(video)] = {
                'query': query,
                'paired_images': paired_images,
            }

        removed = set()
        results = []
        handled = set()
        for _identity, group in grouped.items():
            if self._is_stop_requested():
                return normal_videos, results, handled, True
            base_candidates = []
            for video in group:
                if self._is_stop_requested():
                    return normal_videos, results, handled, True
                base_stem = DUPLICATE_COPY_SUFFIX_RE.sub('', video.stem).strip()
                base_key = self._stem_key(base_stem)
                base_candidates.extend(
                    candidate for candidate in normal_videos
                    if self._stem_key(candidate.stem) == base_key
                )
            candidates = sorted(set(group + base_candidates), key=self._duplicate_rank)
            keep = candidates[0] if candidates else group[0]
            keep_image = self._best_valid_image(self._images_for_stem(image_by_stem, keep.stem))
            for video in candidates:
                metadata.setdefault(str(video), {
                    'query': self.clean_filename_for_search(video.name),
                    'paired_images': [img for img in self._images_for_stem(image_by_stem, video.stem) if img.exists()],
            })
            moved_duplicate = False
            for video in sorted(candidates, key=lambda p: p.name.casefold()):
                if self._is_stop_requested():
                    return normal_videos, results, handled, True
                if video == keep or not video.exists():
                    continue
                meta = metadata.get(str(video)) or {}
                paired_images = [img for img in meta.get('paired_images', []) if img.exists()]
                candidate_image = self._best_valid_image(paired_images)
                distance = self._image_hash_distance(keep_image, candidate_image)
                threshold = self.duplicate_image_similarity_threshold
                if distance is None or distance > threshold:
                    reason_bits = []
                    if distance is None:
                        reason_bits.append('cover-similarity-unavailable')
                    elif distance > threshold:
                        reason_bits.append(f'cover-distance-{distance}-gt-{threshold}')
                    item = {
                        'source_path': str(video),
                        'source_name': video.name,
                        'size': self._file_size(video),
                        'status': 'needs_review',
                        'provider': '-',
                        'query': meta.get('query') or '-',
                        'reason': 'inspection-duplicate-video-needs-review:' + ','.join(reason_bits),
                        'after': '疑似重复，但封面相似度未通过自动移动阈值',
                        'rollback_ok': True,
                    }
                    results.append(item)
                    self._emit_file_result(item)
                    handled.add(str(video))
                    continue
                self._emit_progress(
                    progress_state['completed'],
                    max(int(progress_state.get('total') or 1), 1),
                    f'修复重复 {video.name}',
                )
                moved = self._move_video_pair_to_wip(
                    video=video,
                    images=paired_images,
                    folder_path=folder_path,
                    reason='duplicate-video-pair',
                )
                for original in [video] + paired_images:
                    moved_paths.add(str(original))
                removed.add(video)
                moved_duplicate = True
                item = {
                    'source_path': str(video),
                    'source_name': video.name,
                    'size': self._file_size(Path(moved[0])) if moved else self._file_size(video),
                    'status': 'needs_review',
                    'provider': '-',
                    'query': meta.get('query') or '-',
                    'reason': f'inspection-duplicate-video-pair-moved-to-wip:cover-distance-{distance}-lte-{threshold}',
                    'after': f'已移入 01.wip: {Path(moved[0]).name if moved else video.name}',
                    'target_video_path': moved[0] if moved else None,
                    'target_image_path': next((path for path in moved[1:] if Path(path).suffix.lower() in IMAGE_EXTENSIONS), None),
                    'rollback_ok': True,
                }
                results.append(item)
                self._emit_file_result(item)
            if moved_duplicate:
                new_keep, normalize_item = self._rename_duplicate_keep_pair(
                    keep=keep,
                    image_by_stem=image_by_stem,
                )
                if normalize_item:
                    results.append(normalize_item)
                    self._emit_file_result(normalize_item)
                    if normalize_item.get('status') == 'success':
                        handled.add(str(new_keep))
                        removed.add(keep)
        remaining = [video for video in normal_videos if video not in removed]
        for item in results:
            target = item.get('target_video_path')
            if item.get('reason') == 'inspection-duplicate-keep-normalized' and target:
                remaining.append(Path(target))
        return remaining, results, handled, False

    def _image_request_from_result(self, result, provider_name):
        raw_meta = result.get('raw_meta') or {}
        if not isinstance(raw_meta, dict):
            raw_meta = {}
        fallback_images = result.get('fallback_images') or raw_meta.get('fallback_images') or []
        if not result.get('image_url') and not fallback_images:
            return None
        return {
            'image_url': result.get('image_url'),
            'referer': result.get('referer') or result.get('detail_url'),
            'detail_url': result.get('detail_url'),
            'provider': result.get('provider') or provider_name,
            'fallback_images': fallback_images,
        }

    def _search_provider(self, provider, provider_name, query):
        started = time.time()
        result = provider.search(query)
        elapsed = round(time.time() - started, 3)
        if hasattr(result, 'to_dict'):
            result = result.to_dict()
        raw_meta = result.get('raw_meta') or {}
        if isinstance(raw_meta, dict):
            raw_meta['provider_elapsed_seconds'] = elapsed
            result['raw_meta'] = raw_meta
        self.log(f'⏱️ 巡检 Provider搜索耗时: provider={provider_name} | query={query} | {elapsed:.1f}秒', 'INFO')
        return result, elapsed

    def _download_cover_for_video(self, *, video_path: Path, image_path: Path, provider, provider_name,
                                  query: str, max_filename_bytes=None, invalid_image_path: Path | None = None):
        result, provider_elapsed = self._search_provider(provider, provider_name, query)
        if not result.get('ok') or not (result.get('image_url') or result.get('fallback_images')):
            reason = f"provider:{result.get('error_type') or 'invalid-result'}:{result.get('message') or 'missing image'}"
            return False, {
                'source_path': str(video_path),
                'source_name': video_path.name,
                'size': self._file_size(video_path),
                'status': 'failed',
                'provider': provider_name,
                'query': query,
                'reason': reason,
                'title': result.get('title'),
                'image_url': result.get('image_url'),
                'detail_url': result.get('detail_url'),
                'provider_elapsed_seconds': provider_elapsed,
            }

        image_request = self._image_request_from_result(result, provider_name)
        success, temp_path, message = self.atomic_processor.download_image_to_temp(
            image_request,
            image_path.name,
            max_filename_bytes=max_filename_bytes,
        )
        if not success:
            return False, {
                'source_path': str(video_path),
                'source_name': video_path.name,
                'size': self._file_size(video_path),
                'status': 'failed',
                'provider': provider_name,
                'query': query,
                'reason': f'image-repair-failed:{message}',
                'title': result.get('title'),
                'image_url': result.get('image_url'),
                'detail_url': result.get('detail_url'),
                'provider_elapsed_seconds': provider_elapsed,
            }

        if invalid_image_path and invalid_image_path.exists():
            self._move_to_wip(invalid_image_path, str(video_path.parent), 'invalid-image-replaced')
        final_path = str(image_path)
        if os.path.exists(final_path):
            self._move_to_wip(Path(final_path), str(video_path.parent), 'duplicate-before-cover-repair')
        self.atomic_processor._move_temp_image_to_final(temp_path, final_path)
        try:
            self.atomic_processor._fsync_committed_path(final_path)
        except Exception:
            pass
        return True, {
            'source_path': str(video_path),
            'source_name': video_path.name,
            'size': self._file_size(video_path),
            'status': 'success',
            'provider': provider_name,
            'query': query,
            'reason': 'inspection-cover-repaired',
            'title': result.get('title'),
            'image_url': result.get('image_url'),
            'detail_url': result.get('detail_url'),
            'target_video_path': str(video_path),
            'target_image_path': final_path,
            'image_downloaded': True,
            'rollback_ok': True,
            'provider_elapsed_seconds': provider_elapsed,
        }

    def _looks_unprocessed(self, video_path: Path, query: str) -> bool:
        if not query:
            return False
        stem = video_path.stem.strip()
        normalized_query = query.replace('_', '-').upper()
        compact_query = normalized_query.replace('-', '')
        upper_stem = stem.upper()
        if '@' in stem or '[' in stem or ']' in stem:
            return True
        if upper_stem == normalized_query or upper_stem == compact_query:
            return True
        if upper_stem.startswith(normalized_query + ' ') and len(stem) > len(normalized_query) + 4:
            return False
        return not upper_stem.startswith(normalized_query)

    def _process_unprocessed_video(self, *, video_path: Path, provider, provider_name, query: str,
                                   max_length=None, max_filename_bytes=None):
        source_size = self._file_size(video_path)
        result, provider_elapsed = self._search_provider(provider, provider_name, query)
        if not result.get('ok') or not result.get('title'):
            reason = f"provider:{result.get('error_type') or 'invalid-result'}:{result.get('message') or 'missing title'}"
            return False, {
                'source_path': str(video_path),
                'source_name': video_path.name,
                'size': source_size,
                'status': 'failed',
                'provider': provider_name,
                'query': query,
                'reason': reason,
                'title': result.get('title'),
                'image_url': result.get('image_url'),
                'detail_url': result.get('detail_url'),
                'provider_elapsed_seconds': provider_elapsed,
            }
        title = result.get('title')
        if max_length:
            title = self.smart_truncate_filename(title, video_path.name, max_length)
        new_filename = self.sanitize_filename(f'{title}{video_path.suffix}', max_bytes=max_filename_bytes)
        ok, payload, message = self.atomic_processor.process_file_atomic(
            str(video_path),
            new_filename,
            self._image_request_from_result(result, provider_name),
            str(video_path.parent),
            max_filename_bytes=max_filename_bytes,
        )
        return ok, {
            'source_path': str(video_path),
            'source_name': video_path.name,
            'size': source_size,
            'status': payload.get('status') or ('success' if ok else 'failed'),
            'provider': provider_name,
            'query': query,
            'reason': 'inspection-unprocessed-repaired' if ok else payload.get('reason') or message,
            'title': title,
            'image_url': result.get('image_url'),
            'detail_url': result.get('detail_url'),
            'target_video_path': payload.get('video_path'),
            'target_image_path': payload.get('image_path'),
            'image_downloaded': payload.get('image_downloaded'),
            'rollback_ok': payload.get('rollback_ok'),
            'provider_elapsed_seconds': provider_elapsed,
        }

    def _result_counts(self, file_results):
        counts = {'success': 0, 'failed': 0, 'skipped': 0, 'needs_review': 0}
        for item in file_results:
            status = item.get('status') or 'failed'
            counts[status] = counts.get(status, 0) + 1
        return counts

    def _wip_moved_count(self, file_results):
        return sum(1 for item in file_results if '-moved-to-wip' in str(item.get('reason') or ''))

    def _log_stage_elapsed(self, stage: str, started_at: float):
        self.log(f'⏱️ 巡检阶段耗时: {stage} | {time.time() - started_at:.1f}秒', 'INFO')

    def run(self, *, folder_path, website, max_length=None, max_filename_bytes=None, log_path=None, logs_dir=None):
        started = time.time()
        self._provider_instances = {}
        primary_provider_name = website
        scan_started = time.time()
        videos, images = self._scan_current_dir(folder_path)
        self._log_stage_elapsed('目录扫描', scan_started)
        image_by_stem = {}
        for image in images:
            image_by_stem.setdefault(self._stem_key(image.stem), []).append(image)

        file_results = []
        total_units = (len(videos) * 3) + len(images)
        completed = 0
        cancelled = self._is_stop_requested()
        self.log(f'🩺 巡检模式: 扫描 {len(videos)} 个视频，{len(images)} 张图片', 'INFO')

        moved_paths = set()
        normal_videos = []
        small_video_started = time.time()
        for video in videos:
            if self._is_stop_requested():
                cancelled = True
                break
            self._emit_progress(completed, max(total_units, 1), f'巡检 {video.name}')
            try:
                size = video.stat().st_size
            except OSError:
                size = 0
            if size < self.minimum_video_size_bytes:
                targets = [video] + self._images_for_stem(image_by_stem, video.stem)
                moved = []
                self._emit_progress(completed, max(total_units, 1), f'修复小视频 {video.name}')
                for target in targets:
                    moved_path = self._move_to_wip(target, folder_path, 'small-video-or-pair')
                    if moved_path:
                        moved.append(moved_path)
                        moved_paths.add(str(target))
                item = {
                    'source_path': str(video),
                    'source_name': video.name,
                    'size': size,
                    'status': 'needs_review',
                    'reason': 'inspection-small-video-moved-to-wip',
                    'after': f'已移入 01.wip: {Path(moved[0]).name if moved else video.name}',
                    'target_video_path': moved[0] if moved else None,
                    'rollback_ok': True,
                }
                file_results.append(item)
                self._emit_file_result(item)
            else:
                normal_videos.append(video)
            completed += 1
        self._log_stage_elapsed('异常小视频检查', small_video_started)

        duplicate_handled_videos = set()
        if not cancelled:
            duplicate_started = time.time()
            duplicate_progress = {'completed': completed, 'total': max(total_units, 1)}
            normal_videos, duplicate_results, duplicate_handled_videos, cancelled = self._prune_duplicate_video_pairs(
                normal_videos=normal_videos,
                image_by_stem=image_by_stem,
                folder_path=folder_path,
                moved_paths=moved_paths,
                progress_state=duplicate_progress,
            )
            completed = int(duplicate_progress.get('completed') or completed)
            file_results.extend(duplicate_results)
            self._log_stage_elapsed('重复视频副本检查', duplicate_started)

        normal_video_stems = {self._stem_key(video.stem) for video in normal_videos}
        image_group_started = time.time()
        for stem, group in image_by_stem.items():
            if cancelled or self._is_stop_requested():
                cancelled = True
                break
            if stem not in normal_video_stems:
                for image in group:
                    if self._is_stop_requested():
                        cancelled = True
                        break
                    completed += 1
                    if str(image) in moved_paths:
                        continue
                    self._emit_progress(completed, max(total_units, 1), f'修复图片 {image.name}')
                    moved = self._move_to_wip(image, folder_path, 'orphan-image')
                    item = {
                        'source_path': str(image),
                        'source_name': image.name,
                        'size': self._file_size(Path(moved)) if moved else self._file_size(image),
                        'status': 'needs_review',
                        'reason': 'inspection-orphan-image-moved-to-wip',
                        'after': f'已移入 01.wip: {Path(moved).name if moved else image.name}',
                        'target_image_path': moved,
                        'rollback_ok': True,
                    }
                    file_results.append(item)
                    self._emit_file_result(item)
                    self._emit_progress(completed, max(total_units, 1), image.name)
            elif len(group) > 1:
                valid_group = [image for image in group if self._is_image_valid(image)]
                keep = valid_group[0] if valid_group else group[0]
                for image in group:
                    if self._is_stop_requested():
                        cancelled = True
                        break
                    completed += 1
                    if image == keep or str(image) in moved_paths:
                        continue
                    self._emit_progress(completed, max(total_units, 1), f'修复图片 {image.name}')
                    moved = self._move_to_wip(image, folder_path, 'duplicate-image')
                    item = {
                        'source_path': str(image),
                        'source_name': image.name,
                        'size': self._file_size(Path(moved)) if moved else self._file_size(image),
                        'status': 'needs_review',
                        'reason': 'inspection-duplicate-image-moved-to-wip',
                        'after': f'已移入 01.wip: {Path(moved).name if moved else image.name}',
                        'target_image_path': moved,
                        'rollback_ok': True,
                    }
                    file_results.append(item)
                    self._emit_file_result(item)
                    self._emit_progress(completed, max(total_units, 1), image.name)
            else:
                for image in group:
                    completed += 1
                    if completed % 50 == 0:
                        self._emit_progress(completed, max(total_units, 1), f'巡检图片 {image.name}')
        self._log_stage_elapsed('孤儿图片与重复图片检查', image_group_started)

        cover_check_started = time.time()
        checked_cover_pairs = 0
        self.log(f'🩺 巡检阶段: 校验配对封面并修复缺失/损坏封面，共 {len(normal_videos)} 个视频', 'INFO')
        for video in normal_videos:
            if cancelled:
                break
            if str(video) in duplicate_handled_videos:
                continue
            if self._is_stop_requested():
                cancelled = True
                break
            self._emit_progress(completed, max(total_units, 1), f'巡检封面 {video.name}')
            query = self.clean_filename_for_search(video.name)
            paired_images = [img for img in self._images_for_stem(image_by_stem, video.stem) if img.exists()]
            valid_images = [img for img in paired_images if self._is_image_valid(img)]
            invalid_images = [img for img in paired_images if img not in valid_images]
            checked_cover_pairs += 1
            if checked_cover_pairs % 50 == 0:
                self.log(
                    f'🩺 巡检封面进度: {checked_cover_pairs}/{len(normal_videos)} | '
                    f'耗时 {time.time() - cover_check_started:.1f}秒',
                    'INFO',
                )
            if valid_images and not self._looks_unprocessed(video, query):
                normalized_video, normalize_item = self._rename_duplicate_keep_pair(
                    keep=video,
                    image_by_stem=image_by_stem,
                )
                if normalize_item:
                    file_results.append(normalize_item)
                    self._emit_file_result(normalize_item)
                    completed += 1
                    self._emit_progress(completed, max(total_units, 1), normalized_video.name)
                    continue
                item = {
                    'source_path': str(video),
                    'source_name': video.name,
                    'size': self._file_size(video),
                    'status': 'skipped',
                    'provider': primary_provider_name,
                    'query': query,
                    'reason': 'inspection-ok-no-action',
                    'target_video_path': str(video),
                    'target_image_path': str(valid_images[0]),
                    'image_downloaded': False,
                    'rollback_ok': True,
                }
                file_results.append(item)
                self._emit_file_result(item, log_result=False)
                completed += 1
                self._emit_progress(completed, max(total_units, 1), video.name)
                continue

            if query and self._looks_unprocessed(video, query):
                self._emit_progress(completed, max(total_units, 1), f'修复视频 {video.name}')
                provider, provider_name = self._resolve_provider_for_video(primary_provider_name, video, query)
                ok, item = self._process_unprocessed_video(
                    video_path=video,
                    provider=provider,
                    provider_name=provider_name,
                    query=query,
                    max_length=max_length,
                    max_filename_bytes=max_filename_bytes,
                )
                if ok:
                    for old_image in paired_images:
                        if old_image.exists():
                            self._move_to_wip(old_image, folder_path, 'old-cover-after-video-rename')
            elif query:
                image_path = video.with_suffix('.jpg')
                self._emit_progress(completed, max(total_units, 1), f'修复封面 {video.name}')
                provider, provider_name = self._resolve_provider_for_video(primary_provider_name, video, query)
                ok, item = self._download_cover_for_video(
                    video_path=video,
                    image_path=image_path,
                    provider=provider,
                    provider_name=provider_name,
                    query=query,
                    max_filename_bytes=max_filename_bytes,
                    invalid_image_path=invalid_images[0] if invalid_images else None,
                )
            else:
                ok = False
                item = {
                    'source_path': str(video),
                    'source_name': video.name,
                    'size': self._file_size(video),
                    'status': 'needs_review',
                    'reason': 'inspection-empty-search-query',
                }
            file_results.append(item)
            self._emit_file_result(item)
            completed += 1
            self._emit_progress(completed, max(total_units, 1), video.name)
        self._log_stage_elapsed('配对封面健康检查与修复', cover_check_started)

        if cancelled:
            self.log('⏹️ 巡检已停止：已完成的小步骤保留结果，未开始的文件保持原样', 'WARNING')

        counts = self._result_counts(file_results)
        wip_moved_count = self._wip_moved_count(file_results)
        normal_count = counts.get('skipped', 0)
        total_time = round(time.time() - started, 3)
        artifacts = {}
        if logs_dir:
            file_results_path = write_json_report(
                os.path.join(logs_dir, f'inspection_file_results_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'),
                {
                    'generated_at': datetime.now().isoformat(),
                    'website': website,
                    'folder': folder_path,
                    'mode': 'inspection',
                    'counts': counts,
                    'results': file_results,
                },
            )
            if cancelled:
                after_manifest_path = None
                self.log('⏹️ 巡检已停止：跳过处理后清单扫描以加快停止', 'WARNING')
            else:
                after_manifest_path = write_json_report(
                    os.path.join(logs_dir, f'inspection_manifest_after_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'),
                    scan_folder_manifest(folder_path, include_subdirectories=False),
                )
            summary = {
                'version': self.app_version,
                'generated_at': datetime.now().isoformat(),
                'website': website,
                'folder': folder_path,
                'mode': 'inspection',
                'dry_run': False,
                'counts': {
                    'total_files': len(file_results),
                    'success_count': counts.get('success', 0),
                    'failed_count': counts.get('failed', 0),
                    'needs_review_count': counts.get('needs_review', 0),
                    'normal_count': normal_count,
                    'cancelled_count': 1 if cancelled else 0,
                    'skipped_hidden': 0,
                    'skipped_small': wip_moved_count,
                    'image_success_count': sum(1 for item in file_results if item.get('image_downloaded')),
                    'image_failed_count': counts.get('failed', 0),
                },
                'timings': {'total_elapsed_seconds': total_time},
                'artifacts': {
                    'log_path': log_path,
                    'after_manifest_path': after_manifest_path,
                    'file_results_path': file_results_path,
                },
            }
            summary_path = write_json_report(
                os.path.join(logs_dir, f'inspection_run_summary_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'),
                summary,
            )
            artifacts = summary['artifacts']
            artifacts['summary_path'] = summary_path
        else:
            file_results_path = after_manifest_path = summary_path = None

        return {
            'mode': 'inspection',
            'success_count': counts.get('success', 0),
            'failed_count': counts.get('failed', 0),
            'planned_count': 0,
            'skipped_hidden': 0,
            'skipped_small': wip_moved_count,
            'skipped_provider_count': 0,
            'needs_review_count': counts.get('needs_review', 0),
            'normal_count': normal_count,
            'cancelled_count': 1 if cancelled else 0,
            'image_success_count': sum(1 for item in file_results if item.get('image_downloaded')),
            'image_failed_count': counts.get('failed', 0),
            'file_result_counts': counts,
            'routed_counts': {website: len(file_results)},
            'before_manifest_path': None,
            'after_manifest_path': after_manifest_path,
            'file_results_path': file_results_path,
            'filename_rule_candidates_path': None,
            'file_results': file_results,
            'summary_path': summary_path,
            'total_time': total_time,
            'total_files': len(file_results),
            'artifacts': artifacts,
        }
