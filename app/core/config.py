"""환경 설정 (pydantic-settings).

모델명·키·한도·타임아웃은 이 모듈에서만 읽는다(TECH_STACK 5장). 값은 환경변수 또는 backend/.env에서 온다.
main.py, core/security.py, db/supabase.py, seed 스크립트가 get_settings()로 같은 설정을 쓴다.
"""

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """서버 설정. 이름은 환경변수 이름과 같다(대소문자 무시)."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"

    # Supabase (B1). URL·키가 비어 있으면 DB가 필요한 기능만 실패하고 앱은 뜬다(헬스 체크·테스트용).
    supabase_url: str = ""
    supabase_anon_key: SecretStr = SecretStr("")
    supabase_service_role_key: SecretStr = SecretStr("")
    # 토큰 검증 방식: 레거시 HS256 공유 비밀이 있으면 그것을, 없으면 프로젝트 JWKS(비대칭 서명 키)를 쓴다.
    supabase_jwt_secret: SecretStr = SecretStr("")
    jwt_audience: str = "authenticated"
    # API가 쓰는 Postgres 직접 연결 (app/db/session.py). 요청마다 역할·클레임을 바꿔 RLS를 그대로 적용한다.
    # 로컬: postgresql://postgres:postgres@127.0.0.1:54322/postgres, 원격: Supabase의 Session pooler 주소
    database_url: SecretStr = SecretStr("")
    db_pool_max_size: int = 10

    # 브라우저 출처. 개발은 Vite proxy로 같은 출처라 비워도 되지만, 배포(Vercel → Render)에는 필요하다.
    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)

    # 외부 API (B4·B5에서 사용)
    google_places_api_key: SecretStr = SecretStr("")
    llm_provider: str = "openai"
    llm_model: str = ""
    llm_api_key: SecretStr = SecretStr("")
    external_timeout_seconds: float = 10.0

    # 사용자별 호출 한도 (TECH_STACK 4-1). 한 시간 동안 허용하는 횟수
    search_limit_per_hour: int = 60
    comment_limit_per_hour: int = 30

    @property
    def jwt_issuer(self) -> str:
        """Supabase Auth가 발급한 토큰의 iss 값"""
        return f"{self.supabase_url.rstrip('/')}/auth/v1"

    @property
    def jwks_url(self) -> str:
        return f"{self.jwt_issuer}/.well-known/jwks.json"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        """CORS_ORIGINS="https://a.app,https://b.app" 처럼 쉼표로 이은 문자열을 목록으로 바꾼다."""
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    """프로세스에서 한 번만 읽는다. 테스트는 get_settings.cache_clear() 후 환경변수를 바꾼다."""
    return Settings()
