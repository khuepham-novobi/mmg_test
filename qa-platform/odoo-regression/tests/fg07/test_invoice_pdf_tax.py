"""FG-07 — TC-INV-003: the invoice PDF shows tax broken down by authority.

Implements row 34.0 (P1, "Invoice document") of the CLIENT MANUAL TESTING
GUIDELINE ``MMG_v19_Client_Manual_Testing_Guideline_FG05-FG14_v1.0.xlsx`` /
sheet ``Testing Guideline``.

The workbook's framing: *"Customers query tax, and institutional buyers need
to see which authority is charging what. The PDF has to carry that breakdown,
not one lumped tax figure."*

Read-only by construction
-------------------------
The workbook's *State After The Test* is "Nothing changed". This module
creates no record, writes no field, and calls neither ``sweep_fg07`` nor
``cleanup`` — a sweep is itself a delete. It is also the one FG-07 case that
touches an **AvaTax-flagged** ``account.move``, where deleting would be worse
than untidy: ``account.move.unlink()`` on an AvaTax document asks Avalara to
void the filed transaction
(``enterprise-19.0/account_avatax/models/account_move.py`` — the
``account.external.tax.mixin`` void hook). Nothing here unlinks anything.

Where the breakdown actually lives in Odoo 19 — read this before triaging
-------------------------------------------------------------------------
``account_avatax`` **removes the per-line Taxes column from the printed
invoice** for AvaTax documents. Its
``reports/account_invoice.xml`` inherits ``account.report_invoice_document``
and adds ``not o.is_avatax`` to the ``t-if`` of exactly two nodes: the header
cell ``<th name="th_taxes">`` and the body cell that wraps
``<span id="line_tax_ids">``. So the authority breakdown the workbook is
hunting for is in the **totals block**, never on the lines. A tester who
reports "no tax column on the lines" has reported the template working as
designed.

The 5 Expected Result lines, and what each is read from
-------------------------------------------------------
1. **"The totals block lists the tax by authority, matching what TC-TAX-002
   found in the journal entry."** — read from ``account.move.tax_totals``, a
   ``fields.Binary`` compute (``addons/account/models/account_move.py:599``,
   computed at ``:1835-1842``) whose whole dict comes back from ``read()``.
   Its ``subtotals[i]['tax_groups'][j]`` list is what
   ``account.document_tax_totals_template`` loops over to emit one
   ``<tr class="o_taxes">`` per row
   (``addons/account/views/report_invoice.xml:535-549``). Compared against
   the journal entry itself: ``account.move.line`` rows with
   ``display_type='tax'`` (``addons/account/models/account_move_line.py:333``)
   carrying ``tax_line_id`` (``:208-213``) and the stored
   ``tax_group_id`` (``:214-217``).
   ``_get_tax_totals_summary`` is PRIVATE and is never called over RPC —
   reading the field gives the identical dict.

   **Two counts are taken, and they answer different questions.** One printed
   row is one ``tax_groups[]`` entry, i.e. one ``account.tax.group``, so the
   printed rows are first compared against the distinct
   ``account.move.line.tax_group_id`` the entry recorded: that proves the
   TEMPLATE prints the ledger's own grouping faithfully. The workbook's line
   is then asserted on the workbook's own unit — one printed row per
   AUTHORITY, i.e. per distinct ``account.move.line.tax_line_id``, since the
   workbook names the failure in as many words ("if the PDF shows one
   combined tax row where the journal entry has several, that is the
   defect"). The group-vs-group count alone cannot fail in that scenario —
   ``tax_totals`` is *built* by grouping those same lines by
   ``account.tax.group`` (``account_tax.py:2826-2833``) — so it would report
   the collapse as a pass. Taking both, in that order, means a failure says
   which layer is at fault: template, or the grouping of the taxes.
2. **"The tax names carry their bracketed authority codes."** — read from the
   ``account.tax`` records the printed rows are made of,
   ``tax_groups[j]['involved_tax_ids']``
   (``addons/account/models/account_tax.py:2841-2845, 2882``), by
   ``read()``-ing ``account.tax.name`` — the same records and the field FG-05
   TC-TAX-002 asserts on screen. **Not** from ``group_name``: the row's
   printed LABEL is ``account.tax.group.name``, and nothing in this stack
   ever writes a jurisdiction code there — see the finding below. That the
   printed label carries no authority code is recorded as a FINDING against
   the tax-group configuration, which is the object that would have to
   change.
3. **"The tax rows plus the untaxed amount equal the Total."** — the printed
   Total row is ``tax_totals['total_amount_currency']``
   (``report_invoice.xml:592-594``), which Odoo builds as
   ``base_amount_currency + tax_amount_currency + cash_rounding``
   (``account_tax.py:3004-3005``). The subtotal row above the tax rows prints
   ``subtotal['base_amount_currency']`` (``report_invoice.xml:541``).
4. **"The line table has no per-line tax column, and the table is still
   correctly aligned."** — read from the rendered document itself:
   ``<th name="th_taxes">`` (``report_invoice.xml:182``) and
   ``<span id="line_tax_ids">`` (``:245``) must both be absent on an AvaTax
   invoice, and every visible body row must span exactly as many columns as
   the header has visible cells.
5. **"On screen, a Taxes column on the lines is EXPECTED in Odoo 19 and is
   not a defect."** — read from the ``account.move`` form arch: the invoice
   line list declares ``<field name="tax_ids" … optional="show"/>``
   (``addons/account/views/account_move_views.xml:1217-1225``), i.e. shown by
   default. Logged as an OBSERVATION and asserted in NEITHER direction, as
   the workbook demands.

Why this is a new-capability check, not a did-it-survive check
--------------------------------------------------------------
On v15 the gallery ran the OCA connector, whose
``_get_avalara_tax_name`` returns ``"{rate}%*"`` and whose tax lookup keys on
the RATE alone (``psus-medicine-man-gallery/account_avatax_oca/models/
account_tax.py:26-52``) — one ``account.tax`` per distinct rate, with **no
jurisdiction anywhere in the record**. A per-authority breakdown was simply
not representable. What made the authority visible on v15 was the gallery's
own override, ``mmg_account_avatax_enhancement._map_avatax``, which names each
tax ``'%s [%s] (%s %%)' % (taxName, jurisCode, rate)``
(``psus-medicine-man-gallery/mmg_account_avatax_enhancement/models/
account_avatax.py:31-35``) — that is where the square brackets of Expected
Result line 2 come from, and it names the **tax**, not the tax group.

A finding this case is built to surface
---------------------------------------
Odoo 19's own ``account_avatax`` names the tax group
``tax_detail['taxName'].removesuffix(' TAX')`` and the tax
``f"{group_name} {rate}%"``
(``enterprise-19.0/account_avatax/models/account_external_tax_mixin.py:
166-179``) — **no jurisdiction code, and no brackets, in either**. The v19
port keeps the v15 tax name, and *only* the tax name:
``mmg_account_avatax_enhancement._extract_tax_values_from_avatax_detail``
rewrites ``tax_values['name']`` to ``'%s [%s] %s' % (taxName, jurisCode,
rate)`` and returns ``tax_group_values`` untouched, deliberately —
"Only the name is rewritten here"
(``psus-medicine-man-gallery/mmg_account_avatax_enhancement/models/
account_external_tax_mixin.py:82-97``). So the square brackets live on
``account.tax.name`` **by design on both versions**, and the printed label —
``account.tax.group.name`` — was never going to carry them. That is why
Expected Result line 2 is asserted against the taxes behind the printed rows
rather than against the row labels: the workbook line is about the tax names,
and asserting it on the group name would fail a correctly ported system for a
reason the workbook is not asking about.

Two mechanisms can then leave the printed page without a breakdown, and this
case is built to tell them apart:

* **coarse grouping.** ``_process_external_taxes`` sets ``tax_group_id`` only
  on the taxes it has to CREATE; a tax it matches by name and reuses keeps
  whatever group it already had (``enterprise-19.0/account_external_tax/
  models/account_external_tax_mixin.py:127-156``). Keeping the v15 name is
  exactly what makes v15's migrated taxes match, so every reused jurisdiction
  tax also drags its migrated ``account.tax.group`` along — and v15's
  override created those taxes with **no ``tax_group_id`` at all**
  (``psus-medicine-man-gallery`` commit ``53f7985``,
  ``mmg_account_avatax_enhancement/models/account_avatax.py:42-54``), so they
  all took the database's default group. Several jurisdictions under one
  group print as ONE row, which is the workbook's named defect and shows up
  as the authority-count assertion failing while the group-count assertion
  passes.
* **a template fault**, which would show up as the group-count assertion
  failing — the report not printing a group the ledger recorded.

A second finding, which is exactly what workbook step 8 hunts
-------------------------------------------------------------
``account_avatax``'s report patch covers the ungrouped branch only. The
collapsed-section branch still emits ``<td name="td_taxes_grouped">`` /
``<span id="grouped_line_tax_ids">`` (``report_invoice.xml:350-354``), and
``line_colspan`` for a section row is still computed as if the Taxes header
existed (``:223``). On an AvaTax invoice the header has one cell fewer than
those rows assume, so a document with a section or a collapsed line prints a
row one column too wide — the misalignment step 8 asks about. The cell
arithmetic below measures it instead of trusting it.

Documented adaptation — what a human still has to look at
----------------------------------------------------------
The platform can prove the *structure* of the printed document (how many tax
rows, what they are called, what they add up to, how many columns each row
spans) because it renders the real report through the real controller. It
cannot prove the *appearance* — that the totals block is not visually cramped
and that removing the Taxes column left no blank gutter. Those are
wkhtmltopdf paint properties. The rendered PDF is therefore attached and the
visual confirmation is recorded as a RESIDUAL MANUAL STEP with every captured
figure printed into it, so the human step is a glance, never a re-run. The
workbook's *If It Fails* ("attach the PDF and the journal entry side by side")
is satisfied by the two CSVs plus the PDF artifact.
"""
from __future__ import annotations

import csv
import re

from adapters.base import OdooRPCError
from framework.fg_common import form_arch
from framework.registry import test_case
from tests.fg07.common import (INVOICE_REPORT, MARK, WORKFLOW, WORKFLOW_NAME,
                               acting_company, company_ctx, fields_present,
                               finding, m2o_id, m2o_name, module_state, money,
                               observation, report_html, report_pdf,
                               require_module, require_v19,
                               residual_manual_step, trace, wkhtmltopdf_state)

TOTALS_CSV = "TC-INV-003-totals-block-vs-journal-entry.csv"
TOTALS_HEADER = ["source", "row", "label", "amount", "base_amount",
                 "tax_group_id", "tax_id", "authority_code"]

TABLE_CSV = "TC-INV-003-printed-line-table.csv"
TABLE_HEADER = ["region", "row", "visible_cells", "colspan_total",
                "header_cells", "aligned", "cell_names"]

PDF_ARTIFACT = "TC-INV-003-invoice.pdf"
HTML_ARTIFACT = "TC-INV-003-invoice.html"

# The square-bracketed jurisdiction code the gallery's own AvaTax override
# puts into a tax name — "ARIZONA STATE TAX [AZ] (5.6000 %)". Defined locally
# rather than imported: FG-05 owns its own copy and cross-suite imports are
# forbidden, and the two suites must be able to disagree about it.
AUTHORITY_CODE_RE = re.compile(r"\[([^\[\]]+)\]")

# How many recent posted customer invoices to look through before concluding
# that no multi-authority document exists. Bounded on purpose: this runs
# against a live gallery database.
CANDIDATE_LIMIT = 60

# ---- rendered-document parsing -------------------------------------------
# The report is fetched with report_type=pdf, which matters here: in html mode
# the section rows emit an extra mobile <td colspan="2">, and the column
# arithmetic below would read a correct template as broken. In pdf mode that
# mobile cell is still emitted but carries class="d-none"
# (report_invoice.xml:266), so "visible" is simply "no d-none in the class".
TABLE_RE = re.compile(
    r'<table[^>]*name="invoice_line_table"[^>]*>(.*?)</table>', re.S | re.I)
THEAD_RE = re.compile(r"<thead[^>]*>(.*?)</thead>", re.S | re.I)
TBODY_RE = re.compile(r"<tbody[^>]*>(.*?)</tbody>", re.S | re.I)
ROW_RE = re.compile(r"<tr\b[^>]*>(.*?)</tr>", re.S | re.I)
CELL_RE = re.compile(r"<(th|td)\b([^>]*)>", re.I)
CLASS_RE = re.compile(r'class="([^"]*)"', re.I)
COLSPAN_RE = re.compile(r'colspan="(\d+)"', re.I)
NAME_ATTR_RE = re.compile(r'name="([^"]*)"', re.I)
O_TAXES_RE = re.compile(r'<tr[^>]*\bclass="[^"]*\bo_taxes\b[^"]*"', re.I)
O_TOTAL_RE = re.compile(r'<tr[^>]*\bclass="[^"]*\bo_total\b[^"]*"', re.I)
# A note row deliberately spans the whole table with colspan="99"
# (addons/account/views/report_invoice.xml:273 — the only colspan="99" in the
# template).
FULL_WIDTH_COLSPAN = 99

NO_AVATAX_MODULE = (
    "'account_avatax' (Odoo Enterprise, 'Avatax') is not installed on this "
    "database, so account.move.is_avatax does not exist, no invoice can carry "
    "an Avalara jurisdiction breakdown, and the whole premise of this case — "
    "'the PDF has to carry that breakdown, not one lumped tax figure' — has "
    "nothing to measure. NOTE the gallery ran the OCA connector "
    "(account_avatax_oca) on v15, which is a DIFFERENT module: if that one is "
    "what is installed here, the per-authority breakdown cannot exist at all, "
    "because the OCA connector created one account.tax per RATE named "
    "'{rate}%*' with no jurisdiction anywhere in the record "
    "(psus-medicine-man-gallery/account_avatax_oca/models/account_tax.py:"
    "26-52). Install the Enterprise account_avatax plus the v19 port of "
    "mmg_account_avatax_enhancement and re-run"
)

NO_MULTI_AUTHORITY_INVOICE = (
    "This case's precondition is not met: the workbook requires the posted "
    "multi-authority invoice left behind by FG-05 TC-TAX-002 ('a posted "
    "invoice exists whose tax is split across several authorities'), and no "
    "posted customer invoice on this database carries more than one distinct "
    "tax line. FG-07 must not create one — an AvaTax invoice files a real "
    "transaction with Avalara, and deleting one voids it — so run FG-05 "
    "TC-TAX-002 against the Avalara SANDBOX first (a Phoenix AZ or Tucson AZ "
    "ship-to address produces state + county + city rows), then re-run this "
    "case. If FG-05 TC-TAX-002 has passed and this still blocks, the tax "
    "lines were collapsed on posting, which is itself the defect this case "
    "exists to find — report it against TC-TAX-002"
)


# --------------------------------------------------------------- utilities
def _escaped(text: str) -> str:
    """QWeb escapes with markupsafe, so a printed label may not be literal."""
    return (text.replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;").replace('"', "&#34;")
                .replace("'", "&#39;"))


def _appears(html: str, text: str) -> bool:
    """Is ``text`` printed in ``html``, raw or markupsafe-escaped?"""
    if not text:
        return False
    return text in html or _escaped(text) in html


def _cells(fragment: str) -> list[dict]:
    """Visible ``<th>``/``<td>`` descriptors of one table row.

    ``d-none`` is the marker the template puts on the cells that exist only
    for the html (mobile) rendering; in pdf mode nothing legitimately visible
    carries it, so dropping those cells is what makes the column arithmetic
    match what the reader actually sees on paper.
    """
    found = []
    for tag, attrs in CELL_RE.findall(fragment):
        class_match = CLASS_RE.search(attrs)
        classes = class_match.group(1) if class_match else ""
        if "d-none" in classes.split():
            continue
        span_match = COLSPAN_RE.search(attrs)
        name_match = NAME_ATTR_RE.search(attrs)
        found.append({"tag": tag.lower(),
                      "colspan": int(span_match.group(1)) if span_match else 1,
                      "name": name_match.group(1) if name_match else ""})
    return found


def _tax_names(ctx, tax_ids, context: dict) -> dict:
    """``account.tax.name`` by id — the stored name, not the display string.

    ``account.tax._compute_display_name`` appends a country-code suffix such
    as " (US)" whenever the tax's country differs from the company's fiscal
    country (``addons/account/models/account_tax.py:704-705``), so the
    many2one label a journal item reads back is not the field the gallery's
    override writes. FG-05 TC-TAX-002 reads the stored name for the same
    reason, and the two cases have to be looking at the same string.
    """
    names: dict[int, str] = {}
    ids = sorted({int(tax_id) for tax_id in tax_ids if tax_id})
    if not ids:
        return names
    try:
        for row in ctx.adapter.rpc.call("account.tax", "read", ids,
                                        fields=["name"], context=context):
            names[row["id"]] = row.get("name") or ""
    except OdooRPCError as exc:
        ctx.log(f"account.tax names are unreadable ({exc}) — the many2one "
                f"display strings captured from the journal entry are used "
                f"instead, which carry the same square brackets plus a "
                f"possible country suffix")
    return names


def _pick_multi_authority_invoice(ctx, company: dict, avatax_field: bool
                                  ) -> tuple[dict, list, int]:
    """The posted customer invoice whose tax is split across authorities.

    Two passes, in the order the workbook's precondition implies. Pass 1 asks
    only for AvaTax-flagged documents, because those are the ones FG-05
    TC-TAX-002 leaves behind and the only ones whose printed layout the
    ``account_avatax`` patch changes — and it asks for them through
    ``fiscal_position_id.is_avatax``, the STORED field, because
    ``account.move.is_avatax`` cannot be put in a domain at all (see the
    comment on the pass below). Pass 2 widens to any posted customer
    invoice with more than one tax line — **for diagnosis only**: the caller
    BLOCKS when the invoice it gets back is not ``is_avatax``, so that the
    block message can name the best candidate on the database instead of
    saying "nothing found". Pass 2 must never become the document this case
    asserts against: with AvaTax switched off it always wins, and running
    AvaTax-shaped expectations (one printed row per Avalara jurisdiction,
    bracketed authority codes) against a legacy OCA-taxed invoice reports a
    document that was never going to carry a breakdown as broken.

    Returns ``(move_row, tax_lines, scanned)``; ``move_row`` is ``{}`` when
    nothing qualifies.
    """
    rpc = ctx.adapter.rpc
    context = company_ctx(company)
    base = [("move_type", "=", "out_invoice"), ("state", "=", "posted"),
            ("company_id", "=", company["id"])]
    passes = []
    if avatax_field:
        # The domain is on the FISCAL POSITION, not on ("is_avatax", "=",
        # True). ``account.move.is_avatax`` is a NON-STORED compute with no
        # search method (enterprise-19.0/account_avatax/models/
        # account_external_tax_mixin.py:18-23), so the ORM cannot put it in a
        # WHERE clause: ``Field.to_sql`` raises "Cannot convert ... to SQL
        # because it is not stored" (odoo/orm/fields.py:1215-1216). Searching
        # it does not return an empty set, it RAISES — and the ``except``
        # below would swallow that into "treated as none found", dropping the
        # case onto pass 2, the fallback this docstring says must never become
        # the document under test. The stored field the compute reads is
        # searched instead: ``account.fiscal.position.is_avatax`` ("Use AvaTax
        # API", account_avatax/models/account_fiscal_position.py:15) is a
        # plain stored Boolean and ``record.is_avatax`` IS
        # ``record.fiscal_position_id.is_avatax``, so the two select exactly
        # the same documents — one of them from SQL.
        passes.append(("AvaTax-flagged",
                       base + [("fiscal_position_id.is_avatax", "=", True)]))
    passes.append(("any posted customer invoice", base))

    scanned = 0
    for label, domain in passes:
        try:
            candidates = rpc.search_read(
                "account.move", domain,
                ["name", "invoice_date", "partner_id", "currency_id",
                 "amount_untaxed", "amount_tax", "amount_total"],
                order="id desc", limit=CANDIDATE_LIMIT, context=context)
        except OdooRPCError as exc:
            ctx.log(f"could not list {label} invoices ({exc}) — treated as "
                    f"none found")
            continue
        ctx.log(f"scanning {len(candidates)} {label} invoice(s), newest first")
        for row in candidates:
            scanned += 1
            try:
                lines = rpc.search_read(
                    "account.move.line",
                    [("move_id", "=", row["id"]),
                     ("display_type", "=", "tax")],
                    ["name", "tax_line_id", "tax_group_id", "balance",
                     "amount_currency", "tax_base_amount"],
                    context=context)
            except OdooRPCError as exc:
                ctx.log(f"  {row.get('name')!r}: tax lines unreadable ({exc})")
                continue
            authorities = {m2o_id(line.get("tax_line_id")) for line in lines
                           if m2o_id(line.get("tax_line_id"))}
            recorded_groups = {m2o_id(line.get("tax_group_id"))
                               for line in lines
                               if m2o_id(line.get("tax_group_id"))}
            if len(authorities) > 1:
                ctx.log(f"  {row.get('name')!r} qualifies — "
                        f"{len(authorities)} distinct tax(es) filed under "
                        f"{len(recorded_groups)} tax group(s)")
                return row, lines, scanned
        if candidates:
            ctx.log(f"no {label} invoice carries more than one tax authority")
    return {}, [], scanned


@test_case(
    id="TEST-FG07-INV-003",
    name="The invoice PDF shows tax broken down by authority",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module="mmg_account",
    priority="P1",
    kind="HYBRID",
    order=705,
    description="Read-only proof that the printed invoice's totals block "
                "carries one tax row per authority the journal entry "
                "recorded, that those rows carry their bracketed authority "
                "codes and add up with the untaxed amount to the Total, and "
                "that the AvaTax per-line tax column is gone without leaving "
                "a misaligned row. Creates nothing.",
    traceability=trace("TC-INV-003"))
def test_inv_003(ctx):
    rpc = ctx.adapter.rpc
    # Accumulators live outside the try: the evidence block runs from
    # `finally` and must never raise a NameError over a step an earlier
    # assertion failure skipped — that would replace a real FAILED verdict
    # with an AUTOMATION_ERROR.
    totals_rows: list[list] = []
    table_rows: list[list] = []
    residual: list[str] = []
    printed = {"html_status": None, "html": "", "pdf_status": None,
               "pdf_bytes": b""}

    with ctx.step("Precondition (workbook): FG-05 TC-TAX-002 has passed, so a "
                  "posted invoice exists whose tax is split across several "
                  "authorities"):
        require_v19(ctx)
        company = acting_company(ctx)
        ctx.log(f"acting company #{company['id']} {company['name']!r} — "
                f"company currency {company['currency_name']}")

        # ir.module.module, never model_exists: the OCA connector defines
        # account.tax.is_avatax too, so a model/field probe alone cannot tell
        # the two AvaTax generations apart.
        require_module(ctx, "account_avatax", NO_AVATAX_MODULE)
        oca_state = module_state(rpc, "account_avatax_oca")
        if oca_state:
            finding(ctx,
                    f"the v15 OCA connector 'account_avatax_oca' is also "
                    f"present on this database (state {oca_state!r}). It "
                    f"created ONE account.tax per RATE named '{{rate}}%*' "
                    f"with no jurisdiction at all "
                    f"(psus-medicine-man-gallery/account_avatax_oca/models/"
                    f"account_tax.py:26-52), so any invoice it taxed can "
                    f"never show a per-authority breakdown. Two AvaTax "
                    f"connectors installed side by side is itself worth "
                    f"raising")
        enhancement_state = module_state(rpc, "mmg_account_avatax_enhancement")
        ctx.log(f"module 'mmg_account_avatax_enhancement' (the override that "
                f"put the jurisdiction code into the tax name on v15): "
                f"{enhancement_state or 'no such module row'}")

        avatax_field = "is_avatax" in fields_present(rpc, "account.move",
                                                     ["is_avatax"])
        ctx.log(f"account.move.is_avatax readable: {avatax_field}")

        move, tax_lines, scanned = _pick_multi_authority_invoice(
            ctx, company, avatax_field)
        if not move:
            ctx.blocked(f"{NO_MULTI_AUTHORITY_INVOICE} ({scanned} posted "
                        f"customer invoice(s) examined)")

        move_id = move["id"]
        extra = ["is_avatax"] if avatax_field else []
        # rpc.read() sends no context, and this suite pins the acting company
        # on every read, so the call is made through rpc.call(). tax_totals is
        # a fields.Binary COMPUTE (account_move.py:599) — read() hands back the
        # whole summary dict, which is why the private
        # _get_tax_totals_summary never has to be called.
        detail = rpc.call("account.move", "read", [move_id],
                          fields=["name", "state", "move_type",
                                  "invoice_date", "partner_id", "currency_id",
                                  "amount_untaxed", "amount_tax",
                                  "amount_total", "fiscal_position_id",
                                  "tax_totals"] + extra,
                          context=company_ctx(company))[0]
        is_avatax = bool(detail.get("is_avatax")) if avatax_field else False
        ctx.log(f"invoice under test: #{move_id} {detail.get('name')!r} "
                f"dated {detail.get('invoice_date')} for "
                f"{m2o_name(detail.get('partner_id'))!r} — untaxed "
                f"{money(detail.get('amount_untaxed')):.2f} + tax "
                f"{money(detail.get('amount_tax')):.2f} = total "
                f"{money(detail.get('amount_total')):.2f} "
                f"{m2o_name(detail.get('currency_id'))}; fiscal position "
                f"{m2o_name(detail.get('fiscal_position_id'))!r}; "
                f"is_avatax={is_avatax}")
        if m2o_name(detail.get("partner_id")).startswith(f"{MARK} "):
            ctx.log("NOTE this invoice belongs to one of this platform's own "
                    "FG07 fixtures rather than to the gallery's data — the "
                    "reading is still valid, but say so when reporting")

        # THE PRECONDITION, ENFORCED. _pick_multi_authority_invoice falls back
        # to "any posted customer invoice" when no is_avatax document
        # qualifies, and on a database where AvaTax is switched off that
        # fallback ALWAYS wins. Running this case's AvaTax-shaped expectations
        # — one printed row per Avalara jurisdiction, each name carrying a
        # bracketed authority code — against a legacy OCA-taxed or manually
        # taxed invoice produces failures that say nothing about the upgrade:
        # the document was never going to carry an Avalara breakdown. The
        # workbook's precondition is "FG-05 TC-TAX-002 has passed", i.e. an
        # AvaTax-flagged document exists, so its absence is a BLOCK.
        if not is_avatax:
            ctx.blocked(
                f"{NO_MULTI_AUTHORITY_INVOICE} — {scanned} posted customer "
                f"invoice(s) were examined and the best candidate found, "
                f"{detail.get('name')!r} (fiscal position "
                f"{m2o_name(detail.get('fiscal_position_id'))!r}), carries "
                f"{len(tax_lines)} tax journal item(s) but is NOT flagged "
                f"is_avatax"
                + ("" if avatax_field else
                   " (account.move.is_avatax is not readable by this user "
                   "either, so the flag could not even be tested)")
                + ". It was taxed by something other than the Enterprise "
                  "AvaTax connector, so account_avatax's report patch does "
                  "not apply to it and it can carry no Avalara "
                  "per-jurisdiction breakdown at all. Asserting this case's "
                  "expectations against it would report the wrong document "
                  "as broken. On the mmg_19 restore this is the expected "
                  "outcome today: 'Use AvaTax' is off, 'Commit Transactions' "
                  "is off and 0 of 10 fiscal positions have 'Use AvaTax API' "
                  "ticked, so no document on the database can be is_avatax. "
                  "That configuration gap is FG-05 TC-DAT-017's finding — fix "
                  "it there, run FG-05 TC-TAX-002 against the Avalara "
                  "SANDBOX, and re-run this case")
        ctx.log("SAFETY — nothing below unlinks, writes or re-posts this "
                "move: unlinking an AvaTax document asks Avalara to void the "
                "filed transaction")

        tax_totals = detail.get("tax_totals")
        if not isinstance(tax_totals, dict) or not tax_totals.get("subtotals"):
            ctx.blocked(
                f"account.move.tax_totals on {detail.get('name')!r} came back "
                f"as {type(tax_totals).__name__} rather than the summary dict "
                f"the printed totals block is built from "
                f"(addons/account/models/account_move.py:599, computed at "
                f":1835-1842). Without it there is no totals block to read. "
                f"This usually means the move is not an invoice, or the "
                f"compute raised — open the invoice in the browser and check "
                f"the Total widget renders")

    try:
        with ctx.step("Step 1: open that invoice at Accounting > Customers > "
                      "Invoices, and read its journal entry tax lines"):
            # The journal entry is the workbook's reference point ("matching
            # what TC-TAX-002 found in the journal entry"), so it is read
            # first and independently of anything the report does.
            by_tax: dict[int, dict] = {}
            by_group: dict[int, dict] = {}
            for line in tax_lines:
                tax_id = m2o_id(line.get("tax_line_id"))
                group_id = m2o_id(line.get("tax_group_id"))
                # A customer invoice's tax journal items are CREDITS, so
                # balance/amount_currency are negative while tax_totals
                # reports the tax positively. The comparison is therefore made
                # on absolute values, which is also what the reader sees.
                amount = money(abs(line.get("amount_currency")
                                   or line.get("balance") or 0.0))
                entry = by_tax.setdefault(
                    tax_id, {"name": m2o_name(line.get("tax_line_id"))
                             or (line.get("name") or ""),
                             "group_id": group_id,
                             "group": m2o_name(line.get("tax_group_id")),
                             "amount": 0.0,
                             "base": money(line.get("tax_base_amount"))})
                entry["amount"] = money(entry["amount"] + amount)
                grp = by_group.setdefault(
                    group_id, {"name": m2o_name(line.get("tax_group_id")),
                               "amount": 0.0})
                grp["amount"] = money(grp["amount"] + amount)

            # The stored account.tax.name, read by id: it is the string the
            # gallery's override writes and the one TC-TAX-002 asserts on
            # screen. The many2one label is only the fallback.
            tax_names = _tax_names(ctx, by_tax.keys(), company_ctx(company))
            for tax_id, entry in by_tax.items():
                entry["tax_name"] = tax_names.get(tax_id) or entry["name"]

            for index, (tax_id, entry) in enumerate(
                    sorted(by_tax.items(), key=lambda kv: -kv[1]["amount"]), 1):
                code = AUTHORITY_CODE_RE.search(entry["tax_name"])
                ctx.log(f"  journal entry tax line {index}: "
                        f"{entry['tax_name']!r} = {entry['amount']:.2f} "
                        f"(account.tax #{tax_id}, tax group "
                        f"{entry['group']!r} #{entry['group_id']})")
                totals_rows.append(["journal_entry", index, entry["tax_name"],
                                    entry["amount"], entry["base"],
                                    entry["group_id"] or "", tax_id or "",
                                    code.group(1) if code else ""])
            ctx.log(f"the journal entry records {len(by_tax)} distinct tax "
                    f"authorit(ies) across {len(by_group)} tax group(s)")

        with ctx.step("Step 2 / Expected line 5: on screen, note whether a "
                      "Taxes column is shown on each line"):
            # The workbook is explicit that this is NOT a defect, so it is
            # logged and asserted in neither direction.
            arch = ""
            try:
                arch = form_arch(ctx, "account.move", "form") or ""
            except OdooRPCError as exc:
                ctx.log(f"the account.move form arch is unreadable ({exc}) — "
                        f"the on-screen observation is reported as unknown")
            region = arch
            start = arch.find('name="invoice_line_ids"')
            if start >= 0:
                end = arch.find('name="line_ids"', start)
                region = arch[start:end if end > start else len(arch)]
            optionals = re.findall(
                r'<field\s+name="tax_ids"[^>]*optional="(\w+)"', region)
            if optionals:
                observation(
                    ctx,
                    f"the invoice line list on the account.move form declares "
                    f"tax_ids with optional={optionals!r} "
                    f"(addons/account/views/account_move_views.xml:1217-1225 "
                    f"ships optional=\"show\"), so a Taxes column IS visible "
                    f"on screen by default in Odoo 19 even though the printed "
                    f"document for an AvaTax invoice has none. The workbook: "
                    f"'the tax column now DOES appear on screen where it used "
                    f"to be hidden, which is also not a defect'")
            else:
                observation(
                    ctx,
                    "no optional= attribute was found on the invoice line "
                    "list's tax_ids field in the account.move form arch, so "
                    "the on-screen Taxes column cannot be characterised from "
                    "the arch alone. Either way the workbook forbids raising "
                    "it — look at the screen and move on")

        with ctx.step("Steps 3-4 (workbook): click Print and open the PDF — "
                      "render the real report and capture it as evidence"):
            # Rendered up front, and NOT asserted here, so that the PDF the
            # workbook's If It Fails column asks for is attached even when one
            # of the figure assertions below fails first.
            state = wkhtmltopdf_state(ctx)
            ctx.log(f"ir.actions.report.get_wkhtmltopdf_state() -> "
                    f"{state or '(unavailable)'}")
            status, html = report_html(ctx, INVOICE_REPORT, move_id, "pdf")
            printed["html_status"] = status
            printed["html"] = html
            ctx.log(f"GET /report/html/{INVOICE_REPORT}/{move_id}"
                    f"?report_type=pdf -> HTTP {status}, "
                    f"{len(html)} character(s)")
            if state == "ok":
                pdf_status, pdf_bytes = report_pdf(ctx, INVOICE_REPORT,
                                                   move_id)
                printed["pdf_status"] = pdf_status
                printed["pdf_bytes"] = pdf_bytes
                ctx.log(f"GET /report/pdf/{INVOICE_REPORT}/{move_id} -> "
                        f"HTTP {pdf_status}, {len(pdf_bytes)} byte(s)")
            else:
                ctx.log(f"wkhtmltopdf is not usable on this server "
                        f"(state {state or 'unknown'}), so only the rendered "
                        f"HTML is captured. Every assertion below reads the "
                        f"same QWeb output the PDF is painted from, so none "
                        f"of them is weakened by this — only the visual "
                        f"residual step needs the binary")

        with ctx.step("Steps 4-5 / Expected line 1: read the tax rows of the "
                      "totals block — is there one row per authority, or one "
                      "combined row?"):
            groups = []
            for subtotal in tax_totals.get("subtotals") or []:
                for group in subtotal.get("tax_groups") or []:
                    groups.append({
                        "subtotal": subtotal.get("name") or "",
                        "id": group.get("id"),
                        "name": group.get("group_name") or "",
                        "amount": money(group.get("tax_amount_currency")),
                        "base": money(group.get("base_amount_currency")),
                        # The account.tax records this printed row is made of
                        # (addons/account/models/account_tax.py:2841-2845,
                        # 2882). This is
                        # what carries the jurisdiction name — the row's own
                        # label is the tax GROUP name — and Expected Result
                        # line 2 is asserted against it in step 6.
                        "involved": [int(tax_id) for tax_id
                                     in (group.get("involved_tax_ids") or [])],
                    })
            for index, group in enumerate(groups, 1):
                code = AUTHORITY_CODE_RE.search(group["name"])
                ctx.log(f"  totals block tax row {index}: {group['name']!r} = "
                        f"{group['amount']:.2f} (under subtotal "
                        f"{group['subtotal']!r}, account.tax.group "
                        f"#{group['id']})"
                        + (f" standing in for account.tax "
                           f"{group['involved']}" if group["involved"] else
                           " — tax_totals published no involved_tax_ids for "
                           "this row"))
                # tax_id carries the account.tax records behind the row, so
                # the CSV shows at a glance which jurisdictions a single
                # printed label is standing in for. authority_code is read
                # from the PRINTED label, and is therefore blank whenever the
                # tax group is not named per jurisdiction — which is the point.
                totals_rows.append(["pdf_totals_block", index, group["name"],
                                    group["amount"], group["base"],
                                    group["id"] or "",
                                    "|".join(str(tax_id) for tax_id
                                             in group["involved"]),
                                    code.group(1) if code else ""])

            if len(groups) == 1 and len(by_tax) > 1:
                finding(ctx,
                        f"the totals block collapses {len(by_tax)} journal "
                        f"entry tax lines into ONE printed row "
                        f"{groups[0]['name']!r}. The template prints "
                        f"tax_group['group_name'], which is "
                        f"account.tax.group.name "
                        f"(addons/account/models/account_tax.py:2889 ; "
                        f"addons/account/views/report_invoice.xml:551), so "
                        f"every Avalara jurisdiction has been filed under a "
                        f"single account.tax.group. This is the workbook's "
                        f"named defect: 'If the PDF shows one combined tax "
                        f"row where the journal entry has several, that is "
                        f"the defect'. Where to look first: "
                        f"_process_external_taxes sets tax_group_id only on "
                        f"the taxes it CREATES — a tax it matches by name and "
                        f"reuses keeps the group it already had "
                        f"(enterprise-19.0/account_external_tax/models/"
                        f"account_external_tax_mixin.py:127-156) — and "
                        f"keeping the v15 tax name is precisely what makes "
                        f"v15's migrated taxes match, so each reused "
                        f"jurisdiction tax drags its migrated tax group along "
                        f"with it — and v15 created those taxes with no "
                        f"tax_group_id at all (psus-medicine-man-gallery "
                        f"53f7985, mmg_account_avatax_enhancement/models/"
                        f"account_avatax.py:42-54), so they all took the "
                        f"database default group. Check the tax_group_id of "
                        f"the account.tax records listed in "
                        f"{TOTALS_CSV}")

            # The taxes-vs-groups gap, described in full BEFORE either
            # assertion so that a failure is triaged against the right object.
            # The totals block emits one row per account.tax.group
            # (report_invoice.xml:535-549), so when several taxes share a
            # group the ledger holds a breakdown the customer's copy does not.
            if len(by_tax) > len(by_group):
                finding(ctx,
                        f"the journal entry records {len(by_tax)} distinct "
                        f"tax(es) but only {len(by_group)} distinct tax "
                        f"group(s), so the printed totals block is "
                        f"structurally coarser than the ledger no matter how "
                        f"the report behaves: the document prints "
                        f"account.tax.group.name (addons/account/models/"
                        f"account_tax.py:2889 ; addons/account/views/"
                        f"report_invoice.xml:551), so every tax filed under "
                        f"one group is printed as ONE line. If the gallery "
                        f"needs a row per Avalara jurisdiction on the "
                        f"customer's copy, each jurisdiction needs its own "
                        f"account.tax.group — that is a configuration "
                        f"decision, not a template change")

            # FIRST, is the TEMPLATE faithful? The totals block emits one
            # <tr class="o_taxes"> per tax_groups[] entry and each of those is
            # one account.tax.group, so the printed rows must match the groups
            # the journal entry recorded, one for one. A group that is
            # recorded and not printed is money the customer's copy does not
            # explain. This assertion is deliberately made BEFORE the
            # workbook's own one below, because the two separate a TEMPLATE
            # fault from a DATA fault: when this passes and the next fails,
            # the report is printing the ledger faithfully and it is the
            # grouping of the taxes that loses the authority breakdown.
            ctx.check(
                "The printed totals block carries one tax row for each "
                "distinct tax GROUP the journal entry recorded, so the "
                "template prints the ledger's own grouping faithfully "
                "(len(tax_totals subtotals[].tax_groups[]) vs distinct "
                "account.move.line.tax_group_id where display_type='tax')",
                len(by_group), len(groups))

            # And each printed row must carry the money the journal entry
            # recorded for it — a breakdown with the right number of rows and
            # the wrong split is no more usable than a lumped one.
            wrong = []
            for group in groups:
                recorded = by_group.get(group["id"])
                if recorded is None:
                    wrong.append(f"printed row {group['name']!r} "
                                 f"({group['amount']:.2f}) has no matching "
                                 f"tax group in the journal entry")
                elif money(recorded["amount"]) != group["amount"]:
                    wrong.append(f"{group['name']!r}: printed "
                                 f"{group['amount']:.2f}, journal entry "
                                 f"{money(recorded['amount']):.2f}")
            for group_id, recorded in by_group.items():
                if group_id not in {g["id"] for g in groups}:
                    wrong.append(f"journal entry tax group "
                                 f"{recorded['name']!r} "
                                 f"({money(recorded['amount']):.2f}) is not "
                                 f"printed at all")
            ctx.check("Every printed tax row carries the amount the journal "
                      "entry recorded for that authority", [], wrong)

            # AND NOW the workbook's own line, on the workbook's own unit.
            # Expected Result line 1 is "the totals block lists the tax by
            # authority, matching what TC-TAX-002 found in the journal entry",
            # and the workbook names the failure in as many words: "if the PDF
            # shows one combined tax row where the journal entry has several,
            # that is the defect". The journal entry's authorities are its
            # distinct account.move.line.tax_line_id — one account.tax per
            # Avalara jurisdiction, which is exactly what
            # mmg_account_avatax_enhancement keeps the "[jurisCode]" naming
            # for (psus-medicine-man-gallery/mmg_account_avatax_enhancement/
            # models/account_external_tax_mixin.py:96). Measuring the printed
            # rows against the tax GROUPS instead cannot fail in that
            # scenario — tax_totals is BUILT by grouping those same lines by
            # account.tax.group (addons/account/models/account_tax.py:
            # 2826-2833) — so it would report the very collapse the workbook
            # calls the defect as a pass. The expectation is reachable: one
            # account.tax.group per jurisdiction is configuration, and Odoo
            # 19's own account_avatax already creates the groups that way
            # (enterprise-19.0/account_avatax/models/
            # account_external_tax_mixin.py:166, 179) for every tax it has to
            # create rather than reuse.
            ctx.check(
                "The totals block lists the tax BY AUTHORITY: the printed "
                "document carries one tax row for each authority the journal "
                "entry recorded, never one combined row (workbook Expected "
                "Result line 1; printed tax_totals subtotals[].tax_groups[] "
                "vs distinct account.move.line.tax_line_id where "
                "display_type='tax')",
                len(by_tax), len(groups))

        with ctx.step("Step 6 / Expected line 2: the tax names shown carry "
                      "the authority code in square brackets, as they did on "
                      "screen in TC-TAX-002"):
            # WHICH OBJECT CARRIES THE AUTHORITY CODE, and therefore what this
            # is asserted against. The printed row's LABEL is
            # account.tax.group.name (addons/account/models/account_tax.py:
            # 2889 ; addons/account/views/report_invoice.xml:551), and nothing
            # in this stack ever puts a jurisdiction code into a tax GROUP
            # name: Odoo 19's account_avatax names the group
            # tax_detail['taxName'].removesuffix(' TAX')
            # (enterprise-19.0/account_avatax/models/
            # account_external_tax_mixin.py:166, 179), and the gallery's v19
            # override rewrites tax_values['name'] ONLY, returning
            # tax_group_values exactly as super() built it and saying so —
            # "Only the name is rewritten here" (psus-medicine-man-gallery/
            # mmg_account_avatax_enhancement/models/
            # account_external_tax_mixin.py:82-97, the name at :96). Demanding
            # the brackets on the GROUP name therefore fails a correctly
            # ported system for a reason that has nothing to do with the
            # workbook's question, which is about the tax NAMES — the same
            # account.tax records FG-05 TC-TAX-002 reads on screen. So the
            # workbook line is asserted, unweakened, against the taxes the
            # printed rows are actually made of: tax_groups[j]
            # ['involved_tax_ids'] (account_tax.py:2841-2845, 2882), falling
            # back to the
            # journal entry's own tax_line_id when tax_totals does not publish
            # that key.
            printed_tax_ids = []
            for group in groups:
                printed_tax_ids.extend(group.get("involved") or [])
            printed_tax_ids = sorted({int(i) for i in printed_tax_ids if i})
            source = "tax_totals subtotals[].tax_groups[].involved_tax_ids"
            if not printed_tax_ids:
                printed_tax_ids = sorted(i for i in by_tax if i)
                source = ("the journal entry's account.move.line.tax_line_id "
                          "(tax_totals published no involved_tax_ids)")
            names = dict(tax_names)
            unknown = [i for i in printed_tax_ids if i not in names]
            if unknown:
                names.update(_tax_names(ctx, unknown, company_ctx(company)))
            ctx.log(f"the {len(groups)} printed tax row(s) are built from "
                    f"{len(printed_tax_ids)} account.tax record(s), read from "
                    f"{source}")

            labels = [group["name"] for group in groups]
            if not any(AUTHORITY_CODE_RE.search(label) for label in labels):
                finding(ctx,
                        f"the LABEL the customer's copy shows for each tax "
                        f"row is the tax GROUP name — printed here as "
                        f"{labels!r} — because the template prints "
                        f"tax_group['group_name'] "
                        f"(addons/account/models/account_tax.py:2889 ; "
                        f"addons/account/views/report_invoice.xml:551), and "
                        f"no group name on this document carries a bracketed "
                        f"authority code. The jurisdiction lives on the "
                        f"account.tax records asserted below, which is where "
                        f"mmg_account_avatax_enhancement writes it and where "
                        f"FG-05 TC-TAX-002 reads it on screen. For the "
                        f"authority to be legible ON THE PRINTED PAGE the "
                        f"account.tax.group names have to carry it too — a "
                        f"configuration/port decision about tax groups, not a "
                        f"report-template change")

            unbracketed = []
            for tax_id in printed_tax_ids:
                recorded = by_tax.get(tax_id) or {}
                name = (names.get(tax_id) or recorded.get("tax_name")
                        or recorded.get("name") or f"account.tax #{tax_id}")
                code = AUTHORITY_CODE_RE.search(name)
                if code:
                    ctx.log(f"  account.tax #{tax_id} {name!r} -> authority "
                            f"code {code.group(1)!r}")
                else:
                    unbracketed.append(
                        f"{name!r} ({money(recorded.get('amount')):.2f})")
            ctx.check("Every tax the printed totals block is built from "
                      "carries its authority code in square brackets in its "
                      "account.tax.name, as TC-TAX-002 saw on screen "
                      "(workbook Expected Result line 2)",
                      [], unbracketed)

        with ctx.step("Step 7 / Expected line 3: the tax rows plus the "
                      "untaxed amount equal the Total"):
            base = money(tax_totals.get("base_amount_currency"))
            rounding = money(tax_totals.get(
                "cash_rounding_base_amount_currency"))
            printed_total = money(tax_totals.get("total_amount_currency"))
            tax_sum = money(sum(group["amount"] for group in groups))
            ctx.log(f"untaxed {base:.2f} + tax rows {tax_sum:.2f}"
                    + (f" + cash rounding {rounding:.2f}" if rounding else "")
                    + f" ; printed Total {printed_total:.2f}")
            # base + tax + cash_rounding is literally how Odoo builds the
            # printed Total (addons/account/models/account_tax.py:3004-3005),
            # so a mismatch means a tax row is missing from the block rather
            # than an arithmetic slip.
            ctx.check("The tax rows plus the untaxed amount (plus cash "
                      "rounding, when the invoice has any) equal the Total "
                      "printed at the foot of the totals block",
                      printed_total, money(base + tax_sum + rounding))
            # And the same figure must be the invoice's own Total, or the PDF
            # and the list view disagree about what the customer owes.
            ctx.check("The Total printed on the document equals the invoice's "
                      "own amount_total", money(detail.get("amount_total")),
                      printed_total)
            ctx.check("The untaxed amount printed above the tax rows equals "
                      "the invoice's own amount_untaxed",
                      money(detail.get("amount_untaxed")), base)

        with ctx.step("Steps 3 and 8 / Expected line 4: the printed line "
                      "table has no per-line tax column, and the table is "
                      "still correctly aligned"):
            status = printed["html_status"]
            html = printed["html"]
            # A 500 here is a finding about the report, recorded as one rather
            # than allowed to become an AUTOMATION_ERROR.
            ctx.check(f"The Print button's report "
                      f"({INVOICE_REPORT}) renders for this invoice",
                      200, status)

            expected_rows = len(groups) * (
                2 if tax_totals.get("display_in_company_currency") else 1)
            if tax_totals.get("display_in_company_currency"):
                ctx.log("this invoice is in a foreign currency and the "
                        "company prints the company-currency tax block too "
                        "(addons/account/views/report_invoice.xml:417-419), "
                        "so every tax row is emitted twice — the expected "
                        "count is doubled accordingly")
            o_taxes = len(O_TAXES_RE.findall(html))
            o_total = len(O_TOTAL_RE.findall(html))
            ctx.log(f"rendered document: {o_taxes} <tr class=\"o_taxes\"> "
                    f"row(s), {o_total} <tr class=\"o_total\"> row(s)")
            ctx.check("The rendered document prints exactly as many tax rows "
                      "as tax_totals holds tax groups "
                      "(<tr class=\"o_taxes\">)", expected_rows, o_taxes)

            missing = [group["name"] for group in groups
                       if not _appears(html, group["name"])]
            ctx.check("Every tax group name is printed verbatim in the "
                      "rendered document, byte for byte as "
                      "account.tax.group.name holds it", [], missing)

            # is_avatax is TRUE here by construction: the precondition step
            # BLOCKS the case when the chosen invoice is not AvaTax-flagged,
            # precisely so that these two AvaTax-only assertions are never
            # made against a document account_avatax's report patch does not
            # apply to. There is therefore no "not an AvaTax invoice" branch
            # left to write — that outcome is a BLOCK with its own reason,
            # not a half-judged pass.
            ctx.log(f"invoice {detail.get('name')!r} is flagged is_avatax "
                    f"(fiscal position "
                    f"{m2o_name(detail.get('fiscal_position_id'))!r}), so "
                    f"account_avatax's report patch applies to it and "
                    f"Expected Result line 4 can be judged in full")
            suppressed = []
            if 'name="th_taxes"' in html:
                suppressed.append(
                    'the header cell <th name="th_taxes"> is still '
                    'rendered, although account_avatax/reports/'
                    'account_invoice.xml adds not o.is_avatax to its t-if')
            if 'id="line_tax_ids"' in html:
                suppressed.append(
                    'a per-line tax cell <span id="line_tax_ids"> is '
                    'still rendered (report_invoice.xml:245)')
            ctx.check("The line table has no per-line tax column on an "
                      "AvaTax invoice, as account_avatax's report patch "
                      "intends", [], suppressed)

            # The patch covers the ungrouped branch only. A stray cell
            # here is the OPPOSITE misalignment — one column too many —
            # and it is exactly what workbook step 8 hunts.
            stray = []
            if 'id="grouped_line_tax_ids"' in html:
                stray.append('<span id="grouped_line_tax_ids">')
            if 'name="td_taxes_grouped"' in html:
                stray.append('<td name="td_taxes_grouped">')
            ctx.check(
                "No stray per-line tax cell survives in the "
                "collapsed-section branch of the table, which "
                "account_avatax's report patch does not cover "
                "(report_invoice.xml:350-354)", [], stray)

            table_match = TABLE_RE.search(html)
            if not table_match:
                ctx.check(
                    "The rendered document contains the invoice line table "
                    "(<table name=\"invoice_line_table\">), without which "
                    "workbook step 8 has nothing to align",
                    True, False)
            body = table_match.group(1) if table_match else ""
            head_match = THEAD_RE.search(body)
            tbody_match = TBODY_RE.search(body)
            head_cells = _cells(head_match.group(1)) if head_match else []
            header_width = sum(cell["colspan"] for cell in head_cells)
            ctx.log(f"printed table header: {len(head_cells)} visible cell(s) "
                    f"spanning {header_width} column(s) — "
                    f"{[cell['name'] for cell in head_cells]}")
            table_rows.append(["thead", 0, len(head_cells), header_width,
                               header_width, "yes",
                               "|".join(cell["name"] for cell in head_cells)])

            misaligned = []
            body_html = tbody_match.group(1) if tbody_match else ""
            for index, row_html in enumerate(ROW_RE.findall(body_html), 1):
                cells = _cells(row_html)
                if not cells:
                    continue
                width = sum(cell["colspan"] for cell in cells)
                # A note row deliberately spans the whole table with
                # colspan="99" (report_invoice.xml:273); it is not a
                # misalignment and must not be counted as one.
                full_width = any(cell["colspan"] >= FULL_WIDTH_COLSPAN
                                 for cell in cells)
                aligned = full_width or width == header_width
                names = "|".join(cell["name"] or "(unnamed)" for cell in cells)
                table_rows.append(["tbody", index, len(cells), width,
                                   header_width, "yes" if aligned else "no",
                                   names])
                if not aligned:
                    misaligned.append(
                        f"row {index} spans {width} column(s) against a "
                        f"{header_width}-column header (cells: {names})")
            ctx.log(f"printed table body: {len(table_rows) - 1} row(s) "
                    f"measured, {len(misaligned)} misaligned")
            # This is the cell arithmetic behind "does not leave a blank gap
            # or a misaligned row". line_colspan for a section row is computed
            # as though the Taxes header existed (report_invoice.xml:223), so
            # on an AvaTax invoice a section row prints one column too wide —
            # which this catches without anyone squinting at the paper.
            ctx.check("Every printed row of the line table spans exactly as "
                      "many columns as the header, so removing the Taxes "
                      "column left no blank gap and no misaligned row",
                      [], misaligned)

            residual.append(
                "confirm visually on the attached " + PDF_ARTIFACT + " that "
                "the totals block reads as " + str(len(groups)) + " tax "
                "row(s) — " + "; ".join(
                    f"{group['name']} {group['amount']:.2f}"
                    for group in groups) + " — over an untaxed amount of "
                f"{money(tax_totals.get('base_amount_currency')):.2f} and a "
                f"Total of "
                f"{money(tax_totals.get('total_amount_currency')):.2f}, and "
                f"that the line table shows no blank gutter where the Taxes "
                f"column used to sit. The cell arithmetic above proves the "
                f"COLUMN COUNTS are right; only the paint is left to a human. "
                f"Put this PDF beside the journal entry of FG-05 TC-TAX-002, "
                f"as the workbook's If It Fails column asks.")
    finally:
        with ctx.step("Evidence: write the totals-block, journal-entry and "
                      "printed-table CSVs and attach the rendered document"):
            for path_name, header, rows in (
                (TOTALS_CSV, TOTALS_HEADER, totals_rows),
                (TABLE_CSV, TABLE_HEADER, table_rows),
            ):
                path = ctx.artifacts_dir / path_name
                try:
                    with path.open("w", newline="", encoding="utf-8") as fh:
                        writer = csv.writer(fh)
                        writer.writerow(header)
                        writer.writerows(rows)
                    ctx.add_artifact(path, "log", path_name)
                    ctx.log(f"wrote {len(rows)} row(s) to {path_name}")
                except OSError as exc:
                    ctx.log(f"could not write {path_name} ({exc}) — the "
                            f"figures above are still in this log")

            if printed.get("pdf_bytes"):
                path = ctx.artifacts_dir / PDF_ARTIFACT
                try:
                    path.write_bytes(printed["pdf_bytes"])
                    ctx.add_artifact(path, "pdf", PDF_ARTIFACT)
                    ctx.log(f"attached {PDF_ARTIFACT} "
                            f"({len(printed['pdf_bytes'])} byte(s)) — this is "
                            f"the file the workbook's If It Fails column asks "
                            f"for")
                except OSError as exc:
                    ctx.log(f"could not save {PDF_ARTIFACT} ({exc})")
            if printed.get("html"):
                path = ctx.artifacts_dir / HTML_ARTIFACT
                try:
                    path.write_text(printed["html"], encoding="utf-8")
                    ctx.add_artifact(path, "log", HTML_ARTIFACT)
                except OSError as exc:
                    ctx.log(f"could not save {HTML_ARTIFACT} ({exc})")

            for note in residual:
                residual_manual_step(ctx, note)
            ctx.log("NOTHING WAS CREATED OR MODIFIED by this case — the "
                    "workbook's State After The Test is 'Nothing changed', so "
                    "no sweep and no cleanup runs here either (a sweep is "
                    "itself a delete, and this case reads an AvaTax document "
                    "whose deletion would void a filed Avalara transaction).")
