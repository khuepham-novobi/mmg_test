"""FG-16 — TC-STU-006 and TC-STU-012: what Odoo Studio left behind.

Implements the CLIENT MANUAL TESTING GUIDELINE
``MMG_v19_Client_Manual_Testing_Guideline_FG15-FG20_v1.0.xlsx`` / sheet
``Testing Guideline``, cases TC-STU-006 (P0) and TC-STU-012 (P2).

Everything the gallery customised in the old system was customised *outside
program code* — Studio fields on ``res.partner`` and ``product.template``,
and the view edits that put them on screen. None of it is in a module anyone
reviewed, which is why TC-STU-006 is the workbook's highest-value case and
why its Expected Result ends *"Any single screen failing to open is a FAIL
for this case, however well the others behaved."*

Ten screens, opened through the menus that lead to them
-------------------------------------------------------
:func:`open_screen` walks ``ir.ui.menu.load_menus`` — the call the web
client makes to build the menu bar — rather than resolving XML ids. That
distinction earns its keep on screen (i): ``Inventory > Operations >
Adjustments > Physical Inventory`` is not served to this user, and a test
written against ``stock.action_view_quants`` would have reported the case
green while the tester could not reach the screen at all.

TC-STU-012 is a round trip, not a field list
---------------------------------------------
The case's point is not that six columns survived the upgrade — a column
with no label, or one that silently drops what you type, survives just as
well. So all six are written, read back, changed, read back again, and
checked against the labels the workbook prints.
"""
from __future__ import annotations

from adapters.base import OdooRPCError
from framework.registry import test_case

from .common import (CONTACT_FIELDS, CONTACT_TABS, CONTACT_VALUES, MARK,
                     MODULE, MODULE_STUDIO, ORDER, ORDER_LEGAL_DATE, PARTNER,
                     PRODUCT_TABS, STUDIO_SCREENS, WORKFLOW, WORKFLOW_NAME,
                     archived, field_attrs, finding, leftovers, make_partner,
                     manual, observation, open_screen, page_titles,
                     require_studio, sweep, trace)

#: Step 3's examples of "the extra gallery columns", per screen family.
EXTRA_COLUMNS = {
    "Contacts > Contacts": ("x_type",),
    "Sales > Orders > Orders": (ORDER_LEGAL_DATE,),
    "Sales > Orders > Quotations": (ORDER_LEGAL_DATE,),
    "Inventory > Products > Products": ("default_code",),
    "Sales > Products > Products": ("default_code",),
}


@test_case(
    id="TEST-FG16-STU-006",
    name="Every screen customised in the old system still opens on Odoo 19",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module=MODULE_STUDIO,
    priority="P0",
    kind="API",
    order=1602,
    description="All ten screens of step 1 are opened through the menus the "
                "workbook names, and every view each action pins is built — "
                "which is what an 'Invalid view definition' pop-up actually "
                "is. The gallery's extra columns are checked on the lists "
                "that had them, its own tabs on the product and contact "
                "forms, and a trivial edit is saved on a product, a "
                "contact, an order and an invoice.",
    traceability=trace("TC-STU-006"))
def test_stu_006(ctx):
    rpc = require_studio(ctx)
    opened = {}

    with ctx.step("Steps 1-2: each of the ten screens opens, and every view "
                  "behind it builds"):
        failures = []
        for letter, path, _mode in STUDIO_SCREENS:
            result = open_screen(ctx, path)
            opened[path] = result
            if result["error"]:
                failures.append(f"({letter}) {path} — {result['error']}")
                ctx.log(f"  {letter}. FAILED  {path}")
                ctx.log(f"        {result['error']}")
            else:
                target = ((result.get("action") or {}).get("res_model")
                          or result.get("kind") or "?")
                ctx.log(f"  {letter}. ok      {path} -> {target} "
                        f"[{', '.join(result['views']) or 'no view to build'}]")

        hidden = [p for p, r in opened.items() if r.get("hidden")]
        if hidden:
            for path in hidden:
                row = opened[path]
                finding(ctx,
                        f"'{path}' cannot be reached. The menu EXISTS and is "
                        f"active; what hides it is '{row.get('gated_at')}', "
                        f"gated on {row.get('group_names')}, so "
                        f"load_menus does not serve it. Stock Odoo 19 "
                        f"declares this branch with no groups attribute at "
                        f"all (addons/stock/views/stock_menu_views.xml:7-10) "
                        f"and no module in mmg_19-custom touches it, so the "
                        f"restriction came across in the restored database "
                        f"rather than from code. Consequence: Transfers, "
                        f"Deliveries, Receipts, Adjustments and Scrap are "
                        f"all invisible under Inventory unless developer "
                        f"mode is on — which is also the navigation FG-12's "
                        f"TC-FUL-013 tells the tester to use.")

        ctx.check("Every screen the workbook names opens — 'any single "
                  "screen failing to open is a FAIL for this case, however "
                  "well the others behaved'", [], failures)

    with ctx.step("Step 3: the gallery's extra columns are on the lists that "
                  "had them"):
        missing = []
        for path, columns in EXTRA_COLUMNS.items():
            arch = (opened.get(path) or {}).get("views", {}).get("list", "")
            if not arch:
                continue
            for column in columns:
                if not field_attrs(arch, column):
                    missing.append(f"{path}: {column}")
        ctx.check("Every extra gallery column the workbook names is on its "
                  "list", [], missing)

    with ctx.step("Step 4: the gallery's own tabs are on the product and "
                  "contact forms"):
        product_arch = rpc.call("product.template", "get_view",
                                view_type="form")["arch"]
        tabs = page_titles(product_arch)
        ctx.log(f"product tabs: {tabs}")
        ctx.check("The product form carries the gallery's three tabs", [],
                  [t for t in PRODUCT_TABS if t not in tabs])

        partner_arch = rpc.call(PARTNER, "get_view", view_type="form")["arch"]
        partner_tabs = page_titles(partner_arch)
        ctx.log(f"contact tabs: {partner_tabs}")
        ctx.check("The contact form carries the 'Notes' tab", [],
                  [t for t in CONTACT_TABS if t not in partner_tabs])

    with ctx.step("Step 5: a trivial edit saves on a product, a contact, an "
                  "order and an invoice"):
        # "Trivial" as the workbook defines it: write a value back onto
        # itself. Nothing is really changed, which is what makes it safe to
        # do on the gallery's own records — and the save is the point.
        refused = []
        for model, field in (("product.template", "description_sale"),
                             (PARTNER, "comment"),
                             (ORDER, "note"),
                             ("account.move", "narration")):
            rows = rpc.search_read(model, [], ["id", field], limit=1,
                                   order="id desc")
            if not rows:
                ctx.log(f"  {model}: no record to edit — skipped")
                continue
            row = rows[0]
            try:
                rpc.write(model, [row["id"]], {field: row[field] or False})
                ctx.log(f"  {model}#{row['id']}: saved")
            except OdooRPCError as exc:
                refused.append(f"{model}#{row['id']}: {exc}")
        ctx.check("All four saves complete", [], refused)

    manual(ctx,
           "TC-STU-006 step 6 — printing one sales order and one customer "
           "invoice to PDF and confirming both open and are not blank. The "
           "reports are QWeb templates and reading a PDF is not something "
           "this platform does; two prints close it. Note also that the "
           "workbook's Expected Result mentions no browser console, so "
           "nothing here reads one — TC-UIX-011 and TC-SMK-003 are the "
           "cases that ask for that, and both need a real browser.")


@test_case(
    id="TEST-FG16-STU-012",
    name="The gallery's extra contact fields survived and still work",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module=MODULE_STUDIO,
    priority="P2",
    kind="API",
    order=1603,
    description="All six Studio contact fields exist with exactly the labels "
                "the workbook prints, are on the contact form, take the "
                "workbook's own Test Data and read it back unchanged, accept "
                "a second edit, and are available as list columns. A contact "
                "carried over from the old system is checked for its "
                "original Customer Type. The contact this test creates is "
                "removed afterwards.",
    traceability=trace("TC-STU-012"))
def test_stu_012(ctx):
    rpc = require_studio(ctx)
    sweep(ctx)

    try:
        with ctx.step("Steps 2-5: all six fields exist, with the labels the "
                      "workbook reads off the form"):
            declared = rpc.call(PARTNER, "fields_get", list(CONTACT_FIELDS),
                                attributes=["string", "type"])
            missing = [n for n in CONTACT_FIELDS if n not in declared]
            ctx.check("Every one of the gallery's six contact fields "
                      "survived the upgrade", [], missing)
            ctx.check("…each with exactly the label the workbook prints",
                      CONTACT_FIELDS,
                      {n: declared[n]["string"] for n in CONTACT_FIELDS
                       if n in declared})

            arch = rpc.call(PARTNER, "get_view", view_type="form")["arch"]
            off_form = [n for n in CONTACT_FIELDS if not field_attrs(arch, n)]
            ctx.check("…and all six are on the contact form, not merely in "
                      "the database", [], off_form)

            tabs = page_titles(arch)
            ctx.check_true("'Alert Notes' lives on the Notes tab the "
                           "workbook sends the tester to",
                           "Notes" in tabs,
                           actual_desc=f"form tabs: {tabs}")

        with ctx.step("Steps 1-6: the workbook's own Test Data goes in and "
                      "reads back exactly as typed"):
            partner_id = make_partner(ctx, "UAT Contact FG16",
                                      company_type="person",
                                      **CONTACT_VALUES)
            read_back = rpc.read(PARTNER, [partner_id],
                                 list(CONTACT_VALUES))[0]
            ctx.check("All six values read back exactly as typed",
                      CONTACT_VALUES,
                      {k: read_back[k] for k in CONTACT_VALUES})

        with ctx.step("Step 7: a second edit also sticks"):
            changed = "Gallery UAT — amended"
            rpc.write(PARTNER, [partner_id], {"x_type": changed})
            ctx.check("The changed value saved", changed,
                      rpc.read(PARTNER, [partner_id],
                               ["x_type"])[0]["x_type"])
            ctx.check_true(
                "…and the other five are untouched by it",
                all(rpc.read(PARTNER, [partner_id], [k])[0][k] == v
                    for k, v in CONTACT_VALUES.items() if k != "x_type"),
                actual_desc="five unchanged fields verified")

        with ctx.step("Step 8: Customer Type and Main Phone are available as "
                      "columns on the contacts list"):
            list_arch = rpc.call(PARTNER, "get_view", view_type="list")["arch"]
            for name in ("x_type", "x_main_phone", "x_email_two"):
                tag = field_attrs(list_arch, name)
                if tag:
                    ctx.log(f"  {name}: on the list — {tag[:110]}")
                else:
                    observation(ctx,
                                f"{name} is not a column on the contacts "
                                f"list view. The workbook allows this: step "
                                f"8 says to add it with the column-picker "
                                f"if it is not shown, which needs the field "
                                f"to be optional-visible rather than "
                                f"present.")
            ctx.check_true(
                "The two the workbook requires outright — Customer Type and "
                "Main Phone — are on the contacts list",
                bool(field_attrs(list_arch, "x_type"))
                and bool(field_attrs(list_arch, "x_main_phone")),
                actual_desc=f"x_type={bool(field_attrs(list_arch, 'x_type'))} "
                            f"x_main_phone="
                            f"{bool(field_attrs(list_arch, 'x_main_phone'))}")

        with ctx.step("Step 9: a contact carried over from the old system "
                      "still shows its original Customer Type"):
            rows = rpc.search_read(
                PARTNER,
                [("x_type", "!=", False), ("name", "not like", MARK)],
                ["name", "x_type"], limit=5, order="id")
            if not rows:
                observation(ctx,
                            "no contact on this database carries a Customer "
                            "Type, so step 9 has nothing to read. That is "
                            "itself worth a look: the field survived but "
                            "its data may not have.")
            ctx.check_true(
                "At least one contact from the old system still carries its "
                "Customer Type",
                bool(rows),
                actual_desc=f"{len(rows)} sampled: "
                            + "; ".join(f"{r['name'][:28]}={r['x_type']!r}"
                                        for r in rows))
            total = rpc.call(PARTNER, "search_count",
                             [("x_type", "!=", False)])
            ctx.log(f"{total} contacts on this database carry a Customer "
                    f"Type")

    finally:
        with ctx.step("Cleanup: the contact this test created is removed"):
            sweep(ctx)
            kept = archived(ctx)
            if kept:
                ctx.log(f"archived rather than deleted: {kept}")
            ctx.check("No LIVE record this test created is left on the "
                      "database", 0, leftovers(ctx))
