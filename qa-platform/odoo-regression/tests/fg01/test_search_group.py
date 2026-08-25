"""FG-01 — search / filter / group-by: TC-ART-019, -020, -021.

Fixture artists/mediums/categories carry the FG01 marker *and* the
per-execution fixture token (`fx()` from tests/fg01/common.py) so exact-match
and count assertions stay deterministic against the 69k-product production
clone: the gallery really sells Maynard Dixon (an unscoped ilike would match
live data), and a leftover that the sweep could only archive — or that another
FG-01 test created — can never share a value with this execution and inflate
a group count. What is asserted is unchanged.

Expected v15 outcomes: all three PASS. Search, ilike, name-search on the
relation and read_group over the art fields are plain v15 ORM behaviour on
stored fields; nothing in these three cases describes the v19 target.

Cleanup runs through ``cleanup_fg01``, which never raises, so it can never
replace a verdict.
"""
from framework.registry import test_case
from tests.fg01.common import (MARK, cleanup_fg01, ensure_medium,
                               fixture_token, fx, sweep_fg01, trace)


@test_case(
    id="TEST-FG01-ART-019", name="Search/filter products by Artist",
    workflow="FG-01", workflow_name="Art Catalogue", module="mmg_stock",
    priority="P1", kind="API", order=115,
    description="ilike search returns exactly the matching template and "
                "variant; empty-artist filter; read_group per-artist counts.",
    traceability=trace("TC-ART-019"))
def test_art_019(ctx):
    """EXPECTED v15 OUTCOME: PASS. x_artist is a stored Char on both models
    in v15 mmg_stock, so ilike, the empty-value filter and read_group all
    work; nothing here describes the v19 target.

    The two artist values are namespaced (fx()) because the searches and the
    group counts match by them — the live catalogue really contains the
    workbook's artist names, and a leftover fixture from an earlier run would
    add a second row to a group.
    """
    rpc = ctx.adapter.rpc
    with ctx.step("Sweep previous fixtures"):
        sweep_fg01(rpc)
    # after the sweep: sweep_fg01() mints this execution's fixture token
    dixon, mell = fx(f"{MARK}-Dixon"), fx(f"{MARK}-Mell")
    with ctx.step("Create three fixture templates (two artists + none)"):
        t1 = rpc.create("product.template",
                        {"name": fx(f"{MARK} ART19 A"), "x_artist": dixon})
        t2 = rpc.create("product.template",
                        {"name": fx(f"{MARK} ART19 B"), "x_artist": mell})
        t3 = rpc.create("product.template",
                        {"name": fx(f"{MARK} ART19 C")})
    try:
        with ctx.step("ilike search returns exactly the Dixon template"):
            found = rpc.search("product.template",
                               [("x_artist", "ilike", dixon.lower())])
            ctx.check("template ilike match", [t1], found)
        with ctx.step("Same search at variant level"):
            vfound = rpc.search_read("product.product",
                                     [("x_artist", "ilike", dixon.lower())],
                                     ["product_tmpl_id"])
            ctx.check("variant ilike match (template ids)", [t1],
                      [v["product_tmpl_id"][0] for v in vfound])
        with ctx.step("Empty-artist filter includes the artist-less fixture"):
            empty = rpc.search("product.template",
                               [("x_artist", "=", False),
                                ("name", "like", f"{MARK} ART19"),
                                ("name", "like", fixture_token())])
            ctx.check("artist-less fixture found", [t3], empty)
        with ctx.step("read_group by x_artist returns one group per artist"):
            groups = rpc.read_group(
                "product.template",
                [("x_artist", "in", [dixon, mell])], ["x_artist"],
                ["x_artist"])
            got = sorted((g["x_artist"], g["x_artist_count"]) for g in groups)
            ctx.check("group-by artist counts",
                      [(dixon, 1), (mell, 1)], got)
    finally:
        with ctx.step("Cleanup fixtures"):
            cleanup_fg01(ctx, rpc)


@test_case(
    id="TEST-FG01-ART-020", name="Search/filter products by Medium",
    workflow="FG-01", workflow_name="Art Catalogue", module="mmg_stock",
    priority="P1", kind="API", order=116,
    description="m2o filter, relation name-search and group-by Medium on "
                "template and variant.",
    traceability=trace("TC-ART-020"))
def test_art_020(ctx):
    """EXPECTED v15 OUTCOME: PASS. x_medium is a stored Many2one to the
    Studio-era x.medium model on both product models in v15, so the m2o
    filter, the dotted name-search and read_group are all supported.

    Both medium names carry the execution token so ensure_medium() creates
    this run's own rows: the name is the value the relation name-search
    matches by.
    """
    rpc = ctx.adapter.rpc
    with ctx.step("Sweep previous fixtures"):
        sweep_fg01(rpc)
    # after the sweep: sweep_fg01() mints this execution's fixture token
    oil_name, bronze_name = fx(f"{MARK} Oil on Canvas"), fx(f"{MARK} Bronze")
    with ctx.step("Create fixtures (2 mediums, 3 templates)"):
        oil = ensure_medium(rpc, oil_name)
        bronze = ensure_medium(rpc, bronze_name)
        t1 = rpc.create("product.template",
                        {"name": fx(f"{MARK} ART20 A"), "x_medium": oil})
        t2 = rpc.create("product.template",
                        {"name": fx(f"{MARK} ART20 B"), "x_medium": oil})
        t3 = rpc.create("product.template",
                        {"name": fx(f"{MARK} ART20 C"), "x_medium": bronze})
    try:
        with ctx.step("Filter by medium id returns exactly the two Oil templates"):
            found = rpc.search("product.template", [("x_medium", "=", oil)])
            ctx.check("oil filter", sorted([t1, t2]), sorted(found))
        with ctx.step("Name search on the relation"):
            found = rpc.search("product.template",
                               [("x_medium.x_name", "ilike",
                                 bronze_name.lower())])
            ctx.check("bronze name-search", [t3], found)
        with ctx.step("read_group by medium returns counts 2 and 1"):
            groups = rpc.read_group(
                "product.template", [("x_medium", "in", [oil, bronze])],
                ["x_medium"], ["x_medium"])
            got = sorted((g["x_medium"][0], g["x_medium_count"])
                         for g in groups)
            ctx.check("group-by medium counts",
                      sorted([(oil, 2), (bronze, 1)]), got)
        with ctx.step("Variant-level filter parity (synced field)"):
            vfound = rpc.search_read("product.product",
                                     [("x_medium", "=", oil)],
                                     ["product_tmpl_id"])
            ctx.check("variant oil filter (template ids)",
                      sorted([t1, t2]),
                      sorted(v["product_tmpl_id"][0] for v in vfound))
    finally:
        with ctx.step("Cleanup fixtures"):
            cleanup_fg01(ctx, rpc)


@test_case(
    id="TEST-FG01-ART-021", name="Group products by art Category",
    workflow="FG-01", workflow_name="Art Catalogue", module="mmg_stock",
    priority="P2", kind="API", order=117,
    description="read_group by product_product_category_id returns counts "
                "3 and 1 on template and variant.",
    traceability=trace("TC-ART-021"))
def test_art_021(ctx):
    """EXPECTED v15 OUTCOME: PASS. product_product_category_id is a stored
    Many2one and sync-listed, so the 3/1 group counts hold on template and
    variant alike in v15.

    The two category names carry the execution token: the counts are asserted
    per category id, but a leftover category with the same name would be
    picked up by another run's sweep-then-reuse pattern.
    """
    rpc = ctx.adapter.rpc
    with ctx.step("Sweep previous fixtures"):
        sweep_fg01(rpc)
    # after the sweep: sweep_fg01() mints this execution's fixture token.
    # The "QA Test" prefix is preserved so sweep_fg01 still finds these.
    with ctx.step("Create fixtures (2 categories, 4 templates)"):
        paint = rpc.create("product.product.category",
                           {"name": fx("QA Test Art Category Paintings")})
        sculpt = rpc.create("product.product.category",
                            {"name": fx("QA Test Art Category Sculpture")})
        for i in range(3):
            rpc.create("product.template",
                       {"name": fx(f"{MARK} ART21 P{i}"),
                        "product_product_category_id": paint})
        rpc.create("product.template",
                   {"name": fx(f"{MARK} ART21 S0"),
                    "product_product_category_id": sculpt})
    try:
        for model in ("product.template", "product.product"):
            with ctx.step(f"read_group on {model} returns counts 3 and 1"):
                groups = rpc.read_group(
                    model,
                    [("product_product_category_id", "in", [paint, sculpt])],
                    ["product_product_category_id"],
                    ["product_product_category_id"])
                got = sorted((g["product_product_category_id"][0],
                              g["product_product_category_id_count"])
                             for g in groups)
                ctx.check(f"{model} group counts",
                          sorted([(paint, 3), (sculpt, 1)]), got)
    finally:
        with ctx.step("Cleanup fixtures"):
            cleanup_fg01(ctx, rpc)
