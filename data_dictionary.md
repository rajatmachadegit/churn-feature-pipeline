# Data Dictionary & Feature Proposal

## 1. Overview & Business Context

This document details the data assets and proposed feature definitions for predicting customer churn in a retail/subscription transaction environment.

The objective is to ingest heterogeneous data across flat files, relational tables, and columnar archives to engineer point-in-time correct customer-level features without data leakage, ensuring strict training/scoring parity and reproducible versioning.

---

## 2. Source Data Schemas, Grains & Relationships

### 2.1 `data/customers.csv`
* **Format**: Delimited Flat File (CSV, UTF-8)
* **Grain**: 1 row per unique `customer_id`
* **Total Records**: 1,500 customers (`customer_id` range: 1 to 1500)
* **Purpose**: Primary customer entity dimension containing static demographics, acquisition metadata, signup dates, and the target churn indicator.

| Column | Physical Type | Logical Type | Nullable | Description & Domain |
| :--- | :--- | :--- | :--- | :--- |
| `customer_id` | `INTEGER` | Entity Primary Key | No | Unique identifier for each customer (1 - 1500). |
| `signup_date` | `TEXT` (`YYYY-MM-DD`) | Date | No | Calendar date when the customer registered / opened their account. |
| `acquisition_channel` | `TEXT` | Categorical | No | Marketing acquisition source: `organic`, `paid_search`, `social`, `referral`. |
| `region` | `TEXT` | Categorical | No | Customer geographic sales region: `east`, `west`, `north`, `south`. |
| `churned` | `INTEGER` | Binary Target (0/1) | No | Ground truth churn outcome flag (1 = churned, 0 = active/retained). |

---

### 2.2 `data/transactions.db` (Table: `transactions`)
* **Format**: Relational SQLite 3 Database
* **Grain**: 1 row per transaction event (fine-grained operational event log)
* **Purpose**: Event-level ledger tracking individual transactions, exact timestamps, monetary values, and return events. Used for precise windowed metrics (e.g., recency, short-term velocity).

| Column | Physical Type | Logical Type | Nullable | Description & Domain |
| :--- | :--- | :--- | :--- | :--- |
| `customer_id` | `INTEGER` | Foreign Key | No | References `customers.customer_id`. |
| `txn_timestamp` | `TEXT` (ISO-8601) | Timestamp | No | Exact event timestamp (`YYYY-MM-DD HH:MM:SS` or UTC ISO format). |
| `amount` | `REAL` (`float64`) | Monetary / Continuous | No | Transaction gross monetary value in currency units. |
| `is_returned` | `INTEGER` | Binary Flag (0/1) | No | 1 if the transaction was subsequently refunded/returned, 0 otherwise. |

---

### 2.3 `data/transactions_monthly_agg.parquet`
* **Format**: Columnar Apache Parquet (Snappy compressed, PyArrow schema)
* **Grain**: 1 row per active `(customer_id, txn_month)` pair
* **Purpose**: Batch pre-aggregated monthly summary rolled up via warehouse ETL. Used for long-term consistency, trend, and tenure analysis. Note: Does not contain zero-activity customer months.

| Column | Physical Type | Logical Type | Nullable | Description & Domain |
| :--- | :--- | :--- | :--- | :--- |
| `customer_id` | `int64` | Foreign Key | No | References `customers.customer_id`. |
| `txn_month` | `timestamp[us]` | Calendar Month Start | No | Truncated month of activity (e.g., `2023-01-01 00:00:00`). |
| `txn_count` | `int64` | Discrete Metric | No | Total number of transactions executed in that calendar month. |
| `total_amount` | `double` (`float64`) | Monetary Metric | No | Total sum of transaction amounts during the calendar month. |
| `return_count` | `int64` | Discrete Metric | No | Total number of return events during that calendar month. |

---

## 3. Entity Relationships & Structural Linkages

```
  +--------------------------------+
  |      data/customers.csv        |
  |--------------------------------|
  | PK: customer_id (1,500 rows)   |
  +---------------+----------------+
                  |
         1-to-many| (0 to N records)
                  |
         +--------+----------------------------+
         |                                     |
         v                                     v
+-------------------------+       +------------------------------------+
|   data/transactions.db  |       | data/transactions_monthly_agg.pq   |
|   (table: transactions) |       |                                    |
|-------------------------|       |------------------------------------|
| FK: customer_id         |       | FK: customer_id                    |
| txn_timestamp           |       | txn_month                          |
| amount                  |       | txn_count, total_amount            |
| is_returned             |       | return_count                       |
+-------------------------+       +------------------------------------+
```

* **Join Keys**: `customer_id` is the uniform primary/foreign key across all sources.
* **Cardinality**:
  * `customers` to `transactions`: 1-to-Many (81 customers have 0 transactions; remaining customers have multiple).
  * `customers` to `transactions_monthly_agg`: 1-to-Many (only months with activity are present; inactive customers have 0 rows).

---

## 4. Observed Data Realities & Edge Cases

1. **Zero-Activity Customers (The "Cold-Start" Cohort)**:
   * Exactly 81 out of 1,500 customers in `customers.csv` have zero transaction history in either `transactions.db` or `transactions_monthly_agg.parquet`.
   * *Feature Pipeline Impact*: Left joins from `customers` onto aggregated transaction features will produce `NULL`/`NaN` for these customers. All features must specify robust, mathematically sensible defaults (e.g., default recency = tenure or sentinel value, transaction counts = 0, spend = 0.0, return rate = 0.0). Missing values must **never** be silently forwarded into model training or online scoring.

2. **Temporal Boundaries & Source Synchronization**:
   * `transactions.db` contains granular, second-level event records up to the ingestion boundary.
   * `transactions_monthly_agg.parquet` is pre-computed at calendar month boundaries (`txn_month`).
   * *Leakage & Parity Constraint*: All feature calculations must accept an arbitrary `as_of` timestamp. Event-level queries must filter `txn_timestamp <= as_of`. For monthly aggregations, only completed months preceding `as_of` (or partial months if cleanly windowed) can be utilized to prevent temporal target leakage.

3. **Monetary Distribution & Return Realities**:
   * Spend amounts are strictly non-negative and right-skewed.
   * `return_count` / `is_returned` requires careful denominator handling when computing return rates: if `txn_count == 0`, return rate must default to `0.0` rather than evaluating `0 / 0 = NaN`.

---

## 5. Candidate Churn Feature Proposal

The following candidate features are proposed for churn modeling across six behavioral dimensions:

### 5.1 Recency: `days_since_last_txn`
* **Source**: `data/transactions.db`
* **Definition / Formula**:
  $$\text{days\_since\_last\_txn} = \frac{\text{as\_of} - \max(\text{txn\_timestamp})}{86400}$$
  filtered to $\text{txn\_timestamp} \le \text{as\_of}$.
* **Zero-Activity Default**: Customer account age in days ($\text{as\_of} - \text{signup\_date}$) or fixed sentinel upper bound (e.g., $999.0$). *Recommended default: Account tenure in days, representing total time without purchasing.*
* **Behavioral Rationale**: Recency is historically the strongest predictor of customer defection; customers who haven't transacted in an extended period are far more likely to have churned.

### 5.2 Frequency: `txn_count_90d`
* **Source**: `data/transactions.db`
* **Definition / Formula**:
  $$\text{txn\_count\_90d} = \sum \mathbf{1}_{\{\text{as\_of} - 90\text{d} \le \text{txn\_timestamp} \le \text{as\_of}\}}$$
* **Zero-Activity Default**: `0`
* **Behavioral Rationale**: A drop in quarterly engagement directly signals waning interest or migration to competitors.

### 5.3 Monetary: `total_spend_90d`
* **Source**: `data/transactions.db`
* **Definition / Formula**:
  $$\text{total\_spend\_90d} = \sum_{\text{window}} \text{amount}$$
  over transactions in $[\text{as\_of} - 90\text{d}, \text{as\_of}]$.
* **Zero-Activity Default**: `0.0`
* **Behavioral Rationale**: Captures immediate revenue contribution and intensity of recent commercial relationship.

### 5.4 Monetary Intensity: `avg_monthly_spend_l12m`
* **Source**: `data/transactions_monthly_agg.parquet`
* **Definition / Formula**:
  $$\text{avg\_monthly\_spend\_l12m} = \frac{\sum_{m \in L12M} \text{total\_amount}}{12}$$
  where $L12M$ represents the 12 calendar months prior to `as_of`.
* **Zero-Activity Default**: `0.0`
* **Behavioral Rationale**: Distinguishes high-value accounts from low-tier purchasers over an extended baseline, smoothing out short-term seasonal spikes.

### 5.5 Consistency: `active_months_l12m`
* **Source**: `data/transactions_monthly_agg.parquet`
* **Definition / Formula**:
  $$\text{active\_months\_l12m} = \text{Count of distinct } \text{txn\_month} \text{ with } \text{txn\_count} > 0 \text{ in } L12M$$
* **Zero-Activity Default**: `0`
* **Behavioral Rationale**: Measures habituation and purchase regularity. Customers purchasing 10 out of 12 months exhibit high stickiness compared to sporadic one-off buyers.

### 5.6 Satisfaction / Risk: `return_rate_90d`
* **Source**: `data/transactions.db`
* **Definition / Formula**:
  $$\text{return\_rate\_90d} = \begin{cases} \frac{\sum \text{is\_returned}}{\text{txn\_count\_90d}}, & \text{if } \text{txn\_count\_90d} > 0 \\ 0.0, & \text{otherwise} \end{cases}$$
* **Zero-Activity Default**: `0.0`
* **Behavioral Rationale**: High return rates reflect customer dissatisfaction, defective products, or buyer remorse, often preceding churn.

### 5.7 Customer Profile: `customer_tenure_days`
* **Source**: `data/customers.csv`
* **Definition / Formula**:
  $$\text{customer\_tenure\_days} = \frac{\text{as\_of} - \text{signup\_date}}{86400}$$
* **Zero-Activity Default**: Non-null by construction (all customers have valid `signup_date`).
* **Behavioral Rationale**: Mature customer cohorts frequently exhibit structurally lower baseline churn rates than newly onboarded cohorts.

### 5.8 Marketing Segment: `acquisition_channel` & `region`
* **Source**: `data/customers.csv`
* **Definition / Formula**: Categorical attributes; one-hot encoded or label encoded for downstream modeling.
* **Zero-Activity Default**: Preserved from customer master table.
* **Behavioral Rationale**: Certain acquisition channels (e.g., social ads vs. organic referrals) carry inherently different long-term retention and lifetime value dynamics.

---

## 6. Parity & Production Delivery Strategy

1. **Unified Transformation Pipeline (`build_features`)**:
   * Both batch training feature generation and single-customer scoring will invoke `features/build.py::build_features(as_of, source_paths, customer_ids)`.
   * No logic divergence or dual-path transformations between offline training and real-time inference.

2. **Feature Store Lineage & Artifact Storage**:
   * Feature schemas and versions are registered in SQLite (`feature_store/registry.db`).
   * Materialized feature sets are persisted to Parquet (`feature_store/values/<feature_name>__v<version>.parquet`).
