"""Módulo de segurança para proteção contra CSRF, redirecionamento aberto e validação de origem.

Conformidade com AUD-02 e RNF-01:
- Validação estrita de cabeçalhos Origin e Referer contra origens externas.
- Token CSRF local para formulários POST.
- Sanitização de URLs de redirecionamento, restringindo a caminhos locais conhecidos.
"""
from __future__ import annotations

import hmac
import os
import secrets
from urllib.parse import urlparse

from fastapi import HTTPException, Request

# Rotas locais canônicas autorizadas para navegação e redirecionamento
ROTAS_LOCAIS_AUTORIZADAS: tuple[str, ...] = (
    "/",
    "/missoes",
    "/grafo",
    "/estudante",
    "/health",
)

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


def validar_origem_local(request: Request) -> None:
    """Valida que a requisição provém estritamente de host local (127.0.0.1 ou localhost).

    AUD-02:
    - Se houver 'Origin', deve ser 127.0.0.1 ou localhost.
    - Se houver 'Referer', deve ser 127.0.0.1 ou localhost.
    - Se ambos estiverem ausentes, exige token CSRF válido.

    Raises:
        HTTPException(403): Se a origem ou referer for externo, malformado ou ausente sem CSRF.
    """
    origin = request.headers.get("origin")
    referer = request.headers.get("referer")

    origens_permitidas = {"127.0.0.1", "localhost"}

    # 1. Se Origin está presente, valida rigorosamente
    if origin:
        parsed_origin = urlparse(origin)
        if parsed_origin.hostname not in origens_permitidas:
            raise HTTPException(
                status_code=403,
                detail=f"Origem externa rejeitada por segurança (AUD-02): {origin}",
            )

    # 2. Se Referer está presente, valida rigorosamente
    if referer:
        parsed_referer = urlparse(referer)
        if parsed_referer.hostname not in origens_permitidas:
            raise HTTPException(
                status_code=403,
                detail=f"Referer externo rejeitado por segurança (AUD-02): {referer}",
            )

    # 3. Se ambos estiverem ausentes, requer verificação adicional
    if not origin and not referer:
        # Requer token CSRF na query ou cabeçalho se nenhum cabeçalho de origem foi fornecido
        csrf_header = request.headers.get("x-csrf-token") or request.query_params.get("csrf_token")
        if not validar_csrf_token(csrf_header):
            raise HTTPException(
                status_code=403,
                detail="Requisição POST sem origem identificada ou token CSRF (AUD-02).",
            )


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
        if parsed.hostname not in ("127.0.0.1", "localhost"):
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
