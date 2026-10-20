"""Políticas de segurança, contenção e validação do Método C.H.

Este módulo implementa verificações de falha fechada (fail-closed) para garantir
que nenhuma operação fora do escopo, sem autorização ou com risco de vazamento
possa ser disparada.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ch_sentinela.config import (
    CUSTO_ADICIONAL_PERMITIDO_BRL,
    LIMITE_TEMPO_EXECUCAO_SEGUNDOS,
    MAXIMO_EXECUCOES_ATIVAS,
    MAXIMO_TENTATIVAS_RETRY,
    PO_IDENTIDADE_PADRAO,
)

# Expressão regular para validar SHAs completos de 40 caracteres hexadecimais
PADRAO_SHA40 = re.compile(r"^[0-9a-f]{40}$", re.IGNORECASE)

# Expressões regulares para redação de segredos e credenciais conhecidas
PADROES_SEGREDOS: list[re.Pattern[str]] = [
    re.compile(r"\b(?:gh[opusr]_|github_pat_)[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bAIza[0-9A-Za-z-_]{35}\b"),  # Chaves Google API
    re.compile(r"-----BEGIN [A-Z ]+ PRIVATE KEY-----.*?-----END [A-Z ]+ PRIVATE KEY-----", re.DOTALL),
    re.compile(r"(?i)(?:password|token|secret|senha)\s*[:=]\s*['\"][^'\"]+['\"]"),
]

# Padrões de caminhos estritamente proibidos (defesa em profundidade)
PADROES_CAMINHOS_BLOQUEADOS_OBRIGATORIOS: tuple[str, ...] = (
    "worlds",
    "saves",
    ".env",
    "secrets",
    ".git",
    ".ssh",
    "/etc",
    "/root",
    "id_rsa",
    "id_ed25519",
    "token",
    "credential",
    "credentials",
)

# Nomes de agentes e entidades que NUNCA podem ser autores de autorização
AGENTES_PROIBIDOS_COMO_AUTORIZADOR: tuple[str, ...] = (
    "codex",
    "agy",
    "antigravity",
    "gemini",
    "chatgpt",
    "github-actions",
    "bot",
    "fake",
)


class ViolacaoPoliticaSegurancaErro(ValueError):
    """Exceção levantada quando uma regra de segurança ou contenção é violada.

    Indica que a operação foi interrompida preventivamente em modo fail-closed.
    """


def validar_sha_commit(sha: str) -> str:
    """Valida se o SHA de commit fornecido é um hash hexadecimal completo de 40 caracteres.

    Não aceita SHAs curtos (7 caracteres), nulos ou genéricos, para evitar
    ambiguidade no baseline da missão.

    Args:
        sha: String contendo o SHA a verificar.

    Returns:
        O SHA em formato minúsculo e validado.

    Raises:
        ViolacaoPoliticaSegurancaErro: Se o SHA for inválido ou não tiver 40 caracteres hex.
    """
    if not isinstance(sha, str) or not PADRAO_SHA40.match(sha.strip()):
        raise ViolacaoPoliticaSegurancaErro(
            f"SHA de baseline inválido: '{sha}'. Deve ser um hash hexadecimal completo de 40 caracteres."
        )
    return sha.strip().lower()


def validar_caminhos_escopo(
    caminhos_permitidos: list[str],
    caminhos_bloqueados: list[str] | None = None,
) -> None:
    """Valida se os caminhos de escopo estão bem delimitados e seguros.

    Aplica as seguintes regras de segurança:
    1. A lista de caminhos permitidos não pode ser vazia.
    2. Proíbe curingas amplos como '*' ou '**' que liberem o repositório inteiro.
    3. Proíbe sequências de fuga de diretório ('..').
    4. Proíbe caminhos que toquem dados sensíveis conhecidos (mundos, saves, segredos).

    Args:
        caminhos_permitidos: Lista de caminhos relativos autorizados para edição.
        caminhos_bloqueados: Lista adicional de padrões proibidos.

    Raises:
        ViolacaoPoliticaSegurancaErro: Se qualquer caminho violar as restrições de escopo.
    """
    if not isinstance(caminhos_permitidos, list) or not caminhos_permitidos:
        raise ViolacaoPoliticaSegurancaErro(
            "Escopo inválido: 'allowed_paths' deve ser uma lista não vazia de caminhos explícitos."
        )

    todos_bloqueados = set(PADROES_CAMINHOS_BLOQUEADOS_OBRIGATORIOS)
    if caminhos_bloqueados and isinstance(caminhos_bloqueados, list):
        for b in caminhos_bloqueados:
            if isinstance(b, str):
                todos_bloqueados.add(b.strip().lower())

    for caminho in caminhos_permitidos:
        if not isinstance(caminho, str) or not caminho.strip():
            raise ViolacaoPoliticaSegurancaErro("Caminho no escopo não pode ser vazio ou não-texto.")

        caminho_limpo = caminho.strip().replace("\\", "/")

        # Bloqueia curingas genéricos perigosos
        if caminho_limpo in ("*", "**", ".", "/", "./"):
            raise ViolacaoPoliticaSegurancaErro(
                f"Caminho genérico '{caminho_limpo}' proibido: o escopo deve ser estritamente delimitado."
            )

        # Bloqueia subida de diretórios (path traversal)
        if ".." in caminho_limpo.split("/"):
            raise ViolacaoPoliticaSegurancaErro(
                f"Tentativa de fuga de diretório (path traversal) detectada no caminho '{caminho}'."
            )

        # Bloqueia caminhos absolutos do sistema operacional
        if caminho_limpo.startswith("/"):
            raise ViolacaoPoliticaSegurancaErro(
                f"Caminho absoluto '{caminho}' proibido: somente caminhos relativos ao repositório são válidos."
            )

        # Verifica colisão com padrões proibidos
        caminho_baixo = caminho_limpo.lower()
        for padrao_bloqueado in todos_bloqueados:
            padrao_limpo = padrao_bloqueado.replace("*", "").strip("/").lower()
            if padrao_limpo and padrao_limpo in caminho_baixo:
                raise ViolacaoPoliticaSegurancaErro(
                    f"Caminho '{caminho}' viola a política de bloqueio para '{padrao_bloqueado}'."
                )


def validar_custo_zero(custo_declarado: Any) -> None:
    """Verifica se o custo adicional declarado é estritamente R$ 0,00.

    Conforme Decisão D06, qualquer operação com custo potencial, serviço pago
    ou valor indefinido deve falhar preventivamente.

    Args:
        custo_declarado: Valor monetário informado.

    Raises:
        ViolacaoPoliticaSegurancaErro: Se o custo for maior que zero ou não for numérico.
    """
    if not isinstance(custo_declarado, (int, float)):
        raise ViolacaoPoliticaSegurancaErro(
            f"Valor de custo adicional inválido: '{custo_declarado}'. Esperado número zero."
        )
    if custo_declarado > CUSTO_ADICIONAL_PERMITIDO_BRL:
        raise ViolacaoPoliticaSegurancaErro(
            f"Custo adicional proibido: R$ {custo_declarado:.2f}. "
            f"Apenas operações com custo R$ {CUSTO_ADICIONAL_PERMITIDO_BRL:.2f} são permitidas."
        )


def validar_limites_recurso(limites: dict[str, Any]) -> None:
    """Valida se os limites operacionais respeitam os tetos do Método C.H. (D06).

    Args:
        limites: Dicionário contendo as configurações de limite da missão.

    Raises:
        ViolacaoPoliticaSegurancaErro: Se algum limite exceder as regras aprovadas.
    """
    if not isinstance(limites, dict):
        raise ViolacaoPoliticaSegurancaErro("Bloco de limites deve ser um dicionário estruturado.")

    # Concorrência estrita: apenas 1 execução ativa
    max_parallel = limites.get("max_parallel", 1)
    if max_parallel != MAXIMO_EXECUCOES_ATIVAS:
        raise ViolacaoPoliticaSegurancaErro(
            f"Concorrência 'max_parallel'={max_parallel} inválida. Permitido exclusivamente {MAXIMO_EXECUCOES_ATIVAS}."
        )

    # Tempo máximo de execução por tentativa: até 900 segundos
    timeout = limites.get("timeout_seconds", LIMITE_TEMPO_EXECUCAO_SEGUNDOS)
    if not isinstance(timeout, int) or timeout <= 0 or timeout > LIMITE_TEMPO_EXECUCAO_SEGUNDOS:
        raise ViolacaoPoliticaSegurancaErro(
            f"Timeout de {timeout}s inválido. Limite máximo permitido é {LIMITE_TEMPO_EXECUCAO_SEGUNDOS}s."
        )

    # Máximo de tentativas de repetição após diagnóstico
    retries = limites.get("max_retries_after_diagnosis", 0)
    if not isinstance(retries, int) or retries < 0 or retries > MAXIMO_TENTATIVAS_RETRY:
        raise ViolacaoPoliticaSegurancaErro(
            f"Tentativas de retry={retries} inválidas. Permitido no máximo {MAXIMO_TENTATIVAS_RETRY} após diagnóstico."
        )


def validar_origem_autorizacao(
    aprovado_por: str,
    evento_id: str,
    contexto_simulacao: bool = False,
) -> None:
    """Verifica a autenticidade e validade da aprovação da missão.

    Princípios:
    - Um agente jamais pode aprovar a si mesmo (Codex, AGY, ChatGPT, etc.).
    - Rótulo, coluna de Kanban ou texto livre na Issue NÃO configuram autorização.
    - Em ambiente de produção real, apenas uma autorização do PO humano é válida.
    - Em testes locais, somente fixtures explicitamente marcadas com
      'contexto_simulacao=True' podem simular aprovação do PO.

    Args:
        aprovado_por: Identificador do usuário que emitiu a aprovação.
        evento_id: Identificador verificável do evento de aprovação no GitHub.
        contexto_simulacao: Indicador de que a execução é um teste sintético isolado.

    Raises:
        ViolacaoPoliticaSegurancaErro: Se a aprovação for ilegítima, de agente ou vazia.
    """
    if not aprovado_por or not isinstance(aprovado_por, str):
        raise ViolacaoPoliticaSegurancaErro("Autorização rejeitada: 'approved_by' ausente ou inválido.")

    aprovador_normalizado = aprovado_por.strip().lower()

    # Rejeita autoaprovação de qualquer agente ou bot
    for agente in AGENTES_PROIBIDOS_COMO_AUTORIZADOR:
        if agente in aprovador_normalizado:
            raise ViolacaoPoliticaSegurancaErro(
                f"Tentativa de autoaprovação rejeitada: agente ou bot '{aprovado_por}' não pode autorizar missões."
            )

    # Valida presença de referência ao evento de aprovação
    if not evento_id or not isinstance(evento_id, str) or not evento_id.strip():
        raise ViolacaoPoliticaSegurancaErro(
            "Autorização rejeitada: 'approval_event_id' deve referenciar um evento imutável."
        )

    # Em execução real (não-simulada), a aprovação deve pertencer ao PO e não pode ser forjada
    if not contexto_simulacao:
        if aprovador_normalizado != PO_IDENTIDADE_PADRAO.lower():
            raise ViolacaoPoliticaSegurancaErro(
                f"Autorização negada: '{aprovado_por}' não é o Product Owner autorizado ({PO_IDENTIDADE_PADRAO})."
            )


def sanitizar_texto_segredos(texto: str) -> str:
    """Remove e mascara tokens, senhas ou credenciais conhecidas de qualquer texto ou log.

    Evita que tokens do GitHub, chaves de API ou certificados privados
    apareçam em arquivos de auditoria, mensagens ou telas do terminal.

    Args:
        texto: Texto original potencialmente contendo dados sensíveis.

    Returns:
        Texto sanitizado com segredos substituídos por '[CREDENCIAL_OCULTADA]'.
    """
    if not texto or not isinstance(texto, str):
        return ""

    resultado = texto
    for padrao in PADROES_SEGREDOS:
        resultado = padrao.sub("[CREDENCIAL_OCULTADA]", resultado)

    return resultado
