"""Fábrica da aplicação FastAPI do CHDevFlow Control Center (CC-01).

Configura middleware de segurança local, roteadores, arquivos estáticos e templates.
Opera estritamente em modo somente leitura (CH-1 / RNF-01 / D05).
"""
from __future__ import annotations

from typing import Callable

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from ch_control_center.config import DIRETORIO_STATIC
from ch_control_center.routes.dashboard import router as dashboard_router
from ch_control_center.routes.demo import router as demo_router
from ch_control_center.routes.graph import router as graph_router
from ch_control_center.routes.missions import router as missions_router
from ch_control_center.routes.projects import router as projects_router
from ch_control_center.routes.student import router as student_router
from ch_control_center.security import validar_host_cabecalho


def create_app() -> FastAPI:
    """Cria e configura a instância do FastAPI para o Control Center."""
    app = FastAPI(
        title="CHDevFlow Control Center",
        description="Painel de supervisão e governança de IA local (Somente Leitura)",
        version="0.2.0",
        docs_url="/docs",
        redoc_url=None,
    )

    # Middleware de Segurança e Cabeçalhos Locais (Anti-clickjacking e CSP defensiva inicial/local)
    @app.middleware("http")
    async def aplicar_cabecalhos_seguranca(
        request: Request,
        call_next: Callable[[Request], Response],
    ) -> Response:
        try:
            validar_host_cabecalho(request)
        except Exception as exc:
            from fastapi import HTTPException
            if isinstance(exc, HTTPException):
                return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
            raise

        response = await call_next(request)
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "font-src 'self'; "
            "connect-src 'self'; "
            "frame-ancestors 'none'; "
            "form-action 'self'; "
            "base-uri 'self';"
        )
        response.headers["X-Governanca-Modo"] = "SOMENTE_LEITURA"
        return response

    # Arquivos Estáticos (CSS e JS próprios, sem CDNs externas)
    if DIRETORIO_STATIC.is_dir():
        app.mount("/static", StaticFiles(directory=str(DIRETORIO_STATIC)), name="static")

    # Registro das Rotas do Control Center
    app.include_router(dashboard_router)
    app.include_router(missions_router)
    app.include_router(graph_router)
    app.include_router(student_router)
    app.include_router(demo_router)
    app.include_router(projects_router)

    # Healthcheck para sondas locais e testes automatizados
    @app.get("/health", response_class=JSONResponse)
    async def healthcheck() -> dict[str, str]:
        return {
            "status": "ok",
            "modo": "SOMENTE_LEITURA",
            "versao": "0.2.0",
            "host_politica": "LOCAL_ONLY_127.0.0.1",
        }

    return app


# Instância padrão para inicialização via Uvicorn CLI
app = create_app()
