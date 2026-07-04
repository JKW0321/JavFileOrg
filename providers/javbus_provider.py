from .request_provider import RequestHtmlProvider


class JavBusProvider(RequestHtmlProvider):
    name = 'javbus'
    search_url = 'https://www.javbus.com/{query}'
    title_selectors = ('title', 'h3', '.movie-title', '.title')
    image_selectors = ('.bigImage img', 'img[title]', '.movie-poster img')
    search_page_is_detail = True
    use_anti_crawl_session = True
