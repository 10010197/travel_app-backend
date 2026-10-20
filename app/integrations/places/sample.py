"""샘플 식당 제공자: 후쿠오카 샘플 16곳 (프론트 src/mocks/places와 같은 데이터·매칭 규칙).

GOOGLE_PLACES_API_KEY가 없을 때(로컬 개발·테스트) 쓴다. 외부 API를 부르지 않는다.
"""

import json
from functools import cached_property
from pathlib import Path
from typing import Any

from app.integrations.places.models import PlaceDetail

_DATA = Path(__file__).with_name("sample_places.json")


class SamplePlacesProvider:
    @cached_property
    def _places(self) -> list[tuple[PlaceDetail, tuple[str, ...]]]:
        raw: list[dict[str, Any]] = json.loads(_DATA.read_text(encoding="utf-8"))["places"]
        return [(PlaceDetail.model_validate(p), tuple(p["keywords"])) for p in raw]

    def text_search(
        self, query: str, *, center: tuple[float, float], ignore: tuple[str, ...]
    ) -> list[PlaceDetail]:
        tokens = [t for t in query.split() if t and t not in ignore]
        return [place for place, keywords in self._places if _matches(place, keywords, tokens)]

    def get(self, place_id: str) -> PlaceDetail | None:
        return next((p for p, _ in self._places if p.place_id == place_id), None)


def _matches(place: PlaceDetail, keywords: tuple[str, ...], tokens: list[str]) -> bool:
    """검색어가 식당 이름이나 메뉴 키워드와 맞는지. 검색어가 비면 모두 맞는다."""
    if not tokens:
        return True
    full = " ".join(tokens)
    return any(k in full or any(t in k for t in tokens) for k in keywords) or any(
        t in place.name for t in tokens
    )
