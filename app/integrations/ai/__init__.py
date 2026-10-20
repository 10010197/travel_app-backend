"""AI 구현 고르기. LLM 구현(B5)이 생기면 설정(LLM_API_KEY)에 따라 여기서 바꾼다."""

from app.integrations.ai.dictionary import DictionaryFoodNormalizer, DictionaryMenuClassifier
from app.integrations.ai.ports import FoodNormalizer, MenuClassifier

_classifier = DictionaryMenuClassifier()
_normalizer = DictionaryFoodNormalizer()


def get_menu_classifier() -> MenuClassifier:
    return _classifier


def get_food_normalizer() -> FoodNormalizer:
    return _normalizer
