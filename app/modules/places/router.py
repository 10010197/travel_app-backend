"""식당·맛집 모음 API (API_SPEC 3.9·3.10, #30~#36)."""

from fastapi import APIRouter, Query, Response

from app.core.security import CurrentUserDep
from app.modules.places import service
from app.modules.places.schemas import (
    PlaceDetail,
    PlaceSearchResponse,
    SavedPlace,
    SavePlaceInput,
)

router = APIRouter(tags=["places"])


@router.get("/search/places", response_model=PlaceSearchResponse)
def search_places(
    user: CurrentUserDep, slot_id: str = Query(alias="slotId"), q: str | None = None
) -> PlaceSearchResponse:
    return service.search_for_slot(user, slot_id, q)


@router.get("/search/places/city", response_model=PlaceSearchResponse)
def search_city_places(
    user: CurrentUserDep, city_id: str = Query(alias="cityId"), q: str | None = None
) -> PlaceSearchResponse:
    return service.search_city(user, city_id, q)


@router.get("/places", response_model=list[PlaceDetail])
def get_places(_user: CurrentUserDep, ids: str = "") -> list[PlaceDetail]:
    return service.get_places(ids)


@router.get("/places/{place_id}", response_model=PlaceDetail)
def get_place(place_id: str, _user: CurrentUserDep) -> PlaceDetail:
    return service.get_place_detail(place_id)


@router.get("/collection", response_model=list[SavedPlace])
def list_collection(
    user: CurrentUserDep, city_id: str | None = Query(default=None, alias="cityId")
) -> list[SavedPlace]:
    return service.list_collection(user, city_id)


@router.post("/collection", response_model=SavedPlace, status_code=201)
def save_place(body: SavePlaceInput, user: CurrentUserDep, response: Response) -> SavedPlace:
    saved, created = service.save_place(user, body)
    response.status_code = 201 if created else 200
    return saved


@router.delete("/collection/{saved_place_id}", status_code=204)
def delete_saved_place(saved_place_id: str, user: CurrentUserDep) -> Response:
    service.delete_saved_place(user, saved_place_id)
    return Response(status_code=204)
