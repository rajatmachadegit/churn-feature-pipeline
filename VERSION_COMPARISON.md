# VERSION_COMPARISON.md — Feature Version Evaluation & Interpretation

## Executive Summary
This document provides empirical distribution shifts, rank-order changes, and churn-risk threshold movements between registered versions of all versioned features in the feature store (`feature_store/registry.db`).

Per `feature_spec.md`, version bumps were triggered by deliberate parameter modifications to lookback windows to capture behavioral deterioration faster. All values were retrieved directly from the feature store snapshots via `feature_store.store.get_version` without recomputing.

---

### 1. Feature: `txn_count_recent`
* **Parameter Varied**: `window_days`
  * **v1**: `90`
  * **v2**: `30`
* **Business Rationale for Bump**: v1 (90d) captured quarterly trends, but v2 (30d) was added to catch immediate disengagement prior to monthly renewal cycles.
* **Retrieval Method**: Independently loaded via `feature_store.store.get_version("txn_count_recent", 1)` and `get_version("txn_count_recent", 2)` without recomputing.

#### Customer Value Change
* **Total Customers Evaluated**: 1500
* **Customers With Changed Feature Values**: **1087** (72.5%)
* **Customers With Identical Values**: 413 (primarily customers with no transactions in the window)

#### Distribution Shift & Quantile Comparison
| Metric | Version 1 (90) | Version 2 (30) | Delta (v2 - v1) |
| :--- | :--- | :--- | :--- |
| **Mean** | 2.277 | 0.791 | -1.486 |
| **Std Dev** | 1.793 | 0.994 | -0.799 |
| **Min** | 0.000 | 0.000 | 0.000 |
| **25th Percentile** | 1.000 | 0.000 | -1.000 |
| **Median (50th)** | 2.000 | 1.000 | -1.000 |
| **75th Percentile** | 3.000 | 1.000 | -2.000 |
| **90th Percentile** | 5.000 | 2.000 | -3.000 |
| **Max** | 12.000 | 7.000 | -5.000 |

#### Rank-Order and Churn Risk Re-Ranking
* **Spearman Rank Correlation**: `0.6032`
* **Customers Moving In/Out of High Churn-Risk Tier (Bottom Quartile)**:
  * Total customers re-ranked across the bottom quartile threshold: **414**
  * Newly classified into high-risk tier: **281**
  * Shifted out of high-risk tier: **133**

#### Interpretation
Shortening the lookback window concentrates the feature on immediate customer momentum. A predictive model consuming `txn_count_recent` will strongly notice this shift: customers whose purchasing halted 45 days ago appeared healthy under v1 (90-day window) but drop to 0 under v2, surfacing impending churn 60 days sooner.


---

### 1. Feature: `total_spend_windowed`
* **Parameter Varied**: `window_days`
  * **v1**: `90`
  * **v2**: `60`
* **Business Rationale for Bump**: v1 (90d) smoothed variance, while v2 (60d) aligns closer to two billing cycles to flag rapid monetary drops earlier.
* **Retrieval Method**: Independently loaded via `feature_store.store.get_version("total_spend_windowed", 1)` and `get_version("total_spend_windowed", 2)` without recomputing.

#### Customer Value Change
* **Total Customers Evaluated**: 1500
* **Customers With Changed Feature Values**: **724** (48.3%)
* **Customers With Identical Values**: 776 (primarily customers with no transactions in the window)

#### Distribution Shift & Quantile Comparison
| Metric | Version 1 (90) | Version 2 (60) | Delta (v2 - v1) |
| :--- | :--- | :--- | :--- |
| **Mean** | 115.526 | 78.604 | -36.922 |
| **Std Dev** | 119.928 | 94.019 | -25.909 |
| **Min** | 0.000 | 0.000 | 0.000 |
| **25th Percentile** | 27.887 | 0.000 | -27.887 |
| **Median (50th)** | 82.230 | 47.855 | -34.375 |
| **75th Percentile** | 168.045 | 116.025 | -52.020 |
| **90th Percentile** | 267.272 | 208.851 | -58.421 |
| **Max** | 1004.220 | 649.980 | -354.240 |

#### Rank-Order and Churn Risk Re-Ranking
* **Spearman Rank Correlation**: `0.8118`
* **Customers Moving In/Out of High Churn-Risk Tier (Bottom Quartile)**:
  * Total customers re-ranked across the bottom quartile threshold: **247**
  * Newly classified into high-risk tier: **126**
  * Shifted out of high-risk tier: **121**

#### Interpretation
Shortening the lookback window concentrates the feature on immediate customer momentum. A predictive model consuming `total_spend_windowed` will strongly notice this shift: customers whose purchasing halted 45 days ago appeared healthy under v1 (90-day window) but drop to 0 under v2, surfacing impending churn 60 days sooner.


---

## Conclusion & Recommendations
1. **Model Sensitivity**: Both version bumps produce material distribution shifts (1 and 1) that gradient boosted decision trees or logistic regression models will heavily register.
2. **Feature Store Integrity**: Both v1 and v2 snapshots remain immutable on disk and simultaneously retrievable, allowing parallel A/B testing of model candidates trained on either version.
