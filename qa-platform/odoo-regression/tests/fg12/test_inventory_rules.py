"""FG-12 — TC-FUL-001 … TC-FUL-004: which warehouses count, and how much of
their stock reaches the storefront.

Implements the CLIENT MANUAL TESTING GUIDELINE
``MMG_v19_Client_Manual_Testing_Guideline_FG05-FG14_v1.0.xlsx`` / sheet
``Testing Guideline``, cases TC-FUL-001 (P0), TC-FUL-002 (P0), TC-FUL-003
(P0) and TC-FUL-004 (P2).

The number these four cases are really about
--------------------------------------------
Every step that says "reload the listing and read Available" is asking
about one function::

    def calc_available_qty(self, qty):
        res = math.floor(qty * self.percentage_sync / 100.0)
        max_qty_sync = self.max_qty_sync if self.is_max_qty_sync_enabled else inf
        min_qty_sync = self.min_qty_sync if self.is_min_qty_sync_enabled else -inf
        return int(min(max(res, min_qty_sync), max_qty_sync))

— ``multichannel_fulfillment/models/include_inventory_sync.py:158-166``.
The listing's *Available* column is that function's result carried through
``product.channel.variant._compute_free_qty``
(``product_channel_variant.py:57-80``). So the workbook's arithmetic is
asserted directly against it, on rules scoped to a scratch product, and the
workbook's own worked numbers are used: 20 on hand at 50% is 10, at 10% is
2, capped at 5 it is 5 whatever the percentage, floored at 8 it is 8.

The refusals — 0%, 150%, a maximum of 0, a negative minimum, a minimum
above the maximum — are the other half, and each is checked twice: on the
message, and on whether a rule survived. A guard that raises but leaves the
row behind is as much a failure as one that accepts silently.
"""
from __future__ import annotations

from adapters.base import OdooRPCError
from framework.registry import test_case

from .common import (CHANNEL, INCLUDE, INCLUDE_LABELS, INCLUDE_LEVELS,
                     INVENTORY_SETTINGS, MODULE, MSG_MAXIMUM, MSG_MINIMUM,
                     MSG_MIN_BELOW_MAX, MSG_NO_WAREHOUSE, MSG_PERCENTAGE,
                     WORKFLOW, WORKFLOW_NAME, acting_channel, calc,
                     field_attrs, finding, leftover_rules, make_product,
                     make_rule, manual, observation, require_fulfillment,
                     sweep, trace, try_rule, view_arch)

STORE_FORM = "omni_manage_channel.view_ecommerce_channel_form_settings"

#: The workbook's worked example: 20 on hand.
ON_HAND = 20.0


@test_case(
    id="TEST-FG12-FUL-001",
    name="Only the chosen warehouses count towards published stock",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module=MODULE,
    priority="P0",
    kind="API",
    order=1200,
    description="The Inventory Sync Settings are all present on the store; "
                "the warehouse list is restricted by domain to the "
                "gallery's own company; and saving with inventory sync on "
                "and NO warehouse ticked is refused with a readable "
                "message. The refusal is probed against the live store and "
                "the setting is read back afterwards to prove nothing was "
                "cleared.",
    traceability=trace("TC-FUL-001"))
def test_ful_001(ctx):
    rpc = require_fulfillment(ctx)
    channel = acting_channel(ctx)
    ctx.log(f"store {channel['name']!r} ({channel['platform']}) — "
            f"inventory sync {'ON' if channel['is_enable_inventory_sync'] else 'OFF'}")

    with ctx.step("Steps 1-3: the Inventory Sync Settings group, and the "
                  "help text beside Enable Inventory Sync"):
        fields = rpc.call(CHANNEL, "fields_get", list(INVENTORY_SETTINGS),
                          attributes=["string", "type", "help", "domain"])
        missing = [name for name in INVENTORY_SETTINGS if name not in fields]
        ctx.check("Every Inventory Sync setting the workbook walks is on "
                  "the store", [], missing)
        ctx.check("Enable Inventory Sync is labelled as the workbook reads "
                  "it", "Enable Inventory Sync",
                  fields["is_enable_inventory_sync"]["string"])
        ctx.check("Warehouses to Sync Inventory is labelled as the workbook "
                  "reads it", "Warehouses to Sync Inventory",
                  fields["active_warehouse_ids"]["string"])

        help_text = rpc.read(CHANNEL, [channel["id"]],
                             ["inventory_help_text"])[0]["inventory_help_text"]
        ctx.check_true("There is help text beside Enable Inventory Sync",
                       bool(help_text), actual_desc=str(help_text)[:160])

    with ctx.step("Step 4: the warehouses currently ticked — written down "
                  "so the run can prove it put them back"):
        warehouses = channel["active_warehouse_ids"] or []
        rows = rpc.read("stock.warehouse", warehouses,
                        ["name", "code", "company_id"]) if warehouses else []
        ctx.log("ticked warehouses: " + (", ".join(
            f"{row['name']} ({row['code']})" for row in rows) or "none"))
        ctx.check_true("At least one warehouse is ticked, which is what "
                       "makes the store's published stock meaningful",
                       bool(warehouses), actual_desc=str(warehouses))

    with ctx.step("Step 9: the warehouse list offers only the gallery's own "
                  "company's warehouses"):
        domain = fields["active_warehouse_ids"].get("domain")
        ctx.check_true(
            "Warehouses to Sync Inventory is restricted to the store's own "
            "company",
            "company_id" in str(domain),
            actual_desc=str(domain))

        company_id = (channel["company_id"][0]
                      if isinstance(channel["company_id"], (list, tuple))
                      else channel["company_id"])
        foreign = [row for row in rows
                   if (row["company_id"][0]
                       if isinstance(row["company_id"], (list, tuple))
                       else row["company_id"]) != company_id]
        ctx.check("No ticked warehouse belongs to another company", [],
                  [row["name"] for row in foreign])

        all_warehouses = rpc.search_read("stock.warehouse", [],
                                         ["name", "company_id"])
        if len(all_warehouses) == 1:
            observation(ctx,
                        "this database holds one warehouse only, so "
                        "TC-FUL-001's multi-warehouse steps are N/A — the "
                        "workbook says to mark them so rather than raise "
                        "them.")

    with ctx.step("Steps 7-8 / Expected line 2: saving with inventory sync "
                  "ON and NO warehouse ticked is REFUSED"):
        # This is the one write this suite makes to the live store, and it
        # is a write that must fail. `check_active_warehouses`
        # (ecommerce_channel.py:66-76) is an @api.constrains, so a refusal
        # rolls the whole write back and the store is untouched. If the
        # guard has been lost in the port, the write lands — and this is the
        # case that exists to catch that, so the setting is read back and
        # restored explicitly rather than trusted.
        before = rpc.read(CHANNEL, [channel["id"]],
                          ["active_warehouse_ids",
                           "is_enable_inventory_sync"])[0]
        error = ""
        try:
            rpc.write(CHANNEL, [channel["id"]],
                      {"is_enable_inventory_sync": True,
                       "active_warehouse_ids": [(5, 0, 0)]})
        except OdooRPCError as exc:
            error = str(exc)
        after = rpc.read(CHANNEL, [channel["id"]],
                         ["active_warehouse_ids",
                          "is_enable_inventory_sync"])[0]

        # Restore FIRST, then assert. If the guard has gone, the write
        # landed, and an assertion that fails before the restore would leave
        # the gallery's store syncing inventory with no warehouse scope.
        # Putting the restore ahead of every check makes that impossible
        # whatever any assertion below does.
        if (sorted(after["active_warehouse_ids"] or [])
                != sorted(before["active_warehouse_ids"] or [])
                or after["is_enable_inventory_sync"]
                != before["is_enable_inventory_sync"]):
            rpc.write(CHANNEL, [channel["id"]], {
                "active_warehouse_ids": [
                    (6, 0, before["active_warehouse_ids"] or [])],
                "is_enable_inventory_sync":
                    before["is_enable_inventory_sync"],
            })
            restored = rpc.read(CHANNEL, [channel["id"]],
                                ["active_warehouse_ids",
                                 "is_enable_inventory_sync"])[0]
            ctx.log(f"the write landed and has been reversed: "
                    f"{after} -> {restored}")
            finding(ctx,
                    "the guard at "
                    "multichannel_fulfillment/models/ecommerce_channel.py:"
                    "66-76 did not fire. It is a v15 constraint the 18.0 "
                    "branch dropped and the port deliberately restored — "
                    "without it, _get_syncing_warehouses() returns an empty "
                    "recordset and the per-warehouse scoping collapses into "
                    "publishing something arbitrary. The store's warehouse "
                    "list has been restored by this test.")

        ctx.check_true(
            "Clearing every warehouse while inventory sync is on is refused",
            bool(error),
            actual_desc=error or "THE WRITE WAS ACCEPTED — the store now "
                                 "syncs inventory with no warehouse scope")
        ctx.check_true(
            "…with the readable message the workbook asks for",
            MSG_NO_WAREHOUSE in error,
            actual_desc=error[:240])
        ctx.check("The store's warehouses are exactly as they were",
                  sorted(before["active_warehouse_ids"] or []),
                  sorted(after["active_warehouse_ids"] or []))
        ctx.check("…and Enable Inventory Sync is as it was",
                  before["is_enable_inventory_sync"],
                  after["is_enable_inventory_sync"])

    with ctx.step("Steps 10-11: Allow Bulk Sync Manually and Last all "
                  "inventory updated are readable, and nothing was changed"):
        now = rpc.read(CHANNEL, [channel["id"]],
                       list(INVENTORY_SETTINGS))[0]
        ctx.check("Allow Bulk Sync Manually is as this run found it",
                  channel["is_allow_manual_bulk_inventory_sync"],
                  now["is_allow_manual_bulk_inventory_sync"])
        ctx.check("Enable Inventory Sync is as this run found it",
                  channel["is_enable_inventory_sync"],
                  now["is_enable_inventory_sync"])
        ctx.check("The ticked warehouses are as this run found them",
                  sorted(channel["active_warehouse_ids"] or []),
                  sorted(now["active_warehouse_ids"] or []))
        ctx.log("Last all inventory updated: "
                f"{now['last_all_inventory_sync']}")

    manual(ctx,
           "TC-FUL-001 steps 5 and 10 as the workbook words them — ticking "
           "the values off against Novobi's FG-08 TC-CHN-001 printout. This "
           "run records what the store holds; only the printout can say "
           "whether those are the intended values.")


@test_case(
    id="TEST-FG12-FUL-002",
    name="A percentage rule holds back stock from the storefront",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module=MODULE,
    priority="P0",
    kind="API",
    order=1201,
    description="Apply On offers all four levels; a 50% rule on 20 on hand "
                "publishes 10 and a 10% rule publishes 2, computed by the "
                "function the listing's Available column reads; 0% and 150% "
                "are both refused with the message naming 0.01 to 100 and "
                "leave no rule behind; and deleting the rule puts the "
                "number back. Rules are scoped to a scratch product variant "
                "so they can never match one of the gallery's items.",
    traceability=trace("TC-FUL-002"))
def test_ful_002(ctx):
    rpc = require_fulfillment(ctx)
    channel = acting_channel(ctx)
    sweep(ctx)
    product = None

    try:
        with ctx.step("Step 1: the figure the listing starts from"):
            baseline = rpc.search_read(
                INCLUDE, [("channel_id", "=", channel["id"])],
                ["applied_on", "percentage_sync", "is_max_qty_sync_enabled",
                 "max_qty_sync", "is_min_qty_sync_enabled", "min_qty_sync",
                 "name"], order="applied_on, percentage_sync, id desc")
            ctx.log(f"the store's existing rules ({len(baseline)}): "
                    + "; ".join(f"{r['name']} @{r['percentage_sync']}%"
                                for r in baseline))
            ctx.check_true(
                "The store already has at least one rule — the model "
                "requires it, and this run must leave that untouched",
                bool(baseline), actual_desc=f"{len(baseline)} rule(s)")

            product = make_product(ctx, "FUL-002 Art Item")

        with ctx.step("Steps 2-4: Apply On offers all four levels"):
            fields = rpc.call(INCLUDE, "fields_get",
                              ["applied_on", "percentage_sync"],
                              attributes=["selection", "string", "help"])
            values = [value for value, _ in fields["applied_on"]["selection"]]
            ctx.check("Apply On offers all products, a category, a product "
                      "and a variant", sorted(INCLUDE_LEVELS), sorted(values))
            ctx.check("…labelled as the workbook reads them", INCLUDE_LABELS,
                      dict(fields["applied_on"]["selection"]))

        with ctx.step("Steps 5-9 / Expected line 2: at 50% of 20 the "
                      "storefront is told 10"):
            rule_id = make_rule(ctx, channel["id"], product,
                                percentage_sync=50.0)
            published = calc(ctx, rule_id, ON_HAND)
            ctx.check("50% of 20 on hand publishes 10 — 'about half the "
                      "on-hand figure, around 10 from 20'", 10, published)

        with ctx.step("Step 10 / Expected line 3: at 10% it drops to 2"):
            rpc.write(INCLUDE, [rule_id], {"percentage_sync": 10.0})
            published = calc(ctx, rule_id, ON_HAND)
            ctx.check("10% of 20 on hand publishes 2", 2, published)
            ctx.check_true(
                "The number moved when the percentage moved — the workbook "
                "says a number that never moves is the FAIL",
                published != 10, actual_desc=f"50% -> 10, 10% -> {published}")

        with ctx.step("Steps 11-12 / Expected line 4: 0 and 150 are both "
                      "REFUSED, and leave no rule behind"):
            for attempt in (0.0, 150.0):
                error = ""
                try:
                    rpc.write(INCLUDE, [rule_id],
                              {"percentage_sync": attempt})
                except OdooRPCError as exc:
                    error = str(exc)
                current = rpc.read(INCLUDE, [rule_id],
                                   ["percentage_sync"])[0]["percentage_sync"]
                ctx.check_true(f"A Quantity Sync of {attempt:g} is refused",
                               bool(error),
                               actual_desc=error or "THE WRITE WAS ACCEPTED")
                ctx.check_true(
                    "…with the message naming 0.01% to 100.00%",
                    MSG_PERCENTAGE in error, actual_desc=error[:240])
                ctx.check(f"…and the rule still holds its last valid value "
                          f"after the {attempt:g} attempt", 10.0, current)

            # And the boundaries themselves must be ACCEPTED, or the guard
            # is too strict rather than correct.
            for boundary in (0.01, 100.0):
                rpc.write(INCLUDE, [rule_id], {"percentage_sync": boundary})
                current = rpc.read(INCLUDE, [rule_id],
                                   ["percentage_sync"])[0]["percentage_sync"]
                ctx.check(f"{boundary}% — a stated boundary — is allowed",
                          boundary, current)

        with ctx.step("Steps 13-14: deleting the rule puts the number back"):
            rpc.write(INCLUDE, [rule_id], {"percentage_sync": 100.0})
            rpc.unlink(INCLUDE, [rule_id])
            ctx.check("The rule is gone", 0,
                      rpc.call(INCLUDE, "search_count", [("id", "=", rule_id)]))
            after = rpc.search_read(
                INCLUDE, [("channel_id", "=", channel["id"])],
                ["name", "percentage_sync"],
                order="applied_on, percentage_sync, id desc")
            ctx.check("The store's own rules are exactly as they were",
                      [(r["name"], r["percentage_sync"]) for r in baseline],
                      [(r["name"], r["percentage_sync"]) for r in after])

        with ctx.step("Step 7: the precedence the rules are evaluated in"):
            # `_order = 'applied_on asc, percentage_sync asc, id desc'` and
            # `get_first_matching_rule_for_product` re-sorts by the same key
            # (include_inventory_sync.py:18, 118-124), so the numeric
            # prefixes on the selection values ARE the precedence: variant
            # first, then product, then category, then all products.
            ctx.check_true(
                "The Apply On values sort variant, product, category, all "
                "products — which is the precedence _order encodes",
                INCLUDE_LEVELS == sorted(INCLUDE_LEVELS),
                actual_desc=str(INCLUDE_LEVELS))
            manual(ctx,
                   "TC-FUL-002 steps 1, 9, 10 and 14 as the workbook words "
                   "them — reading Available off the product's listing. "
                   "That figure is product.channel.variant.free_qty, which "
                   "needs a listing, and a listing is created by importing "
                   "from the store. This run asserts the function behind "
                   "the number (calc_available_qty) on a scratch product "
                   "instead; a human should confirm once, on a real "
                   "listing, that the column moves with it.")

    finally:
        with ctx.step("Cleanup: every scratch rule and product is removed"):
            sweep(ctx)
            ctx.check("No rule this test created is left on the store", [],
                      leftover_rules(ctx, channel["id"]))


@test_case(
    id="TEST-FG12-FUL-003",
    name="Maximum and minimum caps override the percentage",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module=MODULE,
    priority="P0",
    kind="API",
    order=1202,
    description="100% of 20 capped at 5 publishes 5; 50% of 20 capped at 5 "
                "still publishes 5 — the cap wins; 10% of 20 with a floor "
                "of 8 publishes 8 — the floor wins; a maximum of 0 and a "
                "negative minimum are both refused with their own messages; "
                "and the rules list shows the percentage, the maximum and "
                "the minimum in their own columns.",
    traceability=trace("TC-FUL-003"))
def test_ful_003(ctx):
    rpc = require_fulfillment(ctx)
    channel = acting_channel(ctx)
    sweep(ctx)

    try:
        product = make_product(ctx, "FUL-003 Art Item")

        with ctx.step("Steps 2-3 / Test A: 100% capped at 5 publishes 5, "
                      "not 20"):
            rule_id = make_rule(ctx, channel["id"], product,
                                percentage_sync=100.0,
                                is_max_qty_sync_enabled=True, max_qty_sync=5)
            ctx.check("100% of 20 on hand, capped at 5 — the cap wins", 5,
                      calc(ctx, rule_id, ON_HAND))

        with ctx.step("Steps 4-5 / Test B: 50% capped at 5 still publishes "
                      "5, not 10"):
            rpc.write(INCLUDE, [rule_id], {"percentage_sync": 50.0})
            ctx.check("50% of 20 on hand, capped at 5 — the cap still wins",
                      5, calc(ctx, rule_id, ON_HAND))

        with ctx.step("Steps 6-7 / Test C: 10% with a floor of 8 publishes "
                      "at least 8, not 2"):
            rpc.write(INCLUDE, [rule_id],
                      {"is_max_qty_sync_enabled": False, "max_qty_sync": 0,
                       "percentage_sync": 10.0,
                       "is_min_qty_sync_enabled": True, "min_qty_sync": 8})
            published = calc(ctx, rule_id, ON_HAND)
            ctx.check("10% of 20 on hand, floored at 8 — the floor wins", 8,
                      published)
            ctx.check_true("…which is more than the percentage alone would "
                           "have published", published > 2,
                           actual_desc=f"{published} > 2")

        with ctx.step("Step 8: a Maximum Quantity of 0 is refused"):
            error = ""
            try:
                rpc.write(INCLUDE, [rule_id],
                          {"is_max_qty_sync_enabled": True,
                           "max_qty_sync": 0})
            except OdooRPCError as exc:
                error = str(exc)
            ctx.check_true("A maximum of 0 is refused", bool(error),
                           actual_desc=error or "THE WRITE WAS ACCEPTED")
            ctx.check_true("…with a message saying it must be greater than "
                           "zero", MSG_MAXIMUM in error,
                           actual_desc=error[:240])
            current = rpc.read(INCLUDE, [rule_id],
                               ["is_max_qty_sync_enabled", "max_qty_sync"])[0]
            ctx.check("…and the rule did not take the value", False,
                      bool(current["is_max_qty_sync_enabled"]
                           and current["max_qty_sync"] == 0))

        with ctx.step("Step 9: a negative Minimum Quantity is refused"):
            error = ""
            try:
                rpc.write(INCLUDE, [rule_id], {"min_qty_sync": -1})
            except OdooRPCError as exc:
                error = str(exc)
            ctx.check_true("A negative minimum is refused", bool(error),
                           actual_desc=error or "THE WRITE WAS ACCEPTED")
            ctx.check_true("…with its own message",
                           MSG_MINIMUM in error, actual_desc=error[:240])
            ctx.check("…and the minimum is unchanged", 8,
                      rpc.read(INCLUDE, [rule_id],
                               ["min_qty_sync"])[0]["min_qty_sync"])

        with ctx.step("Step 10: the rules list shows the percentage, the "
                      "maximum and the minimum in their own columns"):
            arch = view_arch(ctx, INCLUDE,
                             "multichannel_fulfillment."
                             "include_inventory_sync_view_tree", "list")
            for name in ("percentage_sync", "max_qty_sync_display",
                         "min_qty_sync_display"):
                ctx.check_true(f"{name!r} is a column on the rules list",
                               bool(field_attrs(arch, name)),
                               actual_desc=field_attrs(arch, name)[:160]
                               or "absent")

        with ctx.step("Step 11: deleting the rule puts everything back"):
            rpc.unlink(INCLUDE, [rule_id])
            ctx.check("The rule is gone", 0,
                      rpc.call(INCLUDE, "search_count",
                               [("id", "=", rule_id)]))

    finally:
        with ctx.step("Cleanup: every scratch rule and product is removed"):
            sweep(ctx)
            ctx.check("No rule this test created is left on the store", [],
                      leftover_rules(ctx, channel["id"]))


@test_case(
    id="TEST-FG12-FUL-004",
    name="A minimum above the maximum is refused",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module=MODULE,
    priority="P2",
    kind="API",
    order=1203,
    description="Minimum 10 with Maximum 5 is refused with a message saying "
                "the minimum must be less than the maximum and leaves no "
                "rule behind; Minimum 5 with Maximum 10 saves without "
                "complaint; and whether equal values are allowed is "
                "recorded either way — the workbook says either answer is "
                "acceptable, Novobi needs to know which.",
    traceability=trace("TC-FUL-004"))
def test_ful_004(ctx):
    rpc = require_fulfillment(ctx)
    channel = acting_channel(ctx)
    sweep(ctx)

    try:
        product = make_product(ctx, "FUL-004 Art Item")

        with ctx.step("Steps 3-4 / Attempt A: Minimum 10, Maximum 5 is "
                      "REFUSED"):
            attempt = try_rule(ctx, channel["id"], product,
                               is_max_qty_sync_enabled=True, max_qty_sync=5,
                               is_min_qty_sync_enabled=True, min_qty_sync=10)
            ctx.check_true("An impossible rule is refused",
                           bool(attempt["error"]),
                           actual_desc=attempt["error"]
                           or "THE RULE WAS CREATED")
            ctx.check_true(
                "…with a readable message saying the minimum must be less "
                "than the maximum",
                MSG_MIN_BELOW_MAX in attempt["error"],
                actual_desc=attempt["error"][:240])
            ctx.log(f"message in full: {attempt['error']}")
            ctx.check_true("…and no rule was left behind",
                           not attempt["leaked"],
                           actual_desc=f"{attempt['before']} -> "
                                       f"{attempt['after']} rules on the "
                                       f"store")

        with ctx.step("Steps 5-6 / Attempt B: Minimum 5, Maximum 10 saves "
                      "without complaint"):
            attempt = try_rule(ctx, channel["id"], product,
                               is_max_qty_sync_enabled=True, max_qty_sync=10,
                               is_min_qty_sync_enabled=True, min_qty_sync=5)
            ctx.check_true("A sensible rule saves", not attempt["error"],
                           actual_desc=attempt["error"] or "saved")
            rule_id = attempt["rule_id"]
            ctx.check_true("…and it is there when read back",
                           bool(rpc.call(INCLUDE, "search_count",
                                         [("id", "=", rule_id)])),
                           actual_desc=f"rule #{rule_id}")
            # And it behaves: 100% of 20 clamped into [5, 10] is 10.
            ctx.check("…and it clamps as its values say it should", 10,
                      calc(ctx, rule_id, ON_HAND))

        with ctx.step("Step 7 / Attempt C: equal values — recorded either "
                      "way, because the workbook accepts either answer"):
            error = ""
            try:
                rpc.write(INCLUDE, [rule_id],
                          {"min_qty_sync": 5, "max_qty_sync": 5})
            except OdooRPCError as exc:
                error = str(exc)
            allowed = not error
            current = rpc.read(INCLUDE, [rule_id],
                               ["min_qty_sync", "max_qty_sync"])[0]
            ctx.check_true(
                "The system gave a definite answer on equal minimum and "
                "maximum — it neither half-saved nor failed obscurely",
                (allowed and current["min_qty_sync"] == 5
                 and current["max_qty_sync"] == 5)
                or (not allowed and MSG_MIN_BELOW_MAX in error),
                actual_desc=("ALLOWED — a rule with Minimum 5 and Maximum 5 "
                             "saves" if allowed
                             else f"REFUSED — {error[:200]}"))
            observation(ctx,
                        "Novobi's answer to TC-FUL-004 step 7: equal "
                        "minimum and maximum are "
                        + ("ALLOWED" if allowed else "REFUSED")
                        + ". The guard is `min_qty_sync >= max_qty_sync and "
                          "max_qty_sync and min_qty_sync` "
                          "(include_inventory_sync.py:126-129), so equal "
                          "non-zero values are refused and a zero on either "
                          "side short-circuits the check.")

        with ctx.step("Steps 8-9: no impossible rule exists, and the test "
                      "rule is deleted"):
            impossible = rpc.search_read(
                INCLUDE,
                [("channel_id", "=", channel["id"]),
                 ("is_min_qty_sync_enabled", "=", True),
                 ("is_max_qty_sync_enabled", "=", True)],
                ["name", "min_qty_sync", "max_qty_sync"])
            broken = [row for row in impossible
                      if row["min_qty_sync"] > row["max_qty_sync"]]
            ctx.check("No rule on the store holds a minimum above its "
                      "maximum", [], broken)

    finally:
        with ctx.step("Cleanup: every scratch rule and product is removed"):
            sweep(ctx)
            ctx.check("No rule this test created is left on the store", [],
                      leftover_rules(ctx, channel["id"]))
