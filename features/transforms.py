"""
One pure function per candidate feature named in your confirmed `feature_spec.md`.

Each function:
- Is independent of any I/O (takes already-loaded DataFrames in, returns a Series/DataFrame out).
- Handles the zero-activity case explicitly, per the default feature_spec.md states.
- Only touches the source(s) feature_spec.md names for that feature.
"""

from __future__ import annotations

import pandas as pd
import numpy as np


def compute_customer_tenure_days(
    customers: pd.DataFrame,
    as_of: pd.Timestamp,
) -> pd.Series:
    """Feature: customer_tenure_days
    Source: data/customers.csv (signup_date)
    Computation: (as_of - signup_date) in fractional days (total_seconds / 86400.0)
    Zero-activity default: Non-null by construction.
    """
    tenure_seconds = (as_of - pd.to_datetime(customers["signup_date"])).dt.total_seconds()
    tenure_days = tenure_seconds / 86400.0
    return pd.Series(tenure_days.values, index=customers["customer_id"], name="customer_tenure_days", dtype="float64")


def compute_days_since_last_txn(
    customers: pd.DataFrame,
    transactions: pd.DataFrame,
    as_of: pd.Timestamp,
) -> pd.Series:
    """Feature: days_since_last_txn
    Source: data/transactions.db (txn_timestamp)
    Computation: (as_of - max(txn_timestamp)) / 86400.0 where txn_timestamp <= as_of
    Zero-activity default: Customer account tenure in fractional days: (as_of - signup_date) / 86400.0
    """
    # 1. Compute tenure default for all customers
    tenure = compute_customer_tenure_days(customers, as_of)

    # 2. Filter transactions strictly upstream to <= as_of
    valid_txns = transactions[transactions["txn_timestamp"] <= as_of]

    if valid_txns.empty:
        return tenure.rename("days_since_last_txn")

    # 3. Max txn_timestamp per customer
    last_txns = valid_txns.groupby("customer_id")["txn_timestamp"].max()
    days_since = (as_of - last_txns).dt.total_seconds() / 86400.0

    # 4. Align to customer index and fill missing (zero activity) with tenure
    result = tenure.copy()
    result.loc[days_since.index] = days_since
    return result.rename("days_since_last_txn").astype("float64")


def compute_txn_count_recent(
    customers: pd.DataFrame,
    transactions: pd.DataFrame,
    as_of: pd.Timestamp,
    window_days: int = 90,
) -> pd.Series:
    """Feature: txn_count_recent
    Source: data/transactions.db (txn_timestamp)
    Computation: Count of transactions where as_of - window_days <= txn_timestamp <= as_of
    Zero-activity default: 0
    """
    start_window = as_of - pd.Timedelta(days=window_days)
    in_window = transactions[
        (transactions["txn_timestamp"] >= start_window) &
        (transactions["txn_timestamp"] <= as_of)
    ]
    counts = in_window.groupby("customer_id")["txn_timestamp"].count()
    result = pd.Series(0, index=customers["customer_id"], name="txn_count_recent", dtype="int64")
    result.loc[counts.index] = counts
    return result.astype("int64")


def compute_total_spend_windowed(
    customers: pd.DataFrame,
    transactions: pd.DataFrame,
    as_of: pd.Timestamp,
    window_days: int = 90,
) -> pd.Series:
    """Feature: total_spend_windowed
    Source: data/transactions.db (amount, txn_timestamp)
    Computation: Sum of amount where as_of - window_days <= txn_timestamp <= as_of
    Zero-activity default: 0.0
    """
    start_window = as_of - pd.Timedelta(days=window_days)
    in_window = transactions[
        (transactions["txn_timestamp"] >= start_window) &
        (transactions["txn_timestamp"] <= as_of)
    ]
    spend = in_window.groupby("customer_id")["amount"].sum()
    result = pd.Series(0.0, index=customers["customer_id"], name="total_spend_windowed", dtype="float64")
    result.loc[spend.index] = spend
    return result.astype("float64")


def compute_avg_monthly_spend_l12m(
    customers: pd.DataFrame,
    monthly_agg: pd.DataFrame,
    as_of: pd.Timestamp,
    months: int = 12,
) -> pd.Series:
    """Feature: avg_monthly_spend_l12m
    Source: data/transactions_monthly_agg.parquet (total_amount, txn_month)
    Computation: sum(total_amount) / 12.0 over trailing 12 completed calendar months prior to as_of
    Zero-activity default: 0.0
    """
    # Completed months: txn_month must be strictly less than trunc_month(as_of)
    # Start: trunc_month(as_of) - 12 months
    month_start_as_of = as_of.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    start_month = month_start_as_of - pd.DateOffset(months=months)

    in_window = monthly_agg[
        (monthly_agg["txn_month"] >= start_month) &
        (monthly_agg["txn_month"] < month_start_as_of)
    ]
    total_spend = in_window.groupby("customer_id")["total_amount"].sum()
    avg_spend = total_spend / float(months)

    result = pd.Series(0.0, index=customers["customer_id"], name="avg_monthly_spend_l12m", dtype="float64")
    result.loc[avg_spend.index] = avg_spend
    return result.astype("float64")


def compute_active_months_l12m(
    customers: pd.DataFrame,
    monthly_agg: pd.DataFrame,
    as_of: pd.Timestamp,
    months: int = 12,
) -> pd.Series:
    """Feature: active_months_l12m
    Source: data/transactions_monthly_agg.parquet (txn_count, txn_month)
    Computation: Count of distinct completed calendar months with txn_count > 0 in trailing 12 months
    Zero-activity default: 0
    """
    month_start_as_of = as_of.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    start_month = month_start_as_of - pd.DateOffset(months=months)

    in_window = monthly_agg[
        (monthly_agg["txn_month"] >= start_month) &
        (monthly_agg["txn_month"] < month_start_as_of) &
        (monthly_agg["txn_count"] > 0)
    ]
    active_counts = in_window.groupby("customer_id")["txn_month"].nunique()

    result = pd.Series(0, index=customers["customer_id"], name="active_months_l12m", dtype="int64")
    result.loc[active_counts.index] = active_counts
    return result.astype("int64")


def compute_return_rate_recent(
    customers: pd.DataFrame,
    transactions: pd.DataFrame,
    as_of: pd.Timestamp,
    window_days: int = 90,
) -> pd.Series:
    """Feature: return_rate_recent
    Source: data/transactions.db (is_returned, txn_timestamp)
    Computation: sum(is_returned) / txn_count_recent in trailing window. If txn_count_recent == 0, returns 0.0.
    Zero-activity default: 0.0
    """
    start_window = as_of - pd.Timedelta(days=window_days)
    in_window = transactions[
        (transactions["txn_timestamp"] >= start_window) &
        (transactions["txn_timestamp"] <= as_of)
    ]
    if in_window.empty:
        return pd.Series(0.0, index=customers["customer_id"], name="return_rate_recent", dtype="float64")

    grouped = in_window.groupby("customer_id")
    total_txns = grouped["txn_timestamp"].count()
    returned_txns = grouped["is_returned"].sum()

    rate = (returned_txns / total_txns).fillna(0.0)

    result = pd.Series(0.0, index=customers["customer_id"], name="return_rate_recent", dtype="float64")
    result.loc[rate.index] = rate
    return result.astype("float64")
