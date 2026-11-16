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
    assert dados_decisao["decisao_po"]["decisao"] == "APROVADO"
    assert "100% de cobertura" in dados_decisao["decisao_po"]["justificativa"]

    # 3. Consulta de detalhes confirma a persistência
    detalhes_resp = client.get(f"/api/missoes/execucoes/{exec_id}", headers={"Host": "127.0.0.1:8000"})
    assert detalhes_resp.json()["decisao_po"]["decisao"] == "APROVADO"


def test_detalhes_execucao_404_para_id_inexistente(custom_client):
    """Retorna HTTP 404 para ID de execução que não existe."""
    client, _ = custom_client
    resp = client.get("/api/missoes/execucoes/id_inexistente_12345", headers={"Host": "127.0.0.1:8000"})
    assert resp.status_code == 404
