"""Rotas para alternância e consulta de perfis de projetos suportados."""
from __future__ import annotations

import urllib.parse
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse

from ch_control_center.dependencies import get_project_service
from ch_control_center.security import (
    sanitizar_caminho_redirecionamento,
    validar_origem_local,
    validar_requisicao_post_segura,
)
from ch_control_center.services.project_service import ProjectService

router = APIRouter()


@router.post("/projetos/alternar")
async def toggle_project_profile(
    request: Request,
    project_service: ProjectService = Depends(get_project_service),
) -> RedirectResponse:
    """Alterna o perfil de projeto ativo visualizado no painel.

    AUD-02.1 e AUD-03:
    - Validação de Host, Origem/Referer e Token CSRF obrigatório.
    - Seletor protegido: HallanCraft é preparatório na CC-01 e não altera fonte de dados.
    - Redirecionamento restrito a rotas locais conhecidas.
    """
    body_bytes = await request.body()
    parsed_body = urllib.parse.parse_qs(body_bytes.decode("utf-8", errors="ignore"))
    csrf_token = (
        parsed_body.get("csrf_token", [None])[0]
        or request.headers.get("x-csrf-token")
        or request.query_params.get("csrf_token")
    )

    # Validação estrita de segurança local e exigência incondicional de CSRF (AUD-02.1)
    validar_requisicao_post_segura(request, csrf_token=csrf_token)

    chave = parsed_body.get("project_key", [None])[0] or request.query_params.get("project_key")

    if chave:
        project_service.alternar_perfil(chave)

    destino = sanitizar_caminho_redirecionamento(request.headers.get("referer"))
    return RedirectResponse(url=destino, status_code=303)


@router.get("/api/projetos", response_class=JSONResponse)
async def list_projects_api(
    project_service: ProjectService = Depends(get_project_service),
) -> list[dict[str, Any]]:
    """Retorna os perfis de projetos configurados."""
    return project_service.listar_perfis()


@router.get("/api/projetos/ativo", response_class=JSONResponse)
async def get_active_project_api(
    project_service: ProjectService = Depends(get_project_service),
) -> dict[str, Any]:
    """Retorna o perfil do projeto atualmente ativo."""
    return project_service.obter_perfil_ativo()
