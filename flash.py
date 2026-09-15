import typing
from fastapi import Request


def flash(request: Request, message: typing.Any, category: str = "primary") -> None:
    """세션에 플래시 메시지를 저장합니다."""
    if "_messages" not in request.session:
        request.session["_messages"] = []
    request.session["_messages"].append({
        "message": message,
        "category": category,
    })


def get_flashed_messages(request: Request = None):
    """세션에서 플래시 메시지를 꺼내고 삭제합니다 (일회성)."""
    if request is None:
        return []
    return request.session.pop("_messages") if "_messages" in request.session else []
