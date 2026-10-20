"""식당 정보 제공자 인터페이스 (F-09, C-8).

실제 구현은 Google Places(New) Text Search·Place Details를 필드 마스크로 부른다(B4, GOOGLE_PLACES_API_KEY).
키가 없으면 샘플 구현(sample.py)을 쓴다. 범위 거르기·거리 정렬·캐시·호출 한도는 places 서비스가 맡는다.
"""

from typing import Protocol

from app.integrations.places.models import PlaceDetail


class PlacesProvider(Protocol):
    def text_search(
        self, query: str, *, center: tuple[float, float], ignore: tuple[str, ...]
    ) -> list[PlaceDetail]:
        """검색어에 맞는 식당 (center 근처 우선). ignore는 검색어 중 매칭에서 빼도 되는 도시·동네 이름"""
        ...

    def get(self, place_id: str) -> PlaceDetail | None:
        """식당 상세. 없으면 None"""
        ...
