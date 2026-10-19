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
