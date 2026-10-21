"""Rotas para controle e alternância do Modo de Demonstração Offline."""
from __future__ import annotations

import urllib.parse
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse

from ch_control_center.config import MODO_DEMO_OFFLINE, MODO_LIVE_GITHUB
from ch_control_center.dependencies import get_mission_service
from ch_control_center.security import (
    sanitizar_caminho_redirecionamento,
    validar_csrf_token,
    validar_origem_local,
    validar_requisicao_post_segura,
)
from ch_control_center.services.mission_service import MissionService

router = APIRouter()


@router.post("/demo/alternar")
async def toggle_demo_mode(
    request: Request,
    mission_service: MissionService = Depends(get_mission_service),
) -> RedirectResponse:
    """Alterna entre o modo de demonstração offline e o modo ao vivo no GitHub.

    Protegido contra CSRF com validação de Host, Origin/Referer e Token obrigatório (AUD-02.1).
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

    modo_param = parsed_body.get("modo", [None])[0] or request.query_params.get("modo")

    modo_atual = mission_service.obter_modo_operacao()

    if modo_param:
        novo_modo = modo_param.upper().strip()
    else:
        novo_modo = MODO_LIVE_GITHUB if modo_atual == MODO_DEMO_OFFLINE else MODO_DEMO_OFFLINE

    mission_service.alternar_modo_operacao(novo_modo)

    # Redirecionamento restrito a rotas locais conhecidas (AUD-02)
    destino = sanitizar_caminho_redirecionamento(request.headers.get("referer"))
    return RedirectResponse(url=destino, status_code=303)


@router.get("/api/demo/status", response_class=JSONResponse)
async def demo_status_api(
    mission_service: MissionService = Depends(get_mission_service),
) -> dict[str, Any]:
    """Retorna o estado atual do modo de operação."""
    return {
        "modo_operacao": mission_service.obter_modo_operacao(),
        "is_offline": mission_service.obter_modo_operacao() == MODO_DEMO_OFFLINE,
    }
