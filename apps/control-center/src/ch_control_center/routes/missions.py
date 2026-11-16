"""Rotas para listagem, detalhamento e despacho local de missões (Fatias W).

Conecta a interface do Control Center à execução local autorizada (Issue #121 / CC-DESPACHO-01).
Preserva 127.0.0.1, validação Host/Origin/CSRF e diferencia visualmente consultas
somente-leitura do GitHub das execuções locais de missões em laboratório descartável.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool

from ch_control_center.config import DIRETORIO_TEMPLATES
from ch_control_center.dependencies import (
    get_execution_service,
    get_mission_service,
    get_project_service,
)
from ch_control_center.security import (
    obter_csrf_token,
    validar_host_cabecalho,
    validar_requisicao_post_segura,
)
from ch_control_center.services.execution_service import (
    ExecutionConflictError,
    ExecutionNotFoundError,
    ExecutionService,
    ManifestValidationError,
)
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
    execution_service: ExecutionService = Depends(get_execution_service),
) -> HTMLResponse:
    """Renderiza a página com tabela completa, filtros de missões e painel de despacho."""
    missoes = await run_in_threadpool(
        mission_service.listar_missoes,
        filtro_status=status,
        filtro_esteira=esteira,
        termo_busca=busca,
    )
    estado_sync = mission_service.obter_estado_sincronizacao()
    execucao_ativa = await run_in_threadpool(execution_service.obter_execucao_ativa)

    contexto = {
        "active_page": "missoes",
        "projeto_ativo": project_service.obter_perfil_ativo(),
        "modo_operacao": mission_service.obter_modo_operacao(),
        "missoes": missoes,
        "filtro_status": status,
        "filtro_esteira": esteira,
        "filtro_busca": busca,
        "estado_sync": estado_sync,
        "execucao_ativa": execucao_ativa,
        "csrf_token": obter_csrf_token(),
    }
    return templates.TemplateResponse(request=request, name="missions.html", context=contexto)


@router.get("/api/missoes/execucoes/ativa", response_class=JSONResponse)
async def get_active_execution_api(
    request: Request,
    execution_service: ExecutionService = Depends(get_execution_service),
) -> dict[str, Any]:
    """Retorna dados da execução ativa atual, se houver."""
    validar_host_cabecalho(request)
    execucao = await run_in_threadpool(execution_service.obter_execucao_ativa)
    return execucao or {"ativa": False}


@router.get("/api/missoes/execucoes/{execution_id}", response_class=JSONResponse)
async def get_execution_detail_api(
    execution_id: str,
    request: Request,
    execution_service: ExecutionService = Depends(get_execution_service),
) -> dict[str, Any]:
    """Retorna dados detalhados e atualizados de uma execução local."""
    validar_host_cabecalho(request)
    execucao = await run_in_threadpool(execution_service.obter_execucao, execution_id)
    if not execucao:
        raise HTTPException(status_code=404, detail=f"Execução '{execution_id}' não encontrada.")
    return execucao


@router.post("/api/missoes/executar", response_class=JSONResponse, status_code=202)
async def dispatch_mission_execution_api(
    request: Request,
    execution_service: ExecutionService = Depends(get_execution_service),
) -> dict[str, Any]:
    """Inicia execução local de uma missão a partir de manifesto pré-preparado e validado."""
    content_type = request.headers.get("content-type", "")
    manifest_path: str | None = None
    confirmacao_po: bool = False
    timeout: int = 480
    csrf_token: str | None = None

    if "application/json" in content_type:
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Corpo da requisição JSON inválido.")
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="Corpo da requisição deve ser um objeto JSON.")
        manifest_path = body.get("manifest_path") or body.get("caminho_manifesto")
        raw_conf = body.get("confirmacao_po") if "confirmacao_po" in body else body.get("confirmation")
        if raw_conf is not True:
            raise HTTPException(
                status_code=400,
                detail="Confirmação explícita de execução pelo PO é obrigatória e deve ser o booleano True.",
            )
        confirmacao_po = True
        raw_timeout = body.get("timeout_segundos") or body.get("timeout")
        try:
            timeout = int(raw_timeout) if raw_timeout is not None else 480
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="Timeout deve ser um número inteiro válido.")
        csrf_token = body.get("csrf_token")
    else:
        try:
            form = await request.form()
            manifest_path = form.get("manifest_path") or form.get("caminho_manifesto")
            confirmacao_po = form.get("confirmacao_po") in ("true", "True", "1", True, "on") or form.get("confirmation") in ("true", "True", "1", True, "on")
            timeout_raw = form.get("timeout_segundos") or form.get("timeout")
            timeout = int(timeout_raw) if timeout_raw else 480
            csrf_token = form.get("csrf_token")
        except Exception:
            raise HTTPException(status_code=400, detail="Dados de formulário inválidos.")

    # Validação estrita de Host, Origin, Referer e CSRF Token (AUD-02.1)
    validar_requisicao_post_segura(request, csrf_token=csrf_token)

    if not manifest_path or not isinstance(manifest_path, str) or not manifest_path.strip():
        raise HTTPException(
            status_code=400,
            detail="Caminho do manifesto pré-preparado é obrigatório (nenhuma execução a partir de texto livre).",
        )

    try:
        resultado = await run_in_threadpool(
            execution_service.executar_missao,
            manifest_path=manifest_path.strip(),
            confirmacao_po=confirmacao_po,
            timeout_segundos=timeout,
        )
        return resultado
    except ExecutionConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ManifestValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erro interno ao despachar missão: {str(exc)}")


@router.post("/api/missoes/execucoes/{execution_id}/cancelar", response_class=JSONResponse)
async def cancel_execution_api(
    execution_id: str,
    request: Request,
    execution_service: ExecutionService = Depends(get_execution_service),
) -> dict[str, Any]:
    """Interrompe uma execução local ativa e encerra seus processos filhos."""
    csrf_token: str | None = None
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            body = await request.json()
            if isinstance(body, dict):
                csrf_token = body.get("csrf_token")
        except Exception:
            pass
    elif content_type:
        try:
            form = await request.form()
            csrf_token = form.get("csrf_token")
        except Exception:
            pass

    validar_requisicao_post_segura(request, csrf_token=csrf_token)
    try:
        resultado = await run_in_threadpool(execution_service.cancelar_execucao, execution_id)
        return resultado
    except ExecutionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/api/missoes/execucoes/{execution_id}/decisao", response_class=JSONResponse)
async def record_po_decision_api(
    execution_id: str,
    request: Request,
    execution_service: ExecutionService = Depends(get_execution_service),
) -> dict[str, Any]:
    """Registra formalmente a decisão do PO sobre a execução concluída."""
    csrf_token: str | None = None
    decisao: str | None = None
    justificativa: str | None = None

    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            body = await request.json()
            if isinstance(body, dict):
                decisao = body.get("decisao")
                justificativa = body.get("justificativa")
                csrf_token = body.get("csrf_token")
        except Exception:
            raise HTTPException(status_code=400, detail="JSON malformado.")
    else:
        form = await request.form()
        decisao = form.get("decisao")
        justificativa = form.get("justificativa")
        csrf_token = form.get("csrf_token")

    validar_requisicao_post_segura(request, csrf_token=csrf_token)
    if not decisao:
        raise HTTPException(
            status_code=400,
            detail="Campo 'decisao' é obrigatório (APROVADO, REPROVADO, AJUSTES).",
        )

    try:
        resultado = await run_in_threadpool(
            execution_service.registrar_decisao_po,
            execution_id=execution_id,
            decisao=decisao,
            justificativa=justificativa,
        )
        return resultado
    except ExecutionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/api/missoes/{mission_id}", response_class=JSONResponse)
async def get_mission_detail_api(
    mission_id: str,
    mission_service: MissionService = Depends(get_mission_service),
) -> dict[str, Any]:
    """Retorna dados detalhados de uma missão em formato JSON (somente leitura)."""
    missao = await run_in_threadpool(mission_service.obter_missao_por_id, mission_id)
    if not missao:
        raise HTTPException(status_code=404, detail=f"Missão '{mission_id}' não encontrada.")
    return missao
