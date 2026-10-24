"""Integração da Sentinela Python ao CHDevFlow CLI (`ch watch`)."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys


class WatchSecurityError(PermissionError):
    """Erro caso seja solicitada execução contínua ou não autorizada pela D05."""
    pass


def _ensure_sentinela_path() -> None:
    """Localiza e adiciona o pacote ch_sentinela ao sys.path se necessário."""
    try:
        import ch_sentinela
        return
    except ImportError:
        pass

    # Tenta localizar apps/bootstrap/sentinela/src
    candidates = [
        Path(__file__).resolve().parents[3] / "apps" / "bootstrap" / "sentinela" / "src",
        Path.cwd() / "apps" / "bootstrap" / "sentinela" / "src",
    ]
    for c in candidates:
        if c.is_dir() and str(c) not in sys.path:
            sys.path.insert(0, str(c))
            try:
                import ch_sentinela
                return
            except ImportError:
                continue

    raise ModuleNotFoundError(
        "Módulo 'ch_sentinela' não encontrado. Verifique se 'apps/bootstrap/sentinela/src' está presente."
    )


def run_watch(once: bool = False, dry_run: bool = False, fixture: str | None = None) -> int:
    """
    Executa a observação pontual da Sentinela.
    Preserva rigorosamente a Decisão D05: execução contínua / daemons são proibidos na v0.1.
    """
    if not once:
        raise WatchSecurityError(
            "Modo contínuo/daemon não autorizado na v0.1 (Decisão D05). "
            "Especifique obrigatoriamente a flag '--once' (ex.: 'ch watch --once --dry-run')."
        )

    _ensure_sentinela_path()
    from ch_sentinela.cli import comando_watch

    # Prepara namespace de argumentos esperado pelo comando_watch da Sentinela
    args = argparse.Namespace(
        once=once,
        dry_run=dry_run,
        fixture=fixture,
    )
    return comando_watch(args)
