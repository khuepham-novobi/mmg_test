"""FG-06 — Customer & Vendor Deposits. Shared fixtures and gates.

Source of truth for this suite is the CLIENT MANUAL TESTING GUIDELINE
``MMG_v19_Client_Manual_Testing_Guideline_FG05-FG14_v1.0.xlsx``, sheet
``Testing Guideline``, rows 15–29 (TC-DAT-016, TC-DAT-019 and TC-DEP-001 …
TC-DEP-017). Every assertion in this suite implements that workbook's
*Expected Result* column verbatim — never weakened, never inverted.

Odoo 19 only
------------
The workbook describes Odoo 19 screens, and the v19 deposit surface is a
different generation from v15's. The MMG port (branch ``staging_19``,
``account_partner_deposit`` / ``sale_partner_deposit`` 19.0.1.0.0) changed
behaviour that these expectations read directly:

* the per-partner deposit accounts moved from ``ir.property`` rows to a
  ``company_dependent`` JSONB column (``odoo/orm/fields.py:127-129``);
* ``account.payment.state`` is now
  ``draft/in_process/paid/canceled/rejected`` — ``'posted'`` is not a
  payment state and ``'cancel'`` is spelled ``'canceled'``
  (``addons/account/models/account_payment.py:36-43``);
* ``account.move.payment_id`` was renamed ``origin_payment_id``
  (``addons/account/models/account_move.py:207``);
* the v15 ``sale_order.action_cancel`` override that detached deposits with
  ``(5, 0, 0)`` no longer exists, so cancelling an order **keeps** its
  deposits attached (``sale_partner_deposit/PORTING.md`` §4).

Running these assertions against a v15 target would report version
differences as product defects, so every test calls :func:`require_v19`
first and reports BLOCKED on anything else.

How this suite drives Odoo — and why that matters here
------------------------------------------------------
The platform talks to Odoo over ``/web/dataset/call_kw``, the endpoint the
browser itself uses (``adapters/base.py``). Two consequences shape every
fixture below:

1. **``@api.onchange`` methods do NOT fire on ``create()`` / ``write()``.**
   ``account_partner_deposit.account_payment._update_default_deposit_account``
   is the onchange that fills *Deposit Account* from the contact, and
   ``account.payment.create`` raises
   ``ValidationError('Deposit account has not been set')`` when neither
   deposit-account field is in the create values
   (``account_partner_deposit/models/account_payment.py:60-64``). So
   :func:`make_deposit` always passes the account explicitly.
2. **The onchange itself is still testable.** ``onchange(values,
   field_names, fields_spec)`` is a public model method implemented in the
   ``web`` addon (``addons/web/models/models.py:1973``) and is exactly what
   the form view calls. :func:`form_defaults` (empty ``field_names`` = the
   "record created from scratch" path, ``models.py:2019-2031``) reproduces
   *opening a form*, and :func:`onchange_values` reproduces *changing one
   field*. Every workbook expectation of the shape "the field fills itself
   in from the contact" is therefore asserted for real, against the same
   call the browser makes — not simulated.
   It is called IDS FIRST. ``onchange`` is not decorated ``@api.model``,
   so ``call_kw`` consumes ``args[0]`` as the record ids —
   ``ids, args = args[0], args[1:]`` (``odoo/service/model.py:86``) —
   before the method sees its own arguments. Both helpers therefore send
   ``[[], values, field_names, fields_spec]``, the empty id list standing
   for the record the form has not saved yet. Sending only the three
   documented arguments shifted every one of them along and raised
   ``Base.onchange() missing 1 required positional argument:
   'fields_spec'``.

Safety properties this suite keeps
----------------------------------
* Every record it creates is namespaced with the ``FG06`` marker and swept
  before and after each test; pre-existing business records — real
  customers, the chart of accounts, company journals — are read-only.
* No test reactivates a cron, a connector instance or a mail server, and
  nothing here reaches an external system. FG-06 is entirely local, so
  ``AUTOMATION_CONVENTIONS`` rule 4 needs no deviation for this suite.
* TC-DAT-016 and TC-DAT-019 are whole-population reads and create nothing
  at all.
* Posted records are never handed to ``unlink()``: Odoo refuses it, and the
  workbook's own *State After The Test* column says to leave them. Every
  assertion is scoped to ids captured in-test, never to a count of all
  FG06 records — see :func:`sweep_fg06`.
"""
from __future__ import annotations

import re

from adapters.base import OdooRPCError
from framework.context import BlockedTest, SkipTest

# --------------------------------------------------------------- identity
FEATURE = "FG-06 Customer & Vendor Deposits"
WORKFLOW = "FG-06"
WORKFLOW_NAME = "Customer & Vendor Deposits"
MODULE = "account_partner_deposit"
MODULE_SALE = "sale_partner_deposit"
MARK = "FG06"

# MMG auto-invoice. ``mmg_sale_auto_create_invoice`` overrides
# ``sale.order.action_confirm`` to call ``_create_invoices()`` on every
# order whose company carries this Boolean (``models/sale_order.py``; the
# field is declared in ``models/res_company.py``). The flag is ON for the
# acting company on the MMG v19 database, so confirming an order raises
# its invoice immediately and ``invoice_status`` reads ``'invoiced'``
# straight away. That is an MMG FEATURE the FG-06 workbook does not
# describe — not a defect — so :func:`acting_company` reports the flag and
# the cases whose workbook precondition says "confirmed, uninvoiced"
# branch on it instead of reporting the feature as a product failure.
MODULE_AUTO_INVOICE = "mmg_sale_auto_create_invoice"
AUTO_INVOICE_FIELD = "auto_create_invoice_after_confirming_so"

WORKBOOK = "MMG_v19_Client_Manual_Testing_Guideline_FG05-FG14_v1.0.xlsx"
SHEET = "Testing Guideline"


def trace(tc_ids, user_story: str = "") -> dict:
    """Traceability back to the client manual testing guideline."""
    return {
        "tc_ids": tc_ids if isinstance(tc_ids, list) else [tc_ids],
        "feature": FEATURE,
        "user_story": user_story,
        "source": f"{WORKBOOK} / {SHEET}",
    }


# ------------------------------------------------------- workbook constants
# account.payment.state (addons/account/models/account_payment.py:36-43).
# The workbook's TC-DEP-001 expects the status bar to read
# "Draft — In Process — Paid", which is statusbar_visible="draft,in_process,paid"
# on addons/account/views/account_payment_view.xml:163.
PAYMENT_STATES = ("draft", "in_process", "paid", "canceled", "rejected")
PAYMENT_STATUSBAR = ("draft", "in_process", "paid")
# "Confirmed" for a deposit means: the payment left draft AND its entry is
# posted. BC-016 — _generate_journal_entry stamps state='in_process' at CREATE
# time for any payment carrying write_off_line_vals, which every deposit does
# (addons/account/models/account_payment.py:1080), so the payment state alone
# does not mean the money was received. Both the module's partner domain and
# its sale-order domain gate on the move as well
# (account_partner_deposit/models/res_partner.py:38-46,
# sale_partner_deposit/models/sale_order.py:20-24).
PAYMENT_LIVE_STATES = ("in_process", "paid")

# account.move.payment_state (addons/account/models/account_move.py:49-57).
PAYMENT_STATE_PARTIAL = "partial"
PAYMENT_STATE_NOT_PAID = "not_paid"
PAYMENT_STATE_PAID = "paid"

# Deposit-account field domains, from
# account_partner_deposit/models/res_partner.py:6-28 (identical on
# account.payment, models/account_payment.py:11-33).
CUSTOMER_SIDE = "customer"
VENDOR_SIDE = "vendor"
DEPOSIT_ACCOUNT_FIELD = {
    CUSTOMER_SIDE: "property_account_customer_deposit_id",
    VENDOR_SIDE: "property_account_vendor_deposit_id",
}
DEPOSIT_ACCOUNT_TYPE = {
    CUSTOMER_SIDE: "liability_current",
    VENDOR_SIDE: "asset_prepayments",
}
# account.payment.partner_type / payment_type per side, from the two deposit
# actions (account_partner_deposit/views/account_payment_deposit_view.xml:
# 65-101) and the wizard (wizard/order_make_deposit.py:37-49).
DEPOSIT_PARTNER_TYPE = {CUSTOMER_SIDE: "customer", VENDOR_SIDE: "supplier"}
DEPOSIT_PAYMENT_TYPE = {CUSTOMER_SIDE: "inbound", VENDOR_SIDE: "outbound"}

# order.make.deposit.deposit_option (wizard/order_make_deposit.py:8-11).
OPTION_FIXED = "fixed"
OPTION_PERCENTAGE = "percentage"

# sale.advance.payment.inv.advance_payment_method — 'delivered' is labelled
# "Regular invoice", which is what TC-DEP-007 step 1 chooses
# (addons/sale/wizard/sale_make_invoice_advance.py:13-19).
REGULAR_INVOICE = "delivered"


# ------------------------------------------------------------ block reasons
V19_ONLY = (
    "FG-06 targets Odoo 19 only: the client manual testing guideline describes "
    "the v19 deposit surface, where account.payment.state is "
    "draft/in_process/paid/canceled/rejected, the per-partner deposit accounts "
    "are company_dependent JSONB columns rather than ir.property rows, and "
    "cancelling a sales order keeps its deposits attached. On a v15 target "
    "every one of those expectations would report a version difference as a "
    "product defect. Point the runner at the odoo19 environment (ODOO19_URL / "
    "ODOO19_DB in config/local.yaml)"
)

NO_ACCOUNT_DEPOSIT = (
    "'account_partner_deposit' (Novobi: Partner Deposit, 19.0.1.0.0) is not "
    "installed on this database — account.payment.is_deposit is absent, so no "
    "FG-06 expectation can be evaluated. Install it from the MMG v19 addons "
    "path (branch staging_19, mmg_19-custom/account_partner_deposit)"
)

NO_SALE_DEPOSIT = (
    "'sale_partner_deposit' (Novobi: Sale Partner Deposit, 19.0.1.0.0) is not "
    "installed on this database — sale.order.deposit_total is absent, so the "
    "Create deposit button, the Deposits smart button and the Total Deposit / "
    "Net Total figures this case reads do not exist. Install it from the MMG "
    "v19 addons path (branch staging_19, mmg_19-custom/sale_partner_deposit)"
)


# ----------------------------------------------------------------- plumbing
def m2o_id(value):
    """RPC read() returns a Many2one as ``[id, display_name]`` or ``False``."""
    if isinstance(value, (list, tuple)):
        return value[0] if value else None
    if isinstance(value, dict):          # web_read / onchange shape
        return value.get("id") or None
    return value or None


def m2o_name(value) -> str:
    if isinstance(value, (list, tuple)) and len(value) > 1:
        return value[1] or ""
    if isinstance(value, dict):
        return value.get("display_name") or ""
    return ""


def money(value) -> float:
    """Round to the cent — every workbook figure is stated to two places."""
    return round(float(value or 0.0), 2)


def x2m_ids(value) -> list[int]:
    """Ids out of an x2many value, in any shape the two transports return.

    ``read()`` gives a plain list of ids; ``onchange()`` gives x2many values
    "as a list of commands to be applied on the caller's field value"
    (``addons/web/models/models.py:1990-1993``), so the same field arrives as
    ``[(6, 0, [ids])]`` or a run of ``(4, id)`` / ``(1, id, vals)`` tuples.
    Both are normalised here rather than at each call site, because guessing
    wrong yields an empty list — which would silently turn an assertion about
    the contents into an assertion about nothing.
    """
    if not value:
        return []
    ids: list[int] = []
    for item in value:
        if isinstance(item, int):
            ids.append(item)
        elif isinstance(item, dict):
            if item.get("id"):
                ids.append(item["id"])
        elif isinstance(item, (list, tuple)) and item:
            code = item[0]
            if code == 6 and len(item) > 2:          # SET
                ids = list(item[2] or [])
            elif code == 4 and len(item) > 1:        # LINK
                ids.append(item[1])
            elif code == 1 and len(item) > 1:        # UPDATE
                ids.append(item[1])
            elif code == 5:                          # CLEAR
                ids = []
            elif code == 3 and len(item) > 1:        # UNLINK
                ids = [i for i in ids if i != item[1]]
    return [i for i in ids if isinstance(i, int)]


def fields_present(rpc, model: str, names) -> set:
    """Field names of ``model`` the acting user can actually read.

    ``fields_get`` omits fields the user has no group for, which is the right
    verdict here: a value that cannot be read cannot be checked.
    """
    try:
        return set(rpc.call(model, "fields_get", list(names),
                            attributes=["type"]))
    except OdooRPCError:
        return set()


# ------------------------------------------------------------- view arches
def _tag_attrs(arch: str, tag: str, name: str) -> str:
    """The raw opening ``<tag name="…" …>`` for one named element in an arch.

    A string search rather than an XML parse: what is being asserted is that a
    specific attribute expression is present *on that element*, and the tag
    text is the most faithful evidence to put in front of a reviewer.

    Scoping to the element's OWN tag is the whole point. ``'name="x" in arch
    and 'readonly="1"' in arch`` passes whenever both strings appear anywhere
    in the combined arch — a view of any size contains both — so an assertion
    written that way still passes after the attribute it names is deleted from
    the field. ``[^>]`` stops at the element's own closing angle bracket and
    matches newlines, so a tag whose attributes are spread over several lines
    (which is how ``sale_partner_deposit/views/sale_order_views.xml:15-19``
    writes the Deposits button) is still matched as one unit.
    """
    match = re.search(rf'<{tag}[^>]*name="{re.escape(name)}"[^>]*>', arch)
    return match.group(0) if match else ""


def field_attrs(arch: str, field_name: str) -> str:
    """The raw ``<field name="…" …/>`` tag for one field in a view arch."""
    return _tag_attrs(arch, "field", field_name)


def button_attrs(arch: str, button_name: str) -> str:
    """The raw ``<button name="…" …>`` tag for one button in a view arch."""
    return _tag_attrs(arch, "button", button_name)


# ------------------------------------------------------------------- gates
def require_v19(ctx):
    """BLOCK unless the target is Odoo 19 with account_partner_deposit."""
    if ctx.env.version != "19":
        ctx.blocked(f"{V19_ONLY} (current target: {ctx.env.name})")
    rpc = ctx.adapter.rpc
    if not rpc.field_exists("account.payment", "is_deposit"):
        ctx.blocked(NO_ACCOUNT_DEPOSIT)
    if not rpc.field_exists("res.partner",
                            "property_account_customer_deposit_id"):
        ctx.blocked(
            f"{NO_ACCOUNT_DEPOSIT} (account.payment.is_deposit is present but "
            f"res.partner.property_account_customer_deposit_id is not, which "
            f"means a partial install — the module's res_partner.py did not "
            f"load)")


def require_sale_deposit(ctx):
    """BLOCK unless sale_partner_deposit is installed as well."""
    require_v19(ctx)
    rpc = ctx.adapter.rpc
    if not rpc.field_exists("sale.order", "deposit_total"):
        ctx.blocked(NO_SALE_DEPOSIT)
    if not rpc.model_exists("order.make.deposit"):
        ctx.blocked(
            f"{NO_SALE_DEPOSIT} (the 'order.make.deposit' wizard model behind "
            f"the Create deposit button does not exist on this database)")


def acting_company(ctx) -> dict:
    """The company the runner user acts as, with its deposit journals.

    Everything in this suite is scoped to this one company. The platform
    sends no ``allowed_company_ids``, so ``env.companies`` falls back to every
    company the user may enter and an unscoped search would reach a sibling
    company's records — which for a company-dependent field would silently
    read a different value.

    ``auto_invoice_on_confirm`` reports :data:`AUTO_INVOICE_FIELD` — whether
    confirming a sales order auto-creates its invoice on this company. It
    is read through :func:`fields_present` like the deposit journals, so a
    database without ``mmg_sale_auto_create_invoice`` reports ``False``
    rather than failing the read.
    """
    rpc = ctx.adapter.rpc
    user = rpc.call("res.users", "read", [rpc.uid], fields=["company_id"])[0]
    company_id = m2o_id(user["company_id"])
    wanted = ["name", "currency_id", "chart_template",
              "customer_deposit_journal_id", "vendor_deposit_journal_id",
              AUTO_INVOICE_FIELD]
    readable = [f for f in wanted
                if f in fields_present(rpc, "res.company", wanted)]
    row = rpc.read("res.company", [company_id], readable)[0]
    return {
        "id": company_id,
        "name": row.get("name") or "",
        "currency_id": m2o_id(row.get("currency_id")),
        "currency_name": m2o_name(row.get("currency_id")),
        "chart_template": row.get("chart_template") or "",
        "customer_deposit_journal_id": m2o_id(
            row.get("customer_deposit_journal_id")),
        "customer_deposit_journal": m2o_name(
            row.get("customer_deposit_journal_id")),
        "vendor_deposit_journal_id": m2o_id(
            row.get("vendor_deposit_journal_id")),
        "vendor_deposit_journal": m2o_name(
            row.get("vendor_deposit_journal_id")),
        "journal_fields_present": (
            "customer_deposit_journal_id"
            in fields_present(rpc, "res.company",
                              ["customer_deposit_journal_id"])),
        # False when mmg_sale_auto_create_invoice is not installed: the
        # field is then absent from `readable` and never read, which is
        # exactly the stock-Odoo branch the deposit cases want.
        "auto_invoice_field_present": AUTO_INVOICE_FIELD in readable,
        "auto_invoice_on_confirm": bool(row.get(AUTO_INVOICE_FIELD)),
    }


def require_multi_currency(ctx, company: dict) -> dict:
    """TC-DEP-012's precondition: a second active currency with a rate.

    v19 has no ``group_multi_currency`` (it exists only in stale translation
    files), so the workbook's own wording — "More than one currency is
    active" — is the check: count active ``res.currency`` rows and pick one
    that is not the company currency and carries a rate this company can use.
    BLOCKS rather than fails: this is a database setup condition, exactly as
    the workbook's precondition says ("ask Novobi to enable multi-currency on
    the test system first").
    """
    rpc = ctx.adapter.rpc
    active = rpc.search_read("res.currency", [("active", "=", True)],
                             ["name"], order="id")
    ctx.log(f"active currencies ({len(active)}): "
            f"{', '.join(c['name'] for c in active)}")
    if len(active) < 2:
        ctx.blocked(
            f"TC-DEP-012's own precondition is not met: only "
            f"{len(active)} currency is active on this database "
            f"({', '.join(c['name'] for c in active) or 'none'}), so no order "
            f"can be priced in a currency other than the company's. Enable a "
            f"second currency (Accounting > Configuration > Currencies) and "
            f"load a rate for today, then re-run")

    others = [c for c in active if c["id"] != company["currency_id"]]
    for candidate in others:
        rates = rpc.search_read(
            "res.currency.rate",
            [("currency_id", "=", candidate["id"]),
             "|", ("company_id", "=", False),
             ("company_id", "=", company["id"])],
            ["name", "company_id"], order="name desc", limit=1)
        if rates:
            ctx.log(f"foreign currency for this case: {candidate['name']} "
                    f"(latest rate dated {rates[0]['name']})")
            return {"id": candidate["id"], "name": candidate["name"],
                    "latest_rate_date": rates[0]["name"]}
    ctx.blocked(
        f"a second currency is active "
        f"({', '.join(c['name'] for c in others)}) but none of them carries an "
        f"exchange rate this company can use, so Odoo cannot convert the "
        f"deposit. sale.order.currency_rate and "
        f"res.currency._get_conversion_rate would both fall back to 1.0, which "
        f"would make the case's figures meaningless. Load a rate for today "
        f"(Accounting > Configuration > Currencies > the currency > Rates) and "
        f"re-run")


# --------------------------------------------------------- deposit accounts
def account_row(ctx, account_id) -> dict:
    """One chart-of-accounts row as the workbook reads it.

    ``account.account.code`` is computed in v19 from the ``code_store``
    company-dependent column (``addons/account/models/account_account.py:
    39-40, 336-340``), so it is read here rather than assumed, and it is the
    acting company's code.
    """
    if not account_id:
        return {}
    # "Out of use" is `active = False` on v19. Odoo 19 REMOVED
    # `account.account.deprecated` outright (v15 declared it at
    # addons/account/models/account_account.py:62 and had no `active`; v19
    # declares `active` at :42 and no `deprecated`), so reading the v15 name
    # raises `Invalid field account.account.deprecated`. The leftover
    # `vals.get('deprecated')` guard at v19 :1075 is dead code on a field the
    # model no longer declares. The returned `deprecated` key is kept so
    # callers read the same sense as before: True = the account is out of use.
    row = ctx.adapter.rpc.read(
        "account.account", [account_id],
        ["code", "name", "account_type", "reconcile", "active"])[0]
    out_of_use = not bool(row.get("active", True))
    return {"id": account_id, "code": row.get("code") or "",
            "name": row.get("name") or "",
            "account_type": row.get("account_type") or "",
            "reconcile": bool(row.get("reconcile")),
            "active": not out_of_use,
            "deprecated": out_of_use}


def eligible_deposit_accounts(ctx, side: str, company_id: int,
                              limit: int = 10) -> list[dict]:
    """Accounts the deposit-account field would actually accept.

    The domain is the module's own
    (``account_partner_deposit/models/res_partner.py:10-14`` for the customer
    side, ``:20-24`` for the vendor side), plus the company scope: v19 gives
    ``account.account`` a Many2many ``company_ids``
    (``addons/account/models/account_account.py:97``), not a Many2one.

    ONE deliberate difference from the module: its ``('deprecated', '=',
    False)`` term is **dropped**, not translated. v19 removed
    ``account.account.deprecated`` entirely and archives accounts with the
    standard ``active`` flag, which ``active_test`` already excludes from
    every search — so dropping the term is equivalent, and keeping it raises
    ``Invalid field account.account.deprecated``. This is the same rewrite
    the migration applied in ``multichannel_order/models/
    payment_method_mapping.py:33``, which documents the rule.

    That the module still carries the removed term is a PRODUCT defect, not a
    test concern; :func:`deposit_domain_removed_field` reports it so fixing
    this helper does not hide it.
    """
    domain = [("account_type", "=", DEPOSIT_ACCOUNT_TYPE[side]),
              ("reconcile", "=", True),
              ("company_ids", "in", [company_id])]
    rows = ctx.adapter.rpc.search_read(
        "account.account", domain, ["code", "name", "account_type"],
        order="code", limit=limit)
    return [{"id": r["id"], "code": r.get("code") or "",
             "name": r.get("name") or ""} for r in rows]


def deposit_domain_removed_field(ctx, side: str) -> tuple[bool, str]:
    """Does the deposit-account field's own domain name a field v19 removed?

    ``account_partner_deposit`` was ported to v19 with
    ``('deprecated', '=', False)`` left in the domain of all four
    deposit-account fields (``models/res_partner.py:13,23`` and
    ``models/account_payment.py:17,27``). ``account.account.deprecated`` does
    not exist in Odoo 19, and the migration's own note in
    ``multichannel_order/models/payment_method_mapping.py:33`` spells out the
    consequence: *"Leaving it in fails view validation outright — Unknown
    field 'account.account.deprecated' in domain"*. The same note shows the
    term was correctly dropped there, so this is a missed occurrence rather
    than a decision.

    User-visible effect: opening the Deposit Account dropdown on a contact
    (or a payment) evaluates that domain against a field the model no longer
    declares.

    Read from the live registry via ``fields_get`` rather than from source,
    so the verdict reflects what is actually installed. Returns
    ``(is_broken, domain_text)``.
    """
    field_name = DEPOSIT_ACCOUNT_FIELD[side]
    info = ctx.adapter.rpc.call("res.partner", "fields_get", [field_name],
                                attributes=["domain"])
    domain = str((info.get(field_name) or {}).get("domain") or "")
    return ("deprecated" in domain), domain


def company_default_deposit_account(ctx, side: str, company_id: int) -> dict:
    """The company-level DEFAULT behind a partner's deposit account.

    Needed to tell "this contact carries its own account" apart from "this
    contact is falling back to the company default" — a distinction the
    workbook's TC-DAT-019 and TC-DEP-003 both depend on, and one that
    ``read()`` alone cannot make:

    * a ``company_dependent`` field stores a jsonb dict keyed by company id on
      the model's own table (``odoo/orm/fields.py:127-129, 783``);
    * ``convert_to_column`` stores **None** when the value being written
      equals the company fallback (``odoo/orm/fields.py:1000-1005``), so an
      explicit write of the default value leaves no override at all;
    * the fallback itself comes from
      ``ir.default._get_model_defaults()`` (``odoo/orm/fields.py:794-801``),
      which is **private** and therefore unreachable over RPC
      (``odoo/service/model.py`` refuses private methods).

    So the fallback is read from the ``ir.default`` rows directly, which is
    where ``res_company.create_or_update_deposit_property`` writes it
    (``account_partner_deposit/models/res_company.py:171-177``). Returns
    ``{}`` when the company has no default at all.

    Precedence — why the choice is made in Python
    ---------------------------------------------
    Two rows can match: one scoped to this company and one global
    (``company_id = NULL``). Odoo resolves that in
    ``ir.default._get_model_defaults`` with ``ORDER BY d.user_id,
    d.company_id, d.id`` plus "keep the highest priority default for each
    field" (``odoo/addons/base/models/ir_default.py``) — ASCENDING, and
    PostgreSQL sorts NULLs LAST in ASC, so the company-scoped row wins and the
    global row is the fallback.

    An ``order="company_id desc"`` on the search does NOT express that: it is
    passed through to SQL verbatim (``odoo/orm/models.py:5250-5252`` adds no
    NULLS clause), and PostgreSQL sorts NULLs FIRST in DESC — so the global
    row came back first and shadowed the company's own default, the exact
    opposite of the intent. Ordering by a Many2one also recurses into the
    comodel's ``_order`` (``odoo/orm/models.py:5262-5300``), which makes the
    SQL ordering less predictable still. The rows are therefore fetched
    unordered-but-stable and the preference is applied here.
    """
    rpc = ctx.adapter.rpc
    field_name = DEPOSIT_ACCOUNT_FIELD[side]
    rows = rpc.search_read(
        "ir.default",
        [("field_id.model", "=", "res.partner"),
         ("field_id.name", "=", field_name),
         ("user_id", "=", False),
         ("condition", "=", False),
         ("company_id", "in", [company_id, False])],
        ["json_value", "company_id"], order="id")
    scoped = [r for r in rows if m2o_id(r.get("company_id")) == company_id]
    unscoped = [r for r in rows if not m2o_id(r.get("company_id"))]
    for row in scoped + unscoped:
        raw = (row.get("json_value") or "").strip()
        if not raw or raw in ("null", "false"):
            continue
        try:
            account_id = int(raw)
        except ValueError:
            ctx.log(f"[ir.default] {field_name}: json_value {raw!r} is not an "
                    f"account id — recorded as unreadable rather than guessed")
            continue
        default = account_row(ctx, account_id)
        default["scope_company_id"] = m2o_id(row.get("company_id"))
        return default
    return {}


def stored_partner_deposit_account_ids(ctx, side: str,
                                       company_id: int) -> dict:
    """Every deposit-account id STORED against a contact, read from the jsonb.

    Why this cannot be done through the ORM
    ---------------------------------------
    ``Many2one.to_sql`` wraps a company-dependent Many2one in an EXISTENCE
    sub-select — ``(SELECT a.id FROM account_account a WHERE a.id = <stored
    id>)`` (``odoo/orm/fields_relational.py:466-478``) — and every ORM read
    path goes through it: ``fetch`` builds its SELECT from
    ``_field_to_sql`` (``odoo/orm/models.py:3905-3908``) and so does every
    domain condition. So a stored id whose ``account.account`` row was
    DELETED reads back as ``False``, indistinguishable over RPC from "this
    contact never had an override" and from "this contact's override was
    cleared". v19 erases the dangling reference on the way out.

    That erasure is exactly what hides one of the two failure shapes
    TC-DAT-019 exists to separate. The migration wrote raw ids into
    ``res_partner.<field>`` as jsonb keyed by company id
    (``odoo/orm/fields.py:783, 1218-1219``); if MS-001 mapped a v15 account to
    an id that does not exist on v19, the value is still sitting in that
    column and every contact carrying it silently falls back to the company
    default. The only place the id survives is the column itself, so it is
    read from the column.

    Read-only, and never a reason to lose the case: the platform's SQL access
    is optional (``framework/sqltool.py`` raises ``SqlUnavailable`` →
    ``ctx.blocked`` when ``pg_host``/``pg_user`` are unset), so availability
    is probed on ``ctx.env`` FIRST and reported as ``reason`` rather than
    allowed to block a case that otherwise runs entirely over RPC.

    Returns ``{"available": bool, "reason": str,
               "stored": {partner_id: account_id}, "unreadable": [(id, raw)]}``.
    """
    field_name = DEPOSIT_ACCOUNT_FIELD[side]
    if not re.fullmatch(r"[a-z_][a-z0-9_]*", field_name):    # defensive
        return {"available": False, "stored": {}, "unreadable": [],
                "reason": f"{field_name!r} is not a plain column name"}
    if not (getattr(ctx.env, "pg_host", "")
            and getattr(ctx.env, "pg_user", "")):
        return {
            "available": False, "stored": {}, "unreadable": [],
            "reason": (
                f"no PostgreSQL access is configured for environment "
                f"{ctx.env.key!r} (ODOO{ctx.env.version}_PG_HOST / _PG_USER "
                f"in config/local.yaml), and v19 erases a dangling "
                f"company-dependent reference on every ORM read path "
                f"(odoo/orm/fields_relational.py:466-478), so a migrated "
                f"res_partner.{field_name} value pointing at a deleted "
                f"account cannot be seen from here")}
    # The pg_host/pg_user probe above only rules out framework/sqltool.py's
    # SqlUnavailable path. Everything after it can still fail for reasons that
    # are environment conditions, not verdicts: psycopg2 missing, the host
    # unreachable, a bad password, the wrong dbname, a permission error on the
    # table. Those must degrade to "not available" exactly like an unset
    # host — never escape and turn a case that otherwise runs entirely over
    # RPC into ERROR / AUTOMATION_ERROR.
    try:
        sql = ctx.sql
        if not sql.column_exists("res_partner", field_name):
            return {
                "available": False, "stored": {}, "unreadable": [],
                "reason": (f"res_partner has no {field_name} column — the "
                           f"company-dependent value is not stored where "
                           f"odoo/orm/fields.py:783 puts it")}
        rows = sql.rows(
            f"SELECT id, jsonb_extract_path_text({field_name}, %s) "
            f"FROM res_partner "
            f"WHERE {field_name} IS NOT NULL "
            f"  AND jsonb_extract_path_text({field_name}, %s) IS NOT NULL "
            f"ORDER BY id", (str(company_id), str(company_id)))
    except (SkipTest, BlockedTest):
        # ctx.sql raises BlockedTest through ctx.blocked when the environment
        # has no pg_* config. Re-raise: a deliberate verdict is never swallowed.
        raise
    except Exception as exc:                                    # noqa: BLE001
        return {
            "available": False, "stored": {}, "unreadable": [],
            "reason": (f"PostgreSQL is configured for environment "
                       f"{ctx.env.key!r} but could not be used ({exc}), so "
                       f"the stored res_partner.{field_name} ids could not "
                       f"be read")}
    stored, unreadable = {}, []
    for partner_id, raw in rows:
        try:
            stored[partner_id] = int(raw)
        except (TypeError, ValueError):
            unreadable.append((partner_id, raw))
    return {"available": True, "reason": "", "stored": stored,
            "unreadable": unreadable}


def partner_deposit_account(ctx, partner_id: int, side: str,
                            company_id: int) -> dict:
    """The deposit account this contact resolves to, for one company.

    ``company_dependent`` fields carry ``_depends_context = ('company',)``
    (``odoo/orm/fields.py:477``), so the value returned depends entirely on
    the company in context. The context is therefore always explicit here —
    reading without it would silently return whichever company the runner
    user happens to default to.
    """
    field_name = DEPOSIT_ACCOUNT_FIELD[side]
    row = ctx.adapter.rpc.call(
        "res.partner", "read", [partner_id], fields=[field_name],
        context={"allowed_company_ids": [company_id],
                 "company_id": company_id})[0]
    return account_row(ctx, m2o_id(row.get(field_name)))


def set_partner_deposit_account(ctx, partner_id: int, side: str,
                                account_id, company_id: int):
    """Write a contact's deposit account for one company, explicitly."""
    field_name = DEPOSIT_ACCOUNT_FIELD[side]
    ctx.adapter.rpc.call(
        "res.partner", "write", [partner_id],
        {field_name: account_id or False},
        context={"allowed_company_ids": [company_id],
                 "company_id": company_id})


def ensure_deposit_account(ctx, side: str, company_id: int,
                           label: str) -> dict:
    """An FG06-marked account of the right type, created only if needed.

    TC-DEP-003 needs *two different* customer-deposit accounts. Where the
    database already has two eligible ones the test uses those and creates
    nothing (the workbook's own precondition: "Novobi can point you at
    them"). Where it has fewer, this creates a marked one rather than
    reporting BLOCKED on a condition the test can satisfy safely. The account
    is namespaced and swept, and no existing account is ever modified.
    """
    rpc = ctx.adapter.rpc
    name = f"{MARK} {label}"
    found = rpc.search("account.account",
                       [("name", "=", name),
                        ("company_ids", "in", [company_id])], limit=1)
    if found:
        return account_row(ctx, found[0])
    # A free code in a high range, so it cannot collide with the migrated CoA.
    used = {r["code"] for r in rpc.search_read(
        "account.account", [("company_ids", "in", [company_id]),
                            ("code", "like", "9799%")], ["code"])}
    code = next(c for c in (f"9799{n:02d}" for n in range(1, 100))
                if c not in used)
    account_id = rpc.create("account.account", {
        "code": code,
        "name": name,
        "account_type": DEPOSIT_ACCOUNT_TYPE[side],
        "reconcile": True,
        "company_ids": [(6, 0, [company_id])],
    })
    ctx.log(f"fixture account #{account_id} {code} {name!r} "
            f"({DEPOSIT_ACCOUNT_TYPE[side]}, reconcile=True) — created "
            f"because the database had fewer than two eligible "
            f"{side}-deposit accounts")
    return account_row(ctx, account_id)


def deposit_accounts_for_test(ctx, side: str, company_id: int,
                              wanted: int = 1) -> list[dict]:
    """``wanted`` eligible deposit accounts, DISTINCT BY ID, real ones first.

    Distinct by id is the whole point of this helper, and the earlier
    build could not guarantee it. :func:`ensure_deposit_account` is
    find-or-create *by name*, and :func:`eligible_deposit_accounts`
    already returns any FG06 fixture account an earlier run left behind —
    ``sweep_fg06`` cannot remove one that a posted deposit points at.
    Labelling the top-ups from a counter that restarted at ``A`` on every
    call therefore re-found the account the seed already held and
    appended it a second time, so the caller was handed the SAME account
    twice. TC-DEP-003 recorded exactly that:
    ``A = 979901 FG06 Customer Deposit Account A,
    B = 979901 FG06 Customer Deposit Account A``.

    Each top-up label is now chosen against the ids already collected and
    every append is de-duplicated, so
    ``len({a["id"] for a in result}) == wanted`` holds for every value
    this function returns.
    """
    result: list[dict] = []
    seen: set[int] = set()
    for row in eligible_deposit_accounts(ctx, side, company_id,
                                         limit=max(wanted, 4)):
        if row["id"] in seen:
            continue
        seen.add(row["id"])
        result.append(row)
        ctx.log(f"existing {side}-deposit account #{row['id']} "
                f"{row['code']} {row['name']!r}")
        if len(result) == wanted:
            return result
    # Top up. ensure_deposit_account finds by name before it creates, so
    # walk the labels until one resolves to an account this set does not
    # already hold — otherwise the account an earlier run created under
    # that label is simply found again and duplicated.
    for offset in range(26):
        if len(result) == wanted:
            break
        row = ensure_deposit_account(
            ctx, side, company_id,
            f"{side.title()} Deposit Account {chr(ord('A') + offset)}")
        if row["id"] in seen:
            ctx.log(f"{side}-deposit account #{row['id']} {row['name']!r} "
                    f"is already in this set — moving on to the next label "
                    f"so the caller gets DISTINCT accounts")
            continue
        seen.add(row["id"])
        result.append(row)
    if len(result) < wanted:
        ctx.blocked(
            f"could not assemble {wanted} DISTINCT {side}-deposit "
            f"accounts for company #{company_id}: only "
            f"{[r['code'] for r in result]} after 26 fixture labels")
    return result


# ------------------------------------------------- form / onchange mirroring
def _spec(names) -> dict:
    """``fields_spec`` for onchange — the shape the web client sends."""
    return {name: {} for name in names}


def form_defaults(ctx, model: str, names, context: dict) -> dict:
    """The values a form shows when it OPENS, under ``context``.

    ``onchange(values, [], fields_spec)`` with an empty ``field_names`` is the
    web client's "record created from scratch" call: it applies
    ``default_get`` for every field in the spec, then runs the onchange
    methods over all of them (``addons/web/models/models.py:2019-2031,
    2128``). That is precisely what the workbook means by "the pop-up opens
    with…" and by "the field fills itself in from the customer".

    IDS FIRST — the wire shape ``/web/dataset/call_kw`` requires
    -----------------------------------------------------------
    The method is declared ``def onchange(self, values, field_names,
    fields_spec)`` and is **not** decorated ``@api.model``
    (``addons/web/models/models.py:1973``), so ``call_kw`` consumes the
    first positional argument as the record IDS —
    ``ids, args = args[0], args[1:]`` (``odoo/service/model.py:86``) — and
    only then calls the method with what is left. Sending
    ``[values, field_names, fields_spec]`` therefore made Odoo browse
    ``values`` as ids and call ``onchange(recs, field_names,
    fields_spec)``, one argument short: ``Base.onchange() missing 1
    required positional argument: 'fields_spec'`` — which is how five
    FG-06 cases ERRORed. The call now leads with ids like every other
    non-``@api.model`` call in this platform
    (``rpc.call("account.move", "action_post", [move_id])``), and the id
    list is EMPTY because a form being opened has no record yet.
    """
    payload = ctx.adapter.rpc.call(model, "onchange", [], {}, [],
                                   _spec(names), context=context) or {}
    return payload.get("value") or {}


def onchange_values(ctx, model: str, values: dict, changed, names,
                    context: dict | None = None) -> dict:
    """The values a form shows after the user edits ``changed``.

    Same ids-first wire shape as :func:`form_defaults`: ``onchange`` is
    not ``@api.model``, so ``call_kw`` takes ``args[0]`` as the record ids
    (``odoo/service/model.py:86``) before the method sees ``values``. The
    leading ``[]`` is the unsaved record the form is editing; the three
    documented arguments follow it.
    """
    payload = ctx.adapter.rpc.call(
        model, "onchange", [], values, list(changed), _spec(names),
        context=context or {}) or {}
    return payload.get("value") or {}


# ---------------------------------------------------------------- fixtures
def make_partner(ctx, label: str, *, company: dict,
                 customer_deposit_account_id=None,
                 vendor_deposit_account_id=None,
                 is_company: bool = True) -> int:
    """One FG06-marked contact. Never reuses a business record.

    ``is_company`` defaults to True because the Invoicing tab that carries
    the deposit accounts is hidden on a child contact that is not a company
    (``invisible="not is_company and parent_id"``,
    ``addons/account/views/partner_view.xml:210``), and because TC-DEP-003
    step 1 says to create the contact as a Company.
    """
    rpc = ctx.adapter.rpc
    partner_id = rpc.create("res.partner", {
        "name": f"{MARK} {label}",
        "is_company": is_company,
        "comment": "Created by the odoo-regression platform (FG-06). "
                   "Safe to delete.",
    })
    for side, account_id in ((CUSTOMER_SIDE, customer_deposit_account_id),
                             (VENDOR_SIDE, vendor_deposit_account_id)):
        if account_id:
            set_partner_deposit_account(ctx, partner_id, side, account_id,
                                        company["id"])
    ctx.log(f"fixture partner #{partner_id} {MARK} {label!r} "
            f"(customer deposit account={customer_deposit_account_id}, "
            f"vendor deposit account={vendor_deposit_account_id})")
    return partner_id


def make_product(ctx, label: str, price: float) -> int:
    """One FG06-marked storable product carrying NO Odoo-side tax.

    Taxes are cleared so that ``amount_total`` equals the workbook's stated
    order total exactly; every FG-06 figure (10,000.00 / 3,000.00 /
    7,000.00 …) is quoted tax-free.
    """
    rpc = ctx.adapter.rpc
    values = {
        "name": f"{MARK} {label}",
        "default_code": f"{MARK}-{label.upper().replace(' ', '-')}",
        "list_price": price,
        "sale_ok": True,
        "taxes_id": [(6, 0, [])],
    }
    values.update(ctx.adapter.storable_product_values())
    tmpl_id = rpc.create("product.template", values)
    variant = rpc.search_read("product.product",
                              [("product_tmpl_id", "=", tmpl_id)],
                              ["id"], limit=1)
    ctx.log(f"fixture product #{variant[0]['id']} {values['name']!r} @ {price}")
    return variant[0]["id"]


def ensure_pricelist(ctx, currency: dict, company: dict) -> int:
    """An FG06-marked pricelist in ``currency`` — the only way to a
    foreign-currency order.

    ``sale.order.currency_id`` is ``compute='_compute_currency_id',
    store=True`` with **no** ``readonly=False``
    (``addons/sale/models/sale_order.py:195-201``), and the compute is
    ``pricelist_id.currency_id or company_id.currency_id``
    (``:454-456``). So the currency cannot be written on the order; it has to
    come from a pricelist. This mirrors the module's own test fixture
    (``sale_partner_deposit/tests/common.py``, ``pricelist_eur``).
    """
    rpc = ctx.adapter.rpc
    name = f"{MARK} {currency['name']} Pricelist"
    found = rpc.search("product.pricelist", [("name", "=", name)], limit=1)
    if found:
        return found[0]
    pricelist_id = rpc.create("product.pricelist", {
        "name": name,
        "currency_id": currency["id"],
        "company_id": company["id"],
    })
    ctx.log(f"fixture pricelist #{pricelist_id} {name!r} "
            f"({currency['name']})")
    return pricelist_id


def make_order(ctx, partner_id: int, lines, *, confirm: bool = True,
               pricelist_id=None) -> int:
    """One FG06 sales order. ``lines`` is ``[(product_id, qty, price)]``.

    Confirmed by default: the workbook's precondition on every
    deposits-from-orders case is a CONFIRMED order, because
    ``sale_partner_deposit`` hides the Create deposit button on anything else
    (``invisible="invoice_status == 'invoiced' or state != 'sale'"``,
    ``views/sale_order_views.xml:9-13``).
    """
    rpc = ctx.adapter.rpc
    order_lines = []
    for product_id, qty, price in lines:
        order_lines.append((0, 0, {
            "product_id": product_id,
            "product_uom_qty": qty,
            "price_unit": price,
            # v19 field names: sale.order.line.tax_ids / product_uom_id
            # (addons/sale/models/sale_order_line.py). v15's tax_id and
            # product_uom no longer exist.
            "tax_ids": [(6, 0, [])],
        }))
    values = {"partner_id": partner_id, "order_line": order_lines}
    if pricelist_id:
        values["pricelist_id"] = pricelist_id
    order_id = rpc.create("sale.order", values)
    if confirm:
        rpc.call("sale.order", "action_confirm", [order_id])
    row = rpc.read("sale.order", [order_id],
                   ["name", "state", "amount_total", "currency_id"])[0]
    ctx.log(f"fixture order #{order_id} {row['name']} — state={row['state']!r} "
            f"total={money(row['amount_total']):.2f} "
            f"{m2o_name(row['currency_id'])}")
    return order_id


def make_invoice(ctx, partner_id: int, lines, *, post: bool = False,
                 currency_id=None) -> int:
    """One standalone draft customer invoice (not raised from an order)."""
    rpc = ctx.adapter.rpc
    invoice_lines = []
    for product_id, qty, price in lines:
        invoice_lines.append((0, 0, {
            "product_id": product_id,
            "quantity": qty,
            "price_unit": price,
            "tax_ids": [(6, 0, [])],
        }))
    values = {"move_type": "out_invoice", "partner_id": partner_id,
              "invoice_line_ids": invoice_lines}
    if currency_id:
        values["currency_id"] = currency_id
    move_id = rpc.create("account.move", values)
    if post:
        rpc.call("account.move", "action_post", [move_id])
    ctx.log(f"fixture invoice #{move_id} for partner #{partner_id} "
            f"(posted={post})")
    return move_id


def invoice_from_order(ctx, order_id: int) -> int:
    """The workbook's *Create Invoice > Regular invoice* on a sales order.

    Driven through ``sale.advance.payment.inv`` exactly as the button does
    (``addons/sale/views/sale_order_views.xml:273-283`` opens
    ``sale.action_view_sale_advance_payment_inv``), with
    ``advance_payment_method='delivered'`` — the option labelled "Regular
    invoice" (``addons/sale/wizard/sale_make_invoice_advance.py:13-19``) —
    then ``create_invoices()`` (``:121``).
    """
    rpc = ctx.adapter.rpc
    context = {"active_model": "sale.order", "active_id": order_id,
               "active_ids": [order_id]}
    wizard_id = rpc.call("sale.advance.payment.inv", "create",
                         {"advance_payment_method": REGULAR_INVOICE},
                         context=context)
    try:
        rpc.call("sale.advance.payment.inv", "create_invoices", [wizard_id],
                 context=context)
    finally:
        try:
            rpc.unlink("sale.advance.payment.inv", [wizard_id])
        except OdooRPCError:
            pass       # TransientModel rows are vacuumed automatically
    invoice_ids = rpc.read("sale.order", [order_id], ["invoice_ids"])[0]
    invoice_ids = invoice_ids.get("invoice_ids") or []
    if not invoice_ids:
        return 0
    ctx.log(f"invoice(s) raised from order #{order_id}: {invoice_ids}")
    return invoice_ids[-1]


def order_invoice_rows(ctx, order_id: int) -> list[dict]:
    """Every invoice currently linked to one sales order, with its state."""
    rpc = ctx.adapter.rpc
    invoice_ids = rpc.read("sale.order", [order_id],
                           ["invoice_ids"])[0].get("invoice_ids") or []
    if not invoice_ids:
        return []
    rows = rpc.read("account.move", invoice_ids,
                    ["name", "state", "move_type", "amount_total"])
    return [{"id": r["id"], "name": r.get("name") or "",
             "state": r.get("state") or "",
             "move_type": r.get("move_type") or "",
             "amount_total": money(r.get("amount_total"))} for r in rows]


def drop_draft_order_invoices(ctx, order_id: int) -> tuple[list, list]:
    """Remove the DRAFT invoices of one FG06 fixture order.

    Returns ``(removed, kept)`` as row dicts. Used only to put a fixture
    order back into the workbook's stated "confirmed, uninvoiced"
    precondition after ``mmg_sale_auto_create_invoice`` raised an invoice
    at confirm time (see :data:`AUTO_INVOICE_FIELD`). It restores a
    precondition; it is never a way to make an assertion pass.

    ``AUTOMATION_CONVENTIONS`` rule 3 is kept. The only moves it can reach
    are those linked to the order handed to it, which this test's own
    ``action_confirm`` created moments earlier, and a POSTED move is never
    touched — it comes back in ``kept`` so the caller can decide, and the
    callers BLOCK rather than proceed on a state the workbook does not
    describe.
    """
    removed, kept = [], []
    for row in order_invoice_rows(ctx, order_id):
        if row["state"] != "draft":
            kept.append(row)
            ctx.log(f"[auto-invoice] invoice {row['name']} (#{row['id']}) "
                    f"is {row['state']!r}, not draft — left in place")
            continue
        try:
            ctx.adapter.rpc.unlink("account.move", [row["id"]])
        except OdooRPCError as exc:
            kept.append(row)
            ctx.log(f"[auto-invoice] draft invoice {row['name']} "
                    f"(#{row['id']}) could not be removed ({exc})")
        else:
            removed.append(row)
            ctx.log(f"[auto-invoice] removed the draft invoice "
                    f"{row['name']} (#{row['id']}, "
                    f"{row['amount_total']:.2f}) that action_confirm "
                    f"auto-created, restoring the workbook's uninvoiced "
                    f"precondition on order #{order_id}")
    return removed, kept


def restore_uninvoiced_order(ctx, order_id: int, company: dict) -> list[dict]:
    """Give a just-confirmed FG06 order back its INVOICEABLE quantity.

    For the cases whose own workbook step is *Create Invoice > Regular
    invoice*. ``mmg_sale_auto_create_invoice`` raises a draft invoice for
    the whole order inside ``action_confirm`` whenever the acting company
    carries :data:`AUTO_INVOICE_FIELD` (``models/sale_order.py``), and that
    flag is ON for the acting company on the MMG v19 database. Every line is
    then already invoiced — ``sale.order.line.qty_to_invoice`` counts draft
    invoices too — so ``_get_invoiceable_lines`` returns nothing and the
    wizard's ``create_invoices()`` raises *"Cannot create an invoice. No
    items are available to invoice … change the 'Invoicing Policy' to
    'Prepaid/Fixed Price'"* (``addons/sale/models/sale_order.py:1615-1616``,
    message at ``:1485-1493``). The message names the invoicing policy, but
    the policy is not the cause here: with a delivered-quantities product
    ``action_confirm`` itself would have raised, and it did not — it
    produced the invoice.

    So the auto-created DRAFT invoice is removed before the case performs
    its own step, exactly as TC-DEP-004 does
    (``test_order_deposit.py._require_confirmed_uninvoiced(restore=True)``).
    This restores the workbook's stated precondition — "a confirmed order
    with no invoice yet" — and is never a way to make an assertion pass.

    A POSTED invoice is never touched: the case BLOCKS instead, because the
    workbook describes no such starting state and inventing one would put a
    fabricated verdict in the report. Returns the rows removed (empty when
    the flag is off or nothing was auto-created).
    """
    if not company.get("auto_invoice_on_confirm"):
        return []
    raised = order_invoice_rows(ctx, order_id)
    if not raised:
        return []
    ctx.log(f"the acting company has {AUTO_INVOICE_FIELD} = True, so "
            f"confirming order #{order_id} auto-created "
            f"{[(r['name'], r['state']) for r in raised]}. That is "
            f"{MODULE_AUTO_INVOICE} working as designed — an MMG feature "
            f"the FG-06 workbook does not describe, NOT a deposit defect. "
            f"This case's own step is 'Create Invoice > Regular invoice', "
            f"which needs the order's quantity still to be invoiceable, so "
            f"the auto-created draft is removed to restore the workbook's "
            f"precondition.")
    removed, kept = drop_draft_order_invoices(ctx, order_id)
    status = ctx.adapter.rpc.read(
        "sale.order", [order_id], ["invoice_status"])[0].get(
            "invoice_status") or ""
    # ``invoice_status`` is the whole gate: it reads 'invoiced' only while
    # every line is still fully invoiced, and a CANCELLED move releases its
    # quantity again — ``_prepare_qty_invoiced`` counts an invoice line only
    # while ``move_id.state != 'cancel'``
    # (addons/sale/models/sale_order_line.py:1007-1017). So a leftover row in
    # ``kept`` is reported but does not by itself block the case.
    if status == "invoiced":
        ctx.blocked(
            f"this case's workbook step is 'Create Invoice > Regular "
            f"invoice' and the order cannot be returned to the CONFIRMED, "
            f"UNINVOICED state that step needs: {AUTO_INVOICE_FIELD} is ON "
            f"for the acting company, and after removing "
            f"{[r['name'] for r in removed] or 'nothing'} the order still "
            f"reads invoice_status={status!r} with "
            f"{[(r['name'], r['state']) for r in kept]} attached. Posted "
            f"invoices are deliberately left alone "
            f"(AUTOMATION_CONVENTIONS rule 3)")
    ctx.log(f"order #{order_id} is invoiceable again "
            f"(invoice_status={status!r}) after removing "
            f"{[r['name'] for r in removed]}")
    return removed


def make_deposit(ctx, partner_id: int, amount: float, *, account_id: int,
                 side: str = CUSTOMER_SIDE, sale_deposit_id=None,
                 date=None, currency_id=None, journal_id=None,
                 post: bool = False, memo: str = "") -> int:
    """One FG06 deposit payment, created the way the deposit screen does.

    ``account_id`` is REQUIRED and never inferred. The module's ``create``
    raises ``ValidationError('Deposit account has not been set')`` when
    neither deposit-account field is in the values
    (``account_partner_deposit/models/account_payment.py:60-64``), and the
    onchange that fills it on screen
    (``_update_default_deposit_account``, ``:44-52``) does **not** run on a
    ``create()`` over RPC. Whether that onchange works is asserted separately,
    through :func:`form_defaults` / :func:`onchange_values`, so passing the
    account here removes a dependency rather than hiding a behaviour.
    """
    rpc = ctx.adapter.rpc
    values = {
        "is_deposit": True,
        "partner_id": partner_id,
        "partner_type": DEPOSIT_PARTNER_TYPE[side],
        "payment_type": DEPOSIT_PAYMENT_TYPE[side],
        "amount": amount,
        DEPOSIT_ACCOUNT_FIELD[side]: account_id,
    }
    if date:
        values["date"] = date
    if currency_id:
        values["currency_id"] = currency_id
    if journal_id:
        values["journal_id"] = journal_id
    if sale_deposit_id:
        values["sale_deposit_id"] = sale_deposit_id
    if memo:
        values["memo"] = memo
    payment_id = rpc.create("account.payment", values)
    if post:
        rpc.call("account.payment", "action_post", [payment_id])
    row = payment_row(ctx, payment_id)
    ctx.log(f"fixture deposit #{payment_id} {row['name']!r} — "
            f"{money(row['amount']):.2f} {row['currency']} "
            f"state={row['state']!r} entry={row['move_state']!r}")
    return payment_id


# ----------------------------------------------- the Create deposit journey
def open_make_deposit_wizard(ctx, order_id: int) -> dict:
    """Press *Create deposit* on the order.

    ``sale.order.action_make_a_deposit`` returns the
    ``order.make.deposit`` act_window with ``default_currency_id`` set to the
    ORDER's currency (``sale_partner_deposit/models/sale_order.py:69-73``) —
    which is the detail TC-DEP-012 exists to check.
    """
    return ctx.adapter.rpc.call("sale.order", "action_make_a_deposit",
                                [order_id]) or {}


def run_make_deposit_wizard(ctx, order_id: int, option: str,
                            amount: float, wizard_context: dict) -> dict:
    """Fill in the *Make a Deposit* pop-up and press *Create deposit*.

    ``percentage`` is ``related='amount'`` on the wizard
    (``wizard/order_make_deposit.py:15-16``), and the form shows one input or
    the other depending on ``deposit_option``
    (``wizard/order_make_deposit_views.xml:12-17``), so writing ``amount`` is
    what typing in either box does. Returns the act_window for the payment
    pop-up; its ``context`` carries that pop-up's initial values, including
    the ``default_amount`` the workbook asks the tester to read *before*
    validating.
    """
    rpc = ctx.adapter.rpc
    context = dict(wizard_context)
    context.update({"active_model": "sale.order", "active_id": order_id,
                    "active_ids": [order_id]})
    wizard_id = rpc.call("order.make.deposit", "create",
                         {"deposit_option": option, "amount": amount},
                         context=context)
    try:
        return rpc.call("order.make.deposit", "action_create_deposit",
                        [wizard_id], context=context) or {}
    finally:
        try:
            rpc.unlink("order.make.deposit", [wizard_id])
        except OdooRPCError:
            pass       # TransientModel rows are vacuumed automatically


PAYMENT_POPUP_FIELDS = (
    "is_deposit", "partner_id", "partner_type", "payment_type", "amount",
    "currency_id", "date", "memo", "journal_id", "payment_method_line_id",
    "sale_deposit_id", "property_account_customer_deposit_id",
    "property_account_vendor_deposit_id",
)


def deposit_popup_state(ctx, action: dict) -> dict:
    """What the *Make a Deposit* payment pop-up shows when it opens.

    The act_window's own context supplies the ``default_*`` values and
    ``onchange``'s first call then runs
    ``_update_default_deposit_account`` over them, so this is the pop-up as a
    tester sees it — Customer filled in, Amount computed, Deposit Account
    pre-filled from the contact.
    """
    context = dict(action.get("context") or {})
    values = form_defaults(ctx, "account.payment", PAYMENT_POPUP_FIELDS,
                           context)
    state = {
        "context": context,
        "raw": values,
        "amount": money(values.get("amount")),
        "currency_id": m2o_id(values.get("currency_id")),
        "currency": m2o_name(values.get("currency_id")),
        "partner_id": m2o_id(values.get("partner_id")),
        "partner": m2o_name(values.get("partner_id")),
        "payment_type": values.get("payment_type") or "",
        "partner_type": values.get("partner_type") or "",
        "is_deposit": bool(values.get("is_deposit")),
        "sale_deposit_id": m2o_id(values.get("sale_deposit_id")),
        "journal_id": m2o_id(values.get("journal_id")),
        "customer_deposit_account_id": m2o_id(
            values.get("property_account_customer_deposit_id")),
        "vendor_deposit_account_id": m2o_id(
            values.get("property_account_vendor_deposit_id")),
    }
    ctx.log(f"payment pop-up opens with — Customer={state['partner']!r} "
            f"Amount={state['amount']:.2f} {state['currency']} "
            f"Deposit Account="
            f"{state['customer_deposit_account_id'] or state['vendor_deposit_account_id']} "
            f"Journal={state['journal_id']}")
    return state


def validate_deposit_popup(ctx, state: dict, *,
                           side: str = CUSTOMER_SIDE,
                           account_id=None) -> tuple[int, str]:
    """Press *Validate* on the payment pop-up.

    The footer's Validate button is ``name="action_post" type="object"``
    (``account_partner_deposit/views/account_payment_deposit_view.xml:
    134-136``), so the record is created from the pop-up's values and then
    posted. Returns ``(payment_id, error)`` — ``error`` non-empty when the
    guard refused it, which is what TC-DEP-005 and TC-DEP-017 read.
    """
    rpc = ctx.adapter.rpc
    field_name = DEPOSIT_ACCOUNT_FIELD[side]
    resolved = account_id or state.get(
        "customer_deposit_account_id" if side == CUSTOMER_SIDE
        else "vendor_deposit_account_id")
    values = {
        "is_deposit": True,
        "partner_id": state["partner_id"],
        "partner_type": state["partner_type"] or DEPOSIT_PARTNER_TYPE[side],
        "payment_type": state["payment_type"] or DEPOSIT_PAYMENT_TYPE[side],
        "amount": state["amount"],
        field_name: resolved,
    }
    if state.get("currency_id"):
        values["currency_id"] = state["currency_id"]
    if state.get("journal_id"):
        values["journal_id"] = state["journal_id"]
    if state.get("sale_deposit_id"):
        values["sale_deposit_id"] = state["sale_deposit_id"]

    payment_id, error = 0, ""
    try:
        payment_id = rpc.call("account.payment", "create", values,
                              context=state.get("context") or {})
    except OdooRPCError as exc:
        return 0, str(exc)
    try:
        rpc.call("account.payment", "action_post", [payment_id])
    except OdooRPCError as exc:
        error = str(exc)
        ctx.log(f"Validate refused deposit #{payment_id}: {error}")
    return payment_id, error


# ----------------------------------------------------------------- readers
def order_totals(ctx, order_id: int) -> dict:
    """The order's totals block as the workbook reads it.

    ``deposit_total`` is labelled *Total Deposit* and ``remaining_total``
    *Net Total*; both, and ``deposit_count``, are hidden until a deposit
    exists (``invisible="deposit_count == 0"``,
    ``sale_partner_deposit/views/sale_order_views.xml:22-27``).
    """
    row = ctx.adapter.rpc.read(
        "sale.order", [order_id],
        ["name", "state", "invoice_status", "amount_total", "currency_id",
         "deposit_count", "deposit_total", "remaining_total", "deposit_ids",
         "invoice_ids"])[0]
    return {
        "id": order_id, "name": row.get("name") or "",
        "state": row.get("state") or "",
        "invoice_status": row.get("invoice_status") or "",
        "amount_total": money(row.get("amount_total")),
        "currency_id": m2o_id(row.get("currency_id")),
        "currency": m2o_name(row.get("currency_id")),
        "deposit_count": int(row.get("deposit_count") or 0),
        "deposit_total": money(row.get("deposit_total")),
        "remaining_total": money(row.get("remaining_total")),
        "deposit_ids": row.get("deposit_ids") or [],
        "invoice_ids": row.get("invoice_ids") or [],
    }


def invoice_totals(ctx, move_id: int) -> dict:
    """The invoice's Amount Due and payment status."""
    row = ctx.adapter.rpc.read(
        "account.move", [move_id],
        ["name", "state", "payment_state", "amount_total", "amount_residual",
         "currency_id", "invoice_has_outstanding"])[0]
    return {
        "id": move_id, "name": row.get("name") or "",
        "state": row.get("state") or "",
        "payment_state": row.get("payment_state") or "",
        "amount_total": money(row.get("amount_total")),
        "amount_residual": money(row.get("amount_residual")),
        "currency": m2o_name(row.get("currency_id")),
        "has_outstanding": bool(row.get("invoice_has_outstanding")),
    }


def payment_row(ctx, payment_id: int) -> dict:
    """One deposit as its form shows it, including its entry's state."""
    rpc = ctx.adapter.rpc
    fields = ["name", "state", "amount", "currency_id", "date", "memo",
              "partner_id", "journal_id", "move_id", "is_deposit",
              "amount_company_currency_signed",
              "property_account_customer_deposit_id",
              "property_account_vendor_deposit_id"]
    optional = [f for f in ("sale_deposit_id", "deposit_ids")
                if f in fields_present(rpc, "account.payment", [f])]
    row = rpc.read("account.payment", [payment_id], fields + optional)[0]
    move_id = m2o_id(row.get("move_id"))
    move_state = ""
    if move_id:
        move_state = rpc.read("account.move", [move_id],
                              ["state"])[0].get("state") or ""
    return {
        "id": payment_id, "name": row.get("name") or "",
        "state": row.get("state") or "",
        "amount": money(row.get("amount")),
        "amount_company_signed": money(
            row.get("amount_company_currency_signed")),
        "currency_id": m2o_id(row.get("currency_id")),
        "currency": m2o_name(row.get("currency_id")),
        "date": row.get("date") or "",
        "memo": row.get("memo") or "",
        "partner_id": m2o_id(row.get("partner_id")),
        "journal_id": m2o_id(row.get("journal_id")),
        "journal": m2o_name(row.get("journal_id")),
        "move_id": move_id, "move_state": move_state,
        "is_deposit": bool(row.get("is_deposit")),
        "customer_deposit_account_id": m2o_id(
            row.get("property_account_customer_deposit_id")),
        "vendor_deposit_account_id": m2o_id(
            row.get("property_account_vendor_deposit_id")),
        "sale_deposit_id": m2o_id(row.get("sale_deposit_id")),
        "deposit_ids": row.get("deposit_ids") or [],
    }


def payment_liquidity_account(ctx, payment_id: int) -> dict:
    """The account a payment books its LIQUIDITY line to — Odoo's own rule.

    NOT an ``account_type`` test, and this is the reason why.

    ``_prepare_move_liquidity_lines`` writes that line to
    ``self.outstanding_account_id``
    (``addons/account/models/account_payment.py:293``), and
    ``_seek_for_lines`` classifies a line as liquidity by membership of
    ``_get_valid_liquidity_accounts()`` — ``journal_id.default_account_id |
    payment_method_line_id.payment_account_id | the journal's inbound and
    outbound method-line payment accounts | outstanding_account_id``
    (``:216-228``, ``:242-250``) — never by ``account_type``. An
    unreconciled deposit therefore sits on the Outstanding Receipts /
    Outstanding Payments account, not on the journal's bank account, and on
    ``mmg_19`` EVERY such outstanding account is typed ``asset_current``
    while the journals' ``default_account_id`` accounts are ``asset_cash``.
    Filtering the entry's lines on ``account_type in ('asset_cash',
    'liability_credit_card')`` consequently matched NOTHING on a perfectly
    well-formed entry and reported it as a product defect.

    ``outstanding_account_id`` is ``store=True, compute=
    '_compute_outstanding_account_id'`` in v19 (``:123-129``, computed from
    ``payment_method_line_id.payment_account_id`` at ``:621-623``), so it is
    readable over RPC. It falls back to the journal's own
    ``default_account_id`` — also a member of
    ``_get_valid_liquidity_accounts()`` — when the payment method line
    carries no payment account and the field is therefore empty.

    Returns ``{"account_id", "source"}``; ``account_id`` is ``None`` when
    neither is set, which the caller reports rather than hides.
    """
    rpc = ctx.adapter.rpc
    row = rpc.read("account.payment", [payment_id],
                   ["outstanding_account_id", "journal_id"])[0]
    outstanding_id = m2o_id(row.get("outstanding_account_id"))
    if outstanding_id:
        return {"account_id": outstanding_id,
                "source": f"account.payment.outstanding_account_id "
                          f"({m2o_name(row.get('outstanding_account_id'))})"}
    journal_id = m2o_id(row.get("journal_id"))
    if not journal_id:
        return {"account_id": None,
                "source": "neither outstanding_account_id nor a journal is "
                          "set on the payment"}
    journal = rpc.read("account.journal", [journal_id],
                       ["name", "default_account_id"])[0]
    default_id = m2o_id(journal.get("default_account_id"))
    return {
        "account_id": default_id,
        "source": f"account.payment.outstanding_account_id is not set, so "
                  f"the journal's own default_account_id "
                  f"({m2o_name(journal.get('default_account_id')) or 'unset'}"
                  f") on {journal.get('name')!r}",
    }


def move_lines(ctx, move_id: int) -> list[dict]:
    """Every journal item of one entry, as the workbook's step reads them."""
    rows = ctx.adapter.rpc.search_read(
        "account.move.line", [("move_id", "=", move_id)],
        ["account_id", "name", "debit", "credit", "amount_currency",
         "currency_id", "reconciled", "amount_residual", "payment_id"],
        order="id")
    out = []
    for row in rows:
        account = account_row(ctx, m2o_id(row.get("account_id")))
        out.append({
            "id": row["id"],
            "account_id": account.get("id"),
            "account_code": account.get("code", ""),
            "account_name": account.get("name", ""),
            "account_type": account.get("account_type", ""),
            "name": row.get("name") or "",
            "debit": money(row.get("debit")),
            "credit": money(row.get("credit")),
            "amount_currency": money(row.get("amount_currency")),
            "currency": m2o_name(row.get("currency_id")),
            "reconciled": bool(row.get("reconciled")),
            "amount_residual": money(row.get("amount_residual")),
            "payment_id": m2o_id(row.get("payment_id")),
        })
    return out


def deposit_account_lines(ctx, payment_id: int, account_id: int) -> list[dict]:
    """The deposit-account line(s) of a deposit's own journal entry.

    BC-001 — ``account.payment`` no longer delegates to ``account.move`` in
    v19, so the lines are reached through ``move_id``
    (``account_partner_deposit/PORTING.md`` §3).
    """
    row = ctx.adapter.rpc.read("account.payment", [payment_id],
                               ["move_id"])[0]
    move_id = m2o_id(row.get("move_id"))
    if not move_id:
        return []
    return [line for line in move_lines(ctx, move_id)
            if line["account_id"] == account_id]


def outstanding_credits(ctx, move_id: int) -> list[dict]:
    """The invoice's *Outstanding credits* panel, entry by entry.

    ``invoice_outstanding_credits_debits_widget`` is a computed
    ``fields.Binary`` in v19 whose value is the payload dict the OWL
    component reads (``addons/account/models/account_move.py:498-502``); the
    MMG override appends the deposit entries to it
    (``account_partner_deposit/models/account_move.py:16-97``). Reading the
    field over RPC returns that dict, which is the same thing the browser
    receives. Each RPC call is its own transaction, so the compute is always
    fresh — no cache invalidation is needed.
    """
    row = ctx.adapter.rpc.read(
        "account.move", [move_id],
        ["invoice_outstanding_credits_debits_widget"])[0]
    widget = row.get("invoice_outstanding_credits_debits_widget")
    if not isinstance(widget, dict):
        return []
    entries = []
    for item in widget.get("content") or []:
        entries.append({
            "line_id": item.get("id"),
            "amount": money(item.get("amount")),
            "journal_name": item.get("journal_name") or "",
            "move_ref": item.get("move_ref") or "",
            "date": item.get("date") or "",
            "payment_id": item.get("account_payment_id"),
            "move_id": item.get("move_id"),
            "keys": sorted(item),
        })
    return entries


def apply_outstanding_credit(ctx, move_id: int, line_id: int):
    """Click one entry in the *Outstanding credits* panel.

    ``account.move.js_assign_outstanding_line(credit_aml_id)`` is what the
    widget calls; the MMG override intercepts it for deposit lines and builds
    the intermediate 'Deposit to Payment' entry
    (``account_partner_deposit/models/account_move.py:117-133``).
    """
    return ctx.adapter.rpc.call("account.move", "js_assign_outstanding_line",
                                [move_id], line_id)


def residual_manual_step(ctx, text: str):
    """Record a comparison only a human (or a Novobi baseline) can settle."""
    ctx.log(f"RESIDUAL MANUAL STEP — {text}")


# ----------------------------------------------------------------- sweeping
def sweep_fg06(ctx):
    """Remove leftovers from previous FG-06 runs — marker-scoped only.

    POSTED payments and moves are deliberately NOT deleted: Odoo refuses it,
    and the workbook's own *State After The Test* column says to leave them
    ("One confirmed customer deposit of 2,500.00 exists"). Every assertion in
    this suite is therefore scoped to ids captured in-test, never to a count
    of all FG06 records — the one exception being TC-DAT-016, which is a
    whole-population count by design and reports the FG06 fixture share
    separately so a human can subtract it from the Novobi baseline
    comparison.

    Order matters: orders before deposits (a deposit points at an order),
    deposits before partners and accounts, products before their partners.
    """
    rpc = ctx.adapter.rpc
    marker = f"{MARK} %"
    try:
        company_id = acting_company(ctx)["id"]
    except (OdooRPCError, IndexError, KeyError) as exc:
        ctx.log(f"[sweep] could not resolve the acting company ({exc}) — "
                f"nothing swept")
        return
    scope = [("company_id", "=", company_id)]

    def _drop(model, domain, label):
        try:
            ids = rpc.search(model, domain)
        except OdooRPCError as exc:
            ctx.log(f"[sweep] {model} not searchable ({exc}) — skipped")
            return
        if not ids:
            return
        try:
            rpc.unlink(model, ids)
            ctx.log(f"swept {len(ids)} {label}")
        except OdooRPCError as exc:
            ctx.log(f"[sweep] {len(ids)} {label} left in place ({exc})")

    # 1. sales orders — cancel first: v19 refuses to unlink a confirmed order.
    try:
        confirmed = rpc.search("sale.order",
                               [("partner_id.name", "like", marker),
                                ("state", "=", "sale")] + scope)
        # OdooAdapter.cancel_order takes ONE order id (adapters/base.py:271
        # `order_id: int`) and wraps it into the call's ids list itself.
        # Handing it the search result sent ids=[[id, …]], which Odoo browses
        # into a record whose id is a list; the first field read in
        # sale.order.action_cancel then uses it as a cache key and raises
        # TypeError: unhashable type: 'list'
        # (odoo/orm/environments.py:709). The sweep swallowed that as "not
        # cancellable", so confirmed FG06 orders were never cancelled and
        # never swept — a repeatability hole (AUTOMATION_CONVENTIONS rule 3).
        # Cancel them one at a time so one stuck order cannot hide the rest.
        for order_id in confirmed:
            try:
                ctx.adapter.cancel_order(order_id)
            except OdooRPCError as exc:
                ctx.log(f"[sweep] FG06 order {order_id} not cancellable "
                        f"({exc}) — left in place")
    except OdooRPCError:
        pass
    _drop("sale.order",
          [("partner_id.name", "like", marker),
           ("state", "in", ("draft", "sent", "cancel"))] + scope,
          "FG06 sales order(s)")

    # 2. deposits whose journal entry never posted, and draft/cancelled moves.
    #
    # SAFETY — the predicate here is the ENTRY's state, not the payment's, and
    # that choice is load-bearing in both directions:
    #
    #  * a remnant left by a refused Validate reads state='in_process' with a
    #    draft entry (BC-016 — _generate_journal_entry stamps 'in_process' at
    #    create time, addons/account/models/account_payment.py:1080), so a
    #    sweep keyed on ('state','in',('draft','canceled')) would MISS it and
    #    the suite would not be repeatable;
    #  * conversely v19's account.payment.unlink() is not a safe no-op on a
    #    posted deposit: it calls button_draft() on the move and then unlinks
    #    it (addons/account/models/account_payment.py:957-959), so the
    #    posted-move guard on account.move.line never fires and a CONFIRMED
    #    deposit would be silently destroyed along with its journal entry.
    #    Anything with a posted entry is therefore excluded by the domain
    #    rather than left to fail, which is why this is not simply attempted
    #    and logged like the other models.
    _drop("account.payment",
          [("partner_id.name", "like", marker),
           ("is_deposit", "=", True),
           ("move_id.state", "!=", "posted")] + scope,
          "FG06 deposit payment(s) whose journal entry never posted")
    _drop("account.move",
          [("partner_id.name", "like", marker),
           ("state", "in", ("draft", "cancel"))] + scope,
          "FG06 journal entr(ies)/invoice(s)")

    # 3. products, then pricelists, then partners.
    for model in ("product.product", "product.template"):
        try:
            ids = rpc.search(model, [("name", "like", marker),
                                     ("active", "in", [True, False])])
        except OdooRPCError:
            continue
        if not ids:
            continue
        try:
            rpc.unlink(model, ids)
        except OdooRPCError:
            try:
                rpc.write(model, ids, {"active": False})
            except OdooRPCError:
                pass
    _drop("product.pricelist", [("name", "like", marker)],
          "FG06 pricelist(s)")
    _drop("res.partner",
          [("name", "like", marker), ("user_ids", "=", False)],
          "FG06 contact(s)")

    # 4. FG06 fixture accounts, last: a referenced account cannot be removed,
    #    and that is fine — it stays namespaced and is reused next run.
    _drop("account.account",
          [("name", "like", marker), ("company_ids", "in", [company_id])],
          "FG06 fixture account(s)")


def cleanup(ctx, created: dict):
    """Best-effort teardown of ids captured during a test, then a sweep.

    ``created`` maps model name -> list of ids, deleted in the order given.
    Never raises: an unguarded call here would escape the caller's ``finally``
    and be recorded as ERROR/AUTOMATION_ERROR, destroying the real FAILED or
    BLOCKED verdict the test had already reached.

    **Callers MUST remove an id from ``created`` once its record is posted.**
    For ``account.move`` that is merely tidy — a posted move refuses to
    unlink. For ``account.payment`` it is a safety requirement: v19's
    ``unlink`` calls ``button_draft()`` on the move and then unlinks it
    (``addons/account/models/account_payment.py:957-959``), so the
    posted-move guard never fires and a CONFIRMED deposit would be destroyed
    together with its journal entry — exactly the data loss FG-06 exists to
    detect. This function therefore refuses posted deposits itself as well,
    rather than trusting every caller.
    """
    rpc = ctx.adapter.rpc
    for model, ids in created.items():
        ids = [i for i in ids if i]
        if not ids:
            continue
        if model == "account.payment":
            # Defence in depth: never let a confirmed deposit reach unlink().
            try:
                confirmed = rpc.search("account.payment",
                                       [("id", "in", ids),
                                        ("move_id.state", "=", "posted")])
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[cleanup] could not classify account.payment{ids} "
                        f"({exc}) — left in place rather than risking the "
                        f"unlink path that resets a posted move to draft")
                continue
            if confirmed:
                ctx.log(f"[cleanup] confirmed deposit(s) {confirmed} left in "
                        f"place BY DESIGN: v19 account.payment.unlink() would "
                        f"reset the posted entry to draft and delete it "
                        f"(addons/account/models/account_payment.py:957-959), "
                        f"destroying accounting evidence. The workbook's "
                        f"State After The Test expects these to survive.")
                ids = [i for i in ids if i not in set(confirmed)]
                if not ids:
                    continue
        try:
            rpc.unlink(model, ids)
        except Exception as exc:      # noqa: BLE001 — teardown must not raise
            ctx.log(f"[cleanup] {model}{ids} not removable ({exc}) — left in "
                    f"place (a posted move refuses to unlink; the workbook's "
                    f"State After The Test column expects several of these to "
                    f"survive)")
    try:
        sweep_fg06(ctx)
    except Exception as exc:          # noqa: BLE001
        ctx.log(f"[cleanup] sweep incomplete: {exc}")
