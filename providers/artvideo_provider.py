import re
import time
import unicodedata
from difflib import SequenceMatcher
from urllib.parse import quote, urlencode, urljoin

import requests
from bs4 import BeautifulSoup

from .base import BaseProvider, ProviderResult


class ArtVideoProvider(BaseProvider):
    """Strict legacy ART VIDEO lookup backed by a live Japanese VHS catalog."""

    name = 'artvideo'
    base_url = 'https://pureadult.co.jp'
    search_path = '/user_data/sp_search_result.php'
    connect_timeout = 6
    read_timeout = 18
    max_detail_candidates = 6

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
            headers.setdefault('Accept-Language', 'ja,en-US;q=0.8,en;q=0.6')
        return self.session

    def _request(self, url, *, referer=None):
        self.log(f'🔍 ART旧片目录URL: {url}', 'INFO')
        started = time.monotonic()
        try:
            response = self._get_session().get(
                url,
                timeout=(self.connect_timeout, self.read_timeout),
                headers={'Referer': referer or f'{self.base_url}/'},
            )
            response.raise_for_status()
            return response
        finally:
            self.log(
                f'⏱️ {self.name} HTTP耗时 {time.monotonic() - started:.1f}秒: {url}',
                'INFO',
            )

    @staticmethod
    def _normalize_spaces(value):
        return re.sub(r'\s+', ' ', unicodedata.normalize('NFKC', str(value or ''))).strip()

    @classmethod
    def _compact(cls, value):
        return re.sub(r'[^0-9A-Za-z\u3040-\u30ff\u3400-\u9fff]+', '', cls._normalize_spaces(value)).casefold()

    @classmethod
    def _clean_title_hint(cls, value):
        value = cls._normalize_spaces(value)
        value = re.sub(
            r'(?<![A-Za-z0-9])(?:ART\s*VIDEO|アート\s*ビデオ)(?![A-Za-z0-9])',
            ' ',
            value,
            flags=re.IGNORECASE,
        )
        return re.sub(r'\s+', ' ', value).strip(' ._-')

    @classmethod
    def _search_terms(cls, title_hint):
        """Return conservative PureAdult keyword fallbacks for legacy names.

        Full filenames often contain an English translation, year and actor
        after the Japanese catalog title.  PureAdult search is much more
        reliable with the Japanese title phrase, but the final detail page is
        still verified separately for maker and title similarity.
        """
        cleaned = cls._clean_title_hint(title_hint)
        terms = []

        def add(value):
            value = cls._normalize_spaces(value).strip(' ._-')
            if len(cls._compact(value)) >= 3 and value not in terms:
                terms.append(value)

        add(cleaned)
        without_parentheses = re.sub(r'[（(][^（）()]*[）)]', ' ', cleaned)
        without_parentheses = re.sub(r'\s+', ' ', without_parentheses).strip()
        add(without_parentheses)

        # Drop a leading ASCII translation when a Japanese title follows it.
        japanese_start = re.search(r'[\u3040-\u30ff\u3400-\u9fff]', without_parentheses)
        japanese_text = without_parentheses[japanese_start.start():] if japanese_start else without_parentheses
        japanese_text = re.split(r'\s+-\s+', japanese_text, maxsplit=1)[0].strip()
        add(japanese_text)

        tokens = japanese_text.split()
        if len(tokens) >= 2:
            add(' '.join(tokens[:2]))
        if tokens:
            add(tokens[0])
        return terms[:5]

    @classmethod
    def _title_variants(cls, value):
        cleaned = cls._clean_title_hint(value)
        variants = [cleaned]
        no_parentheses = re.sub(r'[（(][^（）()]*[）)]', ' ', cleaned)
        no_parentheses = re.sub(r'\s+', ' ', no_parentheses).strip()
        variants.append(no_parentheses)
        japanese_start = re.search(r'[\u3040-\u30ff\u3400-\u9fff]', no_parentheses)
        if japanese_start:
            variants.append(no_parentheses[japanese_start.start():].split(' - ', 1)[0].strip())
        return [item for item in dict.fromkeys(variants) if item]

    @classmethod
    def _explicit_installment_numbers(cls, value):
        """Return unmistakable series installment numbers.

        Shared series text can otherwise make ``No.11`` look highly similar
        to ``No.28``.  Only explicit labels are compared here so ordinary
        years, actress names and catalog numbers do not create false rejects.
        """
        normalized = cls._normalize_spaces(value)
        matches = re.findall(
            r'(?<![A-Za-z0-9])(?:NO\.?|VOL\.?|VOLUME|PART|第)\s*0*(\d{1,4})',
            normalized,
            re.IGNORECASE,
        )
        return {int(number) for number in matches}

    @classmethod
    def _parse_query(cls, query):
        normalized = cls._normalize_spaces(query)
        match = re.match(r'^ART\s*VIDEO\s+(?:(\d{3,6})\s*)?(.*)$', normalized, re.IGNORECASE)
        if not match:
            return None
        legacy_number = match.group(1)
        title_hint = match.group(2).strip(' ._-')
        return {'legacy_number': legacy_number, 'title_hint': title_hint}

    @classmethod
    def _title_matches(cls, hint, candidate):
        hint_installments = cls._explicit_installment_numbers(hint)
        candidate_installments = cls._explicit_installment_numbers(candidate)
        if (
            hint_installments
            and candidate_installments
            and hint_installments.isdisjoint(candidate_installments)
        ):
            return False
        candidate_key = cls._compact(candidate)
        if not candidate_key:
            return False
        for variant in cls._title_variants(hint):
            hint_key = cls._compact(variant)
            if not hint_key:
                continue
            if hint_key == candidate_key:
                return True
            shorter = min(len(hint_key), len(candidate_key))
            longer = max(len(hint_key), len(candidate_key))
            if (
                (candidate_key in hint_key or hint_key in candidate_key)
                and shorter >= 4
                and shorter / longer >= 0.45
            ):
                return True
            if SequenceMatcher(None, hint_key, candidate_key).ratio() >= 0.58:
                return True
        return False

    @classmethod
    def _maker_is_art_video(cls, maker):
        compact = re.sub(r'[^A-Z]', '', cls._normalize_spaces(maker).upper())
        return compact == 'ARTVIDEO'

    @staticmethod
    def _detail_links(soup, search_url):
        links = []
        for anchor in soup.select('a[href*="sp_artist_product_detail.php"]'):
            url = urljoin(search_url, anchor.get('href') or '')
            if url and url not in links:
                links.append(url)
        return links

    @classmethod
    def _detail_fields(cls, soup):
        fields = {}
        for row in soup.select('table.prd_detail_box tr'):
            cells = row.find_all('td')
            if len(cells) < 2:
                continue
            label = cls._normalize_spaces(cells[0].get_text(' ', strip=True))
            value = cls._normalize_spaces(cells[1].get_text(' ', strip=True))
            if label and value:
                fields[label] = value
        return fields

    @staticmethod
    def _detail_image(soup, detail_url):
        for selector, attribute in (
            ('a.example-image-link[href*="/sp_images/gazou/"]', 'href'),
            ('img[src*="/sp_images/gazou/"]', 'src'),
        ):
            element = soup.select_one(selector)
            value = element.get(attribute) if element else None
            if value:
                return urljoin(detail_url, value)
        return None

    def search(self, query):
        context = self._parse_query(query)
        if not context:
            return ProviderResult(
                ok=False, provider=self.name, query=query,
                error_type='unsupported-query',
                message='ART Video 数据源只接受由直属 ART 目录识别出的查询',
            )
        title_hint = context['title_hint']
        if len(self._compact(title_hint)) < 3:
            return ProviderResult(
                ok=False, provider=self.name, query=query,
                error_type='insufficient-context',
                message=(
                    '仅有 ART 旧站数字编号，当前在线目录无法安全反查标题；'
                    '未使用本地图片，也未修改源文件'
                ),
                raw_meta=context,
            )

        try:
            seen_details = set()
            last_search_url = None
            candidate_count = 0
            for search_term in self._search_terms(title_hint):
                search_url = f'{self.base_url}{self.search_path}?' + urlencode(
                    {'km': '2', 'kw': search_term}, quote_via=quote
                )
                last_search_url = search_url
                search_response = self._request(search_url)
                search_soup = BeautifulSoup(search_response.content, 'html.parser')
                links = self._detail_links(search_soup, search_url)
                candidate_count += len(links)
                for detail_url in links[:self.max_detail_candidates]:
                    if detail_url in seen_details:
                        continue
                    seen_details.add(detail_url)
                    if self.should_stop():
                        return ProviderResult(
                            ok=False, provider=self.name, query=query,
                            error_type='cancelled', message='user stopped',
                        )
                    detail_response = self._request(detail_url, referer=search_url)
                    soup = BeautifulSoup(detail_response.content, 'html.parser')
                    fields = self._detail_fields(soup)
                    title = fields.get('タイトル') or ''
                    maker = fields.get('メーカー') or ''
                    if not self._maker_is_art_video(maker):
                        continue
                    if not self._title_matches(title_hint, title):
                        continue
                    image_url = self._detail_image(soup, detail_url)
                    if not image_url:
                        continue
                    actress = fields.get('AV女優') or ''
                    display_title = title
                    if actress and self._compact(actress) not in self._compact(display_title):
                        display_title = f'{display_title} {actress}'
                    if context.get('legacy_number'):
                        display_title = f'ART-{context["legacy_number"]} {display_title}'
                    return ProviderResult(
                        ok=True,
                        title=display_title,
                        image_url=image_url,
                        provider=self.name,
                        query=query,
                        detail_url=detail_url,
                        referer=search_url,
                        raw_meta={
                            **context,
                            'maker': maker,
                            'catalog_product_code': fields.get('商品コード'),
                            'actress': actress,
                            'source': 'pureadult',
                            'search_term': search_term,
                        },
                    )
            return ProviderResult(
                ok=False, provider=self.name, query=query,
                referer=last_search_url,
                error_type='not-found',
                message='旧片目录未找到厂牌和标题均严格匹配的 ART VIDEO 商品',
                raw_meta={**context, 'candidate_count': candidate_count},
            )
        except requests.exceptions.RequestException as exc:
            return ProviderResult(
                ok=False, provider=self.name, query=query,
                referer=locals().get('last_search_url'),
                error_type='network-error', message=str(exc),
                raw_meta=context,
            )
        except Exception as exc:
            return ProviderResult(
                ok=False, provider=self.name, query=query,
                referer=locals().get('last_search_url'),
                error_type='provider-error', message=str(exc),
                raw_meta=context,
            )
