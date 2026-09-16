"""FG-10 — the Shopify Collections screen and its rule editor.

TC-SHP-016 builds an automated collection's rules without publishing it.
TC-SHP-031 goes back to that collection and proves the rule editor's two
dropdowns behave: Field is populated, and Condition narrows to the Field
chosen rather than offering the same list every time.

Why the rule dropdowns are checked through the ONCHANGE and not by reading
a static list
------------------------------------------------------------------------
The Condition dropdown is not a selection. It is a ``many2one`` to
``rule.relation`` whose options are narrowed at runtime:
``rule.collection.change_column`` is an ``@api.onchange('column')``
returning ``{'domain': {'relation_id': [('columns', '=ilike',
'%<column>%')]}}`` (``multichannel_shopify/models/product_collection.py:
91-95``), and the form's list view repeats the same domain inline
(``views/product_collection_views.xml``). A test that read
``rule.relation`` whole would report eight options for every Field and
prove nothing about step 4's "not the same list for every field". So the
domain is applied per Field value, exactly as the editor applies it, and
what is asserted is the set each one really yields.

Nothing here reaches Shopify. The collection created is left in Draft with
``published = False``, and ``publish``, ``do_update``, ``set_to_draft`` and
``get_data`` — the four buttons TC-SHP-016 step 14 says not to press — are
never called.
"""
from __future__ import annotations

from adapters.base import OdooRPCError
from framework.registry import test_case

from tests.fg10.common import (COLLECTION, MARK, MATCH_ALL, MATCH_ANY, MODULE,
                               RELATION, RULE, STATUS_DRAFT, TYPE_AUTOMATED,
                               TYPE_MANUAL, WORKFLOW, WORKFLOW_NAME,
                               IMPORT_ONLY_COLUMNS, acting_store, attr,
                               conditions_by_column, field_tag, finding,
                               m2o_id, manual, observation, raw_arch,
                               require_connected, require_shopify, selection_of,
                               selection_labels, sweep_fg10, trace)

COLLECTION_TITLE = f"UAT Collection 01 [{MARK}]"

#: The four buttons TC-SHP-016 step 14 forbids. Named so the case can prove
#: it did not press them rather than merely not pressing them.
FORBIDDEN_BUTTONS = ("publish", "do_update", "set_to_draft", "get_data")


@test_case(
    id="TEST-FG10-SHP-016",
    name="Build an automated collection's rules, without publishing it",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module=MODULE,
    priority="P1",
    kind="API",
    order=1016,
    description="Creates UAT Collection 01 as an Automated collection with "
                "one rule, saves it, and proves it lands in Draft with the "
                "rule intact and nothing sent to Shopify. The Conditions "
                "group's show/hide rule, the all/any choice and both rule "
                "dropdowns are asserted; the missing search panel and the "
                "read-only Collection Type are reported with their evidence.",
    traceability=trace("TC-SHP-016",
                       "As an E-commerce Manager, I can define an automated "
                       "collection's membership rules and save it without "
                       "publishing it to the storefront."))
def test_shp_016(ctx):
    rpc = require_shopify(ctx)
    store = acting_store(ctx)
    require_connected(ctx, store)
    sweep_fg10(ctx)
    collection_id = None

    try:
        with ctx.step("Steps 1-3: the Collections list, its columns, and the "
                      "search panel"):
            arch = raw_arch(rpc, "multichannel_shopify."
                                 "product_collection_tree_view")
            ctx.check_true(
                "The Collections list view exists",
                bool(arch), actual_desc=f"{len(arch)} characters of arch")
            for field, label in (("name", "Title"),
                                 ("rule_ids", "Product Conditions")):
                tag = field_tag(arch, field)
                ctx.check_true(
                    f"The list carries the {label!r} column "
                    f"({COLLECTION}.{field})",
                    bool(tag), actual_desc=tag or "field absent from the arch")
                ctx.check(f"…labelled {label!r} as step 2 reads it",
                          label, attr(tag, "string"))

            # Step 3 and Expected line 1 are about the SEARCH view, which is a
            # different record from the list. Odoo generates a fallback when a
            # model has none, so "a search box appeared" is not evidence that
            # the panel is there -- the fallback has to be told apart from a
            # real view, and the only way to do that is to look for the view.
            search_rows = rpc.search_read(
                "ir.ui.view", [("model", "=", COLLECTION),
                               ("type", "=", "search")],
                ["name"], context={"active_test": False})
            generated = rpc.call(COLLECTION, "get_view", view_type="search")
            ctx.log(f"search views defined for {COLLECTION}: "
                    f"{[r['name'] for r in search_rows] or 'NONE'}")
            ctx.log(f"what the client is therefore served: "
                    f"{generated['arch']}")

            # A title search DOES work -- the generated view gives one field,
            # and that is what step 3 asks the tester to try -- so that half
            # is asserted rather than assumed from the arch.
            probe = rpc.search_read(COLLECTION, [("name", "!=", False)],
                                    ["name"], limit=1, order="id")
            if probe:
                # len(search) rather than search_count: the adapter
                # exposes search/search_read/read/create/write/unlink/
                # read_group and no count, and a limit keeps a
                # 2,668-row model from being pulled back whole just to
                # prove the box matches something.
                hits = len(rpc.search(
                    COLLECTION, [("name", "ilike", probe[0]["name"])],
                    limit=5))
                ctx.check_true(
                    "Searching the Collections list by title finds a "
                    "collection — step 3's 'find a collection by title'",
                    bool(hits),
                    actual_desc=f"searching for {probe[0]['name']!r} "
                                f"returned {hits} row(s)")

            if not search_rows:
                finding(ctx,
                        "Expected line 1 says 'the Collections list opens "
                        "with a working search panel (Novobi added the search "
                        "panel back during the upgrade)'. There is NO search "
                        "view for product.collection in multichannel_shopify "
                        "and the Collections action carries "
                        "search_view_id = False, so Odoo serves its generated "
                        "fallback: " + generated["arch"] + " — one Title box "
                        "and nothing else. The v15 module HAD one: "
                        "mmg_multichannel_shopify/views/"
                        "product_collection_views.xml declares "
                        "view_product_collection_search with a Title field "
                        "AND a 'Group By > Type' filter. That module is on "
                        "the not-ported list (FG-10b), and the search view "
                        "went with it. Title search still works, which is "
                        "why this is easy to miss; the Group By panel is "
                        "gone.")

        with ctx.step("Steps 4-7: a new Automated collection reveals the "
                      "Conditions group, and Product must match offers both "
                      "choices"):
            form = raw_arch(rpc, "multichannel_shopify."
                                 "product_collection_form_view")
            ctx.check_true("The collection form view exists", bool(form),
                           actual_desc=f"{len(form)} characters of arch")

            # Expected line 2 and line 5 are the same arch rule read twice.
            # It is asserted literally so a later edit that inverts it is
            # caught, rather than inferred from one observed screen.
            conditions_group = ""
            for chunk in form.split("<group"):
                if 'string="Conditions"' in chunk[:120]:
                    conditions_group = chunk[:200]
                    break
            ctx.check_true(
                "The form has a Conditions group",
                bool(conditions_group), actual_desc=conditions_group or "absent")
            ctx.check(
                "…hidden for a Manual collection and shown for an Automated "
                "one — Expected lines 2 and 5, which are one rule",
                "type == 'custom'",
                attr(conditions_group, "invisible"))

            match = selection_labels(rpc, COLLECTION, "condition_type")
            ctx.log(f"Product must match offers: {match}")
            ctx.check("…'all condition' and 'any condition' are the two "
                      "choices step 7 reads",
                      [MATCH_ALL, MATCH_ANY], sorted(match))

            types = selection_labels(rpc, COLLECTION, "type")
            ctx.log(f"Collection Type offers: {types}")
            ctx.check_true(
                "Collection Type offers Manual and Automated (stored as "
                f"{TYPE_MANUAL!r} and {TYPE_AUTOMATED!r})",
                {TYPE_MANUAL, TYPE_AUTOMATED} <= set(types),
                actual_desc=str(types))

        with ctx.step("Steps 8-9: the rule row's Field and Condition "
                      "dropdowns are populated"):
            columns = selection_of(rpc, RULE, "column")
            ctx.check_true(
                "The Field dropdown is populated — 'an EMPTY dropdown is the "
                "failure this case exists to find'",
                bool(columns), actual_desc=f"{len(columns)} option(s)")
            ctx.log(f"Field offers {len(columns)}: "
                    f"{[c[0] for c in columns]}")

            relations = rpc.search_read(RELATION, [], ["name", "value",
                                                       "columns"], order="id")
            ctx.check_true(
                "The Condition dropdown has rows to offer at all "
                f"({RELATION} is populated — an empty table would leave every "
                f"Condition dropdown blank while relation_id is required)",
                bool(relations), actual_desc=f"{len(relations)} row(s)")
            for row in relations:
                ctx.log(f"  {row['name']!r} ({row['value']}) applies to: "
                        f"{row['columns']}")

        with ctx.step("Steps 5-11: create UAT Collection 01, Automated, one "
                      "rule, and confirm it saves in Draft"):
            usable = {col: rows for col, rows in conditions_by_column(rpc).items()
                      if rows}
            if not usable:
                ctx.blocked(
                    "no rule.collection.column value has a matching "
                    "rule.relation row, so no rule row can be built at all "
                    "and step 8 cannot be performed.")
            column = "title" if "title" in usable else sorted(usable)[0]
            relation = usable[column][0]
            ctx.log(f"building the rule row as Field={column!r} "
                    f"Condition={relation['name']!r} Value='Navajo'")

            collection_id = rpc.create(COLLECTION, {
                "name": COLLECTION_TITLE,
                "channel_id": store["id"],
                "type": TYPE_AUTOMATED,
                "condition_type": MATCH_ALL,
                "description": "<p>Created by the FG-10 automated suite. "
                               "Draft only; never published.</p>",
                "rule_ids": [(0, 0, {"column": column,
                                     "relation_id": relation["id"],
                                     "condition": "Navajo"})],
            })
            ctx.log(f"created {COLLECTION} #{collection_id}")

            saved = rpc.read(COLLECTION, [collection_id],
                             ["name", "type", "condition_type", "status",
                              "published", "id_on_channel", "rule_ids",
                              "description"])[0]
            ctx.check("The collection saves in Draft — step 11's status bar",
                      STATUS_DRAFT, saved["status"])
            ctx.check("…as an Automated collection", TYPE_AUTOMATED,
                      saved["type"])
            ctx.check("…matching all conditions, as the Test Data says",
                      MATCH_ALL, saved["condition_type"])
            ctx.check_true(
                "…with its rule intact — 'the collection saves in Draft with "
                "its rules intact'",
                len(saved["rule_ids"]) == 1,
                actual_desc=f"rule_ids = {saved['rule_ids']}")
            ctx.check_true("…and a Description, as step 10 asks",
                           bool(saved.get("description")),
                           actual_desc=str(saved.get("description"))[:120])

            rule = rpc.read(RULE, saved["rule_ids"],
                            ["column", "relation_id", "condition",
                             "display_name"])[0]
            ctx.check("The saved rule kept its Field", column, rule["column"])
            ctx.check("…its Condition", relation["id"],
                      m2o_id(rule["relation_id"]))
            ctx.check("…and its Value", "Navajo", rule["condition"])
            ctx.log(f"the rule reads: {rule['display_name']!r}")

        with ctx.step("Step 14: nothing was sent to Shopify"):
            after = rpc.read(COLLECTION, [collection_id],
                             ["published", "id_on_channel", "published_at",
                              "status"])[0]
            # WHAT PROVES "not sent to Shopify", and what does not.
            #
            # `published` is NOT it. It is the Online Store sales-channel
            # flag and it defaults to True
            # (product_collection.py:288, `default=True`), so a collection a
            # tester creates by clicking New carries it too. It records where
            # the collection is MEANT to appear once it is published; it does
            # not record that anything left Odoo.
            #
            # `id_on_channel` is it. It is written by publish(), and nothing
            # else writes it, so an empty value is the proof no request was
            # ever made. `status` staying at draft and `published_at` staying
            # empty are the same fact from two more directions.
            ctx.check_true(
                "The collection has no id on the channel — the proof it was "
                "never sent, since publish() is what writes id_on_channel",
                not after["id_on_channel"],
                actual_desc=f"id_on_channel = {after['id_on_channel']!r}")
            ctx.check("…and it is still in Draft", STATUS_DRAFT,
                      after["status"])
            observation(ctx,
                        f"the Online Store flag reads "
                        f"{bool(after['published'])} on this brand-new "
                        f"collection. That is the field's declared default "
                        f"(product_collection.py:288, default=True), not "
                        f"something this suite set, and it means only 'when "
                        f"this is published, put it on the Online Store'. "
                        f"The workbook's State After The Test calls the "
                        f"record 'unpublished', which is true in the sense "
                        f"that matters: id_on_channel is empty, published_at "
                        f"is empty and the status is Draft.")
            ctx.check_true("…and it was never published at any time",
                           not after["published_at"],
                           actual_desc=str(after["published_at"]))
            ctx.log(f"the four buttons step 14 forbids — "
                    f"{', '.join(FORBIDDEN_BUTTONS)} — are not called "
                    f"anywhere in this suite; the state above is what "
                    f"proves it rather than the promise")

        with ctx.step("Steps 12-13: switching the type, and the weight note"):
            # Step 12 asks the tester to switch Collection Type AFTER the
            # save in step 11. The form makes that impossible, and it is a
            # property of the arch rather than of this run:
            type_tag = field_tag(form, "type")
            readonly = attr(type_tag, "readonly")
            ctx.log(f"the Collection Type field is declared: {type_tag}")
            if readonly:
                observation(ctx,
                            f"step 12 says 'now switch Collection Type to "
                            f"Manual' AFTER step 11 has saved, and the form "
                            f"will not allow it: the field carries "
                            f"readonly=\"{readonly}\", so once write_date is "
                            f"set the radio is read-only. The Expected Result "
                            f"it supports ('switching to Manual hides the "
                            f"Conditions group; switching back shows it') is "
                            f"still true and is asserted above from the "
                            f"group's own invisible=\"type == 'custom'\" — "
                            f"but a tester can only exercise it BEFORE the "
                            f"first save. Worth a wording fix in the "
                            f"workbook, or a decision that the lock is "
                            f"wrong.")

            ctx.check_true(
                "Step 13: the note about the unit of weight is printed under "
                "the conditions",
                "Unit of Weight is lb" in form,
                actual_desc="present" if "Unit of Weight is lb" in form
                            else "no such note in the form arch")

        with ctx.step("Step 15: an automated collection's tag cannot be "
                      "removed by hand"):
            listing_arch = raw_arch(
                rpc, "multichannel_shopify.view_shopify_product_channel_form")
            if not listing_arch:
                manual(ctx,
                       "the listing form view could not be read, so step 15 "
                       "(try to remove an automated collection's tag from a "
                       "listing) stays with the tester.")
            else:
                read_only_tag = field_tag(listing_arch, "collection_ids")
                editable_tag = field_tag(listing_arch, "custom_collection_ids")
                ctx.log(f"listing form, read-only Collections field: "
                        f"{read_only_tag}")
                ctx.log(f"listing form, editable Collections field: "
                        f"{editable_tag}")
                ctx.check_true(
                    "The listing form separates the two: a read-only tag "
                    "field for every collection and an editable one for "
                    "MANUAL collections, which is how an automated "
                    "collection's tag ends up with no 'x'",
                    bool(read_only_tag) and bool(editable_tag),
                    actual_desc=f"collection_ids={bool(read_only_tag)}, "
                                f"custom_collection_ids={bool(editable_tag)}")
                manual(ctx,
                       "step 15 asks the tester to TRY to remove the tag and "
                       "see no 'x'. The absence of an 'x' is a rendering "
                       "property of the many2many_tags widget on a read-only "
                       "field; the fields behind it are asserted above, but "
                       "only a browser can confirm the glyph is not drawn.")

    finally:
        with ctx.step("Cleanup: the collection this case created is removed"):
            # The workbook's State After The Test says "leave it or delete
            # it", so deleting is within what the case allows and keeps the
            # run idempotent.
            if collection_id:
                try:
                    rpc.unlink(COLLECTION, [collection_id])
                    ctx.log(f"removed {COLLECTION} #{collection_id}")
                except OdooRPCError as exc:
                    ctx.log(f"could not remove #{collection_id}: {exc}")
            left = rpc.search(COLLECTION, [("name", "like", MARK)])
            ctx.check("No FG-10 collection is left behind", [], left)


@test_case(
    id="TEST-FG10-SHP-031",
    name="The collection-rule editor renders and its dropdowns are populated",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module=MODULE,
    priority="P1",
    kind="API",
    order=1031,
    description="Proves the Condition options really do narrow to the Field "
                "chosen — the onchange domain is applied per Field, exactly "
                "as the editor applies it — that a rule survives a reload "
                "unchanged, that a collection can hold more than one rule, "
                "and that the all/any choice sticks across a save.",
    traceability=trace("TC-SHP-031",
                       "As an E-commerce Manager, I can edit an automated "
                       "collection's rules and trust that what I saved is "
                       "what comes back."))
def test_shp_031(ctx):
    rpc = require_shopify(ctx)
    store = acting_store(ctx)
    require_connected(ctx, store)
    sweep_fg10(ctx)
    collection_id = None

    try:
        with ctx.step("Steps 1-2: the collection TC-SHP-016 left in Draft"):
            # TC-SHP-031's precondition is "TC-SHP-016 has passed and left the
            # UAT Collection 01 record in Draft". This suite deletes its own
            # fixture in a finally, per convention rule 5 (no dependence on
            # another test's fixtures), so the record is rebuilt here to the
            # same shape rather than hunted for.
            by_column = conditions_by_column(rpc)
            usable = {c: rows for c, rows in by_column.items() if rows}
            if not usable:
                ctx.blocked(
                    "no rule.collection.column value has a matching "
                    "rule.relation row, so no rule can be built and there is "
                    "nothing for this case to edit.")
            first = "title" if "title" in usable else sorted(usable)[0]
            collection_id = rpc.create(COLLECTION, {
                "name": COLLECTION_TITLE,
                "channel_id": store["id"],
                "type": TYPE_AUTOMATED,
                "condition_type": MATCH_ALL,
                "rule_ids": [(0, 0, {"column": first,
                                     "relation_id": usable[first][0]["id"],
                                     "condition": "Navajo"})],
            })
            row = rpc.read(COLLECTION, [collection_id],
                           ["type", "status"])[0]
            ctx.check("Collection Type reads Automated", TYPE_AUTOMATED,
                      row["type"])
            ctx.check("…and it is in Draft, as the precondition describes",
                      STATUS_DRAFT, row["status"])

        with ctx.step("Steps 3-5 / Expected lines 1-2: the Field dropdown is "
                      "populated, and the Condition options change with the "
                      "Field chosen"):
            labels = selection_labels(rpc, RULE, "column")
            ctx.check_true(
                "The Field dropdown lists options — 'an EMPTY dropdown is "
                "the failure this case exists to find'",
                bool(labels), actual_desc=f"{len(labels)} option(s)")

            by_column = conditions_by_column(rpc)
            for column in sorted(by_column):
                names = [r["name"] for r in by_column[column]]
                ctx.log(f"  Field {labels.get(column, column)!r} "
                        f"({column}) -> {len(names)} condition(s): {names}")

            offered = {col: tuple(sorted(r["value"] for r in rows))
                       for col, rows in by_column.items() if rows}
            ctx.check_true(
                "Every Field a rule can really use offers at least one "
                "Condition",
                bool(offered), actual_desc=f"{len(offered)} of {len(labels)} "
                                           f"Field values yield conditions")
            distinct = set(offered.values())
            ctx.check_true(
                "The Condition list is NOT the same for every Field — step "
                "4's 'not the same list for every field'. The onchange "
                "domain [('columns','=ilike','%<field>%')] is applied here "
                "per Field, the same way the editor applies it",
                len(distinct) > 1,
                actual_desc=f"{len(distinct)} distinct condition set(s) "
                            f"across {len(offered)} usable Field value(s)")

            empty = sorted(col for col in labels if not by_column.get(col))
            if empty:
                expected_empty = sorted(IMPORT_ONLY_COLUMNS)
                observation(ctx,
                            f"{len(empty)} of the {len(labels)} Field values "
                            f"offer NO Condition at all: {empty}. That is "
                            f"deliberate and documented — "
                            f"multichannel_shopify/models/"
                            f"product_collection.py:65-67 says they are "
                            f"Shopify rule columns with no product.channel "
                            f"equivalent, accepted only so that importing a "
                            f"collection that uses one does not raise and "
                            f"roll back the whole channel creation. A tester "
                            f"who picks one gets an empty Condition dropdown "
                            f"on a required field and cannot save. Worth "
                            f"hiding them from the editor, since they exist "
                            f"for the importer rather than for the user.")
                ctx.check(
                    "…and the Field values with no Condition are exactly the "
                    "four the module documents as import-only — a fifth would "
                    "be a real empty dropdown",
                    expected_empty, empty)

        with ctx.step("Steps 6-7 / Expected line 3: a rule survives a save "
                      "and a reload with the same Field, Condition and Value"):
            rule_ids = rpc.read(COLLECTION, [collection_id],
                                ["rule_ids"])[0]["rule_ids"]
            before = rpc.read(RULE, rule_ids,
                              ["column", "relation_id", "condition"])[0]
            rpc.write(RULE, [before["id"]], {"condition": "Hopi"})
            after = rpc.read(RULE, [before["id"]],
                             ["column", "relation_id", "condition"])[0]
            ctx.check("The Value came back as it was left", "Hopi",
                      after["condition"])
            ctx.check("…the Field unchanged", before["column"],
                      after["column"])
            ctx.check("…and the Condition unchanged",
                      m2o_id(before["relation_id"]),
                      m2o_id(after["relation_id"]))

        with ctx.step("Steps 8-9 / Expected line 4: a collection holds more "
                      "than one rule, and a row can be deleted again"):
            usable = {c: rows for c, rows in conditions_by_column(rpc).items()
                      if rows}
            second_column = next(
                (c for c in sorted(usable)
                 if c != rpc.read(RULE, [rpc.read(
                     COLLECTION, [collection_id], ["rule_ids"])[0]
                     ["rule_ids"][0]], ["column"])[0]["column"]),
                None)
            if not second_column:
                ctx.blocked("only one Field value is usable on this "
                            "database, so a second, DIFFERENT rule row "
                            "cannot be built.")
            rpc.write(COLLECTION, [collection_id], {
                "rule_ids": [(0, 0, {
                    "column": second_column,
                    "relation_id": usable[second_column][0]["id"],
                    "condition": "Zuni"})]})
            rows = rpc.read(COLLECTION, [collection_id],
                            ["rule_ids"])[0]["rule_ids"]
            ctx.check_true("Both rows are held", len(rows) == 2,
                           actual_desc=f"rule_ids = {rows}")
            held = rpc.read(RULE, rows, ["column", "condition"])
            ctx.check_true(
                "…and they hold DIFFERENT rules, as step 8 requires",
                len({(r["column"], r["condition"]) for r in held}) == 2,
                actual_desc=str([(r["column"], r["condition"])
                                 for r in held]))

            rpc.write(COLLECTION, [collection_id],
                      {"rule_ids": [(2, rows[-1])]})
            left = rpc.read(COLLECTION, [collection_id],
                            ["rule_ids"])[0]["rule_ids"]
            ctx.check_true("Step 9: the second row deletes again",
                           len(left) == 1, actual_desc=f"rule_ids = {left}")

        with ctx.step("Step 10 / Expected line 5: the all/any choice sticks "
                      "across a save"):
            rpc.write(COLLECTION, [collection_id],
                      {"condition_type": MATCH_ANY})
            ctx.check("Product must match reads 'any condition' after the "
                      "save", MATCH_ANY,
                      rpc.read(COLLECTION, [collection_id],
                               ["condition_type"])[0]["condition_type"])
            rpc.write(COLLECTION, [collection_id],
                      {"condition_type": MATCH_ALL})
            ctx.check("…and back to 'all condition'", MATCH_ALL,
                      rpc.read(COLLECTION, [collection_id],
                               ["condition_type"])[0]["condition_type"])

        with ctx.step("Step 11 / Expected line 6: the Products group renders "
                      "a list or its 'no products' message, never a blank "
                      "area"):
            form = raw_arch(rpc, "multichannel_shopify."
                                 "product_collection_form_view")
            products_group = ""
            for chunk in form.split("<group"):
                if 'string="Products"' in chunk[:120]:
                    products_group = chunk[:200]
                    break
            ctx.check_true("The form has a Products group",
                           bool(products_group),
                           actual_desc=products_group or "absent")
            has_products_tag = field_tag(form, "product_channel_ids")
            ctx.log(f"the product list is declared: {has_products_tag}")
            ctx.check(
                "…the product list is shown only when there ARE products",
                "not has_products", attr(has_products_tag, "invisible"))
            ctx.check_true(
                "…and the 'no products' message covers the other case, so "
                "the area is never blank",
                "There are no products in this collection" in form
                and 'invisible="has_products or not write_date"' in form,
                actual_desc="message present with the complementary "
                            "invisible rule"
                            if "There are no products in this collection"
                            in form else "no such message in the arch")
            row = rpc.read(COLLECTION, [collection_id],
                           ["has_products", "product_channel_ids"])[0]
            ctx.log(f"this collection: has_products={row['has_products']}, "
                    f"{len(row['product_channel_ids'])} product(s) — so the "
                    f"screen would show the "
                    f"{'list' if row['has_products'] else 'message'}")

    finally:
        with ctx.step("Cleanup: the collection this case created is removed"):
            if collection_id:
                try:
                    rpc.unlink(COLLECTION, [collection_id])
                    ctx.log(f"removed {COLLECTION} #{collection_id}")
                except OdooRPCError as exc:
                    ctx.log(f"could not remove #{collection_id}: {exc}")
            left = rpc.search(COLLECTION, [("name", "like", MARK)])
            ctx.check("No FG-10 collection is left behind", [], left)
