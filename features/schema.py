"""
Versioned output feature schema: the authoritative list of every feature this pipeline
produces, with dtype, nullability, source(s), and feature-set version.

This is generated/maintained from `feature_spec.md`, and is consumed by
`FEATURE_LINEAGE.md` generation and by the feature store registration step.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FeatureSpec:
    name: str
    dtype: str
    nullable: bool
    source: str
    feature_set_version: str
    description: str
    source_columns: str
    transform_summary: str
    business_rationale: str
    parameters: dict


FEATURE_SCHEMA: list[FeatureSpec] = [
    FeatureSpec(
        name="days_since_last_txn",
        dtype="float64",
        nullable=False,
        source="data/transactions.db",
        feature_set_version="v1",
        description="Number of days elapsed from the most recent transaction up to as_of timestamp.",
        source_columns="data/transactions.db:transactions.txn_timestamp",
        transform_summary="(as_of - max(txn_timestamp)) / 86400.0 for txn_timestamp <= as_of; zero-activity default: customer account tenure in fractional days.",
        business_rationale="Predicts churn because customers who have not transacted recently tend to disengage, distinct from low spend because a high-value customer could simply have stopped buying.",
        parameters={},
    ),
    FeatureSpec(
        name="txn_count_recent",
        dtype="int64",
        nullable=False,
        source="data/transactions.db",
        feature_set_version="v1",
        description="Count of transactions in the trailing 90 days [as_of - 90d, as_of].",
        source_columns="data/transactions.db:transactions.txn_timestamp",
        transform_summary="Count of transactions where as_of - window_days <= txn_timestamp <= as_of (window_days=90). Default: 0.",
        business_rationale="Predicts churn because a drop in recent transaction frequency signals waning habituation, distinct from baseline low spend since high-ticket buyers may buy infrequently.",
        parameters={"window_days": 90},
    ),
    FeatureSpec(
        name="total_spend_windowed",
        dtype="float64",
        nullable=False,
        source="data/transactions.db",
        feature_set_version="v1",
        description="Sum of transaction amounts in the trailing 90 days [as_of - 90d, as_of].",
        source_columns="data/transactions.db:transactions.amount,txn_timestamp",
        transform_summary="Sum of amount where as_of - window_days <= txn_timestamp <= as_of (window_days=90). Default: 0.0.",
        business_rationale="Predicts churn because declining short-term spend reflects immediate reduced wallet share, distinct from overall lifetime customer value.",
        parameters={"window_days": 90},
    ),
    FeatureSpec(
        name="avg_monthly_spend_l12m",
        dtype="float64",
        nullable=False,
        source="data/transactions_monthly_agg.parquet",
        feature_set_version="v1",
        description="Average monthly spend over the trailing 12 completed calendar months prior to as_of.",
        source_columns="data/transactions_monthly_agg.parquet:total_amount,txn_month",
        transform_summary="sum(total_amount) / 12.0 for completed months in [trunc_month(as_of) - 12m, trunc_month(as_of)). Default: 0.0.",
        business_rationale="Predicts churn because it establishes baseline account value, distinguishing high-tier accounts from low-tier buyers while smoothing short-term seasonality.",
        parameters={"months": 12},
    ),
    FeatureSpec(
        name="active_months_l12m",
        dtype="int64",
        nullable=False,
        source="data/transactions_monthly_agg.parquet",
        feature_set_version="v1",
        description="Count of distinct completed calendar months with txn_count > 0 in trailing 12 months prior to as_of.",
        source_columns="data/transactions_monthly_agg.parquet:txn_count,txn_month",
        transform_summary="Count of distinct txn_month with txn_count > 0 in [trunc_month(as_of) - 12m, trunc_month(as_of)). Default: 0.",
        business_rationale="Predicts churn because purchase regularity measures product stickiness; a customer active 10/12 months has higher retention habits regardless of total spend.",
        parameters={"months": 12},
    ),
    FeatureSpec(
        name="return_rate_recent",
        dtype="float64",
        nullable=False,
        source="data/transactions.db",
        feature_set_version="v1",
        description="Proportion of transactions in trailing 90 days that were returned.",
        source_columns="data/transactions.db:transactions.is_returned,txn_timestamp",
        transform_summary="sum(is_returned) / txn_count_recent for transactions in [as_of - 90d, as_of]. If txn_count_recent == 0, returns 0.0.",
        business_rationale="Predicts churn because a rising return share signals customer dissatisfaction or buyer remorse, distinct from low engagement.",
        parameters={"window_days": 90},
    ),
    FeatureSpec(
        name="customer_tenure_days",
        dtype="float64",
        nullable=False,
        source="data/customers.csv",
        feature_set_version="v1",
        description="Customer account age in fractional days from signup_date to as_of timestamp.",
        source_columns="data/customers.csv:signup_date",
        transform_summary="(as_of - signup_date) in days (fractional). Non-null by construction.",
        business_rationale="Predicts churn because mature customer cohorts exhibit structurally lower baseline churn rates than newly onboarded cohorts.",
        parameters={},
    ),
]
