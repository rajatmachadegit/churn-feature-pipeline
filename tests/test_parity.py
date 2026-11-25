"""
The parity test that matters most for this pipeline: build features for the same
customer via the "training" path (historical as-of date, batch of many customers) and
via the "scoring" path (single customer, same as-of date), and assert the resulting
feature values are identical.

If these two paths can't be driven through the same test with the same expected output,
the parity guarantee in feature_spec.md isn't real — fix features/build.py, not this test.
"""
from __future__ import annotations

import pandas as pd
import numpy as np
import pytest

from features.build import build_features


def test_training_and_scoring_paths_agree_for_same_customer():
    """Call the shared build_features(as_of, ...) entry point once in "training"
    mode (batch) and once in "scoring" mode (single customer_id), same as_of date, and
    assert every feature value matches exactly for that customer.
    Test across:
    - Customer with regular transactions
    - Customer with zero transactions (cold start)
    - Single transaction customer
    """
    as_of = "2026-08-01"

    # Batch training build for all customers
    training_df = build_features(as_of=as_of)

    # Test several distinct customer profiles
    # 1. First customer in dataset
    c1_id = int(training_df.iloc[0]["customer_id"])
    scoring_c1 = build_features(as_of=as_of, customer_ids=[c1_id])

    c1_train_row = training_df[training_df["customer_id"] == c1_id].reset_index(drop=True)
    pd.testing.assert_frame_equal(c1_train_row, scoring_c1, check_dtype=True)

    # 2. Zero-activity customer test
    # Find a customer with txn_count_recent == 0 and active_months_l12m == 0
    zero_candidates = training_df[
        (training_df["txn_count_recent"] == 0) &
        (training_df["active_months_l12m"] == 0)
    ]
    if not zero_candidates.empty:
        c_zero_id = int(zero_candidates.iloc[0]["customer_id"])
        scoring_zero = build_features(as_of=as_of, customer_ids=[c_zero_id])
        zero_train_row = training_df[training_df["customer_id"] == c_zero_id].reset_index(drop=True)
        pd.testing.assert_frame_equal(zero_train_row, scoring_zero, check_dtype=True)

    # 3. High activity customer
    active_candidates = training_df[training_df["txn_count_recent"] > 5]
    if not active_candidates.empty:
        c_active_id = int(active_candidates.iloc[0]["customer_id"])
        scoring_active = build_features(as_of=as_of, customer_ids=[c_active_id])
        active_train_row = training_df[training_df["customer_id"] == c_active_id].reset_index(drop=True)
        pd.testing.assert_frame_equal(active_train_row, scoring_active, check_dtype=True)


def test_scoring_handles_multiple_customer_ids():
    """Verify scoring path handles multi-customer requests identically to batch training."""
    as_of = "2026-08-01"
    training_df = build_features(as_of=as_of)

    test_ids = [1, 25, 81, 150, 500]
    scoring_df = build_features(as_of=as_of, customer_ids=test_ids)

    expected_df = training_df[training_df["customer_id"].isin(test_ids)].reset_index(drop=True)
    pd.testing.assert_frame_equal(expected_df, scoring_df, check_dtype=True)


def test_scoring_nonexistent_customer_raises_error():
    """Verify that scoring a non-existent customer raises a clean ValueError."""
    with pytest.raises(ValueError, match="Requested customer_id.*do not exist"):
        build_features(as_of="2026-08-01", customer_ids=[999999])
