"""core/ 검증: 오류 형식, 인증 의존성, 설정, 호출 제한, 로그 가리기."""

import logging

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.errors import AppError, ErrorCode, install_error_handlers
from app.core.logging import RedactingFilter
from app.core.rate_limit import RateLimiter
from app.core.security import CurrentUserDep, OptionalUserDep, require_registered
from tests.conftest import make_token


class Body(BaseModel):
    name: str = Field(min_length=1, max_length=12)


def probe_app() -> TestClient:
    """core만 붙인 작은 앱. 실제 라우터가 생기기 전(B1)에 의존성과 오류 형식을 확인한다."""
    app = FastAPI()
    install_error_handlers(app)
    router = APIRouter()

    @router.get("/me")
    def me(user: CurrentUserDep) -> dict[str, object]:
        return {"id": user.id, "isAnonymous": user.is_anonymous}

    @router.get("/public")
    def public(user: OptionalUserDep) -> dict[str, object]:
        return {"loggedIn": user is not None}

    @router.post("/share")
    def share(user: CurrentUserDep) -> dict[str, str]:
        require_registered(user)
        return {"ok": "yes"}

    @router.post("/body")
    def body(payload: Body) -> dict[str, str]:
        return {"name": payload.name}

    @router.get("/conflict")
    def conflict() -> None:
        raise AppError(
            409, ErrorCode.GUEST_TRIP_LIMIT, "로그인하지 않으면 여행을 하나만 만들 수 있어요."
        )

    @router.get("/boom")
    def boom() -> None:
        raise RuntimeError("unexpected")

    app.include_router(router)
    return TestClient(app, raise_server_exceptions=False)


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------- 앱 ----------


def test_health_is_served_under_api(client: TestClient) -> None:
    assert client.get("/api/health").json() == {"status": "ok"}
    assert client.get("/api/openapi.json").status_code == 200


def test_unknown_path_uses_error_format(client: TestClient) -> None:
    res = client.get("/api/nowhere")
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "NOT_FOUND"


# ---------- 오류 형식 ----------


def test_app_error_and_validation_error_use_contract_format() -> None:
    api = probe_app()
    res = api.get("/conflict")
    assert res.status_code == 409
    assert res.json() == {
        "error": {
            "code": "GUEST_TRIP_LIMIT",
            "message": "로그인하지 않으면 여행을 하나만 만들 수 있어요.",
        }
    }

    res = api.post("/body", json={"name": ""})
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "VALIDATION_ERROR"
    assert res.json()["error"]["message"].startswith("name:")


def test_unexpected_error_hides_details() -> None:
    res = probe_app().get("/boom")
    assert res.status_code == 500
    assert res.json() == {
        "error": {"code": "INTERNAL_ERROR", "message": "잠시 후 다시 시도해 주세요."}
    }


# ---------- 인증 ----------


def test_valid_token_gives_current_user() -> None:
    res = probe_app().get("/me", headers=auth(make_token("user-1", anonymous=True)))
    assert res.json() == {"id": "user-1", "isAnonymous": True}


@pytest.mark.parametrize(
    ("token", "message"),
    [
        (None, "로그인이 필요해요."),
        ("not-a-jwt", "로그인이 필요해요."),
        (make_token(expires_in=-10), "로그인이 만료됐어요. 다시 로그인해 주세요."),
        (make_token(audience="other"), "로그인이 필요해요."),
        (make_token(issuer="https://evil.test/auth/v1"), "로그인이 필요해요."),
        (make_token(secret="another-secret-that-is-also-32-bytes!!"), "로그인이 필요해요."),
    ],
    ids=["missing", "garbage", "expired", "wrong-audience", "wrong-issuer", "wrong-signature"],
)
def test_bad_tokens_are_401(token: str | None, message: str) -> None:
    res = probe_app().get("/me", headers=auth(token) if token else {})
    assert res.status_code == 401
    assert res.json() == {"error": {"code": "UNAUTHORIZED", "message": message}}


def test_optional_user_allows_no_token_but_rejects_bad_token() -> None:
    api = probe_app()
    assert api.get("/public").json() == {"loggedIn": False}
    assert api.get("/public", headers=auth(make_token())).json() == {"loggedIn": True}
    assert api.get("/public", headers=auth("bad")).status_code == 401


def test_guest_is_blocked_from_registered_only_features() -> None:
    api = probe_app()
    res = api.post("/share", headers=auth(make_token(anonymous=True)))
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "LOGIN_REQUIRED"
    assert api.post("/share", headers=auth(make_token())).status_code == 200


# ---------- 설정 ----------


def test_cors_origins_accept_comma_separated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "https://a.app, https://b.app")
    get_settings.cache_clear()
    assert get_settings().cors_origins == ["https://a.app", "https://b.app"]
    assert get_settings().jwks_url == "http://supabase.test/auth/v1/.well-known/jwks.json"


# ---------- 호출 제한 ----------


def test_rate_limiter_blocks_after_limit_and_recovers_after_window() -> None:
    now = [0.0]
    limiter = RateLimiter(limit=2, window_seconds=60, clock=lambda: now[0])
    limiter.hit("search:u1")
    limiter.hit("search:u1")
    with pytest.raises(AppError) as blocked:
        limiter.hit("search:u1")
    assert blocked.value.status == 429
    limiter.hit("search:u2")  # 다른 사용자는 따로 센다
    now[0] = 61
    limiter.hit("search:u1")


# ---------- 로그 ----------


def test_redacting_filter_hides_diet_text_and_names() -> None:
    record = logging.LogRecord(
        "x",
        logging.INFO,
        __file__,
        1,
        "companion %s",
        ({"name": "민지", "foodsRaw": "비건", "strictness": "flex"},),
        None,
    )
    RedactingFilter().filter(record)
    assert (
        record.getMessage() == "companion {'name': '***', 'foodsRaw': '***', 'strictness': 'flex'}"
    )
