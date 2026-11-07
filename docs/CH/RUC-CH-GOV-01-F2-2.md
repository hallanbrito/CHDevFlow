# RUC/1.0 — CH-GOV-01 / W-F2.2 (implementação CH-2)

- **PO:** aditamento autorizado para scripts/ch_project_assist.py, src/chdevflow/cli.py (roteamento somente), tests/test_ch_project_assist.py e dois documentos CH-GOV-01 F2.2.
- **Branch:** chatgpt/f2-2-project-admit.
- **Baseline:** main após merge da PR #65: 724386124415b54c04e7aa7e4760d7d0caac3766.
- **Entrega de código:** caminhos de admissão separados das funções legadas do KSYNC-03; plano canônico/digest; decisão de PO via comentário autenticado; CH-0 por menor privilégio; mutation GraphQL addProjectV2ItemById, campos via updateProjectV2ItemFieldValue, read-back após cada passo; CLI somente roteamento.
- **Testes:** fakes offline adicionados no arquivo de testes existente, sem nenhuma escrita LIVE. **CI/HEAD ainda pendentes de confirmação.**
- **Segurança:** sem autorização de execução; nenhuma etiqueta concede admissão; planos são rejeitados quando LIVE muda; não repetir mutação após timeout; cartão parcial exige reconciliação.
- **Project #2 real:** **nenhuma mutation executada**.
- **Agentes reais, deploy, release, merge:** não executados.
- **Custo adicional:** R$0, sem contratação de serviços.
- **Estado:** IMPLEMENTAÇÃO EM DRAFT / AWAITING_CI_AND_PO_AUDIT.
