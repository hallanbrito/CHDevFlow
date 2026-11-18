"""Testes da preparação guiada de missões e preflight (CC-USO-01 / Issue #124 / R1).

Verifica integralmente os requisitos da Fatia A e as correções de revisão R1:
- P1: Isolamento estrito de labs_root (rejeição a labs_root igual ou interno ao repo fonte, preservando o clone principal).
- P1: Validação de critérios de aceite vinculados explicitamente a testes preexistentes rastreados no Git.
- P2: Paridade estrita de rejeição a symlinks de manifesto entre preflight e ExecutionService.
- P2: Distinção entre status APTO e PREPARADO_SEM_CLI com alertas de não-verificação de autenticação/cotas.
- P2: Bloqueio antecipado fail-closed por lock ativo sem mutação de arquivos ou criação de branches descartáveis.
- Testes adversariais de path traversal, target em tests/, arquivos não-Python, CSRF e origem externa.
- Preservação do contrato de F6 e ausência de chamadas a modelos em CI.
"""
from __future__ import annotations

import json
import os
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
from ch_control_center.services.execution_service import (
    ExecutionService,
    ManifestValidationError,
)
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

    # Simula ferramentas CLIs disponíveis no host para prova completa de APTO
    with patch.object(
        svc,
        "verificar_ferramentas_locais",
        return_value={"git": True, "agy": True, "codex": True, "python": True},
    ):
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
    assert "tests/test_modulo_alvo.py" in resultado.testes_referenciados
    assert resultado.cost_verified is False
    assert resultado.os_isolation_verified is False
    assert resultado.test_execution == "host"
    assert resultado.sem_consumo_agentes is True
    assert resultado.auto_merge is False

    # 2. Valida existência física da worktree descartável CH-Lab-*
    worktree_path = Path(resultado.worktree)
    assert worktree_path.is_dir()
    assert worktree_path.name.startswith("CH-Lab-")

    # 3. Valida prompt versionado dentro do laboratório com testes rastreados
    prompt_file = worktree_path / "prompt_missao.txt"
    assert prompt_file.is_file()
    prompt_content = prompt_file.read_text(encoding="utf-8")
    assert "Implementar preparação guiada" in prompt_content
    assert "tests/test_modulo_alvo.py" in prompt_content

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


def test_adversarial_rejeita_labs_root_no_repositorio_principal(repo_fonte_simulado):
    """P1: Comprova bloqueio estrito quando labs_root contamina ou coincide com o repositório fonte."""
    repo = repo_fonte_simulado["repo"]
    data_dir = repo_fonte_simulado["data_dir"]

    # Caso 1: labs_root é exatamente igual à raiz do clone principal
    with pytest.raises(PreparationValidationError, match="não pode ser igual ao repositório principal"):
        MissionPreparationService(
            source_repo=repo,
            labs_root=repo,
            data_dir=data_dir,
        )

    # Caso 2: labs_root é uma subpasta dentro do clone principal
    sub_pasta_insegura = repo / "CH-Labs-Contaminado"
    with pytest.raises(PreparationValidationError, match="não pode estar contido no repositório principal"):
        MissionPreparationService(
            source_repo=repo,
            labs_root=sub_pasta_insegura,
            data_dir=data_dir,
        )

    # Comprova que o repositório fonte permanece 100% intocado
    assert not sub_pasta_insegura.exists()
    proc = subprocess.run(["git", "status", "--porcelain"], cwd=repo, capture_output=True, text=True, check=True)
    assert proc.stdout.strip() == ""


def test_adversarial_rejeita_criterios_sem_referencia_a_teste_rastreado(repo_fonte_simulado):
    """P1: Comprova rejeição a critérios de aceite que não referenciam testes rastreados preexistentes."""
    repo = repo_fonte_simulado["repo"]
    labs_root = repo_fonte_simulado["labs_root"]
    data_dir = repo_fonte_simulado["data_dir"]

    svc = MissionPreparationService(
        source_repo=repo,
        labs_root=labs_root,
        data_dir=data_dir,
    )

    # Caso 1: Texto arbitrário que não cita arquivo de teste
    with pytest.raises(PreparationValidationError, match="pelo menos um arquivo de teste"):
        svc.preparar_missao(
            issue=124,
            repository="hallanbrito/CHDevFlow",
            target_file=repo_fonte_simulado["target_rel"],
            objetivo="Fazer funcionar perfeitamente",
            criterios_aceite="O código deve estar sem erros e funcionando bem.",
            confirmacao_po=True,
        )

    # Caso 2: Cita teste inexistente
    with pytest.raises(PreparationValidationError, match="pelo menos um arquivo de teste"):
        svc.preparar_missao(
            issue=124,
            repository="hallanbrito/CHDevFlow",
            target_file=repo_fonte_simulado["target_rel"],
            objetivo="Teste com arquivo fantasma",
            criterios_aceite="pytest tests/test_inexistente_fantasma.py",
            confirmacao_po=True,
        )

    # Caso 3: Cita teste que existe no disco mas NÃO está rastreado no Git
    untracked_test = repo / "tests" / "test_nao_rastreado.py"
    untracked_test.write_text("def test_x(): pass\n", encoding="utf-8")
    with pytest.raises(PreparationValidationError, match="pelo menos um arquivo de teste"):
        svc.preparar_missao(
            issue=124,
            repository="hallanbrito/CHDevFlow",
            target_file=repo_fonte_simulado["target_rel"],
            objetivo="Teste não rastreado",
            criterios_aceite="pytest tests/test_nao_rastreado.py",
            confirmacao_po=True,
        )
    untracked_test.unlink()


def test_adversarial_preparacao_recusada_quando_lock_ativo_sem_mutacao(repo_fonte_simulado):
    """P2: Comprova que lock ativo recusa preparação ANTES de criar worktree ou branch (sem mutação)."""
    repo = repo_fonte_simulado["repo"]
    labs_root = repo_fonte_simulado["labs_root"]
    data_dir = repo_fonte_simulado["data_dir"]

    # Cria trava ativa em disco
    lock_file = data_dir / "active_execution.lock"
    lock_file.write_text(json.dumps({"execution_id": "lock-ativo-teste", "pid": 99999}), encoding="utf-8")

    svc = MissionPreparationService(
        source_repo=repo,
        labs_root=labs_root,
        data_dir=data_dir,
    )

    # Tentativa de preparação deve falhar com PreparationConflictError antes de criar arquivos
    with pytest.raises(PreparationConflictError, match="Trava de execução ativa em disco"):
        svc.preparar_missao(
            issue=124,
            repository="hallanbrito/CHDevFlow",
            target_file=repo_fonte_simulado["target_rel"],
            objetivo="Tentativa sob lock",
            criterios_aceite="pytest tests/test_modulo_alvo.py",
            confirmacao_po=True,
        )

    # Comprova que nenhuma pasta CH-Lab-* e nenhum manifesto foram criados em labs_root
    assert list(labs_root.glob("CH-Lab-*")) == []
    assert list(labs_root.glob("CH-Manifest-*")) == []

    # Comprova que nenhuma branch descartável foi criada no repositório fonte
    proc_branches = subprocess.run(
        ["git", "branch", "--list", "ch-lab/*"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    assert proc_branches.stdout.strip() == ""


def test_preflight_rejeita_symlink_de_manifesto_paridade_execucao(repo_fonte_simulado, tmp_path):
    """P2: Comprova que preflight visual e despacho rejeitam symlinks de manifesto com idêntica paridade."""
    repo = repo_fonte_simulado["repo"]
    labs_root = repo_fonte_simulado["labs_root"]
    data_dir = repo_fonte_simulado["data_dir"]

    svc = MissionPreparationService(
        source_repo=repo,
        labs_root=labs_root,
        data_dir=data_dir,
    )

    with patch.object(
        svc,
        "verificar_ferramentas_locais",
        return_value={"git": True, "agy": True, "codex": True, "python": True},
    ):
        resultado = svc.preparar_missao(
            issue=124,
            repository="hallanbrito/CHDevFlow",
            target_file=repo_fonte_simulado["target_rel"],
            objetivo="Teste de symlink",
            criterios_aceite="pytest tests/test_modulo_alvo.py",
            confirmacao_po=True,
        )

    manifest_real = Path(resultado.manifest_path)
    assert manifest_real.is_file()

    # Cria symlink apontando para o manifesto real (ou simula com patch caso o SO restrinja)
    symlink_manifest = tmp_path / "symlink_manifesto.json"
    symlink_real_criado = False
    try:
        symlink_manifest.symlink_to(manifest_real)
        symlink_real_criado = True
    except OSError:
        symlink_manifest.write_text("{}", encoding="utf-8")

    if symlink_real_criado:
        # 1. Validação no Preflight do MissionPreparationService: deve recusar e acusar BLOQUEADO
        resultado_preflight = svc.verificar_preflight(symlink_manifest)
        assert resultado_preflight.apto is False
        assert resultado_preflight.status == "BLOQUEADO"
        assert any("simbolico" in m.lower() for m in resultado_preflight.motivos_bloqueio)

        # 2. Validação no ExecutionService: deve rejeitar com ManifestValidationError
        exec_svc = ExecutionService(
            data_dir=data_dir,
            labs_root=labs_root,
        )
        with pytest.raises(ManifestValidationError, match="arquivo regular existente"):
            exec_svc.executar_missao(
                manifest_path=symlink_manifest,
                confirmacao_po=True,
            )
    else:
        orig_is_symlink = Path.is_symlink
        with patch.object(
            Path,
            "is_symlink",
            autospec=True,
            side_effect=lambda p: True if p.name == "symlink_manifesto.json" else orig_is_symlink(p),
        ):
            resultado_preflight = svc.verificar_preflight(symlink_manifest)
            assert resultado_preflight.apto is False
            assert resultado_preflight.status == "BLOQUEADO"
            assert any("simbolico" in m.lower() for m in resultado_preflight.motivos_bloqueio)

            exec_svc = ExecutionService(
                data_dir=data_dir,
                labs_root=labs_root,
            )
            with pytest.raises(ManifestValidationError, match="arquivo regular existente"):
                exec_svc.executar_missao(
                    manifest_path=symlink_manifest,
                    confirmacao_po=True,
                )


def test_preflight_sem_cli_retorna_preparado_sem_cli(repo_fonte_simulado):
    """P2: Comprova que ausência de AGY/Codex no host retorna PREPARADO_SEM_CLI em vez de falso APTO."""
    repo = repo_fonte_simulado["repo"]
    labs_root = repo_fonte_simulado["labs_root"]
    data_dir = repo_fonte_simulado["data_dir"]

    svc = MissionPreparationService(
        source_repo=repo,
        labs_root=labs_root,
        data_dir=data_dir,
    )

    # Simula ambiente onde Git existe mas AGY e Codex não estão instalados
    with patch.object(
        svc,
        "verificar_ferramentas_locais",
        return_value={"git": True, "agy": False, "codex": False, "python": True},
    ):
        resultado = svc.preparar_missao(
            issue=124,
            repository="hallanbrito/CHDevFlow",
            target_file=repo_fonte_simulado["target_rel"],
            objetivo="Teste sem CLIs",
            criterios_aceite="pytest tests/test_modulo_alvo.py",
            confirmacao_po=True,
        )

    assert resultado.apto is False
    assert resultado.status == "PREPARADO_SEM_CLI"
    assert any("AGY" in m for m in resultado.motivos_bloqueio)
    assert any("Codex" in m for m in resultado.motivos_bloqueio)
    # Alerta mandatório de autenticação não verificada
    assert any("autenticacao_clis=nao_verificada" in a for a in resultado.avisos_seguranca)


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
                criterios_aceite="pytest tests/test_modulo_alvo.py",
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
            criterios_aceite="pytest tests/test_modulo_alvo.py",
            confirmacao_po=True,
        )

    with pytest.raises(PreparationValidationError, match="arquivo Python"):
        svc.preparar_missao(
            issue=124,
            repository="hallanbrito/CHDevFlow",
            target_file="src/chdevflow/core/script.sh",
            objetivo="Alvo não-python",
            criterios_aceite="pytest tests/test_modulo_alvo.py",
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
            criterios_aceite="pytest tests/test_modulo_alvo.py",
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
            criterios_aceite="pytest tests/test_modulo_alvo.py",
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
            criterios_aceite="pytest tests/test_modulo_alvo.py",
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

    with patch.object(
        svc,
        "verificar_ferramentas_locais",
        return_value={"git": True, "agy": True, "codex": True, "python": True},
    ):
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
        "criterios_aceite": "pytest tests/test_modulo_alvo.py",
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
        "criterios_aceite": "pytest tests/test_modulo_alvo.py",
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

    app = create_app()
    app.dependency_overrides[get_preparation_service] = lambda: svc
    client = TestClient(app, base_url="http://127.0.0.1:8000")

    with patch.object(
        svc,
        "verificar_ferramentas_locais",
        return_value={"git": True, "agy": True, "codex": True, "python": True},
    ):
        resultado_prep = svc.preparar_missao(
            issue=124,
            repository="hallanbrito/CHDevFlow",
            target_file=repo_fonte_simulado["target_rel"],
            objetivo="Teste consulta preflight",
            criterios_aceite="pytest tests/test_modulo_alvo.py",
            confirmacao_po=True,
        )

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


def test_preparacao_inibe_hooks_adversariais_git(repo_fonte_simulado, tmp_path):
    """Comprova neutralização de hooks post-checkout e pre-commit durante a preparação (P1-A)."""
    repo = repo_fonte_simulado["repo"]
    hooks_dir = repo / ".git" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)

    sentinela_checkout = tmp_path / "post_checkout_fired.txt"
    sentinela_commit = tmp_path / "pre_commit_fired.txt"

    # Hook adversarial post-checkout
    hook_post_checkout = hooks_dir / "post-checkout"
    hook_post_checkout.write_text(
        f"#!/bin/sh\necho 'HOOK POST-CHECKOUT' > '{sentinela_checkout.as_posix()}'\nexit 0\n",
        encoding="utf-8",
    )

    # Hook adversarial pre-commit
    hook_pre_commit = hooks_dir / "pre-commit"
    hook_pre_commit.write_text(
        f"#!/bin/sh\necho 'HOOK PRE-COMMIT' > '{sentinela_commit.as_posix()}'\nexit 0\n",
        encoding="utf-8",
    )

    svc = MissionPreparationService(
        source_repo=repo,
        labs_root=repo_fonte_simulado["labs_root"],
        data_dir=repo_fonte_simulado["data_dir"],
    )

    with patch.object(
        svc,
        "verificar_ferramentas_locais",
        return_value={"git": True, "agy": True, "codex": True, "python": True},
    ):
        resultado = svc.preparar_missao(
            issue=124,
            repository="hallanbrito/CHDevFlow",
            target_file=repo_fonte_simulado["target_rel"],
            objetivo="Testar neutralização de hooks adversariais",
            criterios_aceite="pytest tests/test_modulo_alvo.py",
            confirmacao_po=True,
        )

    assert resultado.apto is True
    assert not sentinela_checkout.exists(), "Hook post-checkout NÃO deveria ter sido executado!"
    assert not sentinela_commit.exists(), "Hook pre-commit NÃO deveria ter sido executado!"


def test_rollback_apos_falha_parcial_worktree_add(repo_fonte_simulado):
    """Comprova rollback estrito de branch e worktree após falha parcial de worktree add (P1-A)."""
    repo = repo_fonte_simulado["repo"]
    labs_root = repo_fonte_simulado["labs_root"]

    # Cria recurso legítimo de terceiro em labs_root que não deve ser tocado
    outro_lab = labs_root / "CH-Lab-OUTRA-MISSAO"
    outro_lab.mkdir(parents=True)
    arquivo_terceiro = outro_lab / "dados_importantes.txt"
    arquivo_terceiro.write_text("conteúdo legítimo de outra missão", encoding="utf-8")

    # Cria branch legítima de outro desenvolvedor que não deve ser tocada
    subprocess.run(["git", "branch", "branch-de-terceiro"], cwd=repo, check=True)

    svc = MissionPreparationService(
        source_repo=repo,
        labs_root=labs_root,
        data_dir=repo_fonte_simulado["data_dir"],
    )

    original_exec = svc._executar_git_seguro

    # Simula falha parcial: git cria a branch e cria arquivos na pasta, mas aborta com erro
    def fake_exec_git(cwd, *args, **kwargs):
        if len(args) >= 2 and args[0] == "worktree" and args[1] == "add":
            # args: ("worktree", "add", "-b", branch_name, worktree_dir, head_commit)
            b_name = args[3]
            wt_path = Path(args[4])
            wt_path.mkdir(parents=True, exist_ok=True)
            (wt_path / "arquivo_parcial.txt").write_text("parcial", encoding="utf-8")
            subprocess.run(["git", "branch", b_name], cwd=repo, check=True)
            return subprocess.CompletedProcess(
                args=["git", *args],
                returncode=1,
                stdout="",
                stderr="fatal: erro simulado de checkout parcial durante worktree add",
            )
        return original_exec(cwd, *args, **kwargs)

    with patch.object(svc, "_executar_git_seguro", side_effect=fake_exec_git):
        with pytest.raises(MissionPreparationError) as exc_info:
            svc.preparar_missao(
                issue=124,
                repository="hallanbrito/CHDevFlow",
                target_file=repo_fonte_simulado["target_rel"],
                objetivo="Teste falha parcial",
                criterios_aceite="pytest tests/test_modulo_alvo.py",
                confirmacao_po=True,
                mission_id="MISSAO-FALHA-PARCIAL",
            )

    assert "erro simulado de checkout parcial" in str(exc_info.value)

    # 1. Branch efêmera da missão falhada deve ter sido limpa pelo rollback
    proc_branch = subprocess.run(
        ["git", "rev-parse", "--verify", "refs/heads/ch-lab/missao-falha-parcial"],
        cwd=repo,
        capture_output=True,
    )
    assert proc_branch.returncode != 0, "Branch da missão falhada deveria ter sido removida no rollback!"

    # 2. Pasta temporária da missão falhada deve ter sido limpa pelo rollback
    pasta_lab_falhada = labs_root / "CH-Lab-MISSAO-FALHA-PARCIAL"
    assert not pasta_lab_falhada.exists(), "Diretório de worktree da missão falhada deveria ter sido removido!"

    # 3. Recurso de terceiro em labs_root permaneceu intacto
    assert outro_lab.is_dir()
    assert arquivo_terceiro.read_text(encoding="utf-8") == "conteúdo legítimo de outra missão"

    # 4. Branch de terceiro no repositório permaneceu intacta
    proc_terceiro = subprocess.run(
        ["git", "rev-parse", "--verify", "refs/heads/branch-de-terceiro"],
        cwd=repo,
        capture_output=True,
    )
    assert proc_terceiro.returncode == 0

    # 5. Clone principal permaneceu limpo
    proc_status = subprocess.run(["git", "status", "--porcelain"], cwd=repo, capture_output=True, text=True)
    assert proc_status.stdout.strip() == ""


def test_criterios_aceite_rejeita_teste_apenas_staged(repo_fonte_simulado):
    """Comprova que testes adicionados ao índice mas ausentes de HEAD são rejeitados (P1-B)."""
    repo = repo_fonte_simulado["repo"]
    teste_staged = repo / "tests" / "test_apenas_no_indice.py"
    teste_staged.write_text("def test_staged(): pass\n", encoding="utf-8")

    # Adiciona ao índice via git add, mas NÃO faz commit (staged-only)
    subprocess.run(["git", "add", "tests/test_apenas_no_indice.py"], cwd=repo, check=True)

    svc = MissionPreparationService(
        source_repo=repo,
        labs_root=repo_fonte_simulado["labs_root"],
        data_dir=repo_fonte_simulado["data_dir"],
    )

    with pytest.raises(PreparationValidationError) as exc_info:
        svc.preparar_missao(
            issue=124,
            repository="hallanbrito/CHDevFlow",
            target_file=repo_fonte_simulado["target_rel"],
            objetivo="Testar rejeição de teste staged-only",
            criterios_aceite="pytest tests/test_apenas_no_indice.py",
            confirmacao_po=True,
        )

    msg = str(exc_info.value)
    assert "presente como blob regular em HEAD" in msg or "rejeitados" in msg


def test_criterios_aceite_rejeita_teste_removido_de_head(repo_fonte_simulado):
    """Comprova rejeição de teste que foi removido no commit HEAD (P1-B)."""
    repo = repo_fonte_simulado["repo"]
    teste_removido = repo / "tests" / "test_temporario.py"
    teste_removido.write_text("def test_temp(): pass\n", encoding="utf-8")
    subprocess.run(["git", "add", "tests/test_temporario.py"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "Adiciona teste temporario"], cwd=repo, check=True)

    # Agora remove o teste e commita a remoção
    subprocess.run(["git", "rm", "tests/test_temporario.py"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "Remove teste temporario"], cwd=repo, check=True)

    svc = MissionPreparationService(
        source_repo=repo,
        labs_root=repo_fonte_simulado["labs_root"],
        data_dir=repo_fonte_simulado["data_dir"],
    )

    with pytest.raises(PreparationValidationError) as exc_info:
        svc.preparar_missao(
            issue=124,
            repository="hallanbrito/CHDevFlow",
            target_file=repo_fonte_simulado["target_rel"],
            objetivo="Testar rejeição de teste removido de HEAD",
            criterios_aceite="pytest tests/test_temporario.py",
            confirmacao_po=True,
        )

    assert "devem referenciar explicitamente pelo menos um arquivo de teste" in str(exc_info.value)


def test_criterios_aceite_rejeita_helper_sem_prefixo_test(repo_fonte_simulado):
    """Comprova que arquivos em tests/ que não sejam test_*.py são rejeitados (P1-B)."""
    repo = repo_fonte_simulado["repo"]
    helper = repo / "tests" / "helper.py"
    helper.write_text("def helper_fn(): pass\n", encoding="utf-8")
    subprocess.run(["git", "add", "tests/helper.py"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "Adiciona helper.py"], cwd=repo, check=True)

    svc = MissionPreparationService(
        source_repo=repo,
        labs_root=repo_fonte_simulado["labs_root"],
        data_dir=repo_fonte_simulado["data_dir"],
    )

    with pytest.raises(PreparationValidationError) as exc_info:
        svc.preparar_missao(
            issue=124,
            repository="hallanbrito/CHDevFlow",
            target_file=repo_fonte_simulado["target_rel"],
            objetivo="Testar rejeição de helper sem test_",
            criterios_aceite="pytest tests/helper.py",
            confirmacao_po=True,
        )

    assert "devem referenciar explicitamente pelo menos um arquivo de teste" in str(exc_info.value)


def test_preflight_bloqueia_se_teste_referenciado_ausente_do_laboratorio_ou_snapshot(repo_fonte_simulado):
    """Comprova que preflight bloqueia se teste referenciado não integrar o snapshot F6 (P1-B)."""
    svc = MissionPreparationService(
        source_repo=repo_fonte_simulado["repo"],
        labs_root=repo_fonte_simulado["labs_root"],
        data_dir=repo_fonte_simulado["data_dir"],
    )

    with patch.object(
        svc,
        "verificar_ferramentas_locais",
        return_value={"git": True, "agy": True, "codex": True, "python": True},
    ):
        resultado = svc.preparar_missao(
            issue=124,
            repository="hallanbrito/CHDevFlow",
            target_file=repo_fonte_simulado["target_rel"],
            objetivo="Missão teste snapshot",
            criterios_aceite="pytest tests/test_modulo_alvo.py",
            confirmacao_po=True,
        )

    assert resultado.apto is True

    # 1. Consulta com teste ausente do snapshot F6
    res_consulta = svc.verificar_preflight(
        resultado.manifest_path,
        testes_esperados=["tests/test_inexistente_no_snapshot.py"],
    )
    assert res_consulta.apto is False
    assert res_consulta.status == "BLOQUEADO"
    assert any("Teste obrigatório 'tests/test_inexistente_no_snapshot.py' ausente" in m for m in res_consulta.motivos_bloqueio)

    # 2. Simula adulteração física no laboratório (remoção de arquivo de teste)
    lab_teste = Path(resultado.worktree) / "tests" / "test_modulo_alvo.py"
    lab_teste.unlink()

    # Preflight detecta violação de integridade / dirty worktree do F6 e bloqueia
    res_adulterado = svc.verificar_preflight(resultado.manifest_path)
    assert res_adulterado.apto is False
    assert res_adulterado.status == "BLOQUEADO"
    assert any("reprovada" in m.lower() or "ausente" in m.lower() for m in res_adulterado.motivos_bloqueio)
