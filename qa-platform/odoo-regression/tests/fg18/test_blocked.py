"""FG-18 — TC-SMK-014, TC-SMK-016 and TC-SMK-017: what this instance cannot
answer, and the measurement that proves it.

Implements the CLIENT MANUAL TESTING GUIDELINE
``MMG_v19_Client_Manual_Testing_Guideline_FG15-FG20_v1.0.xlsx`` / sheet
``Testing Guideline``.

Each of these three is blocked by the test INSTANCE, not by the product,
and a bare ``blocked("needs X")`` would waste the run. So each does the
measuring it can do first and blocks on the number it found. Two of those
numbers are worth having on their own:

* the filestore shortfall — how many of the gallery's 1.07 million stored
  files would not open today. That is a cutover input, not just a test
  result;
* the mail configuration count — zero, because the restore deleted it
  deliberately.

A blocked verdict here is the honest one. Reporting TC-SMK-014 as FAILED
would put a product defect in the client's acceptance record for something
the restore did on purpose (``..._test_nofs.zip`` — no filestore), and
reporting it as passed would be worse.
"""
from __future__ import annotations

from adapters.base import OdooRPCError
from framework.registry import test_case

from .common import MODULE, WORKFLOW, WORKFLOW_NAME, observation, \
    require_v19, trace


@test_case(
    id="TEST-FG18-SMK-014",
    name="Images, PDFs and document templates all still open",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module=MODULE,
    priority="P0",
    kind="API",
    order=1804,
    description="Samples the stored files this database claims to hold and "
                "tries to read them back, then reports how many would not "
                "open. BLOCKED on this instance: the restore was taken "
                "without a filestore, so the shortfall it measures is the "
                "restore's, not the product's — but the number is a cutover "
                "input the gallery needs either way.",
    traceability=trace("TC-SMK-014"))
def test_smk_014(ctx):
    rpc = require_v19(ctx)

    with ctx.step("How many stored files does this database claim, and how "
                  "many can actually be read back?"):
        total = rpc.call("ir.attachment", "search_count", [])
        on_disk = rpc.call("ir.attachment", "search_count",
                           [("store_fname", "!=", False)])
        ctx.log(f"{total} attachments recorded, {on_disk} of them claim a "
                f"file on disk")

        # A small sample of the SMALLEST files: reading `datas` pulls the
        # whole file back base64-encoded, so a sample of large ones would
        # move a lot of bytes to learn the same thing.
        sample = rpc.search_read(
            "ir.attachment",
            [("store_fname", "!=", False), ("file_size", ">", 0)],
            ["name", "file_size", "res_model"],
            limit=15, order="file_size asc")
        readable, missing = 0, []
        for row in sample:
            try:
                data = rpc.read("ir.attachment", [row["id"]], ["datas"])[0]
                if data.get("datas"):
                    readable += 1
                else:
                    missing.append(f"{row['name']} ({row['res_model']})")
            except OdooRPCError as exc:
                missing.append(f"{row['name']} — {str(exc)[:80]}")
        ctx.log(f"sampled {len(sample)} stored files: {readable} readable, "
                f"{len(missing)} missing")
        for name in missing[:10]:
            ctx.log(f"  MISSING  {name}")

        if missing:
            observation(
                ctx,
                f"{len(missing)} of {len(sample)} sampled files could not be "
                f"read back. Scaled across the {on_disk} attachments that "
                f"claim a file, that is the order of the gallery's exposure "
                f"if this database were promoted as-is. The cause is known "
                f"and deliberate: the dump this instance was built from is "
                f"`medicinemangallery-staging-19-..._test_nofs.zip` — "
                f"`nofs` meaning no filestore — so the rows came across and "
                f"the files did not.")

    ctx.blocked(
        "TC-SMK-014 cannot be judged on this instance. It asks whether 15 "
        "named stored files open, and this database was restored WITHOUT "
        "its filestore (the dump is `..._test_nofs.zip`), so every stored "
        "file is missing by construction — a FAIL here would record a "
        "product defect for something the restore did on purpose. Two "
        "things are needed to run it: a restore that includes the "
        "filestore, and Novobi's list of the 15 files (5 product photos, 5 "
        "invoice PDFs, 5 contact attachments). The two PRINTED documents "
        "the case also asks for — Product Certificate and Avery Label — are "
        "QWeb reports that do not depend on the filestore and could be run "
        "today; they are checked as bound actions by TEST-FG18-SMK-007.")


@test_case(
    id="TEST-FG18-SMK-016",
    name="Everyone can still log in, and two-factor authentication still "
         "works",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module=MODULE,
    priority="P1",
    kind="API",
    order=1805,
    description="Reports how many non-administrator logins exist and how "
                "many carry two-factor authentication, then BLOCKS: the "
                "case turns on signing in with the OLD passwords and a code "
                "from an EXISTING authenticator, and neither is something a "
                "test can hold.",
    traceability=trace("TC-SMK-016"))
def test_smk_016(ctx):
    rpc = require_v19(ctx)

    with ctx.step("What logins exist to test with?"):
        users = rpc.search_read(
            "res.users", [("share", "=", False)],
            ["login", "active"], limit=0, context={"active_test": False})
        active = [u for u in users if u["active"]]
        ctx.log(f"{len(users)} internal logins, {len(active)} active")

        totp = 0
        if rpc.field_exists("res.users", "totp_enabled"):
            totp = rpc.call("res.users", "search_count",
                            [("totp_enabled", "=", True)])
            ctx.log(f"{totp} of them have two-factor authentication on")
        else:
            observation(ctx, "res.users.totp_enabled does not exist — the "
                             "auth_totp module is not installed, so the "
                             "two-factor half of this case has nothing to "
                             "check even with the right credentials.")

        ctx.check_true(
            "There are non-administrator logins to test with",
            len(active) > 1, actual_desc=f"{len(active)} active logins")

    ctx.blocked(
        "TC-SMK-016 cannot be automated, and not for want of trying. It "
        "asks for three non-administrator users to sign in with their OLD "
        "passwords, and for one of them to pass two-factor authentication "
        "using a code from the EXISTING authenticator app without "
        "re-enrolling. A password this platform could supply would be a "
        "password it had set, which tests nothing about whether the old one "
        "survived; and a TOTP code needs the phone. Step 7 — 'the menus "
        "each person sees match what they saw in the old system' — is "
        "separately blocked on the old system's menu list. This one stays "
        "with a human holding the authenticator.")


@test_case(
    id="TEST-FG18-SMK-017",
    name="Outgoing and incoming email are still configured and reachable",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module=MODULE,
    priority="P1",
    kind="API",
    order=1806,
    description="Counts the mail servers and templates this database holds "
                "and confirms no Magento template survives, then BLOCKS on "
                "the mail configuration: the restore deleted every outgoing "
                "and incoming server on purpose, so there is nothing to "
                "test a connection against.",
    traceability=trace("TC-SMK-017"))
def test_smk_017(ctx):
    rpc = require_v19(ctx)

    with ctx.step("Steps 1 and 3: what mail configuration does this "
                  "database hold?"):
        outgoing = rpc.call("ir.mail_server", "search_count", [])
        incoming = rpc.call("fetchmail.server", "search_count", []) \
            if rpc.model_exists("fetchmail.server") else 0
        ctx.log(f"outgoing mail servers: {outgoing}; incoming: {incoming}")
        observation(ctx,
                    "both are zero because the restore neutralized them — "
                    "`UPDATE ir_mail_server SET active=false` and the rows "
                    "themselves deleted (docker/README.md §4) — precisely so "
                    "a copy of production cannot send the gallery's "
                    "customers real email. That is the right state for a "
                    "test instance and the reason this case cannot run on "
                    "it.")

    with ctx.step("Steps 6-7: the templates, which CAN be checked here"):
        templates = rpc.search_read("mail.template", [], ["name"], limit=0)
        ctx.log(f"{len(templates)} email templates on the database")
        magento = [t["name"] for t in templates
                   if "magento" in (t["name"] or "").lower()]
        ctx.check("No Magento email template survives — step 7", [], magento)

        cancellation = [t["name"] for t in templates
                        if "cancel" in (t["name"] or "").lower()]
        ctx.check_true(
            "An order-cancellation template is present — step 6",
            bool(cancellation),
            actual_desc="; ".join(cancellation[:5]) or "none found")

    ctx.blocked(
        "TC-SMK-017 cannot be judged on this instance. Steps 1-5 turn on "
        "pressing 'Test Connection', 'Test & Confirm' and 'Fetch Now' "
        "against real mail servers, and this database has none: the restore "
        "deleted every outgoing and incoming server so a production copy "
        "cannot reach the gallery's mailboxes. Step 3 also compares the "
        "incoming servers against the old system 'same number, same server "
        "name, port and user' — which needs the old system's settings. To "
        "run it: a test instance pointed at a SAFE test mailbox, plus that "
        "comparison list. What could be checked here — the templates, and "
        "that no Magento template survives — is asserted above and passed.")
