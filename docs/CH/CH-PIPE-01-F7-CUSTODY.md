# F7 Gate 1 — custódia protegida do atestador

O produtor executa a qualificação Docker em `main` e publica apenas evidências da sonda. O atestador consulta a API, valida a origem e o ZIP e assina em outro runner. Um terceiro runner consulta as evidências novamente e verifica o recibo com a chave pública. O publicador rejeita recibos de qualificação. O cenário usa um fornecedor determinístico de código e executa o ciclo de reprovação real em Docker.

## Provisionamento administrativo

1. Após autorização separada para integrar os workflows, confirme que `main` exige PR e revisão independente para mudanças no código executado pelo atestador e nos workflows. O ruleset anterior exige PR, com zero revisões obrigatórias. Restrinja quem pode alterar a configuração da regra e as variáveis do repositório.
2. Em **Settings → Environments**, crie `f7-attestor`. Em **Deployment branches and tags**, selecione exclusivamente a branch `main`. Configure revisor autorizado, impeça a autorrevisão e desative o bypass administrativo da proteção. Mantenha a chave privada exclusivamente no secret **do environment** `CH_F7_SIGNING_KEY`. O produtor, a CI de PR e o verificador não recebem o secret. Confira a proteção antes de inserir a chave.
3. Na estação sob custódia, gere uma chave dedicada Ed25519 sem passphrase para consumo não interativo. Guarde-a fora do repositório em diretório com acesso restrito ao custodiante. Exemplo em PowerShell, substituindo o caminho por um diretório privado já existente:

   ```powershell
   $f7Key = Join-Path $env:LOCALAPPDATA 'CHDevFlow-Custodia\ch-f7-ed25519'
   ssh-keygen -t ed25519 -N '' -C 'CHDevFlow F7 attestor' -f $f7Key
   Get-Content -Raw -LiteralPath $f7Key |
     gh secret set CH_F7_SIGNING_KEY --env f7-attestor --repo hallanbrito/CHDevFlow
   ssh-keygen -lf "$f7Key.pub"
   ```

   Confira o fingerprint da chave pública com o custodiante por um canal independente. Preserve uma cópia privada conforme a política de custódia. A chave privada deve ficar fora de logs, artefatos, comentários e commits.
4. Em **Settings → Secrets and variables → Actions → Variables**, configure estes valores por meio da conta administrativa:

   | Variável | Valor |
   | --- | --- |
   | `CH_F7_TRUSTED_RUNNER_PUBKEY` | Dois campos da chave pública verificada, no formato `ssh-ed25519 <base64>` |
   | `CH_F7_TRUSTED_RUNNER_SHA` | SHA completo revisado do produtor em `main` |
   | `CH_F7_PRODUCER_WORKFLOW_ID` | ID numérico de `gh workflow view f7-custody-producer.yml --repo hallanbrito/CHDevFlow --json id --jq .id` |
   | `CH_F7_ATTESTOR_SHA` | SHA completo revisado do atestador em `main` |
   | `CH_F7_REVOKED_RUNNER_FINGERPRINTS` | `NONE` inicialmente, ou fingerprints OpenSSH `SHA256:…` separados por espaços |

   Uma mudança no HEAD de `main` exige nova revisão antes de atualizar os SHAs. Os jobs bloqueiam execuções cujo SHA difere da política.

## Prova para aceite

1. Dispare **F7 - Produtor de qualificacao da custodia** em `main`. Confira as três reprovações Docker, o run ID e o artefato `f7-custody-evidence-<run>-<attempt>`.
2. Dispare **F7 - Custodia protegida do atestador** em `main` com esse run ID. O revisor compara o SHA e a identidade do workflow antes de liberar o environment. A prova exige sucesso em `sign` e `verify` e somente o recibo e a chave pública no artefato do atestador.
3. Verifique que uma execução de PR não consegue usar o environment e que a admissão rejeita run, SHA, ZIP ou fingerprint divergente. Registre o run ID, o SHA, o digest do artefato e o fingerprint público na PR.

Em rotação ou perda de custódia, pause novas assinaturas retirando o pin do atestador, acrescente o fingerprint antigo à lista de revogação e substitua a chave privada e a chave pública. Restaure o pin após revisar a política. Recibos que dependem da chave revogada são recusados pelo verificador. Preserve as evidências necessárias antes do vencimento da retenção dos artefatos.
