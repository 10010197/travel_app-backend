"""사용자별 호출 제한 (TECH_STACK 4-1: 지도 API 비용, 공유 의견 남용 방지).

한 시간 창 안의 호출 수를 세는 단순한 메모리 제한기다. 프로세스 하나 기준이라 Render에서 인스턴스를
늘리면 인스턴스마다 따로 센다. 그때는 같은 인터페이스(RateLimiter.hit)로 Redis 구현을 붙인다.
검색 라우터(B4)와 공유 의견 라우터(B6)가 쓴다.
"""

import time
from collections import defaultdict, deque
from collections.abc import Callable
from threading import Lock

from app.core.errors import AppError, ErrorCode


class RateLimiter:
    """key(예: "search:<user_id>")마다 window_seconds 동안 limit번까지 허용한다."""

    def __init__(
        self, limit: int, window_seconds: float = 3600, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self.limit = limit
        self.window = window_seconds
        self._clock = clock
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def hit(self, key: str) -> None:
        """한 번 호출로 센다. 한도를 넘으면 429 RATE_LIMITED."""
        now = self._clock()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] >= self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                raise AppError(
                    429, ErrorCode.RATE_LIMITED, "요청이 너무 많아요. 잠시 후 다시 시도해 주세요."
                )
            hits.append(now)
