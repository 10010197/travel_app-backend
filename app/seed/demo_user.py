"""개발용 데모 계정 (로컬 Supabase 전용).

Google·카카오 OAuth 앱을 등록하기 전까지, 프론트의 개발용 로그인("데모 계정으로 로그인")이 이 계정을 쓴다.

- `uv run python -m app.seed.demo_user`
- 계정: demo@wayfarer.test, 이름 "데모" (이메일 확인 완료 상태로 만든다). 이미 있으면 그대로 둔다
- 비밀번호: .env의 DEMO_USER_PASSWORD. 없으면 새로 만들어 .env에 적는다(커밋하지 않는 파일)
- SUPABASE_URL이 로컬(127.0.0.1·localhost)일 때만 돈다. 원격 프로젝트에는 만들지 않는다
"""

import secrets
import sys
from pathlib import Path
from urllib.parse import urlparse

import httpx

from app.core.config import get_settings

DEMO_EMAIL = "demo@wayfarer.test"
DEMO_NAME = "데모"
ENV_PATH = Path(__file__).resolve().parents[2] / ".env"
PASSWORD_KEY = "DEMO_USER_PASSWORD"


def _password() -> str:
    """.env의 비밀번호. 없으면 만들어서 .env 끝에 적는다."""
    lines = ENV_PATH.read_text(encoding="utf-8").splitlines() if ENV_PATH.exists() else []
    for line in lines:
        if line.startswith(f"{PASSWORD_KEY}=") and line.split("=", 1)[1].strip():
            return line.split("=", 1)[1].strip()
    password = secrets.token_urlsafe(18)
    lines = [line for line in lines if not line.startswith(f"{PASSWORD_KEY}=")]
    lines += [
        "",
        "# 개발용 데모 계정 비밀번호 (app/seed/demo_user.py가 만든다)",
        f"{PASSWORD_KEY}={password}",
    ]
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return password


def main() -> None:
    settings = get_settings()
    if urlparse(settings.supabase_url).hostname not in ("127.0.0.1", "localhost"):
        sys.exit("로컬 Supabase(SUPABASE_URL=127.0.0.1)에서만 데모 계정을 만들어요.")
    key = settings.supabase_service_role_key.get_secret_value()
    headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    base = f"{settings.supabase_url.rstrip('/')}/auth/v1/admin/users"

    with httpx.Client(timeout=30) as client:
        users = client.get(base, headers=headers, params={"per_page": 1000})
        users.raise_for_status()
        if any(u.get("email") == DEMO_EMAIL for u in users.json().get("users", [])):
            print(f"데모 계정이 이미 있어요: {DEMO_EMAIL} (비밀번호는 .env의 {PASSWORD_KEY})")
            return
        created = client.post(
            base,
            headers=headers,
            json={
                "email": DEMO_EMAIL,
                "password": _password(),
                "email_confirm": True,
                "user_metadata": {"full_name": DEMO_NAME},
            },
        )
        created.raise_for_status()
    print(f"데모 계정을 만들었어요: {DEMO_EMAIL} (비밀번호는 .env의 {PASSWORD_KEY})")


if __name__ == "__main__":
    main()
