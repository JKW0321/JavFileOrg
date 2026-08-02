import re
import time
from urllib.parse import unquote, urlencode, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from .base import BaseProvider, ProviderResult


class MadouQuProvider(BaseProvider):
    """Exact-code Madou metadata lookup.

    The source is only queried for an explicit Madou catalog code.  Search
    results are never trusted by themselves: the detail page must repeat the
    same code and provide a non-placeholder cover before a file can change.
    """

    name = 'madouqu'
    base_url = 'https://madouqu.com/'
    connect_timeout = 5
    read_timeout = 12
    max_detail_candidates = 5
    code_pattern = re.compile(
        r'^(MDHG|MDSR|MDL|MD|MM)[-_\s]*0*(\d{1,6})$',
        re.IGNORECASE,
    )

    @classmethod
    def _normalize_code(cls, value):
        match = cls.code_pattern.fullmatch(str(value or '').strip())
        if not match:
            return None
        width = 4 if match.group(1).upper() in {'MDHG', 'MDSR', 'MDL', 'MD'} else 3
        return f'{match.group(1).upper()}-{match.group(2).zfill(width)}'

    @staticmethod
    def _code_key(value):
        return re.sub(r'[^A-Z0-9]', '', str(value or '').upper())

    def _request(self, url, *, referer=None):
        if self.session is None:
            self.session = requests.Session()
        headers = getattr(self.session, 'headers', None)
        if headers is not None:
            headers.setdefault(
                'User-Agent',
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                'AppleWebKit/537.36 Chrome/126.0.0.0 Safari/537.36',
            )
            headers.setdefault('Accept-Language', 'zh-CN,zh;q=0.9,en;q=0.6')
        self.log(f'🔍 Madou精确查询URL: {url}', 'INFO')
        started = time.monotonic()
        try:
            response = self.session.get(
                url,
                timeout=(self.connect_timeout, self.read_timeout),
                headers={'Referer': referer or self.base_url},
            )
            response.raise_for_status()
            return response
        finally:
            self.log(
                f'⏱️ {self.name} HTTP耗时 {time.monotonic() - started:.1f}秒: {url}',
                'INFO',
            )

    @staticmethod
    def _text(value):
        return re.sub(r'\s+', ' ', str(value or '')).strip()

    @classmethod
    def _detail_links(cls, soup, search_url, expected_code):
        expected_key = cls._code_key(expected_code)
        exact = []
        other = []
        for article in soup.select('article[id^="post"]'):
            anchor = article.select_one('h2 a[href], a[rel="bookmark"][href]')
            if not anchor:
                continue
            url = urljoin(search_url, anchor.get('href') or '')
            if not url:
                continue
            context = ' '.join((
                anchor.get('title') or '',
                anchor.get_text(' ', strip=True),
                article.get_text(' ', strip=True)[:800],
            ))
            target = exact if expected_key in cls._code_key(context) else other
            if url not in target:
                target.append(url)
        return (exact + other)[:cls.max_detail_candidates]

    @staticmethod
    def _unwrap_image_url(value, detail_url):
        value = str(value or '').strip()
        if not value:
            return None
        parsed = urlparse(value)
        decoded_path = unquote(parsed.path)
        embedded = re.search(r'https?://.+$', decoded_path, re.IGNORECASE)
        if embedded:
            value = embedded.group(0)
        return urljoin(detail_url, value)

    @classmethod
    def _detail_data(cls, soup, detail_url):
        fields = {}
        article = soup.select_one('article[id^="post"]') or soup
        for paragraph in article.select('p'):
            text = cls._text(paragraph.get_text(' ', strip=True))
            match = re.match(r'^(番號|番号|片名|女郎|演員|演员)\s*[：:]\s*(.+)$', text)
            if match:
                fields[match.group(1)] = cls._text(match.group(2))
        image_url = None
        for image in article.select('p img[src], .entry-content img[src], img[data-src]'):
            candidate = image.get('data-src') or image.get('src')
            candidate = cls._unwrap_image_url(candidate, detail_url)
            lowered = str(candidate or '').lower()
            if candidate and not any(
                marker in lowered
                for marker in ('logo', 'avatar', 'banner', 'icon', '.svg')
            ):
                image_url = candidate
                break
        number = fields.get('番號') or fields.get('番号') or ''
        title = fields.get('片名') or ''
        actress = fields.get('女郎') or fields.get('演員') or fields.get('演员') or ''
        return number, title, actress, image_url

    def search(self, query):
        code = self._normalize_code(query)
        if not code:
            return ProviderResult(
                ok=False,
                provider=self.name,
                query=query,
                error_type='unsupported-query',
                message='Madou 数据源只接受 MD/MDHG/MDL/MDSR/MM 的明确编号',
            )
        search_url = self.base_url + '?' + urlencode({'s': code})
        try:
            search_response = self._request(search_url)
            soup = BeautifulSoup(search_response.content, 'html.parser')
            links = self._detail_links(soup, search_url, code)
            for detail_url in links:
                if self.should_stop():
                    return ProviderResult(
                        ok=False, provider=self.name, query=query,
                        error_type='cancelled', message='user stopped',
                    )
                response = self._request(detail_url, referer=search_url)
                detail_soup = BeautifulSoup(response.content, 'html.parser')
                number, title, actress, image_url = self._detail_data(detail_soup, detail_url)
                if self._code_key(number) != self._code_key(code):
                    continue
                if not title or not image_url:
                    continue
                display_title = f'{code} {title}'
                if actress and self._text(actress) not in display_title:
                    display_title += f' {self._text(actress)}'
                return ProviderResult(
                    ok=True,
                    title=display_title,
                    image_url=image_url,
                    provider=self.name,
                    query=query,
                    detail_url=detail_url,
                    referer=detail_url,
                    raw_meta={
                        'family': 'madou',
                        'code': code,
                        'catalog_number': number,
                        'source': 'madouqu',
                    },
                )
            return ProviderResult(
                ok=False,
                provider=self.name,
                query=query,
                referer=search_url,
                error_type='not-found',
                message='Madou 目录未找到编号、标题和封面均可核验的结果',
                raw_meta={'family': 'madou', 'code': code, 'candidate_count': len(links)},
            )
        except requests.exceptions.RequestException as exc:
            return ProviderResult(
                ok=False,
                provider=self.name,
                query=query,
                referer=search_url,
                error_type='network-error',
                message=str(exc),
                raw_meta={'family': 'madou', 'code': code},
            )
        except Exception as exc:
            return ProviderResult(
                ok=False,
                provider=self.name,
                query=query,
                referer=search_url,
                error_type='provider-error',
                message=str(exc),
                raw_meta={'family': 'madou', 'code': code},
            )
