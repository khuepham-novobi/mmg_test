"""FG-08 — TC-CHN-001: the Shopify store's settings all came across.

Implements row 44.0 (P0, "Store setup") of the CLIENT MANUAL TESTING
GUIDELINE ``MMG_v19_Client_Manual_Testing_Guideline_FG05-FG14_v1.0.xlsx`` /
sheet ``Testing Guideline``.

The workbook's framing: *"Everything the connector does — which orders it
pulls, which warehouse it reports, which journal a payment lands in — comes
from this one screen. A setting that reverted to a default will not raise an
error; it will just start behaving differently."* Its *Why It Matters* opens
with **READ THIS FIRST** and says to run this before any other FG-08,
FG-09, FG-10, FG-11 or FG-12 case. The workbook's own *Order of Testing*
puts it in step 2.0, behind **GATE 2**.

What this case actually is, and what the platform can do about it
-----------------------------------------------------------------
It is a four-tab, field-by-field comparison against a printout of the old
system. The platform does not hold the printout, and there is no v15
database on this workstation to generate one from, so the comparison itself
stays a human step. What the platform does instead:

1. **Captures the whole inventory** — every value the workbook's steps 2-7
   name, with the tab it sits on, its technical field name and its resolved
   display value (labels, not raw ids) — into
   ``TC-CHN-001-store-settings-inventory.csv``, plus a row-counts-only
   companion. The tick-off becomes a two-column read instead of a
   screen-by-screen hunt across four tabs.
2. **Asserts the structural claims the workbook makes about the screen**,
   which need no printout: the three notebook tabs exist with the exact
   strings the workbook names, every field it names is on the tab it says,
   ``Name`` is read-only on a saved store, ``Platform`` is hidden on a
   saved store, and ``Access Token`` is masked and not empty.
3. **Asserts the failure shapes the workbook's *If It Fails* names**, which
   also need no printout: a configured many2one that points at a record
   that is archived or gone (its "reverted to a default … will silently
   mis-route real orders" shape), and a sub-table that the module's own
   constraints require to be non-empty but which came across empty (its
   "a LIST with fewer rows … means rules were lost" shape).
4. **Asserts Expected Result line 4 exactly as written.** It fails — see
   below.
5. **Reports every gap in one pass.** Each check records its finding and the
   case carries on; one hard assertion at the end decides the verdict — see
   *Why the checks collect* below.

Expected Result line 4 — the Salesperson field
----------------------------------------------
    *"Salesperson is present on the Order Configuration tab and carries the
    expected user. (Novobi restored this field during the upgrade; it was
    missing from the screen in an earlier build.)"*

Half of that is true. ``ecommerce.channel.user_id`` (string ``Salesperson``)
**was** restored on the model, deliberately and with a note, under
``FG11-D2 / BC-012`` (``multichannel_order/models/ecommerce_channel.py:
44-61``) — including a ``BC-029`` fix to its domain, because v19 renamed
``res.users.groups_id`` to ``group_ids``.

But it was restored on the **model only**. There is no
``<field name="user_id"/>`` in any ``ecommerce.channel`` view on
``staging_19``, where v15 carried one on exactly the tab the workbook names
(``novobi-omni-addons/multichannel_order/views/
omnichannel_dashboard_views.xml:71``, inside ``<group name="top_left">`` of
``<page name="order_configuration_page">``). So the field is not on the
Order Configuration tab, cannot be read or set from the screen, and on the
MMG restore it is empty.

``AUTOMATION_CONVENTIONS`` rule 2 makes this an assertion, not a note: the
workbook's expected result is implemented as written, never weakened and
never inverted. This test therefore **fails on the shipped build**, and the
log names both source locations so the fix is a one-line view change rather
than an investigation.

Why the checks collect rather than abort
----------------------------------------
That failure is real, and ``ctx.check`` raises. Until this pass the case
therefore stopped at Expected Result line 4 — which sits ahead of the
checks the workbook's own *If It Fails* column asks for, so on every
recorded execution these had never run at all: the step-8 guard proof, "no
configured many2one points at an archived or deleted record" across the 18
routing fields, "no required sub-table came across empty", and the
dropped-v15-fields assertion. A known, already-triaged product defect was
hiding the P0 migration checks behind it.

So every check goes through :func:`_audit` / :func:`_audit_true`, which
record the failure and let the case carry on, and one hard ``ctx.check`` at
the end asserts the collected list is empty. The verdict is unchanged — the
Salesperson gap still FAILS this case, as rule 2 requires — and every
assertion still carries its own expected-vs-actual, because
``TestContext.check`` appends and emits before it raises. The shape is
``tests/fg05/test_avatax_config.py``'s.

Do NOT press anything — enforced, not remembered
------------------------------------------------
Step 8: *"Do NOT press Reconnect, Refresh Locations or the Auto Import
buttons anywhere on this screen."* Every RPC call in this suite goes through
:class:`tests.fg08.common.ReadOnlyRPC`, which refuses any method outside a
small read allow-list, so those buttons' methods cannot be reached even by
mistake — and the test proves that by trying four of them and asserting all
four were refused before reaching Odoo. It also reads the buttons out of the
arch and names their methods in the log, so the human tester knows exactly
which controls to keep away from on a store that is live (``active=True``,
``auto_import_data=True``, ``environment='production'``).
"""
from __future__ import annotations

from adapters.base import OdooRPCError
from framework.context import AssertionFailed
from framework.registry import test_case
from tests.fg08.common import (ACTION_MANAGE_STORES, CHANNEL,
                               DROPPED_V15_FIELDS, EXPECTED_PAGES,
                               GROUP_MANAGER, GROUP_MULTI_COMPANY,
                               MENU_CONFIGURATION, MENU_MANAGE_STORES,
                               MENU_ROOT, MENU_STORE_CONFIGURATION, MODULE,
                               PAGE_INVENTORY, PAGE_ORDER, PAGE_PRODUCT,
                               RENAMED_SINCE_V15, SHOPIFY, VIEW_STORE_FORM,
                               VIEW_STORE_LIST, WORKFLOW, WORKFLOW_NAME,
                               ReadOnlyViolation, arch_buttons,
                               arch_field_map, arch_pages, channel_fields,
                               field_on_page, find_shopify_store, finding,
                               list_columns, m2o_id, manual, observation,
                               parse_arch, readonly_rpc, require_connector,
                               require_manager_group, require_v19,
                               resolve_action, secret_state, store_values,
                               trace, view_arch, visible_occurrence,
                               write_csv)

# ---------------------------------------------------------------------------
# The workbook's own field list, tab by tab, exactly as its steps 2-7 name
# the labels. Each entry is (page name, workbook label, field name, kind).
#
# kind: "value"  — a scalar the tester ticks off
#       "list"   — a sub-table or checkbox group whose ROW COUNT matters
#                  ("every list … has the same number of entries as the
#                  printout, with the same values")
#       "secret" — read to prove non-empty; the value is never captured
# ---------------------------------------------------------------------------
HEADER = ""          # the area above the notebook — the workbook's steps 2-3

WORKBOOK_FIELDS = (
    # --- steps 2-3: the top of the screen ----------------------------------
    (HEADER, "Name", "name", "value"),
    (HEADER, "Company", "company_id", "value"),
    (HEADER, "Platform", "platform", "value"),
    (HEADER, "Hostname", "shopify_hostname", "value"),
    (HEADER, "Access Token", "shopify_access_token", "secret"),

    # --- step 4: Product Configuration -------------------------------------
    (PAGE_PRODUCT[0], "Auto Create Product if Not Found",
     "auto_create_master_product", "value"),
    (PAGE_PRODUCT[0], "Auto Override Product Info after Importing",
     "auto_override_product", "value"),
    (PAGE_PRODUCT[0], "Product Fields are Overridden",
     "auto_override_imported_field_ids", "list"),
    (PAGE_PRODUCT[0], "Pricelist", "pricelist_id", "value"),
    (PAGE_PRODUCT[0], "Export from Master",
     "can_export_product_from_master", "value"),
    (PAGE_PRODUCT[0], "Export from Mapping",
     "can_export_product_from_mapping", "value"),
    (PAGE_PRODUCT[0], "Fields to Export (from Master)",
     "master_template_exported_field_ids", "list"),
    (PAGE_PRODUCT[0], "Fields to Export (from Mapping)",
     "mapping_template_exported_field_ids", "list"),

    # --- steps 5-6: Inventory Configuration --------------------------------
    (PAGE_INVENTORY[0], "Enable Inventory Sync",
     "is_enable_inventory_sync", "value"),
    (PAGE_INVENTORY[0], "Allow Bulk Sync Manually",
     "is_allow_manual_bulk_inventory_sync", "value"),
    (PAGE_INVENTORY[0], "Warehouses to Sync Inventory",
     "active_warehouse_ids", "list"),
    (PAGE_INVENTORY[0], "Inventory Export Rules",
     "include_inventory_sync_ids", "list"),
    (PAGE_INVENTORY[0], "Exclude Mappings from Inventory Export",
     "exclude_inventory_sync_ids", "list"),
    (PAGE_INVENTORY[0], "Default Fulfillment Location",
     "fulfillment_location_id", "value"),
    (PAGE_INVENTORY[0], "Allow to manage multi-warehouses",
     "has_multi_warehouses", "value"),
    (PAGE_INVENTORY[0], "Default Warehouse",
     "display_default_warehouse", "value"),
    (PAGE_INVENTORY[0], "Location-to-warehouse mapping",
     "shopify_location_mapping_ids", "list"),

    # --- step 7: Order Configuration ---------------------------------------
    (PAGE_ORDER[0], "Enable Export Shipment",
     "auto_export_shipment_to_store", "value"),
    (PAGE_ORDER[0], "Order Date to Import",
     "min_order_date_to_import", "value"),
    (PAGE_ORDER[0], "Order Prefix", "order_prefix", "value"),
    (PAGE_ORDER[0], "Sales Team", "sales_team_id", "value"),
    (PAGE_ORDER[0], "Guest Customer Name", "default_guest_customer",
     "value"),
    (PAGE_ORDER[0], "Salesperson", "user_id", "value"),
    (PAGE_ORDER[0], "Tags", "default_order_tag_ids", "list"),
    (PAGE_ORDER[0], "Shipping Policy", "default_shipping_policy", "value"),
    (PAGE_ORDER[0], "Default Warehouse", "default_warehouse_id", "value"),
    (PAGE_ORDER[0], "Tax", "default_tax_product_id", "value"),
    (PAGE_ORDER[0], "Discount", "default_discount_product_id", "value"),
    (PAGE_ORDER[0], "Shipping Cost", "default_shipping_cost_product_id",
     "value"),
    (PAGE_ORDER[0], "Import Customer Info & Addresses",
     "is_import_customer_allowed", "value"),
    (PAGE_ORDER[0], "Default Customer", "default_customer_id", "value"),
    (PAGE_ORDER[0], "Payment Method Mapping (Payment Settings)",
     "payment_method_mapping_ids", "list"),
    (PAGE_ORDER[0], "Import & Automation Settings",
     "order_process_rule_ids", "list"),
)

#: Fields the workbook names that this build does NOT place on the screen.
#: Kept as data rather than buried in a branch, so the reason each one is
#: here is reviewable.
KNOWN_OFF_SCREEN = {
    "user_id": (
        "restored on the model under FG11-D2 / BC-012 "
        "(multichannel_order/models/ecommerce_channel.py:44-61) but placed "
        "on NO view; v15 carried it at novobi-omni-addons/"
        "multichannel_order/views/omnichannel_dashboard_views.xml:71 inside "
        "group 'top_left' of page 'order_configuration_page'"),
}

#: Buttons on this screen whose methods reach Shopify or re-arm the import
#: cron. The workbook's step 8 forbids pressing them; this suite cannot
#: call them (ReadOnlyRPC), and names them so the tester can avoid them.
DANGEROUS_BUTTON_METHODS = (
    "reconnect", "disconnect", "shopify_refresh_location",
    "bulk_inventory_sync", "enable_auto_import_data",
    "disable_auto_import_data", "toggle_safe_mode", "toggle_debug_logging",
)

#: Methods this test tries to call, to prove the guard rather than assert
#: good intentions. All four must be refused before reaching Odoo.
GUARD_PROBE = ("write", "reconnect", "shopify_refresh_location",
               "enable_auto_import_data")

#: Many2one config fields whose target must be a live record. A value that
#: silently points at an archived or deleted record is the workbook's
#: "will silently mis-route real orders" shape.
ROUTING_M2O = (
    ("company_id", "res.company"),
    ("pricelist_id", "product.pricelist"),
    ("fulfillment_location_id", "shopify.location"),
    ("default_warehouse_id", "stock.warehouse"),
    ("sales_team_id", "crm.team"),
    ("default_tax_product_id", "product.product"),
    ("default_discount_product_id", "product.product"),
    ("default_shipping_cost_product_id", "product.product"),
    ("default_fee_product_id", "product.product"),
    ("default_handling_cost_product_id", "product.product"),
    ("default_wrapping_cost_product_id", "product.product"),
    ("default_customer_id", "res.partner"),
    ("default_payment_journal_id", "account.journal"),
    ("default_payment_method_line_id", "account.payment.method.line"),
    ("default_deposit_account_id", "account.account"),
    ("user_id", "res.users"),
    ("currency_id", "res.currency"),
    ("measure_unit", "uom.uom"),
)


def _audit(ctx, findings, name, expected, actual):
    """``ctx.check`` that records the gap and lets the case carry on.

    TC-CHN-001 is a four-tab inventory review, and the workbook says to run
    it FIRST because every later e-commerce case depends on its result. A
    plain ``ctx.check`` raises on the first mismatch — and on the shipped
    build the first mismatch is a KNOWN, already-triaged PRODUCT defect: the
    Salesperson field restored on the model but placed on no view (Expected
    Result line 4, below). That one gap aborted the case before the checks
    the workbook's own *If It Fails* column asks for had run at all: the
    step-8 guard proof, the archived-or-deleted many2one sweep over the 18
    routing fields, the required-sub-table sweep, and the dropped-v15-fields
    assertion. None of them had ever executed on a recorded run.

    The assertion is still recorded in full: ``TestContext.check`` appends to
    ``ctx.assertions`` and emits the ASSERTION event BEFORE it raises, so the
    evidence keeps expected-vs-actual per line. Only the abort is deferred —
    the collected findings are asserted together by one hard ``ctx.check`` at
    the end, so the verdict is unchanged and the Salesperson gap still FAILS
    this case.

    ``ctx.blocked()`` / ``ctx.skip()`` raise ``BlockedTest`` / ``SkipTest``
    and are deliberately NOT caught: a precondition that cannot be evaluated
    must still stop the case. Same shape, and the same reasoning, as
    ``tests/fg05/test_avatax_config.py``.
    """
    try:
        ctx.check(name, expected, actual)
    except AssertionFailed as exc:
        findings.append(str(exc))
        ctx.log(f"AUDIT FINDING — {exc}")


def _audit_true(ctx, findings, name, condition, actual_desc=""):
    """``ctx.check_true`` counterpart of :func:`_audit`."""
    try:
        ctx.check_true(name, condition, actual_desc=actual_desc)
    except AssertionFailed as exc:
        findings.append(str(exc))
        ctx.log(f"AUDIT FINDING — {exc}")


def _menu_group_field(ctx) -> str:
    """``ir.ui.menu``'s group field, resolved rather than assumed.

    v19 renamed the many2many from ``groups_id`` to ``group_ids`` with no
    shim (``odoo/addons/base/models/ir_ui_menu.py:29``; the same rename hit
    ``res.users``, ``ir.ui.view`` and ``ir.actions.*`` — the port's
    ``BC-014``). Reading the field name from ``fields_get`` keeps this
    assertion correct on either side of that rename instead of silently
    reading nothing.
    """
    available = readonly_rpc(ctx).fields_get("ir.ui.menu",
                                             ["group_ids", "groups_id"],
                                             ["type"])
    return "group_ids" if "group_ids" in available else "groups_id"


def _resolve_display(ctx, meta: dict, raw):
    """Turn a raw RPC value into what a printout comparison needs.

    ``read()`` gives a many2one as ``[id, display_name]``, an x2many as a
    list of bare ids and a selection as its technical key. A tester ticking
    values off a printout needs labels, so ids are resolved to display
    names (with ``active_test: False``, so an archived target still shows
    its name rather than vanishing) and selection keys are shown with their
    label. Returns ``(display, row count)``.
    """
    rpc = readonly_rpc(ctx)
    kind = meta.get("type")
    if kind == "many2one":
        if isinstance(raw, (list, tuple)) and len(raw) > 1:
            return str(raw[1]), 1
        return ("" if not raw else str(raw)), 1 if raw else 0
    if kind in ("many2many", "one2many"):
        ids = list(raw or [])
        if not ids:
            return "", 0
        comodel = meta.get("relation")
        labels = [f"#{i}" for i in ids]
        if comodel:
            try:
                rows = rpc.search_read(comodel, [("id", "in", ids)],
                                       ["display_name"],
                                       context={"active_test": False})
                by_id = {r["id"]: r.get("display_name") or f"#{r['id']}"
                         for r in rows}
                labels = [str(by_id.get(i, f"#{i} (MISSING)")) for i in ids]
            except OdooRPCError as exc:
                ctx.log(f"[warn] could not label {comodel} rows ({exc})")
        return " | ".join(labels), len(ids)
    if kind == "selection":
        options = dict(meta.get("selection") or [])
        if not raw:
            return "", 0
        return f"{options.get(raw, raw)} [{raw}]", 1
    if kind == "boolean":
        return ("Yes" if raw else "No"), 1
    return ("" if raw in (None, False) else str(raw)), 1 if raw else 0


@test_case(
    id="TEST-FG08-CHN-001",
    name="The Shopify store's settings all came across",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module=MODULE,
    priority="P0",
    kind="DATA",
    order=800,
    description="Captures every value on the store's four tabs into a CSV "
                "for the Novobi-printout tick-off, and asserts what needs "
                "no printout: the three tabs and every field the workbook "
                "names are on the screen where it says, Name is read-only "
                "and Platform hidden on a saved store, the Access Token is "
                "masked and not empty, no configured many2one points at an "
                "archived or missing record, and no required sub-table came "
                "across empty. Expected Result line 4 (Salesperson on the "
                "Order Configuration tab) is asserted as written and FAILS: "
                "the field was restored on the model but on no view. Every "
                "check records its finding and the case carries on, with "
                "one closing assertion deciding the verdict, so that known "
                "failure no longer hides the checks behind it.",
    traceability=trace(
        "TC-CHN-001",
        user_story="As the E-commerce Manager I need every connector "
                   "setting to have survived the upgrade, because a value "
                   "that reverted to a default will not raise an error — it "
                   "will just start mis-routing real orders."))
def test_chn_001(ctx):
    rpc = readonly_rpc(ctx)
    inventory_rows: list[list] = []
    list_counts: list[list] = []
    findings: list[str] = []      # every gap, reported together at the end

    try:
        with ctx.step("Gate: Odoo 19 target, the e-commerce connector stack "
                      "installed, and the workbook's own 'E-commerce "
                      "Manager' precondition met"):
            require_v19(ctx)
            require_manager_group(ctx)
            fields_meta = require_connector(ctx)
            ctx.log(f"{CHANNEL} exposes {len(fields_meta)} fields on this "
                    f"database")
            manual(ctx, "this case is the reference for every later "
                        "e-commerce case (FG-08 to FG-12) and sits behind "
                        "the workbook's GATE 2 — do not run an export "
                        "against any store until it passes")

        with ctx.step("Step 1: the menu path 'E-commerce Connectors > "
                      "Configuration > Store Configuration > Manage Stores' "
                      "resolves, and the store is listed"):
            menus = {}
            for label, xmlid in (
                    ("E-commerce Connectors", MENU_ROOT),
                    ("Configuration", MENU_CONFIGURATION),
                    ("Store Configuration", MENU_STORE_CONFIGURATION),
                    ("Manage Stores", MENU_MANAGE_STORES)):
                menu_id = rpc.ref(xmlid)
                menus[label] = menu_id
                ctx.log(f"  menu {label!r} -> {xmlid} = {menu_id}")
            _audit(ctx, findings,
                   "Every level of the workbook's menu path exists", [],
                   [label for label, mid in menus.items() if not mid])

            group_field = _menu_group_field(ctx)
            manage = rpc.read("ir.ui.menu", [menus["Manage Stores"]],
                              ["name", "parent_id", group_field,
                               "action"])[0]
            # The 'Store Configuration' level is the v19 marker: v15 hung
            # Manage Stores straight off Configuration
            # (novobi-omni-addons/omni_manage_channel/views/
            # ecommerce_channel_views.xml:82).
            _audit(ctx, findings,
                   "'Manage Stores' hangs off 'Store Configuration' — the "
                   "v19 menu level the workbook navigates",
                   menus["Store Configuration"],
                   m2o_id(manage.get("parent_id")))
            manager_group = rpc.ref(GROUP_MANAGER)
            _audit_true(ctx, findings,
                "…and is restricted to the 'E-commerce Manager' group, "
                "which is why the workbook's precondition names it",
                manager_group in (manage.get(group_field) or []),
                actual_desc=f"menu {group_field}={manage.get(group_field)}, "
                            f"{GROUP_MANAGER}={manager_group}")

            action = resolve_action(ctx, ACTION_MANAGE_STORES)
            ctx.log(f"action {ACTION_MANAGE_STORES}: "
                    f"domain={action['parsed_domain']!r} "
                    f"context={action['parsed_context']!r} "
                    f"view_mode={action['view_mode']!r} "
                    f"views={action['views']!r}")
            store = find_shopify_store(ctx, action)
            store_id = store["id"]

        with ctx.step("Step 2: Name, Company and Platform — and the two "
                      "things the workbook warns about on a SAVED store"):
            arch = view_arch(ctx, VIEW_STORE_FORM, "form")
            root = parse_arch(arch)
            field_map = arch_field_map(root)
            pages = arch_pages(root)
            ctx.log(f"assembled form arch: {len(field_map)} distinct fields; "
                    f"pages={pages}")

            _audit(ctx, findings,
                "The three notebook tabs the workbook walks exist, in its "
                "order",
                [name for name, _string in EXPECTED_PAGES],
                [name for name, _string in pages])
            _audit(ctx, findings,
                   "…with the labels the workbook names",
                   [string for _name, string in EXPECTED_PAGES],
                   [string for _name, string in pages])

            values = store_values(ctx, store_id)
            _audit(ctx, findings,
                   "Platform is Shopify", SHOPIFY, values.get("platform"))
            _audit_true(ctx, findings,
                        "Name is not empty", bool(values.get("name")),
                        actual_desc=f"name={values.get('name')!r}")

            # "the store Name is read-only once the record has been saved"
            name_field = field_on_page(field_map, "name", HEADER) or {}
            name_readonly = str(name_field.get("readonly") or "").replace(
                " ", "")
            _audit_true(ctx, findings,
                "The workbook's warning holds: Name is read-only once the "
                "record has been saved",
                name_readonly == "write_date!=False",
                actual_desc=f"<field name=\"name\" "
                            f"readonly={name_field.get('readonly')!r}> "
                            f"(omni_manage_channel/views/"
                            f"omnichannel_dashboard_views.xml:248-250)")

            # "the Platform is HIDDEN altogether on a saved store"
            platform_field = field_on_page(field_map, "platform",
                                            HEADER) or {}
            platform_invisible = str(
                platform_field.get("invisible") or "").replace(" ", "")
            _audit_true(ctx, findings,
                "The workbook's warning holds: Platform is hidden "
                "altogether on a saved store",
                platform_invisible == "write_date!=False",
                actual_desc=f"<field name=\"platform\" "
                            f"invisible={platform_field.get('invisible')!r}> "
                            f"(omni_manage_channel/views/"
                            f"omnichannel_dashboard_views.xml:254)")

            # …which is why the workbook says to read it off the list instead
            list_arch = view_arch(ctx, VIEW_STORE_LIST, "list")
            columns = list_columns(list_arch)
            ctx.log(f"Manage Stores list columns: {columns}")
            _audit_true(ctx, findings,
                "…and the Manage Stores list carries the store logo the "
                "workbook says to read the Platform from instead",
                any(name == "logo_and_name" for name, _s, _w in columns),
                actual_desc=f"columns={[c[0] for c in columns]}")
            observation(
                ctx,
                f"the list's logo path and the card's are built "
                f"differently: logo_and_name embeds "
                f"'/omni_manage_channel/static/src/img/<platform>.png' "
                f"(omni_manage_channel/models/ecommerce_channel.py:268-276) "
                f"while the stored image_url compute uses the 'i64x64/' "
                f"variant (…:344-357) and the kanban card builds its own "
                f"'i64x64/' path inline. This database holds "
                f"image_url={values.get('image_url')!r} — harmless, since "
                f"neither the list widget nor the card reads that stored "
                f"value, but worth knowing if 'the logo' is compared "
                f"between screens")

            company = values.get("company_id")
            company_field = visible_occurrence(field_map, "company_id") or {}
            _audit_true(ctx, findings,
                        "Company is set", bool(m2o_id(company)),
                        actual_desc=f"company_id={company!r}")
            observation(
                ctx,
                f"Company is only shown with the multi-company group "
                f"(groups={company_field.get('groups')!r}); on a "
                f"single-company database the tester will not see the field "
                f"at all and should tick it off from this log: "
                f"{company!r}. {GROUP_MULTI_COMPANY} = "
                f"{rpc.ref(GROUP_MULTI_COMPANY)}")

        with ctx.step("Step 3: Hostname is correct, and Access Token shows "
                      "as filled — the value never enters the evidence"):
            _audit_true(ctx, findings,
                "Hostname is not empty",
                bool(values.get("shopify_hostname")),
                actual_desc=f"shopify_hostname="
                            f"{values.get('shopify_hostname')!r}")
            manual(ctx, f"tick the Hostname off against the printout: "
                        f"{values.get('shopify_hostname')!r} (the store's "
                        f"own URL field reads {values.get('secure_url')!r})")

            token_field = field_on_page(field_map, "shopify_access_token",
                                         HEADER) or {}
            _audit_true(ctx, findings,
                "Access Token is masked on the form, which is why the "
                "workbook only asks whether it is filled",
                str(token_field.get("password")) == "1",
                actual_desc=f"<field name=\"shopify_access_token\" "
                            f"password={token_field.get('password')!r}> "
                            f"(multichannel_shopify/views/"
                            f"ecommerce_channel_views.xml:50-53)")

            credentials = secret_state(ctx, store_id)
            reportable = {key: value for key, value in credentials.items()
                          if not key.endswith("__length")}
            ctx.log(f"credential state (values deliberately not captured): "
                    f"{reportable}")
            _audit(ctx, findings,
                   "Access Token is not empty", "set",
                   credentials.get("shopify_access_token"))
            token_meta_groups = (
                channel_fields(ctx).get("shopify_access_token", {})
                .get("groups"))
            ctx.log(f"FG-19 D-2: the token is not a column on "
                    f"ecommerce_channel at all — it is a non-stored compute "
                    f"over the channel secret store (ir.config_parameter "
                    f"key 'omni_manage_channel.channel_secret.<id>."
                    f"shopify_access_token', System-only ACL) and the field "
                    f"carries groups={token_field.get('groups')!r} on the "
                    f"view / {token_meta_groups!r} on the model. A tester "
                    f"without 'E-commerce Manager' sees no field at all and "
                    f"must not read that as an empty token.")

        with ctx.step("Steps 4-7: every field the workbook names is on the "
                      "tab it says, and its value is captured for the "
                      "printout tick-off"):
            off_screen, wrong_tab = [], []
            for page_name, label, field_name, kind in WORKBOOK_FIELDS:
                meta = fields_meta.get(field_name) or {}
                on_model = bool(meta)
                occurrence = (field_on_page(field_map, field_name, page_name)
                              if on_model else None)
                if kind == "secret":
                    state = credentials.get(field_name)
                    display = ("<set, not captured>" if state == "set"
                               else f"<{state}>")
                    count = 1 if state == "set" else 0
                else:
                    display, count = _resolve_display(
                        ctx, meta, values.get(field_name))

                tab = dict(EXPECTED_PAGES).get(page_name, "(top of screen)")
                inventory_rows.append([
                    tab, label, field_name, meta.get("type") or "ABSENT",
                    display, count if kind == "list" else "",
                    "on screen" if occurrence else
                    ("ON THE MODEL BUT NOT ON ANY VIEW" if on_model
                     else "ABSENT FROM THE MODEL"),
                    KNOWN_OFF_SCREEN.get(field_name, ""),
                ])
                if kind == "list":
                    list_counts.append([tab, label, field_name, count])

                if kind == "secret" and not on_model:
                    # In v19 fields_get() OMITS a group-restricted field
                    # rather than returning it empty (asserted by
                    # omni_manage_channel/tests/test_sec_007.py:96-125), so
                    # "absent" here means "not visible to this user", which
                    # the gate above has already ruled out — record it
                    # rather than counting it as a migration loss.
                    ctx.log(f"  {label} ({field_name}) is not in "
                            f"fields_get() for this user; the E-commerce "
                            f"Manager gate passed, so treat this as a "
                            f"module-install gap, not a lost value")
                elif not on_model:
                    off_screen.append(f"{label} ({field_name}): absent from "
                                      f"the model")
                elif not occurrence:
                    elsewhere = [o["page"] or "(top of screen)"
                                 for o in field_map.get(field_name, {})
                                 .get("occurrences", [])]
                    if elsewhere:
                        wrong_tab.append(
                            f"{label} ({field_name}) is in the arch but not "
                            f"on {page_name!r} — it is on {elsewhere}")
                    else:
                        off_screen.append(
                            f"{label} ({field_name}): "
                            + (KNOWN_OFF_SCREEN.get(field_name)
                               or "not in the assembled form arch"))

            for line in off_screen + wrong_tab:
                ctx.log(f"  MISSING/MISPLACED: {line}")
            ctx.log(f"captured {len(inventory_rows)} workbook fields across "
                    f"{len(set(row[0] for row in inventory_rows))} tabs")

            # Salesperson carries its own verdict below (Expected line 4),
            # so it is excluded here to keep the two readable.
            _audit(ctx, findings,
                "Every field the workbook's steps 2-7 names — other than "
                "Salesperson, which is asserted on its own below — is on "
                "the tab it says",
                [],
                [line for line in off_screen + wrong_tab
                 if "user_id" not in line])
            manual(ctx, "tick every row of "
                        "TC-CHN-001-store-settings-inventory.csv off against "
                        "the Novobi printout. Only the printout says what "
                        "each value SHOULD be — the platform does not hold "
                        "it. Per the workbook's If It Fails, two shapes "
                        "matter: a value that reverted to a DEFAULT, and a "
                        "LIST with fewer rows than the printout")
            manual(ctx, "the row counts alone are in "
                        "TC-CHN-001-list-row-counts.csv — compare those "
                        "first; a short list means rules were lost, which is "
                        "the more serious of the two shapes")

        with ctx.step("Expected Result line 4: Salesperson is present on "
                      "the Order Configuration tab and carries the expected "
                      "user"):
            salesperson_meta = fields_meta.get("user_id") or {}
            ctx.log(f"model side: ecommerce.channel.user_id = "
                    f"{salesperson_meta.get('type')} "
                    f"string={salesperson_meta.get('string')!r} "
                    f"relation={salesperson_meta.get('relation')!r} — "
                    f"restored under FG11-D2 / BC-012 (multichannel_order/"
                    f"models/ecommerce_channel.py:44-61)")
            _audit(ctx, findings,
                   "Salesperson exists on the model, labelled as the "
                   "workbook names it", "Salesperson",
                   salesperson_meta.get("string"))

            occurrences = field_map.get("user_id", {}).get("occurrences", [])
            finding(ctx,
                    "user_id (Salesperson) was restored on the MODEL by the "
                    "port but placed on NO view. v15 carried it on exactly "
                    "the tab the workbook names — novobi-omni-addons/"
                    "multichannel_order/views/"
                    "omnichannel_dashboard_views.xml:71, inside "
                    "<group name=\"top_left\"> of page "
                    "'order_configuration_page'. On staging_19 there is no "
                    "<field name=\"user_id\"/> in any ecommerce.channel "
                    "view. The fix is a one-line view addition; until then "
                    "the field cannot be read or set from the screen at "
                    "all, so 'carries the expected user' is unreachable for "
                    "the tester as well.")
            _audit(ctx, findings,
                "Salesperson is present on the Order Configuration tab "
                "(workbook Expected Result line 4)",
                True,
                bool(field_on_page(field_map, "user_id", PAGE_ORDER[0])))
            # The second half of the workbook's line. It is reached even
            # while the first half fails (the checks collect), and on this
            # build it fails too: a field on no view cannot be set from the
            # screen, so the store's user_id is empty.
            _audit_true(ctx, findings,
                "…and carries a user ('carries the expected user')",
                bool(m2o_id(values.get("user_id"))),
                actual_desc=f"user_id={values.get('user_id')!r} "
                            f"(arch occurrences: {occurrences})")

        with ctx.step("Step 8: the buttons the workbook forbids pressing "
                      "are named — and cannot be reached from this suite"):
            buttons = arch_buttons(root)
            for button in buttons:
                ctx.log(f"  button name={button['name']!r} "
                        f"label={button['label']!r} "
                        f"icon={button['icon']!r} "
                        f"caption-from={button['fields']!r} "
                        f"tab={button['page_string'] or '(top of screen)'} "
                        f"invisible={button['invisible']!r} "
                        f"confirm={bool(button['confirm'])} "
                        f"groups={button['groups']!r}")
            names = {button["name"] for button in buttons}
            _audit_true(ctx, findings,
                "The Reconnect / Refresh Locations / Auto Import controls "
                "the workbook's step 8 forbids are on this screen, so the "
                "tester knows what to keep away from",
                bool(names & set(DANGEROUS_BUTTON_METHODS)),
                actual_desc=f"present: "
                            f"{sorted(names & set(DANGEROUS_BUTTON_METHODS))}"
                            f"; absent: "
                            f"{sorted(set(DANGEROUS_BUTTON_METHODS) - names)}")
            ctx.log(f"Reconnect calls check_connection -> "
                    f"_shopify_check_connection -> shopify_api.shop.all() "
                    f"(multichannel_shopify/models/ecommerce_channel.py:"
                    f"126-138) — a live call to "
                    f"{values.get('shopify_hostname')!r}. Refresh Locations "
                    f"is shopify_refresh_location. The Auto Import stat "
                    f"buttons are enable_auto_import_data / "
                    f"disable_auto_import_data, and enabling re-stamps "
                    f"last_sync_order to now (omni_manage_channel/models/"
                    f"ecommerce_channel.py:597-603), which would destroy "
                    f"TC-CHN-005's baseline before it is read.")

            # Prove the guard rather than assert good intentions.
            refused = []
            for method in GUARD_PROBE:
                try:
                    rpc.call(CHANNEL, method, [store_id])
                except ReadOnlyViolation:
                    refused.append(method)
                except Exception as exc:            # noqa: BLE001
                    refused.append(f"{method} (REACHED ODOO: {exc})")
            _audit(ctx, findings,
                "This suite is structurally unable to press them: every one "
                "is refused by ReadOnlyRPC before it reaches Odoo",
                list(GUARD_PROBE), refused)

        with ctx.step("If It Fails, shape 1: no configured many2one points "
                      "at a record that is archived or gone"):
            dangling, archived = [], []
            for field_name, comodel in ROUTING_M2O:
                if field_name not in fields_meta:
                    continue
                target = m2o_id(values.get(field_name))
                if not target:
                    continue
                rows = rpc.search_read(comodel, [("id", "=", target)],
                                       ["display_name"],
                                       context={"active_test": False})
                if not rows:
                    dangling.append(f"{field_name} -> {comodel}#{target} "
                                    f"does not exist")
                    continue
                if not rpc.search_count(comodel, [("id", "=", target)]):
                    archived.append(
                        f"{field_name} -> {comodel}#{target} "
                        f"{rows[0].get('display_name')!r} is ARCHIVED")
            _audit(ctx, findings,
                   "No configured setting points at a record that no "
                   "longer exists", [], dangling)
            _audit(ctx, findings,
                   "No configured setting points at an ARCHIVED record — "
                   "the workbook's 'will silently mis-route real orders' "
                   "shape", [], archived)

        with ctx.step("If It Fails, shape 2: no list this configuration "
                      "requires came across empty"):
            # Every rule below is the module's own constraint or required=
            # binding, not an invented expectation.
            required_lists = []
            if values.get("is_enable_inventory_sync"):
                required_lists.append((
                    "active_warehouse_ids",
                    "Warehouses to Sync Inventory is required= when Enable "
                    "Inventory Sync is on (multichannel_fulfillment/views/"
                    "ecommerce_channel_views.xml:40-42)"))
            if values.get("has_multi_warehouses") and \
                    values.get("is_enable_inventory_sync"):
                required_lists.append((
                    "shopify_location_mapping_ids",
                    "check_mapping_locations raises 'There must be at least "
                    "one line for location mapping.' when multi-warehouses "
                    "and inventory sync are both on (multichannel_shopify/"
                    "models/ecommerce_channel.py:94-113)"))
            if values.get("auto_override_product"):
                required_lists.append((
                    "auto_override_imported_field_ids",
                    "Product Fields are Overridden is what Auto Override "
                    "actually overrides; on with an empty list overrides "
                    "nothing (multichannel_product/views/"
                    "ecommerce_channel_views.xml:38-43)"))
            if values.get("can_export_product") and \
                    values.get("can_export_product_from_master"):
                required_lists.append((
                    "master_template_exported_field_ids",
                    "Fields to Export decides what an export from Master "
                    "sends; empty means an export sends nothing "
                    "(multichannel_product/views/"
                    "ecommerce_channel_views.xml:60-74)"))
            for name, reason in required_lists:
                ctx.log(f"  {name}: {len(values.get(name) or [])} row(s) — "
                        f"{reason}")
            _audit(ctx, findings,
                   "Every list this configuration requires has at least "
                   "one row", [],
                   [f"{name}: {reason}" for name, reason in required_lists
                    if not (values.get(name) or [])])

            include_rows = values.get("include_inventory_sync_ids") or []
            _audit_true(ctx, findings,
                "Inventory Export Rules is not empty — a store created by "
                "the module gets one global 100% rule by default, so an "
                "empty list on a migrated store means rules were lost",
                bool(include_rows),
                actual_desc=f"{len(include_rows)} row(s); "
                            f"prepare_default_inv_include_vals seeds one "
                            f"'3_global' 100% rule at create "
                            f"(multichannel_fulfillment/models/"
                            f"ecommerce_channel.py:286-294)")

        with ctx.step("Briefing the tester: what is gone or renamed since "
                      "v15, so a printout comparison does not report it as "
                      "a loss"):
            _audit(ctx, findings,
                "The four v15 fields the port drops on purpose are still "
                "gone (oauth_version, state, is_in_syncing, "
                "last_option_sync_product) — re-adding one without a "
                "decision is what this asserts against",
                [], [f for f in DROPPED_V15_FIELDS if f in fields_meta])
            ctx.log("their removal is deliberate and reviewed: "
                    "omni_manage_channel/tests/test_ecommerce_channel.py "
                    "test_tc_dat_015_dropped_fields_are_deliberate — "
                    "oauth_version had no reader anywhere in the v15 tree; "
                    "state / is_in_syncing / last_option_sync_product were "
                    "UI state for the onboarding and Import-Products "
                    "screens, retired under D5. None of them appears on any "
                    "tab this case walks, so none is a printout row.")
            for old, new in RENAMED_SINCE_V15.items():
                observation(
                    ctx,
                    f"printout comparison note: v15's {old!r} is v19's "
                    f"{new!r} (present on ecommerce.channel here: "
                    f"{new in fields_meta})")
            ctx.log("the Payment Method Mapping sub-table follows the same "
                    "rename on its lines: v15 "
                    "payment.method.mapping.payment_method_id is v19 "
                    "payment_method_line_id (multichannel_order/views/"
                    "omnichannel_dashboard_views.xml:147-153, against v15's "
                    "…:113-120)")

        # One verdict for the whole case. Each gap above was recorded as
        # its own assertion as it happened — ctx.check appends to
        # ctx.assertions and emits the ASSERTION event BEFORE it raises — so
        # the evidence keeps expected-vs-actual per line while the run still
        # reaches every step. That matters here more than anywhere: the
        # Salesperson gap is a real product defect that fails on every
        # execution, and while it aborted the case the P0 migration checks
        # behind it never ran at all.
        with ctx.step("Audit summary: every gap this case found, reported "
                      "together"):
            if findings:
                ctx.log(f"{len(findings)} finding(s). The Salesperson view "
                        f"gap is expected on the shipped build "
                        f"(reports/data/fg08_feasibility.json, key "
                        f"_finding_salesperson); anything else listed here "
                        f"is new and needs triage:")
                for number, text in enumerate(findings, 1):
                    ctx.log(f"  {number}. {text}")
            # HARD check: the one that decides the verdict. The Salesperson
            # gap still FAILS this case through it — it is a product defect
            # and must keep being detected; it simply no longer hides the
            # checks behind it.
            ctx.check("TC-CHN-001 findings", [], findings)

    finally:
        write_csv(ctx, "TC-CHN-001-store-settings-inventory.csv",
                  ["Tab", "Workbook label", "Technical field", "Type",
                   "Value on v19", "Rows", "On screen?", "Note"],
                  inventory_rows)
        write_csv(ctx, "TC-CHN-001-list-row-counts.csv",
                  ["Tab", "Workbook label", "Technical field", "Rows on v19"],
                  list_counts)
        ctx.log(f"read-only RPC calls made: {rpc.calls}; records created or "
                f"modified: 0 (ReadOnlyRPC allows no write path)")
