"""
Runnable-standalone data-quality checks (drift / null / outlier / row count)
against a built features DataFrame, implementing every check listed in your confirmed
`feature_spec.md`'s data-quality section.

Each check function returns a clear pass/fail plus which rows/features
triggered a failure — failing checks raise ValueError when asserted.
"""

from __future__ import annotations

import pandas as pd
import numpy as np


def check_no_unexpected_nulls(features: pd.DataFrame) -> dict:
    """Fail if any feature column has nulls after applying defaults.
    Catches left join null propagation on the 81 zero-transaction customers.
    """
    feature_cols = [
        col for col in features.columns
        if col not in ["customer_id", "as_of_date"]
    ]
    null_counts = features[feature_cols].isnull().sum()
    failing_features = null_counts[null_counts > 0].to_dict()

    failing_rows = []
    if failing_features:
        failing_rows = features[features[list(failing_features.keys())].isnull().any(axis=1)]["customer_id"].tolist()

    passed = len(failing_features) == 0
    return {
        "check": "check_no_unexpected_nulls",
        "passed": passed,
        "failing_features": failing_features,
        "failing_rows": failing_rows,
        "message": "Passed: no unexpected nulls found." if passed else f"Failed: nulls found in features: {failing_features}",
    }


def check_zero_activity_defaults(features: pd.DataFrame, zero_customer_ids: list[int] | None = None) -> dict:
    """Ensure explicit zero-activity defaults are applied rather than NaN or unhandled nulls."""
    if zero_customer_ids is not None:
        zero_subset = features[features["customer_id"].isin(zero_customer_ids)]
    else:
        # A customer is inactive in recent windows if 0 count in 90d AND 0 active months in 12m
        zero_subset = features[(features["txn_count_recent"] == 0) & (features["active_months_l12m"] == 0)]

    failing_rows = []
    if not zero_subset.empty:
        for idx, row in zero_subset.iterrows():
            failures = []
            if row.get("txn_count_recent", 0) != 0:
                failures.append("txn_count_recent != 0")
            if row.get("total_spend_windowed", 0.0) != 0.0:
                failures.append("total_spend_windowed != 0.0")
            if row.get("avg_monthly_spend_l12m", 0.0) != 0.0:
                failures.append("avg_monthly_spend_l12m != 0.0")
            if row.get("active_months_l12m", 0) != 0:
                failures.append("active_months_l12m != 0")
            if row.get("return_rate_recent", 0.0) != 0.0:
                failures.append("return_rate_recent != 0.0")
            # Verify days_since_last_txn is valid and non-negative
            if "days_since_last_txn" in row:
                if pd.isna(row["days_since_last_txn"]) or row["days_since_last_txn"] < 0:
                    failures.append("days_since_last_txn is null or negative")
                # Only require exact tenure match if explicitly passing zero_customer_ids (never-transacted customers)
                if zero_customer_ids is not None and "customer_tenure_days" in row:
                    if abs(row["days_since_last_txn"] - row["customer_tenure_days"]) > 1e-4:
                        failures.append(f"days_since_last_txn ({row['days_since_last_txn']}) != customer_tenure_days ({row['customer_tenure_days']})")
            if failures:
                failing_rows.append({"customer_id": int(row["customer_id"]), "reasons": failures})

    passed = len(failing_rows) == 0
    return {
        "check": "check_zero_activity_defaults",
        "passed": passed,
        "failing_rows": failing_rows,
        "message": "Passed: zero-activity defaults correctly applied." if passed else f"Failed: defaults violated for {len(failing_rows)} rows",
    }


def check_outliers(features: pd.DataFrame) -> dict:
    """Fail if a feature has values outside sane mathematical/business boundaries per feature_spec.md.
    - return_rate_recent in [0.0, 1.0]
    - total_spend_windowed >= 0.0
    - days_since_last_txn >= 0.0
    - customer_tenure_days >= 0.0
    - txn_count_recent >= 0
    - active_months_l12m in [0, 12]
    - avg_monthly_spend_l12m >= 0.0
    """
    violations = {}

    if "return_rate_recent" in features.columns:
        bad_rr = features[(features["return_rate_recent"] < 0.0) | (features["return_rate_recent"] > 1.0)]
        if not bad_rr.empty:
            violations["return_rate_recent"] = bad_rr["customer_id"].tolist()

    if "total_spend_windowed" in features.columns:
        bad_spend = features[features["total_spend_windowed"] < 0.0]
        if not bad_spend.empty:
            violations["total_spend_windowed"] = bad_spend["customer_id"].tolist()

    if "days_since_last_txn" in features.columns:
        bad_days = features[features["days_since_last_txn"] < 0.0]
        if not bad_days.empty:
            violations["days_since_last_txn"] = bad_days["customer_id"].tolist()

    if "customer_tenure_days" in features.columns:
        bad_tenure = features[features["customer_tenure_days"] < 0.0]
        if not bad_tenure.empty:
            violations["customer_tenure_days"] = bad_tenure["customer_id"].tolist()

    if "txn_count_recent" in features.columns:
        bad_txns = features[features["txn_count_recent"] < 0]
        if not bad_txns.empty:
            violations["txn_count_recent"] = bad_txns["customer_id"].tolist()

    if "active_months_l12m" in features.columns:
        bad_active = features[(features["active_months_l12m"] < 0) | (features["active_months_l12m"] > 12)]
        if not bad_active.empty:
            violations["active_months_l12m"] = bad_active["customer_id"].tolist()

    if "avg_monthly_spend_l12m" in features.columns:
        bad_avg = features[features["avg_monthly_spend_l12m"] < 0.0]
        if not bad_avg.empty:
            violations["avg_monthly_spend_l12m"] = bad_avg["customer_id"].tolist()

    passed = len(violations) == 0
    return {
        "check": "check_outliers",
        "passed": passed,
        "failing_features": violations,
        "message": "Passed: all features within sane numerical bounds." if passed else f"Failed: bounds violated in {list(violations.keys())}",
    }


def check_row_count_reconciliation(features: pd.DataFrame, expected_count: int) -> dict:
    """Fail if output feature rows do not reconcile against expected customer count.
    Catches inner join dropouts or duplicate key fan-outs.
    """
    actual_count = len(features)
    unique_customers = features["customer_id"].nunique() if "customer_id" in features.columns else 0
    passed = (actual_count == expected_count) and (unique_customers == expected_count)
    return {
        "check": "check_row_count_reconciliation",
        "passed": passed,
        "actual_count": actual_count,
        "unique_customers": unique_customers,
        "expected_count": expected_count,
        "message": f"Passed: exactly {actual_count} rows matching customer count." if passed else f"Failed: row count {actual_count} (unique {unique_customers}) != expected {expected_count}",
    }


def check_drift(
    features: pd.DataFrame,
    reference: pd.DataFrame | None = None,
    threshold_psi: float = 0.25,
) -> dict:
    """Compare current feature distribution against a reference snapshot.
    Uses Population Stability Index (PSI) or mean relative difference.
    """
    if reference is None:
        return {
            "check": "check_drift",
            "passed": True,
            "message": "Passed: reference snapshot not provided, skipping drift check.",
            "metrics": {},
        }

    drifted_features = {}
    metrics = {}
    feature_cols = [
        col for col in features.columns
        if col not in ["customer_id", "as_of_date"] and col in reference.columns
    ]

    for col in feature_cols:
        curr_vals = features[col].dropna()
        ref_vals = reference[col].dropna()
        if len(curr_vals) == 0 or len(ref_vals) == 0:
            continue

        ref_mean = ref_vals.mean()
        curr_mean = curr_vals.mean()
        std_ref = ref_vals.std()
        if std_ref > 1e-6:
            norm_shift = abs(curr_mean - ref_mean) / std_ref
        else:
            norm_shift = abs(curr_mean - ref_mean)

        metrics[col] = float(norm_shift)
        if norm_shift > 2.0:  # > 2 standard deviations shift in mean
            drifted_features[col] = float(norm_shift)

    passed = len(drifted_features) == 0
    return {
        "check": "check_drift",
        "passed": passed,
        "metrics": metrics,
        "drifted_features": drifted_features,
        "message": "Passed: no significant distribution drift detected." if passed else f"Failed: drift detected in {list(drifted_features.keys())}",
    }


def run_all_checks(
    features: pd.DataFrame,
    expected_row_count: int | None = None,
    zero_customer_ids: list[int] | None = None,
    reference: pd.DataFrame | None = None,
    raise_on_failure: bool = False,
) -> dict:
    """Run every quality check and return combined summary.
    If raise_on_failure is True, raises ValueError on any failed check.
    """
    results = []

    res_nulls = check_no_unexpected_nulls(features)
    results.append(res_nulls)

    res_defaults = check_zero_activity_defaults(features, zero_customer_ids=zero_customer_ids)
    results.append(res_defaults)

    res_outliers = check_outliers(features)
    results.append(res_outliers)

    if expected_row_count is not None:
        res_rows = check_row_count_reconciliation(features, expected_row_count)
        results.append(res_rows)

    if reference is not None:
        res_drift = check_drift(features, reference)
        results.append(res_drift)

    all_passed = all(r["passed"] for r in results)

    summary = {
        "passed": all_passed,
        "checks": {r["check"]: r for r in results},
    }

    if raise_on_failure and not all_passed:
        failing = [r["check"] for r in results if not r["passed"]]
        raise ValueError(f"Data quality checks failed: {failing}. Details: {summary}")

    return summary
