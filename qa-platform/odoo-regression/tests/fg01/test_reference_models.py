"""FG-01 — reference catalogue models: TC-ART-014..018.

Expected v15 outcomes: all five PASS on the current clone. Two step groups
were written as v19 targets and are worth naming, because a FAIL there is a
documented baseline rather than a regression:

* the seed XML ids (``mmg_stock.product_color_*`` / ``product_origin_*``) —
  source-verified as present in v15 mmg_stock (data/product_color_data.xml,
  data/product_origin_data.xml, both ``noupdate="1"``), so they resolve on
  this clone;
* ACL decision #4, plain-user CRUD on the reference models — granted in v15
  by security/ir.model.access.csv (``access_x_medium_user`` on
  base.group_user; the product.color / product.origin / product.product.*
  rows carry no group at all, i.e. they apply to every user).

Live-DB determinism adaptations (documented, not assertion-weakening):

* every fixture name carries the per-execution token (``fx()``); the marker
  prefixes ("QA Test …", "AA First Style") are preserved so ``sweep_fg01``'s
  prefix searches keep finding them;
* the post-delete verification counts are scoped to this execution (prefix
  LIKE + token LIKE) instead of counting every "QA Test …" row in the table:
  a leftover a crashed earlier run could not remove would otherwise fail a
  "the record I deleted is gone" assertion. What is asserted is unchanged;
* the workbook's live anchors (x.medium == 341, exactly one "White", exactly
  one "Acoma") are NOT namespaced — they describe migrated business data and
  stay hard assertions;
* cleanup runs through ``unlink_quiet`` / ``cleanup_fg01``, which never
  raise, so it can never replace a verdict.
"""
from adapters.base import OdooRPCError
from framework.registry import test_case
from framework.qa_fixtures import ensure_qa_user, rpc_as_qa_user
from tests.fg01.common import (cleanup_fg01, display_name, fixture_token, fx,
                               m2o_id, sweep_fg01, trace, unlink_quiet)


def _crud_roundtrip(ctx, rpc, model, name_field, create_name, edited_name):
    """create → display_name → write → read-back on a reference model.

    The v15/v19 difference (``name_get`` vs ``display_name``) lives in
    ``tests.fg01.common.display_name``, never inline here.
    """
    rec = rpc.create(model, {name_field: create_name})
    ctx.check(f"{model} display_name after create", create_name,
              display_name(ctx, rpc, model, rec))
    rpc.write(model, [rec], {name_field: edited_name})
    val = rpc.read(model, [rec], [name_field])[0][name_field]
    ctx.check(f"{model} readback after edit", edited_name, val)
    return rec


def _this_run(prefix: str, field: str = "name") -> list:
    """Domain matching only the records this execution created under
    `prefix`: prefix LIKE + token LIKE, so it still matches whatever suffix
    the edit step appended ("QA Test Color (edited) [token]")."""
    return [(field, "like", prefix), (field, "like", fixture_token())]


def _plain_user_crud(ctx, rpc, model: str, values: dict, created: list):
    """Workbook ACL step: a plain internal user can create and delete a
    reference record (decision #4). An AccessError is recorded as the
    assertion's actual value, never swallowed."""
    ensure_qa_user(rpc)
    try:
        user_rpc = rpc_as_qa_user(ctx.env)
        rec = user_rpc.create(model, values)
        created.append(rec)
        user_rpc.unlink(model, [rec])
        created.remove(rec)
        ctx.check("plain-user CRUD without AccessError", True, True)
    except OdooRPCError as exc:
        ctx.check("plain-user CRUD without AccessError", True,
                  f"AccessError: {exc}")


@test_case(
    id="TEST-FG01-ART-014", name="Medium reference records list/form CRUD",
    workflow="FG-01", workflow_name="Art Catalogue", module="mmg_stock",
    priority="P2", kind="API", order=110,
    description="x.medium count anchor 341; CRUD as admin and as a plain "
                "internal user (ACL decision #4 — v19 target).",
    traceability=trace("TC-ART-014"))
def test_art_014(ctx):
    """EXPECTED v15 OUTCOME: PASS. The 341-row anchor is measured to still
    hold on this clone (unlike the catalogue-size anchors of TC-DAT-011), and
    ``access_x_medium_user`` already grants base.group_user full CRUD on
    x.medium in v15, so the ACL step passes too.

    The anchor is asserted right after the sweep, before any fixture exists,
    so this execution's own rows can never be counted.
    """
    rpc = ctx.adapter.rpc
    with ctx.step("Sweep previous fixtures"):
        sweep_fg01(rpc)
    with ctx.step("Assert migrated baseline count"):
        count = rpc.call("x.medium", "search_count", [])
        ctx.check("x.medium count", 341, count)
    created = []
    try:
        with ctx.step("CRUD as admin"):
            rec = _crud_roundtrip(ctx, rpc, "x.medium", "x_name",
                                  fx("QA Test Medium"),
                                  fx("QA Test Medium (edited)"))
            created.append(rec)
            rpc.unlink("x.medium", [rec])
            created.remove(rec)
            ctx.check("count restored after delete", 341,
                      rpc.call("x.medium", "search_count", []))
        with ctx.step("CRUD as plain internal user (ACL decision #4)"):
            _plain_user_crud(ctx, rpc, "x.medium",
                             {"x_name": fx("QA Test Medium")}, created)
    finally:
        with ctx.step("Cleanup fixtures"):
            unlink_quiet(ctx, rpc, "x.medium", created)
            cleanup_fg01(ctx, rpc)


@test_case(
    id="TEST-FG01-ART-015", name="Product Colour reference CRUD + seed data present",
    workflow="FG-01", workflow_name="Art Catalogue", module="mmg_stock",
    priority="P3", kind="API", order=111,
    description="10 seeded colours resolve by XML id without duplicates "
                "(v19 seed files); CRUD round-trip.",
    traceability=trace("TC-ART-015"))
def test_art_015(ctx):
    """EXPECTED v15 OUTCOME: PASS. All ten XML ids exist in v15 mmg_stock
    (data/product_color_data.xml, loaded by the manifest), so they resolve on
    this clone and the "exactly one White" duplication guard holds. Should a
    future clone lack them, the FAIL is the documented seed-data baseline, not
    a regression.
    """
    rpc = ctx.adapter.rpc
    seeds = ["white", "brown", "black", "gray", "blue", "green", "orange",
             "red", "pink", "yellow"]
    with ctx.step("Sweep previous fixtures"):
        sweep_fg01(rpc)
    with ctx.step("Assert the 10 seeded colours resolve by XML id"):
        missing = [s for s in seeds
                   if not rpc.ref(f"mmg_stock.product_color_{s}")]
        ctx.check("all seed XML ids resolve (missing list empty)", [],
                  missing)
    with ctx.step("Assert no seed duplication"):
        # live seed value — deliberately NOT namespaced
        ctx.check("exactly one 'White'", 1, rpc.call(
            "product.color", "search_count", [("name", "=", "White")]))
    created = []
    try:
        with ctx.step("CRUD round-trip"):
            rec = _crud_roundtrip(ctx, rpc, "product.color", "name",
                                  fx("QA Test Color"),
                                  fx("QA Test Color (edited)"))
            created.append(rec)
            rpc.unlink("product.color", [rec])
            created.remove(rec)
            ctx.check("test colour deleted", 0, rpc.call(
                "product.color", "search_count", _this_run("QA Test Color")))
    finally:
        with ctx.step("Cleanup fixtures"):
            unlink_quiet(ctx, rpc, "product.color", created)
            cleanup_fg01(ctx, rpc)


@test_case(
    id="TEST-FG01-ART-016", name="Product Origin reference CRUD + seed data present",
    workflow="FG-01", workflow_name="Art Catalogue", module="mmg_stock",
    priority="P3", kind="API", order=112,
    description="Seeded origins resolve by XML id without duplicates (v19 "
                "seed files); CRUD round-trip.",
    traceability=trace("TC-ART-016"))
def test_art_016(ctx):
    """EXPECTED v15 OUTCOME: PASS — same reasoning as TC-ART-015, against
    data/product_origin_data.xml (the six sampled XML ids are all declared
    there in v15).
    """
    rpc = ctx.adapter.rpc
    seeds = ["acoma", "alaskan", "apache", "arapaho", "bisti", "chinle"]
    with ctx.step("Sweep previous fixtures"):
        sweep_fg01(rpc)
    with ctx.step("Assert seeded origins resolve by XML id"):
        missing = [s for s in seeds
                   if not rpc.ref(f"mmg_stock.product_origin_{s}")]
        ctx.check("all seed XML ids resolve (missing list empty)", [],
                  missing)
    with ctx.step("Assert no seed duplication"):
        # live seed value — deliberately NOT namespaced
        ctx.check("exactly one 'Acoma'", 1, rpc.call(
            "product.origin", "search_count", [("name", "=", "Acoma")]))
    created = []
    try:
        with ctx.step("CRUD round-trip"):
            rec = _crud_roundtrip(ctx, rpc, "product.origin", "name",
                                  fx("QA Test Origin"),
                                  fx("QA Test Origin (edited)"))
            created.append(rec)
            rpc.unlink("product.origin", [rec])
            created.remove(rec)
            ctx.check("test origin deleted", 0, rpc.call(
                "product.origin", "search_count", _this_run("QA Test Origin")))
    finally:
        with ctx.step("Cleanup fixtures"):
            unlink_quiet(ctx, rpc, "product.origin", created)
            cleanup_fg01(ctx, rpc)


@test_case(
    id="TEST-FG01-ART-017", name="Product Style reference CRUD",
    workflow="FG-01", workflow_name="Art Catalogue", module="mmg_stock",
    priority="P3", kind="API", order=113,
    description="product.product.style CRUD, name ordering, plain-user CRUD.",
    traceability=trace("TC-ART-017"))
def test_art_017(ctx):
    """EXPECTED v15 OUTCOME: PASS. product.product.style declares
    ``_order = 'name'`` in v15 mmg_stock and its ACL row carries no group, so
    the ordering and the plain-user CRUD step both hold.

    The ordering fixtures keep their "AA …" / "QA Test …" prefixes with the
    token appended, so the asserted alphabetical order is unchanged and the
    sweep still finds them.
    """
    rpc = ctx.adapter.rpc
    with ctx.step("Sweep previous fixtures"):
        sweep_fg01(rpc)
    created = []
    try:
        with ctx.step("CRUD round-trip"):
            edited = fx("QA Test Style (edited)")
            rec = _crud_roundtrip(ctx, rpc, "product.product.style", "name",
                                  fx("QA Test Style"), edited)
            created.append(rec)
        with ctx.step("Assert ordering by name (_order = 'name')"):
            first_name = fx("AA First Style")
            first = rpc.create("product.product.style", {"name": first_name})
            created.append(first)
            found = rpc.search_read(
                "product.product.style",
                [("name", "in", [first_name, edited])], ["name"])
            ctx.check("ordered by name", [first_name, edited],
                      [r["name"] for r in found])
            rpc.unlink("product.product.style", [rec, first])
            created.clear()
        with ctx.step("Create/delete as plain internal user"):
            _plain_user_crud(ctx, rpc, "product.product.style",
                             {"name": fx("QA Test Style")}, created)
    finally:
        with ctx.step("Cleanup fixtures"):
            unlink_quiet(ctx, rpc, "product.product.style", created)
            cleanup_fg01(ctx, rpc)


@test_case(
    id="TEST-FG01-ART-018", name="Product (art) Category reference CRUD",
    workflow="FG-01", workflow_name="Art Catalogue", module="mmg_stock",
    priority="P3", kind="API", order=114,
    description="product.product.category CRUD, m2o from template resolves, "
                "referenced unlink raises-or-nulls consistently, clean "
                "unlink once unreferenced; plain-user CRUD.",
    traceability=trace("TC-ART-018"))
def test_art_018(ctx):
    """EXPECTED v15 OUTCOME: PASS. Everything asserted here is v15 behaviour:
    the m2o resolves, the referenced-unlink outcome is observed rather than
    prescribed (either a raise or an FK null-out is accepted, but the pair
    error/database-state must agree), the unreferenced unlink succeeds, and
    the ACL row for product.product.category carries no group so a plain user
    may create and delete.
    """
    rpc = ctx.adapter.rpc
    with ctx.step("Sweep previous fixtures"):
        sweep_fg01(rpc)
    created = []
    with ctx.step("CRUD round-trip"):
        cat = _crud_roundtrip(ctx, rpc, "product.product.category", "name",
                              fx("QA Test Art Category"),
                              fx("QA Test Art Category (edited)"))
    tmpl = None
    try:
        with ctx.step("Link the category from a product template"):
            tmpl = rpc.create("product.template", {
                "name": fx("FG01 Categ Link"),
                "product_product_category_id": cat})
            data = rpc.read("product.template", [tmpl],
                            ["product_product_category_id"])[0]
            ctx.check("m2o resolves", cat,
                      data["product_product_category_id"][0])
        with ctx.step("Deleting a still-referenced category behaves "
                      "consistently (unlink raises, or nulls per the FK)"):
            # workbook step 4, first half: the referenced-unlink behaviour has
            # to be OBSERVED before the link is removed. Either outcome is
            # accepted — a raise (ondelete='restrict'/RedirectWarning) or a
            # silent FK null-out (ondelete='set null') — but the pair
            # (error, database state) must agree.
            try:
                rpc.unlink("product.product.category", [cat])
                raised, detail = False, "unlink() returned without error"
            except OdooRPCError as exc:
                raised, detail = True, f"unlink() raised: {exc}"
            ctx.log(detail)
            survived = bool(rpc.call("product.product.category",
                                     "search_count", [("id", "=", cat)]))
            if survived:
                created.append(cat)
            # search_read (not read) so a cascade-deleted template is reported
            # as an outcome instead of raising MissingError past the assertion
            rows = rpc.search_read("product.template", [("id", "=", tmpl)],
                                   ["product_product_category_id"],
                                   context={"active_test": False})
            link = (m2o_id(rows[0]["product_product_category_id"])
                    if rows else "template gone (cascade)")
            if raised and survived and link == cat:
                observed = ("raised — category kept, template m2o still "
                            f"{link}")
            elif not raised and not survived and link is None:
                observed = "nulled — category removed, template m2o set NULL"
            else:
                observed = (f"inconsistent — raised={raised}, "
                            f"category_present={survived}, m2o={link!r}")
            ctx.check_true(
                "referenced unlink either raises or nulls the FK",
                observed.startswith(("raised", "nulled")),
                actual_desc=observed)
        with ctx.step("Unlink category cleanly once unreferenced"):
            if survived:
                rpc.write("product.template", [tmpl],
                          {"product_product_category_id": False})
            else:
                # the FK nulled the reference and took the category with it;
                # workbook step 4's clean-unlink expectation is then asserted
                # on a fresh, never-referenced record so the step still proves
                # that unlink succeeds once unreferenced
                cat = rpc.create("product.product.category",
                                 {"name": fx("QA Test Art Category (clean)")})
                created.append(cat)
            rpc.unlink("product.product.category", [cat])
            if cat in created:
                created.remove(cat)
            ctx.check("category gone", 0, rpc.call(
                "product.product.category", "search_count",
                [("id", "=", cat)]))
        with ctx.step("Create/delete as plain internal user"):
            _plain_user_crud(ctx, rpc, "product.product.category",
                             {"name": fx("QA Test Art Category")}, created)
    finally:
        with ctx.step("Cleanup fixtures"):
            unlink_quiet(ctx, rpc, "product.product.category", created)
            cleanup_fg01(ctx, rpc)
