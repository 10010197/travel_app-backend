"""공통 테스트 준비: 테스트용 설정과 토큰 발급 도구.

실제 Supabase 없이 돌도록 HS256 공유 비밀로 토큰을 직접 만든다(core/security.py가 같은 비밀로 검증한다).
"""

import time
from collections.abc import Iterator

import jwt
import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings

TEST_SECRET = "test-secret-at-least-32-bytes-long-for-hs256"
TEST_SUPABASE_URL = "http://supabase.test"


@pytest.fixture(autouse=True)
def test_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """테스트마다 같은 설정으로 시작한다. 테스트 안에서 환경변수를 바꾸면 get_settings.cache_clear()를 부른다."""
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("SUPABASE_URL", TEST_SUPABASE_URL)
    monkeypatch.setenv("SUPABASE_JWT_SECRET", TEST_SECRET)
    monkeypatch.setenv("CORS_ORIGINS", "")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def make_token(
    sub: str = "00000000-0000-0000-0000-000000000001",
    *,
    anonymous: bool = False,
    expires_in: int = 3600,
    audience: str = "authenticated",
    issuer: str = f"{TEST_SUPABASE_URL}/auth/v1",
    secret: str = TEST_SECRET,
) -> str:
    """Supabase Auth가 주는 Access Token과 같은 모양의 토큰"""
    now = int(time.time())
    return jwt.encode(
        {
            "sub": sub,
            "aud": audience,
            "iss": issuer,
            "iat": now,
            "exp": now + expires_in,
            "role": "authenticated",
            "is_anonymous": anonymous,
        },
        secret,
        algorithm="HS256",
    )


@pytest.fixture
def client() -> Iterator[TestClient]:
    from app.main import create_app

    with TestClient(create_app(), raise_server_exceptions=False) as test_client:
        yield test_client
