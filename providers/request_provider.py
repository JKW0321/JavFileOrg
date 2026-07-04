from urllib.parse import quote, urljoin

import requests
from bs4 import BeautifulSoup

from .base import BaseProvider, ProviderResult


class RequestHtmlProvider(BaseProvider):
    search_url = ''
    title_selectors = ('title',)
    image_selectors = ('img',)
    detail_url_pattern = None
    use_anti_crawl_session = False
    site_suffixes = ()

    def _get_session(self):
        if self.use_anti_crawl_session and self.anti_crawl:
            return self.anti_crawl.session
        return self.session

    def _request(self, url: str):
        session = self._get_session()
        response = session.get(url, timeout=(5, 15))
        response.raise_for_status()
        return response

    def _clean_title(self, title: str) -> str:
        title = (title or '').strip()
        for suffix in self.site_suffixes:
            if title.endswith(suffix):
                title = title[:-len(suffix)].strip()
        if ' - ' in title:
            parts = title.rsplit(' - ', 1)
            if len(parts) == 2 and len(parts[1]) < 20:
                title = parts[0].strip()
        return title.strip()

    def _find_detail_url(self, soup, search_url, search_query):
        if not self.detail_url_pattern:
            return None
        code_lower = search_query.lower()
        expected_url = self.detail_url_pattern.format(code_lower=code_lower)
        candidates = []
        for a in soup.select('article h2 a, article .thumbnail a, article a'):
            href = a.get('href', '')
            if not href or href.startswith('#'):
                continue
            abs_url = urljoin(search_url, href)
            if abs_url not in candidates:
                candidates.append(abs_url)
            if len(candidates) >= 3:
                break
        if expected_url and expected_url not in candidates:
            candidates.append(expected_url)
        for url in candidates:
            if code_lower.replace('-', '') in url.lower().replace('-', '').replace('/', ''):
                return url
        return candidates[0] if candidates else None

    def _fetch_detail_page(self, detail_url):
        response = self._request(detail_url)
        soup = BeautifulSoup(response.content, 'html.parser')
        if not soup or not soup.find():
            return None, None
        title = None
        h1 = soup.find('h1')
        if h1:
            title = h1.get_text().strip()
        if not title:
            t = soup.find('title')
            if t:
                title = self._clean_title(t.get_text())
        image_url = None
        for img in soup.find_all('img'):
            src = img.get('data-src') or img.get('src') or ''
            if src and 'logo' not in src.lower():
                image_url = urljoin(detail_url, src)
                break
        return title, image_url

    def search(self, query: str) -> ProviderResult:
        if self.should_stop():
            return ProviderResult(ok=False, provider=self.name, error_type='cancelled', message='user stopped')
        search_url = self.search_url.format(query=quote(query))
        self.log(f'🔍 搜索URL: {search_url}', 'INFO')
        try:
            response = self._request(search_url)
            soup = BeautifulSoup(response.content, 'html.parser')
            if not soup or not soup.find():
                return ProviderResult(ok=False, provider=self.name, error_type='parse-error', message='empty html')
            title = None
            for selector in self.title_selectors:
                try:
                    if selector == 'title':
                        title_element = soup.find('title')
                        if title_element:
                            title = self._clean_title(title_element.get_text())
                            if title:
                                break
                    else:
                        title_element = soup.select_one(selector)
                        if title_element:
                            title = title_element.get_text().strip()
                            if title:
                                break
                except Exception:
                    continue
            if not title or len(title.strip()) < 3:
                return ProviderResult(ok=False, provider=self.name, error_type='not-found', message='title not found')
            image_url = None
            for selector in self.image_selectors:
                try:
                    img_element = soup.select_one(selector)
                    if img_element:
                        image_url = img_element.get('src') or img_element.get('data-src')
                        if image_url:
                            image_url = urljoin(search_url, image_url)
                            break
                except Exception:
                    continue
            detail_url = self._find_detail_url(soup, search_url, query)
            if detail_url and (title or image_url):
                try:
                    upgrade_title, upgrade_image = self._fetch_detail_page(detail_url)
                    if upgrade_title and len(upgrade_title) > len(title or ''):
                        title = upgrade_title
                    if upgrade_image:
                        image_url = upgrade_image
                except Exception as e:
                    self.log(f'⚠️ 详情页升级失败（保留搜索页结果）: {e}', 'WARNING')
            return ProviderResult(ok=True, title=title, image_url=image_url, provider=self.name)
        except requests.exceptions.RequestException as e:
            return ProviderResult(ok=False, provider=self.name, error_type='network-error', message=str(e))
        except Exception as e:
            return ProviderResult(ok=False, provider=self.name, error_type='provider-error', message=str(e))
