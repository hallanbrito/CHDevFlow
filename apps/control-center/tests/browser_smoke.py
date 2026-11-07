"""Smoke E2E executável contra o Control Center já iniciado em 127.0.0.1.

Uso (somente leitura no produto, exceto refresh de cache local):
    python -m pip install playwright
    python -m playwright install chromium firefox
    python apps/control-center/tests/browser_smoke.py

Defina CH_CC_BASE_URL (default http://127.0.0.1:8000), CH_CC_BROWSER
(chromium/firefox) e CH_CC_SCREENSHOT_DIR para customizar. Não dispara agentes.
Não faz alterações em GitHub Project. Executa sob a CSP estrita de produção
(sem bypass_csp), sem eval(), com validação explícita de status HTTP/JSON do sync.
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
    http_errors: list[str] = []
    checks: list[str] = []
    try:
        with sync_playwright() as pw:
            factory = getattr(pw, browser_name)
            browser = factory.launch(headless=True)
            # GATE-1: Executa estritamente sob a CSP de produção, sem bypass_csp
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            page.set_default_timeout(60000)
            page.on("pageerror", lambda error: console_errors.append(str(error)))
            page.on(
                "console",
                lambda msg: console_errors.append(msg.text) if msg.type == "error" else None,
            )
            page.on("requestfailed", lambda request: failed_requests.append(request.url))
            page.on(
                "response",
                lambda resp: http_errors.append(f"{resp.request.method} {resp.url} -> {resp.status}")
                if resp.status >= 400 and "favicon.ico" not in resp.url
                else None,
            )
            try:
                # 1. Dashboard e inicialização JS (sem eval)
                page.goto(base + "/", wait_until="domcontentloaded", timeout=75000)
                page.locator("html[data-cc-js-ready='true']").wait_for(state="attached", timeout=15000)
                assert page.locator("#cc-js-health").is_hidden(), "#cc-js-health visível: JS não iniciou"
                checks.append("JavaScript inicializado e heartbeat OK (CSP real)")
                page.screenshot(path=str(pasta / f"smoke_{browser_name}_dashboard.png"))

                # 2. Alternância de tema (via atributo DOM, sem evaluate/eval)
                theme = page.locator('button[title="Alternar Modo Escuro / Claro"]')
                assert theme.count() == 1
                before_class = page.locator("html").get_attribute("class") or ""
                before_dark = "dark" in before_class.split()
                theme.click()
                page.wait_for_timeout(300)
                after_class = page.locator("html").get_attribute("class") or ""
                after_dark = "dark" in after_class.split()
                assert before_dark != after_dark, f"Botão de tema não reagiu: {before_class} -> {after_class}"
                checks.append("Botão de tema funcional (CSP real)")

                # 3. Grafo DAG, abertura de modal e tecla Escape
                page.goto(base + "/grafo", wait_until="domcontentloaded", timeout=75000)
                page.locator("html[data-cc-js-ready='true']").wait_for(state="attached", timeout=15000)
                grafo = page.locator(".graph-node-card:visible")
                assert grafo.count() >= 1, "Nenhum cartão visível para abrir modal"
                grafo.first.click()
                dialog = page.locator("#modal-detalhes-missao.active")
                dialog.wait_for(state="visible", timeout=5000)
                assert page.locator("#modal-node-title").inner_text().strip(), "Modal sem título"
                page.keyboard.press("Escape")
                dialog.wait_for(state="hidden", timeout=5000)
                assert page.locator("#modal-detalhes-missao.active").count() == 0, "Esc não fechou modal"
                checks.append("Cartão → modal → Esc (CSP real)")

                # 4. Raia 4 recolhível e filtro de texto
                section = page.locator("#secao-dados-insuficientes")
                assert section.count() == 1
                assert page.locator("#secao-dados-insuficientes[open]").count() == 0, "Raia deveria começar fechada"
                section.locator("summary").click()
                page.locator("#secao-dados-insuficientes[open]").wait_for(state="attached", timeout=5000)
                total = page.locator("#raia-dados-insuficientes .graph-node-card:visible").count()
                filtro = page.locator("#filtro-dados-insuficientes")
                filtro.fill("#5")
                page.wait_for_timeout(300)
                filtrado = page.locator("#raia-dados-insuficientes .graph-node-card:visible").count()
                assert total >= filtrado > 0, f"Filtro falhou: {total} -> {filtrado}"
                assert filtrado < total, "Filtro não reduziu a lista"
                checks.append("Raia expandiu e filtro reagiu ao texto (CSP real)")
                page.screenshot(path=str(pasta / f"smoke_{browser_name}_grafo.png"))

                # 5. GATE-2: "Atualizar agora" com validação explícita de resposta HTTP 200 e status OK/PARTIAL
                with page.expect_response(
                    lambda r: "/api/sincronizar" in r.url and r.request.method == "POST",
                    timeout=75000,
                ) as resp_info:
                    page.locator("#btn-atualizar-agora").click()

                sync_resp = resp_info.value
                assert sync_resp.status == 200, f"POST /api/sincronizar retornou HTTP {sync_resp.status}"
                sync_json = sync_resp.json()
                sync_status = sync_json.get("status")
                assert sync_status in ("OK", "PARTIAL"), (
                    f"Status de sincronização inválido: {sync_status} (esperado OK ou PARTIAL, rejeitado ERROR/STALE)"
                )

                # Verifica que a UI concluiu fora de SYNCING e sem erros
                page.locator("#sync-indicator.sync-ok, #sync-indicator.sync-partial").wait_for(state="visible", timeout=10000)
                assert page.locator("#sync-indicator.sync-stale").count() == 0, "Badge exibiu STALE indevidamente"
                assert page.locator("#sync-indicator.sync-error").count() == 0, "Badge exibiu ERROR indevidamente"
                assert page.locator("#sync-indicator.sync-syncing").count() == 0, "Atualização permaneceu travada em SYNCING"

                assert page.locator("#filtro-dados-insuficientes").input_value() == "#5", "Atualização perdeu o filtro"
                assert page.locator("#secao-dados-insuficientes[open]").count() == 1, "Atualização perdeu expansão da raia"
                checks.append(f"Atualizar agora concluiu com HTTP 200 / {sync_status} preservando busca e expansão (CSP real)")

                # 6. Missões: busca instantânea e busca por formulário GET
                page.goto(base + "/missoes", wait_until="domcontentloaded", timeout=75000)
                page.locator("html[data-cc-js-ready='true']").wait_for(state="attached", timeout=15000)
                page.locator('input[name="busca"]').fill("#7")
                page.wait_for_timeout(300)
                assert "Missões Encontradas (1)" in page.locator("body").inner_text(), (
                    "Busca instantânea não filtrou a tabela"
                )
                checks.append("Busca instantânea reagiu sem botão (CSP real)")

                with page.expect_navigation(timeout=75000):
                    page.get_by_role("button", name="Filtrar", exact=True).click()
                assert "busca=%237" in page.url, f"Formulário GET não submeteu busca: {page.url}"
                assert "Missões Encontradas (1)" in page.locator("body").inner_text(), (
                    "Busca #7 não retornou uma missão"
                )
                checks.append("Busca por número de Issue via formulário GET (CSP real)")
                page.screenshot(path=str(pasta / f"smoke_{browser_name}_missoes.png"))

                relevantes = [erro for erro in console_errors if "favicon.ico" not in erro]
                assert not relevantes, f"Erros de console: {relevantes}"
                assert not failed_requests, f"Requisições de rede falharam: {failed_requests}"
                assert not http_errors, f"Respostas HTTP com erro: {http_errors}"
            finally:
                browser.close()
    except Exception as exc:
        print("FALHA E2E:", repr(exc), file=sys.stderr)
        for issue in console_errors[-20:]:
            print("CONSOLE:", issue, file=sys.stderr)
        for issue in failed_requests[-20:]:
            print("REQUISIÇÃO_FALHOU:", issue, file=sys.stderr)
        for issue in http_errors[-20:]:
            print("HTTP_ERRO:", issue, file=sys.stderr)
        print("Verifique Network /static/js/app.js e Console do navegador.", file=sys.stderr)
        return 1

    for check in checks:
        print("PASSOU:", check)
    print(f"RESULTADO: E2E ({browser_name}) aprovado sob CSP real; evidências em", pasta)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
