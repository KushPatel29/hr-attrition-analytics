"""
Power BI project integrity: guarantees the hand-authored PBIR report and TMDL
model stay in sync, so the .pbip always opens and every visual binds to a real
field. This is the kind of check that catches a renamed measure before Power
BI Desktop throws a broken-visual error.
"""
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PBIP = ROOT / "powerbi" / "pbip"
SM = PBIP / "HRAttritionAnalytics.SemanticModel"
RPT = PBIP / "HRAttritionAnalytics.Report"


@pytest.fixture(scope="module")
def model():
    """Parse TMDL into {table: set(columns)} and set(measures)."""
    cols, measures = {}, set()
    for f in (SM / "definition" / "tables").glob("*.tmdl"):
        txt = f.read_text(encoding="utf-8")
        tname = re.search(r"^table (\S+)", txt, re.M).group(1)
        cols.setdefault(tname, set())
        for mo in re.finditer(r"^\tcolumn ([^\s=]+)", txt, re.M):
            cols[tname].add(mo.group(1))
        for mo in re.finditer(r"^\tmeasure '([^']+)'", txt, re.M):
            measures.add(mo.group(1))
    return cols, measures


def _visual_files():
    return list((RPT / "definition" / "pages").glob("**/visual.json"))


def test_pbip_and_core_files_exist():
    assert (PBIP / "HRAttritionAnalytics.pbip").exists()
    assert (RPT / "definition" / "report.json").exists()
    assert (SM / "definition" / "model.tmdl").exists()
    assert (RPT / "StaticResources" / "RegisteredResources" / "MeridianTheme.json").exists()


def test_every_visual_field_resolves(model):
    cols, measures = model
    unresolved = []
    for vf in _visual_files():
        v = json.loads(vf.read_text(encoding="utf-8"))
        qs = v["visual"].get("query", {}).get("queryState", {})
        for role, body in qs.items():
            for proj in body["projections"]:
                fld = proj["field"]
                if "Measure" in fld:
                    if fld["Measure"]["Property"] not in measures:
                        unresolved.append((vf.parent.name, "measure", fld["Measure"]["Property"]))
                else:
                    ent = fld["Column"]["Expression"]["SourceRef"]["Entity"]
                    prop = fld["Column"]["Property"]
                    if prop not in cols.get(ent, set()):
                        unresolved.append((vf.parent.name, "column", f"{ent}.{prop}"))
    assert not unresolved, f"unresolved field references: {unresolved}"


def test_page_order_matches_page_dirs():
    pages_meta = json.loads((RPT / "definition" / "pages" / "pages.json").read_text(encoding="utf-8"))
    declared = set(pages_meta["pageOrder"])
    on_disk = {p.name for p in (RPT / "definition" / "pages").iterdir() if p.is_dir()}
    assert declared == on_disk
    assert pages_meta["activePageName"] in declared


def test_relationships_reference_real_columns(model):
    cols, _ = model
    rel_txt = (SM / "definition" / "relationships.tmdl").read_text(encoding="utf-8")
    refs = re.findall(r"(?:from|to)Column: (\S+)\.(\S+)", rel_txt)
    assert refs, "no relationships found"
    for table, col in refs:
        assert col in cols.get(table, set()), f"relationship references missing {table}.{col}"


def test_datapath_expression_present():
    expr = (SM / "definition" / "expressions.tmdl").read_text(encoding="utf-8")
    assert "DataPath" in expr and "IsParameterQuery=true" in expr


def test_no_midline_carriage_returns():
    """CRLF line endings are fine; a lone CR mid-line corrupts TMDL parsing."""
    for f in (SM / "definition").glob("**/*.tmdl"):
        b = f.read_bytes()
        lone = sum(1 for i, ch in enumerate(b)
                   if ch == 13 and (i + 1 >= len(b) or b[i + 1] != 10))
        assert lone == 0, f"{f.name} has {lone} mid-line CR(s)"
