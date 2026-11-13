"""Fila sequencial persistente multi-repositório com controle estrito de concorrência.

Implementa os requisitos fundamentais de segurança e governança:
- Ordenação rigorosa por Prioridade CH (P0 > P1 > P2 > P3) e Risco CH (BAIXO > MEDIO > ALTO).
- Concorrência máxima global = 1 (uma única missão ativa no ecossistema inteiro).
- Persistência atômica segura no disco (.ch_sentinela/fila_sequencial_multi_repo.json).
- Idempotência com chave determinística {repo}:{issue}:{digest}:{attempt}.
- Replay protection: missões já registradas preservam seu estado e não são reexecutadas.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
from threading import Lock
from typing import Any

from ch_sentinela.config import (
    CUSTO_ADICIONAL_PERMITIDO_BRL,
    LIMITE_TEMPO_EXECUCAO_SEGUNDOS,
    MAXIMO_EXECUCOES_ATIVAS,
    MAXIMO_TENTATIVAS_RETRY,
    obter_diretorio_dados,
)
from ch_sentinela.security.policies import (
    ViolacaoPoliticaSegurancaErro,
    sanitizar_texto_segredos,
)
from chdevflow.core.multi_repo_verifier import ParecerElegibilidade


NOME_ARQUIVO_FILA_PADRAO = "fila_sequencial_multi_repo.json"

_PESO_PRIORIDADE: dict[str, int] = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
_PESO_RISCO: dict[str, int] = {"BAIXO": 0, "MEDIO": 1, "ALTO": 2, "CRITICO": 3}


@dataclass(frozen=True)
class ItemFila:
    """Entrada ordenada e imutável de uma missão na fila sequencial."""

    chave: str
    repositorio: str
    issue_number: int
    titulo: str
    prioridade_ch: str
    risco_ch: str
    etapa_ch: str
    autonomia_ch: str
    decisao_po: str
    card_id: str | None
    url: str | None
    enfileirado_em_utc: str
    mission_digest: str = ""

    @property
    def rank(self) -> tuple[int, int, str]:
        """Critério de ordenação determinístico: prioridade -> risco -> timestamp."""
        p_val = _PESO_PRIORIDADE.get(self.prioridade_ch.upper(), 99)
        r_val = _PESO_RISCO.get(self.risco_ch.upper(), 99)
        return (p_val, r_val, self.enfileirado_em_utc)

    def para_dicionario(self) -> dict[str, Any]:
        """Serializa o item da fila."""
        return asdict(self)


@dataclass
class RegistroReserva:
    """Estado persistido de uma reserva ativa ou histórica."""

    chave: str
    run_id: str
    repositorio: str
    issue_number: int
    mission_digest: str
    tentativa: int
    estado: str  # "CLAIMED", "RUNNING", "COMPLETED", "BLOCKED", "TIMED_OUT", "CANCELLED", "INDETERMINATE"
    motivo: str
    iniciado_em_utc: str
    atualizado_em_utc: str
    custo_adicional_brl: float = 0.0

    def para_dicionario(self) -> dict[str, Any]:
        return asdict(self)


class FilaSequencialMultiRepo:
    """Gerenciador da fila sequencial persistente com controle atômico de concorrência."""

    def __init__(self, caminho_arquivo: Path | None = None) -> None:
        """Inicializa a fila.

        Args:
            caminho_arquivo: Caminho opcional do arquivo de persistência (usado em testes).
        """
        self._lock = Lock()
        if caminho_arquivo is not None:
            self.caminho_arquivo = Path(caminho_arquivo)
        else:
            self.caminho_arquivo = obter_diretorio_dados() / NOME_ARQUIVO_FILA_PADRAO

        self._itens_fila: list[ItemFila] = []
        self._reservas: dict[str, RegistroReserva] = {}
        self._reserva_ativa: str | None = None
        self._carregar_estado()

    def _carregar_estado(self) -> None:
        """Carrega o estado persistido do arquivo JSON se existir."""
        if not self.caminho_arquivo.exists():
            return

        try:
            with open(self.caminho_arquivo, "r", encoding="utf-8") as f:
                dados = json.load(f)

            if not isinstance(dados, dict):
                return

            itens_raw = dados.get("itens_fila", [])
            self._itens_fila = [
                ItemFila(**item) for item in itens_raw if isinstance(item, dict)
            ]

            reservas_raw = dados.get("reservas", {})
            self._reservas = {}
            for k, v in reservas_raw.items():
                if isinstance(v, dict):
                    self._reservas[k] = RegistroReserva(**v)

            self._reserva_ativa = dados.get("reserva_ativa")
        except (json.JSONDecodeError, OSError, TypeError, KeyError):
            # Se houver erro de parsing, mantém estado limpo para integridade
            self._itens_fila = []
            self._reservas = {}
            self._reserva_ativa = None

    def _salvar_estado(self) -> None:
        """Persiste o estado atômico no disco com modo 0o600."""
        self.caminho_arquivo.parent.mkdir(parents=True, exist_ok=True)
        dir_pai = self.caminho_arquivo.parent

        dados = {
            "schema": "chdevflow.multi-repo-queue/1.0",
            "atualizado_em_utc": datetime.now(timezone.utc).isoformat(),
            "reserva_ativa": self._reserva_ativa,
            "total_na_fila": len(self._itens_fila),
            "itens_fila": [item.para_dicionario() for item in self._itens_fila],
            "reservas": {k: v.para_dicionario() for k, v in self._reservas.items()},
        }

        fd, temp_path = tempfile.mkstemp(dir=dir_pai, prefix="queue_", suffix=".tmp")
        try:
            with open(fd, "w", encoding="utf-8") as f:
                json.dump(dados, f, ensure_ascii=False, indent=2)
            try:
                os.chmod(temp_path, 0o600)
            except OSError:
                pass  # Em ambientes Windows pode não aplicar permissões POSIX
            os.replace(temp_path, self.caminho_arquivo)
        except Exception:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
            raise

    def sincronizar_com_pareceres(
        self, pareceres: list[ParecerElegibilidade], titulos: dict[str, str] | None = None
    ) -> list[ItemFila]:
        """Sincroniza a fila com a lista de pareceres elegíveis e reordena por prioridade.

        Args:
            pareceres: Lista de pareceres gerados pelo verificador.
            titulos: Mapeamento opcional de chave para título legível da missão.

        Returns:
            Lista ordenada dos itens atualmente na fila.
        """
        titulos = titulos or {}
        with self._lock:
            chaves_atuais = {item.chave for item in self._itens_fila}
            novos_itens = list(self._itens_fila)

            for p in pareceres:
                if not p.elegivel:
                    continue

                repo = p.repositorio or "hallanbrito/CHDevFlow"
                num = p.issue_number or 0
                digest = p.baseline_sha or ""
                chave = f"{repo}:{num}:{digest}"

                # Não reinsere se já estiver na fila
                if chave in chaves_atuais:
                    continue

                # Não reinsere se já tiver reserva concluída com sucesso
                reserva_existente = self._reservas.get(chave)
                if reserva_existente and reserva_existente.estado in ("COMPLETED", "CLAIMED", "RUNNING"):
                    continue

                titulo = titulos.get(chave, f"Missão #{num} em {repo}")
                item = ItemFila(
                    chave=chave,
                    repositorio=repo,
                    issue_number=num,
                    titulo=titulo,
                    prioridade_ch=p.prioridade_ch or "P2",
                    risco_ch=p.risco_ch or "BAIXO",
                    etapa_ch=p.etapa_ch or "PRONTA",
                    autonomia_ch=p.autonomia_ch or "CH-2",
                    decisao_po=p.decisao_po or "APROVADO",
                    card_id=p.card_id,
                    url=p.url,
                    enfileirado_em_utc=datetime.now(timezone.utc).isoformat(),
                    mission_digest=digest,
                )
                novos_itens.append(item)
                chaves_atuais.add(chave)

            # Ordenação canônica por rank (Prioridade P0..P3 -> Risco BAIXO..ALTO -> Timestamp)
            novos_itens.sort(key=lambda x: x.rank)
            self._itens_fila = novos_itens
            self._salvar_estado()
            return list(self._itens_fila)

    def obter_fila(self) -> tuple[ItemFila, ...]:
        """Retorna a visão imutável atual da fila ordenada."""
        with self._lock:
            return tuple(self._itens_fila)

    def obter_reserva_ativa(self) -> RegistroReserva | None:
        """Retorna a reserva ativa no momento, ou None se livre."""
        with self._lock:
            if self._reserva_ativa and self._reserva_ativa in self._reservas:
                return self._reservas[self._reserva_ativa]
            return None

    def reservar_proxima(
        self, run_id: str, attempt: int = 1, repo_especifico: str | None = None
    ) -> RegistroReserva | None:
        """Reserva atomicamente a próxima missão elegível da fila global.

        Garante exclusão mútua global: se já houver uma missão ativa em qualquer
        repositório do catálogo, recusa nova reserva levantando ConcorrenciaBloqueadaErro.

        Args:
            run_id: Identificador único e rastreável do ciclo/execução.
            attempt: Número da tentativa (1 para normal, 2 apenas após diagnóstico formal).
            repo_especifico: Se fornecido, reserva a próxima exclusivamente desse repositório.

        Returns:
            RegistroReserva criado ou None se a fila estiver vazia.

        Raises:
            RuntimeError: Se houver concorrência bloqueada ou tentativa inválida.
        """
        if attempt not in (1, 2):
            raise ValueError(f"Tentativa {attempt} inválida (permitido 1 ou 2).")

        with self._lock:
            # 1. Regra de concorrência irrevogável: exatamente 1 missão ativa globalmente
            if self._reserva_ativa is not None:
                ativa = self._reservas.get(self._reserva_ativa)
                if ativa and ativa.estado in ("CLAIMED", "RUNNING"):
                    raise RuntimeError(
                        f"Concorrência bloqueada! Já existe uma missão ativa no ecossistema: "
                        f"'{ativa.chave}' (run_id: {ativa.run_id}, estado: {ativa.estado}). "
                        f"Limite D06: máximo de 1 missão ativa globalmente."
                    )

            if not self._itens_fila:
                return None

            # 2. Localiza a primeira missão elegível
            candidato: ItemFila | None = None
            indice_candidato = -1
            for idx, item in enumerate(self._itens_fila):
                if repo_especifico and item.repositorio.lower() != repo_especifico.lower():
                    continue
                candidato = item
                indice_candidato = idx
                break

            if candidato is None:
                return None

            chave_reserva = f"{candidato.chave}:{attempt}"

            # 3. Proteção contra Replay Idempotente
            if chave_reserva in self._reservas:
                existente = self._reservas[chave_reserva]
                if existente.estado in ("CLAIMED", "RUNNING"):
                    self._reserva_ativa = chave_reserva
                    return existente
                # Se já concluída, remove da fila e avança
                self._itens_fila.pop(indice_candidato)
                self._salvar_estado()
                return existente

            # 4. Criação da reserva
            agora = datetime.now(timezone.utc).isoformat()
            reserva = RegistroReserva(
                chave=chave_reserva,
                run_id=run_id,
                repositorio=candidato.repositorio,
                issue_number=candidato.issue_number,
                mission_digest=candidato.mission_digest,
                tentativa=attempt,
                estado="CLAIMED",
                motivo=f"Reserva exclusiva da missão #{candidato.issue_number} em {candidato.repositorio}.",
                iniciado_em_utc=agora,
                atualizado_em_utc=agora,
                custo_adicional_brl=0.0,
            )

            self._reservas[chave_reserva] = reserva
            self._reserva_ativa = chave_reserva
            # Remove o item reservado da fila de espera
            self._itens_fila.pop(indice_candidato)
            self._salvar_estado()
            return reserva

    def finalizar_reserva(
        self, chave: str, estado_final: str, motivo: str, custo_brl: float = 0.0
    ) -> RegistroReserva:
        """Finaliza a reserva com o estado final e libera o lock de concorrência.

        Args:
            chave: Chave da reserva.
            estado_final: Estado de término (COMPLETED, BLOCKED, TIMED_OUT, CANCELLED, INDETERMINATE).
            motivo: Justificativa auditável do encerramento.
            custo_brl: Custo incremental incorrido (deve ser 0.0).

        Returns:
            RegistroReserva atualizado.
        """
        with self._lock:
            if chave not in self._reservas:
                raise ValueError(f"Reserva '{chave}' desconhecida.")

            reserva = self._reservas[chave]
            agora = datetime.now(timezone.utc).isoformat()

            reserva.estado = estado_final
            reserva.motivo = sanitizar_texto_segredos(motivo)
            reserva.atualizado_em_utc = agora
            reserva.custo_adicional_brl = custo_brl

            if self._reserva_ativa == chave:
                self._reserva_ativa = None

            self._salvar_estado()
            return reserva

    def cancelar_reserva(self, chave: str, motivo: str) -> None:
        """Cancela administrativamente uma reserva ativa, liberando o lock."""
        self.finalizar_reserva(chave, "CANCELLED", motivo)
