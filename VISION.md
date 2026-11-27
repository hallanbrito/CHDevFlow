# CHDevFlow — AI Software Factory

Decisão de produto de 27/11/2026. Nova direção aprovada pelo responsável humano; detalhes técnicos sujeitos a auditoria.

## Visão
Uma fábrica de software local-first, open source, multiagente e independente de fornecedor. O usuário descreve uma necessidade, configura as IAs que ocupam cargos predefinidos, acompanha reuniões, aprova decisões e recebe software executável com testes e evidências.

## Princípios
- Cargo permanente, modelo substituível: perfil, modelo, esforço, ferramentas e permissões independentes.
- BYOM: preferir CLIs oficiais e ACP quando suportado; não presumir custo zero nem contornar limites contratuais.
- Maestro recomenda e coordena; motor determinístico valida estados, permissões e aprovações.
- Colaboração com mensagens persistentes, tarefas e entregáveis, não conversas infinitas.
- Docker obrigatório para execução autônoma e testes não confiáveis; isolamento comprovado antes de liberar execução.
- KISS, segurança desde o início, GitHub como fonte de verdade, aprovação humana de alterações sensíveis.

## MVP
Maestro, Arquiteto (inclui levantamento de requisitos com humano), Desenvolvedor e QA independente. Duas integrações de IA verificadas, reunião limitada, plano aprovado, implementação em workspace isolado, testes, patch e dossiê. Sem merge ou deploy automático. Expandir posteriormente para PO, Tech Lead, UX/UI, frontend, backend, segurança e DevOps.

## Não objetivos iniciais
Microsserviços, execução 24/7, produção autônoma, fallback pago, catálogo indiscriminado, fine-tuning sem dados e métricas.
