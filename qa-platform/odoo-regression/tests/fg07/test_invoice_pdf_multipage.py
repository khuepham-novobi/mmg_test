"""FG-07 — TC-INV-002: a long, sectioned invoice still prints correctly across pages.

Implements row 33.0 (P1, "Invoice document") of the CLIENT MANUAL TESTING
GUIDELINE ``MMG_v19_Client_Manual_Testing_Guideline_FG05-FG14_v1.0.xlsx`` /
sheet ``Testing Guideline``.

The workbook's framing: *"Gallery invoices for an exhibition or an estate can
run to dozens of lines with section headings. Those are exactly the invoices
where a layout change breaks — columns drift, a section heading spans the
wrong width, or the totals land on a page of their own."*

Its READ-THIS-FIRST paragraph is the whole point of the case: *"The Product
column that TC-INV-001 checks makes the line table one column wider. Section
and note rows have to be widened to match. There is a known case — a
collapsed line — where they are not."*

The 5 Expected Result lines, and what each is read from
------------------------------------------------------
1. **"More than one page, with the column headings repeated on each page."**
   Two halves.
   *Page count* — the real PDF, fetched from ``/report/pdf/
   account.report_invoice_with_payments/<id>`` and counted by its ``/Type
   /Page`` objects. Only attempted when ``ir.actions.report.
   get_wkhtmltopdf_state()`` (public, ``odoo/addons/base/models/
   ir_actions_report.py:276``) says the renderer is present; otherwise the
   count becomes a RESIDUAL MANUAL STEP with the PDF attached.
   *Headings repeating* — read from the ``<thead>`` of the line table. In
   ``addons/account/views/report_invoice.xml:172-174`` the head carries
   ``style="display: table-row-group"`` **only** when ``has_long_desc`` is
   true, and that style is precisely what stops wkhtmltopdf repeating the
   head on later pages. So "the headings repeat" is machine-readable as "the
   thead exists and carries no ``table-row-group`` override".

2. **"Every section and note row spans the full table width. None stops
   short."** Read from the rendered ``report_type=pdf`` HTML. The head's
   ``<th>`` count is the table width: ``th_description``, ``th_quantity``,
   ``th_priceunit``, ``th_discount`` (only when ``display_discount``),
   ``th_taxes`` (only when ``display_taxes``) and ``th_subtotal``
   (``report_invoice.xml:176-186``), **plus** the ``th_product`` column that
   ``mmg_account/report/report_invoice.xml`` inserts before
   ``th_description``. Each section / sub-section / note row's own width is
   the sum of the ``colspan`` of its cells that are not ``d-none``: the
   desktop ``line_name_td`` (:259-263) plus the trailing ``o_price_total``
   cell (:268-270); the ``colspan="2"`` mobile cell at :265 is ``d-none`` in
   pdf mode, which is why this case renders with ``?report_type=pdf`` and
   never in html mode.

3. **"The long description wraps inside its cell; no column is pushed out of
   alignment."** The wrap itself is a pixel fact and is left as a RESIDUAL
   MANUAL STEP. What *is* asserted is the half that causes a column to drift:
   the long text is present, whole, inside one product row's description
   cell, and **every** product row's visible cells add up to exactly the
   header's column count.

4. **"The totals block is whole."** Read from the totals table at
   ``report_invoice.xml:370``: it must carry ``avoid-page-break-inside`` —
   the CSS class that tells wkhtmltopdf not to split it — and it must contain
   the ``<tr class="o_total">`` grand-total row (``:591``, via
   ``account.document_tax_totals``).

5. **"Page numbers are correct."** The numbers themselves are substituted by
   wkhtmltopdf's own JavaScript (``addons/web/views/report_templates.xml:247``)
   and cannot be read from HTML. What is asserted is that the pdf-mode
   footer still emits the placeholder pair ``Page <span class="page"/> /
   <span class="topage"/>`` (``report_templates.xml:368, 432, 496, 557``) —
   if a layout override dropped it, there would be no page numbers at all.
   Whether the sequence then runs correctly is a RESIDUAL MANUAL STEP.

Documented adaptation — the platform cannot look at a printed page
------------------------------------------------------------------
Four of the workbook's checks are pagination facts that exist only after
wkhtmltopdf has laid the document out: which page a row lands on, whether
the head is repainted at the top of page 2, whether a long cell wrapped or
overflowed, and whether the totals block was split. None of them is visible
in ``/report/html``. This case therefore does three things instead of
pretending: it asserts every *structural* precondition for each of them (the
thead override, the colspan arithmetic, ``avoid-page-break-inside``, the page
placeholders), it attaches the real PDF and the rendered HTML as artifacts so
the human step is a two-minute look rather than a re-run, and it records each
remaining eyeball check as a RESIDUAL MANUAL STEP naming the page and the row
to look at.

A finding this case is built to surface
---------------------------------------
``line_colspan`` is computed as ``3 + display_discount + (display_taxes and
not line.tax_ids)`` (``report_invoice.xml:223``). Unmodified Odoo 19 is
internally consistent — that 3 matches its own three leading columns. It has
never learned about the extra **Product** column that
``mmg_account/report/report_invoice.xml`` adds, and MMG's inherited template
does not widen it either. So on a database carrying the MMG template this
case is *predicted to fail* Expected line 2, one column short, on the section
rows — and the short row is MMG's, not Odoo's. That prediction is not
softened here: if it fails, that is the finding, and the offender list names
each row by its CSS class (``o_line_section`` / ``o_line_subsection`` /
``o_line_note``) exactly as the workbook's If It Fails column asks.

Because that assertion raises and would suppress everything after it, it is
deliberately the LAST of the five to be asserted. Every figure it depends on
is gathered, logged and written to CSV several steps earlier, so the run
produces the full diagnosis either way.

Expected v19 differences, logged and asserted in neither direction
------------------------------------------------------------------
* v15 printed a separate **Subtotal** row after each section. Odoo 19 prints
  the section subtotal inline in the section row's own trailing cell, from
  the public ``account.move.line.get_section_subtotal()`` /
  ``get_section_total()`` (``addons/account/models/account_move_line.py:
  3642-3648``, used at ``report_invoice.xml:253-257``). A tester comparing
  against a v15 printout will see one row fewer per section. That is the new
  design, not a defect.
* v19 adds a third heading kind, ``line_subsection``
  (``account_move_line.py:338``), which v15 had no equivalent for.

The known collapsed-line case
-----------------------------
``account.move.line.collapse_composition`` ("Hide Composition") is a new v19
Boolean (``account_move_line.py:349-352``). When it is set, the section is
rendered through the *grouped* branch instead
(``report_invoice.xml:280-360``), whose ``line_colspan`` is computed by the
same Product-column-unaware formula at :286 and whose row **loses the
``o_line_section`` class altogether** (:301-304) — so a short collapsed row
cannot be identified by CSS class at all, only by its
``account_invoice_line_name_grouped_desktop`` cell. This case reproduces that
on a throwaway *draft* fixture so the shortfall is measured rather than
guessed, and then searches the gallery's own posted and draft customer
invoices for any line that actually carries the flag. The workbook says
Novobi does not expect any; if one is found it is reported as a FINDING with
its invoice number. Neither is asserted — the workbook's Expected Result
covers the ordinary invoice only.

Safety
------
Everything created is ``FG07``-marked and swept before and after. The long
invoice is POSTED, which the workbook's State After The Test requires ("One
long posted invoice. Keep it"), so its id is dropped from ``created`` the
moment it posts — a posted ``account.move`` is never handed to ``unlink()``.
The collapsed-line probe stays in draft precisely so it can be removed. No
pre-existing invoice, template, layout or paper format is read for anything
but evidence, and none is written.
"""
from __future__ import annotations

import csv
import re
from html.parser import HTMLParser

from adapters.base import OdooRPCError
from framework.registry import test_case
from tests.fg07.common import (INVOICE_REPORT, MARK, NO_MMG_INVOICE_TEMPLATE,
                               WORKFLOW, WORKFLOW_NAME, acting_company,
                               cleanup, company_ctx, finding, make_partner,
                               make_product, module_state, money, observation,
                               report_html, report_pdf, require_module,
                               require_v19, residual_manual_step,
                               structured_invoice_lines, sweep_fg07, trace,
                               wkhtmltopdf_state)

ROWS_CSV = "TC-INV-002-line-table-rows.csv"
ROWS_HEADER = ["invoice", "row_index", "row_kind", "css_classes",
               "visible_cells", "visible_colspan", "table_columns",
               "short_by", "first_cell_text"]

PDF_NAME = "TC-INV-002-long-invoice.pdf"
HTML_NAME = "TC-INV-002-long-invoice.html"
COLLAPSED_HTML_NAME = "TC-INV-002-collapsed-section.html"

# The workbook asks for "25 or more product lines". 26 is used so the count is
# unambiguously over the line rather than exactly on it, and so the two
# sections split it evenly (13 / 13).
N_PRODUCT_LINES = 26

# "One line whose description runs to three or more lines of text" (workbook
# Test Data). ONE paragraph, deliberately with no hard newlines in it:
# has_long_desc at report_invoice.xml:172 trips at more than 30 newlines in a
# single line name and then forces the thead to display:table-row-group, which
# STOPS the column headings repeating on page 2 — a fixture built with 31
# newlines would therefore fail the workbook's own step 7 for a reason that
# has nothing to do with the template under test.
LONG_DESC_START = "FG07-LONGDESC-START"
LONG_DESC_END = "FG07-LONGDESC-END"
LONG_DESC = (
    f"{LONG_DESC_START} Navajo silver and turquoise squash blossom necklace, "
    f"circa 1940, acquired from the estate of a private collector in Santa "
    f"Fe; the piece carries its original hand-stamped naja, twelve blossoms "
    f"set with hand-cut Blue Gem turquoise, and is accompanied by a written "
    f"condition report describing two replaced beads and one professionally "
    f"repaired clasp, all of which must appear on the printed invoice "
    f"without pushing the price columns out of alignment. {LONG_DESC_END}"
)

# The v19 row classes at report_invoice.xml:219-223, in the workbook's own
# vocabulary. The If It Fails column asks which of the three a short row was,
# "because those are three different rows in the template".
ROW_CLASS_LABEL = {
    "o_line_section": "section",
    "o_line_subsection": "sub-section",
    "o_line_note": "note",
}
# The grouped/collapsed branch (report_invoice.xml:307) emits no row class at
# all, so it has to be recognised by the name of its description cell.
GROUPED_CELL = "account_invoice_line_name_grouped_desktop"
PRODUCT_CELLS = ("account_invoice_line_name", "td_subtotal")

# Totals block, report_invoice.xml:370 and :591.
TOTALS_TABLE_CLASS = "o_total_table"
TOTALS_NOBREAK_CLASS = "avoid-page-break-inside"
TOTALS_ROW_CLASS = "o_total"

# The pdf-mode page-number placeholder pair, report_templates.xml:368 etc.
# 'page' alone is useless as a probe — web.html_container also emits
# <div class="page">. 'topage' appears only in the footer pair.
PAGE_PLACEHOLDER_RE = re.compile(r'class="[^"]*\btopage\b[^"]*"')
# Uncompressed PDF page objects. '(?![a-zA-Z])' keeps /Type /Pages (the page
# TREE node, of which there is exactly one) out of the count.
PDF_PAGE_RE = re.compile(rb"/Type\s*/Page(?![a-zA-Z])")

CSV_LIMIT = 500


def _classes(attrs: dict) -> set:
    return {token for token in (attrs.get("class") or "").split() if token}


def _colspan(raw) -> int:
    """A cell's colspan, defaulting to 1 the way HTML does."""
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return 1
    return value if value > 0 else 1


class _InvoiceTableParser(HTMLParser):
    """Reads the invoice line table and the totals block out of the report.

    Hand-written rather than pulled from a library: the platform ships no
    HTML parsing dependency, and the two facts this case needs are purely
    structural — how many ``<th>`` the head declares, and what each body
    row's non-``d-none`` cells add up to.

    The line table is located by ``name="invoice_line_table"``
    (``report_invoice.xml:173``) rather than by position, so the header block
    and the totals table cannot be mistaken for it. The line table contains
    no nested table in any Odoo or MMG version read for this case; the depth
    counter is kept anyway so a future nested one degrades into "ignored"
    rather than into wrong arithmetic.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.table_depth = 0
        self._line_table_depth = 0
        self._in_head = False
        self._row = None
        self._cell = None
        self.thead_style = ""
        self.has_thead = False
        self.head_cells: list[dict] = []
        self.body_rows: list[dict] = []
        self.table_classes: list[set] = []
        self.row_classes: list[set] = []
        self.parse_error = ""

    # -- helpers -----------------------------------------------------------
    def _inside(self) -> bool:
        return bool(self._line_table_depth)

    def _new_cell(self, attrs: dict) -> dict:
        return {"name": attrs.get("name") or "", "classes": _classes(attrs),
                "colspan": _colspan(attrs.get("colspan")), "text": []}

    # -- HTMLParser --------------------------------------------------------
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "table":
            self.table_depth += 1
            self.table_classes.append(_classes(attrs))
            if (attrs.get("name") == "invoice_line_table"
                    and not self._line_table_depth):
                self._line_table_depth = self.table_depth
            return
        if tag == "thead":
            if self._inside():
                self._in_head = True
                self.has_thead = True
                self.thead_style = attrs.get("style") or ""
            return
        if tag == "tr":
            self.row_classes.append(_classes(attrs))
            if self._inside() and not self._in_head:
                self._row = {"classes": _classes(attrs), "cells": []}
            return
        if tag == "th" and self._inside() and self._in_head:
            cell = self._new_cell(attrs)
            self.head_cells.append(cell)
            self._cell = cell
            return
        if tag == "td" and self._row is not None and self._cell is None:
            cell = self._new_cell(attrs)
            self._row["cells"].append(cell)
            self._cell = cell

    def handle_endtag(self, tag):
        if tag == "table":
            if self._line_table_depth and self.table_depth == self._line_table_depth:
                self._line_table_depth = 0
                self._in_head = False
                self._row = None
                self._cell = None
            self.table_depth = max(0, self.table_depth - 1)
            return
        if tag == "thead":
            self._in_head = False
            self._cell = None
            return
        if tag == "tr":
            if self._row is not None:
                self.body_rows.append(self._row)
            self._row = None
            self._cell = None
            return
        if tag in ("td", "th"):
            self._cell = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell["text"].append(data)


def _parse_report(html_text: str) -> _InvoiceTableParser:
    parser = _InvoiceTableParser()
    try:
        parser.feed(html_text)
        parser.close()
    except Exception as exc:               # noqa: BLE001
        # A page this parser chokes on is itself evidence about the report;
        # it must not become an AUTOMATION_ERROR. Whatever was parsed before
        # the error is kept and the reason is reported by the caller.
        parser.parse_error = f"{type(exc).__name__}: {exc}"
    return parser


def _cell_text(cell: dict) -> str:
    return " ".join("".join(cell["text"]).split())


def _visible(cells) -> list:
    """Cells that actually occupy a column in the printed table.

    In ``report_type='pdf'`` the only ``d-none`` cell in a section row is the
    mobile duplicate at ``report_invoice.xml:265``, which exists so the html
    preview can collapse two columns into one. Counting it would inflate
    every section row by 2 and turn a real defect into a pass.
    """
    return [cell for cell in cells if "d-none" not in cell["classes"]]


def _row_kind(row: dict) -> str:
    for token, label in ROW_CLASS_LABEL.items():
        if token in row["classes"]:
            return label
    names = {cell["name"] for cell in row["cells"]}
    if GROUPED_CELL in names:
        return "collapsed section (grouped, carries no row class)"
    if names.intersection(PRODUCT_CELLS):
        return "product"
    return "other"


def _row_label(row: dict) -> str:
    for cell in _visible(row["cells"]):
        text = _cell_text(cell)
        if text:
            return text[:80]
    return ""


def _measure(parser: _InvoiceTableParser) -> tuple:
    """``(n_cols, measured_rows)`` for one parsed report.

    ``n_cols`` counts only the ``<th>`` that are not ``d-none``; in pdf mode
    none of them is, but the filter keeps the two modes comparable if anyone
    ever renders this in html mode by mistake.
    """
    n_cols = len(_visible(parser.head_cells))
    measured = []
    for index, row in enumerate(parser.body_rows, start=1):
        cells = _visible(row["cells"])
        span = sum(cell["colspan"] for cell in cells)
        measured.append({
            "index": index,
            "kind": _row_kind(row),
            "classes": " ".join(sorted(row["classes"])),
            "cells": len(cells),
            "span": span,
            # The whole printed row, so a search for the long description does
            # not have to guess which cell it landed in: with the MMG Product
            # column in place the FIRST cell of a product row is the product
            # name, not the description.
            "text": " ".join(_cell_text(cell) for cell in cells).strip(),
            # A note row carries colspan="99" (report_invoice.xml:273), which
            # is MORE than the table width, not less. The workbook's question
            # is "does it stop one column short?", so only a shortfall counts.
            "short_by": max(0, n_cols - span),
            "label": _row_label(row),
        })
    return n_cols, measured


@test_case(
    id="TEST-FG07-INV-002",
    name="A long, sectioned invoice still prints correctly across pages",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module="mmg_account",
    priority="P1",
    kind="HYBRID",
    order=704,
    description="Builds and posts a 26-line invoice with two sections, a note "
                "and a three-line description, prints it, and proves from the "
                "rendered report that the head repeats, that every section "
                "and note row spans the full — Product-column-widened — table "
                "width, that no product row is pushed out of alignment, that "
                "the totals block carries avoid-page-break-inside, and that "
                "the page-number placeholders survive.",
    traceability=trace("TC-INV-002"))
def test_inv_002(ctx):
    rpc = ctx.adapter.rpc
    created = {"account.move": [], "product.product": [], "res.partner": []}
    evidence: list[list] = []
    residual: list[str] = []
    # Declared before the try: the evidence block runs from `finally` and must
    # never raise a NameError over a step that an earlier assertion skipped —
    # that would replace a real FAILED verdict with an AUTOMATION_ERROR.
    html_text = ""
    pdf_blob = b""
    collapsed_html = ""
    n_cols = 0
    measured: list[dict] = []
    head_names: list[str] = []
    parser = None
    page_count = 0
    move_id = 0
    amount_total = 0.0

    with ctx.step("Precondition (workbook): TC-INV-001 has passed — Odoo 19 "
                  "carrying the MMG invoice template, and this user can "
                  "create and post invoices"):
        require_v19(ctx)
        # The Product column is what makes this case different from a stock
        # Odoo pagination check, and it is mmg_account that adds it
        # (mmg_account/report/report_invoice.xml, xpath before th_description).
        # Without that module there is nothing here to widen, so the case is
        # BLOCKED rather than passed vacuously.
        require_module(ctx, "mmg_account", NO_MMG_INVOICE_TEMPLATE)
        # The v15 module name, probed only to say out loud that it is ABSENT
        # BY DESIGN. mmg_account absorbed mmg_change_invoice_template in the
        # v19 port (decision D1, mmg_account/__manifest__.py), so on a correct
        # staging_19 database this reads 'no such module row' and that is the
        # right answer — nothing here gates on it.
        template_state = module_state(rpc, "mmg_change_invoice_template")
        ctx.log(f"mmg_change_invoice_template state: "
                f"{template_state or 'no such module row'} "
                f"(expected: absent — mmg_account absorbed it in v19, "
                f"decision D1). It is mmg_account/report/report_invoice.xml "
                f"that now forces display_discount to False, which removes "
                f"the Disc.% column and therefore changes the expected table "
                f"width by one. This case reads the width from the rendered "
                f"head rather than assuming it, so either state is handled")
        company = acting_company(ctx)
        ctx.log(f"acting company #{company['id']} {company['name']!r} — "
                f"company currency {company['currency_name']}")
        sweep_fg07(ctx)

    try:
        with ctx.step("Steps 1-4 (workbook): create the invoice with two Add "
                      "a section, one Add a note, 26 product lines and one "
                      "three-line description, then Save and Confirm"):
            partner_id = make_partner(ctx, "INV-002 Exhibition Buyer",
                                      company=company)
            created["res.partner"].append(partner_id)
            product_id = make_product(ctx, "INV-002 Gallery Piece", 100.0)
            created["product.product"].append(product_id)

            lines = structured_invoice_lines(product_id,
                                             n_product=N_PRODUCT_LINES,
                                             long_text=LONG_DESC)
            move_id = rpc.call("account.move", "create", {
                "move_type": "out_invoice",
                "partner_id": partner_id,
                "invoice_origin": f"{MARK}-INV-002",
                "invoice_line_ids": lines,
            }, context=company_ctx(company))
            created["account.move"].append(move_id)

            # Count what actually landed, rather than what was asked for: a
            # line the ORM refused (or silently retyped) would invalidate the
            # whole fixture, and every figure below would then be measuring
            # the wrong document.
            counts = {}
            for display_type in ("product", "line_section", "line_subsection",
                                 "line_note"):
                counts[display_type] = len(rpc.search(
                    "account.move.line",
                    [("move_id", "=", move_id),
                     ("display_type", "=", display_type)]))
            ctx.log(f"invoice #{move_id} line make-up: {counts}")
            ctx.check_true(
                "The invoice carries the 25-or-more product lines, two "
                "section headings and one note row the workbook's Test Data "
                "calls for",
                counts["product"] >= 25 and counts["line_section"] >= 2
                and counts["line_note"] >= 1,
                actual_desc=f"{counts['product']} product line(s), "
                            f"{counts['line_section']} section(s), "
                            f"{counts['line_subsection']} sub-section(s), "
                            f"{counts['line_note']} note(s)")

            posted = False
            try:
                rpc.call("account.move", "action_post", [move_id],
                         context=company_ctx(company))
                posted = True
            except OdooRPCError as exc:
                # Never let this escape: an invoice that refuses to post is a
                # product finding, and it has to be recorded as a failed
                # assertion rather than as a broken test.
                ctx.log(f"action_post refused invoice #{move_id}: {exc}")
            row = rpc.read("account.move", [move_id],
                           ["name", "state", "amount_total"])[0]
            invoice_name = row.get("name") or f"#{move_id}"
            amount_total = money(row.get("amount_total"))
            ctx.check_true(
                f"Confirm posts the long invoice ({invoice_name})",
                posted and row.get("state") == "posted",
                actual_desc=f"state={row.get('state')!r}, "
                            f"total={amount_total:.2f}")
            if row.get("state") == "posted":
                # Dropped from `created` the instant it posts: cleanup must
                # never hand a posted account.move to unlink(), and the
                # workbook's State After The Test says to keep this one.
                created["account.move"] = [
                    i for i in created["account.move"] if i != move_id]
                ctx.log(f"invoice #{move_id} {invoice_name!r} removed from the "
                        f"cleanup list — it is POSTED, and the workbook's "
                        f"State After The Test is 'One long posted invoice. "
                        f"Keep it — TC-INV-003 can reuse it.'")

        with ctx.step("Steps 5-6 (workbook): Click Print, open the PDF, and "
                      "check that it is more than one page"):
            status, html_text = report_html(ctx, INVOICE_REPORT, move_id,
                                            report_type="pdf")
            ctx.log(f"GET /report/html/{INVOICE_REPORT}/{move_id}"
                    f"?report_type=pdf -> HTTP {status}, "
                    f"{len(html_text)} character(s)")
            # Asserted, not assumed: a 500 here IS the finding, and without a
            # body there is nothing for the rest of the case to read.
            ctx.check(f"The Print route renders the invoice "
                      f"({INVOICE_REPORT})", 200, status)

            state = wkhtmltopdf_state(ctx)
            ctx.log(f"ir.actions.report.get_wkhtmltopdf_state() -> "
                    f"{state or '(unavailable)'}")
            if state == "ok":
                pdf_status, pdf_blob = report_pdf(ctx, INVOICE_REPORT, move_id)
                ctx.log(f"GET /report/pdf/{INVOICE_REPORT}/{move_id} -> HTTP "
                        f"{pdf_status}, {len(pdf_blob)} byte(s)")
                page_count = len(PDF_PAGE_RE.findall(pdf_blob))
                ctx.log(f"PDF page objects counted: {page_count}")
            else:
                residual.append(
                    "the PAGE COUNT could not be measured: this server "
                    f"reports get_wkhtmltopdf_state() = {state or 'unknown'!r}, "
                    "so no PDF was produced. Print the invoice from the "
                    "Odoo UI and confirm the workbook's 'more than one page' "
                    "by eye. The rendered HTML is attached as "
                    + HTML_NAME + " and shows the same document without "
                    "pagination.")

        with ctx.step("Reading the printed line table: how many columns the "
                      "head declares, and how wide every row actually is"):
            parser = _parse_report(html_text)
            if parser.parse_error:
                ctx.log(f"the report HTML did not parse cleanly "
                        f"({parser.parse_error}) — whatever was read before "
                        f"the error is still reported below")
            n_cols, measured = _measure(parser)
            head_names = [cell["name"] or _cell_text(cell)
                          for cell in _visible(parser.head_cells)]
            ctx.log(f"line table head: {n_cols} column(s) -> {head_names}")
            # Context, not a verdict: whether the Product column is present at
            # all is TC-INV-001's expected result, not this case's. It is
            # logged because every number below is relative to it.
            if any(cell["name"] == "th_product"
                   for cell in parser.head_cells):
                ctx.log("the MMG 'Product' column IS present in the head "
                        "(th_product) — the line table is one column wider "
                        "than stock Odoo, which is exactly the condition the "
                        "workbook's READ THIS FIRST paragraph describes")
            else:
                finding(ctx, "the MMG 'Product' column (th_product) is NOT in "
                             "the printed head even though mmg_account "
                             "reports as installed — its xpath into "
                             "account.report_invoice_document did not apply. "
                             "That is TC-INV-001's expected result, so raise "
                             "it there; every width below is measured against "
                             "the head that actually rendered.")

            for row in measured:
                evidence.append(["long invoice", row["index"], row["kind"],
                                 row["classes"], row["cells"], row["span"],
                                 n_cols, row["short_by"], row["label"]])
                if row["short_by"]:
                    ctx.log(f"  row {row['index']} ({row['kind']}) "
                            f"{row['label']!r}: {row['span']} of {n_cols} "
                            f"column(s) — SHORT BY {row['short_by']}")
            ctx.log(f"{len(measured)} body row(s) measured; "
                    f"{sum(1 for r in measured if r['short_by'])} stop short "
                    f"of the {n_cols}-column head")

            observation(ctx,
                        "Odoo 19 no longer prints a separate 'Subtotal' row "
                        "after each section the way v15 did: the section "
                        "subtotal is now printed inline, in the section row's "
                        "own trailing cell, from the public "
                        "account.move.line.get_section_subtotal() / "
                        "get_section_total() (addons/account/models/"
                        "account_move_line.py:3642-3648, used at "
                        "addons/account/views/report_invoice.xml:253-257). A "
                        "tester holding a v15 printout will count one row "
                        "fewer per section. That is the new design.")
            if any("sub-section" == row["kind"] for row in measured):
                observation(ctx,
                            "this invoice contains at least one SUB-SECTION "
                            "row. line_subsection is a heading kind that did "
                            "not exist in v15 (addons/account/models/"
                            "account_move_line.py:338); it is a third row "
                            "shape the template has to widen, and the "
                            "workbook's If It Fails column asks you to name "
                            "it separately from a section.")

        with ctx.step("Why It Matters (workbook): the known collapsed-line "
                      "case — reproduce it, then look for one in the "
                      "gallery's own invoices"):
            # Part 1 — measure the known case instead of describing it. A
            # throwaway DRAFT invoice is used so it can be deleted again; the
            # colspan arithmetic is identical in draft and posted state.
            has_flag = rpc.field_exists("account.move.line",
                                        "collapse_composition")
            if not has_flag:
                ctx.log("account.move.line has no 'collapse_composition' "
                        "field on this database, so the collapsed-line case "
                        "the workbook warns about cannot arise here")
            else:
                probe_id = 0
                try:
                    probe_id = rpc.call("account.move", "create", {
                        "move_type": "out_invoice",
                        "partner_id": partner_id,
                        "invoice_origin": f"{MARK}-INV-002-COLLAPSED",
                        "invoice_line_ids": structured_invoice_lines(
                            product_id, n_product=4),
                    }, context=company_ctx(company))
                    created["account.move"].append(probe_id)
                    section_ids = rpc.search(
                        "account.move.line",
                        [("move_id", "=", probe_id),
                         ("display_type", "=", "line_section")])
                    if section_ids:
                        rpc.write("account.move.line", [section_ids[0]],
                                  {"collapse_composition": True})
                        ctx.log(f"probe invoice #{probe_id}: set Hide "
                                f"Composition on section line "
                                f"#{section_ids[0]}")
                except OdooRPCError as exc:
                    ctx.log(f"could not build the collapsed-line probe "
                            f"({exc}) — the known case is described in this "
                            f"module's docstring but was not measured here")
                if probe_id:
                    c_status, collapsed_html = report_html(
                        ctx, INVOICE_REPORT, probe_id, report_type="pdf")
                    ctx.log(f"GET /report/html/{INVOICE_REPORT}/{probe_id}"
                            f"?report_type=pdf -> HTTP {c_status}")
                    if c_status == 200:
                        c_parser = _parse_report(collapsed_html)
                        c_cols, c_rows = _measure(c_parser)
                        for row in c_rows:
                            evidence.append(
                                ["collapsed probe", row["index"], row["kind"],
                                 row["classes"], row["cells"], row["span"],
                                 c_cols, row["short_by"], row["label"]])
                        short = [r for r in c_rows
                                 if r["short_by"] and r["kind"].startswith(
                                     "collapsed")]
                        if short:
                            finding(ctx,
                                    "the KNOWN CASE reproduces on this "
                                    "database: a section with Hide "
                                    "Composition ticked prints "
                                    f"{short[0]['span']} of {c_cols} columns, "
                                    f"short by {short[0]['short_by']}. Note "
                                    "that the grouped branch emits NO row "
                                    "class (addons/account/views/"
                                    "report_invoice.xml:301-304), so this "
                                    "short row cannot be reported as "
                                    "'o_line_section' — describe it to Novobi "
                                    "as 'a collapsed section row'.")
                        else:
                            ctx.log("the collapsed-section probe printed at "
                                    "full width on this database — the known "
                                    "case does not reproduce here")

            # Part 2 — the question the workbook actually asks the tester:
            # "Novobi does not expect the gallery's data to contain any, so if
            # you see a short row, say so, because it means the data does
            # contain one." Read-only, fixtures excluded, never asserted:
            # the Expected Result column covers the ordinary invoice only.
            if has_flag:
                try:
                    real = rpc.search_read(
                        "account.move.line",
                        [("collapse_composition", "=", True),
                         ("display_type", "in",
                          ("line_section", "line_subsection")),
                         ("company_id", "=", company["id"]),
                         ("move_id.move_type", "in",
                          ("out_invoice", "out_refund")),
                         "!", ("move_id.partner_id.name", "like",
                               f"{MARK} %")],
                        ["move_id", "name", "display_type"], limit=50)
                except OdooRPCError as exc:
                    real = []
                    ctx.log(f"could not scan for collapsed sections in live "
                            f"data ({exc})")
                if real:
                    names = sorted({str(item.get("move_id")) for item in real})
                    finding(ctx,
                            f"{len(real)} line(s) in this company's own "
                            f"customer invoices carry Hide Composition "
                            f"(collapse_composition=True): {names[:10]}. The "
                            f"workbook says Novobi does not expect the "
                            f"gallery's data to contain any, so this is worth "
                            f"reporting on its own — those invoices will "
                            f"print a short heading row.")
                    residual.append(
                        f"open the {len(real)} customer invoice line(s) listed "
                        f"in the log as carrying Hide Composition and confirm "
                        f"with Novobi whether they were meant to. They are "
                        f"the collapsed case the workbook's READ THIS FIRST "
                        f"paragraph warns about.")
                else:
                    ctx.log("no customer invoice line in this company carries "
                            "Hide Composition — the gallery's data contains "
                            "none of the known collapsed case, as Novobi "
                            "expects")

        with ctx.step("Steps 6-7 / Expected line 1: more than one page, with "
                      "the column headings repeated on each page"):
            ctx.check_true(
                "The printed invoice has a table head to repeat "
                "(<thead> in invoice_line_table)",
                parser.has_thead and n_cols > 0,
                actual_desc=f"thead present={parser.has_thead}, "
                            f"{n_cols} column heading(s)")
            # display:table-row-group demotes the thead to an ordinary row
            # group, which is exactly what stops wkhtmltopdf repainting it at
            # the top of page 2. Odoo applies it only when has_long_desc is
            # true (report_invoice.xml:172-174).
            style = " ".join(parser.thead_style.split())
            ctx.check_true(
                "The table head is NOT demoted with "
                "'display: table-row-group', so it repeats at the top of "
                "every page (report_invoice.xml:174)",
                "table-row-group" not in style.replace(" ", ""),
                actual_desc=f"<thead style={style!r}>")
            if page_count:
                ctx.check_true(
                    "The printed invoice runs to more than one page",
                    page_count > 1,
                    actual_desc=f"{page_count} page(s) in the rendered PDF")
                residual.append(
                    f"open {PDF_NAME} and confirm on PAGE 2 AND AFTER that the "
                    f"column headings ({', '.join(head_names)}) are repainted "
                    f"at the top of the table. The PDF has {page_count} "
                    f"page(s). Only the fact that the head is allowed to "
                    f"repeat can be read from the markup; whether wkhtmltopdf "
                    f"actually repainted it has to be seen.")
            else:
                residual.append(
                    "the PAGE COUNT and the 'headings repeated on page 2' "
                    "check could not be measured from the markup. Print the "
                    "invoice from Accounting > Customers > Invoices and "
                    "confirm both by eye; the structural precondition (the "
                    "head is not demoted to a row group) has been asserted "
                    "above.")

        with ctx.step("Step 9 / Expected line 3: the long description wraps "
                      "inside its cell; no column is pushed out of alignment"):
            # The wrap is a pixel fact. What breaks the LAYOUT — and what a
            # tester sees as 'columns drift' — is a row whose cells no longer
            # add up to the header width, and that is measurable.
            described = [row for row in measured
                         if LONG_DESC_START in row["text"]]
            # "Whole, inside its cell" means BOTH markers in the SAME product
            # row — a truncated description, or one that spilled into a
            # neighbouring cell or out of the table altogether, would satisfy
            # "the closing marker is somewhere on the page" while failing the
            # workbook's line 3 outright.
            whole = [row for row in described
                     if LONG_DESC_END in row["text"]
                     and row["kind"] == "product"]
            ctx.check_true(
                "The three-line description was printed on the invoice WHOLE "
                "and inside one product row of the line table — its opening "
                "and closing text both in the same row, neither truncated nor "
                "pushed outside the table",
                bool(whole),
                actual_desc=f"{len(described)} row(s) carry the opening marker "
                            f"{LONG_DESC_START!r}; {len(whole)} of them are a "
                            f"product row also carrying the closing marker "
                            f"{LONG_DESC_END!r}; the closing marker is "
                            f"{'present' if LONG_DESC_END in html_text else 'MISSING'} "
                            f"somewhere in the rendered report")
            misaligned = [
                f"row {row['index']} ({row['kind']}) {row['label']!r}: "
                f"{row['span']} column(s) against a {n_cols}-column head"
                for row in measured
                if row["kind"] == "product" and row["span"] != n_cols]
            # Listed rather than counted, so a failure names every offending
            # row instead of just saying 'some row is wrong'.
            ctx.check("No product line is pushed out of alignment — every "
                      "product row fills exactly the columns the head "
                      "declares", [], misaligned)
            residual.append(
                f"open {HTML_NAME} (or {PDF_NAME}) at the line beginning "
                f"'{LONG_DESC_START}' and confirm the text WRAPS inside the "
                f"Description cell rather than running under the Quantity, "
                f"Unit Price or Amount columns. The cell arithmetic is "
                f"already proven correct above; only the visual wrap is left.")

        with ctx.step("Step 10 / Expected line 4: the totals block is "
                      "complete and not split in half"):
            totals_tables = [classes for classes in parser.table_classes
                             if TOTALS_TABLE_CLASS in classes]
            ctx.check_true(
                "The invoice prints a totals block (table.o_total_table, "
                "report_invoice.xml:370)",
                bool(totals_tables),
                actual_desc=f"{len(totals_tables)} totals table(s) found in "
                            f"the rendered report")
            ctx.check_true(
                "The totals block is marked 'avoid-page-break-inside', so it "
                "cannot be split across two pages",
                any(TOTALS_NOBREAK_CLASS in classes
                    for classes in totals_tables),
                actual_desc="; ".join(" ".join(sorted(classes))
                                      for classes in totals_tables) or "(none)")
            ctx.check_true(
                "The grand-total row is present in the totals block "
                "(tr.o_total, report_invoice.xml:591)",
                any(TOTALS_ROW_CLASS in classes
                    for classes in parser.row_classes),
                actual_desc=f"invoice total on the record is "
                            f"{amount_total:.2f} {company['currency_name']}")
            residual.append(
                f"open {PDF_NAME} at the last page and confirm the totals "
                f"block is WHOLE — either under the last line or cleanly on "
                f"its own page, never with the tax rows on one page and the "
                f"Total on the next. The record's own total is "
                f"{amount_total:.2f} {company['currency_name']}; check the "
                f"printed figure matches it.")

        with ctx.step("Step 11 / Expected line 5: the page numbering runs "
                      "correctly"):
            placeholders = PAGE_PLACEHOLDER_RE.findall(html_text)
            # wkhtmltopdf substitutes these placeholders from its own
            # JavaScript (addons/web/views/report_templates.xml:247), so the
            # NUMBERS never appear in the HTML. Their absence, however, would
            # mean the printed invoice carries no page numbers at all.
            ctx.check_true(
                "The printed layout still emits its page-number footer "
                "('Page <span class=\"page\"/> / <span class=\"topage\"/>')",
                bool(placeholders),
                actual_desc=f"{len(placeholders)} 'topage' placeholder(s) in "
                            f"the pdf-mode render")
            residual.append(
                f"open {PDF_NAME} and confirm the footer reads 'Page 1 / N', "
                f"'Page 2 / N' … with no gap and no repeat. Only the "
                f"placeholders can be read from the markup — wkhtmltopdf "
                f"fills in the numbers itself.")

        with ctx.step("Step 8 / Expected line 2: every section heading row "
                      "and the note row stretches the FULL width of the "
                      "table — none stops one column short"):
            # Asserted LAST on purpose. ctx.check raises, and this is the one
            # line this case is predicted to fail: line_colspan at
            # report_invoice.xml:223 is 3 + display_discount + taxes, which
            # has never accounted for the Product column mmg_account inserts.
            # Running it first would suppress the other four expected-result
            # lines. Every figure it uses was gathered and logged several
            # steps ago and is in the CSV either way.
            short_rows = [
                f"row {row['index']} — {row['kind']} "
                f"({row['classes'] or 'no row class'}) {row['label']!r}: "
                f"{row['span']} of {n_cols} column(s), short by "
                f"{row['short_by']}"
                for row in measured
                if row["short_by"] and row["kind"] in (
                    "section", "sub-section", "note",
                    "collapsed section (grouped, carries no row class)")]
            if short_rows:
                finding(ctx,
                        "a heading or note row is narrower than the line "
                        "table. In unmodified Odoo 19 the arithmetic is "
                        "self-consistent (line_colspan = 3 + discount + taxes "
                        "at addons/account/views/report_invoice.xml:223 "
                        "matches its own three leading columns), so a "
                        "shortfall of exactly one on a database carrying "
                        "mmg_account points at the Product column that "
                        "mmg_account/report/report_invoice.xml adds without "
                        "widening line_colspan. The fix belongs in the MMG "
                        "template, not in Odoo.")
                residual.append(
                    "the workbook's If It Fails asks for the PAGE and the ROW. "
                    "The row kinds and labels are listed in the assertion "
                    f"below and in {ROWS_CSV}; open {PDF_NAME} to read off "
                    "which page each of them landed on before filing.")
            ctx.check(
                f"Every section, sub-section and note row spans the full "
                f"{n_cols}-column width of the line table — none stops one "
                f"column short", [], short_rows)
    finally:
        with ctx.step("Evidence: attach the printed invoice and write the "
                      "row-width CSV, then remove the FG07 fixtures"):
            if html_text:
                path = ctx.artifacts_dir / HTML_NAME
                try:
                    path.write_text(html_text, encoding="utf-8")
                    ctx.add_artifact(path, "log", HTML_NAME)
                    ctx.log(f"wrote the rendered report to {HTML_NAME}")
                except OSError as exc:
                    ctx.log(f"could not write {HTML_NAME} ({exc})")
            if collapsed_html:
                path = ctx.artifacts_dir / COLLAPSED_HTML_NAME
                try:
                    path.write_text(collapsed_html, encoding="utf-8")
                    ctx.add_artifact(path, "log", COLLAPSED_HTML_NAME)
                    ctx.log(f"wrote the collapsed-section probe render to "
                            f"{COLLAPSED_HTML_NAME}")
                except OSError as exc:
                    ctx.log(f"could not write {COLLAPSED_HTML_NAME} ({exc})")
            if pdf_blob:
                path = ctx.artifacts_dir / PDF_NAME
                try:
                    path.write_bytes(pdf_blob)
                    ctx.add_artifact(path, "pdf", PDF_NAME)
                    ctx.log(f"wrote {len(pdf_blob)} byte(s) to {PDF_NAME} "
                            f"({page_count or 'unknown'} page(s))")
                except OSError as exc:
                    ctx.log(f"could not write {PDF_NAME} ({exc}) — print the "
                            f"invoice from the UI instead")
            path = ctx.artifacts_dir / ROWS_CSV
            try:
                with path.open("w", newline="", encoding="utf-8") as fh:
                    writer = csv.writer(fh)
                    writer.writerow(ROWS_HEADER)
                    writer.writerows(evidence[:CSV_LIMIT])
                ctx.add_artifact(path, "log", ROWS_CSV)
                ctx.log(f"wrote {min(len(evidence), CSV_LIMIT)} row(s) to "
                        f"{ROWS_CSV}")
            except OSError as exc:
                ctx.log(f"could not write {ROWS_CSV} ({exc}) — the row widths "
                        f"above are still in this log")
            for note in residual:
                residual_manual_step(ctx, note)
            ctx.log("The posted long invoice is left in place on purpose: the "
                    "workbook's State After The Test is 'One long posted "
                    "invoice. Keep it — TC-INV-003 can reuse it.' Everything "
                    "else created here is FG07-marked and removed now.")
            cleanup(ctx, created)
