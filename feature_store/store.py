"""
Local feature store API: a SQLite metadata/version registry (`feature_store/registry.db`,
table `feature_registry`) plus one parquet value snapshot per registered version
(`feature_store/values/<feature_name>__v<version>.parquet`).

Do not add mlflow, feast, or any other feature-store library — this store is SQLite +
parquet only. Schema implements:
columns: feature_name, version, created_at, description, source_columns,
transform_summary, business_rationale, parameters, parquet_path, is_latest.

Primary key: (feature_name, version).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import pandas as pd

REGISTRY_DB = "feature_store/registry.db"
VALUES_DIR = "feature_store/values"


def _init_registry(db_path: str = REGISTRY_DB) -> None:
    """Initialize the SQLite registry database and table if not already present."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        with conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS feature_registry (
                    feature_name TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    description TEXT,
                    source_columns TEXT,
                    transform_summary TEXT,
                    business_rationale TEXT,
                    parameters TEXT,
                    parquet_path TEXT NOT NULL,
                    is_latest INTEGER NOT NULL CHECK (is_latest IN (0, 1)),
                    PRIMARY KEY (feature_name, version)
                );
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_feature_latest
                ON feature_registry (feature_name, is_latest);
                """
            )
    finally:
        conn.close()


def register_version(
    feature_name: str,
    values_df: pd.DataFrame,
    description: str,
    source_columns: str,
    transform_summary: str,
    business_rationale: str,
    parameters: dict,
    db_path: str = REGISTRY_DB,
    values_dir: str = VALUES_DIR,
) -> int:
    """Write a new parquet snapshot, insert the registry row, flip is_latest, return the
    new version number.

    Never overwrite an existing version's file or row.
    """
    _init_registry(db_path)
    Path(values_dir).mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    try:
        with conn:
            # Determine next version
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COALESCE(MAX(version), 0) FROM feature_registry WHERE feature_name = ?",
                (feature_name,),
            )
            max_v = cursor.fetchone()[0]
            new_version = max_v + 1

            # Format parquet path
            parquet_filename = f"{feature_name}__v{new_version}.parquet"
            parquet_path = Path(values_dir) / parquet_filename
            # Store relative posix path in registry
            rel_parquet_path = f"{values_dir}/{parquet_filename}".replace("\\", "/")

            if parquet_path.exists():
                raise FileExistsError(f"Parquet file {parquet_path} already exists! Never overwrite an existing version.")

            # Validate values_df contains required columns: customer_id, feature column, as_of_date
            expected_cols = {"customer_id", feature_name, "as_of_date"}
            if not expected_cols.issubset(set(values_df.columns)):
                raise ValueError(f"values_df must contain columns {expected_cols}, got {list(values_df.columns)}")

            # Write parquet snapshot
            values_df[["customer_id", feature_name, "as_of_date"]].to_parquet(
                parquet_path, index=False, engine="pyarrow"
            )

            # In the same transaction: flip prior latest to 0, insert new row with is_latest=1
            cursor.execute(
                "UPDATE feature_registry SET is_latest = 0 WHERE feature_name = ? AND is_latest = 1",
                (feature_name,),
            )

            created_at = datetime.now(timezone.utc).isoformat()
            params_json = json.dumps(parameters or {})

            cursor.execute(
                """
                INSERT INTO feature_registry (
                    feature_name, version, created_at, description,
                    source_columns, transform_summary, business_rationale,
                    parameters, parquet_path, is_latest
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                """,
                (
                    feature_name,
                    new_version,
                    created_at,
                    description,
                    source_columns,
                    transform_summary,
                    business_rationale,
                    params_json,
                    rel_parquet_path,
                ),
            )
            return new_version
    finally:
        conn.close()


def get_latest(feature_name: str, db_path: str = REGISTRY_DB) -> pd.DataFrame:
    """Return the DataFrame for the version currently flagged is_latest = 1."""
    _init_registry(db_path)
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT parquet_path, version FROM feature_registry WHERE feature_name = ? AND is_latest = 1",
            (feature_name,),
        )
        row = cursor.fetchone()
        if not row:
            raise KeyError(f"Feature '{feature_name}' not found in registry (no latest version).")
        parquet_path, _ = row
        return pd.read_parquet(parquet_path)
    finally:
        conn.close()


def get_version(feature_name: str, version: int, db_path: str = REGISTRY_DB) -> pd.DataFrame:
    """Return the DataFrame for a specific (feature_name, version)."""
    _init_registry(db_path)
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT parquet_path FROM feature_registry WHERE feature_name = ? AND version = ?",
            (feature_name, version),
        )
        row = cursor.fetchone()
        if not row:
            raise KeyError(f"Feature '{feature_name}' version {version} not found in registry.")
        parquet_path = row[0]
        return pd.read_parquet(parquet_path)
    finally:
        conn.close()


def list_versions(feature_name: str, db_path: str = REGISTRY_DB) -> pd.DataFrame:
    """Return every registered version's metadata row for feature_name, most recent first."""
    _init_registry(db_path)
    conn = sqlite3.connect(db_path)
    try:
        df = pd.read_sql_query(
            "SELECT * FROM feature_registry WHERE feature_name = ? ORDER BY version DESC",
            conn,
            params=(feature_name,),
        )
        return df
    finally:
        conn.close()


def list_all_features(db_path: str = REGISTRY_DB) -> pd.DataFrame:
    """Return all rows in feature_registry ordered by feature_name and version."""
    _init_registry(db_path)
    conn = sqlite3.connect(db_path)
    try:
        df = pd.read_sql_query(
            "SELECT * FROM feature_registry ORDER BY feature_name ASC, version ASC",
            conn,
        )
        return df
    finally:
        conn.close()
