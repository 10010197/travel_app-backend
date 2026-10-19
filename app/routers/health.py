"""헬스 체크. Render 상태 확인과 프론트 개발 서버 proxy 연결 확인에 쓴다."""

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
