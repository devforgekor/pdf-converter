"""
CSRF 토큰 관리

참조 소스:
- Flask-WTF CSRF 보호 패턴을 FastAPI로 포팅
- 더블 서브밋 쿠키 방식: secrets.token_urlsafe() + secrets.compare_digest()
"""
import secrets
from fastapi import Request


def generate_csrf_token(request: Request) -> str:
    """세션에 CSRF 토큰을 생성/저장하고 반환합니다."""
    if "csrf_token" not in request.session:
        request.session["csrf_token"] = secrets.token_urlsafe(32)
    return request.session["csrf_token"]


def validate_csrf_token(request: Request, token: str) -> bool:
    """폼에서 제출된 CSRF 토큰과 세션의 토큰을 비교합니다."""
    session_token = request.session.get("csrf_token")
    if not session_token or not token:
        return False
    return secrets.compare_digest(session_token, token)
