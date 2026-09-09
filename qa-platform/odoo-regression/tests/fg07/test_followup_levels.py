"""FG-07 — TC-INV-013: the chasing / follow-up levels are still set up.

Implements row 39.0 (P2, "Collections") of the CLIENT MANUAL TESTING
GUIDELINE ``MMG_v19_Client_Manual_Testing_Guideline_FG05-FG14_v1.0.xlsx`` /
sheet ``Testing Guideline``.

The workbook's framing: *"The gallery chases overdue invoices on a schedule.
Those levels — how many days, what the letter says — are configuration that an
upgrade can drop."* Its Why It Matters is the reason this P2 is worth
automating at all: *"if the levels are gone the gallery silently stops chasing
anybody, and that is only noticed at the next receivables review."*

Read-only by construction
-------------------------
The workbook's *State After The Test* is "Nothing changed". This module
creates no record, writes no field, and calls neither ``sweep_fg07`` nor
``cleanup`` — a sweep is itself a delete and would violate the workbook.

Where the levels live in Odoo 19
--------------------------------
One model, one list, no parent "policy" record:
``account_followup.followup.line``
(``enterprise-19.0/account_followup/models/account_followup.py:8-49``).
The workbook's navigation "Accounting > Configuration > Invoicing > Follow-up
Levels" is exactly the menu tree
``account.menu_finance_configuration`` (Configuration,
``addons/account/views/account_menuitem.xml:46``) >
``account.account_invoicing_menu`` (Invoicing, same file ``:59``) >
``account_followup.account_followup_menu`` (Follow-up Levels,
``enterprise-19.0/account_followup/views/account_followup_line_views.xml:104``),
whose action ``action_account_followup_line_definition_form`` (same file
``:87-102``) opens that model. Every leg of that path is resolved by xmlid
here rather than trusted, because the workbook's *If It Fails* column asks the
tester to separate "the menu is missing" from "the levels are missing" — they
have different fixes.

The 3 Expected Result lines, and what each is read from
-------------------------------------------------------
1. **"Every level on the baseline is present with the same day count."** —
   read from ``account_followup.followup.line`` ``name`` (labelled
   *Description*, ``account_followup.py:14``) and ``delay`` (labelled *Due
   Days*, ``:15``), searched under the acting company only because the model
   carries a global multi-company ``ir.rule``
   (``security/account_followup_security.xml:4-9``).
   The comparison against Novobi's list is a **RESIDUAL MANUAL STEP** — the
   platform does not hold the old system's levels and must not invent them.
   What *is* asserted without a baseline: at least one level exists (zero
   levels is the silent-stop-chasing failure the workbook is about, and needs
   no baseline to judge), every level carries a non-blank Description, and
   every level belongs to the acting company.
2. **"The message body on the level you opened is intact and readable."** —
   Odoo 19's level has **no** body / description / printed-message field of
   its own; the letter lives on the linked template. So this line is read
   from ``mail_template_id`` (``account_followup.py:20``, domain
   ``[('model','=','res.partner')]``) -> ``mail.template.body_html``
   (``addons/mail/models/mail_template.py:69``) and ``subject`` (``:51``),
   and, for the SMS leg, from ``sms_template_id`` (``account_followup.py:26``)
   -> ``sms.template.body`` (``addons/sms/models/sms_template.py:28``). Both
   templates are readable by any internal user
   (``addons/mail/security/ir.model.access.csv:39`` and
   ``addons/mail/security/mail_security.xml:275-284``, whose employee rule
   sets ``perm_read`` False so reading is unrestricted;
   ``addons/sms/security/ir.model.access.csv:5``).
   A level with ``send_email`` True (default True, ``account_followup.py:21``)
   and an empty ``mail_template_id`` is **the v19 shape of "the message body
   is gone"**, and it is failed with those words.
   *Strengthening, declared:* the workbook opens **one** level; this case
   opens **every** level. A superset of the workbook's check, never a subset.
3. **"The order of the levels matches the baseline."** — the model's own
   ``_order`` is ``'delay asc'`` (``account_followup.py:11``), so the order in
   which the list view shows the levels **is** the day-count order; there is
   no sequence field to reorder them by hand. Read by issuing the search with
   no ``order`` argument at all, so the database applies ``_order`` itself,
   and asserting the delays come back strictly increasing. Strictly, not
   merely non-decreasing: the SQL constraint ``unique(company_id, delay)``
   (``account_followup.py:42-45``) forbids a tie, so a tie means the
   constraint did not survive the upgrade. Matching that order against
   Novobi's list is again a RESIDUAL MANUAL STEP.

Documented adaptation — the Novobi baseline the platform does not hold
----------------------------------------------------------------------
Two of the three Expected Result lines are tick-offs against "the Novobi
baseline list of levels" (workbook *Test Data*). The platform holds no such
list and inventing one would be worse than not checking. So the levels are
**captured in full** — day count, description, every action, the template
behind each one and the first characters of the letter itself — printed into
the execution log and written to two CSV artifacts, and the tick-off is named
as a RESIDUAL MANUAL STEP with the captured levels in the message. The human
step is then a comparison, never a re-run.

Workbook step 3 ("check the message body … reads correctly") splits the same
way: *present and non-blank* is machine-checkable and is asserted; *reads
correctly* is a human judgement and is a RESIDUAL MANUAL STEP, with the letter
text supplied in ``TC-INV-013-followup-messages.csv`` so the human reads
rather than re-navigates.

A finding this case is built to surface
---------------------------------------
Odoo 19 ships two follow-up levels of its own — "15 Days" / delay 15 and
"30 Days" / delay 30 — in ``data/account_followup_data.xml:4-10`` and
``:47-53``, both ``forcecreate="False"``. If the database comes back holding
**exactly** those two, the most likely explanation is not that the gallery's
levels were edited down to two: it is that they were never migrated and a
fresh default set was created by the module's own data file. That is a far
more actionable verdict than "the count does not match", so it is detected,
named, cross-checked against ``ir.model.data`` (which says which module owns
each level record) and printed as a FINDING plus a pointed residual note. It
is **not** asserted, in either direction: the condition the finding turns on
is "and the baseline says otherwise", and the baseline is exactly what this
platform does not have. Asserting it would be inventing a baseline.

The other expected v19 difference, logged as an OBSERVATION and asserted in
neither direction: v15-era level fields that carried the printed letter and
the manual action (``description`` / ``send_letter`` / ``print_letter`` /
``manual_action*``) have no counterpart on the v19 model — the v19 model's
complete field list is ``account_followup.py:14-40``. [UNVERIFIED] The exact
v15 field names are not verifiable on this machine: no Odoo 15 Enterprise
tree is present (only the MMG v15 custom modules at
``D:/Projects/mmg/psus-medicine-man-gallery``, which do not include
``account_followup``). They are therefore probed by name at run time with
``fields_get`` and merely reported absent, never assumed present.

Source trees these citations were read from
-------------------------------------------
* Odoo 19 Community — ``D:/Projects/odoo-19.0/addons``
* Odoo 19 Enterprise — ``D:/Projects/odoo-19.0/enterprise-19.0``
"""
from __future__ import annotations

import csv
import re

from adapters.base import OdooRPCError
from framework.registry import test_case
from tests.fg07.common import (FOLLOWUP_MENU_XMLID, FOLLOWUP_MODEL,
                               FOLLOWUP_V19_DEFAULTS, NO_FOLLOWUP, WORKFLOW,
                               WORKFLOW_NAME, acting_company, company_ctx,
                               fields_present, finding, has_group, m2o_id,
                               m2o_name, menu_by_xmlid, module_state,
                               observation, require_module, require_v19,
                               residual_manual_step, trace)

LEVELS_CSV = "TC-INV-013-followup-levels.csv"
MESSAGES_CSV = "TC-INV-013-followup-messages.csv"

LEVELS_HEADER = ["position", "delay_days", "description", "company",
                 "send_email", "email_template", "email_subject",
                 "email_body_chars", "attach_invoices", "send_sms",
                 "sms_template", "sms_body_chars", "schedule_activity",
                 "activity_type", "automatic", "owned_by_module", "xmlid"]
MESSAGES_HEADER = ["delay_days", "description", "channel", "template",
                   "subject", "body_text"]

# The two menus the workbook's step 1 walks through, innermost last. Asserted
# by xmlid rather than by label so a translated database still passes.
CONFIG_MENU_XMLID = "account.menu_finance_configuration"
INVOICING_MENU_XMLID = "account.account_invoicing_menu"
MENU_PATH = "Accounting > Configuration > Invoicing > Follow-up Levels"

# The group the Follow-up Levels menu is restricted to
# (views/account_followup_line_views.xml:104). The workbook's precondition is
# "You have the Administrator accounting group" — this is that group.
MANAGER_GROUP = "account.group_account_manager"
# The lowest group that may READ the levels
# (security/ir.model.access.csv:2). A user with only this group cannot see
# the menu but can still be measured against every Expected Result line.
READONLY_GROUP = "account.group_account_readonly"

# Fields on the v19 level, in the order the form view shows them
# (views/account_followup_line_views.xml:24-71). Read through
# fields_present() first: a field the acting user has no group for is omitted
# by fields_get, and reading it anyway would turn a permission into a crash.
LEVEL_FIELDS = ("name", "delay", "company_id", "send_email",
                "mail_template_id", "join_invoices", "send_sms",
                "sms_template_id", "create_activity", "activity_type_id",
                "activity_summary", "activity_default_responsible_type",
                "auto_execute")

# v15-era level fields that carried the printed letter and the manual action.
# [UNVERIFIED] — no Odoo 15 Enterprise tree exists on this machine, so these
# are CANDIDATE names probed at run time, never assumed. Each one that is
# absent is reported as "no v19 field" so the tester's tick-off does not
# stall on a row that cannot exist any more.
V15_ERA_FIELD_CANDIDATES = ("description", "send_letter", "print_letter",
                            "manual_action", "manual_action_note",
                            "manual_action_type_id",
                            "manual_action_responsible_id", "sms_description",
                            "email_subject", "body", "body_html")

# Cap on how much of a letter goes into the CSV. The whole point of the
# messages CSV is that a human reads the letter without re-navigating, so the
# cap is generous; it exists only to stop a pathological template producing an
# unopenable file.
BODY_CHARS_IN_CSV = 4000

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _plain_text(html: str) -> str:
    """A readable rendering of an Html field, for the log and the CSV.

    Deliberately a tag strip and not a parse: nothing is asserted on this
    value, it exists so the human doing the "reads correctly" half of workbook
    step 3 sees the letter rather than its markup. ``<br>`` and block ends are
    turned into spaces first so words do not run together.
    """
    text = re.sub(r"<\s*br\s*/?>|</\s*(p|div|li|tr|h[1-6])\s*>", " ",
                  html or "", flags=re.I)
    text = _TAG_RE.sub(" ", text)
    for entity, char in (("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"),
                         ("&gt;", ">"), ("&quot;", '"'), ("&#39;", "'")):
        text = text.replace(entity, char)
    return _WS_RE.sub(" ", text).strip()


def _body_is_blank(html: str) -> bool:
    """True when an Html body carries no words a customer could read.

    ``body_html`` is never NULL in practice — an emptied rich-text editor
    stores ``<p><br></p>`` — so a truthiness test would call a wiped letter
    intact. Odoo's own ``is_html_empty`` makes the same distinction, which is
    why the shipped template guards its signature with it
    (``data/account_followup_data.xml:33``).
    """
    return not _plain_text(html)


def _owner_xmlid(rpc, model: str, res_id: int) -> tuple[str, str]:
    """``(module, name)`` of the ir.model.data row owning a record, or ('','').

    Evidence for the default-data finding: a level the gallery configured has
    no xmlid at all, while Odoo 19's two shipped levels are owned by
    ``account_followup.demo_followup_line1`` / ``demo_followup_line2``
    (``data/account_followup_data.xml:4`` and ``:47``). Never raises — a
    database where ir.model.data is unreadable still gets every other check.
    """
    try:
        rows = rpc.search_read("ir.model.data",
                               [("model", "=", model), ("res_id", "=", res_id)],
                               ["module", "name"], limit=1)
    except OdooRPCError:
        return "", ""
    if not rows:
        return "", ""
    return rows[0].get("module") or "", rows[0].get("name") or ""


@test_case(
    id="TEST-FG07-INV-013",
    name="The chasing / follow-up levels are still set up",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module="account_followup",
    priority="P2",
    kind="DATA",
    order=710,
    description="Read-only read of every account_followup.followup.line under "
                "the acting company: the Follow-up Levels menu resolves along "
                "the workbook's own path, at least one level exists, the day "
                "counts are strictly increasing in the model's own delay-asc "
                "order, and every level's letter (mail.template.body_html, "
                "sms.template.body) is present and non-blank. Creates "
                "nothing; the tick-off against the Novobi baseline is a "
                "residual manual step.",
    traceability=trace("TC-INV-013"))
def test_inv_013(ctx):
    rpc = ctx.adapter.rpc
    # Both accumulators are declared before the try, not inside the step that
    # fills them: the evidence block runs from `finally` and must not raise a
    # NameError over a step an earlier assertion failure skipped — that would
    # replace a real FAILED verdict with an AUTOMATION_ERROR.
    levels: list[dict] = []
    messages: list[list] = []
    residual: list[str] = []

    with ctx.step("Precondition (workbook): the follow-up module is installed "
                  "and you have the Administrator accounting group"):
        require_v19(ctx)

        # Report the whole dependency chain BEFORE blocking on it.
        # account_followup depends on account_reports and is auto_install=True
        # (__manifest__.py:25 and :45), so when it is absent the useful
        # question is which layer below it is absent too — the workbook's If
        # It Fails column calls a missing menu "a different problem from
        # missing levels", and this is the line that tells the reader which.
        for name in ("account_followup", "account_reports", "account"):
            ctx.log(f"ir.module.module state for {name!r}: "
                    f"{module_state(rpc, name) or 'no such module row'}")
        require_module(ctx, "account_followup", NO_FOLLOWUP)

        # Probe the model as a REGISTRY cross-check, never as the installed
        # test: the module list and the loaded registry can disagree when an
        # upgrade fails half-way, and that disagreement is worth its own
        # sentence rather than a confusing "method does not exist" later.
        if not rpc.model_exists(FOLLOWUP_MODEL):
            ctx.blocked(
                f"{NO_FOLLOWUP} — ir.module.module says account_followup is "
                f"installed, but the model {FOLLOWUP_MODEL!r} is not in the "
                f"registry (enterprise-19.0/account_followup/models/"
                f"account_followup.py:9). The module list and the registry "
                f"disagree; a module upgrade probably failed half-way")

        company = acting_company(ctx)
        ctx.log(f"acting company #{company['id']} {company['name']!r}")

        # The menu is restricted to account.group_account_manager, but the
        # MODEL is readable from account.group_account_readonly upward
        # (security/ir.model.access.csv:2-4). Those two facts are reported
        # separately because they fail differently: without the manager group
        # the tester cannot walk the workbook's step 1, but every Expected
        # Result line can still be measured.
        is_manager = has_group(ctx, MANAGER_GROUP)
        is_reader = is_manager or has_group(ctx, READONLY_GROUP)
        ctx.log(f"runner user: {MANAGER_GROUP} = {is_manager}, "
                f"{READONLY_GROUP} = {is_reader}")
        if not is_manager:
            residual.append(
                f"the runner user does NOT hold {MANAGER_GROUP}, which is the "
                f"group the '{MENU_PATH}' menu item is restricted to "
                f"(views/account_followup_line_views.xml:104). Every Expected "
                f"Result line below was still measured, because the model is "
                f"readable from {READONLY_GROUP} upward "
                f"(security/ir.model.access.csv:2-4) — but a client "
                f"accountant walking the workbook's step 1 needs the "
                f"Administrator accounting group the Preconditions ask for, "
                f"so confirm THEY have it before accepting this run as the "
                f"navigation check.")

        # A read that raises here is a permission fact, not a defect, and it
        # must be said as one rather than escaping as AUTOMATION_ERROR.
        try:
            rpc.search(FOLLOWUP_MODEL, [], limit=1)
        except OdooRPCError as exc:
            ctx.blocked(
                f"the runner user cannot read {FOLLOWUP_MODEL} on this "
                f"database ({exc}), so none of the three Expected Result "
                f"lines can be measured and nothing here is evidence about "
                f"the gallery's levels. Grant the runner {READONLY_GROUP} or "
                f"higher (security/ir.model.access.csv:2-4) and re-run")

    try:
        with ctx.step("Step 1 / If It Fails: 'Accounting > Configuration > "
                      "Invoicing > Follow-up Levels' resolves — a missing "
                      "menu is a different problem from missing levels"):
            menu = menu_by_xmlid(ctx, FOLLOWUP_MENU_XMLID)
            ctx.log(f"{FOLLOWUP_MENU_XMLID} -> {menu or '(does not resolve)'}")
            ctx.check_true(
                f"The Follow-up Levels menu item still exists "
                f"({FOLLOWUP_MENU_XMLID})",
                bool(menu),
                actual_desc=f"ir.model.data lookup returned "
                            f"{menu.get('id') or 'nothing'}; the workbook's If "
                            f"It Fails column asks you to say so explicitly, "
                            f"because a missing MENU means the follow-up "
                            f"module did not install, not that the levels "
                            f"were lost")
            ctx.check_true(
                "The Follow-up Levels menu item is active (not archived out "
                "of the Configuration list)",
                menu.get("active") is True,
                actual_desc=f"ir.ui.menu.active = {menu.get('active')!r}")

            # The workbook's path is asserted leg by leg by xmlid, so a
            # translated database still passes and a menu that was reparented
            # into some other section is still caught.
            invoicing_id = rpc.ref(INVOICING_MENU_XMLID)
            config_id = rpc.ref(CONFIG_MENU_XMLID)
            invoicing = menu_by_xmlid(ctx, INVOICING_MENU_XMLID)
            ctx.log(f"menu path: {CONFIG_MENU_XMLID} #{config_id} > "
                    f"{INVOICING_MENU_XMLID} #{invoicing_id} "
                    f"({invoicing.get('name')!r}) > Follow-up Levels "
                    f"#{menu.get('id')} ({menu.get('name')!r})")
            ctx.check("Follow-up Levels hangs under Configuration > Invoicing, "
                      "the path the workbook's step 1 walks "
                      "(addons/account/views/account_menuitem.xml:46,59)",
                      invoicing_id, menu.get("parent_id"))
            ctx.check("…and Invoicing hangs under Accounting > Configuration",
                      config_id, invoicing.get("parent_id"))

            # The action behind the menu is what proves the menu leads to the
            # LEVELS and not to some other list that inherited its place.
            action_ref = menu.get("action") or ""
            action_model = ""
            if "," in action_ref:
                action_kind, _, action_id = action_ref.partition(",")
                try:
                    action_row = rpc.read(action_kind.strip(),
                                          [int(action_id)],
                                          ["name", "res_model"])[0]
                    action_model = action_row.get("res_model") or ""
                    ctx.log(f"menu action {action_ref} -> "
                            f"{action_row.get('name')!r} on {action_model!r}")
                except (OdooRPCError, ValueError, IndexError) as exc:
                    ctx.log(f"menu action {action_ref!r} could not be read "
                            f"({exc}) — reported as unreadable rather than "
                            f"guessed")
            ctx.check("The Follow-up Levels menu opens the follow-up level "
                      "list itself (action res_model)",
                      FOLLOWUP_MODEL, action_model)

        with ctx.step("Step 2 / Expected line 1: read the list of levels — "
                      "the number of days and the description"):
            readable = fields_present(rpc, FOLLOWUP_MODEL, LEVEL_FIELDS)
            wanted = [f for f in LEVEL_FIELDS if f in readable]
            missing = [f for f in LEVEL_FIELDS if f not in readable]
            if missing:
                # Not a failure by itself: fields_get omits what the acting
                # user has no group for. It IS reported, because every field
                # omitted here is a tick-off row that silently went unchecked.
                ctx.log(f"NOT READABLE by the runner user (omitted from "
                        f"fields_get, so omitted from every check below): "
                        f"{', '.join(missing)}")

            # No `order` argument on purpose — see Expected line 3 in the
            # module docstring. The database applies the model's own
            # _order = 'delay asc' (account_followup.py:11), so what comes
            # back IS the order the Follow-up Levels list shows.
            rows = rpc.search_read(
                FOLLOWUP_MODEL,
                [("company_id", "in", [company["id"], False])],
                wanted, context=company_ctx(company))
            for position, row in enumerate(rows, start=1):
                mail_id = m2o_id(row.get("mail_template_id"))
                sms_id = m2o_id(row.get("sms_template_id"))
                levels.append({
                    "id": row.get("id"),
                    "position": position,
                    "delay": int(row.get("delay") or 0),
                    "name": (row.get("name") or "").strip(),
                    "company": m2o_name(row.get("company_id")),
                    "company_id": m2o_id(row.get("company_id")),
                    "send_email": bool(row.get("send_email")),
                    "mail_template_id": mail_id,
                    "mail_template": m2o_name(row.get("mail_template_id")),
                    "join_invoices": bool(row.get("join_invoices")),
                    "send_sms": bool(row.get("send_sms")),
                    "sms_template_id": sms_id,
                    "sms_template": m2o_name(row.get("sms_template_id")),
                    "create_activity": bool(row.get("create_activity")),
                    "activity_type": m2o_name(row.get("activity_type_id")),
                    "activity_type_id": m2o_id(row.get("activity_type_id")),
                    "auto_execute": bool(row.get("auto_execute")),
                })
            for level in levels:
                module, xmlid_name = _owner_xmlid(rpc, FOLLOWUP_MODEL,
                                                  level["id"])
                level["owner_module"] = module
                level["xmlid"] = f"{module}.{xmlid_name}" if module else ""
                ctx.log(
                    f"  level {level['position']}: {level['delay']} day(s) "
                    f"after due date — {level['name']!r} "
                    f"[email={level['send_email']} "
                    f"template={level['mail_template'] or '(none)'!r}; "
                    f"sms={level['send_sms']} "
                    f"template={level['sms_template'] or '(none)'!r}; "
                    f"activity={level['create_activity']} "
                    f"{level['activity_type'] or ''!r}; "
                    f"automatic={level['auto_execute']}]"
                    + (f" owned by {level['xmlid']}" if level["xmlid"] else ""))

            # Zero levels is the whole failure the workbook is about ("the
            # gallery silently stops chasing anybody"), and it needs no
            # baseline to judge — so it is a real assertion, not a note.
            ctx.check_true(
                "The gallery still has at least one follow-up level, so "
                "overdue invoices are still chased at all",
                bool(levels),
                actual_desc=f"{len(levels)} level(s) found on "
                            f"{FOLLOWUP_MODEL} for company "
                            f"#{company['id']} {company['name']!r} — zero "
                            f"means nobody is chased and nothing on screen "
                            f"says so")

            # 'the description' half of the tick-off. name is required at the
            # ORM level (account_followup.py:14), so a blank one means the
            # column was written past the ORM during the migration.
            blank_names = [f"level at {lv['delay']} day(s) (id {lv['id']})"
                           for lv in levels if not lv["name"]]
            ctx.check("Every follow-up level still carries a Description, the "
                      "column the tester ticks off by name", [], blank_names)

            # A level whose company is neither the acting company nor shared
            # would not appear on this accountant's screen at all.
            foreign = [f"{lv['name']!r} -> {lv['company']!r}"
                       for lv in levels
                       if lv["company_id"] not in (company["id"], None)]
            ctx.check(f"Every level read belongs to "
                      f"{company['name']!r} (or is shared across companies), "
                      f"so the tick-off is against this gallery's own list",
                      [], foreign)

        with ctx.step("Step 4 / Expected line 3: the levels are in the right "
                      "order and the day counts match"):
            delays = [lv["delay"] for lv in levels]
            ctx.log(f"day counts in the model's own delay-asc order: {delays}")

            # Strictly increasing, not merely sorted: unique(company_id, delay)
            # (account_followup.py:42-45) forbids a tie, so a tie means the SQL
            # constraint did not survive the upgrade — two levels would then
            # fire on the same day and the customer gets two letters.
            out_of_order = [
                f"level {lv['position']} {lv['name']!r} at {lv['delay']} "
                f"day(s) follows {prev['delay']} day(s)"
                for prev, lv in zip(levels, levels[1:])
                if lv["delay"] <= prev["delay"]]
            ctx.check(
                "Reading the Follow-up Levels list top to bottom gives "
                "strictly increasing day counts (the model orders itself by "
                "'delay asc' and unique(company_id, delay) forbids a tie)",
                [], out_of_order)

            residual.append(
                "tick the day counts and descriptions off against the Novobi "
                "baseline list of levels, which the platform does not hold. "
                "In the order the Follow-up Levels list shows them, this "
                "database has: "
                + ("; ".join(f"{lv['delay']} day(s) = {lv['name']!r}"
                             for lv in levels) or "(no levels at all)")
                + f". That is {len(levels)} level(s). Expected Result lines 1 "
                  f"and 3 are both this one comparison: same levels, same day "
                  f"counts, same order. The full row-by-row detail is in "
                  f"{LEVELS_CSV}.")

        with ctx.step("Step 3 / Expected line 2: open each level and check "
                      "the message body is still there"):
            # Odoo 19 keeps no letter on the level itself; it keeps a link to
            # a template. So 'the message body is gone' has two distinct
            # shapes in v19 and both are checked: the LINK is empty, or the
            # link resolves to a template whose body is empty.
            mail_ids = sorted({lv["mail_template_id"] for lv in levels
                               if lv["mail_template_id"]})
            sms_ids = sorted({lv["sms_template_id"] for lv in levels
                              if lv["sms_template_id"]})
            mail_rows, sms_rows = {}, {}
            mail_unreadable = sms_unreadable = ""
            if mail_ids:
                try:
                    mail_rows = {
                        row["id"]: row for row in
                        rpc.read("mail.template", mail_ids,
                                 ["name", "subject", "body_html", "model"])}
                except OdooRPCError as exc:
                    mail_unreadable = str(exc)
            if sms_ids:
                try:
                    sms_rows = {row["id"]: row for row in
                                rpc.read("sms.template", sms_ids,
                                         ["name", "body", "model"])}
                except OdooRPCError as exc:
                    sms_unreadable = str(exc)
            # "not readable" is reported as its own fact and never counted as
            # "empty": a permission is not a missing letter.
            if mail_unreadable:
                ctx.log(f"mail.template is NOT READABLE by the runner user "
                        f"({mail_unreadable}) — the email bodies below are "
                        f"recorded as 'not readable', which is NOT the same "
                        f"finding as an empty letter")
            if sms_unreadable:
                ctx.log(f"sms.template is NOT READABLE by the runner user "
                        f"({sms_unreadable}) — the SMS bodies below are "
                        f"recorded as 'not readable'")

            no_letter, blank_letter, wrong_model = [], [], []
            for level in levels:
                label = f"level {level['position']} {level['name']!r} " \
                        f"({level['delay']} day(s))"

                if level["send_email"]:
                    if not level["mail_template_id"]:
                        no_letter.append(
                            f"{label}: Email is ticked but no Email Template "
                            f"is set, so THE MESSAGE BODY IS GONE — in Odoo 19 "
                            f"the letter lives on mail_template_id, the level "
                            f"itself has no body field")
                    elif mail_unreadable:
                        level["email_body"] = "(not readable)"
                    else:
                        row = mail_rows.get(level["mail_template_id"]) or {}
                        body = row.get("body_html") or ""
                        text = _plain_text(body)
                        level["email_subject"] = row.get("subject") or ""
                        level["email_body"] = text
                        if _body_is_blank(body):
                            blank_letter.append(
                                f"{label}: the Email Template "
                                f"{row.get('name')!r} has an empty body_html "
                                f"— the letter would go out blank")
                        if (row.get("model") or "") != "res.partner":
                            wrong_model.append(
                                f"{label}: the Email Template "
                                f"{row.get('name')!r} is on model "
                                f"{row.get('model')!r}, not 'res.partner' — "
                                f"the follow-up field only accepts res.partner "
                                f"templates (account_followup.py:20), so this "
                                f"one cannot render against a customer")
                        messages.append([level["delay"], level["name"],
                                         "email", row.get("name") or "",
                                         row.get("subject") or "",
                                         text[:BODY_CHARS_IN_CSV]])
                        ctx.log(f"  {label} email subject="
                                f"{(row.get('subject') or '')!r} "
                                f"body={len(text)} readable character(s): "
                                f"{text[:120]!r}")

                if level["send_sms"]:
                    if not level["sms_template_id"]:
                        no_letter.append(
                            f"{label}: SMS is ticked but no SMS Template is "
                            f"set, so that level sends nothing")
                    elif sms_unreadable:
                        level["sms_body"] = "(not readable)"
                    else:
                        row = sms_rows.get(level["sms_template_id"]) or {}
                        text = (row.get("body") or "").strip()
                        level["sms_body"] = text
                        if not text:
                            blank_letter.append(
                                f"{label}: the SMS Template "
                                f"{row.get('name')!r} has an empty body")
                        messages.append([level["delay"], level["name"], "sms",
                                         row.get("name") or "", "",
                                         text[:BODY_CHARS_IN_CSV]])
                        ctx.log(f"  {label} sms body={len(text)} "
                                f"character(s): {text[:120]!r}")

                if level["create_activity"] and not level["activity_type_id"]:
                    # Required in the form view (line_views.xml:62), so a
                    # blank one is data written past the UI during migration:
                    # the level would raise when it fires.
                    no_letter.append(
                        f"{label}: Schedule Activity is ticked but no "
                        f"Activity Type is set, which the form view makes "
                        f"required (views/account_followup_line_views.xml:62)")

            # A template this session may not read leaves Expected line 2
            # UNMEASURED for that level. It is not a pass and it is not a
            # failure — it is a hole, and it has to be handed to a human with
            # the levels named, exactly like the unreadable-credential case in
            # TC-INV-010. Appended BEFORE the checks below, because ctx.check
            # raises and a residual added after one would be lost.
            unmeasured = [
                f"level {lv['position']} {lv['name']!r} ({lv['delay']} day(s))"
                f" — {'email' if lv.get('email_body') == '(not readable)' else ''}"
                f"{'/' if lv.get('email_body') == '(not readable)' and lv.get('sms_body') == '(not readable)' else ''}"
                f"{'sms' if lv.get('sms_body') == '(not readable)' else ''}"
                for lv in levels
                if lv.get("email_body") == "(not readable)"
                or lv.get("sms_body") == "(not readable)"]
            if unmeasured:
                residual.append(
                    "EXPECTED RESULT LINE 2 WAS NOT MEASURED for these levels: "
                    + "; ".join(unmeasured)
                    + f". The level links a template, but the runner user "
                      f"cannot read it "
                      f"(mail.template: {mail_unreadable or 'readable'}; "
                      f"sms.template: {sms_unreadable or 'readable'}), so the "
                      f"platform could prove neither that the letter is there "
                      f"nor that it is blank. This is a permission fact about "
                      f"the runner, NOT a finding about the gallery — do not "
                      f"record it as a missing message body. Open each level "
                      f"listed at '" + MENU_PATH + "' as a user who can read "
                      "mail.template / sms.template and confirm the body is "
                      "present and reads correctly, or re-run this case as "
                      "that user.")

            ctx.check("Every follow-up level that says it emails, texts or "
                      "schedules an activity actually has the thing it needs "
                      "to do it — in Odoo 19 an empty Email Template IS the "
                      "missing message body", [], no_letter)
            ctx.check("The message body on every level is intact and "
                      "readable — no linked template has an empty body",
                      [], blank_letter)
            ctx.check("Every follow-up email template still renders against "
                      "the customer (mail.template.model == 'res.partner')",
                      [], wrong_model)

            # A level that does nothing at all is not caught by any check
            # above, because each check is conditional on a ticked action.
            silent = [f"level {lv['position']} {lv['name']!r} "
                      f"({lv['delay']} day(s))" for lv in levels
                      if not (lv["send_email"] or lv["send_sms"]
                              or lv["create_activity"])]
            ctx.check("No follow-up level is completely silent — every level "
                      "still emails, texts or schedules an activity when it "
                      "fires", [], silent)

            residual.append(
                "read the letters for sense — the machine can only prove they "
                "are present and non-blank, not that they still say what the "
                "gallery wants said. The full text of every level's email and "
                f"SMS is in {MESSAGES_CSV}, one row per level per channel, so "
                f"this is a read and not a re-navigation. Captured: "
                + ("; ".join(f"{row[0]} day(s) {row[2]} subject={row[4]!r} "
                             f"({len(row[5])} chars)" for row in messages)
                   or "(no template body was reachable)"))

        with ctx.step("Finding check: are these Odoo 19's own shipped "
                      "defaults rather than the gallery's migrated levels?"):
            shape = tuple(sorted((lv["delay"], lv["name"]) for lv in levels))
            defaults = tuple(sorted(FOLLOWUP_V19_DEFAULTS))
            stock_owned = [lv["xmlid"] for lv in levels
                           if lv.get("owner_module") == "account_followup"]
            ctx.log(f"level shape (delay, description) = {list(shape)}; "
                    f"levels owned by an account_followup xmlid: "
                    f"{stock_owned or 'none'}")
            if shape == defaults:
                # Asserted in NEITHER direction, deliberately. The condition
                # that would make this a defect is "…and the Novobi baseline
                # says otherwise", and the baseline is exactly what this
                # platform does not hold; failing here would be inventing one.
                finding(ctx,
                        f"this database holds EXACTLY Odoo 19's two shipped "
                        f"follow-up levels and nothing else — "
                        f"{', '.join(f'{d} day(s) = {n!r}' for d, n in shape)}"
                        f" — which are created by the module's own data file "
                        f"(enterprise-19.0/account_followup/data/"
                        f"account_followup_data.xml:4-10 and :47-53, both "
                        f"forcecreate=\"False\"). If the Novobi baseline lists "
                        f"anything else, the gallery's levels were NOT "
                        f"migrated and a fresh default set was created on "
                        f"install. That is a different fix from 'a level is "
                        f"missing': the old levels have to be re-entered or "
                        f"re-imported, not repaired. Cross-check: "
                        f"{len(stock_owned)} of {len(levels)} level(s) are "
                        f"owned by an account_followup xmlid "
                        f"({', '.join(stock_owned) or 'none'}) — a level the "
                        f"gallery configured has no xmlid at all")
                residual.append(
                    "SETTLE THE DEFAULT-DATA FINDING FIRST, before ticking "
                    "anything else off: the two levels found are exactly "
                    "Odoo 19's shipped defaults. Compare them to the Novobi "
                    "baseline. If the baseline is also 15/30 days with those "
                    "descriptions, the run is clean; if it is anything else, "
                    "raise it as 'follow-up levels not migrated, defaults "
                    "created instead', not as 'levels missing'.")
            else:
                ctx.log("the level set is NOT Odoo 19's shipped default pair, "
                        "so these levels did not simply come from the "
                        "module's data file — the baseline tick-off is the "
                        "real question")

        with ctx.step("Tick-off completeness: v15-era level fields that have "
                      "no Odoo 19 counterpart"):
            # Reported so the tester's row-by-row tick-off does not stall on a
            # baseline column that cannot exist in v19. Asserted in neither
            # direction — this is a version difference, not a defect.
            present = fields_present(rpc, FOLLOWUP_MODEL,
                                     V15_ERA_FIELD_CANDIDATES)
            gone = [f for f in V15_ERA_FIELD_CANDIDATES if f not in present]
            still_there = [f for f in V15_ERA_FIELD_CANDIDATES
                           if f in present]
            observation(ctx,
                        f"the Odoo 19 follow-up level has no "
                        f"{', '.join(gone)} field — its complete field list is "
                        f"enterprise-19.0/account_followup/models/"
                        f"account_followup.py:14-40, and the letter now lives "
                        f"on the linked mail.template / sms.template rather "
                        f"than on the level. If the Novobi baseline has a "
                        f"'printed message' or 'manual action' column, it has "
                        f"no v19 equivalent and cannot be ticked off — say "
                        f"'no v19 field' rather than 'missing'"
                        + (f". Still present on this database, unexpectedly: "
                           f"{', '.join(still_there)}" if still_there else ""))
    finally:
        with ctx.step("Evidence: write the level inventory and the letters"):
            # Built defensively and entirely with .get(): this runs from
            # `finally`, and a KeyError raised here would replace whatever
            # real FAILED or BLOCKED verdict the case had already reached
            # with an AUTOMATION_ERROR.
            level_rows = []
            try:
                for lv in levels:
                    level_rows.append(
                        [lv.get("position"), lv.get("delay"), lv.get("name"),
                         lv.get("company"), lv.get("send_email"),
                         lv.get("mail_template"), lv.get("email_subject", ""),
                         len(lv.get("email_body", "")),
                         lv.get("join_invoices"), lv.get("send_sms"),
                         lv.get("sms_template"), len(lv.get("sms_body", "")),
                         lv.get("create_activity"), lv.get("activity_type"),
                         lv.get("auto_execute"), lv.get("owner_module", ""),
                         lv.get("xmlid", "")])
            except Exception as exc:                  # noqa: BLE001
                ctx.log(f"could not assemble the {LEVELS_CSV} rows ({exc}) — "
                        f"every level above is still in this log")
            for path_name, header, rows in ((LEVELS_CSV, LEVELS_HEADER,
                                             level_rows),
                                            (MESSAGES_CSV, MESSAGES_HEADER,
                                             messages)):
                path = ctx.artifacts_dir / path_name
                try:
                    with path.open("w", newline="", encoding="utf-8") as fh:
                        writer = csv.writer(fh)
                        writer.writerow(header)
                        writer.writerows(rows)
                    ctx.add_artifact(path, "log", path_name)
                    ctx.log(f"wrote {len(rows)} row(s) to {path_name}")
                except Exception as exc:              # noqa: BLE001
                    # Broader than OSError on purpose: this is inside a
                    # `finally`, and an encoding or csv error here must not be
                    # allowed to destroy the verdict either.
                    ctx.log(f"could not write {path_name} ({exc}) — every "
                            f"level and letter above is still in this log")
            for note in residual:
                residual_manual_step(ctx, note)
            ctx.log("NOTHING WAS CREATED OR MODIFIED by this case — the "
                    "workbook's State After The Test is 'Nothing changed', so "
                    "no sweep and no cleanup runs here either (a sweep is "
                    "itself a delete).")
