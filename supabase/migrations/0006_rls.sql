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
