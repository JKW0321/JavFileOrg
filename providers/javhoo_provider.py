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
