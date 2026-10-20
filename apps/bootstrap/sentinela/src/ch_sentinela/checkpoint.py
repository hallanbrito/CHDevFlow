"""Gerenciador de estado local e controle de concorrência (checkpoint).

Garante idempotência, exclusividade de execução (concorrência máxima = 1)
e persistência segura do histórico de transições de estado no disco.
"""
from __future__ import annotations

import json
import os
import tempfile
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ch_sentinela.config import (
    MAXIMO_EXECUCOES_ATIVAS,
    NOME_ARQUIVO_CHECKPOINT,
    obter_diretorio_dados,
)


class ConcorrenciaBloqueadaErro(RuntimeError):
    """Exceção levantada quando já existe uma execução ativa no sistema."""


class IdempotenciaVioladaErro(RuntimeError):
    """Exceção levantada ao tentar executar novamente uma missão já concluída ou em andamento."""


@dataclass
class RegistroExecucao:
    """Registro estruturado de uma execução individual persistida no checkpoint."""

    run_id: str
    mission_id: str
    mission_digest: str
    estado_atual: str
    tentativa: int
    data_inicio_utc: str
    data_atualizacao_utc: str
    ativo: bool
    resultado_final: str | None = None
    motivo_bloqueio: str | None = None


class GerenciadorCheckpoint:
    """Controla e persiste o estado local das execuções garantindo exclusão mútua e idempotência."""

    def __init__(self, caminho_arquivo: Path | None = None) -> None:
        """Inicializa o gerenciador.

        Args:
            caminho_arquivo: Caminho opcional para o arquivo de checkpoint (usado em testes).
        """
        if caminho_arquivo is not None:
            self.caminho_arquivo = caminho_arquivo
        else:
            self.caminho_arquivo = obter_diretorio_dados() / NOME_ARQUIVO_CHECKPOINT

    def _ler_estado(self) -> dict[str, Any]:
        """Lê o arquivo de estado de forma segura.

        Returns:
            Dicionário com os dados do checkpoint ou estrutura padrão vazia.
        """
        if not self.caminho_arquivo.exists():
            return {"versao": 1, "execucoes": {}}

        try:
            with open(self.caminho_arquivo, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {"versao": 1, "execucoes": {}}

    def _gravar_estado(self, dados: dict[str, Any]) -> None:
        """Grava os dados no arquivo de checkpoint usando escrita atômica e permissão 0o600.

        Args:
            dados: Dicionário contendo os dados a persistir.
        """
        self.caminho_arquivo.parent.mkdir(parents=True, exist_ok=True)
        dir_pai = self.caminho_arquivo.parent

        # Criação de arquivo temporário no mesmo diretório para garantir rename atômico
        fd, temp_path = tempfile.mkstemp(dir=dir_pai, prefix="chk_", suffix=".tmp")
        try:
            with open(fd, "w", encoding="utf-8") as f:
                json.dump(dados, f, ensure_ascii=False, indent=2)
            os.chmod(temp_path, 0o600)
            os.replace(temp_path, self.caminho_arquivo)
        except Exception:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise

    def verificar_execucao_ativa(self) -> bool:
        """Verifica se há alguma execução marcada como ativa no momento.

        Returns:
            True se houver uma execução ativa, False caso contrário.
        """
        estado = self._ler_estado()
        for registro in estado.get("execucoes", {}).values():
            if registro.get("ativo", False):
                return True
        return False

    def reivindicar_execucao(
        self,
        run_id: str,
        mission_id: str,
        mission_digest: str,
        tentativa: int = 1,
    ) -> RegistroExecucao:
        """Reivindica a exclusividade para iniciar uma nova execução (transição para CLAIMED).

        Garante a regra de no máximo 1 execução ativa (D06) e idempotência.

        Args:
            run_id: Identificador único da execução.
            mission_id: Identificador da missão.
            mission_digest: Hash canônico dos parâmetros da missão.
            tentativa: Número da tentativa (1 ou 2).

        Returns:
            O RegistroExecucao criado e persistido.

        Raises:
            ConcorrenciaBloqueadaErro: Se já houver execução em andamento.
            IdempotenciaVioladaErro: Se a mesma missão e tentativa já tiverem sido registradas.
        """
        estado = self._ler_estado()
        execucoes = estado.setdefault("execucoes", {})

        # 1. Verifica se já existe qualquer execução ativa
        for id_existente, reg in execucoes.items():
            if reg.get("ativo", False):
                raise ConcorrenciaBloqueadaErro(
                    f"Execução concorrente bloqueada: run_id='{id_existente}' ainda está ativo. "
                    f"Limite operacional é de no máximo {MAXIMO_EXECUCOES_ATIVAS} execução ativa."
                )

        # 2. Verifica idempotência: mesma missão e tentativa não podem ser duplicadas
        chave_idempotencia = f"{mission_digest}:tentativa_{tentativa}"
        for id_existente, reg in execucoes.items():
            chave_existente = f"{reg.get('mission_digest')}:tentativa_{reg.get('tentativa')}"
            if chave_existente == chave_idempotencia:
                raise IdempotenciaVioladaErro(
                    f"Violação de idempotência: a missão '{mission_id}' (digest '{mission_digest[:8]}...') "
                    f"na tentativa {tentativa} já foi processada sob o run_id '{id_existente}'."
                )

        agora = datetime.now(timezone.utc).isoformat()
        novo_registro = RegistroExecucao(
            run_id=run_id,
            mission_id=mission_id,
            mission_digest=mission_digest,
            estado_atual="CLAIMED",
            tentativa=tentativa,
            data_inicio_utc=agora,
            data_atualizacao_utc=agora,
            ativo=True,
        )

        execucoes[run_id] = asdict(novo_registro)
        self._gravar_estado(estado)
        return novo_registro

    def atualizar_estado(
        self,
        run_id: str,
        novo_estado: str,
        ativo: bool | None = None,
        resultado_final: str | None = None,
        motivo_bloqueio: str | None = None,
    ) -> None:
        """Atualiza a transição de estado de uma execução existente no checkpoint.

        Args:
            run_id: Identificador da execução.
            novo_estado: Próximo estado na máquina de estados.
            ativo: Indica se a execução continua ativa. Se None, mantém o valor anterior.
            resultado_final: Parecer conclusivo da execução, se encerrada.
            motivo_bloqueio: Descrição textual do motivo caso o estado seja terminal ou bloqueado.
        """
        estado = self._ler_estado()
        execucoes = estado.get("execucoes", {})
        if run_id not in execucoes:
            raise KeyError(f"Execução '{run_id}' não encontrada no checkpoint.")

        registro = execucoes[run_id]
        registro["estado_atual"] = novo_estado
        registro["data_atualizacao_utc"] = datetime.now(timezone.utc).isoformat()

        if ativo is not None:
            registro["ativo"] = ativo

        if resultado_final is not None:
            registro["resultado_final"] = resultado_final

        if motivo_bloqueio is not None:
            registro["motivo_bloqueio"] = motivo_bloqueio

        self._gravar_estado(estado)

    def obter_registro(self, run_id: str) -> dict[str, Any] | None:
        """Consulta um registro específico pelo run_id."""
        estado = self._ler_estado()
        return estado.get("execucoes", {}).get(run_id)

    def listar_execucoes(self) -> list[dict[str, Any]]:
        """Retorna a lista de todas as execuções registradas em ordem cronológica."""
        estado = self._ler_estado()
        return list(estado.get("execucoes", {}).values())
