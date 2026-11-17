# STATUS — CHDevFlow

**Atualizado:** 17/11/2026 (America/Fortaleza)  
**Referência:** [`main`](https://github.com/hallanbrito/CHDevFlow/tree/main) protegida. O GitHub é a fonte de verdade para HEAD, CI, PRs e Issues em andamento.

## ✅ Última entrega integrada
**CC-DESPACHO-01 — [PR #123](https://github.com/hallanbrito/CHDevFlow/pull/123) integrada à `main` em 17/11/2026**, por squash commit [`80dff4fc`](https://github.com/hallanbrito/CHDevFlow/commit/80dff4fcd694bbe5d7e07e5d9cb1468b6bbb3c96).

- **Produto:** Control Center local pode despachar missão por manifesto e acompanhar F6 → AGY → testes Python → Codex → dossiê, com autorização individual do PO e bloqueio fail-closed após crash.
- **Homologação:** funcional **somente em laboratório**. Piloto `PILOTO-CC-123`: 1 tentativa AGY, 0 devoluções, 3/3 testes de aceite, Codex textual `APROVAR_LAB`, integridade SHA256 e escopo Git conferidos pelo PO.
- **Qualidade:** 142 testes locais do Control Center aprovados (1 aviso); [CI pós-merge da `main`](https://github.com/hallanbrito/CHDevFlow/actions/runs/44152759648) concluída com `success`.

## ⚠️ Limites atuais
- **Não é ferramenta pronta para uso cotidiano:** exige preparar `CH-Lab-*`, prompt, testes independentes e manifesto JSON manualmente.
- `cost_verified=false`; `os_isolation_verified=false`; `test_execution=host`: não declarar custo zero nem isolamento de SO comprovado.
- Codex no piloto fez auditoria textual; o parecer não equivale a execução independente dos testes.
- Recuperação após crash exige intervenção humana segura; cancelamento avançado pela interface adiado.
- Sem liberação para produção, deploy, merge automático ou execução de agentes sem confirmação.

## 🎯 Próxima melhoria
**[Issue #124 — CC-USO-01](https://github.com/hallanbrito/CHDevFlow/issues/124):** preparar e validar missões úteis diretamente pela interface, sem edição manual de manifesto nem cópia de caminhos. **Backlog, implementação futura dependente de novo aceite do PO.**

## 📌 Regra permanente do STATUS.md
1. **Atualizar este arquivo na mesma PR que altera o estado do produto**, antes do merge; não deixar o status para uma PR corretiva posterior.
2. Registrar apenas **entregas integradas, limitações reais e próximo passo**. Uma PR ainda aberta não é descrita como entregue na `main`.
3. Após cada merge, conferir coerência entre `STATUS.md`, PR e CI; corrigir qualquer divergência pelo fluxo de PR da `main`, sem escrita direta ou bypass.
4. Evitar diário extenso: detalhes, logs e histórico permanecem nas Issues/PRs e no [RUC do piloto](docs/control-center/RUC-CC-DESPACHO-01-PILOTO-20261117.md).
