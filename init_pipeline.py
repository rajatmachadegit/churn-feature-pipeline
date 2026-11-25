import os
import shutil
from pathlib import Path
import pandas as pd
from features.build import build_features
from features.schema import FEATURE_SCHEMA
from features.quality_checks import run_all_checks
from feature_store.store import register_version, _init_registry
import scripts.compare_feature_versions as cfv

def main():
    print("Executing full feature pipeline initialization...")
    as_of = "2026-08-01"

    # 1. Clean feature store if needed
    if os.path.exists("feature_store/registry.db"):
        os.remove("feature_store/registry.db")
    if os.path.exists("feature_store/values"):
        shutil.rmtree("feature_store/values")

    _init_registry()

    # 2. Build training features as of 2026-08-01
    print(f"Building features as of {as_of}...")
    features_df = build_features(as_of=as_of)
    print(f"Features built: {len(features_df)} rows, {len(features_df.columns)} columns.")

    # 3. Run Quality Checks
    print("Running quality checks...")
    customers_df = pd.read_csv("data/customers.csv")
    qc = run_all_checks(features_df, expected_row_count=len(customers_df), raise_on_failure=True)
    print("Quality checks passed!")

    # 4. Save training snapshot
    snapshot_path = Path("outputs/artifacts/training_features_snapshot.parquet")
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    features_df.to_parquet(snapshot_path, index=False, engine="pyarrow")
    print(f"Saved snapshot to {snapshot_path}")

    # 5. Register v1 for all candidate features in feature store
    for fspec in FEATURE_SCHEMA:
        v = register_version(
            feature_name=fspec.name,
            values_df=features_df,
            description=fspec.description,
            source_columns=fspec.source_columns,
            transform_summary=fspec.transform_summary,
            business_rationale=fspec.business_rationale,
            parameters=fspec.parameters,
        )
        print(f"Registered {fspec.name} v{v}")

    # 6. Versioning Exercise: Register v2 for versioned features
    # txn_count_recent: v2 (window=30)
    v2_txn = build_features(as_of=as_of, txn_count_window_days=30)
    v2_txn_v = register_version(
        feature_name="txn_count_recent",
        values_df=v2_txn,
        description="Count of transactions in the trailing 30 days [as_of - 30d, as_of].",
        source_columns="data/transactions.db:transactions.txn_timestamp",
        transform_summary="Count of transactions where as_of - window_days <= txn_timestamp <= as_of (window_days=30). Default: 0.",
        business_rationale="v1 (90d) captured quarterly trends, but v2 (30d) was added to catch immediate disengagement prior to monthly renewal cycles.",
        parameters={"window_days": 30},
    )
    print(f"Registered txn_count_recent v{v2_txn_v}")

    # total_spend_windowed: v2 (window=60)
    v2_spend = build_features(as_of=as_of, spend_window_days=60)
    v2_spend_v = register_version(
        feature_name="total_spend_windowed",
        values_df=v2_spend,
        description="Sum of transaction amounts in the trailing 60 days [as_of - 60d, as_of].",
        source_columns="data/transactions.db:transactions.amount,txn_timestamp",
        transform_summary="Sum of amount where as_of - window_days <= txn_timestamp <= as_of (window_days=60). Default: 0.0.",
        business_rationale="v1 (90d) smoothed variance, while v2 (60d) aligns closer to two billing cycles to flag rapid monetary drops earlier.",
        parameters={"window_days": 60},
    )
    print(f"Registered total_spend_windowed v{v2_spend_v}")

    # 7. Run compare_feature_versions script
    print("Running version comparison...")
    cfv.main()
    print("All tasks completed successfully!")

if __name__ == "__main__":
    main()
