"""Módulo do Modo Estudante Didático (Glossário e Explicações Contextuais).

Implementa a ADR-BOOT01-01 e a aprovação formal da ADR-CC02-03 pelo PO:
Oferece explicações técnicas didáticas em português brasileiro, glossário contextual
e interpretação de estados, bloqueios e invariantes de governança do Método C.H.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class TermoGlossario:
    """Representa um conceito ou termo do Método C.H. explicado de forma didática."""

    id: str
    termo: str
    categoria: str               # Governança, Segurança, Criptografia, Fluxo
    resumo_curto: str
    explicacao_didatica: str
    exemplo_pratico: str
    regra_ou_adr: str

    def para_dicionario(self) -> dict[str, Any]:
        return asdict(self)


GLOSSARIO_METODO_CH: dict[str, TermoGlossario] = {
    "fail_closed": TermoGlossario(
        id="fail_closed",
        termo="Fail-Closed (Falha Fechada e Segura)",
        categoria="Segurança",
        resumo_curto="Se algo estiver incerto, incompleto ou duvidoso, o sistema pára e bloqueia.",
        explicacao_didatica=(
            "Em engenharia de software e segurança, 'fail-closed' é o princípio pelo qual um sistema, "
            "ao encontrar qualquer erro imprevisto, falta de permissão ou divergência de dados, "
            "adota o estado mais seguro possível: BLOQUEADO. Ele nunca tenta 'adivinhar' o que o humano queria, "
            "nem prossegue com dados parciais."
        ),
        exemplo_pratico=(
            "Se a Sentinela tentar ler o GitHub e a internet oscilar, ela não inventa tarefas falsas: "
            "ela encerra imediatamente com erro e zero tarefas descobertas (correção AUD-01)."
        ),
        regra_ou_adr="Decisão D06 e ADR-BOOT01-05",
    ),
    "mission_digest": TermoGlossario(
        id="mission_digest",
        termo="Digest Criptográfico (SHA-256)",
        categoria="Criptografia",
        resumo_curto="A impressão digital matemática imutável dos parâmetros de uma missão.",
        explicacao_didatica=(
            "O digest é um código de 64 caracteres hexadecimais gerado pelo algoritmo SHA-256 a partir "
            "do texto JSON canônico de uma tarefa. Se alguém alterar uma única letra no escopo, adicionar "
            "uma pasta ou trocar o executor, o hash muda por completo, invalidando qualquer autorização prévia."
        ),
        exemplo_pratico=(
            "Hash não é consentimento! O digest apenas prova que a tarefa não foi adulterada após a criação; "
            "ele não prova que o PO concordou com a execução até que haja uma assinatura formal."
        ),
        regra_ou_adr="Contrato W2-A e ch_sentinela.contracts",
    ),
    "fatia_w": TermoGlossario(
        id="fatia_w",
        termo="Fatia W (Work Slice)",
        categoria="Fluxo",
        resumo_curto="A menor unidade de trabalho autônoma, delimitada e verificável do Método C.H.",
        explicacao_didatica=(
            "Em vez de pedir aos agentes para 'fazerem o projeto inteiro', o trabalho é fatiado em partes "
            "pequenas (Fatias W), cada uma com escopo restrito de arquivos permitidos (allowed_paths), "
            "tempo limite (900s), critério de aceite claro e branch própria isolada."
        ),
        exemplo_pratico="A fatia CC-01 constrói apenas a interface web somente leitura; ela não executa robôs nem altera o servidor de produção.",
        regra_ou_adr="RFC-CH-DEVFLOW-001 (Seção 4)",
    ),
    "ciclo_chave": TermoGlossario(
        id="ciclo_chave",
        termo="Ciclo CHAVE",
        categoria="Governança",
        resumo_curto="Compreender, Hipotetizar, Agir, Verificar e Evoluir.",
        explicacao_didatica=(
            "É o ciclo metodológico que orienta o desenvolvimento assistido por IA: "
            "1. Compreender o contexto e as decisões canônicas; "
            "2. Hipotetizar a solução arquitetural; "
            "3. Agir dentro de limites estritos e isolamento; "
            "4. Verificar com testes e evidências reais (RUC/1.0); "
            "5. Evoluir sob decisão e aceite do Product Owner."
        ),
        exemplo_pratico="Primeiro planejamos documentalmente (CC-00.2 e CC-01), depois o PO homologa, e só então implementamos em branch isolada.",
        regra_ou_adr="RFC-CH-DEVFLOW-001 (Seção 1)",
    ),
    "idempotencia": TermoGlossario(
        id="idempotencia",
        termo="Idempotência Estrita",
        categoria="Segurança",
        resumo_curto="Executar uma ação 1 vez ou 10 vezes produz exatamente o mesmo resultado seguro.",
        explicacao_didatica=(
            "Uma operação é idempotente quando sua repetição não causa efeitos colaterais duplicados. "
            "Se o supervisor tentar processar uma missão que já foi concluída, o Checkpoint atômico "
            "detecta a repetição e impede a criação de Pull Requests redundantes ou retrabalho."
        ),
        exemplo_pratico="O comando watch --once pode ser rodado várias vezes sem nunca duplicar cartões no GitHub Project.",
        regra_ou_adr="ADR-BOOT01-03 e checkpoint.py",
    ),
    "autonomia_ch": TermoGlossario(
        id="autonomia_ch",
        termo="Níveis de Autonomia (CH-0 a CH-3)",
        categoria="Governança",
        resumo_curto="A gradação de poder concedida aos agentes de IA pelo humano.",
        explicacao_didatica=(
            "CH-0: Leitura e diagnóstico passivo, sem tocar arquivos; "
            "CH-1: Proposta documental, planejamento e criação de testes/documentos locais; "
            "CH-2: Implementação técnica de código em branch/worktree isolada com testes e Draft PR; "
            "CH-3: Autonomia assistida ampla com integração (sob supervisão direta do PO)."
        ),
        exemplo_pratico="Esta missão CC-01-IMPL é uma implementação delimitada sob branch curta isolada sem tocar na main.",
        regra_ou_adr="RFC-CH-DEVFLOW-001 (Seção 3)",
    ),
    "git_worktree": TermoGlossario(
        id="git_worktree",
        termo="Git Worktree (Isolamento de Checkout)",
        categoria="Fluxo",
        resumo_curto="Permite trabalhar em múltiplos branches ao mesmo tempo sem clonar o repositório do zero.",
        explicacao_didatica=(
            "Uma worktree compartilha a pasta .git principal, mas fornece uma pasta física independente no disco. "
            "Atenção: Worktree é isolamento de arquivos de checkout, NÃO É sandbox de segurança! "
            "Processos rodando na worktree ainda precisam de permissões de usuário restritas."
        ),
        exemplo_pratico="Criamos a pasta cc01_fundacao_somente_leitura para desenvolver o Control Center sem mexer na pasta onde está a branch main.",
        regra_ou_adr="Decisão D07 e MVP v0.2",
    ),
    "portao_criptografico": TermoGlossario(
        id="portao_criptografico",
        termo="Portão Criptográfico do PO (Gate CH-2)",
        categoria="Segurança",
        resumo_curto="A trava de segurança que impede robôs de se autoaprovarem ou rodarem sem consentimento.",
        explicacao_didatica=(
            "O portão de autorização exige que uma prova externa e autenticada de consentimento de Hallan "
            "seja vinculada matematicamente ao digest exato da missão. Clicar em botões da tela web não "
            "gera autorização válida se a prova criptográfica não for verificada pela Sentinela."
        ),
        exemplo_pratico="A decisão ADR-CC02-02 aprovou o conceito do portão, mantendo a implementação e testes para a fatia CC-02.",
        regra_ou_adr="ADR-CC02-02 e Condicionante C01",
    ),
}


EXPLICACOES_ESTADOS_MAQUINA: dict[str, dict[str, str]] = {
    "DISCOVERED": {
        "titulo": "Tarefa Descoberta no GitHub",
        "o_que_significa": "A Sentinela encontrou um cartão no GitHub Project marcado com 'ch:workflow'.",
        "acao_do_sistema": "Lê os campos da Issue sem fazer nenhuma alteração remota.",
        "por_que_seguro": "Operação 100% somente leitura.",
    },
    "PROPOSED": {
        "titulo": "Missão Analisada e Contrato Validado",
        "o_que_significa": "O Contrato de Missão passou pela validação rigorosa de schema, baseline SHA e limites.",
        "acao_do_sistema": "Calcula o mission_digest SHA-256 e confere se não há pastas proibidas.",
        "por_que_seguro": "Qualquer dado incorreto ou pasta sensível causa bloqueio imediato (fail-closed).",
    },
    "AWAITING_AUTH": {
        "titulo": "Aguardando Autorização Formal do PO",
        "o_que_significa": "A tarefa é elegível, mas NÃO TEM autorização de execução emitida pelo humano.",
        "acao_do_sistema": "O fluxo PÁRA obrigatoriamente aqui. Nenhum robô pode iniciar ferramentas.",
        "por_que_seguro": "Garante que robôs nunca se autoaprovem nem gastem tempo sem consentimento de Hallan.",
    },
    "PREFLIGHT_OK": {
        "titulo": "Verificações Pré-Execução Concluídas",
        "o_que_significa": "A autorização do PO foi conferida, o custo é R$ 0,00 e o host está disponível.",
        "acao_do_sistema": "Prepara a worktree isolada e reserva o lock de concorrência.",
        "por_que_seguro": "Confirma que não há APIs pagas nem tarefas simultâneas no host.",
    },
    "CLAIMED": {
        "titulo": "Reserva Exclusiva de Execução (Lock = 1)",
        "o_que_significa": "A tarefa registrou posse temporária no Checkpoint com permissão restrita 0o600.",
        "acao_do_sistema": "Impede qualquer outra tarefa de rodar ao mesmo tempo no CachyOS (Decisão D06).",
        "por_que_seguro": "Concorrência máxima = 1; zero corrida de arquivos.",
    },
    "RUNNING": {
        "titulo": "Em Execução Supervisionada",
        "o_que_significa": "O worker está trabalhando dentro dos limites restritos de tempo (900s) e pastas autorizadas.",
        "acao_do_sistema": "O supervisor monitora o cronômetro e cancela imediatamente se passar de 15 minutos.",
        "por_que_seguro": "Cancelamento forçado via SIGTERM/SIGKILL disponível a qualquer momento.",
    },
    "EVIDENCE_PENDING": {
        "titulo": "Coleta e Sanitização de Evidências",
        "o_que_significa": "O trabalho terminou e o sistema está reunindo os resultados dos testes e diffs.",
        "acao_do_sistema": "Mascara tokens e credenciais antes de gravar o relatório RUC/1.0.",
        "por_que_seguro": "Zero vazamento de senhas ou caminhos privados nos relatórios.",
    },
    "AWAITING_PO": {
        "titulo": "Aguardando Avaliação e Decisão de Hallan",
        "o_que_significa": "O dossiê completo foi gerado e está pronto para o humano inspecionar no GitHub.",
        "acao_do_sistema": "Não faz merge! O robô descansa e aguarda o parecer do Product Owner.",
        "por_que_seguro": "Somente Hallan tem a autoridade de aprovar, solicitar ajustes ou integrar na main.",
    },
    "BLOCKED": {
        "titulo": "Execução Bloqueada com Segurança",
        "o_que_significa": "Uma regra de segurança foi violada (tentativa de tocar em saves, custo > 0, hash alterado).",
        "acao_do_sistema": "Interrupção imediata, registro do incidente na auditoria e preservação do host.",
        "por_que_seguro": "Princípio Fail-Closed em ação para proteger seu computador.",
    },
}


def obter_glossario_completo() -> list[dict[str, Any]]:
    """Retorna todos os termos do glossário formatados em lista de dicionários."""
    return [termo.para_dicionario() for termo in GLOSSARIO_METODO_CH.values()]


def obter_termo_por_id(termo_id: str) -> dict[str, Any] | None:
    """Retorna um termo específico pelo seu identificador ou None se não existir."""
    termo = GLOSSARIO_METODO_CH.get(termo_id.lower().strip())
    return termo.para_dicionario() if termo else None


def obter_explicacao_estado(estado: str) -> dict[str, str] | None:
    """Retorna as informações didáticas sobre um estado da máquina de governança."""
    return EXPLICACOES_ESTADOS_MAQUINA.get(estado.upper().strip())

