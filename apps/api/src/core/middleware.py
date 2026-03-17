import uuid
from collections.abc import Awaitable, Callable

from fastapi import Request
from starlette.responses import Response

from .request_context import correlation_id_ctx, request_id_ctx


async def request_id_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
    correlation_id = request.headers.get("x-correlation-id", request_id)

    request_id_token = request_id_ctx.set(request_id)
    correlation_id_token = correlation_id_ctx.set(correlation_id)

    try:
        response = await call_next(request)
    finally:
        request_id_ctx.reset(request_id_token)
        correlation_id_ctx.reset(correlation_id_token)

    response.headers["x-request-id"] = request_id
    response.headers["x-correlation-id"] = correlation_id
    return response
