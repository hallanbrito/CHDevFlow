"""Geração do Relatório Universal C.H. (RUC/1.0) auditável."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess

from chdevflow.core.config import load_manifest
from chdevflow.core.status import check_git_status


def get_latest_evidence(project_path: Path) -> dict | None:
    """Carrega o arquivo de evidência mais recente em .ch/evidence."""
    evidence_dir = project_path / ".ch" / "evidence"
    if not evidence_dir.is_dir():
        return None

    files = sorted(evidence_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return None

    try:
        return json.loads(files[0].read_text(encoding="utf-8"))
    except Exception:
        return None


def get_modified_files(project_path: Path) -> list[str]:
    """Lista arquivos modificados em relação ao Git HEAD."""
    res = subprocess.run(
        ["git", "-C", str(project_path), "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=False,
    )
    if res.returncode != 0:
        return []

    lines = res.stdout.strip().splitlines()
    files = []
    for l in lines:
        parts = l.strip().split(maxsplit=1)
        if len(parts) == 2:
            files.append(parts[1])
    return sorted(files)


def generate_ruc_text(
    project_path: Path,
    executor: str = "AGY",
    mission_title: str | None = None,
) -> str:
    """
    Gera o texto do RUC v1.0 a partir de evidências reais observadas no Git e em .ch/evidence.
    Compara estritamente branch e SHA da evidência com o estado atual.
    Evidência antiga/divergente vira NÃO_VERIFICADO.
    FAIL permanece estritamente BLOQUEADO, nunca AGUARDANDO_PO.
    Registra unicamente fatos observados; limites não auditados são marcados como NÃO_VERIFICADO.
    """
    target = project_path.resolve()
    git_info = check_git_status(target)
    raw_evidence = get_latest_evidence(target)
    mod_files = get_modified_files(target)

    now_iso = datetime.now(timezone.utc).isoformat()
    proj_name = raw_evidence.get("project_name") if raw_evidence else target.name
    cur_branch = git_info["branch"] or "NÃO_VERIFICADO"
    cur_sha = git_info["commit_sha"] or "NÃO_VERIFICADO"
    title_str = mission_title or f"Missão em {cur_branch}"

    # Validação estática de manifesto
    manifest_path = target / "chdevflow.yaml"
    manifest_loaded = False
    manifest_status_msg = "Manifesto ausente (NÃO_VERIFICADO)"
    if manifest_path.is_file():
        try:
            load_manifest(manifest_path)
            manifest_loaded = True
            manifest_status_msg = "Manifesto 'chdevflow.yaml' carregado e validado"
        except Exception as exc:
            manifest_status_msg = f"Falha na validação do manifesto: {exc}"

    # Validação de divergência de evidência em relação ao estado atual
    evidence_valid = False
    evidence_divergence_msg: str | None = None

    if raw_evidence:
        ev_branch = raw_evidence.get("branch")
        ev_sha = raw_evidence.get("commit_sha")

        # Se Git estiver ativo, branch e SHA precisam ser consistentes com a evidência
        if git_info["is_git"]:
            # Se a branch for diferente ou se o SHA divergiu (e não era 'sem commits')
            if ev_branch != cur_branch:
                evidence_divergence_msg = f"Branch divergente: evidência gerada em '{ev_branch}' vs atual '{cur_branch}'"
            elif ev_sha and cur_sha and ev_sha != "sem commits" and cur_sha != "sem commits" and ev_sha != cur_sha:
                evidence_divergence_msg = f"Commit SHA divergente: evidência gerada no commit '{ev_sha}' vs atual '{cur_sha}'"
            else:
                evidence_valid = True
        else:
            evidence_valid = True
    else:
        evidence_divergence_msg = "Nenhum arquivo de evidência localizado em .ch/evidence/"

    if evidence_valid and raw_evidence:
        ev_state = raw_evidence.get("overall_state", "NÃO_VERIFICADO")
    else:
        ev_state = "NÃO_VERIFICADO"

    if ev_state == "PASS":
        parecer = "APROVADO_TECNICAMENTE (Checks locais passaram; aguardando homologação PO)"
        estado_final = "AGUARDANDO_PO"
    elif ev_state == "FAIL":
        parecer = "BLOQUEADO (Falha nos checks de verificação)"
        estado_final = "BLOQUEADO"
    else:
        parecer = "PARCIAL (Verificação não executada ou evidência divergente)"
        estado_final = "NÃO_VERIFICADO"

    # Formata tabela de testes
    tests_rows: list[str] = []
    if evidence_valid and raw_evidence and raw_evidence.get("commands"):
        for i, cmd in enumerate(raw_evidence["commands"], start=1):
            st = cmd.get("state", "NÃO_VERIFICADO")
            dur = cmd.get("duration_seconds", 0.0)
            c_name = cmd.get("command", "desconhecido")
            tests_rows.append(f"| T0{i} | Execução do comando `{c_name}` | {st} | Duração: {dur}s, exit code: {cmd.get('exit_code')} |")
    else:
        motivo = evidence_divergence_msg or "Evidência ausente ou divergente"
        tests_rows.append(f"| T01 | Verificação de projeto | NÃO_VERIFICADO | {motivo} |")

    tests_block = "\n".join(tests_rows)
    files_block = ", ".join(f"`{f}`" for f in mod_files) if mod_files else "Nenhum arquivo modificado na árvore de trabalho"
    git_worktree_desc = "limpa" if not git_info["is_dirty"] else f"dirty ({len(mod_files)} arquivo(s) modificado(s))"

    # Seção 3 com atividades realmente comprovadas
    atividades: list[str] = []
    if manifest_loaded:
        atividades.append("| A01 | Carregamento e validação sintática do manifesto `chdevflow.yaml` | Concluído com sucesso |")
    else:
        atividades.append(f"| A01 | Validação de manifesto `chdevflow.yaml` | NÃO_VERIFICADO ({manifest_status_msg}) |")

    if git_info["is_git"]:
        atividades.append(f"| A02 | Inspeção do estado do repositório Git local | Concluído (branch: `{cur_branch}`, SHA: `{cur_sha}`) |")
    else:
        atividades.append("| A02 | Inspeção do repositório Git | NÃO_VERIFICADO (Diretório não é repositório Git) |")

    if evidence_valid and raw_evidence:
        atividades.append(f"| A03 | Execução de suíte de verificação local (`ch verify`) | {ev_state} |")
    else:
        atividades.append(f"| A03 | Execução de suíte de verificação local | {ev_state} ({evidence_divergence_msg}) |")

    atividades_block = "\n".join(atividades)

    return f"""# RELATÓRIO UNIVERSAL C.H. — {executor} — {title_str}

> **Protocolo:** `RUC/1.0`
> **Natureza:** Documento técnico comprobatório gerado por CLI. **Não substitui decisão humana do PO.**
> **Fonte primária:** Repositório local e evidências estruturadas de verificação.

## 1. Identificação da missão

| Campo | Valor |
|---|---|
| Identificador do Projeto | `{proj_name}` |
| Executor declarado | `{executor}` |
| PO responsável | Hallan |
| Nível CH proposto | CH-2 (trabalho técnico em branch dedicada) |
| Ambiente | Local / Sandbox Linux |
| Fonte da consulta | LOCAL_REPO |
| Horário da geração | `{now_iso}` |
| Baseline SHA | `{cur_sha}` |
| Branch de trabalho | `{cur_branch}` |
| Parecer técnico preliminar | `{parecer}` |

## 2. Resumo executivo

**Parecer:** {parecer}.
Documento estruturado emitido pelo CHDevFlow CLI a partir do estado observado no repositório local e das evidências registradas em `.ch/evidence`.
- **Git observado:** Branch `{cur_branch}`, Commit SHA `{cur_sha}`, Árvore de trabalho {git_worktree_desc}.
- **Verificação local:** {ev_state} (Evidências em `.ch/evidence/`).
- **Estado técnico:** `{estado_final}` (aguardando homologação e auditoria independente).

## 3. Consultas e atividades realizadas

| ID | Ação de fato executada | Resultado |
|---|---|---|
{atividades_block}

**Fora do escopo:** Merge automático, alteração de regras da branch `main`, publicação de pacotes externos e execução de daemons permanentes.

## 4. Evidências verificáveis

| ID | Fato e classe | Fonte / limite |
|---|---|---|
| E01 | Estado geral da verificação: `{ev_state}` | Arquivo de evidência estruturada em `.ch/evidence` |
| E02 | SHA de commit: `{cur_sha}` | Git local (`rev-parse HEAD`) |
| E03 | Arquivos alterados rastreados: {len(mod_files)} | Git local (`status --porcelain`) |
| E04 | Manifesto local: `{manifest_status_msg}` | Arquivo `chdevflow.yaml` |

**Limites e fatos explicitamente NÃO_VERIFICADOS:**
- Ausência de mutação na branch remota `main`: NÃO_VERIFICADO (inspeção restrita ao ambiente local e à branch ativa de trabalho).
- Ausência de exposição de credenciais em todo o histórico do Git: NÃO_VERIFICADO (aplica-se apenas validação do manifesto e mascaramento de saída dos comandos de verificação).
- Inspeção estática de código-fonte de negócio: NÃO_VERIFICADO (atesta apenas comandos e exit codes configurados).
- Custos adicionais em nuvem: NÃO_VERIFICADO (R$ 0,00 declarado pelo executor; sem medição remota).
- Homologação de negócio: NÃO_VERIFICADO (pertence exclusivamente à decisão humana do PO).

## 5. Verificações e resultados

| Teste | Critério | Estado | Evidência |
|---|---|---|---|
{tests_block}

## 6. Riscos e bloqueios

| Risco | Impacto | Condição / mitigação |
|---|---|---|
| Modificações não testadas | Alto | Bloquear merge até execução de `ch verify` com PASS |
| Divergência de branches | Médio | Manter trabalho estritamente na branch da fatia |

## 7. Alterações realizadas

- **Arquivos modificados:** {files_block}
- **Status do manifesto:** {manifest_status_msg}
- **Sanitização de comandos:** Saídas stdout/stderr e comandos de verificação submetidos a filtros de mascaramento de segredos.
- **Custo adicional verificado:** R$ 0,00 declarado pelo executor.
- **Deploy / merge:** NÃO EXECUTADO (Reservado à decisão humana).

## 8. Recomendação técnica e próximo passo

**Parecer final:** {parecer}.
**Estado da entrega:** `{estado_final}` para auditoria independente e homologação.
"""


def generate_ruc(
    project_path: Path | None = None,
    output_path: Path | None = None,
    executor: str = "AGY",
    mission_title: str | None = None,
) -> tuple[Path, str]:
    """Gera o arquivo RUC em docs/CH/ ou caminho customizado."""
    target = (project_path or Path.cwd()).resolve()
    content = generate_ruc_text(target, executor=executor, mission_title=mission_title)

    if output_path:
        dest = output_path.resolve()
    else:
        docs_ch = target / "docs" / "CH"
        docs_ch.mkdir(parents=True, exist_ok=True)
        dest = docs_ch / "RELATORIO-UNIVERSAL-CH-ULTIMO.md"

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content, encoding="utf-8")
    return dest, content
