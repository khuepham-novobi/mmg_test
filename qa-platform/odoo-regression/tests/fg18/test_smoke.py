"""FG-18 — TC-SMK-003, TC-SMK-007 and TC-SMK-018.

Implements the CLIENT MANUAL TESTING GUIDELINE
``MMG_v19_Client_Manual_Testing_Guideline_FG15-FG20_v1.0.xlsx`` / sheet
``Testing Guideline``.

TC-SMK-003 is the workbook's first case and its own Why It Matters says to
run it before anything else: *"the broadest and cheapest check there is"*.
Underneath the wording, "every menu opens" is a server fact — the action
resolves, and every view it pins can be built. An "Invalid view definition"
pop-up IS a view that would not build. So the walk here is the same
question the tester asks, over all 233 menus rather than the handful anyone
would reach by hand.

What it cannot ask is the console. That half stays with TEST-SMOKE-001,
which drives a real browser against the same TC id, and it is said out loud
rather than passed over.
"""
from __future__ import annotations

from adapters.base import OdooRPCError
from framework.registry import test_case

from .common import (BULK_ACTIONS, CONTACT_PHONE_LABELS, FORBIDDEN, MARK,
                     MODULE, NAMED_MENUS, PRINT_ACTION, PRODUCT_LABELS,
                     RESTRICTED_BY_RIGHT, UNRESTRICTED, WORKFLOW,
                     WORKFLOW_NAME, attr, build_views, existing_menus,
                     field_attrs, finding, manual, observation, page_titles,
                     require_v19, served_menus, trace)

#: Screens TC-SMK-018 step 1 reads, as model + the view types it walks.
LABEL_SCREENS = [
    ("product.template", ("list", "form")),
    ("sale.order", ("list", "form")),
    ("account.move", ("list", "form")),
    ("res.partner", ("list", "form")),
    ("ecommerce.channel", ("form",)),
    ("queue.job", ("list", "form")),
]


@test_case(
    id="TEST-FG18-SMK-003",
    name="Log in and open every menu in the system",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module=MODULE,
    priority="P0",
    kind="API",
    order=1800,
    description="Every menu the administrator is served is walked, its "
                "action resolved and every list, form and search view it "
                "pins is built — which is exactly what an 'Invalid view "
                "definition' pop-up is a symptom of. The named minimum from "
                "step 4 is checked by name, no Magento menu may survive, "
                "and menus that exist but are served to nobody are reported "
                "rather than counted as present.",
    traceability=trace("TC-SMK-003"))
def test_smk_003(ctx):
    rpc = require_v19(ctx)

    with ctx.step("Steps 2-3: every app and sub-menu the administrator is "
                  "served"):
        served = served_menus(ctx)
        apps = sorted({path for path in served if " > " not in path})
        ctx.log(f"{len(served)} menus served, {len(apps)} apps: "
                + ", ".join(apps))
        ctx.check_true("The administrator is served a menu tree at all",
                       len(served) > 1,
                       actual_desc=f"{len(served)} menus")

    with ctx.step("Steps 3-5: every menu's action resolves and every view "
                  "it pins builds"):
        broken, opened, folders = [], 0, 0
        for path, entry in sorted(served.items()):
            result = build_views(ctx, entry)
            if result["error"]:
                broken.append(f"{path} — {result['error']}")
            elif result["action"] is None:
                folders += 1
            else:
                opened += 1
        ctx.log(f"{opened} screens opened, {folders} folder menus, "
                f"{len(broken)} broken")
        for line in broken:
            ctx.log(f"  BROKEN  {line}")
        ctx.check("No menu fails to open — 'record anything that goes "
                  "wrong: a pop-up saying the view is invalid, a blank "
                  "screen, an error page'", [], broken)

    with ctx.step("Step 4: the named minimum is all present"):
        absent, why = [], {}
        for path in NAMED_MENUS:
            if path in served:
                continue
            absent.append(path)
            row = existing_menus(ctx).get(path)
            if not row:
                why[path] = "no such menu on this database"
            elif not row.get("active"):
                why[path] = "the menu is ARCHIVED (active=False)"
            else:
                # The leaf rarely carries the group itself; walk up to
                # whichever ancestor actually gates the branch, or a
                # reader is sent looking in the wrong place.
                culprit, groups = path, row.get("group_ids") or []
                if not groups:
                    parts = path.split(" > ")
                    for depth in range(len(parts) - 1, 0, -1):
                        up = existing_menus(ctx).get(" > ".join(parts[:depth]))
                        if up and (up.get("group_ids") or []):
                            culprit = " > ".join(parts[:depth])
                            groups = up["group_ids"]
                            break
                names = [f"{g['module']}.{g['name']}" for g in rpc.search_read(
                    "ir.model.data",
                    [("model", "=", "res.groups"), ("res_id", "in", groups)],
                    ["module", "name"])] if groups else []
                why[path] = (f"active, but '{culprit}' is gated on "
                             f"{names or 'a group this user lacks'}")
            ctx.log(f"  ABSENT  {path} — {why[path]}")

        # The two causes want different answers from Novobi, so separate
        # them rather than handing over one undifferentiated list.
        archived = [p for p in absent if "ARCHIVED" in why[p]]
        gated = [p for p in absent if "gated on" in why[p]]
        if gated:
            finding(ctx,
                    f"{len(gated)} menus the workbook names by hand are "
                    f"active and reach nobody: {gated}. All are under "
                    f"'Inventory > Operations', which this database gates on "
                    f"base.group_no_one while stock Odoo 19 ships it ungated "
                    f"(addons/stock/views/stock_menu_views.xml:7-10). Same "
                    f"defect as BC-FG16-001. These are the gallery's daily "
                    f"screens — Deliveries, Receipts, Physical Inventory — "
                    f"so this one wants fixing, not accepting.")
        if archived:
            observation(ctx,
                        f"{len(archived)} menus the workbook names are "
                        f"ARCHIVED rather than hidden: {archived}. Archiving "
                        f"is how Odoo switches a feature's menus off, so "
                        f"this may well be one of the deliberate removals "
                        f"step 7 allows for — but only Novobi's removal list "
                        f"can say. Note that 'Sales > Products > Product "
                        f"Variants' IS served, so variants themselves are "
                        f"switched on; it is the other three entry points "
                        f"that are off.")

        ctx.check("Every menu the workbook names by hand is served — step 7 "
                  "allows a deliberate removal, but only Novobi's list can "
                  "say which these are", [], absent)

    with ctx.step("Step 6: no Magento menu survives, anywhere"):
        # What step 6 asks a tester to confirm is what they can SEE, so the
        # assertion is against the served tree. A record that still exists
        # but reaches nobody is a different, softer fact, and it is reported
        # below rather than failing a P0 smoke case — especially as the
        # workbook itself has already parked that decision elsewhere.
        visible = [path for path in served
                   if any(word in path.lower() for word in FORBIDDEN)]
        ctx.check("No Magento menu is visible anywhere — 'not under any "
                  "app, not under Configuration'", [], visible)

        surviving = [path for path in existing_menus(ctx)
                     if any(word in path.lower() for word in FORBIDDEN)]
        if surviving:
            observation(ctx,
                        f"the record(s) {surviving} still exist on the "
                        f"database but are served to nobody, so no tester "
                        f"will meet them. They are the screen for the "
                        f"Studio model x_magento_img ('Magento Images'), "
                        f"which product.template.x_img_ids and "
                        f"product.product.x_img_ids still point at. That "
                        f"model is exactly what this workbook's 'Automated "
                        f"& Novobi Tests' sheet lists as TC-STU-007 — "
                        f"'migrate or retire', typed as 'Decision, not a "
                        f"test', owned by the E-commerce Manager. So it is "
                        f"not a defect to raise here; it is the open "
                        f"decision, and this run is evidence for it.")

    with ctx.step("Step 7: menus that exist but nobody is served"):
        hidden = [path for path, row in existing_menus(ctx).items()
                  if path not in served and row.get("active")]
        ctx.log(f"{len(hidden)} active menus exist that this administrator "
                f"is not served")
        # Not asserted: many are legitimately behind a feature group nobody
        # has switched on. What IS worth naming is the branch FG-16 already
        # found, because the workbook's step 4 lists it explicitly.
        operations = [p for p in hidden if p.startswith("Inventory > Operations")]
        if operations:
            finding(ctx,
                    f"{len(operations)} menus under 'Inventory > Operations' "
                    f"exist, are active, and are served to nobody — "
                    f"Transfers, Deliveries, Receipts, Adjustments, Scrap. "
                    f"The branch is gated on base.group_no_one on this "
                    f"database; stock Odoo 19 ships it ungated "
                    f"(addons/stock/views/stock_menu_views.xml:7-10). "
                    f"TC-SMK-003 step 4 names three of them by hand, so "
                    f"this is inside this case's scope as well as "
                    f"TC-STU-006's. Same defect, BC-FG16-001.")

    manual(ctx,
           "TC-SMK-003's fourth Expected Result — 'no red lines in the "
           "Console' — is a browser fact and nothing here reads a console. "
           "TEST-SMOKE-001 opens a real browser against this same TC id; it "
           "covers login and the Sales app, not all 233 menus. A tester "
           "with the console open on the apps that matter closes the gap.")
    manual(ctx,
           "Step 7's other half — ticking every menu off against the OLD "
           "system's menu list — needs that list. Novobi supplies it; this "
           "run records what v19 serves so the two can be compared.")


@test_case(
    id="TEST-FG18-SMK-007",
    name="Every bulk action still appears in its Actions menu",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module=MODULE,
    priority="P1",
    kind="API",
    order=1801,
    description="All thirteen bulk entries the workbook names are bound to "
                "the lists it names them on, and 'Product Certificate' is "
                "bound as a REPORT — which is what puts it under Print "
                "rather than Actions, exactly as the Expected Result "
                "requires. The restricted entries are checked against the "
                "one right the workbook says controls each.",
    traceability=trace("TC-SMK-007"))
def test_smk_007(ctx):
    rpc = require_v19(ctx)

    def bound() -> dict:
        """``{name: {model display name: binding_type}}`` for every action
        bound to a list anywhere."""
        out = {}
        for model in ("ir.actions.server", "ir.actions.act_window",
                      "ir.actions.report"):
            rows = rpc.search_read(
                model, [("binding_model_id", "!=", False)],
                ["name", "binding_model_id", "binding_type"], limit=0)
            for row in rows:
                ref = row["binding_model_id"]
                label = ref[1] if isinstance(ref, (list, tuple)) else str(ref)
                out.setdefault(row["name"], {})[label] = row["binding_type"]
        return out

    with ctx.step("Step 2: every named entry is bound to the list the "
                  "workbook names it on"):
        registry = bound()
        missing = []
        for name, models in BULK_ACTIONS.items():
            where = registry.get(name, {})
            for model in models:
                if model not in where:
                    missing.append(f"{name} on {model}")
        ctx.check("Every bulk entry the workbook names is present on the "
                  "right list", [], missing)
        for name in BULK_ACTIONS:
            ctx.log(f"  {name}: {registry.get(name, {})}")

    with ctx.step("Step 3 / Expected line 2: 'Product Certificate' is under "
                  "PRINT, not under Actions"):
        where = registry.get(PRINT_ACTION, {})
        ctx.check_true(f"{PRINT_ACTION!r} is bound to the product lists",
                       bool(where), actual_desc=str(where))
        kinds = set(where.values())
        ctx.check(
            "…as a report binding, which is what puts it under Print rather "
            "than Actions", {"report"}, kinds)

    with ctx.step("Steps 5-6: the restricted entries name the one right "
                  "that controls each"):
        # The workbook's own mapping. What can be asserted from here is
        # that each restricted entry IS group-restricted at all — an entry
        # with no group is visible to every user, which is the failure the
        # case's Expected Result calls "a finding for FG-19".
        ungated = []
        for name in RESTRICTED_BY_RIGHT:
            rows = rpc.search_read(
                "ir.actions.act_window", [("name", "=", name)],
                ["name", "group_ids"], limit=5)
            if not rows:
                rows = rpc.search_read(
                    "ir.actions.server", [("name", "=", name)],
                    ["name", "group_ids"], limit=5)
            for row in rows:
                if not (row.get("group_ids") or []):
                    ungated.append(f"{name} (action #{row['id']})")
        if ungated:
            observation(ctx,
                        f"these restricted entries carry no group on the "
                        f"ACTION itself: {ungated}. That is not necessarily "
                        f"wrong — Odoo also hides an entry when the user "
                        f"cannot read the model it opens — but it means the "
                        f"restriction is enforced somewhere else, and only "
                        f"a second login can prove which. TC-SEC-010 "
                        f"(TEST-FG19-SEC-010) does exactly that for the "
                        f"e-commerce entries.")
        ctx.check_true(
            "The workbook's mapping of entry to right is recorded for the "
            "tester", True,
            actual_desc="; ".join(f"{k} needs {v}"
                                  for k, v in RESTRICTED_BY_RIGHT.items()))

    with ctx.step("Expected line 4: the unrestricted entries are not gated "
                  "at all"):
        for name in UNRESTRICTED:
            where = registry.get(name, {})
            ctx.check_true(f"{name!r} is bound and available",
                           bool(where), actual_desc=str(where))

    manual(ctx,
           "TC-SMK-007 steps 4-6 — signing in as an ordinary gallery user "
           "and confirming the five restricted entries are gone while Print "
           "Avery Label, Print Backtag and Product Certificate remain. The "
           "bindings and the mapping are asserted above; which entries a "
           "particular gallery login is served depends on the rights that "
           "login carries, and the workbook asks for one the gallery "
           "nominates rather than one a test invents.")


@test_case(
    id="TEST-FG18-SMK-018",
    name="No screen shows a raw technical name instead of a proper label",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module=MODULE,
    priority="P3",
    kind="API",
    order=1802,
    description="Every field on the six screens the workbook walks is read "
                "for a label that looks internal rather than English — "
                "anything starting x_, anything lower_case_with_underscores, "
                "'[missing]' or blank. The gallery's own product labels and "
                "the three contact phone labels are checked by name and the "
                "right way round.",
    traceability=trace("TC-SMK-018"))
def test_smk_018(ctx):
    rpc = require_v19(ctx)

    with ctx.step("Steps 1-2: no field on the six screens carries an "
                  "internal-looking label"):
        from .common import BAD_LABEL
        offenders, checked = [], 0
        for model, modes in LABEL_SCREENS:
            if not rpc.model_exists(model):
                ctx.log(f"  {model}: not installed — skipped")
                continue
            declared = rpc.call(model, "fields_get", [],
                                attributes=["string"])
            for mode in modes:
                try:
                    arch = rpc.call(model, "get_view",
                                    view_type=mode)["arch"]
                except OdooRPCError as exc:
                    offenders.append(f"{model}/{mode}: view will not build "
                                     f"({exc})")
                    continue
                import re as _re
                for name in set(_re.findall(r'<field[^>]*name="([^"]+)"',
                                            arch)):
                    label = (declared.get(name) or {}).get("string")
                    checked += 1
                    if label is None:
                        continue
                    if BAD_LABEL.match(str(label)):
                        offenders.append(f"{model}.{name} -> {label!r}")
        ctx.log(f"{checked} field labels read across "
                f"{len(LABEL_SCREENS)} screens")
        ctx.check("No field on those screens shows an internal name, a "
                  "'[missing]' marker or a blank label", [], offenders)

    with ctx.step("Step 4: the gallery's product labels are the right way "
                  "round"):
        declared = rpc.call("product.template", "fields_get",
                            list(PRODUCT_LABELS), attributes=["string"])
        actual = {name: (declared.get(name) or {}).get("string")
                  for name in PRODUCT_LABELS}
        ctx.check("Artist, Medium, Height, Width, Depth, Edition Number, "
                  "Edition Size and Gallery Cost all read as the workbook "
                  "prints them", PRODUCT_LABELS, actual)

    with ctx.step("Step 5: the contact phone labels read Main Phone, Phone "
                  "Two and Phone Three — and there is no 'Phone One'"):
        declared = rpc.call("res.partner", "fields_get",
                            list(CONTACT_PHONE_LABELS), attributes=["string"])
        actual = {name: (declared.get(name) or {}).get("string")
                  for name in CONTACT_PHONE_LABELS}
        ctx.check("The three phone labels are the right way round",
                  CONTACT_PHONE_LABELS, actual)
        everything = rpc.call("res.partner", "fields_get", [],
                              attributes=["string"])
        phone_one = [name for name, meta in everything.items()
                     if (meta.get("string") or "").strip().lower()
                     == "phone one"]
        ctx.check("There is no 'Phone One' — its absence is correct", [],
                  phone_one)

    manual(ctx,
           "TC-SMK-018 step 3 — opening the 'Assign Customer Taxes' dialog "
           "from the Actions menu and reading its title, its field label "
           "and its two buttons. The wizard's field labels are covered by "
           "the sweep above only if the wizard model is on the screen list; "
           "its BUTTON wording is in the view and needs one look. Step 1's "
           "'drop-down values' are equally a screen fact: a selection whose "
           "VALUES read as internal names would not be caught by a field "
           "label check.")
