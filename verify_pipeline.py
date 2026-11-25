import sys
import pandas as pd
from features.build import build_features
from features.quality_checks import run_all_checks
from feature_store.store import register_version, get_version, get_latest, list_versions, list_all_features
from features.schema import FEATURE_SCHEMA

print("1. Testing ingest and build_features...")
as_of = "2026-08-01"
df = build_features(as_of)
print(f"Features shape: {df.shape}")
print(f"Columns: {list(df.columns)}")
print(f"Null count:\n{df.isnull().sum()}")

print("\n2. Testing quality checks...")
qc = run_all_checks(df, expected_row_count=1500, raise_on_failure=True)
print("QC passed successfully!")

print("\n3. Testing build_training_features registration...")
# Clean up any test DB if present
import os
import shutil
if os.path.exists("feature_store/registry.db"):
    os.remove("feature_store/registry.db")
if os.path.exists("feature_store/values"):
    shutil.rmtree("feature_store/values")

# Register baseline for all features
for fspec in FEATURE_SCHEMA:
    v = register_version(
        feature_name=fspec.name,
        values_df=df,
        description=fspec.description,
        source_columns=fspec.source_columns,
        transform_summary=fspec.transform_summary,
        business_rationale=fspec.business_rationale,
        parameters=fspec.parameters,
    )
    print(f"Registered {fspec.name} v{v}")

# Register v2 for txn_count_recent (window=30)
v2_txn = build_features(as_of=as_of, txn_count_window_days=30)
v2_txn_ver = register_version(
    feature_name="txn_count_recent",
    values_df=v2_txn,
    description="Count of transactions in the trailing 30 days [as_of - 30d, as_of].",
    source_columns="data/transactions.db:transactions.txn_timestamp",
    transform_summary="Count of transactions where as_of - window_days <= txn_timestamp <= as_of (window_days=30). Default: 0.",
    business_rationale="v1 (90d) captured quarterly trends, but v2 (30d) was added to catch immediate disengagement prior to monthly renewal cycles.",
    parameters={"window_days": 30},
)
print(f"Registered txn_count_recent v{v2_txn_ver}")

# Register v2 for total_spend_windowed (window=60)
v2_spend = build_features(as_of=as_of, spend_window_days=60)
v2_spend_ver = register_version(
    feature_name="total_spend_windowed",
    values_df=v2_spend,
    description="Sum of transaction amounts in the trailing 60 days [as_of - 60d, as_of].",
    source_columns="data/transactions.db:transactions.amount,txn_timestamp",
    transform_summary="Sum of amount where as_of - window_days <= txn_timestamp <= as_of (window_days=60). Default: 0.0.",
    business_rationale="v1 (90d) smoothed variance, while v2 (60d) aligns closer to two billing cycles to flag rapid monetary drops earlier.",
    parameters={"window_days": 60},
)
print(f"Registered total_spend_windowed v{v2_spend_ver}")

# Save snapshot
df.to_parquet("outputs/artifacts/training_features_snapshot.parquet", index=False)
print("Saved training_features_snapshot.parquet")

# Test compare_feature_versions script
import scripts.compare_feature_versions as cfv
cfv.main()

print("\nVerification script finished cleanly!")
