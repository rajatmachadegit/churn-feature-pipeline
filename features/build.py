"""
The ONE shared feature-build entry point. Both `scripts/build_training_features.py`
(training path: a historical as-of date, batch of many customers) and
`scripts/score_customer.py` (scoring path: single customer_id, same as-of date) must call
this same function — that is the entire train/score parity guarantee for this pipeline.

There must be exactly one code path here. If you find yourself writing separate logic for
"training mode" vs. "scoring mode" beyond which rows they select at the end, that is a
parity bug — go back and unify it rather than special-casing either path.
"""

from __future__ import annotations

from pathlib import Path
import pandas as pd

from features import ingest, transforms


DEFAULT_SOURCE_PATHS = {
    "customers": "data/customers.csv",
    "transactions": "data/transactions.db",
    "monthly_agg": "data/transactions_monthly_agg.parquet",
}


def build_features(
    as_of: str,
    source_paths: dict | None = None,
    customer_ids: list[int] | None = None,
    txn_count_window_days: int = 90,
    spend_window_days: int = 90,
    return_rate_window_days: int = 90,
    avg_spend_months: int = 12,
    active_months_l12m_count: int = 12,
) -> pd.DataFrame:
    """Build the full feature set as of `as_of` for either the whole customer base
    (training path, `customer_ids=None`) or a specific subset (scoring path, one or more
    `customer_ids`).

    Parameters
    ----------
    as_of : str
        As-of timestamp / date string (e.g. '2026-08-01' or '2026-08-01 00:00:00').
    source_paths : dict, optional
        Dictionary mapping 'customers', 'transactions', 'monthly_agg' to file paths.
    customer_ids : list[int], optional
        If provided, filter output features to these specific customer IDs.
        This filtering is the ONLY difference allowed between the training and scoring call sites.
    """
    paths = {**DEFAULT_SOURCE_PATHS, **(source_paths or {})}
    as_of_ts = pd.to_datetime(as_of)

    # Ingest data via pure loaders
    customers_df = ingest.load_customers(paths["customers"])
    transactions_df = ingest.load_transactions(paths["transactions"])
    monthly_agg_df = ingest.load_monthly_agg(paths["monthly_agg"])

    # If customer_ids requested in scoring mode, check that requested customer_ids exist in customers
    if customer_ids is not None:
        missing_ids = set(customer_ids) - set(customers_df["customer_id"])
        if missing_ids:
            raise ValueError(f"Requested customer_id(s) do not exist in customer master: {sorted(missing_ids)}")

    # Compute candidate features (pure functions on customer master)
    tenure_s = transforms.compute_customer_tenure_days(customers_df, as_of_ts)
    days_since_s = transforms.compute_days_since_last_txn(customers_df, transactions_df, as_of_ts)
    txn_count_s = transforms.compute_txn_count_recent(customers_df, transactions_df, as_of_ts, window_days=txn_count_window_days)
    spend_s = transforms.compute_total_spend_windowed(customers_df, transactions_df, as_of_ts, window_days=spend_window_days)
    avg_spend_s = transforms.compute_avg_monthly_spend_l12m(customers_df, monthly_agg_df, as_of_ts, months=avg_spend_months)
    active_m_s = transforms.compute_active_months_l12m(customers_df, monthly_agg_df, as_of_ts, months=active_months_l12m_count)
    return_rate_s = transforms.compute_return_rate_recent(customers_df, transactions_df, as_of_ts, window_days=return_rate_window_days)

    features_df = pd.DataFrame({
        "customer_id": customers_df["customer_id"].values,
        "as_of_date": as_of_ts.strftime("%Y-%m-%d %H:%M:%S"),
        "days_since_last_txn": days_since_s.values,
        "txn_count_recent": txn_count_s.values,
        "total_spend_windowed": spend_s.values,
        "avg_monthly_spend_l12m": avg_spend_s.values,
        "active_months_l12m": active_m_s.values,
        "return_rate_recent": return_rate_s.values,
        "customer_tenure_days": tenure_s.values,
    })

    # The ONLY difference between training and scoring call sites: filter to customer_ids if provided
    if customer_ids is not None:
        features_df = features_df[features_df["customer_id"].isin(customer_ids)].reset_index(drop=True)

    return features_df
