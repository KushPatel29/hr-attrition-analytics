"""Build deterministic, cohort-level governance evidence for the HR decision room.

The source model produces individual synthetic scores for evaluation. This module
deliberately does not publish them. It turns aggregate analytics into a reviewable
intervention portfolio, slice assurance record, release gates and NIST AI RMF map.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "output"
POLICY_PATH = ROOT / "governance" / "responsible_use_policy.json"

FORBIDDEN_PUBLIC_COLUMNS = {
    "employee_id",
    "employee_name",
    "manager_id",
    "manager_name",
    "risk_score",
    "base_salary",
}


def _write_csv(frame: pd.DataFrame, path: Path) -> None:
    frame.to_csv(path, index=False, lineterminator="\n")


def _write_text(path: Path, text: str) -> None:
    path.write_text(text.rstrip() + "\n", encoding="utf-8", newline="\n")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_policy() -> dict:
    return json.loads(POLICY_PATH.read_text(encoding="utf-8"))


def build_intervention_portfolio() -> pd.DataFrame:
    departments = pd.read_csv(OUT / "regretted_by_department.csv")
    focus = departments.sort_values(
        ["regretted_exits", "regretted_salary"], ascending=False
    ).head(6).reset_index(drop=True)

    action_by_division = {
        "Operations": "Pilot schedule-stability and supervisor listening sessions",
        "Go-To-Market": "Pilot role-pathing and manager-led stay conversations",
        "Technology": "Pilot internal mobility and promotion-readiness clinics",
        "Corporate": "Pilot development plans and workload review",
    }
    owner_by_division = {
        "Operations": "People Operations Director",
        "Go-To-Market": "Commercial HR Business Partner",
        "Technology": "Technology Talent Partner",
        "Corporate": "Corporate HR Business Partner",
    }

    rows: list[dict] = []
    for index, row in focus.iterrows():
        division = str(row["division"])
        rows.append(
            {
                "initiative_id": f"RET-{index + 1:02d}",
                "population": f"{row['department']} cohort",
                "business_signal": (
                    f"{int(row['regretted_exits'])} regretted exits; "
                    f"{float(row['first_year_exits']) / max(float(row['exits']), 1):.0%} "
                    "of exits in year one"
                ),
                "proposed_intervention": action_by_division.get(
                    division, "Pilot manager listening and career-path review"
                ),
                "accountable_owner": owner_by_division.get(
                    division, "People Operations Director"
                ),
                "evidence_level": "Descriptive signal; controlled pilot required",
                "decision_status": "Review required",
                "spend_authority": "Not authorized by analytics",
                "harm_review": "Required before pilot",
                "monitoring_metric": "90-day participation, 6-month retention, slice parity",
                "rollback_trigger": "Material adverse slice movement or privacy breach",
            }
        )
    return pd.DataFrame(rows)


def build_slice_assurance(policy: dict) -> pd.DataFrame:
    audit = pd.read_csv(OUT / "fairness_audit.csv")
    low, high = policy["four_fifths_band"]
    minimum = int(policy["minimum_publishable_group"])
    audit["publishable"] = audit["n"] >= minimum
    audit["screen_state"] = "Within review band"
    audit.loc[~audit["di_ratio"].between(low, high), "screen_state"] = (
        "Outside band — monitor"
    )
    audit.loc[~audit["publishable"], "screen_state"] = "Suppressed — sample too small"
    audit["uncertainty_statement"] = audit.apply(
        lambda row: (
            "Not evaluated; group is below the publication floor."
            if not row["publishable"]
            else (
                "Observed disparity is inconclusive, not cleared; retain on monitor list."
                if str(row["verdict"]).startswith("outside band")
                else "No four-fifths screen exception in this snapshot; continue monitoring."
            )
        ),
        axis=1,
    )
    return audit[
        [
            "attribute",
            "group",
            "n",
            "n_high",
            "selection_rate",
            "reference_group",
            "di_ratio",
            "p_value",
            "publishable",
            "screen_state",
            "uncertainty_statement",
        ]
    ]


def build_nist_crosswalk() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "function": "GOVERN",
                "control": "Document authority, prohibited uses and accountable owners",
                "evidence": "responsible_use_policy.json; intervention_portfolio.csv",
                "status": "Implemented",
            },
            {
                "function": "MAP",
                "control": "Define intended context, affected cohorts, harms and limits",
                "evidence": "README responsible-use case; responsible_use_decision_packet.md",
                "status": "Implemented",
            },
            {
                "function": "MEASURE",
                "control": "Measure model quality, slice outcomes, privacy and uncertainty",
                "evidence": "model_evaluation.csv; slice_assurance.csv; privacy_suppression_audit.csv",
                "status": "Implemented",
            },
            {
                "function": "MANAGE",
                "control": "Require approvals, pilot controls, monitoring and rollback triggers",
                "evidence": "release_gates.csv; intervention_portfolio.csv",
                "status": "Review required",
            },
        ]
    )


def build_release_gates(policy: dict, slices: pd.DataFrame, portfolio: pd.DataFrame) -> pd.DataFrame:
    model_eval = pd.read_csv(OUT / "model_evaluation.csv")
    feature_importance = pd.read_csv(OUT / "feature_importance.csv")
    privacy = pd.read_csv(OUT / "privacy_suppression_audit.csv")
    protected = {"gender", "ethnicity_group", "age_band"}
    leaked = feature_importance["feature"].astype(str).map(
        lambda value: any(value.startswith(item) for item in protected)
    ).any()
    chosen = model_eval[model_eval["is_chosen"] == 1].iloc[0]
    monitor_count = int((slices["screen_state"] == "Outside band — monitor").sum())
    forbidden = sorted(FORBIDDEN_PUBLIC_COLUMNS & set(portfolio.columns))

    rows = [
        {
            "gate_id": "HR-GOV-01",
            "gate": "Aggregate-only decision surface",
            "status": "PASS" if not forbidden else "BLOCK",
            "evidence": "No person identifier or individual risk score in intervention portfolio",
            "owner": policy["model_owner"],
        },
        {
            "gate_id": "HR-GOV-02",
            "gate": "Protected attributes excluded from model inputs",
            "status": "PASS" if not leaked else "BLOCK",
            "evidence": "Feature importance contains no protected attribute prefix",
            "owner": policy["model_owner"],
        },
        {
            "gate_id": "HR-GOV-03",
            "gate": "Predictive floor",
            "status": "PASS" if float(chosen["roc_auc"]) >= 0.68 else "BLOCK",
            "evidence": f"Chosen model ROC-AUC {float(chosen['roc_auc']):.3f}",
            "owner": policy["model_owner"],
        },
        {
            "gate_id": "HR-GOV-04",
            "gate": "Privacy suppression active",
            "status": "PASS" if len(privacy) else "BLOCK",
            "evidence": f"{len(privacy)} suppression-audit records; minimum group policy enforced",
            "owner": policy["risk_owner"],
        },
        {
            "gate_id": "HR-GOV-05",
            "gate": "Slice assurance",
            "status": "REVIEW" if monitor_count else "PASS",
            "evidence": f"{monitor_count} slices outside screen band and retained for review",
            "owner": policy["risk_owner"],
        },
        {
            "gate_id": "HR-GOV-06",
            "gate": "Intervention evidence claim",
            "status": "PASS",
            "evidence": "Observed uplift is labelled descriptive and synthetic, never causal",
            "owner": policy["decision_owner"],
        },
        {
            "gate_id": "HR-GOV-07",
            "gate": "Human approval before pilot",
            "status": "REVIEW",
            "evidence": f"{len(portfolio)} proposals require named HR, privacy and legal approval",
            "owner": policy["decision_owner"],
        },
        {
            "gate_id": "HR-GOV-08",
            "gate": "Rollback and monitoring plan",
            "status": "PASS",
            "evidence": "Each proposal names a monitoring metric and rollback trigger",
            "owner": policy["decision_owner"],
        },
    ]
    return pd.DataFrame(rows)


def build_packet(policy: dict, gates: pd.DataFrame, portfolio: pd.DataFrame) -> str:
    counts = gates["status"].value_counts().to_dict()
    lines = [
        "# Workforce Decision Room — release decision packet",
        "",
        f"**Snapshot:** {policy['snapshot_date']}  ",
        f"**Policy version:** {policy['policy_version']}  ",
        (
            "**Release posture:** REVIEW REQUIRED — analytics may inform a controlled "
            "cohort pilot; no employment action is authorized."
        ),
        "",
        "## Decision requested",
        "",
        (
            "Review the proposed cohort-level retention pilots, confirm their lawful and "
            "ethical basis, and either approve a time-boxed experiment or return the "
            "proposal for revision."
        ),
        "",
        "## Release gate result",
        "",
        f"- PASS: {counts.get('PASS', 0)}",
        f"- REVIEW: {counts.get('REVIEW', 0)}",
        f"- BLOCK: {counts.get('BLOCK', 0)}",
        "",
        "## Authority boundary",
        "",
        (
            "This packet permits aggregate planning only. It does not authorize "
            "termination, promotion, compensation, discipline, or named-employee ranking. "
            "A prediction is a signal to investigate conditions, not a finding about a person."
        ),
        "",
        "## Evidence interpretation",
        "",
        (
            "The intervention lift in this synthetic portfolio is descriptive and "
            "deliberately planted by the generator. A real deployment must use a controlled "
            "design (or a defensible quasi-experimental design), pre-register outcomes, and "
            "monitor harms by slice."
        ),
        "",
        "## Proposed portfolio",
        "",
    ]
    for row in portfolio.to_dict("records"):
        lines.extend(
            [
                f"### {row['initiative_id']} — {row['population']}",
                "",
                f"- Signal: {row['business_signal']}",
                f"- Proposal: {row['proposed_intervention']}",
                f"- Owner: {row['accountable_owner']}",
                f"- Evidence: {row['evidence_level']}",
                f"- Monitoring: {row['monitoring_metric']}",
                f"- Rollback: {row['rollback_trigger']}",
                "",
            ]
        )
    lines.extend(
        [
            "## Required sign-off",
            "",
            *[f"- [ ] {role}" for role in policy["required_approvals"]],
            "- [ ] Pilot owner accepts the monitoring and rollback plan",
            "",
            "## Framework note",
            "",
            (
                "The evidence map uses the NIST AI RMF 1.0 core functions — GOVERN, MAP, "
                "MEASURE and MANAGE — as an operating structure, not as a certification claim."
            ),
        ]
    )
    return "\n".join(lines)


def build_all() -> dict:
    policy = load_policy()
    portfolio = build_intervention_portfolio()
    slices = build_slice_assurance(policy)
    crosswalk = build_nist_crosswalk()
    gates = build_release_gates(policy, slices, portfolio)

    paths = {
        "intervention_portfolio.csv": OUT / "intervention_portfolio.csv",
        "slice_assurance.csv": OUT / "slice_assurance.csv",
        "ai_rmf_crosswalk.csv": OUT / "ai_rmf_crosswalk.csv",
        "release_gates.csv": OUT / "release_gates.csv",
        "responsible_use_decision_packet.md": OUT / "responsible_use_decision_packet.md",
    }
    _write_csv(portfolio, paths["intervention_portfolio.csv"])
    _write_csv(slices, paths["slice_assurance.csv"])
    _write_csv(crosswalk, paths["ai_rmf_crosswalk.csv"])
    _write_csv(gates, paths["release_gates.csv"])
    _write_text(
        paths["responsible_use_decision_packet.md"],
        build_packet(policy, gates, portfolio),
    )

    counts = gates["status"].value_counts().to_dict()
    summary = {
        "snapshot_date": policy["snapshot_date"],
        "policy_version": policy["policy_version"],
        "release_posture": "BLOCKED" if counts.get("BLOCK", 0) else "REVIEW_REQUIRED",
        "gate_counts": {
            "pass": int(counts.get("PASS", 0)),
            "review": int(counts.get("REVIEW", 0)),
            "block": int(counts.get("BLOCK", 0)),
        },
        "proposals": len(portfolio),
        "monitor_slices": int(
            (slices["screen_state"] == "Outside band — monitor").sum()
        ),
        "authority": "Cohort-level planning only; no individual employment action",
    }
    summary_path = OUT / "responsible_use_summary.json"
    _write_text(summary_path, json.dumps(summary, indent=2, sort_keys=True))
    paths["responsible_use_summary.json"] = summary_path

    manifest = {
        "schema_version": "1.0.0",
        "snapshot_date": policy["snapshot_date"],
        "policy_sha256": _sha256(POLICY_PATH),
        "artifacts": {
            name: {"sha256": _sha256(path), "bytes": path.stat().st_size}
            for name, path in sorted(paths.items())
        },
    }
    manifest_path = OUT / "responsible_use_manifest.json"
    _write_text(manifest_path, json.dumps(manifest, indent=2, sort_keys=True))
    return summary


if __name__ == "__main__":
    print(json.dumps(build_all(), indent=2, sort_keys=True))
