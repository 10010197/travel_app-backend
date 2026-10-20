"""마스터 데이터 API (API_SPEC 3.3, #11~#14)."""

from fastapi import APIRouter

from app.core.security import CurrentUserDep
from app.modules.catalog import service
from app.modules.catalog.schemas import (
    City,
    CitySummary,
    ClassifyMenuInput,
    ClassifyMenuResult,
    MenuKind,
)

router = APIRouter(tags=["catalog"])


@router.get("/cities", response_model=list[CitySummary])
def list_cities() -> list[CitySummary]:
    return service.list_cities()


@router.get("/cities/{city_id}", response_model=City)
def get_city(city_id: str) -> City:
    return service.get_city(city_id)


@router.get("/menu-kinds", response_model=list[MenuKind])
def list_menu_kinds() -> list[MenuKind]:
    return service.list_menu_kinds()


@router.post("/menu-kinds/classify", response_model=ClassifyMenuResult)
def classify_menu(body: ClassifyMenuInput, _user: CurrentUserDep) -> ClassifyMenuResult:
    return service.classify_menu(body.menu)
