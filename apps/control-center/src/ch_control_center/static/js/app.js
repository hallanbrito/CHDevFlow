// CHDevFlow Control Center — Funções Interativas do Frontend (CC-QUALITY-01)

let ultimoElementoFocado = null;
let isSyncing = false;
let syncSeq = 0;
let pollingIntervalId = null;
let ultimoSucessoTimestamp = Date.now();

document.addEventListener("DOMContentLoaded", () => {
  const aviso = document.getElementById("cc-js-health");
  try {
    inicializarTema();
    inicializarSincronizacao();
    inicializarAcessibilidadeModais();
    inicializarFiltroDadosInsuficientes();
    inicializarBuscaInstantaneaMissoes();
    document.documentElement.dataset.ccJsReady = "true";
    if (aviso) aviso.style.display = "none";
  } catch (erro) {
    console.error("CHDevFlow: falha ao inicializar controles da interface", erro);
    if (aviso) aviso.textContent = "⚠️ Falha na inicialização do painel. Abra o Console (F12).";
  }
});

// --- Gerenciamento de Tema (Dark Mode / Light Mode) ---
function inicializarTema() {
  const temaSalvo = localStorage.getItem("ch_cc_theme");
  const prefereEscuro = window.matchMedia("(prefers-color-scheme: dark)").matches;

  if (temaSalvo === "dark" || (!temaSalvo && prefereEscuro)) {
    document.documentElement.classList.add("dark");
  } else {
    document.documentElement.classList.remove("dark");
  }
}

function alternarTema() {
  const html = document.documentElement;
  if (html.classList.contains("dark")) {
    html.classList.remove("dark");
    localStorage.setItem("ch_cc_theme", "light");
  } else {
    html.classList.add("dark");
    localStorage.setItem("ch_cc_theme", "dark");
  }
}

// --- Controle de Modais e Acessibilidade (F3) ---
function abrirModal(modalId) {
  const modal = document.getElementById(modalId);
  if (modal) {
    ultimoElementoFocado = document.activeElement;
    modal.classList.add("active");
    const closeBtn = modal.querySelector(".modal-close-btn") || modal.querySelector("button");
    if (closeBtn) closeBtn.focus();
  }
}

function fecharModal(modalId) {
  const modal = document.getElementById(modalId);
  if (modal) {
    modal.classList.remove("active");
    if (ultimoElementoFocado && typeof ultimoElementoFocado.focus === "function") {
      ultimoElementoFocado.focus();
    }
  }
}

function fecharModalDetalhesMissao() {
  fecharModal("modal-detalhes-missao");
}

function abrirModalDetalhesMissao(elemento) {
  if (!elemento) return;
  const rawData = elemento.getAttribute("data-node");
  if (!rawData) return;

  try {
    const no = JSON.parse(rawData);
    ultimoElementoFocado = elemento;

    // Preenche os campos do modal
    const elTitulo = document.getElementById("modal-node-title");
    const elIssue = document.getElementById("modal-node-issue");
    const elIssueLink = document.getElementById("modal-node-issue-link");
    const elStatus = document.getElementById("modal-node-status");
    const elEtapa = document.getElementById("modal-node-etapa");
    const elEsteira = document.getElementById("modal-node-esteira");
    const elAutonomia = document.getElementById("modal-node-autonomia");
    const elMotivo = document.getElementById("modal-node-motivo");
    const elCausas = document.getElementById("modal-node-causas");
    const elDeps = document.getElementById("modal-node-deps");
    const elHomologacao = document.getElementById("modal-node-homologacao");
    const elProvenance = document.getElementById("modal-node-provenance");
    const elIdInterno = document.getElementById("modal-node-id-interno");

    if (elTitulo) elTitulo.textContent = no.titulo || "Sem título";

    const issueNum = no.numero_issue;
    if (elIssue) elIssue.textContent = issueNum ? `#${issueNum}` : no.id;
    if (elIssueLink) {
      if (issueNum) {
        elIssueLink.href = `https://github.com/hallanbrito/CHDevFlow/issues/${issueNum}`;
        elIssueLink.style.display = "inline";
      } else {
        elIssueLink.style.display = "none";
      }
    }

    if (elStatus) {
      elStatus.textContent = no.status_grafo || "PENDENTE";
      elStatus.className = `badge-status badge-${(no.status_grafo || "").toLowerCase().replace(/_/g, "-")}`;
    }

    if (elEtapa) elEtapa.textContent = no.etapa_ch || "NAO_INFORMADA";
    if (elEsteira) elEsteira.textContent = no.esteira || "NAO_INFORMADA";
    if (elAutonomia) elAutonomia.textContent = no.autonomia || "NAO_INFORMADA";

    if (elMotivo) {
      if (no.motivo_bloqueio) {
        elMotivo.textContent = no.motivo_bloqueio;
        elMotivo.parentElement.style.display = "block";
      } else {
        elMotivo.parentElement.style.display = "none";
      }
    }

    if (elCausas) {
      elCausas.innerHTML = "";
      const causas = no.causas_diagnosticas || [];
      if (causas.length > 0) {
        causas.forEach(c => {
          const badge = document.createElement("span");
          badge.className = "badge-causa";
          badge.textContent = c;
          badge.style.marginRight = "0.4rem";
          elCausas.appendChild(badge);
        });
        elCausas.parentElement.style.display = "block";
      } else {
        elCausas.parentElement.style.display = "none";
      }
    }

    if (elDeps) {
      elDeps.innerHTML = "";
      const refs = no.dependency_refs || [];
      const state = no.dependency_state || "UNKNOWN";
      const pState = document.createElement("div");
      pState.style.fontSize = "0.8rem";
      pState.style.marginBottom = "0.4rem";
      pState.innerHTML = `<strong>Estado de Dependências:</strong> <code>${state}</code>`;
      elDeps.appendChild(pState);

      if (refs.length > 0) {
        const ul = document.createElement("ul");
        ul.style.marginLeft = "1.2rem";
        ul.style.fontSize = "0.8rem";
        refs.forEach(ref => {
          const li = document.createElement("li");
          const a = document.createElement("a");
          a.href = ref.url;
          a.target = "_blank";
          a.rel = "noopener noreferrer";
          a.textContent = ref.issue_ref;
          li.appendChild(a);
          li.append(` (${ref.state || "UNKNOWN"})`);
          ul.appendChild(li);
        });
        elDeps.appendChild(ul);
      } else if (state === "VERIFIED_EMPTY") {
        const pVazio = document.createElement("div");
        pVazio.style.fontSize = "0.8rem";
        pVazio.style.color = "var(--text-muted)";
        pVazio.textContent = "Sem dependências declaradas (relação blocked_by vazia verificada).";
        elDeps.appendChild(pVazio);
      }
    }

    if (elHomologacao) {
      if (no.homologacao_verificada) {
        elHomologacao.innerHTML = `<span style="color: var(--status-concluida); font-weight: 700;">✓ Homologação Humana Verificada</span>`;
      } else {
        elHomologacao.innerHTML = `<span style="color: var(--status-bloqueada); font-weight: 600;">⚠️ Homologação Humana Não Verificada (Bloqueio Preventivo Fail-Closed)</span>`;
      }
    }

    if (elProvenance) {
      elProvenance.textContent = `Fonte: ${no.dependency_source || "não informada"} | Observado em: ${no.dependency_observed_at || "não informado"}`;
    }

    if (elIdInterno) {
      elIdInterno.textContent = no.id || "-";
    }

    const modal = document.getElementById("modal-detalhes-missao");
    if (modal) {
      modal.classList.add("active");
      const closeBtn = modal.querySelector(".modal-close-btn");
      if (closeBtn) closeBtn.focus();
    }
  } catch (err) {
    console.error("Erro ao abrir modal de detalhes da missão:", err);
  }
}

function inicializarAcessibilidadeModais() {
  // Fechar com Escape
  window.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      const activeModal = document.querySelector(".modal-overlay.active");
      if (activeModal) {
        fecharModal(activeModal.id);
      }
    }
  });

  // Fechar ao clicar fora do modal-content
  window.addEventListener("click", (event) => {
    if (event.target.classList.contains("modal-overlay")) {
      fecharModal(event.target.id);
    }
  });

  // Teclado (Enter ou Espaço) em cartões clicáveis
  document.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      const target = e.target.closest(".clickable-card");
      if (target) {
        e.preventDefault();
        abrirModalDetalhesMissao(target);
      }
    }
  });
}

// --- Filtro e Busca na Raia 4 "Dados Insuficientes" (F3) ---
function inicializarFiltroDadosInsuficientes() {
  const inputFiltro = document.getElementById("filtro-dados-insuficientes");
  if (!inputFiltro) return;

  inputFiltro.addEventListener("input", (e) => {
    const termo = e.target.value.toLowerCase().trim();
    const container = document.getElementById("raia-dados-insuficientes");
    if (!container) return;

    const cards = container.querySelectorAll(".graph-node-card");
    let visiveis = 0;

    cards.forEach(card => {
      const texto = card.textContent.toLowerCase();
      if (!termo || texto.includes(termo)) {
        card.style.display = "";
        visiveis++;
      } else {
        card.style.display = "none";
      }
    });

    const contadorEl = document.getElementById("contador-filtro-dados");
    if (contadorEl) {
      contadorEl.textContent = termo ? `(${visiveis} visíveis de ${cards.length})` : `(${cards.length})`;
    }
  });
}

// --- Busca imediata e acessível na tabela de Missões (fallback GET disponível) ---
function inicializarBuscaInstantaneaMissoes() {
  const campo = document.getElementById("busca");
  const linhas = document.querySelectorAll(".table-responsive tbody tr");
  if (!campo || !linhas.length) return;
  const contador = document.getElementById("contador-missoes");
  const vazia = document.getElementById("mensagem-busca-vazia");
  const aplicar = () => {
    const termo = campo.value.trim().toLocaleLowerCase("pt-BR");
    let visiveis = 0;
    linhas.forEach((linha) => {
      const encontrado = !termo || linha.textContent.toLocaleLowerCase("pt-BR").includes(termo);
      linha.style.display = encontrado ? "" : "none";
      if (encontrado) visiveis++;
    });
    if (contador) contador.textContent = "Missões Encontradas (" + visiveis + ")";
    if (vazia) vazia.style.display = visiveis === 0 ? "block" : "none";
  };
  campo.addEventListener("input", aplicar);
  if (campo.value.trim()) aplicar();
}

// --- Sincronização UX & Polling Econômico 60s (F4) ---
function inicializarSincronizacao() {
  const modoMeta = document.querySelector('meta[name="modo-operacao"]');
  const modoOperacao = modoMeta ? modoMeta.getAttribute("content") : "DEMO_OFFLINE";

  // O horário vem da última leitura confirmada pelo servidor, não da abertura da página.
  const ultimaLeitura = document.querySelector('meta[name="cc-last-success"]')?.content;
  const timestamp = ultimaLeitura ? Date.parse(ultimaLeitura) : NaN;
  ultimoSucessoTimestamp = Number.isFinite(timestamp) ? timestamp : 0;

  // Polling automático de 60 segundos APENAS no modo LIVE_GITHUB
  if (modoOperacao === "LIVE_GITHUB") {
    iniciarPolling();

    // Pausar polling se a aba estiver oculta e retomar quando visível
    document.addEventListener("visibilitychange", () => {
      if (document.hidden) {
        pararPolling();
      } else {
        iniciarPolling();
        // Se já passou mais de 60s desde a última atualização, sincroniza ao retornar
        if (Date.now() - ultimoSucessoTimestamp > 60000) {
          executarSincronizacao(false);
        }
      }
    });
  }
}

function iniciarPolling() {
  if (pollingIntervalId) clearInterval(pollingIntervalId);
  pollingIntervalId = setInterval(() => {
    if (!document.hidden && !isSyncing) {
      executarSincronizacao(false);
    }
  }, 60000);
}

function pararPolling() {
  if (pollingIntervalId) {
    clearInterval(pollingIntervalId);
    pollingIntervalId = null;
  }
}

function atualizarIndicadorUi(status, mensagem) {
  const badge = document.getElementById("sync-indicator");
  const textEl = document.getElementById("sync-status-text");
  const labelEl = document.getElementById("sync-label");
  const iconEl = document.getElementById("sync-icon");

  const st = (status || "OK").toUpperCase();
  if (badge) {
    badge.className = `sync-status-badge sync-${st.toLowerCase()}`;
    badge.title = `Estado da sincronização: ${st}${mensagem ? ` — ${mensagem}` : ""}`;
  }
  if (textEl) {
    textEl.textContent = st;
  }

  if (st === "SYNCING") {
    if (labelEl) labelEl.textContent = "Sincronizando...";
    if (iconEl) iconEl.textContent = "⏳";
  } else {
    if (labelEl) labelEl.textContent = "Atualizar agora";
    if (iconEl) iconEl.textContent = "🔄";
  }
}

async function acionarSincronizacaoManual() {
  if (isSyncing) return;
  await executarSincronizacao(true);
}

// Atualiza o HTML usando o snapshot já sincronizado, sem recarregar a aba.
// Preserva consulta de filtros, expansão da raia, modal ativo e posição de leitura.
async function atualizarConteudoVisivel() {
  const mainAtual = document.querySelector("main.content-area");
  if (!mainAtual) return;

  const scrollX = window.scrollX;
  const scrollY = window.scrollY;
  const filtroAntes = document.getElementById("filtro-dados-insuficientes");
  const buscaAntes = filtroAntes ? filtroAntes.value : "";
  const camposMissao = ["busca", "status", "esteira"].map(id => ({
    id, valor: document.getElementById(id)?.value,
  }));
  const raiaAntes = document.getElementById("secao-dados-insuficientes");
  const raiaAberta = raiaAntes ? raiaAntes.open : false;
  const modalAntes = document.querySelector(".modal-overlay.active");
  const modalId = modalAntes?.id || null;
  let noAberto = null;
  if (modalId === "modal-detalhes-missao") {
    try { noAberto = JSON.parse(ultimoElementoFocado?.getAttribute("data-node") || "{}").id; }
    catch (_) { noAberto = null; }
  }

  const resp = await fetch(window.location.pathname + window.location.search, { cache: "no-store" });
  if (!resp.ok) throw new Error("Não foi possível atualizar a visualização com os dados recentes.");
  const documento = new DOMParser().parseFromString(await resp.text(), "text/html");
  const mainNovo = documento.querySelector("main.content-area");
  if (!mainNovo) throw new Error("A resposta da atualização não contém o conteúdo esperado.");

  mainAtual.replaceWith(mainNovo);
  inicializarFiltroDadosInsuficientes();
  inicializarBuscaInstantaneaMissoes();
  for (const campo of camposMissao) {
    const novo = document.getElementById(campo.id);
    if (novo && campo.valor != null) novo.value = campo.valor;
  }
  const buscaRestaurada = document.getElementById("busca");
  if (buscaRestaurada) buscaRestaurada.dispatchEvent(new Event("input", { bubbles: true }));

  const filtroNovo = document.getElementById("filtro-dados-insuficientes");
  if (filtroNovo && filtroAntes) {
    filtroNovo.value = buscaAntes;
    filtroNovo.dispatchEvent(new Event("input", { bubbles: true }));
  }
  const raiaNova = document.getElementById("secao-dados-insuficientes");
  if (raiaNova && raiaAntes) raiaNova.open = raiaAberta;

  if (modalId === "modal-detalhes-missao" && noAberto) {
    const cartaoNovo = [...document.querySelectorAll(".graph-node-card[data-node]")].find(el => {
      try { return JSON.parse(el.getAttribute("data-node")).id === noAberto; }
      catch (_) { return false; }
    });
    if (cartaoNovo) abrirModalDetalhesMissao(cartaoNovo);
  } else if (modalId) {
    const modalNovo = document.getElementById(modalId);
    if (modalNovo && modalNovo.querySelector("h3")?.textContent === modalAntes.querySelector("h3")?.textContent) {
      modalNovo.classList.add("active");
      modalNovo.querySelector("button")?.focus();
    }
  }
  window.scrollTo(scrollX, scrollY);
}

async function executarSincronizacao(manual = false) {
  if (isSyncing) return;
  isSyncing = true;
  const currentSeq = ++syncSeq;

  atualizarIndicadorUi("SYNCING");

  const csrfMeta = document.querySelector('meta[name="csrf-token"]');
  const csrfToken = csrfMeta ? csrfMeta.getAttribute("content") : "";

  try {
    const res = await fetch("/api/sincronizar", {
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
        "X-CSRF-Token": csrfToken,
      },
      body: `csrf_token=${encodeURIComponent(csrfToken)}`,
    });

    // Proteção contra respostas fora de ordem (race conditions)
    if (currentSeq !== syncSeq) {
      return;
    }

    const data = await res.json();

    if (res.ok && (data.status === "OK" || data.status === "PARTIAL")) {
      const registrado = Date.parse(data.estado?.last_success_at || "");
      if (Number.isFinite(registrado)) ultimoSucessoTimestamp = registrado;
      atualizarIndicadorUi(data.status, data.estado?.diagnostic);

      const idAnterior = document.querySelector('meta[name="cc-snapshot-id"]')?.content || "";
      const idAtual = data.estado?.snapshot_id || "";
      if (manual || idAtual !== idAnterior) {
        await atualizarConteudoVisivel();
        const meta = document.querySelector('meta[name="cc-snapshot-id"]');
        if (meta) meta.content = idAtual;
      }
    } else {
      const st = data.estado && data.estado.status ? data.estado.status : "ERROR";
      atualizarIndicadorUi(st, data.erro || "Falha na sincronização");
    }
  } catch (err) {
    if (currentSeq === syncSeq) {
      console.warn("Erro ao sincronizar com servidor local:", err);
      atualizarIndicadorUi("ERROR", err.message);
    }
  } finally {
    if (currentSeq === syncSeq) {
      isSyncing = false;
    }
  }
}
