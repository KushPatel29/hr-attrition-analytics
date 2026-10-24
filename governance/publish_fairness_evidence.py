"""Keep the public fairness example tied to the actual synthetic audit counts.

Run after fairness_audit.py. --write updates the versioned evidence and README;
the default check fails when the source counts or public example have drifted.
This does not change the audit thresholds or authorize an employment decision.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
START = "<!-- fairness-evidence:start -->"
END = "<!-- fairness-evidence:end -->"


def build_evidence(root=ROOT):
    source = root / "output/fairness_audit.csv"
    policy = json.loads((root / "governance/responsible_use_policy.json").read_text(encoding="utf-8"))
    source_text = source.read_text(encoding="utf-8")
    rows = list(csv.DictReader(source_text.splitlines()))
    indexed = {(r["attribute"], r["group"]): r for r in rows}
    warnings = []
    for row in rows:
        if row["verdict"] == "pass":
            continue
        ref = indexed[(row["attribute"], row["reference_group"])]
        warnings.append({
            "attribute": row["attribute"], "group": row["group"],
            "n": int(row["n"]), "n_high": int(row["n_high"]),
            "reference_group": row["reference_group"],
            "reference_n": int(ref["n"]), "reference_n_high": int(ref["n_high"]),
            "di_ratio": float(row["di_ratio"]), "p_value": float(row["p_value"]),
            "verdict": row["verdict"],
        })
    populations = {attr: sum(int(r["n"]) for r in rows if r["attribute"] == attr)
                   for attr in {r["attribute"] for r in rows}}
    if len(set(populations.values())) != 1:
        raise ValueError("Fairness attributes must cover the same scored population")
    return {
        "schema_version": 1, "snapshot_date": policy["snapshot_date"],
        "data_classification": "synthetic", "scored_population": next(iter(populations.values())),
        "source": {"path": "output/fairness_audit.csv",
                   "hash_normalization": "UTF-8 with CRLF normalized to LF",
                   "sha256": hashlib.sha256(source_text.encode("utf-8")).hexdigest()},
        "screen": {"ratio_band": policy["four_fifths_band"],
                   "minimum_group_n": policy["minimum_publishable_group"],
                   "significance_level": 0.05},
        "warnings": warnings,
        "interpretation": "A non-significant result does not establish the absence of bias. Unresolved disparities remain visible for monitoring and human review.",
        "authority": "Synthetic model-screening evidence only; no employment action or legal compliance conclusion is authorized.",
    }


def render_markdown(evidence):
    lines = [START, f"**Current synthetic snapshot: {evidence['snapshot_date']} · "
             f"{evidence['scored_population']:,} scored people.**", "",
             "| Monitored / unresolved group | High-risk flags | Reference flags | Ratio | Fisher p |",
             "|---|---:|---:|---:|---:|"]
    for row in evidence["warnings"]:
        lines.append(f"| {row['attribute']}: {row['group']} | {row['n_high']} / {row['n']} | "
                     f"{row['reference_group']}: {row['reference_n_high']} / {row['reference_n']:,} | "
                     f"{row['di_ratio']:.3f} | {row['p_value']:.4f} |")
    if not evidence["warnings"]:
        lines.append("| No unresolved group in this snapshot | — | — | — | — |")
    lines += ["", evidence["interpretation"], "",
              "The [versioned evidence](output/fairness_evidence.json) records the source CSV hash, "
              "snapshot, counts and screening policy. Rebuild with "
              "`python governance/publish_fairness_evidence.py --write`; CI checks for drift.", END]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    evidence = build_evidence()
    target = ROOT / "output/fairness_evidence.json"
    expected_json = json.dumps(evidence, ensure_ascii=False, indent=2) + "\n"
    readme = ROOT / "README.md"
    text = readme.read_text(encoding="utf-8")
    if text.count(START) != 1 or text.count(END) != 1:
        raise SystemExit("README must contain exactly one fairness-evidence block")
    before, rest = text.split(START, 1)
    _, after = rest.split(END, 1)
    expected_readme = before + render_markdown(evidence) + after
    if args.write:
        target.write_text(expected_json, encoding="utf-8")
        readme.write_text(expected_readme, encoding="utf-8")
        print("Updated fairness evidence and README from the committed audit counts")
    else:
        if not target.exists() or target.read_text(encoding="utf-8") != expected_json or text != expected_readme:
            raise SystemExit("Fairness narrative/evidence drift: run governance/publish_fairness_evidence.py --write")
        print("Fairness source counts, evidence and README agree; uncertainty remains explicit")


if __name__ == "__main__":
    main()
