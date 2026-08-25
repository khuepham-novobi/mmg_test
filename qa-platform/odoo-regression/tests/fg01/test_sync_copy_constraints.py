"""FG-01 — sync mixin, barcode constraints, copy, archive:
TC-ART-003, -004, -005, -026.

Expected v15 outcomes: TC-ART-003, TC-ART-004 and TC-ART-026 PASS; TC-ART-005
FAILs on its last step only — v15 ``copy()`` is singleton-only
(mmg_stock/models/product.py:242-243 declares ``@api.returns`` and calls
``self.ensure_one()``), and the per-record zip is the v19 fix DW-004. That
FAIL is the documented baseline and classifies as FIXED when v19 passes.

Transport note: the runner drives /web/dataset/call_kw over an authenticated
web session, so every call commits its own transaction and the cr.precommit
sync hooks fire at the end of each call — no explicit precommit.run(), and
the template<->variant mirror persists on create (see adapters/base.py).

Live-DB determinism adaptations (documented, not assertion-weakening):

* fixture names and the x.medium reference fixtures carry the per-execution
  token (``fx()``), so ``ensure_medium()`` can never reuse a row an earlier
  run left behind, and TC-ART-005 — which has to resolve the duplicates by
  name — can never count another run's records;
* barcodes come from ``fx_barcode()``. barcode is UNIQUE database-wide and
  ``_check_barcode_numeric`` allows digits only, so a hard-coded fixture
  barcode kept alive by an archived leftover would make the next run's create
  fail for a reason that has nothing to do with the constraint under test;
* per-record/per-field verification collects mismatches and asserts once, so
  one broken field cannot hide the rest (rule 3 in tests/fg01/common.py);
* cleanup goes through ``unlink_quiet`` / ``cleanup_fg01``, which never raise:
  a raising cleanup step would replace TC-ART-005's documented FAIL with an
  ERROR.
"""
from adapters.base import OdooRPCError
from framework.registry import test_case
from tests.fg01.common import (MARK, cleanup_fg01, ensure_medium, fx,
                               fx_barcode, m2o_id, sweep_fg01, trace,
                               unlink_quiet)


def _diff(expected: dict, actual: dict, m2o_fields=()) -> dict:
    """{field: {expected, actual}} for every mismatch.

    Every field is evaluated — ``ctx.check`` raises on the first mismatch, so
    a loop of per-field checks would report one broken field and drop the
    evidence for the others.
    """
    out = {}
    for field, want in expected.items():
        got = actual[field]
        if field in m2o_fields:
            got = m2o_id(got)
        if got != want:
            out[field] = {"expected": want, "actual": got}
    return out


def _copy_and_resolve(rpc, ids, name_domain):
    """Run copy() on `ids` and resolve the duplicates from the database
    instead of from the return value.

    Why not use the return value: the v19 port of mmg_stock.copy() drops
    @api.returns (DW-004), so call_kw can no longer serialise the returned
    recordset — the call would fail for an API-shape reason while the copy
    itself succeeded. Subtracting the ids present before the call from those
    present after it keeps the assertion about business behaviour on both
    versions.

    Returns (new_ids sorted, error_message) — an empty new_ids together with a
    message is a genuine refusal (v15 copy() is singleton-only).
    """
    before = set(rpc.search("product.product", name_domain))
    error = ""
    try:
        rpc.call("product.product", "copy", ids)
    except OdooRPCError as exc:
        error = str(exc)
    after = set(rpc.search("product.product", name_domain))
    return sorted(after - before), error


@test_case(
    id="TEST-FG01-ART-003", name="Template ↔ variant field synchronisation still works",
    workflow="FG-01", workflow_name="Art Catalogue", module="mmg_stock",
    priority="P0", kind="API", order=120,
    description="Sync mixin both directions on create and write, batched "
                "create path, and a non-sync field must not propagate.",
    traceability=trace("TC-ART-003"))
def test_art_003(ctx):
    """EXPECTED v15 OUTCOME: PASS. product.level.data.sync.mixin ships in v15
    mmg_stock and the web transport commits per call, so the cr.precommit
    mirror fires on create as well as on write.

    Workbook step 6 ("a field outside _get_both_level_sync_fields() does NOT
    propagate to the variant") is asserted as the absence of INDEPENDENT
    variant storage, not as a value difference: product.product _inherits
    product.template, so the variant reads every template field by
    delegation and a value comparison would be unsatisfiable on any
    transport. See the inline comment at that step.
    """
    rpc = ctx.adapter.rpc
    with ctx.step("Sweep previous fixtures"):
        sweep_fg01(rpc)
    with ctx.step("Create medium fixtures"):
        oil = ensure_medium(rpc, fx(f"{MARK} Oil on Canvas"))
        bronze = ensure_medium(rpc, fx(f"{MARK} Bronze"))
    try:
        with ctx.step("Template→variant on create"):
            written = {"x_artist": "FG01-Dixon", "x_medium": oil,
                       "x_width": 30.0}
            tmpl = rpc.create("product.template",
                              dict({"name": fx(f"{MARK} Sync")}, **written))
            var = rpc.search_read("product.product",
                                  [("product_tmpl_id", "=", tmpl)],
                                  list(written))[0]
            ctx.check("template→variant create mismatches", {},
                      _diff(written, var, m2o_fields=("x_medium",)))
        with ctx.step("Template→variant on write"):
            written = {"x_artist": "FG01-Mell", "x_height": 40.0}
            rpc.write("product.template", [tmpl], written)
            var = rpc.search_read("product.product",
                                  [("product_tmpl_id", "=", tmpl)],
                                  list(written))[0]
            ctx.check("template→variant write mismatches", {},
                      _diff(written, var))
        with ctx.step("Variant→template on create"):
            written = {"x_medium": bronze, "x_vendor": "Consignor A"}
            var_id = rpc.create("product.product",
                                dict({"name": fx(f"{MARK} Sync V")}, **written))
            tmpl2 = m2o_id(rpc.read("product.product", [var_id],
                                    ["product_tmpl_id"])[0]["product_tmpl_id"])
            t = rpc.read("product.template", [tmpl2], list(written))[0]
            ctx.check("variant→template create mismatches", {},
                      _diff(written, t, m2o_fields=("x_medium",)))
        with ctx.step("Variant→template on write"):
            written = {"x_medium": oil, "x_gallery_cost": 1200.0}
            rpc.write("product.product", [var_id], written)
            t = rpc.read("product.template", [tmpl2], list(written))[0]
            ctx.check("variant→template write mismatches", {},
                      _diff(written, t, m2o_fields=("x_medium",)))
        with ctx.step("Batched create path (multi-record create call)"):
            ids = rpc.create("product.template", [
                {"name": fx(f"{MARK} Sync Batch 1"), "x_artist": "FG01-Batch1"},
                {"name": fx(f"{MARK} Sync Batch 2"), "x_artist": "FG01-Batch2"}])
            ids = ids if isinstance(ids, list) else [ids]
            got = {}
            for tid in ids:
                v = rpc.search_read("product.product",
                                    [("product_tmpl_id", "=", tid)],
                                    ["x_artist"])[0]
                got[tid] = v["x_artist"]
            ctx.check("each variant got its own value",
                      sorted(["FG01-Batch1", "FG01-Batch2"]),
                      sorted(got.values()))
        with ctx.step("Non-sync field is not mirrored by the mixin "
                      "(e_blast_date)"):
            # Workbook step 6 asks that a field outside
            # _get_both_level_sync_fields() "does NOT propagate to the
            # variant". Read literally against a value comparison that is
            # unsatisfiable on ANY transport: e_blast_date is declared on
            # product.template only (mmg_stock/models/product.py:137), and
            # product.product _inherits product.template, so Odoo exposes
            # every template field on the variant as a delegated field. The
            # variant therefore always reads the template's value — by
            # delegation, not by the mixin.
            # What the workbook actually protects is that the mixin does not
            # give the variant its OWN synced copy, so that is what we assert:
            # the variant-side field must have no independent storage.
            rpc.write("product.template", [tmpl],
                      {"e_blast_date": "2026-06-01"})
            row = rpc.search_read(
                "ir.model.fields",
                [("model", "=", "product.product"),
                 ("name", "=", "e_blast_date")],
                ["related", "store", "ttype"], limit=1)
            if not row:
                ctx.check("e_blast_date has no product.product field", [], row)
            else:
                ctx.check("e_blast_date on the variant is delegated to the "
                          "template (no independent stored copy)",
                          "product_tmpl_id.e_blast_date",
                          row[0]["related"])
                ctx.log("variant value comes from the template by _inherits "
                        "delegation, not from the sync mixin")
    finally:
        with ctx.step("Cleanup fixtures"):
            cleanup_fg01(ctx, rpc)


@test_case(
    id="TEST-FG01-ART-004", name="Numeric-barcode constraint enforced on template and variant",
    workflow="FG-01", workflow_name="Art Catalogue", module="mmg_stock",
    priority="P1", kind="API", order=121,
    description="Non-numeric Tile rejected on template and variant; numeric "
                "saves; duplicate rejected; UNIQUE constraint exists in "
                "pg_constraint.",
    traceability=trace("TC-ART-004"))
def test_art_004(ctx):
    """EXPECTED v15 OUTCOME: PASS. Both constraint halves ship in v15
    mmg_stock: the @api.constrains digit checks on template
    (models/product.py:157) and variant (:236), plus the
    ``product_product_barcode_uniq`` SQL constraint (:232).

    The numeric fixtures come from ``fx_barcode()`` so the duplicate under
    test is this execution's own barcode and never a leftover's.
    """
    rpc = ctx.adapter.rpc
    with ctx.step("Sweep previous fixtures"):
        sweep_fg01(rpc)
    numeric = fx_barcode(1)
    ctx.log(f"this execution's fixture Tile: {numeric}")
    created = []
    try:
        with ctx.step("Non-numeric Tile rejected at template level"):
            try:
                bad = rpc.create("product.template",
                                 {"name": fx(f"{MARK} Bad Tile T"),
                                  "barcode": "ABC123"})
                created.append(("product.template", bad))
                ctx.check("template-level rejection raised", True,
                          "no error raised")
            except OdooRPCError as exc:
                ctx.check_true("template-level rejection raised",
                               "numbers only" in str(exc).lower()
                               or "validation" in str(exc).lower(),
                               actual_desc=f"rejected: {exc}")
        with ctx.step("Non-numeric Tile rejected at variant level"):
            var = rpc.create("product.product",
                             {"name": fx(f"{MARK} Bad Tile V")})
            created.append(("product.product", var))
            try:
                rpc.write("product.product", [var], {"barcode": "12A34"})
                ctx.check("variant-level rejection raised", True,
                          "no error raised")
            except OdooRPCError as exc:
                ctx.check_true("variant-level rejection raised",
                               "numbers only" in str(exc).lower()
                               or "validation" in str(exc).lower(),
                               actual_desc=f"rejected: {exc}")
        with ctx.step("Purely numeric barcode saves"):
            holder = rpc.create("product.product",
                                {"name": fx(f"{MARK} Tile Holder"),
                                 "barcode": numeric})
            created.append(("product.product", holder))
            ctx.check("numeric barcode saved", numeric,
                      rpc.read("product.product", [holder],
                               ["barcode"])[0]["barcode"])
        with ctx.step("Duplicate Tile rejected"):
            try:
                dup = rpc.create("product.product",
                                 {"name": fx(f"{MARK} Tile Dup"),
                                  "barcode": numeric})
                created.append(("product.product", dup))
                ctx.check("duplicate barcode rejected", True,
                          "no error raised — duplicate saved")
            except OdooRPCError as exc:
                ctx.check_true("duplicate barcode rejected", True,
                               actual_desc=f"rejected: {exc}")
        with ctx.step("UNIQUE constraint physically exists (pg_constraint)"):
            row = ctx.sql.one(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE conname = 'product_product_barcode_uniq'")
            ctx.check_true("product_product_barcode_uniq contains "
                           "UNIQUE (barcode)",
                           bool(row) and "unique" in row.lower()
                           and "barcode" in row.lower(),
                           actual_desc=f"pg_constraint: {row!r}")
    finally:
        with ctx.step("Cleanup fixtures"):
            # variants first (a template unlink would take its variant with
            # it and make the second call a no-op on a missing id)
            for model in ("product.product", "product.template"):
                unlink_quiet(ctx, rpc, model,
                             [rec for mod, rec in created if mod == model])
            cleanup_fg01(ctx, rpc)


@test_case(
    id="TEST-FG01-ART-005", name="Duplicating an art item does not clone the barcode",
    workflow="FG-01", workflow_name="Art Catalogue", module="mmg_stock",
    priority="P1", kind="API", order=122,
    description="copy(): empty barcode, 17 carry-over fields kept; "
                "multi-record copy zips per record (v19 DW-004 — expected "
                "v15 FAIL on the multi-record path).",
    traceability=trace("TC-ART-005"))
def test_art_005(ctx):
    """EXPECTED v15 OUTCOME: FAIL on the last step — documented baseline.

    Single-record copy behaves as the workbook expects on v15 (empty barcode,
    carry-over values), and those assertions run first so their evidence is
    recorded. The final step asserts the workbook's multi-record expectation,
    which is the v19 fix DW-004: v15 ``copy()`` calls ``self.ensure_one()``
    (mmg_stock/models/product.py:243-244), so the call is refused with
    "Expected singleton" and the assertion FAILs. The expectation is
    immutable — it classifies as FIXED once v19 zips the values per record.
    """
    rpc = ctx.adapter.rpc
    with ctx.step("Sweep previous fixtures"):
        sweep_fg01(rpc)
    with ctx.step("Create medium fixture"):
        oil = ensure_medium(rpc, fx(f"{MARK} Oil on Canvas"))
    carryover = {
        "x_artist": "Fritz Scholder", "x_medium": oil,
        "x_gallery_cost": 5000.0, "x_consignment_percentage": 40.0,
        "x_discount": "250", "x_exclude_cart": True, "x_height": 24.0,
        "x_width": 18.0, "x_jewelry_size": "7.5", "x_ed_num": "12",
        "x_ed_size": "50", "x_date": "1978",
    }
    source_name = fx(f"{MARK} Copy Source")
    multi_name = fx(f"{MARK} Copy Multi")
    try:
        with ctx.step("Create the source variant with barcode + carry-over fields"):
            src = rpc.create("product.product", {
                "name": source_name, "barcode": fx_barcode(2),
                **carryover})
        with ctx.step("Duplicate the variant"):
            # workbook step 2 (re-browse before copying) is inherent here:
            # every RPC call re-browses by id, so no create() context sticks.
            dups, err = _copy_and_resolve(
                rpc, [src], [("name", "like", source_name)])
            ctx.check_true(
                "copy() produced exactly one duplicate", len(dups) == 1,
                actual_desc=f"{len(dups)} new record(s)"
                            + (f"; copy() error: {err}" if err else ""))
            dup = dups[0]
        with ctx.step("Assert barcode empty and carry-over values equal source"):
            d = rpc.read("product.product", [dup],
                         ["barcode"] + list(carryover))[0]
            ctx.check("duplicate barcode empty", False, d["barcode"])
            ctx.check("carry-over field mismatches", {},
                      _diff(carryover, d, m2o_fields=("x_medium",)))
        with ctx.step("Multi-record copy zips values per record (DW-004)"):
            a = rpc.create("product.product",
                           {"name": f"{multi_name} A",
                            "x_artist": "FG01-MultiA"})
            b = rpc.create("product.product",
                           {"name": f"{multi_name} B",
                            "x_artist": "FG01-MultiB"})
            dups, err = _copy_and_resolve(
                rpc, [a, b], [("name", "like", multi_name)])
            if dups:
                artists = sorted(
                    (r["x_artist"] for r in
                     rpc.read("product.product", dups, ["x_artist"])),
                    key=str)
            else:
                # genuine refusal: v15 copy() is singleton-only
                # (ensure_one via @api.returns) — DW-004 is the v19 fix, so
                # this FAIL is the documented v15 baseline.
                artists = f"copy() failed on multi-record set: {err}"
            ctx.check("multi-record duplicate works, values zipped",
                      ["FG01-MultiA", "FG01-MultiB"], artists)
    finally:
        with ctx.step("Cleanup fixtures"):
            cleanup_fg01(ctx, rpc)


@test_case(
    id="TEST-FG01-ART-026", name="Archive / unarchive an art item",
    workflow="FG-01", workflow_name="Art Catalogue", module="mmg_stock",
    priority="P2", kind="API", order=123,
    description="Archive/unarchive round-trip keeps art values + barcode; "
                "variant follows template active state.",
    traceability=trace("TC-ART-026"))
def test_art_026(ctx):
    """EXPECTED v15 OUTCOME: PASS. Archiving a template cascades to its
    variants in standard Odoo 15 and no custom field is copy/active-sensitive,
    so the round-trip keeps every art value.

    The barcode fixture is per-execution (``fx_barcode``): an archived
    leftover keeps its Tile, and a hard-coded one would make the create fail
    on the UNIQUE constraint instead of testing the archive round-trip.
    """
    rpc = ctx.adapter.rpc
    with ctx.step("Sweep previous fixtures"):
        sweep_fg01(rpc)
    barcode = fx_barcode(3)
    values = {"name": fx(f"{MARK} Archive Item"), "barcode": barcode,
              "x_artist": "FG01-Archive", "x_gallery_cost": 750.0}
    try:
        with ctx.step("Create fixture template"):
            tmpl = rpc.create("product.template", values)
        with ctx.step("Archive — variant must follow"):
            rpc.call("product.template", "action_archive", [tmpl])
            t = rpc.call("product.template", "read", [tmpl],
                         fields=["active"], context={"active_test": False})[0]
            ctx.check("template archived", False, t["active"])
            variants = rpc.call(
                "product.product", "search_read",
                [("product_tmpl_id", "=", tmpl)],
                fields=["active"], context={"active_test": False})
            ctx.check("variant archived too", [False],
                      [v["active"] for v in variants])
        with ctx.step("Values unchanged while archived"):
            kept = {"barcode": barcode, "x_artist": "FG01-Archive",
                    "x_gallery_cost": 750.0}
            t = rpc.call("product.template", "read", [tmpl],
                         fields=list(kept),
                         context={"active_test": False})[0]
            ctx.check("archived-record value mismatches", {}, _diff(kept, t))
        with ctx.step("Unarchive — every value still reads back"):
            rpc.call("product.template", "action_unarchive", [tmpl],
                     context={"active_test": False})
            t = rpc.read("product.template", [tmpl],
                         ["active"] + list(kept))[0]
            ctx.check("template active again", True, t["active"])
            ctx.check("round-trip value mismatches", {}, _diff(kept, t))
        with ctx.step("Channel-listing mapping check"):
            if rpc.model_exists("product.channel"):
                listings = rpc.search("product.channel",
                                      [("product_tmpl_id", "=", tmpl)])
                ctx.log(f"fixture has {len(listings)} channel listings — "
                        "mapping integrity for live listings is covered in "
                        "the FG-10 suite")
            else:
                ctx.log("product.channel not installed — N/A")
    finally:
        with ctx.step("Cleanup fixtures"):
            cleanup_fg01(ctx, rpc)
