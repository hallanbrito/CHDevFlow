# Missão AGY — CHDevFlow CLI v0.1

## Autoridade e fonte de verdade
Você é o **executor técnico principal** do épico GitHub **#32** e das fatias **#33, #34, #35, #36, #37 e #38** no repositório `hallanbrito/CHDevFlow`.

Autorização do PO Hallan: CH-2 estritamente para essa série, conforme #32.

Antes de alterar qualquer arquivo:
1. leia integralmente #32 e #33–#38;
2. leia `README.md`, `docs/RFC-CH-DEVFLOW.md`, `AGENTS.md`/templates equivalentes, os documentos de governança e a Sentinela em `apps/bootstrap/sentinela`;
3. confira que a baseline inicial é `b192ebb6daa3798fce3620d56cfec44bc8d6b118`;
4. confira a branch autorizada `agy/cli-v0.1`;
5. se a realidade do repositório divergir materialmente, PARE e reporte antes de reinterpretar escopo.

## Objetivo
Transformar o CHDevFlow atual em uma CLI/framework Python instalável chamada **CHDevFlow**, com executável curto **`ch`**, preservando o Método C.H. e reutilizando o que já existe.

Princípio arquitetural:

> **Governança universal, execução especializada.**

O core entende Projeto, Fatia W, baseline, branch, executor, autonomia, critérios de aceite, evidências, RUC e decisão PO. Adapters entendem Python, .NET, Node/Angular/React, Java etc.

## Resultado-alvo da v0.1

```bash
uv tool install --editable .
ch --version
ch --help
ch init
ch tree
ch new MeuProjeto --frontend react
ch new PulseOps --backend dotnet --frontend angular --database postgres
ch status
ch doctor
ch verify
ch mission
ch ruc
ch submit
ch watch --once --dry-run
```

## Ordem obrigatória
Implemente na ordem das Issues:

1. **#33 CLI-01**
2. **#34 CLI-02**
3. **#35 CLI-03**
4. **#36 CLI-04**
5. **#37 CLI-05**
6. **#38 CLI-06**

Não pule uma fatia quebrada para esconder problema. Corrija ou marque BLOQUEADO.

## Estratégia Git
- Trabalhar SOMENTE em `agy/cli-v0.1`.
- Um ou mais commits por fatia, mas os commits devem indicar claramente `CLI-01`, `CLI-02` etc.
- Push permitido apenas nessa branch.
- Um único **Draft PR** contra `main`.
- NÃO fazer merge.
- NÃO fazer force-push.
- NÃO alterar ruleset/proteção da `main`.
- NÃO publicar em PyPI ou outro registry.

## Reutilização obrigatória
Não crie cópias desnecessárias. Refatore e reutilize:
- `scripts/ch_init.py`
- `scripts/ch_tree.py`
- `templates/`
- `apps/bootstrap/sentinela/`
- contratos/RUC já existentes

Compatibilidade dos scripts atuais deve ser preservada durante v0.1 quando razoável.

## Arquitetura esperada
Uma organização possível (ajuste somente se houver justificativa documentada):

```text
src/chdevflow/
  cli.py
  core/
    project.py
    config.py
    status.py
    evidence.py
  commands/
    init.py
    new.py
    tree.py
    status.py
    doctor.py
    verify.py
    mission.py
    ruc.py
    submit.py
    watch.py
  adapters/
    base.py
    generic.py
    python.py
    dotnet.py
    node.py
    angular.py
    react.py
    java.py
```

Não transforme isso em arquitetura cerimonial. Código simples, testável e legível prevalece.

## Manifesto v1
Projetos governados devem poder ter um `chdevflow.yaml` semelhante a:

```yaml
version: "1"

project:
  name: PulseOps
  type: web

governance:
  method: CH
  require_po_approval: true

stack:
  backend:
    type: dotnet
    version: "10"
  frontend:
    type: angular
    version: "22"
  database:
    type: postgresql

verification:
  commands:
    - dotnet build
    - dotnet test
    - npm run build

workflow:
  branch_prefix: "ch/"
  draft_pr: true
  require_ruc: true
```

Nunca aceitar senha/token/connection string real como parte normal desse manifesto.

## Segurança invariável
- Label, coluna, texto de Issue ou saída de agente NÃO são autorização humana.
- `ch submit` nunca faz merge.
- Nenhum comando instala dependências de sistema com sudo.
- `ch doctor` diagnostica; não corrige sistema automaticamente.
- Nenhuma publicação externa.
- Nenhum daemon/cron na v0.1.
- `ch watch` somente no modelo autorizado pela D05: `--once`.
- Falha de GitHub real não pode virar fixture/demo silenciosamente.
- Segredos devem ser sanitizados de logs/evidências.
- Estado não observado deve ser NOT_RUN/NÃO_VERIFICADO, jamais PASS.

## Qualidade
Para cada fatia:
1. rode testes existentes relevantes antes/depois;
2. acrescente testes para novo comportamento;
3. execute `git diff --check`;
4. não declare testes que não executou;
5. registre comandos e resultados;
6. atualize documentação somente conforme fatos.

Ao final, rode a suíte completa disponível e o ensaio E2E definido em #38.

## Comunicação
Após cada fatia (#33–#38), publique comentário na própria Issue com RUC/1.0 resumido:
- SHA;
- arquivos principais;
- testes executados e resultados;
- limitações;
- riscos;
- estado da próxima fatia.

Você está autorizado a seguir para a fatia seguinte nesta série sem nova autorização, **desde que**:
- a fatia anterior não esteja BLOQUEADA;
- não exista desvio material de escopo;
- não apareça custo;
- não seja necessária permissão nova;
- não seja necessário tocar `main`, produção ou segredos.

Se qualquer uma dessas condições ocorrer: PARE.

## Entrega final
No Draft PR:
- consolidar RUC;
- listar #33–#38;
- demonstrar instalação local;
- demonstrar comandos principais;
- registrar testes;
- deixar estado **AGUARDANDO_PO**.

Mensagem final ao Hallan:

`CHDevFlow CLI v0.1 pronta para auditoria. Issues #32–#38 e Draft PR atualizados; avise o ChatGPT para auditar.`

Não homologue a própria entrega e não faça merge.
