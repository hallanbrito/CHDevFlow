# C.H. DevFlow

**Framework e CLI de esteiras de desenvolvimento humano–IA com governança do Método C.H.**

O **CHDevFlow** organiza o trabalho de Hallan (Product Owner), ChatGPT (orquestração e auditoria), Codex e AGY/Gemini (execução), usando GitHub como fonte de verdade versionada. O objetivo é evitar estados divergentes, registrar prompts e evidências, trabalhar por Fatias W e reservar as decisões de integração ao responsável humano.

> Princípio arquitetural: **Governança universal, execução especializada.**
> O núcleo C.H. governa Projeto, Fatia W, baseline, branch, executor, autonomia, critérios de aceite, evidências, RUC e decisão do PO. Adapters conhecem as stacks específicas (.NET, Angular, React, Python, Java, etc.).

---

## CHDevFlow CLI (`ch`)

A partir da versão v0.1 (Épico #32), o CHDevFlow pode ser instalado localmente como ferramenta de linha de comando (`ch`).

### Instalação local

Requer Python >= 3.10 e [uv](https://astral.sh/uv):

```bash
# Instalação local isolada em modo editável (garanta ~/.local/bin no PATH)
uv tool install --editable . --force

# Ou no ambiente Python corrente
pip install -e .
```

Verifique a instalação:

```bash
ch --version
ch --help
```

### Ambiente de Testes e Autossuficiência

Para executar a suíte completa de testes unitários e ensaios E2E:

```bash
python3 -m unittest discover -s tests -p "test_*.py"
python3 -m unittest discover -s apps/bootstrap/sentinela/tests -p "test_*.py"
```

O executor de testes e a verificação E2E são autossuficientes: caso o comando `ch` não esteja disponível no PATH do ambiente, a resolução ocorre internamente via módulo Python (`python3 -m chdevflow.cli`).

---

## Ciclo de Uso e Comandos

```bash
ch --version
ch --help
ch new <nome> [--backend <stack>] [--frontend <stack>] [--database <db>] [--preset <preset>]
ch init [--path <dir>] [--apply]
ch doctor [--path <dir>] [--json]
ch status [--path <dir>] [--strict] [--json]
ch tree [--path <dir>]
ch verify [--path <dir>] [--json]
ch mission new "<Título>" [--executor AGY] [--autonomy CH-2] [--remote]
ch ruc [--path <dir>] [--output <caminho>]
ch submit [--remote]
ch watch --once --dry-run
```

### Exemplos Práticos

#### 1. Novo projeto React
```bash
ch new MeuFrontend --frontend react
cd MeuFrontend
git init
ch doctor
ch status
ch verify
```

#### 2. Novo projeto Fullstack .NET + Angular + PostgreSQL
```bash
ch new PulseOps --backend dotnet --frontend angular --database postgres
cd PulseOps
git init
ch doctor
ch status
ch verify
```

Também é possível utilizar presets arquiteturais:
```bash
ch new PulseOps --preset dotnet-angular
```

#### 3. Projeto existente via `ch init`
Para adotar a governança C.H. em um repositório já existente sem sobrescrever arquivos existentes:

```bash
# Prévia (dry-run por padrão)
ch init --path /caminho/do/projeto

# Aplicação segura (apenas cria arquivos ausentes)
ch init --path /caminho/do/projeto --apply

# Atualiza inventário da árvore
ch tree --path /caminho/do/projeto
```

#### 4. Verificação auditável e evidências estruturadas
```bash
ch verify
```
Executa sequencialmente os comandos definidos em `verification.commands` no `chdevflow.yaml`, sanitiza credenciais e persiste evidência auditável em `.ch/evidence/<timestamp>-<id>.json`.

#### 5. Ciclo de Missão, RUC e Submissão
```bash
# Gera fatia de missão local a partir do modelo CHAVE
ch mission new "Implementar Autenticação OAuth"

# Gera o Relatório Universal C.H. com base nos fatos e testes locais observados
ch ruc

# Valida branch != main, diff existente e checks PASS, preparando Draft PR
ch submit
```

#### 6. Observação pontual com a Sentinela
Conforme a **Decisão D05**, o CHDevFlow opera estritamente sem daemons ou cron na v0.1:

```bash
# Observação única em modo somente leitura (LIVE_GITHUB)
ch watch --once --dry-run
```

---

## Governança e Regras Invariáveis

1. **Gate Humano Estrito**: Nenhuma label, coluna de Project, saída de agente ou comando de CLI substitui a autorização do Product Owner humano.
2. **Sem Merge Automático**: Comandos como `ch submit` nunca fazem merge; preparam commits/branches e abrem exclusivamente **Draft PRs**.
3. **Proteção da Main**: Submissões diretas na branch `main` são bloqueadas na raiz.
4. **Sigilo de Segredos**: Segredos, tokens, senhas ou connection strings são estritamente proibidos em `chdevflow.yaml` e são mascarados em logs e relatórios RUC.
5. **Sem mutação indevida de sistema**: O comando `ch doctor` apenas diagnostica o ambiente e instrui remediações; nunca executa `sudo` nem modifica pacotes do sistema.

---

## Navegação

- [RFC de arquitetura](docs/RFC-CH-DEVFLOW.md)
- [W1 — Esteiras e Kanban (instalado e homologado)](docs/W1-ESTEIRAS-KANBAN.md)
- [GitHub Project W1 — esteiras](https://github.com/users/hallanbrito/projects/2)
- [W2-A — Arquitetura documental](docs/W2-A/01-ARQUITETURA.md)
- [W2-A — Contratos de missão e autorização](docs/W2-A/02-CONTRATOS.md)
- [Relatório Universal C.H. v1.0 (especificação)](docs/CH/RELATORIO-UNIVERSAL-CH-v1.0.md)
- [Gerador legado ch_init](scripts/ch_init.py) (preservado para compatibilidade)
- [Gerador legado ch_tree](scripts/ch_tree.py) (preservado para compatibilidade)
- [Modelos de arquivos para novos projetos](templates/)
- [Sentinela Python](apps/bootstrap/sentinela/)
- [Método C.H. original](https://github.com/hallanbrito/metodo-ch)
