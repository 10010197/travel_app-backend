"""오류 형식 통일 (BUSINESS_LOGIC 16장, frontend/src/api/client.ts와 같은 계약).

모든 4xx·5xx를 { "error": { "code", "message" } }로 돌려준다. 프론트는 code로 문구·행동을 고른다.
서비스는 AppError를 던지고, main.py가 install_error_handlers()로 처리기를 등록한다.
"""

import logging
from enum import StrEnum

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class ErrorCode(StrEnum):
    """프론트 ApiError.code와 같은 문자열"""

    VALIDATION_ERROR = "VALIDATION_ERROR"
    CITY_NOT_SUPPORTED = "CITY_NOT_SUPPORTED"
    UNAUTHORIZED = "UNAUTHORIZED"
    LOGIN_REQUIRED = "LOGIN_REQUIRED"
    NOT_FOUND = "NOT_FOUND"
    SHARE_DISABLED = "SHARE_DISABLED"
    GUEST_TRIP_LIMIT = "GUEST_TRIP_LIMIT"
    MUST_PICK_PLACED = "MUST_PICK_PLACED"
    RATE_LIMITED = "RATE_LIMITED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class AppError(Exception):
    """서비스·의존성이 던지는 예상된 오류. 상태 코드와 화면용 메시지를 함께 든다."""

    def __init__(self, status: int, code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def error_body(code: ErrorCode | str, message: str) -> dict[str, dict[str, str]]:
    return {"error": {"code": str(code), "message": message}}


async def _app_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)
    return JSONResponse(error_body(exc.code, exc.message), status_code=exc.status)


async def _validation_error(_: Request, exc: Exception) -> JSONResponse:
    # Pydantic 기본 422 대신 400 VALIDATION_ERROR (목 핸들러와 같은 동작)
    assert isinstance(exc, RequestValidationError)
    first = exc.errors()[0] if exc.errors() else {}
    where = ".".join(str(p) for p in first.get("loc", ()) if p != "body")
    message = f"{where}: {first.get('msg', '잘못된 요청이에요')}" if where else "잘못된 요청이에요"
    return JSONResponse(error_body(ErrorCode.VALIDATION_ERROR, message), status_code=400)


async def _http_error(_: Request, exc: Exception) -> JSONResponse:
    # 없는 경로(404)·허용되지 않은 메서드(405) 등 프레임워크가 내는 오류도 같은 형식으로
    assert isinstance(exc, StarletteHTTPException)
    code = ErrorCode.NOT_FOUND if exc.status_code == 404 else ErrorCode.VALIDATION_ERROR
    return JSONResponse(error_body(code, str(exc.detail)), status_code=exc.status_code)


async def _unexpected_error(_: Request, exc: Exception) -> JSONResponse:
    logger.exception("처리하지 못한 오류", exc_info=exc)
    return JSONResponse(
        error_body(ErrorCode.INTERNAL_ERROR, "잠시 후 다시 시도해 주세요."), status_code=500
    )


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _app_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(Exception, _unexpected_error)
