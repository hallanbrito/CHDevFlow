"""Smoke E2E executável contra o Control Center já iniciado em 127.0.0.1.

Uso (somente leitura no produto, exceto refresh de cache local):
    python -m pip install playwright
    python -m playwright install chromium
    python apps/control-center/tests/browser_smoke.py

Defina CH_CC_BASE_URL (default http://127.0.0.1:8000), CH_CC_BROWSER
(chromium/firefox) e CH_CC_SCREENSHOT_DIR para customizar. Não dispara agentes.
Não faz alterações em GitHub Project. Se falhar, sai com erro e relata Console.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("FALHA: falta Playwright. Instale com: python -m pip install playwright", file=sys.stderr)
        return 2

    base = os.environ.get("CH_CC_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    browser_name = os.environ.get("CH_CC_BROWSER", "chromium").strip().lower()
    pasta = Path(os.environ.get("CH_CC_SCREENSHOT_DIR", "/tmp/chdevflow-smoke"))
    pasta.mkdir(parents=True, exist_ok=True)
    console_errors: list[str] = []
    failed_requests: list[str] = []
    checks: list[str] = []
    try:
        with sync_playwright() as pw:
            factory = getattr(pw, browser_name)
            browser = factory.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            page.set_default_timeout(60000)
            page.on("pageerror", lambda error: console_errors.append(str(error)))
            page.on(
                "console",
                lambda msg: console_errors.append(msg.text) if msg.type == "error" else None,
            )
            page.on("requestfailed", lambda request: failed_requests.append(request.url))
            try:
                page.goto(base + "/", wait_until="domcontentloaded", timeout=75000)
                page.wait_for_function(
                    'document.documentElement.dataset.ccJsReady === "true"', timeout=10000
                )
                assert page.locator("#cc-js-health").is_hidden()
                checks.append("JavaScript inicializado e heartbeat OK")
                page.screenshot(path=str(pasta / "smoke_dashboard.png"))

                theme = page.locator('button[title="Alternar Modo Escuro / Claro"]')
                assert theme.count() == 1
                before = page.evaluate('document.documentElement.classList.contains("dark")')
                theme.click()
                after = page.evaluate('document.documentElement.classList.contains("dark")')
                assert before != after, "Botão de tema não reagiu"
                checks.append("Botão de tema funcional")

                page.goto(base + "/grafo", wait_until="domcontentloaded", timeout=75000)
                page.wait_for_function(
                    'document.documentElement.dataset.ccJsReady === "true"', timeout=10000
                )
                grafo = page.locator(".graph-node-card:visible")
                assert grafo.count() >= 1, "Nenhum cartão visível para abrir modal"
                grafo.first.click()
                dialog = page.locator("#modal-detalhes-missao.active")
                dialog.wait_for(state="visible")
                assert page.locator("#modal-node-title").inner_text().strip()
                page.keyboard.press("Escape")
                assert dialog.count() == 0, "Esc não fechou modal"
                checks.append("Cartão → modal → Esc")

                section = page.locator("#secao-dados-insuficientes")
                assert section.count() == 1
                assert not section.evaluate("(el) => el.open"), "Raia deveria começar fechada"
                section.locator("summary").click()
                assert section.evaluate("(el) => el.open"), "Raia não abriu"
                total = page.locator("#raia-dados-insuficientes .graph-node-card:visible").count()
                filtro = page.locator("#filtro-dados-insuficientes")
                filtro.fill("#5")
                filtrado = page.locator("#raia-dados-insuficientes .graph-node-card:visible").count()
                assert total >= filtrado > 0, f"Filtro falhou: {total} -> {filtrado}"
                assert filtrado < total, "Filtro não reduziu a lista"
                checks.append("Raia expandiu e filtro reagiu ao texto")
                page.screenshot(path=str(pasta / "smoke_grafo.png"))

                page.locator("#btn-atualizar-agora").click()
                page.wait_for_function(
                    'document.getElementById("sync-status-text").textContent !== "SYNCING" '
                    '&& document.getElementById("sync-label").textContent === "Atualizar agora"',
                    timeout=75000,
                )
                assert page.locator("#filtro-dados-insuficientes").input_value() == "#5", (
                    "Atualização perdeu o filtro"
                )
                assert page.locator("#secao-dados-insuficientes").evaluate("(el) => el.open"), (
                    "Atualização perdeu expansão da raia"
                )
                checks.append("Atualizar agora concluiu preservando busca e expansão")

                page.goto(base + "/missoes", wait_until="domcontentloaded", timeout=75000)
                page.locator('input[name="busca"]').fill("#7")
                assert "Missões Encontradas (1)" in page.locator("body").inner_text(), (
                    "Busca instantânea não filtrou a tabela"
                )
                checks.append("Busca instantânea reagiu sem botão")
                page.get_by_role("button", name="Filtrar", exact=True).click()
                assert "busca=%237" in page.url, f"Formulário GET não submeteu busca: {page.url}"
                assert "Missões Encontradas (1)" in page.locator("body").inner_text(), (
                    "Busca #7 não retornou uma missão"
                )
                checks.append("Busca por número de Issue via formulário GET")
                page.screenshot(path=str(pasta / "smoke_missoes.png"))

                relevantes = [erro for erro in console_errors if "favicon.ico" not in erro]
                assert not relevantes, f"Erros de console: {relevantes}"
                assert not failed_requests, f"Requisições falharam: {failed_requests}"
            finally:
                browser.close()
    except Exception as exc:
        print("FALHA E2E:", repr(exc), file=sys.stderr)
        for issue in console_errors[-20:]:
            print("CONSOLE:", issue, file=sys.stderr)
        for issue in failed_requests[-20:]:
            print("REQUISIÇÃO:", issue, file=sys.stderr)
        print("Verifique Network /static/js/app.js e Console do navegador.", file=sys.stderr)
        return 1

    for check in checks:
        print("PASSOU:", check)
    print("RESULTADO: E2E aprovado; evidências em", pasta)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
