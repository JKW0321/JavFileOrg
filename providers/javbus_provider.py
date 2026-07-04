from .request_provider import RequestHtmlProvider


class JavBusProvider(RequestHtmlProvider):
    name = 'javbus'
    search_url = 'https://www.javbus.com/{query}'
    title_selectors = ('title', 'h3', '.movie-title', '.title')
    image_selectors = ('.bigImage img', 'img[title]', '.movie-poster img')
    use_anti_crawl_session = True
