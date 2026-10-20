"""식당 정보 제공자 고르기. Google Places 구현(B4)이 생기면 GOOGLE_PLACES_API_KEY가 있을 때 그것을 쓴다."""

from app.integrations.places.ports import PlacesProvider
from app.integrations.places.sample import SamplePlacesProvider

_provider: PlacesProvider = SamplePlacesProvider()


def get_places_provider() -> PlacesProvider:
    return _provider
