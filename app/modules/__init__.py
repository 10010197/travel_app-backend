"""기능 경계별 모듈 (docs/ARCHITECTURE.md 2장).

identity, catalog, trips, places, sharing 다섯 모듈이 들어온다(B3~B6). 각 모듈은
router.py → service.py → repository.py, 응답·요청 모델은 schemas.py에 둔다.
"""
