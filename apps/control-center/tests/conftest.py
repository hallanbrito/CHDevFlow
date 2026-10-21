"""Configuração e fixtures do Pytest para o CHDevFlow Control Center."""
from __future__ import annotations

import asyncio
from typing import Any
from urllib.parse import urlparse

import pytest

from ch_control_center.app import create_app
from ch_control_center.dependencies import reset_services


class ASGIResponse:
    """Resposta HTTP simplificada para testes ASGI sem necessidade de dependências externas."""

    def __init__(self, status_code: int, headers: dict[str, str], body: bytes) -> None:
        self.status_code = status_code
        self.headers = headers
        self.body = body

    @property
    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")

    def json(self) -> Any:
        import json

        return json.loads(self.text)


class ASGIClient:
    """Cliente ASGI local in-memory para testes sem abertura de socket de rede."""

    def __init__(self, app: Any) -> None:
        self.app = app

    def request(
        self,
        method: str,
        path: str,
        headers: dict[str, str] | None = None,
        body: bytes = b"",
    ) -> ASGIResponse:
        return asyncio.run(self._async_request(method, path, headers, body))

    async def _async_request(
        self,
        method: str,
        path: str,
        headers: dict[str, str] | None = None,
        body: bytes = b"",
    ) -> ASGIResponse:
        parsed = urlparse(path)
        path_only = parsed.path or "/"
        query_string = parsed.query.encode("utf-8")

        asgi_headers = [(b"host", b"127.0.0.1:8000")]
        if headers:
            for k, v in headers.items():
                asgi_headers.append((k.lower().encode("latin1"), v.encode("latin1")))

        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": method.upper(),
            "scheme": "http",
            "path": path_only,
            "raw_path": path_only.encode("utf-8"),
            "query_string": query_string,
            "headers": asgi_headers,
        }

        status_code: int = 500
        resp_headers: dict[str, str] = {}
        resp_body = bytearray()
        body_sent = False

        async def receive() -> dict[str, Any]:
            nonlocal body_sent
            if not body_sent:
                body_sent = True
                return {"type": "http.request", "body": body, "more_body": False}
            return {"type": "http.disconnect"}

        async def send(message: dict[str, Any]) -> None:
            nonlocal status_code, resp_headers, resp_body
            if message["type"] == "http.response.start":
                status_code = message["status"]
                for k, v in message.get("headers", []):
                    resp_headers[k.decode("latin1")] = v.decode("latin1")
            elif message["type"] == "http.response.body":
                resp_body.extend(message.get("body", b""))

        await self.app(scope, receive, send)
        return ASGIResponse(status_code, resp_headers, bytes(resp_body))

    def get(self, path: str, headers: dict[str, str] | None = None) -> ASGIResponse:
        return self.request("GET", path, headers=headers)

    def post(
        self,
        path: str,
        data: bytes | str | None = None,
        headers: dict[str, str] | None = None,
    ) -> ASGIResponse:
        hdrs = dict(headers or {})
        if isinstance(data, str):
            body_bytes = data.encode("utf-8")
            if "content-type" not in [k.lower() for k in hdrs]:
                hdrs["content-type"] = "application/x-www-form-urlencoded"
        elif isinstance(data, bytes):
            body_bytes = data
        else:
            body_bytes = b""
        return self.request("POST", path, headers=hdrs, body=body_bytes)


@pytest.fixture(autouse=True)
def clean_services() -> None:
    """Garante isolamento de estado entre testes."""
    reset_services()


@pytest.fixture
def client() -> ASGIClient:
    """Fixture que fornece um cliente ASGI para a aplicação FastAPI."""
    app = create_app()
    return ASGIClient(app)
