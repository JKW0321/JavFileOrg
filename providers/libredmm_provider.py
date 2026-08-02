import time
from urllib.parse import quote

import requests

from .base import BaseProvider, ProviderResult
from .dmm_utils import (
    dmm_identity_matches,
    full_cover_url,
    normalize_standard_code,
    title_with_code,
)


class LibreDMMProvider(BaseProvider):
    name = 'libredmm'
    base_url = 'https://www.libredmm.com'
    connect_timeout = 5
    read_timeout = 15
    # LibreDMM may return 202 while it aggregates a previously uncached DMM
    # title. Four short polls are still bounded, but avoid abandoning entries
    # that become available just after the former single 0.4-second wait.
    poll_attempts = 4
    poll_interval = 0.25

    def _get_session(self):
        if self.session is None:
            self.session = requests.Session()
        headers = getattr(self.session, 'headers', None)
        if headers is not None:
            headers.setdefault(
                'User-Agent',
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                'AppleWebKit/537.36 Chrome/126.0.0.0 Safari/537.36',
            )
            headers.setdefault('Accept', 'application/json, text/plain, */*')
            headers.setdefault('Accept-Language', 'ja,en-US;q=0.8,en;q=0.6')
        return self.session

    def _sleep_before_poll(self):
        deadline = time.monotonic() + max(float(self.poll_interval), 0)
        while time.monotonic() < deadline and not self.should_stop():
            time.sleep(min(0.05, deadline - time.monotonic()))

    def search(self, query: str) -> ProviderResult:
        normalized = normalize_standard_code(query)
        if not normalized:
            return ProviderResult(
                ok=False,
                provider=self.name,
                query=query,
                error_type='unsupported-query',
                message='LibreDMM 自动模式仅处理可严格校验的标准番号',
            )
        search_url = (
            f'{self.base_url}/search?q={quote(normalized["display"])}&format=json'
        )
        current_url = search_url
        response = None
        attempts = max(int(self.poll_attempts or 1), 1)
        for attempt in range(1, attempts + 1):
            if self.should_stop():
                return ProviderResult(
                    ok=False, provider=self.name, query=query, referer=search_url,
                    detail_url=current_url, error_type='cancelled', message='user stopped',
                )
            self.log(f'🔍 搜索URL: {current_url}', 'INFO')
            started = time.monotonic()
            try:
                response = self._get_session().get(
                    current_url,
                    timeout=(self.connect_timeout, self.read_timeout),
                    headers={'Referer': f'{self.base_url}/'},
                )
            except requests.exceptions.RequestException as exc:
                return ProviderResult(
                    ok=False, provider=self.name, query=query, referer=search_url,
                    detail_url=current_url, error_type='network-error', message=str(exc),
                )
            finally:
                self.log(
                    f'⏱️ {self.name} HTTP耗时 {time.monotonic() - started:.1f}秒: {current_url}',
                    'INFO',
                )
            current_url = str(getattr(response, 'url', None) or current_url)
            if response.status_code != 202:
                break
            if attempt < attempts:
                self._sleep_before_poll()

        if response is None:
            return ProviderResult(
                ok=False, provider=self.name, query=query, referer=search_url,
                error_type='provider-error', message='LibreDMM 未返回响应',
            )
        if response.status_code == 202:
            return ProviderResult(
                ok=False, provider=self.name, query=query, referer=search_url,
                detail_url=current_url, error_type='processing-timeout',
                message='LibreDMM 仍在后台聚合，本文件继续尝试下一数据源',
            )
        if response.status_code == 404:
            return ProviderResult(
                ok=False, provider=self.name, query=query, referer=search_url,
                detail_url=current_url, error_type='not-found',
                message=f'LibreDMM 未收录 {normalized["display"]}',
            )
        if response.status_code != 200:
            return ProviderResult(
                ok=False, provider=self.name, query=query, referer=search_url,
                detail_url=current_url, error_type='server-error',
                message=f'LibreDMM HTTP {response.status_code}',
            )
        try:
            payload = response.json()
        except (ValueError, TypeError) as exc:
            return ProviderResult(
                ok=False, provider=self.name, query=query, referer=search_url,
                detail_url=current_url, error_type='parse-error', message=str(exc),
            )
        if payload.get('err'):
            return ProviderResult(
                ok=False, provider=self.name, query=query, referer=search_url,
                detail_url=current_url, error_type='provider-error',
                message=f'LibreDMM: {payload.get("err")}',
            )

        normalized_id = str(payload.get('normalized_id') or '').strip()
        content_id = str(payload.get('subtitle') or '').strip()
        if not dmm_identity_matches(query, normalized_id, content_id):
            return ProviderResult(
                ok=False,
                provider=self.name,
                query=query,
                referer=search_url,
                detail_url=current_url,
                error_type='code-mismatch',
                message=(
                    f'LibreDMM 返回标识 {normalized_id or content_id or "-"} 与 '
                    f'{normalized["display"]} 不一致，已拒绝模糊结果'
                ),
                raw_meta={'normalized_id': normalized_id, 'content_id': content_id},
            )
        image_url = full_cover_url(payload.get('cover_image_url'))
        if not image_url:
            return ProviderResult(
                ok=False, provider=self.name, query=query, referer=search_url,
                detail_url=current_url, error_type='invalid-result',
                message='LibreDMM 未返回可用的完整大封面',
                raw_meta={'normalized_id': normalized_id, 'content_id': content_id},
            )
        return ProviderResult(
            ok=True,
            title=title_with_code(query, payload.get('title')),
            image_url=image_url,
            provider=self.name,
            query=query,
            detail_url=current_url,
            referer=search_url,
            raw_meta={
                'normalized_id': normalized_id,
                'content_id': content_id,
                'source_url': payload.get('url'),
                'date': payload.get('date'),
                'makers': payload.get('makers') or [],
                'labels': payload.get('labels') or [],
                'actresses': payload.get('actresses') or [],
            },
        )
