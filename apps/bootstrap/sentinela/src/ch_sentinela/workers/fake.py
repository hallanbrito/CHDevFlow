"""FakeWorker: executor inteiramente simulado para validação do Bootstrap Engine.

Este worker é inofensivo e de efeito colateral estritamente nulo:
- Não toca arquivos do projeto ou do repositório.
- Não efetua chamadas a LLMs ou APIs remotas faturáveis.
- Não abre Pull Requests ou Issues.
- Não executa comandos de shell reais.
- Retorna saídas sintéticas estruturadas aderentes ao Worker Contract.
"""
from __future__ import annotations

import time
from typing import Any

from ch_sentinela.config import SCHEMA_WORKER_VERSAO
from ch_sentinela.contracts import ContratoMissao, ContratoWorkerResultado


class FakeWorkerErro(RuntimeError):
    """Exceção levantada quando uma simulação programada de falha do FakeWorker é acionada."""


class FakeWorker:
    """Implementação simulada do contrato de worker para ensaios e testes offline."""

    def __init__(
        self,
        modo_simulacao: str = "SUCESSO",
        atraso_segundos: float = 0.0,
    ) -> None:
        """Inicializa o FakeWorker.

        Args:
            modo_simulacao: Modo de resposta desejado: 'SUCESSO', 'FALHA', 'TIMEOUT' ou 'CANCELADO'.
            atraso_segundos: Pequeno atraso opcional para simular processamento temporal.
        """
        modos_validos = ("SUCESSO", "FALHA", "TIMEOUT", "CANCELADO")
        if modo_simulacao.upper() not in modos_validos:
            raise ValueError(f"Modo de simulação '{modo_simulacao}' inválido. Válidos: {modos_validos}")

        self.modo_simulacao = modo_simulacao.upper()
        self.atraso_segundos = atraso_segundos

    def processar_missao(
        self,
        missao: ContratoMissao,
        run_id: str,
        contexto_sandbox: dict[str, Any] | None = None,
    ) -> ContratoWorkerResultado:
        """Executa a simulação do ciclo de trabalho do worker.

        Args:
            missao: Contrato de missão previamente validado.
            run_id: Identificador da execução associada.
            contexto_sandbox: Metadados do ambiente de execução delimitado.

        Returns:
            ContratoWorkerResultado preenchido de forma sintética.
        """
        if self.atraso_segundos > 0:
            time.sleep(self.atraso_segundos)

        # 1. Simulação de TIMEOUT
        if self.modo_simulacao == "TIMEOUT":
            return ContratoWorkerResultado(
                schema=SCHEMA_WORKER_VERSAO,
                run_id=run_id,
                executor="fake",
                status="TIMED_OUT",
                exit_code=124,
                artifacts=[],
                tests=[
                    {
                        "id": "T_TIMEOUT",
                        "descricao": "Simulação de tempo limite operacional de 900s excedido",
                        "status": "FALHOU",
                    }
                ],
                cost={"currency": "BRL", "additional": 0, "verified": True},
                event_log_ref=f"local://{run_id}/eventos_fake.jsonl",
            )

        # 2. Simulação de CANCELAMENTO MANUAL
        if self.modo_simulacao == "CANCELADO":
            return ContratoWorkerResultado(
                schema=SCHEMA_WORKER_VERSAO,
                run_id=run_id,
                executor="fake",
                status="CANCELLED",
                exit_code=130,
                artifacts=[],
                tests=[
                    {
                        "id": "T_CANCEL",
                        "descricao": "Simulação de parada manual imediata solicitada pelo operador",
                        "status": "CANCELADO",
                    }
                ],
                cost={"currency": "BRL", "additional": 0, "verified": True},
                event_log_ref=f"local://{run_id}/eventos_fake.jsonl",
            )

        # 3. Simulação de FALHA INTERNA
        if self.modo_simulacao == "FALHA":
            return ContratoWorkerResultado(
                schema=SCHEMA_WORKER_VERSAO,
                run_id=run_id,
                executor="fake",
                status="FAILED",
                exit_code=1,
                artifacts=[],
                tests=[
                    {
                        "id": "T_FALHA_SIMULADA",
                        "descricao": "Simulação de erro na geração sintética do artefato",
                        "status": "FALHOU",
                    }
                ],
                cost={"currency": "BRL", "additional": 0, "verified": True},
                event_log_ref=f"local://{run_id}/eventos_fake.jsonl",
            )

        # 4. Simulação de SUCESSO (padrão)
        artefato_sintetico = {
            "caminho": "docs/bootstrap/artefato_sintetico_demo.md",
            "descricao": "Artefato puramente demonstrativo gerado pelo FakeWorker (em memória)",
            "digest_conteudo": "simulado_sha256_e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            "modificou_disco": False,
        }

        testes_sinteticos = [
            {
                "id": "TESTE_SIMULADO_01",
                "nome": "Verificação estática sintética",
                "status": "PASSOU",
            },
            {
                "id": "TESTE_SIMULADO_02",
                "nome": "Conformidade sintética de formato",
                "status": "PASSOU",
            },
        ]

        return ContratoWorkerResultado(
            schema=SCHEMA_WORKER_VERSAO,
            run_id=run_id,
            executor="fake",
            status="COMPLETED",
            exit_code=0,
            artifacts=[artefato_sintetico],
            tests=testes_sinteticos,
            cost={"currency": "BRL", "additional": 0, "verified": True},
            event_log_ref=f"local://{run_id}/eventos_fake.jsonl",
        )
