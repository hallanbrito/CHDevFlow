"""Módulo de segurança para proteção contra CSRF, redirecionamento aberto e validação de origem.

Conformidade com AUD-02, AUD-02.1 e RNF-01:
- Validação estrita de cabeçalho Host (127.0.0.1 ou localhost na porta configurada).
- Validação rigorosa de protocolo, hostname e porta para Origin e Referer.
- Token CSRF local obrigatório como autoridade principal de segurança para requisições POST.
- Sanitização de URLs de redirecionamento, restringindo a caminhos locais conhecidos.
"""
from __future__ import annotations

import hmac
import os
import secrets
from urllib.parse import urlparse

from fastapi import HTTPException, Request

from ch_control_center.config import obter_porta_configurada

# Rotas locais canônicas autorizadas para navegação e redirecionamento
ROTAS_LOCAIS_AUTORIZADAS: tuple[str, ...] = (
    "/",
    "/missoes",
    "/grafo",
    "/estudante",
    "/health",
)

# Hosts permitidos para vinculação e cabeçalho HTTP
HOSTS_PERMITIDOS: frozenset[str] = frozenset({"127.0.0.1", "localhost"})

# Chave secreta de sessão efêmera gerada na inicialização do processo
_CHAVE_CSRF_LOCAL: str = os.getenv("CH_CC_SECRET_KEY", secrets.token_hex(32))


def obter_csrf_token() -> str:
    """Retorna o token CSRF válido para a sessão local atual."""
    return hmac.new(
        _CHAVE_CSRF_LOCAL.encode("utf-8"),
        b"chdevflow_csrf_v02",
        "sha256",
    ).hexdigest()


def validar_csrf_token(token: str | None) -> bool:
    """Valida um token CSRF fornecido contra o token local esperado."""
    if not token or not isinstance(token, str):
        return False
    esperado = obter_csrf_token()
    return hmac.compare_digest(token.strip(), esperado)


def validar_host_cabecalho(request: Request, porta_esperada: int | None = None) -> None:
    """Valida o cabeçalho Host da requisição HTTP (AUD-02.1).

    Permite estritamente '127.0.0.1' e 'localhost' na porta configurada.
    Rejeita domínios externos, coringas ou portas discrepantes com HTTP 403.
    """
    if porta_esperada is None:
        porta_esperada = obter_porta_configurada()

    host_header = request.headers.get("host")
    if not host_header:
        return

    if ":" in host_header:
        host_name, porta_str = host_header.split(":", 1)
        host_name = host_name.strip().lower()
        porta_str = porta_str.strip()
        if host_name not in HOSTS_PERMITIDOS:
            raise HTTPException(
                status_code=403,
                detail=f"Host externo rejeitado por segurança (AUD-02.1): {host_header}",
            )
        try:
            porta_int = int(porta_str)
            if porta_int != porta_esperada:
                raise HTTPException(
                    status_code=403,
                    detail=f"Porta do Host incompatível (AUD-02.1): {porta_int} != {porta_esperada}",
                )
        except ValueError:
            raise HTTPException(
                status_code=403,
                detail=f"Porta do Host malformada (AUD-02.1): {porta_str}",
            )
    else:
        host_name = host_header.strip().lower()
        if host_name not in HOSTS_PERMITIDOS:
            raise HTTPException(
                status_code=403,
                detail=f"Host externo rejeitado por segurança (AUD-02.1): {host_header}",
            )


def validar_origem_e_referer(request: Request, porta_esperada: int | None = None) -> None:
    """Valida protocolo, hostname e porta de Origin e Referer (AUD-02.1).

    Não considera apenas hostname como prova de mesma origem.
    Exige protocolo http/https, hostname 127.0.0.1/localhost e porta igual à configurada.
    """
    if porta_esperada is None:
        porta_esperada = obter_porta_configurada()

    origin = request.headers.get("origin")
    if origin:
        parsed = urlparse(origin)
        if parsed.scheme not in ("http", "https"):
            raise HTTPException(
                status_code=403,
                detail=f"Protocolo inválido em Origin (AUD-02.1): {parsed.scheme}",
            )
        if parsed.hostname not in HOSTS_PERMITIDOS:
            raise HTTPException(
                status_code=403,
                detail=f"Origem externa rejeitada por segurança (AUD-02.1): {origin}",
            )
        if parsed.port is not None and parsed.port != porta_esperada:
            raise HTTPException(
                status_code=403,
                detail=f"Porta de Origin incompatível (AUD-02.1): {parsed.port} != {porta_esperada}",
            )

    referer = request.headers.get("referer")
    if referer:
        parsed_ref = urlparse(referer)
        if parsed_ref.scheme not in ("http", "https"):
            raise HTTPException(
                status_code=403,
                detail=f"Protocolo inválido em Referer (AUD-02.1): {parsed_ref.scheme}",
            )
        if parsed_ref.hostname not in HOSTS_PERMITIDOS:
            raise HTTPException(
                status_code=403,
                detail=f"Referer externo rejeitado por segurança (AUD-02.1): {referer}",
            )
        if parsed_ref.port is not None and parsed_ref.port != porta_esperada:
            raise HTTPException(
                status_code=403,
                detail=f"Porta de Referer incompatível (AUD-02.1): {parsed_ref.port} != {porta_esperada}",
            )


def validar_requisicao_post_segura(request: Request, csrf_token: str | None = None) -> None:
    """Valida rigorosamente uma requisição POST de alteração de estado (AUD-02.1).

    1. Valida cabeçalho Host (estritamente 127.0.0.1 ou localhost na porta configurada).
    2. Valida Origin e Referer (protocolo, hostname e porta esperados).
    3. Exige obrigatoriamente token CSRF válido como autoridade principal de segurança.
    """
    # 1. Validação do Host
    validar_host_cabecalho(request)

    # 2. Validação de Origin e Referer
    validar_origem_e_referer(request)

    # 3. Exigência incondicional de Token CSRF válido
    if not validar_csrf_token(csrf_token):
        raise HTTPException(
            status_code=403,
            detail="Token CSRF inválido ou ausente (AUD-02.1).",
        )


def validar_origem_local(request: Request) -> None:
    """Validação legada de origem local (mantida para compatibilidade)."""
    validar_host_cabecalho(request)
    validar_origem_e_referer(request)


def sanitizar_caminho_redirecionamento(url_ou_caminho: str | None) -> str:
    """Valida e sanitiza o caminho de redirecionamento, aceitando estritamente rotas locais conhecidas.

    AUD-02:
    - Rejeita URLs com host externo.
    - Rejeita URLs relativas de protocolo (//evil.com).
    - Aceita somente rotas locais conhecidas ('/', '/missoes', '/grafo', '/estudante').
    - Caso contrário, redireciona seguramente para '/'.
    """
    if not url_ou_caminho:
        return "/"

    caminho = url_ou_caminho.strip()

    # Se for URL absoluta, extrai o path apenas se for host local
    if "://" in caminho:
        parsed = urlparse(caminho)
        if parsed.hostname not in HOSTS_PERMITIDOS:
            return "/"
        caminho = parsed.path or "/"

    # Proteção contra protocol-relative URLs (ex: //attacker.com)
    if caminho.startswith("//"):
        return "/"

    # Deve iniciar com barra única
    if not caminho.startswith("/"):
        return "/"

    # Extrai o caminho base antes de eventuais parâmetros de query
    path_base = caminho.split("?")[0].rstrip("/")
    if not path_base:
        path_base = "/"

    if path_base in ROTAS_LOCAIS_AUTORIZADAS:
        return caminho

    return "/"
