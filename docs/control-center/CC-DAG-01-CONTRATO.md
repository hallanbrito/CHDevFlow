# CC-DAG-01 — Contrato de dependências nativas

Escopo: leitura e apresentação somente leitura das relações `blocked_by` das GitHub Issues para o Control Center. Gate CH-2 do PO: [Issue #59, comentário de 06/11/2026](https://github.com/hallanbrito/CHDevFlow/issues/59#issuecomment-6691485065).

## Fonte e identidade

`LeitorGitHub.obter_dependencias_issue` consulta `GET /repos/{owner}/{repo}/issues/{number}/dependencies/blocked_by` por `gh api --method GET --paginate --slurp`. A saída deve conter páginas JSON completas; falha de qualquer página impede aceitar lista vazia. O leitor valida número, URL canônica, repositório, `node_id`, ID REST, estado e duplicações. A resposta preserva `issue_ref` (`owner/repo#number`), URL, `node_id`, ID REST, estado da Issue, fonte e horário UTC da observação. ID do item do Project e `task_id` permanecem distintos.

`VERIFIED_EMPTY` e `VERIFIED_NONEMPTY` exigem resposta nativa válida. `UNKNOWN` indica ausência da observação ou falha de acesso/rede/timeout; `INVALID` indica resposta ou identidade inconsistente. A ausência de `dependencies` na saída de `gh project item-list` não é uma lista vazia comprovada. Erros são sanitizados; a visão não reaproveita uma leitura anterior.

O `MissionService` mapeia referências canônicas para IDs dos itens presentes no Project. Uma dependência fora da amostra permanece como referência canônica e bloqueia a sucessora. IDs duplicados tornam o grafo inconclusivo. Os dados do Project e das Issues são lidos na mesma requisição do painel, mas o GitHub não oferece transação atômica entre esses endpoints; `observed_at` descreve o instante de cada resposta, não um snapshot global imutável.

A leitura ao vivo tem orçamento total de 30 segundos, incluindo o Project e todas as Issues. Cada subprocesso recebe somente o tempo restante; resultados que chegam após o prazo viram `UNKNOWN`. Duas falhas consecutivas interrompem novas consultas de dependências nesta requisição, e os itens restantes também ficam `UNKNOWN`. Não há cache ou reaproveitamento de leitura antiga.

## Regra de desbloqueio

`INTEGRADA`, `DONE`, `CLOSED`, `PROD_OK` e `Etapa CH=HOMOLOGADA` isoladamente não satisfazem uma dependência. O DAG só reconhece conclusão para pré-requisitos quando há etapa `HOMOLOGADA`, dados íntegros e prova de homologação humana vinculada à missão. **O Control Center atual não dispõe de um verificador confiável dessa prova.** Por isso o `MissionService` fornece `homologacao_verificada=False` em toda leitura ao vivo e de demonstração: a dependência permanece bloqueada mesmo que a etapa visual seja `HOMOLOGADA`.

Mesmo na entrada interna de teste com prova positiva, dependência órfã, externa ao Project, interna ainda pendente ou estado `UNKNOWN`/`INVALID` impede que a missão satisfaça sua sucessora. A conclusão satisfatória exige que todos os pré-requisitos internos estejam, por sua vez, homologados de forma verificável; a prova da missão não substitui a dos seus antecedentes. Não há regra de exceção/override autorizada pelo PO neste contrato. O dashboard mostra contagens distintas para etapas visuais de conclusão e homologações verificadas; a primeira nunca libera pré-requisitos.

O sinal aceito pelo `DAGEngine` é uma entrada interna do serviço, destinada a um futuro verificador autorizado; não é um campo do Project nem uma autorização executiva. Nenhuma classificação `ELEGIVEL` permite iniciar Codex, AGY ou outro agente. O contrato executivo separado da Sentinela permanece obrigatório e inalterado.

## Limites

- Uma leitura com credencial sem visibilidade de determinada Issue pode resultar em `UNKNOWN` ou referência não resolvida; não prova ausência global de dependências.
- `gh api --paginate` segue a paginação indicada pelo GitHub e falha se uma requisição falhar. O leitor valida páginas recebidas, mas não pode detectar um servidor que omita silenciosamente um link de próxima página.
- O RUC desta fatia registra testes offline e a impossibilidade de verificar homologações reais com o contrato atual. A definição de uma prova autenticada e imutável de homologação requer decisão/contrato próprio do PO antes de liberar dependências em produção.
