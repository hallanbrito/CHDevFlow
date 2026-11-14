# CH-PIPE-01 — Ciclo de Correção Controlada (CCC-01)

**Status da decisão:** APROVADA PELO PO em 14/11/2026 (America/Fortaleza).  
**Status de implementação:** PENDENTE — documento de política/contrato; não constitui executor homologado.  
**Origem:** Issue #78; implementação alvo: Draft PR #83 e fatias subsequentes.  
**Papéis:** AGY implementador; Python/CHDevFlow orquestrador; Codex auditor independente; CH-1 supervisão; PO autoridade de decisão/escalonamento.

## 1. Regra vinculante

Para uma mesma missão, uma execução inicial **mais no máximo duas devoluções ao AGY**:

| Tentativa | Trabalho do AGY | Se Python ou Codex reprovar tecnicamente |
| --- | --- | --- |
| 1/3 | Implementação inicial | Enviar achados/testes ao AGY (devolução 1/2) |
| 2/3 | Correção da implementação existente | Enviar novos achados/testes ao AGY (devolução 2/2) |
| 3/3 | Última correção | **Não chamar AGY novamente.** Encerrar e escalar ao PO, com dossiê completo |

**Máximo absoluto: 3 invocações do AGY por missão e 2 devoluções.** Aprovação válida pode encerrar o ciclo em qualquer tentativa. Não é obrigatório consumir todas as tentativas. Inexistência de progresso, achados repetidos, esgotamento do orçamento ou risco pode encerrar antes.

Esta política substitui, especificamente **para reprovação técnica do código**, a orientação D06 da Issue #78 de um retry após diagnóstico. Restrições de ativação, autorização, segurança e custo das demais decisões continuam valendo.

## 2. Fluxo por tentativa

1. O orquestrador cria `execution_id`, `mission_id`, contador persistido e diretório de evidências; restaura estado já persistido em retomada, sem zerar tentativas.
2. AGY recebe a missão delimitada e, quando for correção, **o código anterior e um pacote estruturado de feedback**, com falhas de testes e/ou parecer integral do Codex (segredos redigidos); não recomeçar trabalho do zero.
3. Python valida allowlist, integridade, AST/contratos e executa testes independentes. Se houver reprovação técnica, guarda logs e abre devolução ao AGY se ainda houver cota, **sem declarar aprovação**; revisão Codex pode ser pulada quando o código não passou na etapa de testes.
4. Se os testes passarem, Codex recebe diff, testes e contexto da missão. Só aceitar veredito final de turno concluído, com identificação de tentativa e achados; ausência de parecer válido é bloqueio, não aprovação.
5. **Codex aprova + testes passam:** estado `APROVADO_AGUARDANDO_CH1`; evidências entregues à supervisão. **Codex veta:** feedback volta ao AGY dentro dos limites; na terceira tentativa, estado `AGUARDANDO_PO`.
6. Cada iteração deve registrar antes da próxima chamada: contador, objetivo, SHA/diff do artefato, testes e resultados, parecer, horários, tokens/custo quando informados, motivo de continuidade/parada e caminho do dossiê.

Nenhum parecer `PASS` dos testes substitui a revisão independente do Codex. Nenhuma validação de texto, rótulo ou saída parcial do agente substitui um parecer íntegro.

## 3. Máquina de estados e encerramento

`PENDENTE` → `AGY_EXECUTANDO` → `VALIDANDO_PYTHON` → (falha técnica → `CORRECAO_PENDENTE`; sucesso → `AUDITORIA_CODEX`) → (`APROVADO_AGUARDANDO_CH1` ou `CORRECAO_PENDENTE` ou `AGUARDANDO_PO`).

Estados terminais ou suspensivos:
- `APROVADO_AGUARDANDO_CH1`: testes válidos e Codex aprovou.
- `AGUARDANDO_PO`: terceira tentativa reprovada; não reexecutar automaticamente.
- `BLOQUEADO_INFRA`: credencial, quota, serviço, executável indisponível, timeout, falha de parser, resultado incompleto ou perda de integridade. **Não repetir automaticamente** chamadas de IA por problemas não técnicos.
- `BLOQUEADO_ESCOPO`: arquivo fora da allowlist, alteração proibida ou violação de limite. Exige investigação; não contornar limites para conseguir PASS.
- `CANCELADO` e `ORCAMENTO_ESGOTADO`: encerramento com registro de evidências.

**Invariante:** contador de AGY <= 3; devoluções <= 2; quando estado terminal/suspensivo, nenhuma nova chamada de modelo sem ação humana autorizada. Retomadas/replays devem ser idempotentes e não duplicar execução/cobrança.

## 4. Contenção de loops e consumo

- Teto de tentativas **e** teto total de duração, chamadas e orçamento/cota. O teto de 3 não substitui custo nem tempo. Aplicar o **menor** limite disponível; não iniciar a próxima rodada se não houver tempo/cota suficiente.
- Usar a configuração restritiva atual do piloto (timeout máximo 900 s), até implementar um orçamento total explícito para as três rodadas. Não multiplicar automaticamente o timeout por três.
- Se Codex retornar exatamente a mesma reprovação sem progresso verificável, permitir encerramento antecipado para análise; nunca tratar ausência de mudança como sucesso.
- Sem retry automático de autenticação, 429/quota, timeouts, erros de infraestrutura ou comportamento suspeito. Sem usar modelo de fallback pago por inferência.
- Segredos nunca devem ser enviados nos feedbacks/dossiês. CLI local deve herdar autenticação do usuário da sessão, sem exportar credenciais.

## 5. Contrato de devolução do Codex ao AGY

O orquestrador deve montar um envelope durável por tentativa com, no mínimo:
- `mission_id`, `execution_id`, `attempt_number`, `max_attempts: 3`, `returns_remaining`;
- SHA do artefato e diff autorizado;
- logs de testes com resultados e IDs de teste, incluindo casos adversariais;
- parecer literal final do Codex, achados classificados, arquivo/trecho e ações corretivas;
- instrução de alterar **apenas** arquivos da missão e manter testes independentes imutáveis.

O exemplo que motivou a decisão foi a função `movimentar`: os nove testes Python passaram, mas Codex vetou ausência de validação de tipo `type(tipo) is str`, que permitia objetos com `__eq__` enganoso. **Adicionar teste de regressão adversarial** para esse caso no contrato de aceite; não basta consertar só o laboratório existente.

## 6. Dossiê, esteira e escalonamento

Em cada tentativa guardar artefatos separados, imutáveis ou versionados: `attempt-01/`, `attempt-02/`, `attempt-03/` com código, diff/hash, testes e auditoria. Ao encerrar, consolidar `RELATORIO_COMPLETO_CH1.md` e `execucao.json` com linha do tempo, contador, custos conhecidos, motivos e decisão solicitada.

Na **terceira reprovação**, criar um item `AGUARDANDO_PO` na esteira de supervisão quando a integração de escrita ao Project #2 estiver **explicitamente autorizada e tecnicamente disponível**; antes disso, registrar a pendência na Issue/PR GitHub correspondente e no dossiê, sem alegar que existe cartão no Project #2. O item não deve duplicar registros em retomadas.

O PO pode decidir: corrigir requisitos, delegar nova missão com autorização nova, arquivar, ou interromper. A autorização para nova missão **não reinicia silenciosamente** o contador da missão encerrada.

## 7. Critérios de aceite da implementação

- [ ] Teste: Codex aprova na tentativa 1 → exatamente 1 AGY, 1 Codex, 0 devoluções, dossiê.
- [ ] Teste: Codex reprova 1 e 2, aprova 3 → exatamente 3 AGY, 3 revisões e 2 devoluções, estado aprovado.
- [ ] Teste: Codex reprova as 3 → **3 AGY, 2 devoluções, nenhum quarto AGY**, `AGUARDANDO_PO`, dossiê completo.
- [ ] Teste: os testes Python reprovam → feedback de testes ao AGY, revisão Codex não exigida até testes passarem; respeitar contadores.
- [ ] Teste: falha de autenticação/quota/timeout/saída incompleta → bloqueio sem loop ou cobrança adicional.
- [ ] Teste: retomada e crash/restart preservam contador, estado e tentativas; sem duplo processamento.
- [ ] Teste: rejeitar `tipo` não-string com `__eq__` enganoso na aceitação independente.
- [ ] Integração real local AGY + Codex validada pelo PO com dossiê; CI offline com agentes simulados **não** é prova de integração real.
- [ ] O escalonamento publica evidência na Issue/PR sem escrever no Project #2 até autorização específica.

## 8. Fronteiras de autorização

Esta decisão aprova a **política e sua implementação em branch/PR para revisão**. Não autoriza merge, deploy, execução autônoma/cron, gastos de API, incremento de cotas, bypass de limites ou acesso de escrita ao GitHub Project #2. O piloto real continua opt-in no computador do operador. A aplicação futura a missões gerais dependerá de homologação do controlador.
