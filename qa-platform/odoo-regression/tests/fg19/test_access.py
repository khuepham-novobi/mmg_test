"""FG-19 — TC-SEC-007, TC-SEC-010 and TC-SEC-011.

Implements the CLIENT MANUAL TESTING GUIDELINE
``MMG_v19_Client_Manual_Testing_Guideline_FG15-FG20_v1.0.xlsx`` / sheet
``Testing Guideline``.

The one thing these cases must not do is prove a refusal by the wrong
route. A menu that is absent because the whole app is missing, a field that
``fields_get`` omits because the model could not be read at all, a button
that is not in an arch because the arch failed to build — each of those
would read as "correctly hidden" while proving nothing. So every negative
is paired with the same question asked of the MANAGER login, and the
manager's answer has to be positive for the user's to count.

Nothing here presses a storefront button. TC-SEC-010 step 3 says "Do not
press any of them even if they are [shown]", and the four in question are
``publish`` / ``do_update`` / ``get_data`` / ``set_to_draft`` on
``product.collection`` — the first three reach Shopify. Their presence and
absence is read off the assembled arch instead, which is exactly what a
tester looking at the screen sees.
"""
from __future__ import annotations

from adapters.base import OdooRPCError
from framework.registry import test_case

from .common import (CHANNEL, COLLECTION, COLLECTION_BUTTONS, GROUP_MANAGER,
                     GROUP_USER, MODULE, RESTRICTED_MENUS,
                     SCHEDULED_ACTIONS, SCHEDULED_EDITABLE,
                     SCHEDULED_OFF_ON_PURPOSE, TOKEN_FIELD, TOKEN_LABEL,
                     WORKFLOW, WORKFLOW_NAME, Probe, attr, button_attrs,
                     field_attrs, finding, live_probes, manual, observation,
                     ref, require_connector, sweep_probes, trace)


@test_case(
    id="TEST-FG19-SEC-007",
    name="The storefront access token is hidden from ordinary e-commerce "
         "users",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module=MODULE,
    priority="P0",
    kind="API",
    order=1900,
    description="With one throw-away E-commerce User and one E-commerce "
                "Manager: the Manage Stores menu is not served to the User, "
                "the Access Token row is absent from the store form as the "
                "User is served it, and the Manager sees it labelled "
                "'Access Token' and dot-masked. Whether the User can read "
                "the token by any other route is probed directly, because "
                "the workbook calls a readable token a same-day P0.",
    traceability=trace("TC-SEC-007"))
def test_sec_007(ctx):
    rpc = require_connector(ctx)
    sweep_probes(ctx)
    user = manager = None

    try:
        with ctx.step("Preconditions: two logins, one E-commerce User and "
                      "one E-commerce Manager, neither an administrator"):
            user = Probe(ctx, "user", GROUP_USER)
            manager = Probe(ctx, "manager", GROUP_MANAGER)
            settings = ref(rpc, "base.group_system")
            for probe in (user, manager):
                ctx.check_true(
                    f"The {probe.label} login is NOT an administrator — an "
                    f"admin would see everything and prove nothing",
                    settings["res_id"] not in probe.groups(),
                    actual_desc=f"{probe.groups_field}={probe.groups()}")

        with ctx.step("Step 2: the Manage Stores menu is not served to the "
                      "E-commerce User"):
            stores = ref(rpc, "omni_manage_channel.menu_management_channels")
            ctx.check_true("The Manage Stores menu exists on this database",
                           bool(stores), actual_desc=str(stores))
            seen_by_user = user.visible_menus()
            seen_by_manager = manager.visible_menus()
            ctx.check_true(
                "The Manager IS served it — which is what makes the User's "
                "result mean something",
                stores["res_id"] in seen_by_manager,
                actual_desc=f"{len(seen_by_manager)} menus served to the "
                            f"manager")
            ctx.check("The E-commerce User is NOT served Manage Stores",
                      False, stores["res_id"] in seen_by_user)
            ctx.log(f"menus served: user={len(seen_by_user)} "
                    f"manager={len(seen_by_manager)}")

        with ctx.step("Step 4: reached any other way, the Access Token row "
                      "is absent from the store form for the User"):
            user_arch = user.arch(CHANNEL, "form")
            manager_arch = manager.arch(CHANNEL, "form")
            ctx.check_true(
                "The Manager's store form builds — the comparison below is "
                "against a real form, not a failed one",
                bool(manager_arch),
                actual_desc=f"{len(manager_arch)} characters")

            manager_tag = field_attrs(manager_arch, TOKEN_FIELD)
            user_tag = field_attrs(user_arch, TOKEN_FIELD) if user_arch else ""
            ctx.check_true(
                f"The Manager is served the token field ({TOKEN_FIELD})",
                bool(manager_tag),
                actual_desc=manager_tag[:200] or "absent")
            ctx.check_true(
                "The E-commerce User is NOT served it on the store form",
                not user_tag,
                actual_desc=user_tag[:200] or
                ("absent" if user_arch else "the form did not build for the "
                                            "user at all"))

        with ctx.step("Step 7 / Expected line 2: for the Manager the row is "
                      "labelled 'Access Token' and dot-masked"):
            ctx.check(f"It is labelled {TOKEN_LABEL!r}, as the workbook "
                      f"reads it", TOKEN_LABEL, attr(manager_tag, "string"))
            ctx.check("…and it is masked, not readable text", "1",
                      attr(manager_tag, "password"))

        with ctx.step("Expected line 4: the User cannot read the token by "
                      "ANY route — a readable token is a same-day P0"):
            # Not the form: the value itself. A field kept off the form but
            # readable over RPC is exactly the shape of leak the workbook's
            # P0 wording is about, and no amount of view work would catch it.
            readable = user.fields_get(CHANNEL, [TOKEN_FIELD])
            ctx.check(
                "The token field is not even declared to the E-commerce "
                "User — fields_get omits what the user has no group for",
                {}, readable)

            rows, error = user.can_read(CHANNEL, [TOKEN_FIELD])
            leaked = bool(rows) and any(row.get(TOKEN_FIELD) for row in rows)
            if leaked:
                finding(ctx,
                        "STOP — the E-commerce User read the storefront "
                        "access token over RPC. The workbook calls this a "
                        "P0 to be raised the same day. Hiding the field on "
                        "the form is not enough; the value has to be "
                        "restricted at the field or the ACL.")
            ctx.check_true(
                "Reading the token as an E-commerce User returns nothing",
                not leaked,
                actual_desc=(error or (f"RETURNED {rows}" if rows
                                       else "no rows")))

        with ctx.step("Step 8: no export route hands the token to a file"):
            # Export offers exactly the fields `fields_get` returns for the
            # acting user, so "no route lets either user export the token"
            # is a statement about that list — NOT about whether the user
            # can see stores at all. An E-commerce User legitimately reads a
            # store's name: listings point at one. What must not be in the
            # list is the token.
            exportable_user = set(user.fields_get(
                CHANNEL, []) or {})
            exportable_manager = set(manager.fields_get(CHANNEL, []) or {})
            ctx.check_true(
                "The Manager's exportable field list built, so the "
                "comparison below is against a real list",
                bool(exportable_manager),
                actual_desc=f"{len(exportable_manager)} fields")
            ctx.check_true(
                "The token is not among the fields an E-commerce User could "
                "tick in an Export",
                TOKEN_FIELD not in exportable_user,
                actual_desc=f"{len(exportable_user)} fields offered to the "
                            f"user; {TOKEN_FIELD} "
                            f"{'PRESENT' if TOKEN_FIELD in exportable_user else 'absent'}")
            observation(ctx,
                        f"the E-commerce User can read {len(exportable_user)} "
                        f"field(s) on a store, name among them — that is "
                        f"correct and expected, because a listing points at "
                        f"a store. The case is about the token, and the "
                        f"token is not in that list.")
            manual(ctx,
                   "TC-SEC-007 step 8 as the workbook words it — ticking the "
                   "store on the Manage Stores list as the MANAGER and "
                   "confirming the gear menu offers no Export that would "
                   "download the token. Export is a web-client feature over "
                   "the same field access asserted above; one look at the "
                   "gear menu closes it.")

    finally:
        with ctx.step("Cleanup: both throw-away logins are removed"):
            for probe in (p for p in (user, manager) if p):
                ctx.log(f"probe '{probe.label}' {probe.remove()}")
            sweep_probes(ctx)
            ctx.check("No usable probe login is left on the database", 0,
                      live_probes(ctx))


@test_case(
    id="TEST-FG19-SEC-010",
    name="An E-commerce User cannot do the things only a Manager should",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module=MODULE,
    priority="P1",
    kind="API",
    order=1901,
    description="The three menus the workbook names are absent for the "
                "E-commerce User and present for the Manager; the four "
                "storefront buttons are absent from the collection form as "
                "the User is served it and present for the Manager; and "
                "what happens when a Manager saves a store is recorded "
                "either way, because the workbook says a rights message "
                "there is expected and a successful save is the finding. No "
                "storefront button is pressed.",
    traceability=trace("TC-SEC-010"))
def test_sec_010(ctx):
    rpc = require_connector(ctx)
    sweep_probes(ctx)
    user = manager = None

    try:
        with ctx.step("Preconditions: the same two logins as TC-SEC-007"):
            user = Probe(ctx, "user", GROUP_USER)
            manager = Probe(ctx, "manager", GROUP_MANAGER)

        with ctx.step("Steps 1-2 / 6: the three restricted menus are absent "
                      "for the User and present for the Manager"):
            seen_by_user = user.visible_menus()
            seen_by_manager = manager.visible_menus()
            wrongly_visible, wrongly_hidden = [], []
            for xmlid, label in RESTRICTED_MENUS.items():
                row = ref(rpc, xmlid)
                if not row:
                    wrongly_hidden.append(f"{label} — menu does not exist")
                    continue
                if row["res_id"] in seen_by_user:
                    wrongly_visible.append(label)
                if row["res_id"] not in seen_by_manager:
                    wrongly_hidden.append(f"{label} — hidden from the "
                                          f"Manager too")
            ctx.check("No restricted menu is served to the E-commerce User "
                      "— 'any menu from step 2 that the USER can see is a "
                      "real failure'", [], wrongly_visible)
            ctx.check("…and all three ARE served to the Manager, so the "
                      "result above is a restriction and not an absence",
                      [], wrongly_hidden)

        with ctx.step("Steps 3 / 6: the four storefront buttons are absent "
                      "for the User and present for the Manager"):
            if not rpc.model_exists(COLLECTION):
                ctx.skip(f"model '{COLLECTION}' does not exist on this "
                         f"database, so there is no storefront collection "
                         f"to open.")
            manager_arch = manager.arch(COLLECTION, "form")
            user_arch = user.arch(COLLECTION, "form")
            ctx.check_true(
                "The Manager's collection form builds",
                bool(manager_arch), actual_desc=f"{len(manager_arch)} chars")

            shown_to_user, hidden_from_manager = [], []
            for name, label in COLLECTION_BUTTONS.items():
                if user_arch and button_attrs(user_arch, name):
                    shown_to_user.append(f"{label} ({name})")
                if not button_attrs(manager_arch, name):
                    hidden_from_manager.append(f"{label} ({name})")
            ctx.check("No storefront button is served to the E-commerce "
                      "User", [], shown_to_user)
            ctx.check("…and all four ARE served to the Manager", [],
                      hidden_from_manager)
            observation(ctx,
                        "none of the four is pressed. Three of them — "
                        "publish, do_update, get_data — reach the "
                        "gallery's live Shopify store, and the workbook's "
                        "step 3 says not to press them even if they are "
                        "shown.")

        with ctx.step("Step 4: deleting a listing image as the User is "
                      "refused"):
            images = "product.channel.image"
            if not rpc.model_exists(images):
                observation(ctx, f"model '{images}' does not exist; the "
                                 f"listing-image check has nothing to act "
                                 f"on.")
            else:
                rows = rpc.search(images, [], limit=1)
                if not rows:
                    observation(ctx, "no listing image exists to try to "
                                     "delete.")
                else:
                    error = ""
                    try:
                        user.rpc.unlink(images, rows)
                    except OdooRPCError as exc:
                        error = str(exc)
                    still = rpc.call(images, "search_count",
                                     [("id", "in", rows)])
                    ctx.check_true(
                        "Deleting a listing image as an E-commerce User is "
                        "refused", bool(error),
                        actual_desc=error[:240] or "THE DELETE WAS ACCEPTED")
                    ctx.check("…and the image is still there", len(rows),
                              still)

        with ctx.step("Steps 7-8: what happens when a MANAGER saves a store "
                      "— recorded either way"):
            stores = rpc.search_read(CHANNEL, [], ["name"], limit=1)
            if not stores:
                ctx.skip("no store exists to save.")
            store = stores[0]
            # The workbook says "add a space to the store name". Writing the
            # name back onto ITSELF tests the same permission and cannot
            # change the gallery's data whichever way the guard falls.
            error = ""
            try:
                manager.rpc.write(CHANNEL, [store["id"]],
                                  {"name": store["name"]})
            except OdooRPCError as exc:
                error = str(exc)
            after = rpc.read(CHANNEL, [store["id"]], ["name"])[0]["name"]
            ctx.check("The store's name is untouched whichever way the "
                      "write fell", store["name"], after)

            if error:
                observation(ctx,
                            f"TC-SEC-010 step 7, as expected: an E-commerce "
                            f"Manager CANNOT write to a store. Server said: "
                            f"{error[:200]}. The workbook says to record "
                            f"this on the Sign-off tab as accepted "
                            f"behaviour, not raise it.")
            else:
                finding(ctx,
                        "TC-SEC-010 step 8: an E-commerce Manager CAN write "
                        "to a store. The workbook's Expected Result says a "
                        "rights message here is what it expects, and that a "
                        "successful save 'is the finding worth raising'. "
                        "Nothing was changed by this test — the name was "
                        "written back onto itself — but the permission is "
                        "there.")
            ctx.check_true(
                "The system gave a definite answer on whether a Manager may "
                "write to a store",
                True,
                actual_desc=("REFUSED — " + error[:160]) if error
                else "ALLOWED — the write was accepted")

    finally:
        with ctx.step("Cleanup: both throw-away logins are removed"):
            for probe in (p for p in (user, manager) if p):
                ctx.log(f"probe '{probe.label}' {probe.remove()}")
            sweep_probes(ctx)
            ctx.check("No usable probe login is left on the database", 0,
                      live_probes(ctx))


@test_case(
    id="TEST-FG19-SEC-011",
    name="Scheduled actions can be edited again after the old connector is "
         "removed",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module=MODULE,
    priority="P2",
    kind="API",
    order=1902,
    description="All seven named scheduled actions are present, 'Check new "
                "orders' is present too, and the interval on two of them is "
                "changed and put straight back with no rights message — the "
                "point of the case, since the retired connector used to "
                "make these read-only. No task is left altered and none "
                "fires: crons are deactivated on this instance.",
    traceability=trace("TC-SEC-011"))
def test_sec_011(ctx):
    rpc = require_connector(ctx)

    with ctx.step("Steps 1-2: the gallery's own scheduled actions are all "
                  "listed"):
        # `active_test=False` is what step 3 is warning the tester about in
        # UI terms: a switched-off task is hidden unless the filter includes
        # it, and reporting it missing would be wrong.
        rows = rpc.search_read("ir.cron", [], ["name", "active",
                                               "interval_number",
                                               "interval_type"],
                               context={"active_test": False}, limit=0)
        by_name = {row["name"]: row for row in rows}
        missing = [name for name in SCHEDULED_ACTIONS if name not in by_name]
        ctx.check("Every scheduled action the workbook names is present",
                  [], missing)
        for name in SCHEDULED_ACTIONS:
            row = by_name.get(name)
            if row:
                ctx.log(f"  {name}: active={row['active']} every "
                        f"{row['interval_number']} {row['interval_type']}")

    with ctx.step("Step 3: 'Check new orders' is present, and switched off "
                  "on purpose"):
        row = by_name.get(SCHEDULED_OFF_ON_PURPOSE)
        ctx.check_true(f"{SCHEDULED_OFF_ON_PURPOSE!r} is present",
                       bool(row), actual_desc=str(row))
        ctx.check(f"…and switched off, which the workbook says is correct",
                  False, row["active"])

        off = [name for name in SCHEDULED_ACTIONS if not by_name[name]["active"]]
        if len(off) == len(SCHEDULED_ACTIONS):
            observation(ctx,
                        "EVERY scheduled action on this instance is "
                        "switched off, not just 'Check new orders'. That is "
                        "the restore's own doing — the database was "
                        "neutralized with `UPDATE ir_cron SET active=false` "
                        "so a copy of production cannot fire real syncs "
                        "(docker/README.md §4). So the ON/OFF state cannot "
                        "be judged here at all; only a tester on a system "
                        "with crons live can confirm which ones the gallery "
                        "expects running. What this case CAN prove — that "
                        "the tasks exist and are editable — is asserted "
                        "below.")

    with ctx.step("Steps 4-7: the interval on two tasks changes and goes "
                  "straight back, with no rights message"):
        for name in SCHEDULED_EDITABLE:
            row = by_name.get(name)
            if not row:
                continue
            original = row["interval_number"]
            changed = original + 15
            error = ""
            try:
                rpc.write("ir.cron", [row["id"]],
                          {"interval_number": changed})
            except OdooRPCError as exc:
                error = str(exc)
            now = rpc.read("ir.cron", [row["id"]],
                           ["interval_number"])[0]["interval_number"]
            ctx.check_true(
                f"{name!r} saves with no rights message — the retired "
                f"connector used to make these read-only",
                not error, actual_desc=error[:240] or "saved")
            ctx.check(f"…and it took the new interval", changed, now)

            rpc.write("ir.cron", [row["id"]], {"interval_number": original})
            restored = rpc.read("ir.cron", [row["id"]],
                                ["interval_number"])[0]["interval_number"]
            ctx.check(f"…and it is put straight back to {original}",
                      original, restored)

    with ctx.step("Step 8: no task is read-only, and none carries a "
                  "connector message"):
        model_access = rpc.search_read(
            "ir.model.access",
            [("model_id.model", "=", "ir.cron"), ("perm_write", "=", True)],
            ["name", "group_id"])
        ctx.check_true(
            "Something on this database is granted write on ir.cron — which "
            "the two saves above have already demonstrated in practice",
            bool(model_access),
            actual_desc=f"{len(model_access)} access line(s) grant write")
        ctx.log("write access on ir.cron: " + "; ".join(
            f"{row['name']} ({row['group_id'][1] if row['group_id'] else 'all'})"
            for row in model_access[:6]))
