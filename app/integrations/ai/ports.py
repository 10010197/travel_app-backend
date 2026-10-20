"""AI 기능의 인터페이스 (TECH_STACK 3장). 프롬프트와 외부 호출은 integrations/ai 안에만 둔다.

- 메뉴 → 종류 분류 (F-04 1): 허용된 종류 목록 안에서만 답하고, 모르면 None
- 못 먹는 음식 원문 → 정규화 태그 (F-02 4): 원문은 그대로 두고, 알아들을 수 없는 조각이 있으면 needs_check

마스터 데이터(필수 메뉴, 음식 태그·프리셋)는 호출할 때 넘긴다. 구현은 DB나 모듈을 모른다.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol


@dataclass(frozen=True, slots=True)
class KnownMenu:
    """이름이 같으면 그대로 쓰는 도시 필수 메뉴"""

    name: str
    kind_id: str
    food_tags: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Classification:
    kind_id: str | None
    confidence: Literal["high", "low"]
    menu_tags: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FoodVocabulary:
    """정규화 결과로 쓸 수 있는 태그(id, 한국어 이름)와 프리셋(이름, 태그들)"""

    tags: tuple[tuple[str, str], ...]
    presets: tuple[tuple[str, tuple[str, ...]], ...]


@dataclass(frozen=True, slots=True)
class NormalizedFoods:
    food_tags: tuple[str, ...]
    tag_status: Literal["ok", "needs_check"]


class MenuClassifier(Protocol):
    def classify(self, menu: str, known: Sequence[KnownMenu]) -> Classification: ...


class FoodNormalizer(Protocol):
    def normalize(self, raw: str, vocabulary: FoodVocabulary) -> NormalizedFoods: ...
