"""
Invariants for the multinational workforce layer.

The failures to guard against here are the ones that still render: an org
chart with a cycle in it, an exit classification that double-counts, a pay gap
that is really a currency conversion, and a "manager effect" that is nothing
but small-team noise.
"""
import numpy as np
import pandas as pd
import pytest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = ROOT / "output"


def _read(name, folder=OUT):
    # keep_default_na=False: manager_id is blank for the top of the house, and
    # letting pandas turn that into NaN silently makes it a float column where
    # every "no manager" row compares unequal to "".
    return pd.read_csv(folder / f"{name}.csv", keep_default_na=False, na_values=[])


@pytest.fixture(scope="module")
def emp():
    return _read("fact_employees", DATA)


@pytest.fixture(scope="module")
def jobs():
    return _read("dim_job", DATA)


# --- the org chart --------------------------------------------------------

def test_the_reporting_graph_has_no_cycles(emp):
    """A cycle makes every "how many layers" answer the loop guard rather than
    the org. Walked explicitly rather than trusting the recursive CTE that
    consumes it - the guard would hide the cycle in both."""
    mgr = {int(r.employee_id): (int(r.manager_id) if str(r.manager_id) != "" else None)
           for r in emp.itertuples()}
    for start in mgr:
        seen, node, hops = {start}, mgr[start], 0
        while node is not None:
            assert node not in seen, f"cycle in the reporting chain at {node}"
            assert hops < 20, "chain longer than any plausible org"
            seen.add(node)
            node, hops = mgr.get(node), hops + 1


def test_a_manager_always_outranks_their_report(emp, jobs):
    """Acyclicity is a consequence of this rule, not a coincidence. If a peer
    can manage a peer, two of them can manage each other."""
    rank = jobs.set_index("job_id").level_rank.to_dict()
    joined = emp[emp.manager_id != ""].copy()
    joined["mine"] = joined.job_id.map(rank)
    joined["theirs"] = joined.manager_id.astype(int).map(
        emp.set_index("employee_id").job_id.map(rank).to_dict())
    assert (joined.theirs > joined.mine).all(), \
        "a manager sits at or below their report's level"


def test_org_layers_account_for_every_active_employee():
    """The top of the house has no manager row to join to, which is exactly how
    a headcount reconciliation loses its executives."""
    layers = _read("org_layers")
    emp = _read("fact_employees", DATA)
    assert layers.employees.sum() == int((emp.is_active == 1).sum())
    assert layers.layer.min() == 1
    assert layers.share_of_headcount.sum() == pytest.approx(1.0, abs=0.001)


def test_the_org_is_flatter_at_the_top_than_at_the_bottom():
    layers = _read("org_layers").sort_values("layer")
    assert layers.employees.iloc[-1] > layers.employees.iloc[0] * 5, \
        "a pyramid this flat is not a pyramid"
    assert layers.avg_salary.is_monotonic_decreasing, \
        "salary should fall as you go down the layers"


def test_span_of_control_covers_everyone_who_has_a_manager():
    span = _read("span_of_control")
    emp = _read("fact_employees", DATA)
    assert span.reports_total.sum() == int((emp.manager_id != "").sum())
    assert set(span.span_band) <= {"1. Thin (<4)", "2. Healthy (4-10)", "3. Wide (>10)"}


# --- the manager effect ---------------------------------------------------

def test_attrition_really_does_cluster_by_manager(emp, jobs):
    """The page claims teams differ by MANAGER. Held to a permutation test.

    The shuffle has to hold fixed everything else a team shares, or the test
    passes with the manager effect switched off entirely - which is exactly
    what it did twice while being written:

      * geography. Managers are recruited locally, so a team sits almost
        entirely in one market, and markets here churn between 12% and 29%.
      * seniority. A manager's reports sit below them, so a Director's team is
        managers and a Manager's team is juniors - and tenure, which tracks
        level, is the model's strongest attrition driver.

    Permuting inside (country x level) cells holds both fixed. What is left
    that still clusters by team is the manager.
    """
    loc = pd.read_csv(DATA / "dim_location.csv")
    rank = jobs.set_index("job_id").level_rank.to_dict()
    teams = emp[emp.manager_id != ""].merge(loc[["location_id", "country"]],
                                            on="location_id")
    teams["rank"] = teams.job_id.map(rank)
    sizes = teams.groupby("manager_id").size()
    big = sizes[sizes >= 8].index
    teams = teams[teams.manager_id.isin(big)]
    assert len(big) >= 50, "too few sizeable teams for this to mean anything"

    left = (teams.is_active == 0).to_numpy()
    labels = teams.manager_id.to_numpy()
    strata = (teams.country + "|" + teams["rank"].astype(str)).to_numpy()
    observed = pd.Series(left).groupby(labels).mean().std()

    rng = np.random.default_rng(20260907)
    shuffled = []
    for _ in range(300):
        swapped = left.copy()
        for s in np.unique(strata):        # hold market and seniority fixed
            m = strata == s
            swapped[m] = rng.permutation(left[m])
        shuffled.append(pd.Series(swapped).groupby(labels).mean().std())
    beaten = float(np.mean([observed > s for s in shuffled]))
    assert beaten >= 0.99, (
        f"team attrition spread {observed:.3f} beats only {beaten:.0%} of "
        f"stratified shuffles (median {np.median(shuffled):.3f})")


def test_manager_outliers_are_judged_against_their_own_market():
    """Comparing every team to the company rate ranks countries, not managers:
    a market churning at 29% fills the top of the list on its own."""
    o = _read("manager_outliers")
    assert o.reports_total.min() >= 8
    assert set(o.verdict) <= {"Well above market", "In line", "Well below market"}
    assert (o[o.verdict == "Well above market"].team_attrition_rate
            >= o[o.verdict == "Well above market"].market_rate * 1.5).all()
    assert o.market_rate.nunique() > 1, "one market rate for everyone proves nothing"
    # The flagged teams must not simply be the worst country's teams.
    flagged = o[o.verdict == "Well above market"]
    assert flagged.country.nunique() >= 3


# --- exit classification --------------------------------------------------

def test_the_exit_classes_partition_the_exits_exactly():
    """Regretted, non-regretted and neutral must add up to every exit and
    overlap on none of them, or the page is counting some departures twice."""
    h = _read("attrition_headline").iloc[0]
    assert (h.regretted_exits + h.non_regretted_exits + h.neutral_exits) == h.exits
    assert h.active_headcount + h.exits == h.headcount_ever


def test_regretted_means_a_good_performer_left_by_choice(emp):
    """Re-derived from the employee master, independently of the SQL."""
    left = emp[emp.is_active == 0]
    expected = int(((left.term_type == "Voluntary")
                    & (left.performance_rating >= 4)).sum())
    assert int(_read("attrition_headline").iloc[0].regretted_exits) == expected


def test_regretted_and_headline_attrition_disagree(emp):
    """The whole reason the split exists. If regretted attrition simply tracked
    the headline rate across countries, the extra column would be decoration."""
    r = _read("regretted_attrition")
    c = r[r.dimension == "Country"]
    assert len(c) >= 6
    assert c.attrition_rate.idxmax() != c.regretted_share.idxmax(), \
        "the worst market for attrition is also the worst for regretted exits"


def test_first_year_exits_are_a_real_share_not_a_rounding_artefact():
    h = _read("attrition_headline").iloc[0]
    assert 0.2 < h.first_year_share < 0.9
    assert h.first_year_exits <= h.exits


# --- pay across markets ---------------------------------------------------

def test_the_benchmark_join_does_not_fan_out(emp):
    """comp_benchmark is per country AND level. Joining on level alone
    multiplies every employee by the number of countries - and the resulting
    pay gap still looks perfectly plausible."""
    roll = _read("pay_equity")
    roll = roll[roll.job_level == "ALL (level + market-adjusted)"].iloc[0]
    active = emp[(emp.is_active == 1) & emp.gender.isin(["Female", "Male"])]
    assert roll.n_female + roll.n_male <= len(active), "the join fanned out"
    # Cells with only one gender contribute nothing rather than a spurious
    # 100% gap, so this roll-up covers most of the population, not all of it.
    assert roll.n_female + roll.n_male >= len(active) * 0.75

    # The level-adjusted roll-up drops nothing, so it must reconcile exactly -
    # the sharpest form of the fan-out check.
    lvl = _read("pay_equity")
    lvl = lvl[lvl.job_level == "ALL (level-adjusted)"].iloc[0]
    assert lvl.n_female + lvl.n_male == len(active)


def test_pay_is_set_to_the_local_market_not_a_global_one():
    """Every market pays its own median, so compa-ratio is comparable
    everywhere and raw salary is not. This is the trap the market-adjusted gap
    exists to avoid, so assert the trap is actually present in the data."""
    geo = _read("workforce_by_country")
    assert geo.avg_compa_ratio.between(0.95, 1.05).all(), \
        "some market is systematically off its own benchmark"
    assert geo.avg_salary.max() / geo.avg_salary.min() > 2.5, \
        "raw salaries barely differ, so the geography trap is not demonstrated"


def test_the_market_adjusted_gap_is_reported_next_to_the_others():
    pe = _read("pay_equity")
    labels = set(pe.job_level)
    assert "ALL (level-adjusted)" in labels
    assert "ALL (level + market-adjusted)" in labels
    adj = pe[pe.job_level == "ALL (level-adjusted)"].raw_gap_pct.iloc[0]
    mkt = pe[pe.job_level == "ALL (level + market-adjusted)"].raw_gap_pct.iloc[0]
    assert abs(adj) < 0.10 and abs(mkt) < 0.10, "a gap this size is a data bug"


def test_pay_equity_levels_excludes_both_rollups():
    lv = _read("pay_equity_levels")
    assert not lv.job_level.str.startswith("ALL").any()
    assert lv.level_rank.max() < 98


# --- geography ------------------------------------------------------------

def test_country_shares_add_up():
    geo = _read("workforce_by_country")
    assert geo.share_of_headcount.sum() == pytest.approx(1.0, abs=0.002)
    assert geo.share_of_payroll.sum() == pytest.approx(1.0, abs=0.002)
    assert geo.headcount.sum() == _read("attrition_headline").iloc[0].active_headcount


def test_headcount_share_and_payroll_share_come_apart():
    """The finding the geography page leads with: a market can carry a quarter
    of the people and a twelfth of the cost. If these ever tracked each other,
    reporting both would be pointless."""
    geo = _read("workforce_by_country")
    ratio = geo.share_of_payroll / geo.share_of_headcount
    assert ratio.max() / ratio.min() > 2.0


def test_the_geo_headline_matches_the_country_table():
    h = _read("geo_headline").iloc[0]
    geo = _read("workforce_by_country")
    assert h.countries == geo.country.nunique()
    assert h.headcount == geo.headcount.sum()
    biggest = geo.loc[geo.headcount.idxmax()]
    assert h.largest_market == biggest.country
    assert h.largest_market_payroll_share == pytest.approx(biggest.share_of_payroll)
    sizeable = geo[geo.headcount >= 100]
    assert h.worst_market == sizeable.loc[sizeable.attrition_rate.idxmax()].country


# --- the talent grid ------------------------------------------------------

def test_the_nine_box_covers_every_active_employee_once(emp):
    box = _read("nine_box")
    assert box.employees.sum() == int((emp.is_active == 1).sum())
    assert box.share.sum() == pytest.approx(1.0, abs=0.002)
    assert len(box) == 9, "a nine-box with an empty cell is not a nine-box"


def test_potential_is_not_just_performance_wearing_a_hat(emp):
    """Two axes that agree are one axis. A grid where every employee sits on
    the diagonal tells a talent review nothing it did not already know."""
    active = emp[emp.is_active == 1]
    perf = active.performance_rating.clip(1, 5)
    pot = active.potential_label.map({"Low": 1, "Medium": 2, "High": 3})
    r = np.corrcoef(perf, pot)[0, 1]
    assert 0.2 < r < 0.75, f"performance/potential correlation {r:.2f} is degenerate"
    off_diagonal = 1 - (box_diagonal_share := _read("nine_box")
                        .query("performance_rank == potential_rank").share.sum())
    assert off_diagonal > 0.5, "most of the population sits on the diagonal"


# --- the figures the README quotes ----------------------------------------

def test_headline_figures_are_what_the_readme_claims():
    """Every number the README states, asserted against the published output.

    Without this the README is a snapshot of a run nobody can reproduce, and
    the numbers quietly stop being true the first time the generator changes.
    """
    geo = _read("geo_headline").iloc[0]
    ex = _read("attrition_headline").iloc[0]
    pe = _read("pay_equity")
    span = _read("span_of_control")
    outliers = _read("manager_outliers")
    layers = _read("org_layers")

    assert ex.active_headcount == 2151
    assert geo.countries == 8
    assert geo.largest_market == "Canada"
    assert geo.largest_market_headcount_share == pytest.approx(0.375, abs=0.002)
    assert geo.largest_market_payroll_share == pytest.approx(0.479, abs=0.003)
    assert geo.worst_market == "India"
    assert geo.worst_market_rate == pytest.approx(0.276, abs=0.002)
    assert geo.attrition_spread == pytest.approx(0.145, abs=0.003)
    assert geo.pay_market_multiple == pytest.approx(4.9, abs=0.1)

    assert ex.regretted_exits == 170
    assert ex.regretted_share == pytest.approx(0.26, abs=0.005)
    assert ex.regretted_salary == pytest.approx(11_068_000, rel=1e-4)
    assert ex.first_year_share == pytest.approx(0.56, abs=0.005)
    assert ex.stalled_high_performers == 75

    market = pe[pe.job_level == "ALL (level + market-adjusted)"].raw_gap_pct.iloc[0]
    level = pe[pe.job_level == "ALL (level-adjusted)"].raw_gap_pct.iloc[0]
    assert level == pytest.approx(0.045, abs=0.002)
    assert market == pytest.approx(0.037, abs=0.002)

    assert len(span) == 351
    assert (span.span_band == "1. Thin (<4)").mean() == pytest.approx(0.388, abs=0.005)
    assert len(outliers) == 167
    assert int((outliers.verdict == "Well above market").sum()) == 33
    assert layers.layer.max() == 4
    assert layers.sort_values("layer").share_of_headcount.iloc[-1] > 0.80


def test_the_readme_pay_table_matches_the_published_levels():
    """The four rows the README tabulates, read back from the SQL output."""
    lv = _read("pay_equity_levels").set_index("job_level")
    for level, raw, market in [("Senior Manager", 0.182, 0.034),
                               ("Senior Analyst", 0.131, 0.037),
                               ("Lead", -0.015, 0.043)]:
        assert lv.loc[level, "raw_gap_pct"] == pytest.approx(raw, abs=0.002)
        assert lv.loc[level, "market_adjusted_gap_pct"] == pytest.approx(market, abs=0.002)
    # And the point of the table: adjusting for market compresses the spread.
    assert (lv.market_adjusted_gap_pct.max() - lv.market_adjusted_gap_pct.min()) < \
           (lv.raw_gap_pct.max() - lv.raw_gap_pct.min()) / 3
