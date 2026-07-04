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
                 stop_requested=None, minimum_video_size_bytes: int = 16 * 1024,
                 progress_callback=None):
        self.log = log
        self.provider_factory = provider_factory or (lambda name: create_provider(name, log=log))
        self.atomic_processor = atomic_processor
        self.clean_filename_for_search = clean_filename_for_search
        self.sanitize_filename = sanitize_filename
        self.detect_series_files = detect_series_files
        self.smart_truncate_filename = smart_truncate_filename
        self.stop_requested = stop_requested or (lambda: False)
        self.minimum_video_size_bytes = minimum_video_size_bytes
        self.progress_callback = progress_callback or (lambda completed, total, label='': None)

    def _emit_progress(self, completed, total, label=''):
        try:
            self.progress_callback(completed, total, label)
        except Exception as e:
            self.log(f'⚠️ 进度更新失败: {e}', 'WARNING')

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

    def _new_file_result(self, *, source_path, status, provider=None, query=None,
                         reason='', group=None, sequence=None, target_video_path=None,
                         target_image_path=None, image_url=None, title=None,
                         rollback_ok=None, detail_url=None, referer=None,
                         image_downloaded=None, filename_rule_candidate=None,
                         provider_elapsed_seconds=None, file_elapsed_seconds=None,
                         atomic_elapsed_seconds=None):
        return {
            'source_path': source_path,
            'source_name': os.path.basename(source_path) if source_path else None,
            'status': status,
            'provider': provider,
            'query': query,
            'reason': reason,
            'group': group,
            'sequence': sequence,
            'title': title,
            'image_url': image_url,
            'detail_url': detail_url,
            'referer': referer,
            'target_video_path': target_video_path,
            'target_image_path': target_image_path,
            'rollback_ok': rollback_ok,
            'image_downloaded': image_downloaded,
            'filename_rule_candidate': filename_rule_candidate,
            'provider_elapsed_seconds': provider_elapsed_seconds,
            'file_elapsed_seconds': file_elapsed_seconds,
            'atomic_elapsed_seconds': atomic_elapsed_seconds,
        }

    def _file_result_counts(self, file_results):
        counts = {}
        for item in file_results:
            status = item.get('status') or 'unknown'
            counts[status] = counts.get(status, 0) + 1
        return counts

    def _derive_result_stats(self, file_results, total_files):
        file_result_counts = self._file_result_counts(file_results)
        skipped_hidden = 0
        skipped_small = 0
        skipped_provider = 0
        needs_review = 0
        cancelled = 0
        successful_image_paths = set()
        image_failed_count = 0

        for item in file_results:
            status = item.get('status')
            reason = item.get('reason')
            if status == 'skipped' and reason == 'hidden-file':
                skipped_hidden += 1
            elif status == 'skipped' and reason == 'small-video':
                skipped_small += 1
            elif status == 'skipped':
                skipped_provider += 1
            elif status == 'needs_review':
                needs_review += 1
            elif status == 'cancelled':
                cancelled += 1

            if status == 'success':
                if item.get('image_downloaded') and item.get('target_image_path'):
                    successful_image_paths.add(item.get('target_image_path'))
                elif item.get('image_downloaded') is False:
                    image_failed_count += 1

        return {
            'success_count': file_result_counts.get('success', 0),
            'failed_count': file_result_counts.get('failed', 0) + file_result_counts.get('critical', 0),
            'planned_count': file_result_counts.get('planned', 0),
            'skipped_hidden': skipped_hidden,
            'skipped_small': skipped_small,
            'skipped_provider_count': skipped_provider,
            'needs_review_count': needs_review,
            'cancelled_count': cancelled,
            'image_success_count': len(successful_image_paths),
            'image_failed_count': image_failed_count,
            'file_result_counts': file_result_counts,
            'total_files': total_files,
        }

    def _write_file_results(self, *, logs_dir, website, folder_path, dry_run, file_results):
        payload = {
            'generated_at': datetime.now().isoformat(),
            'website': website,
            'folder': folder_path,
            'dry_run': dry_run,
            'counts': self._file_result_counts(file_results),
            'results': file_results,
        }
        return write_json_report(
            os.path.join(logs_dir, f'file_results_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'),
            payload,
        )

    def _write_filename_rule_candidates(self, *, logs_dir, video_files):
        from filename_rule_library import write_filename_rule_candidates
        from filename_utils import analyze_unknown_filename

        candidates = []
        for filename in video_files:
            candidate = analyze_unknown_filename(filename)
            if candidate:
                candidates.append(candidate)

        if not candidates:
            return None

        return write_filename_rule_candidates(
            os.path.join(logs_dir, f'filename_rule_candidates_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'),
            candidates,
        )

    def _write_run_reports(self, *, logs_dir, website, folder_path, dry_run, log_path,
                           before_manifest_path, routed_counts, file_results,
                           total_files, video_files):
        after_manifest_path = write_json_report(
            os.path.join(logs_dir, f'manifest_after_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'),
            scan_folder_manifest(folder_path),
        )
        filename_rule_candidates_path = self._write_filename_rule_candidates(
            logs_dir=logs_dir,
            video_files=video_files,
        )
        file_results_path = self._write_file_results(
            logs_dir=logs_dir,
            website=website,
            folder_path=folder_path,
            dry_run=dry_run,
            file_results=file_results,
        )
        stats = self._derive_result_stats(file_results, total_files)
        summary = build_run_summary(
            version='workflow-service', website=website, folder=folder_path,
            total_files=total_files, success_count=stats['success_count'], failed_count=stats['failed_count'],
            skipped_hidden=stats['skipped_hidden'], skipped_small=stats['skipped_small'],
            skipped_provider=stats['skipped_provider_count'], dry_run=dry_run, log_path=log_path,
            before_manifest_path=before_manifest_path, after_manifest_path=after_manifest_path,
            routed_counts=routed_counts, file_results_path=file_results_path,
            planned_count=stats['planned_count'],
            needs_review_count=stats['needs_review_count'],
            cancelled_count=stats['cancelled_count'],
            image_success_count=stats['image_success_count'],
            image_failed_count=stats['image_failed_count'],
            file_result_counts=stats['file_result_counts'],
            filename_rule_candidates_path=filename_rule_candidates_path,
        )
        summary_path = write_json_report(
            os.path.join(logs_dir, f'run_summary_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'),
            summary,
        )
        return {
            'stats': stats,
            'after_manifest_path': after_manifest_path,
            'file_results_path': file_results_path,
            'filename_rule_candidates_path': filename_rule_candidates_path,
            'summary_path': summary_path,
        }

    def _provider_search(self, cache, provider_name, provider, query):
        cache_key = (provider_name, query)
        if cache_key not in cache:
            started = time.time()
            result = provider.search(query)
            elapsed = time.time() - started
            self._attach_provider_elapsed(result, elapsed)
            self.log(f'⏱️ Provider搜索耗时: provider={provider_name} | query={query} | {elapsed:.1f}秒', 'INFO')
            if self._is_retryable_provider_failure(result) and not self.stop_requested():
                self.log(
                    f'⚠️ {provider_name} 需要验证或验证超时，重试一次: {query}',
                    'WARNING',
                )
                retry_started = time.time()
                result = provider.search(query)
                retry_elapsed = time.time() - retry_started
                elapsed += retry_elapsed
                self._attach_provider_elapsed(result, elapsed)
                self.log(f'⏱️ Provider重试耗时: provider={provider_name} | query={query} | {retry_elapsed:.1f}秒 | 累计 {elapsed:.1f}秒', 'INFO')
            cache[cache_key] = {
                'provider': provider_name,
                'query': query,
                'timestamp': datetime.now().isoformat(),
                'source_url': result.get('referer') or result.get('detail_url'),
                'result': result,
                'elapsed_seconds': elapsed,
            }
        else:
            elapsed = cache[cache_key].get('elapsed_seconds')
            if elapsed is not None:
                self.log(f'⏱️ Provider缓存命中: provider={provider_name} | query={query} | 原搜索耗时 {elapsed:.1f}秒', 'INFO')
        return cache[cache_key]['result']

    def _attach_provider_elapsed(self, result, elapsed):
        raw_meta = result.get('raw_meta') or {}
        if not isinstance(raw_meta, dict):
            raw_meta = {}
        raw_meta['provider_elapsed_seconds'] = round(elapsed, 3)
        if isinstance(result, dict):
            result['raw_meta'] = raw_meta
        else:
            try:
                result.raw_meta = raw_meta
            except Exception:
                pass

    def _provider_elapsed(self, result):
        raw_meta = result.get('raw_meta') or {}
        if isinstance(raw_meta, dict):
            return raw_meta.get('provider_elapsed_seconds')
        return None

    def _is_retryable_provider_failure(self, result):
        if result.get('ok'):
            return False
        return result.get('error_type') in {'verification-timeout', 'verification-required'}

    def _append_cancelled_series(self, file_results, series_items):
        for base_code, files in series_items:
            for file_path, sequence in files:
                file_results.append(self._new_file_result(
                    source_path=file_path,
                    status='cancelled',
                    reason='user-stopped',
                    group=base_code,
                    sequence=sequence,
                ))

    def _append_cancelled_standalone(self, file_results, standalone_files):
        for file_path in standalone_files:
            file_results.append(self._new_file_result(
                source_path=file_path,
                status='cancelled',
                reason='user-stopped',
            ))

    def _empty_paths(self):
        return {
            'after_manifest_path': None,
            'file_results_path': None,
            'filename_rule_candidates_path': None,
            'summary_path': None,
        }

    def _result_payload(self, *, stats, routed_counts, before_manifest_path, paths,
                        file_results, start_time, total_files):
        return {
            'success_count': stats['success_count'],
            'failed_count': stats['failed_count'],
            'planned_count': stats['planned_count'],
            'skipped_hidden': stats['skipped_hidden'],
            'skipped_small': stats['skipped_small'],
            'skipped_provider_count': stats['skipped_provider_count'],
            'needs_review_count': stats['needs_review_count'],
            'cancelled_count': stats['cancelled_count'],
            'image_success_count': stats['image_success_count'],
            'image_failed_count': stats['image_failed_count'],
            'file_result_counts': stats['file_result_counts'],
            'routed_counts': routed_counts,
            'before_manifest_path': before_manifest_path,
            'after_manifest_path': paths['after_manifest_path'],
            'file_results_path': paths['file_results_path'],
            'filename_rule_candidates_path': paths['filename_rule_candidates_path'],
            'file_results': file_results,
            'summary_path': paths['summary_path'],
            'total_time': time.time() - start_time,
            'total_files': total_files,
        }

    def _provider_failure_reason(self, result):
        error_type = result.get('error_type') or 'unknown'
        message = result.get('message') or ''
        return f'provider:{error_type}:{message}'

    def _log_not_processed(self, *, label, provider=None, query=None, reason='',
                           title=None, image_url=None, count=None):
        count_text = f' | files={count}' if count is not None else ''
        provider_text = f' | provider={provider}' if provider else ''
        query_text = f' | query={query}' if query else ''
        self.log(
            f'❌ 未处理: {label}{count_text}{provider_text}{query_text} | 原因: {reason} | 源文件保持原样',
            'ERROR',
        )
        if title:
            self.log(f'   返回标题: {title}', 'WARNING')
        if image_url:
            self.log(f'   返回图片: {image_url}', 'WARNING')

    def run(self, *, folder_path, finish_folder, website, max_length=None,
            batch_count=None, dry_run=False, log_path=None, logs_dir=None):
        start_time = time.time()
        scan = self._scan_video_files(folder_path)
        video_files = scan['accepted']
        if batch_count:
            video_files = video_files[:batch_count]
        total_files = len(video_files)
        if logs_dir:
            before_manifest_path = write_json_report(
                os.path.join(logs_dir, f'manifest_before_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'),
                scan_folder_manifest(folder_path),
            )
        else:
            before_manifest_path = None

        routed_counts = {}
        provider_cache = {}
        file_results = []

        for filename in scan['skipped_hidden']:
            file_results.append(self._new_file_result(
                source_path=os.path.join(folder_path, filename),
                status='skipped',
                reason='hidden-file',
            ))
        for filename in scan['skipped_small']:
            file_results.append(self._new_file_result(
                source_path=os.path.join(folder_path, filename),
                status='skipped',
                reason='small-video',
            ))

        if total_files == 0:
            stats = self._derive_result_stats(file_results, total_files)
            paths = self._empty_paths()
            if logs_dir:
                paths = self._write_run_reports(
                    logs_dir=logs_dir,
                    website=website,
                    folder_path=folder_path,
                    dry_run=dry_run,
                    log_path=log_path,
                    before_manifest_path=before_manifest_path,
                    routed_counts=routed_counts,
                    file_results=file_results,
                    total_files=total_files,
                    video_files=video_files,
                )
                stats = paths['stats']
            return self._result_payload(
                stats=stats,
                routed_counts=routed_counts,
                before_manifest_path=before_manifest_path,
                paths=paths,
                file_results=file_results,
                start_time=start_time,
                total_files=total_files,
            )

        finish_folder = self._safe_finish_folder(folder_path, finish_folder, dry_run)
        video_file_paths = [os.path.join(folder_path, f) for f in video_files]
        series_groups, standalone_files = self.detect_series_files(video_file_paths)
        series_items = list(series_groups.items())
        cancelled = False
        completed_units = 0

        for series_index, (base_code, files) in enumerate(series_items):
            if self.stop_requested():
                self._append_cancelled_series(file_results, series_items[series_index:])
                self._append_cancelled_standalone(file_results, standalone_files)
                cancelled = True
                break
            self._emit_progress(completed_units, total_files, f'正在处理序列组 {base_code}')
            item_started = time.time()
            decision, provider, provider_name = self._resolve_provider(website, os.path.basename(files[0][0]), base_code)
            if decision.get('action') == 'skip':
                reason = decision.get('reason') or 'provider-skip'
                self._log_not_processed(
                    label=f'序列组 {base_code}',
                    provider=provider_name,
                    query=base_code,
                    reason=reason,
                    count=len(files),
                )
                for file_path, sequence in files:
                    file_results.append(self._new_file_result(
                        source_path=file_path,
                        status='skipped',
                        provider=provider_name,
                        query=base_code,
                        reason=reason,
                        group=base_code,
                        sequence=sequence,
                    ))
                completed_units += len(files)
                self._emit_progress(completed_units, total_files, f'序列组 {base_code}')
                continue
            if decision.get('warning_only'):
                self.log(f'⚠️ provider 警告: {base_code} -> {decision.get("reason")}', 'WARNING')
            routed_counts[provider_name] = routed_counts.get(provider_name, 0) + len(files)
            if dry_run:
                self.log(f'🧪 DRY-RUN 序列组: {base_code} | provider={provider_name} | files={len(files)}', 'INFO')
                for file_path, sequence in files:
                    file_results.append(self._new_file_result(
                        source_path=file_path,
                        status='planned',
                        provider=provider_name,
                        query=base_code,
                        reason='dry-run',
                        group=base_code,
                        sequence=sequence,
                    ))
                completed_units += len(files)
                self._emit_progress(completed_units, total_files, f'序列组 {base_code}')
                continue
            result = self._provider_search(provider_cache, provider_name, provider, base_code)
            provider_elapsed = self._provider_elapsed(result)
            if not result.get('ok'):
                reason = self._provider_failure_reason(result)
                file_elapsed = round(time.time() - item_started, 3)
                self._log_not_processed(
                    label=f'序列组 {base_code}',
                    provider=provider_name,
                    query=base_code,
                    reason=reason,
                    title=result.get('title'),
                    image_url=result.get('image_url'),
                    count=len(files),
                )
                for file_path, sequence in files:
                    file_results.append(self._new_file_result(
                        source_path=file_path,
                        status='failed',
                        provider=provider_name,
                        query=base_code,
                        reason=reason,
                        group=base_code,
                        sequence=sequence,
                        title=result.get('title'),
                        image_url=result.get('image_url'),
                        detail_url=result.get('detail_url'),
                        referer=result.get('referer'),
                        provider_elapsed_seconds=provider_elapsed,
                        file_elapsed_seconds=file_elapsed,
                    ))
                completed_units += len(files)
                self._emit_progress(completed_units, total_files, f'序列组 {base_code}')
                continue
            title = result.get('title')
            if max_length:
                title = self.smart_truncate_filename(title, os.path.basename(files[0][0]), max_length)
            atomic_started = time.time()
            ok, payload, message = self.atomic_processor.process_series_group_atomic(files, title, result.get('image_url'), finish_folder)
            atomic_elapsed = round(time.time() - atomic_started, 3)
            file_elapsed = round(time.time() - item_started, 3)
            self.log(
                f'⏱️ 序列组处理耗时: {base_code} | provider={provider_elapsed or 0:.1f}秒 | 落盘/下载={atomic_elapsed:.1f}秒 | 总计={file_elapsed:.1f}秒',
                'INFO',
            )
            if ok:
                target_paths = payload.get('video_paths', [])
                for index, (file_path, sequence) in enumerate(files):
                    file_results.append(self._new_file_result(
                        source_path=file_path,
                        status='success',
                        provider=provider_name,
                        query=base_code,
                        group=base_code,
                        sequence=sequence,
                        title=title,
                        image_url=result.get('image_url'),
                        detail_url=result.get('detail_url'),
                        referer=result.get('referer'),
                        target_video_path=target_paths[index] if index < len(target_paths) else None,
                        target_image_path=payload.get('image_path'),
                        rollback_ok=payload.get('rollback_ok'),
                        image_downloaded=payload.get('image_downloaded'),
                        provider_elapsed_seconds=provider_elapsed,
                        atomic_elapsed_seconds=atomic_elapsed,
                        file_elapsed_seconds=file_elapsed,
                    ))
                completed_units += len(files)
                self._emit_progress(completed_units, total_files, f'序列组 {base_code}')
            else:
                failure_reason = payload.get('reason') or message
                self._log_not_processed(
                    label=f'序列组 {base_code}',
                    provider=provider_name,
                    query=base_code,
                    reason=failure_reason,
                    title=title,
                    image_url=result.get('image_url'),
                    count=len(files),
                )
                for file_path, sequence in files:
                    file_results.append(self._new_file_result(
                        source_path=file_path,
                        status=payload.get('status') or 'failed',
                        provider=provider_name,
                        query=base_code,
                        reason=failure_reason,
                        group=base_code,
                        sequence=sequence,
                        title=title,
                        image_url=result.get('image_url'),
                        detail_url=result.get('detail_url'),
                        referer=result.get('referer'),
                        rollback_ok=payload.get('rollback_ok'),
                        image_downloaded=payload.get('image_downloaded'),
                        provider_elapsed_seconds=provider_elapsed,
                        atomic_elapsed_seconds=atomic_elapsed,
                        file_elapsed_seconds=file_elapsed,
                    ))
                completed_units += len(files)
                self._emit_progress(completed_units, total_files, f'序列组 {base_code}')

        if not cancelled:
            from filename_utils import analyze_unknown_filename

        for standalone_index, file_path in enumerate(standalone_files if not cancelled else []):
            if self.stop_requested():
                self._append_cancelled_standalone(file_results, standalone_files[standalone_index:])
                break
            filename = os.path.basename(file_path)
            self._emit_progress(completed_units, total_files, f'正在处理 {filename}')
            item_started = time.time()
            query = self.clean_filename_for_search(filename)
            if not query:
                candidate = analyze_unknown_filename(filename)
                self._log_not_processed(
                    label=filename,
                    reason='filename-rule-needs-review' if candidate else 'empty-search-query',
                )
                file_results.append(self._new_file_result(
                    source_path=file_path,
                    status='needs_review',
                    reason='filename-rule-needs-review' if candidate else 'empty-search-query',
                    filename_rule_candidate=candidate,
                ))
                completed_units += 1
                self._emit_progress(completed_units, total_files, filename)
                continue
            decision, provider, provider_name = self._resolve_provider(website, filename, query)
            if decision.get('action') == 'skip':
                reason = decision.get('reason') or 'provider-skip'
                self._log_not_processed(
                    label=filename,
                    provider=provider_name,
                    query=query,
                    reason=reason,
                )
                file_results.append(self._new_file_result(
                    source_path=file_path,
                    status='skipped',
                    provider=provider_name,
                    query=query,
                    reason=reason,
                ))
                completed_units += 1
                self._emit_progress(completed_units, total_files, filename)
                continue
            if decision.get('warning_only'):
                self.log(f'⚠️ provider 警告: {filename} -> {decision.get("reason")}', 'WARNING')
            routed_counts[provider_name] = routed_counts.get(provider_name, 0) + 1
            if dry_run:
                self.log(f'🧪 DRY-RUN 文件: {filename} | query={query} | provider={provider_name}', 'INFO')
                file_results.append(self._new_file_result(
                    source_path=file_path,
                    status='planned',
                    provider=provider_name,
                    query=query,
                    reason='dry-run',
                ))
                completed_units += 1
                self._emit_progress(completed_units, total_files, filename)
                continue
            result = self._provider_search(provider_cache, provider_name, provider, query)
            provider_elapsed = self._provider_elapsed(result)
            if not result.get('ok') or not result.get('title'):
                reason = self._provider_failure_reason(result)
                file_elapsed = round(time.time() - item_started, 3)
                self._log_not_processed(
                    label=filename,
                    provider=provider_name,
                    query=query,
                    reason=reason,
                    title=result.get('title'),
                    image_url=result.get('image_url'),
                )
                file_results.append(self._new_file_result(
                    source_path=file_path,
                    status='failed',
                    provider=provider_name,
                    query=query,
                    reason=reason,
                    image_url=result.get('image_url'),
                    title=result.get('title'),
                    detail_url=result.get('detail_url'),
                    referer=result.get('referer'),
                    provider_elapsed_seconds=provider_elapsed,
                    file_elapsed_seconds=file_elapsed,
                ))
                completed_units += 1
                self._emit_progress(completed_units, total_files, filename)
                continue
            title = result.get('title')
            if max_length:
                title = self.smart_truncate_filename(title, filename, max_length)
            file_ext = os.path.splitext(filename)[1]
            new_filename = self.sanitize_filename(f'{title}{file_ext}')
            atomic_started = time.time()
            ok, payload, message = self.atomic_processor.process_file_atomic(file_path, new_filename, result.get('image_url'), finish_folder)
            atomic_elapsed = round(time.time() - atomic_started, 3)
            file_elapsed = round(time.time() - item_started, 3)
            self.log(
                f'⏱️ 文件处理耗时: {filename} | provider={provider_elapsed or 0:.1f}秒 | 落盘/下载={atomic_elapsed:.1f}秒 | 总计={file_elapsed:.1f}秒',
                'INFO',
            )
            if ok:
                file_results.append(self._new_file_result(
                    source_path=file_path,
                    status='success',
                    provider=provider_name,
                    query=query,
                    title=title,
                    image_url=result.get('image_url'),
                    detail_url=result.get('detail_url'),
                    referer=result.get('referer'),
                    target_video_path=payload.get('video_path'),
                    target_image_path=payload.get('image_path'),
                    rollback_ok=payload.get('rollback_ok'),
                    image_downloaded=payload.get('image_downloaded'),
                    provider_elapsed_seconds=provider_elapsed,
                    atomic_elapsed_seconds=atomic_elapsed,
                    file_elapsed_seconds=file_elapsed,
                ))
                completed_units += 1
                self._emit_progress(completed_units, total_files, filename)
            else:
                failure_reason = payload.get('reason') or message
                self._log_not_processed(
                    label=filename,
                    provider=provider_name,
                    query=query,
                    reason=failure_reason,
                    title=title,
                    image_url=result.get('image_url'),
                )
                file_results.append(self._new_file_result(
                    source_path=file_path,
                    status=payload.get('status') or 'failed',
                    provider=provider_name,
                    query=query,
                    reason=failure_reason,
                    title=title,
                    image_url=result.get('image_url'),
                    detail_url=result.get('detail_url'),
                    referer=result.get('referer'),
                    rollback_ok=payload.get('rollback_ok'),
                    image_downloaded=payload.get('image_downloaded'),
                    provider_elapsed_seconds=provider_elapsed,
                    atomic_elapsed_seconds=atomic_elapsed,
                    file_elapsed_seconds=file_elapsed,
                ))
                completed_units += 1
                self._emit_progress(completed_units, total_files, filename)

        stats = self._derive_result_stats(file_results, total_files)

        paths = self._empty_paths()
        if logs_dir:
            paths = self._write_run_reports(
                logs_dir=logs_dir,
                website=website,
                folder_path=folder_path,
                dry_run=dry_run,
                log_path=log_path,
                before_manifest_path=before_manifest_path,
                routed_counts=routed_counts,
                file_results=file_results,
                total_files=total_files,
                video_files=video_files,
            )
            stats = paths['stats']

        return self._result_payload(
            stats=stats,
            routed_counts=routed_counts,
            before_manifest_path=before_manifest_path,
            paths=paths,
            file_results=file_results,
            start_time=start_time,
            total_files=total_files,
        )
