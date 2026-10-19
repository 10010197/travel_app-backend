-- 자동 생성 파일: backend/app/seed/master_data.py --sql
-- 원본은 shared/master-data/*.json. 이 파일을 직접 고치지 않는다.

insert into public.menu_kinds (id, label, allow_daily_repeat, sort_order) values
  ('noodle', '면', false, 0),
  ('rice', '밥', true, 1),
  ('hotpot', '전골', false, 2),
  ('seafood', '생선', false, 3),
  ('grill', '고기', false, 4),
  ('fried', '튀김', false, 5),
  ('street', '포장마차', false, 6),
  ('bread', '빵', true, 7),
  ('dessert', '디저트', true, 8),
  ('cafe', '카페', true, 9),
  ('other', '기타', true, 10)
on conflict (id) do update set label = excluded.label, allow_daily_repeat = excluded.allow_daily_repeat, sort_order = excluded.sort_order;

insert into public.food_tags (id, label, parent_id, sort_order) values
  ('meat', '육류', null, 0),
  ('seafood', '해산물', null, 5),
  ('egg', '달걀', null, 12),
  ('dairy', '유제품', null, 13),
  ('wheat', '밀', null, 14),
  ('nuts', '견과류', null, 15),
  ('sesame', '참깨', null, 16),
  ('alcohol', '알코올', null, 17),
  ('pork', '돼지고기', 'meat', 1),
  ('beef', '소고기', 'meat', 2),
  ('chicken', '닭고기', 'meat', 3),
  ('offal', '내장', 'meat', 4),
  ('fish', '생선', 'seafood', 6),
  ('raw_fish', '날생선', 'seafood', 7),
  ('crustacean', '갑각류', 'seafood', 8),
  ('shellfish', '조개류', 'seafood', 9),
  ('cephalopod', '오징어·문어', 'seafood', 10),
  ('fish_roe', '생선알', 'seafood', 11)
on conflict (id) do update set label = excluded.label, parent_id = excluded.parent_id, sort_order = excluded.sort_order;

insert into public.food_tag_presets (label, tags, sort_order) values
  ('비건', array['meat', 'seafood', 'egg', 'dairy']::text[], 0),
  ('갑각류 알레르기', array['crustacean']::text[], 1),
  ('날생선 못 먹음', array['raw_fish']::text[], 2)
on conflict (label) do update set tags = excluded.tags, sort_order = excluded.sort_order;

insert into public.cities (id, name, country_code, time_zone, center_lat, center_lng, sort_order) values
  ('fukuoka', '후쿠오카', 'JP', 'Asia/Tokyo', 33.5902, 130.4017, 0)
on conflict (id) do update set name = excluded.name, country_code = excluded.country_code, time_zone = excluded.time_zone, center_lat = excluded.center_lat, center_lng = excluded.center_lng, sort_order = excluded.sort_order;

insert into public.areas (id, city_id, name, center_lat, center_lng, radius_meters, sort_order) values
  ('hakata', 'fukuoka', '하카타', 33.5902, 130.4207, 800, 0),
  ('tenjin', 'fukuoka', '텐진', 33.5911, 130.399, 700, 1),
  ('nakasu', 'fukuoka', '나카스', 33.5935, 130.4062, 500, 2),
  ('yakuin', 'fukuoka', '야쿠인', 33.5822, 130.3986, 600, 3),
  ('ohori', 'fukuoka', '오호리 공원', 33.5858, 130.3762, 700, 4),
  ('momochi', 'fukuoka', '모모치', 33.5934, 130.3515, 1000, 5),
  ('dazaifu', 'fukuoka', '다자이후', 33.5196, 130.5347, 1000, 6)
on conflict (id) do update set city_id = excluded.city_id, name = excluded.name, center_lat = excluded.center_lat, center_lng = excluded.center_lng, radius_meters = excluded.radius_meters, sort_order = excluded.sort_order;

insert into public.must_menus (id, city_id, name, kind_id, description, food_tags, is_signature, sort_order) values
  ('fuk-motsunabe', 'fukuoka', '모츠나베', 'hotpot', '곱창 전골, 후쿠오카 대표 메뉴', array['meat', 'beef', 'offal']::text[], true, 0),
  ('fuk-mentaiko-onigiri', 'fukuoka', '멘타이코 주먹밥', 'rice', '명란젓, 하카타 명물', array['seafood', 'fish_roe']::text[], true, 1),
  ('fuk-mizutaki', 'fukuoka', '미즈타키', 'hotpot', '맑은 닭 육수 전골', array['meat', 'chicken']::text[], true, 2),
  ('fuk-yatai', 'fukuoka', '야타이', 'street', '나카스 강변 포장마차, 저녁 추천', '{}'::text[], true, 3),
  ('fuk-hakata-ramen', 'fukuoka', '하카타 라멘', 'noodle', '돼지뼈 국물의 가는 면', array['meat', 'pork', 'wheat']::text[], false, 4),
  ('fuk-gomasaba', 'fukuoka', '고마사바', 'seafood', '참깨 소스 고등어회', array['seafood', 'fish', 'raw_fish', 'sesame']::text[], false, 5),
  ('fuk-crab', 'fukuoka', '게 요리', 'seafood', '제철 게 정식', array['seafood', 'crustacean']::text[], false, 6),
  ('fuk-udon', 'fukuoka', '하카타 우동', 'noodle', '부드러운 면과 우엉 튀김 고명', array['wheat']::text[], false, 7),
  ('fuk-ika', 'fukuoka', '이카 이키즈쿠리', 'seafood', '살아 있는 오징어 회, 요부코 명물', array['seafood', 'cephalopod', 'raw_fish']::text[], false, 8),
  ('fuk-tetsunabe-gyoza', 'fukuoka', '테츠나베 교자', 'grill', '철판에 구운 한입 교자', array['meat', 'pork', 'wheat']::text[], false, 9)
on conflict (id) do update set city_id = excluded.city_id, name = excluded.name, kind_id = excluded.kind_id, description = excluded.description, food_tags = excluded.food_tags, is_signature = excluded.is_signature, sort_order = excluded.sort_order;
