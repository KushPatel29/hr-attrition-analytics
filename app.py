"""Workforce Decision Room — governed, cohort-level retention planning."""

from __future__ import annotations

import hashlib
import html
import json
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "output"
POLICY_PATH = ROOT / "governance" / "responsible_use_policy.json"

st.set_page_config(
    page_title="Workforce Decision Room",
    page_icon="◆",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
<style>
:root {
  --ink: #172026;
  --paper: #F4F6F3;
  --teal: #1E6B67;
  --teal-soft: #DCE9E5;
  --amber: #B56A24;
  --amber-soft: #F4E6D5;
  --red: #A33A3A;
  --line: #B9C4BF;
  --muted: #586661;
}
.stApp { background: var(--paper); color: var(--ink); }
[data-testid="stHeader"] { background: rgba(244,246,243,.92); }
[data-testid="stSidebar"] { background: #E7ECE8; border-right: 1px solid var(--line); }
[data-testid="stSidebar"] hr { border-color: var(--line); }
.block-container { max-width: 1440px; padding-top: 2.2rem; padding-bottom: 4rem; }
h1, h2, h3 { color: var(--ink); letter-spacing: -.025em; }
h1 { font-size: clamp(2rem, 4vw, 4rem); line-height: 1.03; max-width: 16ch; }
h2 { font-size: clamp(1.35rem, 2vw, 2rem); margin-top: .4rem; }
p, li { line-height: 1.62; }
.hero-shell {
  display: grid;
  grid-template-columns: minmax(0, 1.7fr) minmax(260px, .7fr);
  gap: 2rem;
  border-top: 8px solid var(--ink);
  border-bottom: 1px solid var(--ink);
  padding: 1.6rem 0 1.5rem;
  margin-bottom: 1rem;
}
.hero-kicker { color: var(--teal); font-weight: 700; font-size: 1.05rem; margin-bottom: .55rem; }
.hero-title { font-weight: 750; font-size: clamp(2.35rem, 5vw, 5.4rem); line-height: .95; letter-spacing: -.055em; max-width: 11ch; }
.hero-copy { color: var(--muted); font-size: 1.06rem; max-width: 64ch; margin: 1rem 0 0; }
.posture {
  border-left: 5px solid var(--amber);
  background: var(--amber-soft);
  padding: 1.15rem 1.2rem;
  align-self: end;
}
.posture strong { display:block; color: #6E3C14; font-size: 1.35rem; margin-bottom: .35rem; }
.posture span { color: #604833; }
.gate-ledger {
  display:grid;
  grid-template-columns: repeat(4, minmax(0,1fr));
  border: 1px solid var(--line);
  border-right: 0;
  margin: 0 0 1.5rem;
}
.ledger-cell { padding: .9rem 1rem; border-right: 1px solid var(--line); min-height: 88px; }
.ledger-value { font-size: 1.7rem; font-weight: 760; letter-spacing: -.04em; }
.ledger-label { color: var(--muted); font-size: .86rem; margin-top: .1rem; }
.accent-pass { color: var(--teal); }
.accent-review { color: var(--amber); }
.accent-block { color: var(--red); }
.authority-box {
  border: 1px solid var(--ink);
  padding: 1.25rem;
  background: #FBFCFA;
  min-height: 100%;
}
.authority-box h3 { margin: 0 0 .7rem; font-size: 1.1rem; }
.authority-box p { margin-bottom: 0; color: var(--muted); }
.record {
  border-left: 5px solid var(--teal);
  background: #FBFCFA;
  padding: 1.15rem 1.25rem;
  margin: .5rem 0 1.1rem;
}
.record h3 { margin: 0 0 .35rem; }
.record p { margin: .22rem 0; color: var(--muted); }
.signal { color: var(--ink) !important; font-weight: 650; }
.small-note { color: var(--muted); font-size: .9rem; }
.stTabs [data-baseweb="tab-list"] { gap: .25rem; border-bottom: 1px solid var(--line); }
.stTabs [data-baseweb="tab"] { border-radius: 0; padding: .7rem .85rem; }
.stTabs [aria-selected="true"] { color: var(--teal) !important; border-bottom: 3px solid var(--teal); }
.stButton > button, .stDownloadButton > button {
  border-radius: 2px; border: 1px solid var(--ink); background: var(--ink); color: white;
  font-weight: 650; min-height: 2.7rem;
}
.stButton > button:hover, .stDownloadButton > button:hover { border-color: var(--teal); background: var(--teal); color:white; }
*:focus-visible { outline: 3px solid #D3954F !important; outline-offset: 2px !important; }
@media (max-width: 850px) {
  .hero-shell { grid-template-columns: 1fr; }
  .gate-ledger { grid-template-columns: repeat(2, minmax(0,1fr)); }
}
@media (prefers-reduced-motion: reduce) { * { scroll-behavior: auto !important; transition: none !important; } }
</style>
""",
    unsafe_allow_html=True,
)


@st.cache_data
def load_csv(name: str) -> pd.DataFrame:
    return pd.read_csv(OUT / name)


@st.cache_data
def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def money(value: float) -> str:
    if value >= 1_000_000:
        return f"${value / 1_000_000:.1f}M"
    return f"${value:,.0f}"


def pct(value: float) -> str:
    return f"{value:.1%}"


def safe(value: object) -> str:
    return html.escape(str(value))


def verify_manifest() -> tuple[int, int]:
    manifest = load_json(OUT / "responsible_use_manifest.json")
    verified = 0
    for name, evidence in manifest["artifacts"].items():
        path = OUT / name
        if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == evidence["sha256"]:
            verified += 1
    return verified, len(manifest["artifacts"])


policy = load_json(POLICY_PATH)
summary = load_json(OUT / "responsible_use_summary.json")
gates = load_csv("release_gates.csv")
portfolio = load_csv("intervention_portfolio.csv")
slices = load_csv("slice_assurance.csv")
crosswalk = load_csv("ai_rmf_crosswalk.csv")
verified_files, evidence_files = verify_manifest()

counts = summary["gate_counts"]
st.markdown(
    f"""
<section class="hero-shell">
  <div>
    <div class="hero-kicker">People analytics with an authority boundary</div>
    <div class="hero-title">Workforce decision room</div>
    <p class="hero-copy">Turn workforce signals into controlled, cohort-level retention pilots. Every proposal carries an owner, evidence limit, approval path, monitoring measure and rollback trigger.</p>
  </div>
  <aside class="posture" aria-label="Release posture">
    <strong>Review required</strong>
    <span>No blocker is open, but analytics alone cannot authorize an intervention. HR, privacy and legal review remain mandatory.</span>
  </aside>
</section>
<div class="gate-ledger" role="list" aria-label="Release summary">
  <div class="ledger-cell" role="listitem"><div class="ledger-value accent-pass">{counts['pass']}</div><div class="ledger-label">Controls passed</div></div>
  <div class="ledger-cell" role="listitem"><div class="ledger-value accent-review">{counts['review']}</div><div class="ledger-label">Human reviews due</div></div>
  <div class="ledger-cell" role="listitem"><div class="ledger-value accent-block">{counts['block']}</div><div class="ledger-label">Release blockers</div></div>
  <div class="ledger-cell" role="listitem"><div class="ledger-value">{verified_files}/{evidence_files}</div><div class="ledger-label">Evidence files hash-verified</div></div>
</div>
""",
    unsafe_allow_html=True,
)

with st.sidebar:
    st.markdown("## Decision policy")
    st.caption(f"Version {policy['policy_version']} · snapshot {policy['snapshot_date']}")
    st.markdown(f"**Scope**  \n{policy['decision_scope']}")
    st.markdown(f"**Decision owner**  \n{policy['decision_owner']}")
    st.markdown(f"**Risk owner**  \n{policy['risk_owner']}")
    st.divider()
    st.markdown("**Allowed**")
    for item in policy["allowed_uses"]:
        st.markdown(f"- {item}")
    st.markdown("**Never allowed**")
    for item in policy["prohibited_uses"]:
        st.markdown(f"- {item}")
    st.divider()
    st.caption(
        "Synthetic portfolio. The operating model is realistic; the workforce and observed effects are not real people or production claims."
    )

tab_release, tab_portfolio, tab_signals, tab_fairness, tab_evidence = st.tabs(
    [
        "Release decision",
        "Intervention portfolio",
        "Workforce signals",
        "Fairness & privacy",
        "Evidence map",
    ]
)

with tab_release:
    st.markdown("## Decide whether the portfolio is ready for a controlled pilot")
    st.caption(
        "A green model is necessary but insufficient. The release posture combines model, privacy, fairness, evidence and authority controls."
    )
    left, right = st.columns([1.15, 1], gap="large")
    with left:
        display_gates = gates.rename(
            columns={
                "gate_id": "Control",
                "gate": "Decision test",
                "status": "State",
                "evidence": "Evidence",
                "owner": "Owner",
            }
        )
        st.dataframe(
            display_gates,
            hide_index=True,
            use_container_width=True,
            column_config={
                "Control": st.column_config.TextColumn(width="small"),
                "Decision test": st.column_config.TextColumn(width="medium"),
                "State": st.column_config.TextColumn(width="small"),
                "Evidence": st.column_config.TextColumn(width="large"),
            },
        )
    with right:
        st.markdown(
            """
<div class="authority-box">
  <h3>What this decision does</h3>
  <p><strong>Approve:</strong> authorizes a time-boxed cohort pilot after the named reviewers sign.</p>
  <p><strong>Return:</strong> sends the proposal back for evidence, privacy or design changes.</p>
  <p><strong>Stop:</strong> blocks release when any control is marked BLOCK.</p>
  <p>This screen cannot authorize a decision about a named person.</p>
</div>
""",
            unsafe_allow_html=True,
        )
        packet = (OUT / "responsible_use_decision_packet.md").read_text(encoding="utf-8")
        st.download_button(
            "Download review packet",
            data=packet,
            file_name="workforce-decision-room-release-packet.md",
            mime="text/markdown",
            use_container_width=True,
        )
    with st.expander("Approval checklist", expanded=True):
        for role in policy["required_approvals"]:
            st.checkbox(role, value=False, disabled=True, help="Evidence artifact — approvals are not simulated in this public demo.")
        st.checkbox(
            "Pilot owner accepts monitoring and rollback plan",
            value=False,
            disabled=True,
            help="This public portfolio records the required control without fabricating sign-off.",
        )
        st.info("Public demo posture: review remains open. No approval is implied or stored.")

with tab_portfolio:
    st.markdown("## Move from signal to a governed intervention")
    st.caption(
        "The portfolio is ranked by aggregate regretted-exit burden. It does not expose or rank people."
    )
    selected_id = st.selectbox(
        "Proposal to review",
        portfolio["initiative_id"].tolist(),
        format_func=lambda key: f"{key} · {portfolio.loc[portfolio['initiative_id'] == key, 'population'].iloc[0]}",
    )
    selected = portfolio.loc[portfolio["initiative_id"] == selected_id].iloc[0]
    st.markdown(
        f"""
<article class="record">
  <h3>{safe(selected['initiative_id'])} · {safe(selected['population'])}</h3>
  <p class="signal">{safe(selected['business_signal'])}</p>
  <p><strong>Proposed response:</strong> {safe(selected['proposed_intervention'])}</p>
  <p><strong>Accountable owner:</strong> {safe(selected['accountable_owner'])}</p>
  <p><strong>Evidence limit:</strong> {safe(selected['evidence_level'])}</p>
  <p><strong>Monitoring:</strong> {safe(selected['monitoring_metric'])}</p>
  <p><strong>Rollback:</strong> {safe(selected['rollback_trigger'])}</p>
</article>
""",
        unsafe_allow_html=True,
    )
    p_left, p_right = st.columns([1.15, 1], gap="large")
    with p_left:
        regretted = load_csv("regretted_by_department.csv").sort_values(
            "regretted_exits", ascending=False
        )
        st.markdown("### Regretted exits by department")
        st.bar_chart(
            regretted.set_index("department")["regretted_exits"],
            color="#1E6B67",
            horizontal=True,
        )
    with p_right:
        effects = load_csv("intervention_effectiveness.csv")
        st.markdown("### Observed synthetic uplift")
        st.dataframe(
            effects[["cohort_label", "n_employees", "retention_rate", "lift_vs_control"]],
            hide_index=True,
            use_container_width=True,
            column_config={
                "cohort_label": "Cohort",
                "n_employees": st.column_config.NumberColumn("Population", format="%d"),
                "retention_rate": st.column_config.NumberColumn("Retention", format="%.1%%"),
                "lift_vs_control": st.column_config.NumberColumn("Observed lift", format="%.1%%"),
            },
        )
        st.warning(
            "The uplift was planted in synthetic data and is descriptive—not a causal effect. A real pilot must pre-register outcomes and use a controlled or defensible quasi-experimental design."
        )
    with st.expander("View the full intervention register"):
        st.dataframe(portfolio, hide_index=True, use_container_width=True)

with tab_signals:
    st.markdown("## Read workforce conditions before choosing an intervention")
    workforce = load_csv("workforce_kpis.csv")
    latest = workforce.dropna(subset=["rolling_12m_attrition_rate"]).iloc[-1]
    exit_detail = load_csv("regretted_attrition.csv")
    regretted_salary = exit_detail.loc[
        exit_detail["dimension"] == "Department", "regretted_salary"
    ].sum()
    chosen_model = load_csv("model_evaluation.csv").query("is_chosen == 1").iloc[0]
    s1, s2, s3, s4 = st.columns(4)
    s1.metric("Active headcount", f"{int(latest['headcount']):,}")
    s2.metric("Trailing-12-month attrition", pct(float(latest["rolling_12m_attrition_rate"])))
    s3.metric("Regretted salary exposure", money(float(regretted_salary)))
    s4.metric("Chosen model ROC-AUC", f"{float(chosen_model['roc_auc']):.3f}")
    st.markdown("### Attrition operating trend")
    trend = workforce.dropna(subset=["rolling_12m_attrition_rate"]).copy()
    trend["month"] = pd.to_datetime(trend["month"])
    st.line_chart(
        trend.set_index("month")[["rolling_12m_attrition_rate"]],
        color=["#1E6B67"],
    )
    st.caption(
        "Use this trend to frame a cohort hypothesis. The application deliberately does not open a person-level risk queue."
    )
    dept = load_csv("regretted_by_department.csv").copy()
    dept["attrition_rate"] = dept["attrition_rate"].map(lambda value: f"{value:.1%}")
    dept["regretted_rate"] = dept["regretted_rate"].map(lambda value: f"{value:.1%}")
    st.markdown("### Department evidence register")
    st.dataframe(
        dept[
            [
                "department",
                "division",
                "headcount_ever",
                "exits",
                "regretted_exits",
                "first_year_exits",
                "attrition_rate",
                "regretted_rate",
            ]
        ],
        hide_index=True,
        use_container_width=True,
    )

with tab_fairness:
    st.markdown("## Treat fairness exceptions as questions, not verdicts")
    st.caption(
        "The four-fifths ratio is a screen. Sample size and statistical uncertainty remain visible, and an inconclusive result stays on the monitor list."
    )
    attribute = st.selectbox(
        "Slice family",
        sorted(slices["attribute"].unique()),
        format_func=lambda value: value.replace("_", " ").title(),
    )
    view = slices[slices["attribute"] == attribute].copy()
    f_left, f_right = st.columns([1.15, 1], gap="large")
    with f_left:
        st.markdown("### High-risk selection rate")
        st.bar_chart(
            view.set_index("group")["selection_rate"],
            color="#1E6B67",
            horizontal=True,
        )
    with f_right:
        monitor = view[view["screen_state"] == "Outside band — monitor"]
        st.markdown("### Review posture")
        if len(monitor):
            st.warning(
                f"{len(monitor)} slice(s) fall outside the 0.80–1.25 screen band. The evidence is inconclusive, so review remains open."
            )
        else:
            st.success("No slice in this family falls outside the current screen band.")
        st.markdown(
            f"Minimum publishable group: **{policy['minimum_publishable_group']}**  \n"
            f"Reference: largest group in each slice family  \n"
            "Decision: monitor aggregate outcomes; never infer an employment action for a person."
        )
    st.dataframe(
        view.rename(
            columns={
                "group": "Group",
                "n": "Population",
                "selection_rate": "Selection rate",
                "di_ratio": "DI ratio",
                "p_value": "p-value",
                "screen_state": "Screen state",
                "uncertainty_statement": "Interpretation",
            }
        )[
            [
                "Group",
                "Population",
                "Selection rate",
                "DI ratio",
                "p-value",
                "Screen state",
                "Interpretation",
            ]
        ],
        hide_index=True,
        use_container_width=True,
        column_config={
            "Selection rate": st.column_config.NumberColumn(format="%.1%%"),
            "DI ratio": st.column_config.NumberColumn(format="%.3f"),
            "p-value": st.column_config.NumberColumn(format="%.4f"),
            "Interpretation": st.column_config.TextColumn(width="large"),
        },
    )
    with st.expander("Privacy release evidence"):
        privacy = load_csv("privacy_suppression_audit.csv")
        st.write(
            f"The pipeline recorded **{len(privacy):,}** suppression decisions. The release product uses aggregate artifacts and does not load the individual score register."
        )
        st.dataframe(privacy.head(100), hide_index=True, use_container_width=True)

with tab_evidence:
    st.markdown("## Trace the claim to the control and artifact")
    st.caption(
        "The NIST AI RMF structure is used as an operating map. This project does not claim certification or legal compliance."
    )
    st.dataframe(
        crosswalk.rename(
            columns={
                "function": "Function",
                "control": "Operational control",
                "evidence": "Repository evidence",
                "status": "State",
            }
        ),
        hide_index=True,
        use_container_width=True,
        column_config={
            "Function": st.column_config.TextColumn(width="small"),
            "Operational control": st.column_config.TextColumn(width="large"),
            "Repository evidence": st.column_config.TextColumn(width="large"),
        },
    )
    manifest = load_json(OUT / "responsible_use_manifest.json")
    manifest_rows = [
        {
            "Artifact": name,
            "Bytes": evidence["bytes"],
            "SHA-256": evidence["sha256"],
            "Verified": hashlib.sha256((OUT / name).read_bytes()).hexdigest()
            == evidence["sha256"],
        }
        for name, evidence in manifest["artifacts"].items()
    ]
    st.markdown("### Reproducible evidence manifest")
    st.dataframe(
        pd.DataFrame(manifest_rows),
        hide_index=True,
        use_container_width=True,
        column_config={"SHA-256": st.column_config.TextColumn(width="large")},
    )
    e_left, e_right = st.columns(2)
    with e_left:
        st.link_button(
            "Open repository",
            "https://github.com/KushPatel29/hr-attrition-analytics",
            use_container_width=True,
        )
    with e_right:
        st.download_button(
            "Download evidence manifest",
            data=json.dumps(manifest, indent=2, sort_keys=True),
            file_name="responsible-use-manifest.json",
            mime="application/json",
            use_container_width=True,
        )

st.divider()
st.caption(
    "Synthetic demonstration · cohort-level planning only · no individual employment action · evidence snapshot 2026-06-30"
)
