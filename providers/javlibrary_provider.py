from .base import BaseProvider, ProviderResult


class JavLibraryProvider(BaseProvider):
    name = 'javlibrary'

    def search(self, query: str) -> ProviderResult:
        if self.should_stop():
            return ProviderResult(ok=False, provider=self.name, error_type='cancelled', message='user stopped')
        if self.anti_crawl and getattr(self.anti_crawl, 'selenium_javlibrary', None):
            self.log('🌐 使用Selenium访问JAVLibrary', 'INFO')
            try:
                result = self.anti_crawl.selenium_javlibrary.search_by_id(query)
                if result:
                    self.log('✅ Selenium获取数据成功', 'SUCCESS')
                    return ProviderResult(
                        ok=True,
                        title=result.get('title', ''),
                        image_url=result.get('cover_url', ''),
                        provider=self.name,
                        raw_meta=result,
                    )
                return ProviderResult(ok=False, provider=self.name, error_type='not-found', message='selenium returned empty')
            except Exception as e:
                return ProviderResult(ok=False, provider=self.name, error_type='browser-error', message=str(e))
        return ProviderResult(ok=False, provider=self.name, error_type='provider-error', message='selenium not initialized')
