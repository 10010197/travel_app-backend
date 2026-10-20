"""I/O 없는 결정론적 규칙. 프론트 src/domain과 이름을 맞춘다(evaluateDuplicates → stale_acks 등).

서버에 필요한 규칙만 옮겼다: 기간·일차(days), 시간대(time_band), 하루 중복 허용 기록 정리(duplicate),
좌표·지도 링크(geo). 화면 전용 규칙(지표, 식이 상태, 휴무 판정 …)은 프론트만 계산한다(BUSINESS_LOGIC 1장).
"""
