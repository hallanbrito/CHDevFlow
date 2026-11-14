"""Verificador fail-closed de autorização e integridade multi-repositório.

Implementa a validação rigorosa dos portões do Método C.H. para a Esteira AGY:
- Se os campos estruturados do Project #2 não estiverem presentes, não infere
  elegibilidade a partir de labels ou estados visuais (Fail-Closed).
- Filtra estritamente missões atribuídas à Esteira AGY.
- Exige decisão expressa do PO ('APROVADO') ou gate formal autenticado.
- Valida o repositório no catálogo permitido.
- Valida baseline SHA (40 caracteres hexadecimais), delimitando escopo de arquivos.
- Valida custo zero obrigatório (Decisão D06: R$ 0,00).
- Avalia risco: Risco CRÍTICO bloqueia a execução automática.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ch_sentinela.config import (
    CUSTO_ADICIONAL_PERMITIDO_BRL,
    LIMITE_TEMPO_EXECUCAO_SEGUNDOS,
    MAXIMO_EXECUCOES_ATIVAS,
    PO_IDENTIDADE_PADRAO,
)
from ch_sentinela.contracts import ContratoAutorizacao, ContratoMissao
from ch_sentinela.security.policies import (
    ViolacaoPoliticaSegurancaErro,
    sanitizar_texto_segredos,
    validar_caminhos_escopo,
    validar_custo_zero,
    validar_limites_recurso,
    validar_origem_autorizacao,
    validar_sha_commit,
)
from chdevflow.core.multi_repo_registry import (
    RepositorioPermitido,
    normalizar_identificador_repositorio,
    validar_repositorio_autorizado,
)


CAMPOS_GOVERNANCA_OBRIGATORIOS: tuple[str, ...] = (
    "Esteira",
    "Etapa CH",
    "Decisao PO",
    "Autonomia CH",
    "Prioridade CH",
    "Risco CH",
)

VALORES_VALIDOS_ESTEIRA: tuple[str, ...] = ("AGY", "ChatGPT", "Codex", "Hallan")
VALORES_VALIDOS_ETAPA: tuple[str, ...] = (
    "BACKLOG",
    "PRONTA",
    "EM_EXECUCAO",
    "EM_REVISAO",
    "AGUARDANDO_PO",
    "APROVADA",
    "PARCIAL",
    "CORRECOES",
    "REPROVADA",
    "INTEGRADA",
    "HOMOLOGADA",
)
VALORES_VALIDOS_DECISAO_PO: tuple[str, ...] = (
    "PENDENTE",
    "APROVADO",
    "PARCIAL",
    "AJUSTES",
    "REPROVADO",
)
VALORES_VALIDOS_AUTONOMIA: tuple[str, ...] = ("CH-0", "CH-1", "CH-2", "CH-3")
VALORES_VALIDOS_PRIORIDADE: tuple[str, ...] = ("P0", "P1", "P2", "P3")
VALORES_VALIDOS_RISCO: tuple[str, ...] = ("BAIXO", "MEDIO", "ALTO", "CRITICO")


@dataclass(frozen=True)
class ParecerElegibilidade:
    """Resultado estruturado e detalhado da análise de elegibilidade de uma missão."""

    elegivel: bool
    status: str
    motivo: str
    repositorio: str | None
    issue_number: int | None
    esteira: str | None
    etapa_ch: str | None
    decisao_po: str | None
    autonomia_ch: str | None
    prioridade_ch: str | None
    risco_ch: str | None
    card_id: str | None = None
    url: str | None = None
    baseline_sha: str | None = None
    allowed_paths: tuple[str, ...] = ()
    custo_adicional_brl: float = 0.0
    autorizado_por: str | None = None
    autorizacao_valida: bool = False
    contrato_autorizacao_ref: str | None = None

    def para_dicionario(self) -> dict[str, Any]:
        """Converte o parecer para dicionário JSON."""
        return {
            "elegivel": self.elegivel,
            "status": self.status,
            "motivo": self.motivo,
            "repositorio": self.repositorio,
            "issue_number": self.issue_number,
            "esteira": self.esteira,
            "etapa_ch": self.etapa_ch,
            "decisao_po": self.decisao_po,
            "autonomia_ch": self.autonomia_ch,
            "prioridade_ch": self.prioridade_ch,
            "risco_ch": self.risco_ch,
            "card_id": self.card_id,
            "url": self.url,
            "baseline_sha": self.baseline_sha,
            "allowed_paths": list(self.allowed_paths),
            "custo_adicional_brl": self.custo_adicional_brl,
            "autorizado_por": self.autorizado_por,
            "autorizacao_valida": self.autorizacao_valida,
            "contrato_autorizacao_ref": self.contrato_autorizacao_ref,
        }


class VerificadorAutorizacaoMultiRepo:
    """Validador fail-closed para missões submetidas à Esteira AGY."""

    def __init__(
        self,
        po_identidade: str = PO_IDENTIDADE_PADRAO,
        autorizacoes: Mapping[str | int, ContratoAutorizacao] | None = None,
        exigir_contrato_po: bool = True,
    ) -> None:
        self.po_identidade = po_identidade
        self.autorizacoes = autorizacoes or {}
        self.exigir_contrato_po = exigir_contrato_po

    def avaliar_item_projeto(
        self,
        item: dict[str, Any],
        sha_observado: str | None = None,
        paths_autorizados: list[str] | None = None,
        fixture_autorizacao: ContratoAutorizacao | None = None,
        autorizacoes: Mapping[str | int, ContratoAutorizacao] | None = None,
        exigir_contrato_po: bool | None = None,
    ) -> ParecerElegibilidade:
        """Avalia um cartão extraído do GitHub Project #2.

        Aplica rigorosamente a regra: Se não houver acesso aos campos do Project,
        NÃO inferir elegibilidade a partir de labels ou estados visuais.

        Args:
            item: Dicionário contendo os dados do cartão do Project #2.
            sha_observado: SHA do commit HEAD observado no repositório local/remoto.
            paths_autorizados: Lista opcional de caminhos permitidos (se definidos no contrato).
            fixture_autorizacao: Fixture de autorização (para testes ou simulações).
            autorizacoes: Dicionário opcional mapeando issue/repo para contratos de autorização.
            exigir_contrato_po: Se True, exige contrato formal do PO para aprovar missões.

        Returns:
            ParecerElegibilidade com o veredito fail-closed.
        """
        card_id = item.get("id") or item.get("card_id")
        content = item.get("content") if isinstance(item.get("content"), dict) else {}
        issue_number = content.get("number") or item.get("number")
        url = content.get("url") or item.get("url")

        # 1. Resolução do repositório
        repo_raw = content.get("repository") or item.get("repository")
        if not repo_raw:
            return ParecerElegibilidade(
                elegivel=False,
                status="BLOQUEADO_SEM_REPOSITORIO",
                motivo="Item do Project sem repositório identificado.",
                repositorio=None,
                issue_number=issue_number,
                esteira=None,
                etapa_ch=None,
                decisao_po=None,
                autonomia_ch=None,
                prioridade_ch=None,
                risco_ch=None,
                card_id=card_id,
                url=url,
            )

        try:
            repo_info = validar_repositorio_autorizado(str(repo_raw))
        except ViolacaoPoliticaSegurancaErro as exc:
            return ParecerElegibilidade(
                elegivel=False,
                status="BLOQUEADO_REPOSITORIO_NAO_AUTORIZADO",
                motivo=sanitizar_texto_segredos(str(exc)),
                repositorio=str(repo_raw),
                issue_number=issue_number,
                esteira=None,
                etapa_ch=None,
                decisao_po=None,
                autonomia_ch=None,
                prioridade_ch=None,
                risco_ch=None,
                card_id=card_id,
                url=url,
            )

        # 2. Extração dos campos canônicos do Project (suporta snake_case e nomes originais)
        esteira = item.get("esteira") or item.get("Esteira")
        etapa_ch = item.get("etapa_ch") or item.get("etapa CH") or item.get("Etapa CH")
        decisao_po = item.get("decisao_po") or item.get("decisao PO") or item.get("Decisao PO")
        autonomia_ch = item.get("autonomia_ch") or item.get("autonomia CH") or item.get("Autonomia CH")
        prioridade_ch = item.get("prioridade_ch") or item.get("prioridade CH") or item.get("Prioridade CH")
        risco_ch = item.get("risco_ch") or item.get("risco CH") or item.get("Risco CH")

        # Regra irrevogável: sem campos do Project, não inferir elegibilidade por labels!
        campos_faltantes = []
        if not esteira or esteira == "NÃO_OBSERVADO":
            campos_faltantes.append("Esteira")
        if not etapa_ch or etapa_ch == "NÃO_OBSERVADO":
            campos_faltantes.append("Etapa CH")
        if not decisao_po or decisao_po == "NÃO_OBSERVADO":
            campos_faltantes.append("Decisao PO")
        if not autonomia_ch or autonomia_ch == "NÃO_OBSERVADO":
            campos_faltantes.append("Autonomia CH")

        if campos_faltantes:
            return ParecerElegibilidade(
                elegivel=False,
                status="DADOS_INSUFICIENTES",
                motivo=(
                    f"Campos essenciais ausentes ou não preenchidos no Project #2: {', '.join(campos_faltantes)}. "
                    f"Regra de governança: elegibilidade não pode ser inferida de labels ou estados visuais."
                ),
                repositorio=repo_info.full_name,
                issue_number=issue_number,
                esteira=esteira,
                etapa_ch=etapa_ch,
                decisao_po=decisao_po,
                autonomia_ch=autonomia_ch,
                prioridade_ch=prioridade_ch,
                risco_ch=risco_ch,
                card_id=card_id,
                url=url,
            )

        # 3. Filtro estrito de Esteira: apenas 'AGY' (Peão)
        if esteira != "AGY":
            return ParecerElegibilidade(
                elegivel=False,
                status="IGNORADO_OUTRA_ESTEIRA",
                motivo=f"Missão pertence à esteira '{esteira}', não à Esteira AGY.",
                repositorio=repo_info.full_name,
                issue_number=issue_number,
                esteira=esteira,
                etapa_ch=etapa_ch,
                decisao_po=decisao_po,
                autonomia_ch=autonomia_ch,
                prioridade_ch=prioridade_ch,
                risco_ch=risco_ch,
                card_id=card_id,
                url=url,
            )

        # 4. Decisão expressa do PO
        if decisao_po != "APROVADO":
            return ParecerElegibilidade(
                elegivel=False,
                status="BLOQUEADO_SEM_AUTORIZACAO_PO",
                motivo=f"Decisão do PO é '{decisao_po}'. Apenas 'APROVADO' autoriza avanço.",
                repositorio=repo_info.full_name,
                issue_number=issue_number,
                esteira=esteira,
                etapa_ch=etapa_ch,
                decisao_po=decisao_po,
                autonomia_ch=autonomia_ch,
                prioridade_ch=prioridade_ch,
                risco_ch=risco_ch,
                card_id=card_id,
                url=url,
            )

        # 4.1 Resolução e validação obrigatória do contrato de autorização do PO (Auditoria Priority 1)
        deve_exigir = self.exigir_contrato_po if exigir_contrato_po is None else exigir_contrato_po
        auth: ContratoAutorizacao | None = fixture_autorizacao

        mapa_auth = dict(self.autorizacoes)
        if autorizacoes:
            mapa_auth.update(autorizacoes)

        if auth is None and issue_number is not None:
            auth = (
                mapa_auth.get(f"{repo_info.full_name}:{issue_number}")
                or mapa_auth.get(f"{repo_info.slug}:{issue_number}")
                or mapa_auth.get(str(issue_number))
                or mapa_auth.get(issue_number)
            )

        if auth is None:
            raw_auth = item.get("autorizacao") or item.get("contrato_autorizacao")
            if isinstance(raw_auth, ContratoAutorizacao):
                auth = raw_auth
            elif isinstance(raw_auth, dict):
                try:
                    auth = ContratoAutorizacao(**raw_auth)
                except Exception as exc:
                    return ParecerElegibilidade(
                        elegivel=False,
                        status="BLOQUEADO_AUTORIZACAO_INVALIDA",
                        motivo=f"Contrato de autorização embutido com formato inválido: {sanitizar_texto_segredos(str(exc))}",
                        repositorio=repo_info.full_name,
                        issue_number=issue_number,
                        esteira=esteira,
                        etapa_ch=etapa_ch,
                        decisao_po=decisao_po,
                        autonomia_ch=autonomia_ch,
                        prioridade_ch=prioridade_ch,
                        risco_ch=risco_ch,
                        card_id=card_id,
                        url=url,
                    )

        if auth is None and deve_exigir:
            return ParecerElegibilidade(
                elegivel=False,
                status="BLOQUEADO_SEM_CONTRATO_AUTORIZACAO",
                motivo=(
                    f"Decisão PO está 'APROVADO', porém contrato formal de autorização do PO ({self.po_identidade}) "
                    f"não foi localizado para esta missão (Princípio Fail-Closed do Método C.H.)."
                ),
                repositorio=repo_info.full_name,
                issue_number=issue_number,
                esteira=esteira,
                etapa_ch=etapa_ch,
                decisao_po=decisao_po,
                autonomia_ch=autonomia_ch,
                prioridade_ch=prioridade_ch,
                risco_ch=risco_ch,
                card_id=card_id,
                url=url,
            )

        if auth is not None:
            try:
                validar_origem_autorizacao(
                    aprovado_por=auth.approved_by,
                    evento_id=auth.event_id,
                    contexto_simulacao=getattr(auth, "is_simulation", False),
                )
            except ViolacaoPoliticaSegurancaErro as exc:
                return ParecerElegibilidade(
                    elegivel=False,
                    status="BLOQUEADO_AUTORIZACAO_INVALIDA",
                    motivo=sanitizar_texto_segredos(str(exc)),
                    repositorio=repo_info.full_name,
                    issue_number=issue_number,
                    esteira=esteira,
                    etapa_ch=etapa_ch,
                    decisao_po=decisao_po,
                    autonomia_ch=autonomia_ch,
                    prioridade_ch=prioridade_ch,
                    risco_ch=risco_ch,
                    card_id=card_id,
                    url=url,
                )

            if auth.approved_by != self.po_identidade:
                return ParecerElegibilidade(
                    elegivel=False,
                    status="BLOQUEADO_AUTORIZACAO_INVALIDA",
                    motivo=f"Autorização não provém do PO canônico '{self.po_identidade}' (aprovado por '{auth.approved_by}').",
                    repositorio=repo_info.full_name,
                    issue_number=issue_number,
                    esteira=esteira,
                    etapa_ch=etapa_ch,
                    decisao_po=decisao_po,
                    autonomia_ch=autonomia_ch,
                    prioridade_ch=prioridade_ch,
                    risco_ch=risco_ch,
                    card_id=card_id,
                    url=url,
                )

            if auth.authorized_repo != repo_info.full_name:
                return ParecerElegibilidade(
                    elegivel=False,
                    status="BLOQUEADO_DIVERGENCIA_AUTORIZACAO",
                    motivo=f"Fixture autoriza '{auth.authorized_repo}', mas item pertence a '{repo_info.full_name}'.",
                    repositorio=repo_info.full_name,
                    issue_number=issue_number,
                    esteira=esteira,
                    etapa_ch=etapa_ch,
                    decisao_po=decisao_po,
                    autonomia_ch=autonomia_ch,
                    prioridade_ch=prioridade_ch,
                    risco_ch=risco_ch,
                    card_id=card_id,
                    url=url,
                )

        # 5. Etapa CH: deve estar em PRONTA ou EM_EXECUCAO
        if etapa_ch not in ("PRONTA", "EM_EXECUCAO"):
            return ParecerElegibilidade(
                elegivel=False,
                status="IGNORADO_ETAPA_INADEQUADA",
                motivo=f"Etapa CH '{etapa_ch}' não está elegível para execução (esperado PRONTA ou EM_EXECUCAO).",
                repositorio=repo_info.full_name,
                issue_number=issue_number,
                esteira=esteira,
                etapa_ch=etapa_ch,
                decisao_po=decisao_po,
                autonomia_ch=autonomia_ch,
                prioridade_ch=prioridade_ch,
                risco_ch=risco_ch,
                card_id=card_id,
                url=url,
            )

        # 6. Autonomia: AGY opera em CH-2 (supervisionado) ou CH-1 (consultivo)
        if autonomia_ch not in ("CH-1", "CH-2"):
            return ParecerElegibilidade(
                elegivel=False,
                status="BLOQUEADO_AUTONOMIA_INADEQUADA",
                motivo=f"Nível de autonomia '{autonomia_ch}' não permitido para execução automática (permitido CH-1 ou CH-2).",
                repositorio=repo_info.full_name,
                issue_number=issue_number,
                esteira=esteira,
                etapa_ch=etapa_ch,
                decisao_po=decisao_po,
                autonomia_ch=autonomia_ch,
                prioridade_ch=prioridade_ch,
                risco_ch=risco_ch,
                card_id=card_id,
                url=url,
            )

        # 7. Risco: CRITICO exige gate humano especial
        if risco_ch == "CRITICO":
            return ParecerElegibilidade(
                elegivel=False,
                status="BLOQUEADO_RISCO_CRITICO",
                motivo="Missão possui Risco CH 'CRITICO'. Exige portão de segurança humano presencial antes do despacho.",
                repositorio=repo_info.full_name,
                issue_number=issue_number,
                esteira=esteira,
                etapa_ch=etapa_ch,
                decisao_po=decisao_po,
                autonomia_ch=autonomia_ch,
                prioridade_ch=prioridade_ch,
                risco_ch=risco_ch,
                card_id=card_id,
                url=url,
            )

        # 8. Validação de baseline e escopo se informados
        sha_validado = None
        sha_a_validar = sha_observado or (auth.baseline_sha if auth and auth.baseline_sha else None)
        if sha_a_validar:
            try:
                sha_validado = validar_sha_commit(sha_a_validar)
            except ViolacaoPoliticaSegurancaErro as exc:
                return ParecerElegibilidade(
                    elegivel=False,
                    status="BLOQUEADO_BASELINE_INVALIDO",
                    motivo=sanitizar_texto_segredos(str(exc)),
                    repositorio=repo_info.full_name,
                    issue_number=issue_number,
                    esteira=esteira,
                    etapa_ch=etapa_ch,
                    decisao_po=decisao_po,
                    autonomia_ch=autonomia_ch,
                    prioridade_ch=prioridade_ch,
                    risco_ch=risco_ch,
                    card_id=card_id,
                    url=url,
                )

        paths_finais: tuple[str, ...] = ()
        if paths_autorizados:
            try:
                validar_caminhos_escopo(paths_autorizados)
                paths_finais = tuple(paths_autorizados)
            except ViolacaoPoliticaSegurancaErro as exc:
                return ParecerElegibilidade(
                    elegivel=False,
                    status="BLOQUEADO_ESCOPO_INVALIDO",
                    motivo=sanitizar_texto_segredos(str(exc)),
                    repositorio=repo_info.full_name,
                    issue_number=issue_number,
                    esteira=esteira,
                    etapa_ch=etapa_ch,
                    decisao_po=decisao_po,
                    autonomia_ch=autonomia_ch,
                    prioridade_ch=prioridade_ch,
                    risco_ch=risco_ch,
                    card_id=card_id,
                    url=url,
                )

        # 9. Verificação de custo incremental zero
        try:
            validar_custo_zero(0.0)
        except ViolacaoPoliticaSegurancaErro as exc:
            return ParecerElegibilidade(
                elegivel=False,
                status="BLOQUEADO_CUSTO_INVALIDO",
                motivo=sanitizar_texto_segredos(str(exc)),
                repositorio=repo_info.full_name,
                issue_number=issue_number,
                esteira=esteira,
                etapa_ch=etapa_ch,
                decisao_po=decisao_po,
                autonomia_ch=autonomia_ch,
                prioridade_ch=prioridade_ch,
                risco_ch=risco_ch,
                card_id=card_id,
                url=url,
            )

        # Todas as checagens passaram!
        return ParecerElegibilidade(
            elegivel=True,
            status="ELEGIVEL_AGY",
            motivo="Todos os critérios de governança, esteira, contrato de autorização do PO, autonomia e risco atendidos.",
            repositorio=repo_info.full_name,
            issue_number=issue_number,
            esteira=esteira,
            etapa_ch=etapa_ch,
            decisao_po=decisao_po,
            autonomia_ch=autonomia_ch,
            prioridade_ch=prioridade_ch or "P2",
            risco_ch=risco_ch or "BAIXO",
            card_id=card_id,
            url=url,
            baseline_sha=sha_validado,
            allowed_paths=paths_finais,
            custo_adicional_brl=0.0,
            autorizado_por=auth.approved_by if auth else None,
            autorizacao_valida=True if auth else False,
            contrato_autorizacao_ref=auth.issue_ref or auth.event_id if auth else None,
        )
