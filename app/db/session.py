"""Postgres 연결과 요청 단위 트랜잭션 (TECH_STACK 4장 3).

API는 Supabase Postgres에 직접 연결한다. 여행 만들기·기간 변경·일괄 상태 변경처럼 여러 표를 한 번에 바꾸는
일이 많아서, 한 요청을 한 트랜잭션으로 묶어야 일부만 바뀐 채로 남지 않는다(PostgREST로는 요청마다 따로 커밋된다).

RLS는 그대로 쓴다. 트랜잭션을 열 때 Supabase/PostgREST와 같은 방식으로 역할과 JWT 클레임을 바꾼다.
- user_tx(user): 역할 authenticated + 토큰의 sub·is_anonymous. RLS가 그 사용자의 행만 보여 준다
- public_tx(): 역할 anon. 마스터 데이터 읽기용
- service_tx(): 역할 service_role(RLS 우회). 공유 공개 조회·의견 쓰기에서만 쓴다

서비스 층이 `with user_tx(user) as conn:`으로 열고 repository 함수에 conn을 넘긴다.
블록이 오류 없이 끝나면 커밋, 예외(AppError 포함)가 나면 되돌린다.
"""

import json
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from typing import Any

import psycopg
from psycopg.rows import DictRow, dict_row
from psycopg_pool import ConnectionPool

from app.core.config import get_settings
from app.core.security import CurrentUser

Conn = psycopg.Connection[DictRow]

_pool: ConnectionPool[Conn] | None = None


def _get_pool() -> ConnectionPool[Conn]:
    global _pool
    if _pool is None:
        settings = get_settings()
        url = settings.database_url.get_secret_value()
        if not url:
            raise RuntimeError("DATABASE_URL이 없어요. .env에 넣어 주세요.")
        _pool = ConnectionPool(
            url,
            connection_class=psycopg.Connection[DictRow],
            kwargs={"row_factory": dict_row},
            min_size=1,
            max_size=settings.db_pool_max_size,
            # 꺼낼 때마다 연결이 살아 있는지 확인한다. DB가 재시작되거나 네트워크가 끊긴 뒤
            # 죽은 연결로 요청이 500이 나지 않게 한다(죽었으면 새 연결로 바꿔 준다)
            check=ConnectionPool.check_connection,
            open=True,
        )
    return _pool


def close_pool() -> None:
    """앱이 끝날 때 연결을 닫는다 (main.py lifespan)."""
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


@contextmanager
def _transaction(role: str, claims: dict[str, Any]) -> Iterator[Conn]:
    with _get_pool().connection() as conn:
        # set_config(…, true) = SET LOCAL: 이 트랜잭션이 끝나면 원래 역할로 돌아온다
        conn.execute(
            "select set_config('role', %s, true), set_config('request.jwt.claims', %s, true)",
            (role, json.dumps(claims)),
        )
        yield conn


def user_tx(user: CurrentUser) -> AbstractContextManager[Conn]:
    """그 사용자의 권한(RLS)으로 트랜잭션을 연다."""
    claims = {"sub": user.id, "role": "authenticated", "is_anonymous": user.is_anonymous}
    return _transaction("authenticated", claims)


def public_tx() -> AbstractContextManager[Conn]:
    """토큰 없는 요청의 권한(anon)으로 연다. 마스터 데이터만 읽을 수 있다."""
    return _transaction("anon", {"role": "anon"})


def service_tx() -> AbstractContextManager[Conn]:
    """RLS를 건너뛴다. 공유 공개 조회와 의견 쓰기(sharing 모듈)에서만 쓴다."""
    return _transaction("service_role", {"role": "service_role"})
