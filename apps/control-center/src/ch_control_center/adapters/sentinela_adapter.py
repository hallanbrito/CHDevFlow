"""Adaptador de Fachada da Sentinela Python (SentinelFacade).

Implementa a decisão ADR-CC02-01 (Integração por Composição):
O Control Center não duplica validadores, contratos ou leitores do GitHub;
ele consome estritamente as interfaces públicas estáveis de 'ch_sentinela'.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ch_sentinela.contracts import (
    ContratoInvalidoErro,
    ContratoMissao,
    calcular_digest_sha256,
    validar_contrato_missao,
)
from ch_sentinela.github_reader import (
    LeitorGitHub,
    LeitorGitHubErro,
    validar_snapshot_projeto,
)
from ch_sentinela.security.policies import (
    ViolacaoPoliticaSegurancaErro,
    sanitizar_texto_segredos,
)
from ch_sentinela.sentinel import EventoSentinela, Sentinela


class SentinelaAdapterErro(RuntimeError):
    """Exceção levantada para falhas na camada adaptadora da Sentinela."""


class SentinelFacade:
    """Fachada estável de integração entre o Control Center e o motor ch_sentinela."""

    def __init__(
        self,
        leitor: LeitorGitHub | None = None,
        caminho_fixture_demo: Path | None = None,
    ) -> None:
        """Inicializa a fachada.

        Args:
            leitor: Instância opcional de LeitorGitHub. Se None, cria uma padrão.
            caminho_fixture_demo: Caminho opcional para fixture de demonstração offline.
        """
        self.leitor = leitor or LeitorGitHub()
        self.sentinela = Sentinela(leitor=self.leitor)
        self.caminho_fixture_demo = caminho_fixture_demo

    def validar_estrutura_snapshot(self, snapshot: dict[str, Any]) -> bool:
        """Executa a validação centralizada AUD-02 da Sentinela sobre um snapshot."""
        validar_snapshot_projeto(snapshot)
        return True

    def validar_snapshot(self, snapshot: dict[str, Any]) -> bool:
        """Alias para validar_estrutura_snapshot."""
        return self.validar_estrutura_snapshot(snapshot)

    def obter_snapshot_ao_vivo(self) -> dict[str, Any]:
        """Obtém o snapshot atual do GitHub Project #2 via CLI gh somente leitura.

        Raises:
            SentinelaAdapterErro: Se ocorrer falha na execução ou validação estrutural.
        """
        try:
            snapshot = self.leitor.listar_itens_projeto()
            self.validar_estrutura_snapshot(snapshot)
            return snapshot
        except LeitorGitHubErro as exc:
            msg = f"Falha na leitura ao vivo do GitHub Project: {exc}"
            raise SentinelaAdapterErro(msg) from exc

    def obter_snapshot_demo(self, caminho_arquivo: Path | None = None) -> dict[str, Any]:
        """Carrega e valida o snapshot da fixture de demonstração offline."""
        caminho = caminho_arquivo or self.caminho_fixture_demo
        if not caminho or not caminho.is_file():
            raise SentinelaAdapterErro(f"Arquivo de fixture de demonstração não encontrado: {caminho}")

        try:
            with open(caminho, encoding="utf-8") as f:
                dados = json.load(f)
            self.validar_estrutura_snapshot(dados)
            return dados
        except (json.JSONDecodeError, LeitorGitHubErro, ValueError) as exc:
            msg = f"Fixture de demonstração inválida ou malformada ({caminho}): {exc}"
            raise SentinelaAdapterErro(msg) from exc

    def observar_missoes(
        self,
        snapshot: dict[str, Any] | None = None,
        fonte_dados: str = "LIVE_GITHUB",
    ) -> list[EventoSentinela]:
        """Executa a observação pontual 'watch --once' da Sentinela e retorna eventos."""
        try:
            return self.sentinela.observar_uma_vez(
                snapshot_projeto=snapshot,
                fonte_dados=fonte_dados,
            )
        except LeitorGitHubErro as exc:
            raise SentinelaAdapterErro(f"Erro na observação da Sentinela: {exc}") from exc

    def validar_missao(self, payload: dict[str, Any]) -> ContratoMissao:
        """Valida um payload de missão gerando o ContratoMissao imutável com fail-closed."""
        try:
            return validar_contrato_missao(payload)
        except (ContratoInvalidoErro, ViolacaoPoliticaSegurancaErro) as exc:
            raise SentinelaAdapterErro(f"Validação de contrato rejeitada: {exc}") from exc

    def calcular_digest(self, objeto: Any) -> str:
        """Gera o digest SHA-256 canônico determinístico através da Sentinela."""
        return calcular_digest_sha256(objeto)

    def calcular_digest_missao(self, payload: dict[str, Any]) -> str:
        """Alias para calcular_digest com foco em missão."""
        return self.calcular_digest(payload)

    def sanitizar(self, texto: str) -> str:
        """Remove credenciais e segredos de mensagens e saídas."""
        return sanitizar_texto_segredos(texto)
