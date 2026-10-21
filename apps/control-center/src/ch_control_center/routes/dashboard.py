"""Rota do Dashboard principal de supervisão do Control Center."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from ch_control_center.config import DIRETORIO_TEMPLATES
from ch_control_center.dependencies import get_mission_service, get_project_service
from ch_control_center.security import obter_csrf_token
from ch_control_center.services.mission_service import MissionService
from ch_control_center.services.project_service import ProjectService

router = APIRouter()
templates = Jinja2Templates(directory=str(DIRETORIO_TEMPLATES))
templates.env.globals["csrf_token"] = obter_csrf_token()


@router.get("/", response_class=HTMLResponse)
async def dashboard_view(
    request: Request,
    mission_service: MissionService = Depends(get_mission_service),
    project_service: ProjectService = Depends(get_project_service),
) -> HTMLResponse:
    """Exibe o dashboard de supervisão consolidado com métricas do grafo DAG."""
    try:
        # AUD-05: Única leitura atômica de snapshot para todo o contexto do dashboard
        contexto_op = mission_service.obter_contexto_dashboard()
        stats = contexto_op["stats"]
        missoes = contexto_op["missoes"]
    except Exception as exc:
        # Modo fail-closed informativo em caso de falha de conexão remota no modo ao vivo
        stats = {
            "total_tarefas": 0,
            "total_elegiveis": 0,
            "total_bloqueadas": 0,
            "total_concluidas": 0,
            "total_ciclos": 0,
            "total_orfas": 0,
            "modo_operacao": mission_service.obter_modo_operacao(),
            "erro": str(exc),
        }
        missoes = []

    contexto = {
        "active_page": "dashboard",
        "projeto_ativo": project_service.obter_perfil_ativo(),
        "modo_operacao": mission_service.obter_modo_operacao(),
        "stats": stats,
        "missoes": missoes,
    }
    return templates.TemplateResponse(request=request, name="dashboard.html", context=contexto)
