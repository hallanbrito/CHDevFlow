// CHDevFlow Control Center — Funções Interativas do Frontend

document.addEventListener("DOMContentLoaded", () => {
  inicializarTema();
});

// Gerenciamento de Tema (Dark Mode / Light Mode)
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

// Controle de Modais
function abrirModal(modalId) {
  const modal = document.getElementById(modalId);
  if (modal) {
    modal.classList.add("active");
  }
}

function fecharModal(modalId) {
  const modal = document.getElementById(modalId);
  if (modal) {
    modal.classList.remove("active");
  }
}

// Fechar modal ao clicar fora
window.addEventListener("click", (event) => {
  if (event.target.classList.contains("modal-overlay")) {
    event.target.classList.remove("active");
  }
});
