"""
Feature store unit tests:
For each feature feature_spec.md designates as versioned:
- Register its versions
- Confirm each is independently retrievable by version number
- Confirm is_latest correctly identifies the highest version and not an earlier one
- Confirm list_versions returns every version with distinct parquet_path values that actually exist on disk.
"""
from __future__ import annotations

from pathlib import Path
import sqlite3
import pandas as pd
import pytest

from feature_store.store import (
    register_version,
    get_latest,
    get_version,
    list_versions,
    list_all_features,
    _init_registry,
)


@pytest.fixture
def temp_store(tmp_path):
    db_path = str(tmp_path / "test_registry.db")
    values_dir = str(tmp_path / "values")
    _init_registry(db_path)
    return {"db_path": db_path, "values_dir": values_dir}


@pytest.fixture
def sample_feature_df():
    return pd.DataFrame({
        "customer_id": [1, 2, 3],
        "txn_count_recent": [10, 0, 4],
        "as_of_date": ["2026-08-01 00:00:00"] * 3,
    })


def test_register_and_retrieve_all_versions_of_a_versioned_feature(temp_store, sample_feature_df):
    db = temp_store["db_path"]
    v_dir = temp_store["values_dir"]

    # Register v1
    v1_df = sample_feature_df.copy()
    v1 = register_version(
        feature_name="txn_count_recent",
        values_df=v1_df,
        description="v1 window 90d",
        source_columns="transactions.txn_timestamp",
        transform_summary="count 90d",
        business_rationale="quarterly trend",
        parameters={"window_days": 90},
        db_path=db,
        values_dir=v_dir,
    )
    assert v1 == 1

    # Register v2
    v2_df = sample_feature_df.copy()
    v2_df["txn_count_recent"] = [3, 0, 1]
    v2 = register_version(
        feature_name="txn_count_recent",
        values_df=v2_df,
        description="v2 window 30d",
        source_columns="transactions.txn_timestamp",
        transform_summary="count 30d",
        business_rationale="monthly trend",
        parameters={"window_days": 30},
        db_path=db,
        values_dir=v_dir,
    )
    assert v2 == 2

    # Independently retrieve v1 and v2
    retrieved_v1 = get_version("txn_count_recent", 1, db_path=db)
    retrieved_v2 = get_version("txn_count_recent", 2, db_path=db)

    assert retrieved_v1["txn_count_recent"].tolist() == [10, 0, 4]
    assert retrieved_v2["txn_count_recent"].tolist() == [3, 0, 1]


def test_is_latest_points_to_highest_version_not_an_earlier_one(temp_store, sample_feature_df):
    db = temp_store["db_path"]
    v_dir = temp_store["values_dir"]

    # Register v1
    register_version(
        feature_name="txn_count_recent",
        values_df=sample_feature_df,
        description="v1",
        source_columns="col",
        transform_summary="sum",
        business_rationale="v1",
        parameters={"w": 90},
        db_path=db,
        values_dir=v_dir,
    )
    latest_v1 = get_latest("txn_count_recent", db_path=db)
    assert latest_v1["txn_count_recent"].tolist() == [10, 0, 4]

    # Register v2
    v2_df = sample_feature_df.copy()
    v2_df["txn_count_recent"] = [99, 98, 97]
    register_version(
        feature_name="txn_count_recent",
        values_df=v2_df,
        description="v2",
        source_columns="col",
        transform_summary="sum",
        business_rationale="v2",
        parameters={"w": 30},
        db_path=db,
        values_dir=v_dir,
    )

    latest_v2 = get_latest("txn_count_recent", db_path=db)
    assert latest_v2["txn_count_recent"].tolist() == [99, 98, 97]

    # Verify directly in SQLite that exactly one row has is_latest = 1 and it is v2
    conn = sqlite3.connect(db)
    cursor = conn.cursor()
    cursor.execute("SELECT version, is_latest FROM feature_registry WHERE feature_name = 'txn_count_recent'")
    rows = cursor.fetchall()
    conn.close()

    assert len(rows) == 2
    row_dict = dict(rows)
    assert row_dict[1] == 0
    assert row_dict[2] == 1


def test_list_versions_returns_distinct_parquet_paths_that_exist(temp_store, sample_feature_df):
    db = temp_store["db_path"]
    v_dir = temp_store["values_dir"]

    # Register v1
    register_version(
        feature_name="total_spend_windowed",
        values_df=sample_feature_df.rename(columns={"txn_count_recent": "total_spend_windowed"}),
        description="v1",
        source_columns="amount",
        transform_summary="sum 90d",
        business_rationale="v1",
        parameters={"window_days": 90},
        db_path=db,
        values_dir=v_dir,
    )

    # Register v2
    register_version(
        feature_name="total_spend_windowed",
        values_df=sample_feature_df.rename(columns={"txn_count_recent": "total_spend_windowed"}),
        description="v2",
        source_columns="amount",
        transform_summary="sum 60d",
        business_rationale="v2",
        parameters={"window_days": 60},
        db_path=db,
        values_dir=v_dir,
    )

    versions_df = list_versions("total_spend_windowed", db_path=db)
    assert len(versions_df) == 2
    assert versions_df.iloc[0]["version"] == 2
    assert versions_df.iloc[1]["version"] == 1

    paths = versions_df["parquet_path"].tolist()
    assert len(paths) == len(set(paths)), "Parquet paths must be distinct"

    for p in paths:
        assert Path(p).exists(), f"Parquet file {p} must exist on disk"
