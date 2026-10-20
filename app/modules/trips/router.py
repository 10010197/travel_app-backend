"""여행 API (API_SPEC 3.4~3.8, #15~#29). 규칙은 service.py에 있다."""

from fastapi import APIRouter, Response

from app.core.schemas import MealDef
from app.core.security import CurrentUserDep
from app.modules.trips import service
from app.modules.trips.schemas import (
    Companion,
    CompanionInput,
    CompanionPatch,
    CreateTripInput,
    DietCheck,
    DietCheckInput,
    DuplicateAck,
    MustPick,
    PutMustPicksInput,
    Slot,
    Trip,
    TripSummary,
    UpdateDayInput,
    UpdateSlotInput,
    UpdateSlotsStateInput,
    UpdateTripInput,
)

router = APIRouter(tags=["trips"])


@router.get("/trips", response_model=list[TripSummary])
def list_trips(user: CurrentUserDep) -> list[TripSummary]:
    return service.list_trips(user)


@router.post("/trips", response_model=Trip, status_code=201)
def create_trip(body: CreateTripInput, user: CurrentUserDep) -> Trip:
    return service.create_trip(user, body)


@router.get("/trips/{trip_id}", response_model=Trip)
def get_trip(trip_id: str, user: CurrentUserDep) -> Trip:
    return service.get_trip(user, trip_id)


@router.patch("/trips/{trip_id}", response_model=Trip)
def update_trip(trip_id: str, body: UpdateTripInput, user: CurrentUserDep) -> Trip:
    return service.update_trip(user, trip_id, body)


@router.delete("/trips/{trip_id}", status_code=204)
def delete_trip(trip_id: str, user: CurrentUserDep) -> Response:
    service.delete_trip(user, trip_id)
    return Response(status_code=204)


@router.patch("/trips/{trip_id}/days/{day_id}", response_model=Trip)
def set_day_area(trip_id: str, day_id: str, body: UpdateDayInput, user: CurrentUserDep) -> Trip:
    return service.set_day_area(user, trip_id, day_id, body)


@router.post("/trips/{trip_id}/days/{day_id}/slots", response_model=Slot, status_code=201)
def add_slot(trip_id: str, day_id: str, body: MealDef, user: CurrentUserDep) -> Slot:
    return service.add_slot(user, trip_id, day_id, body)


@router.patch("/trips/{trip_id}/slots", response_model=Trip)
def set_slots_state(trip_id: str, body: UpdateSlotsStateInput, user: CurrentUserDep) -> Trip:
    return service.set_slots_state(user, trip_id, body)


@router.patch("/slots/{slot_id}", response_model=Slot)
def update_slot(slot_id: str, body: UpdateSlotInput, user: CurrentUserDep) -> Slot:
    return service.update_slot(user, slot_id, body)


@router.post("/trips/{trip_id}/duplicate-acks", status_code=204)
def ack_duplicate(trip_id: str, body: DuplicateAck, user: CurrentUserDep) -> Response:
    service.ack_duplicate(user, trip_id, body)
    return Response(status_code=204)


@router.post("/trips/{trip_id}/companions", response_model=Companion, status_code=201)
def add_companion(trip_id: str, body: CompanionInput, user: CurrentUserDep) -> Companion:
    return service.add_companion(user, trip_id, body)


@router.patch("/trips/{trip_id}/companions/{companion_id}", response_model=Companion)
def update_companion(
    trip_id: str, companion_id: str, body: CompanionPatch, user: CurrentUserDep
) -> Companion:
    return service.update_companion(user, trip_id, companion_id, body)


@router.delete("/trips/{trip_id}/companions/{companion_id}", status_code=204)
def delete_companion(trip_id: str, companion_id: str, user: CurrentUserDep) -> Response:
    service.delete_companion(user, trip_id, companion_id)
    return Response(status_code=204)


@router.put("/slots/{slot_id}/diet-checks/{companion_id}", response_model=DietCheck)
def set_diet_check(
    slot_id: str, companion_id: str, body: DietCheckInput, user: CurrentUserDep
) -> DietCheck:
    return service.set_diet_check(user, slot_id, companion_id, body.checked)


@router.put("/trips/{trip_id}/must-picks", response_model=list[MustPick])
def put_must_picks(trip_id: str, body: PutMustPicksInput, user: CurrentUserDep) -> list[MustPick]:
    return service.put_must_picks(user, trip_id, body)
