"""Rotas para status e execução da sincronização de dados (CC-QUALITY-01)."""
from __future__ import annotations

import urllib.parse
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.concurrency import run_in_threadpool

from ch_control_center.dependencies import get_mission_service
from ch_control_center.security import (
    sanitizar_caminho_redirecionamento,
    validar_requisicao_post_segura,
)
from ch_control_center.services.mission_service import MissionService

router = APIRouter()


@router.get("/api/sincronizacao", response_class=JSONResponse)
async def get_sync_status(
    mission_service: MissionService = Depends(get_mission_service),
) -> dict[str, Any]:
    """Retorna o estado estruturado da sincronização em memória (F4)."""
    estado = mission_service.obter_estado_sincronizacao()
    # Se houver visão em cache, inclui resumo de contagens coerentes
    stats = {}
    if mission_service._cache_visao:
        stats = mission_service._cache_visao.get("stats", {})

    return {
        **estado.para_dicionario(),
        "stats": stats,
    }


@router.post("/api/sincronizar", response_class=JSONResponse)
async def trigger_sync_now(
    request: Request,
    mission_service: MissionService = Depends(get_mission_service),
) -> JSONResponse:
    """Aciona a atualização imediata ('Atualizar agora') sob demanda (F4).

    Protegido contra CSRF e requisições externas não autorizadas.
    """
    body_bytes = await request.body()
    parsed_body = urllib.parse.parse_qs(body_bytes.decode("utf-8", errors="ignore"))
    csrf_token = (
        request.headers.get("x-csrf-token")
        or parsed_body.get("csrf_token", [None])[0]
        or request.query_params.get("csrf_token")
    )

    validar_requisicao_post_segura(request, csrf_token=csrf_token)

    try:
        resultado = await run_in_threadpool(mission_service.sincronizar_agora)
        return JSONResponse(
            status_code=200 if resultado["status"] == "OK" else 503,
            content={
                "status": resultado["status"],
                "estado": resultado["estado"],
                "stats": resultado["stats"],
            },
        )
    except Exception as exc:
        erro_sanitizado = mission_service.facade.sanitizar(str(exc))
        return JSONResponse(
            status_code=503,
            content={
                "status": "ERROR",
                "estado": mission_service.obter_estado_sincronizacao().para_dicionario(),
                "erro": erro_sanitizado,
            },
        )


@router.post("/sincronizar")
async def trigger_sync_form(
    request: Request,
    mission_service: MissionService = Depends(get_mission_service),
) -> RedirectResponse:
    """Endpoint alternativo via POST de formulário HTML com redirecionamento seguro."""
    body_bytes = await request.body()
    parsed_body = urllib.parse.parse_qs(body_bytes.decode("utf-8", errors="ignore"))
    csrf_token = (
        parsed_body.get("csrf_token", [None])[0]
        or request.headers.get("x-csrf-token")
        or request.query_params.get("csrf_token")
    )

    validar_requisicao_post_segura(request, csrf_token=csrf_token)

    try:
        await run_in_threadpool(mission_service.sincronizar_agora)
    except Exception:
        # Erro fica registrado no estado de sincronização
        pass

    referer = request.headers.get("referer", "/")
    destino = sanitizar_caminho_redirecionamento(referer)
    return RedirectResponse(url=destino, status_code=303)
