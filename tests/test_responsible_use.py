"""Contract tests for the aggregate workforce decision product."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "output"
sys.path.insert(0, str(ROOT / "governance"))

from build_responsible_use_evidence import (
    FORBIDDEN_PUBLIC_COLUMNS,
    build_all,
    build_release_gates,
    build_slice_assurance,
    load_policy,
)


@pytest.fixture(scope="module", autouse=True)
def rebuild_evidence():
    return build_all()


def test_policy_names_three_lines_of_accountability():
    policy = load_policy()
    assert policy["decision_owner"]
    assert policy["model_owner"]
    assert policy["risk_owner"]
    assert len(policy["required_approvals"]) >= 3


@pytest.mark.parametrize(
    "prohibited_phrase",
    ["termination", "named employees", "protected attribute", "causal"],
)
def test_policy_prohibits_high_risk_uses(prohibited_phrase):
    prohibited = " ".join(load_policy()["prohibited_uses"]).lower()
    assert prohibited_phrase in prohibited


def test_public_intervention_portfolio_has_no_person_level_fields():
    portfolio = pd.read_csv(OUT / "intervention_portfolio.csv")
    assert not (FORBIDDEN_PUBLIC_COLUMNS & set(portfolio.columns))
    assert portfolio["population"].str.endswith(" cohort").all()


def test_every_proposal_has_owner_monitoring_and_rollback():
    portfolio = pd.read_csv(OUT / "intervention_portfolio.csv")
    required = {
        "accountable_owner",
        "monitoring_metric",
        "rollback_trigger",
        "harm_review",
    }
    assert required <= set(portfolio.columns)
    assert portfolio[list(required)].notna().all().all()


def test_analytics_does_not_authorize_spend_or_action():
    portfolio = pd.read_csv(OUT / "intervention_portfolio.csv")
    assert set(portfolio["decision_status"]) == {"Review required"}
    assert set(portfolio["spend_authority"]) == {"Not authorized by analytics"}


def test_intervention_claim_is_explicitly_noncausal():
    portfolio = pd.read_csv(OUT / "intervention_portfolio.csv")
    evidence = " ".join(portfolio["evidence_level"]).lower()
    assert "descriptive" in evidence and "controlled pilot" in evidence
    packet = (OUT / "responsible_use_decision_packet.md").read_text(encoding="utf-8")
    assert "descriptive" in packet.lower()
    assert "not authorize" in packet.lower()


def test_slice_floor_matches_policy():
    policy = load_policy()
    slices = pd.read_csv(OUT / "slice_assurance.csv")
    expected = slices["n"] >= policy["minimum_publishable_group"]
    assert slices["publishable"].astype(bool).equals(expected)


def test_outside_band_is_monitored_not_cleared():
    slices = pd.read_csv(OUT / "slice_assurance.csv")
    outside = slices[slices["screen_state"] == "Outside band — monitor"]
    assert len(outside) >= 1
    assert outside["uncertainty_statement"].str.contains("inconclusive").all()
    assert not outside["uncertainty_statement"].str.contains("fair", case=False).any()


def test_crosswalk_covers_nist_core_functions():
    crosswalk = pd.read_csv(OUT / "ai_rmf_crosswalk.csv")
    assert set(crosswalk["function"]) == {"GOVERN", "MAP", "MEASURE", "MANAGE"}
    assert crosswalk["evidence"].str.len().gt(10).all()


def test_release_gate_ids_are_unique_and_typed():
    gates = pd.read_csv(OUT / "release_gates.csv")
    assert gates["gate_id"].is_unique
    assert set(gates["status"]) <= {"PASS", "REVIEW", "BLOCK"}
    assert {"PASS", "REVIEW"} <= set(gates["status"])


def test_release_posture_requires_review_without_blockers():
    summary = json.loads((OUT / "responsible_use_summary.json").read_text())
    assert summary["release_posture"] == "REVIEW_REQUIRED"
    assert summary["gate_counts"]["review"] >= 1
    assert summary["gate_counts"]["block"] == 0


def test_release_gate_fails_closed_on_person_level_column():
    policy = load_policy()
    slices = build_slice_assurance(policy)
    unsafe = pd.DataFrame({"employee_id": [1], "population": ["named person"]})
    gates = build_release_gates(policy, slices, unsafe).set_index("gate_id")
    assert gates.loc["HR-GOV-01", "status"] == "BLOCK"


def test_manifest_hashes_every_declared_artifact():
    manifest = json.loads((OUT / "responsible_use_manifest.json").read_text())
    for name, evidence in manifest["artifacts"].items():
        path = OUT / name
        assert path.exists()
        assert path.stat().st_size == evidence["bytes"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == evidence["sha256"]


def test_builder_is_byte_reproducible():
    build_all()
    first = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in OUT.glob("*responsible_use*")
    }
    build_all()
    second = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in OUT.glob("*responsible_use*")
    }
    assert first == second


def test_app_never_loads_individual_score_file():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "flight_risk_scores.csv" not in source
    assert "employee_id" not in source
    assert "employee_name" not in source


def test_app_exposes_release_packet_download():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "responsible_use_decision_packet.md" in source
    assert "download_button" in source
