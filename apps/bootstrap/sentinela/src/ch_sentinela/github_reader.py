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

        itens = dados.get("items")
        total_count = dados.get("totalCount")

        if not isinstance(itens, list) or not isinstance(total_count, int):
            raise LeitorGitHubErro("Estrutura inválida no retorno do Project: 'items' ou 'totalCount' ausentes.")

        if len(itens) != total_count:
            raise LeitorGitHubErro(
                f"Project incompleto: 'items' ({len(itens)}) difere de 'totalCount' ({total_count})."
            )

        if total_count > MAXIMO_ITEMS_PROJECT:
            raise LeitorGitHubErro(
                f"Project excede limite seguro de leitura: {total_count} > {MAXIMO_ITEMS_PROJECT}."
            )

        return dados
