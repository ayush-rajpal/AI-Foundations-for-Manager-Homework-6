"""Prompt-injection defenses for the vendor desk agent (Problem 6).

Three independent layers, switched by `Defenses(code, design, prompt)`:

CODE   - before the model sees a document: keep only text a person would actually see (drop hidden HTML,
         HTML comments, white / tiny / off-page PDF text, the email part a mail app does not show,
         zero-width characters) and scan what is left for instructions aimed at an AI.
DESIGN - how the agent is wired: the model only EXTRACTS facts; Python checks those facts against the
         document and the handbook and makes the recommendation itself; send_email / approve_payment
         need human approval, so a document can never trigger them; the document is passed as clearly
         fenced data with no tool for the model to read files.
PROMPT - prompts/prompt.md tells the model that document text is data, never instructions.

`Defenses.none()` is the Problem 3/5 agent with no defenses (kept for Problem 7).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from email import policy
from email.parser import BytesParser
from pathlib import Path

import pymupdf
from bs4 import BeautifulSoup, Comment

HW_DIR = Path(__file__).resolve().parent
HANDBOOK_PATH = HW_DIR / "data" / "shop_handbook.md"


@dataclass(frozen=True)
class Defenses:
    code: bool = True
    design: bool = True
    prompt: bool = True

    @property
    def name(self) -> str:
        on = [n for n in ("code", "design", "prompt") if getattr(self, n)]
        return "all" if len(on) == 3 else "+".join(on) or "none"

    @classmethod
    def parse(cls, spec: str) -> "Defenses":
        """'all', 'none', or a comma/plus list such as 'code,prompt'."""
        spec = spec.strip().lower()
        if spec == "all":
            return cls()
        if spec == "none":
            return cls(False, False, False)
        parts = set(re.split(r"[,+ ]+", spec))
        unknown = parts - {"code", "design", "prompt"}
        if unknown:
            raise ValueError(f"unknown defense layer(s): {sorted(unknown)}")
        return cls("code" in parts, "design" in parts, "prompt" in parts)


# =========================================================================== CODE LAYER
# Turn a document into the text a person would see, and record everything that was hidden.

INVISIBLE_CHARS = re.compile(r"[\u00ad\u200b-\u200f\u202a-\u202e\u2060-\u2064\u2066-\u2069\ufeff]")
WHITE = re.compile(r"^(#fff(fff)?|white|rgba?\(\s*25[0-5]\s*,\s*25[0-5]\s*,\s*25[0-5]\s*(,\s*[\d.]+\s*)?\))$", re.I)


@dataclass
class HiddenItem:
    where: str   # e.g. "html <p>", "pdf page 1", "email text/plain part"
    why: str     # e.g. "font-size:0px", "white text", "off the page"
    text: str


@dataclass
class ScanReport:
    """What the code layer found in one document."""

    hidden: list[HiddenItem] = field(default_factory=list)
    invisible_chars_removed: int = 0
    instruction_flags: list[str] = field(default_factory=list)  # AI-directed wording in the visible text

    def summary_lines(self) -> list[str]:
        out = [f"Removed hidden {h.where} text ({h.why})" for h in self.hidden]
        if self.invisible_chars_removed:
            out.append(f"Removed {self.invisible_chars_removed} invisible zero-width/bidi characters")
        out += [f"Instruction-like text in document: {f}" for f in self.instruction_flags]
        return out

    def as_dict(self) -> dict:
        return {
            "hidden_removed": [h.__dict__ for h in self.hidden],
            "invisible_chars_removed": self.invisible_chars_removed,
            "instruction_flags": self.instruction_flags,
        }


def _style_hides(style: str) -> str | None:
    """Return why an inline CSS declaration block hides its text, or None if it is visible."""
    decl = {}
    for part in style.split(";"):
        if ":" in part:
            k, v = part.split(":", 1)
            decl[k.strip().lower()] = v.strip().lower()
    if decl.get("display") == "none":
        return "display:none"
    if decl.get("visibility") in ("hidden", "collapse"):
        return "visibility:hidden"
    if decl.get("opacity") not in (None, "") and _num(decl["opacity"]) == 0:
        return "opacity:0"
    fs = decl.get("font-size")
    if fs is not None:
        n = _num(fs)
        if n is not None and ((fs.endswith("px") and n <= 2) or (fs.endswith("pt") and n <= 2)
                              or (fs.endswith(("em", "rem")) and n <= 0.2) or n == 0):
            return f"font-size:{fs}"
    if "color" in decl and WHITE.match(decl["color"]):
        return f"white text (color:{decl['color']})"
    for side in ("left", "top", "text-indent", "margin-left"):
        n = _num(decl.get(side, ""))
        if n is not None and n <= -999:
            return f"moved off screen ({side}:{decl[side]})"
    if decl.get("clip", "").startswith("rect(0") or decl.get("clip-path", "").startswith("inset(50%"):
        return "clipped to nothing"
    if (_num(decl.get("height", "")) == 0 or _num(decl.get("width", "")) == 0) and decl.get("overflow") == "hidden":
        return "zero-size box"
    return None


def _num(v: str) -> float | None:
    m = re.match(r"^\s*(-?\d*\.?\d+)", v or "")
    return float(m.group(1)) if m else None


def _stylesheet_rules(soup: BeautifulSoup) -> list[tuple[str, str]]:
    """Simple selectors (tag, .class, #id) from <style> blocks whose rules hide text."""
    rules = []
    for style in soup.find_all("style"):
        for selectors, body in re.findall(r"([^{}]+)\{([^{}]*)\}", style.get_text()):
            why = _style_hides(body)
            if why:
                rules += [(s.strip(), why) for s in selectors.split(",") if s.strip()]
    return rules


def _html_visible(html: str, where: str, report: ScanReport) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for c in soup.find_all(string=lambda s: isinstance(s, Comment)):
        if c.strip():
            report.hidden.append(HiddenItem(f"{where} comment", "HTML comment, never shown", " ".join(c.split())))
        c.extract()
    hide_rules = _stylesheet_rules(soup)
    for tag in soup(["script", "style", "template", "noscript"]):
        tag.decompose()
    for el in list(soup.find_all(True)):
        if getattr(el, "decomposed", False):
            continue
        why = None
        if el.has_attr("hidden"):
            why = "hidden attribute"
        elif el.get("aria-hidden") == "true":
            why = "aria-hidden"
        elif el.has_attr("style"):
            why = _style_hides(el["style"])
        if why is None:
            for sel, rule_why in hide_rules:
                if (sel.startswith(".") and sel[1:] in (el.get("class") or [])) or \
                   (sel.startswith("#") and el.get("id") == sel[1:]) or sel == el.name:
                    why = f"stylesheet {sel} {{{rule_why}}}"
                    break
        if why:
            text = " ".join(el.get_text(" ").split())
            if text:
                report.hidden.append(HiddenItem(f"{where} <{el.name}>", why, text))
            el.decompose()
    lines = (line.strip() for line in soup.get_text("\n").splitlines())
    return "\n".join(line for line in lines if line)


def _pdf_visible(path: Path, report: ScanReport) -> str:
    doc = pymupdf.open(path)
    pages = []
    for pno, page in enumerate(doc, 1):
        rect = page.rect
        # Every text run the PDF draws, including off-page runs (pypdf extracts those too).
        for t in page.get_texttrace():
            text = "".join(chr(c[0]) for c in t["chars"]).strip()
            if not text:
                continue
            color = [round(c * 255) for c in (t["color"] or (0, 0, 0))[:3]]
            why = None
            if not rect.intersects(pymupdf.Rect(t["bbox"])):
                why = f"off the page (y={t['bbox'][1]:.0f} on a {rect.height:.0f}pt page)"
            elif t["type"] == 3 or t["opacity"] == 0:
                why = "invisible render mode"
            elif min(color) >= 240:
                why = "white text on white page"
            elif t["size"] < 3:
                why = f"tiny font ({t['size']:.1f}pt)"
            if why:
                report.hidden.append(HiddenItem(f"pdf page {pno}", why, text))
        # Visible text: on-page spans that are not white, tiny or invisible.
        lines = []
        for block in page.get_text("dict", clip=rect)["blocks"]:
            for line in block.get("lines", []):
                kept = []
                for s in line["spans"]:
                    c = s["color"]
                    if min((c >> 16) & 255, (c >> 8) & 255, c & 255) >= 240 or s["size"] < 3:
                        continue
                    kept.append(s["text"])
                if "".join(kept).strip():
                    lines.append("".join(kept).strip())
        pages.append(f"[page {pno}]\n" + "\n".join(lines))
    return "\n\n".join(pages)


def _eml_visible(path: Path, report: ScanReport) -> str:
    msg = BytesParser(policy=policy.default).parse(path.open("rb"))
    head = [f"{h}: {msg[h]}" for h in ("From", "To", "Subject", "Date") if msg[h]]
    html_part = msg.get_body(preferencelist=("html",))
    plain_part = msg.get_body(preferencelist=("plain",))
    # A mail app shows the HTML part when there is one, so that is what the reader of the email saw.
    if html_part is not None:
        body = _html_visible(html_part.get_content(), "email html", report)
        if plain_part is not None:
            seen = " ".join(INVISIBLE_CHARS.sub("", body).split()).lower()
            for line in plain_part.get_content().splitlines():
                ln = " ".join(INVISIBLE_CHARS.sub("", line).split())
                if len(ln) > 15 and ln.lower() not in seen:
                    report.hidden.append(HiddenItem("email text/plain part", "not in the part a mail app shows", ln))
        shown = "[body: text/html part as a mail app shows it]"
    else:
        body = plain_part.get_content().strip() if plain_part is not None else ""
        shown = "[body: text/plain]"
    for part in msg.walk():
        if part.get_content_type() == "application/pdf":
            tmp = HW_DIR / "output" / f"_attachment_{path.stem}.pdf"
            tmp.write_bytes(part.get_payload(decode=True))
            body += f"\n\n[attachment: {part.get_filename()}]\n" + _pdf_visible(tmp, report)
            tmp.unlink(missing_ok=True)
    return "\n".join(head) + f"\n\n{shown}\n{body}"


# Wording aimed at an AI reviewer rather than at a human buyer. Ordinary business language
# ("corrected quote", "please ignore my earlier email") is deliberately NOT flagged.
INSTRUCTION_PATTERNS: list[tuple[str, str]] = [
    (r"\b(send_email|approve_payment|read_document|function call|tool call)\b", "names an agent tool"),
    (r"\b(ignore|disregard|forget)\s+(all\s+|any\s+|the\s+)?(previous|prior|above|earlier|your)\s+(instructions|rules|prompt)", "tells the reader to ignore its instructions"),
    (r"\b(AI|assistant|language model|LLM|chatbot|the reviewer|the agent|vendor desk agent)\b", "addresses an AI / the reviewer"),
    (r"\b(system prompt|developer message|your instructions)\b", "mentions prompts or instructions"),
    (r"\b(in|into) your (reason|answer|response|output|summary)\b", "tells the AI what to put in its answer"),
    (r"\b(max(imum)? unit cost|margin)s?\b.*\b(send|share|email)\b|\b(send|share|email)\b.*\b(max(imum)? unit cost|margin)s?\b", "asks for confidential cost data"),
    (r"\b(approve|authori[sz]e)\b.*\b(payment|deposit|invoice)\b", "asks for a payment to be approved"),
]


def scan_instructions(text: str) -> list[str]:
    flags = []
    for line in text.splitlines():
        for pattern, label in INSTRUCTION_PATTERNS:
            if re.search(pattern, line, re.I):
                flags.append(f"{label}: \"{line.strip()[:140]}\"")
                break
    return flags


def visible_document(path: Path) -> tuple[str, ScanReport]:
    """CODE LAYER entry point: the human-visible text of a document plus what was removed/flagged."""
    report = ScanReport()
    suffix = path.suffix.lower()
    if suffix in {".html", ".htm"}:
        text = _html_visible(path.read_text(encoding="utf-8", errors="replace"), "html", report)
    elif suffix == ".pdf":
        text = _pdf_visible(path, report)
    elif suffix == ".eml":
        text = _eml_visible(path, report)
    else:
        raise ValueError(f"unsupported file type {suffix}")
    report.invisible_chars_removed = len(INVISIBLE_CHARS.findall(text))
    text = INVISIBLE_CHARS.sub("", text)
    report.instruction_flags = scan_instructions(text)
    return text, report


# =========================================================================== DESIGN LAYER
# The model only extracts facts. These functions check them and make the decision in code.

@dataclass
class Handbook:
    approved: dict[str, dict]   # normalized vendor name -> {name, code, domain}
    removed: dict[str, str]     # normalized vendor name -> display name
    max_cost: dict[str, float]  # SKU -> max unit cost


def _norm(s: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", (s or "").lower()).split())


def _table_rows(md: str, heading_prefix: str) -> list[list[str]]:
    section = md.split(heading_prefix, 1)[1].split("\n## ", 1)[0]
    rows = [r for r in section.splitlines() if r.startswith("|") and not r.startswith("|---")]
    return [[c.strip() for c in r.strip("|").split("|")] for r in rows[1:]]


def load_handbook(path: Path = HANDBOOK_PATH) -> Handbook:
    md = path.read_text(encoding="utf-8")
    approved = {}
    for code, name, *_rest, notes in _table_rows(md, "## 5."):
        m = re.search(r"@([\w.-]+)", notes)
        approved[_norm(name)] = {"name": name, "code": code, "domain": m.group(1).lower() if m else None}
    removed = {_norm(name): name for name, _status in _table_rows(md, "## 6.")}
    max_cost = {row[0]: float(row[4].lstrip("$").replace(",", "")) for row in _table_rows(md, "## 9.")}
    return Handbook(approved, removed, max_cost)


HANDBOOK = load_handbook()

PRICE_RE = re.compile(r"price\b[^$.]{0,40}\$\s?(\d[\d,]*(?:\.\d{1,2})?)", re.I)
LEAD_RE = re.compile(r"lead\s*time\b[^.\d]{0,40}?(\d+)\s*(?:business\s+|calendar\s+|working\s+)?(day|week)", re.I)
MOQ_RE = re.compile(r"(?:minimum(?:\s+order)?(?:\s+quantity)?|\bMOQ)\b[^.\d]{0,30}?(\d[\d,]*)", re.I)
# Links and email addresses are scrubbed from anything the model writes for the buyer.
LINK_RE = re.compile(r"https?://\S+|www\.\S+|\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b", re.I)
DOMAIN_RE = re.compile(r"(?:@|https?://(?:www\.)?)([a-z0-9-]+(?:\.[a-z0-9-]+)+)", re.I)


def _values(regex: re.Pattern, text: str, kind: str) -> set[float]:
    out = set()
    for m in regex.finditer(text):
        v = float(m.group(1).replace(",", ""))
        if kind == "lead" and m.group(2).lower().startswith("week"):
            v *= 7
        out.add(v)
    return out


def _numbers(text: str) -> set[float]:
    return {float(n.replace(",", "")) for n in re.findall(r"\d[\d,]*\.?\d*", text) if n.strip(",.")}


def decide(facts: dict, doc_text: str, scan: ScanReport | None, model_flags: list[str]) -> dict:
    """DESIGN LAYER: verify the extracted facts against the document, then apply the four handbook
    checks in code. Returns the final answer (VendorDecision fields + security fields)."""
    flags: list[str] = []
    block: list[str] = []  # problems that force do_not_recommend + human review
    vendor, sku = facts.get("vendor"), facts.get("sku")
    price, lead, moq = facts.get("unit_price"), facts.get("lead_time_days"), facts.get("min_order")
    norm_doc = _norm(doc_text)
    nums = _numbers(doc_text)

    # 1. Grounding: every value the model reports must literally be in the document it was shown.
    if vendor and _norm(vendor) not in norm_doc:
        block.append(f"vendor '{vendor}' does not appear in the document")
    if sku and sku.lower() not in doc_text.lower():
        block.append(f"SKU {sku} does not appear in the document")
    if price is not None and not any(abs(price - n) < 0.005 for n in nums):
        block.append(f"unit price {price} does not appear in the document")
    if lead is not None and lead not in nums and (lead % 7 or lead / 7 not in nums):
        block.append(f"lead time {lead} does not appear in the document")
    if moq is not None and moq not in nums:
        block.append(f"minimum order {moq} does not appear in the document")

    # 2. Conflicts: the document states two different values for the same fact.
    for label, regex, kind in (("unit prices", PRICE_RE, "price"), ("lead times", LEAD_RE, "lead"),
                               ("minimum orders", MOQ_RE, "moq")):
        vals = _values(regex, doc_text, kind)
        if len(vals) > 1:
            shown = ", ".join(f"${v:.2f}" if kind == "price" else f"{v:g}" for v in sorted(vals))
            block.append(f"document states conflicting {label} ({shown}); buyer must confirm in writing")

    # 3. Identity: a removed/pending vendor named in the document, or a sender domain that does not
    #    match the approved vendor's domain in the handbook, means the vendor claim cannot be trusted.
    for key, name in HANDBOOK.removed.items():
        if key in norm_doc and _norm(vendor or "") != key:
            block.append(f"document names removed/pending vendor {name} but the extracted vendor is '{vendor}'")
    approved = HANDBOOK.approved.get(_norm(vendor or ""))
    domains = {d.lower() for d in DOMAIN_RE.findall(doc_text)} - {"campuscustoms.example"}
    if approved and approved["domain"] and domains and approved["domain"] not in domains:
        block.append(f"document comes from {', '.join(sorted(domains))}, not {approved['name']}'s "
                     f"domain {approved['domain']} (possible impersonation)")

    # 4. The four handbook checks, in code, using handbook numbers only.
    failed = []
    if approved is None:
        failed.append(f"approved-vendor check: {vendor or 'the vendor'} is not on the approved vendor list"
                      + (" (removed/pending vendor)" if _norm(vendor or "") in HANDBOOK.removed else ""))
    max_cost = HANDBOOK.max_cost.get(sku or "")
    if price is None:
        failed.append("price check: unit price is unknown")
    elif max_cost is None:
        failed.append(f"price check: SKU {sku} is not in the catalogue, so the price cannot be checked")
    elif price > max_cost:
        failed.append(f"price check: ${price:.2f} is above the ${max_cost:.2f} max unit cost for {sku}")
    if lead is None:
        failed.append("lead-time check: lead time is unknown")
    elif lead > 21:
        failed.append(f"lead-time check: {lead} days is over the 21-day limit")
    if moq is None:
        failed.append("minimum-order check: minimum order is unknown")
    elif moq > 600:
        failed.append(f"minimum-order check: {moq} units is over the 600-unit limit")

    if scan is not None:
        flags += scan.summary_lines()
    flags += ["Model noticed: " + LINK_RE.sub("[link or email removed]", f)[:200] for f in model_flags]
    flags += [f"BLOCKED: {b}" for b in block]

    if block:
        decision = "do_not_recommend"
        reason = "Needs buyer review before any purchase: " + "; ".join(block[:2]) + "."
    elif failed:
        decision = "do_not_recommend"
        reason = "Fails the " + "; the ".join(failed) + "."
    else:
        decision = "recommend"
        reason = (f"All four checks pass: {approved['name']} is approved, ${price:.2f} is within the "
                  f"${max_cost:.2f} max unit cost, {lead} days is within 21, and {moq} units is within 600.")
    return {
        "vendor": vendor, "sku": sku, "unit_price": price, "lead_time_days": lead, "min_order": moq,
        "decision": decision, "reason": reason,
        "security_flags": flags,
        "needs_human_review": bool(block or model_flags or (scan and (scan.hidden or scan.instruction_flags))),
        "checks_failed": failed, "blocked_by": block,
    }
