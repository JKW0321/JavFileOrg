import re
import time
from urllib.parse import quote_plus, urljoin

import requests
from bs4 import BeautifulSoup

from .base import BaseProvider, ProviderResult


class UncensoredProvider(BaseProvider):
    name = 'uncensored'

    OFFICIAL_PAGE_FAMILIES = {
        '1pondo': {
            'display_prefix': '1PONDO',
            'domain': 'https://www.1pondo.tv',
            'path_template': '/movies/{code_underscore}/',
            'json_template': '/dyn/phpauto/movie_details/movie_id/{code_underscore}.json',
            'image_templates': (
                '/assets/sample/{code_underscore}/str.jpg',
                '/assets/sample/{code_underscore}/l_l.jpg',
            ),
            'part_width': 3,
            'prefixes': ('1PONDO', '1PON'),
        },
        '10musume': {
            'display_prefix': '10MUSUME',
            'domain': 'https://www.10musume.com',
            'path_template': '/movies/{code_underscore}/',
            'json_template': '/dyn/phpauto/movie_details/movie_id/{code_underscore}.json',
            'image_templates': (
                '/moviepages/{code_underscore}/images/str.jpg',
                '/assets/sample/{code_underscore}/str.jpg',
            ),
            'part_width': 2,
            'prefixes': ('10MUSUME',),
        },
        'pacopacomama': {
            'display_prefix': 'PACOPACOMAMA',
            'domain': 'https://www.pacopacomama.com',
            'path_template': '/movies/{code_underscore}/',
            'json_template': '/dyn/phpauto/movie_details/movie_id/{code_underscore}.json',
            'image_templates': (
                '/moviepages/{code_underscore}/images/l_hd.jpg',
                '/moviepages/{code_underscore}/images/l.jpg',
                '/assets/sample/{code_underscore}/l_hd.jpg',
            ),
            'part_width': 3,
            'prefixes': ('PACOPACOMAMA', 'PACOPACOM'),
        },
    }

    URABUKKAKE_TOUR_PAGES = 12

    UNSUPPORTED_FAMILY_PATTERNS = (
        ('night24-dms', re.compile(r'\b(?:DMS[-_\s]*)?NIGHT24[-_\s]*[A-Z]?\d+\b|^DMS[-_\s]*NIGHT24[-_\s]*[A-Z]?\d+\b', re.IGNORECASE)),
        ('s-cute', re.compile(r'\bS[-_]?CUTE[-_\s]*\d+\b', re.IGNORECASE)),
        ('mesubuta', re.compile(r'\bMESUBUTA[-_\s]*\d{6}[-_\s]*\d{3}\b', re.IGNORECASE)),
        ('madou', re.compile(r'\bMM[-_\s]*\d+\b|麻豆|MADOU', re.IGNORECASE)),
        ('number-name-series', re.compile(r'^\d{2,4}[-_\s]+[A-Z][A-Z]+', re.IGNORECASE)),
    )

    UNSUPPORTED_FAMILY_MESSAGES = {
        'night24-dms': 'DMS Night24 recognized, but no verified public cover/detail source is configured yet',
        's-cute': 'S-Cute recognized, but the official old site ended service and no stable cover source is configured yet',
        'mesubuta': 'Mesubuta recognized, but the known official domain is unavailable and no stable cover source is configured yet',
        'madou': 'Madou recognized, but no verified public cover/detail source is configured yet',
        'number-name-series': 'filename pattern recognized, but the source family is ambiguous and needs manual review',
    }

    MGSTAGE_PREFIXES = (
        '300MIUM', '393OTIM', '420HPT', '420STH', '546EROFV', '583ERKR',
        '328CNSTV', '476MLA', '253KAKU',
    )

    def _request(self, url):
        session = self.session
        if session is None:
            session = requests.Session()
            session.headers.update({
                'User-Agent': (
                    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                    'AppleWebKit/537.36 (KHTML, like Gecko) '
                    'Chrome/126.0.0.0 Safari/537.36'
                ),
                'Accept-Language': 'ja,en-US;q=0.9,en;q=0.8',
            })
            self.session = session
        started = time.monotonic()
        try:
            response = session.get(url, timeout=(5, 10))
            response.raise_for_status()
            return response
        finally:
            elapsed = time.monotonic() - started
            self.log(f'⏱️ uncensored HTTP耗时 {elapsed:.1f}秒: {url}', 'INFO')

    def _normalize_query(self, query):
        raw = (query or '').strip()
        compact = re.sub(r'[._\s]+', '-', raw.upper())

        for family, config in self.OFFICIAL_PAGE_FAMILIES.items():
            prefixes = '|'.join(re.escape(prefix) for prefix in config['prefixes'])
            match = re.search(rf'\b(?:{prefixes})-?(\d{{6}})-(\d{{1,5}})\b', compact)
            if match:
                return self._official_page_meta(family, match.group(1), match.group(2))

        match = re.search(r'\b(?:CARIB|CARIBBEANCOM)-?(\d{6})-(\d{2,5})\b', compact)
        if match:
            code = f'{match.group(1)}-{match.group(2)}'
            return {
                'family': 'caribbeancom',
                'supported': True,
                'code': code,
                'display_code': f'CARIB-{code}',
                'detail_url': f'https://www.caribbeancom.com/moviepages/{code}/index.html',
                'image_candidates': [
                    f'https://www.caribbeancom.com/moviepages/{code}/images/l_l.jpg',
                    f'https://www.caribbeancom.com/moviepages/{code}/images/str.jpg',
                ],
            }

        match = re.search(r'\b(\d{6})-(\d{2,5})-(?:CARIB|CARIBBEANCOM)\b', compact)
        if match:
            code = f'{match.group(1)}-{match.group(2)}'
            return {
                'family': 'caribbeancom',
                'supported': True,
                'code': code,
                'display_code': f'CARIB-{code}',
                'detail_url': f'https://www.caribbeancom.com/moviepages/{code}/index.html',
                'image_candidates': [
                    f'https://www.caribbeancom.com/moviepages/{code}/images/l_l.jpg',
                    f'https://www.caribbeancom.com/moviepages/{code}/images/str.jpg',
                ],
            }

        match = re.search(r'\bFC2[-_\s]*(?:PPV[-_\s]*)?(\d{5,8})\b', compact)
        if match:
            item_id = match.group(1)
            return {
                'family': 'fc2-ppv',
                'supported': True,
                'code': item_id,
                'display_code': f'FC2-PPV-{item_id}',
                'detail_url': f'https://adult.contents.fc2.com/article/{item_id}/',
                'image_candidates': [],
            }

        match = re.search(r'\bHEYZO(?:[-_\s]*HD)?[-_\s]*(\d{3,6})\b', compact)
        if match:
            item_id = match.group(1)
            return {
                'family': 'heyzo',
                'supported': True,
                'code': item_id,
                'display_code': f'HEYZO-{item_id}',
                'detail_url': f'https://www.heyzo.com/moviepages/{item_id}/index.html',
                'image_candidates': [
                    f'https://www.heyzo.com/contents/3000/{item_id}/images/player_thumbnail.jpg',
                    f'https://www.heyzo.com/contents/3000/{item_id}/images/thumbnail.jpg',
                ],
            }

        match = re.search(r'\b(?:HEYDOUGA|HEY)[-_\s]*4030[-_\s]*(?:PPV[-_\s]*)?(\d{3,6})\b', compact)
        if match:
            item_id = match.group(1)
            return {
                'family': 'heydouga',
                'supported': True,
                'code': item_id,
                'display_code': f'HEYDOUGA-4030-{item_id}',
                'detail_url': f'https://www.heydouga.com/moviepages/4030/{item_id}/index.html',
                'image_candidates': [
                    f'https://www.heydouga.com/contents/4030/{item_id}/player_thumb.jpg',
                    f'https://www.heydouga.com/contents/4030/{item_id}/player_thumb.webp',
                ],
            }

        match = re.search(r'\b(?:TOKYO[-_\s]*HOT|TOKYOHOT)[-_\s]*([A-Z]\d{3,6})\b', compact)
        if match:
            code = match.group(1).lower()
            display_code = f'TOKYO-HOT-{code.upper()}'
            return {
                'family': 'tokyo-hot',
                'supported': True,
                'code': code,
                'display_code': display_code,
                'detail_url': f'https://my.tokyo-hot.com/product/?q={code}',
                'image_candidates': [],
            }

        mgstage_prefixes = '|'.join(re.escape(prefix) for prefix in self.MGSTAGE_PREFIXES)
        match = re.search(rf'\b({mgstage_prefixes})[-_\s]*(\d{{2,6}}[A-Z]?)\b', compact)
        if match:
            code = f'{match.group(1).upper()}-{match.group(2).upper()}'
            prefix = match.group(1).lower()
            number = match.group(2).lower()
            return {
                'family': 'mgstage',
                'supported': True,
                'code': code,
                'display_code': code,
                'detail_url': f'https://www.mgstage.com/product/product_detail/{code}/',
                'image_candidates': [
                    f'https://image.mgstage.com/images/{prefix}/{number}/pb_e_{code.lower()}.jpg',
                    f'https://image.mgstage.com/images/{prefix}/{number}/pf_o1_{code.lower()}.jpg',
                ],
            }

        match = re.search(
            r'\bJAPANHDV[-_\s]*(?:(\d{6})|(\d{2})[-_\s]*(\d{2})[-_\s]*(\d{2}))(?:[-_\s]+([A-Z0-9][A-Z0-9-]*))?\b',
            compact,
        )
        if match:
            date_part = match.group(1) or f'{match.group(2)}{match.group(3)}{match.group(4)}'
            search_slug = (match.group(5) or '').strip('-')
            search_terms = self._search_terms_from_slug(search_slug)
            return {
                'family': 'japanhdv',
                'supported': bool(search_terms),
                'code': f'JAPANHDV-{date_part}' + (f'-{search_slug.lower()}' if search_slug else ''),
                'display_code': f'JAPANHDV-{date_part}',
                'detail_url': f'http://japanhdv.com/?s={quote_plus(" ".join(search_terms))}' if search_terms else '',
                'image_candidates': [],
                'search_terms': search_terms,
            }

        match = re.search(r'\bURABUKKAKE[-_\s]*(\d{1,5})(?:[-_\s]+([A-Z][A-Z0-9-]*))?\b', compact)
        if match:
            item_id = match.group(1)
            search_slug = (match.group(2) or '').strip('-')
            search_terms = self._search_terms_from_slug(search_slug)
            return {
                'family': 'urabukkake',
                'supported': bool(search_terms),
                'code': f'URABUKKAKE-{item_id}' + (f'-{search_slug.lower()}' if search_slug else ''),
                'display_code': f'URABUKKAKE-{item_id}',
                'detail_url': 'https://www.urabukkake.com/en/tour',
                'image_candidates': [],
                'search_terms': search_terms,
            }

        for family, pattern in self.UNSUPPORTED_FAMILY_PATTERNS:
            if pattern.search(raw) or pattern.search(compact):
                return {
                    'family': family,
                    'supported': False,
                    'code': raw.replace('_', '-').lower(),
                    'display_code': raw,
                    'detail_url': '',
                    'image_candidates': [],
                }

        normalized = raw.replace('_', '-').lower()
        return {
            'family': None,
            'supported': False,
            'code': normalized,
            'display_code': raw,
            'detail_url': '',
            'image_candidates': [],
        }

    def _official_page_meta(self, family, date_part, item_part):
        config = self.OFFICIAL_PAGE_FAMILIES[family]
        normalized_part = item_part.zfill(config.get('part_width') or len(item_part))
        code_underscore = f'{date_part}_{normalized_part}'
        code_dash = f'{date_part}-{normalized_part}'
        detail_url = config['domain'] + config['path_template'].format(
            code_underscore=code_underscore,
            code_dash=code_dash,
        )
        image_candidates = [
            config['domain'] + template.format(code_underscore=code_underscore, code_dash=code_dash)
            for template in config['image_templates']
        ]
        json_url = config.get('json_template')
        if json_url:
            json_url = config['domain'] + json_url.format(code_underscore=code_underscore, code_dash=code_dash)
        return {
            'family': family,
            'supported': True,
            'code': code_underscore,
            'display_code': f"{config['display_prefix']}-{code_dash}",
            'detail_url': detail_url,
            'json_url': json_url,
            'image_candidates': image_candidates,
        }

    def _blocked_page_failure(self, soup):
        title = ''
        title_element = soup.find('title')
        if title_element:
            title = title_element.get_text(' ', strip=True).lower()
        html_text = str(soup).lower()
        if (
            'just a moment' in title
            or 'cf_chl' in html_text
            or 'challenge-platform' in html_text
            or 'enable javascript and cookies' in html_text
        ):
            return 'verification-required', 'uncensored source returned verification page'
        return None

    def _clean_title(self, title, meta):
        title = (title or '').strip()
        for suffix in (
            ' - Caribbeancom',
            ' | Caribbeancom',
            ' - 1Pondo',
            ' | 1Pondo',
            ' | 1pondo.tv',
            ' - 1pondo.tv',
            ' - 10Musume',
            ' | 10Musume',
            ' | 10musume.com',
            ' - 10musume.com',
            ' - Pacopacomama',
            ' | Pacopacomama',
            ' | pacopacomama.com',
            ' - pacopacomama.com',
            ' | FC2コンテンツマーケット',
            ' | FC2 Contents Market',
            ' - FC2コンテンツマーケット',
            ' - FC2 Contents Market',
            ' - HEYZO',
            ' | HEYZO',
            ' - Tokyo-Hot',
            ' | Tokyo-Hot',
            ' - TOKYO-HOT',
            ' | TOKYO-HOT',
            ' - MGStage',
            ' | MGStage',
            ' - MGS動画',
            ' | MGS動画',
        ):
            if title.endswith(suffix):
                title = title[:-len(suffix)].strip()
        display_code = meta.get('display_code') or ''
        if title and display_code and display_code.lower() not in title.lower():
            return f'{display_code} {title}'
        return title or display_code

    def _select_image(self, soup, detail_url, image_candidates, meta=None):
        for selector in (
            'meta[property="og:image"]',
            'meta[name="twitter:image"]',
        ):
            element = soup.select_one(selector)
            content = element.get('content') if element else ''
            if content and not self._is_placeholder_image(content):
                return urljoin(detail_url, content)

        if image_candidates:
            return image_candidates[0]

        for img in soup.find_all('img'):
            src = (
                img.get('data-src')
                or img.get('data-lazy-src')
                or img.get('data-original')
                or img.get('data-url')
                or img.get('src')
                or ''
            )
            if not src:
                srcset = img.get('srcset') or img.get('data-srcset') or ''
                if srcset:
                    src = srcset.split(',')[-1].strip().split()[0]
            if not src:
                continue
            src_lower = src.lower()
            if self._is_placeholder_image(src):
                continue
            cls = ' '.join(img.get('class', [])).lower()
            if 'gallery-image' in cls:
                return urljoin(detail_url, src)
            if any(marker in src_lower for marker in ('/sample/', '/moviepages/', '/file/', 'l_l', 'l_hd', 'str', 'poster', 'cover')):
                return urljoin(detail_url, src)

        if meta and meta.get('family') == 'fc2-ppv':
            fc2_image = self._extract_fc2_storage_image(str(soup), detail_url)
            if fc2_image:
                return fc2_image

        return None

    def _extract_fc2_storage_image(self, html_text, detail_url):
        if not html_text:
            return None
        unescaped = (
            html_text
            .replace('\\/', '/')
            .replace('&amp;', '&')
            .replace('\\u002F', '/')
        )
        patterns = (
            r'https?://storage\d+\.contents\.fc2\.com/file/[^"\'<>\s\\]+?\.(?:jpg|jpeg|png)',
            r'//storage\d+\.contents\.fc2\.com/file/[^"\'<>\s\\]+?\.(?:jpg|jpeg|png)',
        )
        for pattern in patterns:
            match = re.search(pattern, unescaped, re.IGNORECASE)
            if match:
                return urljoin(detail_url, match.group(0))
        return None

    def _is_placeholder_image(self, image_url):
        image_lower = (image_url or '').lower()
        return any(marker in image_lower for marker in (
            'logo',
            'header',
            'banner',
            'sprite',
            'icon',
            'avatar',
            '.svg',
        ))

    def _fetch_json_detail(self, meta):
        json_url = meta.get('json_url')
        if not json_url:
            return None
        response = self._request(json_url)
        data = response.json()
        title = data.get('Title') or data.get('TitleEn')
        image_url = (
            data.get('ThumbUltra')
            or data.get('ThumbHigh')
            or data.get('MovieThumb')
            or data.get('ThumbMed')
            or data.get('ThumbLow')
        )
        return {
            'title': self._clean_title(title, meta),
            'image_url': image_url,
            'raw': data,
        }

    def _search_terms_from_slug(self, slug):
        if not slug:
            return []
        spaced = re.sub(r'([a-z])([A-Z])', r'\1 \2', str(slug))
        spaced = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1 \2', spaced)
        words = re.findall(r'[A-Za-z0-9]+', spaced.lower())
        return [
            word
            for word in words
            if len(word) > 1 and word not in {'hd', 'fhd', 'uhd', 'mp4', 'avi', 'wmv', 'mkv'}
        ]

    def _score_terms(self, search_terms, text):
        words = self._search_terms_from_slug(text)
        if not search_terms or not words:
            return 0
        word_set = set(words)
        joined_words = ''.join(words)
        score = 0
        for term in search_terms:
            if term in word_set or term in joined_words:
                score += 2
                continue
            parts = self._split_compound_term(term)
            if len(parts) > 1 and all(part in word_set for part in parts):
                score += len(parts)
        return score

    def _split_compound_term(self, term):
        if not term:
            return []
        parts = re.findall(r'[a-z]+|\d+', term.lower())
        if len(parts) > 1:
            return [part for part in parts if len(part) > 1]
        common_suffixes = (
            'ass', 'pussy', 'gokkun', 'bukkake', 'creampie', 'whore',
            'cum', 'slut', 'girl', 'schoolgirl', 'facial',
        )
        for suffix in common_suffixes:
            if term.endswith(suffix) and len(term) > len(suffix) + 1:
                return [term[:-len(suffix)], suffix]
        return [term]

    def _search_japanhdv(self, meta, query):
        detail_url = meta.get('detail_url')
        response = self._request(detail_url)
        soup = BeautifulSoup(response.content, 'html.parser')
        blocked_failure = self._blocked_page_failure(soup)
        if blocked_failure:
            error_type, message = blocked_failure
            return ProviderResult(
                ok=False,
                provider=self.name,
                query=query,
                detail_url=detail_url,
                referer=detail_url,
                error_type=error_type,
                message=message,
                raw_meta={'family': meta.get('family'), 'code': meta.get('code')},
            )
        search_terms = meta.get('search_terms') or []
        candidates = []
        for link in soup.select('a.video-thumb-prev[href], a[href]'):
            image_element = link.select_one('img')
            title = (
                link.get('title')
                or (image_element.get('alt') if image_element else '')
            )
            if not title:
                heading = link.find_next('h3', class_='title_desc')
                title = heading.get_text(' ', strip=True) if heading else ''
            image_url = ''
            if image_element:
                image_url = (
                    image_element.get('data-src')
                    or image_element.get('data-original')
                    or image_element.get('src')
                    or ''
                )
            if not title or not image_url or self._is_placeholder_image(image_url):
                continue
            score = self._score_terms(search_terms, title)
            if score <= 0:
                continue
            candidates.append({
                'score': score,
                'title': title,
                'image_url': urljoin(detail_url, image_url),
                'detail_url': urljoin(detail_url, link.get('href')),
            })
        if not candidates:
            return ProviderResult(
                ok=False,
                provider=self.name,
                query=query,
                detail_url=detail_url,
                referer=detail_url,
                error_type='not-found',
                message='japanhdv search results did not match filename terms',
                raw_meta={'family': meta.get('family'), 'code': meta.get('code')},
            )
        best = max(candidates, key=lambda item: item['score'])
        return ProviderResult(
            ok=True,
            title=self._clean_title(best['title'], meta),
            image_url=best['image_url'],
            provider=self.name,
            query=query,
            detail_url=best['detail_url'],
            referer=detail_url,
            raw_meta={'family': meta.get('family'), 'code': meta.get('code')},
        )

    def _search_urabukkake(self, meta, query):
        base_url = meta.get('detail_url') or 'https://www.urabukkake.com/en/tour'
        search_terms = meta.get('search_terms') or []
        if not search_terms:
            return ProviderResult(
                ok=False,
                provider=self.name,
                query=query,
                detail_url=base_url,
                referer=base_url,
                error_type='invalid-query',
                message='urabukkake filename lacks title words needed for tour-page matching',
                raw_meta={'family': meta.get('family'), 'code': meta.get('code')},
            )
        best = None
        for page in range(1, self.URABUKKAKE_TOUR_PAGES + 1):
            if self.should_stop():
                return ProviderResult(
                    ok=False,
                    provider=self.name,
                    query=query,
                    detail_url=base_url,
                    referer=base_url,
                    error_type='cancelled',
                    message='user stopped during urabukkake tour scan',
                    raw_meta={'family': meta.get('family'), 'code': meta.get('code')},
                )
            page_url = f'{base_url}?page={page}'
            response = self._request(page_url)
            soup = BeautifulSoup(response.content, 'html.parser')
            blocked_failure = self._blocked_page_failure(soup)
            if blocked_failure:
                error_type, message = blocked_failure
                return ProviderResult(
                    ok=False,
                    provider=self.name,
                    query=query,
                    detail_url=page_url,
                    referer=base_url,
                    error_type=error_type,
                    message=message,
                    raw_meta={'family': meta.get('family'), 'code': meta.get('code')},
                )
            for section in self._iter_urabukkake_sections(soup, page_url):
                score = self._score_terms(search_terms, section.get('title', ''))
                if score <= 0:
                    continue
                if not best or score > best.get('score', 0):
                    best = dict(section)
                    best['score'] = score
            required_score = max(1, len(search_terms))
            if best and best.get('score', 0) >= required_score:
                break
        if not best:
            return ProviderResult(
                ok=False,
                provider=self.name,
                query=query,
                detail_url=base_url,
                referer=base_url,
                error_type='not-found',
                message='urabukkake tour pages did not match filename terms',
                raw_meta={'family': meta.get('family'), 'code': meta.get('code')},
            )
        return ProviderResult(
            ok=True,
            title=self._clean_title(best.get('title'), meta),
            image_url=best.get('image_url'),
            provider=self.name,
            query=query,
            detail_url=best.get('detail_url') or base_url,
            referer=best.get('referer') or base_url,
            fallback_images=best.get('fallback_images') or [],
            raw_meta={'family': meta.get('family'), 'code': meta.get('code')},
        )

    def _iter_urabukkake_sections(self, soup, page_url):
        for top in soup.select('#section-top'):
            title_element = top.select_one('h2')
            title = title_element.get_text(' ', strip=True) if title_element else ''
            middle = top.find_next_sibling(id='section-mid') or top.find_next(id='section-mid')
            if not title or not middle:
                continue
            image_url = ''
            fallback_images = []
            bigpic = middle.select_one('#bigpic img[src], img.thumb[src]')
            if bigpic:
                image_url = urljoin(page_url, bigpic.get('src'))
            for img in middle.select('img[src]'):
                src = img.get('src')
                if src and not self._is_placeholder_image(src):
                    fallback_images.append(urljoin(page_url, src))
            if not image_url:
                player = middle.select_one('#player[style]')
                style = player.get('style', '') if player else ''
                match = re.search(r'url\((["\']?)([^)"\']+)\1\)', style, re.IGNORECASE)
                if match:
                    image_url = urljoin(page_url, match.group(2))
            if not image_url or self._is_placeholder_image(image_url):
                continue
            yield {
                'title': title,
                'image_url': image_url,
                'detail_url': page_url,
                'referer': page_url,
                'fallback_images': [
                    url for url in fallback_images
                    if url != image_url and not self._is_placeholder_image(url)
                ],
            }

    def search(self, query):
        if self.should_stop():
            return ProviderResult(ok=False, provider=self.name, query=query, error_type='cancelled', message='user stopped')

        meta = self._normalize_query(query)
        if not meta.get('family'):
            return ProviderResult(
                ok=False,
                provider=self.name,
                query=query,
                error_type='unsupported-source',
                message='uncensored provider could not identify a supported source family',
                raw_meta={'family': None, 'code': meta.get('code')},
            )
        if not meta.get('supported'):
            family = meta.get('family')
            if family in {'japanhdv', 'urabukkake'}:
                return ProviderResult(
                    ok=False,
                    provider=self.name,
                    query=query,
                    error_type='invalid-query',
                    message=f'{family} filename lacks searchable title/performer terms',
                    raw_meta={'family': family, 'code': meta.get('code')},
                )
            return ProviderResult(
                ok=False,
                provider=self.name,
                query=query,
                error_type='unsupported-family',
                message=self.UNSUPPORTED_FAMILY_MESSAGES.get(
                    family,
                    f'uncensored family not implemented yet: {family}',
                ),
                raw_meta={'family': family, 'code': meta.get('code')},
            )

        detail_url = meta['detail_url']
        self.log(f'🔍 无码源URL: family={meta.get("family")} | {detail_url}', 'INFO')
        try:
            if meta.get('family') == 'japanhdv':
                return self._search_japanhdv(meta, query)
            if meta.get('family') == 'urabukkake':
                return self._search_urabukkake(meta, query)

            json_detail = None
            try:
                json_detail = self._fetch_json_detail(meta)
            except Exception as exc:
                if meta.get('json_url'):
                    self.log(f'⚠️ 无码源 JSON 详情失败，改用页面解析: {exc}', 'WARNING')

            if self._json_detail_is_complete(json_detail):
                return ProviderResult(
                    ok=True,
                    title=json_detail.get('title'),
                    image_url=json_detail.get('image_url'),
                    provider=self.name,
                    query=query,
                    detail_url=detail_url,
                    referer=detail_url,
                    raw_meta={'family': meta.get('family'), 'code': meta.get('code')},
                )

            if self.should_stop():
                return ProviderResult(
                    ok=False,
                    provider=self.name,
                    query=query,
                    detail_url=detail_url,
                    referer=detail_url,
                    error_type='cancelled',
                    message='user stopped before detail page fetch',
                    raw_meta={'family': meta.get('family'), 'code': meta.get('code')},
                )

            response = self._request(detail_url)
            if self.should_stop():
                return ProviderResult(
                    ok=False,
                    provider=self.name,
                    query=query,
                    detail_url=detail_url,
                    referer=detail_url,
                    error_type='cancelled',
                    message='user stopped after network response',
                    raw_meta={'family': meta.get('family'), 'code': meta.get('code')},
                )
            soup = BeautifulSoup(response.content, 'html.parser')
            if not soup or not soup.find():
                return ProviderResult(
                    ok=False,
                    provider=self.name,
                    query=query,
                    detail_url=detail_url,
                    referer=detail_url,
                    error_type='parse-error',
                    message='empty html',
                )

            blocked_failure = self._blocked_page_failure(soup)
            if blocked_failure:
                error_type, message = blocked_failure
                return ProviderResult(
                    ok=False,
                    provider=self.name,
                    query=query,
                    detail_url=detail_url,
                    referer=detail_url,
                    error_type=error_type,
                    message=message,
                )
            if meta.get('family') == 'fc2-ppv' and self._is_fc2_not_found_page(soup):
                return ProviderResult(
                    ok=False,
                    provider=self.name,
                    query=query,
                    detail_url=detail_url,
                    referer=detail_url,
                    error_type='not-found',
                    message='fc2 article not found or unavailable',
                    raw_meta={'family': meta.get('family'), 'code': meta.get('code')},
                )
            if meta.get('family') == 'tokyo-hot':
                tokyo_hot_result = self._parse_tokyo_hot_result(soup, detail_url, meta)
                if tokyo_hot_result:
                    return ProviderResult(
                        ok=True,
                        title=tokyo_hot_result['title'],
                        image_url=tokyo_hot_result['image_url'],
                        provider=self.name,
                        query=query,
                        detail_url=tokyo_hot_result['detail_url'],
                        referer=detail_url,
                        fallback_images=tokyo_hot_result.get('fallback_images') or [],
                        raw_meta={'family': meta.get('family'), 'code': meta.get('code')},
                    )
                return ProviderResult(
                    ok=False,
                    provider=self.name,
                    query=query,
                    detail_url=detail_url,
                    referer=detail_url,
                    error_type='not-found',
                    message='tokyo-hot product not found in search results',
                    raw_meta={'family': meta.get('family'), 'code': meta.get('code')},
                )

            title = json_detail.get('title') if json_detail else None
            image_url = json_detail.get('image_url') if json_detail else None
            if not title:
                title_selectors = ('meta[property="og:title"]', 'meta[name="twitter:title"]', 'h1', 'title')
                if meta.get('family') != 'fc2-ppv':
                    title_selectors = ('h1', 'meta[property="og:title"]', 'title')
                for selector in title_selectors:
                    element = soup.select_one(selector)
                    if not element:
                        continue
                    title = element.get('content', '').strip() if element.name == 'meta' else element.get_text(' ', strip=True)
                    if title:
                        break
                title = self._clean_title(title, meta)
            if not image_url or self._is_placeholder_image(image_url):
                image_url = self._select_image(soup, detail_url, meta.get('image_candidates') or [], meta=meta)
            if not image_url:
                return ProviderResult(
                    ok=False,
                    title=title,
                    provider=self.name,
                    query=query,
                    detail_url=detail_url,
                    referer=detail_url,
                    error_type='invalid-result',
                    message='missing image',
                )

            return ProviderResult(
                ok=True,
                title=title,
                image_url=image_url,
                provider=self.name,
                query=query,
                detail_url=detail_url,
                referer=detail_url,
                raw_meta={'family': meta.get('family'), 'code': meta.get('code')},
            )
        except requests.exceptions.RequestException as exc:
            return self._request_exception_result(exc, query, detail_url, meta)
        except Exception as exc:
            return ProviderResult(
                ok=False,
                provider=self.name,
                query=query,
                detail_url=detail_url,
                referer=detail_url,
                error_type='provider-error',
                message=str(exc),
            )

    def _is_fc2_not_found_page(self, soup):
        title_element = soup.find('title')
        title = title_element.get_text(' ', strip=True) if title_element else ''
        if 'お探しの商品が見つかりませんでした' in title:
            return True
        page_text = soup.get_text(' ', strip=True)
        return 'お探しの商品が見つかりませんでした' in page_text[:1000]

    def _json_detail_is_complete(self, json_detail):
        if not json_detail:
            return False
        image_url = json_detail.get('image_url')
        return bool(json_detail.get('title') and image_url and not self._is_placeholder_image(image_url))

    def _request_exception_result(self, exc, query, detail_url, meta):
        if self.should_stop():
            return ProviderResult(
                ok=False,
                provider=self.name,
                query=query,
                detail_url=detail_url,
                referer=detail_url,
                error_type='cancelled',
                message='user stopped during network request',
                raw_meta={'family': meta.get('family'), 'code': meta.get('code')},
            )
        message = str(exc)
        message_lower = message.lower()
        response = getattr(exc, 'response', None)
        status_code = getattr(response, 'status_code', None)
        access_denied = (
            status_code in (401, 403, 451)
            or '401' in message_lower
            or '403' in message_lower
            or '451' in message_lower
            or 'forbidden' in message_lower
        )
        if access_denied:
            family = meta.get('family') or 'uncensored source'
            return ProviderResult(
                ok=False,
                provider=self.name,
                query=query,
                detail_url=detail_url,
                referer=detail_url,
                error_type='access-denied',
                message=(
                    f'{family} access denied; official page may require browser cookies, '
                    'age/region verification, or site-side anti-bot access'
                ),
                raw_meta={'family': meta.get('family'), 'code': meta.get('code')},
            )
        return ProviderResult(
            ok=False,
            provider=self.name,
            query=query,
            detail_url=detail_url,
            referer=detail_url,
            error_type='network-error',
            message=message,
            raw_meta={'family': meta.get('family'), 'code': meta.get('code')},
        )

    def _parse_tokyo_hot_result(self, soup, detail_url, meta):
        expected_code = (meta.get('code') or '').lower()
        for item in soup.select('li.detail'):
            item_text = item.get_text(' ', strip=True).lower()
            if expected_code and expected_code not in item_text:
                continue
            title_element = item.select_one('.title')
            image_element = item.select_one('img[src]')
            link_element = item.select_one('a[href]')
            title = title_element.get_text(' ', strip=True) if title_element else ''
            image_url = image_element.get('src') if image_element else ''
            if not title or not image_url or self._is_placeholder_image(image_url):
                continue
            upgraded_image_url = image_url.replace('/220x124_', '/820x462_')
            result_detail_url = detail_url
            if link_element and link_element.get('href'):
                result_detail_url = urljoin(detail_url, link_element.get('href'))
            return {
                'title': self._clean_title(title, meta),
                'image_url': urljoin(detail_url, upgraded_image_url),
                'detail_url': result_detail_url,
                'fallback_images': [urljoin(detail_url, image_url)],
            }
        return None
