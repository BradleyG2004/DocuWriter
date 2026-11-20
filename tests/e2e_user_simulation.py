from pathlib import Path
import os
import re
import subprocess
import sys
import tempfile
import time
import traceback
import urllib.request

import fitz
from docx import Document
from docx.enum.text import WD_COLOR_INDEX
from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
SCREENSHOT_DIR = ROOT / "output" / "e2e_screenshots"
TEMP_DIR = Path(tempfile.mkdtemp(prefix="docuwriter-e2e-"))


def wait_http(url: str, timeout: float = 30.0) -> None:
    deadline = time.time() + timeout
    error = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return
        except Exception as exc:
            error = exc
        time.sleep(0.1)
    raise RuntimeError(f"{url} unavailable: {error}")


def make_files() -> dict[str, Path]:
    context = Document()
    context.add_heading("Architecture technique", level=1)
    context.add_paragraph(
        "Cluster Kubernetes EKS, base PostgreSQL 15 multi-AZ, "
        "authentification OAuth2 / JWT RS256."
    )
    context.add_paragraph("TLS, segmentation réseau et sauvegardes chiffrées.")
    context_path = TEMP_DIR / "contexte_archi.docx"
    context.save(context_path)

    template = Document()
    template.add_heading("Spécifications du service", level=1)
    template.add_paragraph("Architecture de données à remplacer")
    template.add_paragraph("Deuxième paragraphe pour test d'insertion")
    table = template.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "Composant"
    table.cell(0, 1).text = "Protocole"
    table.cell(1, 0).text = "API"
    table.cell(1, 1).text = "Cellule à baliser"
    template_path = TEMP_DIR / "template_vierge.docx"
    template.save(template_path)

    pdf_template = fitz.open()
    page1 = pdf_template.new_page()
    page1.insert_text((50, 60), "Rapport technique", fontsize=18)
    page1.insert_text((50, 100), "Description de l'architecture à remplacer", fontsize=11)
    page2 = pdf_template.new_page()
    page2.insert_text((50, 60), "Annexe réseau", fontsize=18)
    page2.insert_text((50, 100), "Réseau, TLS et PostgreSQL", fontsize=11)
    pdf_template_path = TEMP_DIR / "rapport_modele.pdf"
    pdf_template.save(pdf_template_path)
    pdf_template.close()

    pdf_context = fitz.open()
    page = pdf_context.new_page()
    page.insert_text((50, 60), "Cluster Kubernetes EKS", fontsize=14)
    page.insert_text((50, 100), "PostgreSQL 15 multi-AZ", fontsize=11)
    page.insert_text((50, 140), "OAuth2 JWT RS256 TLS", fontsize=11)
    pdf_context_path = TEMP_DIR / "specs_reseau.pdf"
    pdf_context.save(pdf_context_path)
    pdf_context.close()

    pretagged = Document()
    pretagged.add_heading("Document pré-balisé", level=1)
    pretagged.add_paragraph("<here>Zone pré-balisée 1</here>")
    pretagged.add_paragraph("<here>Zone pré-balisée 2</here>")
    pretagged_path = TEMP_DIR / "pre_tagged.docx"
    pretagged.save(pretagged_path)
    return {
        "context": context_path,
        "template": template_path,
        "pdf_template": pdf_template_path,
        "pdf_context": pdf_context_path,
        "pretagged": pretagged_path,
    }


def start_servers():
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    ollama_log = (TEMP_DIR / "mock_ollama.log").open("w")
    ollama = subprocess.Popen(
        [sys.executable, str(ROOT / "tests" / "mock_ollama_server.py")],
        stdout=ollama_log,
        stderr=subprocess.STDOUT,
        cwd=str(ROOT),
    )
    web_log = (TEMP_DIR / "uvicorn.log").open("w")
    env = os.environ.copy()
    env["OLLAMA_HOST"] = "http://127.0.0.1:11435"
    env["OLLAMA_MODEL"] = "llama3.1"
    env["MAX_RETRIES"] = "0"
    web = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "docuwriter.web:app",
         "--host", "127.0.0.1", "--port", "8000"],
        stdout=web_log,
        stderr=subprocess.STDOUT,
        cwd=str(ROOT),
        env={**env, "PYTHONPATH": str(ROOT / "src")},
    )
    wait_http("http://127.0.0.1:11435/api/tags")
    wait_http("http://127.0.0.1:8000/")
    return ollama, web


def attach_monitor(page):
    failures = []
    page.on("pageerror", lambda error: failures.append(f"pageerror: {error}"))
    page.on("console", lambda message: failures.append(f"console error: {message.text}")
              if message.type == "error" else None)

    def check_response(response):
        if "/api/" in response.url and response.status >= 400:
            failures.append(f"HTTP {response.status}: {response.url}")
        if "/api/" in response.url and response.status >= 500:
            raise AssertionError(f"HTTP 500: {response.url}")

    page.on("response", check_response)
    return failures


def select_text(page, text: str):
    locator = page.get_by_text(text, exact=False).first
    locator.wait_for()
    locator.evaluate(
        "(element, text) => {"
        "const walker=document.createTreeWalker(element,NodeFilter.SHOW_TEXT);"
        "let node=walker.nextNode();"
        "while(node){const i=node.textContent.indexOf(text);"
        "if(i>=0){const r=document.createRange();r.setStart(node,i);"
        "r.setEnd(node,i+text.length);const s=window.getSelection();"
        "s.removeAllRanges();s.addRange(r);"
        "element.dispatchEvent(new MouseEvent('mouseup',{bubbles:true,clientX:300,clientY:300}));"
        "return;}node=walker.nextNode();}}",
        text,
    )
    page.locator("#floating-popover").wait_for(state="visible")


def submit_floating(page, instruction: str):
    page.locator("#popover-input").fill(instruction)
    page.locator("#popover-confirm").click()
    page.locator("#floating-popover").wait_for(state="hidden")


def wait_generation(page):
    page.wait_for_function(
        "() => document.getElementById('progress').textContent.includes('Génération terminée')",
        timeout=30000,
    )


def run_scenarios(page, files):
    failures = attach_monitor(page)

    page.goto("http://127.0.0.1:8000", wait_until="networkidle")
    page.locator("#demo").click()
    page.locator("#a4-sheet").wait_for(state="visible")
    assert page.locator("#reader .reader-block").count() > 0
    assert page.locator("table.doc-table").count() >= 1
    page.screenshot(path=str(SCREENSHOT_DIR / "01_demo_loaded.png"), full_page=True)

    select_text(page, "Description:")
    submit_floating(page, "Décrire l'architecture démonstrative")
    page.locator(".insert-divider").first.locator("button").click(force=True)
    submit_floating(page, "Ajouter une conclusion")
    assert page.locator("#marker-list .marker-card").count() >= 2

    page.goto("http://127.0.0.1:8000", wait_until="networkidle")
    page.set_input_files("#target-file", str(files["template"]))
    page.set_input_files("#context-files", [str(files["context"])])
    page.locator("#upload").click()
    page.locator("#a4-sheet").wait_for(state="visible")
    assert "Aucune balise préexistante" in page.locator("#tag-badge").inner_text()

    select_text(page, "Architecture de données à remplacer")
    submit_floating(page, "Décrire l'architecture base de données")
    page.locator(".insert-divider").nth(1).locator("button").click(force=True)
    submit_floating(page, "Ajouter une section sécurité et authentification")
    page.locator("td.table-cell").last.click(force=True)
    submit_floating(page, "Préciser le protocole réseau")

    marker_cards = page.locator("#marker-list .marker-card")
    assert marker_cards.count() >= 3
    marker_cards.nth(0).locator("textarea").fill(
        "Décrire l'architecture base de données PostgreSQL 15 multi-AZ"
    )
    page.wait_for_timeout(400)
    page.screenshot(path=str(SCREENSHOT_DIR / "02_markers_placed.png"), full_page=True)

    with page.expect_download() as download_info:
        page.locator("#export-template").click()
    tagged_path = TEMP_DIR / "modele_balisé.docx"
    download_info.value.save_as(tagged_path)
    tagged_doc = Document(tagged_path)
    tagged_text = "\n".join(p.text for p in tagged_doc.paragraphs)
    tagged_text += "\n".join(
        cell.text for table in tagged_doc.tables
        for row in table.rows for cell in row.cells
    )
    assert len(re.findall(r"<here>.*?</here>", tagged_text, re.DOTALL)) >= 3

    page.locator("#generate").click()
    wait_generation(page)
    assert page.locator("#reader .ai-suggestion-card").count() >= 3
    page.screenshot(path=str(SCREENSHOT_DIR / "03_generation_done.png"), full_page=True)

    manual_text = "Texte édité manuellement — PostgreSQL 15 multi-AZ validé"
    page.locator(".replacement-textarea").first.fill(manual_text)
    with page.expect_download() as download_info:
        page.locator("#export-final").click()
    final_path = TEMP_DIR / "final.docx"
    download_info.value.save_as(final_path)
    final_doc = Document(final_path)
    final_text = "\n".join(p.text for p in final_doc.paragraphs)
    final_text += "\n".join(
        cell.text for table in final_doc.tables
        for row in table.rows for cell in row.cells
    )
    assert "<here>" not in final_text
    assert manual_text in final_text
    yellow = any(
        run.font.highlight_color == WD_COLOR_INDEX.YELLOW
        for paragraph in final_doc.paragraphs
        for run in paragraph.runs
    )
    assert yellow

    page.goto("http://127.0.0.1:8000", wait_until="networkidle")
    page.set_input_files("#target-file", str(files["pdf_template"]))
    page.set_input_files("#context-files", [str(files["pdf_context"])])
    page.locator("#upload").click()
    page.locator("#a4-sheet").wait_for(state="visible")
    assert page.locator(".page-separator").count() >= 2
    separators = page.locator(".page-separator").all_text_contents()
    assert any("Page 1" in text for text in separators)
    assert any("Page 2" in text for text in separators)
    page.screenshot(path=str(SCREENSHOT_DIR / "04_pdf_reader.png"), full_page=True)

    select_text(page, "Description de l'architecture")
    submit_floating(page, "Décrire l'architecture réseau")
    page.locator("#generate").click()
    wait_generation(page)
    with page.expect_download() as download_info:
        page.locator("#export-final").click()
    pdf_path = TEMP_DIR / "final.pdf"
    download_info.value.save_as(pdf_path)
    pdf = fitz.open(pdf_path)
    assert pdf.page_count >= 2
    pdf_text = "".join(pdf_page.get_text() for pdf_page in pdf)
    pdf.close()
    assert "Contenu technique généré" in pdf_text

    page.goto("http://127.0.0.1:8000", wait_until="networkidle")
    page.set_input_files("#target-file", str(files["pretagged"]))
    page.locator("#upload").click()
    page.locator("#a4-sheet").wait_for(state="visible")
    assert page.locator("#marker-list .marker-card").count() == 2
    page.locator("#generate").click()
    wait_generation(page)
    with page.expect_download() as download_info:
        page.locator("#export-final").click()
    pretagged_path = TEMP_DIR / "pretagged_final.docx"
    download_info.value.save_as(pretagged_path)
    pretagged_doc = Document(pretagged_path)
    text = "\n".join(p.text for p in pretagged_doc.paragraphs)
    text += "\n".join(
        cell.text for table in pretagged_doc.tables
        for row in table.rows for cell in row.cells
    )
    assert "<here>" not in text

    if failures:
        raise AssertionError("\n".join(failures))


def main() -> int:
    files = make_files()
    ollama = web = None
    try:
        ollama, web = start_servers()
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": 1440, "height": 900},
                accept_downloads=True,
            )
            page = context.new_page()
            run_scenarios(page, files)
            context.close()
            browser.close()
        print("E2E SUCCESS: 4/4 scenarios passed")
        for screenshot in sorted(SCREENSHOT_DIR.glob("*.png")):
            print(f"- {screenshot}")
        return 0
    except Exception as exc:
        print(f"E2E FAILURE: {exc}", file=sys.stderr)
        traceback.print_exc()
        return 1
    finally:
        for process in (web, ollama):
            if process is not None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()


if __name__ == "__main__":
    raise SystemExit(main())
