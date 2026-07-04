#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import threading

import jav_file_organizer as jfo_mod


class RecordingWindow:
    def __init__(self):
        self.after_calls = []

    def after(self, ms, callback):
        self.after_calls.append((ms, callback))


class FakeButton:
    def __init__(self):
        self.state = None

    def config(self, **kwargs):
        self.state = kwargs.get('state', self.state)


class FakeVar:
    def __init__(self, value=None):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class FakeProgressBar(dict):
    pass


def make_shell():
    obj = jfo_mod.JavFileOrganizer.__new__(jfo_mod.JavFileOrganizer)
    obj.window = RecordingWindow()
    obj.start_btn = FakeButton()
    obj.stop_btn = FakeButton()
    obj.test_btn = FakeButton()
    obj.status_var = FakeVar()
    obj.progress_bar = FakeProgressBar()
    obj.progress_var = FakeVar()
    obj.progress_percent_var = FakeVar()
    obj.speed_var = FakeVar()
    obj.is_processing = True
    obj.stop_processing = True
    obj._stop_event = threading.Event()
    obj._stop_event.set()
    obj._close_run_log = lambda: None
    return obj


def make_shell_with_inputs():
    obj = make_shell()
    obj.folder_var = FakeVar('/tmp/source')
    obj.website_var = FakeVar('javhoo')
    obj.search_url_var = FakeVar('https://example/search/{query}')
    obj.text_selector_var = FakeVar('h1')
    obj.image_selector_var = FakeVar('img.cover')
    obj.max_filename_length_var = FakeVar('90')
    obj.batch_count_var = FakeVar('12')
    obj.dry_run_var = FakeVar(True)
    obj.website_configs = {
        'javhoo': {
            'name': 'JavHoo',
            'search_url': 'old',
            'title_selectors': ['title'],
            'image_selectors': ['img'],
        }
    }
    return obj


def test_run_on_ui_thread_executes_immediately_on_main_thread():
    obj = make_shell()
    calls = []

    obj._run_on_ui_thread(lambda: calls.append('ran'))

    assert calls == ['ran']
    assert obj.window.after_calls == []


def test_run_on_ui_thread_schedules_from_worker_thread():
    obj = make_shell()
    calls = []
    worker = threading.Thread(target=lambda: obj._run_on_ui_thread(lambda: calls.append('ran')))

    worker.start()
    worker.join()

    assert calls == []
    assert len(obj.window.after_calls) == 1
    ms, callback = obj.window.after_calls[0]
    assert ms == 0
    callback()
    assert calls == ['ran']


def test_finish_processing_ui_resets_controls_on_ui_thread():
    obj = make_shell()

    obj._finish_processing_ui()

    assert obj.is_processing is False
    assert obj.stop_processing is False
    assert obj._is_stop_requested() is False
    assert obj.start_btn.state == jfo_mod.tk.NORMAL
    assert obj.stop_btn.state == jfo_mod.tk.DISABLED
    assert obj.status_var.value == jfo_mod.STATUS_READY


def test_stop_processing_func_sets_thread_safe_cancel_signal():
    obj = make_shell()
    obj.log = lambda *a, **k: None
    obj.stop_processing = False
    obj._stop_event.clear()

    obj.stop_processing_func()

    assert obj.stop_processing is True
    assert obj._is_stop_requested() is True


def test_reset_stop_signal_clears_legacy_flag_and_event():
    obj = make_shell()
    obj.stop_processing = True
    obj._stop_event.set()

    obj._reset_stop_signal()

    assert obj.stop_processing is False
    assert obj._is_stop_requested() is False


def test_capture_processing_request_copies_ui_values():
    obj = make_shell_with_inputs()

    request = obj._capture_processing_request()

    assert request.folder_path == '/tmp/source'
    assert request.website == 'javhoo'
    assert request.dry_run is True
    assert request.batch_count_text == '12'
    assert request.max_length_text == '90'
    assert request.website_config['search_url'] == 'https://example/search/{query}'
    assert request.website_config['title_selectors'] == ['h1']
    assert request.website_config['image_selectors'] == ['img.cover']
    assert obj.website_configs['javhoo']['search_url'] == 'old'


def test_start_processing_passes_plain_request_to_worker(monkeypatch):
    obj = make_shell_with_inputs()
    obj.is_processing = False
    obj.log = lambda *a, **k: None
    captured = []

    class ImmediateThread:
        def __init__(self, target, daemon=None):
            self.target = target
            self.daemon = daemon

        def start(self):
            self.target()

    obj._process_files_worker = lambda request: captured.append(request)
    monkeypatch.setattr(jfo_mod.threading, 'Thread', ImmediateThread)

    obj.start_processing()

    assert len(captured) == 1
    assert captured[0].folder_path == '/tmp/source'
    assert obj.start_btn.state == jfo_mod.tk.DISABLED
    assert obj.stop_btn.state == jfo_mod.tk.NORMAL
    assert obj.status_var.value == "处理中..."


def test_connection_success_uses_safe_messagebox(monkeypatch):
    obj = make_shell_with_inputs()
    obj.website_var.set('javhoo')
    obj.logs = []
    obj.log = lambda message, level='INFO': obj.logs.append((level, message))
    obj._run_connection_probe = lambda website, query: {
        'ok': True,
        'title': 'TITLE',
        'image_url': 'http://image',
    }
    obj.clean_filename_for_search = lambda filename: filename.lower()
    messages = []
    obj._show_messagebox = lambda kind, title, message: messages.append((kind, title, message))

    class ImmediateThread:
        def __init__(self, target, daemon=None):
            self.target = target
            self.daemon = daemon

        def start(self):
            self.target()

    monkeypatch.setattr(jfo_mod.threading, 'Thread', ImmediateThread)

    obj.test_connection()

    assert any(level == 'SUCCESS' and '连接测试成功' in message for level, message in obj.logs)
    assert len(obj.window.after_calls) == 2
    obj.window.after_calls[0][1]()
    assert messages[0][0] == 'info'
    assert messages[0][1] == '测试成功'
    obj.window.after_calls[1][1]()
    assert obj.test_btn.state == jfo_mod.tk.NORMAL
    assert obj.status_var.value == jfo_mod.STATUS_READY


def test_update_processing_progress_shows_timing_estimates(monkeypatch):
    obj = make_shell()
    times = iter([100.0, 110.0, 130.0])
    monkeypatch.setattr(jfo_mod.time, 'time', lambda: next(times))

    obj._update_processing_progress(0, 4, '准备处理')
    assert obj.progress_bar['value'] == 0
    assert obj.progress_var.value == '🔄 处理中: 0/4'
    assert obj.progress_percent_var.value == '0%'
    assert obj.speed_var.value == '平均: 计算中 | 已用时间: 0.0秒 | 剩余时间: 计算中'

    obj._update_processing_progress(1, 4, '正在处理 A.mp4')
    assert obj.progress_bar['value'] == 25
    assert obj.progress_percent_var.value == '25%'
    assert '平均: 10.0秒/文件' in obj.speed_var.value
    assert '已用时间: 10.0秒' in obj.speed_var.value
    assert '剩余时间: 30.0秒' in obj.speed_var.value

    obj._update_processing_progress(2, 4, '正在处理 B.mp4')
    assert obj.progress_bar['value'] == 50
    assert '平均: 15.0秒/文件' in obj.speed_var.value
    assert '已用时间: 30.0秒' in obj.speed_var.value
    assert '剩余时间: 30.0秒' in obj.speed_var.value
