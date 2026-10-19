# Prompts e Diretrizes de Instrução — Módulo Sentinela

Este diretório armazena e documenta a estrutura dos prompts de missão utilizados no âmbito do **CHDevFlow Bootstrap Engine**.

---

## 1. O Papel dos Prompts no Método C.H.

No ecossistema CHDevFlow, um **prompt não é um comando com privilégios de execução**.

O texto de uma Issue ou de um arquivo de instrução é classificado tecnicamente como **dado de entrada não confiável**:
1. Um prompt não pode ampliar o escopo de arquivos permitidos (`allowed_paths`).
2. Um prompt não pode revogar regras de segurança (*fail-closed*), contornar sandboxes ou solicitar autorizações elevadas.
3. Um prompt não pode autorizar a própria execução nem conter assinaturas válidas de aprovação executiva.

---

## 2. Imutabilidade e Rastreabilidade

Cada missão executada sob o Bootstrap Engine faz referência explícita a uma instrução canônica através do campo:
```json
"instruction_ref": "docs/bootstrap/BOOT-00-CONTRATOS.md"
```

O hash criptográfico SHA-256 (`mission_digest`) é calculado sobre todo o conjunto de parâmetros da missão, incluindo a referência da instrução. Qualquer alteração no texto do prompt ou na instrução após a aprovação do Product Owner **invalida automaticamente a autorização anterior**, exigindo novo ciclo de revisão humana.

---

## 3. Instruções em Português Brasileiro

Seguindo o padrão de didática do projeto, prompts destinados aos executores devem ser redigidos em **português brasileiro (pt-BR)** com foco em clareza, especificidade, delimitação de fronteiras e definição inequívoca dos critérios de aceite.
