"""
Quality check tests: feed each check in features/quality_checks.py a deliberately
bad input (injected null, out-of-range amount, shifted distribution) and confirm it fires;
feed it clean input and confirm it doesn't false-positive.
"""
from __future__ import annotations

import pandas as pd
import numpy as np
import pytest

from features.quality_checks import (
    check_no_unexpected_nulls,
    check_zero_activity_defaults,
    check_outliers,
    check_row_count_reconciliation,
    check_drift,
    run_all_checks,
)


@pytest.fixture
def clean_features():
    return pd.DataFrame({
        "customer_id": [1, 2, 3],
        "as_of_date": ["2026-08-01 00:00:00"] * 3,
        "days_since_last_txn": [12.5, 45.0, 500.0],
        "txn_count_recent": [5, 1, 0],
        "total_spend_windowed": [250.0, 75.0, 0.0],
        "avg_monthly_spend_l12m": [120.0, 30.0, 0.0],
        "active_months_l12m": [8, 3, 0],
        "return_rate_recent": [0.2, 0.0, 0.0],
        "customer_tenure_days": [600.0, 400.0, 500.0],
    })


def test_checks_do_not_false_positive_on_clean_input(clean_features):
    summary = run_all_checks(
        clean_features,
        expected_row_count=3,
        zero_customer_ids=[3],
        raise_on_failure=False,
    )
    assert summary["passed"] is True
    for check_name, res in summary["checks"].items():
        assert res["passed"] is True


def test_null_check_fires_on_injected_null(clean_features):
    bad_df = clean_features.copy()
    bad_df.loc[1, "avg_monthly_spend_l12m"] = np.nan
    res = check_no_unexpected_nulls(bad_df)
    assert res["passed"] is False
    assert "avg_monthly_spend_l12m" in res["failing_features"]
    assert 2 in res["failing_rows"]  # customer_id 2


def test_outlier_check_fires_on_out_of_range_value(clean_features):
    # Test negative spend
    bad_spend = clean_features.copy()
    bad_spend.loc[0, "total_spend_windowed"] = -50.0
    res_spend = check_outliers(bad_spend)
    assert res_spend["passed"] is False
    assert "total_spend_windowed" in res_spend["failing_features"]

    # Test return rate > 1.0
    bad_rr = clean_features.copy()
    bad_rr.loc[0, "return_rate_recent"] = 1.5
    res_rr = check_outliers(bad_rr)
    assert res_rr["passed"] is False
    assert "return_rate_recent" in res_rr["failing_features"]

    # Test negative days_since_last_txn
    bad_days = clean_features.copy()
    bad_days.loc[0, "days_since_last_txn"] = -2.0
    res_days = check_outliers(bad_days)
    assert res_days["passed"] is False
    assert "days_since_last_txn" in res_days["failing_features"]


def test_zero_activity_default_fires_on_bad_zero_handling(clean_features):
    bad_df = clean_features.copy()
    # Customer 3 has txn_count_recent == 0 but let's give them return_rate_recent != 0.0 or spend != 0
    bad_df.loc[2, "total_spend_windowed"] = 99.0
    res = check_zero_activity_defaults(bad_df, zero_customer_ids=[3])
    assert res["passed"] is False
    assert len(res["failing_rows"]) > 0


def test_row_count_reconciliation_fires_on_mismatch(clean_features):
    res = check_row_count_reconciliation(clean_features, expected_count=5)
    assert res["passed"] is False
    assert res["actual_count"] == 3
    assert res["expected_count"] == 5


def test_drift_check_fires_on_shifted_distribution(clean_features):
    ref_df = clean_features.copy()
    # Create severe distribution shift
    shifted_df = clean_features.copy()
    shifted_df["total_spend_windowed"] = [50000.0, 75000.0, 30000.0]

    res = check_drift(shifted_df, reference=ref_df)
    assert res["passed"] is False
    assert "total_spend_windowed" in res["drifted_features"]


def test_run_all_checks_raises_when_requested(clean_features):
    bad_df = clean_features.copy()
    bad_df.loc[0, "total_spend_windowed"] = -10.0
    with pytest.raises(ValueError, match="Data quality checks failed"):
        run_all_checks(bad_df, raise_on_failure=True)
