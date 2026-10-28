"""Serviço de gerenciamento de perfis de projetos (ProjectService).

Permite a alternância de visualização entre CHDevFlow e HallanCraft com isolamento
estrito de políticas de segurança e caminhos autorizados (RF-09 e Condicionante C05).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ch_control_center.config import (
    DIRETORIO_PROFILES,
    PERFIL_CHDEVFLOW,
    PERFIL_HALLANCRAFT,
    obter_perfil_ativo,
)


class ProjectService:
    """Gerencia perfis de projeto em modo estritamente somente leitura."""

    def __init__(self, diretorio_profiles: Path | None = None) -> None:
        self.diretorio_profiles = diretorio_profiles or DIRETORIO_PROFILES
        self._perfil_ativo_key = obter_perfil_ativo()
        self._perfis_cache: dict[str, dict[str, Any]] = {}
        self._carregar_perfis()

    def _carregar_perfis(self) -> None:
        """Carrega todos os arquivos JSON do diretório profiles/."""
        if not self.diretorio_profiles.is_dir():
            return

        for arquivo in self.diretorio_profiles.glob("*.json"):
            try:
                with open(arquivo, encoding="utf-8") as f:
                    dados = json.load(f)
                    chave = dados.get("project_key")
                    if chave:
                        self._perfis_cache[chave] = dados
            except (json.JSONDecodeError, OSError):
                continue

    def listar_perfis(self) -> list[dict[str, Any]]:
        """Retorna a lista resumida de perfis disponíveis."""
        return list(self._perfis_cache.values())

    def obter_perfil_ativo_key(self) -> str:
        """Retorna a chave do perfil ativo."""
        return self._perfil_ativo_key

    def obter_perfil_ativo(self) -> dict[str, Any]:
        """Retorna o dicionário completo de configuração do perfil ativo."""
        return self._perfis_cache.get(
            self._perfil_ativo_key,
            {
                "project_key": PERFIL_CHDEVFLOW,
                "display_name": "CHDevFlow (Meta-Governança)",
                "repository": "hallanbrito/CHDevFlow",
                "default_branch": "main",
                "autonomy_level": "CH-1",
            },
        )

    def alternar_perfil(self, project_key: str) -> dict[str, Any]:
        """Alterna o perfil ativo no painel.

        Conformidade AUD-03:
        - Na fatia CC-01, as fatias W e dados observados pertencem estritamente ao CHDevFlow.
        - O perfil HallanCraft é preparatório ('PREPARATÓRIO — SEM TROCA DE DADOS') e sua
          ingestão real de dados está reservada para fases futuras.
        - Para impedir estritamente que a tela exiba 'HallanCraft' enquanto os dados pertencem
          ao CHDevFlow, a tentativa de alternância não altera a fonte e preserva CHDevFlow.
        """
        chave = project_key.lower().strip()
        if chave == PERFIL_HALLANCRAFT:
            self._perfil_ativo_key = PERFIL_CHDEVFLOW
            return self.obter_perfil_ativo()

        if chave in self._perfis_cache:
            self._perfil_ativo_key = chave
        return self.obter_perfil_ativo()
