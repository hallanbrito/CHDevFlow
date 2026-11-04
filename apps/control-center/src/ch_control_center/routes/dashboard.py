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
    erro_leitura = None
    try:
        # AUD-05: Única leitura atômica de snapshot para todo o contexto do dashboard
        contexto_op = mission_service.obter_contexto_dashboard()
        stats = contexto_op["stats"]
        missoes = contexto_op["missoes"]
    except Exception as exc:
        # Não apresentar falha como projeto vazio. Sanitizar antes de renderizar;
        # o autoescape do Jinja protege também contra HTML vindo de mensagens.
        erro_leitura = mission_service.facade.sanitizar(str(exc))
        stats = {}
        missoes = []

    contexto = {
        "active_page": "dashboard",
        "projeto_ativo": project_service.obter_perfil_ativo(),
        "modo_operacao": mission_service.obter_modo_operacao(),
        "stats": stats,
        "missoes": missoes,
        "erro_leitura": erro_leitura,
    }
    return templates.TemplateResponse(
        request=request, name="dashboard.html", context=contexto,
        status_code=503 if erro_leitura else 200,
    )
