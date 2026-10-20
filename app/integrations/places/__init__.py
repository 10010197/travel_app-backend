"""식당 정보 제공자 고르기. GOOGLE_PLACES_API_KEY가 있으면 Google Places(New), 없으면 샘플 16곳."""

from functools import lru_cache

from app.core.config import get_settings
from app.integrations.places.google import GooglePlacesProvider
from app.integrations.places.ports import PlacesProvider
from app.integrations.places.sample import SamplePlacesProvider


@lru_cache
def _provider(api_key: str, timeout: float) -> PlacesProvider:
    if api_key:
        return GooglePlacesProvider(api_key, timeout=timeout)
    return SamplePlacesProvider()


def get_places_provider() -> PlacesProvider:
    settings = get_settings()
    return _provider(
        settings.google_places_api_key.get_secret_value(), settings.external_timeout_seconds
    )
