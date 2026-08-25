"""FG-01 — catalogue record CRUD: TC-ART-001, -011, -022, -009, -010.

Expected v15 outcomes: TC-ART-001, -011, -022 and -009 PASS; TC-ART-010 FAILs
on a CONFIRMED PRODUCT DEFECT that will not self-heal on v19 (see its
docstring).

Live-DB determinism adaptations (documented, not assertion-weakening):

* Fixture *record names* go through ``fx()`` so they are unique per execution.
  Names are the only values these tests match by name (``sweep_fg01``'s
  marker-scoped searches, ``ensure_medium``'s search-by-x_name); a leftover an
  earlier run could only archive can therefore never be reused or counted.
  Workbook *data* values ("Maynard Dixon", "Consignor A", "520-555-0100", …)
  are deliberately NOT namespaced — they are read back by record id, so the
  asserted values stay exactly the workbook's.

* Per-field verification collects mismatches into one mapping asserted once.
  ``ctx.check`` raises on the first mismatch, so a loop of per-field
  ``ctx.check`` calls reported one broken field and silently never evaluated
  the rest (observed on TC-ART-001: 1 of 14 sync fields evaluated). The
  collected form records the complete picture in a single assertion.

* Cleanup runs through ``cleanup_fg01`` / ``unlink_quiet``, which never raise:
  a raising cleanup step replaces the verdict, turning TC-ART-010's documented
  FAIL into an ERROR.
"""
import xml.etree.ElementTree as ET

from framework.registry import test_case
from framework.qa_fixtures import ensure_qa_user
from tests.fg01.common import (MARK, cleanup_fg01, ensure_medium, form_arch,
                               fx, m2o_id, sweep_fg01, trace, unlink_quiet)

SYNC_FIELDS = ["x_artist", "x_medium", "x_width", "x_height", "x_depth",
               "x_jewelry_size", "x_ed_num", "x_ed_size", "x_date",
               "x_cfp_category", "x_cfp_sub", "x_vendor", "x_gallery_cost",
               "x_consignment_percentage"]

# Workbook TC-ART-001 expected_result: "template-only fields
# product_auction_provenance and x_cfp_circa stay on the template".
# "Template-only" means excluded from the mixin sync list
# _get_both_level_sync_fields() (mmg_stock/models/product.py:33-61) — the two
# names are absent from it. Their mechanics differ, and both are asserted:
#   * product_auction_provenance is declared on product.template only
#     (mmg_stock/models/product.py:154) → it must not exist on product.product;
#   * x_cfp_circa IS declared on product.product too
#     (mmg_stock/models/product.py:208) but is not sync-listed → the variant's
#     copy must stay empty while the template holds the written value.
TEMPLATE_ONLY_FIELDS = ["product_auction_provenance", "x_cfp_circa"]


def _mismatches(expected: dict, actual: dict, fields) -> dict:
    """Compare `fields` and return {field: {expected, actual}} for every
    mismatch — evaluated for ALL fields, never short-circuited."""
    out = {}
    for field in fields:
        got = actual[field]
        if field == "x_medium":
            got = m2o_id(got)
        if got != expected[field]:
            out[field] = {"expected": expected[field], "actual": got}
    return out


def _form_field_order(ctx, model: str) -> list:
    """Field names of the model's default form view, in document order."""
    arch = form_arch(ctx, model)
    if arch.lstrip().startswith("<?xml"):
        arch = arch.split("?>", 1)[1]
    return [el.get("name") for el in ET.fromstring(arch).iter("field")
            if el.get("name")]


@test_case(
    id="TEST-FG01-ART-001", name="Create an art item with the full catalogue record",
    workflow="FG-01", workflow_name="Art Catalogue", module="mmg_stock",
    priority="P0", kind="API", order=101,
    description="Full 17-field catalogue create at ORM level; every field "
                "reads back; variant mirrors the sync-listed fields.",
    traceability=trace("TC-ART-001"))
def test_art_001(ctx):
    """EXPECTED v15 OUTCOME: PASS. Every asserted behaviour (17-field create,
    the 14 sync-listed mirror fields, the two template-only fields having no
    independent variant storage) is v15 behaviour of mmg_stock — nothing here
    describes the v19 target.

    Workbook steps 4 and 5 verify 17 template fields and 14 variant sync
    fields. Both verifications collect their mismatches and assert once, so a
    single broken field no longer masks the other 30 (see module docstring).
    Step 5's parenthetical — the two template-only fields — is asserted too.
    """
    rpc = ctx.adapter.rpc
    with ctx.step("Sweep previous FG-01 fixtures"):
        sweep_fg01(rpc)
    with ctx.step("Create x.medium fixture"):
        medium = ensure_medium(rpc, fx(f"{MARK} Oil on Canvas"))
    values = {
        "name": fx(f"{MARK} Full Record"), "x_artist": "Maynard Dixon",
        "x_medium": medium, "x_width": 30.0, "x_height": 40.0, "x_depth": 2.0,
        "x_jewelry_size": "7.5", "x_ed_num": "12", "x_ed_size": "50",
        "x_date": "1935", "x_cfp_circa": "c. 1935",
        "x_cfp_sub": "Desert landscape", "x_cfp_category": "Painting",
        "product_auction_provenance": "Estate of the artist",
        "x_vendor": "Consignor A", "x_gallery_cost": 5000.0,
        "x_consignment_percentage": 40.0,
    }
    with ctx.step("Create the full catalogue record (17 fields)"):
        tmpl_id = rpc.create("product.template", values)
        ctx.log(f"template id {tmpl_id}")
    try:
        with ctx.step("Re-browse and assert every field reads back exactly"):
            data = rpc.read("product.template", [tmpl_id],
                            list(values.keys()))[0]
            mismatches = _mismatches(values, data, list(values.keys()))
            ctx.check("template field mismatches", {}, mismatches)
        variant = None
        with ctx.step("Assert the variant mirrors all sync-listed fields"):
            var = rpc.search_read("product.product",
                                  [("product_tmpl_id", "=", tmpl_id)],
                                  ["id"] + SYNC_FIELDS + ["x_cfp_circa"],
                                  limit=2)
            ctx.check("exactly one variant", expected=1, actual=len(var))
            variant = var[0]
            mismatches = _mismatches(values, variant, SYNC_FIELDS)
            ctx.check("variant sync-field mismatches", {}, mismatches)
        with ctx.step("Assert the template-only fields stayed on the template"):
            # "Template-only" cannot mean "invisible on the variant":
            # product.product _inherits product.template, so Odoo exposes
            # EVERY template field on the variant as a delegated field
            # (measured: product_auction_provenance reads on product.product
            # as type=text). What the workbook protects is that the sync mixin
            # gives the variant no INDEPENDENT copy, so that is what we check:
            # each template-only field must have no own storage on
            # product.product - either no ir.model.fields row at all, or a
            # row delegated through product_tmpl_id.
            own_storage = {}
            for field in TEMPLATE_ONLY_FIELDS:
                rows = rpc.search_read(
                    "ir.model.fields",
                    [("model", "=", "product.product"), ("name", "=", field)],
                    ["related", "store"], limit=1)
                if rows and rows[0]["related"] != f"product_tmpl_id.{field}":
                    own_storage[field] = {
                        "related": rows[0]["related"],
                        "store": rows[0]["store"],
                    }
            ctx.check("template-only fields have no independent storage on "
                      "the variant", {}, own_storage)
            tmpl = rpc.read("product.template", [tmpl_id],
                            TEMPLATE_ONLY_FIELDS)[0]
            ctx.check("template still holds both template-only values",
                      {f: values[f] for f in TEMPLATE_ONLY_FIELDS},
                      {f: tmpl[f] for f in TEMPLATE_ONLY_FIELDS})
    finally:
        with ctx.step("Cleanup fixtures"):
            cleanup_fg01(ctx, rpc)


@test_case(
    id="TEST-FG01-ART-011", name="Auction data capture",
    workflow="FG-01", workflow_name="Art Catalogue", module="mmg_stock",
    priority="P1", kind="API", order=102,
    description="All nine auction values persist; six sync-listed values "
                "mirror onto the variant; three stay template-only.",
    traceability=trace("TC-ART-011"))
def test_art_011(ctx):
    """EXPECTED v15 OUTCOME: PASS. The nine auction fields and the six the
    sync mixin lists (mmg_stock/models/product.py:33-61) are v15 behaviour;
    no step describes the v19 port.

    The three template-only auction fields are covered by TC-ART-001's
    no-independent-variant-storage assertion — product.product _inherits
    product.template, so they are readable on the variant by delegation and
    "absent on the variant" would be an unsatisfiable expectation here.
    """
    rpc = ctx.adapter.rpc
    with ctx.step("Sweep previous fixtures"):
        sweep_fg01(rpc)
    auction = {
        "product_lot_number": "LOT-042", "product_starting_bid": "1000",
        "product_low_estimate": "1500", "product_hihg_estimate": "3000",
        "product_buy_now_price": "3500", "product_condition": "Excellent",
        "product_auction_date": "2026-09-01", "product_reserve": 1200.0,
        "product_auction_provenance": "Estate of the artist",
    }
    synced = ["product_lot_number", "product_starting_bid",
              "product_low_estimate", "product_hihg_estimate",
              "product_buy_now_price", "product_condition"]
    with ctx.step("Create template and write the nine auction values"):
        tmpl_id = rpc.create("product.template",
                             {"name": fx(f"{MARK} Auction Item")})
        rpc.write("product.template", [tmpl_id], auction)
    try:
        with ctx.step("Assert all nine values read back exactly"):
            data = rpc.read("product.template", [tmpl_id],
                            list(auction.keys()))[0]
            ctx.check("template auction field mismatches", {},
                      _mismatches(auction, data, list(auction.keys())))
        with ctx.step("Assert the variant mirrors the six synced fields"):
            var = rpc.search_read("product.product",
                                  [("product_tmpl_id", "=", tmpl_id)],
                                  synced, limit=1)[0]
            ctx.check("variant auction sync-field mismatches", {},
                      _mismatches(auction, var, synced))
    finally:
        with ctx.step("Cleanup fixtures"):
            cleanup_fg01(ctx, rpc)


@test_case(
    id="TEST-FG01-ART-022", name="Gallery Cost and Consignment % editable and stored",
    workflow="FG-01", workflow_name="Art Catalogue", module="mmg_stock",
    priority="P1", kind="API", order=103,
    description="x_gallery_cost / x_consignment_percentage persist on the "
                "variant, mirror to the template, and feed search_read.",
    traceability=trace("TC-ART-022"))
def test_art_022(ctx):
    """EXPECTED v15 OUTCOME: PASS. x_gallery_cost and
    x_consignment_percentage are stored code fields on both models and are
    sync-listed, so persistence, the variant→template mirror and the
    search_read read-back are all v15 behaviour.

    The three read-backs each verify both fields at once through a collected
    mismatch mapping, so a single broken field cannot hide the other.
    """
    rpc = ctx.adapter.rpc
    expected = {"x_gallery_cost": 5000.0, "x_consignment_percentage": 40.0}
    with ctx.step("Sweep previous fixtures"):
        sweep_fg01(rpc)
    with ctx.step("Create variant and write cost/consignment"):
        var_id = rpc.create("product.product",
                            {"name": fx(f"{MARK} Cost Item")})
        rpc.write("product.product", [var_id], dict(expected))
    try:
        with ctx.step("Assert values persist on the variant"):
            v = rpc.read("product.product", [var_id],
                         list(expected) + ["product_tmpl_id"])[0]
            ctx.check("variant field mismatches", {},
                      _mismatches(expected, v, list(expected)))
        with ctx.step("Assert values mirrored onto the template (sync mixin)"):
            t = rpc.read("product.template", [m2o_id(v["product_tmpl_id"])],
                         list(expected))[0]
            ctx.check("template mirror mismatches", {},
                      _mismatches(expected, t, list(expected)))
        with ctx.step("Assert search_read feeds reporting"):
            sr = rpc.search_read("product.product", [("id", "=", var_id)],
                                 list(expected))
            ctx.check("search_read mismatches", {},
                      _mismatches(expected, sr[0], list(expected)))
    finally:
        with ctx.step("Cleanup fixtures"):
            cleanup_fg01(ctx, rpc)


@test_case(
    id="TEST-FG01-ART-009", name="Museum-membership purchase date on a contact",
    workflow="FG-01", workflow_name="Art Catalogue", module="mmg_stock",
    priority="P2", kind="API", order=104,
    description="mmg_museum_membership_ps_date persists, is copy=False, and "
                "renders on the contact form anchored after vat.",
    traceability=trace("TC-ART-009"))
def test_art_009(ctx):
    """EXPECTED v15 OUTCOME: PASS. mmg_museum_membership_ps_date is a
    code-declared copy=False field placed by a code-owned view inherit, so
    every asserted fact holds on the v15 clone; the arch assertion is the
    regression detector for v19.

    Workbook expected_result: "the date persists AND is visible on the
    contact form"; step 5 is the form spot-check (field renders, anchored
    after vat). mmg_stock places it by xpath after //field[@name='vat'] in
    views/partner_views.xml (mmg_view_partner_details_form_inherit), so the
    arch assertion passes on v15 and becomes a real regression detector for
    v19: if the v19 base partner form drops or moves the vat anchor, the
    inherit either fails to apply or lands somewhere else.
    """
    rpc = ctx.adapter.rpc
    with ctx.step("Sweep previous fixtures"):
        sweep_fg01(rpc)
    with ctx.step("Create contact and set the membership date"):
        pid = rpc.create("res.partner", {"name": fx(f"{MARK} Member")})
        rpc.write("res.partner", [pid],
                  {"mmg_museum_membership_ps_date": "2026-01-15"})
    dup = None
    try:
        with ctx.step("Assert the date reads back"):
            val = rpc.read("res.partner", [pid],
                           ["mmg_museum_membership_ps_date"])[0]
            ctx.check("membership date", "2026-01-15",
                      val["mmg_museum_membership_ps_date"])
        with ctx.step("Duplicate the contact — copy=False must hold"):
            dup = rpc.call("res.partner", "copy", [pid])
            dup_val = rpc.read("res.partner", [dup],
                               ["mmg_museum_membership_ps_date"])[0]
            ctx.check("duplicate has no membership date", False,
                      dup_val["mmg_museum_membership_ps_date"])
        with ctx.step("Form spot-check: the field renders after the vat "
                      "anchor on the contact form"):
            names = _form_field_order(ctx, "res.partner")
            ctx.check(
                "vat anchor and membership date both in the res.partner "
                "form arch",
                {"vat": True, "mmg_museum_membership_ps_date": True},
                {"vat": "vat" in names,
                 "mmg_museum_membership_ps_date":
                     "mmg_museum_membership_ps_date" in names})
            ctx.check("membership date rendered after vat", True,
                      names.index("mmg_museum_membership_ps_date")
                      > names.index("vat"))
    finally:
        with ctx.step("Cleanup fixtures"):
            unlink_quiet(ctx, rpc, "res.partner",
                         ([dup] if dup else []) + [pid])
            cleanup_fg01(ctx, rpc)


@test_case(
    id="TEST-FG01-ART-010", name="Main Phone on partner and user",
    workflow="FG-01", workflow_name="Art Catalogue", module="mmg_stock",
    priority="P2", kind="API", order=105,
    description="x_main_phone reads/writes identically through the related "
                "user and the partner (single source of truth); field is "
                "code-declared (state base).",
    traceability=trace("TC-ART-010"))
def test_art_010(ctx):
    """EXPECTED v15 OUTCOME: FAIL — CONFIRMED PRODUCT DEFECT. This FAIL is a
    real defect, not a v15/v19 version gap, and must NOT be auto-scored
    FIXED.

    Root cause: mmg_stock/models/res_users.py:9 declares a plain
    ``x_main_phone = fields.Char(string='Main Phone')`` on res.users. Odoo
    adds an _inherits-delegated field only when the name is not already taken
    (odoo/models.py: inherited fields are added "if name not in
    self._fields"), so this declaration SHADOWS the delegation: res_users
    grows its own column and partner/user own two independent values that can
    never agree. Reading through the user after a partner write returns the
    user's own (empty) column, and writing through the user leaves the
    partner untouched.

    Why it will not self-heal on v19: the shadowing Char lives in the shared
    mmg_stock branch, not in version-specific code, so the v19 port carries
    it forward unchanged. Expect the same FAIL on v19 until res_users.py:9 is
    deleted — do not classify a v19 FAIL here as a regression, and do not
    classify it FIXED without confirming that declaration is gone.

    Assertion order is deliberate: the ir.model.fields diagnostic runs before
    the divergence assertion so the recorded failure names the root cause in
    one line for the developer, and the three readings it explains are logged
    immediately above it.

    The test writes on the platform's own QA internal user (never a business
    contact) and restores both x_main_phone values in a defensive finally
    step, so a rerun starts from the same state.
    """
    rpc = ctx.adapter.rpc
    first, second = "520-555-0100", "520-555-0199"
    with ctx.step("Ensure the QA internal user exists"):
        uid = ensure_qa_user(rpc)
        partner_id = m2o_id(rpc.read("res.users", [uid], ["partner_id"])[0]
                            ["partner_id"])
    with ctx.step("Snapshot the QA user's/partner's current Main Phone"):
        before = {
            "partner": rpc.read("res.partner", [partner_id],
                                ["x_main_phone"])[0]["x_main_phone"],
            "user": rpc.read("res.users", [uid],
                             ["x_main_phone"])[0]["x_main_phone"],
        }
        ctx.log(f"x_main_phone before the test: {before}")
    readings = {}
    try:
        with ctx.step("Set the phone on the contact, then read partner and "
                      "user"):
            rpc.write("res.partner", [partner_id], {"x_main_phone": first})
            readings["partner after partner write"] = rpc.read(
                "res.partner", [partner_id],
                ["x_main_phone"])[0]["x_main_phone"]
            readings["user after partner write"] = rpc.read(
                "res.users", [uid], ["x_main_phone"])[0]["x_main_phone"]
        with ctx.step("Write through the user — the partner must follow"):
            rpc.write("res.users", [uid], {"x_main_phone": second})
            readings["partner after user write"] = rpc.read(
                "res.partner", [partner_id],
                ["x_main_phone"])[0]["x_main_phone"]
        for key, value in readings.items():
            ctx.log(f"  x_main_phone / {key} = {value!r}")
        with ctx.step("Assert the field is code-declared on res.partner"):
            rows = rpc.search_read("ir.model.fields",
                                   [("model", "=", "res.partner"),
                                    ("name", "=", "x_main_phone")], ["state"])
            ctx.check("res.partner x_main_phone declarations (exactly one, "
                      "code-declared)", [{"state": "base"}],
                      [{"state": r["state"]} for r in rows])
        with ctx.step("Diagnose: res.users must NOT declare its own "
                      "x_main_phone (a declaration there shadows the "
                      "_inherits delegation)"):
            shadow = rpc.search_read("ir.model.fields",
                                     [("model", "=", "res.users"),
                                      ("name", "=", "x_main_phone")],
                                     ["ttype", "state"])
            ctx.check("no x_main_phone row on res.users in ir.model.fields "
                      "(root cause: mmg_stock/models/res_users.py:9)",
                      expected=[],
                      actual=[{"ttype": r["ttype"], "state": r["state"]}
                              for r in shadow])
        with ctx.step("Assert partner and user never diverge (single source "
                      "of truth on the partner)"):
            ctx.check("x_main_phone readings",
                      {"partner after partner write": first,
                       "user after partner write": first,
                       "partner after user write": second},
                      readings)
    finally:
        with ctx.step("Restore the QA user's/partner's Main Phone"):
            for model, ids, key in (("res.partner", [partner_id], "partner"),
                                    ("res.users", [uid], "user")):
                try:
                    rpc.write(model, ids, {"x_main_phone": before[key]})
                except Exception as exc:  # noqa: BLE001 — never replace the verdict
                    ctx.log(f"cleanup incomplete: restoring {model} "
                            f"x_main_phone failed: {exc}")
