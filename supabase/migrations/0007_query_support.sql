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
