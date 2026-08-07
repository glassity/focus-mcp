"""The shipped specification YAML must carry what its fields promise.

These are invariants on the extracted artifacts, not the extractor: the
extractor only runs when a maintainer refreshes the spec, but the YAML
ships in every wheel, and a client is told value_format is "Allowed
values" or that an attribute has requirements - so the values and the
requirements have to actually be there.
"""

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SPECS = ROOT / "src" / "focus_mcp" / "resources" / "specifications"

with open(SPECS / "columns.yaml", encoding="utf-8") as f:
    COLUMNS = yaml.safe_load(f)
with open(SPECS / "attributes.yaml", encoding="utf-8") as f:
    ATTRIBUTES = yaml.safe_load(f)


def test_every_entry_declares_its_introduced_version():
    # spec_loader._available_at excludes an entry missing this field from
    # every version-filtered listing - no error, green suite, the column
    # just vanishes. The extractor matches heading spellings the spec has
    # already renamed once, so a re-extraction is exactly where one could
    # silently go missing.
    missing = [
        entry.get("column_id") or entry.get("attribute_id")
        for entry in [*COLUMNS, *ATTRIBUTES]
        if not entry.get("introduced_version")
    ]
    assert missing == [], (
        "entries that would vanish from every version listing: "
        + ", ".join(missing)
    )


def test_declared_allowed_values_are_actually_listed():
    # "Value format: Allowed values" with no values is a promise the
    # client cannot cash - it would have to guess or query the data.
    missing = [
        c["column_id"] for c in COLUMNS
        if c.get("value_format") == "Allowed values"
        and not c.get("allowed_values")
    ]
    assert missing == [], (
        "columns declaring 'Allowed values' without listing them: "
        + ", ".join(missing)
    )


def test_allowed_values_entries_are_complete():
    broken = [
        f"{c['column_id']}: {entry!r}"
        for c in COLUMNS
        for entry in c.get("allowed_values", [])
        if not (entry.get("value") and entry.get("description"))
    ]
    assert broken == [], "allowed_values entries missing value or description:\n  " + "\n  ".join(broken)


def test_charge_category_carries_the_canonical_values():
    charge_category = next(c for c in COLUMNS if c["column_id"] == "ChargeCategory")
    values = {v["value"] for v in charge_category["allowed_values"]}
    assert values == {"Usage", "Purchase", "Tax", "Credit", "Adjustment"}


def test_every_attribute_has_requirements():
    empty = [a["attribute_id"] for a in ATTRIBUTES if not a.get("requirements")]
    assert empty == [], "attributes with no requirements: " + ", ".join(empty)


def test_no_requirement_is_a_dangling_intro():
    # "X MUST adhere to the following requirements:" with nothing
    # following is how a MULTILINE regex once truncated every section to
    # its first line. An item may end with a colon only if its
    # sub-requirements come with it.
    stubs = [
        f"{a['attribute_id']}: {item!r}"
        for a in ATTRIBUTES
        for item in a.get("requirements", [])
        if item.rstrip().endswith(":") and "\n" not in item
    ]
    assert stubs == [], (
        "requirement items that introduce a list that is not there:\n  "
        + "\n  ".join(stubs)
    )


def test_no_internal_spec_anchors_leak_into_text():
    # "[*charge*](#glossary:charge)" only resolves inside the rendered
    # specification document; served over MCP it is noise.
    def texts():
        for c in COLUMNS:
            yield c["column_id"], c.get("description", "")
            for entry in c.get("allowed_values", []):
                yield c["column_id"], entry.get("description", "")
        for a in ATTRIBUTES:
            yield a["attribute_id"], a.get("description", "")
            for item in a.get("requirements", []):
                yield a["attribute_id"], item

    leaks = [f"{owner}: ...{text[max(0, text.find('](#') - 40):text.find('](#') + 20]}..."
             for owner, text in texts() if "](#" in text]
    assert leaks == [], "internal markdown anchors in served text:\n  " + "\n  ".join(leaks)


def test_requirement_parser_handles_every_shape_the_spec_uses():
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        from focus_spec_markdown_extractor import requirement_items
    finally:
        sys.path.pop(0)

    body = (
        "Column conforming MUST adhere to the following requirements:\n"
        "\n"
        "* First requirement with a [link](#glossary:thing).\n"
        "* Parent requirement introducing sub-items:\n"
        "  * Nested child one.\n"
        "  * Nested child two.\n"
        "\n"
        "Prose paragraph that is a requirement in its own right.\n"
    )
    items = requirement_items(body)
    assert items == [
        "First requirement with a link.",
        "Parent requirement introducing sub-items:\n- Nested child one.\n- Nested child two.",
        "Prose paragraph that is a requirement in its own right.",
    ]

    # A list may sit indented under its prose intro; top-level is the
    # list's own baseline, not column zero, or the bullets would nest
    # under each other and the intro survive out of order.
    indented = (
        "The values MUST follow these rules:\n"
        "  * Rule one.\n"
        "  * Rule two.\n"
    )
    assert requirement_items(indented) == ["Rule one.", "Rule two."]
