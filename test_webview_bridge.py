import json
import time
import unicodedata
from pathlib import Path

from app_metadata import BASELINE_BUILD_ID, BASELINE_VERSION
from webview_app import OrganizerApi


def _api_with_temp_config(tmp_path):
    api = OrganizerApi()
    api._config_path = lambda: tmp_path / 'config.json'
    return api


def test_webview_initial_state_exposes_real_version_and_providers(tmp_path):
    api = _api_with_temp_config(tmp_path)

    state = api.initial_state()

    assert state['version'] == BASELINE_VERSION
    assert state['build_id'] == BASELINE_BUILD_ID
    assert {'javhoo', 'javbus', 'javlibrary', 'bestjavporn', 'uncensored'} <= {
        item['key'] for item in state['providers']
    }
    assert state['settings']['website'] == 'javbus'
    assert state['settings']['include_subdirectories'] is False


def test_webview_settings_state_contains_version_processing_and_provider_fields(tmp_path):
    api = _api_with_temp_config(tmp_path)

    state = api.settings_state()
    javbus = next(item for item in state['providers'] if item['key'] == 'javbus')

    assert state['version'] == BASELINE_VERSION
    assert state['settings']['max_filename_length'] == '80'
    assert state['settings']['max_filename_bytes'] == '240'
    assert javbus['search_url']
    assert javbus['text_selector']
    assert javbus['image_selector']
    assert state['paths']['config'].endswith('config.json')


def test_webview_save_and_reset_provider_config_persists_per_provider(tmp_path):
    api = _api_with_temp_config(tmp_path)

    saved = api.save_provider_config({
        'website': 'javbus',
        'search_url': 'https://example.test/{query}',
        'text_selector': 'h1',
        'image_selector': '.cover img',
    })

    assert saved['ok'] is True
    payload = json.loads((tmp_path / 'config.json').read_text(encoding='utf-8'))
    assert payload['provider_overrides']['javbus']['search_url'] == 'https://example.test/{query}'
    assert api.engine.search_url_var.get() == 'https://example.test/{query}'

    reset = api.reset_provider_config('javbus')
    assert reset['ok'] is True
    payload = json.loads((tmp_path / 'config.json').read_text(encoding='utf-8'))
    assert 'javbus' not in payload['provider_overrides']
    assert api.engine.search_url_var.get() == api.engine.website_configs['javbus']['search_url']


def test_webview_save_processing_settings_validates_and_persists(tmp_path):
    api = _api_with_temp_config(tmp_path)

    invalid = api.save_processing_settings({'max_filename_length': 'abc'})
    assert invalid['ok'] is False
    assert invalid['errors']['max_filename_length']

    saved = api.save_processing_settings({
        'max_filename_length': '120',
        'max_filename_bytes': '230',
        'batch_count': '10',
        'preserve_actor': False,
        'include_subdirectories': True,
        'dry_run': True,
    })

    assert saved['ok'] is True
    assert api.engine.max_filename_length_var.get() == '120'
    assert api.engine.max_filename_bytes_var.get() == '230'
    assert api.engine.batch_count_var.get() == '10'
    assert api.engine.preserve_actor_var.get() is False
    assert api.engine.include_subdirectories_var.get() is True
    assert api.engine.dry_run_var.get() is True

    payload = json.loads((tmp_path / 'config.json').read_text(encoding='utf-8'))
    assert payload['max_filename_length'] == '120'
    assert payload['max_filename_bytes'] == '230'
    assert payload['batch_count'] == '10'
    assert payload['dry_run'] is True


def test_webview_report_state_uses_last_real_result(tmp_path):
    api = _api_with_temp_config(tmp_path)
    log_path = tmp_path / 'JFO_RUN.log'
    log_path.write_text('ok', encoding='utf-8')
    api.last_result = {
        'website': 'javbus',
        'folder': str(tmp_path),
        'total_files': 1,
        'success_count': 1,
        'failed_count': 0,
        'needs_review_count': 0,
        'total_time': 1.5,
        'log_path': str(log_path),
        'file_results': [{
            'status': 'success',
            'source_path': str(tmp_path / 'ABF-139.mp4'),
            'target_video_path': str(tmp_path / 'Finish' / 'ABF-139 title.mp4'),
            'query': 'ABF-139',
            'file_elapsed_seconds': 1.5,
        }],
    }

    report = api.report_state()

    assert report['version'] == BASELINE_VERSION
    assert report['result']['success_count'] == 1
    assert report['file_results'][0]['query'] == 'ABF-139'
    assert report['artifacts'][0]['kind'] == '运行日志'
    assert report['artifacts'][0]['size']


def test_webview_report_state_lists_only_current_session_runs(tmp_path):
    api = _api_with_temp_config(tmp_path)
    api.set_folder(str(tmp_path))
    logs = tmp_path / 'JFO_Logs'
    logs.mkdir()

    run_payloads = [
        ('20260726_101010', 'javbus', 'ABF-217.mp4', 'success'),
        ('20260726_111111', 'javhoo', 'JBD-102.mp4', 'failed'),
    ]
    summary_paths = []
    for stamp, website, source_name, status in run_payloads:
        log_path = logs / f'JFO_RUN_{stamp}_{website}.log'
        result_path = logs / f'file_results_{stamp}.json'
        summary_path = logs / f'run_summary_{stamp}.json'
        log_path.write_text(source_name, encoding='utf-8')
        result_path.write_text(json.dumps({
            'results': [{
                'status': status,
                'source_name': source_name,
                'query': source_name.split('.')[0],
            }]
        }), encoding='utf-8')
        summary_path.write_text(json.dumps({
            'generated_at': f'2026-07-26T{stamp[-6:-4]}:{stamp[-4:-2]}:{stamp[-2:]}',
            'website': website,
            'folder': str(tmp_path),
            'dry_run': False,
            'counts': {
                'total_files': 1,
                'success_count': 1 if status == 'success' else 0,
                'failed_count': 1 if status == 'failed' else 0,
            },
            'artifacts': {
                'log_path': str(log_path),
                'file_results_path': str(result_path),
            },
        }), encoding='utf-8')
        summary_paths.append(summary_path)

    historical = api.report_state(str(summary_paths[0]))

    assert historical['runs'] == []
    assert historical['result'] is None

    api._remember_session_run({'summary_path': str(summary_paths[1])})
    api._remember_session_run({'summary_path': str(summary_paths[0])})
    report = api.report_state(str(summary_paths[0]))

    assert len(report['runs']) == 2
    assert report['active_run_path'] == str(summary_paths[0])
    assert report['result']['website'] == 'javbus'
    assert report['file_results'][0]['source_name'] == 'ABF-217.mp4'
    assert report['artifacts'][0]['kind'] == '运行日志'


def test_webview_connection_test_runs_in_background_and_emits_result(tmp_path):
    api = _api_with_temp_config(tmp_path)

    def fake_probe(website, query):
        time.sleep(0.02)
        return {'ok': True, 'title': 'ok', 'image_url': 'http://example/image.jpg'}

    api.engine._run_connection_probe = fake_probe
    started = time.monotonic()
    response = api.test_connection({'website': 'javbus'})
    elapsed = time.monotonic() - started

    assert response['ok'] is True
    assert response['started'] is True
    assert elapsed < 0.2

    deadline = time.monotonic() + 1
    events = []
    while time.monotonic() < deadline:
        events = api.poll_events(0)
        if any(event['type'] == 'connection' for event in events):
            break
        time.sleep(0.01)

    connection = next(event for event in events if event['type'] == 'connection')
    assert connection['payload']['website'] == 'javbus'
    assert connection['payload']['result']['ok'] is True
    assert connection['payload']['result']['provider_name']
    assert '连接测试成功' in connection['payload']['result']['summary']
    assert connection['payload']['result']['query'] == 'SONE-753'


def test_webview_emits_file_result_events_for_realtime_table_updates(tmp_path):
    api = _api_with_temp_config(tmp_path)

    api._file_result({
        'source_path': str(tmp_path / 'SONE-753.mp4'),
        'source_name': 'SONE-753.mp4',
        'status': 'success',
        'target_video_path': str(tmp_path / 'Finish' / 'SONE-753 title.mp4'),
        'file_elapsed_seconds': 1.2,
    })

    events = api.poll_events(0)
    event = next(item for item in events if item['type'] == 'file_result')
    assert event['payload']['result']['source_name'] == 'SONE-753.mp4'
    assert event['payload']['result']['status'] == 'success'


def test_webview_cover_image_data_returns_local_data_url(tmp_path):
    from PIL import Image

    api = _api_with_temp_config(tmp_path)
    image = tmp_path / 'cover.jpg'
    Image.new('RGB', (4, 6), (40, 90, 150)).save(image)

    result = api.cover_image_data(str(image))

    assert result['ok'] is True
    assert result['src'].startswith('data:image/jpeg;base64,')


def test_webview_cover_image_data_resolves_unicode_normalized_path(tmp_path):
    from PIL import Image

    api = _api_with_temp_config(tmp_path)
    nfd_name = unicodedata.normalize('NFD', 'エロ過ぎ.jpg')
    nfc_name = unicodedata.normalize('NFC', 'エロ過ぎ.jpg')
    image = tmp_path / nfd_name
    Image.new('RGB', (4, 6), (120, 50, 60)).save(image)

    result = api.cover_image_data(str(tmp_path / nfc_name))

    assert result['ok'] is True
    assert result['src'].startswith('data:image/jpeg;base64,')


def test_webview_choose_new_folder_resets_workspace_event_history(tmp_path):
    api = _api_with_temp_config(tmp_path)
    folder = tmp_path / 'next'
    folder.mkdir()
    api.last_result = {'success_count': 1}
    api.workspace_files = [{'name': 'old.mp4'}]
    api.workspace_scan_meta = {'total_files': 1}
    api.last_progress = {'total': 1}
    api._emit('complete', {'result': {'file_results': []}})

    class FakeWindow:
        def create_file_dialog(self, *args, **kwargs):
            return [str(folder)]

    api.set_window(FakeWindow())
    result = api.choose_folder()

    assert result['ok'] is True
    assert api.last_result is None
    assert api.workspace_files == []
    assert api.workspace_scan_meta == {}
    assert api.last_progress == {}
    events = api.poll_events(0)
    assert [event['type'] for event in events] == ['folder']
    assert events[0]['payload']['folder'] == str(folder)


def test_webview_scan_uses_backend_filename_rules_for_preview_codes(tmp_path):
    api = _api_with_temp_config(tmp_path)
    api.set_folder(str(tmp_path))

    def fake_scan(folder):
        return {
            'accepted': [
                'hhd800.com@MIDA-588.mp4',
                'hhd800.com@MIDA-678.mp4',
                'MIRD-277_3.mp4',
            ],
            'file_sizes': {
                'hhd800.com@MIDA-588.mp4': 1024,
                'hhd800.com@MIDA-678.mp4': 2048,
                'MIRD-277_3.mp4': 4096,
            },
            'total_files': 3,
            'skipped_hidden': [],
            'skipped_small': [],
            'manifest_entries': [],
        }

    api.engine._scan_video_files = fake_scan
    result = api.scan_folder({'website': 'javbus'})

    assert result['ok'] is True
    by_name = {item['name']: item for item in result['files']}
    assert by_name['hhd800.com@MIDA-588.mp4']['code'] == 'MIDA-588'
    assert by_name['hhd800.com@MIDA-588.mp4']['query'] == 'mida-588'
    assert by_name['hhd800.com@MIDA-678.mp4']['code'] == 'MIDA-678'
    assert by_name['MIRD-277_3.mp4']['code'] == 'MIRD-277'
    assert by_name['MIRD-277_3.mp4']['query'] == 'mird-277'
    assert by_name['MIRD-277_3.mp4']['group'] == 'MIRD-277'
    assert by_name['MIRD-277_3.mp4']['sequence'] == '3'


def test_webview_initial_state_restores_workspace_snapshot_after_event_truncation(tmp_path):
    api = _api_with_temp_config(tmp_path)
    api.set_folder(str(tmp_path))

    def fake_scan(folder):
        return {
            'accepted': ['ABF-217.mp4', 'ABF-244.mp4'],
            'file_sizes': {'ABF-217.mp4': 1024, 'ABF-244.mp4': 2048},
            'total_files': 2,
            'skipped_hidden': [],
            'skipped_small': [],
            'manifest_entries': [],
        }

    api.engine._scan_video_files = fake_scan
    api.scan_folder({'website': 'javbus'})
    api._file_result({
        'source_path': str(tmp_path / 'ABF-217.mp4'),
        'source_name': 'ABF-217.mp4',
        'status': 'success',
        'provider': 'javbus',
        'query': 'abf-217',
        'title': 'ABF-217 title',
        'target_video_path': str(tmp_path / 'Finish' / 'ABF-217 title.mp4'),
        'target_image_path': str(tmp_path / 'Finish' / 'ABF-217 title.jpg'),
        'file_elapsed_seconds': 3.4,
        'image_downloaded': True,
    })

    with api.events_lock:
        api.events = []
    state = api.initial_state()
    rows = {item['name']: item for item in state['workspace']['files']}

    assert state['events'] == []
    assert state['workspace']['scan_meta']['total_files'] == 2
    assert rows['ABF-217.mp4']['status'] == 'success'
    assert rows['ABF-217.mp4']['after'] == 'ABF-217 title.mp4'
    assert rows['ABF-217.mp4']['targetImage'].endswith('ABF-217 title.jpg')
    assert rows['ABF-217.mp4']['elapsed'] == '3.4s'
    assert rows['ABF-244.mp4']['status'] == 'planned'


def test_webview_prepare_run_workspace_clears_previous_run_and_rescans(tmp_path):
    api = _api_with_temp_config(tmp_path)
    api.set_folder(str(tmp_path))
    api.last_result = {'success_count': 1}
    api.workspace_files = [{'name': 'old.mp4', 'status': 'success'}]
    api.workspace_scan_meta = {'total_files': 1}
    api.last_progress = {'total': 1}
    api._emit('complete', {'result': {'file_results': []}})

    def fake_scan(folder):
        return {
            'accepted': ['retry.mp4'],
            'file_sizes': {'retry.mp4': 1024},
            'total_files': 1,
            'skipped_hidden': [],
            'skipped_small': [],
            'manifest_entries': [],
        }

    api.engine._scan_video_files = fake_scan
    result = api.prepare_run_workspace({'website': 'javhoo'})

    assert result['ok'] is True
    assert result['files'][0]['name'] == 'retry.mp4'
    assert api.last_result is None
    assert api.last_progress == {}
    assert api.workspace_files[0]['name'] == 'retry.mp4'
    assert api.poll_events(0) == []


def test_webview_provider_switch_keeps_failed_rows_retryable_in_workspace_snapshot(tmp_path):
    api = _api_with_temp_config(tmp_path)
    api.workspace_files = [
        {'name': 'failed.mp4', 'status': 'failed', 'provider': 'JavBus'},
        {'name': 'planned.mp4', 'status': 'planned', 'provider': 'JavBus'},
        {'name': 'done.mp4', 'status': 'success', 'provider': 'JavBus'},
    ]

    result = api.set_active_provider('javhoo')

    assert result['ok'] is True
    javhoo_name = api.engine.website_configs['javhoo']['name']
    assert api.workspace_files[0]['provider'] == javhoo_name
    assert api.workspace_files[1]['provider'] == javhoo_name
    assert api.workspace_files[2]['provider'] == 'JavBus'


def test_webview_start_processing_passes_selected_files_to_worker(tmp_path):
    api = _api_with_temp_config(tmp_path)
    api.set_folder(str(tmp_path))
    captured = []

    def fake_worker(request):
        captured.append(request)

    api.engine._process_files_worker = fake_worker
    response = api.start_processing({
        'website': 'javbus',
        'selected_files': ['SONE-753.mp4', 'ABF-139-1.mp4'],
    })

    assert response['ok'] is True
    deadline = time.monotonic() + 1
    while time.monotonic() < deadline and not captured:
        time.sleep(0.01)

    assert captured
    assert captured[0].selected_files == ['SONE-753.mp4', 'ABF-139-1.mp4']


def test_webview_connection_failure_includes_clear_advice(tmp_path):
    api = _api_with_temp_config(tmp_path)

    javlibrary_failed = api._normalize_connection_result(
        'javlibrary',
        'JBD-131',
        {
            'ok': False,
            'error_type': 'verification-required',
            'message': 'Cloudflare verification page',
        },
    )
    javbus_failed = api._normalize_connection_result(
        'javbus',
        'SONE-753',
        {
            'ok': False,
            'error_type': 'invalid-result',
            'message': 'javbus invalid result: age-verification-title,missing-image',
        },
    )
    javhoo_500_failed = api._normalize_connection_result(
        'javhoo',
        'SONE-753',
        {
            'ok': False,
            'error_type': 'server-error',
            'message': "too many 500 error responses; detail fallback also failed: too many 500 error responses",
        },
    )

    assert '连接测试失败' in javlibrary_failed['summary']
    assert 'JBD-131' in javlibrary_failed['summary']
    assert 'Chrome' in javlibrary_failed['advice']
    assert 'JavBus 返回年龄确认页' in javbus_failed['advice']
    assert 'Chrome' not in javbus_failed['advice']
    assert '服务端错误' in javhoo_500_failed['advice']
    assert '搜索页和详情页' in javhoo_500_failed['advice']


def test_webview_shutdown_does_not_block_on_slow_browser_cleanup(tmp_path):
    api = _api_with_temp_config(tmp_path)

    class SlowAntiCrawl:
        class Selenium:
            def stop_browser(self):
                time.sleep(1)

        selenium_javlibrary = Selenium()

    api.engine.anti_crawl = SlowAntiCrawl()
    started = time.monotonic()
    response = api.shutdown()
    elapsed = time.monotonic() - started

    assert response['ok'] is True
    assert elapsed < 0.2


def test_webview_lazy_anti_crawl_keeps_legacy_request_session(tmp_path):
    api = _api_with_temp_config(tmp_path)

    anti_session = api.engine.anti_crawl.session

    assert anti_session is not api.engine.session
    assert 'Macintosh' in anti_session.headers.get('User-Agent', '')
    assert 'Chrome/120.0.0.0' in anti_session.headers.get('User-Agent', '')
    assert anti_session.headers.get('Accept-Language') == 'zh-CN,zh;q=0.9,en;q=0.8'


def test_webview_html_no_longer_contains_stubbed_settings_or_demo_report():
    root = Path(__file__).resolve().parent / 'webui'

    index = (root / 'index.html').read_text(encoding='utf-8')
    workspace = (root / 'workspace.html').read_text(encoding='utf-8')
    settings = (root / 'settings.html').read_text(encoding='utf-8')
    report = (root / 'report.html').read_text(encoding='utf-8')

    assert '完整设置页下一步接入' not in index
    assert (root / 'app-icon.png').exists()
    for html in (index, workspace, settings, report):
        assert 'src="app-icon.png"' in html
        assert 'appmark svg' not in html
        assert 'v1.5.14' not in html
        assert 'baseline-v1.5.14' not in html
    assert 'bridgeReady' in index
    assert 'bridgeReady' in settings
    assert 'bridgeReady' in report
    assert 'poll_events' in settings
    assert '连接测试成功' in index
    assert '连接测试失败' in index
    assert 'connectionAdvice' in index
    assert 'JavBus 返回年龄确认页' in index
    assert '目标站点返回服务端错误' in index
    assert '目标站点搜索页和详情页都返回服务端错误' in index
    assert 'state-running' in index
    assert 'btnCopyLog' in index
    assert 'user-select: text' in index
    assert 'logPlainText' in index
    assert 'code:f.code||guessCode(f.name)' in index
    assert 'query:f.query||' in index
    assert 'class="fchip"' in index
    assert 'class="rowcheck"' in index
    assert 'class="chev"' in index
    assert 'st st-ok' in index
    assert 'function normalizeStatus' in index
    assert "'计划':'planned'" in index
    assert "success:'ok'" in index
    assert "needs_review:'review'" in index
    assert "cancelled:'skip'" in index
    assert 'data-status="${status}"' in index
    assert 'markRunning(label)' in index
    assert "ev.type==='file_result'" in index
    assert 'updateFromResults([p.result||{}])' in index
    assert 'cover_image_data' in index
    assert 'function coverHtml(f)' in index
    assert 'function loadCover(f,id)' in index
    assert 'function coverErrorText' in index
    assert '本地封面不存在' in index
    assert '远程封面加载失败' in index
    assert 'function previewFromResult' in index
    assert 'function applyCompletedProgress' in index
    assert 'applyCompletedProgress(p.result,p.dry_run)' in index
    assert '处理失败 - 源文件保持原样' in index
    assert 'f.targetImage=r.target_image_path||f.targetImage' in index
    assert "['本地封面',f.targetImage||'—']" in index
    assert 'function selectedProcessableFiles' in index
    assert 'function isProcessableStatus' in index
    assert "['planned','review','audit','err']" in index
    assert 'selected_files: selectedProcessableFiles()' in index
    assert '失败、待确认' in index
    assert '没有勾选可处理文件' in index
    assert '本次将处理已勾选文件' in index
    assert 'function resetWorkspaceForNewFolder' in index
    assert 'function resetRunSurface' in index
    assert 'function prepareWorkspaceForRun' in index
    assert "api('prepare_run_workspace',settings)" in index
    assert '新处理动作：正在刷新当前目录' in index
    assert '刷新后没有勾选可处理文件' in index
    assert 'function restoreWorkspaceSnapshot' in index
    assert 'restoreWorkspaceSnapshot(s.workspace||{})' in index
    assert 'function scrollToFile' in index
    assert 'function jumpToLogForFile' in index
    assert 'logTermsForFile(f)' in index
    assert "tr.onclick=()=>jumpToLogForFile(id)" in index
    assert '.logline.hit' in index
    assert "tr.closest('.tablewrap')" in index
    assert "mode:'follow'" in index
    assert "!f._finalized" in index
    assert "f._finalized=true" in index
    assert 'renderTable({scrollTo:current&&current.id' in index
    assert 'renderTable({scrollTo:touched[touched.length-1]' in index
    assert 'if(!(replay&&state.files.length))' in index
    assert "receive(ev,{replay:true})" in index
    assert 'if(!replay)' in index
    assert "window.addEventListener('pageshow',()=>hideTransientOverlays())" in index
    assert "const status=normalizeStatus(f.status||'planned')" in index
    assert "_finalized:['ok','err','skip','review','audit'].includes(status)" in index
    assert 'class="filter ' not in index
    assert 'class="pill ' not in index
    assert 'class="rowbtn"' not in index
    assert 'class="fchip"' in workspace
    assert 'class="rowcheck"' in workspace
    assert 'class="chev"' in workspace
    assert 'function normalizeStatus' in workspace
    assert "'计划':'planned'" in workspace
    assert 'data-status="${status}"' in workspace
    assert 'markRunning(label)' in workspace
    assert "ev.type==='file_result'" in workspace
    assert 'updateFromResults([p.result||{}])' in workspace
    assert 'cover_image_data' in workspace
    assert 'function coverHtml(f)' in workspace
    assert 'function loadCover(f,id)' in workspace
    assert 'function coverErrorText' in workspace
    assert '本地封面不存在' in workspace
    assert '远程封面加载失败' in workspace
    assert 'function previewFromResult' in workspace
    assert 'function applyCompletedProgress' in workspace
    assert 'applyCompletedProgress(p.result,p.dry_run)' in workspace
    assert '处理失败 - 源文件保持原样' in workspace
    assert 'f.targetImage=r.target_image_path||f.targetImage' in workspace
    assert "['本地封面',f.targetImage||'—']" in workspace
    assert 'function selectedProcessableFiles' in workspace
    assert 'function isProcessableStatus' in workspace
    assert "['planned','review','audit','err']" in workspace
    assert 'selected_files: selectedProcessableFiles()' in workspace
    assert '失败、待确认' in workspace
    assert '没有勾选可处理文件' in workspace
    assert '本次将处理已勾选文件' in workspace
    assert 'function resetWorkspaceForNewFolder' in workspace
    assert 'function resetRunSurface' in workspace
    assert 'function prepareWorkspaceForRun' in workspace
    assert "api('prepare_run_workspace',settings)" in workspace
    assert '新处理动作：正在刷新当前目录' in workspace
    assert '刷新后没有勾选可处理文件' in workspace
    assert 'function restoreWorkspaceSnapshot' in workspace
    assert 'restoreWorkspaceSnapshot(s.workspace||{})' in workspace
    assert 'function scrollToFile' in workspace
    assert 'function jumpToLogForFile' in workspace
    assert 'logTermsForFile(f)' in workspace
    assert "tr.onclick=()=>jumpToLogForFile(id)" in workspace
    assert '.logline.hit' in workspace
    assert "tr.closest('.tablewrap')" in workspace
    assert "mode:'follow'" in workspace
    assert "!f._finalized" in workspace
    assert "f._finalized=true" in workspace
    assert 'renderTable({scrollTo:current&&current.id' in workspace
    assert 'renderTable({scrollTo:touched[touched.length-1]' in workspace
    assert 'if(!(replay&&state.files.length))' in workspace
    assert "receive(ev,{replay:true})" in workspace
    assert 'if(!replay)' in workspace
    assert "window.addEventListener('pageshow',()=>hideTransientOverlays())" in workspace
    assert "const status=normalizeStatus(f.status||'planned')" in workspace
    assert "_finalized:['ok','err','skip','review','audit'].includes(status)" in workspace
    assert 'class="filter ' not in workspace
    assert 'class="pill ' not in workspace
    assert 'class="rowbtn"' not in workspace
    assert 'state.dryRun=!!state.settings.dry_run' in index
    assert 'const wasStopping=state.stopping' in index
    show_connection = index.split('function showConnectionResult', 1)[1].split('function receive', 1)[0]
    assert 'log(' not in show_connection
    assert '连接测试成功' in settings
    assert '连接测试失败' in settings
    assert 'connectionAdvice' in settings
    assert 'JavBus 返回年龄确认页' in settings
    assert '目标站点返回服务端错误' in settings
    assert '目标站点搜索页和详情页都返回服务端错误' in settings
    assert 'settings_state' in settings
    assert 'save_provider_config' in settings
    assert '169 通过' not in settings
    assert '快捷键' not in settings
    assert 'report_state' in report
    assert 'state.runs' in report
    assert 'state.active_run_path' in report
    assert 'data-path="${esc(run.summary_path' in report
    assert "load(btn.dataset.path||'')" in report
    assert '快捷键' not in report
    assert 'const RUNS = [' not in report


def test_webview_window_opens_at_full_workspace_size():
    source = (Path(__file__).resolve().parent / 'webview_app.py').read_text(encoding='utf-8')

    assert 'width=1320' in source
    assert 'height=840' in source
    assert 'min_size=(1120, 700)' in source
