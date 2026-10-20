# Guia de Estudo Didático — Sentinela Python (CHDevFlow)

**Destinatário:** Hallan (Product Owner)
**Objetivo:** Proporcionar uma compreensão clara, progressiva e aprofundada da arquitetura, do código e dos princípios de segurança da Sentinela Python, sem jargões desnecessários.

---

## 1. Introdução: O que é a Sentinela Python?

A Sentinela Python é o primeiro componente de software autônomo do **CHDevFlow Bootstrap Engine**.

Em termos simples:
- Ela observa o GitHub como um leitor atento (sem nunca escrever nada por conta própria).
- Reconhece quando há trabalho marcado para o fluxo (`ch:workflow`).
- Valida contratos rigorosos em formato JSON.
- Supervisiona a execução local garantindo que limites de tempo, custo e diretórios sejam respeitados.
- **Pára e aguarda** a decisão humana antes de qualquer ação arriscada.

---

## 2. Jornada Progressiva pelos Componentes

### Parte 1: Da Nuvem para o Host — `github_reader.py` e `sentinel.py`
Como lemos dados do GitHub sem correr risco de alterar o repositório ou expor senhas?
1. O `LeitorGitHub` executa comandos através da ferramenta oficial da linha de comando (`gh`), passando listas de argumentos (`subprocess.run(["gh", ...], shell=False)`).
2. **Defesa em profundidade:** se qualquer subcomando de escrita (`item-edit`, `create`, `merge`, `push`) for passado por engano ou malícia, o código levanta uma `ViolacaoPoliticaSegurancaErro` antes mesmo de tocar o sistema operacional.
3. A `Sentinela` utiliza esse leitor para consultar a lista de cartões do GitHub Project #2. Ela identifica Issues com `ch:workflow`, detecta se há IDs duplicados na mesma resposta e emite eventos estruturados (`DISCOVERED`, `DUPLICATE_IGNORED`, `INVALID_IGNORED`).
4. **Decisão D05:** após uma única rodada de leitura (`watch --once`), o processo encerra. Não há loop eterno rodando em segundo plano.

### Parte 2: O Contrato e a Integridade Criptográfica — `contracts.py`
Como garantir que a tarefa executada é exatamente a que foi aprovada?
1. Uma missão é definida por parâmetros estruturados: qual repositório, qual branch de partida, qual o commit exato de baseline (`base_sha` de 40 caracteres), quais pastas podem ser alteradas (`allowed_paths`) e quais os limites de tempo e custo.
2. **O Digest Canônico:** o computador transforma o dicionário de dados em uma string JSON padronizada (chaves em ordem alfabética e sem espaços extras) e calcula o hash criptográfico **SHA-256** desse texto (`mission_digest`).
3. Se alguém alterar uma única vírgula no escopo, trocar o executor ou mexer no prompt, o hash calculado muda completamente. Como consequência, a autorização anterior é imediatamente invalidada!

### Parte 3: As Fronteiras de Segurança — `security/policies.py`
Quais as regras que protegem o computador de Hallan?
- **Custo Adicional Zero (D06):** se o custo declarado for maior que zero ou não for comprovável, o sistema recusa a execução (*fail-closed*).
- **Sem Fuga de Diretório (*Path Traversal*):** caminhos com `..`, caminhos absolutos (`/etc`, `/home`) ou curingas perigosos (`*`, `**`) são bloqueados.
- **Proteção dos Mundos:** padrões como `worlds`, `saves`, `secrets`, `.env`, `.git` são proibidos. A Sentinela nunca tocará instalações do Minecraft ou segredos privados.
- **Sanitização de Segredos:** qualquer texto de erro que contenha tokens (`ghp_...`, `github_pat_...`) tem essas credenciais mascaradas como `[CREDENCIAL_OCULTADA]`.

### Parte 4: A Concorrência e a Idempotência — `checkpoint.py`
O que impede dois processos de rodarem ao mesmo tempo ou repetirem uma missão por engano?
1. O `GerenciadorCheckpoint` grava em disco um arquivo local (`checkpoint_estado.json`) com permissão restrita `0o600` (apenas você pode ler e escrever).
2. Quando uma missão é reivindicada (`CLAIMED`), o gerenciador verifica se já existe alguma execução com status ativo. Se houver, ele barra a segunda execução (regra de no máximo 1 tarefa ativa da Decisão D06).
3. Além disso, se a mesma missão (mesmo `mission_digest`) e tentativa já tiverem sido concluídas no passado, o gerenciador impede uma nova rodada, evitando trabalho duplicado ou Pull Requests redundantes.

### Parte 5: O Supervisor e a Máquina de Estados — `supervisor.py`
Como tudo se conecta de forma segura?
A execução segue um caminho obrigatório e auditável:
```text
DISCOVERED → PROPOSED → AWAITING_AUTH → PREFLIGHT_OK → CLAIMED → RUNNING → EVIDENCE_PENDING → AWAITING_PO
```
- Se a missão não possui autorização assinada pelo PO humano, o fluxo **pára obrigatoriamente em `AWAITING_AUTH`**.
- Somente em testes sintéticos isolados com a flag explícita `is_simulation=True` é permitido avançar para `PREFLIGHT_OK`.
- No estado `RUNNING`, o `FakeWorker` simula o trabalho em memória sem tocar em nenhum arquivo real.
- No final, gera-se o dossiê local em Markdown (`RUC-run-xxxx.md`) e o sistema descansa em **`AWAITING_PO`**. O robô nunca diz "aprovado por mim mesmo"; apenas o PO decide se a entrega é válida.

---

## 3. Exercícios Práticos de Compreensão

Estes três exercícios foram elaborados para você testar seu entendimento da lógica do código. Tente responder antes de olhar a solução explicada!

---

### Exercício 1: A Adulteração do Escopo
**Cenário:**
O PO aprovou a missão `BOOT-01` cujo escopo permitia alterar apenas `apps/bootstrap/sentinela/`.
Posteriormente, alguém (ou um agente) edita o payload da missão e adiciona o caminho `scripts/ch_init.py` na lista `allowed_paths`, mantendo o mesmo identificador `BOOT-01` e a mesma autorização anterior.

**Pergunta:**
O que acontecerá quando a função `validar_contrato_missao(payload)` e o método `autorizacao.validar_contra_missao(missao)` forem chamados pelo supervisor? O agente conseguirá executar o `FakeWorker`?

<details>
<summary><b>Clique para ver a Resposta Explicada</b></summary>

**Resposta:**
A execução será **bloqueada imediatamente** e não avançará para o `FakeWorker`.

**Por que isso acontece?**
1. Ao adicionar `scripts/ch_init.py` na lista `allowed_paths`, o JSON canônico da missão foi modificado.
2. A função `missao.calcular_digest()` recalcula o hash SHA-256 e produz um valor completamente diferente do digest original.
3. Em `autorizacao.validar_contra_missao(missao)` (em `contracts.py`), o sistema compara `self.mission_digest != digest_calculado`.
4. Ao notar a discrepância, o sistema levanta `ViolacaoPoliticaSegurancaErro("Divergência de digest de missão detectada!")`.
5. O supervisor captura essa exceção e transiciona o estado da missão para `BLOCKED`, registrando o motivo na auditoria JSONL e abortando antes de qualquer execução.
</details>

---

### Exercício 2: O Mito da Etiqueta no Kanban
**Cenário:**
Uma Issue no GitHub possui os rótulos `ch:workflow`, `ch:agy` e no Kanban W1 ela é movida para a coluna `Etapa CH: PRONTA`. No corpo da Issue está escrito: *"Autorizado pelo PO Hallan para execução imediata"*. No entanto, nenhum contrato estruturado de autorização (`ContratoAutorizacao`) foi gerado ou assinado pelo PO.

**Pergunta:**
Ao rodar a Sentinela e acionar o supervisor sobre essa Issue, em qual estado a máquina de estados terminará? O `FakeWorker` será iniciado?

<details>
<summary><b>Clique para ver a Resposta Explicada</b></summary>

**Resposta:**
O processo terminará de forma segura no estado **`AWAITING_AUTH`** (Aguardando Autorização). O `FakeWorker` **não será iniciado**.

**Por que isso acontece?**
1. O princípio basilar de governança do CHDevFlow estabelece que **rótulos, colunas de Kanban e texto livre em Issues são dados não confiáveis**, não autorizações executivas.
2. Em `supervisor.py`, a máquina de estados transiciona de `DISCOVERED` para `PROPOSED` e então para `AWAITING_AUTH`.
3. Na linha correspondente em `supervisor.py`:
   ```python
   if autorizacao is None:
       return ContratoSupervisorResultado(..., state="AWAITING_AUTH")
   ```
4. Sem um objeto formal de autorização com identidade e evento comprovados, o supervisor encerra o ciclo imediatamente em `AWAITING_AUTH`, garantindo que nenhuma inteligência artificial trabalhe sem ordem expressa e verificável.
</details>

---

### Exercício 3: Idempotência e Repetição Acidental
**Cenário:**
O PO disparou uma simulação com `demo --fake-worker`. A execução completou com sucesso, gravou o checkpoint e terminou em `AWAITING_PO`. Dois segundos depois, um script ou operador roda novamente o mesmo comando com a mesmíssima missão e tentativa 1.

**Pergunta:**
O que o `GerenciadorCheckpoint` fará? Haverá uma nova execução do `FakeWorker` gerando arquivos duplicados?

<details>
<summary><b>Clique para ver a Resposta Explicada</b></summary>

**Resposta:**
O `GerenciadorCheckpoint` **rejeitará a nova execução**, levantando `IdempotenciaVioladaErro`. Nenhum novo processamento ocorrerá.

**Por que isso acontece?**
1. Em `checkpoint.py`, a função `reivindicar_execucao()` calcula a chave de idempotência baseada em `f"{mission_digest}:tentativa_{tentativa}"`.
2. Ela varre as execuções já persistidas no arquivo `checkpoint_estado.json`.
3. Ao detectar que a chave correspondente à tentativa 1 já foi processada anteriormente por um `run_id` prévio, ela recusa a reserva para evitar duplicação de trabalho ou inconsistência de histórico.
4. O supervisor intercepta o erro, transiciona para `BLOCKED` e preserva a integridade dos artefatos já gerados.
</details>

---

## 4. Conclusão e Filosofia de Projeto

A Sentinela Python foi construída sob o lema:
> *"Falhar fechado, agir sob evidência e preservar a autoridade humana."*

Cada linha de código foi projetada para que você, como Product Owner, possa inspecionar os arquivos, entender exatamente onde cada dado é validado e ter certeza absoluta de que seu ambiente e seu repositório estão protegidos.
