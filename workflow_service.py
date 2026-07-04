#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import time
from datetime import datetime
from typing import Callable

from manifest_utils import build_run_summary, scan_folder_manifest, write_json_report
from provider_router import route_provider
from providers import create_provider

VIDEO_EXTENSIONS = {'.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v'}


class WorkflowService:
    def __init__(self, *, log: Callable, provider_factory=None, atomic_processor=None,
                 clean_filename_for_search=None, sanitize_filename=None,
                 detect_series_files=None, smart_truncate_filename=None,
                 stop_requested=None, minimum_video_size_bytes: int = 16 * 1024):
        self.log = log
        self.provider_factory = provider_factory or (lambda name: create_provider(name, log=log))
        self.atomic_processor = atomic_processor
        self.clean_filename_for_search = clean_filename_for_search
        self.sanitize_filename = sanitize_filename
        self.detect_series_files = detect_series_files
        self.smart_truncate_filename = smart_truncate_filename
        self.stop_requested = stop_requested or (lambda: False)
        self.minimum_video_size_bytes = minimum_video_size_bytes

    def _scan_video_files(self, folder_path):
        result = {'accepted': [], 'skipped_hidden': [], 'skipped_small': []}
        for file in os.listdir(folder_path):
            file_path = os.path.join(folder_path, file)
            if file.startswith('._') or file.startswith('.'):
                result['skipped_hidden'].append(file)
                continue
            if not os.path.isfile(file_path):
                continue
            _, ext = os.path.splitext(file.lower())
            if ext not in VIDEO_EXTENSIONS:
                continue
            if os.path.getsize(file_path) < self.minimum_video_size_bytes:
                result['skipped_small'].append(file)
                continue
            result['accepted'].append(file)
        return result

    def _resolve_provider(self, preferred_provider, filename, search_query):
        decision = route_provider(preferred_provider, filename, search_query)
        provider = self.provider_factory(preferred_provider)
        return decision, provider, preferred_provider

    def _safe_finish_folder(self, folder_path, finish_folder, dry_run):
        if dry_run:
            return finish_folder
        if not os.path.exists(finish_folder):
            os.makedirs(finish_folder)
            self.log(f'✅ 📁 创建输出文件夹: {finish_folder}', 'SUCCESS')
        return finish_folder

    def run(self, *, folder_path, finish_folder, website, max_length=None,
            batch_count=None, dry_run=False, log_path=None, logs_dir=None):
        start_time = time.time()
        scan = self._scan_video_files(folder_path)
        video_files = scan['accepted']
        skipped_hidden = len(scan['skipped_hidden'])
        skipped_small = len(scan['skipped_small'])
        if batch_count:
            video_files = video_files[:batch_count]
        total_files = len(video_files)
        if total_files == 0:
            return {
                'success_count': 0,
                'failed_count': 0,
                'planned_count': 0,
                'skipped_hidden': skipped_hidden,
                'skipped_small': skipped_small,
                'skipped_provider_count': 0,
                'routed_counts': {},
            }
        if logs_dir:
            before_manifest_path = write_json_report(
                os.path.join(logs_dir, f'manifest_before_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'),
                scan_folder_manifest(folder_path),
            )
        else:
            before_manifest_path = None
        finish_folder = self._safe_finish_folder(folder_path, finish_folder, dry_run)
        video_file_paths = [os.path.join(folder_path, f) for f in video_files]
        series_groups, standalone_files = self.detect_series_files(video_file_paths)
        success_count = 0
        failed_count = 0
        planned_count = 0
        skipped_provider_count = 0
        image_success_count = 0
        image_failed_count = 0
        routed_counts = {}

        for base_code, files in series_groups.items():
            if self.stop_requested():
                break
            decision, provider, provider_name = self._resolve_provider(website, os.path.basename(files[0][0]), base_code)
            if decision.get('action') == 'skip':
                skipped_provider_count += len(files)
                continue
            if decision.get('warning_only'):
                self.log(f'⚠️ provider 警告: {base_code} -> {decision.get("reason")}', 'WARNING')
            routed_counts[provider_name] = routed_counts.get(provider_name, 0) + len(files)
            if dry_run:
                planned_count += len(files)
                self.log(f'🧪 DRY-RUN 序列组: {base_code} | provider={provider_name} | files={len(files)}', 'INFO')
                continue
            result = provider.search(base_code)
            if not result.get('ok'):
                failed_count += len(files)
                continue
            title = result.get('title')
            if max_length:
                title = self.smart_truncate_filename(title, os.path.basename(files[0][0]), max_length)
            ok, payload, _ = self.atomic_processor.process_series_group_atomic(files, title, result.get('image_url'), finish_folder)
            if ok:
                success_count += len(files)
                image_success_count += 1 if payload.get('image_downloaded') else 0
                image_failed_count += 0 if payload.get('image_downloaded') else 1
            else:
                failed_count += len(files)

        for file_path in standalone_files:
            if self.stop_requested():
                break
            filename = os.path.basename(file_path)
            query = self.clean_filename_for_search(filename)
            decision, provider, provider_name = self._resolve_provider(website, filename, query)
            if decision.get('action') == 'skip':
                skipped_provider_count += 1
                continue
            if decision.get('warning_only'):
                self.log(f'⚠️ provider 警告: {filename} -> {decision.get("reason")}', 'WARNING')
            routed_counts[provider_name] = routed_counts.get(provider_name, 0) + 1
            if dry_run:
                planned_count += 1
                self.log(f'🧪 DRY-RUN 文件: {filename} | query={query} | provider={provider_name}', 'INFO')
                continue
            result = provider.search(query)
            if not result.get('ok') or not result.get('title'):
                failed_count += 1
                continue
            title = result.get('title')
            if max_length:
                title = self.smart_truncate_filename(title, filename, max_length)
            file_ext = os.path.splitext(filename)[1]
            new_filename = self.sanitize_filename(f'{title}{file_ext}')
            ok, payload, _ = self.atomic_processor.process_file_atomic(file_path, new_filename, result.get('image_url'), finish_folder)
            if ok:
                success_count += 1
                image_success_count += 1 if payload.get('image_downloaded') else 0
                image_failed_count += 0 if payload.get('image_downloaded') else 1
            else:
                failed_count += 1

        if logs_dir:
            after_manifest_path = write_json_report(
                os.path.join(logs_dir, f'manifest_after_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'),
                scan_folder_manifest(folder_path),
            )
            summary = build_run_summary(
                version='workflow-service', website=website, folder=folder_path,
                total_files=total_files, success_count=success_count, failed_count=failed_count,
                skipped_hidden=skipped_hidden, skipped_small=skipped_small,
                skipped_provider=skipped_provider_count, dry_run=dry_run, log_path=log_path,
                before_manifest_path=before_manifest_path, after_manifest_path=after_manifest_path,
                routed_counts=routed_counts,
            )
            summary_path = write_json_report(
                os.path.join(logs_dir, f'run_summary_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'),
                summary,
            )
        else:
            after_manifest_path = None
            summary_path = None

        return {
            'success_count': success_count,
            'failed_count': failed_count,
            'planned_count': planned_count,
            'skipped_hidden': skipped_hidden,
            'skipped_small': skipped_small,
            'skipped_provider_count': skipped_provider_count,
            'image_success_count': image_success_count,
            'image_failed_count': image_failed_count,
            'routed_counts': routed_counts,
            'before_manifest_path': before_manifest_path,
            'after_manifest_path': after_manifest_path,
            'summary_path': summary_path,
            'total_time': time.time() - start_time,
            'total_files': total_files,
        }
