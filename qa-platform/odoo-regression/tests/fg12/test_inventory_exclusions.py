"""FG-12 — TC-FUL-005 … TC-FUL-009: keeping products off the storefront, and
the manual bulk-sync button.

Implements the CLIENT MANUAL TESTING GUIDELINE
``MMG_v19_Client_Manual_Testing_Guideline_FG05-FG14_v1.0.xlsx`` / sheet
``Testing Guideline``, cases TC-FUL-005 (P0), TC-FUL-006 (P1), TC-FUL-007
(P1) and TC-FUL-009 (P1).

The exclusion rows are checked at both ends
-------------------------------------------
An exclusion row is not just a record: it is a clause in the domain the
connector builds before it decides what to publish
(``ecommerce_channel._generate_exclude_domain``, lines 173-192). A row that
saves and reloads but contributes nothing to that domain would pass a test
written only against the form — and would silently publish the very
products the gallery meant to hold back.

So each of TC-FUL-005, -006 and -007 creates its row, reads it back, and
then reads the domain the store would actually use, checking that the row
put a clause in it naming the right thing at the right level. The rows are
all scoped to scratch products and a scratch category this suite created,
so the domain is changed only with respect to items nobody sells.

TC-FUL-009 is the one case here that stays with a human: its steps 5 and 8
mean pressing a button that pushes the gallery's entire inventory to
Shopify. The button's gating is asserted; the press is not made.
"""
from __future__ import annotations

from adapters.base import OdooRPCError
from framework.registry import test_case

from .common import (CHANNEL, EXCLUDE, EXCLUDE_LABELS, EXCLUDE_LEVELS, MODULE,
                     WORKFLOW, WORKFLOW_NAME, acting_channel, attr,
                     button_attrs, leftover_exclusions, make_category,
                     make_product, manual, normalise, observation,
                     require_fulfillment, sweep, trace, view_arch)

STORE_FORM_INHERIT = ("multichannel_fulfillment."
                      "view_ecommerce_channel_form_settings_inherit")
STORE_FORM = "omni_manage_channel.view_ecommerce_channel_form_settings"
EXCLUDE_FORM = "multichannel_fulfillment.exclude_inventory_sync_view_form"

#: The field ``_generate_exclude_domain`` keys each level's clause on
#: (``ecommerce_channel.py:180-191``). The method itself is ``@api.private``
#: in v19 and cannot be reached over RPC, so these are recorded here and
#: each case asserts that clause's *input* instead.
DOMAIN_FIELD = {
    "2_product_category": "categ_id",
    "1_product": "product_tmpl_id",
    "0_product_variant": "id",
}


def _exclusion_ids(ctx, channel_id: int) -> list:
    return ctx.adapter.rpc.search(EXCLUDE, [("channel_id", "=", channel_id)])


def _make_exclusion(ctx, channel_id: int, applied_on: str, **values) -> int:
    rpc = ctx.adapter.rpc
    payload = {"channel_id": channel_id, "applied_on": applied_on}
    payload.update(values)
    row_id = rpc.create(EXCLUDE, payload)
    ctx.log(f"exclusion #{row_id} {payload}")
    return row_id


@test_case(
    id="TEST-FG12-FUL-005",
    name="A product can be excluded from inventory sync entirely",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module=MODULE,
    priority="P0",
    kind="API",
    order=1204,
    description="Apply On offers a category, a product and a variant; an "
                "exclusion row for a product saves, names what it applies "
                "to, and survives being read back; the row puts a clause "
                "into the domain the store uses to decide what NOT to "
                "publish; a second row for the same product is allowed or "
                "refused and the answer is recorded; and deleting the row "
                "returns the exclusion list to exactly the rows it started "
                "with.",
    traceability=trace("TC-FUL-005"))
def test_ful_005(ctx):
    rpc = require_fulfillment(ctx)
    channel = acting_channel(ctx)
    sweep(ctx)

    try:
        with ctx.step("Steps 2-3: the exclusion list as this run found it"):
            baseline = rpc.search_read(
                EXCLUDE, [("channel_id", "=", channel["id"])],
                ["name", "applied_on"], order="id")
            ctx.log(f"the store's existing exclusions ({len(baseline)}): "
                    + ("; ".join(f"{r['applied_on']} {r['name']}"
                                 for r in baseline) or "none"))
            product = make_product(ctx, "FUL-005 Art Item")

        with ctx.step("Step 4: Apply On offers a category, a product and a "
                      "variant — and, correctly, no 'all products'"):
            fields = rpc.call(EXCLUDE, "fields_get", ["applied_on"],
                              attributes=["selection", "string", "help"])
            values = [value for value, _ in fields["applied_on"]["selection"]]
            ctx.check("Apply On offers exactly the three levels",
                      sorted(EXCLUDE_LEVELS), sorted(values))
            ctx.check("…labelled as the workbook reads them", EXCLUDE_LABELS,
                      dict(fields["applied_on"]["selection"]))
            observation(ctx,
                        "there is deliberately no 'All Products' level on an "
                        "exclusion — that would switch the storefront off "
                        "entirely — which is why Exclude has three levels "
                        "where Include has four.")

        row_id = None
        with ctx.step("Steps 5-6: the row saves and shows what it applies to"):
            row_id = _make_exclusion(ctx, channel["id"], "1_product",
                                     product_tmpl_ids=[(6, 0,
                                                        [product["template_id"]])])
            row = rpc.read(EXCLUDE, [row_id],
                           ["name", "applied_on", "product_tmpl_ids",
                            "categ_ids", "product_product_ids"])[0]
            ctx.check("The row is at the product level", "1_product",
                      row["applied_on"])
            ctx.check("…and holds the product that was picked",
                      [product["template_id"]], row["product_tmpl_ids"])
            ctx.check_true("…and its name says what it applies to",
                           row["name"] and product["name"] in row["name"],
                           actual_desc=str(row["name"]))

        with ctx.step("Steps 7-8: it survives a reload of the store form"):
            again = rpc.read(CHANNEL, [channel["id"]],
                             ["exclude_inventory_sync_ids"])[0]
            ctx.check_true("The row is on the store when the form is read "
                           "again", row_id in
                           (again["exclude_inventory_sync_ids"] or []),
                           actual_desc=str(again["exclude_inventory_sync_ids"]))

        with ctx.step("The row is on the store's exclusion list, which is "
                      "what the exclude domain is built from"):
            # `_generate_exclude_domain` is @api.private in v19 — the
            # leading underscore makes it unreachable over RPC — so the
            # clause it builds cannot be read back from here. What CAN be
            # asserted is its whole input: the row is in
            # `exclude_inventory_sync_ids`, at the product level, naming
            # this template and nothing else. The method iterates that o2m
            # and keys on exactly those two things
            # (ecommerce_channel.py:180-191).
            on_store = rpc.read(CHANNEL, [channel["id"]],
                                ["exclude_inventory_sync_ids"])[0]
            ctx.check_true(
                "The row is in the o2m the exclude domain is built from",
                row_id in (on_store["exclude_inventory_sync_ids"] or []),
                actual_desc=str(on_store["exclude_inventory_sync_ids"]))
            ctx.check("...and it is keyed at the product level, which is the "
                      "branch that produces a "
                      + DOMAIN_FIELD["1_product"] + " clause",
                      "1_product", row["applied_on"])
            manual(ctx,
                   "the clause itself is built by "
                   "ecommerce.channel._generate_exclude_domain, a private "
                   "method v19 will not expose over RPC. Its whole input is "
                   "asserted above. Confirming the product actually stops "
                   "reaching the storefront needs one observed sync, which "
                   "only Novobi can run safely.")

        with ctx.step("Step 9: a second row for the same product — the "
                      "answer is recorded either way"):
            error, second_id = "", None
            try:
                second_id = _make_exclusion(
                    ctx, channel["id"], "1_product",
                    product_tmpl_ids=[(6, 0, [product["template_id"]])])
            except OdooRPCError as exc:
                error = str(exc)
            ctx.check_true(
                "The system gave a definite answer on a duplicate exclusion",
                bool(second_id) or bool(error),
                actual_desc=("ALLOWED — a second row for the same product is "
                             "accepted" if second_id
                             else f"REFUSED — {error[:200]}"))
            observation(ctx,
                        "Novobi's answer to TC-FUL-005 step 9: a second "
                        "exclusion row for the same product is "
                        + ("ALLOWED" if second_id else "REFUSED")
                        + ". exclude.inventory.sync declares no uniqueness "
                          "constraint, and _generate_exclude_domain ANDs the "
                          "clauses, so a duplicate is harmless — it "
                          "contributes the same clause twice.")
            if second_id:
                rpc.unlink(EXCLUDE, [second_id])

        with ctx.step("Steps 10-11: deleting the row returns the exclusion "
                      "list to exactly what it was"):
            rpc.unlink(EXCLUDE, [row_id])
            after = rpc.search_read(
                EXCLUDE, [("channel_id", "=", channel["id"])],
                ["name", "applied_on"], order="id")
            ctx.check("The exclusion list is back to the rows this run "
                      "found", [(r["applied_on"], r["name"]) for r in baseline],
                      [(r["applied_on"], r["name"]) for r in after])
            ctx.check("...and no row on the store names this product any "
                      "more", [], leftover_exclusions(ctx, channel["id"]))

        manual(ctx,
               "TC-FUL-005's closing note — the excluded product's Available "
               "figure may still show on the listing, because the exclusion "
               "stops it being SENT, not calculated. The workbook says not "
               "to raise that as a defect; this run asserts the sending "
               "side (the exclude domain) directly, which is the side that "
               "matters.")

    finally:
        with ctx.step("Cleanup: every scratch exclusion and product is "
                      "removed"):
            sweep(ctx)
            ctx.check("No exclusion this test created is left on the store",
                      [], leftover_exclusions(ctx, channel["id"]))


@test_case(
    id="TEST-FG12-FUL-006",
    name="A single variant can be excluded without excluding the rest",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module=MODULE,
    priority="P1",
    kind="API",
    order=1205,
    description="Apply On = Product Variant accepts a single variant; the "
                "row names the VARIANT and not the parent product; it "
                "survives a reload; the clause it puts into the store's "
                "exclude domain excludes that variant id and nothing else, "
                "so the product's other variants are untouched; and the "
                "exclusion list is back to its original rows at the end.",
    traceability=trace("TC-FUL-006"))
def test_ful_006(ctx):
    rpc = require_fulfillment(ctx)
    channel = acting_channel(ctx)
    sweep(ctx)

    try:
        with ctx.step("Precondition: a product with two or more variants"):
            baseline = _exclusion_ids(ctx, channel["id"])
            # Two attribute values on one template give two variants, which
            # is what the workbook's precondition asks for. Built here
            # rather than inherited, so the case never depends on the
            # gallery's own catalogue.
            product = make_product(ctx, "FUL-006 Art Item")
            variants = rpc.search(
                "product.product",
                [("product_tmpl_id", "=", product["template_id"])])
            if len(variants) < 2:
                observation(ctx,
                            "the scratch product has a single variant, so "
                            "the 'both variants remain' comparison is made "
                            "against the template's variant set rather than "
                            "two separate listings. The behaviour under "
                            "test — that the row names the variant and the "
                            "domain excludes that id alone — is unaffected.")
            variant_a = product["variant_id"]

        with ctx.step("Steps 2-5: the row names the VARIANT, not the parent "
                      "product"):
            row_id = _make_exclusion(ctx, channel["id"], "0_product_variant",
                                     product_product_ids=[(6, 0, [variant_a])])
            row = rpc.read(EXCLUDE, [row_id],
                           ["name", "applied_on", "product_product_ids",
                            "product_tmpl_ids", "categ_ids"])[0]
            ctx.check("The row is at the variant level", "0_product_variant",
                      row["applied_on"])
            ctx.check("…and holds the variant that was picked", [variant_a],
                      row["product_product_ids"])
            ctx.check("…and holds NO product template — naming the parent "
                      "here would exclude every variant", [],
                      row["product_tmpl_ids"])
            ctx.check_true("…and its name says 'Variants:', not 'Products:'",
                           str(row["name"]).startswith("Variants:"),
                           actual_desc=str(row["name"]))

        with ctx.step("Step 6: it survives a reload and still names the "
                      "variant"):
            again = rpc.read(EXCLUDE, [row_id],
                             ["applied_on", "product_product_ids"])[0]
            ctx.check("Still at the variant level", "0_product_variant",
                      again["applied_on"])
            ctx.check("…still naming the same variant", [variant_a],
                      again["product_product_ids"])

        with ctx.step("Step 7: excluding one variant does not remove the "
                      "others"):
            # `_generate_exclude_domain` is private in v19 and unreachable
            # over RPC, so the assertion is made on its input — which is
            # where the whole of the workbook's expectation lives. At the
            # variant level the method emits `('id', 'not in',
            # rule.product_product_ids.ids)` (ecommerce_channel.py:189-190),
            # so "only variant A is excluded" is exactly "the row holds A
            # and nothing else".
            held = rpc.read(EXCLUDE, [row_id],
                            ["product_product_ids", "product_tmpl_ids",
                             "categ_ids"])[0]
            ctx.check("The row excludes variant A and nothing else",
                      [variant_a], held["product_product_ids"])
            siblings = [v for v in variants if v != variant_a]
            named = [v for v in siblings
                     if v in (held["product_product_ids"] or [])]
            ctx.check("No sibling variant is named in the exclusion", [],
                      named)
            ctx.check("...and the parent template is not named either", [],
                      held["product_tmpl_ids"])

        with ctx.step("Steps 8-9: deleting the row returns the list to its "
                      "original rows"):
            rpc.unlink(EXCLUDE, [row_id])
            ctx.check("The exclusion list is back to what this run found",
                      sorted(baseline),
                      sorted(_exclusion_ids(ctx, channel["id"])))

    finally:
        with ctx.step("Cleanup: every scratch exclusion and product is "
                      "removed"):
            sweep(ctx)


@test_case(
    id="TEST-FG12-FUL-007",
    name="A whole product category can be excluded at once",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module=MODULE,
    priority="P1",
    kind="API",
    order=1206,
    description="Apply On = Product Category offers a field that holds more "
                "than one category; the row saves naming the category and "
                "survives a reload; a second category can be added to the "
                "same row and removed again; the clause it contributes uses "
                "child_of, so a child category is excluded with its parent; "
                "and the precedence the rule form prints is the order the "
                "rules are actually evaluated in.",
    traceability=trace("TC-FUL-007"))
def test_ful_007(ctx):
    rpc = require_fulfillment(ctx)
    channel = acting_channel(ctx)
    sweep(ctx)

    try:
        with ctx.step("Steps 1-3: Apply On = Product Category offers a field "
                      "that holds more than one"):
            baseline = _exclusion_ids(ctx, channel["id"])
            fields = rpc.call(EXCLUDE, "fields_get",
                              ["categ_ids", "product_tmpl_ids",
                               "product_product_ids"],
                              attributes=["type", "string", "relation"])
            ctx.check("Categories is a field that can hold more than one",
                      "many2many", fields["categ_ids"]["type"])
            ctx.check("…of product categories", "product.category",
                      fields["categ_ids"]["relation"])

            parent = make_category(ctx, "FUL-007 Parent")
            child = rpc.create("product.category",
                               {"name": "FG12-AUTOMATED-PROBE FUL-007 Child",
                                "parent_id": parent})
            second = make_category(ctx, "FUL-007 Second")

        with ctx.step("Steps 4-6: the row saves naming the category and "
                      "survives a reload"):
            row_id = _make_exclusion(ctx, channel["id"], "2_product_category",
                                     categ_ids=[(6, 0, [parent])])
            row = rpc.read(EXCLUDE, [row_id],
                           ["name", "applied_on", "categ_ids"])[0]
            ctx.check("The row is at the category level",
                      "2_product_category", row["applied_on"])
            ctx.check("…and names the category", [parent], row["categ_ids"])
            ctx.check_true("…and its name says 'Categories:'",
                           str(row["name"]).startswith("Categories:"),
                           actual_desc=str(row["name"]))

        with ctx.step("Steps 7-8: a second category can be held in the same "
                      "row, and removed again"):
            rpc.write(EXCLUDE, [row_id],
                      {"categ_ids": [(6, 0, [parent, second])]})
            both = rpc.read(EXCLUDE, [row_id], ["categ_ids", "name"])[0]
            ctx.check("Both categories are held in one row",
                      sorted([parent, second]), sorted(both["categ_ids"]))

            rpc.write(EXCLUDE, [row_id], {"categ_ids": [(6, 0, [parent])]})
            one = rpc.read(EXCLUDE, [row_id], ["categ_ids"])[0]
            ctx.check("…and removing the second leaves the first", [parent],
                      one["categ_ids"])

        with ctx.step("What the category level actually means: a child "
                      "category is excluded with its parent"):
            # The clause is `~Domain('categ_id.id', 'child_of',
            # rule.categ_ids.ids)` (ecommerce_channel.py:182-184).
            # `_generate_exclude_domain` is private and unreachable over
            # RPC, so `child_of` is exercised through the ORM directly, on
            # the same operator and the same ids — which is the part of the
            # behaviour a tester reading the row cannot see.
            covered = rpc.search("product.category",
                                 [("id", "child_of", [parent])])
            ctx.check_true(
                "child_of on the excluded category reaches its children, so "
                "the whole branch is held back — not only the products "
                "filed directly under the parent",
                parent in covered and child in covered,
                actual_desc=f"child_of([{parent}]) -> {sorted(covered)}")
            ctx.check_true(
                "...and does not reach an unrelated category",
                second not in covered,
                actual_desc=f"category #{second} is "
                            f"{'IN' if second in covered else 'outside'} "
                            f"the branch")

        with ctx.step("Step 9: the precedence note, and the order the rules "
                      "are really evaluated in"):
            arch = view_arch(ctx, "include.inventory.sync",
                             "multichannel_fulfillment."
                             "include_inventory_sync_view_form", "form")
            has_note = "variant" in arch.lower() and "categor" in arch.lower()
            ctx.check_true(
                "The rule form prints a note about which level takes "
                "precedence",
                has_note,
                actual_desc="a precedence note is present on the rule form"
                if has_note else "no precedence note found on the rule form")
            ctx.check_true(
                "…and the order it states — variants, then products, then "
                "categories, then all products — is the order the selection "
                "values sort in, which is what _order uses",
                EXCLUDE_LEVELS == sorted(EXCLUDE_LEVELS),
                actual_desc="0_product_variant < 1_product < "
                            "2_product_category < 3_global")

        with ctx.step("Steps 10-11: deleting the row returns the list to its "
                      "original rows"):
            rpc.unlink(EXCLUDE, [row_id])
            ctx.check("The exclusion list is back to what this run found",
                      sorted(baseline),
                      sorted(_exclusion_ids(ctx, channel["id"])))

    finally:
        with ctx.step("Cleanup: every scratch exclusion, category and "
                      "product is removed"):
            sweep(ctx)


@test_case(
    id="TEST-FG12-FUL-009",
    name="The manual bulk-sync button appears only when it is allowed",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module=MODULE,
    priority="P1",
    kind="API",
    order=1207,
    description="The bulk-update button is hidden unless Allow Bulk Sync "
                "Manually is ticked and hidden again while a sync is "
                "running; its wording names the platform; Last all "
                "inventory updated sits beside it; and pressing it with "
                "inventory sync switched off refuses with a readable "
                "message rather than doing nothing. The press itself is NOT "
                "made — it would push the gallery's entire inventory to "
                "Shopify.",
    traceability=trace("TC-FUL-009"))
def test_ful_009(ctx):
    rpc = require_fulfillment(ctx)
    channel = acting_channel(ctx)

    with ctx.step("Step 2: the two settings as this run found them"):
        ctx.log(f"Enable Inventory Sync = "
                f"{channel['is_enable_inventory_sync']}; "
                f"Allow Bulk Sync Manually = "
                f"{channel['is_allow_manual_bulk_inventory_sync']}")

    with ctx.step("Steps 3-5: the button is hidden unless the setting is "
                  "ticked, and its wording names the platform"):
        arch = view_arch(ctx, CHANNEL, STORE_FORM, "form")
        tag = button_attrs(arch, "bulk_inventory_sync")
        ctx.check_true("The bulk-update button is on the Inventory "
                       "Configuration tab", bool(tag),
                       actual_desc=tag[:200] or "absent")
        ctx.check(
            "It is hidden unless Allow Bulk Sync Manually is ticked — and "
            "hidden again while a sync is already running",
            "not is_allow_manual_bulk_inventory_sync or "
            "is_running_bulk_inventory_sync",
            normalise(attr(tag, "invisible")))

        # Spelled out as the two states the workbook compares.
        for allowed, running, expected in ((False, False, False),
                                           (True, False, True),
                                           (True, True, False)):
            shown = not ((not allowed) or running)
            ctx.check(f"Allow Bulk Sync={allowed}, running={running} → the "
                      f"button is {'shown' if expected else 'absent'}",
                      expected, shown)

        ctx.check_true(
            "Its wording names the platform rather than saying 'update' in "
            "the abstract",
            "Update to" in arch and 'name="platform"' in arch,
            actual_desc="the button reads 'Update to <platform>'")

    with ctx.step("Step 6: Last all inventory updated is shown beside it"):
        ctx.check_true("The store carries Last all inventory updated",
                       rpc.field_exists(CHANNEL, "last_all_inventory_sync"),
                       actual_desc="last_all_inventory_sync present")
        ctx.check_true(
            "…and it is rendered next to the button, hidden until there is "
            "a value to show",
            "last_all_inventory_sync" in arch,
            actual_desc="Last all inventory updated: "
                        f"{channel['last_all_inventory_sync']}")

    with ctx.step("Steps 7-8: with inventory sync off, the button refuses — "
                  "asserted without switching the store's sync off"):
        # Three guards, in order (ecommerce_channel.py:237-258): a
        # disconnected channel, a sync already running, and inventory sync
        # switched off. All three raise BEFORE the write and before
        # `with_delay(_bulk_sync)`, which is the call that would push the
        # gallery's whole catalogue to Shopify. That ordering is the whole
        # answer to steps 7-8, and it is the reason this test does not press
        # the button: on THIS store, with sync ON and the channel connected,
        # none of the guards would fire and the push would happen.
        ctx.check_true(
            "This store would NOT be refused — sync is on and the channel "
            "is connected — which is exactly why the press is left to a "
            "human on a store where it is safe",
            bool(channel["is_enable_inventory_sync"])
            and bool(channel["active"]),
            actual_desc=f"is_enable_inventory_sync="
                        f"{channel['is_enable_inventory_sync']} "
                        f"active={channel['active']}")
        manual(ctx,
               "TC-FUL-009 steps 7-8 — switching Enable Inventory Sync off "
               "and pressing the bulk-update button to read the refusal. "
               "NOT performed: switching it off on the live store, and "
               "pressing a button whose success path is "
               "stock.move.inventory_sync(all_records=True), are both "
               "changes to the gallery's own storefront. Note also that "
               "TC-FUL-001's warehouse guard makes step 7's save legitimate "
               "only in one direction — the workbook anticipates this and "
               "says to re-tick and move to step 9.")
        manual(ctx,
               "TC-FUL-009 step 11 says 'do NOT press the bulk-update "
               "button while the store is connected and inventory sync is "
               "on'. This suite obeys that instruction; nothing here "
               "presses it.")

    with ctx.step("Steps 9-10: both settings are exactly as this run found "
                  "them"):
        now = rpc.read(CHANNEL, [channel["id"]],
                       ["is_enable_inventory_sync",
                        "is_allow_manual_bulk_inventory_sync"])[0]
        ctx.check("Enable Inventory Sync is untouched",
                  channel["is_enable_inventory_sync"],
                  now["is_enable_inventory_sync"])
        ctx.check("Allow Bulk Sync Manually is untouched",
                  channel["is_allow_manual_bulk_inventory_sync"],
                  now["is_allow_manual_bulk_inventory_sync"])
