"""Authenticated HTTP only; no registry database access in the UI."""

from typing import Any

import requests


class APIError(Exception):
    pass


class APIClient:
    def __init__(self, base_url: str, token: str, timeout: int = 10) -> None:
        self.base_url = base_url.rstrip("/")
        self.headers = {"Authorization": f"Bearer {token}"}
        self.timeout = timeout

    def request(
        self,
        method: str,
        path: str,
        *,
        data: dict | None = None,
        params: dict | None = None,
        idempotency_key: str | None = None,
    ) -> Any:
        try:
            response = requests.request(
                method,
                self.base_url + path,
                headers={
                    **self.headers,
                    **({"Idempotency-Key": idempotency_key} if idempotency_key else {}),
                },
                json=data,
                params=params,
                timeout=self.timeout,
            )
            if not response.ok:
                try:
                    error = response.json().get("error", {})
                    message = error.get("message", "Request failed")
                    request_id = error.get(
                        "request_id", response.headers.get("X-Request-ID", "")
                    )
                except (ValueError, AttributeError):
                    message, request_id = "Request failed", ""
                raise APIError(
                    f"{message} ({response.status_code}). Request ID: {request_id}"
                )
            return None if response.status_code == 204 else response.json()
        except (requests.RequestException, ValueError) as exc:
            raise APIError("Unable to reach the API or read its response") from exc
