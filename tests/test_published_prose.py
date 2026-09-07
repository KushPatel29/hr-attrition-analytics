"""
Every number the README states in prose must still be the number the engines
produce, formatted the way a reader sees it.

`test_global_workforce.py` pins the published FIGURES, so changing the analysis
fails the build. What nothing pinned was the other direction - the prose. A
figure can move, the assertion can be updated, and the README can go on quoting
last month's run with a green build the whole way.

Each assertion below reads the value from the engine output and looks for it in
the README **as formatted**: thousands separators, bold markers, percent
precision and all. When a figure legitimately changes, this fails and names the
document that needs editing. That is the intended cost.
"""
import csv
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
OUT = ROOT / "output"


def one_row(name):
    with open(OUT / f"{name}.csv", encoding="utf-8") as f:
        return next(csv.DictReader(f))


def rows(name):
    with open(OUT / f"{name}.csv", encoding="utf-8") as f:
        return list(csv.DictReader(f))


@pytest.fixture(scope="module")
def prose():
    # Prose wraps; a figure that lands either side of a line break is still
    # quoted, so match on the flattened text.
    return " ".join(README.read_text(encoding="utf-8").split())


@pytest.fixture(scope="module")
def geo():
    return one_row("geo_headline")


@pytest.fixture(scope="module")
def exits():
    return one_row("attrition_headline")


def quoted(prose, needle):
    return " ".join(needle.split()) in prose


def every_mention(prose, pattern, expected, what):
    """A figure quoted in two places has to be right in both.

    Checking that the correct value appears somewhere is not enough: the intro,
    the headline table and the section body all quote the same numbers, and
    updating one of the three is exactly how a README goes stale while still
    containing the right answer.
    """
    found = set(re.findall(pattern, prose))
    assert found, f"no mention of {what} at all - has the wording changed?"
    assert found == {expected}, (
        f"{what} is quoted as {sorted(found)}; it should be {expected} everywhere")


def test_the_readme_is_the_real_one(prose):
    """Guards against every assertion below passing on a stub file."""
    assert len(prose) > 10_000
    assert "Three questions a single-country dashboard cannot frame" in prose


def test_the_geography_headlines_are_quoted_as_published(geo, prose):
    assert quoted(prose, f"**{int(geo['countries'])} countries**")
    assert quoted(prose, f"**{geo['largest_market']}**")
    assert quoted(prose, f"**{float(geo['largest_market_payroll_share']):.0%}** of the payroll")
    assert quoted(prose, f"**{geo['worst_market']}** — {float(geo['worst_market_rate']):.1%}")
    assert quoted(prose, f"**{float(geo['worst_market_headcount_share']):.0%}** of the workforce")
    assert quoted(prose, f"**{float(geo['attrition_spread']) * 100:.1f} points**")
    assert quoted(prose, f"**{float(geo['pay_market_multiple']):.1f}x**"
                  ) or quoted(prose, f"{float(geo['pay_market_multiple']):.1f}x range")


def test_the_exit_headlines_are_quoted_as_published(exits, prose):
    e = exits
    assert quoted(prose, f"**{int(e['active_headcount']):,}**")
    assert quoted(prose, f"**{int(e['regretted_exits'])}**")
    assert quoted(prose, f"**${float(e['regretted_salary']) / 1e6:.1f}M**")
    assert quoted(prose, f"**{float(e['first_year_share']) * 100:.0f}% of every exit**")
    assert quoted(prose, f"{float(e['regretted_share']) * 100:.0f}% of all exits")


def test_the_pay_gap_table_matches_the_sql(prose):
    """The README tabulates four gaps before and after holding market constant.
    Both columns come from the same file; quoting one stale is the easiest way
    to make the point look stronger than it is."""
    pe = {r["job_level"]: r for r in rows("pay_equity")}
    lv = {r["job_level"]: r for r in rows("pay_equity_levels")}

    company_level = float(pe["ALL (level-adjusted)"]["raw_gap_pct"])
    company_market = float(pe["ALL (level + market-adjusted)"]["raw_gap_pct"])
    assert quoted(prose, f"| Company | {company_level:.1%} | **{company_market:.1%}** |")

    for level in ("Senior Manager", "Senior Analyst", "Lead"):
        raw = float(lv[level]["raw_gap_pct"])
        market = float(lv[level]["market_adjusted_gap_pct"])
        shown_raw = f"{raw:.1%}".replace("-", "−")
        assert quoted(prose, f"| {level} | {shown_raw} | {market:.1%} |"), \
            f"the {level} row no longer matches pay_equity_levels.csv"


def test_the_org_design_figures_are_quoted_as_published(prose):
    span = rows("span_of_control")
    layers = rows("org_layers")
    outliers = rows("manager_outliers")
    thin = sum(1 for r in span if r["span_band"] == "1. Thin (<4)") / len(span)
    above = sum(1 for r in outliers if r["verdict"] == "Well above market")

    assert quoted(prose, f"**{max(int(r['layer']) for r in layers)} layers**")
    assert quoted(prose, f"{len(span)} managers")
    assert quoted(prose, f"**{thin:.0%} of them managing fewer than four people**")
    # Quoted in the headline table as well as in the section body.
    every_mention(prose, r"\*\*(\d+)%\*\* managing fewer", f"{thin * 100:.0f}",
                  "the thin-span share")
    every_mention(prose, r"\*\*(\d+) layers\*\*",
                  str(max(int(r["layer"]) for r in layers)), "the layer count")
    assert quoted(prose, f"**{above} of the {len(outliers)} teams**"
                  ) or quoted(prose, f"**{above} of {len(outliers)}** teams")


def test_the_claim_the_split_exists_for_still_holds(prose):
    """The README argues most of a level's gap is geography. If the adjusted
    column ever stopped compressing the spread, the argument would be wrong
    while every individual number stayed correct."""
    lv = rows("pay_equity_levels")
    raw = [float(r["raw_gap_pct"]) for r in lv]
    market = [float(r["market_adjusted_gap_pct"]) for r in lv]
    assert (max(market) - min(market)) < (max(raw) - min(raw)) / 3
    assert quoted(prose, "of which most is the exchange rate")


def test_the_badge_and_page_count_are_real():
    text = README.read_text(encoding="utf-8")
    badge = re.search(r"tests-(\d+)%20passing", text)
    assert badge, "README no longer carries a test-count badge"
    defined = sum(len(re.findall(r"^def test_", p.read_text(encoding="utf-8"), re.M))
                  for p in (ROOT / "tests").glob("*.py"))
    assert int(badge.group(1)) >= defined

    pages = len(list((ROOT / "powerbi" / "pbip").glob(
        "*.Report/definition/pages/*/page.json")))
    flat = " ".join(text.split())
    assert f"{pages}-page" in flat or f"{pages} pages" in flat, \
        f"the report has {pages} pages; the README does not say so"
    # And nowhere says a different number. The intro, the dashboard section and
    # the visual count all name it; updating one of the three is how a document
    # ends up containing both the right answer and the wrong one.
    every_mention(flat, r"(\d+)-page (?:interactive )?Power BI", str(pages),
                  "the page count")
    every_mention(flat, r"visuals across (\d+) pages", str(pages),
                  "the page count beside the visual count")
