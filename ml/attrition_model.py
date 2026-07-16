"""
Flight-risk model — predicts which employees are likely to leave.

Trains on the SQL-built feature view (output/flight_risk_features.csv), runs an
honest three-way bake-off, evaluates on a held-out set, then scores the
currently active workforce and attaches a plain-English reason for each
high-risk employee.

Design choices worth calling out (the honest-model story):
  * Baseline first. A prevalence DummyClassifier sets the floor an ML model
    has to beat to be worth shipping.
  * The winner is picked on held-out ROC-AUC, but when logistic regression is
    within 0.01 AUC of the random forest we ship the logistic model, because a
    people-analytics score that a partner has to defend needs per-feature
    reasons, not a black box.
  * A pytest gate (tests/test_ml_model.py) fails the build if the chosen model
    does not clear 0.70 AUC and beat the baseline — so "the model works" stays
    true on every push, not just today.

Outputs (output/):
    flight_risk_scores.csv   employee_id, risk_score, risk_band, top_reason
    model_evaluation.csv     per-model roc_auc / pr_auc / lift@decile
    feature_importance.csv   standardized driver weights of the chosen model

Usage:
    python ml/attrition_model.py
"""

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "output"

NUMERIC = [
    "tenure_months", "compa_ratio", "performance_rating", "engagement_score",
    "overtime_hours", "commute_km", "months_since_promotion", "level_rank",
    "engagement_vs_dept", "comp_gap_vs_level",
]
# Protected attributes (gender, ethnicity_group, age_band) are deliberately
# NOT features. An HR risk score must not learn from who someone is — and
# "we never showed the model gender" is only half the defense, because other
# features can proxy for it. The other half is ml/fairness_audit.py, which
# measures the *outcome*: high-risk selection rates across protected groups,
# checked against the 80% disparate-impact rule on every run.
CATEGORICAL = ["department", "division", "region"]

# Human-readable driver phrasing for the top-reason explainability.
REASON_TEXT = {
    "tenure_months": "early tenure",
    "engagement_score": "low engagement",
    "engagement_vs_dept": "engagement below dept peers",
    "compa_ratio": "paid below market",
    "comp_gap_vs_level": "paid below level peers",
    "months_since_promotion": "overdue for promotion",
    "overtime_hours": "high overtime",
    "commute_km": "long commute",
    "performance_rating": "performance rating",
    "level_rank": "seniority level",
}

RANDOM_STATE = 29


def load_features() -> pd.DataFrame:
    df = pd.read_csv(OUT / "flight_risk_features.csv")
    return df


def lift_at_decile(y_true: np.ndarray, scores: np.ndarray, decile: float = 0.10) -> float:
    """Positive rate in the top-`decile` scored / overall positive rate."""
    n_top = max(1, int(len(scores) * decile))
    order = np.argsort(-scores)
    top_rate = y_true[order[:n_top]].mean()
    base = y_true.mean()
    return float(top_rate / base) if base > 0 else float("nan")


def build_preprocessor() -> ColumnTransformer:
    return ColumnTransformer([
        ("num", StandardScaler(), NUMERIC),
        ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL),
    ])


def evaluate_models(X_train, X_test, y_train, y_test) -> tuple[dict, dict]:
    models = {
        "Baseline (prevalence)": DummyClassifier(strategy="prior"),
        "Logistic Regression": Pipeline([
            ("prep", build_preprocessor()),
            ("clf", LogisticRegression(max_iter=2000, class_weight="balanced")),
        ]),
        "Random Forest": Pipeline([
            ("prep", build_preprocessor()),
            ("clf", RandomForestClassifier(
                n_estimators=300, max_depth=8, min_samples_leaf=20,
                class_weight="balanced", random_state=RANDOM_STATE, n_jobs=-1)),
        ]),
    }

    results = {}
    fitted = {}
    for name, model in models.items():
        model.fit(X_train, y_train)
        proba = model.predict_proba(X_test)[:, 1]
        results[name] = {
            "roc_auc": roc_auc_score(y_test, proba),
            "pr_auc": average_precision_score(y_test, proba),
            "lift_at_decile": lift_at_decile(y_test.values, proba),
        }
        fitted[name] = model
    return results, fitted


def choose_model(results: dict) -> str:
    """Pick on held-out ROC-AUC, but prefer the explainable logistic model
    when it is within 0.01 AUC of the random forest."""
    contenders = {k: v for k, v in results.items() if k != "Baseline (prevalence)"}
    best = max(contenders, key=lambda k: contenders[k]["roc_auc"])
    lr = "Logistic Regression"
    if best == "Random Forest" and (results["Random Forest"]["roc_auc"]
                                    - results[lr]["roc_auc"]) < 0.01:
        return lr
    return best


def feature_names(preprocessor: ColumnTransformer) -> list[str]:
    names = list(NUMERIC)
    ohe = preprocessor.named_transformers_["cat"]
    names += list(ohe.get_feature_names_out(CATEGORICAL))
    return names


def top_reasons_logistic(model: Pipeline, active: pd.DataFrame) -> pd.Series:
    """Per-employee dominant positive risk driver = argmax(x_std * coef)."""
    prep = model.named_steps["prep"]
    clf = model.named_steps["clf"]
    X = prep.transform(active)
    if hasattr(X, "toarray"):
        X = X.toarray()
    contrib = X * clf.coef_[0]                        # signed contribution per feature
    names = feature_names(prep)
    # Map one-hot columns back to their base feature for readable reasons.
    base = []
    for nm in names:
        root = nm
        for cat in CATEGORICAL:
            if nm.startswith(cat + "_"):
                root = cat
                break
        base.append(root)
    base = np.array(base)

    reasons = []
    for i in range(X.shape[0]):
        row = contrib[i]
        idx = int(np.argmax(row))
        if row[idx] <= 0:
            reasons.append("mixed factors")
            continue
        root = base[idx]
        reasons.append(REASON_TEXT.get(root, root.replace("_", " ")))
    return pd.Series(reasons, index=active.index)


def assign_bands(scores: pd.Series) -> pd.Series:
    """High = top 15% of scored risk, Medium = next 25%, Low = rest."""
    hi = scores.quantile(0.85)
    md = scores.quantile(0.60)
    return pd.cut(scores, bins=[-np.inf, md, hi, np.inf],
                 labels=["Low", "Medium", "High"])


def main() -> dict:
    df = load_features()
    X = df[NUMERIC + CATEGORICAL]
    y = df["left_flag"]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.30, stratify=y, random_state=RANDOM_STATE)

    results, fitted = evaluate_models(X_train, X_test, y_train, y_test)
    chosen = choose_model(results)

    # Persist evaluation table.
    eval_rows = [
        {"model": name, "roc_auc": round(r["roc_auc"], 4),
         "pr_auc": round(r["pr_auc"], 4),
         "lift_at_decile": round(r["lift_at_decile"], 3),
         "is_chosen": int(name == chosen)}
        for name, r in results.items()
    ]
    pd.DataFrame(eval_rows).to_csv(OUT / "model_evaluation.csv", index=False)

    # Refit chosen model on all data, then score the active workforce.
    model = fitted[chosen]
    model.fit(X, y)
    active = df[df["is_active"] == 1].copy()
    active_scores = model.predict_proba(active[NUMERIC + CATEGORICAL])[:, 1]
    active["risk_score"] = np.round(active_scores, 4)
    active["risk_band"] = assign_bands(active["risk_score"])

    if chosen == "Logistic Regression":
        active["top_reason"] = top_reasons_logistic(model, active[NUMERIC + CATEGORICAL])
        # Standardized coefficient importances.
        prep = model.named_steps["prep"]
        coef = model.named_steps["clf"].coef_[0]
        imp = (pd.DataFrame({"feature": feature_names(prep),
                             "weight": coef, "abs_weight": np.abs(coef)})
               .sort_values("abs_weight", ascending=False))
    else:
        active["top_reason"] = "see feature importances"
        prep = model.named_steps["prep"]
        importances = model.named_steps["clf"].feature_importances_
        imp = (pd.DataFrame({"feature": feature_names(prep),
                             "weight": importances, "abs_weight": importances})
               .sort_values("abs_weight", ascending=False))

    imp.round(4).to_csv(OUT / "feature_importance.csv", index=False)

    # Attach the (synthetic) employee name so the watch list reads like a real
    # worklist instead of a bare ID column.
    names = pd.read_csv(ROOT / "data" / "fact_employees.csv",
                        usecols=["employee_id", "employee_name"])
    active = active.merge(names, on="employee_id", how="left")

    scores_out = active[[
        "employee_id", "employee_name", "department", "job_level", "region",
        "tenure_months", "engagement_score",
        "risk_score", "risk_band", "top_reason",
    ]]
    scores_out.to_csv(OUT / "flight_risk_scores.csv", index=False)

    # ---- report ----
    print("FLIGHT-RISK MODEL BAKE-OFF (held-out 30%)")
    print("=" * 58)
    print(f"{'model':<24}{'ROC-AUC':>9}{'PR-AUC':>9}{'lift@10%':>10}")
    for name, r in results.items():
        mark = "  <- shipped" if name == chosen else ""
        print(f"{name:<24}{r['roc_auc']:>9.3f}{r['pr_auc']:>9.3f}"
              f"{r['lift_at_decile']:>10.2f}{mark}")
    print("-" * 58)
    band_counts = active["risk_band"].value_counts()
    print(f"Scored active employees : {len(active):>6,}")
    print(f"  High risk             : {int(band_counts.get('High', 0)):>6,}")
    print(f"  Medium risk           : {int(band_counts.get('Medium', 0)):>6,}")
    print(f"  Low risk              : {int(band_counts.get('Low', 0)):>6,}")
    print("Top drivers:", ", ".join(imp["feature"].head(5)))
    print("=" * 58)

    return {"results": results, "chosen": chosen, "scores": scores_out, "importance": imp}


if __name__ == "__main__":
    main()
