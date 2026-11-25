"""
Pure I/O loaders for the three heterogeneous raw sources described in
`data_dictionary.md`. No feature logic belongs here — only loading and basic
type coercion, so ingestion can be unit-tested and swapped independently of
`transforms.py`.
"""

from __future__ import annotations

from pathlib import Path
import sqlite3
import pandas as pd


def load_customers(path: str = "data/customers.csv") -> pd.DataFrame:
    """Load customers.csv.

    - Read CSV with pandas.
    - Parse `signup_date` as a datetime (date).
    - Ensure customer_id is int.
    - Return one row per customer_id, unmodified otherwise.
    """
    df = pd.read_csv(path)
    df["customer_id"] = df["customer_id"].astype(int)
    df["signup_date"] = pd.to_datetime(df["signup_date"])
    return df


def load_transactions(path: str = "data/transactions.db") -> pd.DataFrame:
    """Load the row-level `transactions` table from the SQLite database.

    - Connect with sqlite3 against `path`.
    - Cast `txn_timestamp` to a real datetime (SQLite stores it as ISO-8601 text).
    - Cast `is_returned` to a clean 0/1 int.
    - Return the full row-level frame — do not aggregate here.
    """
    conn = sqlite3.connect(path)
    try:
        df = pd.read_sql_query("SELECT customer_id, txn_timestamp, amount, is_returned FROM transactions", conn)
    finally:
        conn.close()

    df["customer_id"] = df["customer_id"].astype(int)
    df["txn_timestamp"] = pd.to_datetime(df["txn_timestamp"])
    df["amount"] = df["amount"].astype(float)
    df["is_returned"] = df["is_returned"].astype(int)
    return df


def load_monthly_agg(path: str = "data/transactions_monthly_agg.parquet") -> pd.DataFrame:
    """Load the pre-aggregated customer x month parquet extract.

    - Read the parquet file with pandas.
    - Parse `txn_month` as a datetime (first-of-month).
    - Return as-is — remember customers/months with zero activity have no row.
    """
    df = pd.read_parquet(path)
    df["customer_id"] = df["customer_id"].astype(int)
    df["txn_month"] = pd.to_datetime(df["txn_month"])
    df["txn_count"] = df["txn_count"].astype(int)
    df["total_amount"] = df["total_amount"].astype(float)
    df["return_count"] = df["return_count"].astype(int)
    return df
