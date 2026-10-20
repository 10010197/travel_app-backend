"""DB 테스트 준비: 빈 PostgreSQL에 Supabase 대역 → 마이그레이션 → 시드를 순서대로 적용한다.

- DATABASE_URL_TEST가 있으면 그 서버를 쓴다 (CI, Docker의 supabase/postgres 등)
- 없으면 pgserver(개발 의존성)로 임시 PostgreSQL을 띄운다. Docker가 없는 Windows에서도 돈다
테스트 세션마다 새 데이터베이스를 만들고 끝나면 지운다.
"""

import json
import os
import tempfile
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import psycopg
import pytest
from psycopg import sql

from app.seed.master_data import MIGRATIONS_DIR, SEED_SQL_PATH

MIGRATIONS = sorted(MIGRATIONS_DIR.glob("*.sql"))
HERE = Path(__file__).resolve().parent


@pytest.fixture(scope="session")
def server_url() -> Iterator[str]:
    url = os.environ.get("DATABASE_URL_TEST")
    if url:
        yield url
        return
    pgserver = pytest.importorskip("pgserver")
    with tempfile.TemporaryDirectory() as data_dir:
        server = pgserver.get_server(data_dir, cleanup_mode="stop")
        yield server.get_uri()
        server.cleanup()


@pytest.fixture(scope="session")
def database_url(server_url: str) -> Iterator[str]:
    """마이그레이션까지 적용한 테스트 전용 데이터베이스"""
    name = f"wayfarer_test_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(server_url, autocommit=True) as admin:
        admin.execute(sql.SQL("create database {}").format(sql.Identifier(name)))
    url = server_url.rsplit("/", 1)[0] + "/" + name
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute((HERE / "supabase_stub.sql").read_text(encoding="utf-8"))
        for migration in MIGRATIONS:
            conn.execute(migration.read_text(encoding="utf-8"))
        conn.execute(SEED_SQL_PATH.read_text(encoding="utf-8"))
        conn.execute((HERE / "supabase_grants.sql").read_text(encoding="utf-8"))
    yield url
    with psycopg.connect(server_url, autocommit=True) as admin:
        admin.execute(sql.SQL("drop database {} with (force)").format(sql.Identifier(name)))


@pytest.fixture
def db(database_url: str) -> Iterator[psycopg.Connection]:
    """테스트마다 트랜잭션 하나. 끝나면 되돌려 다음 테스트에 남지 않게 한다."""
    with psycopg.connect(database_url) as conn:
        yield conn
        conn.rollback()


def create_user(conn: psycopg.Connection, *, anonymous: bool = False) -> str:
    """auth.users에 사용자를 만든다 (가입 트리거가 프로필·설정을 만든다)."""
    user_id = str(uuid.uuid4())
    conn.execute("insert into auth.users (id, is_anonymous) values (%s, %s)", (user_id, anonymous))
    return user_id


@contextmanager
def as_user(
    conn: psycopg.Connection, user_id: str | None, *, anonymous: bool = False
) -> Iterator[None]:
    """그 사용자의 토큰으로 요청한 것처럼 역할과 클레임을 바꾼다. user_id가 None이면 토큰 없는 anon."""
    role = "anon" if user_id is None else "authenticated"
    claims = {} if user_id is None else {"sub": user_id, "role": role, "is_anonymous": anonymous}
    conn.execute("savepoint as_user")
    conn.execute(sql.SQL("set local role {}").format(sql.Identifier(role)))
    conn.execute("select set_config('request.jwt.claims', %s, true)", (json.dumps(claims),))
    try:
        yield
    except Exception:
        # 정책 위반 등으로 트랜잭션이 깨졌으면 이 블록 시작 전으로 되돌린다(역할·클레임도 함께 돌아온다).
        # 실패를 기대하는 테스트는 `with pytest.raises(...): with as_user(...):` 순서로 쓴다
        conn.execute("rollback to savepoint as_user")
        raise
    else:
        conn.execute("reset role")
        conn.execute("select set_config('request.jwt.claims', '', true)")
        conn.execute("release savepoint as_user")
