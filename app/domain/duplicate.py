"""하루 단위 메뉴 중복 (FEATURE_SPEC R-01, F-05). 프론트 src/domain/duplicate.ts와 같다.

서버는 경고를 계산해 내려주지 않는다(화면이 계산한다). 서버가 쓰는 건 하나:
끼니가 바뀐 뒤 중복이 풀린 "괜찮아요" 기록(staleAcks)을 찾아 지우는 것 (F-05 5, cleanupStaleAcks).
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DupSlot:
    id: str
    day_id: str
    state: str
    kind_id: str | None


@dataclass(frozen=True, slots=True)
class DupAck:
    day_id: str
    kind_id: str
    slot_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DuplicateGroup:
    day_id: str
    kind_id: str
    slot_ids: tuple[str, ...]


def is_duplicate_candidate(slot: DupSlot) -> bool:
    """중복 검사 대상: 메뉴가 있고(filled) 종류가 정해진 끼니"""
    return slot.state == "filled" and slot.kind_id is not None


def find_duplicate_groups(slots: list[DupSlot], no_repeat_kinds: set[str]) -> list[DuplicateGroup]:
    """같은 날짜에 하루 반복을 허용하지 않는 종류가 2번 이상 나온 묶음 (R-01 1, 2)"""
    groups: dict[tuple[str, str], list[str]] = {}
    for slot in slots:
        if not is_duplicate_candidate(slot) or slot.kind_id not in no_repeat_kinds:
            continue
        assert slot.kind_id is not None
        groups.setdefault((slot.day_id, slot.kind_id), []).append(slot.id)
    return sorted(
        (
            DuplicateGroup(day_id, kind_id, tuple(sorted(ids)))
            for (day_id, kind_id), ids in groups.items()
            if len(ids) >= 2
        ),
        key=lambda g: (g.day_id, g.kind_id),
    )


def stale_acks(slots: list[DupSlot], no_repeat_kinds: set[str], acks: list[DupAck]) -> list[DupAck]:
    """같은 날·종류의 중복이 사라져 더 이상 필요 없는 허용 기록 (evaluateDuplicates의 staleAcks)"""
    groups = {(g.day_id, g.kind_id) for g in find_duplicate_groups(slots, no_repeat_kinds)}
    return [a for a in acks if (a.day_id, a.kind_id) not in groups]
