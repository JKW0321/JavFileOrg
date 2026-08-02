#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Inspection and repair workflow for already-organized folders."""
from __future__ import annotations

import os
import re
import shutil
import time
import unicodedata
import hashlib
from bisect import bisect_left, bisect_right
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Callable

from PIL import Image

from app_metadata import BASELINE_VERSION
from filename_utils import split_sequence_suffix
from manifest_utils import scan_folder_manifest, write_json_report
from provider_result_validation import reject_mismatched_provider_result
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
        file_status_callback: Callable | None = None,
        finalizing_callback: Callable | None = None,
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
        self.file_status_callback = file_status_callback or (
            lambda source_name, status, stage='': None
        )
        self.finalizing_callback = finalizing_callback or (lambda result, dry_run=False: None)
        self.minimum_video_size_bytes = minimum_video_size_bytes
        self.duplicate_image_similarity_threshold = max(0, int(duplicate_image_similarity_threshold))
        self.app_version = app_version
        self._image_valid_cache = {}
        self._image_hash_cache = {}
        self._video_hash_cache = {}
        self._provider_instances = {}
        self._deep_reference_cache = {}
        self._known_video_sizes = {}
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

    def _query_key(self, filename: str) -> str:
        try:
            query = self.clean_filename_for_search(str(filename or ''))
        except Exception:
            return ''
        return self._stem_key(query) if query else ''

    def _images_for_stem(self, image_by_stem: dict, stem: str):
        return image_by_stem.get(self._stem_key(stem), [])

    def _strong_single_sequence_base(self, stem: str):
        """Return a low-ambiguity shared stem for a lone sequence part."""
        text = str(stem or '').strip()
        patterns = (
            # ``Title_1`` is the concrete legacy form that motivated this
            # repair.  A bare space/hyphen number is deliberately excluded:
            # titles commonly end in ``17``, ``R-20`` or ``VOL.3``.
            re.compile(r'^(?P<base>.+?)_(?P<sequence>\d{1,3})$'),
            re.compile(
                r'^(?P<base>.+?)[\s._-]*[\(\[【（［]\s*'
                # Parenthesized two-digit numbers commonly represent age,
                # e.g. ``松永さな（30）``. Only a single digit is safe as an
                # isolated, unlabeled part marker.
                r'(?P<sequence>[1-9]|[a-z])\s*[\)\]】）］]$',
                re.IGNORECASE,
            ),
            re.compile(
                r'^(?P<base>.+?)[\s._-]*第\s*(?P<sequence>\d{1,3})'
                r'\s*(?:集|話|话|部|章|篇|回|卷)$',
                re.IGNORECASE,
            ),
        )
        for pattern in patterns:
            match = pattern.fullmatch(text)
            if match:
                base = match.group('base').rstrip(' ._-')
                if base:
                    return base
        return None

    def _shared_cover_stems_for_sequences(self, videos, images=()):
        """Map organized sequence videos to their unnumbered shared cover stem."""
        grouped = {}
        result = {}
        for video in videos:
            shared_stem, sequence = split_sequence_suffix(video.stem)
            if not shared_stem or sequence is None:
                continue
            strong_single_base = self._strong_single_sequence_base(video.stem)
            if strong_single_base:
                result[video] = strong_single_base
            key = self._stem_key(shared_stem)
            entry = grouped.setdefault(
                key,
                {'shared_stem': shared_stem, 'videos': [], 'sequences': set()},
            )
            entry['videos'].append(video)
            entry['sequences'].add(sequence)

        for entry in grouped.values():
            if len(entry['videos']) < 2 or len(entry['sequences']) < 2:
                continue
            for video in entry['videos']:
                result[video] = entry['shared_stem']

        # Existing shared covers provide safe context for compact forms such as
        # Titlea/Titleb/Titlec, which should not be stripped from a lone file.
        # Use a sorted prefix index so a large folder does not compare every
        # image against every video (2,000 x 2,000 used to take tens of seconds
        # on a NAS before the next stage even emitted progress).
        indexed_videos = sorted(
            (
                unicodedata.normalize('NFKC', video.stem).strip().casefold(),
                video,
            )
            for video in videos
        )
        indexed_stems = [stem for stem, _video in indexed_videos]
        for image in images:
            if not image.exists():
                continue
            matched_videos = []
            sequences = set()
            normalized_hint = unicodedata.normalize(
                'NFKC',
                image.stem,
            ).rstrip().casefold()
            start = bisect_left(indexed_stems, normalized_hint)
            stop = bisect_right(indexed_stems, normalized_hint + '\U0010ffff')
            for _normalized_stem, video in indexed_videos[start:stop]:
                _base, sequence = split_sequence_suffix(
                    video.stem,
                    base_hint=image.stem,
                )
                if sequence is None:
                    continue
                matched_videos.append(video)
                sequences.add(sequence)
            if len(matched_videos) < 2 or len(sequences) < 2:
                continue
            for video in matched_videos:
                result[video] = image.stem
        return result

    def _emit_progress(self, completed, total, label=''):
        try:
            self.progress_callback(completed, total, label)
        except Exception as exc:
            self.log(f'⚠️ 巡检进度更新失败: {exc}', 'WARNING')

    def _emit_file_status(self, video_path: Path, status: str, stage: str = ''):
        """Publish transient inspection state without adding a final result."""
        try:
            self.file_status_callback(video_path.name, status, stage)
        except Exception as exc:
            self.log(f'⚠️ 巡检阶段状态更新失败: {exc}', 'WARNING')

    def _emit_file_result(self, item, *, log_result=True):
        if item is not None and not item.get('reason_text'):
            item['reason_text'] = self._reason_text(item)
        if log_result:
            self._log_file_result(item or {})
        try:
            self.file_result_callback(dict(item or {}))
        except Exception as exc:
            self.log(f'⚠️ 巡检文件状态更新失败: {exc}', 'WARNING')

    def _emit_finalizing(self, result):
        try:
            self.finalizing_callback(dict(result or {}), False)
        except Exception as exc:
            self.log(f'⚠️ 巡检完成状态更新失败: {exc}', 'WARNING')

    def _get_provider(self, provider_name: str):
        if provider_name not in self._provider_instances:
            self._provider_instances[provider_name] = self.provider_factory(provider_name)
        return self._provider_instances[provider_name]

    def _resolve_provider_for_video(self, preferred_provider: str, video_path: Path, query: str):
        decision = route_provider(preferred_provider, video_path.name, query)
        provider_name = decision.get('provider') or preferred_provider
        reason = decision.get('reason') or ''
        if provider_name != preferred_provider:
            self.log(
                f'🧭 巡检自动切换数据源: {video_path.name} | {preferred_provider} -> '
                f'{provider_name} | {reason}',
                'INFO',
            )
        return self._get_provider(provider_name), provider_name, decision

    def _log_file_result(self, item):
        status = item.get('status') or 'failed'
        name = item.get('source_name') or Path(item.get('source_path') or '').name or 'unknown'
        provider = item.get('provider') or '-'
        query = item.get('query') or '-'
        reason = item.get('reason_text') or self._reason_text(item) or '-'
        after = item.get('after') or ''
        if status == 'success':
            suffix = f' | 结果: {after}' if after else ''
            self.log(
                f'✅ 巡检修复成功: {name} | provider={provider} | query={query} | '
                f'原因: {reason}{suffix}',
                'SUCCESS',
            )
        elif status == 'needs_review':
            suffix = f' | {after}' if after else ''
            self.log(
                f'⚠️ 巡检待确认: {name} | 原因: {reason}{suffix}',
                'WARNING',
            )
        elif status == 'skipped':
            warning_reasons = {
                'inspection-cover-content-unverified',
                'inspection-video-deferred',
            }
            level = 'WARNING' if item.get('reason') in warning_reasons else 'INFO'
            if item.get('reason') == 'inspection-cover-content-unverified':
                prefix = '⚠️ 巡检未完成内容验证'
            elif item.get('reason') == 'inspection-video-deferred':
                prefix = '⏳ 巡检延后处理'
            else:
                prefix = '🙈 巡检跳过'
            self.log(f'{prefix}: {name} | 原因: {reason}', level)
        else:
            self.log(
                f'❌ 巡检未修复: {name} | provider={provider} | query={query} | 原因: {reason} | 源文件保持原样',
                'ERROR',
            )

    def _reason_text(self, item):
        """Translate stable internal reason codes into user-facing Chinese."""
        reason = str((item or {}).get('reason') or '')
        if not reason:
            return ''
        if reason == 'inspection-small-video-moved-to-wip':
            actual_kib = float((item or {}).get('size') or 0) / 1024
            threshold_kib = float(self.minimum_video_size_bytes) / 1024
            return (
                f'视频文件过小（实际 {actual_kib:.1f} KB，小于阈值 {threshold_kib:.1f} KB），'
                '疑似下载不完整或占位文件，已连同配对封面移入 01.wip'
            )
        if reason == 'inspection-ok-no-action':
            if (item or {}).get('cover_content_verified'):
                distance = (item or {}).get('cover_hash_distance')
                threshold = (item or {}).get('cover_hash_threshold')
                return (
                    f'封面可正常解码、配对正确，且内容与数据源参考封面相符'
                    f'（差异 {distance}，阈值 {threshold}）'
                )
            return '封面可完整解码且未发现损坏，并与视频或视频组配对正确，无需处理'
        if reason == 'inspection-cover-content-unverified':
            detail = str((item or {}).get('cover_verification_message') or '参考封面不可用')
            return f'本地封面结构和配对正常，但未完成内容核验：{detail}；本地文件保持原样'
        if reason.startswith('inspection-cover-content-mismatch:'):
            distance = (item or {}).get('cover_hash_distance')
            threshold = (item or {}).get('cover_hash_threshold')
            return (
                f'本地图片可正常解码，但内容与该番号的数据源参考封面不一致'
                f'（差异 {distance}，阈值 {threshold}）；未覆盖或移动本地文件，请人工确认'
            )
        if reason == 'inspection-cover-repaired':
            return '原封面缺失或无法正常解码，已重新下载并修复'
        if reason.startswith('inspection-cover-commit-failed:'):
            return '参考封面已下载，但写入网络磁盘时失败；已尽力恢复原封面，本视频未中断后续巡检'
        if reason == 'inspection-unprocessed-repaired':
            return '视频尚未完成整理，已重新查询资料并完成重命名和封面处理'
        if reason == 'inspection-orphan-image-moved-to-wip':
            return '图片没有对应的视频或视频组，已移入 01.wip'
        if reason == 'inspection-duplicate-image-moved-to-wip':
            return '同一视频存在重复图片，已保留有效封面并将重复图片移入 01.wip'
        if reason == 'inspection-redundant-sequence-cover-moved-to-wip':
            return '视频组已有有效共享封面，内容相同的分集封面已移入 01.wip'
        if reason == 'inspection-sequence-cover-normalized':
            return '已去除封面文件名中的分段标记并恢复为视频组共享封面名；视频文件名保持不变'
        if reason == 'inspection-single-sequence-normalized':
            return '该番号在当前目录只有一个视频，已去除视频和封面的孤立分段编号'
        if reason.startswith('inspection-single-sequence-normalize-skipped:target-exists'):
            return '单文件的无编号目标视频已经存在，为避免覆盖文件，未自动重命名'
        if reason.startswith('inspection-single-sequence-normalize-failed:'):
            return '单文件分段编号需要移除，但重命名失败；已尽力恢复原文件'
        if reason.startswith('inspection-sequence-cover-normalize-skipped:target-exists'):
            return '目标共享封面名已经存在，为避免覆盖图片，未自动重命名，请人工确认'
        if reason.startswith('inspection-sequence-cover-normalize-failed:'):
            return '视频组封面名称需要规范，但网络磁盘重命名失败；视频和原图片保持原样'
        if reason == 'inspection-empty-search-query':
            return '无法从文件名提取可用番号，未自动修改，请人工确认'
        if reason.startswith('inspection-video-unavailable:'):
            return '视频文件暂时无法读取（可能是网络磁盘短暂断开或目录缓存失效），未移动文件，请刷新后重试'
        if reason == 'inspection-video-deferred':
            return '网络磁盘暂时无法稳定读取该视频，本轮已延后且不计为文件故障；文件未移动，请稍后再次巡检'
        if reason == 'inspection-small-video-move-failed':
            return '视频过小，但移入 01.wip 失败，源文件未改动，请检查磁盘连接和权限'
        if reason == 'inspection-orphan-image-move-failed':
            return '图片没有可用的配对视频，但移入 01.wip 失败，源文件未改动'
        if reason == 'inspection-duplicate-image-move-failed':
            return '检测到重复图片，但移入 01.wip 失败，源文件未改动'
        if reason == 'inspection-duplicate-keep-normalized':
            return '重复副本清理后，已将保留的视频和封面恢复为标准文件名'
        if reason.startswith('inspection-duplicate-keep-normalize-skipped:target-exists'):
            return '标准文件名已存在，为避免覆盖文件，未自动重命名'
        if reason.startswith('inspection-duplicate-keep-normalize-failed:'):
            return '重复副本已处理，但保留文件重命名失败，请人工确认'
        if reason.startswith('inspection-duplicate-video-pair-moved-to-wip:'):
            match = re.search(r'cover-distance-(\d+)-lte-(\d+)', reason)
            detail = f'（封面差异 {match.group(1)}，阈值 {match.group(2)}）' if match else ''
            return f'视频大小和 SHA-256 内容完全一致，且封面高度相似{detail}，副本及其封面已移入 01.wip'
        if reason.startswith('inspection-duplicate-video-needs-review:'):
            if 'video-content-unavailable' in reason:
                return '疑似重复视频，但无法完成视频内容比对，未自动移动，请人工确认'
            if 'cover-similarity-unavailable' in reason:
                return '疑似重复视频，但封面无法完成相似度比较，未自动移动，请人工确认'
            match = re.search(r'cover-distance-(\d+)-gt-(\d+)', reason)
            if match:
                return f'疑似重复视频，但封面差异 {match.group(1)} 超过阈值 {match.group(2)}，未自动移动，请人工确认'
            return '疑似重复视频，但自动判定条件不足，未自动移动，请人工确认'
        if reason.startswith('provider:code-mismatch:'):
            return reason.split(':', 2)[2] + '，源文件保持原样'
        return reason

    def _file_size(self, path: Path) -> int:
        path = Path(path)
        if path.suffix.lower() in VIDEO_EXTENSIONS:
            cached = self._known_video_sizes.get(self._stem_key(path.name))
            if cached is not None:
                return int(cached)
        try:
            return int(path.stat().st_size)
        except OSError:
            return 0

    def _is_image_valid(self, path: Path) -> bool:
        # Quick inspection must fully decode every local cover so truncated or
        # otherwise damaged pixel data is detected. The path-only cache is
        # scoped to one run and prevents the same shared cover from being read
        # repeatedly for every part in a video group.
        key = str(Path(path))
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

    def _prevalidate_images(self, images, *, completed: int, total_units: int):
        """Fully decode unique covers concurrently and warm the run cache."""
        unique_images = list(dict.fromkeys(Path(image) for image in images))
        if not unique_images:
            return completed, False

        workers = min(4, len(unique_images))
        checked = 0
        cancelled = False
        executor = ThreadPoolExecutor(
            max_workers=workers,
            thread_name_prefix='jfo-cover-check',
        )
        futures = {
            executor.submit(self._is_image_valid, image): image
            for image in unique_images
        }
        try:
            for future in as_completed(futures):
                image = futures[future]
                try:
                    future.result()
                except Exception:
                    self._image_valid_cache[str(image)] = False
                checked += 1
                completed += 1
                if checked == 1 or checked % 50 == 0 or checked == len(unique_images):
                    self._emit_progress(
                        completed,
                        max(total_units, 1),
                        f'完整解码封面 {checked}/{len(unique_images)} · {image.name}',
                    )
                    self.log(
                        f'🖼️ 快速巡检封面完整解码进度: '
                        f'{checked}/{len(unique_images)}',
                        'INFO',
                    )
                if self._is_stop_requested():
                    cancelled = True
                    break
        finally:
            if cancelled:
                for future in futures:
                    future.cancel()
            executor.shutdown(wait=not cancelled, cancel_futures=cancelled)
        return completed, cancelled

    def _video_sha256(self, path: Path):
        """Return a full-content digest, or None when the video cannot be read.

        This is deliberately used only after sizes match. Shared covers are
        normal for multi-part videos, so a cover hash must never be used as
        proof that two video files are duplicates.
        """
        try:
            stat = path.stat()
            key = (str(path), int(stat.st_size), int(stat.st_mtime_ns))
        except OSError:
            return None
        if key in self._video_hash_cache:
            return self._video_hash_cache[key]
        digest = hashlib.sha256()
        try:
            with path.open('rb') as stream:
                while True:
                    if self._is_stop_requested():
                        return None
                    chunk = stream.read(8 * 1024 * 1024)
                    if not chunk:
                        break
                    digest.update(chunk)
        except OSError:
            self._video_hash_cache[key] = None
            return None
        value = digest.hexdigest()
        self._video_hash_cache[key] = value
        return value

    def _same_video_content(self, left: Path, right: Path):
        left_size = self._file_size(left)
        right_size = self._file_size(right)
        if left_size <= 0 or right_size <= 0:
            return None
        if left_size != right_size:
            return False
        left_hash = self._video_sha256(left)
        right_hash = self._video_sha256(right)
        if left_hash is None or right_hash is None:
            return None
        return left_hash == right_hash

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
        deleted_metadata = []
        for entry in root.iterdir():
            if self._is_stop_requested():
                break
            if entry.name == '.DS_Store' or entry.name.startswith('._'):
                try:
                    if entry.is_file() and not entry.is_symlink():
                        entry.unlink()
                        deleted_metadata.append(entry.name)
                except OSError as exc:
                    self.log(f'⚠️ 无法清理系统元数据文件: {entry.name} | {exc}', 'WARNING')
                continue
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
        if deleted_metadata:
            self.log(
                f'🧹 巡检已清理 {len(deleted_metadata)} 个系统元数据文件（.DS_Store / ._*）',
                'INFO',
            )
        return videos, images

    def _safe_wip_path(self, folder_path: str, filename: str) -> Path:
        wip = Path(folder_path) / '01.wip'
        wip.mkdir(exist_ok=True)
        target = Path(self.atomic_processor._available_target_path(str(wip), filename))
        return target

    def _move_to_wip(self, path: Path, folder_path: str, reason: str):
        if not path.exists():
            return None
        try:
            target = self._safe_wip_path(folder_path, path.name)
            shutil.move(str(path), str(target))
        except FileNotFoundError:
            self.log(
                f'⚠️ 文件在移动前已不存在，可能是网络磁盘目录缓存变化: {path.name} | 原因: {reason}',
                'WARNING',
            )
            return None
        except OSError as exc:
            self.log(f'⚠️ 无法移入 01.wip: {path.name} | 原因: {reason} | {exc}', 'WARNING')
            return None
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

    def _normalize_sequence_cover_name(
        self,
        *,
        video: Path,
        cover: Path,
        shared_stem: str,
        image_by_stem: dict,
    ):
        """Rename only a per-part cover to the group's shared cover name."""
        target = cover.with_name(f'{shared_stem}{cover.suffix.lower()}')
        if target == cover:
            return cover, None
        if target.exists():
            return cover, {
                'source_path': str(video),
                'source_name': video.name,
                'size': self._file_size(video),
                'status': 'needs_review',
                'provider': '-',
                'query': self.clean_filename_for_search(video.name) or '-',
                'reason': 'inspection-sequence-cover-normalize-skipped:target-exists',
                'after': f'共享封面名已存在: {target.name}；未覆盖任何图片',
                'target_video_path': str(video),
                'target_image_path': str(cover),
                'rollback_ok': True,
            }

        try:
            os.rename(cover, target)
            self.atomic_processor._fsync_parent_dir(str(cover))
            self.atomic_processor._fsync_parent_dir(str(target))
        except Exception as exc:
            return cover, {
                'source_path': str(video),
                'source_name': video.name,
                'size': self._file_size(video),
                'status': 'failed',
                'provider': '-',
                'query': self.clean_filename_for_search(video.name) or '-',
                'reason': f'inspection-sequence-cover-normalize-failed:{exc}',
                'after': '共享封面重命名失败，视频和原图片保持原样',
                'target_video_path': str(video),
                'target_image_path': str(cover),
                'rollback_ok': True,
            }

        old_key = self._stem_key(cover.stem)
        old_images = image_by_stem.get(old_key, [])
        image_by_stem[old_key] = [image for image in old_images if image != cover]
        if not image_by_stem[old_key]:
            image_by_stem.pop(old_key, None)
        shared_images = image_by_stem.setdefault(self._stem_key(shared_stem), [])
        if target not in shared_images:
            shared_images.append(target)
        item = {
            'source_path': str(video),
            'source_name': video.name,
            'size': self._file_size(video),
            'status': 'success',
            'provider': '-',
            'query': self.clean_filename_for_search(video.name) or '-',
            'reason': 'inspection-sequence-cover-normalized',
            'after': f'共享封面已规范为: {target.name}；视频文件名保持不变',
            'target_video_path': str(video),
            'target_image_path': str(target),
            'image_downloaded': False,
            'rollback_ok': True,
        }
        self.log(f'✅ 已规范视频组封面名: {cover.name} -> {target.name}', 'SUCCESS')
        return target, item

    def _normalize_single_sequence_pair(
        self,
        *,
        video: Path,
        shared_stem: str,
        image_by_stem: dict,
    ):
        """Remove an isolated sequence marker from one video and its cover."""
        target_video = video.with_name(f'{shared_stem}{video.suffix}')
        if target_video == video or not video.exists():
            return video, None
        if target_video.exists():
            return video, {
                'source_path': str(video),
                'source_name': video.name,
                'size': self._file_size(video),
                'status': 'needs_review',
                'provider': '-',
                'query': self.clean_filename_for_search(video.name) or '-',
                'reason': 'inspection-single-sequence-normalize-skipped:target-exists',
                'after': f'无编号视频已存在: {target_video.name}；未覆盖任何文件',
                'target_video_path': str(video),
                'rollback_ok': True,
            }

        exact_images = [
            image
            for image in self._images_for_stem(image_by_stem, video.stem)
            if image.exists()
        ]
        renames = [(video, target_video)]
        for image in exact_images:
            target_image = image.with_name(f'{shared_stem}{image.suffix.lower()}')
            if target_image == image or target_image.exists():
                continue
            renames.append((image, target_image))

        source_size = self._file_size(video)
        committed = []
        try:
            for source, target in renames:
                os.rename(source, target)
                committed.append((source, target))
            for source, target in committed:
                self.atomic_processor._fsync_parent_dir(str(source))
                self.atomic_processor._fsync_parent_dir(str(target))
        except Exception as exc:
            rollback_ok = True
            for source, target in reversed(committed):
                try:
                    if target.exists() and not source.exists():
                        os.rename(target, source)
                except Exception:
                    rollback_ok = False
            return video, {
                'source_path': str(video),
                'source_name': video.name,
                'size': source_size,
                'status': 'failed',
                'provider': '-',
                'query': self.clean_filename_for_search(video.name) or '-',
                'reason': f'inspection-single-sequence-normalize-failed:{exc}',
                'after': '单文件名称规范失败，已尽力恢复原文件',
                'target_video_path': str(video),
                'rollback_ok': rollback_ok,
            }

        old_video_key = self._stem_key(video.name)
        self._known_video_sizes.pop(old_video_key, None)
        self._known_video_sizes[self._stem_key(target_video.name)] = source_size
        old_image_key = self._stem_key(video.stem)
        renamed_images = {source: target for source, target in renames[1:]}
        if renamed_images:
            remaining = [
                image for image in image_by_stem.get(old_image_key, [])
                if image not in renamed_images
            ]
            if remaining:
                image_by_stem[old_image_key] = remaining
            else:
                image_by_stem.pop(old_image_key, None)
            shared_images = image_by_stem.setdefault(self._stem_key(shared_stem), [])
            for target in renamed_images.values():
                if target not in shared_images:
                    shared_images.append(target)

        target_image_path = next(
            (str(target) for _source, target in renames[1:]),
            None,
        )
        if target_image_path is None:
            shared_image = self._best_valid_image(
                self._images_for_stem(image_by_stem, shared_stem)
            )
            target_image_path = str(shared_image) if shared_image else None
        item = {
            'source_path': str(video),
            'source_name': video.name,
            'size': source_size,
            'status': 'success',
            'provider': '-',
            'query': self.clean_filename_for_search(target_video.name) or '-',
            'reason': 'inspection-single-sequence-normalized',
            'after': f'单文件已规范为: {target_video.name}；封面不带分段编号',
            'target_video_path': str(target_video),
            'target_image_path': target_image_path,
            'image_downloaded': False,
            'rollback_ok': True,
        }
        self.log(f'✅ 已移除单文件分段编号: {video.name} -> {target_video.name}', 'SUCCESS')
        return target_video, item

    def _prune_duplicate_video_pairs(
        self,
        *,
        normal_videos,
        image_by_stem,
        folder_path: str,
        moved_paths: set,
        sequence_videos=None,
        progress_state=None,
    ):
        progress_state = progress_state or {'completed': 0, 'total': 1}
        sequence_cover_by_video = (
            dict(sequence_videos)
            if isinstance(sequence_videos, dict)
            else {video: None for video in (sequence_videos or ())}
        )
        video_stem_keys = {self._stem_key(video.stem) for video in normal_videos}
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
            if video in sequence_cover_by_video:
                shared_stem = sequence_cover_by_video.get(video)
                # A lone explicit part, or a family made only from numbered
                # parts, is a real video group.  If an unnumbered video with
                # exactly the shared stem also exists, keep the historical
                # duplicate-copy check: ``Title`` + ``Title_1`` is normally a
                # copied pair and still needs cover-similarity verification.
                if not shared_stem or self._stem_key(shared_stem) not in video_stem_keys:
                    continue
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
                self._emit_progress(
                    progress_state['completed'],
                    max(int(progress_state.get('total') or 1), 1),
                    f'核对视频内容 {video.name}',
                )
                same_content = self._same_video_content(keep, video)
                if same_content is False:
                    # Same cover is expected for a video group. Different
                    # video bytes prove this is not a duplicate copy.
                    continue
                if same_content is None:
                    item = {
                        'source_path': str(video),
                        'source_name': video.name,
                        'size': self._file_size(video),
                        'status': 'needs_review',
                        'provider': '-',
                        'query': meta.get('query') or '-',
                        'reason': 'inspection-duplicate-video-needs-review:video-content-unavailable',
                        'after': '视频内容比对未完成，文件保持原样',
                        'rollback_ok': True,
                    }
                    results.append(item)
                    self._emit_file_result(item)
                    handled.add(str(video))
                    continue
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
                    'reason': (
                        'inspection-duplicate-video-pair-moved-to-wip:'
                        f'video-sha256-match,cover-distance-{distance}-lte-{threshold}'
                    ),
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

    def _prune_redundant_sequence_covers(
        self,
        *,
        shared_cover_stem_by_video,
        image_by_stem,
        folder_path: str,
        moved_paths: set,
        progress_state=None,
    ):
        """Move per-part covers that duplicate a valid shared sequence cover."""
        progress_state = progress_state or {'completed': 0, 'total': 1}
        grouped_videos = {}
        for video, shared_stem in shared_cover_stem_by_video.items():
            grouped_videos.setdefault(self._stem_key(shared_stem), []).append(video)

        results = []
        handled_images = set()
        for shared_key, videos in grouped_videos.items():
            if self._is_stop_requested():
                return results, True
            shared_cover = self._best_valid_image(
                image_by_stem.get(shared_key, [])
            )
            if not shared_cover:
                continue

            for video in videos:
                if self._is_stop_requested():
                    return results, True
                for image in self._images_for_stem(image_by_stem, video.stem):
                    if (
                        not image.exists()
                        or image == shared_cover
                        or str(image) in handled_images
                    ):
                        continue

                    is_valid = self._is_image_valid(image)
                    distance = (
                        self._image_hash_distance(shared_cover, image)
                        if is_valid
                        else None
                    )
                    if is_valid and (
                        distance is None
                        or distance > self.duplicate_image_similarity_threshold
                    ):
                        continue

                    progress_state['completed'] = int(
                        progress_state.get('completed') or 0
                    ) + 1
                    self._emit_progress(
                        progress_state['completed'],
                        max(int(progress_state.get('total') or 1), 1),
                        f'整理序列冗余封面 {image.name}',
                    )
                    moved = self._move_to_wip(
                        image,
                        folder_path,
                        'redundant-sequence-cover',
                    )
                    if not moved:
                        continue

                    handled_images.add(str(image))
                    moved_paths.add(str(image))
                    item = {
                        'source_path': str(image),
                        'source_name': image.name,
                        'size': self._file_size(Path(moved)),
                        'status': 'success',
                        'provider': '-',
                        'query': self.clean_filename_for_search(video.name) or '-',
                        'reason': 'inspection-redundant-sequence-cover-moved-to-wip',
                        'after': f'已保留共享封面 {shared_cover.name}；冗余分集封面移入 01.wip',
                        'target_video_path': str(video),
                        'target_image_path': moved,
                        'rollback_ok': True,
                    }
                    results.append(item)
                    self._emit_file_result(item)

        return results, False

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
        reject_mismatched_provider_result(query, result)
        raw_meta = result.get('raw_meta') or {}
        if isinstance(raw_meta, dict):
            raw_meta['provider_elapsed_seconds'] = elapsed
            result['raw_meta'] = raw_meta
        self.log(f'⏱️ 巡检 Provider搜索耗时: provider={provider_name} | query={query} | {elapsed:.1f}秒', 'INFO')
        return result, elapsed

    def _search_provider_with_fallback(self, provider, provider_name, decision, query, *, require_image=False):
        result, total_elapsed = self._search_provider(provider, provider_name, query)
        active_name = provider_name

        def usable(candidate):
            if not candidate.get('ok'):
                return False
            if require_image:
                return bool(candidate.get('image_url') or candidate.get('fallback_images'))
            return bool(candidate.get('title'))

        for fallback_name in list((decision or {}).get('candidates') or [provider_name])[1:]:
            if usable(result) or self._is_stop_requested():
                break
            self.log(
                f'🧭 巡检自动来源回退: {query} | {active_name} 未成功，尝试 {fallback_name}',
                'INFO',
            )
            active_name = fallback_name
            result, elapsed = self._search_provider(
                self._get_provider(active_name), active_name, query
            )
            total_elapsed += elapsed
        return result, round(total_elapsed, 3), active_name

    def _deep_reference_cover(self, *, video_path: Path, query: str,
                              preferred_provider: str, max_filename_bytes=None):
        """Fetch and hash one exact provider cover, cached per routed code."""
        provider, provider_name, decision = self._resolve_provider_for_video(
            preferred_provider, video_path, query
        )
        cache_key = (provider_name, self._stem_key(query))
        if cache_key in self._deep_reference_cache:
            cached = dict(self._deep_reference_cache[cache_key])
            cached['cache_hit'] = True
            return cached

        result, provider_elapsed, actual_provider = self._search_provider_with_fallback(
            provider, provider_name, decision, query, require_image=True
        )
        payload = {
            'ok': False,
            'provider': actual_provider,
            'provider_elapsed_seconds': provider_elapsed,
            'title': result.get('title'),
            'image_url': result.get('image_url'),
            'detail_url': result.get('detail_url'),
        }
        if not result.get('ok') or not (result.get('image_url') or result.get('fallback_images')):
            payload['message'] = result.get('message') or '数据源没有返回可用参考封面'
            self._deep_reference_cache[cache_key] = payload
            return dict(payload)

        digest = hashlib.sha256(f'{provider_name}\0{query}'.encode('utf-8')).hexdigest()[:16]
        success, temp_path, message = self.atomic_processor.download_image_to_temp(
            self._image_request_from_result(result, actual_provider),
            f'jfo_cover_verify_{digest}.jpg',
            max_filename_bytes=max_filename_bytes,
        )
        if not success or not temp_path:
            payload['message'] = message or '参考封面下载失败'
            self._deep_reference_cache[cache_key] = payload
            return dict(payload)

        try:
            reference_hash = self._image_dhash(Path(temp_path))
            if reference_hash is None:
                payload['message'] = '参考封面无法计算内容特征'
            else:
                payload.update({'ok': True, 'hash': reference_hash, 'message': '验证完成'})
        finally:
            try:
                Path(temp_path).unlink(missing_ok=True)
            except OSError:
                pass
        self._deep_reference_cache[cache_key] = payload
        return dict(payload)

    def _verify_cover_content(self, *, local_image: Path, video_path: Path, query: str,
                              preferred_provider: str, threshold: int,
                              max_filename_bytes=None):
        reference = self._deep_reference_cover(
            video_path=video_path,
            query=query,
            preferred_provider=preferred_provider,
            max_filename_bytes=max_filename_bytes,
        )
        if not reference.get('ok'):
            return {**reference, 'verified': False}
        local_hash = self._image_dhash(local_image)
        if local_hash is None:
            return {
                **reference,
                'verified': False,
                'message': '本地封面无法计算内容特征',
            }
        distance = (local_hash ^ reference['hash']).bit_count()
        return {
            **reference,
            'verified': True,
            'matches': distance <= threshold,
            'distance': distance,
            'threshold': threshold,
        }

    def _download_cover_for_video(self, *, video_path: Path, image_path: Path, provider, provider_name,
                                  query: str, max_filename_bytes=None, invalid_image_path: Path | None = None,
                                  provider_decision=None):
        result, provider_elapsed, provider_name = self._search_provider_with_fallback(
            provider, provider_name, provider_decision, query, require_image=True
        )
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

        final_path = str(image_path)
        moved_existing = []
        invalid_is_final = bool(
            invalid_image_path and str(invalid_image_path) == final_path
        )
        if invalid_image_path and invalid_image_path.exists():
            moved = self._move_to_wip(
                invalid_image_path,
                str(video_path.parent),
                'invalid-image-replaced',
            )
            if moved:
                moved_existing.append((invalid_image_path, Path(moved)))
        # A corrupt paired cover normally is the same path as final_path. Do not
        # query/move it twice: remote filesystems can briefly report stale exists().
        if not invalid_is_final and os.path.exists(final_path):
            moved = self._move_to_wip(
                Path(final_path),
                str(video_path.parent),
                'duplicate-before-cover-repair',
            )
            if moved:
                moved_existing.append((Path(final_path), Path(moved)))
        try:
            self.atomic_processor._move_temp_image_to_final(temp_path, final_path)
        except Exception as exc:
            try:
                Path(temp_path).unlink(missing_ok=True)
            except OSError:
                pass
            rollback_ok = True
            for original, moved in reversed(moved_existing):
                try:
                    if moved.exists() and not original.exists():
                        shutil.move(str(moved), str(original))
                except OSError:
                    rollback_ok = False
            return False, {
                'source_path': str(video_path),
                'source_name': video_path.name,
                'size': self._file_size(video_path),
                'status': 'failed',
                'provider': provider_name,
                'query': query,
                'reason': f'inspection-cover-commit-failed:{exc}',
                'title': result.get('title'),
                'image_url': result.get('image_url'),
                'detail_url': result.get('detail_url'),
                'image_downloaded': False,
                'rollback_ok': rollback_ok,
                'provider_elapsed_seconds': provider_elapsed,
            }
        self._image_valid_cache[str(Path(final_path))] = True
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
        query_aliases = [normalized_query, compact_query]
        if normalized_query.startswith('TOKYO-HOT-N'):
            query_aliases.append(normalized_query.removeprefix('TOKYO-HOT-'))
        if upper_stem in query_aliases:
            return True
        normalized_stem = upper_stem.replace('_', '-')
        organized_prefixes = tuple(alias + ' ' for alias in query_aliases)
        if normalized_stem.startswith(organized_prefixes) and len(stem) > len(compact_query) + 4:
            return False
        # A title can legitimately contain '@' (for example
        # ``KNAM-064 完ナマSTYLE@のあ ...``). Only treat it as a site marker
        # after ruling out a normal code-prefixed organized title.
        if '@' in stem or '[' in stem or ']' in stem:
            return True
        code_pattern = re.compile(
            r'(?<![A-Z0-9])' + re.escape(normalized_query) + r'(?![A-Z0-9])',
            re.IGNORECASE,
        )
        if code_pattern.search(normalized_stem):
            return False
        return not normalized_stem.startswith(tuple(query_aliases))

    def _process_unprocessed_video(self, *, video_path: Path, provider, provider_name, query: str,
                                   max_length=None, max_filename_bytes=None, provider_decision=None):
        source_size = self._file_size(video_path)
        result, provider_elapsed, provider_name = self._search_provider_with_fallback(
            provider, provider_name, provider_decision, query
        )
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
        deferred = (
            not ok and (
                not video_path.exists() or
                'No such file or directory' in str(message or '') or
                '暂时无法读取' in str(message or '')
            )
        )
        return ok, {
            'source_path': str(video_path),
            'source_name': video_path.name,
            'size': source_size,
            'status': 'skipped' if deferred else payload.get('status') or ('success' if ok else 'failed'),
            'provider': provider_name,
            'query': query,
            'reason': (
                'inspection-unprocessed-repaired' if ok else
                'inspection-video-deferred' if deferred else
                payload.get('reason') or message
            ),
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

    def _normal_video_count(self, videos, file_results):
        """Count videos whose final inspection outcome is still normal.

        One video can emit more than one result.  For example, moving its
        redundant part cover emits ``needs_review`` before the later cover
        health pass emits ``inspection-ok-no-action``.  The later normal
        result must not hide the earlier action in either the UI or summary.
        """
        normal_video_keys = set()
        non_normal_video_keys = set()
        video_keys = {
            self._stem_key(Path(video).name)
            for video in videos
        }

        for item in file_results:
            candidates = (
                item.get('source_path'),
                item.get('target_video_path'),
                item.get('source_name'),
            )
            item_video_key = None
            for candidate in candidates:
                if not candidate:
                    continue
                candidate_path = Path(str(candidate))
                candidate_key = self._stem_key(candidate_path.name)
                if candidate_key in video_keys:
                    item_video_key = candidate_key
                    break
            if not item_video_key:
                continue

            is_normal = (
                item.get('status') == 'skipped'
                and item.get('reason') == 'inspection-ok-no-action'
            )
            if is_normal:
                normal_video_keys.add(item_video_key)
            else:
                non_normal_video_keys.add(item_video_key)

        return len(normal_video_keys - non_normal_video_keys)

    def _wip_moved_count(self, file_results):
        return sum(1 for item in file_results if '-moved-to-wip' in str(item.get('reason') or ''))

    def _log_stage_elapsed(self, stage: str, started_at: float):
        self.log(f'⏱️ 巡检阶段耗时: {stage} | {time.time() - started_at:.1f}秒', 'INFO')

    def run(self, *, folder_path, website, max_length=None, max_filename_bytes=None,
            log_path=None, logs_dir=None, deep_cover_validation=False,
            deep_cover_selected_files=None, deep_cover_similarity_threshold=16,
            known_video_sizes=None):
        started = time.time()
        self._provider_instances = {}
        self._deep_reference_cache = {}
        self._image_valid_cache = {}
        self._image_hash_cache = {}
        self._video_hash_cache = {}
        self._known_video_sizes = {}
        for name, raw_size in (known_video_sizes or {}).items():
            try:
                size = int(raw_size)
            except (TypeError, ValueError):
                continue
            if size > 0:
                self._known_video_sizes[self._stem_key(Path(str(name)).name)] = size
        primary_provider_name = website
        scan_started = time.time()
        videos, images = self._scan_current_dir(folder_path)
        self._log_stage_elapsed('目录扫描', scan_started)
        image_by_stem = {}
        for image in images:
            image_by_stem.setdefault(self._stem_key(image.stem), []).append(image)

        file_results = []
        total_units = (len(videos) * 3) + (len(images) * 2)
        completed = 0
        cancelled = self._is_stop_requested()
        self.log(f'🩺 巡检模式: 扫描 {len(videos)} 个视频，{len(images)} 张图片', 'INFO')
        if website == 'auto_all':
            self.log(
                '🧭 巡检数据源策略: 全自动；先按文件名判断有码/无码，有码按 JavBus → JavHoo → LibreDMM → R18.dev，无码直接选择无码源',
                'INFO',
            )
        deep_selected = {
            unicodedata.normalize('NFC', str(name or ''))
            for name in (deep_cover_selected_files or [])
            if str(name or '').strip()
        }
        deep_threshold = max(0, min(64, int(deep_cover_similarity_threshold)))
        if deep_cover_validation:
            selected_count = sum(
                1 for video in videos
                if unicodedata.normalize('NFC', video.name) in deep_selected
            )
            self.log(
                f'🔎 深度封面验证已开启：仅核验已勾选的 {selected_count} 个视频；'
                f'同一番号/视频组复用参考封面；差异阈值 {deep_threshold}；不自动覆盖本地图片',
                'INFO',
            )
        else:
            self.log(
                '⚡ 深度封面验证未开启：本轮仍会逐张完整解码本地封面，'
                '检查图片是否损坏及文件名是否配对；只是不联网比较封面内容',
                'INFO',
            )

        image_validation_started = time.time()
        completed, image_validation_cancelled = self._prevalidate_images(
            images,
            completed=completed,
            total_units=max(total_units, 1),
        )
        if image_validation_cancelled:
            cancelled = True
        self._log_stage_elapsed('本地封面完整解码与损坏检查', image_validation_started)

        moved_paths = set()
        unavailable_video_stems = set()
        unavailable_video_queries = set()
        normal_videos = []
        small_video_started = time.time()
        progress_stride = 25 if len(videos) >= 500 else 1
        for video_index, video in enumerate(videos, start=1):
            if self._is_stop_requested():
                cancelled = True
                break
            if video_index == 1 or video_index % progress_stride == 0:
                self._emit_file_status(video, 'prechecking', 'small-video')
                self._emit_progress(
                    completed,
                    max(total_units, 1),
                    f'检查视频大小 {video_index}/{len(videos)} · {video.name}',
                )
            cached_size = self._known_video_sizes.get(self._stem_key(video.name))
            size = cached_size
            stat_error = None
            if size is None:
                for attempt in range(2):
                    try:
                        size = video.stat().st_size
                        stat_error = None
                        break
                    except OSError as exc:
                        stat_error = exc
                        if attempt == 0:
                            time.sleep(0.05)
            if size is None:
                unavailable_video_stems.add(self._stem_key(video.stem))
                query_key = self._query_key(video.name)
                if query_key:
                    unavailable_video_queries.add(query_key)
                item = {
                    'source_path': str(video),
                    'source_name': video.name,
                    'size': None,
                    'status': 'skipped',
                    'reason': 'inspection-video-deferred',
                    'read_error': str(stat_error or 'unknown read error'),
                    'rollback_ok': True,
                }
                file_results.append(item)
                self._emit_file_result(item)
                completed += 1
                if video_index % progress_stride == 0 or video_index == len(videos):
                    self._emit_progress(
                        completed,
                        max(total_units, 1),
                        f'已检查视频大小 {video_index}/{len(videos)}',
                    )
                continue
            self._known_video_sizes[self._stem_key(video.name)] = int(size)
            if size < self.minimum_video_size_bytes:
                paired_images = self._images_for_stem(image_by_stem, video.stem)
                moved = []
                self._emit_progress(completed, max(total_units, 1), f'修复小视频 {video.name}')
                moved_video = self._move_to_wip(video, folder_path, 'small-video-or-pair')
                if moved_video:
                    moved.append(moved_video)
                    moved_paths.add(str(video))
                for target in paired_images:
                    moved_path = self._move_to_wip(target, folder_path, 'small-video-or-pair')
                    if moved_path:
                        moved.append(moved_path)
                    # Do not count the same paired cover again as an orphan when
                    # this small-video action already attempted to handle it.
                    moved_paths.add(str(target))
                moved_ok = bool(moved_video)
                item = {
                    'source_path': str(video),
                    'source_name': video.name,
                    'size': size,
                    'status': 'needs_review' if moved_ok else 'failed',
                    'reason': 'inspection-small-video-moved-to-wip' if moved_ok else 'inspection-small-video-move-failed',
                    'after': f'已移入 01.wip: {Path(moved_video).name}' if moved_ok else '移动失败，源文件保持原样',
                    'target_video_path': moved_video,
                    'target_image_path': next((path for path in moved[1:] if Path(path).suffix.lower() in IMAGE_EXTENSIONS), None),
                    'rollback_ok': moved_ok,
                }
                file_results.append(item)
                self._emit_file_result(item)
            else:
                normal_videos.append(video)
                self._emit_file_status(video, 'prechecked', 'small-video')
            completed += 1
            if video_index % progress_stride == 0 or video_index == len(videos):
                self._emit_progress(
                    completed,
                    max(total_units, 1),
                    f'已检查视频大小 {video_index}/{len(videos)}',
                )
        self._log_stage_elapsed('异常小视频检查', small_video_started)

        duplicate_handled_videos = set()
        if not cancelled:
            duplicate_started = time.time()
            sequence_videos = self._shared_cover_stems_for_sequences(normal_videos, images)
            duplicate_progress = {'completed': completed, 'total': max(total_units, 1)}
            normal_videos, duplicate_results, duplicate_handled_videos, cancelled = self._prune_duplicate_video_pairs(
                normal_videos=normal_videos,
                image_by_stem=image_by_stem,
                folder_path=folder_path,
                moved_paths=moved_paths,
                sequence_videos=sequence_videos,
                progress_state=duplicate_progress,
            )
            completed = int(duplicate_progress.get('completed') or completed)
            file_results.extend(duplicate_results)
            self._log_stage_elapsed('重复视频副本检查', duplicate_started)

        normal_video_stems = {self._stem_key(video.stem) for video in normal_videos}
        normal_video_stems.update(unavailable_video_stems)
        normal_video_query_keys = {
            key for key in (self._query_key(video.name) for video in normal_videos) if key
        }
        normal_video_query_keys.update(unavailable_video_queries)
        images_by_query = {}
        for image in images:
            query_key = self._query_key(image.name)
            if query_key:
                images_by_query.setdefault(query_key, []).append(image)
        shared_cover_stem_by_video = self._shared_cover_stems_for_sequences(normal_videos, images)
        shared_cover_stems = {
            self._stem_key(stem)
            for stem in shared_cover_stem_by_video.values()
        }
        redundant_cover_started = time.time()
        redundant_progress = {'completed': completed, 'total': max(total_units, 1)}
        redundant_results, redundant_cancelled = self._prune_redundant_sequence_covers(
            shared_cover_stem_by_video=shared_cover_stem_by_video,
            image_by_stem=image_by_stem,
            folder_path=folder_path,
            moved_paths=moved_paths,
            progress_state=redundant_progress,
        )
        completed = int(redundant_progress.get('completed') or completed)
        file_results.extend(redundant_results)
        if redundant_cancelled:
            cancelled = True
        self._log_stage_elapsed('序列冗余封面检查', redundant_cover_started)

        image_group_started = time.time()
        for stem, group in image_by_stem.items():
            if cancelled or self._is_stop_requested():
                cancelled = True
                break
            group_matches_video_code = any(
                self._query_key(image.name) in normal_video_query_keys
                for image in group
            )
            if (
                stem not in normal_video_stems and
                stem not in shared_cover_stems and
                not group_matches_video_code
            ):
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
                        'status': 'needs_review' if moved else 'failed',
                        'reason': 'inspection-orphan-image-moved-to-wip' if moved else 'inspection-orphan-image-move-failed',
                        'after': f'已移入 01.wip: {Path(moved).name}' if moved else '移动失败，源文件保持原样',
                        'target_image_path': moved,
                        'rollback_ok': bool(moved),
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
                        'status': 'needs_review' if moved else 'failed',
                        'reason': 'inspection-duplicate-image-moved-to-wip' if moved else 'inspection-duplicate-image-move-failed',
                        'after': f'已移入 01.wip: {Path(moved).name}' if moved else '移动失败，源文件保持原样',
                        'target_image_path': moved,
                        'rollback_ok': bool(moved),
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
        sequence_group_sizes = {}
        for sequence_video, sequence_stem in shared_cover_stem_by_video.items():
            sequence_key = self._stem_key(sequence_stem)
            sequence_group_sizes[sequence_key] = sequence_group_sizes.get(sequence_key, 0) + 1
        normal_video_stem_keys = {
            self._stem_key(video.stem) for video in normal_videos
        }
        for sequence_key in tuple(sequence_group_sizes):
            if sequence_key in normal_video_stem_keys:
                # ``Title.mp4`` + ``Title (2).mp4`` is a two-part group, not
                # a lone numbered file that should be collapsed to Title.
                sequence_group_sizes[sequence_key] += 1
        self.log(f'🩺 巡检阶段: 校验配对封面并修复缺失/损坏封面，共 {len(normal_videos)} 个视频', 'INFO')
        for video in normal_videos:
            if cancelled:
                break
            if str(video) in duplicate_handled_videos:
                continue
            if self._is_stop_requested():
                cancelled = True
                break
            self._emit_file_status(video, 'checking', 'cover-health')
            self._emit_progress(completed, max(total_units, 1), f'巡检封面 {video.name}')
            shared_cover_stem = shared_cover_stem_by_video.get(video)
            if (
                shared_cover_stem
                and sequence_group_sizes.get(self._stem_key(shared_cover_stem)) == 1
            ):
                normalized_video, normalize_single_item = self._normalize_single_sequence_pair(
                    video=video,
                    shared_stem=shared_cover_stem,
                    image_by_stem=image_by_stem,
                )
                if normalize_single_item:
                    file_results.append(normalize_single_item)
                    self._emit_file_result(normalize_single_item)
                    if normalize_single_item.get('status') == 'success':
                        video = normalized_video
            query = self.clean_filename_for_search(video.name)
            exact_paired_images = [
                img for img in self._images_for_stem(image_by_stem, video.stem) if img.exists()
            ]
            paired_images = list(exact_paired_images)
            query_key = self._query_key(video.name)
            for image in images_by_query.get(query_key, []):
                if image.exists() and image not in paired_images:
                    paired_images.append(image)
            if shared_cover_stem:
                for image in self._images_for_stem(image_by_stem, shared_cover_stem):
                    if image.exists() and image not in paired_images:
                        paired_images.append(image)
            valid_images = [img for img in paired_images if self._is_image_valid(img)]
            invalid_images = [img for img in paired_images if img not in valid_images]
            checked_cover_pairs += 1
            if checked_cover_pairs % 50 == 0:
                self.log(
                    f'🩺 巡检封面进度: {checked_cover_pairs}/{len(normal_videos)} | '
                    f'耗时 {time.time() - cover_check_started:.1f}秒',
                    'INFO',
                )
            if shared_cover_stem and exact_paired_images:
                valid_shared_images = [
                    image
                    for image in self._images_for_stem(image_by_stem, shared_cover_stem)
                    if image.exists() and self._is_image_valid(image)
                ]
                valid_exact_images = [
                    image for image in exact_paired_images
                    if image.exists() and self._is_image_valid(image)
                ]
                if not valid_shared_images and valid_exact_images:
                    _normalized_cover, normalize_item = self._normalize_sequence_cover_name(
                        video=video,
                        cover=valid_exact_images[0],
                        shared_stem=shared_cover_stem,
                        image_by_stem=image_by_stem,
                    )
                    if normalize_item:
                        file_results.append(normalize_item)
                        self._emit_file_result(normalize_item)
                        completed += 1
                        self._emit_progress(completed, max(total_units, 1), video.name)
                        continue
            if valid_images and not self._looks_unprocessed(video, query):
                normalized_video = video
                normalize_item = None
                if not shared_cover_stem and exact_paired_images:
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
                deep_requested = (
                    bool(deep_cover_validation) and
                    unicodedata.normalize('NFC', video.name) in deep_selected and
                    bool(query)
                )
                if deep_requested:
                    verification = self._verify_cover_content(
                        local_image=valid_images[0],
                        video_path=video,
                        query=query,
                        preferred_provider=primary_provider_name,
                        threshold=deep_threshold,
                        max_filename_bytes=max_filename_bytes,
                    )
                    item.update({
                        'provider': verification.get('provider') or primary_provider_name,
                        'title': verification.get('title'),
                        'image_url': verification.get('image_url'),
                        'detail_url': verification.get('detail_url'),
                        'provider_elapsed_seconds': verification.get('provider_elapsed_seconds'),
                        'cover_content_verified': bool(verification.get('verified')),
                        'cover_reference_cache_hit': bool(verification.get('cache_hit')),
                    })
                    if verification.get('verified'):
                        item.update({
                            'cover_hash_distance': verification.get('distance'),
                            'cover_hash_threshold': verification.get('threshold'),
                        })
                        if not verification.get('matches'):
                            item.update({
                                'status': 'needs_review',
                                'reason': (
                                    'inspection-cover-content-mismatch:'
                                    f'distance-{verification.get("distance")}-gt-{deep_threshold}'
                                ),
                                'after': '封面内容疑似不匹配；本地视频和图片保持原样',
                            })
                    else:
                        item.update({
                            'reason': 'inspection-cover-content-unverified',
                            'cover_verification_message': verification.get('message'),
                            'after': '内容核验未完成；本地视频和图片保持原样',
                        })
                file_results.append(item)
                self._emit_file_result(
                    item,
                    log_result=item.get('reason') != 'inspection-ok-no-action',
                )
                completed += 1
                self._emit_progress(completed, max(total_units, 1), video.name)
                continue

            if query and self._looks_unprocessed(video, query):
                self._emit_progress(completed, max(total_units, 1), f'修复视频 {video.name}')
                provider, provider_name, provider_decision = self._resolve_provider_for_video(primary_provider_name, video, query)
                ok, item = self._process_unprocessed_video(
                    video_path=video,
                    provider=provider,
                    provider_name=provider_name,
                    query=query,
                    max_length=max_length,
                    max_filename_bytes=max_filename_bytes,
                    provider_decision=provider_decision,
                )
                if ok:
                    for old_image in paired_images:
                        if old_image.exists():
                            self._move_to_wip(old_image, folder_path, 'old-cover-after-video-rename')
            elif query:
                image_path = (
                    video.with_name(f'{shared_cover_stem}.jpg')
                    if shared_cover_stem
                    else video.with_suffix('.jpg')
                )
                self._emit_progress(completed, max(total_units, 1), f'修复封面 {video.name}')
                provider, provider_name, provider_decision = self._resolve_provider_for_video(primary_provider_name, video, query)
                ok, item = self._download_cover_for_video(
                    video_path=video,
                    image_path=image_path,
                    provider=provider,
                    provider_name=provider_name,
                    query=query,
                    max_filename_bytes=max_filename_bytes,
                    invalid_image_path=invalid_images[0] if invalid_images else None,
                    provider_decision=provider_decision,
                )
                if ok and shared_cover_stem:
                    shared_images = image_by_stem.setdefault(
                        self._stem_key(shared_cover_stem),
                        [],
                    )
                    if image_path not in shared_images:
                        shared_images.append(image_path)
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

        # A sequence may start with only per-part covers.  The cover-health
        # pass above normalizes the first valid one to the shared cover name,
        # so the earlier redundancy pass could not yet see a shared cover.
        # Re-check now and move only per-part covers whose image content
        # matches the newly created shared cover.
        if not cancelled:
            post_normalize_started = time.time()
            post_normalize_progress = {
                'completed': completed,
                'total': max(total_units, 1),
            }
            post_normalize_results, post_normalize_cancelled = (
                self._prune_redundant_sequence_covers(
                    shared_cover_stem_by_video=shared_cover_stem_by_video,
                    image_by_stem=image_by_stem,
                    folder_path=folder_path,
                    moved_paths=moved_paths,
                    progress_state=post_normalize_progress,
                )
            )
            completed = int(
                post_normalize_progress.get('completed') or completed
            )
            file_results.extend(post_normalize_results)
            if post_normalize_cancelled:
                cancelled = True
            self._log_stage_elapsed(
                '共享封面生成后的冗余封面复查',
                post_normalize_started,
            )

        if cancelled:
            self.log('⏹️ 巡检已停止：已完成的小步骤保留结果，未开始的文件保持原样', 'WARNING')

        counts = self._result_counts(file_results)
        wip_moved_count = self._wip_moved_count(file_results)
        normal_count = self._normal_video_count(videos, file_results)
        unverified_count = sum(
            1 for item in file_results
            if item.get('reason') == 'inspection-cover-content-unverified'
        )
        total_time = round(time.time() - started, 3)
        if not cancelled:
            self._emit_finalizing({
                'mode': 'inspection',
                'success_count': counts.get('success', 0),
                'failed_count': counts.get('failed', 0),
                'planned_count': 0,
                'skipped_hidden': 0,
                'skipped_small': wip_moved_count,
                'skipped_provider_count': 0,
                'needs_review_count': counts.get('needs_review', 0),
                'normal_count': normal_count,
                'unverified_count': unverified_count,
                'cancelled_count': 0,
                'image_success_count': sum(1 for item in file_results if item.get('image_downloaded')),
                'image_failed_count': counts.get('failed', 0),
                'file_result_counts': counts,
                'file_results': file_results,
                'summary_path': None,
                'total_time': total_time,
                'total_files': len(file_results),
            })
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
                after_manifest_status = 'skipped-cancelled-fast-stop'
                self.log('⏹️ 巡检已停止：跳过处理后清单扫描以加快停止', 'WARNING')
            else:
                try:
                    after_manifest_path = write_json_report(
                        os.path.join(logs_dir, f'inspection_manifest_after_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'),
                        scan_folder_manifest(folder_path, include_subdirectories=False),
                    )
                    after_manifest_status = 'written'
                except Exception as exc:
                    after_manifest_path = None
                    after_manifest_status = 'failed'
                    self.log(f'⚠️ 巡检处理后清单生成失败，仍将保留文件结果和运行摘要: {exc}', 'WARNING')
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
                    'unverified_count': unverified_count,
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
                    'after_manifest_status': after_manifest_status,
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

        routed_counts = {}
        for result_item in file_results:
            effective_provider = result_item.get('provider')
            if effective_provider and effective_provider != '-':
                routed_counts[effective_provider] = routed_counts.get(effective_provider, 0) + 1

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
            'unverified_count': unverified_count,
            'cancelled_count': 1 if cancelled else 0,
            'image_success_count': sum(1 for item in file_results if item.get('image_downloaded')),
            'image_failed_count': counts.get('failed', 0),
            'file_result_counts': counts,
            'routed_counts': routed_counts,
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
