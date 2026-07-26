#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WebView shell for the OpenDesign-based JAVFileOrganizer UI."""

from __future__ import annotations

import os
import base64
import io
import json
import mimetypes
import threading
import time
import unicodedata
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from app_metadata import APP_TITLE, BASELINE_BUILD_DATE, BASELINE_BUILD_ID, BASELINE_VERSION, CONFIG_FILENAME, STATUS_READY
from filename_utils import clean_filename_for_search, extract_code_from_text, extract_series_info
from jav_file_organizer import JavFileOrganizer, OptimizedAntiCrawlHandler, ProcessingRequest


class LazyAntiCrawl:
    """Cheap startup placeholder; initializes Selenium only when a provider needs it."""

    def __init__(self, session, log_callback):
        self.session = self._create_request_session()
        self.log_callback = log_callback
        self.selenium_javlibrary = None
        self._real = None

    def _create_request_session(self):
        import requests
        from urllib3.util.retry import Retry

        session = requests.Session()
        session.headers.update({
            'User-Agent': (
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/120.0.0.0 Safari/537.36'
            ),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })
        retry_strategy = Retry(
            total=5,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS", "POST"],
        )
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=20,
            pool_maxsize=50,
            max_retries=retry_strategy,
            pool_block=False,
        )
        session.mount('http://', adapter)
        session.mount('https://', adapter)
        return session

    def ensure(self):
        if self._real is None:
            self._real = OptimizedAntiCrawlHandler(log_callback=self.log_callback)
            self.session = self._real.session
            self.selenium_javlibrary = self._real.selenium_javlibrary
        return self._real

    def stop_browser(self):
        selenium = getattr(self, 'selenium_javlibrary', None)
        if selenium is not None:
            selenium.stop_browser()


class BridgeVar:
    def __init__(self, value=None):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class BridgeButton:
    def config(self, **kwargs):
        pass


class BridgeProgress(dict):
    pass


class OrganizerApi:
    def __init__(self):
        self.window = None
        self.events = []
        self.event_counter = 0
        self.events_lock = threading.Lock()
        self.run_thread = None
        self.test_thread = None
        self.is_processing = False
        self.is_testing = False
        self._shutdown_started = False
        self.last_result = None
        self.selected_folder = ''
        self.workspace_files = []
        self.workspace_scan_meta = {}
        self.last_progress = {}
        self.provider_overrides = {}
        self.settings = {
            'website': 'javbus',
            'dry_run': False,
            'include_subdirectories': False,
            'max_filename_length': '80',
            'max_filename_bytes': '240',
            'preserve_actor': True,
            'batch_count': '',
        }
        self.engine = self._create_engine()
        self._load_bridge_config()

    def set_window(self, window):
        self.window = window

    def _create_engine(self):
        original_init_gui = JavFileOrganizer.init_gui
        try:
            JavFileOrganizer.init_gui = lambda _self: None
            engine = JavFileOrganizer()
        finally:
            JavFileOrganizer.init_gui = original_init_gui

        engine.log = self._log
        engine._run_on_ui_thread = lambda callback: callback()
        engine._update_processing_progress = self._progress
        engine._file_result_callback = self._file_result
        engine._complete_processing_ui = self._complete_processing_ui
        engine._finish_processing_ui = self._finish_processing_ui
        engine._show_messagebox = lambda kind, title, message: self._emit('dialog', {
            'kind': kind,
            'title': title,
            'message': message,
        })
        engine.window = None
        engine.start_btn = BridgeButton()
        engine.stop_btn = BridgeButton()
        engine.test_btn = BridgeButton()
        engine.status_var = BridgeVar(STATUS_READY)
        engine.progress_bar = BridgeProgress()
        engine.progress_var = BridgeVar('就绪')
        engine.progress_percent_var = BridgeVar('0%')
        engine.speed_var = BridgeVar('')
        engine.log_text = None
        engine.folder_var = BridgeVar('')
        engine.website_var = BridgeVar('javbus')
        engine.search_url_var = BridgeVar('')
        engine.text_selector_var = BridgeVar('')
        engine.image_selector_var = BridgeVar('')
        engine.max_filename_length_var = BridgeVar('80')
        engine.max_filename_bytes_var = BridgeVar('240')
        engine.preserve_actor_var = BridgeVar(True)
        engine.include_subdirectories_var = BridgeVar(False)
        engine.batch_count_var = BridgeVar('')
        engine.dry_run_var = BridgeVar(False)
        engine._close_run_log = getattr(engine, '_close_run_log', lambda: None)
        engine.anti_crawl = LazyAntiCrawl(engine.session, self._log)
        self._apply_provider_defaults(engine, 'javbus')
        return engine

    def _ensure_anti_crawl(self, *, require_selenium=False):
        anti_crawl = getattr(self.engine, 'anti_crawl', None)
        ensure = getattr(anti_crawl, 'ensure', None)
        if require_selenium and callable(ensure):
            self.engine.anti_crawl = ensure()
        return self.engine.anti_crawl

    def shutdown(self):
        if self._shutdown_started:
            return {'ok': True}
        self._shutdown_started = True
        self.engine._request_stop()
        active_transaction = self.engine._has_active_file_transaction()

        def cleanup():
            try:
                if not active_transaction:
                    self.engine._cancel_inflight_network()
                else:
                    self._log('退出请求已收到：检测到文件事务，等待事务安全边界', 'WARNING')
            except Exception:
                pass
            try:
                session = getattr(self.engine, 'session', None)
                if session is not None:
                    session.close()
            except Exception:
                pass
            try:
                anti_crawl = getattr(self.engine, 'anti_crawl', None)
                if anti_crawl is not None:
                    anti_crawl.stop_browser()
            except Exception:
                pass

        threading.Thread(target=cleanup, daemon=True).start()
        return {'ok': True}

    def _config_path(self):
        return Path(__file__).resolve().parent / CONFIG_FILENAME

    def _load_bridge_config(self):
        payload = self.engine._load_saved_config()
        if not isinstance(payload, dict):
            payload = {}
        self.provider_overrides = payload.get('provider_overrides') or {}
        website = payload.get('website') or payload.get('default_website') or self.settings['website']
        self.settings.update({
            'website': website,
            'dry_run': bool(payload.get('dry_run', self.settings['dry_run'])),
            # 高成本选项：启动时仍重置为 False，只接收当前会话 UI 显式切换。
            'include_subdirectories': False,
            'max_filename_length': str(payload.get('max_filename_length', self.settings['max_filename_length']) or ''),
            'max_filename_bytes': str(payload.get('max_filename_bytes', self.settings['max_filename_bytes']) or ''),
            'preserve_actor': bool(payload.get('preserve_actor', self.settings['preserve_actor'])),
            'batch_count': str(payload.get('batch_count', self.settings['batch_count']) or ''),
        })
        self._sync_engine_settings({})

    def _provider_default_payload(self, website, engine=None):
        engine = engine or self.engine
        config = engine.website_configs.get(website, {})
        return {
            'search_url': config.get('search_url', ''),
            'text_selector': (config.get('title_selectors') or ['title'])[0],
            'image_selector': (config.get('image_selectors') or ['img'])[0],
        }

    def _provider_effective_payload(self, website, engine=None):
        payload = self._provider_default_payload(website, engine=engine)
        override = self.provider_overrides.get(website) or {}
        payload.update({k: v for k, v in override.items() if v is not None})
        return payload

    def _write_bridge_config(self):
        payload = {
            'website': self.settings.get('website') or 'javbus',
            'default_website': self.settings.get('website') or 'javbus',
            'search_url': self.engine.search_url_var.get(),
            'text_selector': self.engine.text_selector_var.get(),
            'image_selector': self.engine.image_selector_var.get(),
            'max_filename_length': self.settings.get('max_filename_length') or '',
            'max_filename_bytes': self.settings.get('max_filename_bytes') or '',
            'preserve_actor': bool(self.settings.get('preserve_actor', True)),
            'batch_count': self.settings.get('batch_count') or '',
            'dry_run': bool(self.settings.get('dry_run')),
            # 写入配置用于兼容旧 UI；读取时不会自动恢复，避免误扫远程子目录。
            'include_subdirectories': bool(self.settings.get('include_subdirectories')),
            'provider_overrides': self.provider_overrides,
        }
        path = self._config_path()
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        return str(path)

    def _apply_provider_defaults(self, engine, website):
        config = engine.website_configs.get(website, {})
        effective = self._provider_effective_payload(website, engine=engine) if hasattr(self, 'provider_overrides') else {}
        engine.website_var.set(website)
        engine.search_url_var.set(effective.get('search_url') or config.get('search_url', ''))
        engine.text_selector_var.set(effective.get('text_selector') or (config.get('title_selectors') or ['title'])[0])
        engine.image_selector_var.set(effective.get('image_selector') or (config.get('image_selectors') or ['img'])[0])

    def _strip_icons(self, text):
        if not text:
            return ''
        icon_chars = '📝✅⚠️❌🔄📁📊🔎⏱️💾🎬🚀🌐🧪📄🧾🧮📦🧠⏹️⏳🙈🚫🖼️📈🎉✨🔧'
        cleaned = str(text)
        changed = True
        while changed:
            before = cleaned
            cleaned = cleaned.lstrip().lstrip('\ufe0f')
            while cleaned and cleaned[0] in icon_chars:
                cleaned = cleaned[1:].lstrip().lstrip('\ufe0f')
            changed = cleaned != before
        return cleaned

    def _emit(self, event_type, payload):
        self.event_counter += 1
        event = {
            'id': self.event_counter,
            'type': event_type,
            'payload': payload,
            'at': time.time(),
        }
        with self.events_lock:
            self.events.append(event)
            self.events = self.events[-600:]
        if self.window is not None:
            try:
                import json
                self.window.evaluate_js(f'window.JFO && window.JFO.receive({json.dumps(event, ensure_ascii=False)})')
            except Exception:
                pass

    def _reset_workspace_session(self):
        self.last_result = None
        self.workspace_files = []
        self.workspace_scan_meta = {}
        self.last_progress = {}
        with self.events_lock:
            self.events = []

    def _log(self, message, level='INFO'):
        timestamp = time.strftime('%H:%M:%S')
        self._emit('log', {
            'time': timestamp,
            'level': level,
            'message': self._strip_icons(message),
        })

    def _progress(self, completed, total, label=''):
        completed = max(int(completed or 0), 0)
        total = max(int(total or 0), 0)
        percent = int((completed / total) * 100) if total else 0
        self.last_progress = {
            'completed': completed,
            'total': total,
            'percent': percent,
            'label': self._strip_icons(label),
            'stopping': self.engine._is_stop_requested(),
            'updated_at': time.time(),
        }
        self._emit('progress', {
            'completed': completed,
            'total': total,
            'percent': percent,
            'label': self.last_progress['label'],
            'stopping': self.last_progress['stopping'],
        })

    def _file_result(self, item):
        self._update_workspace_from_results([item or {}])
        self._emit('file_result', {'result': item or {}})

    def _complete_processing_ui(self, result, dry_run, run_log_path):
        self._update_workspace_from_results((result or {}).get('file_results') or [])
        self.last_result = result
        self.is_processing = False
        self._emit('complete', {
            'result': result,
            'dry_run': dry_run,
            'run_log_path': run_log_path,
        })
        self._finish_processing_ui()

    def _finish_processing_ui(self):
        self.is_processing = False
        try:
            self.engine._close_run_log()
        except Exception:
            pass
        try:
            self.engine._reset_stop_signal()
        except Exception:
            pass
        self._emit('state', {'processing': False, 'stopping': False})

    def _sync_engine_settings(self, payload=None):
        if isinstance(payload, dict):
            self.settings.update({k: v for k, v in payload.items() if k != 'selected_files'})
        website = self.settings.get('website') or 'javbus'
        self._apply_provider_defaults(self.engine, website)
        config = self.engine.website_configs.get(website, {})
        if isinstance(payload, dict):
            if 'search_url' in payload:
                self.engine.search_url_var.set(str(payload.get('search_url') or ''))
            if 'text_selector' in payload:
                self.engine.text_selector_var.set(str(payload.get('text_selector') or ''))
            if 'image_selector' in payload:
                self.engine.image_selector_var.set(str(payload.get('image_selector') or ''))
        self.engine.folder_var.set(self.selected_folder)
        self.engine.dry_run_var.set(bool(self.settings.get('dry_run')))
        self.engine.include_subdirectories_var.set(bool(self.settings.get('include_subdirectories')))
        self.engine.max_filename_length_var.set(str(self.settings.get('max_filename_length') or ''))
        self.engine.max_filename_bytes_var.set(str(self.settings.get('max_filename_bytes') or ''))
        self.engine.preserve_actor_var.set(bool(self.settings.get('preserve_actor', True)))
        self.engine.batch_count_var.set(str(self.settings.get('batch_count') or ''))
        return website, config

    def initial_state(self):
        providers = []
        for key, config in self.engine.website_configs.items():
            providers.append({
                'key': key,
                'name': config.get('name', key),
                'requires_verification': bool(config.get('requires_verification')),
                'search_url': config.get('search_url', ''),
            })
        return {
            'version': BASELINE_VERSION,
            'build_id': BASELINE_BUILD_ID,
            'build_date': BASELINE_BUILD_DATE,
            'providers': providers,
            'settings': self.settings,
            'folder': self.selected_folder,
            'workspace': {
                'files': list(self.workspace_files),
                'scan_meta': dict(self.workspace_scan_meta),
                'progress': dict(self.last_progress),
                'processing': self.is_processing,
                'testing': self.is_testing,
            },
            'events': list(self.events),
            'last_result': self.last_result,
        }

    def settings_state(self):
        providers = []
        for key, config in self.engine.website_configs.items():
            default_cfg = self._provider_default_payload(key)
            effective_cfg = self._provider_effective_payload(key)
            providers.append({
                'key': key,
                'name': config.get('name', key),
                'requires_verification': bool(config.get('requires_verification')),
                'search_url': effective_cfg.get('search_url', ''),
                'text_selector': effective_cfg.get('text_selector', ''),
                'image_selector': effective_cfg.get('image_selector', ''),
                'default_search_url': default_cfg.get('search_url', ''),
                'default_text_selector': default_cfg.get('text_selector', ''),
                'default_image_selector': default_cfg.get('image_selector', ''),
                'is_overridden': key in self.provider_overrides,
            })
        return {
            'version': BASELINE_VERSION,
            'build_id': BASELINE_BUILD_ID,
            'build_date': BASELINE_BUILD_DATE,
            'providers': providers,
            'settings': dict(self.settings),
            'selected_folder': self.selected_folder,
            'config_path': str(self._config_path()),
            'paths': {
                'finish': '{扫描文件夹}/Finish/',
                'logs': '{扫描文件夹}/JFO_Logs/',
                'transactions': '{扫描文件夹}/.jfo_transactions/',
                'config': str(self._config_path()),
                'javlibrary_cookies': '~/.jav_organizer/javlibrary_selenium_cookies.pkl',
                'javlibrary_profile': '~/.jav_organizer/javlibrary_chrome_profile',
            },
            'video_extensions': sorted(self.engine.video_extensions),
        }

    def set_active_provider(self, website):
        website = str(website or '').strip()
        if website not in self.engine.website_configs:
            return {'ok': False, 'message': f'未知数据源: {website}'}
        self.settings['website'] = website
        self._sync_engine_settings({})
        provider_name = self.engine.website_configs.get(website, {}).get('name', website)
        retryable = {
            'planned', 'plan', 'pending', 'queued', 'todo',
            'review', 'needs_review', 'confirm',
            'audit', 'planned_result', 'dry_run',
            'err', 'error', 'failed', 'failure',
        }
        for row in self.workspace_files:
            if str(row.get('status') or '').strip().lower() in retryable:
                row['provider'] = provider_name
        self._write_bridge_config()
        return {'ok': True, 'website': website, 'settings': dict(self.settings)}

    def save_provider_config(self, payload=None):
        payload = payload or {}
        website = str(payload.get('website') or self.settings.get('website') or '').strip()
        if website not in self.engine.website_configs:
            return {'ok': False, 'message': f'未知数据源: {website}'}
        self.settings['website'] = website
        if website != 'uncensored':
            self.provider_overrides[website] = {
                'search_url': str(payload.get('search_url') or '').strip(),
                'text_selector': str(payload.get('text_selector') or '').strip(),
                'image_selector': str(payload.get('image_selector') or '').strip(),
            }
        self._sync_engine_settings({})
        path = self._write_bridge_config()
        return {'ok': True, 'config_path': path, 'provider': self._provider_effective_payload(website)}

    def reset_provider_config(self, website=None):
        website = str(website or self.settings.get('website') or '').strip()
        if website not in self.engine.website_configs:
            return {'ok': False, 'message': f'未知数据源: {website}'}
        self.provider_overrides.pop(website, None)
        self.settings['website'] = website
        self._sync_engine_settings({})
        path = self._write_bridge_config()
        return {'ok': True, 'config_path': path, 'provider': self._provider_effective_payload(website)}

    def save_processing_settings(self, payload=None):
        payload = payload or {}
        errors = {}
        for field in ('max_filename_length', 'max_filename_bytes', 'batch_count'):
            value = str(payload.get(field) or '').strip()
            if value and (not value.isdigit() or int(value) <= 0):
                errors[field] = '请输入正整数，或留空'
        if errors:
            return {'ok': False, 'errors': errors, 'message': '存在无效数值，请修正后再保存'}
        self.settings.update({
            'max_filename_length': str(payload.get('max_filename_length') or '').strip(),
            'max_filename_bytes': str(payload.get('max_filename_bytes') or '').strip(),
            'batch_count': str(payload.get('batch_count') or '').strip(),
            'preserve_actor': bool(payload.get('preserve_actor', True)),
            'include_subdirectories': bool(payload.get('include_subdirectories', False)),
            'dry_run': bool(payload.get('dry_run', False)),
        })
        self._sync_engine_settings({})
        path = self._write_bridge_config()
        return {'ok': True, 'config_path': path, 'settings': dict(self.settings)}

    def reset_processing_settings(self):
        self.settings.update({
            'max_filename_length': '80',
            'max_filename_bytes': '240',
            'batch_count': '',
            'preserve_actor': True,
            'include_subdirectories': False,
            'dry_run': False,
        })
        self._sync_engine_settings({})
        path = self._write_bridge_config()
        return {'ok': True, 'config_path': path, 'settings': dict(self.settings)}

    def _read_json_if_exists(self, path):
        try:
            if path and os.path.exists(path):
                return json.loads(Path(path).read_text(encoding='utf-8'))
        except Exception:
            return None
        return None

    def _latest_run_summary(self):
        folder = self.selected_folder
        if not folder:
            return None
        logs_dir = Path(folder) / 'JFO_Logs'
        if not logs_dir.exists():
            return None
        summaries = sorted(logs_dir.glob('run_summary_*.json'), key=lambda p: p.stat().st_mtime, reverse=True)
        if not summaries:
            return None
        summary = self._read_json_if_exists(str(summaries[0]))
        if not isinstance(summary, dict):
            return None
        summary['_summary_path'] = str(summaries[0])
        return summary

    def report_state(self):
        result = self.last_result if isinstance(self.last_result, dict) else None
        summary = None
        file_results = []
        artifacts = []

        if result:
            summary_path = result.get('summary_path')
            summary = self._read_json_if_exists(summary_path) if summary_path else None
            file_results = result.get('file_results') or []
            artifact_pairs = [
                ('运行日志', result.get('log_path')),
                ('扫描前清单', result.get('before_manifest_path')),
                ('扫描后清单', result.get('after_manifest_path')),
                ('逐文件结果', result.get('file_results_path')),
                ('命名规则候选', result.get('filename_rule_candidates_path')),
                ('运行摘要', result.get('summary_path')),
            ]
            artifacts = [{'kind': k, 'path': v or '', 'size': self._file_size_text(v)} for k, v in artifact_pairs if v]
        else:
            summary = self._latest_run_summary()
            if summary:
                artifacts_payload = summary.get('artifacts') or {}
                file_results_path = artifacts_payload.get('file_results_path')
                file_results_payload = self._read_json_if_exists(file_results_path)
                if isinstance(file_results_payload, dict):
                    file_results = file_results_payload.get('results') or []
                for key, label in (
                    ('log_path', '运行日志'),
                    ('before_manifest_path', '扫描前清单'),
                    ('after_manifest_path', '扫描后清单'),
                    ('file_results_path', '逐文件结果'),
                    ('filename_rule_candidates_path', '命名规则候选'),
                    ('_summary_path', '运行摘要'),
                ):
                    path = artifacts_payload.get(key) if key != '_summary_path' else summary.get('_summary_path')
                    if path:
                        artifacts.append({'kind': label, 'path': path, 'size': self._file_size_text(path)})

        if not result and summary:
            counts = summary.get('counts') or {}
            result = {
                'generated_at': summary.get('generated_at'),
                'website': summary.get('website'),
                'folder': summary.get('folder'),
                'dry_run': summary.get('dry_run'),
                'total_files': counts.get('total_files') or 0,
                'success_count': counts.get('success_count') or 0,
                'failed_count': counts.get('failed_count') or 0,
                'needs_review_count': counts.get('needs_review_count') or 0,
                'cancelled_count': counts.get('cancelled_count') or 0,
                'skipped_hidden': counts.get('skipped_hidden') or 0,
                'skipped_small': counts.get('skipped_small') or 0,
                'image_success_count': counts.get('image_success_count') or 0,
                'image_failed_count': counts.get('image_failed_count') or 0,
                'total_time': ((summary.get('timings') or {}).get('total_elapsed_seconds') or 0),
            }

        return {
            'version': BASELINE_VERSION,
            'build_id': BASELINE_BUILD_ID,
            'build_date': BASELINE_BUILD_DATE,
            'result': result,
            'summary': summary,
            'file_results': file_results,
            'artifacts': artifacts,
            'selected_folder': self.selected_folder,
        }

    def _file_size_text(self, path):
        try:
            size = os.path.getsize(path)
        except Exception:
            return ''
        return self.engine.format_size(size)

    def poll_events(self, after=0):
        after = int(after or 0)
        with self.events_lock:
            return [event for event in self.events if int(event.get('id') or 0) > after]

    def _resolve_existing_path(self, path):
        expanded = os.path.abspath(os.path.expanduser(str(path or '')))
        if os.path.exists(expanded):
            return expanded
        for form in ('NFC', 'NFD'):
            normalized = unicodedata.normalize(form, expanded)
            if os.path.exists(normalized):
                return normalized

        parts = Path(expanded).parts
        if not parts:
            return expanded
        current = Path(parts[0])
        for part in parts[1:]:
            candidate = current / part
            if candidate.exists():
                current = candidate
                continue
            if not current.is_dir():
                return expanded
            wanted = unicodedata.normalize('NFC', part)
            found = None
            try:
                for child in current.iterdir():
                    if unicodedata.normalize('NFC', child.name) == wanted:
                        found = child
                        break
            except Exception:
                return expanded
            if found is None:
                return expanded
            current = found
        return str(current)

    def cover_image_data(self, path):
        path = str(path or '').strip()
        if not path:
            return {'ok': False, 'message': 'empty-path'}
        if path.startswith('file://'):
            path = path[7:]
        try:
            path = self._resolve_existing_path(path)
            if not os.path.isfile(path):
                return {'ok': False, 'message': 'file-not-found', 'path': path}
            if os.path.getsize(path) > 50 * 1024 * 1024:
                return {'ok': False, 'message': 'image-too-large'}
            try:
                from PIL import Image, ImageOps
                with Image.open(path) as image:
                    image = ImageOps.exif_transpose(image)
                    image.thumbnail((1200, 1600))
                    if image.mode in ('RGBA', 'LA'):
                        background = Image.new('RGB', image.size, (255, 255, 255))
                        background.paste(image, mask=image.getchannel('A'))
                        image = background
                    elif image.mode != 'RGB':
                        image = image.convert('RGB')
                    buffer = io.BytesIO()
                    image.save(buffer, format='JPEG', quality=88, optimize=True)
                    encoded = base64.b64encode(buffer.getvalue()).decode('ascii')
                return {'ok': True, 'src': f'data:image/jpeg;base64,{encoded}', 'path': path}
            except Exception:
                mime = mimetypes.guess_type(path)[0] or 'image/jpeg'
                with open(path, 'rb') as handle:
                    encoded = base64.b64encode(handle.read()).decode('ascii')
                return {'ok': True, 'src': f'data:{mime};base64,{encoded}', 'path': path}
        except Exception as exc:
            return {'ok': False, 'message': str(exc)}

    def choose_folder(self):
        if self.window is None:
            return {'ok': False, 'message': 'window not ready'}
        try:
            import webview
            result = self.window.create_file_dialog(webview.FOLDER_DIALOG, allow_multiple=False)
            if not result:
                return {'ok': False, 'message': 'cancelled'}
            folder = result[0] if isinstance(result, (list, tuple)) else result
            self._reset_workspace_session()
            self.selected_folder = folder
            self.engine.folder_var.set(folder)
            self._emit('folder', {'folder': folder})
            return {'ok': True, 'folder': folder}
        except Exception as e:
            return {'ok': False, 'message': str(e)}

    def set_folder(self, folder):
        folder = str(folder or '').strip()
        self.selected_folder = folder
        self.engine.folder_var.set(folder)
        self._emit('folder', {'folder': folder})
        return {'ok': True, 'folder': folder}

    def _filename_preview(self, name):
        query = clean_filename_for_search(name)
        code = extract_code_from_text(name) or (query.upper() if query else '')
        group, sequence = extract_series_info(name)
        if group:
            code = group
        return {
            'code': code,
            'query': query,
            'group': group or '',
            'sequence': sequence or '',
        }

    def _workspace_preview_from_result(self, result, status, current_after='等待处理'):
        target = os.path.basename(str((result or {}).get('target_video_path') or ''))
        if target:
            return target
        if status in ('success', 'ok', 'succeeded', 'done', 'completed'):
            target_image = os.path.basename(str((result or {}).get('target_image_path') or ''))
            return target_image or current_after
        if status in ('failed', 'failure', 'error', 'err'):
            return '处理失败 - 源文件保持原样'
        if status in ('skipped', 'skip', 'cancelled', 'canceled'):
            return '已跳过 - 源文件保持原样'
        if status in ('needs_review', 'review'):
            return '待确认命名规则'
        if status in ('planned_result', 'audit', 'dry_run'):
            return '已计划 - 未落盘'
        return current_after or '等待处理'

    def _workspace_result_key(self, result):
        result = result or {}
        return (
            result.get('source_name')
            or os.path.basename(str(result.get('source_path') or ''))
            or ''
        )

    def _update_workspace_from_results(self, results):
        if not self.workspace_files:
            return
        rows_by_name = {row.get('name'): row for row in self.workspace_files}
        for result in results or []:
            if not result:
                continue
            row = rows_by_name.get(self._workspace_result_key(result))
            if not row:
                continue
            status = result.get('status') or row.get('status') or 'planned'
            row['status'] = status
            row['provider'] = result.get('provider') or row.get('provider')
            row['query'] = result.get('query') or row.get('query')
            row['title'] = result.get('title') or row.get('title')
            row['img'] = result.get('image_url') or row.get('img')
            row['targetImage'] = result.get('target_image_path') or row.get('targetImage')
            row['detail'] = result.get('detail_url') or row.get('detail')
            row['reason'] = result.get('reason') or ''
            row['note'] = result.get('reason') or ''
            row['after'] = self._workspace_preview_from_result(result, str(status).lower(), row.get('after'))
            if result.get('file_elapsed_seconds') is not None:
                row['elapsed'] = f"{float(result.get('file_elapsed_seconds')):.1f}s"
            row['rollback_ok'] = result.get('rollback_ok')
            row['image_downloaded'] = result.get('image_downloaded')

    def scan_folder(self, settings=None):
        self._sync_engine_settings(settings or {})
        folder = self.selected_folder
        if not folder or not os.path.exists(folder):
            return {'ok': False, 'message': '请选择有效的源目录'}
        started = time.time()
        scan = self.engine._scan_video_files(folder)
        elapsed = time.time() - started
        self.engine._remember_folder_scan(folder, scan, elapsed)
        file_sizes = scan.get('file_sizes') or {}
        files = []
        for name in scan.get('accepted') or []:
            preview = self._filename_preview(name)
            files.append({
                'id': f'f{len(files)}',
                'name': name,
                'path': os.path.join(folder, name),
                'size': file_sizes.get(name, 0),
                'status': 'planned',
                'provider': self.engine.website_configs.get(self.settings.get('website'), {}).get('name', self.settings.get('website')),
                'after': '等待处理',
                'note': '',
                **preview,
            })
        payload = {
            'ok': True,
            'folder': folder,
            'files': files,
            'elapsed': elapsed,
            'total_files': scan.get('total_files', 0),
            'skipped_hidden': len(scan.get('skipped_hidden') or []),
            'skipped_small': len(scan.get('skipped_small') or []),
            'include_subdirectories': self.engine._include_subdirectories(),
        }
        self.workspace_files = [dict(item) for item in files]
        self.workspace_scan_meta = {
            'total_files': payload['total_files'],
            'visible_files': len(files),
            'skipped_hidden': payload['skipped_hidden'],
            'skipped_small': payload['skipped_small'],
            'elapsed': elapsed,
            'include_subdirectories': payload['include_subdirectories'],
        }
        self.last_progress = {}
        self._emit('scan', payload)
        return payload

    def start_processing(self, settings=None):
        if self.is_processing:
            return {'ok': False, 'message': '任务正在处理中'}
        website, config = self._sync_engine_settings(settings or {})
        folder = self.selected_folder
        if not folder or not os.path.exists(folder):
            return {'ok': False, 'message': '请选择有效的源目录'}
        self._ensure_anti_crawl(require_selenium=(website == 'javlibrary'))

        website_config = dict(config)
        website_config['search_url'] = self.engine.search_url_var.get()
        website_config['title_selectors'] = [self.engine.text_selector_var.get()]
        website_config['image_selectors'] = [self.engine.image_selector_var.get()]
        request = ProcessingRequest(
            folder_path=folder,
            website=website,
            website_config=website_config,
            dry_run=bool(self.settings.get('dry_run')),
            batch_count_text=str(self.settings.get('batch_count') or '').strip(),
            max_length_text=str(self.settings.get('max_filename_length') or '').strip(),
            max_filename_bytes_text=str(self.settings.get('max_filename_bytes') or '').strip(),
            include_subdirectories=bool(self.settings.get('include_subdirectories')),
            selected_files=list(settings.get('selected_files') or []) if isinstance(settings, dict) else None,
        )
        self.is_processing = True
        self._emit('state', {'processing': True, 'stopping': False, 'request': asdict(request)})
        self.run_thread = threading.Thread(target=lambda: self.engine._process_files_worker(request), daemon=True)
        self.run_thread.start()
        return {'ok': True}

    def stop_processing(self):
        if not self.is_processing:
            return {'ok': True, 'message': '当前没有运行中的任务'}
        active_transaction = self.engine._has_active_file_transaction()
        self.engine._request_stop()
        if not active_transaction:
            self.engine._cancel_inflight_network()
        self._emit('state', {
            'processing': True,
            'stopping': True,
            'active_transaction': active_transaction,
        })
        self._log(
            '停止请求已提交：已有文件事务，等待安全边界' if active_transaction
            else '停止请求已提交：当前无落盘事务，已请求快速取消网络/浏览器任务',
            'WARNING',
        )
        return {'ok': True, 'active_transaction': active_transaction}

    def _provider_display_name(self, website):
        config = self.engine.website_configs.get(website, {})
        return config.get('name') or website

    def _connection_advice(self, website, result):
        error_type = str((result or {}).get('error_type') or '').lower()
        message = str((result or {}).get('message') or '').lower()
        text = f'{error_type} {message}'
        if website == 'javbus' and 'age-verification' in text:
            return 'JavBus 返回年龄确认页。请先在浏览器打开 JavBus 完成年龄确认，或稍后重试。'
        if website == 'javlibrary' or 'cloudflare' in text or 'challenge' in text:
            return '需要在弹出的 Chrome 窗口完成验证后，再重新测试。'
        if 'verification' in text:
            return '目标站点返回验证页，请先在浏览器完成该站点验证或稍后重试。'
        if 'detail fallback also failed' in text and any(key in text for key in ('500', '502', '503', '504', 'server error', 'too many 500')):
            return '目标站点搜索页和详情页都返回服务端错误；当前源暂时不可用，建议换源或稍后重试。'
        if any(key in text for key in ('500', '502', '503', '504', 'server error', 'too many 500')):
            return '目标站点返回服务端错误；程序会尝试详情页兜底，仍失败时建议稍后重试或换源。'
        if any(key in text for key in ('timeout', 'connection', 'network', 'dns', 'reset', 'proxy')):
            return '请检查网络、代理或远程链路，稍后重试。'
        if '403' in text or 'forbidden' in text:
            return '目标站点拒绝访问，可能需要 Cookie、Referer 或稍后重试。'
        if error_type == 'image-download-failed':
            return '详情页可解析，但封面下载验证失败；处理时会继续使用 provider 的图片下载策略和候选封面。'
        if any(key in text for key in ('not-found', 'not found', 'no result', 'provider-error')):
            return '该测试番号可能在当前源找不到；可以换源或使用无码源自动匹配。'
        return '请查看日志中的错误类型和返回信息。'

    def _normalize_connection_result(self, website, query, result):
        result = dict(result or {})
        provider_name = self._provider_display_name(website)
        result.setdefault('ok', False)
        result.setdefault('error_type', '' if result.get('ok') else 'provider-error')
        result.setdefault('message', '')
        result['provider_name'] = provider_name
        result['query'] = query
        result['tested_at'] = datetime.now().isoformat(timespec='seconds')
        if result.get('ok'):
            result['summary'] = f'连接测试成功：{provider_name} | 测试番号 {query} | 标题已提取 | 封面可下载'
            result['advice'] = ''
        else:
            reason = result.get('message') or result.get('error_type') or '未知错误'
            result['advice'] = self._connection_advice(website, result)
            result['summary'] = f'连接测试失败：{provider_name} | 测试番号 {query} | {reason}'
        return result

    def test_connection(self, settings=None):
        website, _config = self._sync_engine_settings(settings or {})
        if self.is_testing:
            return {'ok': False, 'message': '连接测试正在进行中'}
        test_query_map = {
            'javhoo': 'SONE-753',
            'javbus': 'SONE-753',
            'javlibrary': 'JBD-131',
            'bestjavporn': 'ABF-311',
            'uncensored': 'CARIB-032226-001',
        }
        query = test_query_map.get(website, 'SONE-753')
        self.is_testing = True
        self._emit('state', {'testing': True})

        def worker():
            try:
                self._ensure_anti_crawl(require_selenium=(website == 'javlibrary'))
                result = self.engine._run_connection_probe(website, query)
            except Exception as e:
                result = {
                    'ok': False,
                    'error_type': 'connection-test-error',
                    'message': str(e),
                }
            finally:
                result = self._normalize_connection_result(website, query, result)
                self.is_testing = False
                self._log(result['summary'], 'SUCCESS' if result.get('ok') else 'ERROR')
                if result.get('advice'):
                    self._log(f"连接测试建议：{result['advice']}", 'WARNING')
                self._emit('connection', {'website': website, 'query': query, 'result': result})
                self._emit('state', {'testing': False})

        self.test_thread = threading.Thread(target=worker, daemon=True)
        self.test_thread.start()
        return {'ok': True, 'started': True, 'website': website, 'query': query}


def main():
    try:
        import webview
    except Exception:
        app = JavFileOrganizer()
        app.run()
        return

    api = OrganizerApi()
    html_path = Path(__file__).resolve().parent / 'webui' / 'index.html'
    window = webview.create_window(
        APP_TITLE,
        url=str(html_path),
        js_api=api,
        width=1320,
        height=840,
        min_size=(1120, 700),
    )
    api.set_window(window)
    window.events.closing += lambda: api.shutdown()
    webview.start(debug=False)


if __name__ == '__main__':
    main()
