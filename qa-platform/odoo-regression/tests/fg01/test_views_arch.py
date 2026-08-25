"""FG-01 — form/list field availability: TC-ART-002, TC-ART-023.

Expected v15 outcomes: both FAIL, and both are documented baselines —
TC-ART-002 on the 47 x_image fields that only become code fields on the v19
Images page, TC-ART-023 because a DB-resident Studio view at priority 640
applies last and drops the barcode/Tile column from the served list arch. In
both tests every assertion that is green on v15 runs (and is recorded)
*before* the documented FAIL, so a real regression surfaces on its own
instead of being masked.

Partial automation of two UI/tour cases: the deterministic core (every
field present in the served view architecture, list column set/order,
multi-edit, default order) is asserted via the view arch the web client
actually receives; a real-browser screenshot of the rendered page is
attached as evidence — through ``screenshot_evidence()``, which never
raises, so a browser problem cannot turn either documented FAIL into an
ERROR. The residual manual step is pixel-level "renders and is editable"
verification, tracked in the FG-01 report.

Arch-inspection rules used by both tests (a served arch is not the same
document as the source XML):

* **presence** and **visibility** are two different questions and are
  asserted separately. A field that is in the arch but hidden is a hidden
  column, not a missing column — collapsing the two produced the false
  "missing: ['barcode']" that TC-ART-023 reported (see below).
* invisibility is read version-agnostically. On v15 ``fields_view_get``
  post-processing moves a tree view's ``invisible="1"`` into the generated
  ``modifiers`` JSON as ``{"column_invisible": true}``; v17+ keeps
  ``invisible`` / ``column_invisible`` as plain attributes.
  ``_static_invisible()`` reads both.
* ``optional="hide"`` is recorded as evidence, never as absence: an
  optional column is present in the arch and toggleable by the user, so it
  is neither missing nor invisible.
"""
import json
import xml.etree.ElementTree as ET

from framework.registry import test_case
from tests.fg01.common import (form_arch, list_url, record_url,
                               screenshot_evidence, trace, view_arch)

# TC-ART-002 splits the v15 baseline field list into its two provenance
# groups, because they carry two different expectations on the v15 clone.
#
# (1) code-declared in mmg_stock (models/product.py, models/magento_product.py)
#     and placed by code-owned views (views/product_template_views.xml).
#     Source-verified: all 32 have both a `= fields.X(...)` declaration and a
#     <field> placement inside psus-medicine-man-gallery. These must be in the
#     served arch on v15 AND on v19 — this group is the regression detector.
FORM_FIELDS_TEMPLATE_CODE = [
    # main + product info tab
    "image_1920_download", "x_gallery_cost", "x_cfp_category", "x_cfp_sub",
    "x_vendor", "x_consignment_percentage", "x_discount", "color_id",
    "origin_id", "x_artist", "x_medium", "x_height", "x_width", "x_depth",
    "x_jewelry_size", "x_ed_num", "x_ed_size", "x_date",
    "x_product_shipping", "e_blast_date",
    # auction info tab
    "product_lot_number", "product_starting_bid", "product_reserve",
    "product_low_estimate", "product_hihg_estimate", "product_buy_now_price",
    "product_condition", "product_product_category_id",
    "product_product_origin_id", "product_product_style_id",
    "product_auction_date", "product_auction_provenance",
]

# (2) Studio/DB-only on v15, formalized as code fields on the new code-owned
#     Images page in v19 (workbook decision #2, TC-ART-002 precondition
#     "views/product_images_views.xml loaded"). Source-verified: x_image_1..47
#     have NO field declaration and NO code-owned view placement anywhere in
#     psus-medicine-man-gallery on v15 (grep "x_image" over *.py/*.xml returns
#     only unrelated multichannel_shopify helpers), and mmg_stock/views/ has no
#     product_images_views.xml. The workbook expectation describes the v19
#     target state, so this check is the documented v15 baseline FAIL and
#     classifies as FIXED when v19 loads the Images page.
FORM_FIELDS_TEMPLATE_V19 = [f"x_image_{i}" for i in range(1, 48)]

# the union is exactly the workbook's v15 baseline tick-off list (steps 4-6)
FORM_FIELDS_TEMPLATE = FORM_FIELDS_TEMPLATE_CODE + FORM_FIELDS_TEMPLATE_V19

# TC-ART-002 step 7, split the same way as the template list: the v19 port
# formalizes the Studio variant fields (decision #2) and adds the code-owned
# placement, so on v15 they legitimately have no code-declared arch entry.
# Keeping them in one bucket let their expected v15 absence mask a genuine
# regression in the fields that ARE code-placed on v15.
FORM_FIELDS_VARIANT_CODE = ["x_studio_shipping"]
FORM_FIELDS_VARIANT_V19 = ["x_desc", "x_length", "x_image",
                           "website_extra_categories"]
FORM_FIELDS_VARIANT = FORM_FIELDS_VARIANT_CODE + FORM_FIELDS_VARIANT_V19

# TC-ART-023 step 2: the v15 business column set, in order. The image
# thumbnail (image_1920 avatar) is excluded because it may or may not be a
# <field> node across versions — the business columns are asserted in
# relative order instead of exact equality. The workbook declares all of
# these default-visible, so the same list drives the presence check and the
# visibility check; the split is what keeps a hidden column from being
# reported as a missing one.
LIST_COLUMNS = ["default_code", "name", "e_blast_date", "list_price",
                "standard_price", "barcode", "qty_available",
                "virtual_available"]


def _arch_fields(arch: str) -> dict:
    """name → attributes for every <field> in a view arch."""
    root = ET.fromstring(arch)
    return {n.get("name"): n.attrib for n in root.iter("field")}


def _arch_field_nodes(root) -> list:
    """(name, attributes) for every <field> node, in document order."""
    return [(n.get("name"), dict(n.attrib)) for n in root.iter("field")]


def _static_invisible(attrs: dict) -> bool:
    """True when the client never renders this field, read version-agnostically.

    v15 `fields_view_get` moves a tree view's invisible="1" into the generated
    `modifiers` JSON as {"column_invisible": true}; v17+ keeps `invisible` /
    `column_invisible` as plain attributes. A *conditional* value (a domain
    list on v15, a python expression on v19) is not a static hide — it is
    logged as evidence, not asserted on.

    `optional` is deliberately NOT consulted: an optional column is present
    in the arch and user-toggleable, so it is neither absent nor invisible.
    """
    for attr in ("invisible", "column_invisible"):
        raw = (attrs.get(attr) or "").strip()
        if raw.lower() in ("1", "true"):
            return True
    try:
        modifiers = json.loads(attrs.get("modifiers") or "{}")
    except (ValueError, TypeError):
        modifiers = {}
    if not isinstance(modifiers, dict):
        return False
    return any(modifiers.get(key) is True
               for key in ("invisible", "column_invisible"))


def _attr_summary(attrs: dict) -> str:
    if not attrs:
        return "(no attributes)"
    return ", ".join(f"{k}={v!r}" for k, v in sorted(attrs.items()))


@test_case(
    id="TEST-FG01-ART-002", name="All ~35 art fields are visible and editable after upgrade",
    workflow="FG-01", workflow_name="Art Catalogue", module="mmg_stock",
    priority="P0", kind="HYBRID", order=160,
    description="Every field on the v15 baseline list is present in the "
                "served product form arch (template + variant) — plus a "
                "rendered-form screenshot. The template list is checked in "
                "two groups (code-declared mmg_stock fields vs the 47 "
                "x_image fields formalized in v19) so the v19-only group "
                "cannot mask a regression in the code-owned fields. "
                "Pixel-level editability tick-off remains a manual residual.",
    traceability=trace("TC-ART-002"))
def test_art_002(ctx):
    """EXPECTED v15 OUTCOME: FAIL, on the two v19-formalized groups only —
    documented baseline. x_image_1..47 (template) and
    x_desc/x_length/x_image/website_extra_categories (variant) are
    Studio/DB-only on v15 with no code declaration and no code-owned view
    placement, and only become code fields on the v19 Images page
    (workbook decision #2). Every code-declared group is expected GREEN on
    v15 and is asserted first.

    Workbook steps 3-7, split by field provenance — same expectation, same
    union of fields, no assertion weakened.

    Why the split: the workbook's single tick-off list mixes two provenances
    with two different v15 outcomes.

    * `FORM_FIELDS_TEMPLATE_CODE` (32 fields) is declared and placed by
      mmg_stock code, so it must be in the served arch on v15 too. This is
      the real regression detector and is expected GREEN on v15.
    * `FORM_FIELDS_TEMPLATE_V19` (x_image_1..47) is Studio/DB-only on v15 —
      no declaration, no code-owned placement — and only becomes a code
      field on the v19 Images page (decision #2). Expected FAIL on v15;
      classifies as FIXED once v19 loads views/product_images_views.xml.

    As one combined check, the 47 guaranteed x_image failures aborted the
    test before the 32 code fields, the barcode label, the variant fields and
    the screenshot evidence were ever evaluated — a regression in the
    code-owned fields was invisible. The v19-only group is therefore asserted
    last, after every green-on-v15 assertion and after the evidence step,
    so a real regression surfaces on its own.
    """
    rpc = ctx.adapter.rpc
    with ctx.step("Fetch the served product.template form arch"):
        arch = form_arch(ctx, "product.template")
        tmpl_fields = _arch_fields(arch)
        ctx.log(f"{len(tmpl_fields)} distinct fields in the template form arch")
    with ctx.step("Assert every code-declared mmg_stock template field is in "
                  "the arch (regression detector)"):
        missing = [f for f in FORM_FIELDS_TEMPLATE_CODE
                   if f not in tmpl_fields]
        ctx.check("missing code-declared template form fields (must be empty)",
                  [], missing)
    with ctx.step("Assert the barcode field is labelled 'Tile'"):
        label = tmpl_fields.get("barcode", {}).get("string", "")
        if not label:
            info = rpc.call("product.template", "fields_get", ["barcode"],
                            attributes=["string"])
            label = info.get("barcode", {}).get("string", "")
        ctx.check("barcode label", "Tile", label)
    with ctx.step("Fetch the variant form arch and assert the code-placed "
                  "variant fields (regression detector)"):
        var_arch = form_arch(ctx, "product.product")
        var_fields = _arch_fields(var_arch)
        missing_code = [f for f in FORM_FIELDS_VARIANT_CODE
                        if f not in var_fields]
        ctx.check("missing code-placed variant fields (must be empty)",
                  [], missing_code)
    with ctx.step("Screenshot a populated live art item (evidence)"):
        populated = rpc.search("product.template",
                               [("x_artist", "!=", False),
                                ("x_medium", "!=", False)], limit=1)
        if populated:
            screenshot_evidence(ctx, "art-item-form",
                                record_url(ctx, "product.template",
                                           populated[0]))
        else:
            ctx.log("no populated art item found for the screenshot")
    with ctx.step("Assert the fields formalized in v19 are in the served "
                  "arch: the 47 x_image Images-page fields (workbook step 6) "
                  "and the four variant fields (step 7) — decision #2, "
                  "documented v15 baseline FAIL"):
        # both v19-formalized groups are asserted together, in ONE collected
        # assertion at the very end: they are guaranteed to fail on v15, and
        # asserting them separately/earlier aborted the test before the
        # code-owned groups, the barcode label and the screenshot evidence
        # were ever evaluated — a real regression was invisible.
        missing = {
            "product.template x_image_1..47": [f for f in
                                               FORM_FIELDS_TEMPLATE_V19
                                               if f not in tmpl_fields],
            "product.product v19-formalized": [f for f in
                                               FORM_FIELDS_VARIANT_V19
                                               if f not in var_fields],
        }
        ctx.log(f"{len(FORM_FIELDS_TEMPLATE_V19) - len(missing['product.template x_image_1..47'])}/"
                f"{len(FORM_FIELDS_TEMPLATE_V19)} x_image fields present in "
                f"the served arch")
        ctx.check("fields formalized in v19 missing from the served arch "
                  "(both lists must be empty)",
                  {"product.template x_image_1..47": [],
                   "product.product v19-formalized": []},
                  missing)


@test_case(
    id="TEST-FG01-ART-023", name="Product list view custom columns intact",
    workflow="FG-01", workflow_name="Art Catalogue", module="mmg_stock",
    priority="P2", kind="HYBRID", order=161,
    description="The replaced product list arch reproduces the v15 column "
                "set/order, hides categ_id, keeps default_order and "
                "multi-edit — plus a rendered-list screenshot. Column "
                "presence and column visibility are asserted separately.",
    traceability=trace("TC-ART-023"))
def test_art_023(ctx):
    """EXPECTED v15 OUTCOME: FAIL on the column-presence assertion —
    documented baseline. The served arch is the result of every inheriting
    view applied in priority order, and this clone carries a DB-resident
    ``studio_customization`` view at priority 640 that applies last and drops
    the barcode/Tile column; mmg_stock's own code-owned arch declares it
    (views/product_template_views.xml). The presence assertion is therefore
    asserted LAST, after the order, visibility, categ_id, default_order,
    multi_edit and screenshot evidence, so those facts are recorded instead of
    being aborted — and the provenance diagnostic step names the view that
    causes the FAIL.

    Workbook steps 2-5 against the served list arch.

    Automation-defect fix: the previous implementation built a single
    "visible" list by dropping every <field> node that carried
    `optional` / `invisible` / `column_invisible`, then reported the dropped
    names as *missing columns*. That conflation produced
    `missing list columns: expected [], got ['barcode']` on the v15 clone —
    an automation artefact, not a product finding: barcode IS declared in the
    code-owned arch (mmg_stock/views/product_template_views.xml, the
    priority-64 full-arch replace of product.product_template_tree_view) as
    `<field name="barcode" readonly="1"/>` — readonly only, with no
    invisible / optional / column_invisible attribute — and no other addon in
    psus-medicine-man-gallery touches that node. So "missing" could not come
    from the product code; the node was present and filtered.

    The arch is now inspected properly: all <field> nodes are gathered with
    their attributes and their document order, then asserted as three
    independent facts — present / in relative v15 order / not statically
    invisible — plus categ_id absent-or-invisible, default_order and
    multi_edit. Every column's full attribute set is logged so the served
    arch itself is the evidence for which attribute the old filter tripped
    on. No expectation changed.

    The order assertion covers the columns that ARE in the arch: presence is
    a separate, still-asserted fact, so a column dropped by an inheriting
    view is reported exactly once (as absent) instead of failing both checks
    and hiding whether the surviving columns kept the v15 sequence.
    """
    rpc = ctx.adapter.rpc
    with ctx.step("Fetch the served product.template list arch (the "
                  "replaced core tree view, as the product actions use it)"):
        view_id = rpc.ref("product.product_template_tree_view")
        arch = view_arch(ctx, "product.template", view_type="tree",
                         view_id=view_id)
        root = ET.fromstring(arch)
        nodes = _arch_field_nodes(root)
        # first occurrence wins — a column is declared once in this arch
        attrs_by_name = {}
        for name, attrs in nodes:
            attrs_by_name.setdefault(name, attrs)
        ctx.log(f"{len(nodes)} <field> nodes in the arch: "
                f"{[name for name, _ in nodes]}")
        ctx.log("attributes of the expected v15 columns (arch evidence):")
        for name in LIST_COLUMNS:
            attrs = attrs_by_name.get(name)
            if attrs is None:
                ctx.log(f"  {name}: NOT IN ARCH")
            else:
                ctx.log(f"  {name}: {_attr_summary(attrs)}")
    with ctx.step("Record who shapes this arch (inheriting views, by "
                  "priority) so an absent column names its own cause"):
        # The served arch is the result of every inheriting view, applied in
        # priority order — including views that live only in the database.
        # Measured on this clone: a `studio_customization` view at priority
        # 640 applies last, which is why barcode/Tile is absent from the
        # served arch even though mmg_stock's own arch declares it.
        inheriting = rpc.search_read(
            "ir.ui.view",
            ["|", ("inherit_id", "=", view_id), ("id", "=", view_id)],
            ["name", "priority", "mode"], order="priority,id")
        studio = []
        for view in inheriting:
            data = rpc.search_read(
                "ir.model.data",
                [("model", "=", "ir.ui.view"), ("res_id", "=", view["id"])],
                ["module"], limit=1)
            module = data[0]["module"] if data else ""
            if not module or module == "studio_customization":
                studio.append(view["name"])
                module = module or "<no module: DB-only>"
            ctx.log(f"  prio {view['priority']:>4} {module:<22} "
                    f"{view['name']} ({view['mode']})")
        ctx.log(f"{len(studio)} of {len(inheriting)} contributing views are "
                f"Studio/DB-resident and apply last by priority: {studio} — "
                "those do not migrate the way code-owned views do")
    with ctx.step("Assert the v15 columns present in the arch keep their "
                  "relative order"):
        ordered = []
        for name, _ in nodes:
            if name in LIST_COLUMNS and name not in ordered:
                ordered.append(name)
        ctx.check("relative order of the v15 columns present in the arch",
                  [f for f in LIST_COLUMNS if f in attrs_by_name], ordered)
    with ctx.step("Assert no v15 column is hidden (invisible / "
                  "column_invisible)"):
        hidden = [f for f in LIST_COLUMNS
                  if _static_invisible(attrs_by_name.get(f, {}))]
        ctx.check("v15 columns hidden by invisible/column_invisible "
                  "(must be empty)", [], hidden)
        optional = {f: (attrs_by_name.get(f, {}).get("optional") or "").strip()
                    for f in LIST_COLUMNS}
        toggleable = {f: v for f, v in optional.items() if v}
        ctx.log(f"optional attribute per column (evidence, not asserted — an "
                f"optional column is present and user-toggleable): "
                f"{toggleable or 'none set'}")
    with ctx.step("Assert categ_id absent or invisible"):
        categ = [attrs for name, attrs in nodes if name == "categ_id"]
        hidden = (not categ) or all(_static_invisible(a) for a in categ)
        ctx.check_true("categ_id absent or invisible", hidden,
                       actual_desc=f"nodes={len(categ)} "
                                   f"attrs={[_attr_summary(a) for a in categ]}")
    with ctx.step("Assert default order and multi-edit"):
        list_node = root if root.tag in ("tree", "list") else (
            next(root.iter("tree"), None) or next(root.iter("list"), None))
        list_attrs = dict(list_node.attrib) if list_node is not None else {}
        ctx.check("list attributes (default_order, multi_edit)",
                  {"default_order": "default_code", "multi_edit": "1"},
                  {"default_order":
                       (list_attrs.get("default_order") or "").strip(),
                   "multi_edit": list_attrs.get("multi_edit") or ""})
    with ctx.step("Screenshot the rendered product list (evidence)"):
        screenshot_evidence(ctx, "product-list-view",
                            list_url(ctx, "product.template",
                                     v19_path="/odoo/inventory"))
    with ctx.step("Assert every v15 column is present in the arch "
                  "(presence only — visibility was checked separately; "
                  "documented v15 baseline FAIL: the priority-640 Studio "
                  "view drops barcode/Tile)"):
        absent = [f for f in LIST_COLUMNS if f not in attrs_by_name]
        ctx.check("v15 columns absent from the arch (must be empty)",
                  [], absent)
