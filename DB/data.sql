-- 자동 생성 파일: app/seed/master_data.py --sql
-- 초기 데이터(마스터 데이터). 원본은 data/master-data/*.json. 이 파일을 직접 고치지 않는다.
-- DB/init.sql 다음에 적용한다. upsert라 여러 번 적용해도 된다.

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
  ('fukuoka', '후쿠오카', 'JP', 'Asia/Tokyo', 33.5902, 130.4017, 0),
  ('osaka', '오사카', 'JP', 'Asia/Tokyo', 34.6937, 135.5023, 1),
  ('tokyo', '도쿄', 'JP', 'Asia/Tokyo', 35.6812, 139.7671, 2),
  ('taipei', '타이베이', 'TW', 'Asia/Taipei', 25.0478, 121.517, 3),
  ('bangkok', '방콕', 'TH', 'Asia/Bangkok', 13.7563, 100.5018, 4)
on conflict (id) do update set name = excluded.name, country_code = excluded.country_code, time_zone = excluded.time_zone, center_lat = excluded.center_lat, center_lng = excluded.center_lng, sort_order = excluded.sort_order;

insert into public.areas (id, city_id, name, center_lat, center_lng, radius_meters, sort_order) values
  ('hakata', 'fukuoka', '하카타', 33.5902, 130.4207, 800, 0),
  ('tenjin', 'fukuoka', '텐진', 33.5911, 130.399, 700, 1),
  ('nakasu', 'fukuoka', '나카스', 33.5935, 130.4062, 500, 2),
  ('yakuin', 'fukuoka', '야쿠인', 33.5822, 130.3986, 600, 3),
  ('ohori', 'fukuoka', '오호리 공원', 33.5858, 130.3762, 700, 4),
  ('momochi', 'fukuoka', '모모치', 33.5934, 130.3515, 1000, 5),
  ('dazaifu', 'fukuoka', '다자이후', 33.5196, 130.5347, 1000, 6),
  ('umeda', 'osaka', '우메다', 34.7025, 135.4959, 900, 0),
  ('namba', 'osaka', '난바', 34.6659, 135.5013, 700, 1),
  ('shinsaibashi', 'osaka', '신사이바시', 34.6749, 135.5009, 500, 2),
  ('shinsekai', 'osaka', '신세카이', 34.6525, 135.5063, 500, 3),
  ('tenma', 'osaka', '텐마', 34.7046, 135.5124, 600, 4),
  ('tsuruhashi', 'osaka', '츠루하시', 34.6655, 135.5308, 500, 5),
  ('osakajo', 'osaka', '오사카성', 34.6873, 135.5262, 800, 6),
  ('shinjuku', 'tokyo', '신주쿠', 35.6909, 139.7003, 900, 0),
  ('shibuya', 'tokyo', '시부야', 35.658, 139.7016, 800, 1),
  ('ginza', 'tokyo', '긴자', 35.6717, 139.765, 700, 2),
  ('tsukiji', 'tokyo', '츠키지', 35.6655, 139.7707, 500, 3),
  ('tsukishima', 'tokyo', '츠키시마', 35.6634, 139.7826, 500, 4),
  ('asakusa', 'tokyo', '아사쿠사', 35.7148, 139.7967, 700, 5),
  ('ueno', 'tokyo', '우에노', 35.7138, 139.7773, 700, 6),
  ('ximending', 'taipei', '시먼딩', 25.0421, 121.5081, 600, 0),
  ('zhongshan', 'taipei', '중산', 25.0527, 121.5203, 600, 1),
  ('yongkang', 'taipei', '융캉제', 25.033, 121.5297, 500, 2),
  ('xinyi', 'taipei', '신이', 25.034, 121.5645, 900, 3),
  ('dadaocheng', 'taipei', '다다오청', 25.0559, 121.5101, 500, 4),
  ('shilin', 'taipei', '스린 야시장', 25.088, 121.5241, 600, 5),
  ('raohe', 'taipei', '라오허제 야시장', 25.0509, 121.5775, 500, 6),
  ('siam', 'bangkok', '시암', 13.7457, 100.5343, 700, 0),
  ('sukhumvit', 'bangkok', '수쿰윗', 13.7376, 100.5603, 900, 1),
  ('silom', 'bangkok', '실롬', 13.7286, 100.534, 800, 2),
  ('khaosan', 'bangkok', '카오산 로드', 13.759, 100.4974, 500, 3),
  ('yaowarat', 'bangkok', '차이나타운', 13.7408, 100.5103, 600, 4),
  ('riverside', 'bangkok', '리버사이드', 13.7266, 100.5102, 700, 5),
  ('chatuchak', 'bangkok', '짜뚜짝', 13.7999, 100.5505, 800, 6)
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
  ('fuk-tetsunabe-gyoza', 'fukuoka', '테츠나베 교자', 'grill', '철판에 구운 한입 교자', array['meat', 'pork', 'wheat']::text[], false, 9),
  ('osa-takoyaki', 'osaka', '타코야키', 'street', '문어를 넣은 동그란 풀빵, 오사카 대표 간식', array['seafood', 'cephalopod', 'wheat', 'egg']::text[], true, 0),
  ('osa-okonomiyaki', 'osaka', '오코노미야키', 'grill', '철판에 구운 양배추 부침', array['meat', 'pork', 'wheat', 'egg']::text[], true, 1),
  ('osa-kushikatsu', 'osaka', '쿠시카츠', 'fried', '꼬치 튀김, 신세카이 명물', array['meat', 'pork', 'beef', 'wheat', 'egg']::text[], true, 2),
  ('osa-kitsune-udon', 'osaka', '키츠네 우동', 'noodle', '달큰한 유부를 올린 맑은 국물 우동', array['wheat']::text[], true, 3),
  ('osa-yakiniku', 'osaka', '야키니쿠', 'grill', '츠루하시 숯불 고기구이', array['meat', 'beef', 'offal']::text[], false, 4),
  ('osa-battera', 'osaka', '밧테라', 'seafood', '초절임 고등어를 눌러 만든 상자 초밥', array['seafood', 'fish']::text[], false, 5),
  ('osa-butaman', 'osaka', '부타만', 'other', '돼지고기 찐빵', array['meat', 'pork', 'wheat']::text[], false, 6),
  ('osa-omurice', 'osaka', '오므라이스', 'rice', '오사카에서 시작된 달걀 덮은 볶음밥', array['egg', 'meat', 'chicken']::text[], false, 7),
  ('osa-ikayaki', 'osaka', '이카야키', 'street', '오징어를 넣어 납작하게 구운 부침', array['seafood', 'cephalopod', 'wheat', 'egg']::text[], false, 8),
  ('tyo-sushi', 'tokyo', '스시', 'seafood', '에도마에 초밥, 츠키지 장외시장 추천', array['seafood', 'fish', 'raw_fish']::text[], true, 0),
  ('tyo-tendon', 'tokyo', '텐동', 'fried', '새우·채소 튀김 덮밥', array['seafood', 'crustacean', 'wheat', 'egg']::text[], true, 1),
  ('tyo-soba', 'tokyo', '소바', 'noodle', '메밀 면을 쯔유에 찍어 먹는 자루 소바', array['wheat']::text[], true, 2),
  ('tyo-monjayaki', 'tokyo', '몬자야키', 'other', '묽은 반죽을 철판에 눌러 먹는 츠키시마 명물', array['seafood', 'wheat']::text[], true, 3),
  ('tyo-tsukemen', 'tokyo', '츠케멘', 'noodle', '진한 국물에 찍어 먹는 굵은 면', array['meat', 'pork', 'seafood', 'fish', 'wheat']::text[], false, 4),
  ('tyo-unaju', 'tokyo', '우나주', 'rice', '찬합에 담은 장어 덮밥', array['seafood', 'fish']::text[], false, 5),
  ('tyo-yakitori', 'tokyo', '야키토리', 'grill', '숯불 닭꼬치, 저녁 추천', array['meat', 'chicken', 'offal']::text[], false, 6),
  ('tyo-tonkatsu', 'tokyo', '돈카츠', 'fried', '두툼한 돼지고기 튀김 정식', array['meat', 'pork', 'wheat', 'egg']::text[], false, 7),
  ('tyo-ningyoyaki', 'tokyo', '닌교야키', 'dessert', '팥소를 넣은 인형 모양 카스텔라, 아사쿠사 명물', array['wheat', 'egg']::text[], false, 8),
  ('tpe-beef-noodle', 'taipei', '우육면', 'noodle', '진한 소고기 국물의 굵은 면', array['meat', 'beef', 'wheat']::text[], true, 0),
  ('tpe-xiaolongbao', 'taipei', '샤오롱바오', 'other', '육즙 가득한 작은 찐만두', array['meat', 'pork', 'wheat']::text[], true, 1),
  ('tpe-luroufan', 'taipei', '루로우판', 'rice', '간장에 졸인 다진 돼지고기 덮밥', array['meat', 'pork', 'egg']::text[], true, 2),
  ('tpe-mango-ice', 'taipei', '망고 빙수', 'dessert', '생망고를 듬뿍 올린 빙수', array['dairy']::text[], true, 3),
  ('tpe-jipai', 'taipei', '지파이', 'fried', '얼굴만 한 닭가슴살 튀김, 야시장 간식', array['meat', 'chicken', 'wheat']::text[], false, 4),
  ('tpe-oyster-omelette', 'taipei', '어아젠', 'street', '굴을 넣은 전분 부침', array['seafood', 'shellfish', 'egg']::text[], false, 5),
  ('tpe-hujiaobing', 'taipei', '후자오빙', 'street', '화덕에 붙여 구운 후추 고기빵', array['meat', 'pork', 'wheat', 'sesame']::text[], false, 6),
  ('tpe-hotpot', 'taipei', '훠궈', 'hotpot', '마라·맑은 국물을 고르는 중국식 샤브샤브', array['meat']::text[], false, 7),
  ('tpe-bubble-tea', 'taipei', '버블티', 'cafe', '타피오카 펄을 넣은 밀크티', array['dairy']::text[], false, 8),
  ('bkk-pad-thai', 'bangkok', '팟타이', 'noodle', '새우와 땅콩을 올린 볶음 쌀국수', array['seafood', 'crustacean', 'egg', 'nuts']::text[], true, 0),
  ('bkk-tom-yum', 'bangkok', '똠얌꿍', 'seafood', '새우를 넣은 맵고 신 수프', array['seafood', 'crustacean']::text[], true, 1),
  ('bkk-khao-man-gai', 'bangkok', '카오만가이', 'rice', '닭 육수로 지은 밥과 삶은 닭', array['meat', 'chicken']::text[], true, 2),
  ('bkk-mango-sticky-rice', 'bangkok', '망고 스티키라이스', 'dessert', '코코넛 찹쌀밥에 생망고', '{}'::text[], true, 3),
  ('bkk-pad-kra-pao', 'bangkok', '팟카파오', 'rice', '바질 고기볶음 덮밥과 달걀 프라이', array['meat', 'pork', 'egg']::text[], false, 4),
  ('bkk-som-tam', 'bangkok', '쏨땀', 'other', '그린 파파야 샐러드', array['seafood', 'crustacean', 'nuts']::text[], false, 5),
  ('bkk-moo-kata', 'bangkok', '무까타', 'grill', '불판 가운데 굽고 둘레에 끓이는 태국식 고기구이', array['meat', 'pork']::text[], false, 6),
  ('bkk-boat-noodle', 'bangkok', '꾸어이띠아우 르아', 'noodle', '작은 그릇에 담은 진한 보트 누들', array['meat', 'pork', 'beef', 'offal']::text[], false, 7),
  ('bkk-poo-pad-pong-curry', 'bangkok', '뿌팟퐁커리', 'seafood', '달걀을 풀어 볶은 게 커리', array['seafood', 'crustacean', 'egg', 'dairy']::text[], false, 8)
on conflict (id) do update set city_id = excluded.city_id, name = excluded.name, kind_id = excluded.kind_id, description = excluded.description, food_tags = excluded.food_tags, is_signature = excluded.is_signature, sort_order = excluded.sort_order;
