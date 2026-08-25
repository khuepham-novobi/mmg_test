"""FG-01 — import/export: TC-ART-024, TC-ART-025.

Expected v15 outcomes: both PASS. ``load()`` with the art columns and
``export_data`` over the art fields are v15 ORM behaviour, and the
non-numeric Tile row is rejected by the v15 constraint
(mmg_stock/models/product.py:157) — neither case describes the v19 target.

Live-DB determinism adaptations (documented, not assertion-weakening):

* the imported row names, the reference medium and the barcodes carry the
  per-execution namespace (``fx()`` / ``fx_barcode()``): the spot-check
  re-reads the imported rows BY NAME and barcode is UNIQUE database-wide, so
  a leftover the sweep could only archive would otherwise be re-read or make
  the import fail on a duplicate;
* TC-ART-025 samples live catalogue rows with the platform's own fixtures
  excluded, so the read-only export evidence is business data and cannot
  depend on another FG-01 test's fixtures;
* the per-row spot-check collects its mismatches and asserts once, so one bad
  column cannot hide the other rows;
* cleanup runs through ``cleanup_fg01``, which never raises.
"""
from framework.registry import test_case
from tests.fg01.common import (MARK, cleanup_fg01, ensure_medium, fx,
                               fx_barcode, sweep_fg01, trace)

ART_EXPORT_FIELDS = [
    "x_artist", "x_medium", "x_mediums", "x_width", "x_height", "x_depth",
    "x_jewelry_size", "x_ed_num", "x_ed_size", "x_date", "x_product_shipping",
    "x_gallery_cost", "x_cfp_category", "x_cfp_circa", "x_cfp_sub", "x_vendor",
    "x_consignment_percentage", "x_discount", "x_exclude_cart",
    "x_update_cart", "e_blast_date", "color_id", "origin_id",
    "product_product_origin_id", "product_product_style_id",
    "product_product_category_id", "product_lot_number",
    "product_starting_bid", "product_low_estimate", "product_hihg_estimate",
    "product_buy_now_price", "product_condition", "product_auction_date",
    "product_reserve", "product_auction_provenance", "barcode",
]


@test_case(
    id="TEST-FG01-ART-024", name="Import 20 art items via base_import with art fields",
    workflow="FG-01", workflow_name="Art Catalogue", module="mmg_stock",
    priority="P1", kind="API", order=130,
    description="load() imports 20 rows with art fields and rejects a "
                "non-numeric Tile row with the constraint message.",
    traceability=trace("TC-ART-024"))
def test_art_024(ctx):
    """EXPECTED v15 OUTCOME: PASS. ``load()`` is the base_import entry point
    on both versions; the art columns are stored fields, the sync mixin
    mirrors x_artist onto the variant, and the non-numeric Tile row is
    rejected by the v15 template constraint with an error message instead of
    being imported.
    """
    rpc = ctx.adapter.rpc
    with ctx.step("Sweep previous fixtures"):
        sweep_fg01(rpc)
    with ctx.step("Create import reference fixtures"):
        medium = ensure_medium(rpc, fx(f"{MARK} Import Medium"))

    def row_name(index):
        return fx(f"{MARK} Import {index:02d}")

    fields = ["name", "barcode", "x_artist", "x_medium/.id", "x_width",
              "x_height", "x_cfp_sub", "x_cfp_category", "x_vendor",
              "x_gallery_cost", "x_consignment_percentage",
              "product_lot_number"]
    rows = [[row_name(i), fx_barcode(i), f"FG01-Imp-{i}",
             str(medium), "30", "40", "Subject", "Painting", "Consignor A",
             "1000", "40", f"LOT-{i:03d}"] for i in range(20)]
    try:
        with ctx.step("Run product.template.load() with 20 rows"):
            res = rpc.call("product.template", "load", fields, rows)
            errors = [m for m in res.get("messages", [])
                      if m.get("type") == "error"]
            ctx.check("no import error messages", [], errors)
            ctx.check("20 records imported", 20, len(res.get("ids") or []))
        with ctx.step("Spot-check three imported templates + variant sync"):
            mismatches = {}
            for idx in (0, 9, 19):
                expected = {"x_artist": f"FG01-Imp-{idx}",
                            "x_gallery_cost": 1000.0,
                            "barcode": fx_barcode(idx)}
                rec = rpc.search_read(
                    "product.template", [("name", "=", row_name(idx))],
                    list(expected), limit=1)[0]
                for field, want in expected.items():
                    if rec[field] != want:
                        mismatches[f"row {idx} {field}"] = {
                            "expected": want, "actual": rec[field]}
                var = rpc.search_read(
                    "product.product",
                    [("product_tmpl_id", "=", rec["id"])],
                    ["x_artist"], limit=1)
                if not var:
                    mismatches[f"row {idx} variant"] = {
                        "expected": "one variant", "actual": "none"}
                elif var[0]["x_artist"] != expected["x_artist"]:
                    mismatches[f"row {idx} variant x_artist synced"] = {
                        "expected": expected["x_artist"],
                        "actual": var[0]["x_artist"]}
            ctx.check("imported-row mismatches", {}, mismatches)
        with ctx.step("Negative: non-numeric Tile row rejected by load()"):
            res = rpc.call("product.template", "load", fields,
                           [[fx(f"{MARK} Import Bad"), "FG01ABC",
                             "FG01-Imp-Bad", str(medium), "30", "40",
                             "Subject", "Painting", "Consignor A", "1000",
                             "40", "LOT-BAD"]])
            errors = [m for m in res.get("messages", [])
                      if m.get("type") == "error"]
            ctx.check_true("bad row rejected with an error message",
                           bool(errors) and not res.get("ids"),
                           actual_desc=f"messages={errors[:2]!r} "
                                       f"ids={res.get('ids')!r}")
    finally:
        with ctx.step("Cleanup imported fixtures"):
            cleanup_fg01(ctx, rpc)


@test_case(
    id="TEST-FG01-ART-025", name="Export 20 art items to XLSX with art fields",
    workflow="FG-01", workflow_name="Art Catalogue", module="mmg_stock",
    priority="P2", kind="API", order=131,
    description="All art fields exportable; export_data returns 20 complete "
                "rows from live catalogue data (read-only).",
    traceability=trace("TC-ART-025"))
def test_art_025(ctx):
    """EXPECTED v15 OUTCOME: PASS. Every art field is declared and exportable
    on v15 and ``export_data`` is unchanged across the versions, so 20
    complete rows come back from live catalogue data.

    Read-only: no fixture is created. The sample explicitly excludes rows this
    platform created (name NOT LIKE 'FG01%'), so the evidence is business data
    and the case cannot be influenced by another FG-01 test's fixtures.
    """
    rpc = ctx.adapter.rpc
    with ctx.step("Select 20 populated live templates (read-only, QA "
                  "fixtures excluded)"):
        ids = rpc.search("product.template",
                         [("x_artist", "!=", False),
                          ("name", "not like", f"{MARK}%")], limit=20)
        ctx.check("20 populated templates found", 20, len(ids))
    with ctx.step("Assert every art field exists and is exportable"):
        info = rpc.call("product.template", "fields_get", ART_EXPORT_FIELDS,
                        attributes=["exportable", "type"])
        missing = [f for f in ART_EXPORT_FIELDS if f not in info]
        ctx.check("all art fields declared (missing list empty)", [], missing)
        not_exportable = [f for f, meta in info.items()
                          if meta.get("exportable") is False]
        ctx.check("no field flagged non-exportable", [], not_exportable)
    with ctx.step("Run export_data over the 20 records"):
        exportable = [f for f in ART_EXPORT_FIELDS
                      if f in info and info[f].get("exportable") is not False]
        data = rpc.call("product.template", "export_data", ids, exportable)
        rows = data.get("datas", [])
        ctx.check("20 export rows returned", 20, len(rows))
        ctx.check("every row has all columns", {len(exportable)},
                  {len(r) for r in rows})
    with ctx.step("Spot-check exported x_artist values on 5 rows"):
        artist_idx = exportable.index("x_artist")
        empty = [i for i, r in enumerate(rows[:5]) if not r[artist_idx]]
        ctx.check("x_artist populated on the 5 sampled rows", [], empty)
