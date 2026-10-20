"""서버가 쓰는 도메인 규칙과 사전 기반 AI 대역 (프론트 src/domain, src/mocks/ai와 같은 결과)."""

from datetime import date

from app.domain.days import (
    describe_range_label,
    diff_trip_dates,
    enumerate_dates,
    validate_trip_range,
)
from app.domain.duplicate import DupAck, DupSlot, find_duplicate_groups, stale_acks
from app.domain.geo import (
    AreaCircle,
    Point,
    area_of_location,
    build_google_maps_search_url,
    build_search_query,
    distance_meters,
)
from app.domain.time_band import band_for_meal_name
from app.integrations.ai.dictionary import DictionaryFoodNormalizer, DictionaryMenuClassifier
from app.integrations.ai.ports import FoodVocabulary, KnownMenu

D = date.fromisoformat


def test_trip_range_rules() -> None:
    today = D("2026-10-20")
    assert validate_trip_range(D("2026-10-20"), D("2026-11-02"), today) is None
    assert validate_trip_range(D("2026-10-19"), D("2026-10-21"), today) == "start_before_today"
    assert validate_trip_range(D("2026-10-22"), D("2026-10-21"), today) == "end_before_start"
    assert validate_trip_range(D("2026-10-20"), D("2026-11-03"), today) == "too_long"


def test_range_label_and_dates() -> None:
    assert describe_range_label(D("2026-11-14"), D("2026-11-16")) == "2박 3일"
    assert describe_range_label(D("2026-11-14"), D("2026-11-14")) == "당일치기"
    assert enumerate_dates(D("2026-12-31"), D("2027-01-01")) == [D("2026-12-31"), D("2027-01-01")]
    diff = diff_trip_dates(
        [D("2026-11-14"), D("2026-11-15"), D("2026-11-16")], D("2026-11-15"), D("2026-11-17")
    )
    assert diff.remove == [D("2026-11-14")]
    assert diff.add == [D("2026-11-17")]
    assert diff.keep == [D("2026-11-15"), D("2026-11-16")]


def test_meal_bands() -> None:
    assert band_for_meal_name("점심") == "lunch"
    assert band_for_meal_name("2차") == "night"
    assert band_for_meal_name("디저트 타임") == "night"


def test_duplicate_groups_and_stale_acks() -> None:
    slots = [
        DupSlot("a", "d1", "filled", "noodle"),
        DupSlot("b", "d1", "filled", "noodle"),
        DupSlot("c", "d1", "skipped", "noodle"),
        DupSlot("d", "d1", "filled", "rice"),
        DupSlot("e", "d1", "filled", "rice"),
        DupSlot("f", "d2", "filled", "noodle"),
    ]
    no_repeat = {"noodle"}
    groups = find_duplicate_groups(slots, no_repeat)
    assert [(g.day_id, g.kind_id, g.slot_ids) for g in groups] == [("d1", "noodle", ("a", "b"))]

    acks = [DupAck("d1", "noodle", ("a", "b")), DupAck("d2", "noodle", ("f", "x"))]
    assert stale_acks(slots, no_repeat, acks) == [acks[1]]


def test_geo() -> None:
    hakata = AreaCircle("hakata", Point(33.5902, 130.4207), 800)
    tenjin = AreaCircle("tenjin", Point(33.5911, 130.399), 700)
    assert distance_meters(Point(33.5902, 130.4207), Point(33.5902, 130.4207)) == 0
    assert area_of_location([hakata, tenjin], Point(33.5915, 130.3995)) == "tenjin"
    assert area_of_location([hakata, tenjin], Point(33.0, 130.0)) is None
    assert build_search_query("하카타 라멘", None, "후쿠오카") == "하카타 라멘 후쿠오카"
    assert (
        build_google_maps_search_url("라멘 텐진")
        == "https://www.google.com/maps/search/?api=1&query=%EB%9D%BC%EB%A9%98%20%ED%85%90%EC%A7%84"
    )


def test_dictionary_classifier() -> None:
    classify = DictionaryMenuClassifier().classify
    known = [KnownMenu("모츠나베", "hotpot", ("meat", "beef", "offal"))]
    assert classify("모츠나베", known).kind_id == "hotpot"
    result = classify("돈코츠 라멘", [])
    assert (result.kind_id, result.confidence, result.menu_tags) == (
        "noodle",
        "high",
        ("wheat", "meat", "pork"),
    )
    assert classify("무언가", []).kind_id is None


def test_dictionary_normalizer() -> None:
    vocabulary = FoodVocabulary(
        tags=(("meat", "육류"), ("crustacean", "갑각류")),
        presets=(
            ("비건", ("meat", "seafood", "egg", "dairy")),
            ("갑각류 알레르기", ("crustacean",)),
        ),
    )
    normalize = DictionaryFoodNormalizer().normalize
    assert normalize("비건", vocabulary).food_tags == ("dairy", "egg", "meat", "seafood")
    result = normalize("갑각류 알레르기, 땅콩", vocabulary)
    assert (result.food_tags, result.tag_status) == (("crustacean", "nuts"), "ok")
    assert normalize("고수", vocabulary).tag_status == "needs_check"
