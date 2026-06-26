import sys
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pwg_intelligence import PWGIntelligenceCard  # noqa: E402
from pwg_intelligence.excel_store import (  # noqa: E402
    DAILY_INTELLIGENCE_COLUMNS,
    REQUIRED_WORKSHEETS,
    build_demo_workbook_payload,
    create_pwg_intelligence_workbook,
)
from pwg_intelligence.models import PWG_MATURITY_LEVELS, PWG_SOURCE_LEVELS  # noqa: E402


MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


def _xml_from_zip(xlsx_path, member):
    with zipfile.ZipFile(xlsx_path) as archive:
        return ET.fromstring(archive.read(member))


def _shared_strings(xlsx_path):
    with zipfile.ZipFile(xlsx_path) as archive:
        if "xl/sharedStrings.xml" not in archive.namelist():
            return []
        root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    values = []
    for item in root.findall(f"{{{MAIN_NS}}}si"):
        texts = [node.text or "" for node in item.findall(f".//{{{MAIN_NS}}}t")]
        values.append("".join(texts))
    return values


def _sheet_paths(xlsx_path):
    workbook = _xml_from_zip(xlsx_path, "xl/workbook.xml")
    rels = _xml_from_zip(xlsx_path, "xl/_rels/workbook.xml.rels")
    rel_targets = {
        rel.attrib["Id"]: rel.attrib["Target"]
        for rel in rels.findall(f"{{{PACKAGE_REL_NS}}}Relationship")
    }
    sheet_paths = {}
    for sheet in workbook.findall(f".//{{{MAIN_NS}}}sheet"):
        name = sheet.attrib["name"]
        rel_id = sheet.attrib[f"{{{REL_NS}}}id"]
        target = rel_targets[rel_id].lstrip("/")
        if not target.startswith("xl/"):
            target = f"xl/{target}"
        sheet_paths[name] = target
    return sheet_paths


def _rows_for_sheet(xlsx_path, sheet_name):
    shared = _shared_strings(xlsx_path)
    sheet_paths = _sheet_paths(xlsx_path)
    root = _xml_from_zip(xlsx_path, sheet_paths[sheet_name])
    rows = []
    for row in root.findall(f".//{{{MAIN_NS}}}sheetData/{{{MAIN_NS}}}row"):
        values = []
        for cell in row.findall(f"{{{MAIN_NS}}}c"):
            cell_type = cell.attrib.get("t")
            if cell_type == "s":
                value_node = cell.find(f"{{{MAIN_NS}}}v")
                value = shared[int(value_node.text)] if value_node is not None and value_node.text is not None else ""
            elif cell_type == "inlineStr":
                value = "".join(node.text or "" for node in cell.findall(f".//{{{MAIN_NS}}}t"))
            else:
                value_node = cell.find(f"{{{MAIN_NS}}}v")
                value = value_node.text if value_node is not None and value_node.text is not None else ""
            values.append(value)
        rows.append(values)
    return rows


def _expect_validation_error(**kwargs):
    try:
        PWGIntelligenceCard(**kwargs)
    except ValidationError:
        return
    raise AssertionError("Expected ValidationError")


def test_pwg_intelligence_card_validates_levels():
    card = PWGIntelligenceCard(
        card_id="DEMO-PWG-001",
        source_level="A",
        maturity_level="M3",
        keywords="DEMO；polymer waveguide",
        key_parameters={"loss": "DEMO"},
    )
    assert card.source_level == "A"
    assert card.maturity_level == "M3"
    assert card.keywords == ["DEMO", "polymer waveguide"]

    _expect_validation_error(card_id="DEMO-PWG-002", source_level="E", maturity_level="M3")
    _expect_validation_error(card_id="DEMO-PWG-003", source_level="A", maturity_level="M8")


def test_demo_payload_has_required_sheets_and_demo_rows():
    payload = build_demo_workbook_payload()
    assert set(payload) == set(REQUIRED_WORKSHEETS)
    for sheet_name, rows in payload.items():
        assert 3 <= len(rows) <= 5, sheet_name
        assert all(row.get("demo_flag") == "DEMO" for row in rows), sheet_name

    daily_rows = payload["daily_intelligence"]
    for row in daily_rows:
        assert row["card_id"].startswith("DEMO-")
        assert row["source_level"] in PWG_SOURCE_LEVELS
        assert row["maturity_level"] in PWG_MATURITY_LEVELS
        assert "DEMO" in row["title"] or "DEMO" in row["factual_summary"]


def test_create_pwg_intelligence_workbook():
    tmpdir = tempfile.TemporaryDirectory()
    output_path = Path(tmpdir.name) / "pwg_intelligence.xlsx"
    created_path = create_pwg_intelligence_workbook(output_path)
    try:
        assert created_path == output_path
        assert output_path.exists()

        sheet_paths = _sheet_paths(output_path)
        assert set(sheet_paths) == set(REQUIRED_WORKSHEETS)

        for sheet_name, columns in REQUIRED_WORKSHEETS.items():
            rows = _rows_for_sheet(output_path, sheet_name)
            assert rows[0] == columns
            assert 3 <= len(rows[1:]) <= 5
            demo_flag_index = rows[0].index("demo_flag")
            assert all(row[demo_flag_index] == "DEMO" for row in rows[1:])

        daily_rows = _rows_for_sheet(output_path, "daily_intelligence")
        assert daily_rows[0] == DAILY_INTELLIGENCE_COLUMNS
        level_index = daily_rows[0].index("source_level")
        maturity_index = daily_rows[0].index("maturity_level")
        for row in daily_rows[1:]:
            assert row[level_index] in PWG_SOURCE_LEVELS
            assert row[maturity_index] in PWG_MATURITY_LEVELS
    finally:
        tmpdir.cleanup()


def run_all():
    tests = [
        test_pwg_intelligence_card_validates_levels,
        test_demo_payload_has_required_sheets_and_demo_rows,
        test_create_pwg_intelligence_workbook,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")


if __name__ == "__main__":
    run_all()
