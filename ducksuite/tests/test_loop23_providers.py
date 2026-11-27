import pytest
from duckcore.providers import Provider, Registry, local_base_url


@pytest.mark.parametrize('url', ['http://127.0.0.1:8080', 'http://localhost:8000', 'http://[::1]:8080'])
def test_local_urls(url):
    assert local_base_url(url) == url


@pytest.mark.parametrize('url', ['https://example.com', 'http://localhost.example.com',
                               'http://user:secret@localhost', 'http://localhost/?key=x'])
def test_external_or_secret_urls_refused(url):
    with pytest.raises(ValueError):
        local_base_url(url)


def test_registry_rejects_secret_provider():
    registry = Registry()
    noop = lambda: None
    with pytest.raises(ValueError):
        registry.register(Provider('remote', 'rewrite', (), noop, noop, noop, True))
    provider = Provider('local', 'rewrite', (), noop, noop, noop)
    registry.register(provider)
    assert registry.get('local') is provider
