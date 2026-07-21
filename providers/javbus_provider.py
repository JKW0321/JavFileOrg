from .request_provider import RequestHtmlProvider


class JavBusProvider(RequestHtmlProvider):
    name = 'javbus'
    search_url = 'https://www.javbus.com/{query}'
    title_selectors = ('title', 'h3', '.movie-title', '.title')
    image_selectors = ('.bigImage img', 'img[title]', '.movie-poster img')
    search_page_is_detail = True
    use_anti_crawl_session = True
    connect_timeout = 8
    read_timeout = 15
    retry_network_errors = 1

    def _prepare_session_for_request(self, session, url: str):
        headers = getattr(session, 'headers', None)
        if headers is not None:
            headers.setdefault('Accept-Language', 'ja,en-US;q=0.9,en;q=0.8')
            headers.setdefault('Referer', 'https://www.javbus.com/')
        cookies = getattr(session, 'cookies', None)
        if cookies is not None:
            for domain in ('.javbus.com', 'www.javbus.com'):
                cookies.set('existmag', 'mag', domain=domain, path='/')
            cookies.set('existmag', 'mag', path='/')

    def _invalid_result_reason(self, title, image_url, detail_url, referer):
        title_lower = (title or '').strip().lower()
        image_lower = (image_url or '').lower()
        reasons = []
        if 'age verification' in title_lower:
            reasons.append('age-verification-title')
        if not image_url:
            reasons.append('missing-image')
        elif any(marker in image_lower for marker in ('logo', 'sprite', 'icon', '.svg')):
            reasons.append('placeholder-image')
        return 'javbus invalid result: ' + ','.join(reasons) if reasons else ''
