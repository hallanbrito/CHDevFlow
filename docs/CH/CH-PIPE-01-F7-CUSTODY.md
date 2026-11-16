# F7 Gate 1 — custódia protegida do atestador (CHDevFlow Solo)

O produtor executa a qualificação Docker em `main` e publica apenas evidências da sonda. O atestador consulta a API, valida a origem e o ZIP e assina em outro runner. Um terceiro runner consulta as evidências novamente e verifica o recibo com a chave pública. O publicador rejeita recibos de qualificação. O cenário usa um fornecedor determinístico de código e executa o ciclo de reprovação real em Docker.

## Decisão do PO — modelo Solo (15/11/2026)

**Aprovado pelo PO:** adotar operação individual, sem adicionar uma segunda conta GitHub e com **custo incremental R$ 0**. Esta decisão é de **modelo de governança e preparação documental**, não autorização para habilitar POST remoto, criar reservas/tags, executar AGY/Codex em produção, fazer merge, deploy, release ou editar o Project #2.

**Separação técnica obrigatória:** AGY implementa em PR sem acesso a segredos; Codex/CH-1 revisa evidências e código sem ter a chave privada; o produtor executa sem a chave; somente o job `sign` do workflow confiável na `main`, com Environment `f7-attestor`, pode consumir o secret da chave. O job `verify` fica sem esse secret e valida novamente o recibo usando a política pública externa. GitHub Actions e auditoria automatizada **não são revisores humanos independentes**.

**Risco residual explícito:** o mesmo proprietário administra repositório, rulesets, variável de SHA, Environment e segredo; o ruleset de `main` exige PR, mas no momento registra **0 aprovações obrigatórias**. Portanto a cadeia tem isolamento operacional, porém **não demonstra independência administrativa/humana** e um único administrador ainda pode alterar código e política. O PO aceita esse compromisso apenas para o piloto individual. Não alegar conformidade com exigência de revisão humana externa.

**Estado do aceite atualizado em 16/11/2026:** o PO **HOMOLOGOU OPERACIONALMENTE o Gate 1 no modelo Solo**, após as provas positivas de custódia e as negativas documentadas, aceitando expressamente as ressalvas de administrador único e ausência de revisão humana independente. O Gate 2 já estava homologado. Portanto a F7 registra **2 de 5 gates aceitos (40%)**, exclusivamente no escopo do piloto com um único operador. Isso **não homologa a F7 como um todo** e **não autoriza** publicação real, merge, deploy, release, alteração no Project #2 ou ativação automática dos agentes. `REMOTE_PUBLICATION_ENABLED=False` permanece obrigatório.

## Escopo de governança conforme número de operadores (decisão PO — 16/11/2026)

| Contexto | Política de validação recomendada |
| --- | --- |
| **Projeto com um único operador (Solo)** | Este Gate 1 está homologado **operacionalmente**, sob revisão manual do próprio PO, auditoria CH-1/Codex e registros de CI/assinatura, com **risco residual conscientemente aceito**. A revisão automatizada **não é uma segunda aprovação humana**. |
| **Projeto com mais de um operador** | O **ideal é que pelo menos duas pessoas distintas validem mudanças e ações sensíveis**: por exemplo, uma implementa e outra revisa/aprova, com identidades separadas e trilha de auditoria. Configurar revisões obrigatórias, proteção de branch, Environment e gestão de segredos conforme o risco do projeto. **O aceite Solo não se aplica automaticamente**; exigir nova avaliação e homologação antes de habilitar operação multioperador. |

A validação por duas pessoas é **a diretriz recomendada pelo PO para contexto multioperador**, não uma capacidade já configurada neste repositório Solo, nem uma alegação de controle humano independente na F7 atual. Quando houver exigências regulatórias ou alto impacto, poderão ser necessários controles adicionais além de duas pessoas.

**Limites da homologação Solo:** atesta somente a custódia da sonda F7 no pipeline protegido e as negativas verificadas; não valida execução de AGY/Codex em produção, publicação remota, governança de múltiplos operadores nem os Gates 3, 4 e 5. O administrador único ainda pode alterar código, segredos e políticas; uma conta comprometida ou alteração administrativa maliciosa permanece risco residual. Chave privada local sem passphrase deve permanecer protegida e ser revogada/rotacionada em caso de suspeita.

### Checklist Solo antes de provisionar ou executar

1. Abrir PR para toda mudança de código/workflow/política e registrar auditoria Codex/CH-1 mais revisão manual do diff pelo PO. A revisão automatizada não remove a responsabilidade do PO.
2. Confirmar que o ruleset `main` continua exigindo PR, bloqueando deleção e force-push e sem bypass; checar permissões de Actions, de Environment e acesso de terceiros.
3. Criar `f7-attestor` com acesso **exclusivo da branch `main`**, sem required reviewers no modelo Solo, e com o secret apenas no Environment. Se o GitHub/plano não disponibilizar restrição apropriada, **parar sem provisionar a chave**.
4. Fixar os SHAs integrais revisados e o workflow ID em variáveis confiáveis; usar workflow_dispatch manual do PO. Não atualizar pins automaticamente após merges.
5. Confirmar que workflows de `pull_request`, AGY e o produtor **não** têm acesso ao secret; a verificação deve ocorrer em outro job/runner sem segredo. Rejeitar artefatos e proveniência não confiáveis.
6. Observar e registrar run-id, commit, hashes, fingerprint público, falhas negativas e permissões na PR. Nenhuma prova = Gate 1 pendente.
7. Para liberar **publicação real**, exigir nova autorização específica do PO para ação, issue, texto, commit, custo e plano. Esta decisão Solo **não** contém tal autorização.

## Provisionamento administrativo

1. Confirme que `main` exige PR e proteções sem bypass. O modelo Solo registra auditoria automatizada e conferência manual do PO em cada mudança sensível; **não reivindica revisão humana independente**. O ruleset observado em 15/11/2026 exige PR com zero revisões obrigatórias. Restrinja ao mínimo quem pode alterar a regra e variáveis e documente cada alteração de pin.
2. Em **Settings → Environments**, crie `f7-attestor`. Em **Deployment branches and tags**, selecione exclusivamente a branch `main`. No modo Solo **não configure required reviewers**: o PO é o único proprietário e isso não deve ser disfarçado como aprovação independente. Mantenha a chave privada exclusivamente no secret **do environment** `CH_F7_SIGNING_KEY`. O produtor, a CI de PR e o verificador não recebem o secret. Confirme a disponibilidade das restrições de branch e do Environment antes de inserir a chave.
3. Na estação sob custódia, gere uma chave dedicada Ed25519 sem passphrase para consumo não interativo. Guarde-a fora do repositório em diretório com acesso restrito ao custodiante. Exemplo em PowerShell, substituindo o caminho por um diretório privado já existente:

   ```powershell
   $f7Key = Join-Path $env:LOCALAPPDATA 'CHDevFlow-Custodia\ch-f7-ed25519'
   ssh-keygen -t ed25519 -N '' -C 'CHDevFlow F7 attestor' -f $f7Key
   Get-Content -Raw -LiteralPath $f7Key |
     gh secret set CH_F7_SIGNING_KEY --env f7-attestor --repo hallanbrito/CHDevFlow
   ssh-keygen -lf "$f7Key.pub"
   ```

   O PO deve conferir o fingerprint público usando outra sessão/ferramenta de leitura, registrar o valor público na evidência e proteger o material privado fora do repositório. Essa checagem em outro contexto **não equivale a uma segunda pessoa custodiante**. A chave privada deve ficar fora de logs, artefatos, comentários e commits.
4. Em **Settings → Secrets and variables → Actions → Variables**, configure estes valores por meio da conta administrativa:

   | Variável | Valor |
   | --- | --- |
   | `CH_F7_TRUSTED_RUNNER_PUBKEY` | Dois campos da chave pública verificada, no formato `ssh-ed25519 <base64>` |
   | `CH_F7_TRUSTED_RUNNER_SHA` | SHA completo revisado do produtor em `main` |
   | `CH_F7_PRODUCER_WORKFLOW_ID` | ID numérico consultado via `gh api repos/hallanbrito/CHDevFlow/actions/workflows/f7-custody-producer.yml --jq .id` (`gh workflow view` não aceita `--json`) |
   | `CH_F7_ATTESTOR_SHA` | SHA completo revisado do atestador em `main` |
   | `CH_F7_REVOKED_RUNNER_FINGERPRINTS` | `NONE` inicialmente, ou fingerprints OpenSSH `SHA256:…` separados por espaços |

   Uma mudança no HEAD de `main` exige nova auditoria automatizada, conferência manual e registro de decisão do PO antes de atualizar os SHAs. Os jobs bloqueiam execuções cujo SHA difere da política.

## Provas operacionais observadas (15/11/2026)

- **Produtor de qualificação**, run [#43782606042](https://github.com/hallanbrito/CHDevFlow/actions/runs/43782606042): job `produce` success no commit `ce939630363f8f762d0f0810a78735fe6975f7ff`; artefato `f7-custody-evidence-43782606042-1` (ID 14189245139, SHA256 `395c702f43ef39e16947bbac626c11d2e65f2420dc2dd631607e4c15808c5aed`).
- **Atestador e verificador** [#43782675357](https://github.com/hallanbrito/CHDevFlow/actions/runs/43782675357): jobs `sign` e `verify` success; ambos relataram `CUSTODY_VERIFIED` para o mesmo run de produtor. Artefato público `f7-custody-public-1` (ID 14188803542, SHA256 `77a59365505a718feb651692e73cbdb6e22ca74bc9c9196f033299e2b208d92a`). Não foi publicado secret privado.
- O PO consultou a configuração administrativa LIVE do Environment via `gh api`: `f7-attestor.can_admins_bypass=false`, `custom_branch_policies=true`, com política de deployment única para `main`. O ruleset da `main` e a regra de tags F7 também foram reconferidos. A conexão GitHub não acessa diretamente os endpoints administrativos do Environment; a evidência dessa parte provém da saída autenticada fornecida pelo PO.
- Negativas de admissão, SHA, secret ausente, metadados e ZIP adulterados, revogação e isolamento estático do workflow na [Draft PR #93](https://github.com/hallanbrito/CHDevFlow/pull/93), commit `4ebc54d3b20bdf1fc943b2230bbd5b1847ad7a7b`, [CI integral #43869659827](https://github.com/hallanbrito/CHDevFlow/actions/runs/43869659827): Linux e Windows **success**. A [prova LIVE negativa #43870850635](https://github.com/hallanbrito/CHDevFlow/actions/runs/43870850635) em branch diferente de `main` concluiu `skipped`: `sign=skipped`, `verify=skipped`, **zero artefatos**. Essa negativa valida o bloqueio do workflow atual, não comprova que qualquer workflow arbitrário malicioso estaria impedido de acessar o Environment. A homologação é decisão explícita do PO, não resultado automático de CI.

## Critérios de prova e reprodução (para nova homologação ou mudança sensível)

1. Dispare **F7 - Produtor de qualificacao da custodia** em `main`. Confira as três reprovações Docker, o run ID e o artefato `f7-custody-evidence-<run>-<attempt>`.
2. Após conferência manual do SHA e da identidade pelo PO, dispare **F7 - Custodia protegida do atestador** em `main` com esse run ID. No modo Solo não há aprovação adicional de revisor no Environment; a prova exige sucesso em `sign` e `verify` e somente o recibo e a chave pública no artefato do atestador.
3. Verifique que o workflow não executa assinatura fora da `main` e que a admissão rejeita run, SHA, ZIP ou fingerprint divergente. Registre o run ID, SHA, digest e fingerprint público na PR. Confirme as restrições LIVE do Environment e não confunda `skipped` do workflow com teste de um workflow arbitrário. Mudanças de política, código pinado ou modelo operacional exigem reavaliação antes de renovar o aceite.

Em rotação ou perda de custódia, pause novas assinaturas retirando o pin do atestador, acrescente o fingerprint antigo à lista de revogação e substitua a chave privada e a chave pública. Restaure o pin após revisar a política. Recibos que dependem da chave revogada são recusados pelo verificador. Preserve as evidências necessárias antes do vencimento da retenção dos artefatos.
