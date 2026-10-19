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
