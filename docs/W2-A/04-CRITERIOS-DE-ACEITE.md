# W2-A / 04 — Critérios de aceite, riscos, decisões e próximos gates

**Entrega:** documentação CH-1 da [Fatia #8](https://github.com/hallanbrito/CHDevFlow/issues/8).  
**Base de decisão:** [D01–D07 ratificadas pelo PO](https://github.com/hallanbrito/CHDevFlow/issues/7).  
**Estado:** PR documental deve ficar **Draft**, sem merge e sem qualquer autorização executiva.

## 1. O que o PO poderá aprovar nesta W2-A

O PO poderá aceitar, rejeitar, ou solicitar mudanças **apenas ao desenho documental**. O aceite desta W2-A não autoriza W2-B/C/D/E, criação de código, instalação no CachyOS, acesso ao HallanCraft nem execução de AGY/Codex.

Critérios objetivos para revisão do Draft PR:

- [ ] A branch e o PR alteram **somente Markdown** no CHDevFlow.
- [ ] A arquitetura identifica fronteiras GitHub/Project/host/AGY/worktree/PO e deixa **desligado por padrão** qualquer futuro executor.
- [ ] As sete decisões D01–D07 são refletidas fielmente, sem novos custos ou executor alternativo presumido.
- [ ] Há contrato exemplificado de missão, autorização CH-2 **individual** e relatório/run_id; payload completo e autoria verificada previstos.
- [ ] Etapa CH, etiqueta ch:workflow e atribuição à esteira nunca concedem permissão para executar.
- [ ] Concorrência = 1, 15 minutos por tentativa, no máximo uma tentativa adicional **após diagnóstico**, cancelamento manual e falha segura são regras explícitas.
- [ ] Custo adicional zero é uma condição de **pré-disparo**, não promessa de monitoramento posterior.
- [ ] Não há merge/deploy automáticos ou permissão de escrever na branch principal.
- [ ] HallanCraft, produção, mundos, saves e dados privados permanecem intocados.
- [ ] A incerteza sobre headless/cancelamento/custos do AGY/Antigravity está declarada como pendência, sem inferência de compatibilidade com Gemini CLI.
- [ ] O plano de testes contém casos positivos/negativos, evidências e **não declara testes funcionais executados**.
- [ ] O PR solicita uma decisão humana explícita e não faz merge por si mesmo.

## 2. Riscos e bloqueios abertos

| Risco | Gravidade | Tratamento exigido antes da implementação |
|---|---|---|
| Antigravity não expõe API/CLI de automação compatível | Bloqueador | Investigação técnica documentada no CachyOS; se inviável, retornar ao PO |
| Impossibilidade de provar operação com custo extra zero | Bloqueador | Não iniciar missão; obter prova do caminho gratuito sem créditos pagos |
| Falha na interrupção confiável de processo/grupo | Bloqueador | Testar kill/cancelamento em ambiente seguro; sem controle, sem AGY |
| GitHub Projects tem campos visuais sem atomicidade transacional | Alto | Usar mecanismo de reserva/autoridade verificável; não tratar comentário/label como lock |
| Instrução maliciosa em Issue/prompt/saída de agente | Alto | Separar dados da política e impedir elevação/autoaprovação |
| Proteção de main ausente, permissões/bypass excessivos | Bloqueador | Confirmar ruleset/branch protection e mínimo privilégio |
| Alteração acidental de mundos/saves/arquivos ignorados | Bloqueador | Worktree isolada, allowlist estrita, verificar caminhos reais, backup e rollback antes do futuro piloto |
| Aprovação humana atribuída incorretamente a bot | Bloqueador | Identidade autenticada separada de executor lógico e autor de commit |
| Paralelismo/replay depois de crash | Alto | Exclusão forte e idempotência, testes de queda e retomada bloqueada |

## 3. Decisões já resolvidas x perguntas ainda abertas

**Resolvidas pelo PO (não reabrir silenciosamente):** notebook CachyOS; AGY/Antigravity; CH-2 por tarefa futura; HallanCraft como piloto; disparo manual; limite 1/15min/1 retry pós-diagnóstico/parada manual/custo adicional zero; credenciais locais seguras, mínimo privilégio, logs de agente/run_id, branch principal protegida.

**Não são decisões novas de produto; são verificações técnicas futuras:**
1. Qual interface de automação AGY/Antigravity realmente existe e é suportada no notebook?
2. Como observar de modo verificável cobranças e garantir **nenhum gasto adicional**, mesmo usando assinaturas existentes?
3. Qual é o mecanismo apropriado para autorização PO autenticada, versionada e não repetível?
4. Como garantir mutex atômico e retomada fail-closed sem transformar Projects em fonte de autoridade?
5. Quais regras/branches de HallanCraft e CHDevFlow estão efetivamente protegidas; existe bypass?
6. Qual prova de cancelamento seguro em 15 minutos para o AGY?
7. Qual Fatia W futura autorizará inspeção somente leitura do ambiente para responder a essas perguntas?

Se qualquer resposta exigir nova permissão, cobrar serviço ou alterar decisão D01–D07, **submeter ao PO primeiro**.

## 4. Plano de evolução condicionado

| Fatia futura | Entrega pretendida | Pré-condição |
|---|---|---|
| W2-B | Contrato implementável + simulador de despacho **dry-run** com mocks (nenhum AGY iniciado) | autorização CH-2 própria, revisão do Draft PR documental, isolamento |
| W2-C | Prova inofensiva no HallanCraft (sem merge; branch/worktree) | AGY viável ou decisão expressa sobre executor, segurança/custo/backup verificados e autorização CH-2 da missão |
| W2-D | Adaptador AGY/Antigravity controlado, se oficialmente/suportadamente possível | confirmação de interface e limites, autorização específica, sem custo extra |
| W2-E | Auditoria final e critérios de homologação | todos os bloqueios críticos eliminados e validação do PO |

A ordem entre W2-C e W2-D poderá ser revisada no planejamento; **não é autorização para implementar qualquer uma**. Evitar alegar disponibilidade AGY antes de prova.

## 5. Inventário e rollback desta entrega W2-A

**Arquivos propostos:** 01-ARQUITETURA.md, 02-CONTRATOS.md, 03-PLANO-DE-TESTES.md e 04-CRITERIOS-DE-ACEITE.md na pasta docs/W2-A do **CHDevFlow**, eventualmente link no README. Nenhum arquivo de código, GitHub Action, teste executável ou segredo novo.

**Verificação nesta entrega:** inspeção textual do diff para detectar alterações fora de Markdown, conflito com decisões do PO, dados sensíveis e afirmações de testes inexistentes. Nenhum teste funcional ou de integração pode ser alegado.

**Rollback:** fechar o Draft PR sem merge ou remover a branch de documentação após decisão do PO. A branch main e o HallanCraft não serão alterados; Issues preservam evidências e decisão histórica.

## 6. Decisão formal solicitada ao PO

- **APROVADO (documentação):** autoriza integrar SOMENTE os arquivos documentais após revisão e aprovação de merge específica; não autoriza implementação.
- **AJUSTES:** retornar à mesma branch/PR com mudanças pontuais, nova revisão humana.
- **APROVADO PARCIALMENTE:** integrar apenas se escopo documental e diff puderem ser separados com clareza; abrir issue residual.
- **REPROVADO:** encerrar sem integrar; manter trilha auditável.

**Estado ao enviar para revisão:** EM_REVISAO / AGUARDANDO_PO, Draft PR aberto. **Próximo gatilho:** decisão explícita do PO no Draft PR; não executar nenhuma Fatia W futura sem autorização nova.
