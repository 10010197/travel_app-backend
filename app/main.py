"""FastAPI 앱 진입점.

실행: `uv run uvicorn app.main:app --reload --port 8000`
프론트 개발 서버(.env.real/.env.partial)는 /api를 이 서버로 넘긴다(Vite proxy, 경로 그대로).
그래서 모든 라우터를 /api 아래에 붙인다. 계약 경로는 frontend/src/api/endpoints.ts와 같다.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.errors import install_error_handlers
from app.core.logging import configure_logging
from app.db.session import close_pool
from app.modules.catalog.router import router as catalog_router
from app.modules.identity.router import router as identity_router
from app.modules.places.router import router as places_router
from app.modules.sharing.router import router as sharing_router
from app.modules.trips.router import router as trips_router
from app.routers import health

API_PREFIX = "/api"


@asynccontextmanager
async def _lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    close_pool()


def create_app() -> FastAPI:
    """앱을 만든다. 테스트는 설정을 바꾼 뒤 새로 만들어 쓴다."""
    settings = get_settings()
    if settings.environment != "test":
        # 테스트는 pytest가 로그를 모으므로 루트 핸들러를 바꾸지 않는다
        configure_logging()

    app = FastAPI(
        title="Wayfarer API",
        version="0.1.0",
        docs_url=f"{API_PREFIX}/docs",
        openapi_url=f"{API_PREFIX}/openapi.json",
        lifespan=_lifespan,
    )
    install_error_handlers(app)
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_methods=["*"],
            allow_headers=["Authorization", "Content-Type"],
        )

    api = APIRouter(prefix=API_PREFIX)
    api.include_router(health.router)
    api.include_router(identity_router)
    api.include_router(catalog_router)
    api.include_router(trips_router)
    api.include_router(places_router)
    api.include_router(sharing_router)
    app.include_router(api)
    return app


app = create_app()
