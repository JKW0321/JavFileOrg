from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .request_provider import RequestHtmlProvider


class JavHooProvider(RequestHtmlProvider):
    name = 'javhoo'
    search_url = 'https://www.javhoo.com/search/{query}'
    detail_url_pattern = 'https://www.javhoo.com/{code_lower}'
    title_selectors = ('article h2 a', 'h1', 'title')
    image_selectors = (
        'article img[data-src]',
        'article .thumbnail img',
        'img[src*="pics.javhoo.net"]',
        'a.dt-single-image img',
        '.movie-poster img',
    )
    site_suffixes = ('-JAVHOO', '-JavHoo', ' - JAVHOO', ' - JavHoo', '-javhoo')

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
        # 优先命中真实封面：pics.javhoo.net + 非 logo/flag/thumb，且最好带 alt/title 信息
        for img in soup.find_all('img'):
            src = img.get('data-src') or img.get('src') or ''
            src_lower = src.lower()
            cls = ' '.join(img.get('class', [])).lower()
            alt = (img.get('alt') or '').strip()
            if not src or 'pics.javhoo.net' not in src_lower:
                continue
            if 'logo' in src_lower or 'flag' in src_lower or 'qtranxs' in cls or 'thumb' in cls:
                continue
            if alt or '_b.' in src_lower or src_lower.endswith(('.jpg', '.jpeg', '.png')):
                image_url = urljoin(detail_url, src)
                break

        # 兜底：任意非 flag/logo 的 javhoo 图片
        if not image_url:
            for img in soup.find_all('img'):
                src = img.get('data-src') or img.get('src') or ''
                src_lower = src.lower()
                cls = ' '.join(img.get('class', [])).lower()
                if not src or 'pics.javhoo.net' not in src_lower:
                    continue
                if 'logo' in src_lower or 'flag' in src_lower or 'qtranxs' in cls:
                    continue
                image_url = urljoin(detail_url, src)
                break

        return title, image_url