from urllib.parse import quote

from .base import BaseProvider, ProviderResult


class JavLibraryProvider(BaseProvider):
    name = 'javlibrary'

    def search(self, query: str) -> ProviderResult:
        normalized_query = (query or '').strip().upper()
        referer = f'https://www.javlibrary.com/tw/vl_searchbyid.php?keyword={quote(normalized_query)}'
        if self.should_stop():
            return ProviderResult(
                ok=False,
                provider=self.name,
                query=query,
                referer=referer,
                error_type='cancelled',
                message='user stopped',
            )
        if self.anti_crawl and getattr(self.anti_crawl, 'selenium_javlibrary', None):
            self.log('🌐 使用Selenium访问JAVLibrary', 'INFO')
            try:
                result = self.anti_crawl.selenium_javlibrary.search_by_id(normalized_query)
                if result:
                    title = result.get('title', '')
                    cover_url = result.get('cover_url', '')
                    if not title or not cover_url:
                        return ProviderResult(
                            ok=False,
                            title=title,
                            image_url=cover_url,
                            provider=self.name,
                            query=query,
                            detail_url=result.get('detail_url') or result.get('url'),
                            referer=referer,
                            error_type='parse-error',
                            message='selenium result missing title or cover_url',
                            raw_meta=result,
                        )
                    self.log('✅ Selenium获取数据成功', 'SUCCESS')
                    return ProviderResult(
                        ok=True,
                        title=title,
                        image_url=cover_url,
                        provider=self.name,
                        query=query,
                        detail_url=result.get('detail_url') or result.get('url'),
                        referer=referer,
                        raw_meta=result,
                    )
                error_type = getattr(self.anti_crawl.selenium_javlibrary, 'last_error_type', '') or 'not-found'
                message = getattr(self.anti_crawl.selenium_javlibrary, 'last_error_message', '') or 'selenium returned empty'
                return ProviderResult(
                    ok=False,
                    provider=self.name,
                    query=query,
                    referer=referer,
                    error_type=error_type,
                    message=message,
                )
            except Exception as e:
                return ProviderResult(
                    ok=False,
                    provider=self.name,
                    query=query,
                    referer=referer,
                    error_type='browser-error',
                    message=str(e),
                )
        return ProviderResult(
            ok=False,
            provider=self.name,
            query=query,
            referer=referer,
            error_type='provider-error',
            message='selenium not initialized',
        )
