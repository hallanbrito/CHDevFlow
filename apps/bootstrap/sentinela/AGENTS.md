# Protocolo e Fronteiras de Operação de Agentes — Módulo Sentinela

Este documento estabelece as diretrizes vinculantes para qualquer agente de inteligência artificial (AGY, Codex, ChatGPT ou outro) que interaja com o código ou documentação deste módulo.

---

## 1. Regras Irrevogáveis do Módulo

1. **Autonomia Delimitada:** A Sentinela Python é uma ferramenta de apoio ao Product Owner (PO). Nenhum agente possui autorização para conceder autonomia a si próprio ou a terceiros.
2. **Proibição de Despacho de Agentes Reais:** É estritamente proibido instanciar processos de outros agentes (Codex, AGY em modo real, Gemini CLI) dentro do fluxo de execução deste módulo. Na missão BOOT-01, o executor permitido é exclusivamente o `FakeWorker`.
3. **Imutabilidade Remota:** Nenhum comando que altere o estado do GitHub (como `gh project item-edit`, `gh issue edit`, `git push` ou merge automático) pode ser executado por iniciativa própria de um agente.
4. **Respeito à Decisão D05:** A observação do repositório deve ocorrer apenas sob demanda manual com encerramento imediato (`watch --once`). Proibido implementar loops infinitos, daemons ou tarefas em segundo plano.
5. **Custo Adicional Zero (D06):** É vetado o uso de APIs pagas, compra de créditos ou serviços faturáveis. Qualquer operação com custo incerto deve falhar preventivamente (*fail-closed*).
6. **Contenção Estrita:** Proibido tocar arquivos externos ao escopo autorizado, em especial: mundos do Minecraft, saves, branches protegidas (`main`, `hallan/cc00-fundacao-control-center`), Docker de produção ou outros projetos do host.

---

## 2. Padrão de Didática e Idioma (pt-BR)

- Todo código novo, refatoração, documentação, docstring e comentário deve ser escrito em **português brasileiro (pt-BR)** claro e acessível.
- Nomes de variáveis e funções próprias devem ser autoexplicativos em português (ex: `reivindicar_execucao`, `validar_contrato_missao`, `calcular_digest_sha256`).
- Manter em inglês apenas palavras reservadas da linguagem Python e identificadores padronizados por contratos externos (`run_id`, `mission_digest`, `FakeWorker`, `DISCOVERED`, `AWAITING_PO`).
- As mensagens de erro e exceções devem explicar claramente o motivo do bloqueio para facilitar a auditoria pelo PO humano.

---

## 3. Estado Final Obrigatório

Toda entrega ou execução deve encerrar no estado formal **`AWAITING_PO`** (Aguardando Decisão do Product Owner). Nenhum agente pode homologar a própria entrega ou considerar que a existência de um Pull Request representa aprovação tácita.
