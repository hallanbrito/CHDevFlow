"""Rotas para o Modo Estudante Didático (Método C.H. e Governança de IA)."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from ch_control_center.config import DIRETORIO_TEMPLATES
from ch_control_center.dependencies import get_mission_service, get_project_service
from ch_control_center.security import obter_csrf_token
from ch_control_center.services.mission_service import MissionService
from ch_control_center.services.project_service import ProjectService
from ch_control_center.student.glossary import (
    EXPLICACOES_ESTADOS_MAQUINA,
    GLOSSARIO_METODO_CH,
    obter_glossario_completo,
)

router = APIRouter()
templates = Jinja2Templates(directory=str(DIRETORIO_TEMPLATES))
templates.env.globals["csrf_token"] = obter_csrf_token()


@router.get("/estudante", response_class=HTMLResponse)
async def student_view(
    request: Request,
    mission_service: MissionService = Depends(get_mission_service),
    project_service: ProjectService = Depends(get_project_service),
) -> HTMLResponse:
    """Renderiza a página educativa do Modo Estudante com glossário e explicações de estados."""
    contexto = {
        "active_page": "estudante",
        "projeto_ativo": project_service.obter_perfil_ativo(),
        "modo_operacao": mission_service.obter_modo_operacao(),
        "estados_maquina": EXPLICACOES_ESTADOS_MAQUINA,
        "termos": GLOSSARIO_METODO_CH,
    }
    return templates.TemplateResponse(request=request, name="student.html", context=contexto)


@router.get("/api/estudante/glossario", response_class=JSONResponse)
async def student_glossary_api() -> list[dict[str, Any]]:
    """Endpoint da API para consulta do glossário em formato JSON."""
    return obter_glossario_completo()
