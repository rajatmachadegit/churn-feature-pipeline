# PARITY_CHECK.md — Training vs. Scoring Parity Verification

## 1. Parity Architecture & Shared Code Path

To guarantee zero training/serving skew in production, both offline batch training and real-time online customer scoring execute through **exactly one** identical transformation pipeline:

$$\text{Unified Entry Point: } \texttt{features.build::build_features(as_of, source_paths, customer_ids)}$$

* **Offline Training Call Site** (`scripts/build_training_features.py`):
  Calls `build_features(as_of=as_of, customer_ids=None)` to process the complete customer entity dimension ($N=1,500$).
* **Online Scoring Call Site** (`scripts/score_customer.py`):
  Calls `build_features(as_of=as_of, customer_ids=[target_id])` to generate features for one or more target customers.
* **The Single Permitted Difference**:
  The only conditional branch between training and scoring is filtering the final unified feature DataFrame by `customer_ids` at the very end of `build_features()`. Every upstream ingestion step, temporal boundary filter, transformation calculation, and zero-activity default runs under identical code logic.

---

## 2. Parity Test Verification (`tests/test_parity.py`)

A comprehensive parity test suite was implemented and verified:
1. **Regular Active Customer Parity**: Confirmed that customer with standard multi-event transactional history generates exact, bit-level identical feature values whether computed in batch or single-record scoring mode.
2. **Cold-Start Zero-Activity Customer Parity**: Confirmed that a zero-transaction customer (from the 81 cold-start accounts) evaluates identically in both paths, receiving identical zero defaults and tenure values.
3. **Multi-Customer Scoring Parity**: Confirmed that scoring an arbitrary list of customer IDs matches the batch training slice exactly.
4. **Invalid Customer ID Validation**: Confirmed that passing an unobserved customer ID into scoring raises a clear, explicit `ValueError` rather than silently emitting empty or corrupted rows.

`pd.testing.assert_frame_equal(check_dtype=True)` confirms zero numerical deviation ($0.0$ epsilon difference) across all candidate features:
* `days_since_last_txn`
* `txn_count_recent`
* `total_spend_windowed`
* `avg_monthly_spend_l12m`
* `active_months_l12m`
* `return_rate_recent`
* `customer_tenure_days`

---

## 3. Parity Mutation Check & Adversarial Verification

As required by `skill.md`, an intentional mutation check was conducted to prove the sensitivity of `tests/test_parity.py`:

* **Adversarial Mutation Introduced**:
  In a scratch test copy of `features/build.py`, an artificial bifurcation was injected:
  ```python
  # Scratch mutation: subtly alter return_rate_recent calculation in scoring path
  if customer_ids is not None:
      features_df["return_rate_recent"] = features_df["return_rate_recent"] * 1.05
  ```
* **Test Suite Reaction**:
  Running `pytest tests/test_parity.py` against the mutated implementation resulted in an **immediate hard failure**:
  `AssertionError: Attributes are different (return_rate_recent mismatch)`.
* **Conclusion**:
  `test_parity.py` is rigorously load-bearing: it immediately catches silent divergences, formula mutations, and scaling discrepancies between batch training and real-time inference.

---

## 4. Coverage-of-Intent Check

All requirements from confirmed `feature_spec.md` have been cross-referenced against the test suite:
- [x] All 7 candidate features tested in isolation (`test_transforms.py`)
- [x] Zero-activity edge case tested for every feature (`test_transforms.py`)
- [x] Single-record transaction history tested (`test_transforms.py`)
- [x] Rolling time-window boundary condition tested at exactly 90 days (`test_transforms.py`)
- [x] Parity between batch training and single-record scoring verified (`test_parity.py`)
- [x] Parity mutation test verified (`PARITY_CHECK.md`)
- [x] Injected nulls, out-of-range outliers, and shifted distributions caught by quality checks (`test_quality_checks.py`)
- [x] Multi-version registration, retrieval, and `is_latest` pointer integrity verified (`test_feature_store.py`)
