-- 자동 생성 파일: app/seed/master_data.py --sql
-- 스키마 전체 (테이블·제약·RLS·인덱스·뷰). 원본은 supabase/migrations/*.sql. 직접 고치지 않는다.
-- auth 스키마와 anon·authenticated·service_role 역할이 있는 빈 Supabase DB에 적용한다.

-- ===== 0001_catalog.sql =====

-- 마스터 데이터 (catalog 경계). 원본은 data/master-data/*.json, app/seed/master_data.py가 채운다.
-- 사용자는 읽기만 한다(0006 RLS). 쓰기는 service_role(시드)만.

create table public.menu_kinds (
  id                  text primary key,
  label               text not null,
  -- 하루에 같은 종류가 2번 나와도 되는지 (R-01: 밥 true, 면 false)
  allow_daily_repeat  boolean not null,
  sort_order          integer not null
);

create table public.food_tags (
  id          text primary key,
  label       text not null,
  -- 상위 태그(육류, 해산물). 상위 태그는 하위 태그를 가진 메뉴에도 걸린다 (F-02)
  parent_id   text references public.food_tags (id),
  sort_order  integer not null
);

-- 사람들이 흔히 쓰는 표현 → 태그 묶음 ("비건" → 육류·해산물·달걀·유제품)
create table public.food_tag_presets (
  label       text primary key,
  tags        text[] not null,
  sort_order  integer not null
);

create table public.cities (
  id            text primary key,
  name          text not null,
  country_code  text not null,
  -- IANA 시간대. 현지 오늘·영업시간 판단의 기준 (R-05, R-07)
  time_zone     text not null,
  center_lat    double precision not null,
  center_lng    double precision not null,
  sort_order    integer not null
);

-- 동네 id는 도시를 넘어 유일하다(끼니는 area_id만 들고 있다). 새 도시는 겹치지 않게 id를 짓는다.
create table public.areas (
  id             text primary key,
  city_id        text not null references public.cities (id) on delete cascade,
  name           text not null,
  center_lat     double precision not null,
  center_lng     double precision not null,
  -- 식당 찾기 범위: 이 반경 × 1.5 (F-09)
  radius_meters  integer not null check (radius_meters > 0),
  sort_order     integer not null
);
create index areas_city_idx on public.areas (city_id);

-- 도시 필수 메뉴 (F-07). is_signature면 새 여행의 꼭 먹을 목록에서 미리 체크된다
create table public.must_menus (
  id            text primary key,
  city_id       text not null references public.cities (id) on delete cascade,
  name          text not null,
  kind_id       text not null references public.menu_kinds (id),
  description   text not null,
  food_tags     text[] not null default '{}',
  is_signature  boolean not null default false,
  sort_order    integer not null
);
create index must_menus_city_idx on public.must_menus (city_id);

-- ===== 0002_identity.sql =====

-- 사용자 (identity 경계). 계정 자체는 Supabase Auth(auth.users)가 갖고, 여기에는 앱 데이터만 둔다.

create table public.profiles (
  id            uuid primary key references auth.users (id) on delete cascade,
  display_name  text,
  created_at    timestamptz not null default now()
);

-- 마이 설정 (F-16). 기본 끼니는 새 여행의 끼니 기본값
create table public.user_settings (
  user_id             uuid primary key references auth.users (id) on delete cascade,
  default_meals       text[] not null default array['점심', '저녁']
                      check (cardinality(default_meals) >= 1),
  time_display        text not null default 'auto' check (time_display in ('auto')),
  notify_empty_slots  boolean not null default false
);

-- 자주 함께 가는 일행 (F-16). 식이 원문은 본인만 본다(0006 RLS). 게스트는 저장할 수 없다(F-18 7)
create table public.saved_companions (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null default auth.uid() references auth.users (id) on delete cascade,
  name        text not null check (char_length(name) between 1 and 12),
  foods_raw   text not null check (char_length(foods_raw) <= 60),
  food_tags   text[] not null default '{}',
  strictness  text not null check (strictness in ('avoid', 'flex')),
  created_at  timestamptz not null default now()
);
create index saved_companions_user_idx on public.saved_companions (user_id);

-- 가입(익명 포함)하면 프로필과 기본 설정을 만든다.
-- 익명 계정에 소셜 계정을 연결해도 사용자 id가 같으므로 같은 행이 이어진다 (F-18 6)
create function public.handle_new_user() returns trigger
language plpgsql security definer set search_path = ''
as $$
begin
  insert into public.profiles (id, display_name)
  values (new.id, new.raw_user_meta_data ->> 'full_name');
  insert into public.user_settings (user_id) values (new.id);
  return new;
end;
$$;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- ===== 0003_trips.sql =====

-- 여행 계획 (planning 경계, F-01~F-08, F-17). 규칙의 대부분은 app/modules/trips/services가 지키고,
-- 여기서는 깨지면 안 되는 값만 제약으로 막는다.

create function public.set_updated_at() returns trigger
language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create table public.trips (
  id             uuid primary key default gen_random_uuid(),
  owner_id       uuid not null default auth.uid() references auth.users (id) on delete cascade,
  city_id        text not null references public.cities (id),
  title          text not null check (char_length(title) between 1 and 30),
  start_date     date,
  end_date       date,
  -- [{ "name": "점심", "timeBand": "lunch" }, ...] 순서 그대로
  default_meals  jsonb not null check (jsonb_typeof(default_meals) = 'array'),
  -- 읽기 전용 공유 링크 (F-11). null이면 공유 꺼짐
  share_token    text unique,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now(),
  -- 기간은 둘 다 있거나 둘 다 없다. 최대 14일 (F-01)
  constraint trips_dates_pair check ((start_date is null) = (end_date is null)),
  constraint trips_dates_order check (end_date >= start_date),
  constraint trips_dates_max check (end_date - start_date + 1 <= 14)
);
create index trips_owner_idx on public.trips (owner_id);
create trigger trips_updated_at before update on public.trips
  for each row execute function public.set_updated_at();

create table public.trip_days (
  id          uuid primary key default gen_random_uuid(),
  trip_id     uuid not null references public.trips (id) on delete cascade,
  date        date not null,
  -- D1, D2 … 기간을 바꾸면 서비스가 날짜 순으로 다시 매긴다 (중간 상태를 허용하려고 검사를 트랜잭션 끝으로 미룬다)
  day_number  integer not null check (day_number >= 1),
  area_id     text references public.areas (id),
  constraint trip_days_date_unique unique (trip_id, date),
  constraint trip_days_number_unique unique (trip_id, day_number) deferrable initially deferred,
  -- 자식 행이 같은 여행의 날짜만 가리키게 하는 복합 외래 키의 대상 (외래 키 검사는 RLS를 거치지 않는다)
  constraint trip_days_id_trip_unique unique (id, trip_id)
);

create table public.trip_companions (
  id               uuid primary key default gen_random_uuid(),
  trip_id          uuid not null references public.trips (id) on delete cascade,
  name             text not null check (char_length(name) between 1 and 12),
  foods_raw        text not null check (char_length(foods_raw) <= 60),
  food_tags        text[] not null default '{}',
  tag_status       text not null default 'ok' check (tag_status in ('ok', 'needs_check')),
  strictness       text not null check (strictness in ('avoid', 'flex')),
  source_saved_id  uuid references public.saved_companions (id) on delete set null,
  created_at       timestamptz not null default now(),
  constraint trip_companions_id_trip_unique unique (id, trip_id)
);
create index trip_companions_trip_idx on public.trip_companions (trip_id);

-- 꼭 먹을 것 (F-07, C-1): 메뉴(필수 메뉴 또는 직접 추가)와 맛집 모음 식당을 한 목록에.
-- saved_place_id의 외래 키는 0004에서 붙인다 (맛집 모음 테이블이 그때 생긴다)
create table public.must_picks (
  id                   uuid primary key default gen_random_uuid(),
  trip_id              uuid not null references public.trips (id) on delete cascade,
  type                 text not null check (type in ('menu', 'place')),
  sort_order           integer not null,
  checked              boolean not null default false,
  must_menu_id         text references public.must_menus (id),
  custom_menu_name     text check (char_length(custom_menu_name) between 1 and 40),
  custom_menu_kind_id  text references public.menu_kinds (id),
  saved_place_id       uuid,
  constraint must_picks_source check (
    (type = 'menu' and saved_place_id is null
      and (must_menu_id is null) <> (custom_menu_name is null))
    or (type = 'place' and saved_place_id is not null
      and must_menu_id is null and custom_menu_name is null)
  ),
  constraint must_picks_id_trip_unique unique (id, trip_id)
);
create index must_picks_trip_idx on public.must_picks (trip_id);

-- 끼니. trip_id는 day에서 알 수 있지만, RLS를 한 번의 조회로 판단하려고 함께 둔다
create table public.slots (
  id               uuid primary key default gen_random_uuid(),
  trip_id          uuid not null references public.trips (id) on delete cascade,
  day_id           uuid not null,
  name             text not null check (char_length(name) between 1 and 12),
  -- R-06 시간대 7개. 정렬은 시간대 → sort_order
  time_band        text not null check (time_band in
                     ('morning', 'late_morning', 'lunch', 'afternoon', 'dinner', 'night', 'late_night')),
  sort_order       integer not null,
  -- F-06, F-17. 빠짐이어도 메뉴·식당은 남겨 "다시 넣기"로 그대로 돌아온다
  state            text not null default 'empty'
                     check (state in ('empty', 'filled', 'onsite', 'skipped')),
  menu             text check (char_length(menu) between 1 and 40),
  kind_id          text references public.menu_kinds (id),
  kind_source      text check (kind_source in ('ai', 'user')),
  menu_tags        text[] not null default '{}',
  area_id          text references public.areas (id),
  -- 사용자가 끼니 동네를 날짜 동네와 다르게 바꿨는지 (F-03 "변경됨")
  area_overridden  boolean not null default false,
  -- Google placeId만 저장한다. 이름·영업시간은 저장하지 않는다 (C-8, Places 약관)
  place_id         text,
  must_pick_id     uuid,
  skip_reason      text check (char_length(skip_reason) <= 20),
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now(),
  constraint slots_filled_has_menu check (state <> 'filled' or menu is not null),
  constraint slots_id_trip_unique unique (id, trip_id),
  -- 끼니의 날짜·꼭 먹을 항목은 같은 여행 것이어야 한다
  constraint slots_day_fk foreign key (day_id, trip_id)
    references public.trip_days (id, trip_id) on delete cascade,
  constraint slots_must_pick_fk foreign key (must_pick_id, trip_id)
    references public.must_picks (id, trip_id) on delete set null (must_pick_id)
);
create index slots_day_idx on public.slots (day_id);
create index slots_trip_idx on public.slots (trip_id);
create trigger slots_updated_at before update on public.slots
  for each row execute function public.set_updated_at();

-- flex 일행의 "확인함" (F-08). 끼니 × 일행. 식당을 다른 식당으로 바꾸면 서비스가 지운다
create table public.diet_checks (
  slot_id       uuid not null,
  companion_id  uuid not null,
  trip_id       uuid not null references public.trips (id) on delete cascade,
  checked       boolean not null,
  primary key (slot_id, companion_id),
  constraint diet_checks_slot_fk foreign key (slot_id, trip_id)
    references public.slots (id, trip_id) on delete cascade,
  constraint diet_checks_companion_fk foreign key (companion_id, trip_id)
    references public.trip_companions (id, trip_id) on delete cascade
);

-- "괜찮아요" 허용 기록 (F-05). 중복이 풀리면 서비스가 지운다
create table public.duplicate_acks (
  day_id    uuid not null,
  kind_id   text not null references public.menu_kinds (id),
  trip_id   uuid not null references public.trips (id) on delete cascade,
  slot_ids  uuid[] not null check (cardinality(slot_ids) >= 2),
  primary key (day_id, kind_id),
  constraint duplicate_acks_day_fk foreign key (day_id, trip_id)
    references public.trip_days (id, trip_id) on delete cascade
);

-- ===== 0004_places.sql =====

-- 맛집 모음 (places 경계, F-15, C-2). 사용자 단위로 여행 밖에 저장한다. placeId만 저장한다 (C-8)

create table public.saved_places (
  id        uuid primary key default gen_random_uuid(),
  user_id   uuid not null default auth.uid() references auth.users (id) on delete cascade,
  city_id   text not null references public.cities (id),
  place_id  text not null,
  menu      text not null check (char_length(menu) between 1 and 40),
  kind_id   text references public.menu_kinds (id),
  -- 식당 좌표로 정한 동네. 어느 동네 반경에도 없으면 null ("동네 미정")
  area_id   text references public.areas (id),
  source    text not null default 'search' check (source in ('search')),
  saved_at  timestamptz not null default now(),
  -- 같은 식당을 다시 저장하면 새 행이 아니라 메뉴만 바꾼다
  constraint saved_places_user_place_unique unique (user_id, place_id)
);
create index saved_places_user_city_idx on public.saved_places (user_id, city_id);

-- 맛집 모음에서 지우면 그 식당을 담은 꼭 먹을 항목도 빠진다.
-- 끼니에 넣은 식당(slots.place_id)은 그대로 남는다
alter table public.must_picks
  add constraint must_picks_saved_place_fk
  foreign key (saved_place_id) references public.saved_places (id) on delete cascade;

-- ===== 0005_sharing.sql =====

-- 공유 (sharing 경계, F-11). 링크는 trips.share_token이다.
-- 공개 조회와 의견 쓰기는 sharing 서비스가 service_role로 토큰을 확인한 뒤 허용된 필드만 다룬다.
-- 그래서 익명(anon) 역할에는 정책을 주지 않는다 (0006).

create table public.share_comments (
  id           uuid primary key default gen_random_uuid(),
  trip_id      uuid not null references public.trips (id) on delete cascade,
  slot_id      uuid not null,
  author_name  text not null check (char_length(author_name) between 1 and 12),
  body         text not null default '' check (char_length(body) <= 100),
  "like"       boolean not null default false,
  created_at   timestamptz not null default now(),
  -- 좋아요나 한마디 중 하나는 있어야 한다
  constraint share_comments_not_empty check ("like" or char_length(body) > 0),
  -- 의견은 같은 여행의 끼니에만
  constraint share_comments_slot_fk foreign key (slot_id, trip_id)
    references public.slots (id, trip_id) on delete cascade
);
create index share_comments_trip_idx on public.share_comments (trip_id);

-- ===== 0006_rls.sql =====

-- 행 수준 보안 (TECH_STACK 4장 3, 5). 모든 public 테이블에 RLS를 켠다.
-- - 마스터 데이터: 누구나 읽기만
-- - 사용자 데이터: 그 사용자 것만 (요청 본문의 사용자 id가 아니라 토큰의 auth.uid() 기준)
-- - 여행에 딸린 데이터: 그 여행의 소유자만
-- - 게스트 제한(여행 1개, 일행 저장 불가)은 서비스가 먼저 막고(409·403), 여기서 한 번 더 막는다
-- service_role(시드, 공유 공개 조회)은 RLS를 건너뛴다.

-- ---------- 도우미 ----------

-- 지금 요청한 사용자가 이 여행의 소유자인지. security definer라 trips의 RLS를 다시 거치지 않는다
create function public.is_trip_owner(target_trip_id uuid) returns boolean
language sql stable security definer set search_path = ''
as $$
  select exists (
    select 1 from public.trips t
    where t.id = target_trip_id and t.owner_id = (select auth.uid())
  );
$$;

-- 지금 사용자가 이미 여행을 갖고 있는지 (게스트 1개 제한).
-- trips 정책 안에서 trips를 다시 조회하면 정책이 자기 자신을 부르는 무한 재귀가 되므로 security definer로 우회한다
create function public.has_any_trip() returns boolean
language sql stable security definer set search_path = ''
as $$
  select exists (select 1 from public.trips t where t.owner_id = (select auth.uid()));
$$;

-- 지금 요청한 사용자가 게스트(익명 로그인)인지. Supabase 토큰의 is_anonymous 클레임
create function public.is_anonymous_user() returns boolean
language sql stable
as $$
  select coalesce(((select auth.jwt()) ->> 'is_anonymous')::boolean, false);
$$;

-- 이 저장 식당·저장 일행이 지금 사용자 것인지 (외래 키 검사는 RLS를 거치지 않으므로 직접 확인한다)
create function public.owns_saved_place(target_id uuid) returns boolean
language sql stable security definer set search_path = ''
as $$
  select exists (
    select 1 from public.saved_places p
    where p.id = target_id and p.user_id = (select auth.uid())
  );
$$;

create function public.owns_saved_companion(target_id uuid) returns boolean
language sql stable security definer set search_path = ''
as $$
  select exists (
    select 1 from public.saved_companions c
    where c.id = target_id and c.user_id = (select auth.uid())
  );
$$;

-- ---------- 마스터 데이터: 읽기만 ----------

alter table public.menu_kinds enable row level security;
alter table public.food_tags enable row level security;
alter table public.food_tag_presets enable row level security;
alter table public.cities enable row level security;
alter table public.areas enable row level security;
alter table public.must_menus enable row level security;

create policy "catalog readable" on public.menu_kinds for select to anon, authenticated using (true);
create policy "catalog readable" on public.food_tags for select to anon, authenticated using (true);
create policy "catalog readable" on public.food_tag_presets for select to anon, authenticated using (true);
create policy "catalog readable" on public.cities for select to anon, authenticated using (true);
create policy "catalog readable" on public.areas for select to anon, authenticated using (true);
create policy "catalog readable" on public.must_menus for select to anon, authenticated using (true);

-- ---------- 사용자 데이터 ----------

alter table public.profiles enable row level security;
alter table public.user_settings enable row level security;
alter table public.saved_companions enable row level security;
alter table public.saved_places enable row level security;

-- 프로필·설정은 가입 트리거가 만든다. 사용자는 읽고 고치기만 한다
create policy "own profile read" on public.profiles for select to authenticated
  using (id = (select auth.uid()));
create policy "own profile update" on public.profiles for update to authenticated
  using (id = (select auth.uid())) with check (id = (select auth.uid()));

create policy "own settings read" on public.user_settings for select to authenticated
  using (user_id = (select auth.uid()));
create policy "own settings update" on public.user_settings for update to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));

-- 자주 함께 가는 일행: 게스트는 저장할 수 없다 (F-18 7)
create policy "own saved companions read" on public.saved_companions for select to authenticated
  using (user_id = (select auth.uid()));
create policy "own saved companions insert" on public.saved_companions for insert to authenticated
  with check (user_id = (select auth.uid()) and not public.is_anonymous_user());
create policy "own saved companions update" on public.saved_companions for update to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));
create policy "own saved companions delete" on public.saved_companions for delete to authenticated
  using (user_id = (select auth.uid()));

-- 맛집 모음: 게스트도 쓴다 (C-7, 탭 세션 동안)
create policy "own saved places" on public.saved_places for all to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));

-- ---------- 여행 ----------

alter table public.trips enable row level security;

create policy "own trips read" on public.trips for select to authenticated
  using (owner_id = (select auth.uid()));
-- 게스트는 여행을 하나만 만든다 (F-18 3)
create policy "own trips insert" on public.trips for insert to authenticated
  with check (
    owner_id = (select auth.uid())
    and (not public.is_anonymous_user() or not public.has_any_trip())
  );
create policy "own trips update" on public.trips for update to authenticated
  using (owner_id = (select auth.uid())) with check (owner_id = (select auth.uid()));
create policy "own trips delete" on public.trips for delete to authenticated
  using (owner_id = (select auth.uid()));

-- ---------- 여행에 딸린 데이터: 그 여행의 소유자만 ----------

alter table public.trip_days enable row level security;
alter table public.slots enable row level security;
alter table public.diet_checks enable row level security;
alter table public.duplicate_acks enable row level security;
alter table public.trip_companions enable row level security;
alter table public.must_picks enable row level security;
alter table public.share_comments enable row level security;

create policy "trip owner" on public.trip_days for all to authenticated
  using (public.is_trip_owner(trip_id)) with check (public.is_trip_owner(trip_id));
create policy "trip owner" on public.slots for all to authenticated
  using (public.is_trip_owner(trip_id)) with check (public.is_trip_owner(trip_id));
create policy "trip owner" on public.diet_checks for all to authenticated
  using (public.is_trip_owner(trip_id)) with check (public.is_trip_owner(trip_id));
create policy "trip owner" on public.duplicate_acks for all to authenticated
  using (public.is_trip_owner(trip_id)) with check (public.is_trip_owner(trip_id));

-- 여행 일행: 불러온 저장 일행이 있다면 내 것이어야 한다
create policy "trip owner" on public.trip_companions for all to authenticated
  using (public.is_trip_owner(trip_id))
  with check (
    public.is_trip_owner(trip_id)
    and (source_saved_id is null or public.owns_saved_companion(source_saved_id))
  );

-- 꼭 먹을 것: 식당 항목은 내 맛집 모음 식당만 (C-2)
create policy "trip owner" on public.must_picks for all to authenticated
  using (public.is_trip_owner(trip_id))
  with check (
    public.is_trip_owner(trip_id)
    and (saved_place_id is null or public.owns_saved_place(saved_place_id))
  );

-- 공유 의견: 소유자는 읽고 지울 수 있다. 쓰기는 sharing 서비스(service_role)만 한다
create policy "trip owner reads comments" on public.share_comments for select to authenticated
  using (public.is_trip_owner(trip_id));
create policy "trip owner deletes comments" on public.share_comments for delete to authenticated
  using (public.is_trip_owner(trip_id));

-- ===== 0007_query_support.sql =====

-- 조회·삭제 경로에 맞춘 인덱스와 여행 목록 요약 뷰 (docs/DATABASE.md 5장, 6장).
-- 테이블 구조는 그대로 두고, API가 실제로 데이터를 찾는 경로에만 인덱스를 더한다.

-- ---------- 여행 상세(GET /trips/{id})와 끼니 수정(PATCH /slots/{id}) ----------

-- 여행 상세가 trip_id로 식이 체크·허용 기록을 모두 읽는다. 끼니 수정 뒤 허용 기록 정리도 trip_id로 찾는다
create index diet_checks_trip_idx on public.diet_checks (trip_id);
create index duplicate_acks_trip_idx on public.duplicate_acks (trip_id);

-- ---------- 삭제 연쇄 (외래 키가 가리키는 쪽을 지우면 이 열로 자식 행을 찾는다) ----------

-- 여행 일행 삭제 → 그 일행의 식이 체크 삭제 (기본 키는 slot_id가 앞이라 companion_id로는 못 찾는다)
create index diet_checks_companion_idx on public.diet_checks (companion_id);
-- 기간 축소로 끼니 삭제 → 그 끼니의 공유 의견 삭제
create index share_comments_slot_idx on public.share_comments (slot_id);
-- 꼭 먹을 항목 삭제 → 그 항목을 넣은 끼니의 must_pick_id 비우기
create index slots_must_pick_idx on public.slots (must_pick_id) where must_pick_id is not null;
-- 맛집 모음 삭제 → 그 식당을 담은 꼭 먹을 항목 삭제
create index must_picks_saved_place_idx on public.must_picks (saved_place_id)
  where saved_place_id is not null;
-- 자주 함께 가는 일행 삭제 → 그 일행을 불러온 여행 일행의 source_saved_id 비우기
create index trip_companions_source_saved_idx on public.trip_companions (source_saved_id)
  where source_saved_id is not null;

-- ---------- 맛집 모음 (GET /collection) ----------

-- 저장한 식당마다 "이 식당을 넣은 끼니" (SavedPlace.placements)를 placeId로 찾는다
create index slots_place_idx on public.slots (place_id) where place_id is not null;

-- ---------- 여행 목록 (GET /trips) ----------

-- TripSummary 한 줄 = 여행 + 도시 이름·시간대 + 일행 수 + 끼니 상태별 수.
-- security_invoker라 부르는 사용자의 RLS가 그대로 적용된다(내 여행만 보인다, PostgreSQL 15 이상).
-- 저장하지 않고 조회할 때마다 센다. 여행 하나는 끼니가 많아야 200개 안팎이라 세는 비용이 작고,
-- 숫자를 따로 저장하면 끼니를 바꿀 때마다 같이 고쳐야 해서 어긋날 위험이 생긴다.
create view public.trip_summaries with (security_invoker = true) as
select
  t.id,
  t.owner_id,
  t.city_id,
  c.name as city_name,
  c.time_zone,
  t.title,
  t.start_date,
  t.end_date,
  t.updated_at,
  (select count(*) from public.trip_companions tc where tc.trip_id = t.id) as companion_count,
  count(s.id) filter (where s.state <> 'skipped') as active_slots,
  count(s.id) filter (where s.state = 'filled') as filled_slots,
  count(s.id) filter (where s.state = 'onsite') as onsite_slots,
  count(s.id) filter (where s.state = 'empty') as empty_slots
from public.trips t
join public.cities c on c.id = t.city_id
left join public.slots s on s.trip_id = t.id
group by t.id, c.name, c.time_zone;

grant select on public.trip_summaries to authenticated;
