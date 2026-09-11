"""Safe platform error envelopes and server-generated request correlation."""

from collections.abc import Mapping
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from services.policy_service import PolicyError
from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class RequestIdMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = str(uuid4())
        scope.setdefault("state", {})["request_id"] = request_id

        async def send_response(message: Message) -> None:
            if message["type"] == "http.response.start":
                message["headers"] = [
                    (key, value)
                    for key, value in message.get("headers", [])
                    if key.lower() != b"x-request-id"
                ]
                message["headers"].append((b"x-request-id", request_id.encode()))
            await send(message)

        await self.app(scope, receive, send_response)


def envelope(
    request: Request,
    status: int,
    code: str,
    message: str,
    details: dict | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", str(uuid4()))
    return JSONResponse(
        {
            "error": {
                "code": code,
                "message": message,
                "request_id": request_id,
                "details": details or {},
            }
        },
        status_code=status,
        headers={**(headers or {}), "X-Request-ID": request_id},
    )


def install_errors(app: FastAPI) -> None:
    app.add_middleware(RequestIdMiddleware)

    @app.exception_handler(PolicyError)
    async def policy_error(request: Request, exc: PolicyError) -> Response:
        return envelope(request, exc.status, exc.code, exc.message)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> Response:
        if not request.url.path.startswith("/api/v1/"):
            return JSONResponse(
                {"detail": exc.detail}, status_code=exc.status_code, headers=exc.headers
            )
        code = {
            401: "unauthenticated",
            403: "forbidden",
            404: "not_found",
            405: "method_not_allowed",
            429: "rate_limited",
        }.get(exc.status_code, "request_failed")
        return envelope(
            request, exc.status_code, code, str(exc.detail), headers=exc.headers
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(
        request: Request, exc: RequestValidationError
    ) -> Response:
        if not request.url.path.startswith("/api/v1/"):
            # Avoid reflecting passwords or other submitted values in auth errors.
            return JSONResponse({"detail": "Invalid request"}, status_code=422)
        fields = [
            {"location": list(error["loc"]), "type": error["type"]}
            for error in exc.errors()
        ]
        return envelope(
            request, 422, "validation_error", "Invalid request", {"fields": fields}
        )

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception) -> Response:
        return envelope(
            request, 500, "internal_error", "Unable to complete the request"
        )
