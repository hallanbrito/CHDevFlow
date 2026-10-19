"""Configurações e constantes centrais da Sentinela Python.

Centraliza todas as regras de limites, caminhos padrão, listas de permissão
(allowlists) e invariantes operacionais do Método C.H.
"""
from __future__ import annotations

import os
from pathlib import Path

# Repositórios explicitamente autorizados para leitura e operação
REPOSITORIO_CANONICO: str = "hallanbrito/CHDevFlow"
REPOSITORIOS_PERMITIDOS: tuple[str, ...] = (
    "hallanbrito/CHDevFlow",
    "hallanbrito/HallanCraft",
)

# Identificadores do GitHub Project #2
PROPRIETARIO_PADRAO: str = "hallanbrito"
NUMERO_PROJETO_PADRAO: int = 2

# Limites operacionais irrevogáveis (Decisões D01 a D07)
LIMITE_TEMPO_EXECUCAO_SEGUNDOS: int = 900  # 15 minutos por tentativa
MAXIMO_EXECUCOES_ATIVAS: int = 1            # Concorrência estrita = 1
MAXIMO_TENTATIVAS_RETRY: int = 1           # No máximo 1 retry após diagnóstico
CUSTO_ADICIONAL_PERMITIDO_BRL: float = 0.0  # Custo adicional R$ 0 obrigatório

# Limites de leitura para evitar sobrecarga ou estouro de memória
MAXIMO_ITEMS_PROJECT: int = 500
MAXIMO_ISSUES_POR_LOTE: int = 5
MAXIMO_EVENTOS_TIMELINE: int = 3000

# Versões dos esquemas de contrato suportados
SCHEMA_MISSAO_VERSAO: str = "chdevflow.mission/0.1"
SCHEMA_WORKER_VERSAO: str = "chdevflow.worker-result/0.1"
SCHEMA_SUPERVISOR_VERSAO: str = "chdevflow.supervisor-result/0.1"

# Identidade padrão do Product Owner autorizador
PO_IDENTIDADE_PADRAO: str = "hallanbrito"

# Diretório padrão para persistência de auditoria e checkpoints
# Permite sobrescrita via variável de ambiente para testes isolados
DIRETORIO_DADOS_PADRAO: Path = Path(
    os.getenv("CH_SENTINELA_DATA_DIR", ".ch_sentinela")
)
NOME_ARQUIVO_AUDITORIA: str = "auditoria_eventos.jsonl"
NOME_ARQUIVO_CHECKPOINT: str = "checkpoint_estado.json"


def obter_diretorio_dados() -> Path:
    """Retorna o diretório base para gravação de auditoria e checkpoints.

    Garante que o diretório exista com permissões seguras (0o700) para evitar
    acesso indevido de outros usuários do sistema.

    Returns:
        Path: Caminho do diretório de dados validado e existente.
    """
    diretorio = Path(os.getenv("CH_SENTINELA_DATA_DIR", DIRETORIO_DADOS_PADRAO))
    diretorio.mkdir(mode=0o700, parents=True, exist_ok=True)
    return diretorio
