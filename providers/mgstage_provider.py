from .base import ProviderResult
from .uncensored_provider import UncensoredProvider


class MGStageProvider(UncensoredProvider):
    """Exact-source MGStage adapter used by automatic censored routing."""

    name = 'mgstage'

    def search(self, query: str) -> ProviderResult:
        meta = self._normalize_query(query)
        if meta.get('family') != 'mgstage':
            return ProviderResult(
                ok=False,
                provider=self.name,
                query=query,
                error_type='unsupported-source',
                message='MGStage provider only accepts recognized MGStage product codes',
                raw_meta={'family': meta.get('family'), 'code': meta.get('code')},
            )
        return super().search(query)
