# ARTIFACT_NOTES.md — Engineering Critique & Implementation Log

## 1. Initial Oversights, Corrections & Self-Critique

In compliance with `skill.md`'s production-readiness mandate, the following design decisions, implementation pitfalls, and edge-case corrections were navigated during the development of the churn feature pipeline:

### 1.1 Zero-Activity Default for `days_since_last_txn`
* **Initial Consideration**: Setting `days_since_last_txn = -1.0` or a high arbitrary sentinel like `999.0` for customers with 0 transaction records.
* **Why It Was Rejected**: Artificial sentinels distort linear and tree-based distance metrics, create discontinuous feature splits, and violate `feature_spec.md`'s explicit contract.
* **Adopted Implementation**: Computed customer tenure (`as_of - signup_date`) as the natural zero-activity default. For a customer who has never transacted since onboarding, their elapsed duration without a transaction is identically equal to their entire account lifetime. This provides a strictly continuous, monotonic, and mathematically justifiable signal.

### 1.2 Temporal Boundary & Data Leakage Prevention in Monthly Aggregates
* **Initial Consideration**: Including `txn_month == trunc_month(as_of)` in `avg_monthly_spend_l12m` and `active_months_l12m`.
* **Why It Was Rejected**: At `as_of = 2026-08-01 00:00:00`, the calendar month of August 2026 has either just begun or is incomplete. Including the current month creates partial-month bias and risks temporal target leakage when evaluating historical cohorts.
* **Adopted Implementation**: Enforced a strict half-open completed calendar month window:
  `[trunc_month(as_of) - 12 months, trunc_month(as_of))`. Only the 12 fully finalized calendar months prior to `as_of` are aggregated.

### 1.3 As-Of Date Threading vs. Hardcoded Fallbacks
* **Initial Consideration**: Relying on default `as_of` values deep within individual transform functions.
* **Why It Was Rejected**: Hidden defaults inside transform functions inevitably lead to train/score skew when scoring requests pass dynamic timestamps.
* **Adopted Implementation**: `as_of` is accepted as a parameter in `build_features` and explicitly threaded as a `pd.Timestamp` to every transform function in `features/transforms.py`. All raw data filtering occurs upstream of any aggregation.

### 1.4 Atomic Feature Store Version Invariant & `is_latest` Management
* **Initial Consideration**: Using simple file writes without database transactions, potentially leaving SQLite out of sync if Parquet serialization failed.
* **Why It Was Rejected**: A failure during Parquet writing could leave the registry pointing to missing files, or multiple rows marked `is_latest = 1`.
* **Adopted Implementation**: Parquet snapshots are written first with collision checks (`FileExistsError` if the version file exists), followed by an atomic SQLite transaction that flips previous `is_latest = 0` and inserts the new version with `is_latest = 1`. `store.py` ensures that `get_latest` always returns the highest registered version.

---

## 2. Source Data Quality Observations (Confirmed on Real Data)

During Step 0 ingestion validation of the actual raw data:
1. **Cold-Start Inactive Cohort**: Confirmed that exactly 81 of the 1,500 customers in `customers.csv` have zero records in `transactions.db` and zero rows in `transactions_monthly_agg.parquet`. All zero-activity defaults successfully prevent `NaN` leakage across the entire feature matrix.
2. **Key Consistency**: `customer_id` is cleanly formatted across all three sources with zero unparseable keys.
3. **Monetary Non-Negativity**: Confirmed that all transactions have `amount >= 0.0`.
