"""Supabase 클라이언트 (TECH_STACK 2장 supabase-py, 4장 3).

두 종류만 만든다.
- user_client(user): 사용자의 Access Token을 그대로 실어 보낸다. RLS가 그 사용자의 행만 보여 준다.
  모든 사용자 데이터 읽기·쓰기는 이 클라이언트로 한다(repository 층).
- admin_client(): service_role 키. RLS를 건너뛰므로 공유 공개 조회(sharing 모듈)와 시드 스크립트에서만 쓴다.
"""

from functools import lru_cache

from app.core.config import get_settings
from app.core.security import CurrentUser
from supabase import Client, ClientOptions, create_client


def user_client(user: CurrentUser) -> Client:
    """요청마다 만든다. 토큰이 사용자마다 다르므로 캐시하지 않는다."""
    settings = get_settings()
    return create_client(
        settings.supabase_url,
        settings.supabase_anon_key.get_secret_value(),
        options=ClientOptions(
            headers={"Authorization": f"Bearer {user.access_token}"},
            auto_refresh_token=False,
            persist_session=False,
        ),
    )


@lru_cache
def admin_client() -> Client:
    """RLS를 우회한다. 공유 공개 조회와 시드 외에는 쓰지 않는다."""
    settings = get_settings()
    return create_client(
        settings.supabase_url,
        settings.supabase_service_role_key.get_secret_value(),
        options=ClientOptions(auto_refresh_token=False, persist_session=False),
    )
