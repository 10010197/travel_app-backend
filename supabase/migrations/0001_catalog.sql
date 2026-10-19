-- 마스터 데이터 (catalog 경계). 원본은 shared/master-data/*.json, app/seed/master_data.py가 채운다.
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
