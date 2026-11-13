"""Registro explícito e seguro de repositórios autorizados para governança centralizada.

Implementa os requisitos de registro e contenção da missão CH-AUTO-MULTI-01:
- Apenas repositórios expressamente catalogados e confirmados pelo PO são elegíveis.
- O repositório hallanbrito/CHDevFlow atua como central canônica de governança.
- Todos os repositórios satélites (maestro-router, PulseOps, DriveHub-API,
  DriveHub-Web, VagaFlow, HallanCraft, MindFlip, perfil_profissional)
  são catalogados com suas características técnicas e políticas de contenção.
- Comportamento fail-closed: qualquer repositório não reconhecido é sumariamente recusado.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Mapping

from ch_sentinela.config import REPOSITORIO_CANONICO, REPOSITORIOS_PERMITIDOS
from ch_sentinela.security.policies import ViolacaoPoliticaSegurancaErro


@dataclass(frozen=True)
class RepositorioPermitido:
    """Metadados estruturados e imutáveis de um repositório autorizado."""

    slug: str
    full_name: str
    url: str
    is_canonical_governance: bool
    default_branch: str
    is_private: bool
    status: str  # "ATIVO", "INATIVO", "EM_VALIDACAO"
    description: str = ""

    def para_dicionario(self) -> dict[str, str | bool]:
        """Converte o registro para dicionário serializável."""
        return asdict(self)


# Cadastro canônico explícito validado contra a infraestrutura real do GitHub
_REPOSITORIOS_CATALOGO: dict[str, RepositorioPermitido] = {
    "hallanbrito/CHDevFlow": RepositorioPermitido(
        slug="CHDevFlow",
        full_name="hallanbrito/CHDevFlow",
        url="https://github.com/hallanbrito/CHDevFlow",
        is_canonical_governance=True,
        default_branch="main",
        is_private=False,
        status="ATIVO",
        description="Central canônica de governança, esteiras e auditoria C.H.",
    ),
    "hallanbrito/maestro-router": RepositorioPermitido(
        slug="maestro-router",
        full_name="hallanbrito/maestro-router",
        url="https://github.com/hallanbrito/maestro-router",
        is_canonical_governance=False,
        default_branch="main",
        is_private=False,
        status="ATIVO",
        description="Roteador e barramento de eventos Maestro.",
    ),
    "hallanbrito/PulseOps": RepositorioPermitido(
        slug="PulseOps",
        full_name="hallanbrito/PulseOps",
        url="https://github.com/hallanbrito/PulseOps",
        is_canonical_governance=False,
        default_branch="main",
        is_private=False,
        status="ATIVO",
        description="Monitoramento operacional e telemetria PulseOps.",
    ),
    "hallanbrito/DriveHub-API": RepositorioPermitido(
        slug="DriveHub-API",
        full_name="hallanbrito/DriveHub-API",
        url="https://github.com/hallanbrito/DriveHub-API",
        is_canonical_governance=False,
        default_branch="main",
        is_private=False,
        status="ATIVO",
        description="Backend API de serviços de mobilidade DriveHub.",
    ),
    "hallanbrito/DriveHub-Web": RepositorioPermitido(
        slug="DriveHub-Web",
        full_name="hallanbrito/DriveHub-Web",
        url="https://github.com/hallanbrito/DriveHub-Web",
        is_canonical_governance=False,
        default_branch="main",
        is_private=True,
        status="ATIVO",
        description="Frontend web do ecossistema DriveHub (repositório privado).",
    ),
    "hallanbrito/VagaFlow": RepositorioPermitido(
        slug="VagaFlow",
        full_name="hallanbrito/VagaFlow",
        url="https://github.com/hallanbrito/VagaFlow",
        is_canonical_governance=False,
        default_branch="main",
        is_private=False,
        status="ATIVO",
        description="Plataforma de gestão e matching de vagas VagaFlow.",
    ),
    "hallanbrito/HallanCraft": RepositorioPermitido(
        slug="HallanCraft",
        full_name="hallanbrito/HallanCraft",
        url="https://github.com/hallanbrito/HallanCraft",
        is_canonical_governance=False,
        default_branch="main",
        is_private=False,
        status="ATIVO",
        description="Repositório piloto para ensaios locais isolados.",
    ),
    "hallanbrito/MindFlip": RepositorioPermitido(
        slug="MindFlip",
        full_name="hallanbrito/MindFlip",
        url="https://github.com/hallanbrito/MindFlip",
        is_canonical_governance=False,
        default_branch="main",
        is_private=False,
        status="ATIVO",
        description="Aplicação de testes cognitivos e capacidade neural.",
    ),
    "hallanbrito/perfil_profissional": RepositorioPermitido(
        slug="perfil_profissional",
        full_name="hallanbrito/perfil_profissional",
        url="https://github.com/hallanbrito/perfil_profissional",
        is_canonical_governance=False,
        default_branch="main",
        is_private=False,
        status="ATIVO",
        description="Página de portfólio e perfil profissional.",
    ),
}

_URL_PATTERN = re.compile(
    r"^https?://github\.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?/?$"
)


def normalizar_identificador_repositorio(identificador: str) -> str:
    """Normaliza URLs do GitHub, nomes completos 'owner/repo' ou slugs para o formato canônico.

    Args:
        identificador: URL (https://github.com/owner/repo), owner/repo ou slug.

    Returns:
        String no formato canônico 'owner/repo'.
    """
    if not isinstance(identificador, str) or not identificador.strip():
        raise ViolacaoPoliticaSegurancaErro("Identificador de repositório vazio ou inválido.")

    limpo = identificador.strip()
    match_url = _URL_PATTERN.match(limpo)
    if match_url:
        return match_url.group(1)

    # Se for no formato owner/repo
    if "/" in limpo:
        partes = limpo.split("/")
        if len(partes) == 2 and partes[0] and partes[1]:
            return f"{partes[0].strip()}/{partes[1].strip()}"

    # Se for apenas slug, busca no catálogo
    for repo in _REPOSITORIOS_CATALOGO.values():
        if repo.slug.lower() == limpo.lower():
            return repo.full_name

    return limpo


def obter_repositorio(identificador: str) -> RepositorioPermitido | None:
    """Consulta o repositório pelo identificador ou retorna None se não cadastrado.

    Args:
        identificador: Nome completo ('hallanbrito/CHDevFlow'), URL ou slug.
    """
    try:
        nome_normalizado = normalizar_identificador_repositorio(identificador)
    except ViolacaoPoliticaSegurancaErro:
        return None

    # Busca exata ou por insensibilidade a maiúsculas/minúsculas
    for chave, repo in _REPOSITORIOS_CATALOGO.items():
        if chave.lower() == nome_normalizado.lower():
            return repo

    return None


def validar_repositorio_autorizado(identificador: str) -> RepositorioPermitido:
    """Valida se o repositório pertence à lista restrita de repositórios autorizados.

    Fail-closed: Se o repositório não estiver cadastrado com status ATIVO,
    lança ViolacaoPoliticaSegurancaErro impedindo qualquer processamento.

    Args:
        identificador: Nome completo, URL ou slug do repositório.

    Returns:
        Instância validada de RepositorioPermitido.

    Raises:
        ViolacaoPoliticaSegurancaErro: Se o repositório não for autorizado ou estiver inativo.
    """
    repo = obter_repositorio(identificador)
    if repo is None:
        raise ViolacaoPoliticaSegurancaErro(
            f"Repositório '{identificador}' NÃO AUTORIZADO! "
            f"Apenas repositórios registrados pelo PO no catálogo C.H. são permitidos."
        )

    if repo.status != "ATIVO":
        raise ViolacaoPoliticaSegurancaErro(
            f"Repositório '{repo.full_name}' está com status '{repo.status}'. "
            f"Operações estão suspensas até regularização explícita do PO."
        )

    return repo


def listar_repositorios_permitidos() -> tuple[RepositorioPermitido, ...]:
    """Retorna a lista completa de repositórios permitidos pelo catálogo."""
    return tuple(_REPOSITORIOS_CATALOGO.values())


def listar_repositorios_ativos() -> tuple[RepositorioPermitido, ...]:
    """Retorna exclusivamente os repositórios em estado ATIVO."""
    return tuple(r for r in _REPOSITORIOS_CATALOGO.values() if r.status == "ATIVO")


def obter_repositorio_canonico() -> RepositorioPermitido:
    """Retorna o registro do repositório canônico de governança (CHDevFlow)."""
    repo = _REPOSITORIOS_CATALOGO.get(REPOSITORIO_CANONICO)
    if repo is None or not repo.is_canonical_governance:
        raise RuntimeError("Configuração corrompida: repositório canônico não encontrado.")
    return repo
