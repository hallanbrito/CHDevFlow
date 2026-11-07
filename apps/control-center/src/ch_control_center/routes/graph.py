"""Rotas para visualização do Grafo de Dependências (DAG)."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool

from ch_control_center.config import DIRETORIO_TEMPLATES
from ch_control_center.dependencies import get_mission_service, get_project_service
from ch_control_center.security import obter_csrf_token
from ch_control_center.services.mission_service import MissionService
from ch_control_center.services.project_service import ProjectService

router = APIRouter()
templates = Jinja2Templates(directory=str(DIRETORIO_TEMPLATES))
templates.env.globals["csrf_token"] = obter_csrf_token()


@router.get("/grafo", response_class=HTMLResponse)
async def graph_view(
    request: Request,
    mission_service: MissionService = Depends(get_mission_service),
    project_service: ProjectService = Depends(get_project_service),
) -> HTMLResponse:
    """Renderiza a visualização topológica do Grafo de Dependências com alertas de ciclo/órfãs."""
    grafo = await run_in_threadpool(mission_service.obter_grafo_dag)
    estado_sync = mission_service.obter_estado_sincronizacao()

    contexto = {
        "active_page": "grafo",
        "projeto_ativo": project_service.obter_perfil_ativo(),
        "modo_operacao": mission_service.obter_modo_operacao(),
        "grafo": grafo,
        "estado_sync": estado_sync,
    }
    return templates.TemplateResponse(request=request, name="graph.html", context=contexto)


@router.get("/api/grafo", response_class=JSONResponse)
async def graph_api(
    mission_service: MissionService = Depends(get_mission_service),
) -> dict[str, Any]:
    """Retorna os dados estruturados do Grafo DAG em JSON para renderizadores dinâmicos."""
    grafo = await run_in_threadpool(mission_service.obter_grafo_dag)
    return grafo.para_dicionario()
