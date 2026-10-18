"""Browser smoke test: load the demo, open a card, check the main panels, and fail on any console error.

Expects the backend on http://localhost:8000 (STORE=memory, AI_ENABLED=false) and the built web app on
http://localhost:5173 (`npm run build` then `npm run preview -- --port 5173 --strictPort`). CI runs it on every pull
request; locally: `pip install playwright`, `python -m playwright install chromium`, then `python e2e/smoke.py`.
"""
import os
import sys

from playwright.sync_api import sync_playwright

WEB = "http://localhost:5173"
checks = []


def check(name, ok):
    checks.append(ok)
    print(("PASS " if ok else "FAIL ") + name)


with sync_playwright() as p:
    browser = p.chromium.launch(channel=os.getenv("PW_CHANNEL") or None)   # e.g. PW_CHANNEL=msedge on a laptop
    page = browser.new_page(viewport={"width": 1366, "height": 800})
    errors = []
    page.on("console", lambda m: m.type == "error" and errors.append(m.text))
    page.on("pageerror", lambda e: errors.append(str(e)))

    page.goto(f"{WEB}/?as=p_priya", wait_until="networkidle")
    page.get_by_text("Q4 Budget Review").first.wait_for(timeout=30000)
    check("the demo loads with Priya's meetings", page.get_by_text("Q4 Budget Review").first.is_visible())

    page.get_by_text("Q4 Budget Review").first.click()
    page.get_by_role("button", name="Ask Meena to cover").first.wait_for(timeout=15000)
    check("the card recommends Meena as proxy", page.get_by_role("button", name="Ask Meena to cover").first.is_visible())

    page.get_by_role("button", name="At company scale ›").click()
    dialog = page.get_by_role("dialog")
    dialog.get_by_text("An illustrative model, not a forecast.").wait_for(timeout=15000)
    check("the company-scale estimate opens, labelled illustrative", "(illustrative)" in dialog.inner_text())
    page.keyboard.press("Escape")

    page.get_by_role("button", name="Report an absence").first.click()
    own = page.get_by_role("textbox", name="Who is out")
    check("an absence can be reported only for yourself", own.input_value().endswith("(you)") and own.is_editable() is False)

    check("no console errors", not errors)
    for e in errors:
        print("  console:", e)
    browser.close()

sys.exit(0 if all(checks) else 1)
