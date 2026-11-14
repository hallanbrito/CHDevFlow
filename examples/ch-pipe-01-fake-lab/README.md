# Laboratório descartável F4 — somente fakes

Este diretório contém apenas testes `unittest` fictícios. Nenhum segredo,
conta, configuração de login, Git interno ou arquivo real de repositório deve
ser copiado aqui. O comando `ch pipeline sandbox-plan` **apenas gera**
uma proposta de argv, e não inicia o Docker/Podman.

`--network none` torna o ensaio incapaz de chamar provedores externos:
isso é intencional, pois não há autorização para agentes reais.
A execução manual de um container dependerá da verificação do host,
imagem fixada e aprovação do PO.
