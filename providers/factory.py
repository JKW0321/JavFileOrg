from .javbus_provider import JavBusProvider
from .javhoo_provider import JavHooProvider
from .javlibrary_provider import JavLibraryProvider


def create_provider(name: str, *, log, session=None, anti_crawl=None, stop_requested=None):
    mapping = {
        'javhoo': JavHooProvider,
        'javbus': JavBusProvider,
        'javlibrary': JavLibraryProvider,
    }
    cls = mapping.get(name)
    if cls is None:
        raise ValueError(f'unknown provider: {name}')
    return cls(log=log, session=session, anti_crawl=anti_crawl, stop_requested=stop_requested)
