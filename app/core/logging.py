"""로그 설정과 민감 정보 가리기 (TECH_STACK 5장).

일행 이름·못 먹는 음식 원문·토큰이 로그에 남지 않게, 로그 레코드의 dict 인자와 extra 필드에서
민감한 키의 값을 "***"로 바꾼다. main.py의 create_app()이 configure_logging()을 부른다.
"""

import logging
from typing import Any

SENSITIVE_KEYS = frozenset(
    {"foodsRaw", "foods_raw", "authorName", "author_name", "access_token", "authorization", "name"}
)


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: "***" if k in SENSITIVE_KEYS else _redact(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return type(value)(_redact(v) for v in value)
    return value


class RedactingFilter(logging.Filter):
    """로그를 남기기 전에 민감한 키의 값을 가린다."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, dict):
            record.args = _redact(record.args)
        elif isinstance(record.args, tuple):
            record.args = tuple(_redact(a) for a in record.args)
        for key in SENSITIVE_KEYS & record.__dict__.keys():
            setattr(record, key, "***")
        return True


def configure_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler()
    handler.addFilter(RedactingFilter())
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
