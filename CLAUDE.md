# Wayfarer 백엔드

프론트엔드(`frontend/`)가 MSW 목으로 쓰던 API를 실제로 구현하는 FastAPI 서버. 데이터베이스와 인증은 Supabase.

- 구조 기준: `docs/ARCHITECTURE.md` (4장 백엔드, 5장 목 → 백엔드 대응표)
- 규칙 기준: `docs/BUSINESS_LOGIC.md` · API 계약: `docs/API_SPEC.md`, `frontend/src/api/schemas`
- DB 구조: `ERD.md` (이 레포), `docs/DATABASE.md` (무엇을 왜 저장하는지, API별 인덱스)
- 단계: `docs/IMPLEMENTATION_PLAN.md` Phase 2 (B1~B7)

## 현재 상태

| 단계 | 상태 | 내용 |
|---|---|---|
| B1 | ✅ | 프로젝트, `core/`(설정·오류·인증·호출 제한·로그), `db/`, 마이그레이션 + RLS, 마스터 데이터 시드, DB 테스트 |
| B2 | 🟡 | 서버가 쓰는 규칙만 옮김(`days`, `time_band`, `duplicate`, `geo`). `rule-fixtures` 복사는 아직 |
| B3 | ✅ | identity·catalog·trips 모듈 (API_SPEC #4~#29) |
| B4 | 🟡 | places 모듈 (#30~#36). 식당 제공자는 샘플 16곳(`integrations/places/sample.py`). Google Places 구현은 아직 |
| B5 | 🟡 | 메뉴 분류·식이 정규화는 사전 구현(`integrations/ai/dictionary.py`, 목과 같은 규칙). LangChain은 아직 |
| B6 | ✅ | sharing 모듈 (#37~#41) |
| B7 | — | 계약을 OpenAPI로 이전, 배포 |

## 명령어

`uv`로 관리한다. Python은 3.12 (`.python-version`). `uv`가 PATH에 없으면 `py -3.12 -m uv`로 부른다.

```bash
uv sync                                         # 의존성 설치 (.venv)
uv run uvicorn app.main:app --reload --port 8000
uv run pytest                                   # 전체 테스트 (DB 테스트 포함)
uv run ruff format . && uv run ruff check .
uv run mypy                                     # strict
uv run python -m app.seed.master_data --sql     # migrations → DB/init.sql, data/master-data → DB/data.sql 다시 만들기
uv run python -m app.seed.master_data           # Supabase에 마스터 데이터 upsert (service_role 키 필요)
```

의존성을 더할 때는 `uv add --bounds exact <패키지>`로 정확한 버전을 고정한다 (프론트와 같은 규칙).

## 구조

```
app/
  main.py            create_app(). 모든 라우터를 /api 아래에 붙인다
  core/              config, errors, security, rate_limit, logging
  db/session.py      Postgres 연결 풀. user_tx(user)=RLS 적용 / public_tx()=anon / service_tx()=RLS 우회
  db/supabase.py     supabase-py 클라이언트 (시드 upsert만 쓴다)
  routers/           경계에 속하지 않는 라우터 (health)
  modules/<경계>/    identity, catalog, trips, places, sharing
                     router.py → service.py → repository.py, schemas.py
  domain/            프론트 src/domain과 이름을 맞춘 순수 함수 (서버가 쓰는 것만)
  integrations/      ai/(ports.py + dictionary.py), places/(ports.py + models.py + sample.py)
  seed/master_data.py
DB/
  init.sql           스키마 전체 = supabase/migrations 합본. 자동 생성, 직접 고치지 않는다
  data.sql           초기 데이터(마스터 데이터). 자동 생성. Supabase 시드로 쓴다(config.toml)
supabase/
  config.toml        로컬 Supabase 설정
  migrations/        0001_catalog … 0007_query_support (스키마의 원본. 테이블 0001~0005, RLS 0006, 인덱스·요약 뷰 0007)
tests/
  core/ seed/ domain/  DB 없이 도는 테스트
  db/                마이그레이션·RLS 테스트와 API 흐름 테스트(test_api_flow.py) (supabase_stub.sql로 Supabase 흉내)
```

## 규칙

### 층

- router: 요청 파싱, `CurrentUserDep`, 서비스 호출, 응답 모델. 규칙 판단·DB 접근·외부 호출 금지.
- service: 비즈니스 규칙과 여러 테이블에 걸친 변경. 실패는 `AppError`로 던진다.
- repository: 테이블 읽기·쓰기만.
- domain: I/O 없는 결정론적 함수. 프론트 `src/domain`과 이름을 맞춘다(`evaluateDuplicates` → `evaluate_duplicates`).
- 다른 모듈의 데이터는 그 모듈의 **service**로 받는다. 다른 모듈의 repository를 직접 부르지 않는다.
- 프롬프트와 외부 API 호출은 `integrations/`에만 둔다(TECH_STACK 3장).

### API 계약

- 경로는 `frontend/src/api/endpoints.ts`와 같다. 앞에 `/api`가 붙는다.
- JSON 필드는 camelCase. Pydantic 모델에 `alias_generator=to_camel`, `populate_by_name=True`를 쓴다.
- 오류는 항상 `{ "error": { "code", "message" } }`. 코드는 `core/errors.py`의 `ErrorCode`만 쓴다(프론트 `ApiError.code`와 같은 문자열). 검증 실패는 422가 아니라 400 `VALIDATION_ERROR`.
- 계약을 바꾸면 `frontend/src/api/schemas`와 `frontend/CLAUDE.md` 표를 같은 커밋에서 바꾼다(B7 전까지 프론트 zod가 원본).

### 인증

- 모든 보호된 엔드포인트는 `user: CurrentUserDep`를 받는다. 사용자 id는 토큰의 `sub`만 쓴다. 요청 본문의 사용자 id는 믿지 않는다.
- 게스트 = 토큰의 `is_anonymous`. 로그인 전용 기능은 `require_registered(user)` (403 `LOGIN_REQUIRED`).
- 토큰 검증: `SUPABASE_JWT_SECRET`이 있으면 HS256, 없으면 `SUPABASE_URL`의 JWKS(ES256/RS256). 대상 `authenticated`, 발급자 `<SUPABASE_URL>/auth/v1`.
- `/auth/*`는 만들지 않는다. 프론트가 Supabase Auth를 직접 쓴다.

### 데이터베이스

- 스키마 변경은 새 마이그레이션 파일로만 한다. 이미 적용한 파일을 고치지 않는다(아직 원격에 적용하기 전인 B1 파일은 예외).
- 모든 public 테이블에 RLS를 켠다. 사용자 데이터는 `auth.uid()`, 여행에 딸린 데이터는 `public.is_trip_owner(trip_id)`.
- 정책 안에서 같은 테이블을 다시 조회하지 않는다. 무한 재귀 오류가 난다. `security definer` 도우미 함수로 우회한다(`has_any_trip`, `is_trip_owner`).
- 사용자 데이터를 가리키는 외래 키에는 그 열로 시작하는 인덱스를 둔다(`tests/db`가 자동 확인). 마스터 데이터를 가리키는 외래 키는 예외.
- 계산할 수 있는 값(지표, 목록 숫자)은 저장하지 않는다. 여행 목록 숫자는 `trip_summaries` 뷰가 센다.
- 외래 키 검사는 RLS를 거치지 않는다. 여행에 딸린 자식 행은 `(id, trip_id)` 복합 외래 키로 같은 여행 것만 가리키게 한다. 다른 사용자 소유 행을 가리킬 수 있는 열(`saved_place_id`, `source_saved_id`)은 정책의 `with check`에서 소유를 확인한다.
- 게스트 제한(여행 1개, 일행 저장 불가)은 서비스가 먼저 막고(409·403, 화면용 메시지), RLS가 한 번 더 막는다.
- API는 `db/session.py`로 Postgres에 직접 연결한다. 서비스가 `with user_tx(user) as conn:`으로 요청 하나를 트랜잭션 하나로 묶고 repository에 `conn`을 넘긴다. 트랜잭션마다 역할(`authenticated`)과 `request.jwt.claims`를 바꾸므로 RLS가 그대로 적용된다. 남의 행은 안 보이니 서비스는 404로 답한다.
- `service_tx()`(service_role, RLS 우회)는 sharing 공개 조회·의견 쓰기에서만, `admin_client()`는 시드에서만 쓴다.
- 시각은 응답 모델의 `Instant`가 UTC(`…Z`)로 바꾼다. 연결 시간대에 기대지 않는다(Windows `pgserver`는 시간대 이름을 모른다).
- 식당은 `place_id`만 저장한다. 이름·영업시간은 저장하지 않는다(Places 약관, C-8).

### 마스터 데이터

- 원본은 `data/master-data/*.json` 하나다. 프론트 레포의 `src/mocks/data/master-data`는 복사본이라, 바꾸면 그쪽에도 복사한다. 바꾸면 `--sql`로 `DB/data.sql`을 다시 만든다(`tests/seed`가 확인한다). 마이그레이션을 더해도 `--sql`로 `DB/init.sql`을 다시 만든다.
- 동네 id는 도시를 넘어 유일해야 한다(`areas.id`가 기본 키).

### 테스트

- `tests/db`는 빈 PostgreSQL에 `supabase_stub.sql` → 마이그레이션 → `DB/data.sql` → `supabase_grants.sql`을 적용하고, 역할(`anon`·`authenticated`)과 `request.jwt.claims`를 바꿔 RLS를 검증한다.
- DB 서버: `DATABASE_URL_TEST`가 있으면 그것, 없으면 `pgserver`(개발 의존성)가 임시 PostgreSQL을 띄운다. Docker 없이 돈다.
- 실패를 기대하는 RLS 테스트는 `with pytest.raises(...), as_user(...):` 순서로 쓴다.
- `tests/db/test_api_flow.py`는 같은 DB에 앱을 붙여(`DATABASE_URL`) 라우터 → 서비스 → RLS까지 부른다. 사용자는 autocommit 연결로 `auth.users`에 넣고 테스트 토큰(HS256)을 쓴다.
- 외부 API(LLM, Places)는 테스트에서 실제로 부르지 않는다. `integrations/ai/dictionary.py`, `integrations/places/sample.py`를 쓴다.
- 목 핸들러 테스트(`frontend/src/mocks/__tests__/handlers.test.ts`)의 시나리오를 모듈 테스트의 체크리스트로 쓴다.

### 로그

- 일행 이름·못 먹는 음식 원문·의견 작성자·토큰은 로그에 남기지 않는다. `core/logging.py`의 `RedactingFilter`가 dict 인자에서 가린다. 새 민감 필드는 `SENSITIVE_KEYS`에 더한다.

## 로컬 Supabase (Docker)

Docker Desktop(WSL 2 엔진)을 켜 두고, Supabase CLI는 설치하지 않고 `npx`로 버전을 고정해 부른다. `supabase/config.toml`은 커밋돼 있다(`project_id = "wayfarer"`, 익명 로그인 켬, analytics 끔).

```bash
npx -y supabase@2.121.0 start          # 컨테이너 시작. 처음이면 migrations + DB/data.sql 적용
npx -y supabase@2.121.0 status -o env  # URL·키 확인 → .env
npx -y supabase@2.121.0 db reset       # DB를 migrations + DB/data.sql로 다시 만들기
npx -y supabase@2.121.0 stop           # 멈추기 (데이터는 남는다)
```

- 주소: API `http://127.0.0.1:54321`, DB `postgresql://postgres:postgres@127.0.0.1:54322/postgres`, Studio `http://127.0.0.1:54323`
- `.env`는 `.env.example`을 복사해 `SUPABASE_URL`·`SUPABASE_ANON_KEY`·`SUPABASE_SERVICE_ROLE_KEY`를 채운다. `DATABASE_URL`은 위 DB 주소다. 로컬 Auth는 ES256으로 서명하므로 `SUPABASE_JWT_SECRET`은 **비워** JWKS로 검증한다(채우면 모든 토큰이 401).
- `DATABASE_URL_TEST`는 로컬 Supabase DB를 가리키지 않는다. `tests/db`는 빈 DB에 스텁부터 적용한다.
- analytics를 켜면 Windows에서 `vector` 컨테이너가 Docker 소켓에 붙지 못해 계속 재시작한다.
- 원격: `supabase link` → `supabase db push`.
- 프론트를 실제 서버에 붙이려면 `frontend`에서 `pnpm dev:real`(전부) 또는 `.env.partial` + `implementedEndpoints`(일부).
