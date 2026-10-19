-- 테스트용: Supabase가 public 스키마에 기본으로 주는 권한을 흉내 낸다.
-- Supabase는 anon·authenticated에 테이블 권한을 넓게 주고 RLS로 막는다. 그래서 테스트도 같은 조건에서 RLS를 검증한다.
grant usage on schema public to anon, authenticated, service_role;
grant all on all tables in schema public to anon, authenticated, service_role;
grant execute on all functions in schema public to anon, authenticated, service_role;
