#!/usr/bin/env python3
"""
Builds features for the full training population as of a given date, writes a versioned
parquet feature snapshot, and registers every candidate feature into the feature store.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import pandas as pd

from features.build import build_features
from features.schema import FEATURE_SCHEMA
from features.quality_checks import run_all_checks
from feature_store.store import register_version, REGISTRY_DB


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--as-of",
        default="2026-08-01",
        help="As-of date for feature computation (default: 2026-08-01).",
    )
    parser.add_argument(
        "--output-snapshot",
        default="outputs/artifacts/training_features_snapshot.parquet",
        help="Path to save full training features parquet snapshot.",
    )
    args = parser.parse_args()

    print(f"Building training features as of {args.as_of}...")
    features_df = build_features(as_of=args.as_of)
    print(f"Built features for {len(features_df)} customers with {len(features_df.columns)} columns.")

    # 1. Run quality checks
    print("Running quality checks against built features...")
    # Read customer master count for reconciliation check
    customers_df = pd.read_csv("data/customers.csv")
    expected_count = len(customers_df)

    qc_summary = run_all_checks(
        features=features_df,
        expected_row_count=expected_count,
        raise_on_failure=True,
    )
    print("All quality checks passed successfully!")
    for check_name, res in qc_summary["checks"].items():
        print(f"  - {check_name}: {res['message']}")

    # 2. Save full feature dataset snapshot to outputs/artifacts
    output_path = Path(args.output_snapshot)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    features_df.to_parquet(output_path, index=False, engine="pyarrow")
    print(f"Saved full feature dataset snapshot to {output_path}")

    # 3. Register baseline (v1) for every candidate feature in feature_store
    print("\nRegistering v1 for all candidate features in feature store...")
    schema_map = {f.name: f for f in FEATURE_SCHEMA}

    for feature_spec in FEATURE_SCHEMA:
        fname = feature_spec.name
        v = register_version(
            feature_name=fname,
            values_df=features_df,
            description=feature_spec.description,
            source_columns=feature_spec.source_columns,
            transform_summary=feature_spec.transform_summary,
            business_rationale=feature_spec.business_rationale,
            parameters=feature_spec.parameters,
        )
        print(f"  Registered {fname} as version {v}")

    # 4. Perform the Spec-Defined Versioning Exercise for versioned features
    # Feature 1: txn_count_recent (v1: 90d, v2: 30d)
    print("\nRegistering v2 for txn_count_recent (window_days=30)...")
    v2_txn_count_df = build_features(as_of=args.as_of, txn_count_window_days=30)
    v_txn2 = register_version(
        feature_name="txn_count_recent",
        values_df=v2_txn_count_df,
        description="Count of transactions in the trailing 30 days [as_of - 30d, as_of].",
        source_columns="data/transactions.db:transactions.txn_timestamp",
        transform_summary="Count of transactions where as_of - window_days <= txn_timestamp <= as_of (window_days=30). Default: 0.",
        business_rationale="v1 (90d) captured quarterly trends, but v2 (30d) was added to catch immediate disengagement prior to monthly renewal cycles.",
        parameters={"window_days": 30},
    )
    print(f"  Registered txn_count_recent v{v_txn2}")

    # Feature 2: total_spend_windowed (v1: 90d, v2: 60d)
    print("\nRegistering v2 for total_spend_windowed (window_days=60)...")
    v2_spend_df = build_features(as_of=args.as_of, spend_window_days=60)
    v_spend2 = register_version(
        feature_name="total_spend_windowed",
        values_df=v2_spend_df,
        description="Sum of transaction amounts in the trailing 60 days [as_of - 60d, as_of].",
        source_columns="data/transactions.db:transactions.amount,txn_timestamp",
        transform_summary="Sum of amount where as_of - window_days <= txn_timestamp <= as_of (window_days=60). Default: 0.0.",
        business_rationale="v1 (90d) smoothed variance, while v2 (60d) aligns closer to two billing cycles to flag rapid monetary drops earlier.",
        parameters={"window_days": 60},
    )
    print(f"  Registered total_spend_windowed v{v_spend2}")

    print("\nTraining feature build and registration complete.")


if __name__ == "__main__":
    main()
