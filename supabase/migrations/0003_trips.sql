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
