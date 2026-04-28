from __future__ import annotations

from fastapi import HTTPException, status


class EntitlementExceeded(HTTPException):
    def __init__(self, *, kind: str, plan: str, current: int | None = None, limit: int | None = None) -> None:
        detail: dict = {"code": "entitlement_exceeded", "kind": kind, "plan": plan}
        if current is not None:
            detail["current"] = current
        if limit is not None:
            detail["limit"] = limit
        super().__init__(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


class ViewWindowExpired(HTTPException):
    def __init__(self, *, plan: str) -> None:
        super().__init__(
            status_code=status.HTTP_410_GONE,
            detail={"code": "view_window_expired", "plan": plan},
        )
