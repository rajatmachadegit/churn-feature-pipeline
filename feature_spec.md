# feature_spec.md — Churn Feature Pipeline

### Candidate features

* **Feature**: `days_since_last_txn`
  * **Source**: `data/transactions.db`
  * **Computation**: `(as_of_timestamp - max(txn_timestamp)) / 86400.0` (in fractional days) where `txn_timestamp <= as_of_timestamp`
  * **Zero-activity default**: Account tenure in fractional days: `(as_of_timestamp - signup_date_00:00:00) / 86400.0`
  * **If multiple sources could supply this, which and why?**: Chosen `transactions.db` for exact timestamp precision up to `as_of`.
  * **Rationale**: This predicts churn because customers who have not transacted recently tend to disengage, distinct from low spend because a high-value customer could simply have stopped buying.

* **Feature**: `txn_count_recent`
  * **Source**: `data/transactions.db`
  * **Computation**: Count of transactions in trailing window `[as_of - window_days, as_of]` (default `window_days = 90`)
  * **Zero-activity default**: `0`
  * **If multiple sources could supply this, which and why?**: Chosen `transactions.db` because rolling day-window precision beats calendar-truncated monthly aggregates.
  * **Rationale**: This predicts churn because a drop in recent transaction frequency signals waning habituation, distinct from baseline low spend since high-ticket buyers may buy infrequently.

* **Feature**: `total_spend_windowed`
  * **Source**: `data/transactions.db`
  * **Computation**: Sum of `amount` in trailing window `[as_of - window_days, as_of]` (default `window_days = 90`)
  * **Zero-activity default**: `0.0`
  * **If multiple sources could supply this, which and why?**: Chosen `transactions.db` to capture exact rolling monetary volume without monthly ETL lag.
  * **Rationale**: This predicts churn because declining short-term spend reflects immediate reduced wallet share, distinct from overall lifetime customer value.

* **Feature**: `avg_monthly_spend_l12m`
  * **Source**: `data/transactions_monthly_agg.parquet`
  * **Computation**: `sum(total_amount) / 12.0` over the trailing 12 completed calendar months prior to `as_of` (`trunc_month(as_of) - 12 months <= txn_month < trunc_month(as_of)`)
  * **Zero-activity default**: `0.0`
  * **If multiple sources could supply this, which and why?**: Chosen `transactions_monthly_agg.parquet` to leverage pre-aggregated monthly totals and avoid expensive row-level scans for long-term baselines.
  * **Rationale**: This predicts churn because it establishes baseline account value, distinguishing high-tier accounts from low-tier buyers while smoothing short-term seasonality.

* **Feature**: `active_months_l12m`
  * **Source**: `data/transactions_monthly_agg.parquet`
  * **Computation**: Count of distinct completed calendar months with `txn_count > 0` within `trunc_month(as_of) - 12 months <= txn_month < trunc_month(as_of)`
  * **Zero-activity default**: `0`
  * **If multiple sources could supply this, which and why?**: Chosen `transactions_monthly_agg.parquet` as monthly aggregation natively tracks active monthly buckets.
  * **Rationale**: This predicts churn because purchase regularity measures product stickiness; a customer active 10/12 months has higher retention habits regardless of total spend.

* **Feature**: `return_rate_recent`
  * **Source**: `data/transactions.db`
  * **Computation**: `sum(is_returned) / txn_count_recent` if `txn_count_recent > 0` else `0.0` within trailing 90 days `[as_of - 90d, as_of]`
  * **Zero-activity default**: `0.0`
  * **If multiple sources could supply this, which and why?**: Chosen `transactions.db` to maintain exact alignment with row-level return flags and the recent transaction window.
  * **Rationale**: This predicts churn because a rising return share signals customer dissatisfaction or buyer remorse, distinct from low engagement.

* **Feature**: `customer_tenure_days`
  * **Source**: `data/customers.csv`
  * **Computation**: `(as_of_timestamp - signup_date_00:00:00) / 86400.0` (in fractional days)
  * **Zero-activity default**: Non-null by construction (all customers in `customers.csv` have valid `signup_date`)
  * **If multiple sources could supply this, which and why?**: Only present in `customers.csv`.
  * **Rationale**: This predicts churn because mature customer cohorts exhibit structurally lower baseline churn rates than newly onboarded cohorts.

### Train/score parity design

* **Shared function/code path**: `features.build::build_features(as_of, source_paths=None, customer_ids=None)`
* **Only allowed training/scoring difference**: Filtering output by `customer_ids` at the end of the transformation pipeline
* **How as_of is threaded (not hardcoded)**: Passed as an explicit string/datetime parameter `as_of` into `build_features()`, applied as a strict upstream filter (`txn_timestamp <= as_of` and `txn_month < trunc_month(as_of)`) before any aggregations

### Feature store, versioning & lineage

* **Features versioned**: `txn_count_recent`, `total_spend_windowed`
* **Version details**:
  * **Feature**: `txn_count_recent` | **Parameter**: `window_days` | **v1**: `90` | **v2**: `30` | **Reason**: `v1` (90d) captured quarterly trends, but `v2` (30d) was added to catch immediate disengagement prior to monthly renewal cycles.
  * **Feature**: `total_spend_windowed` | **Parameter**: `window_days` | **v1**: `90` | **v2**: `60` | **Reason**: `v1` (90d) smoothed variance, while `v2` (60d) aligns closer to two billing cycles to flag rapid monetary drops earlier.
* **What forces a version bump vs. not**: Changes to lookback window parameters, underlying source selections, or mathematical transformation formulas force a version bump. Renaming columns or modifying formatting does not.
* **What a lineage entry must let someone reconstruct**: The exact mapping `source file -> transformation parameters -> behavioral rationale -> parquet output path`.

### Multi-source judgment calls

* **Feature**: `txn_count_recent` / `total_spend_windowed` — **Source chosen**: `transactions.db` — **Why**: Requires exact rolling day-window up to `as_of`, which monthly truncated aggregates cannot guarantee.
* **Feature**: `avg_monthly_spend_l12m` / `active_months_l12m` — **Source chosen**: `transactions_monthly_agg.parquet` — **Why**: Reduces memory overhead and query execution time for 12-month long-term baseline metrics without row-level scan overhead.

### Data-quality checks

* **Check**: No unexpected nulls after applying defaults — **Catches**: Left join null propagation on the 81 zero-transaction customers — **On failure**: `raise ValueError / non-zero exit`
* **Check**: Explicit zero-activity defaults applied — **Catches**: 81 zero-activity customers getting `NaN` or `None` instead of explicit defaults (`0`, `0.0`, tenure) — **On failure**: `raise ValueError / non-zero exit`
* **Check**: Sane numerical bounds (`return_rate_recent` in `[0.0, 1.0]`, `total_spend_windowed >= 0.0`, `days_since_last_txn >= 0.0`) — **Catches**: Join duplicate fan-outs or division-by-zero errors — **On failure**: `raise ValueError / non-zero exit`
* **Check**: Row count reconciliation (`output_rows == input_customer_count`) — **Catches**: Inner join dropping inactive customers or duplicate key fan-outs — **On failure**: `raise ValueError / non-zero exit`
