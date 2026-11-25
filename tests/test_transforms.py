"""
Unit tests for each feature function in features/transforms.py in isolation.

Exercises:
- Normal case (customer with normal transaction history)
- Zero-activity case (customer with zero transactions returns explicit spec default, not NaN)
- Single-record case (customer with exactly one transaction)
- Time-window boundary case (transaction exactly at window cutoff)
"""
from __future__ import annotations

import pandas as pd
import numpy as np
import pytest

from features.transforms import (
    compute_customer_tenure_days,
    compute_days_since_last_txn,
    compute_txn_count_recent,
    compute_total_spend_windowed,
    compute_avg_monthly_spend_l12m,
    compute_active_months_l12m,
    compute_return_rate_recent,
)


@pytest.fixture
def mock_customers():
    return pd.DataFrame({
        "customer_id": [1, 2, 3],
        "signup_date": pd.to_datetime(["2025-01-01", "2025-06-01", "2026-01-01"]),
        "acquisition_channel": ["organic", "paid_search", "referral"],
        "region": ["east", "west", "north"],
        "churned": [0, 1, 0],
    })


@pytest.fixture
def mock_transactions():
    # Customer 1: multiple transactions
    # Customer 2: single transaction exactly at 90 days boundary (2026-05-03 00:00:00 for as_of 2026-08-01 00:00:00)
    # Customer 3: zero transactions
    return pd.DataFrame({
        "customer_id": [1, 1, 1, 2],
        "txn_timestamp": pd.to_datetime([
            "2026-07-20 10:00:00",
            "2026-06-15 12:00:00",
            "2026-04-01 09:00:00",  # outside 90d window for as_of 2026-08-01
            "2026-05-03 00:00:00",  # exactly at 90d boundary: 2026-08-01 - 90d = 2026-05-03
        ]),
        "amount": [100.0, 50.0, 200.0, 75.0],
        "is_returned": [0, 1, 0, 0],
    })


@pytest.fixture
def mock_monthly_agg():
    # Customer 1: active 6 months
    # Customer 2: active 1 month
    # Customer 3: zero activity
    return pd.DataFrame({
        "customer_id": [1, 1, 1, 1, 1, 1, 2],
        "txn_month": pd.to_datetime([
            "2026-07-01", "2026-06-01", "2026-05-01",
            "2026-04-01", "2026-03-01", "2026-02-01",
            "2026-05-01"
        ]),
        "txn_count": [2, 1, 3, 2, 1, 4, 1],
        "total_amount": [150.0, 50.0, 300.0, 200.0, 80.0, 420.0, 75.0],
        "return_count": [0, 1, 0, 0, 0, 0, 0],
    })


def test_customer_tenure_days(mock_customers):
    as_of = pd.Timestamp("2026-08-01 00:00:00")
    tenure = compute_customer_tenure_days(mock_customers, as_of)
    assert len(tenure) == 3
    assert not tenure.isnull().any()
    # Customer 1 signup 2025-01-01 to 2026-08-01: 577 days
    assert abs(tenure.loc[1] - 577.0) < 1e-2


def test_normal_case(mock_customers, mock_transactions, mock_monthly_agg):
    as_of = pd.Timestamp("2026-08-01 00:00:00")
    # Customer 1 normal history
    txn_count = compute_txn_count_recent(mock_customers, mock_transactions, as_of, window_days=90)
    assert txn_count.loc[1] == 2  # July 20 and June 15 inside 90d

    spend = compute_total_spend_windowed(mock_customers, mock_transactions, as_of, window_days=90)
    assert spend.loc[1] == 150.0  # 100 + 50

    return_rate = compute_return_rate_recent(mock_customers, mock_transactions, as_of, window_days=90)
    assert return_rate.loc[1] == 0.5  # 1 returned out of 2 txns

    avg_spend = compute_avg_monthly_spend_l12m(mock_customers, mock_monthly_agg, as_of, months=12)
    assert avg_spend.loc[1] == (150.0 + 50.0 + 300.0 + 200.0 + 80.0 + 420.0) / 12.0

    active_m = compute_active_months_l12m(mock_customers, mock_monthly_agg, as_of, months=12)
    assert active_m.loc[1] == 6


def test_zero_activity_case(mock_customers, mock_transactions, mock_monthly_agg):
    as_of = pd.Timestamp("2026-08-01 00:00:00")
    # Customer 3 has 0 transactions
    txn_count = compute_txn_count_recent(mock_customers, mock_transactions, as_of, window_days=90)
    assert txn_count.loc[3] == 0

    spend = compute_total_spend_windowed(mock_customers, mock_transactions, as_of, window_days=90)
    assert spend.loc[3] == 0.0

    return_rate = compute_return_rate_recent(mock_customers, mock_transactions, as_of, window_days=90)
    assert return_rate.loc[3] == 0.0

    avg_spend = compute_avg_monthly_spend_l12m(mock_customers, mock_monthly_agg, as_of, months=12)
    assert avg_spend.loc[3] == 0.0

    active_m = compute_active_months_l12m(mock_customers, mock_monthly_agg, as_of, months=12)
    assert active_m.loc[3] == 0

    # Days since last txn should equal tenure for zero activity
    days_since = compute_days_since_last_txn(mock_customers, mock_transactions, as_of)
    tenure = compute_customer_tenure_days(mock_customers, as_of)
    assert abs(days_since.loc[3] - tenure.loc[3]) < 1e-4


def test_single_record_case(mock_customers, mock_transactions, mock_monthly_agg):
    as_of = pd.Timestamp("2026-08-01 00:00:00")
    # Customer 2 has 1 record
    txn_count = compute_txn_count_recent(mock_customers, mock_transactions, as_of, window_days=90)
    assert txn_count.loc[2] == 1

    spend = compute_total_spend_windowed(mock_customers, mock_transactions, as_of, window_days=90)
    assert spend.loc[2] == 75.0

    return_rate = compute_return_rate_recent(mock_customers, mock_transactions, as_of, window_days=90)
    assert return_rate.loc[2] == 0.0


def test_time_window_boundary_case(mock_customers, mock_transactions):
    as_of = pd.Timestamp("2026-08-01 00:00:00")
    # Customer 2 txn at 2026-05-03 00:00:00 is exactly as_of - 90d
    # With window_days=90: start = 2026-05-03 00:00:00 -> included
    txn_count_90 = compute_txn_count_recent(mock_customers, mock_transactions, as_of, window_days=90)
    assert txn_count_90.loc[2] == 1

    # With window_days=89: start = 2026-05-04 00:00:00 -> excluded
    txn_count_89 = compute_txn_count_recent(mock_customers, mock_transactions, as_of, window_days=89)
    assert txn_count_89.loc[2] == 0
