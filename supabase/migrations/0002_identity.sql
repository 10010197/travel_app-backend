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
