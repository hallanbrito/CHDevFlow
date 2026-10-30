"""Leitor de consultas seguras e somente-leitura ao GitHub via CLI `gh`.

Este módulo é estritamente passivo (read-only):
- Nunca executa mutações (sem item-edit, create, close, merge, etc.).
- Comunica-se exclusivamente com repositórios e projetos autorizados.
- Suporta execução offline via injeção de provedor de dados / fixtures.
- Usa subprocess com lista de argumentos (shell=False) e sanitização de saída.
"""
from __future__ import annotations

import json
import re
import subprocess
from typing import Any, Callable

from ch_sentinela.config import (
    MAXIMO_ITEMS_PROJECT,
    NUMERO_PROJETO_PADRAO,
    PROPRIETARIO_PADRAO,
    REPOSITORIO_CANONICO,
    REPOSITORIOS_PERMITIDOS,
)
from ch_sentinela.security.policies import (
    ViolacaoPoliticaSegurancaErro,
    sanitizar_texto_segredos,
)

# Subcomandos gh explicitamente proibidos para garantir imutabilidade estrita
SUBCOMANDOS_MUTAVEIS_PROIBIDOS: tuple[str, ...] = (
    "create",
    "edit",
    "close",
    "reopen",
    "delete",
    "merge",
    "comment",
    "item-edit",
    "item-create",
    "item-delete",
    "item-archive",
    "field-create",
    "field-delete",
    "push",
    "apply",
    "--apply",
    "--apply-plan",
)


class LeitorGitHubErro(RuntimeError):
    """Exceção levantada quando ocorre erro de comunicação, timeout ou formato com o GitHub."""


def executar_comando_gh(
    argumentos: list[str],
    timeout_segundos: int = 30,
    executor_customizado: Callable[[list[str]], str] | None = None,
) -> str:
    """Executa o comando `gh` de forma segura com lista de argumentos e sem shell.

    Sanitiza mensagens de erro para evitar vazamento acidental de tokens em stderr.

    Args:
        argumentos: Lista de argumentos passados ao executável `gh`.
        timeout_segundos: Tempo limite para retorno do processo.
        executor_customizado: Função alternativa para execução (usada para testes offline).

    Returns:
        Saída padrão (stdout) limpa do comando.

    Raises:
        ViolacaoPoliticaSegurancaErro: Se for detectada tentativa de mutação.
        LeitorGitHubErro: Se o comando falhar, expirar ou retornar erro de rede.
    """
    # 1. Defesa em profundidade: bloqueia qualquer argumento mutável
    for arg in argumentos:
        arg_limpo = arg.strip().lower()
        if arg_limpo in SUBCOMANDOS_MUTAVEIS_PROIBIDOS:
            raise ViolacaoPoliticaSegurancaErro(
                f"Tentativa de operação mutável bloqueada: argumento proibido '{arg}'."
            )

    # 2. Se houver executor customizado (ex: modo offline ou testes unitários)
    if executor_customizado is not None:
        try:
            return executor_customizado(argumentos)
        except Exception as exc:
            erro_sanitizado = sanitizar_texto_segredos(str(exc))
            raise LeitorGitHubErro(f"Falha na consulta ao GitHub CLI: {erro_sanitizado}") from exc

    # 3. Execução real do processo no host com subprocess.run
    comando = ["gh", *argumentos]
    try:
        resultado = subprocess.run(
            comando,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_segundos,
        )
    except FileNotFoundError as exc:
        raise LeitorGitHubErro(
            "GitHub CLI (`gh`) não encontrada no host. Para modo offline, utilize fixtures."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise LeitorGitHubErro(
            f"Timeout de {timeout_segundos}s excedido ao consultar o GitHub CLI."
        ) from exc
    except Exception as exc:
        raise LeitorGitHubErro(f"Erro inesperado ao invocar GitHub CLI: {exc}") from exc

    if resultado.returncode != 0:
        erro_sanitizado = sanitizar_texto_segredos(resultado.stderr or resultado.stdout)
        raise LeitorGitHubErro(f"Falha na consulta ao GitHub CLI: {erro_sanitizado.strip()}")

    return resultado.stdout


def executar_consulta_json(
    argumentos: list[str],
    executor_customizado: Callable[[list[str]], str] | None = None,
) -> dict[str, Any]:
    """Executa uma consulta gh e converte a resposta para dicionário JSON validado.

    Args:
        argumentos: Lista de argumentos do comando.
        executor_customizado: Provedor alternativo para testes.

    Returns:
        Dicionário com o payload JSON decodificado.

    Raises:
        LeitorGitHubErro: Se a saída não for JSON válido ou não for um objeto.
    """
    saida_bruta = executar_comando_gh(argumentos, executor_customizado=executor_customizado)
    try:
        dados = json.loads(saida_bruta)
    except json.JSONDecodeError as exc:
        raise LeitorGitHubErro("Resposta do GitHub CLI não é um JSON válido.") from exc

    if not isinstance(dados, dict):
        raise LeitorGitHubErro(f"Formato JSON inesperado do GitHub CLI: esperado objeto, obtido {type(dados).__name__}.")

    return dados


def validar_snapshot_projeto(dados: Any) -> None:
    """Valida a integridade estrutural e limites de um snapshot do GitHub Project.

    Garante que o snapshot contenha um dicionário com:
    - 'items': lista de itens
    - 'totalCount': inteiro não-negativo exatamente igual a len(items)
    - totalCount <= MAXIMO_ITEMS_PROJECT

    Args:
        dados: Objeto a ser validado como snapshot do Project.

    Raises:
        LeitorGitHubErro: Se a estrutura for inválida, incompleta ou violar limites operacionais.
    """
    if not isinstance(dados, dict):
        raise LeitorGitHubErro(
            f"Snapshot do Project inválido: esperado objeto JSON (dict), obtido {type(dados).__name__}."
        )

    if "items" not in dados:
        raise LeitorGitHubErro("Snapshot do Project inválido: campo 'items' ausente.")

    itens = dados["items"]
    if not isinstance(itens, list):
        raise LeitorGitHubErro(
            f"Snapshot do Project inválido: campo 'items' deve ser uma lista, obtido {type(itens).__name__}."
        )

    if "totalCount" not in dados:
        raise LeitorGitHubErro("Snapshot do Project inválido: campo 'totalCount' ausente.")

    total_count = dados["totalCount"]
    # Em Python, bool é subclasse de int. Rejeitar explicitamente bool.
    if isinstance(total_count, bool) or not isinstance(total_count, int):
        raise LeitorGitHubErro(
            f"Snapshot do Project inválido: campo 'totalCount' deve ser um inteiro, obtido {type(total_count).__name__}."
        )

    if total_count < 0:
        raise LeitorGitHubErro(
            f"Snapshot do Project inválido: campo 'totalCount' não pode ser negativo ({total_count})."
        )

    if len(itens) != total_count:
        raise LeitorGitHubErro(
            f"Project incompleto: 'items' ({len(itens)}) difere de 'totalCount' ({total_count})."
        )

    if total_count > MAXIMO_ITEMS_PROJECT:
        raise LeitorGitHubErro(
            f"Project excede limite seguro de leitura: {total_count} > {MAXIMO_ITEMS_PROJECT}."
        )


def validar_campos_projeto(dados: Any) -> None:
    """Valida a integridade estrutural e limites da lista de campos do GitHub Project.

    Garante que o dicionário contenha:
    - 'fields': lista de campos do Project V2
    - 'totalCount': inteiro não-negativo exatamente igual a len(fields)

    Args:
        dados: Objeto a ser validado como resposta de campos do Project.

    Raises:
        LeitorGitHubErro: Se a estrutura for inválida, incompleta ou com tipos inesperados.
    """
    if not isinstance(dados, dict):
        raise LeitorGitHubErro(
            f"Campos do Project inválidos: esperado objeto JSON (dict), obtido {type(dados).__name__}."
        )

    if "fields" not in dados:
        raise LeitorGitHubErro("Campos do Project inválidos: campo 'fields' ausente.")

    campos = dados["fields"]
    if not isinstance(campos, list):
        raise LeitorGitHubErro(
            f"Campos do Project inválidos: campo 'fields' deve ser uma lista, obtido {type(campos).__name__}."
        )

    if "totalCount" not in dados:
        raise LeitorGitHubErro("Campos do Project inválidos: campo 'totalCount' ausente.")

    total_count = dados["totalCount"]
    if isinstance(total_count, bool) or not isinstance(total_count, int):
        raise LeitorGitHubErro(
            f"Campos do Project inválidos: campo 'totalCount' deve ser um inteiro, obtido {type(total_count).__name__}."
        )

    if total_count < 0:
        raise LeitorGitHubErro(
            f"Campos do Project inválidos: campo 'totalCount' não pode ser negativo ({total_count})."
        )

    if len(campos) != total_count:
        raise LeitorGitHubErro(
            f"Campos do Project incompletos: 'fields' ({len(campos)}) difere de 'totalCount' ({total_count})."
        )


class LeitorGitHub:
    """Interface de leitura restrita e somente-leitura para o GitHub."""

    def __init__(
        self,
        repositorio_padrao: str = REPOSITORIO_CANONICO,
        executor_customizado: Callable[[list[str]], str] | None = None,
    ) -> None:
        """Inicializa o leitor.

        Args:
            repositorio_padrao: Repositório canônico padrão.
            executor_customizado: Função para mockar consultas em testes offline.
        """
        if repositorio_padrao not in REPOSITORIOS_PERMITIDOS:
            raise ViolacaoPoliticaSegurancaErro(
                f"Repositório '{repositorio_padrao}' não autorizado para LeitorGitHub."
            )
        self.repositorio = repositorio_padrao
        self._executor = executor_customizado

    def obter_issue(self, numero_issue: int, repositorio: str | None = None) -> dict[str, Any]:
        """Consulta os dados estruturados de uma Issue.

        Args:
            numero_issue: Número inteiro positivo da Issue.
            repositorio: Repositório a consultar (deve estar na lista de permitidos).

        Returns:
            Dicionário com campos selecionados da Issue.

        Raises:
            ViolacaoPoliticaSegurancaErro: Se o repositório ou ID for inválido.
            LeitorGitHubErro: Em caso de falha de leitura.
        """
        repo = repositorio or self.repositorio
        if repo not in REPOSITORIOS_PERMITIDOS:
            raise ViolacaoPoliticaSegurancaErro(f"Repositório não autorizado: '{repo}'.")

        if not isinstance(numero_issue, int) or numero_issue <= 0:
            raise ViolacaoPoliticaSegurancaErro(f"Número de Issue inválido: {numero_issue}.")

        args = [
            "issue",
            "view",
            str(numero_issue),
            "--repo",
            repo,
            "--json",
            "number,title,body,state,labels,url,author,updatedAt,comments",
        ]
        dados = executar_consulta_json(args, executor_customizado=self._executor)

        # Validação de integridade básica
        if dados.get("number") != numero_issue:
            raise LeitorGitHubErro(f"Número da Issue na resposta ({dados.get('number')}) difere do consultado ({numero_issue}).")

        url_esperada = f"https://github.com/{repo}/issues/{numero_issue}"
        if dados.get("url") != url_esperada:
            raise LeitorGitHubErro(f"URL da Issue incompatível: '{dados.get('url')}'. Esperado '{url_esperada}'.")

        return dados

    def obter_pull_request(self, numero_pr: int, repositorio: str | None = None) -> dict[str, Any]:
        """Consulta os dados estruturados de um Pull Request.

        Args:
            numero_pr: Número inteiro positivo do PR.
            repositorio: Repositório autorizado.

        Returns:
            Dicionário com campos selecionados do PR.
        """
        repo = repositorio or self.repositorio
        if repo not in REPOSITORIOS_PERMITIDOS:
            raise ViolacaoPoliticaSegurancaErro(f"Repositório não autorizado: '{repo}'.")

        if not isinstance(numero_pr, int) or numero_pr <= 0:
            raise ViolacaoPoliticaSegurancaErro(f"Número de PR inválido: {numero_pr}.")

        args = [
            "pr",
            "view",
            str(numero_pr),
            "--repo",
            repo,
            "--json",
            "number,title,state,isDraft,headRefName,baseRefName,headRefOid,url",
        ]
        dados = executar_consulta_json(args, executor_customizado=self._executor)

        if dados.get("number") != numero_pr:
            raise LeitorGitHubErro(f"Número do PR na resposta ({dados.get('number')}) difere do consultado ({numero_pr}).")

        return dados

    def listar_itens_projeto(
        self,
        numero_projeto: int = NUMERO_PROJETO_PADRAO,
        proprietario: str = PROPRIETARIO_PADRAO,
    ) -> dict[str, Any]:
        """Consulta os itens do GitHub Project com validação estrita de integridade.

        Args:
            numero_projeto: Número do projeto (padrão: 2).
            proprietario: Usuário ou organização proprietária (padrão: 'hallanbrito').

        Returns:
            Dicionário com a lista de itens e totalCount validado.

        Raises:
            LeitorGitHubErro: Se o projeto estiver incompleto ou exceder os limites.
        """
        if numero_projeto != NUMERO_PROJETO_PADRAO:
            raise ViolacaoPoliticaSegurancaErro(
                f"Número de Projeto {numero_projeto} não autorizado. Permitido: {NUMERO_PROJETO_PADRAO}."
            )

        args = [
            "project",
            "item-list",
            str(numero_projeto),
            "--owner",
            proprietario,
            "--format",
            "json",
            "-L",
            str(MAXIMO_ITEMS_PROJECT),
        ]
        dados = executar_consulta_json(args, executor_customizado=self._executor)
        validar_snapshot_projeto(dados)
        return dados

    def listar_campos_projeto(
        self,
        numero_projeto: int = NUMERO_PROJETO_PADRAO,
        proprietario: str = PROPRIETARIO_PADRAO,
    ) -> dict[str, Any]:
        """Consulta os campos do GitHub Project com validação estrutural.

        Args:
            numero_projeto: Número do projeto (padrão: 2).
            proprietario: Usuário ou organização proprietária (padrão: 'hallanbrito').

        Returns:
            Dicionário com a lista de campos e totalCount validado.

        Raises:
            ViolacaoPoliticaSegurancaErro: Se o número do projeto não for autorizado.
            LeitorGitHubErro: Se a consulta falhar ou a estrutura for inválida.
        """
        if numero_projeto != NUMERO_PROJETO_PADRAO:
            raise ViolacaoPoliticaSegurancaErro(
                f"Número de Projeto {numero_projeto} não autorizado. Permitido: {NUMERO_PROJETO_PADRAO}."
            )

        args = [
            "project",
            "field-list",
            str(numero_projeto),
            "--owner",
            proprietario,
            "--format",
            "json",
        ]
        dados = executar_consulta_json(args, executor_customizado=self._executor)
        validar_campos_projeto(dados)
        return dados

