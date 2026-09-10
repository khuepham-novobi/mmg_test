"""FG-07 — TC-INV-015: 1099 reporting is still available.

Implements row 41.0 (P2, "Tax reporting") of the CLIENT MANUAL TESTING
GUIDELINE ``MMG_v19_Client_Manual_Testing_Guideline_FG05-FG14_v1.0.xlsx`` /
sheet ``Testing Guideline``.

The workbook's framing: *"The gallery pays consignors and contractors and has
to file 1099s. The report must still be reachable and must still run."*

The workbook's *Why It Matters* column is the whole point of the case: the
entry **moved** in Odoo 19, and its label **ends in an ellipsis** because it
opens a set-up dialog rather than a report. Both of those are turned into
hard assertions below rather than left to the tester's eye.

The four Expected Result lines, and what each is read from
----------------------------------------------------------
1. **"The 1099 Report… entry is present under Taxes & Fiscal."** — read from
   ``ir.ui.menu`` via the xmlid
   ``l10n_us_1099.menu_action_view_l10n_us_1099_wizard``, whose ``name`` and
   ``parent`` are declared in
   ``enterprise-19.0/l10n_us_1099/wizard/generate_1099_wizard_views.xml:41``::

       <menuitem action="view_l10n_us_1099_wizard_act_window"
                 id="menu_action_view_l10n_us_1099_wizard"
                 name="1099 Report…" sequence="50"
                 parent="account.account_reports_taxes_and_fiscal_menu"
                 groups="account.group_account_readonly"/>

   The label's last character was read out of that file **byte by byte**: it
   is a single U+2026 HORIZONTAL ELLIPSIS, *not* three ASCII full stops. The
   workbook says "the name ends in three dots", which is what it looks like
   on screen; a test that compared against ``"..."`` would fail a correct
   system, so :data:`MENU_NAME` is built from ``common.ELLIPSIS``.
   The parent section ``account.account_reports_taxes_and_fiscal_menu`` is
   Community's own (``addons/account/views/account_menuitem.xml:39``), and it
   is asserted **positively** (the entry hangs there) and **negatively** (it
   is not still under ``account.account_reports_management_menu``,
   ``addons/account/views/account_menuitem.xml:40``, which the migration
   brief records as the v15 home — that claim about v15 is [UNVERIFIED] here
   because no Enterprise 15 tree exists on this machine, but the negative
   assertion costs nothing and names the v15 location in the failure text).
   "Present" is proven twice: the record exists with that parent, *and* the
   entry comes back from the public ``ir.ui.menu.load_menus(False)``
   (``odoo/addons/base/models/ir_ui_menu.py:236-312``), which is the list the
   web client actually paints — a menu row can exist and still be invisible.
2. **"It opens without error."** — read from the action the menu points at
   (``ir.actions.act_window`` ``view_l10n_us_1099_wizard_act_window``,
   ``…/generate_1099_wizard_views.xml:34-39``: ``res_model``
   ``l10n_us_1099.wizard``, ``target`` ``new``, ``view_mode`` ``form``), then
   from ``get_views([[False,'form']])`` returning an arch, then from a real
   ``create`` of the transient record. Every one of those three is wrapped in
   ``try/except OdooRPCError`` and turned into a ``ctx.check``: an Access
   Error on opening the dialog is a **finding about this report**, not a
   broken test.
3. **"It produces output for the year selected."** — the dates come from
   ``l10n_us_1099.wizard.start_date`` / ``end_date``, whose defaults are the
   first and last day of *last year*
   (``…/wizard/generate_1099_wizard.py:14-34``), i.e. exactly the workbook's
   Test Data ("Year: the last completed calendar year"). The output is the
   CSV built by the **public** ``action_generate``
   (``…/wizard/generate_1099_wizard.py:110-172``), read back out of the
   ``generated_csv_file`` Binary field and decoded. Its header is asserted
   against the 18 fixed Payer/Payee columns hard-coded at
   ``…/generate_1099_wizard.py:114-133`` followed by one column per
   ``l10n_us.1099_box`` record (``:134-135``), read live from the database
   rather than from the shipped ``data/l10n_us.1099_box.csv``.
4. **"The output can be exported."** — ``action_generate`` returns an
   ``ir.actions.act_url`` pointing at
   ``/web/content?model=l10n_us_1099.wizard&download=true&field=generated_csv_file&…``
   (``…/generate_1099_wizard.py:166-172``). The URL shape is asserted, and
   then the file is actually **downloaded over an authenticated web session**
   and the bytes compared with the field — which is the only way to prove
   "can be exported" rather than "offers a link".

Documented adaptation — no 1099 payment is ever fabricated
-----------------------------------------------------------
The obvious way to guarantee a vendor row would be to create an FG07 vendor
with a ``box_1099_id`` and post a bank payment to it inside the reporting
year. This case deliberately does **not** do that. A posted journal entry
cannot be unlinked (``tests/fg07/common.py:1077-1094``), so the fabricated
payment would stay in the gallery's books, and it would then appear in the
gallery's real 1099 export — a test fixture inside an IRS filing. The
workbook agrees: *State After The Test* is "Nothing changed. Do not file
anything."

So the only record this case creates is **one ``l10n_us_1099.wizard``
row** — a ``TransientModel`` (``…/generate_1099_wizard.py:10``), which
``ir.autovacuum`` removes on its own. No ``account.move``, no
``account.payment``, no ``res.partner``, no ``product``. ``sweep_fg07`` and
``cleanup`` still run, per the suite convention, but they have nothing of
this case's to remove.

The consequence is that "at least one vendor appears" is asserted
**conditionally**, exactly as the workbook words it ("*if* the gallery had
1099-reportable payments that year"):

* the CSV and its header row are asserted unconditionally — that is
  "produces output";
* if ``lines_to_export`` came back populated, at least one vendor data row is
  a hard assertion;
* if it came back empty, the workbook's own *If It Fails* instruction is
  emitted as a RESIDUAL MANUAL STEP ("check with Novobi whether the gallery
  had reportable payments that year before raising it") — never as a pass and
  never as a silent skip.

A finding this case is built to surface
---------------------------------------
The menu is published to ``account.group_account_readonly``
(``…/generate_1099_wizard_views.xml:41``) but the only ACL row for
``l10n_us_1099.wizard`` grants ``account.group_account_invoice``
(``enterprise-19.0/l10n_us_1099/security/ir.model.access.csv:2``), and
``group_account_readonly`` does **not** imply ``group_account_invoice`` —
they are two independent branches
(``addons/account/security/account_security.xml:50-61``; only
``group_account_user`` sits above both, ``:68-71``). Because
``_visible_menu_ids`` hides a menu whose action's model the user cannot read
(``odoo/addons/base/models/ir_ui_menu.py:127``), a user holding *only* the
workbook's stated precondition group — "Show Accounting Features - Readonly"
— will not see the entry at all, and could not press Generate if they did.
That is logged as a FINDING on every run, because it means the workbook's
precondition line is not sufficient in v19; the runner user's own access is
probed with the public ``has_access`` and BLOCKs with that explanation rather
than failing.

An observation, asserted in neither direction
----------------------------------------------
``action_generate``'s row-grouping loop (``…/generate_1099_wizard.py:141-161``)
only flushes a vendor's row when the running total is non-zero, so a vendor
whose payments net to exactly zero is folded into the *next* vendor's total
instead of producing its own row. The number of data rows is therefore **not**
asserted to equal the number of distinct vendors; the per-vendor totals read
from ``account.move.line`` are written to the evidence CSV so a human can see
any such fold. The workbook asks only that "at least one vendor appears".

Sources read for this module
----------------------------
* ``D:/Projects/odoo-19.0/enterprise-19.0/l10n_us_1099/`` (manifest, wizard,
  views, security, data) — Odoo 19 Enterprise, licence OEEL-1.
* ``D:/Projects/odoo-19.0/addons/account/views/account_menuitem.xml``,
  ``…/account/security/account_security.xml`` — Odoo 19 Community.
* ``D:/Projects/odoo-19.0/odoo/addons/base/models/ir_ui_menu.py``,
  ``D:/Projects/odoo-19.0/odoo/service/model.py``,
  ``D:/Projects/odoo-19.0/odoo/orm/models.py``.
"""
from __future__ import annotations

import base64
import csv
import urllib.error

from adapters.base import OdooRPCError
from framework.registry import test_case
from tests.fg07.common import (ELLIPSIS, MARK, MENU_1099_XMLID, NO_1099,
                               TAXES_AND_FISCAL_MENU_XMLID, WIZARD_1099,
                               WORKFLOW, WORKFLOW_NAME, acting_company,
                               cleanup, company_ctx, finding, form_defaults,
                               m2o_id, m2o_name, menu_by_xmlid, money,
                               observation, require_module, require_v19,
                               residual_manual_step, sweep_fg07, trace)

EVIDENCE_CSV = "TC-INV-015-1099-run.csv"
EVIDENCE_HEADER = ["subject", "detail", "value"]
REPORT_CSV = "TC-INV-015-1099-report-redacted.csv"

# The menu label, built from the ellipsis constant rather than typed. The
# character was confirmed by codepoint dump of
# enterprise-19.0/l10n_us_1099/wizard/generate_1099_wizard_views.xml:41 —
# ord() == 0x2026, ONE character. Three ASCII periods would be 0x2e 0x2e 0x2e.
MENU_NAME = "1099 Report" + ELLIPSIS
MENU_LABEL = "Accounting > Reporting > Taxes & Fiscal > 1099 Report" + ELLIPSIS

# The v15 home of this entry, per the migration brief. [UNVERIFIED] against
# source — no Enterprise 15 tree exists on this machine — but naming it in a
# failure message is what turns "it has moved" into an actionable sentence.
V15_MENU_PARENT_XMLID = "account.account_reports_management_menu"

# The action the menu opens
# (…/wizard/generate_1099_wizard_views.xml:34-39).
ACTION_XMLID = "l10n_us_1099.view_l10n_us_1099_wizard_act_window"

# The 18 fixed columns action_generate writes before the per-box columns,
# verbatim and in order from …/wizard/generate_1099_wizard.py:114-133.
FIXED_HEADER = [
    "Payer Name", "Payer Address Line 1", "Payer Address Line 2",
    "Payer City", "Payer State", "Payer Zip", "Payer Country",
    "Payer Phone Number", "Payer TIN",
    "Payee Name", "Payee Address Line 1", "Payee Address Line 2",
    "Payee City", "Payee State", "Payee Zip", "Payee Country",
    "Payee Email", "Payee TIN",
]
# Columns redacted out of the artifact. A Taxpayer Identification Number is a
# US federal identifier; the run still proves it is populated by recording
# "set" / "not set", the same treatment TC-INV-010 gives a credential.
TIN_COLUMNS = ("Payer TIN", "Payee TIN")

# ir.model.access.csv:2 grants only this group; the menu is published to
# account.group_account_readonly. See the module docstring.
ACL_GROUP = "account.group_account_invoice"
MENU_GROUP = "account.group_account_readonly"

NO_1099_ACCESS = (
    "The runner user cannot open the 1099 Report" + ELLIPSIS + " dialog: it "
    "has no access to the model l10n_us_1099.wizard. The module ships exactly "
    "ONE ACL row for that model and it grants 'Invoicing' "
    "(account.group_account_invoice) only "
    "(enterprise-19.0/l10n_us_1099/security/ir.model.access.csv:2), while the "
    "menu itself is published to 'Show Accounting Features - Readonly' "
    "(account.group_account_readonly, "
    "enterprise-19.0/l10n_us_1099/wizard/generate_1099_wizard_views.xml:41). "
    "Those two groups are independent branches — readonly does NOT imply "
    "invoicing (addons/account/security/account_security.xml:50-61) — so the "
    "group the workbook names as the precondition is NOT sufficient in Odoo "
    "19. Give the runner user 'Show Full Accounting Features' "
    "(account.group_account_user), which implies both "
    "(account_security.xml:68-71), and re-run. Do NOT treat this as the "
    "report being missing"
)

NO_1099_VENDORS = (
    "No contact on this database carries a 1099 Box "
    "(res.partner.box_1099_id, enterprise-19.0/l10n_us_1099/models/"
    "res_partner.py:8-12), so the report is CORRECTLY empty and running it "
    "would prove nothing: the wizard's line selection filters on "
    "partner_id.box_1099_id != False "
    "(enterprise-19.0/l10n_us_1099/wizard/generate_1099_wizard.py:60). The "
    "workbook's own precondition is 'at least one vendor exists who was "
    "1099-reportable in the old system' — if the gallery had reportable "
    "vendors in v15 and none carry a 1099 Box here, the box assignment did "
    "not migrate, and THAT is the finding to raise with Novobi rather than a "
    "failure of this report"
)


def _iso_year_bounds(year: int) -> tuple[str, str]:
    """The ISO dates the wizard's own defaults produce for ``year``.

    ``_default_start_date`` / ``_default_end_date`` are
    ``today.replace(today.year - 1, 1, 1)`` and ``…, 12, 31)``
    (…/wizard/generate_1099_wizard.py:14-22), so the calendar year is the
    whole of the selection — there is no ``year`` field on the wizard and
    writing one would be silently ignored.
    """
    return f"{year}-01-01", f"{year}-12-31"


def _menu_children(menus: dict, menu_id) -> list:
    """Children of one node out of ``ir.ui.menu.load_menus`` output.

    ``load_menus`` returns a dict keyed by menu id, but the ids arrive over
    JSON as strings, so both shapes are looked up
    (``odoo/addons/base/models/ir_ui_menu.py:284-306``).
    """
    node = menus.get(menu_id) or menus.get(str(menu_id)) or {}
    return list(node.get("children") or [])


@test_case(
    id="TEST-FG07-INV-015",
    name="1099 reporting is still available",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module="l10n_us_1099",
    priority="P2",
    kind="DATA",
    order=712,
    description="Proves the 1099 Report entry still hangs under Reporting > "
                "Taxes & Fiscal with its single-character ellipsis label, "
                "that the wizard opens, that it defaults to and reports on "
                "the last completed calendar year, and that the generated "
                "CSV really downloads — without fabricating a single 1099 "
                "payment.",
    traceability=trace("TC-INV-015"))
def test_inv_015(ctx):
    rpc = ctx.adapter.rpc
    # Nothing marker-scoped is ever created by this case (see the docstring):
    # the only record is one TransientModel wizard row, which ir.autovacuum
    # collects. The dict is still declared and still handed to cleanup() so
    # the suite's teardown contract holds if this file ever grows a fixture.
    created: dict = {}
    evidence: list[tuple] = []       # CSV rows — declared BEFORE the try
    residual: list[str] = []         # residual notes — declared BEFORE the try
    # Everything below is filled inside the try; declared here so the finally
    # block can never raise NameError over a step an earlier failure skipped.
    report_rows: list[list] = []
    defaults_were_last_year = None
    default_start = default_end = ""
    target_year = 0

    with ctx.step("Precondition (workbook): the 'Show Accounting Features - "
                  "Readonly' group, and at least one vendor that was "
                  "1099-reportable in the old system"):
        require_v19(ctx)
        # ir.module.module, never model_exists: see tests/fg07/common.py:38-48.
        require_module(ctx, "l10n_us_1099", NO_1099)
        company = acting_company(ctx)
        ctx.log(f"acting company #{company['id']} {company['name']!r} — "
                f"currency {company['currency_name']}, country "
                f"{company['country_name']!r}, VAT/TIN "
                f"{'set' if company['vat'] else 'NOT SET'}")
        # The Payer block of every CSV row is this company's address
        # (…/generate_1099_wizard.py:80-89). A blank Payer TIN would make the
        # export unusable for e-filing, so it is reported, not asserted —
        # fixing company data is not what this case is about.
        if not company["vat"]:
            finding(ctx, "the acting company has no VAT/TIN, so the 'Payer "
                         "TIN' column of every generated row will be blank "
                         "(…/generate_1099_wizard.py:89). The export would be "
                         "rejected by an e-filing service. Set it under "
                         "Settings > Companies before the gallery files.")
        sweep_fg07(ctx)

        # The ACL / menu-group asymmetry is a property of the SOURCE, not of
        # this database, so it is logged unconditionally — it is the reason
        # the workbook's precondition line is not sufficient in v19.
        finding(ctx,
                f"the 1099 menu is published to {MENU_GROUP} "
                f"(…/generate_1099_wizard_views.xml:41) but the only ACL row "
                f"for {WIZARD_1099} grants {ACL_GROUP} "
                f"(…/security/ir.model.access.csv:2), and readonly does not "
                f"imply invoicing "
                f"(addons/account/security/account_security.xml:50-61). "
                f"_visible_menu_ids hides a menu whose action model the user "
                f"cannot read (odoo/addons/base/models/ir_ui_menu.py:127), so "
                f"an accountant holding ONLY the workbook's stated group will "
                f"not see this entry at all. The workbook precondition needs "
                f"correcting to 'Show Full Accounting Features'.")

        access = {}
        for operation in ("read", "create"):
            try:
                # has_access is public; check_access is @api.private in v19
                # (odoo/orm/models.py:4099-4117) and would be refused before
                # it was even looked up (odoo/service/model.py:54-55).
                access[operation] = bool(rpc.call(WIZARD_1099, "has_access",
                                                  [], operation))
            except OdooRPCError as exc:
                access[operation] = False
                ctx.log(f"has_access({operation!r}) on {WIZARD_1099} could "
                        f"not be evaluated ({exc}) — treated as no access")
        ctx.log(f"runner access to {WIZARD_1099}: "
                f"read={access['read']} create={access['create']}")
        evidence.append(("access", "has_access(read)", access["read"]))
        evidence.append(("access", "has_access(create)", access["create"]))
        if not (access["read"] and access["create"]):
            ctx.blocked(f"{NO_1099_ACCESS} (read={access['read']}, "
                        f"create={access['create']})")

        # The workbook's own precondition, and the brief's fourth probe: with
        # no 1099-boxed contact the report is legitimately empty, so an empty
        # result would prove nothing either way.
        try:
            boxed = rpc.call("res.partner", "search_count",
                             [("box_1099_id", "!=", False)])
        except OdooRPCError as exc:
            boxed = 0
            ctx.log(f"res.partner.box_1099_id not searchable ({exc}) — "
                    f"treated as zero 1099 contacts")
        ctx.log(f"contacts carrying a 1099 Box: {boxed}")
        evidence.append(("precondition", "contacts with a 1099 Box", boxed))
        if not boxed:
            ctx.blocked(NO_1099_VENDORS)

    try:
        with ctx.step("Step 1 / Expected line 1: Accounting > Reporting > "
                      "Taxes & Fiscal holds an entry named '1099 Report" +
                      ELLIPSIS + "' (the name ends in three dots)"):
            section = menu_by_xmlid(ctx, TAXES_AND_FISCAL_MENU_XMLID)
            # The workbook's If It Fails asks this question first: a missing
            # SECTION is a different fix from a missing ENTRY, so it is
            # answered before anything about the entry is asserted.
            ctx.check_true(
                "The 'Taxes & Fiscal' section itself exists under Reporting "
                "(account.account_reports_taxes_and_fiscal_menu — Community, "
                "addons/account/views/account_menuitem.xml:39)",
                bool(section),
                actual_desc=(f"resolved to menu #{section.get('id')} "
                             f"{section.get('name')!r} under "
                             f"{section.get('parent_name')!r}") if section
                else "the xmlid account.account_reports_taxes_and_fiscal_menu "
                     "does not resolve at all, which means the 'account' "
                     "module's menu data did not load — the whole Reporting "
                     "tree is affected, not just 1099")
            ctx.log(f"section #{section['id']} {section['name']!r} "
                    f"(sequence {section['sequence']}, "
                    f"active={section['active']})")

            entry = menu_by_xmlid(ctx, MENU_1099_XMLID)
            ctx.check_true(
                f"The menu record {MENU_1099_XMLID} exists (the "
                f"'1099 Report{ELLIPSIS}' entry)",
                bool(entry),
                actual_desc=(f"menu #{entry.get('id')} {entry.get('name')!r}")
                if entry else
                f"the xmlid {MENU_1099_XMLID} does not resolve, yet "
                f"ir.module.module reports l10n_us_1099 installed — the "
                f"module's view data did not load, so re-upgrade the module")

            actual_name = entry["name"]
            ctx.log("menu label codepoints: "
                    + " ".join(f"U+{ord(ch):04X}" for ch in actual_name))
            evidence.append(("menu", "label", actual_name))
            evidence.append(("menu", "label codepoints",
                             " ".join(f"U+{ord(ch):04X}"
                                      for ch in actual_name)))
            # Asserted before the full-name check so that a label which reads
            # correctly on screen but ends in three ASCII periods names the
            # real difference instead of dumping two look-alike strings.
            ctx.check_true(
                "The entry's label ends in a single-character ellipsis "
                "U+2026, which is what tells the accountant it opens a "
                "set-up screen rather than a report "
                "(generate_1099_wizard_views.xml:41)",
                actual_name.endswith(ELLIPSIS),
                actual_desc=f"the label ends in "
                            f"{[f'U+{ord(c):04X}' for c in actual_name[-3:]]}"
                            f" — three ASCII full stops (U+002E) would mean "
                            f"someone retyped the label")
            ctx.check("The entry under Taxes & Fiscal is named exactly "
                      "'1099 Report' followed by U+2026",
                      MENU_NAME, actual_name)

            # "It has moved" made into an assertion. The negative comes first
            # so that a database still carrying the v15 placement says so.
            v15_parent_id = rpc.ref(V15_MENU_PARENT_XMLID)
            ctx.check_true(
                f"The entry is NOT still hanging under Reporting > "
                f"Management ({V15_MENU_PARENT_XMLID}), which the migration "
                f"brief records as its Odoo 15 home",
                entry["parent_id"] != v15_parent_id,
                actual_desc=f"parent_id={entry['parent_id']} "
                            f"({entry['parent_name']!r}); the Management "
                            f"section is #{v15_parent_id}")
            ctx.check("The entry's parent menu is Taxes & Fiscal "
                      "(account.account_reports_taxes_and_fiscal_menu)",
                      section["id"], entry["parent_id"])
            ctx.check_true(
                "The entry is active (an archived menuitem exists in "
                "ir.ui.menu but never appears in the Reporting tree)",
                entry["active"],
                actual_desc=f"active={entry['active']}, sequence="
                            f"{entry['sequence']}")
            evidence.append(("menu", "parent", entry["parent_name"]))
            evidence.append(("menu", "sequence", entry["sequence"]))

            # "Present" as the accountant means it: in the menu the client
            # paints. A row can exist in ir.ui.menu and still be filtered out
            # by _visible_menu_ids (ir_ui_menu.py:74-136).
            try:
                menus = rpc.call("ir.ui.menu", "load_menus", False) or {}
            except OdooRPCError as exc:
                menus = {}
                ctx.log(f"ir.ui.menu.load_menus could not be read ({exc}) — "
                        f"the visibility half of Expected line 1 falls back "
                        f"to the ir.ui.menu record above")
            if menus:
                siblings = _menu_children(menus, section["id"])
                visible_names = []
                for child_id in siblings:
                    node = (menus.get(child_id)
                            or menus.get(str(child_id)) or {})
                    visible_names.append(node.get("name") or f"#{child_id}")
                ctx.log(f"Taxes & Fiscal currently shows: "
                        f"{visible_names or '(nothing)'}")
                evidence.append(("menu", "Taxes & Fiscal children",
                                 "; ".join(visible_names)))
                ctx.check_true(
                    f"'{MENU_NAME}' is one of the entries the client actually "
                    f"paints under Taxes & Fiscal, not merely a row in "
                    f"ir.ui.menu (ir.ui.menu.load_menus)",
                    entry["id"] in siblings,
                    actual_desc=f"Taxes & Fiscal children returned by "
                                f"load_menus: {visible_names or '(none)'}")

        with ctx.step("Step 2 / Expected line 2: click it — the set-up screen "
                      "opens without error"):
            action_id = rpc.ref(ACTION_XMLID)
            ctx.check_true(
                f"The menu points at a window action ({ACTION_XMLID})",
                bool(action_id) and bool(entry["action"]),
                actual_desc=f"menu.action={entry['action']!r}, "
                            f"{ACTION_XMLID} -> #{action_id}")
            action_row = rpc.read("ir.actions.act_window", [action_id],
                                  ["name", "res_model", "view_mode",
                                   "target"])[0]
            ctx.log(f"action {action_row.get('name')!r} -> "
                    f"{action_row.get('res_model')!r} "
                    f"view_mode={action_row.get('view_mode')!r} "
                    f"target={action_row.get('target')!r}")
            # target='new' is why the label carries the ellipsis: the entry
            # opens a dialog, it does not render a report.
            ctx.check("Clicking the entry opens the 1099 set-up wizard "
                      "(the reason the label ends in an ellipsis)",
                      WIZARD_1099, action_row.get("res_model"))
            ctx.check("The action opens as a dialog (target='new'), which is "
                      "the set-up screen the workbook describes",
                      "new", action_row.get("target"))

            # "Opens without error" — the two things the client does on open.
            arch_ok, arch_note = False, ""
            try:
                views = rpc.call(WIZARD_1099, "get_views", [[False, "form"]],
                                 context=company_ctx(company)) or {}
                arch = ((views.get("views") or {}).get("form")
                        or {}).get("arch") or ""
                arch_ok = bool(arch)
                arch_note = f"form arch is {len(arch)} character(s) long"
            except OdooRPCError as exc:
                # An error here is a finding about the report, so it is
                # recorded as one — never allowed to escape as
                # AUTOMATION_ERROR (AUTOMATION_CONVENTIONS.md:69-71).
                arch_note = f"get_views raised: {exc}"
            ctx.check_true(
                "The wizard's form view loads (get_views returns an arch) — "
                "this is the call the web client makes when the dialog opens",
                arch_ok, actual_desc=arch_note)

            # What the dialog OFFERS before anyone touches it. Recorded now,
            # asserted in the final step so that a wrong default cannot stop
            # the report from being run and exported.
            try:
                offered = form_defaults(ctx, WIZARD_1099,
                                        ("start_date", "end_date"),
                                        context=company_ctx(company))
            except OdooRPCError as exc:
                offered = {}
                ctx.log(f"the dialog's defaults could not be read ({exc})")
            default_start = str(offered.get("start_date") or "")[:10]
            default_end = str(offered.get("end_date") or "")[:10]
            ctx.log(f"the dialog opens offering Start Date "
                    f"{default_start or '(none)'} and End Date "
                    f"{default_end or '(none)'}")

            wizard_id = None
            create_note = ""
            try:
                wizard_id = rpc.call(WIZARD_1099, "create", {},
                                     context=company_ctx(company))
                create_note = f"wizard record #{wizard_id} created"
            except OdooRPCError as exc:
                create_note = f"create raised: {exc}"
            ctx.check_true(
                "The set-up screen opens without error — the wizard record "
                "the dialog is backed by is created successfully",
                bool(wizard_id), actual_desc=create_note)
            ctx.log(f"{create_note} — l10n_us_1099.wizard is a TransientModel "
                    f"(…/generate_1099_wizard.py:10), so ir.autovacuum "
                    f"collects it; nothing else is created by this case")

        with ctx.step("Step 3 / Test Data: set the year to the last "
                      "completed calendar year"):
            # The server's own clock, not the runner's: create_date is written
            # by the database this report will be filed from. Deriving the
            # year from the runner's machine could disagree across a New Year
            # boundary or a timezone offset and would make the case
            # non-deterministic (AUTOMATION_CONVENTIONS.md rule 5).
            stamp = rpc.read(WIZARD_1099, [wizard_id],
                             ["create_date", "start_date", "end_date"])[0]
            server_today = str(stamp.get("create_date") or "")[:10]
            ctx.check_true(
                "The server's own date is readable, so 'the last completed "
                "calendar year' can be resolved against the database rather "
                "than against the runner's clock",
                len(server_today) == 10 and server_today[:4].isdigit(),
                actual_desc=f"wizard.create_date={stamp.get('create_date')!r}")
            target_year = int(server_today[:4]) - 1
            want_start, want_end = _iso_year_bounds(target_year)
            ctx.log(f"server date {server_today} -> the last completed "
                    f"calendar year is {target_year} "
                    f"({want_start} .. {want_end})")
            evidence.append(("period", "server date", server_today))
            evidence.append(("period", "reporting year", target_year))

            created_start = str(stamp.get("start_date") or "")[:10]
            created_end = str(stamp.get("end_date") or "")[:10]
            defaults_were_last_year = (created_start == want_start
                                       and created_end == want_end)
            evidence.append(("period", "default Start Date",
                             created_start or "(none)"))
            evidence.append(("period", "default End Date",
                             created_end or "(none)"))

            if not defaults_were_last_year:
                # Workbook step 3 says "set the year", so it is set — the
                # wizard has no 'year' field, only the two dates
                # (…/generate_1099_wizard.py:24-34), and writing a 'year' key
                # would be silently ignored.
                ctx.log(f"the wizard opened on {created_start}..{created_end}; "
                        f"setting the dates to {want_start}..{want_end} as "
                        f"workbook step 3 instructs")
                rpc.call(WIZARD_1099, "write", [wizard_id],
                         {"start_date": want_start, "end_date": want_end},
                         context=company_ctx(company))
            else:
                ctx.log("the wizard already opened on the last completed "
                        "calendar year, so step 3 needs no typing — the "
                        "dates are re-read below to confirm")

            row = rpc.read(WIZARD_1099, [wizard_id],
                           ["start_date", "end_date", "lines_to_export"])[0]
            ctx.check("Start Date is 1 January of the last completed calendar "
                      "year", want_start, str(row.get("start_date") or "")[:10])
            ctx.check("End Date is 31 December of the last completed calendar "
                      "year", want_end, str(row.get("end_date") or "")[:10])

            line_ids = [i for i in (row.get("lines_to_export") or [])
                        if isinstance(i, int)]
            ctx.log(f"the wizard pre-populated {len(line_ids)} journal item(s) "
                    f"for {target_year} — its compute keeps only USD, posted, "
                    f"asset_cash / liability_credit_card items whose partner "
                    f"carries a 1099 Box "
                    f"(…/generate_1099_wizard.py:56-76)")
            evidence.append(("run", "journal items selected", len(line_ids)))

            vendor_totals = []
            if line_ids:
                groups = rpc.read_group(
                    "account.move.line", [("id", "in", line_ids)],
                    ["balance:sum"], ["partner_id"])
                for group in groups:
                    # A payment to a vendor is a credit on the bank account,
                    # so balance is negative; action_generate flips the sign
                    # when it writes the row (…/generate_1099_wizard.py:104).
                    vendor_totals.append(
                        (m2o_name(group.get("partner_id")) or "(no contact)",
                         m2o_id(group.get("partner_id")),
                         int(group.get("__count") or 0),
                         money(-(group.get("balance") or 0.0))))
                vendor_totals.sort(key=lambda item: -item[3])
                for name, pid, count, total in vendor_totals:
                    ctx.log(f"    {name} (#{pid}): {count} item(s), "
                            f"{total:.2f} reportable")
                    evidence.append(("vendor", f"{name} (#{pid})",
                                     f"{count} item(s) / {total:.2f}"))
                zero_netting = [name for name, _pid, _c, total
                                in vendor_totals if money(total) == 0.0]
                if zero_netting:
                    observation(ctx,
                                f"{len(zero_netting)} vendor(s) net to exactly "
                                f"0.00 for {target_year} ({', '.join(zero_netting)}). "
                                f"action_generate only flushes a row when the "
                                f"running total is non-zero "
                                f"(…/generate_1099_wizard.py:146,159), so such "
                                f"a vendor is folded into the next vendor's "
                                f"row rather than printed. The row count is "
                                f"therefore not asserted against the vendor "
                                f"count")

        with ctx.step("Step 4 / Expected line 3: run it — the report produces "
                      "output for the year selected"):
            action = None
            run_note = ""
            try:
                # action_generate is PUBLIC (…/generate_1099_wizard.py:110).
                # _generate_row and _compute_lines_to_export are not, and are
                # never reached from here.
                action = rpc.call(WIZARD_1099, "action_generate", [wizard_id],
                                  context=company_ctx(company))
                run_note = f"action_generate returned {type(action).__name__}"
            except OdooRPCError as exc:
                run_note = f"action_generate raised: {exc}"
            ctx.check_true(
                "Pressing Generate runs the report without error",
                isinstance(action, dict) and bool(action),
                actual_desc=run_note)
            ctx.check("Generate hands the browser a download action",
                      "ir.actions.act_url", action.get("type"))

            download_url = str(action.get("url") or "")
            ctx.log(f"download action -> {download_url}")
            evidence.append(("export", "act_url", download_url))
            # Each fragment is checked separately so a failure names the one
            # that is wrong rather than dumping the whole URL twice.
            #
            # The filename fragment is what ties Expected line 3's "for the
            # YEAR SELECTED" to the artifact the accountant actually receives:
            # action_generate stamps the wizard's own start_date/end_date into
            # it with us_format "%m_%d_%Y"
            # (…/generate_1099_wizard.py:165, 169-170), so a file that downloads
            # under a different year's name is not the report that was asked
            # for, however non-empty its bytes are.
            want_filename = (f"filename=1099 report 01_01_{target_year} - "
                             f"12_31_{target_year}.csv")
            missing = [fragment for fragment in
                       (f"model={WIZARD_1099}", "field=generated_csv_file",
                        "download=true", f"id={wizard_id}", want_filename)
                       if fragment not in download_url]
            ctx.check("The download action points at this wizard's generated "
                      "CSV field and names the year that was selected "
                      "(…/generate_1099_wizard.py:166-172)",
                      [], missing)

            raw = rpc.read(WIZARD_1099, [wizard_id],
                           ["generated_csv_file"])[0].get(
                               "generated_csv_file") or ""
            try:
                payload = base64.b64decode(raw)
            except (ValueError, TypeError) as exc:
                payload = b""
                ctx.log(f"generated_csv_file is not decodable base64 "
                        f"({exc}) — treated as no output")
            ctx.check_true(
                "The report produced output for the year selected — the "
                "generated CSV file is non-empty",
                bool(payload),
                actual_desc=f"generated_csv_file decoded to {len(payload)} "
                            f"byte(s)")
            evidence.append(("export", "generated bytes", len(payload)))

        with ctx.step("Step 5 / Expected line 3: confirm the output has the "
                      "1099 columns, and that a vendor appears if the gallery "
                      "had reportable payments that year"):
            text = payload.decode("utf-8", "replace")
            report_rows = [row for row in csv.reader(text.splitlines()) if row]
            ctx.check_true(
                "The generated file is a CSV with at least a header row",
                bool(report_rows),
                actual_desc=f"{len(report_rows)} non-empty row(s) parsed from "
                            f"{len(payload)} byte(s)")
            header = report_rows[0]
            ctx.log(f"header carries {len(header)} column(s)")

            # The per-box tail is read live rather than from the shipped
            # data file: action_generate appends
            # l10n_us.1099_box.search([]).mapped('name')
            # (…/generate_1099_wizard.py:134-135), and the gallery may have
            # added or archived boxes.
            boxes = rpc.search_read("l10n_us.1099_box", [], ["name"],
                                    order="id")
            box_names = [str(box.get("name") or "") for box in boxes]
            ctx.log(f"{len(box_names)} 1099 box(es) defined: {box_names}")
            evidence.append(("report", "1099 boxes defined", len(box_names)))

            ctx.check("The export begins with the 18 fixed Payer/Payee "
                      "columns an e-filing service expects "
                      "(…/generate_1099_wizard.py:114-133)",
                      FIXED_HEADER, header[:len(FIXED_HEADER)])
            ctx.check("The export ends with one amount column per 1099 box "
                      "defined on this database "
                      "(…/generate_1099_wizard.py:134-135)",
                      box_names, header[len(FIXED_HEADER):])

            data_rows = report_rows[1:]
            vendor_names = [row[9] for row in data_rows
                            if len(row) > 9 and row[9]]
            ctx.log(f"the export lists {len(data_rows)} vendor row(s): "
                    f"{vendor_names or '(none)'}")
            evidence.append(("report", "vendor rows", len(data_rows)))

            if line_ids:
                # The gallery DID have reportable payments in the year, so the
                # workbook's condition is met and this is a hard expectation.
                ctx.check_true(
                    f"At least one vendor appears in the {target_year} export, "
                    f"as the workbook requires when the gallery had "
                    f"1099-reportable payments that year",
                    bool(data_rows),
                    actual_desc=f"{len(line_ids)} reportable journal item(s) "
                                f"were selected across "
                                f"{len(vendor_totals)} vendor(s), yet the CSV "
                                f"carries {len(data_rows)} data row(s)")
                blank_payee = [f"row {index + 2}" for index, row
                               in enumerate(data_rows)
                               if len(row) < 10 or not row[9]]
                ctx.check("Every vendor row in the export names its Payee "
                          "(a blank Payee Name cannot be e-filed)",
                          [], blank_payee)
            else:
                # The workbook's own If It Fails branch, verbatim in intent.
                ctx.log("no journal item met the wizard's selection for "
                        f"{target_year}, so the export is header-only")
                residual.append(
                    f"the {target_year} 1099 export ran and produced its "
                    f"header, but no vendor row: no posted USD journal item "
                    f"on a cash or credit-card account in {target_year} "
                    f"belongs to a contact carrying a 1099 Box "
                    f"(the wizard's own filter, "
                    f"…/generate_1099_wizard.py:56-66), although {boxed} "
                    f"contact(s) on this database DO carry a 1099 Box. "
                    f"The workbook's If It Fails says so explicitly: CHECK "
                    f"WITH NOVOBI whether the gallery had 1099-reportable "
                    f"payments in {target_year} before raising this. If it "
                    f"did, the likely causes are (a) the vendor payments were "
                    f"migrated as journal entries on an expense account "
                    f"rather than through a bank/cash account, or (b) the "
                    f"payments carry a currency other than USD.")

        with ctx.step("Step 6 / Expected line 4: confirm the output can be "
                      "exported or downloaded"):
            # The act_url alone only proves a link was offered. The file is
            # fetched over a real authenticated web session, which is what
            # the accountant's browser does.
            status, disposition, body, note = 0, "", b"", ""
            try:
                from framework.fg_common import http_session
                opener = http_session(ctx.env)
                # The generated filename contains spaces
                # (…/generate_1099_wizard.py:169), which urllib will not send
                # raw in a request line.
                full_url = ctx.env.base_url + download_url.replace(" ", "%20")
                with opener.open(full_url, timeout=180) as response:
                    status = response.status
                    disposition = response.headers.get(
                        "Content-Disposition", "")
                    body = response.read()
                note = (f"HTTP {status}, {len(body)} byte(s), "
                        f"Content-Disposition={disposition!r}")
            except urllib.error.HTTPError as exc:
                status, note = exc.code, f"HTTP {exc.code} from {download_url}"
            except (OSError, RuntimeError) as exc:
                note = f"{type(exc).__name__}: {exc}"
            ctx.log(f"download: {note}")
            evidence.append(("export", "download status", status))
            evidence.append(("export", "content-disposition", disposition))

            ctx.check("The generated file downloads over the URL the Generate "
                      "button hands the browser", 200, status)
            ctx.check_true(
                "The download arrives as a file attachment rather than as a "
                "page (Content-Disposition)",
                "attachment" in disposition.lower(),
                actual_desc=f"Content-Disposition={disposition!r}")
            ctx.check_true(
                "The downloaded bytes are the report that was generated, not "
                "a stale or empty file",
                bool(body) and body == payload,
                actual_desc=f"downloaded {len(body)} byte(s) vs "
                            f"{len(payload)} byte(s) held in "
                            f"generated_csv_file")

        with ctx.step("Workbook 'Why It Matters' / Test Data: the set-up "
                      "screen already offers the last completed calendar "
                      "year"):
            # Asserted last on purpose. A wrong default is worth reporting,
            # but it must not stop the case from proving the report runs and
            # exports — which is what the four Expected Result lines ask.
            want_start, want_end = _iso_year_bounds(target_year)
            ctx.check(
                "The 1099 set-up screen opens already showing 1 January of "
                "the last completed calendar year, so the accountant does "
                "not have to know the date to type "
                "(_default_start_date, …/generate_1099_wizard.py:14-17)",
                want_start, default_start)
            ctx.check(
                "The 1099 set-up screen opens already showing 31 December of "
                "the last completed calendar year "
                "(_default_end_date, …/generate_1099_wizard.py:19-22)",
                want_end, default_end)
    finally:
        with ctx.step("Evidence: write the run log and the redacted export"):
            path = ctx.artifacts_dir / EVIDENCE_CSV
            try:
                with path.open("w", newline="", encoding="utf-8") as handle:
                    writer = csv.writer(handle)
                    writer.writerow(EVIDENCE_HEADER)
                    writer.writerows(evidence)
                ctx.add_artifact(path, "log", EVIDENCE_CSV)
                ctx.log(f"wrote {len(evidence)} row(s) to {EVIDENCE_CSV}")
            except OSError as exc:
                ctx.log(f"could not write {EVIDENCE_CSV} ({exc}) — the "
                        f"figures above are still in this log")

            if report_rows:
                # The export itself is the deliverable, so it is attached —
                # but a Taxpayer Identification Number is a US federal
                # identifier and does not belong in a QA artifact. Both TIN
                # columns are replaced with 'set' / 'not set', which is all
                # the tick-off needs and the same treatment TC-INV-010 gives
                # a payment-provider credential.
                report_path = ctx.artifacts_dir / REPORT_CSV
                try:
                    head = report_rows[0]
                    tin_at = [index for index, column in enumerate(head)
                              if column in TIN_COLUMNS]
                    redacted = [list(head)]
                    for row in report_rows[1:]:
                        copy = list(row)
                        for index in tin_at:
                            if index < len(copy):
                                copy[index] = ("set" if copy[index]
                                               else "not set")
                        redacted.append(copy)
                    with report_path.open("w", newline="",
                                          encoding="utf-8") as handle:
                        csv.writer(handle).writerows(redacted)
                    ctx.add_artifact(report_path, "log", REPORT_CSV)
                    ctx.log(f"wrote the generated 1099 export "
                            f"({len(redacted) - 1} vendor row(s)) to "
                            f"{REPORT_CSV}; the two TIN columns are recorded "
                            f"as 'set'/'not set' rather than as values")
                except (OSError, IndexError, TypeError) as exc:
                    ctx.log(f"could not write {REPORT_CSV} ({exc}) — the "
                            f"column list and row count are still in this log")

            for note in residual:
                residual_manual_step(ctx, note)
            residual_manual_step(
                ctx,
                "the workbook's State After The Test is 'Nothing changed. Do "
                "not file anything.' — the CSV attached to this run was "
                "generated for verification only and must not be handed to an "
                "e-filing service.")

            ctx.log(f"No {MARK}-marked business record was created by this "
                    f"case: no invoice, no payment, no contact, no product. "
                    f"Fabricating a 1099 payment would leave a posted entry "
                    f"in the gallery's books and put a test fixture inside a "
                    f"real IRS filing. The only record created is one "
                    f"l10n_us_1099.wizard TransientModel row, which "
                    f"ir.autovacuum collects.")
            cleanup(ctx, created)
