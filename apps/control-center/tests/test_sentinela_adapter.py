"""Testes de integração e conformidade para o SentinelFacade (ADR-CC02-01).

Valida reutilização das interfaces públicas estáveis da Sentinela sem acoplamento a atributos privados.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from ch_control_center.adapters.sentinela_adapter import SentinelFacade, SentinelaAdapterErro
from ch_control_center.config import DIRETORIO_FIXTURES
from ch_sentinela.github_reader import LeitorGitHub, LeitorGitHubErro


@pytest.fixture
def caminho_fixture() -> Path:
    return DIRETORIO_FIXTURES / "demo_project_snapshot.json"


@pytest.fixture
def facade(caminho_fixture: Path) -> SentinelFacade:
    return SentinelFacade(caminho_fixture_demo=caminho_fixture)


def test_obter_snapshot_demo_valido(facade: SentinelFacade) -> None:
    """Verifica carregamento e conformidade estrutural do snapshot de demonstração."""
    snapshot = facade.obter_snapshot_demo()
    assert isinstance(snapshot, dict)
    assert "items" in snapshot
    assert len(snapshot["items"]) >= 10
    assert snapshot.get("totalCount", len(snapshot["items"])) >= 10


def test_validar_snapshot_demo_com_regras_sentinela(facade: SentinelFacade) -> None:
    """Garante que a fixture passa na validação canônica da Sentinela."""
    snapshot = facade.obter_snapshot_demo()
    is_valido = facade.validar_snapshot(snapshot)
    assert is_valido is True


def test_calcular_digest_sha256_consistente(facade: SentinelFacade) -> None:
    """Verifica que o cálculo de digest criptográfico gera SHA-256 válido de 64 caracteres."""
    dados_missao = {
        "mission_id": "CC-01",
        "title": "Fundação Control Center",
        "allowed_paths": ["apps/control-center"],
        "max_cost_usd": 0.0,
    }
    digest = facade.calcular_digest_missao(dados_missao)
    assert isinstance(digest, str)
    assert len(digest) == 64
    assert int(digest, 16) > 0  # Hexadecimal válido

    # Idempotência do hash
    digest_repetido = facade.calcular_digest_missao(dados_missao)
    assert digest == digest_repetido


def test_fail_closed_em_fixture_inexistente(tmp_path: Path) -> None:
    """Fail-closed: se o arquivo de dados não existir, lança SentinelaAdapterErro."""
    arquivo_inexistente = tmp_path / "nao_existe.json"
    facade_invalido = SentinelFacade(caminho_fixture_demo=arquivo_inexistente)

    with pytest.raises(SentinelaAdapterErro, match="não encontrado"):
        facade_invalido.obter_snapshot_demo()


def test_fail_closed_em_fixture_json_corrompido(tmp_path: Path) -> None:
    """Fail-closed: se o arquivo JSON estiver corrompido, recusa processar."""
    arquivo_corrompido = tmp_path / "corrompido.json"
    arquivo_corrompido.write_text("{conteudo_invalido_sem_fechamento", encoding="utf-8")

    facade_corrompido = SentinelFacade(caminho_fixture_demo=arquivo_corrompido)
    with pytest.raises(SentinelaAdapterErro, match="corrompido"):
        facade_corrompido.obter_snapshot_demo()


def test_snapshot_ao_vivo_sem_credenciais_lanca_erro_seguro() -> None:
    """Ao tentar consultar GitHub ao vivo sem token ou ambiente configurado, lança exceção segura."""
    def mock_falha_sem_token(args: list[str]) -> str:
        raise LeitorGitHubErro("authentication required: GH_TOKEN not set or invalid")

    leitor = LeitorGitHub(executor_customizado=mock_falha_sem_token)
    facade = SentinelFacade(leitor=leitor)
    with pytest.raises(SentinelaAdapterErro, match="GH_TOKEN"):
        facade.obter_snapshot_ao_vivo()
