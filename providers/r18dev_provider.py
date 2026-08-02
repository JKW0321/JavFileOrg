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


class R18DevProvider(BaseProvider):
    name = 'r18dev'
    base_url = 'https://r18.dev'
    connect_timeout = 5
    read_timeout = 12
    minimum_request_interval = 0.25

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._last_request_at = 0.0

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
            headers.setdefault('Referer', f'{self.base_url}/')
        return self.session

    def _rate_limit(self):
        remaining = self.minimum_request_interval - (time.monotonic() - self._last_request_at)
        while remaining > 0 and not self.should_stop():
            time.sleep(min(remaining, 0.05))
            remaining = self.minimum_request_interval - (time.monotonic() - self._last_request_at)

    def search(self, query: str) -> ProviderResult:
        normalized = normalize_standard_code(query)
        if not normalized:
            return ProviderResult(
                ok=False,
                provider=self.name,
                query=query,
                error_type='unsupported-query',
                message='R18.dev 仅安全处理可严格校验的标准番号',
            )
        detail_url = (
            f'{self.base_url}/videos/vod/movies/detail/-/'
            f'dvd_id={quote(normalized["compact"])}/json'
        )
        if self.should_stop():
            return ProviderResult(
                ok=False,
                provider=self.name,
                query=query,
                detail_url=detail_url,
                referer=f'{self.base_url}/',
                error_type='cancelled',
                message='user stopped',
            )

        self._rate_limit()
        if self.should_stop():
            return ProviderResult(
                ok=False,
                provider=self.name,
                query=query,
                detail_url=detail_url,
                referer=f'{self.base_url}/',
                error_type='cancelled',
                message='user stopped',
            )
        self.log(f'🔍 搜索URL: {detail_url}', 'INFO')
        started = time.monotonic()
        try:
            response = self._get_session().get(
                detail_url,
                timeout=(self.connect_timeout, self.read_timeout),
                headers={'Referer': f'{self.base_url}/'},
            )
            self._last_request_at = time.monotonic()
        except requests.exceptions.RequestException as exc:
            return ProviderResult(
                ok=False,
                provider=self.name,
                query=query,
                detail_url=detail_url,
                referer=f'{self.base_url}/',
                error_type='network-error',
                message=str(exc),
            )
        finally:
            self.log(
                f'⏱️ {self.name} HTTP耗时 {time.monotonic() - started:.1f}秒: {detail_url}',
                'INFO',
            )

        if response.status_code == 404:
            return ProviderResult(
                ok=False, provider=self.name, query=query, detail_url=detail_url,
                referer=f'{self.base_url}/', error_type='not-found',
                message=f'R18.dev 未收录 {normalized["display"]}',
            )
        if response.status_code == 429:
            return ProviderResult(
                ok=False, provider=self.name, query=query, detail_url=detail_url,
                referer=f'{self.base_url}/', error_type='rate-limited',
                message='R18.dev 请求频率受限，本文件继续尝试下一数据源',
            )
        if response.status_code != 200:
            return ProviderResult(
                ok=False, provider=self.name, query=query, detail_url=detail_url,
                referer=f'{self.base_url}/', error_type='server-error',
                message=f'R18.dev HTTP {response.status_code}',
            )
        try:
            payload = response.json()
        except (ValueError, TypeError) as exc:
            return ProviderResult(
                ok=False, provider=self.name, query=query, detail_url=detail_url,
                referer=f'{self.base_url}/', error_type='parse-error', message=str(exc),
            )

        content_id = str(payload.get('content_id') or '').strip()
        dvd_id = str(payload.get('dvd_id') or '').strip()
        if not dmm_identity_matches(query, dvd_id, content_id):
            return ProviderResult(
                ok=False,
                provider=self.name,
                query=query,
                detail_url=detail_url,
                referer=f'{self.base_url}/',
                error_type='code-mismatch',
                message=(
                    f'R18.dev 返回标识 {dvd_id or content_id or "-"} 与 '
                    f'{normalized["display"]} 不一致，已拒绝模糊结果'
                ),
                raw_meta={'content_id': content_id, 'dvd_id': dvd_id},
            )
        images = payload.get('images') or {}
        jacket = images.get('jacket_image') or {}
        image_url = full_cover_url(jacket.get('large2')) or full_cover_url(jacket.get('large'))
        if not image_url:
            return ProviderResult(
                ok=False, provider=self.name, query=query, detail_url=detail_url,
                referer=f'{self.base_url}/', error_type='invalid-result',
                message='R18.dev 未返回可用的完整大封面',
                raw_meta={'content_id': content_id, 'dvd_id': dvd_id},
            )
        return ProviderResult(
            ok=True,
            title=title_with_code(query, payload.get('title')),
            image_url=image_url,
            provider=self.name,
            query=query,
            detail_url=detail_url,
            referer=f'{self.base_url}/',
            raw_meta={
                'content_id': content_id,
                'dvd_id': dvd_id,
                'release_date': payload.get('release_date'),
                'runtime_minutes': payload.get('runtime_minutes'),
                'maker': (payload.get('maker') or {}).get('name'),
                'label': (payload.get('label') or {}).get('name'),
            },
        )
