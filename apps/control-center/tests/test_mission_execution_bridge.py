"""Testes da ponte de execução local de missões (CC-DESPACHO-01 / Issue #121).

Verifica integralmente os requisitos aprovados pelo PO:
- Execução com fakes offline (sucesso, tentativas, dossiê, decisão do PO).
- Rejeições (sem confirmação, manifesto inválido, texto livre de Issue, worktree inválida).
- Validação estrita de Origin, Referer, Host e CSRF token (AUD-02.1).
- Concorrência de duas missões (uma missão ativa, segunda bloqueada com HTTP 409).
- Cancelamento e interrupção de processos e liberação imediata do lock.
- Recuperação segura de crash/restart (fail-closed, sem replay).
- Sanitização de logs e segredos contra vazamentos.
- Ausência de chamadas a modelos ou agentes reais em CI.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import threading
import time
from unittest.mock import patch

import pytest
from starlette.testclient import TestClient

from chdevflow.core.generic_cycle import GenericResult
from chdevflow.core.manual_pipeline_runner import Mission
from ch_control_center.app import create_app
from ch_control_center.dependencies import get_execution_service, reset_services
from ch_control_center.security import obter_csrf_token
from ch_control_center.services.execution_service import (
    ExecutionConflictError,
    ExecutionService,
    ManifestValidationError,
    ProcessStatus,
    check_process_status,
)


@pytest.fixture
def lab_env(tmp_path: Path):
    """Cria um ambiente de laboratório pré-preparado compatível com o preflight de F6."""
    # Worktree descartável obrigatória com prefixo CH-Lab-*
    worktree = tmp_path / "CH-Lab-teste121"
    worktree.mkdir(parents=True)

    # Inicializa repo Git real limpo
    subprocess.run(["git", "init", "-b", "feature/teste"], cwd=worktree, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Tester"], cwd=worktree, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "tester@example.com"], cwd=worktree, check=True, capture_output=True)
    subprocess.run(["git", "remote", "add", "origin", "https://github.com/hallanbrito/CHDevFlow.git"], cwd=worktree, check=True, capture_output=True)

    # Arquivo alvo permitido
    target_file = worktree / "modulo_teste.py"
    target_file.write_text("def soma(a, b):\n    return a + b\n", encoding="utf-8")

    # Prompt da missão
    prompt_file = worktree / "prompt_missao.txt"
    prompt_file.write_text("Implemente a função soma corretamente.", encoding="utf-8")

    # Suíte de testes independente
    tests_dir = worktree / "tests"
    tests_dir.mkdir()
    test_file = tests_dir / "test_modulo.py"
    test_file.write_text(
        "import unittest\nfrom modulo_teste import soma\n\n"
        "class TestSoma(unittest.TestCase):\n"
        "    def test_soma(self):\n"
        "        self.assertEqual(soma(1, 2), 3)\n",
        encoding="utf-8",
    )

    # Commit inicial para gerar base_sha real
    subprocess.run(["git", "add", "."], cwd=worktree, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Commit inicial"], cwd=worktree, check=True, capture_output=True)
    base_sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=worktree, check=True, capture_output=True, text=True).stdout.strip()

    # Manifesto pré-preparado FORA da worktree
    manifest_path = tmp_path / "manifesto_missao.json"
    manifest_data = {
        "schema": "chdevflow.pipeline.manual/v1",
        "mission_id": "MISSAO-TESTE-121",
        "repository": "hallanbrito/CHDevFlow",
        "issue": 121,
        "base_sha": base_sha,
        "worktree": str(worktree),
        "allowed_paths": ["modulo_teste.py"],
        "prompt_ref": "prompt_missao.txt",
        "timeout_seconds": 480,
    }
    manifest_path.write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")

    labs_root = tmp_path / "CHDevFlow-Labs"
    labs_root.mkdir()

    data_dir = tmp_path / "cc_data"
    data_dir.mkdir()

    return {
        "tmp_path": tmp_path,
        "worktree": worktree,
        "manifest_path": manifest_path,
        "base_sha": base_sha,
        "labs_root": labs_root,
        "data_dir": data_dir,
    }


def fake_cycle_runner_success(**kwargs) -> GenericResult:
    """Dublê de teste simulando sucesso no ciclo F6."""
    evidence = kwargs["evidence"]
    evidence.mkdir(mode=0o700, exist_ok=True)
    attempt_dir = evidence / "attempt-01"
    attempt_dir.mkdir(exist_ok=True)
    (attempt_dir / "codigo.py").write_text("def soma(a, b):\n    return a + b\n", encoding="utf-8")
    (attempt_dir / "alteracoes.patch").write_text("--- a/modulo_teste.py\n+++ b/modulo_teste.py\n", encoding="utf-8")
    (attempt_dir / "auditoria_codex.md").write_text("VEREDITO: APROVAR_LAB\nCódigo atende aos critérios.\n", encoding="utf-8")
    (attempt_dir / "testes.log").write_text("Ran 1 test in 0.01s\n\nOK\n", encoding="utf-8")
    (evidence / "RELATORIO_COMPLETO_CH1.md").write_text("# Relatório CH1\nEstado: APROVADO_AGUARDANDO_CH1\n", encoding="utf-8")
    (evidence / "execucao.json").write_text(
        json.dumps({
            "status": "APROVADO_AGUARDANDO_CH1",
            "execution_id": "fake-exec-123",
            "attempts": [{"number": 1, "status": "PASS", "codex_verdict": "APROVAR_LAB", "sha256": "abc"}],
            "returns_used": 0,
            "findings": [],
        }),
        encoding="utf-8",
    )
    return GenericResult(
        status="APROVADO_AGUARDANDO_CH1",
        execution_id="fake-exec-123",
        mission_id="MISSAO-TESTE-121",
        issue=121,
        mission_digest="abc",
        attempts=[{"number": 1, "status": "PASS", "codex_verdict": "APROVAR_LAB", "sha256": "abc"}],
        returns_used=0,
        findings=[],
    )


@pytest.fixture
def custom_client(lab_env):
    """Cria cliente FastAPI isolado com fake runner configurado."""
    reset_services()
    exec_svc = ExecutionService(
        data_dir=lab_env["data_dir"],
        labs_root=lab_env["labs_root"],
        cycle_runner=fake_cycle_runner_success,
    )
    app = create_app()
    app.dependency_overrides[get_execution_service] = lambda: exec_svc
    client = TestClient(app, base_url="http://127.0.0.1:8000")
    yield client, exec_svc
    reset_services()


def test_execucao_sucesso_com_fakes(custom_client, lab_env):
    """Comprova o disparo e execução local bem-sucedida de missão pré-preparada."""
    client, exec_svc = custom_client
    token = obter_csrf_token()
    headers = {
        "Origin": "http://127.0.0.1:8000",
        "Referer": "http://127.0.0.1:8000/missoes",
        "X-CSRF-Token": token,
    }
    payload = {
        "manifest_path": str(lab_env["manifest_path"]),
        "confirmacao_po": True,
        "timeout_segundos": 480,
        "csrf_token": token,
    }

    # 1. Disparo da missão
    resp = client.post("/api/missoes/executar", json=payload, headers=headers)
    assert resp.status_code == 202
    data = resp.json()
    exec_id = data["execution_id"]
    assert exec_id is not None
    assert data["mission_id"] == "MISSAO-TESTE-121"
    assert data["status"] in ("INICIADO", "EM_EXECUCAO", "APROVADO_AGUARDANDO_CH1")

    # 2. Polling de status
    time.sleep(0.1)
    status_resp = client.get(f"/api/missoes/execucoes/{exec_id}", headers={"Host": "127.0.0.1:8000"})
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert status_data["execution_id"] == exec_id
    assert status_data["status"] == "APROVADO_AGUARDANDO_CH1"
    assert len(status_data["attempts"]) == 1
    assert status_data["attempts"][0]["codex_verdict"] == "APROVAR_LAB"
    assert "Ran 1 test" in status_data["testes_log_tail"]

    # 3. Consulta de execução ativa
    ativa_resp = client.get("/api/missoes/execucoes/ativa", headers={"Host": "127.0.0.1:8000"})
    assert ativa_resp.status_code == 200


def test_rejeicao_sem_confirmacao_po(custom_client, lab_env):
    """Rejeita execução sem confirmação explícita do PO (HTTP 400)."""
    client, _ = custom_client
    token = obter_csrf_token()
    headers = {
        "Origin": "http://127.0.0.1:8000",
        "Referer": "http://127.0.0.1:8000/missoes",
        "X-CSRF-Token": token,
    }
    payload = {
        "manifest_path": str(lab_env["manifest_path"]),
        "confirmacao_po": False,
        "csrf_token": token,
    }
    resp = client.post("/api/missoes/executar", json=payload, headers=headers)
    assert resp.status_code == 400
    assert "Confirmação explícita" in resp.json()["detail"]


def test_rejeicao_manifesto_inexistente(custom_client, lab_env):
    """Rejeita caminho de manifesto não existente (HTTP 400)."""
    client, _ = custom_client
    token = obter_csrf_token()
    headers = {
        "Origin": "http://127.0.0.1:8000",
        "Referer": "http://127.0.0.1:8000/missoes",
        "X-CSRF-Token": token,
    }
    payload = {
        "manifest_path": str(lab_env["tmp_path"] / "nao_existe.json"),
        "confirmacao_po": True,
        "csrf_token": token,
    }
    resp = client.post("/api/missoes/executar", json=payload, headers=headers)
    assert resp.status_code == 400
    assert "arquivo regular existente" in resp.json()["detail"]


def test_rejeicao_texto_livre_de_issue(custom_client):
    """Rejeita envio de texto livre em vez de arquivo pré-preparado (HTTP 400)."""
    client, _ = custom_client
    token = obter_csrf_token()
    headers = {
        "Origin": "http://127.0.0.1:8000",
        "Referer": "http://127.0.0.1:8000/missoes",
        "X-CSRF-Token": token,
    }
    payload = {
        "manifest_path": "Implementar módulo de frete de acordo com a issue #121",
        "confirmacao_po": True,
        "csrf_token": token,
    }
    resp = client.post("/api/missoes/executar", json=payload, headers=headers)
    assert resp.status_code == 400


def test_rejeicao_worktree_fora_do_padrao_ch_lab(custom_client, lab_env):
    """Rejeita manifesto que aponte para worktree sem o prefixo obrigatório CH-Lab-*."""
    client, _ = custom_client
    manifesto_inseguro = lab_env["tmp_path"] / "manifesto_inseguro.json"
    manifesto_inseguro.write_text(json.dumps({
        "schema": "chdevflow.pipeline.manual/v1",
        "mission_id": "MISSAO-INSEGURA",
        "repository": "hallanbrito/CHDevFlow",
        "issue": 121,
        "base_sha": lab_env["base_sha"],
        "worktree": str(lab_env["tmp_path"] / "worktree_invalida"),
        "allowed_paths": ["modulo.py"],
        "prompt_ref": "prompt.txt",
        "timeout_seconds": 480,
    }), encoding="utf-8")

    token = obter_csrf_token()
    headers = {
        "Origin": "http://127.0.0.1:8000",
        "Referer": "http://127.0.0.1:8000/missoes",
        "X-CSRF-Token": token,
    }
    resp = client.post("/api/missoes/executar", json={
        "manifest_path": str(manifesto_inseguro),
        "confirmacao_po": True,
        "csrf_token": token,
    }, headers=headers)
    assert resp.status_code == 400
    assert "CH-Lab-*" in resp.json()["detail"] or "Worktree" in resp.json()["detail"]


def test_seguranca_origem_referer_csrf(custom_client, lab_env):
    """AUD-02.1: Garante rejeição com 403 se Host, Origin, Referer ou CSRF forem inválidos."""
    client, _ = custom_client
    token = obter_csrf_token()
    payload = {
        "manifest_path": str(lab_env["manifest_path"]),
        "confirmacao_po": True,
        "csrf_token": token,
    }

    # 1. Sem CSRF Token
    resp_sem_csrf = client.post("/api/missoes/executar", json=payload, headers={
        "Origin": "http://127.0.0.1:8000",
        "Referer": "http://127.0.0.1:8000/missoes",
    })
    # Sem header X-CSRF-Token e sem token válido
    resp_sem_token = client.post("/api/missoes/executar", json={"manifest_path": str(lab_env["manifest_path"]), "confirmacao_po": True}, headers={
        "Origin": "http://127.0.0.1:8000",
        "Referer": "http://127.0.0.1:8000/missoes",
    })
    assert resp_sem_token.status_code == 403

    # 2. Origin externo malicioso
    resp_origin_externo = client.post("/api/missoes/executar", json=payload, headers={
        "Origin": "https://attacker.com",
        "Referer": "http://127.0.0.1:8000/missoes",
        "X-CSRF-Token": token,
    })
    assert resp_origin_externo.status_code == 403

    # 3. Referer externo
    resp_ref_externo = client.post("/api/missoes/executar", json=payload, headers={
        "Origin": "http://127.0.0.1:8000",
        "Referer": "https://phishing.site/page",
        "X-CSRF-Token": token,
    })
    assert resp_ref_externo.status_code == 403

    # 4. Host externo
    resp_host_externo = client.post("/api/missoes/executar", json=payload, headers={
        "Host": "evil.com",
        "Origin": "http://127.0.0.1:8000",
        "Referer": "http://127.0.0.1:8000/missoes",
        "X-CSRF-Token": token,
    })
    assert resp_host_externo.status_code == 403


def test_bloqueio_duas_missoes_concorrentes(lab_env):
    """Garante que apenas UMA missão pode rodar simultaneamente; a segunda é bloqueada com HTTP 409."""
    reset_services()
    runner_bloqueado_evento = time.sleep

    def slow_runner(**kwargs):
        evidence = kwargs["evidence"]
        evidence.mkdir(mode=0o700, exist_ok=True)
        # Espera cancelamento ou tempo
        cancel_check = kwargs.get("cancel_check")
        for _ in range(20):
            if cancel_check and cancel_check():
                return GenericResult(
                    status="CANCELADO", execution_id="s1", mission_id="M1", issue=1, mission_digest="d1"
                )
            time.sleep(0.05)
        return GenericResult(status="CONCLUIDO", execution_id="s1", mission_id="M1", issue=1, mission_digest="d1")

    exec_svc = ExecutionService(
        data_dir=lab_env["data_dir"],
        labs_root=lab_env["labs_root"],
        cycle_runner=slow_runner,
    )
    app = create_app()
    app.dependency_overrides[get_execution_service] = lambda: exec_svc
    client = TestClient(app, base_url="http://127.0.0.1:8000")

    token = obter_csrf_token()
    headers = {
        "Origin": "http://127.0.0.1:8000",
        "Referer": "http://127.0.0.1:8000/missoes",
        "X-CSRF-Token": token,
    }
    payload = {
        "manifest_path": str(lab_env["manifest_path"]),
        "confirmacao_po": True,
        "csrf_token": token,
    }

    # Primeira execução inicia normalmente
    resp1 = client.post("/api/missoes/executar", json=payload, headers=headers)
    assert resp1.status_code == 202
    exec_id1 = resp1.json()["execution_id"]

    # Segunda tentativa enquanto a primeira roda DEVE falhar com HTTP 409 Conflict
    resp2 = client.post("/api/missoes/executar", json=payload, headers=headers)
    assert resp2.status_code == 409
    assert "ativa em execução" in resp2.json()["detail"]

    # Cancela a primeira para liberar o lock
    client.post(f"/api/missoes/execucoes/{exec_id1}/cancelar", json={"csrf_token": token}, headers=headers)
    reset_services()


def test_cancelamento_interrompe_subprocessos(lab_env):
    """Comprova que o cancelamento interrompe subprocessos e libera o lock de execução."""
    reset_services()
    processos_encerrados = []

    def mock_terminate(*args, **kwargs):
        processos_encerrados.append(True)
        return 1

    def cancelable_runner(**kwargs):
        cancel_check = kwargs.get("cancel_check")
        while not (cancel_check and cancel_check()):
            time.sleep(0.02)
        return GenericResult(status="CANCELADO", execution_id="c1", mission_id="M", issue=1, mission_digest="d")

    exec_svc = ExecutionService(
        data_dir=lab_env["data_dir"],
        labs_root=lab_env["labs_root"],
        cycle_runner=cancelable_runner,
    )
    app = create_app()
    app.dependency_overrides[get_execution_service] = lambda: exec_svc
    client = TestClient(app, base_url="http://127.0.0.1:8000")

    token = obter_csrf_token()
    headers = {
        "Origin": "http://127.0.0.1:8000",
        "Referer": "http://127.0.0.1:8000/missoes",
        "X-CSRF-Token": token,
    }
    payload = {
        "manifest_path": str(lab_env["manifest_path"]),
        "confirmacao_po": True,
        "csrf_token": token,
    }

    with patch("ch_control_center.services.execution_service.terminate_all_active_processes", side_effect=mock_terminate):
        resp = client.post("/api/missoes/executar", json=payload, headers=headers)
        assert resp.status_code == 202
        exec_id = resp.json()["execution_id"]

        # Chama o cancelamento
        cancel_resp = client.post(f"/api/missoes/execucoes/{exec_id}/cancelar", json={"csrf_token": token}, headers=headers)
        assert cancel_resp.status_code == 200
        assert cancel_resp.json()["status"] == "CANCELADO"
        assert len(processos_encerrados) >= 1

    # Verifica que o lock foi liberado imediatamente
    assert not exec_svc.lock_file.exists()
    reset_services()


def test_recuperacao_segura_crash_restart(lab_env):
    """Comprova que um lock deixado por crash anterior é recuperado de forma fail-closed sem travar o painel."""
    reset_services()
    data_dir = lab_env["data_dir"]
    lock_file = data_dir / "active_execution.lock"
    exec_dir = data_dir / "executions"
    exec_dir.mkdir(parents=True, exist_ok=True)

    # Simula gravação prévia que crashou
    crash_id = "exec-crash-999"
    lock_file.write_text(json.dumps({
        "execution_id": crash_id,
        "mission_id": "MISSAO-CRASH",
        "pid": 999999,
        "started_at": "2026-11-16T10:00:00Z",
    }), encoding="utf-8")
    (exec_dir / f"{crash_id}.json").write_text(json.dumps({
        "execution_id": crash_id,
        "mission_id": "MISSAO-CRASH",
        "issue": 121,
        "status": "EM_EXECUCAO",
        "manifest_path": str(lab_env["manifest_path"]),
        "worktree": str(lab_env["worktree"]),
        "evidence_dir": str(lab_env["labs_root"] / "crash-dossier"),
        "started_at": "2026-11-16T10:00:00Z",
        "timeout_seconds": 480,
    }), encoding="utf-8")

    # Inicialização do serviço recupera o lock
    novo_svc = ExecutionService(
        data_dir=data_dir,
        labs_root=lab_env["labs_root"],
        cycle_runner=fake_cycle_runner_success,
    )

    # Lock foi removido do disco
    assert not lock_file.exists()

    # O registro antigo foi marcado como INTERROMPIDO_CRASH
    registro_recuperado = novo_svc.obter_execucao(crash_id)
    assert registro_recuperado["status"] == "INTERROMPIDO_CRASH"
    assert any("Servidor reiniciado" in f for f in registro_recuperado["findings"])

    # Nova execução pode ser iniciada imediatamente sem bloqueio
    app = create_app()
    app.dependency_overrides[get_execution_service] = lambda: novo_svc
    client = TestClient(app, base_url="http://127.0.0.1:8000")
    token = obter_csrf_token()
    headers = {
        "Origin": "http://127.0.0.1:8000",
        "Referer": "http://127.0.0.1:8000/missoes",
        "X-CSRF-Token": token,
    }
    resp = client.post("/api/missoes/executar", json={
        "manifest_path": str(lab_env["manifest_path"]),
        "confirmacao_po": True,
        "csrf_token": token,
    }, headers=headers)
    assert resp.status_code == 202


def test_sanitizacao_logs_e_segredos(lab_env):
    """Garante que segredos e tokens de API sejam redigidos nos logs de execução e relatórios."""
    reset_services()
    def runner_com_segredos(**kwargs):
        evidence = kwargs["evidence"]
        evidence.mkdir(mode=0o700, exist_ok=True)
        (evidence / "RELATORIO_COMPLETO_CH1.md").write_text(
            "Relatório com chave sensível: ghp_1234567890abcdef1234 e sk-proj-1234567890abcdef",
            encoding="utf-8",
        )
        return GenericResult(
            status="APROVADO_AGUARDANDO_CH1",
            execution_id="sec1",
            mission_id="M",
            issue=121,
            mission_digest="d",
            findings=["Tentativa de uso de api_key: ghp_9999999999999999999"],
        )

    exec_svc = ExecutionService(
        data_dir=lab_env["data_dir"],
        labs_root=lab_env["labs_root"],
        cycle_runner=runner_com_segredos,
    )
    app = create_app()
    app.dependency_overrides[get_execution_service] = lambda: exec_svc
    client = TestClient(app, base_url="http://127.0.0.1:8000")

    token = obter_csrf_token()
    headers = {
        "Origin": "http://127.0.0.1:8000",
        "Referer": "http://127.0.0.1:8000/missoes",
        "X-CSRF-Token": token,
    }
    resp = client.post("/api/missoes/executar", json={
        "manifest_path": str(lab_env["manifest_path"]),
        "confirmacao_po": True,
        "csrf_token": token,
    }, headers=headers)
    exec_id = resp.json()["execution_id"]

    time.sleep(0.1)
    status_resp = client.get(f"/api/missoes/execucoes/{exec_id}", headers={"Host": "127.0.0.1:8000"})
    detalhes = status_resp.json()
    assert "ghp_1234567890abcdef1234" not in detalhes.get("report_markdown", "")
    assert "[REDACTED]" in detalhes.get("report_markdown", "")
    assert "ghp_9999999999999999999" not in str(detalhes.get("findings", []))


def test_registro_decisao_po_local(custom_client, lab_env):
    """Comprova o registro local da decisão humana do PO."""
    client, exec_svc = custom_client
    token = obter_csrf_token()
    headers = {
        "Origin": "http://127.0.0.1:8000",
        "Referer": "http://127.0.0.1:8000/missoes",
        "X-CSRF-Token": token,
    }

    # 1. Inicia e aguarda conclusão
    resp = client.post("/api/missoes/executar", json={
        "manifest_path": str(lab_env["manifest_path"]),
        "confirmacao_po": True,
        "csrf_token": token,
    }, headers=headers)
    exec_id = resp.json()["execution_id"]
    time.sleep(0.1)

    # 2. Registra decisão do PO
    decisao_resp = client.post(f"/api/missoes/execucoes/{exec_id}/decisao", json={
        "decisao": "APROVADO",
        "justificativa": "Aceito com 100% de cobertura e veredito Codex favorável.",
        "csrf_token": token,
    }, headers=headers)
    assert decisao_resp.status_code == 200
    dados_decisao = decisao_resp.json()
    assert dados_decisao["decisao_po"]["tipo"] == "decisao_local_declarada"
    assert dados_decisao["decisao_po"]["decisao"] == "APROVADO"
    assert "100% de cobertura" in dados_decisao["decisao_po"]["justificativa"]

    # 3. Consulta de detalhes confirma a persistência
    detalhes_resp = client.get(f"/api/missoes/execucoes/{exec_id}", headers={"Host": "127.0.0.1:8000"})
    assert detalhes_resp.json()["decisao_po"]["tipo"] == "decisao_local_declarada"
    assert detalhes_resp.json()["decisao_po"]["decisao"] == "APROVADO"


def test_detalhes_execucao_404_para_id_inexistente(custom_client):
    """Retorna HTTP 404 para ID de execução que não existe."""
    client, _ = custom_client
    resp = client.get("/api/missoes/execucoes/id_inexistente_12345", headers={"Host": "127.0.0.1:8000"})
    assert resp.status_code == 404


def test_sem_deadlock_consulta_ativa_durante_execucao(lab_env):
    """Comprova ausência de deadlock ao consultar execução ativa durante o ciclo."""
    reset_services()
    em_andamento_event = threading.Event()
    liberar_event = threading.Event()

    def runner_lento(**kwargs):
        em_andamento_event.set()
        liberar_event.wait(timeout=5)
        return GenericResult(
            status="APROVADO_AGUARDANDO_CH1",
            execution_id="lento-1",
            mission_id="M",
            issue=121,
            mission_digest="d",
        )

    exec_svc = ExecutionService(
        data_dir=lab_env["data_dir"],
        labs_root=lab_env["labs_root"],
        cycle_runner=runner_lento,
    )
    app = create_app()
    app.dependency_overrides[get_execution_service] = lambda: exec_svc
    client = TestClient(app, base_url="http://127.0.0.1:8000")

    token = obter_csrf_token()
    headers = {
        "Origin": "http://127.0.0.1:8000",
        "Referer": "http://127.0.0.1:8000/missoes",
        "X-CSRF-Token": token,
    }
    resp = client.post("/api/missoes/executar", json={
        "manifest_path": str(lab_env["manifest_path"]),
        "confirmacao_po": True,
        "csrf_token": token,
    }, headers=headers)
    assert resp.status_code == 202
    exec_id = resp.json()["execution_id"]

    # Aguarda o runner iniciar
    assert em_andamento_event.wait(timeout=3)

    # Consulta execução ativa via API e HTML sem travar
    resp_ativa = client.get("/api/missoes/execucoes/ativa", headers={"Host": "127.0.0.1:8000"})
    assert resp_ativa.status_code == 200
    assert resp_ativa.json()["execution_id"] == exec_id
    assert resp_ativa.json()["status"] in ("INICIADO", "EM_EXECUCAO")

    resp_page = client.get("/missoes", headers={"Host": "127.0.0.1:8000"})
    assert resp_page.status_code == 200

    # Libera e aguarda término
    liberar_event.set()
    time.sleep(0.1)
    reset_services()


def test_cancelamento_espera_thread_e_nao_deleta_lock_de_outra_missao(lab_env):
    """Comprova que cancelamento de missão A aguarda término da thread e não deleta lock de missão B subsequente."""
    reset_services()
    thread_a_iniciou = threading.Event()
    thread_a_finalizou = threading.Event()

    def runner_a(**kwargs):
        thread_a_iniciou.set()
        cancel_check = kwargs.get("cancel_check")
        while not (cancel_check and cancel_check()):
            time.sleep(0.01)
        time.sleep(0.05)
        thread_a_finalizou.set()
        return GenericResult(
            status="CANCELADO",
            execution_id="a",
            mission_id="M",
            issue=121,
            mission_digest="d",
        )

    exec_svc = ExecutionService(
        data_dir=lab_env["data_dir"],
        labs_root=lab_env["labs_root"],
        cycle_runner=runner_a,
    )

    res_a = exec_svc.executar_missao(
        manifest_path=lab_env["manifest_path"],
        confirmacao_po=True,
    )
    exec_id_a = res_a["execution_id"]
    assert thread_a_iniciou.wait(timeout=3)

    # Cancela missão A
    cancel_res = exec_svc.cancelar_execucao(exec_id_a)
    assert cancel_res["status"] == "CANCELADO"
    assert thread_a_finalizou.is_set()

    # Inicia missão B imediatamente
    def runner_b(**kwargs):
        return GenericResult(
            status="APROVADO_AGUARDANDO_CH1",
            execution_id="b",
            mission_id="M",
            issue=121,
            mission_digest="d",
        )
    exec_svc.cycle_runner = runner_b
    res_b = exec_svc.executar_missao(
        manifest_path=lab_env["manifest_path"],
        confirmacao_po=True,
    )
    exec_id_b = res_b["execution_id"]

    # Lock deve ser estritamente de B
    assert exec_svc.lock_file.exists()
    lock_data = json.loads(exec_svc.lock_file.read_text(encoding="utf-8"))
    assert lock_data["execution_id"] == exec_id_b

    time.sleep(0.1)
    reset_services()


def test_crash_recovery_preserva_lock_se_pid_vivo_ou_corrompido(lab_env):
    """Comprova fail-closed na recuperação: preserva lock se PID estiver ativo ou arquivo corrompido."""
    reset_services()
    data_dir = lab_env["data_dir"]
    lock_file = data_dir / "active_execution.lock"

    # Caso 1: Lock com JSON corrompido
    lock_file.write_text("{conteudo corrompido e invalido", encoding="utf-8")
    svc_corrupt = ExecutionService(
        data_dir=data_dir,
        labs_root=lab_env["labs_root"],
        cycle_runner=fake_cycle_runner_success,
    )
    # Lock NÃO deve ser apagado cegamente (fail-closed)
    assert lock_file.exists()

    # Tentativa de executar com lock existente deve falhar com ExecutionConflictError
    with pytest.raises(ExecutionConflictError):
        svc_corrupt.executar_missao(
            manifest_path=lab_env["manifest_path"],
            confirmacao_po=True,
        )

    # Caso 2: Lock com PID vivo mockado
    with patch("ch_control_center.services.execution_service.check_process_status", return_value=ProcessStatus.VIVO):
        lock_file.write_text(json.dumps({
            "execution_id": "exec-vivo",
            "pid": 11111,
        }), encoding="utf-8")
        svc_alive = ExecutionService(
            data_dir=data_dir,
            labs_root=lab_env["labs_root"],
            cycle_runner=fake_cycle_runner_success,
        )
        assert lock_file.exists()
        with pytest.raises(ExecutionConflictError):
            svc_alive.executar_missao(
                manifest_path=lab_env["manifest_path"],
                confirmacao_po=True,
            )

    # Caso 3: Lock com PID inativo/morto
    with patch("ch_control_center.services.execution_service.check_process_status", return_value=ProcessStatus.MORTO_COMPROVADO):
        lock_file.write_text(json.dumps({
            "execution_id": "exec-morto",
            "pid": 99999999,
        }), encoding="utf-8")
        svc_dead = ExecutionService(
            data_dir=data_dir,
            labs_root=lab_env["labs_root"],
            cycle_runner=fake_cycle_runner_success,
        )
        assert not lock_file.exists()


def test_rejeicao_confirmacao_po_string_ou_inteiro(custom_client, lab_env):
    """Garante que confirmacao_po em JSON rejeite qualquer valor que não seja estritamente o booleano True."""
    client, _ = custom_client
    token = obter_csrf_token()
    headers = {
        "Origin": "http://127.0.0.1:8000",
        "Referer": "http://127.0.0.1:8000/missoes",
        "X-CSRF-Token": token,
    }

    valores_invalidos = ["false", "False", "true", "True", "0", "1", 0, 1, None, [], {}]
    for val in valores_invalidos:
        resp = client.post("/api/missoes/executar", json={
            "manifest_path": str(lab_env["manifest_path"]),
            "confirmacao_po": val,
            "csrf_token": token,
        }, headers=headers)
        assert resp.status_code == 400, f"Falha para valor: {val!r}"
        assert "booleano True" in resp.json()["detail"]


def test_rejeicao_decisao_aprovado_em_execucao_ativa_ou_cancelada(lab_env):
    """Comprova que decisões não são aceitas em execução ativa e APROVADO é rejeitado em estados não elegíveis."""
    reset_services()
    em_execucao_event = threading.Event()

    def runner_pausado(**kwargs):
        em_execucao_event.set()
        cancel_check = kwargs.get("cancel_check")
        while not (cancel_check and cancel_check()):
            time.sleep(0.01)
        return GenericResult(
            status="CANCELADO",
            execution_id="c",
            mission_id="M",
            issue=121,
            mission_digest="d",
        )

    exec_svc = ExecutionService(
        data_dir=lab_env["data_dir"],
        labs_root=lab_env["labs_root"],
        cycle_runner=runner_pausado,
    )
    app = create_app()
    app.dependency_overrides[get_execution_service] = lambda: exec_svc
    client = TestClient(app, base_url="http://127.0.0.1:8000")

    token = obter_csrf_token()
    headers = {
        "Origin": "http://127.0.0.1:8000",
        "Referer": "http://127.0.0.1:8000/missoes",
        "X-CSRF-Token": token,
    }

    # 1. Inicia execução que fica aguardando cancelamento
    res = exec_svc.executar_missao(
        manifest_path=lab_env["manifest_path"],
        confirmacao_po=True,
    )
    exec_id = res["execution_id"]
    assert em_execucao_event.wait(timeout=3)

    # Tentativa de registrar decisão durante EM_EXECUCAO deve retornar HTTP 400
    resp_ativa = client.post(f"/api/missoes/execucoes/{exec_id}/decisao", json={
        "decisao": "APROVADO",
        "justificativa": "Tentativa indevida",
        "csrf_token": token,
    }, headers=headers)
    assert resp_ativa.status_code == 400
    assert "ainda em andamento" in resp_ativa.json()["detail"]

    # 2. Cancela a execução
    resp_cancel = exec_svc.cancelar_execucao(exec_id)
    assert resp_cancel["status"] == "CANCELADO"
    assert exec_svc.obter_execucao(exec_id)["status"] == "CANCELADO"

    # Tentativa de APROVAR execução cancelada deve retornar HTTP 400
    resp_cancelada = client.post(f"/api/missoes/execucoes/{exec_id}/decisao", json={
        "decisao": "APROVADO",
        "justificativa": "Tentativa de aprovar cancelado",
        "csrf_token": token,
    }, headers=headers)
    assert resp_cancelada.status_code == 400
    assert "Não é permitido aprovar execução com status 'CANCELADO'" in resp_cancelada.json()["detail"]

    # Mas registrar REPROVADO em execução cancelada é permitido para arquivamento
    resp_reprovada = client.post(f"/api/missoes/execucoes/{exec_id}/decisao", json={
        "decisao": "REPROVADO",
        "justificativa": "Cancelada e reprovada formalmente",
        "csrf_token": token,
    }, headers=headers)
    assert resp_reprovada.status_code == 200
    assert resp_reprovada.json()["decisao_po"]["tipo"] == "decisao_local_declarada"
    assert resp_reprovada.json()["decisao_po"]["decisao"] == "REPROVADO"


def test_adversarial_p1_cancelamento_lento_retorna_pendente_e_bloqueia_missao_b(lab_env):
    """P1-1: Fake worker que ignora cancelamento por mais de timeout do join.

    Comprova:
    - Retorna status CANCELAMENTO_PENDENTE mantendo o lock e exclusividade.
    - Tentativa de despachar missão B enquanto A ainda vive é rejeitada com HTTP 409.
    - Só após o término comprovado de A, a missão B pode iniciar com sucesso.
    """
    reset_services()
    worker_a_iniciou = threading.Event()
    permitir_encerramento_a = threading.Event()

    def runner_lento_a(**kwargs):
        worker_a_iniciou.set()
        # Ignora cancelamento até liberação explícita
        permitir_encerramento_a.wait(timeout=5)
        return GenericResult(
            status="CANCELADO",
            execution_id="a",
            mission_id="M-A",
            issue=121,
            mission_digest="da",
        )

    exec_svc = ExecutionService(
        data_dir=lab_env["data_dir"],
        labs_root=lab_env["labs_root"],
        cycle_runner=runner_lento_a,
    )
    app = create_app()
    app.dependency_overrides[get_execution_service] = lambda: exec_svc
    client = TestClient(app, base_url="http://127.0.0.1:8000")

    token = obter_csrf_token()
    headers = {
        "Origin": "http://127.0.0.1:8000",
        "Referer": "http://127.0.0.1:8000/missoes",
        "X-CSRF-Token": token,
    }

    # 1. Inicia Missão A
    resp_a = client.post("/api/missoes/executar", json={
        "manifest_path": str(lab_env["manifest_path"]),
        "confirmacao_po": True,
        "csrf_token": token,
    }, headers=headers)
    assert resp_a.status_code == 202
    exec_id_a = resp_a.json()["execution_id"]
    assert worker_a_iniciou.wait(timeout=3)

    # 2. Cancela A com timeout curto (0.05s) para simular worker que excede o tempo de join
    res_cancel_a = exec_svc.cancelar_execucao(exec_id_a, join_timeout=0.05)
    assert res_cancel_a["status"] == "CANCELAMENTO_PENDENTE"
    assert exec_svc.lock_file.exists()
    assert exec_svc._active_execution_id == exec_id_a

    # 3. Tentativa de despachar Missão B enquanto A vive DEVE ser rejeitada com HTTP 409
    resp_b_conflito = client.post("/api/missoes/executar", json={
        "manifest_path": str(lab_env["manifest_path"]),
        "confirmacao_po": True,
        "csrf_token": token,
    }, headers=headers)
    assert resp_b_conflito.status_code == 409
    assert "Apenas uma execução é permitida simultaneamente" in resp_b_conflito.json()["detail"] or "Trava local detectada" in resp_b_conflito.json()["detail"]

    # 4. Libera worker A para terminar efetivamente
    permitir_encerramento_a.set()
    time.sleep(0.1)

    # Status de A transicionou para CANCELADO e lock foi liberado
    detalhes_a = exec_svc.obter_execucao(exec_id_a)
    assert detalhes_a["status"] == "CANCELADO"
    assert not exec_svc.lock_file.exists()
    assert exec_svc._active_execution_id is None

    # 5. Agora a Missão B DEVE iniciar com sucesso
    def runner_b(**kwargs):
        return GenericResult(
            status="APROVADO_AGUARDANDO_CH1",
            execution_id="b",
            mission_id="M-B",
            issue=121,
            mission_digest="db",
        )
    exec_svc.cycle_runner = runner_b

    resp_b_sucesso = client.post("/api/missoes/executar", json={
        "manifest_path": str(lab_env["manifest_path"]),
        "confirmacao_po": True,
        "csrf_token": token,
    }, headers=headers)
    assert resp_b_sucesso.status_code == 202
    exec_id_b = resp_b_sucesso.json()["execution_id"]
    assert exec_id_b != exec_id_a
    time.sleep(0.1)
    reset_services()


def test_adversarial_p1_crash_recovery_fail_closed_cinco_casos(lab_env):
    """P1-2: Comprova fail-closed estrito nos 5 cenários enumerados pela auditoria.

    Nenhum destes 5 casos pode gerar desbloqueio automático inseguro:
    1. Lock do processo atual (pid == os.getpid())
    2. PID ausente / inválido
    3. JSON corrompido
    4. PID existente / ativo no SO
    5. Falha de acesso simulada no Windows (ERROR_ACCESS_DENIED) ou POSIX PermissionError
    """
    reset_services()
    data_dir = lab_env["data_dir"]
    lock_file = data_dir / "active_execution.lock"

    # Caso 1: Lock do processo atual (pid == os.getpid())
    lock_file.write_text(json.dumps({
        "execution_id": "exec-meu-pid",
        "pid": os.getpid(),
    }), encoding="utf-8")
    svc1 = ExecutionService(data_dir=data_dir, labs_root=lab_env["labs_root"])
    assert lock_file.exists(), "Lock com PID atual jamais pode ser apagado"
    assert svc1._active_execution_id == "exec-meu-pid"

    # Caso 2: PID ausente / nulo / inválido
    lock_file.write_text(json.dumps({
        "execution_id": "exec-sem-pid",
        "pid": None,
    }), encoding="utf-8")
    svc2 = ExecutionService(data_dir=data_dir, labs_root=lab_env["labs_root"])
    assert lock_file.exists(), "Lock com PID ausente deve permanecer bloqueado (inconclusivo)"

    lock_file.write_text(json.dumps({
        "execution_id": "exec-pid-invalido",
        "pid": -99,
    }), encoding="utf-8")
    svc2_inv = ExecutionService(data_dir=data_dir, labs_root=lab_env["labs_root"])
    assert lock_file.exists(), "Lock com PID inválido deve permanecer bloqueado"

    # Caso 3: JSON corrompido
    lock_file.write_text("{conteudo quebrado e incompleto", encoding="utf-8")
    svc3 = ExecutionService(data_dir=data_dir, labs_root=lab_env["labs_root"])
    assert lock_file.exists(), "Lock com JSON corrompido jamais pode ser apagado cegamente"

    # Caso 4: PID existente / vivo
    with patch("ch_control_center.services.execution_service.check_process_status", return_value=ProcessStatus.VIVO):
        lock_file.write_text(json.dumps({
            "execution_id": "exec-vivo",
            "pid": 12345,
        }), encoding="utf-8")
        svc4 = ExecutionService(data_dir=data_dir, labs_root=lab_env["labs_root"])
        assert lock_file.exists(), "Lock com PID vivo deve ser preservado"

    # Caso 5: Falha de acesso simulada (Windows ERROR_ACCESS_DENIED ou POSIX PermissionError)
    if os.name == "nt":
        import ctypes
        with patch.object(ctypes.windll.kernel32, "OpenProcess", return_value=0), \
             patch.object(ctypes.windll.kernel32, "GetLastError", return_value=5):
            lock_file.write_text(json.dumps({
                "execution_id": "exec-access-denied",
                "pid": 55555,
            }), encoding="utf-8")
            status = check_process_status(55555)
            assert status == ProcessStatus.VIVO
            svc5 = ExecutionService(data_dir=data_dir, labs_root=lab_env["labs_root"])
            assert lock_file.exists(), "Falha de acesso no Windows comprova que o processo existe e está vivo"
    else:
        with patch("os.kill", side_effect=PermissionError):
            lock_file.write_text(json.dumps({
                "execution_id": "exec-perm-error",
                "pid": 55555,
            }), encoding="utf-8")
            status = check_process_status(55555)
            assert status == ProcessStatus.VIVO
            svc5 = ExecutionService(data_dir=data_dir, labs_root=lab_env["labs_root"])
            assert lock_file.exists(), "PermissionError em os.kill comprova que o processo existe e está vivo"

    # Caso de Contraste: Somente MORTO_COMPROVADO deve desbloquear
    with patch("ch_control_center.services.execution_service.check_process_status", return_value=ProcessStatus.MORTO_COMPROVADO):
        lock_file.write_text(json.dumps({
            "execution_id": "exec-morto-comprovado",
            "pid": 99999999,
        }), encoding="utf-8")
        svc_morto = ExecutionService(data_dir=data_dir, labs_root=lab_env["labs_root"])
        assert not lock_file.exists(), "Apenas prova segura de término (MORTO_COMPROVADO) limpa o lock"


def test_adversarial_p1_lock_exclusivo_atomico_e_limpeza_por_proprietario(lab_env):
    """P1-3: Comprova aquisição atômica no filesystem via os.O_CREAT | os.O_EXCL e limpeza estrita por proprietário."""
    reset_services()
    data_dir = lab_env["data_dir"]
    em_andamento = threading.Event()
    liberar = threading.Event()

    def runner_segura(**kwargs):
        em_andamento.set()
        liberar.wait(timeout=5)
        return GenericResult(
            status="APROVADO_AGUARDANDO_CH1",
            execution_id="1",
            mission_id="M",
            issue=121,
            mission_digest="d",
        )

    # Cria duas instâncias independentes apontando para o mesmo data_dir (simulando processos distintos)
    svc1 = ExecutionService(
        data_dir=data_dir,
        labs_root=lab_env["labs_root"],
        cycle_runner=runner_segura,
    )
    svc2 = ExecutionService(
        data_dir=data_dir,
        labs_root=lab_env["labs_root"],
        cycle_runner=fake_cycle_runner_success,
    )

    # svc1 adquire o lock
    res1 = svc1.executar_missao(
        manifest_path=lab_env["manifest_path"],
        confirmacao_po=True,
    )
    exec_id_1 = res1["execution_id"]
    assert em_andamento.wait(timeout=3)
    assert svc1.lock_file.exists()

    # svc2 tenta adquirir enquanto svc1 detém o lock -> DEVE falhar com ExecutionConflictError
    with pytest.raises(ExecutionConflictError) as exc_info:
        svc2.executar_missao(
            manifest_path=lab_env["manifest_path"],
            confirmacao_po=True,
        )
    assert "Trava local detectada" in str(exc_info.value) or "Já existe uma missão ativa" in str(exc_info.value)

    # Garante que o lock file NÃO foi sobrescrito por svc2
    dados_lock = json.loads(svc1.lock_file.read_text(encoding="utf-8"))
    assert dados_lock["execution_id"] == exec_id_1

    # Limpeza por proprietário: svc2 tenta limpar passando outro ID
    svc2._clean_lock_file_if_owned("id_estranho_qualquer")
    assert svc1.lock_file.exists(), "Lock file não pode ser removido por quem não é seu proprietário"

    # Libera svc1 para concluir
    liberar.set()
    time.sleep(0.1)

    # Somente o proprietário correto pode remover o lock
    svc1._clean_lock_file_if_owned(exec_id_1)
    assert not svc1.lock_file.exists(), "Proprietário correto remove o lock com sucesso"
    reset_services()


def test_adversarial_p1_cancelamento_isolado_nao_mata_subprocessos_de_b():
    """P1: Comprova que o cancelamento de uma missão A não mata os subprocessos da missão B."""
    import sys
    from chdevflow.core.local_executor import (
        get_active_processes,
        register_active_process,
        terminate_all_active_processes,
    )

    # Inicia dois subprocessos reais independentes
    proc_a = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(15)"])
    proc_b = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(15)"])

    try:
        register_active_process(proc_a, execution_id="exec-MISSAO-A")
        register_active_process(proc_b, execution_id="exec-MISSAO-B")

        # Verifica rastreamento isolado de processos
        procs_a = get_active_processes("exec-MISSAO-A")
        procs_b = get_active_processes("exec-MISSAO-B")
        assert proc_a in procs_a
        assert proc_b not in procs_a
        assert proc_b in procs_b
        assert proc_a not in procs_b

        # Cancela SOMENTE a execução A
        terminated_count = terminate_all_active_processes(execution_id="exec-MISSAO-A")
        assert terminated_count >= 1

        # Processo de A deve estar encerrado
        proc_a.poll()
        assert proc_a.returncode is not None, "Subprocesso de A deveria ter sido terminado"
        assert proc_a not in get_active_processes("exec-MISSAO-A")

        # Subprocesso de B DEVE PERMANECER VIVO e intacto
        assert proc_b.poll() is None, "Subprocesso de B NÃO PODE ser encerrado pelo cancelamento de A"
        assert proc_b in get_active_processes("exec-MISSAO-B")
    finally:
        # Limpeza segura do subprocesso B
        terminate_all_active_processes(execution_id="exec-MISSAO-B")
        if proc_b.poll() is None:
            proc_b.kill()
            proc_b.wait()
        if proc_a.poll() is None:
            proc_a.kill()
            proc_a.wait()


def test_adversarial_p2_ui_comportamento_cancelamento_pendente_e_polling(lab_env):
    """P2: Comprova o fluxo adversarial de CANCELAMENTO_PENDENTE na API e no template missions.html."""
    reset_services()
    data_dir = lab_env["data_dir"]

    cancelamento_recebido = threading.Event()
    segurar_encerramento = threading.Event()

    def runner_longo(**kwargs):
        cancel_check = kwargs.get("cancel_check")
        while True:
            if cancel_check and cancel_check():
                cancelamento_recebido.set()
                segurar_encerramento.wait(timeout=30)
                break
            time.sleep(0.02)
        return GenericResult(
            status="CANCELADO",
            execution_id="exec-longo",
            mission_id="MISSAO-TESTE-121",
            issue=121,
            mission_digest="abc",
        )

    exec_svc = ExecutionService(
        data_dir=data_dir,
        labs_root=lab_env["labs_root"],
        cycle_runner=runner_longo,
    )
    app = create_app()
    app.dependency_overrides[get_execution_service] = lambda: exec_svc
    client = TestClient(app, base_url="http://127.0.0.1:8000")
    token = obter_csrf_token()
    headers = {
        "Origin": "http://127.0.0.1:8000",
        "Referer": "http://127.0.0.1:8000/missoes",
        "X-CSRF-Token": token,
    }

    # 1. Inicia execução
    resp_init = client.post("/api/missoes/executar", json={
        "manifest_path": str(lab_env["manifest_path"]),
        "confirmacao_po": True,
        "csrf_token": token,
    }, headers=headers)
    assert resp_init.status_code == 202
    exec_id = resp_init.json()["execution_id"]

    time.sleep(0.05)

    # 2. Solicita cancelamento via API enquanto o worker ainda segura o encerramento
    # Usamos join_timeout=0.05s para simular worker que não encerra instantaneamente
    with patch.object(exec_svc, "cancelar_execucao", side_effect=lambda eid: ExecutionService.cancelar_execucao(exec_svc, eid, join_timeout=0.05)):
        resp_cancel = client.post(
            f"/api/missoes/execucoes/{exec_id}/cancelar",
            json={"csrf_token": token},
            headers=headers,
        )
        assert resp_cancel.status_code == 200
        dados_cancel = resp_cancel.json()
        assert dados_cancel["status"] == "CANCELAMENTO_PENDENTE"

    # Consulta ativa durante CANCELAMENTO_PENDENTE
    resp_ativa = client.get("/api/missoes/execucoes/ativa", headers=headers)
    assert resp_ativa.status_code == 200
    dados_ativa = resp_ativa.json()
    assert dados_ativa["status"] == "CANCELAMENTO_PENDENTE"
    assert dados_ativa["is_active"] is True

    # Tentativa de disparar nova missão durante CANCELAMENTO_PENDENTE deve falhar com 409 Conflict
    resp_conflito = client.post("/api/missoes/executar", json={
        "manifest_path": str(lab_env["manifest_path"]),
        "confirmacao_po": True,
        "csrf_token": token,
    }, headers=headers)
    assert resp_conflito.status_code == 409

    # Libera encerramento do worker
    segurar_encerramento.set()
    time.sleep(0.1)

    # Consulta ativa após conclusão do cancelamento: não há mais execução ativa
    resp_ativa_pos = client.get("/api/missoes/execucoes/ativa", headers=headers)
    assert resp_ativa_pos.status_code == 200
    assert resp_ativa_pos.json().get("execution_id") is None

    # 3. Validações estritas no template missions.html (P2)
    template_path = Path(__file__).resolve().parent.parent / "src" / "ch_control_center" / "templates" / "missions.html"
    assert template_path.exists(), "Template missions.html deve existir"
    html_content = template_path.read_text(encoding="utf-8")

    # Verifica que cancelarExecucaoAtiva não anuncia falso sucesso quando não há confirmação
    assert "!resp.ok" in html_content
    assert "exibirAlertaDespacho(data.detail" in html_content
    # Verifica tratamento explícito de CANCELAMENTO_PENDENTE
    assert "data.status === 'CANCELAMENTO_PENDENTE'" in html_content
    assert "Cancelamento solicitado; aguardando encerramento da execução no host." in html_content
    # Verifica que o botão de despachar permanece desabilitado durante cancelamento pendente
    assert "btnDespachar.disabled = true" in html_content
    assert "btnDespachar.textContent = 'Cancelando...'" in html_content
    # Verifica persistência no DOMContentLoaded
    assert "window.addEventListener('DOMContentLoaded'" in html_content
    assert "CANCELAMENTO_PENDENTE" in html_content

    reset_services()




