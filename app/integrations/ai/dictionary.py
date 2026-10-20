"""사전 기반 AI 대역 (프론트 src/mocks/ai/classifyMenu.ts, normalizeFoods.ts와 같은 규칙).

LLM(LangChain, B5)을 붙이기 전까지 실제 서버도 이 구현을 쓰고, 테스트는 LLM을 붙인 뒤에도 이 구현을 쓴다.
결과 형식은 LLM 구현과 같다: 종류는 허용 목록 안의 값 또는 None, 태그는 음식 태그 id만.
"""

import re
from collections.abc import Sequence

from app.integrations.ai.ports import (
    Classification,
    FoodVocabulary,
    KnownMenu,
    NormalizedFoods,
)

# 앞에서부터 처음 맞는 규칙을 쓴다. 면이 주가 되는 메뉴는 모두 noodle (Q-02)
_KIND_RULES: tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...] = (
    ("noodle", ("라멘", "라면", "우동", "소바", "파스타", "짬뽕", "면"), ("wheat",)),
    ("hotpot", ("나베", "전골", "미즈타키", "샤부", "스키야키"), ()),
    ("rice", ("주먹밥", "오니기리", "덮밥", "동", "카레", "밥", "정식"), ()),
    ("seafood", ("스시", "초밥", "회", "사바", "사시미", "이카", "게", "생선"), ("seafood",)),
    ("fried", ("텐푸라", "튀김", "가라아게", "돈카츠", "카츠"), ("wheat",)),
    ("grill", ("교자", "야키토리", "야키니쿠", "구이", "고기", "스테이크"), ("meat",)),
    ("street", ("야타이", "포장마차"), ()),
    ("bread", ("빵", "바게트", "베이커리", "샌드위치"), ("wheat",)),
    ("dessert", ("케이크", "푸딩", "디저트", "아이스", "빙수", "파르페", "모찌"), ()),
    ("cafe", ("커피", "카페", "라테", "차"), ()),
)

# 메뉴 이름에서 짐작할 수 있는 음식 태그
_TAG_HINTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("돈코츠", ("meat", "pork")),
    ("라멘", ("meat", "pork")),
    ("모츠", ("meat", "beef", "offal")),
    ("닭", ("meat", "chicken")),
    ("미즈타키", ("meat", "chicken")),
    ("야키토리", ("meat", "chicken")),
    ("교자", ("meat", "pork", "wheat")),
    ("게", ("seafood", "crustacean")),
    ("새우", ("seafood", "crustacean")),
    ("명란", ("seafood", "fish_roe")),
    ("멘타이코", ("seafood", "fish_roe")),
    ("회", ("seafood", "raw_fish")),
    ("스시", ("seafood", "raw_fish")),
    ("달걀", ("egg",)),
    ("치즈", ("dairy",)),
)

# 사람들이 흔히 쓰는 표현 → 태그
_SYNONYMS: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (("비건", "채식"), ("meat", "seafood", "egg", "dairy")),
    (("페스코",), ("meat",)),
    (("고기", "육류"), ("meat",)),
    (("돼지",), ("pork",)),
    (("소고기", "쇠고기"), ("beef",)),
    (("닭",), ("chicken",)),
    (("내장", "곱창"), ("offal",)),
    (("해산물",), ("seafood",)),
    (("생선",), ("fish",)),
    (("날생선", "회"), ("raw_fish",)),
    (("갑각류", "게", "새우", "랍스터"), ("crustacean",)),
    (("조개", "굴"), ("shellfish",)),
    (("오징어", "문어"), ("cephalopod",)),
    (("달걀", "계란"), ("egg",)),
    (("유제품", "우유", "치즈"), ("dairy",)),
    (("밀", "글루텐"), ("wheat",)),
    (("견과", "땅콩"), ("nuts",)),
    (("참깨",), ("sesame",)),
    (("술", "알코올"), ("alcohol",)),
)

_SPLIT = re.compile(r"[,/·\s]+")
_SUFFIX = re.compile(r"(알레르기|알러지|못\s*먹음|안\s*먹음|X)$")


def _unique(tags: list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(tags))


class DictionaryMenuClassifier:
    def classify(self, menu: str, known: Sequence[KnownMenu]) -> Classification:
        name = menu.strip()
        for item in known:
            if item.name == name:
                return Classification(item.kind_id, "high", item.food_tags)

        rule = next((r for r in _KIND_RULES if any(k in name for k in r[1])), None)
        hinted = [t for keyword, tags in _TAG_HINTS if keyword in name for t in tags]
        tags = _unique([*(rule[2] if rule else ()), *hinted])
        if rule:
            return Classification(rule[0], "high", tags)
        return Classification(None, "low", tags)


class DictionaryFoodNormalizer:
    def normalize(self, raw: str, vocabulary: FoodVocabulary) -> NormalizedFoods:
        pieces = [_SUFFIX.sub("", p).strip() for p in _SPLIT.split(raw)]
        tags: set[str] = set()
        unknown = False
        for piece in (p for p in pieces if p):
            preset = next((p for p in vocabulary.presets if p[0].startswith(piece)), None)
            matched = [s for s in _SYNONYMS if any(w in piece for w in s[0])]
            direct = next((t for t in vocabulary.tags if t[1] == piece), None)
            if preset:
                tags.update(preset[1])
            for _, synonym_tags in matched:
                tags.update(synonym_tags)
            if direct:
                tags.add(direct[0])
            if not preset and not matched and not direct:
                unknown = True
        return NormalizedFoods(tuple(sorted(tags)), "needs_check" if unknown else "ok")
