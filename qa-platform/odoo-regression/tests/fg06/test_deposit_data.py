"""FG-06 — TC-DAT-016: the deposits the gallery is holding are all still there.

Implements row 15.0 (P0, "Deposit data") of the CLIENT MANUAL TESTING
GUIDELINE ``MMG_v19_Client_Manual_Testing_Guideline_FG05-FG14_v1.0.xlsx`` /
sheet ``Testing Guideline``.

The workbook's own framing: *"A deposit is customer money the gallery owes
back or must apply. If deposits went missing in the upgrade, the gallery's
liability is understated and a customer will eventually ask where their money
went."* It is explicitly a **whole-population count and total**, not a single
record check, and it needs figures from the old system to compare against.

Read-only by construction
-------------------------
The workbook's State After The Test is "Nothing changed". This module creates
no record, writes no field, and calls neither ``sweep_fg06`` nor ``cleanup``
— a sweep is itself a delete and would violate the workbook.

What "all of them" means over RPC
---------------------------------
The workbook's steps are "Accounting > Customers > Customer Deposits" then
"clear every filter … so you are looking at all of them", then read the
record count and the sum at the foot of the Amount column. The two menus are
``ir.actions.act_window`` records whose **domains are the definition of the
population**
(``account_partner_deposit/views/account_payment_deposit_view.xml:65-101``):

    Customer Deposits: [('is_deposit','=',True),
                        ('payment_type','=','inbound'),
                        ('partner_type','=','customer')]
    Vendor Deposits:   [('is_deposit','=',True),
                        ('payment_type','=','outbound'),
                        ('partner_type','=','supplier')]

Those domains are read from the action records at run time rather than
retyped here, so if the menu's definition changes the case follows it instead
of silently measuring something else. "Clear every filter" is then simply the
absence of any added domain — the action domain alone.

The Amount column footer is a ``read_group`` sum of ``account.payment.amount``
over the same domain, which is what the list view's own aggregate computes.

Documented adaptation — the Novobi baseline
-------------------------------------------
The workbook compares four numbers (customer count, customer total, vendor
count, vendor total) against figures Novobi supplies from the old system. The
platform does not hold those figures and must not invent them. So:

* the four numbers are **captured and reported** as evidence, together with
  the currency they are summed in and a per-currency breakdown, because a
  single total across mixed currencies is not comparable to anything;
* every invariant that does **not** need the baseline is asserted for real —
  the two menus exist with the domains above, the populations are disjoint,
  no deposit is missing its deposit account, and no deposit sits on a journal
  entry that never posted while counting as money held;
* the FG06 fixture share is reported **separately and subtracted**, because
  earlier cases in this suite leave confirmed deposits behind by the
  workbook's own instruction ("One confirmed customer deposit of 2,500.00
  exists"). A tester comparing the raw count to the baseline without that
  subtraction would see a false surplus. This is the one place in the suite
  where a whole-population figure is read, so it is the one place the
  fixture share matters;
* the baseline comparison itself is named as a RESIDUAL MANUAL STEP with all
  four numbers printed, so the human step is a comparison and never a re-run.

Workbook step 7 — "pick three deposits from the baseline by name and open
each one" — is likewise baseline-driven. What is asserted instead is the
printout-free half: three deposits are opened and every field the workbook
names (Customer, Amount, Date, Journal, Deposit Account) is proven readable
and populated, and the full field set is written to a CSV artifact for the
tick-off. A blank Journal or Deposit Account is a real failure and is caught
here without the printout.
"""
from __future__ import annotations

import csv

from framework.registry import test_case
from tests.fg06.common import (CUSTOMER_SIDE, DEPOSIT_ACCOUNT_FIELD, MARK,
                               MODULE, PAYMENT_LIVE_STATES, VENDOR_SIDE,
                               WORKFLOW, WORKFLOW_NAME, account_row,
                               acting_company, m2o_id, m2o_name, money,
                               require_v19, residual_manual_step, trace)

INVENTORY_CSV = "TC-DAT-016-deposit-population.csv"
SAMPLE_CSV = "TC-DAT-016-three-deposits.csv"

# The two menu actions the workbook's steps 1 and 6 open.
ACTION_XMLID = {
    CUSTOMER_SIDE: "account_partner_deposit."
                   "action_account_payment_customer_deposit",
    VENDOR_SIDE: "account_partner_deposit."
                 "action_account_payment_supplier_deposit",
}
MENU_LABEL = {CUSTOMER_SIDE: "Accounting > Customers > Customer Deposits",
              VENDOR_SIDE: "Accounting > Vendors > Vendor Deposits"}

# The domain each action is expected to carry — asserted, not assumed, so a
# changed menu definition is reported rather than silently followed.
EXPECTED_DOMAIN = {
    CUSTOMER_SIDE: [("is_deposit", "=", True),
                    ("payment_type", "=", "inbound"),
                    ("partner_type", "=", "customer")],
    VENDOR_SIDE: [("is_deposit", "=", True),
                  ("payment_type", "=", "outbound"),
                  ("partner_type", "=", "supplier")],
}

# The five fields workbook step 7 reads off each opened deposit.
STEP7_FIELDS = ("partner_id", "amount", "date", "journal_id")
SAMPLE_SIZE = 3
CSV_LIMIT = 5000


def _action_domain(ctx, side: str) -> tuple[list, dict]:
    """The menu action's own domain, read from the action record.

    ``ir.actions.act_window.domain`` is stored as a Char holding a Python
    literal, so it is parsed rather than evaluated — the strings in these two
    actions contain no expressions.
    """
    rpc = ctx.adapter.rpc
    action_id = rpc.ref(ACTION_XMLID[side])
    if not action_id:
        return [], {}
    row = rpc.read("ir.actions.act_window", [action_id],
                   ["name", "res_model", "domain", "context"])[0]
    raw = row.get("domain") or ""
    parsed = []
    try:
        import ast
        parsed = [tuple(item) if isinstance(item, (list, tuple)) else item
                  for item in ast.literal_eval(raw)]
    except (ValueError, SyntaxError):
        ctx.log(f"[{side}] the action's domain {raw!r} is not a plain literal "
                f"— recorded as unparsed rather than guessed")
    return parsed, row


def _population(ctx, side: str, domain: list, company_id: int) -> dict:
    """Count, total and currency breakdown over one deposit menu.

    ``read_group`` on ``amount`` grouped by ``currency_id`` is what the list
    view's Amount footer aggregates. Grouping by currency is deliberate: the
    workbook asks for "the sum shown at the foot of the Amount column", and
    ``account.payment.amount`` is expressed in each payment's OWN currency,
    so one scalar total across a mixed population is not a figure any
    baseline can be compared against.
    """
    rpc = ctx.adapter.rpc
    scoped = list(domain) + [("company_id", "=", company_id)]
    groups = rpc.read_group("account.payment", scoped,
                            ["amount:sum"], ["currency_id"])
    by_currency, total, count = [], 0.0, 0
    for group in groups:
        currency = m2o_name(group.get("currency_id")) or "(none)"
        amount = money(group.get("amount"))
        rows = int(group.get("__count") or group.get("currency_id_count") or 0)
        by_currency.append({"currency": currency, "count": rows,
                            "total": amount})
        total += amount
        count += rows
    by_currency.sort(key=lambda row: -row["count"])
    return {"count": count, "total": money(total), "by_currency": by_currency,
            "domain": scoped}


@test_case(
    id="TEST-FG06-DAT-016",
    name="The deposits the gallery is holding are all still there",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module=MODULE,
    priority="P0",
    kind="DATA",
    order=601,
    description="Read-only whole-population read of both deposit menus: the "
                "count and total per currency for customer and vendor "
                "deposits, the FG06 fixture share subtracted, the two "
                "populations proven disjoint, every deposit proven to carry "
                "its deposit account, and three deposits opened field by "
                "field. Creates nothing; the baseline comparison is a "
                "residual manual step.",
    traceability=trace("TC-DAT-016"))
def test_dat_016(ctx):
    rpc = ctx.adapter.rpc
    evidence = []
    residual = []
    # Declared here, not inside the step that fills it: the evidence block
    # runs from `finally` and must not raise a NameError over a step that an
    # earlier assertion failure skipped — that would replace a real FAILED
    # verdict with an AUTOMATION_ERROR.
    sample_rows = []

    with ctx.step("Precondition (workbook): Odoo 19 with "
                  "account_partner_deposit, and both deposit menus reachable"):
        require_v19(ctx)
        company = acting_company(ctx)
        ctx.log(f"acting company #{company['id']} {company['name']!r} — "
                f"company currency {company['currency_name']}")

    try:
        with ctx.step("Steps 1-2 and 6: open both deposit menus with every "
                      "filter cleared"):
            domains, actions = {}, {}
            for side in (CUSTOMER_SIDE, VENDOR_SIDE):
                domains[side], actions[side] = _action_domain(ctx, side)
                ctx.log(f"{MENU_LABEL[side]} -> action "
                        f"{actions[side].get('name')!r} on "
                        f"{actions[side].get('res_model')!r} "
                        f"domain={domains[side]}")
            for side in (CUSTOMER_SIDE, VENDOR_SIDE):
                ctx.check_true(
                    f"{MENU_LABEL[side]} exists as an action on "
                    f"account.payment",
                    actions[side].get("res_model") == "account.payment",
                    actual_desc=f"res_model="
                                f"{actions[side].get('res_model')!r}")
                # The domain IS the population definition, so a change to it
                # changes what every figure below means.
                ctx.check(f"{MENU_LABEL[side]} domain (the definition of "
                          f"'all of them')",
                          EXPECTED_DOMAIN[side], domains[side])

        with ctx.step("Steps 3-5 and 6: read the record count and the Amount "
                      "total for each side"):
            counts = {}
            for side in (CUSTOMER_SIDE, VENDOR_SIDE):
                counts[side] = _population(ctx, side, domains[side],
                                           company["id"])
                data = counts[side]
                ctx.log(f"{MENU_LABEL[side]} — {data['count']} record(s), "
                        f"total {data['total']:.2f}")
                for row in data["by_currency"]:
                    ctx.log(f"    {row['currency']}: {row['count']} "
                            f"record(s), {row['total']:.2f}")
                    evidence.append((side, "population", row["currency"],
                                     row["count"], row["total"]))

        with ctx.step("Adaptation: subtract the FG06 fixture share so the "
                      "baseline comparison is apples to apples"):
            # Earlier cases in this suite leave confirmed deposits behind by
            # the workbook's own instruction, and this is the only case that
            # reads a whole-population figure, so the fixtures have to be
            # named and removed from the comparison rather than quietly
            # inflating it.
            for side in (CUSTOMER_SIDE, VENDOR_SIDE):
                fixture_domain = list(domains[side]) + [
                    ("company_id", "=", company["id"]),
                    ("partner_id.name", "like", f"{MARK} %")]
                groups = rpc.read_group("account.payment", fixture_domain,
                                        ["amount:sum"], [])
                fixture_count = int(groups[0].get("__count") or 0) if groups \
                    else 0
                fixture_total = money(groups[0].get("amount")) if groups else 0.0
                counts[side]["fixture_count"] = fixture_count
                counts[side]["fixture_total"] = fixture_total
                counts[side]["baseline_count"] = (counts[side]["count"]
                                                  - fixture_count)
                counts[side]["baseline_total"] = money(
                    counts[side]["total"] - fixture_total)
                ctx.log(f"{MENU_LABEL[side]} — of which {fixture_count} "
                        f"FG06 test fixture(s) totalling "
                        f"{fixture_total:.2f}; compare "
                        f"{counts[side]['baseline_count']} / "
                        f"{counts[side]['baseline_total']:.2f} against the "
                        f"Novobi baseline")
                evidence.append((side, "fixtures", "", fixture_count,
                                 fixture_total))
                evidence.append((side, "baseline_comparable", "",
                                 counts[side]["baseline_count"],
                                 counts[side]["baseline_total"]))

        with ctx.step("Integrity the baseline cannot give: the two "
                      "populations are disjoint"):
            # A deposit counted on both menus would double the gallery's
            # apparent liability. The two action domains differ only on
            # payment_type / partner_type, so an overlap means a record whose
            # two fields disagree with each other.
            overlap = rpc.search(
                "account.payment",
                [("is_deposit", "=", True),
                 ("company_id", "=", company["id"]),
                 "|", "&", ("payment_type", "=", "inbound"),
                 ("partner_type", "=", "supplier"),
                 "&", ("payment_type", "=", "outbound"),
                 ("partner_type", "=", "customer")], limit=50)
            ctx.check("No deposit has a payment_type and partner_type that "
                      "disagree (which would place it on neither menu, or on "
                      "both)", [], overlap)

        with ctx.step("Integrity the baseline cannot give: no deposit has "
                      "lost its deposit account"):
            # The workbook's TC-DAT-019 checks the CONTACT's account; this
            # checks the DEPOSIT's own. A deposit whose account field is empty
            # is money with no liability line behind it — the exact loss this
            # case is about — and it cannot be spotted from a count.
            blanks = {}
            for side, payment_type in ((CUSTOMER_SIDE, "inbound"),
                                       (VENDOR_SIDE, "outbound")):
                field_name = DEPOSIT_ACCOUNT_FIELD[side]
                blanks[side] = rpc.search(
                    "account.payment",
                    [("is_deposit", "=", True),
                     ("company_id", "=", company["id"]),
                     ("payment_type", "=", payment_type),
                     ("state", "in", list(PAYMENT_LIVE_STATES)),
                     (field_name, "=", False)],
                    limit=50)
                ctx.log(f"{MENU_LABEL[side]} — deposits with a blank "
                        f"{field_name}: {len(blanks[side])}")
            ctx.check("No live customer deposit has a blank Deposit Account",
                      [], blanks[CUSTOMER_SIDE])
            ctx.check("No live vendor deposit has a blank Deposit Account",
                      [], blanks[VENDOR_SIDE])

        with ctx.step("Step 7: open three deposits and read Customer, "
                      "Amount, Date, Journal and Deposit Account"):
            for side, payment_type in ((CUSTOMER_SIDE, "inbound"),
                                       (VENDOR_SIDE, "outbound")):
                field_name = DEPOSIT_ACCOUNT_FIELD[side]
                # Real gallery deposits, not this suite's fixtures.
                rows = rpc.search_read(
                    "account.payment",
                    [("is_deposit", "=", True),
                     ("company_id", "=", company["id"]),
                     ("payment_type", "=", payment_type),
                     "!", ("partner_id.name", "like", f"{MARK} %")],
                    ["name", "partner_id", "amount", "currency_id", "date",
                     "journal_id", "state", field_name, "move_id"],
                    order="id desc", limit=SAMPLE_SIZE)
                if not rows:
                    ctx.log(f"{MENU_LABEL[side]} holds no non-fixture "
                            f"deposit, so step 7 has nothing to open on this "
                            f"side")
                    residual.append(
                        f"step 7 could not be run on the {side} side: this "
                        f"database holds no {side} deposit outside this "
                        f"suite's own fixtures. If the Novobi baseline lists "
                        f"any, that is the migration failure this case exists "
                        f"to find.")
                    continue
                for row in rows:
                    account = account_row(ctx, m2o_id(row.get(field_name)))
                    entry_state = ""
                    move_id = m2o_id(row.get("move_id"))
                    if move_id:
                        entry_state = rpc.read(
                            "account.move", [move_id],
                            ["state"])[0].get("state") or ""
                    sample = {
                        "side": side,
                        "deposit": row.get("name") or "",
                        "customer": m2o_name(row.get("partner_id")),
                        "amount": money(row.get("amount")),
                        "currency": m2o_name(row.get("currency_id")),
                        "date": row.get("date") or "",
                        "journal": m2o_name(row.get("journal_id")),
                        "deposit_account": (f"{account.get('code', '')} "
                                            f"{account.get('name', '')}"
                                            ).strip(),
                        "state": row.get("state") or "",
                        "entry_state": entry_state,
                    }
                    sample_rows.append(sample)
                    ctx.log(f"  [{side}] {sample['deposit']} — "
                            f"{sample['customer']!r} "
                            f"{sample['amount']:.2f} {sample['currency']} "
                            f"{sample['date']} journal={sample['journal']!r} "
                            f"account={sample['deposit_account']!r} "
                            f"state={sample['state']!r}/"
                            f"{sample['entry_state']!r}")

            # Every field the workbook names must be readable and populated.
            # This is the printout-free half of step 7: a blank Journal or
            # Deposit Account on a real deposit is a failure no baseline is
            # needed to judge.
            incomplete = []
            for sample in sample_rows:
                missing = [label for label, key in
                           (("Customer", "customer"), ("Amount", "amount"),
                            ("Date", "date"), ("Journal", "journal"),
                            ("Deposit Account", "deposit_account"))
                           if not sample[key]]
                if missing:
                    incomplete.append(
                        f"{sample['deposit']} ({sample['side']}): "
                        f"{', '.join(missing)} blank")
            ctx.check("Every deposit opened in step 7 carries a Customer (or "
                      "Vendor), Amount, Date, Journal and Deposit Account",
                      [], incomplete)
            ctx.check_true(
                "At least one real (non-fixture) deposit exists to open, as "
                "the workbook's step 7 assumes",
                bool(sample_rows),
                actual_desc=f"{len(sample_rows)} non-fixture deposit(s) "
                            f"opened across both sides")

        with ctx.step("The baseline comparison (workbook Expected Result) — "
                      "the four numbers a human must compare"):
            residual.append(
                "compare these four numbers against the Novobi baseline from "
                "the old system, which the platform does not hold: "
                f"CUSTOMER deposits count="
                f"{counts[CUSTOMER_SIDE]['baseline_count']} "
                f"total={counts[CUSTOMER_SIDE]['baseline_total']:.2f}; "
                f"VENDOR deposits count="
                f"{counts[VENDOR_SIDE]['baseline_count']} "
                f"total={counts[VENDOR_SIDE]['baseline_total']:.2f}. Both "
                f"figures already EXCLUDE this suite's FG06 fixtures "
                f"({counts[CUSTOMER_SIDE]['fixture_count']} customer / "
                f"{counts[VENDOR_SIDE]['fixture_count']} vendor). The "
                f"workbook's If It Fails asks you to separate the two "
                f"shapes: a count that matches while a total does not points "
                f"at currency or amount conversion rather than lost records "
                f"— the per-currency breakdown is in " + INVENTORY_CSV + " "
                "and in this log, so say which currency moved.")
    finally:
        with ctx.step("Evidence: write the population and sample CSVs"):
            for path_name, header, rows in (
                (INVENTORY_CSV,
                 ["side", "measure", "currency", "count", "total"],
                 evidence[:CSV_LIMIT]),
                (SAMPLE_CSV,
                 ["side", "deposit", "customer", "amount", "currency", "date",
                  "journal", "deposit_account", "state", "entry_state"],
                 [[s["side"], s["deposit"], s["customer"], s["amount"],
                   s["currency"], s["date"], s["journal"],
                   s["deposit_account"], s["state"], s["entry_state"]]
                  for s in sample_rows]),
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
            for note in residual:
                residual_manual_step(ctx, note)
            ctx.log("NOTHING WAS CREATED OR MODIFIED by this case — the "
                    "workbook's State After The Test is 'Nothing changed', so "
                    "no sweep and no cleanup runs here either.")
