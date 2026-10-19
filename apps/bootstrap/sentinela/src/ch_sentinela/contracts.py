"""Definição e validação dos contratos canônicos do CHDevFlow Bootstrap Engine.

Implementa os três contratos versionados da arquitetura:
1. Contrato de Missão (Mission Contract - schema chdevflow.mission/0.1)
2. Contrato de Resultado do Worker (Worker Contract - schema chdevflow.worker-result/0.1)
3. Contrato de Supervisão (Supervisor Contract - schema chdevflow.supervisor-result/0.1)
além do Contrato de Autorização Separada do Product Owner.

Todas as validações aplicam princípios de 'fail-closed': dados ambíguos,
incompletos ou adulterados causam invalidação imediata.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from ch_sentinela.config import (
    CUSTO_ADICIONAL_PERMITIDO_BRL,
    LIMITE_TEMPO_EXECUCAO_SEGUNDOS,
    MAXIMO_EXECUCOES_ATIVAS,
    MAXIMO_TENTATIVAS_RETRY,
    PO_IDENTIDADE_PADRAO,
    REPOSITORIO_CANONICO,
    REPOSITORIOS_PERMITIDOS,
    SCHEMA_MISSAO_VERSAO,
    SCHEMA_SUPERVISOR_VERSAO,
    SCHEMA_WORKER_VERSAO,
)
from ch_sentinela.security.policies import (
    ViolacaoPoliticaSegurancaErro,
    validar_caminhos_escopo,
    validar_custo_zero,
    validar_limites_recurso,
    validar_origem_autorizacao,
    validar_sha_commit,
)


class ContratoInvalidoErro(ValueError):
    """Exceção levantada quando um contrato possui formato inválido ou campos ausentes."""


def serializar_json_canonico(objeto: Any) -> str:
    """Serializa qualquer estrutura Python em JSON canônico e determinístico.

    Usa ordenação de chaves (sort_keys=True) e separadores compactos sem espaços extras,
    garantindo que o cálculo de hash/digest seja reprodutível em qualquer ambiente.

    Args:
        objeto: Dicionário ou lista a ser serializado.

    Returns:
        String JSON formatada canonicamente.
    """
    return json.dumps(objeto, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def calcular_digest_sha256(objeto: Any) -> str:
    """Calcula o digest criptográfico SHA-256 do JSON canônico de um objeto.

    Args:
        objeto: Estrutura de dados serializável.

    Returns:
        Hash hexadecimal SHA-256 de 64 caracteres.
    """
    json_str = serializar_json_canonico(objeto)
    return hashlib.sha256(json_str.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ContratoMissao:
    """Representa a entrada imutável de uma missão elegível para execução."""

    schema: str
    mission_id: str
    source: dict[str, Any]
    target: dict[str, Any]
    worker: str
    autonomy: str
    instruction_ref: str
    limits: dict[str, Any]
    mission_digest: str = ""

    def para_dicionario(self, incluir_digest: bool = True) -> dict[str, Any]:
        """Converte a missão para dicionário compatível com o schema JSON.

        Args:
            incluir_digest: Se True, inclui a chave 'mission_digest' no dicionário.
        """
        dados: dict[str, Any] = {
            "schema": self.schema,
            "mission_id": self.mission_id,
            "source": dict(self.source),
            "target": dict(self.target),
            "worker": self.worker,
            "autonomy": self.autonomy,
            "instruction_ref": self.instruction_ref,
            "limits": dict(self.limits),
        }
        if incluir_digest and self.mission_digest:
            dados["mission_digest"] = self.mission_digest
        return dados

    def calcular_digest(self) -> str:
        """Gera o digest SHA-256 calculado exclusivamente sobre o payload da missão (sem o digest em si)."""
        dados_sem_digest = self.para_dicionario(incluir_digest=False)
        return calcular_digest_sha256(dados_sem_digest)


@dataclass(frozen=True)
class ContratoAutorizacao:
    """Representa a autorização explícita e externa concedida pelo Product Owner."""

    approval_type: str
    issue_ref: str
    mission_digest: str
    baseline_sha: str
    authorized_executor: str
    authorized_repo: str
    approved_by: str
    approved_at: str
    event_id: str
    is_simulation: bool = False

    def validar_contra_missao(self, missao: ContratoMissao) -> None:
        """Verifica se a autorização corresponde fielmente aos parâmetros da missão.

        Qualquer discrepância de digest, SHA, repositório ou executor invalida a autorização.

        Args:
            missao: Contrato de missão a ser validado.

        Raises:
            ViolacaoPoliticaSegurancaErro: Se houver divergência entre autorização e missão.
        """
        # Validação do emissor e evento
        validar_origem_autorizacao(
            aprovado_por=self.approved_by,
            evento_id=self.event_id,
            contexto_simulacao=self.is_simulation,
        )

        # Validação de conformidade do digest da missão
        digest_calculado = missao.calcular_digest()
        if self.mission_digest != digest_calculado:
            raise ViolacaoPoliticaSegurancaErro(
                f"Divergência de digest de missão detectada! "
                f"Autorizado: '{self.mission_digest}', Calculado: '{digest_calculado}'."
            )

        # Validação de conformidade do SHA de baseline
        sha_missao = missao.target.get("base_sha", "")
        if self.baseline_sha.lower() != sha_missao.lower():
            raise ViolacaoPoliticaSegurancaErro(
                f"Divergência de SHA de baseline detectada! "
                f"Autorizado: '{self.baseline_sha}', Missão: '{sha_missao}'."
            )

        # Validação de conformidade do repositório alvo
        repo_missao = missao.target.get("repository", "")
        if self.authorized_repo != repo_missao:
            raise ViolacaoPoliticaSegurancaErro(
                f"Divergência de repositório! "
                f"Autorizado: '{self.authorized_repo}', Missão: '{repo_missao}'."
            )

        # Validação do executor autorizado
        if self.authorized_executor != missao.worker:
            raise ViolacaoPoliticaSegurancaErro(
                f"Divergência de executor! "
                f"Autorizado: '{self.authorized_executor}', Missão: '{missao.worker}'."
            )


@dataclass(frozen=True)
class ContratoWorkerResultado:
    """Saída estruturada e padronizada emitida por qualquer worker ao supervisor."""

    schema: str
    run_id: str
    executor: str
    status: str
    exit_code: int
    artifacts: list[dict[str, Any]]
    tests: list[dict[str, Any]]
    cost: dict[str, Any]
    event_log_ref: str

    def para_dicionario(self) -> dict[str, Any]:
        """Converte o resultado do worker para dicionário JSON."""
        return asdict(self)


@dataclass(frozen=True)
class ContratoSupervisorResultado:
    """Resultado emitido pelo supervisor ao final do ciclo de processamento da missão."""

    schema: str
    run_id: str
    mission_digest: str
    state: str
    validations: dict[str, str]
    ruc_ref: str | None = None
    pr_ref: str | None = None
    human_decision: str | None = None

    def para_dicionario(self) -> dict[str, Any]:
        """Converte o resultado do supervisor para dicionário JSON."""
        return asdict(self)


def validar_contrato_missao(payload: dict[str, Any]) -> ContratoMissao:
    """Analisa e valida rigorosamente um payload bruto para construir um ContratoMissao.

    Verifica conformidade com schema, repositórios permitidos, regras de escopo,
    limites operacionais e integridade do digest.

    Args:
        payload: Dicionário contendo os dados brutos da missão.

    Returns:
        Instância validada e imutável de ContratoMissao.

    Raises:
        ContratoInvalidoErro: Se faltarem campos obrigatórios ou formatos básicos.
        ViolacaoPoliticaSegurancaErro: Se violar limites de segurança ou repositório.
    """
    if not isinstance(payload, dict):
        raise ContratoInvalidoErro("O payload da missão deve ser um dicionário JSON.")

    # 1. Validação de versão do schema
    schema = payload.get("schema")
    if schema != SCHEMA_MISSAO_VERSAO:
        raise ContratoInvalidoErro(
            f"Schema de missão incompatível: '{schema}'. Esperado '{SCHEMA_MISSAO_VERSAO}'."
        )

    # 2. Identificador da missão
    mission_id = payload.get("mission_id")
    if not isinstance(mission_id, str) or not mission_id.strip():
        raise ContratoInvalidoErro("Campo 'mission_id' obrigatório e não pode ser vazio.")

    # 3. Dados de origem (source)
    source = payload.get("source")
    if not isinstance(source, dict):
        raise ContratoInvalidoErro("Campo 'source' obrigatório deve ser um objeto.")

    source_repo = source.get("repository")
    if source_repo not in REPOSITORIOS_PERMITIDOS:
        raise ViolacaoPoliticaSegurancaErro(
            f"Repositório de origem '{source_repo}' não está na lista de permitidos: {REPOSITORIOS_PERMITIDOS}."
        )

    issue_num = source.get("issue")
    if not isinstance(issue_num, int) or issue_num <= 0:
        raise ContratoInvalidoErro(f"Número de Issue inválido em 'source': '{issue_num}'.")

    # 4. Dados de destino (target)
    target = payload.get("target")
    if not isinstance(target, dict):
        raise ContratoInvalidoErro("Campo 'target' obrigatório deve ser um objeto.")

    target_repo = target.get("repository")
    if target_repo not in REPOSITORIOS_PERMITIDOS:
        raise ViolacaoPoliticaSegurancaErro(
            f"Repositório de destino '{target_repo}' não está na lista de permitidos: {REPOSITORIOS_PERMITIDOS}."
        )

    base_sha = target.get("base_sha")
    validar_sha_commit(base_sha)

    allowed_paths = target.get("allowed_paths")
    blocked_paths = target.get("blocked_paths")
    validar_caminhos_escopo(allowed_paths, blocked_paths)

    # 5. Worker e autonomia
    worker = payload.get("worker")
    if not isinstance(worker, str) or not worker.strip():
        raise ContratoInvalidoErro("Campo 'worker' obrigatório.")

    autonomy = payload.get("autonomy")
    if autonomy not in ("CH-0", "CH-1", "CH-2"):
        raise ContratoInvalidoErro(f"Nível de autonomia '{autonomy}' inválido. Esperado CH-0, CH-1 ou CH-2.")

    # 6. Referência de instrução
    instruction_ref = payload.get("instruction_ref")
    if not isinstance(instruction_ref, str) or not instruction_ref.strip():
        raise ContratoInvalidoErro("Campo 'instruction_ref' obrigatório.")

    # 7. Limites operacionais (D06)
    limits = payload.get("limits")
    validar_limites_recurso(limits)
    validar_custo_zero(limits.get("extra_cost_brl"))

    # Constrói contrato preliminar para calcular digest real
    missao = ContratoMissao(
        schema=schema,
        mission_id=mission_id.strip(),
        source=dict(source),
        target=dict(target),
        worker=worker.strip(),
        autonomy=autonomy,
        instruction_ref=instruction_ref.strip(),
        limits=dict(limits),
    )

    digest_calculado = missao.calcular_digest()

    # Se o payload já forneceu um mission_digest, valida se coincide com o calculado
    digest_declarado = payload.get("mission_digest")
    if digest_declarado and digest_declarado != digest_calculado:
        raise ViolacaoPoliticaSegurancaErro(
            f"Digest da missão adulterado ou desatualizado! "
            f"Declarado: '{digest_declarado}', Calculado: '{digest_calculado}'."
        )

    # Retorna missão com o digest canônico preenchido
    return ContratoMissao(
        schema=missao.schema,
        mission_id=missao.mission_id,
        source=missao.source,
        target=missao.target,
        worker=missao.worker,
        autonomy=missao.autonomy,
        instruction_ref=missao.instruction_ref,
        limits=missao.limits,
        mission_digest=digest_calculado,
    )
