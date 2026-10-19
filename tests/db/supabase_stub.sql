-- 테스트용 Supabase 대역. 일반 PostgreSQL에 Supabase가 기본으로 주는 것 중 마이그레이션이 쓰는 것만 만든다.
-- 실제 Supabase에서는 이 파일을 쓰지 않는다 (supabase/migrations만 적용한다).
--
-- - 역할: anon(토큰 없음), authenticated(로그인·게스트), service_role(RLS 우회)
-- - auth.users: 가입 트리거(handle_new_user)가 붙는 테이블
-- - auth.uid(), auth.jwt(): Supabase처럼 요청 설정 request.jwt.claims에서 읽는다

do $$
begin
  if not exists (select from pg_roles where rolname = 'anon') then
    create role anon nologin;
  end if;
  if not exists (select from pg_roles where rolname = 'authenticated') then
    create role authenticated nologin;
  end if;
  if not exists (select from pg_roles where rolname = 'service_role') then
    create role service_role nologin bypassrls;
  end if;
end;
$$;

create schema auth;

create table auth.users (
  id                  uuid primary key,
  is_anonymous        boolean not null default false,
  raw_user_meta_data  jsonb not null default '{}'::jsonb
);

create function auth.jwt() returns jsonb
language sql stable
as $$
  select coalesce(nullif(current_setting('request.jwt.claims', true), '')::jsonb, '{}'::jsonb);
$$;

create function auth.uid() returns uuid
language sql stable
as $$
  select nullif(auth.jwt() ->> 'sub', '')::uuid;
$$;

grant usage on schema auth to anon, authenticated, service_role;
grant execute on all functions in schema auth to anon, authenticated, service_role;
