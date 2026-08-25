"""FG-01 — stored compute + image route: TC-ART-007, TC-ART-013.

Expected v15 outcomes: both FAIL, each on its own last step, and both FAILs
are real findings rather than automation artefacts:

* TC-ART-007 — DW-005. ``_compute_website_extra_categories``
  (mmg_stock/models/product.py:278-282) assigns only inside
  ``if record.x_categ_ids:`` and has no else branch, so the stored text keeps
  its previous value when the last category is removed. The clear-path
  assertion is the v19 fix; it classifies as FIXED once v19 passes.
* TC-ART-013 — an image_1920 supplied in ``create()`` values is silently
  dropped on v15 (a follow-up ``write()`` stores it). Measured over the web
  transport the platform drives (/web/dataset/call_kw), so it is not the
  /jsonrpc flush asymmetry: it is a genuine finding and the assertion stays.

Assertion order in TC-ART-013 is deliberate: the create-path probe runs
first but is only *recorded* there; the write path, the related-field mirror
and the authenticated /web/image evidence are asserted next, and the
create-path expectation is asserted LAST. Asserting it up front aborted the
test at step 1 and destroyed the evidence for everything the workbook asks
for after it (observed on RUN-700517E4).

Fixture names and the category names the compute is compared against carry
the per-execution token (``fx()``): the assertion compares the stored text
with the joined display names, so a stale value left by an earlier run must
not be able to match by accident.
"""
import base64
import urllib.request

from framework.registry import test_case
from tests.fg01.common import (MARK, PNG_1PX, cleanup_fg01, fx, http_session,
                               sweep_fg01, trace)


@test_case(
    id="TEST-FG01-ART-007", name="Website extra categories compute correctly",
    workflow="FG-01", workflow_name="Art Catalogue", module="mmg_stock",
    priority="P1", kind="API", order=150,
    description="website_extra_categories recomputes on category add/remove "
                "and clears to False when the last category is removed "
                "(DW-005 — expected FAIL on v15).",
    traceability=trace("TC-ART-007"))
def test_art_007(ctx):
    """EXPECTED v15 OUTCOME: FAIL on the last step — documented baseline
    (DW-005). Add and partial-removal recomputes are v15 behaviour and are
    asserted first; the clear-on-last-removal expectation describes the v19
    fix, because the v15 compute never assigns when x_categ_ids is empty.
    """
    rpc = ctx.adapter.rpc
    with ctx.step("Sweep previous fixtures"):
        sweep_fg01(rpc)
    with ctx.step("Create category fixtures + variant"):
        c1 = rpc.create("product.category",
                        {"name": fx(f"{MARK} Web Categ 1")})
        c2 = rpc.create("product.category",
                        {"name": fx(f"{MARK} Web Categ 2")})
        var = rpc.create("product.product",
                         {"name": fx(f"{MARK} Web Categ")})
        names = {c: rpc.read("product.category", [c], ["display_name"])[0]
                 ["display_name"] for c in (c1, c2)}
    try:
        with ctx.step("Add two categories — stored compute matches"):
            rpc.write("product.product", [var],
                      {"x_categ_ids": [(6, 0, [c1, c2])]})
            got = rpc.read("product.product", [var],
                           ["website_extra_categories"])[0]
            ctx.check("compute after add", ", ".join([names[c1], names[c2]]),
                      got["website_extra_categories"])
        with ctx.step("Remove one category — recomputes to the remaining one"):
            rpc.write("product.product", [var],
                      {"x_categ_ids": [(6, 0, [c1])]})
            got = rpc.read("product.product", [var],
                           ["website_extra_categories"])[0]
            ctx.check("compute after removal", names[c1],
                      got["website_extra_categories"])
        with ctx.step("Remove the last category — must clear (DW-005 fix)"):
            rpc.write("product.product", [var], {"x_categ_ids": [(5, 0, 0)]})
            got = rpc.read("product.product", [var],
                           ["website_extra_categories"])[0]
            ctx.check("compute cleared to falsy on last removal", False,
                      got["website_extra_categories"] or False)
    finally:
        with ctx.step("Cleanup fixtures"):
            cleanup_fg01(ctx, rpc)


@test_case(
    id="TEST-FG01-ART-013", name="Image download field usable for channel export",
    workflow="FG-01", workflow_name="Art Catalogue", module="mmg_stock",
    priority="P2", kind="API", order=151,
    description="image_1920_download mirrors image_1920 and the /web/image "
                "route serves it over an authenticated session; the "
                "unauthenticated behaviour is recorded. The create-path "
                "expectation (image in create() values) is asserted last — "
                "expected v15 FAIL, a genuine finding.",
    traceability=trace("TC-ART-013"))
def test_art_013(ctx):
    """EXPECTED v15 OUTCOME: FAIL on the final step — genuine product/version
    finding, not a version-gap target: an image_1920 passed in ``create()``
    values is not stored on v15, while the same value written afterwards is.

    The workbook's step 1 expectation is therefore kept verbatim but asserted
    LAST, so the write path, the ``image_1920_download`` mirror and the
    authenticated /web/image evidence the workbook also asks for are all
    recorded before the known failure. The probe itself still runs first (that
    is where the image is supplied in create values) — only its assertion
    moved.
    """
    rpc = ctx.adapter.rpc
    with ctx.step("Sweep previous fixtures"):
        sweep_fg01(rpc)
    try:
        with ctx.step("Probe: create the template with image_1920 in the "
                      "create values (recorded here, asserted in the last "
                      "step)"):
            tmpl = rpc.create("product.template",
                              {"name": fx(f"{MARK} Image"),
                               "image_1920": PNG_1PX})
            created = rpc.read("product.template", [tmpl], ["image_1920"])[0]
            create_chars = len(created["image_1920"] or "")
            ctx.log(f"create-time image_1920: {create_chars} b64 chars; "
                    f"identical to the fixture: "
                    f"{created['image_1920'] == PNG_1PX}")
        with ctx.step("Re-attach the image with write() and re-verify"):
            rpc.write("product.template", [tmpl], {"image_1920": PNG_1PX})
            written = rpc.read("product.template", [tmpl], ["image_1920"])[0]
            ctx.check_true("image_1920 stored non-empty after write",
                           bool(written["image_1920"]),
                           actual_desc=f"{len(written['image_1920'] or '')} "
                                       "b64 chars")
        with ctx.step("Related field mirrors image_1920"):
            data = rpc.read("product.template", [tmpl],
                            ["image_1920", "image_1920_download"])[0]
            ctx.check_true("image_1920 stored non-empty",
                           bool(data["image_1920"]),
                           actual_desc=f"{len(data['image_1920'] or '')} b64 chars")
            ctx.check_true("image_1920_download equals image_1920",
                           data["image_1920_download"] == data["image_1920"],
                           actual_desc="equal" if data["image_1920_download"]
                           == data["image_1920"] else "differs")
        url = (f"{ctx.env.base_url}/web/image/product.template/{tmpl}"
               f"/image_1920_download")
        with ctx.step("Authenticated GET of the export URL returns the image"):
            opener = http_session(ctx.env)
            res = opener.open(url, timeout=30)
            body = res.read()
            ctype = res.headers.get("Content-Type", "")
            expected_bytes = base64.b64decode(PNG_1PX)
            ctx.check("HTTP 200", 200, res.status)
            ctx.check_true("image content type",
                           ctype.startswith("image/"),
                           actual_desc=f"Content-Type: {ctype}")
            ctx.check_true("body carries the PNG signature",
                           body[:8] == b"\x89PNG\r\n\x1a\n",
                           actual_desc=f"{len(body)} bytes, "
                                       f"first 8 = {body[:8]!r}")
            ctx.check_true("body decodes to the fixture image",
                           body == expected_bytes,
                           actual_desc=f"{len(body)} bytes vs "
                                       f"{len(expected_bytes)} expected "
                                       f"({'identical' if body == expected_bytes else 'differs'})")
        with ctx.step("Record the unauthenticated behaviour (documentation)"):
            try:
                anon = urllib.request.urlopen(url, timeout=30)
                ctx.log(f"unauthenticated GET: HTTP {anon.status}, "
                        f"{len(anon.read())} bytes, "
                        f"type {anon.headers.get('Content-Type')}")
            except Exception as exc:  # noqa: BLE001 — documenting only
                ctx.log(f"unauthenticated GET refused/redirected: {exc}")
        with ctx.step("Assert the create() path stored the image (workbook "
                      "step 1 — expected v15 FAIL, genuine finding)"):
            ctx.check_true("image_1920 stored non-empty after create",
                           bool(create_chars),
                           actual_desc=f"{create_chars} b64 chars")
    finally:
        with ctx.step("Cleanup fixtures"):
            cleanup_fg01(ctx, rpc)
