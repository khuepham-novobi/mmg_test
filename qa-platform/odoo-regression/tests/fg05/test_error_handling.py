"""FG-05 — Error handling: TC-TAX-017.

TC-TAX-017 "A bad Avalara connection fails with a readable message, not a
crash" is the workbook's only deliberate **break-and-restore** case, and the
guideline's step 3.0 says to run it LAST. It overwrites the company's Avalara
API KEY with an obviously invalid string, proves that Odoo then fails
*readably* instead of crashing or half-taxing the invoice, and puts the real
key back.

What it proves (workbook Expected Result, one ctx.check per line)
----------------------------------------------------------------
* step 3 — ``res.config.settings.avatax_ping()`` reports an authentication
  FAILURE, not success;
* step 6 — Compute Taxes raises a readable message that explains the
  credentials were rejected, not a raw traceback and not a blank screen. The
  message asserted on is the FULL server text, re-read untruncated (see the
  adaptation below); it is logged verbatim, which is what the If-It-Fails
  column asks the tester to attach to the defect;
* step 7 — the invoice carries NO tax figure, no tax journal item, is still
  in DRAFT and is still editable — not half-taxed and not locked;
* step 9 — after the restore, Test connection reports success again;
* step 10 — Compute Taxes now succeeds and produces a non-zero tax.

Safety design (the restore is the point of this test)
-----------------------------------------------------
1. :func:`require_sandbox` runs first: a company pointed at *production*
   BLOCKS, so a production-pointed configuration is never broken.
2. ``res.company.avalara_api_key`` carries ``groups='base.group_system'``
   (``account_avatax/models/res_company.py:16``). A key that cannot be READ
   back cannot be RESTORED, so readability is probed **before any write** and
   an unreadable key BLOCKS the test rather than breaking a system it could
   not repair. A key that already reads as the invalid UAT string (a previous
   run that did not restore) also BLOCKS.
3. The break happens inside ``try:``; the restore is the inner ``finally:``
   and therefore runs whatever happens, and is recorded as a real assertion
   (fingerprint of the re-read key vs the fingerprint captured at step 1) so
   a failed restore is a visible FAILED check, never a silent one. A mismatch
   logs a loud line naming the manual recovery step. The restore is *armed*
   on the line BEFORE the break write, not after it: an RPC timeout can be
   raised after the server has already committed that write, and a restore
   that believed nothing was broken would leave the database uncalculable.
4. Credential VALUES never enter evidence. Everything is reported as
   ``set``/``not set``, a length, and a truncated SHA-256 — never the string,
   not in a log line and not in a check's expected/actual. The Server
   Response detail list is dropped from evidence too: it echoes Avalara's
   authenticated user back, and only the verdict line is asserted.

Documented adaptations
----------------------
* **Workbook precondition "TC-TAX-001 has passed" is not a dependency here.**
  The platform forbids relying on another test's fixtures, so this case
  builds its own equivalent starting state: an FG05 partner at the Phoenix AZ
  test address on the AvaTax fiscal position, an FG05 art item at 1,000.00,
  and its own draft invoice. The business assertions are unchanged.
* **Settings are written on ``res.company``, not through
  ``res.config.settings``.** ``res.config.settings.avalara_api_key`` is only
  ``related='company_id.avalara_api_key', readonly=False``
  (``account_avatax/models/res_company.py:40-44``) — a mirror of the same
  stored column. Persisting it through the settings form means
  ``res.config.settings.execute()``, which additionally installs/uninstalls
  every ``module_*`` field on the record and requires ``env.is_admin()``
  (``odoo/addons/base/models/res_config.py:350``). A single targeted
  write on the stored column is the path that certainly persists and is
  exactly reversible, which is what a break-and-restore case needs.
  ``avatax_ping()`` is still called on a real ``res.config.settings`` record,
  because that is where the method is defined.
* **Step 6 asserts the FULL server message, not the last line of it.** The
  platform's RPC layer collapses a multi-line Odoo error to its final line
  (``adapters/base.py:156``), and ``_handle_response`` builds exactly that
  shape — ``"<Odoo title>\\n<Avalara detail>"``
  (``…/account_external_tax_mixin.py:287-295``). Judging readability on the
  truncated form judges the TRANSPORT, not the product: a perfectly readable
  two-line pop-up can arrive as one short fragment and be reported as a
  defect. The step therefore re-reads ``error.data.message`` untouched
  through ``tests.fg05.common.server_error_message`` — the same helper
  TC-TAX-007 uses for its address guard, using only the public
  ``framework.fg_common.http_session``; nothing in ``framework/`` is
  modified. The expectation is unchanged (a readable explanation, not a raw
  trace) and the whole message is logged verbatim. Re-issuing the call is
  safe HERE and only here: the credential is deliberately invalid at step 6,
  so the repeat is a second rejected authentication that files nothing.
  Step 10 runs with the real key restored and keeps the adapter's message,
  because repeating a Compute Taxes there would send a second document.
* **The art item is checked to resolve an Avalara Tax Code before the break.**
  ``_prepare_avatax_document_line_service_call`` raises "The Avalara Tax Code
  is required for …" *before* the HTTP call whenever the line's product,
  template and category chain resolve no ``product.avatax.category``
  (``account_avatax/models/product.py:29-57``,
  ``…/account_external_tax_mixin.py:88-95``). That would make step 6 pass on
  the wrong error and step 10 fail for a reason unrelated to this test. The
  fixture now carries one by construction — ``common.make_product`` files
  every FG05 product under the shared FG05 AvaTax category
  (``common.fg05_product_category``), which is BLOCKED up front if the
  database holds no ``product.avatax.category`` at all. The chain is still
  read back and asserted here, before any write: this test breaks a
  credential, and it does so only once its own precondition is proven.
* The ping verdict is asserted against the English source strings
  ``"Authentication success." / "Authentication failed."``
  (``account_avatax/models/res_company.py:138``); a runner user whose UI
  language is not English would receive the translated wording.
"""
from __future__ import annotations

import hashlib
import re

from adapters.base import OdooRPCError
from framework.registry import test_case
from tests.fg05.common import (ADDRESS_PHOENIX_AZ, MARK, MODULE, WORKFLOW,
                               WORKFLOW_NAME, cleanup, compute_taxes,
                               doc_totals, make_invoice, make_partner,
                               make_product, move_tax_lines,
                               require_avatax_fiscal_position,
                               require_sandbox, server_error_message,
                               sweep_fg05, trace)

# Workbook Test Data — "type any obviously invalid string such as
# INVALID-KEY-FOR-UAT" and "any art item, quantity 1, price 1,000.00".
INVALID_KEY = "INVALID-KEY-FOR-UAT"
LINE_PRICE = 1000.00

# account_avatax/models/res_company.py::_format_response builds the Server
# Response pop-up as "<verdict><ul>…detail…</ul>".
PING_OK = "Authentication success."
PING_FAIL = "Authentication failed."

TRACEBACK_MARK = "Traceback (most recent call last)"

# The workbook's step-6 Expected Result is not only "readable": the message
# must explain "that Avalara could not be reached or the credentials were
# rejected". Avalara answers a rejected key with an AuthenticationException /
# AuthenticationIncomplete detail, so this vocabulary is deliberately broad —
# it is checked against the SERVER's own sentence, with the platform's
# "<model>.<method> failed: " prefix stripped off first.
CONNECTION_VOCABULARY = ("auth", "credential", "connect", "unauthor",
                         "reject", "login", "avalara", "avatax", "api",
                         "permission", "access", "token", "key")

RPC_ERROR_PREFIX = "account.move.button_external_tax_calculation failed: "

COMPUTE_TAXES_METHOD = "button_external_tax_calculation"

_TAG_RE = re.compile(r"<[^>]+>")

MANUAL_RECOVERY = (
    "MANUAL RECOVERY REQUIRED: open Accounting > Configuration > Settings > "
    "Taxes > AvaTax on the company and paste the real SANDBOX API KEY back, "
    "then Save and click Test connection. Until that is done this database "
    "cannot calculate any tax and every later FG-05 case is blocked "
    "(workbook: 'If you cannot restore the key, stop and tell Novobi "
    "immediately')."
)


# ------------------------------------------------------------ evidence-safe
def _fingerprint(value) -> str:
    """Evidence-safe identity of a credential — never the credential itself.

    Used as both sides of the restore assertion, so a failed restore is
    visible in the report without the secret ever being written down.
    """
    if not value:
        return "not set"
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
    return f"set len={len(value)} sha256:{digest}"


def _redact(text, secrets) -> str:
    """Belt-and-braces: strip a credential out of anything about to be logged."""
    out = text or ""
    for secret in secrets:
        if secret and len(secret) >= 4:
            out = out.replace(secret, "<redacted-credential>")
    return out


# --------------------------------------------------------------- primitives
def _m2o(value):
    """Many2one values read back as ``[id, display_name]``."""
    if isinstance(value, (list, tuple)):
        return value[0] if value else None
    return value or None


def _resolve_avatax_category(rpc, product_id):
    """``(avatax_category_id, where_it_came_from)`` for one product.

    Mirrors ``product.product._get_avatax_category_id()`` →
    ``product_tmpl_id`` → ``categ_id`` walking ``parent_id``
    (account_avatax/models/product.py:29-57). The ORM method is private and
    ``call_kw`` refuses private methods, so the same chain is read field by
    field instead.
    """
    row = rpc.read("product.product", [product_id],
                   ["avatax_category_id", "product_tmpl_id", "categ_id"])[0]
    if _m2o(row.get("avatax_category_id")):
        return _m2o(row["avatax_category_id"]), "product.product"
    tmpl_id = _m2o(row.get("product_tmpl_id"))
    if tmpl_id:
        tmpl = rpc.read("product.template", [tmpl_id],
                        ["avatax_category_id"])[0]
        if _m2o(tmpl.get("avatax_category_id")):
            return _m2o(tmpl["avatax_category_id"]), "product.template"
    categ_id = _m2o(row.get("categ_id"))
    seen = set()
    while categ_id and categ_id not in seen:
        seen.add(categ_id)
        categ = rpc.read("product.category", [categ_id],
                         ["avatax_category_id", "parent_id"])[0]
        if _m2o(categ.get("avatax_category_id")):
            return (_m2o(categ["avatax_category_id"]),
                    f"product.category #{categ_id}")
        categ_id = _m2o(categ.get("parent_id"))
    return None, ""


def _read_api_key(rpc, company_id):
    """``(readable, value)`` for ``res.company.avalara_api_key``.

    The field carries ``groups='base.group_system'``
    (account_avatax/models/res_company.py:16), so a runner user outside that
    group neither sees it in ``fields_get`` nor may ``read()`` it. This probe
    runs BEFORE any write: a key that cannot be read back cannot be restored,
    and this test must never break what it cannot repair.
    """
    try:
        present = rpc.call("res.company", "fields_get", ["avalara_api_key"],
                           attributes=["type"])
    except OdooRPCError:
        return False, None
    if "avalara_api_key" not in present:
        return False, None
    try:
        data = rpc.read("res.company", [company_id], ["avalara_api_key"])
    except OdooRPCError:
        return False, None
    if not data:
        return False, None
    return True, (data[0].get("avalara_api_key") or "")


def _ping_verdict(html: str) -> str:
    """The pop-up's verdict line, with the detail list deliberately dropped.

    ``_format_response`` appends a ``<ul>`` echoing Avalara's ping payload —
    including the authenticated user — after the verdict. Only the verdict is
    kept, so no credential-adjacent value reaches the evidence.
    """
    text = (html or "").split("<ul>")[0]
    return _TAG_RE.sub("", text).replace("&nbsp;", " ").strip()


def _test_connection(ctx):
    """The workbook's 'Test connection' button → ``(raised, verdict, error)``.

    ``avatax_ping()`` is defined on ``res.config.settings`` and returns an
    act_window onto a transient ``avatax.connection.test.result`` whose
    ``server_response`` HTML carries the verdict
    (account_avatax/models/res_company.py:121-144). A fresh settings record is
    created per ping so it mirrors the company's CURRENT key; ``execute()`` is
    never called, so nothing is saved through the settings form.
    """
    rpc = ctx.adapter.rpc
    try:
        settings_id = rpc.create("res.config.settings", {})
        action = rpc.call("res.config.settings", "avatax_ping", [settings_id])
    except OdooRPCError as exc:
        return True, "", str(exc)
    result_id = action.get("res_id") if isinstance(action, dict) else None
    if not result_id:
        return False, "", f"avatax_ping returned no result record: {action!r}"
    try:
        rows = rpc.read("avatax.connection.test.result", [result_id],
                        ["server_response"])
    except OdooRPCError as exc:
        return True, "", str(exc)
    raw = rows[0].get("server_response") if rows else ""
    return False, _ping_verdict(raw), ""


def _compute_outcome(ctx, move_id, *, full_message=False):
    """Click Compute Taxes → ``(raised, message)``.

    The workbook expects a message on the failure path, so the RPC error is
    captured and asserted on rather than being allowed to ERROR the test.

    ``full_message`` re-reads the server's UNTRUNCATED text through
    ``common.server_error_message``. ``adapters/base.py:156`` keeps only
    ``splitlines()[-1]``, while ``_handle_response`` returns
    "<Odoo title>\\n<Avalara detail>"
    (…/account_external_tax_mixin.py:287-295), so the truncated form would
    have step 6 judge the transport rather than the product's own message.

    Only step 6 asks for it. The re-issued call is a second
    ``create_transaction`` attempt: at step 6 the API KEY is deliberately
    invalid, so Avalara rejects it and nothing is filed. Step 10 runs with the
    real key back and must not send a second document, so it keeps the
    adapter's message.
    """
    try:
        compute_taxes(ctx, "account.move", move_id)
        return False, ""
    except OdooRPCError as exc:
        message = str(exc)
        if full_message:
            message = server_error_message(
                ctx, "account.move", COMPUTE_TAXES_METHOD,
                [move_id]) or message
        return True, message


@test_case(
    id="TEST-FG05-TAX-017",
    name="A bad Avalara connection fails with a readable message, not a crash",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module=MODULE,
    priority="P1",
    kind="API",
    order=513,
    description="Break-and-restore: with an invalid Avalara API KEY the "
                "connection test reports authentication failure and Compute "
                "Taxes raises a readable message while the invoice stays "
                "untaxed, draft and editable; the key is restored in a "
                "finally block and the restore is asserted.",
    traceability=trace("TC-TAX-017"))
def test_tax_017(ctx):
    rpc = ctx.adapter.rpc
    created = {"account.move": [], "res.partner": [], "product.product": []}
    key_written = False
    move_id = None

    with ctx.step("Precondition: Odoo 19 with a usable Avalara SANDBOX"):
        config = require_sandbox(
            ctx, "deliberately breaking and restoring the Avalara API KEY, "
                 "then computing tax on a draft invoice twice")
        company_id = config["company_id"]
        fp_id, fp_vals = require_avatax_fiscal_position(ctx)
        ctx.log(f"AvaTax fiscal position #{fp_id} {fp_vals.get('name')!r}")
        ctx.log("the error-handling path under test is Odoo Enterprise "
                "account_avatax (_get_client / _handle_response / "
                "avatax_ping); mmg_account_avatax_enhancement only renames "
                "the jurisdiction taxes on the success path — route a defect "
                "here to the stock module first")
        sweep_fg05(ctx)

    with ctx.step("Step 1 (workbook): COPY the current API KEY somewhere "
                  "safe — restore-safety probe, run BEFORE any write"):
        readable, original_key = _read_api_key(rpc, company_id)
        if not readable:
            ctx.blocked(
                "res.company.avalara_api_key carries "
                "groups='base.group_system' "
                "(account_avatax/models/res_company.py:16) and this runner "
                "user cannot read it back. TC-TAX-017 overwrites that key on "
                "purpose and MUST put the original back; a key that cannot "
                "be read cannot be restored, so the test refuses to write it "
                "at all rather than leave the system unable to calculate any "
                "tax (workbook 'Why It Matters'). Re-run as a user in "
                "Settings / Administration (base.group_system).")
        if not original_key:
            ctx.blocked(
                f"res.company.avalara_api_key reads back EMPTY on company "
                f"#{company_id}, so there is no original value to restore "
                f"after the deliberate break. Configure the sandbox API KEY "
                f"first (Accounting > Configuration > Settings > Taxes > "
                f"AvaTax) — TC-TAX-017 is not run against an unconfigured "
                f"company.")
        if original_key == INVALID_KEY:
            ctx.blocked(
                f"the company's Avalara API KEY is ALREADY the invalid UAT "
                f"string {INVALID_KEY!r} — a previous run of TC-TAX-017 did "
                f"not complete its restore step. Restoring 'the original' "
                f"now would only re-save the broken value. {MANUAL_RECOVERY}")
        ctx.check_true(
            "Step 1: the current API KEY is readable, so the restore at step "
            "8 can be guaranteed",
            readable and bool(original_key),
            actual_desc=f"res.company #{company_id} avalara_api_key: "
                        f"{_fingerprint(original_key)}")

    try:
        with ctx.step("Test Data: FG05 customer at the Phoenix AZ address on "
                      "the AvaTax fiscal position + one art item at 1,000.00"):
            # Built in-test on purpose: the workbook's "TC-TAX-001 has passed"
            # precondition may not be leaned on as a fixture dependency.
            partner_id = make_partner(ctx, "TAX-017 Customer",
                                      ADDRESS_PHOENIX_AZ,
                                      fiscal_position_id=fp_id)
            created["res.partner"].append(partner_id)
            product_id = make_product(ctx, "TAX-017 Art Item", LINE_PRICE)
            created["product.product"].append(product_id)
            # Without a resolvable Avalara tax code the line raises "The
            # Avalara Tax Code is required for …" BEFORE the HTTP call, which
            # would make step 6 pass on the wrong error and step 10 fail for
            # an unrelated reason. make_product files every FG05 fixture under
            # the shared FG05 AvaTax category (common.fg05_product_category),
            # which BLOCKS if the database carries no product.avatax.category
            # at all — so this is a read-back of a guaranteed precondition,
            # deliberately made BEFORE the credential is broken.
            avatax_categ, categ_source = _resolve_avatax_category(rpc,
                                                                  product_id)
            if not avatax_categ:
                ctx.blocked(
                    f"the FG05 fixture product #{product_id} resolves no "
                    f"Avalara Tax Code even though common.make_product filed "
                    f"it under the FG05 AvaTax product category: nothing in "
                    f"its product -> template -> category chain carries a "
                    f"product.avatax.category "
                    f"(account_avatax/models/product.py:29-57). Compute "
                    f"Taxes would then fail with 'The Avalara Tax Code is "
                    f"required for ...' for a reason that has nothing to do "
                    f"with the credential this case breaks, so the break is "
                    f"NOT applied. Check that the FG05 category kept its "
                    f"Avatax Category, then re-run.")
            ctx.check_true(
                "the art item resolves an Avalara Tax Code, so a failing "
                "Compute Taxes at step 6 can only be the broken credential",
                bool(avatax_categ),
                actual_desc=f"product.avatax.category #{avatax_categ} "
                            f"resolved from {categ_source or 'nothing'}")

        try:
            with ctx.step(f"Step 2 (workbook): replace the API KEY with "
                          f"{INVALID_KEY!r} and save — DELIBERATE BREAK, "
                          f"restored at step 8"):
                # ARM THE RESTORE BEFORE THE WRITE, never after it.
                # OdooRPC.call turns any OSError from
                # opener.open(..., timeout=900) into an OdooRPCError
                # (adapters/base.py:144-148), and a socket/read timeout can
                # surface AFTER the server has already committed the write.
                # Arming afterwards leaves that window with a broken
                # credential and a step 8 that believes nothing was broken.
                # The restore write is idempotent, so arming early costs at
                # worst a no-op re-write of the unchanged key.
                key_written = True
                rpc.write("res.company", [company_id],
                          {"avalara_api_key": INVALID_KEY})
                _, broken_key = _read_api_key(rpc, company_id)
                ctx.check("Step 2: the invalid key is what the company now "
                          "carries (compared by fingerprint, never by value)",
                          _fingerprint(INVALID_KEY), _fingerprint(broken_key))
                ctx.log("Avalara credentials are now BROKEN on purpose — "
                        "step 8 runs in a finally block and restores them "
                        "whatever happens from here")

            with ctx.step("Step 3 (workbook): click Test connection and read "
                          "the Server Response pop-up"):
                raised, verdict, ping_error = _test_connection(ctx)
                detail = verdict or f"no Server Response — {ping_error}"
                ctx.log(f"Server Response verdict: {detail!r} (the <ul> "
                        f"detail list is dropped from evidence: it echoes "
                        f"the authenticated Avalara user back)")
                ctx.check_true(
                    "Step 3: Test connection reports an authentication "
                    "FAILURE, not success",
                    (not raised) and PING_FAIL in verdict
                    and PING_OK not in verdict,
                    actual_desc=f"Server Response verdict: {detail!r}")

            with ctx.step("Step 4 (workbook): new customer invoice on the "
                          "AvaTax fiscal position, one line at 1,000.00, "
                          "save"):
                move_id = make_invoice(ctx, partner_id,
                                       [(product_id, 1, LINE_PRICE)],
                                       fiscal_position_id=fp_id)
                created["account.move"].append(move_id)
                draft = doc_totals(ctx, "account.move", move_id)
                ctx.check("Step 4: Untaxed Amount on the saved draft",
                          1000.00, draft["untaxed"])
                ctx.check("Step 4: the invoice is saved in DRAFT",
                          "draft", draft["state"])

            with ctx.step("Step 5-6 (workbook): click Compute Taxes and read "
                          "the message that appears, in full"):
                # full_message=True: the readability expectation below is
                # about the message the SERVER produced, so the untruncated
                # error.data.message is re-read rather than the last line
                # adapters/base.py:156 kept. Safe here — the credential is
                # invalid at this point, so the repeat is a second rejected
                # authentication and files no document.
                raised, message = _compute_outcome(ctx, move_id,
                                                   full_message=True)
                message = _redact(message, [original_key])
                # The If-It-Fails column asks for this text verbatim on the
                # defect, so the WHOLE message is logged.
                ctx.log(f"Step 6 message (full server text, re-read "
                        f"untruncated via common.server_error_message): "
                        f"{message!r}")
                ctx.check_true(
                    "Step 6: Compute Taxes reports an error instead of "
                    "silently succeeding against a rejected credential",
                    raised,
                    actual_desc=(f"error raised: {message!r}" if raised
                                 else "no error raised — Compute Taxes "
                                      "returned normally with an invalid "
                                      "API KEY"))
                ctx.check(
                    "Step 6: the message is not a raw technical trace",
                    False, TRACEBACK_MARK in message)
                # the server's own sentence, without the platform's
                # "<model>.<method> failed: " wrapper
                body = (message[len(RPC_ERROR_PREFIX):]
                        if message.startswith(RPC_ERROR_PREFIX) else message)
                words = [w for w in body.split()
                         if any(c.isalpha() for c in w)]
                letters = sum(1 for c in body if c.isalpha())
                # Asserted on the WHOLE server message, not on the
                # fragment the transport left. _handle_response returns
                # "<Odoo title>\n<Avalara detail>"
                # (…/account_external_tax_mixin.py:287-295) and
                # adapters/base.py:156 keeps only that last line, so a
                # perfectly readable two-line pop-up could arrive as one
                # short fragment and be reported as a defect it is not.
                # The floor stays deliberately low — a genuine Avalara
                # detail can be one short sentence ("Authentication
                # Incomplete."; the module's own fixture shows the shape
                # at account_avatax/tests/test_avatax.py:172 "Document
                # not found.") — and it still rules out exactly what the
                # workbook rules out: a blank screen and a bare code both
                # FAIL. "Explains what happened" is asserted separately,
                # by CONNECTION_VOCABULARY below.
                ctx.check_true(
                    "Step 6: the message is readable text — not a blank "
                    "screen and not a bare code",
                    bool(body.strip()) and letters >= 8,
                    actual_desc=f"{len(words)} word(s) / {letters} letter(s): "
                                f"{body!r}")
                matched = [word for word in CONNECTION_VOCABULARY
                           if word in body.lower()]
                ctx.check_true(
                    "Step 6: the message explains that Avalara could not be "
                    "reached or the credentials were rejected",
                    bool(matched),
                    actual_desc=f"vocabulary matched {matched} in {body!r}")

            with ctx.step("Step 7 (workbook): the invoice carries NO tax "
                          "figure and is still draft and editable"):
                after = doc_totals(ctx, "account.move", move_id)
                ctx.check("Step 7: Taxes on the invoice",
                          0.00, after["tax"])
                ctx.check("Step 7: Untaxed Amount is untouched",
                          1000.00, after["untaxed"])
                tax_lines = move_tax_lines(ctx, move_id)
                ctx.check(
                    "Step 7: no tax journal item was written — the invoice "
                    "is not half-taxed",
                    0, len(tax_lines))
                ctx.check("Step 7: the invoice is still in DRAFT",
                          "draft", after["state"])
                probe = f"{MARK} TAX-017 editable probe"
                try:
                    rpc.write("account.move", [move_id], {"ref": probe})
                    back = rpc.read("account.move", [move_id],
                                    ["ref"])[0].get("ref")
                except OdooRPCError as exc:
                    back = f"write refused: {exc}"
                ctx.check(
                    "Step 7: the invoice is still editable — Reference "
                    "written and read back, so it is not locked",
                    probe, back)
        finally:
            with ctx.step("Step 8 (workbook, MANDATORY): restore the correct "
                          "API KEY and prove it is back"):
                restore_note = ""
                if key_written:
                    try:
                        rpc.write("res.company", [company_id],
                                  {"avalara_api_key": original_key})
                    except OdooRPCError as exc:
                        restore_note = f"restore write refused: {exc}"
                else:
                    ctx.log("no break was applied — nothing to restore")
                readable_now, key_now = _read_api_key(rpc, company_id)
                if not readable_now:
                    restore_note = "; ".join(
                        p for p in (restore_note,
                                    "the API KEY is no longer readable back, "
                                    "so the restore could not be verified")
                        if p)
                if _fingerprint(key_now) != _fingerprint(original_key):
                    reason = restore_note or ("value mismatch after the "
                                              "restore write")
                    ctx.log(f"!!! RESTORE FAILED — the company's Avalara API "
                            f"KEY does NOT match the value captured at step "
                            f"1. {reason}. {MANUAL_RECOVERY}")
                else:
                    ctx.log("API KEY restored — fingerprint matches the "
                            "value captured at step 1")
                ctx.check(
                    "Step 8: the original API KEY is restored on the company "
                    "(compared by fingerprint, never by value)",
                    _fingerprint(original_key), _fingerprint(key_now))

        with ctx.step("Step 9 (workbook): click Test connection again"):
            raised, verdict, ping_error = _test_connection(ctx)
            detail = verdict or f"no Server Response — {ping_error}"
            ctx.check_true(
                "Step 9: Test connection reports success again",
                (not raised) and PING_OK in verdict,
                actual_desc=f"Server Response verdict: {detail!r}")

        with ctx.step("Step 10 (workbook): return to the invoice and click "
                      "Compute Taxes"):
            raised, message = _compute_outcome(ctx, move_id)
            message = _redact(message, [original_key])
            ctx.check_true(
                "Step 10: Compute Taxes succeeds once the correct key is "
                "back",
                not raised,
                actual_desc=("computed without error" if not raised
                             else f"error raised: {message!r}"))
            final = doc_totals(ctx, "account.move", move_id)
            ctx.check("Step 10: Untaxed Amount is still the line total",
                      1000.00, final["untaxed"])
            ctx.check_true(
                "Step 10: tax now calculates normally — a non-zero tax "
                "figure is on the invoice",
                final["tax"] > 0,
                actual_desc=f"Taxes = {final['tax']:.2f}, Total = "
                            f"{final['total']:.2f}, state = {final['state']!r}")
            ctx.log("State After The Test — the correct API KEY is restored "
                    "and Test connection succeeds (asserted at steps 8 and "
                    "9); the sandbox tax computation at step 10 confirms the "
                    "database can calculate tax again")
    finally:
        with ctx.step("Cleanup: remove FG05 fixtures"):
            cleanup(ctx, created)
