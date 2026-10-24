"""Geração e registro de missões por Fatias W sob governança C.H."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re
import subprocess
import sys

from chdevflow.core.status import check_git_status


class MissionError(ValueError):
    """Erro em operações de missão."""
    pass


def slugify(text: str) -> str:
    """Converte título em slug seguro para nomes de arquivo e branches."""
    slug = re.sub(r"[^\w\s-]", "", text.strip().lower())
    slug = re.sub(r"[-\s]+", "-", slug)
    return slug[:40] or "missao"


def generate_mission_markdown(
    title: str,
    project_name: str,
    executor: str = "AGY",
    autonomy: str = "CH-2",
    baseline_sha: str | None = None,
    branch_name: str | None = None,
) -> str:
    """Gera o conteúdo textual da Fatia W conforme o padrão do Método C.H."""
    base_sha_str = baseline_sha or "NÃO_VERIFICADO"
    branch_str = branch_name or f"ch/{slugify(title)}"

    return f"""# Fatia W — {title}

## Identidade
- **Projeto**: {project_name}
- **PO**: Hallan
- **Executor declarado**: {executor}
- **Autonomia proposta**: {autonomy} (PENDENTE DE AUTORIZAÇÃO HUMANA FORMAL)
- **Base SHA**: {base_sha_str}
- **Branch prevista**: {branch_str}
- **Data de geração**: {datetime.now(timezone.utc).isoformat()}

## C — Contextualizar
- **Objetivo / valor**: {title}
- **Estado e referências**: Consultar `docs/PROJETO.md` e `docs/STATUS.md`.

## H — Harmonizar
- **Escopo permitido**: Implementar exclusivamente os requisitos definidos nesta fatia.
- **Fora de escopo**: Modificações na branch `main`, publicação externa, daemons permanentes e merge automático.
- **Critérios de aceitação**: Testes automatizados passando, evidência estruturada salva e RUC gerado.
- **Condição de parada**: Parada imediata em caso de custo inesperado, bloqueio técnico ou necessidade de elevação de privilégios.

## A — Agir
- **Branch de trabalho**: `{branch_str}`
- **Ambiente**: Local / Sandbox
- **Ações autorizadas**: Apenas modificações locais compatíveis com o nível de autonomia formalmente autorizado pelo PO.

## V — Verificar
- [ ] Checks de verificação executados com `ch verify` (PASS)
- [ ] Relatório Universal C.H. gerado com `ch ruc`
- [ ] Sem vazamento de credenciais ou tokens em arquivos/logs

## E — Evoluir
- **Decisão PO**: AGUARDANDO_PO
- **Observações do PO**: (Pendente de revisão humana)
- **PR de entrega**: (Draft PR a ser aberto)
"""


def create_mission(
    title: str,
    project_path: Path | None = None,
    executor: str = "AGY",
    autonomy: str = "CH-2",
    remote: bool = False,
) -> tuple[Path | None, str]:
    """
    Cria uma nova fatia de missão localmente em prompts/.
    Se remote=True, tenta adicionalmente abrir Issue no GitHub via gh.
    Nunca converte a criação em autorização automática.
    """
    target = (project_path or Path.cwd()).resolve()
    git_info = check_git_status(target)

    project_name = target.name
    slug = slugify(title)
    prompts_dir = target / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)

    mission_file = prompts_dir / f"MISSAO-{slug.upper()}.md"
    content = generate_mission_markdown(
        title=title,
        project_name=project_name,
        executor=executor,
        autonomy=autonomy,
        baseline_sha=git_info["commit_sha"],
        branch_name=git_info["branch"],
    )
    mission_file.write_text(content, encoding="utf-8")

    remote_msg = ""
    if remote:
        if not git_info["is_git"]:
            raise MissionError("Não é possível criar Issue remota fora de um repositório Git.")

        gh_check = subprocess.run(["gh", "auth", "status"], capture_output=True, text=True, check=False)
        if gh_check.returncode != 0:
            raise MissionError("GitHub CLI (gh) não está autenticado. Execute 'gh auth login' primeiro.")

        # Cria a Issue remota via gh
        cmd = [
            "gh", "issue", "create",
            "--title", f"W: {title}",
            "--body", content,
            "--label", "ch:workflow",
        ]
        res = subprocess.run(cmd, cwd=str(target), capture_output=True, text=True, check=False)
        if res.returncode == 0:
            remote_url = res.stdout.strip()
            remote_msg = f" | Issue remota criada: {remote_url}"
        else:
            remote_msg = f" | Falha ao criar Issue remota: {res.stderr.strip()}"

    return mission_file, f"Fatia W gerada localmente em: {mission_file}{remote_msg}"
