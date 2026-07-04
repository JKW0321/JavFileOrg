from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class ProviderResult:
    ok: bool
    title: Optional[str] = None
    image_url: Optional[str] = None
    provider: Optional[str] = None
    error_type: Optional[str] = None
    message: Optional[str] = None
    raw_meta: Dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default=None):
        return getattr(self, key, default)


class BaseProvider:
    name = 'base'

    def __init__(self, *, log, session=None, anti_crawl=None, stop_requested=None):
        self._log = log
        self.session = session
        self.anti_crawl = anti_crawl
        self.stop_requested = stop_requested or (lambda: False)

    def log(self, message: str, level: str = 'INFO'):
        if self._log:
            self._log(message, level)

    def should_stop(self) -> bool:
        return bool(self.stop_requested())

    def search(self, query: str) -> ProviderResult:
        raise NotImplementedError
