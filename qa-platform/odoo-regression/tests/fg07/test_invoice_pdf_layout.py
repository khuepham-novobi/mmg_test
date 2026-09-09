"""FG-07 — TC-INV-001: The customer invoice PDF still looks like a Medicine
Man Gallery invoice.

Implements row 32.0 (P1, "Invoice document") of the CLIENT MANUAL TESTING
GUIDELINE ``MMG_v19_Client_Manual_Testing_Guideline_FG05-FG14_v1.0.xlsx`` /
sheet ``Testing Guideline``.

The workbook's framing: *"This document goes to the customer. It has been
reshaped over the years — a Product column, no discount column, a signature
line, particular labels — and all of that has to survive the upgrade or the
gallery is sending out a generic Odoo invoice."*

The workbook's own warning — *"Work down the expected list item by item
rather than judging the page as a whole — 'it looked fine' will miss half of
these"* — is why this case renders the real report and evaluates all nine
checklist letters independently before it asserts anything.

The three Expected Result lines, and what each is read from
-----------------------------------------------------------
1. **"Every one of the nine items (a) to (i) is as described."** — read from
   the HTML the printed report actually produces, fetched over the very
   route the Print button drives: ``GET {base}/report/html/
   account.report_invoice_with_payments/{id}?report_type=pdf``
   (``tests/fg07/common.py::report_html``). The ``with_payments`` variant is
   mandatory — item (g)'s "Payment Type:" line lives inside
   ``t-if="print_with_payments"``, which only that template sets
   (``addons/account/views/report_invoice.xml:679-682``, :379). Letter by
   letter, and where each one comes from:

   * **(a) "Invoice Address:" above the customer address** — from the v15
     override ``mmg_change_invoice_template/views/report_invoice.xml:6-17``,
     which replaces ``//t[@t-set='address']``. **Odoo 19 has THREE
     ``<t t-set="address">`` nodes** — one per address branch:
     ``address_not_same_as_shipping`` (``addons/account/views/
     report_invoice.xml:18-19``), ``address_same_as_shipping`` (:32-33) and
     ``no_shipping`` (:46-47) — and ``position="replace"`` patches only the
     FIRST match. See "A finding this case will surface" below.
   * **(b) a first Product column on every line** — from
     ``mmg_account/report/report_invoice.xml:11-21``, which inserts
     ``<th name="th_product">`` before ``th_description``
     (``addons/account/views/report_invoice.xml:176``) and
     ``<td name="account_invoice_line_product">`` before
     ``account_invoice_line_name`` (:225). Read from the rendered
     ``name="invoice_line_table"`` (:173).
   * **(c) NO "Disc.%" column** — from
     ``mmg_change_invoice_template/views/report_invoice.xml:52-54``, which
     forces ``display_discount`` to ``False``; the stock header is
     ``<th name="th_discount">`` with the literal text ``Disc.%``
     (``addons/account/views/report_invoice.xml:179-181``).
   * **(d) the header label reads "Order Number:", not "Source"** — from
     ``mmg_change_invoice_template/views/report_invoice.xml:24-26``
     replacing ``//div[@name='origin']/strong[1]``; v19's stock label is the
     bare word ``Source`` (``addons/account/views/report_invoice.xml:
     146-149``).
   * **(e) no Invoice Date / Due Date / Customer Code / Reference blocks** —
     four ``position="replace"`` xpaths at
     ``mmg_change_invoice_template/views/report_invoice.xml:29, 32, 35, 38``
     against ``addons/account/views/report_invoice.xml:127, 134, 150, 154``.
   * **(f) the invoice number is not next to the word "Invoice"** — from
     ``mmg_change_invoice_template/views/report_invoice.xml:20-21``,
     removing ``//span[@t-field='o.name']``
     (``addons/account/views/report_invoice.xml:121``). That span sits
     inside ``layout_document_title``, which every ``web.external_layout``
     variant renders into an ``<h2>`` (``addons/web/views/
     report_templates.xml:360, 420, 484, 548, 581, 707, 792``) — so the
     assertion is made INSIDE the heading, never over the whole page.
   * **(g) "Payment Type:" under each payment line** — from
     ``mmg_account/report/report_invoice.xml:5-9``, inserted after
     ``//t[@t-foreach='payments_vals']/tr/td[1]/i``
     (``addons/account/views/report_invoice.xml:382-389``). The two values
     it prints come from ``account.move.invoice_payments_widget``:
     ``journal_name`` is ``counterpart_line.journal_id.name`` and
     ``payment_method_name`` is
     ``payment_id.payment_method_line_id.name``
     (``addons/account/models/account_move.py:1562, 1569``).
   * **(h) a "Merchandise Received By:" signature line** — from
     ``mmg_change_invoice_template/views/report_invoice.xml:57-61``,
     inserted after ``//div[@id='qrcode']``
     (``addons/account/views/report_invoice.xml:480``).
   * **(i) no "Payment Communication:" paragraph** — from
     ``mmg_change_invoice_template/views/report_invoice.xml:41``, removing
     ``//p[@name='payment_communication']``
     (``addons/account/views/report_invoice.xml:471``).

2. **"The page renders with no blank boxes, no overlapping text and no
   missing totals."** — the HTTP status of the render, the presence of
   ``name="invoice_line_table"``, a non-empty Product and Amount cell on
   every product row, and a ``<tr class="o_total">`` carrying a non-empty
   figure (``addons/account/views/report_invoice.xml:589-596``). *Overlapping
   text is a pixel property of the wkhtmltopdf raster and cannot be read out
   of HTML* — it is left as a RESIDUAL MANUAL STEP with the real PDF
   attached.

3. **"Nothing else has visibly changed against the old printout."** — the
   platform does not hold the Novobi printout and must not invent one. This
   line is a RESIDUAL MANUAL STEP, with the rendered HTML of both fixtures
   and the PDF attached as artifacts so the tick-off is a comparison rather
   than a memory test.

The diagnostic layer the workbook cannot describe
-------------------------------------------------
Before a single pixel is read, the DEPLOYED arch of both override views is
fetched (``ir.model.data`` -> ``ir.ui.view.arch``) and all FIFTEEN inherited
xpath expressions — eleven from ``mmg_change_invoice_template``, four from
``mmg_account`` — are checked for presence. That turns the vague verdict
"the PDF looks wrong" into "xpath N of module M is not in the deployed
view", which is the difference between a layout complaint and a five-minute
fix. It is asserted AFTER the nine letters, because the letters are the
workbook's own Expected Result and must be the headline verdict; the full
xpath verdict is logged and written to CSV before either assertion runs, so
it survives whichever one fails first.

Documented adaptation — HTML is read, the PDF is attached
----------------------------------------------------------
``/report/pdf/...`` returns a wkhtmltopdf raster; nothing in it can be
addressed by element name. So every one of the nine letters is evaluated
against ``/report/html/...?report_type=pdf`` — the same QWeb template, the
same ``report_type`` value the PDF pipeline sets
(``odoo/addons/base/models/ir_actions_report.py:817``), so the
``report_type == 'html'`` branches that add mobile-only cells are NOT taken
and the document read here is the document that gets printed. The actual PDF
is fetched separately and attached as ``TC-INV-001-invoice.pdf``, because the
workbook's *If It Fails* says "ATTACH THE ACTUAL PDF, not a screenshot". When
``ir.actions.report.get_wkhtmltopdf_state()`` is not ``ok`` the PDF half is
recorded as an environment fact and the HTML assertions continue — a QA
container without wkhtmltopdf is not a product defect.

Two fixtures, deliberately
---------------------------
* **Invoice A** — the ordinary case. ``partner_shipping_id`` is left to
  ``_compute_partner_shipping_id``, which for a contact with no delivery
  child returns the contact itself (``addons/account/models/
  account_move.py:1026-1031``), so ``partner_shipping_id == partner_id``.
  Three lines, a Source Document, a payment reference, and one registered
  payment — exactly the workbook's Test Data.
* **Invoice B** — the same, but with an explicit different
  ``partner_shipping_id`` and a 10% discount on one line. The differing
  address exercises the other v19 address branch; the discount is what makes
  item (c) mean something, because ``display_discount`` is
  ``any(l.discount for l in lines_to_report)``
  (``addons/account/views/report_invoice.xml:167``) and on a discount-free
  invoice the Disc.% column would be absent whether or not the MMG override
  landed.

A finding this case will surface
---------------------------------
Item (a) is expected to FAIL on Invoice A under Odoo 19, and that failure is
the whole point of the case. v15's ``account.report_invoice_document`` had a
single ``<t t-set="address">``; v19 split it into three branches, and
``position="replace"`` resolves to the first match only
(``odoo/tools/template_inheritance.py``, ``locate_node``). The first match is
the ``address_not_same_as_shipping`` branch, so the gallery's "Invoice
Address:" / "Shipping Address:" block renders ONLY when the delivery address
differs from the invoice address — which on an ordinary gallery invoice it
does not. Invoice A therefore prints a stock Odoo address block and Invoice B
prints the MMG one. The two fixtures exist so the report says which branch
broke rather than "sometimes it works".

Expected v19 differences that are logged and NOT asserted (R11)
----------------------------------------------------------------
Odoo 19 added two header blocks the v15 override never knew about and
therefore never removed — ``name="taxable_supply_date"``
(``addons/account/views/report_invoice.xml:138``) and
``name="delivery_date"`` (:142), plus ``name="incoterm_id"`` (:158). The
workbook's item (e) names four blocks and only those four; new blocks are
recorded as OBSERVATIONs and asserted in neither direction.
"""
from __future__ import annotations

import csv
import re
from html import unescape

from adapters.base import OdooRPCError
from framework.registry import test_case
from tests.fg07.common import (INVOICE_REPORT, MARK, NO_MMG_INVOICE_TEMPLATE,
                               WORKFLOW, WORKFLOW_NAME, acting_company,
                               cleanup, company_ctx, confirm_payment_register,
                               finding, m2o_id, m2o_name, make_invoice,
                               make_partner, make_product, money, observation,
                               register_payment, report_html, report_pdf,
                               require_module, require_v19,
                               residual_manual_step, sweep_fg07, trace,
                               wkhtmltopdf_state)

CHECKLIST_CSV = "TC-INV-001-checklist.csv"
XPATH_CSV = "TC-INV-001-template-xpaths.csv"
PDF_NAME = "TC-INV-001-invoice.pdf"

# The two MMG modules that between them own the printed invoice. Both must be
# installed: mmg_change_invoice_template owns items (a), (c) to (f), (h) and
# (i); mmg_account owns items (b) and (g).
TEMPLATE_MODULES = ("mmg_change_invoice_template", "mmg_account")

# The Studio-side field the v15 template dereferences unconditionally inside a
# t-if. It is declared in NO module in the MMG repository — it only ever
# existed as a database-level x_ field — so a migration that did not carry it
# across makes the whole report raise rather than render badly.
LEGAL_DATE_FIELD = "x_legal_invoice_date"

# Every inherited xpath the two modules apply to account.report_invoice_document,
# verbatim from the source, with the workbook item each one implements.
# (module, xpath expr, position, what it implements)
TEMPLATE_XPATHS = (
    ("mmg_change_invoice_template", "//t[@t-set='address']", "replace",
     "item (a) — the 'Invoice Address:' / 'Shipping Address:' block"),
    ("mmg_change_invoice_template", "//span[@t-field='o.name']", "replace",
     "item (f) — removes the invoice number from the document title"),
    ("mmg_change_invoice_template", "//div[@name='origin']/strong[1]",
     "replace", "item (d) — relabels 'Source' as 'Order Number:'"),
    ("mmg_change_invoice_template", "//div[@name='invoice_date']", "replace",
     "item (e) — removes the Invoice Date block"),
    ("mmg_change_invoice_template", "//div[@name='due_date']", "replace",
     "item (e) — removes the Due Date block"),
    ("mmg_change_invoice_template", "//div[@name='customer_code']", "replace",
     "item (e) — removes the Customer Code block"),
    ("mmg_change_invoice_template", "//div[@name='reference']", "replace",
     "item (e) — removes the Reference block"),
    ("mmg_change_invoice_template", "//p[@name='payment_communication']",
     "replace", "item (i) — removes the Payment Communication paragraph"),
    ("mmg_change_invoice_template", "//div[@name='origin']", "after",
     "adds the Legal Sale Date block (dereferences "
     f"o.{LEGAL_DATE_FIELD})"),
    ("mmg_change_invoice_template", "//t[@t-set='display_discount']",
     "attributes", "item (c) — forces display_discount to False"),
    ("mmg_change_invoice_template", "//div[@id='qrcode']", "after",
     "item (h) — adds the 'Merchandise Received By:' signature line"),
    ("mmg_account", "//t[@t-foreach='payments_vals']/tr/td[1]/i", "after",
     "item (g) — adds the 'Payment Type:' line under each payment"),
    ("mmg_account", "//th[@name='th_description']", "before",
     "item (b) — adds the Product column HEADER"),
    ("mmg_account", "//td[@name='account_invoice_line_name']", "before",
     "item (b) — adds the Product column CELL on every product line"),
    ("mmg_account", "//th[@name='th_priceunit']", "attributes",
     "restyles the Unit Price header (Bootstrap 4 'text-right')"),
)

# The nine checklist letters, worded as the workbook words them (step 4).
LETTER_TEXT = {
    "a": "Above the customer's address, the words 'Invoice Address:' appear",
    "b": "The line table's FIRST column is a Product column, showing the "
         "product name on every line",
    "c": "There is NO 'Disc.%' column",
    "d": "In the header block, the label reads 'Order Number:' — not 'Source'",
    "e": "There is NO Invoice Date block, NO Due Date block, NO Customer Code "
         "and NO Reference in the header",
    "f": "The invoice number does NOT appear next to the word 'Invoice' at "
         "the top",
    "g": "Under each payment line, a line reads 'Payment Type:' followed by "
         "the journal and the payment method",
    "h": "At the bottom of the page there is a signature line reading "
         "'Merchandise Received By:'",
    "i": "There is no 'Payment Communication:' paragraph",
}

# Item (e) names exactly four header blocks. v19 ships three more that the
# v15 override never removed because they did not exist when it was written.
HEADER_BLOCKS_REMOVED = ("invoice_date", "due_date", "customer_code",
                         "reference")
HEADER_BLOCKS_NEW_IN_V19 = ("taxable_supply_date", "delivery_date",
                            "incoterm_id")


# ------------------------------------------------------------ HTML reading
# Deliberately regex-based rather than an XML parse: the rendered report is
# HTML5 with unclosed void elements, so etree.fromstring would raise on a
# perfectly good page and turn a product verdict into an AUTOMATION_ERROR.
def _text(fragment: str) -> str:
    """Visible text of an HTML fragment, entity-decoded, space-collapsed."""
    return re.sub(r"\s+", " ",
                  unescape(re.sub(r"<[^>]*>", " ", fragment or ""))).strip()


def _open_tag(page: str, tag: str, name: str) -> str:
    """The opening ``<tag ... name="<name>" ...>`` string, or ''.

    Attribute values in QWeb output never contain '>' (they are escaped), so
    ``[^>]*`` is safe here.
    """
    match = re.search(rf'<{tag}\b[^>]*\bname="{re.escape(name)}"[^>]*>', page)
    return match.group(0) if match else ""


def _element(page: str, opening: str, tag: str) -> str:
    """The whole ``<tag>…</tag>`` element whose opening tag matches ``opening``.

    Depth-counted rather than "up to the next closing tag", so a table nested
    inside the element by some other inheriting module cannot truncate it.
    """
    match = re.search(opening, page)
    if not match:
        return ""
    start = match.start()
    depth = 0
    for token in re.finditer(rf"<{tag}\b[^>]*?/>|<{tag}\b[^>]*>|</{tag}>",
                             page[start:]):
        text = token.group(0)
        if text.endswith("/>"):
            continue
        if text.startswith("</"):
            depth -= 1
            if depth <= 0:
                return page[start:start + token.end()]
        else:
            depth += 1
    return page[start:]


def _cells(row: str, tag: str) -> list:
    """The ``<td>``/``<th>`` elements of one row, in document order."""
    return re.findall(rf"<{tag}\b[^>]*>.*?</{tag}>", row, re.S)


def _rows(fragment: str) -> list:
    return re.findall(r"<tr\b[^>]*>.*?</tr>", fragment or "", re.S)


def _headings(page: str) -> list:
    """Every ``<h2>``/``<h3>`` block — where layout_document_title lands."""
    return re.findall(r"<h[23]\b[^>]*>.*?</h[23]>", page, re.S)


# ------------------------------------------------------------- evaluation
def _evaluate_letters(ctx, page: str, invoice: dict) -> dict:
    """Verdict for each of the nine workbook checklist letters.

    Returns ``{letter: (verdict, evidence)}`` where ``verdict`` is one of
    ``"pass"``, ``"FAIL"`` or ``"not proven"``. Nothing here asserts: the
    workbook says to work down the list item by item, so every letter is
    evaluated and recorded before any of them is allowed to end the test.
    """
    page_text = _text(page)
    table = _element(page, r'<table\b[^>]*\bname="invoice_line_table"[^>]*>',
                     "table")
    thead = _element(table, r"<thead\b[^>]*>", "thead")
    verdicts = {}

    # ---- (a) 'Invoice Address:' -------------------------------------------
    # Presence of the literal label, not of the address itself: the stock v19
    # branches print the address with no label at all, which is precisely the
    # difference a customer would notice.
    if "Invoice Address:" in page_text:
        verdicts["a"] = ("pass", "the label 'Invoice Address:' is on the page")
    else:
        verdicts["a"] = (
            "FAIL",
            f"'Invoice Address:' is absent. partner_shipping_id="
            f"{invoice['shipping_name']!r} vs partner_id="
            f"{invoice['partner_name']!r} -> the page took the "
            f"{invoice['address_branch']} branch of the three v19 address "
            f"branches, and mmg_change_invoice_template patches only the "
            f"first one")

    # ---- (b) the Product column -------------------------------------------
    header_cells = _cells(thead, "th")
    first_header = header_cells[0] if header_cells else ""
    header_ok = ('name="th_product"' in first_header
                 and _text(first_header) == "Product")
    bad_rows = []
    product_rows = [r for r in _rows(table)
                    if 'name="account_invoice_line_product"' in r
                    or 'name="account_invoice_line_name"' in r]
    for index, row in enumerate(product_rows, start=1):
        cells = _cells(row, "td")
        if not cells:
            bad_rows.append(f"line {index}: no cells at all")
            continue
        if 'name="account_invoice_line_product"' not in cells[0]:
            bad_rows.append(
                f"line {index}: the first cell is not "
                f"account_invoice_line_product "
                f"({_text(cells[0])[:60]!r})")
            continue
        shown = _text(cells[0])
        if not shown:
            bad_rows.append(f"line {index}: the Product cell is blank")
        elif not any(name and name in shown
                     for name in invoice["product_names"]):
            bad_rows.append(
                f"line {index}: the Product cell reads {shown!r}, which "
                f"names none of the invoice's products "
                f"{invoice['product_names']}")
    if not product_rows:
        # NOT "not proven": the workbook wants the product name on EVERY line,
        # and a table with no product row at all shows it on none of them.
        verdicts["b"] = (
            "FAIL",
            f"invoice_line_table prints no product row at all — neither a "
            f"td name='account_invoice_line_product' nor the stock "
            f"td name='account_invoice_line_name' is on the page, so the "
            f"product name is shown on NO line, let alone on every one. The "
            f"invoice's products are {invoice['product_names']}")
    elif header_ok and not bad_rows:
        verdicts["b"] = (
            "pass",
            f"first header cell is th_product 'Product'; "
            f"{len(product_rows)} product line(s) each show their product")
    else:
        detail = []
        if not header_ok:
            detail.append(f"first header cell is {_text(first_header)!r} "
                          f"({first_header[:80]!r})")
        detail.extend(bad_rows)
        verdicts["b"] = ("FAIL", "; ".join(detail))

    # ---- (c) no Disc.% column ---------------------------------------------
    # Two independent reads: the literal label a human would see, and the
    # header element that carries it. Either one surviving is a failure.
    disc_header = _open_tag(page, "th", "th_discount")
    if "Disc.%" not in page_text and not disc_header:
        verdicts["c"] = (
            "pass",
            f"no 'Disc.%' text and no th_discount element; the invoice "
            f"carries discount(s) {invoice['discounts']}, so the stock "
            f"template WOULD have shown the column"
            if any(invoice["discounts"]) else
            "no 'Disc.%' text and no th_discount element (see the residual "
            "note: this invoice carries no discount)")
    else:
        verdicts["c"] = (
            "FAIL",
            f"'Disc.%' present={('Disc.%' in page_text)}, th_discount "
            f"element={disc_header[:80]!r}")

    # ---- (d) 'Order Number:' not 'Source' ---------------------------------
    origin = _element(page, r'<div\b[^>]*\bname="origin"[^>]*>', "div")
    stock_label = re.search(r"<strong>\s*Source\s*</strong>", page)
    if not origin and invoice["origin"]:
        # A FAILURE, not "not proven". The fixture carries a Source Document,
        # so stock v19 WOULD have emitted the block
        # (addons/account/views/report_invoice.xml:146); if it is missing, the
        # label the workbook asks for is nowhere on the printed page.
        verdicts["d"] = (
            "FAIL",
            f"the header prints no name='origin' block at all although "
            f"invoice_origin={invoice['origin']!r} is set, so the label "
            f"'Order Number:' does not appear anywhere in the header block")
    elif not origin:
        verdicts["d"] = (
            "not proven",
            "this invoice carries no invoice_origin, so the header's origin "
            "block does not render at all and its label cannot be read")
    elif "Order Number:" in _text(origin) and not stock_label:
        verdicts["d"] = ("pass",
                         f"the origin block reads {_text(origin)!r}")
    else:
        verdicts["d"] = (
            "FAIL",
            f"the origin block reads {_text(origin)!r}; the stock "
            f"<strong>Source</strong> label is "
            f"{'still present' if stock_label else 'absent'}")

    # ---- (e) four header blocks removed -----------------------------------
    survivors = [name for name in HEADER_BLOCKS_REMOVED
                 if _open_tag(page, "div", name)]
    if survivors:
        verdicts["e"] = ("FAIL",
                         f"header block(s) still rendered: {survivors}")
    else:
        verdicts["e"] = ("pass",
                         f"none of {list(HEADER_BLOCKS_REMOVED)} is rendered")

    # ---- (f) the invoice number is not in the title -----------------------
    # Scoped to the heading elements on purpose: the move name legitimately
    # appears elsewhere (a reconciliation reference, the PDF filename), and
    # a whole-page search would report a correct template as broken.
    name = invoice["name"]
    guilty = [_text(h) for h in _headings(page) if name and name in h]
    if not name:
        verdicts["f"] = ("not proven",
                         "the invoice has no number to look for")
    elif guilty:
        verdicts["f"] = (
            "FAIL",
            f"the document title reads {guilty[0]!r} — it still carries the "
            f"invoice number {name!r}")
    else:
        titles = [_text(h) for h in _headings(page)][:3]
        verdicts["f"] = ("pass",
                         f"heading(s) {titles} carry no invoice number")

    # ---- (g) 'Payment Type:' under each payment ---------------------------
    expected = invoice["payment_type_lines"]
    if not expected:
        verdicts["g"] = (
            "not proven",
            "this invoice has no reconciled payment, so the payments block "
            "does not render and the line cannot be looked for")
    else:
        missing = [line for line in expected if line not in page_text]
        if missing:
            verdicts["g"] = (
                "FAIL",
                f"missing payment line(s) {missing}; the page's payment area "
                f"reads {_payment_area_text(page)!r}")
        else:
            verdicts["g"] = ("pass", f"found {expected}")

    # ---- (h) the signature line -------------------------------------------
    # Presence only, never position: v19 added #payment_link_qrcode and the
    # terms-and-conditions block after #qrcode (addons/account/views/
    # report_invoice.xml:496, 526), so the signature line is no longer the
    # last thing on the page even when the override landed correctly.
    if "Merchandise Received By:" in page_text:
        verdicts["h"] = ("pass", "the signature line is on the page")
    else:
        verdicts["h"] = ("FAIL", "'Merchandise Received By:' is absent")

    # ---- (i) no Payment Communication paragraph ---------------------------
    if not invoice["payment_reference"]:
        verdicts["i"] = (
            "not proven",
            "payment_reference is empty on this invoice, so the stock "
            "paragraph would not have rendered anyway "
            "(addons/account/views/report_invoice.xml:470)")
    elif "Payment Communication" in page_text:
        verdicts["i"] = (
            "FAIL",
            f"the paragraph is still rendered although payment_reference="
            f"{invoice['payment_reference']!r}")
    else:
        verdicts["i"] = (
            "pass",
            f"absent, and payment_reference={invoice['payment_reference']!r} "
            f"so the stock template WOULD have printed it")
    return verdicts


def _payment_area_text(page: str) -> str:
    """The text of the totals table, for a failure message about item (g)."""
    table = _element(page, r'<table\b[^>]*\bo_total_table[^>]*>', "table")
    return _text(table)[:300]


def _payment_type_lines(ctx, move_id: int, payment_ids: list) -> list:
    """The exact strings item (g) must show, one per reconciled payment.

    Preferred source is ``account.move.invoice_payments_widget``, which is
    the very dict the template iterates
    (``addons/account/views/report_invoice.xml:381``). It is a Binary field
    behind ``account.group_account_invoice`` / ``group_account_readonly``
    (``addons/account/models/account_move.py:507-511``), so it may not be
    readable; the fallback reads the payment's journal and payment method
    line directly.

    ``name`` is read explicitly on both, NEVER ``display_name``: an
    ``account.payment.method.line``'s display name is
    ``"<name> (<journal>)"`` (``addons/account/models/
    account_payment_method.py:134-138``) and a journal's display name gains
    a currency suffix (``addons/account/models/account_journal.py:1063-1068``)
    — either would build an expected string the template never prints.
    """
    rpc = ctx.adapter.rpc
    try:
        widget = rpc.read("account.move", [move_id],
                          ["invoice_payments_widget"])[0].get(
                              "invoice_payments_widget")
    except OdooRPCError as exc:
        ctx.log(f"invoice_payments_widget is not readable ({exc}) — falling "
                f"back to reading the payment records directly")
        widget = None
    lines = []
    if isinstance(widget, dict):
        for entry in widget.get("content") or []:
            if entry.get("is_exchange"):
                continue
            journal = entry.get("journal_name") or ""
            method = entry.get("payment_method_name") or ""
            lines.append(f"Payment Type: {journal} ({method})")
        if lines:
            ctx.log(f"expected 'Payment Type:' line(s) from "
                    f"invoice_payments_widget: {lines}")
            return lines
    for payment_id in payment_ids:
        try:
            row = rpc.read("account.payment", [payment_id],
                           ["journal_id", "payment_method_line_id"])[0]
            journal = rpc.read("account.journal",
                               [m2o_id(row.get("journal_id"))],
                               ["name"])[0].get("name") or ""
            method_id = m2o_id(row.get("payment_method_line_id"))
            method = ""
            if method_id:
                method = rpc.read("account.payment.method.line", [method_id],
                                  ["name"])[0].get("name") or ""
        except (OdooRPCError, IndexError, KeyError) as exc:
            ctx.log(f"could not read payment #{payment_id} ({exc})")
            continue
        lines.append(f"Payment Type: {journal} ({method})")
    ctx.log(f"expected 'Payment Type:' line(s) from the payment records: "
            f"{lines}")
    return lines


def _describe_invoice(ctx, move_id: int, label: str,
                      payment_ids: list) -> dict:
    """Everything the nine letters need to know about one fixture invoice."""
    rpc = ctx.adapter.rpc
    row = rpc.read("account.move", [move_id],
                   ["name", "state", "partner_id", "partner_shipping_id",
                    "invoice_origin", "payment_reference", "amount_total",
                    "amount_residual", "payment_state",
                    "invoice_line_ids"])[0]
    partner_id = m2o_id(row.get("partner_id"))
    shipping_id = m2o_id(row.get("partner_shipping_id"))
    lines = rpc.read("account.move.line", row.get("invoice_line_ids") or [],
                     ["product_id", "discount", "display_type"])
    product_names = []
    discounts = []
    for line in lines:
        if line.get("display_type") not in (False, "product"):
            continue
        discounts.append(money(line.get("discount")))
        name = m2o_name(line.get("product_id"))
        if name and name not in product_names:
            product_names.append(name)
    # Which of the three v19 address branches this invoice will take
    # (addons/account/views/report_invoice.xml:9, 31, 44).
    if not shipping_id:
        branch = "no_shipping (:46)"
    elif shipping_id != partner_id:
        branch = "address_not_same_as_shipping (:18) — the ONLY patched one"
    else:
        branch = "address_same_as_shipping (:32)"
    return {
        "label": label,
        "id": move_id,
        "name": row.get("name") or "",
        "state": row.get("state") or "",
        "partner_name": m2o_name(row.get("partner_id")),
        "shipping_name": m2o_name(row.get("partner_shipping_id")),
        "address_branch": branch,
        "origin": row.get("invoice_origin") or "",
        "payment_reference": row.get("payment_reference") or "",
        "amount_total": money(row.get("amount_total")),
        "amount_residual": money(row.get("amount_residual")),
        "payment_state": row.get("payment_state") or "",
        "product_names": product_names,
        "discounts": discounts,
        "payment_type_lines": _payment_type_lines(ctx, move_id, payment_ids),
    }


@test_case(
    id="TEST-FG07-INV-001",
    name="The customer invoice PDF still looks like a Medicine Man Gallery "
         "invoice",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module="mmg_account",
    priority="P1",
    kind="HYBRID",
    order=703,
    description="Renders the real Invoice PDF report for a posted, paid FG07 "
                "invoice and works down the workbook's nine-item checklist "
                "letter by letter — Invoice Address, the Product column, no "
                "Disc.%, Order Number, the four removed header blocks, no "
                "invoice number in the title, Payment Type, the Merchandise "
                "Received By signature line and no Payment Communication — "
                "then names which of the fifteen inherited xpaths did not "
                "land.",
    traceability=trace("TC-INV-001"))
def test_inv_001(ctx):
    rpc = ctx.adapter.rpc
    # Payments first: cleanup() walks the dict in insertion order and a
    # payment must go before the invoice it is matched to.
    created = {"account.payment": [], "account.move": [], "res.partner": []}
    checklist_rows: list[tuple] = []      # -> TC-INV-001-checklist.csv
    xpath_rows: list[tuple] = []          # -> TC-INV-001-template-xpaths.csv
    artifacts: list[tuple] = []           # (filename, payload, artifact kind)
    residual: list[str] = []
    # Declared before the try so the finally can look for the PDF whatever
    # happened, without reaching into locals().
    move_a = 0
    move_b = 0
    payment_ids: list[int] = []

    with ctx.step("Preconditions (workbook): Odoo 19 with the MMG invoice "
                  "template modules installed, and a printable report"):
        require_v19(ctx)
        company = acting_company(ctx)
        ctx.log(f"acting company #{company['id']} {company['name']!r} — "
                f"currency {company['currency_name']}")
        # P1. ir.module.module, never model_exists: the report TEMPLATE would
        # resolve from a stale ir.ui.view row even after the module was
        # uninstalled, and the verdict has to name a module the client can
        # install.
        for module in TEMPLATE_MODULES:
            require_module(ctx, module, NO_MMG_INVOICE_TEMPLATE)

        # P2. The Studio field the override dereferences. This is a BLOCK and
        # not a failure of item (a)..(i), because without it the report does
        # not render badly — it raises, and every letter would be reported as
        # missing for one single upstream cause.
        legal_field = rpc.search_read(
            "ir.model.fields",
            [("model", "=", "account.move"), ("name", "=", LEGAL_DATE_FIELD)],
            ["name", "ttype", "state"], limit=1)
        if not legal_field:
            ctx.blocked(
                f"account.move has no {LEGAL_DATE_FIELD!r} field on this "
                f"database. mmg_change_invoice_template/views/"
                f"report_invoice.xml:45 renders "
                f"<div t-if=\"o.{LEGAL_DATE_FIELD}\">, and QWeb raises on an "
                f"unknown attribute — so the Invoice PDF report will return "
                f"500 for EVERY invoice, not merely print the wrong layout. "
                f"That is the cause to report: the Legal Sale Date field was "
                f"never a module field in the MMG repository, it existed only "
                f"as a database-level x_ field, so nothing in the code carries "
                f"it across an upgrade. Re-create it (Studio, or a data "
                f"script) and re-run this case")
        ctx.log(f"{LEGAL_DATE_FIELD}: present as "
                f"{legal_field[0].get('ttype')!r} "
                f"(ir.model.fields.state={legal_field[0].get('state')!r})")

        # P4. The ir.actions.report the Print button runs.
        report_rows = rpc.search_read(
            "ir.actions.report", [("report_name", "=", INVOICE_REPORT)],
            ["name", "report_type", "model"], limit=1)
        if not report_rows:
            ctx.blocked(
                f"No ir.actions.report with report_name "
                f"{INVOICE_REPORT!r} exists on this database, so the header "
                f"Print button has nothing to run. In stock Odoo 19 this is "
                f"the 'Invoice PDF' action "
                f"(addons/account/views/account_report.xml:5-18); its absence "
                f"means the account module's report data did not load")
        ctx.log(f"print action: {report_rows[0].get('name')!r} "
                f"({report_rows[0].get('report_type')} on "
                f"{report_rows[0].get('model')})")
        sweep_fg07(ctx)

    try:
        with ctx.step("Diagnostic (not in the workbook): all FIFTEEN "
                      "inherited xpaths are in the DEPLOYED view arch"):
            # Read the arch Odoo is actually running, not the arch on disk.
            # A view whose data file failed to load, or was disabled by
            # Studio, leaves the module 'installed' and the layout stock.
            data_rows = rpc.search_read(
                "ir.model.data",
                [("module", "in", list(TEMPLATE_MODULES)),
                 ("model", "=", "ir.ui.view")],
                ["module", "name", "res_id"], order="module,name")
            arch_by_module = {module: [] for module in TEMPLATE_MODULES}
            for data_row in data_rows:
                try:
                    view = rpc.read("ir.ui.view", [data_row["res_id"]],
                                    ["name", "key", "inherit_id", "arch",
                                     "active"])[0]
                except (OdooRPCError, IndexError) as exc:
                    ctx.log(f"ir.ui.view #{data_row['res_id']} "
                            f"({data_row['module']}.{data_row['name']}) is "
                            f"not readable ({exc})")
                    continue
                ctx.log(f"view {data_row['module']}.{data_row['name']} "
                        f"#{data_row['res_id']} {view.get('name')!r} — "
                        f"inherits {m2o_name(view.get('inherit_id')) or '(none)'}"
                        f", active={bool(view.get('active'))}")
                if not view.get("active"):
                    finding(ctx, f"view "
                                 f"{data_row['module']}.{data_row['name']} is "
                                 f"ARCHIVED, so none of its changes are "
                                 f"applied to the printed invoice even though "
                                 f"the module reports as installed")
                arch_by_module[data_row["module"]].append(
                    view.get("arch") or "")
            missing_xpaths = []
            for module, expr, position, implements in TEMPLATE_XPATHS:
                arch = "\n".join(arch_by_module.get(module) or [])
                # Match on the full attribute so that //div[@name='origin']
                # is not satisfied by //div[@name='origin']/strong[1].
                present = f'expr="{expr}"' in arch
                xpath_rows.append((module, expr, position, implements,
                                   "present" if present else "MISSING"))
                if not present:
                    missing_xpaths.append(
                        f"{module}: xpath expr={expr} position={position} "
                        f"({implements})")
                ctx.log(f"  [{'ok ' if present else 'MISSING'}] {module} "
                        f"{expr} ({position}) — {implements}")

        with ctx.step("Test Data (workbook): a posted invoice with three or "
                      "more lines, a Source Document and a registered "
                      "payment — built twice, once per v19 address branch"):
            partner_id = make_partner(ctx, "Invoice Layout Customer",
                                      company=company)
            created["res.partner"].append(partner_id)
            ship_id = make_partner(ctx, "Invoice Layout Delivery Address",
                                   company=company)
            created["res.partner"].append(ship_id)
            products = [
                (make_product(ctx, "Layout Canvas", 1000.00), 1, 1000.00),
                (make_product(ctx, "Layout Bronze", 2000.00), 2, 2000.00),
                (make_product(ctx, "Layout Pottery", 1500.00), 1, 1500.00),
            ]

            # Invoice A — the ordinary gallery invoice. partner_shipping_id is
            # left to the compute, which returns the customer itself for a
            # contact with no delivery child (addons/account/models/
            # account_move.py:1026-1031).
            move_a = make_invoice(ctx, partner_id, products, company=company,
                                  origin=f"{MARK}-SO-0001",
                                  payment_reference=f"{MARK}/2026/0001")
            created["account.move"].append(move_a)

            # Invoice B — same shape, but the delivery address differs, and
            # one line carries a discount so that item (c) is not vacuous.
            move_b = make_invoice(ctx, partner_id, products, company=company,
                                  origin=f"{MARK}-SO-0002",
                                  payment_reference=f"{MARK}/2026/0002",
                                  extra={"partner_shipping_id": ship_id})
            created["account.move"].append(move_b)
            b_lines = rpc.read("account.move", [move_b],
                               ["invoice_line_ids"])[0]["invoice_line_ids"]
            if b_lines:
                try:
                    rpc.call("account.move", "write", [move_b],
                             {"invoice_line_ids": [(1, b_lines[0],
                                                    {"discount": 10.0})]},
                             context=company_ctx(company))
                    ctx.log(f"invoice B line #{b_lines[0]} carries a 10% "
                            f"discount — without it display_discount would be "
                            f"False on its own (addons/account/views/"
                            f"report_invoice.xml:167) and item (c) would pass "
                            f"whether or not the MMG override landed")
                except OdooRPCError as exc:
                    ctx.log(f"could not put a discount on invoice B ({exc}) — "
                            f"item (c) will be reported, but see the residual "
                            f"note about it being vacuous")

            post_errors = []
            for move_id in (move_a, move_b):
                try:
                    rpc.call("account.move", "action_post", [move_id])
                    created["account.move"].remove(move_id)  # never unlink it
                except OdooRPCError as exc:
                    # Wrapped rather than allowed to escape: an invoice that
                    # will not post is a product finding, and an escaped
                    # OdooRPCError would be filed as a broken test instead.
                    post_errors.append(f"invoice #{move_id}: {exc}")
            ctx.check("Both fixture invoices post (the workbook's "
                      "precondition is 'a POSTED customer invoice')",
                      [], post_errors)
            ctx.log(f"posted invoices A=#{move_a} B=#{move_b}")

        with ctx.step("Precondition (workbook): 'at least one registered "
                      "payment' — pay invoice A in full through the Pay "
                      "pop-up"):
            payment_error = ""
            try:
                wizard_id = register_payment(ctx, [move_a], company=company)
                payment_ids = confirm_payment_register(ctx, wizard_id,
                                                       [move_a],
                                                       company=company)
                created["account.payment"].extend(payment_ids)
            except OdooRPCError as exc:
                # Never let this escape: a payment that cannot be registered
                # is a finding about the payment flow, and it must not be
                # recorded as a broken layout test. The assertion about it is
                # made at the very END of the case, so that a payment problem
                # cannot stop the nine workbook letters from being read.
                payment_error = str(exc)
                ctx.log(f"could not register a payment on invoice A ({exc})")
            if not payment_ids:
                why = payment_error or ("the Pay pop-up returned no payment "
                                        "id")
                residual.append(
                    f"NO payment could be registered on the fixture invoice "
                    f"({why}). Workbook item (g) — the 'Payment Type:' line — "
                    f"could therefore not be exercised at all. Register a "
                    f"payment on a real posted invoice by hand, print it, and "
                    f"check item (g) on that PDF before signing this case "
                    f"off.")
            else:
                ctx.log(f"registered payment(s) {payment_ids} against invoice "
                        f"A")

        with ctx.step("Steps 1-3 (workbook): open each posted invoice, press "
                      "Print, and fetch the document the button produces"):
            invoices = []
            pages = {}
            statuses = {}
            for label, move_id, paid in (("A (delivery address = invoice "
                                          "address)", move_a, payment_ids),
                                         ("B (delivery address differs)",
                                          move_b, [])):
                invoice = _describe_invoice(ctx, move_id, label, paid)
                invoices.append(invoice)
                ctx.log(f"invoice {label}: {invoice['name']!r} "
                        f"state={invoice['state']!r} "
                        f"total={invoice['amount_total']:.2f} "
                        f"residual={invoice['amount_residual']:.2f} "
                        f"payment_state={invoice['payment_state']!r} "
                        f"origin={invoice['origin']!r} "
                        f"payment_reference={invoice['payment_reference']!r}")
                ctx.log(f"  address branch -> {invoice['address_branch']}")
                try:
                    status, page = report_html(ctx, INVOICE_REPORT, move_id)
                except Exception as exc:                 # noqa: BLE001
                    # report_html already turns HTTP and socket errors into a
                    # status code; this catches the one remaining escape —
                    # http_session raising when the web login is refused —
                    # so a session problem is reported as a render failure
                    # rather than as AUTOMATION_ERROR.
                    status, page = 0, ""
                    ctx.log(f"could not fetch the report for invoice "
                            f"#{move_id}: {type(exc).__name__}: {exc}")
                statuses[move_id] = status
                pages[move_id] = page
                artifacts.append((f"TC-INV-001-invoice-"
                                  f"{'A' if move_id == move_a else 'B'}.html",
                                  page, "log"))
                ctx.log(f"  GET /report/html/{INVOICE_REPORT}/{move_id}"
                        f"?report_type=pdf -> HTTP {status}, "
                        f"{len(page)} character(s)")
                # P5. A 200 with no line table means some localisation
                # redirected _get_name_invoice_report to its own template
                # (addons/account/views/report_invoice.xml:672-674), in which
                # case none of the MMG xpaths apply and every letter would
                # read as failed for one unrelated reason.
                if status == 200 and 'name="invoice_line_table"' not in page:
                    ctx.blocked(
                        "The report rendered (HTTP 200) but contains no "
                        "element named 'invoice_line_table', which "
                        "account.report_invoice_document always emits "
                        "(addons/account/views/report_invoice.xml:173). The "
                        "printed document is therefore NOT "
                        "account.report_invoice_document: a localisation has "
                        "redirected account.move._get_name_invoice_report to "
                        "its own template (:672-674), and neither MMG "
                        "override applies to it. Find the localisation module "
                        "that overrides _get_name_invoice_report and decide "
                        "whether the gallery's layout has to be ported onto "
                        "its template before any of items (a)-(i) can mean "
                        "anything")

        with ctx.step("Step 4 (workbook): work down the checklist (a) to (i) "
                      "on the printed page, item by item"):
            # Everything is evaluated and recorded BEFORE any assertion, so
            # the CSV and the log name every failing letter even though the
            # first failing check ends the run — the workbook's If It Fails
            # asks for exactly that list of letters.
            failures = []
            unproven = []
            for invoice in invoices:
                page = pages[invoice["id"]]
                if statuses[invoice["id"]] != 200 or not page:
                    ctx.log(f"invoice {invoice['label']}: not rendered "
                            f"(HTTP {statuses[invoice['id']]}) — its nine "
                            f"letters cannot be read")
                    for letter in sorted(LETTER_TEXT):
                        checklist_rows.append(
                            (invoice["label"], invoice["name"], letter,
                             LETTER_TEXT[letter], "not proven",
                             f"the report did not render (HTTP "
                             f"{statuses[invoice['id']]})"))
                    # Counted against Expected Result line 1 as well, not only
                    # against the render check further down: "every one of the
                    # nine items is as described" cannot be TRUE of a page that
                    # never rendered, and leaving `failures` empty here would
                    # let the workbook's headline assertion pass vacuously on a
                    # 500.
                    failures.append(
                        f"invoice {invoice['label']} ({invoice['name']}): the "
                        f"printed document did not render (HTTP "
                        f"{statuses[invoice['id']]}), so NOT ONE of the nine "
                        f"items (a) to (i) could be shown to be as described")
                    continue
                verdicts = _evaluate_letters(ctx, page, invoice)
                for letter in sorted(verdicts):
                    verdict, evidence = verdicts[letter]
                    checklist_rows.append((invoice["label"], invoice["name"],
                                           letter, LETTER_TEXT[letter],
                                           verdict, evidence))
                    ctx.log(f"  invoice {invoice['label']} item ({letter}) "
                            f"{verdict.upper()} — {LETTER_TEXT[letter]}: "
                            f"{evidence}")
                    if verdict == "FAIL":
                        failures.append(
                            f"({letter}) on invoice {invoice['label']}: "
                            f"{LETTER_TEXT[letter]} — {evidence}")
                    elif verdict == "not proven":
                        unproven.append(
                            f"({letter}) on invoice {invoice['label']}: "
                            f"{evidence}")

                # R11 — v19 header blocks the v15 override never removed
                # because they did not exist. The workbook's item (e) names
                # four blocks and only four; these are recorded and asserted
                # in neither direction.
                for block in HEADER_BLOCKS_NEW_IN_V19:
                    if _open_tag(page, "div", block):
                        observation(
                            ctx,
                            f"invoice {invoice['label']} prints the v19 "
                            f"header block name={block!r}, which did not "
                            f"exist when mmg_change_invoice_template was "
                            f"written (addons/account/views/"
                            f"report_invoice.xml:138/142/158). The workbook's "
                            f"item (e) lists Invoice Date, Due Date, Customer "
                            f"Code and Reference and no others, so this is "
                            f"NOT a failure of item (e) — but it IS new text "
                            f"on a customer-facing document, and belongs in "
                            f"the Expected line 3 comparison against the old "
                            f"printout")

            for note in unproven:
                residual.append(
                    f"CHECKLIST ITEM NOT PROVEN — {note}. It is reported as "
                    f"neither a pass nor a failure: read this letter off the "
                    f"attached PDF by hand before signing the case off.")

            # Item (c) only means something on an invoice that WOULD have
            # shown a discount column. Say so out loud when the fixture ended
            # up without one, rather than letting a vacuous pass look like a
            # verified layout.
            if not any(any(inv["discounts"]) for inv in invoices):
                residual.append(
                    "Item (c), 'There is NO Disc.% column', passed VACUOUSLY: "
                    "no line on either fixture invoice carries a discount, "
                    "and display_discount is any(l.discount for l in "
                    "lines_to_report) (addons/account/views/"
                    "report_invoice.xml:167), so stock Odoo 19 would not have "
                    "printed the column either. Print one real invoice that "
                    "HAS a discount and confirm the column is still absent.")

            # Expected Result line 1, in the workbook's own words. The list
            # form is deliberate: nine independent things can be wrong and the
            # workbook's If It Fails asks which letters failed, so a failure
            # here names every one of them rather than only the first.
            ctx.check("Expected Result line 1: every one of the nine "
                      "checklist items (a) to (i) on the printed customer "
                      "invoice is as described",
                      [], failures)

        with ctx.step("Diagnosis behind Expected line 1: every inherited "
                      "xpath of both MMG modules is in the deployed arch"):
            # Asserted after the letters, because a missing xpath is the
            # CAUSE and the letters are the workbook's stated effect. Both
            # verdicts are already in the log and in the CSVs, so whichever
            # assertion fires first, the tester has the whole picture.
            ctx.check("All fifteen inherited xpaths of "
                      "mmg_change_invoice_template (11) and mmg_account (4) "
                      "are present in the view arch Odoo 19 is running",
                      [], missing_xpaths)

        with ctx.step("Expected Result line 2: the page renders with no "
                      "blank boxes and no missing totals"):
            render_failures = [
                f"invoice {inv['label']} ({inv['name']}) -> HTTP "
                f"{statuses[inv['id']]}"
                for inv in invoices if statuses[inv["id"]] != 200]
            ctx.check("The Invoice PDF report renders for every posted "
                      f"invoice (GET /report/html/{INVOICE_REPORT}/<id>"
                      "?report_type=pdf returns 200)",
                      [], render_failures)

            blank_cells = []
            missing_totals = []
            for invoice in invoices:
                page = pages[invoice["id"]]
                table = _element(
                    page, r'<table\b[^>]*\bname="invoice_line_table"[^>]*>',
                    "table")
                for index, row in enumerate(_rows(table), start=1):
                    if 'name="account_invoice_line_product"' not in row:
                        continue          # a section, a note or the header
                    for cell_name in ("account_invoice_line_product",
                                      "td_subtotal"):
                        cell = [c for c in _cells(row, "td")
                                if f'name="{cell_name}"' in c]
                        if not cell:
                            blank_cells.append(
                                f"invoice {invoice['label']} line {index}: no "
                                f"{cell_name} cell at all")
                        elif not _text(cell[0]):
                            blank_cells.append(
                                f"invoice {invoice['label']} line {index}: the "
                                f"{cell_name} cell is blank")
                # The grand total, read from the totals table's o_total row
                # (addons/account/views/report_invoice.xml:589-596) rather
                # than by string-matching a formatted amount, whose thousands
                # separator and currency position are locale-dependent.
                totals = [r for r in _rows(page) if 'class="o_total"' in r]
                figures = [_text(_cells(r, "td")[-1]) for r in totals
                           if _cells(r, "td")]
                if not totals:
                    missing_totals.append(
                        f"invoice {invoice['label']} ({invoice['name']}): the "
                        f"page has no o_total row at all")
                elif not any(figures):
                    missing_totals.append(
                        f"invoice {invoice['label']} ({invoice['name']}): the "
                        f"Total row is present but its amount cell is empty")
                else:
                    ctx.log(f"invoice {invoice['label']} Total row(s) show "
                            f"{figures} (account.move.amount_total = "
                            f"{invoice['amount_total']:.2f})")
            ctx.check("No product line prints a blank Product or Amount box",
                      [], blank_cells)
            ctx.check("Every printed invoice carries its Total", [],
                      missing_totals)

        with ctx.step("Beyond the workbook: the Unit Price header is still "
                      "right-aligned under Bootstrap 5"):
            # mmg_account/report/report_invoice.xml:23-27 rewrites
            # th_priceunit's class to the Bootstrap 4 'text-right'. Odoo 19
            # ships Bootstrap 5, where that class DOES NOT EXIST — the stock
            # header uses 'text-end' (addons/account/views/
            # report_invoice.xml:178). Nothing errors; the Unit Price heading
            # simply stops being right-aligned over its right-aligned column,
            # which is exactly the kind of "it looked fine" difference the
            # workbook warns about. Asserted last so it can never mask one of
            # the nine workbook letters.
            misaligned = []
            for invoice in invoices:
                header = _open_tag(pages[invoice["id"]], "th", "th_priceunit")
                if not header:
                    misaligned.append(
                        f"invoice {invoice['label']}: there is no "
                        f"th_priceunit header at all")
                elif "text-end" not in header:
                    misaligned.append(
                        f"invoice {invoice['label']}: {header} — Bootstrap 5 "
                        f"has no 'text-right' class, so the Unit Price "
                        f"heading is no longer right-aligned")
                else:
                    ctx.log(f"invoice {invoice['label']} th_priceunit: "
                            f"{header}")
            ctx.check("The Unit Price column header carries the Bootstrap 5 "
                      "'text-end' class that Odoo 19 uses to right-align it "
                      "(mmg_account replaced it with Bootstrap 4's "
                      "'text-right', which Odoo 19 does not define)",
                      [], misaligned)

        with ctx.step("Precondition audit, deliberately last: the fixture "
                      "really did carry 'at least one registered payment'"):
            # Asserted here and nowhere earlier ON PURPOSE. A payment that
            # cannot be registered would otherwise end the case before a
            # single one of the nine workbook letters had been read, and the
            # workbook's If It Fails asks for the letters.
            ctx.check_true(
                "A payment was registered against the fixture invoice, so "
                "the printed page really contained a payments block and "
                "workbook item (g) was exercised rather than skipped",
                bool(payment_ids),
                actual_desc=(f"account.payment id(s) created: {payment_ids}"
                             if payment_ids
                             else f"the Pay pop-up produced no payment "
                                  f"({payment_error or 'no id returned'}) — "
                                  f"item (g) is recorded as NOT PROVEN above, "
                                  f"never as a pass"))
    finally:
        with ctx.step("Evidence: the PDF the workbook asks to attach, the "
                      "rendered pages, and the two verdict tables"):
            # Nothing in this block may raise (F3/R4): an exception here would
            # replace whatever FAILED or BLOCKED verdict the case reached.
            try:
                # Only worth asking when there is an invoice to print: on a
                # BLOCKED precondition there is nothing to capture and this
                # would be one more pointless call against the target.
                state = wkhtmltopdf_state(ctx) if move_a else ""
                ctx.log(f"ir.actions.report.get_wkhtmltopdf_state() -> "
                        f"{state!r}")
                if state == "ok":
                    status, payload = report_pdf(ctx, INVOICE_REPORT, move_a)
                    ctx.log(f"GET /report/pdf/{INVOICE_REPORT}/{move_a} -> "
                            f"HTTP {status}, {len(payload)} byte(s)")
                    if payload[:4] == b"%PDF":
                        artifacts.append((PDF_NAME, payload, "pdf"))
                    else:
                        ctx.log("the PDF route did not return a PDF — the "
                                "HTML rendering above is the evidence "
                                "instead")
                        residual.append(
                            f"The PDF itself could not be captured (HTTP "
                            f"{status}). The workbook's If It Fails says to "
                            f"ATTACH THE ACTUAL PDF, so print the invoice "
                            f"from the browser and attach that file to the "
                            f"sign-off.")
                elif state:
                    residual.append(
                        f"wkhtmltopdf reports state {state!r} on this server, "
                        f"so no PDF could be produced here and only the HTML "
                        f"rendering was checked. Print one invoice from a "
                        f"browser and attach that PDF — the workbook's State "
                        f"After The Test says to keep it for the sign-off.")
            except Exception as exc:                     # noqa: BLE001
                ctx.log(f"could not capture the PDF ({exc}) — the HTML "
                        f"evidence above still stands")

            for name, payload, kind in artifacts:
                try:
                    path = ctx.artifacts_dir / name
                    if isinstance(payload, bytes):
                        path.write_bytes(payload)
                    else:
                        path.write_text(payload or "", encoding="utf-8")
                    ctx.add_artifact(path, kind, name)
                    ctx.log(f"wrote {name}")
                except Exception as exc:                 # noqa: BLE001
                    ctx.log(f"could not write {name} ({exc})")

            for name, header, rows in (
                    (CHECKLIST_CSV,
                     ["invoice", "invoice_number", "item", "workbook_wording",
                      "verdict", "evidence"], checklist_rows),
                    (XPATH_CSV,
                     ["module", "xpath_expr", "position", "implements",
                      "in_deployed_arch"], xpath_rows)):
                try:
                    path = ctx.artifacts_dir / name
                    with path.open("w", newline="", encoding="utf-8") as fh:
                        writer = csv.writer(fh)
                        writer.writerow(header)
                        writer.writerows(rows)
                    ctx.add_artifact(path, "log", name)
                    ctx.log(f"wrote {len(rows)} row(s) to {name}")
                except OSError as exc:
                    ctx.log(f"could not write {name} ({exc}) — the verdicts "
                            f"above are still in this log")

            # Expected Result line 3 — the only line the platform cannot
            # settle. Never dropped, never invented.
            residual.append(
                "Expected Result line 3, 'Nothing else has visibly changed "
                "against the old printout': hold the Novobi printout of an "
                "old invoice next to " + PDF_NAME + " and compare the whole "
                "page — company header and logo, the footer, the terms and "
                "conditions block, fonts and column widths. The platform does "
                "not hold that printout and must not invent one, so this is "
                "the one comparison a human has to make. Two v19 additions "
                "to look for specifically: the payment-link QR block "
                "(#payment_link_qrcode, addons/account/views/"
                "report_invoice.xml:496) and 'Total amount in words' "
                "(:408-412), neither of which existed in v15.")
            residual.append(
                "Expected Result line 2, the 'no overlapping text' half: "
                "overlapping text is a property of the wkhtmltopdf raster, "
                "not of the HTML this case reads, so it cannot be asserted. "
                "Open " + PDF_NAME + " and look at the header block and the "
                "line table for text running into a neighbouring box — the "
                "extra Product column narrows every other column, which is "
                "where overlap shows up first.")
            for note in residual:
                residual_manual_step(ctx, note)

        with ctx.step("Cleanup: remove the FG07 fixtures"):
            ctx.log("the two posted invoices and any posted payment are left "
                    "in place BY DESIGN — deleting a posted entry destroys "
                    "accounting evidence, and the workbook's State After The "
                    "Test for this case is 'Nothing changed'")
            cleanup(ctx, created)
