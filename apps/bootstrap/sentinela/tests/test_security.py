"""Testes unitários das políticas de segurança e contenção (security/policies.py).

Cobre validação de caminhos e bloqueio de traversal, proteção de mundos/saves/segredos,
validação de SHA de commit, garantia de custo adicional R$ 0,00 e sanitização de credenciais.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from ch_sentinela.security.policies import (
    ViolacaoPoliticaSegurancaErro,
    sanitizar_texto_segredos,
    validar_caminhos_escopo,
    validar_custo_zero,
    validar_limites_recurso,
    validar_origem_autorizacao,
    validar_sha_commit,
)


class TestesSeguranca(unittest.TestCase):
    """Testes de conformidade com as políticas de contenção do Método C.H."""

    def test_validacao_caminhos_permitidos_sucesso(self) -> None:
        """Valida que caminhos bem delimitados e dentro do escopo passam na verificação."""
        caminhos = ["apps/bootstrap/sentinela/docs/PROJETO.md", "src/modulo.py"]
        # Não deve levantar exceção
        validar_caminhos_escopo(caminhos)

    def test_bloqueio_path_traversal(self) -> None:
        """Garante bloqueio de tentativas de fuga de diretório com '..'."""
        caminhos_perigosos = [
            "../fora_do_repo.py",
            "apps/../../etc/passwd",
            "docs/sub/../../../secrets",
        ]
        for caminho in caminhos_perigosos:
            with self.assertRaises(ViolacaoPoliticaSegurancaErro) as ctx:
                validar_caminhos_escopo([caminho])
            self.assertIn("Tentativa de fuga de diretório", str(ctx.exception))

    def test_bloqueio_caminho_absoluto(self) -> None:
        """Garante bloqueio de caminhos absolutos do sistema operacional."""
        caminhos_absolutos = ["/etc/shadow", "/home/usuario/arquivo.txt", "/var/log"]
        for caminho in caminhos_absolutos:
            with self.assertRaises(ViolacaoPoliticaSegurancaErro) as ctx:
                validar_caminhos_escopo([caminho])
            self.assertIn("Caminho absoluto", str(ctx.exception))

    def test_bloqueio_curingas_amplos(self) -> None:
        """Garante bloqueio de curingas genéricos que tentem liberar todo o repositório."""
        for curinga in ("*", "**", ".", "/", "./"):
            with self.assertRaises(ViolacaoPoliticaSegurancaErro) as ctx:
                validar_caminhos_escopo([curinga])
            self.assertIn("Caminho genérico", str(ctx.exception))

    def test_bloqueio_mundos_saves_e_segredos(self) -> None:
        """Valida que caminhos sensíveis como mundos do Minecraft, saves e .env sejam barrados."""
        caminhos_sensiveis = [
            "minecraft/worlds/world1/level.dat",
            "game/saves/savegame.tar",
            "config/.env.local",
            "auth/secrets/id_rsa",
            "credentials/token.json",
        ]
        for sensivel in caminhos_sensiveis:
            with self.assertRaises(ViolacaoPoliticaSegurancaErro) as ctx:
                validar_caminhos_escopo([sensivel])
            self.assertIn("viola a política de bloqueio", str(ctx.exception))

    def test_validacao_sha_commit(self) -> None:
        """Valida SHA de commit hexadecimal estrito com 40 caracteres."""
        sha_valido = "d2a74426bfa1fab12aafb721c8dad60876f6f8ec"
        self.assertEqual(validar_sha_commit(sha_valido), sha_valido)

        shas_invalidos = [
            "d2a7442",  # curto (7 chars)
            "d2a74426bfa1fab12aafb721c8dad60876f6f8ecXX",  # inválido (>40)
            "g" * 40,  # 'g' não é hexadecimal
            "",
            None,
        ]
        for sha in shas_invalidos:
            with self.assertRaises(ViolacaoPoliticaSegurancaErro):
                validar_sha_commit(sha)  # type: ignore

    def test_garantia_custo_zero(self) -> None:
        """Valida garantia de custo adicional R$ 0,00 (D06)."""
        validar_custo_zero(0)
        validar_custo_zero(0.0)

        with self.assertRaises(ViolacaoPoliticaSegurancaErro) as ctx:
            validar_custo_zero(0.01)
        self.assertIn("Custo adicional proibido", str(ctx.exception))

        with self.assertRaises(ViolacaoPoliticaSegurancaErro):
            validar_custo_zero("gratis")  # Não numérico

    def test_limites_operacionais_d06(self) -> None:
        """Valida que concorrência > 1 ou timeout > 900s sejam rejeitados."""
        limites_validos = {
            "max_parallel": 1,
            "timeout_seconds": 900,
            "max_retries_after_diagnosis": 1,
        }
        validar_limites_recurso(limites_validos)

        # Concorrência > 1 proibida
        lim_paralelo = dict(limites_validos, max_parallel=2)
        with self.assertRaises(ViolacaoPoliticaSegurancaErro):
            validar_limites_recurso(lim_paralelo)

        # Timeout > 900s proibido
        lim_timeout = dict(limites_validos, timeout_seconds=901)
        with self.assertRaises(ViolacaoPoliticaSegurancaErro):
            validar_limites_recurso(lim_timeout)

        # Retries > 1 proibido
        lim_retries = dict(limites_validos, max_retries_after_diagnosis=2)
        with self.assertRaises(ViolacaoPoliticaSegurancaErro):
            validar_limites_recurso(lim_retries)

    def test_sanitizacao_de_segredos_em_texto(self) -> None:
        """Valida redação de tokens GitHub, chaves e credenciais em texto."""
        texto_exposto = (
            "Log com ghp_ABCdef1234567890abcdefghijklmnopqrstuvwxyz e "
            "github_pat_11AAAAAAA000000000000000000000000000000000000000000000000000000000 "
            "e AIzaSyD1234567890abcdef1234567890abcdef"
        )
        texto_limpo = sanitizar_texto_segredos(texto_exposto)
        self.assertNotIn("ghp_ABC", texto_limpo)
        self.assertNotIn("github_pat_", texto_limpo)
        self.assertNotIn("AIzaSyD", texto_limpo)
        self.assertIn("[CREDENCIAL_OCULTADA]", texto_limpo)


if __name__ == "__main__":
    unittest.main()
