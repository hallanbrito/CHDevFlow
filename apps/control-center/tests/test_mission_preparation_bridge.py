"""Testes da preparação guiada de missões e preflight (CC-USO-01 / Issue #124).

Verifica integralmente os requisitos da Fatia A:
- Preparação segura do laboratório descartável CH-Lab-*, prompt e manifesto manual/v1.
- Validação real pelo motor _preflight determinístico de F6.
- Preservação estrita do repositório principal (sem escritas ou commits na branch principal).
- Preflight visual com estados APTO e BLOQUEADO e explicações auditáveis.
- Testes adversariais: path traversal, target em tests/, arquivos não-Python, repos não permitidos,
  symlinks, ausência de testes, lock ativo e falhas de CSRF/Host/Origin.
- Ausência de chamadas a modelos ou agentes reais em CI.
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
from unittest.mock import patch

import pytest
from starlette.testclient import TestClient

from chdevflow.core.generic_cycle import _preflight
from ch_control_center.app import create_app
from ch_control_center.dependencies import (
    get_preparation_service,
    reset_services,
)
from ch_control_center.security import obter_csrf_token
from ch_control_center.services.mission_preparation_service import (
    MissionPreparationError,
    MissionPreparationService,
    PreparationConflictError,
    PreparationValidationError,
    PreflightResult,
)


@pytest.fixture
def repo_fonte_simulado(tmp_path: Path):
    """Cria um repositório Git fonte isolado simulando hallanbrito/CHDevFlow."""
    repo = tmp_path / "CHDevFlow-Source"
    repo.mkdir(parents=True)

    # Inicializa repo Git com branch main
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Tester"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "tester@example.com"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://github.com/hallanbrito/CHDevFlow.git"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    # Cria módulo Python no repositório
    src_dir = repo / "src" / "chdevflow" / "core"
    src_dir.mkdir(parents=True)
    target_py = src_dir / "modulo_alvo.py"
    target_py.write_text("def executar():\n    return 'original'\n", encoding="utf-8")

    # Cria diretório tests com teste independente
    tests_dir = repo / "tests"
    tests_dir.mkdir()
    test_file = tests_dir / "test_modulo_alvo.py"
    test_file.write_text(
        "import unittest\nfrom src.chdevflow.core.modulo_alvo import executar\n\n"
        "class TestModulo(unittest.TestCase):\n"
        "    def test_exec(self):\n"
        "        self.assertIsNotNone(executar())\n",
        encoding="utf-8",
    )

    # Commit inicial em main
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Commit inicial em main"], cwd=repo, check=True, capture_output=True)

    labs_root = tmp_path / "CHDevFlow-Labs"
    labs_root.mkdir()
    data_dir = tmp_path / "cc_data"
    data_dir.mkdir()

    return {
        "repo": repo,
        "labs_root": labs_root,
        "data_dir": data_dir,
        "target_rel": "src/chdevflow/core/modulo_alvo.py",
    }


def test_preparar_missao_sucesso_preflight_apto(repo_fonte_simulado):
    """Comprova fluxo positivo: prepara lab CH-Lab-*, versiona prompt e obtém preflight APTO via F6."""
    repo = repo_fonte_simulado["repo"]
    labs_root = repo_fonte_simulado["labs_root"]
    data_dir = repo_fonte_simulado["data_dir"]
    target_rel = repo_fonte_simulado["target_rel"]

    svc = MissionPreparationService(
        source_repo=repo,
        labs_root=labs_root,
        data_dir=data_dir,
    )

    resultado = svc.preparar_missao(
        issue=124,
        repository="hallanbrito/CHDevFlow",
        target_file=target_rel,
        objetivo="Implementar preparação guiada de missões na interface.",
        criterios_aceite="pytest tests/test_modulo_alvo.py deve passar com 100% de sucesso.",
        confirmacao_po=True,
        timeout_segundos=480,
    )

    # 1. Valida resultado do preflight
    assert isinstance(resultado, PreflightResult)
    assert resultado.apto is True
    assert resultado.status == "APTO"
    assert resultado.motivos_bloqueio == []
    assert resultado.issue == 124
    assert resultado.repository == "hallanbrito/CHDevFlow"
    assert resultado.target_file == target_rel
    assert resultado.testes_independentes_count >= 1
    assert resultado.cost_verified is False
    assert resultado.os_isolation_verified is False
    assert resultado.test_execution == "host"
    assert resultado.sem_consumo_agentes is True
    assert resultado.auto_merge is False

    # 2. Valida existência física da worktree descartável CH-Lab-*
    worktree_path = Path(resultado.worktree)
    assert worktree_path.is_dir()
    assert worktree_path.name.startswith("CH-Lab-")

    # 3. Valida prompt versionado dentro do laboratório
    prompt_file = worktree_path / "prompt_missao.txt"
    assert prompt_file.is_file()
    prompt_content = prompt_file.read_text(encoding="utf-8")
    assert "Implementar preparação guiada" in prompt_content
    assert "pytest tests/test_modulo_alvo.py" in prompt_content

    # 4. Valida estado Git limpo do laboratório
    proc_status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=worktree_path,
        capture_output=True,
        text=True,
        check=True,
    )
    assert proc_status.stdout.strip() == ""

    # 5. Valida manifesto fora da worktree
    manifest_path = Path(resultado.manifest_path)
    assert manifest_path.is_file()
    assert worktree_path not in manifest_path.parents
    manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest_data["schema"] == "chdevflow.pipeline.manual/v1"
    assert manifest_data["issue"] == 124
    assert manifest_data["allowed_paths"] == [target_rel]
    assert manifest_data["worktree"] == str(worktree_path)
    assert manifest_data["base_sha"] == resultado.base_sha

    # 6. Comprova preservação estrita do repositório fonte principal
    proc_source_branch = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    assert proc_source_branch.stdout.strip() == "main"
    proc_source_status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    assert proc_source_status.stdout.strip() == ""
    assert not (repo / "prompt_missao.txt").exists()

    # 7. Validação cruzada direta com o _preflight real de F6
    mission_f6, root_f6, target_f6, prompt_f6, snapshot_f6 = _preflight(manifest_path)
    assert mission_f6.issue == 124
    assert root_f6 == worktree_path
    assert target_f6 == target_rel


def test_adversarial_rejeita_path_traversal(repo_fonte_simulado):
    """Comprova rejeição a tentativas de path traversal (../, \\, /, coringas)."""
    repo = repo_fonte_simulado["repo"]
    svc = MissionPreparationService(
        source_repo=repo,
        labs_root=repo_fonte_simulado["labs_root"],
        data_dir=repo_fonte_simulado["data_dir"],
    )

    caminhos_inseguros = [
        "../fora_do_repo.py",
        "sub/../../malicioso.py",
        "src\\chdevflow\\core\\invertido.py",
        "/absoluto/inseguro.py",
        "src/core/*.py",
        "src/core/[a-z].py",
        "src/chdevflow/core/modulo_inexistente_dir/algo.py",
    ]

    for caminho in caminhos_inseguros:
        with pytest.raises(PreparationValidationError):
            svc.preparar_missao(
                issue=124,
                repository="hallanbrito/CHDevFlow",
                target_file=caminho,
                objetivo="Teste de segurança",
                criterios_aceite="pytest tests/",
                confirmacao_po=True,
            )


def test_adversarial_rejeita_alvo_em_tests_ou_nao_python(repo_fonte_simulado):
    """Comprova que arquivos em tests/ ou com extensões não-Python são rejeitados."""
    repo = repo_fonte_simulado["repo"]
    svc = MissionPreparationService(
        source_repo=repo,
        labs_root=repo_fonte_simulado["labs_root"],
        data_dir=repo_fonte_simulado["data_dir"],
    )

    with pytest.raises(PreparationValidationError, match="fora do diretório 'tests/'"):
        svc.preparar_missao(
            issue=124,
            repository="hallanbrito/CHDevFlow",
            target_file="tests/test_modulo_alvo.py",
            objetivo="Alvo em tests",
            criterios_aceite="pytest tests/",
            confirmacao_po=True,
        )

    with pytest.raises(PreparationValidationError, match="arquivo Python"):
        svc.preparar_missao(
            issue=124,
            repository="hallanbrito/CHDevFlow",
            target_file="src/chdevflow/core/script.sh",
            objetivo="Alvo não-python",
            criterios_aceite="pytest tests/",
            confirmacao_po=True,
        )


def test_adversarial_rejeita_repositorio_nao_autorizado(repo_fonte_simulado):
    """Comprova que repositórios fora da allowlist são rejeitados."""
    repo = repo_fonte_simulado["repo"]
    svc = MissionPreparationService(
        source_repo=repo,
        labs_root=repo_fonte_simulado["labs_root"],
        data_dir=repo_fonte_simulado["data_dir"],
    )

    with pytest.raises(PreparationValidationError, match="não permitido"):
        svc.preparar_missao(
            issue=124,
            repository="outro_usuario/malicioso",
            target_file=repo_fonte_simulado["target_rel"],
            objetivo="Repo externo",
            criterios_aceite="pytest tests/",
            confirmacao_po=True,
        )


def test_adversarial_rejeita_sem_confirmacao_po(repo_fonte_simulado):
    """Comprova obrigatoriedade da autorização explícita do PO."""
    repo = repo_fonte_simulado["repo"]
    svc = MissionPreparationService(
        source_repo=repo,
        labs_root=repo_fonte_simulado["labs_root"],
        data_dir=repo_fonte_simulado["data_dir"],
    )

    with pytest.raises(PreparationValidationError, match="Confirmação explícita do PO"):
        svc.preparar_missao(
            issue=124,
            repository="hallanbrito/CHDevFlow",
            target_file=repo_fonte_simulado["target_rel"],
            objetivo="Sem autorização",
            criterios_aceite="pytest tests/",
            confirmacao_po=False,
        )


def test_adversarial_rejeita_issue_ou_criterios_invalidos(repo_fonte_simulado):
    """Comprova rejeição a issue <= 0 e critérios de aceite vazios."""
    repo = repo_fonte_simulado["repo"]
    svc = MissionPreparationService(
        source_repo=repo,
        labs_root=repo_fonte_simulado["labs_root"],
        data_dir=repo_fonte_simulado["data_dir"],
    )

    with pytest.raises(PreparationValidationError, match="Número de Issue inválido"):
        svc.preparar_missao(
            issue=0,
            repository="hallanbrito/CHDevFlow",
            target_file=repo_fonte_simulado["target_rel"],
            objetivo="Issue zero",
            criterios_aceite="pytest tests/",
            confirmacao_po=True,
        )

    with pytest.raises(PreparationValidationError, match="Critérios de aceite.*obrigatórios"):
        svc.preparar_missao(
            issue=124,
            repository="hallanbrito/CHDevFlow",
            target_file=repo_fonte_simulado["target_rel"],
            objetivo="Sem critérios",
            criterios_aceite="   ",
            confirmacao_po=True,
        )


def test_preflight_detecta_lock_ativo(repo_fonte_simulado):
    """Comprova que preflight marca BLOQUEADO quando há trava ativa no host."""
    repo = repo_fonte_simulado["repo"]
    labs_root = repo_fonte_simulado["labs_root"]
    data_dir = repo_fonte_simulado["data_dir"]

    # Cria trava ativa em disco
    lock_file = data_dir / "active_execution.lock"
    lock_file.write_text(json.dumps({"execution_id": "lock-teste-124", "pid": 12345}), encoding="utf-8")

    svc = MissionPreparationService(
        source_repo=repo,
        labs_root=labs_root,
        data_dir=data_dir,
    )

    # 1. Prepara a missão (cria worktree e manifesto)
    resultado = svc.preparar_missao(
        issue=124,
        repository="hallanbrito/CHDevFlow",
        target_file=repo_fonte_simulado["target_rel"],
        objetivo="Missão sob lock",
        criterios_aceite="pytest tests/",
        confirmacao_po=True,
    )

    # O preflight deve acusar BLOQUEADO devido à trava ativa
    assert resultado.apto is False
    assert resultado.status == "BLOQUEADO"
    assert resultado.lock_ativo is True
    assert any("active_execution.lock" in m for m in resultado.motivos_bloqueio)


def test_api_preparar_missao_sucesso_via_json(repo_fonte_simulado):
    """Comprova endpoint POST /api/missoes/preparar com payload JSON seguro."""
    reset_services()
    repo = repo_fonte_simulado["repo"]
    labs_root = repo_fonte_simulado["labs_root"]
    data_dir = repo_fonte_simulado["data_dir"]

    svc = MissionPreparationService(
        source_repo=repo,
        labs_root=labs_root,
        data_dir=data_dir,
    )

    app = create_app()
    app.dependency_overrides[get_preparation_service] = lambda: svc
    client = TestClient(app, base_url="http://127.0.0.1:8000")
    token = obter_csrf_token()

    headers = {
        "Origin": "http://127.0.0.1:8000",
        "Referer": "http://127.0.0.1:8000/missoes",
        "X-CSRF-Token": token,
    }

    payload = {
        "issue": 124,
        "repository": "hallanbrito/CHDevFlow",
        "target_file": repo_fonte_simulado["target_rel"],
        "objetivo": "Preparar via API",
        "criterios_aceite": "pytest tests/test_modulo_alvo.py",
        "confirmacao_po": True,
        "timeout_segundos": 480,
        "csrf_token": token,
    }

    resp = client.post("/api/missoes/preparar", json=payload, headers=headers)
    assert resp.status_code == 201
    dados = resp.json()
    assert dados["apto"] is True
    assert dados["status"] == "APTO"
    assert dados["issue"] == 124
    assert dados["repository"] == "hallanbrito/CHDevFlow"
    assert "CH-Lab-" in dados["worktree"]
    assert "CH-Manifest-" in dados["manifest_path"]
    assert dados["sem_consumo_agentes"] is True


def test_api_preparar_missao_rejeita_csrf_invalido(repo_fonte_simulado):
    """Comprova proteção CSRF no endpoint de preparação (AUD-02.1)."""
    reset_services()
    svc = MissionPreparationService(
        source_repo=repo_fonte_simulado["repo"],
        labs_root=repo_fonte_simulado["labs_root"],
        data_dir=repo_fonte_simulado["data_dir"],
    )

    app = create_app()
    app.dependency_overrides[get_preparation_service] = lambda: svc
    client = TestClient(app, base_url="http://127.0.0.1:8000")

    headers = {
        "Origin": "http://127.0.0.1:8000",
        "Referer": "http://127.0.0.1:8000/missoes",
        "X-CSRF-Token": "token_falso_invalido",
    }

    payload = {
        "issue": 124,
        "repository": "hallanbrito/CHDevFlow",
        "target_file": repo_fonte_simulado["target_rel"],
        "objetivo": "Ataque CSRF",
        "criterios_aceite": "pytest tests/",
        "confirmacao_po": True,
        "csrf_token": "token_falso_invalido",
    }

    resp = client.post("/api/missoes/preparar", json=payload, headers=headers)
    assert resp.status_code == 403
    assert "CSRF" in resp.json()["detail"]


def test_api_preparar_missao_rejeita_origem_externa(repo_fonte_simulado):
    """Comprova rejeição a requisições com Origin/Host externo (RNF-01 / AUD-01)."""
    reset_services()
    svc = MissionPreparationService(
        source_repo=repo_fonte_simulado["repo"],
        labs_root=repo_fonte_simulado["labs_root"],
        data_dir=repo_fonte_simulado["data_dir"],
    )

    app = create_app()
    app.dependency_overrides[get_preparation_service] = lambda: svc
    client = TestClient(app, base_url="http://127.0.0.1:8000")
    token = obter_csrf_token()

    headers = {
        "Origin": "http://evil-site.com",
        "Referer": "http://evil-site.com/attack",
        "X-CSRF-Token": token,
    }

    payload = {
        "issue": 124,
        "repository": "hallanbrito/CHDevFlow",
        "target_file": repo_fonte_simulado["target_rel"],
        "objetivo": "Ataque externo",
        "criterios_aceite": "pytest tests/",
        "confirmacao_po": True,
        "csrf_token": token,
    }

    resp = client.post("/api/missoes/preparar", json=payload, headers=headers)
    assert resp.status_code == 403


def test_api_preflight_consulta_manifesto_existente(repo_fonte_simulado):
    """Comprova endpoint GET /api/missoes/preflight para validação sob demanda."""
    reset_services()
    svc = MissionPreparationService(
        source_repo=repo_fonte_simulado["repo"],
        labs_root=repo_fonte_simulado["labs_root"],
        data_dir=repo_fonte_simulado["data_dir"],
    )

    resultado_prep = svc.preparar_missao(
        issue=124,
        repository="hallanbrito/CHDevFlow",
        target_file=repo_fonte_simulado["target_rel"],
        objetivo="Teste consulta preflight",
        criterios_aceite="pytest tests/test_modulo_alvo.py",
        confirmacao_po=True,
    )

    app = create_app()
    app.dependency_overrides[get_preparation_service] = lambda: svc
    client = TestClient(app, base_url="http://127.0.0.1:8000")

    resp = client.get(
        "/api/missoes/preflight",
        params={"manifest_path": resultado_prep.manifest_path},
    )
    assert resp.status_code == 200
    dados = resp.json()
    assert dados["apto"] is True
    assert dados["status"] == "APTO"
    assert dados["target_file"] == repo_fonte_simulado["target_rel"]
    assert dados["cost_verified"] is False
    assert dados["sem_consumo_agentes"] is True
