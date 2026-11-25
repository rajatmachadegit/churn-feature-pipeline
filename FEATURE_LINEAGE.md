# FEATURE_LINEAGE.md — Complete Feature Lineage Documentation

## 1. Overview & Architecture

This document provides complete, reproducible end-to-end lineage tracking for every candidate feature engineered in the customer churn feature pipeline across all registered versions. 

Every entry documents:
1. **Source System & Grain**: Source file/table, grain, and physical columns used.
2. **Transformation & Zero-Activity Handling**: Exact mathematical formulas and deterministic default imputation logic for the 81 zero-transaction customers.
3. **Behavioral Rationale**: Why this feature predicts customer churn distinct from confounds.
4. **Version Parameters**: Version-specific hyperparameter values and business justifications for version bumps.
5. **Feature Store Location**: Physical SQLite registry metadata row (`feature_store/registry.db`, table `feature_registry`) and immutable Parquet snapshot path (`feature_store/values/<feature_name>__v<version>.parquet`).

---

## 2. Feature Lineage Entries by Feature & Version

### 2.1 Feature: `days_since_last_txn`

#### Version 1 (Current Latest: `is_latest = 1`)
* **Feature Name**: `days_since_last_txn`
* **Version**: `1`
* **Created At**: `2026-08-01T00:00:00Z`
* **Feature Store Parquet Snapshot**: [`feature_store/values/days_since_last_txn__v1.parquet`](feature_store/values/days_since_last_txn__v1.parquet)
* **Registry Database**: `feature_store/registry.db` (`feature_registry` table)
* **Source(s)**:
  * Primary: `data/transactions.db` (Table: `transactions`, Columns: `customer_id`, `txn_timestamp`)
  * Default Source: `data/customers.csv` (Columns: `customer_id`, `signup_date`)
* **Computation / Formula**:
  $$\text{days\_since\_last\_txn} = \frac{\text{as\_of} - \max(\text{txn\_timestamp})}{86400.0} \quad \text{for } \text{txn\_timestamp} \le \text{as\_of}$$
* **Zero-Activity Default**:
  $$\text{Customer Account Tenure (days)} = \frac{\text{as\_of} - \text{signup\_date}}{86400.0}$$
  *Applied to the 81 customers with zero recorded transactions to reflect total customer lifetime without purchasing, preventing false nulls or sentinel bias.*
* **Business & Behavioral Rationale**:
  Recency is the single strongest behavioral indicator of defection. Customers who haven't transacted recently exhibit declining brand affinity and higher risk of migrating to competitors, distinct from baseline low spend since a high-value customer may suddenly halt purchases.
* **Tunable Parameters**: `{}` (No window parameters; lifetime recency up to `as_of`).

---

### 2.2 Feature: `txn_count_recent`

#### Version 1 (`is_latest = 0`)
* **Feature Name**: `txn_count_recent`
* **Version**: `1`
* **Created At**: `2026-08-01T00:00:00Z`
* **Feature Store Parquet Snapshot**: [`feature_store/values/txn_count_recent__v1.parquet`](feature_store/values/txn_count_recent__v1.parquet)
* **Registry Database**: `feature_store/registry.db`
* **Source(s)**: `data/transactions.db` (Table: `transactions`, Columns: `customer_id`, `txn_timestamp`)
* **Computation / Formula**:
  $$\text{txn\_count\_recent} = \sum \mathbf{1}_{\{\text{as\_of} - 90\text{d} \le \text{txn\_timestamp} \le \text{as\_of}\}}$$
* **Zero-Activity Default**: `0`
* **Business & Behavioral Rationale**:
  Measures quarterly engagement frequency. A drop in quarterly transaction velocity captures macro habituation decay, distinguishing regular buyers from churned accounts.
* **Tunable Parameters**: `{"window_days": 90}`

#### Version 2 (Current Latest: `is_latest = 1`)
* **Feature Name**: `txn_count_recent`
* **Version**: `2`
* **Created At**: `2026-08-01T00:00:00Z`
* **Feature Store Parquet Snapshot**: [`feature_store/values/txn_count_recent__v2.parquet`](feature_store/values/txn_count_recent__v2.parquet)
* **Registry Database**: `feature_store/registry.db`
* **Source(s)**: `data/transactions.db` (Table: `transactions`, Columns: `customer_id`, `txn_timestamp`)
* **Computation / Formula**:
  $$\text{txn\_count\_recent} = \sum \mathbf{1}_{\{\text{as\_of} - 30\text{d} \le \text{txn\_timestamp} \le \text{as\_of}\}}$$
* **Zero-Activity Default**: `0`
* **Business Reason for Version Bump**:
  v1 (90-day lookback) smoothed quarterly trends but diluted short-term disengagement. v2 (30-day window) was introduced to catch abrupt behavioral halts immediately prior to monthly recurring subscription renewal deadlines.
* **Tunable Parameters**: `{"window_days": 30}`

---

### 2.3 Feature: `total_spend_windowed`

#### Version 1 (`is_latest = 0`)
* **Feature Name**: `total_spend_windowed`
* **Version**: `1`
* **Created At**: `2026-08-01T00:00:00Z`
* **Feature Store Parquet Snapshot**: [`feature_store/values/total_spend_windowed__v1.parquet`](feature_store/values/total_spend_windowed__v1.parquet)
* **Registry Database**: `feature_store/registry.db`
* **Source(s)**: `data/transactions.db` (Table: `transactions`, Columns: `customer_id`, `amount`, `txn_timestamp`)
* **Computation / Formula**:
  $$\text{total\_spend\_windowed} = \sum_{\text{as\_of} - 90\text{d} \le \text{txn\_timestamp} \le \text{as\_of}} \text{amount}$$
* **Zero-Activity Default**: `0.0`
* **Business & Behavioral Rationale**:
  Measures immediate quarterly revenue generation and wallet share. Declining short-term spend reflects reduced reliance on the merchant, distinct from historical customer lifetime value.
* **Tunable Parameters**: `{"window_days": 90}`

#### Version 2 (Current Latest: `is_latest = 1`)
* **Feature Name**: `total_spend_windowed`
* **Version**: `2`
* **Created At**: `2026-08-01T00:00:00Z`
* **Feature Store Parquet Snapshot**: [`feature_store/values/total_spend_windowed__v2.parquet`](feature_store/values/total_spend_windowed__v2.parquet)
* **Registry Database**: `feature_store/registry.db`
* **Source(s)**: `data/transactions.db` (Table: `transactions`, Columns: `customer_id`, `amount`, `txn_timestamp`)
* **Computation / Formula**:
  $$\text{total\_spend\_windowed} = \sum_{\text{as\_of} - 60\text{d} \le \text{txn\_timestamp} \le \text{as\_of}} \text{amount}$$
* **Zero-Activity Default**: `0.0`
* **Business Reason for Version Bump**:
  v1 (90-day window) masked early revenue decay. v2 (60-day window) aligns directly with two consecutive billing/invoicing cycles, flagging steep monetary drops 30 days earlier while remaining robust against single-transaction variance.
* **Tunable Parameters**: `{"window_days": 60}`

---

### 2.4 Feature: `avg_monthly_spend_l12m`

#### Version 1 (Current Latest: `is_latest = 1`)
* **Feature Name**: `avg_monthly_spend_l12m`
* **Version**: `1`
* **Created At**: `2026-08-01T00:00:00Z`
* **Feature Store Parquet Snapshot**: [`feature_store/values/avg_monthly_spend_l12m__v1.parquet`](feature_store/values/avg_monthly_spend_l12m__v1.parquet)
* **Registry Database**: `feature_store/registry.db`
* **Source(s)**: `data/transactions_monthly_agg.parquet` (Columns: `customer_id`, `txn_month`, `total_amount`)
* **Computation / Formula**:
  $$\text{avg\_monthly\_spend\_l12m} = \frac{\sum_{m=1}^{12} \text{total\_amount}_m}{12.0} \quad \text{for } \text{trunc\_month}(\text{as\_of}) - 12\text{m} \le \text{txn\_month} < \text{trunc\_month}(\text{as\_of})$$
* **Zero-Activity Default**: `0.0`
* **Business & Behavioral Rationale**:
  Establishes annualized monetary baseline to normalize short-term volatility. Distinguishes structurally high-value customers experiencing a temporary lull from historically low-spend accounts.
* **Tunable Parameters**: `{"months": 12}`

---

### 2.5 Feature: `active_months_l12m`

#### Version 1 (Current Latest: `is_latest = 1`)
* **Feature Name**: `active_months_l12m`
* **Version**: `1`
* **Created At**: `2026-08-01T00:00:00Z`
* **Feature Store Parquet Snapshot**: [`feature_store/values/active_months_l12m__v1.parquet`](feature_store/values/active_months_l12m__v1.parquet)
* **Registry Database**: `feature_store/registry.db`
* **Source(s)**: `data/transactions_monthly_agg.parquet` (Columns: `customer_id`, `txn_month`, `txn_count`)
* **Computation / Formula**:
  $$\text{active\_months\_l12m} = \text{Count of unique } \text{txn\_month} \text{ with } \text{txn\_count} > 0 \text{ in } [\text{trunc\_month}(\text{as\_of}) - 12\text{m}, \text{trunc\_month}(\text{as\_of}))$$
* **Zero-Activity Default**: `0`
* **Business & Behavioral Rationale**:
  Measures habituation and account stickiness across calendar cycles. Customers transacting in 10-12 distinct months demonstrate ingrained product dependence compared to sporadic, one-time purchasers.
* **Tunable Parameters**: `{"months": 12}`

---

### 2.6 Feature: `return_rate_recent`

#### Version 1 (Current Latest: `is_latest = 1`)
* **Feature Name**: `return_rate_recent`
* **Version**: `1`
* **Created At**: `2026-08-01T00:00:00Z`
* **Feature Store Parquet Snapshot**: [`feature_store/values/return_rate_recent__v1.parquet`](feature_store/values/return_rate_recent__v1.parquet)
* **Registry Database**: `feature_store/registry.db`
* **Source(s)**: `data/transactions.db` (Table: `transactions`, Columns: `customer_id`, `is_returned`, `txn_timestamp`)
* **Computation / Formula**:
  $$\text{return\_rate\_recent} = \begin{cases} \frac{\sum \text{is\_returned}}{\text{txn\_count\_recent}}, & \text{if } \text{txn\_count\_recent} > 0 \\ 0.0, & \text{otherwise} \end{cases}$$
  over trailing 90 days $[\text{as\_of} - 90\text{d}, \text{as\_of}]$.
* **Zero-Activity Default**: `0.0`
* **Business & Behavioral Rationale**:
  Direct proxy for customer dissatisfaction, defective fulfillment, or buyer remorse. Customers experiencing repeated returns often disengage and churn immediately following negative resolution experiences.
* **Tunable Parameters**: `{"window_days": 90}`

---

### 2.7 Feature: `customer_tenure_days`

#### Version 1 (Current Latest: `is_latest = 1`)
* **Feature Name**: `customer_tenure_days`
* **Version**: `1`
* **Created At**: `2026-08-01T00:00:00Z`
* **Feature Store Parquet Snapshot**: [`feature_store/values/customer_tenure_days__v1.parquet`](feature_store/values/customer_tenure_days__v1.parquet)
* **Registry Database**: `feature_store/registry.db`
* **Source(s)**: `data/customers.csv` (Columns: `customer_id`, `signup_date`)
* **Computation / Formula**:
  $$\text{customer\_tenure\_days} = \frac{\text{as\_of} - \text{signup\_date}}{86400.0}$$
* **Zero-Activity Default**: Non-null by construction (every customer in `customers.csv` has a valid `signup_date`).
* **Business & Behavioral Rationale**:
  Tenure captures cohort maturity. Newer cohorts typically experience a steep initial drop-off ("onboarding cliff"), whereas long-tenured accounts have established relationships and lower baseline churn probabilities.
* **Tunable Parameters**: `{}`

---

## 3. Lineage Summary Matrix

| Feature Name | Version | Source | Grain | Lookback Parameter | Default | Is Latest | Parquet Path |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `days_since_last_txn` | v1 | `transactions.db` | Event | None (Max) | Account Tenure | 1 | `feature_store/values/days_since_last_txn__v1.parquet` |
| `txn_count_recent` | v1 | `transactions.db` | Event | 90 days | 0 | 0 | `feature_store/values/txn_count_recent__v1.parquet` |
| `txn_count_recent` | v2 | `transactions.db` | Event | 30 days | 0 | 1 | `feature_store/values/txn_count_recent__v2.parquet` |
| `total_spend_windowed`| v1 | `transactions.db` | Event | 90 days | 0.0 | 0 | `feature_store/values/total_spend_windowed__v1.parquet` |
| `total_spend_windowed`| v2 | `transactions.db` | Event | 60 days | 0.0 | 1 | `feature_store/values/total_spend_windowed__v2.parquet` |
| `avg_monthly_spend_l12m`| v1 | `monthly_agg.parquet` | Monthly | 12 completed months | 0.0 | 1 | `feature_store/values/avg_monthly_spend_l12m__v1.parquet` |
| `active_months_l12m` | v1 | `monthly_agg.parquet` | Monthly | 12 completed months | 0 | 1 | `feature_store/values/active_months_l12m__v1.parquet` |
| `return_rate_recent` | v1 | `transactions.db` | Event | 90 days | 0.0 | 1 | `feature_store/values/return_rate_recent__v1.parquet` |
| `customer_tenure_days`| v1 | `customers.csv` | Entity | Account lifetime | Non-null | 1 | `feature_store/values/customer_tenure_days__v1.parquet` |
