"""Rotas para listagem e detalhamento de missões (Fatias W)."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from ch_control_center.config import DIRETORIO_TEMPLATES
from ch_control_center.dependencies import get_mission_service, get_project_service
from ch_control_center.security import obter_csrf_token
from ch_control_center.services.mission_service import MissionService
from ch_control_center.services.project_service import ProjectService

router = APIRouter()
templates = Jinja2Templates(directory=str(DIRETORIO_TEMPLATES))
templates.env.globals["csrf_token"] = obter_csrf_token()


@router.get("/missoes", response_class=HTMLResponse)
async def list_missions_view(
    request: Request,
    status: str = Query("TODOS", description="Filtro por status do grafo"),
    esteira: str = Query("TODAS", description="Filtro por esteira/executor"),
    busca: str | None = Query(None, description="Busca textual por título ou ID"),
    mission_service: MissionService = Depends(get_mission_service),
    project_service: ProjectService = Depends(get_project_service),
) -> HTMLResponse:
    """Renderiza a página com tabela completa e filtros de missões."""
    missoes = mission_service.listar_missoes(
        filtro_status=status,
        filtro_esteira=esteira,
        termo_busca=busca,
    )

    contexto = {
        "active_page": "missoes",
        "projeto_ativo": project_service.obter_perfil_ativo(),
        "modo_operacao": mission_service.obter_modo_operacao(),
        "missoes": missoes,
        "filtro_status": status,
        "filtro_esteira": esteira,
        "filtro_busca": busca,
    }
    return templates.TemplateResponse(request=request, name="missions.html", context=contexto)


@router.get("/api/missoes/{mission_id}", response_class=JSONResponse)
async def get_mission_detail_api(
    mission_id: str,
    mission_service: MissionService = Depends(get_mission_service),
) -> dict[str, Any]:
    """Retorna dados detalhados de uma missão em formato JSON (somente leitura)."""
    missao = mission_service.obter_missao_por_id(mission_id)
    if not missao:
        raise HTTPException(status_code=404, detail=f"Missão '{mission_id}' não encontrada.")
    return missao
