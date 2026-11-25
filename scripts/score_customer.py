#!/usr/bin/env python3
"""
Builds features for one or more specific customer_ids as of a given date, using the
scoring path of the same shared build_features(as_of, ...) entry point used by
build_training_features.py.
"""
from __future__ import annotations

import argparse
import sys
import pandas as pd

from features.build import build_features


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--customer-id",
        type=int,
        action="append",
        required=True,
        help="Customer ID to score. May be passed multiple times.",
    )
    parser.add_argument(
        "--as-of",
        default="2026-08-01",
        help="As-of date for feature computation (default: 2026-08-01).",
    )
    args = parser.parse_args()

    customer_ids = args.customer_id
    try:
        features_df = build_features(as_of=args.as_of, customer_ids=customer_ids)
    except ValueError as e:
        print(f"Error scoring customer: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Scored {len(features_df)} customer(s) as of {args.as_of}:\n")
    print(features_df.to_string(index=False))


if __name__ == "__main__":
    main()
