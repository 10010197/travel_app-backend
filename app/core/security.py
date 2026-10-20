"""인증 의존성 (TECH_STACK 4장 1~2).

브라우저는 Supabase Auth가 발급한 Access Token을 Authorization: Bearer로 보낸다. 게스트도 익명 로그인 토큰을 쓴다.
여기서 서명·발급자·대상·만료를 확인하고 CurrentUser를 만든다. 요청 본문의 사용자 ID는 믿지 않는다.
라우터는 `user: CurrentUserDep`로 받는다. 공유 공개 엔드포인트처럼 토큰이 없어도 되는 곳은 OptionalUserDep를 쓴다.
"""

from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated, Any

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt.types import Options

from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCode

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True, slots=True)
class CurrentUser:
    """토큰에서 꺼낸 사용자. access_token은 RLS가 적용되는 DB 클라이언트를 만들 때 넘긴다."""

    id: str
    is_anonymous: bool
    access_token: str
    # 토큰의 email 클레임 (GET /me). 게스트는 없다
    email: str | None = None


def _unauthorized(message: str = "로그인이 필요해요.") -> AppError:
    return AppError(401, ErrorCode.UNAUTHORIZED, message)


@lru_cache
def _jwks_client(url: str) -> jwt.PyJWKClient:
    # 공개 키를 받아 캐시한다. 키가 바뀌면(kid 불일치) PyJWKClient가 다시 받는다
    return jwt.PyJWKClient(url, cache_keys=True)


def decode_access_token(token: str, settings: Settings) -> dict[str, Any]:
    """Supabase Access Token을 검증하고 클레임을 돌려준다. 실패하면 401 AppError."""
    secret = settings.supabase_jwt_secret.get_secret_value()
    options: Options = {"require": ["exp", "sub", "aud"]}
    try:
        if secret:
            return jwt.decode(
                token,
                secret,
                algorithms=["HS256"],
                audience=settings.jwt_audience,
                issuer=settings.jwt_issuer if settings.supabase_url else None,
                options=options,
            )
        if not settings.supabase_url:
            raise _unauthorized("인증 설정이 없어요.")
        signing_key = _jwks_client(settings.jwks_url).get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256", "RS256"],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            options=options,
        )
    except jwt.ExpiredSignatureError as exc:
        raise _unauthorized("로그인이 만료됐어요. 다시 로그인해 주세요.") from exc
    except (jwt.InvalidTokenError, jwt.PyJWKClientError) as exc:
        raise _unauthorized() from exc


def _user_from(credentials: HTTPAuthorizationCredentials, settings: Settings) -> CurrentUser:
    claims = decode_access_token(credentials.credentials, settings)
    return CurrentUser(
        id=str(claims["sub"]),
        is_anonymous=bool(claims.get("is_anonymous", False)),
        access_token=credentials.credentials,
        email=claims.get("email") or None,
    )


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> CurrentUser:
    """보호된 엔드포인트용. 토큰이 없거나 틀리면 401 UNAUTHORIZED."""
    if credentials is None:
        raise _unauthorized()
    return _user_from(credentials, settings)


def get_optional_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> CurrentUser | None:
    """토큰이 없어도 되는 엔드포인트용 (공유 페이지). 토큰이 있는데 틀리면 401."""
    return None if credentials is None else _user_from(credentials, settings)


def require_registered(user: CurrentUser) -> None:
    """로그인 사용자 전용 기능(공유 링크, 자주 함께 가는 일행)에서 게스트를 막는다 (F-18 7)."""
    if user.is_anonymous:
        raise AppError(403, ErrorCode.LOGIN_REQUIRED, "로그인하면 쓸 수 있어요.")


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]
OptionalUserDep = Annotated[CurrentUser | None, Depends(get_optional_user)]
