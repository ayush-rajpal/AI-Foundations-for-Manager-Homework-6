"""Problem 5: see each practice document the way a person would, next to what the agent reads.

- HTML  -> screenshot in real Chrome (headless), like opening the file in a browser
- .eml  -> an email-app style page (From/To/Subject/Date + the HTML part, which mail apps show
           instead of the plain-text part when both exist), screenshotted in Chrome
- PDF   -> page rendered to PNG with PyMuPDF, like a PDF viewer; every text span is also checked for
           hiding tricks (white/near-white color, tiny font, off-page position)

Writes output/human_view/<doc>.png, output/human_view/<doc>.view.html (emails) and
output/human_view/pdf_spans.json. Visible-vs-hidden text for HTML/email views is checked separately
in the browser (see output/attack_results.md).

Run:  C:/venvs/hw6/Scripts/python scripts/human_view.py
"""

from __future__ import annotations

import html
import json
import subprocess
from email import policy
from email.parser import BytesParser
from pathlib import Path

import pymupdf

HW_DIR = Path(__file__).resolve().parents[1]
DOCS = HW_DIR / "data" / "practice_docs"
OUT = HW_DIR / "output" / "human_view"
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"


def chrome_screenshot(page: Path, png: Path) -> None:
    subprocess.run(
        [CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--window-size=900,820",
         f"--screenshot={png}", page.as_uri()],
        check=True, capture_output=True, timeout=60,
    )


def email_view(eml: Path) -> Path:
    """Render an .eml the way a mail client shows it: headers, then the HTML body if there is one."""
    msg = BytesParser(policy=policy.default).parse(eml.open("rb"))
    html_part = msg.get_body(preferencelist=("html",))
    plain_part = msg.get_body(preferencelist=("plain",))
    if html_part is not None:
        body, shown = html_part.get_content(), "text/html part (mail apps prefer it over text/plain)"
    else:
        body, shown = f"<pre style='font-family:inherit;white-space:pre-wrap'>{html.escape(plain_part.get_content())}</pre>", "text/plain part"
    headers = "".join(
        f"<div><b>{h}:</b> {html.escape(str(msg[h]))}</div>" for h in ("From", "To", "Subject", "Date") if msg[h]
    )
    page = OUT / f"{eml.stem}.view.html"
    page.write_text(
        "<!DOCTYPE html><html><head><meta charset='utf-8'><title>" + html.escape(str(msg["Subject"])) + "</title></head>"
        "<body style='font-family:Segoe UI,Arial,sans-serif;margin:0;background:#f3f4f6'>"
        "<div style='background:#1f2937;color:#fff;padding:8px 16px;font-size:13px'>Mail - Inbox</div>"
        f"<div style='background:#fff;margin:16px;padding:16px;border:1px solid #d1d5db'>"
        f"<div style='font-size:13px;color:#374151;border-bottom:1px solid #e5e7eb;padding-bottom:8px;margin-bottom:12px'>{headers}"
        f"<div style='color:#9ca3af;font-size:11px;margin-top:4px'>showing: {shown}</div></div>"
        f"{body}</div></body></html>",
        encoding="utf-8",
    )
    return page


def pdf_view(pdf: Path) -> dict:
    doc = pymupdf.open(pdf)
    spans = []
    for pno, page in enumerate(doc, 1):
        page.get_pixmap(dpi=110).save(OUT / f"{pdf.stem}.png" if pno == 1 else OUT / f"{pdf.stem}_p{pno}.png")
        rect = page.rect
        # get_texttrace() lists every text run the PDF draws, including runs outside the page box
        # (get_text() clips those away, but pypdf - the agent's reader - does not).
        for t in page.get_texttrace():
            text = "".join(chr(c[0]) for c in t["chars"])
            if not text.strip():
                continue
            color = tuple(round(c * 255) for c in (t["color"] or (0, 0, 0))[:3])
            hidden = []
            if min(color) >= 240:
                hidden.append("white/near-white text on white page")
            if t["size"] < 3:
                hidden.append(f"tiny font ({t['size']:.1f}pt)")
            if not rect.intersects(pymupdf.Rect(t["bbox"])):
                hidden.append(f"off the page (y={t['bbox'][1]:.0f}, page height {rect.height:.0f})")
            if t["type"] == 3 or t["opacity"] == 0:
                hidden.append("invisible render mode / zero opacity")
            spans.append({
                "page": pno, "text": text, "font_size": round(t["size"], 1),
                "color": "#%02x%02x%02x" % color, "bbox": [round(x) for x in t["bbox"]],
                "hidden_because": hidden,
            })
    return {"pages": len(doc), "spans": spans,
            "hidden_spans": [s for s in spans if s["hidden_because"]]}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    pdf_report = {}
    for doc in sorted(DOCS.iterdir()):
        png = OUT / f"{doc.stem}.png"
        if doc.suffix == ".html":
            chrome_screenshot(doc, png)
        elif doc.suffix == ".eml":
            chrome_screenshot(email_view(doc), png)
        elif doc.suffix == ".pdf":
            pdf_report[doc.name] = pdf_view(doc)
        print("rendered", doc.name)
    (OUT / "pdf_spans.json").write_text(json.dumps(pdf_report, indent=2, ensure_ascii=False), encoding="utf-8")
    for name, rep in pdf_report.items():
        print(name, "hidden spans:", [(s["text"][:60], s["hidden_because"]) for s in rep["hidden_spans"]])


if __name__ == "__main__":
    main()
