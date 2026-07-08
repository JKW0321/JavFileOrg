from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .request_provider import RequestHtmlProvider


class BestJavPornProvider(RequestHtmlProvider):
    name = 'bestjavporn'
    search_url = 'https://www.bestjavporn.com/ja/?s={query}'
    title_selectors = (
        'article h2 a',
        'article .entry-title a',
        '.post-title a',
        '.entry-title a',
        'h1.entry-title',
        'h1',
        'title',
    )
    image_selectors = (
        'article img[data-src]',
        'article img[src]',
        '.post-thumbnail img',
        '.video-cover img',
        '.entry-content img',
    )
    site_suffixes = (
        ' - BestJavPorn',
        ' - Best JAV Porn',
        ' | BestJavPorn',
        ' | Best JAV Porn',
    )

    def _blocked_page_failure(self, soup, response):
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
            return (
                'verification-required',
                'bestjavporn returned Cloudflare verification page',
            )
        return None

    def _is_placeholder_image(self, image_url):
        image_lower = (image_url or '').strip().lower()
        return any(marker in image_lower for marker in (
            'logo',
            'avatar',
            'banner',
            'sprite',
            'icon',
            'placeholder',
        ))

    def _find_detail_url(self, soup, search_url, search_query):
        query_normalized = (search_query or '').lower().replace('-', '')
        candidates = []
        for selector in (
            'article h2 a',
            'article .entry-title a',
            '.post-title a',
            '.entry-title a',
            'article a[href*="/video/"]',
        ):
            for link in soup.select(selector):
                href = link.get('href', '')
                if not href or href.startswith('#'):
                    continue
                abs_url = urljoin(search_url, href)
                if abs_url not in candidates:
                    candidates.append(abs_url)

        for url in candidates:
            if query_normalized and query_normalized in url.lower().replace('-', ''):
                return url
        return candidates[0] if candidates else None

    def _should_use_detail_title(self, current_title, detail_title):
        return bool(detail_title)

    def _invalid_result_reason(self, title, image_url, detail_url, referer):
        reasons = []
        title_lower = (title or '').strip().lower()
        if not title_lower:
            reasons.append('missing-title')
        elif (
            title_lower == 'bestjavporn'
            or title_lower.startswith('search results')
            or title_lower.startswith('no results')
            or 'nothing found' in title_lower
        ):
            reasons.append('generic-title')
        if not image_url:
            reasons.append('missing-image')
        elif self._is_placeholder_image(image_url):
            reasons.append('placeholder-image')
        if reasons:
            return 'bestjavporn invalid result: ' + ','.join(reasons)
        return ''

    def _select_image(self, soup, base_url):
        for meta_selector in (
            'meta[property="og:image"]',
            'meta[name="twitter:image"]',
        ):
            meta = soup.select_one(meta_selector)
            content = meta.get('content') if meta else ''
            if content and not self._is_placeholder_image(content):
                return urljoin(base_url, content)

        for img in soup.find_all('img'):
            src = img.get('data-src') or img.get('data-lazy-src') or img.get('src') or ''
            if not src or self._is_placeholder_image(src):
                continue
            cls = ' '.join(img.get('class', [])).lower()
            if any(marker in cls for marker in ('logo', 'avatar', 'banner', 'icon')):
                continue
            return urljoin(base_url, src)
        return None

    def _fetch_detail_page(self, detail_url):
        response = self._request(detail_url)
        soup = BeautifulSoup(response.content, 'html.parser')
        if not soup or not soup.find():
            return None, None

        blocked_failure = self._blocked_page_failure(soup, response)
        if blocked_failure:
            return None, None

        title = None
        for selector in ('h1.entry-title', 'h1', 'meta[property="og:title"]', 'title'):
            element = soup.select_one(selector)
            if not element:
                continue
            if element.name == 'meta':
                title = element.get('content', '').strip()
            else:
                title = element.get_text(' ', strip=True)
            title = self._clean_title(title)
            if title:
                break

        return title, self._select_image(soup, detail_url)
