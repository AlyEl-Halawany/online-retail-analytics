"""
src/data_cleaning.py
====================
Reusable data cleaning pipeline for the Online Retail II dataset.

PURPOSE (Business context)
--------------------------
Raw transactional data is messy in ways that would silently corrupt every
downstream analysis if not addressed. This module centralises all cleaning
decisions so that:
  1. Every decision is documented with a business reason, not just a code comment.
  2. The same cleaning logic is applied identically across notebooks, making
     results reproducible.
  3. A reviewer (or interviewer) can read this file top-to-bottom and understand
     exactly what data quality tradeoffs were made.

DESIGN DECISION: Why a module, not just notebook cells?
--------------------------------------------------------
Embedding cleaning logic directly in notebooks is fine for exploration but
creates a maintenance problem: if we later discover an edge case (e.g., a new
category of invalid SKU), we'd have to fix it in multiple places. A single
src/ module that notebooks import from is more maintainable and closer to
production-grade practice — relevant for DS/DA interviews.

USAGE
-----
    from src.data_cleaning import load_and_clean
    df = load_and_clean("data/raw/online_retail_II.csv")
    # Cleaned data is also written to data/processed/cleaned.parquet
"""

import pandas as pd
import numpy as np
from pathlib import Path


# ── Constants ─────────────────────────────────────────────────────────────────

RAW_PATH = Path("data/raw/online_retail_II.csv")
PROCESSED_PATH = Path("data/processed/cleaned.parquet")

# The dataset encoding is ISO-8859-1 (Latin-1), not UTF-8.
# This is common for older European datasets — using UTF-8 would cause errors
# on accented characters in product descriptions.
ENCODING = "ISO-8859-1"


# ── Main entry point ──────────────────────────────────────────────────────────

def load_and_clean(
    raw_path: str | Path = RAW_PATH,
    save_processed: bool = True,
    processed_path: str | Path = PROCESSED_PATH,
    verbose: bool = True,
) -> pd.DataFrame:
    """
    Load the raw Online Retail II CSV and apply all cleaning steps.

    Parameters
    ----------
    raw_path : path to the raw CSV file
    save_processed : if True, saves the result to processed_path as parquet
    processed_path : where to save the cleaned file
    verbose : if True, prints a cleaning summary report

    Returns
    -------
    pd.DataFrame : cleaned transaction-level data
    """
    raw_path = Path(raw_path)
    processed_path = Path(processed_path)

    # ── Step 1: Load raw data ──────────────────────────────────────────────────
    # WHY read_csv with encoding=latin1: the file uses ISO-8859-1 encoding,
    # common for European datasets with special characters (e.g. "ç", "é").
    # dtype={'Customer ID': str} avoids pandas reading it as a float and
    # adding unwanted decimal points like "12345.0".
    print("Loading raw data...") if verbose else None
    df = pd.read_csv(
        raw_path,
        encoding=ENCODING,
        dtype={"Customer ID": str},   # keep as string to avoid "12345.0" format
    )
    n_raw = len(df)
    print(f"  Raw rows loaded: {n_raw:,}") if verbose else None

    # ── Step 2: Rename columns for convenience ─────────────────────────────────
    # Remove the space in "Customer ID" — spaces in column names cause problems
    # with attribute access (df.Customer ID fails; df.CustomerID works).
    df = df.rename(columns={"Customer ID": "CustomerID"})

    # ── Step 3: Parse InvoiceDate to datetime ─────────────────────────────────
    # WHY: The date is stored as a string ("2010-01-01 08:26:00"). We need it
    # as a proper datetime to compute Recency, build time series, and do
    # cohort analysis. format=mixed handles two slightly different formats
    # present in the dataset.
    df["InvoiceDate"] = pd.to_datetime(df["InvoiceDate"], format="mixed")

    # ── Step 4: Remove missing CustomerID rows ─────────────────────────────────
    # WHY: ~135,000 rows (~13% of data) have no CustomerID. These are
    # walk-in/guest transactions that cannot be linked to a specific customer.
    # Since every downstream analysis (RFM, CLV, cohort) is customer-level,
    # these rows are unusable for our purpose.
    #
    # BUSINESS DECISION: We are NOT claiming these sales didn't happen — we are
    # saying we can't *attribute* them to a customer. Total revenue figures will
    # note this exclusion. An important limitation to flag in the final report.
    n_before = len(df)
    df = df.dropna(subset=["CustomerID"])
    n_missing_id = n_before - len(df)
    print(f"  Removed {n_missing_id:,} rows with missing CustomerID ({n_missing_id/n_before:.1%} of raw)") if verbose else None

    # ── Step 5: Remove cancelled orders (negative Quantity) ───────────────────
    # WHY: Cancelled orders have negative quantities (e.g., Quantity = -5).
    # Invoices starting with 'C' in the dataset are cancellation records.
    # Including them would deflate revenue figures and corrupt RFM Monetary
    # scores because the revenue column (Quantity × Price) would go negative.
    #
    # BUSINESS DECISION: We exclude cancellations from the main analysis.
    # A separate cancellation analysis could be valuable (cancellation rate as
    # a churn signal) but is out of scope for this brief.
    n_before = len(df)
    cancelled_mask = df["Invoice"].astype(str).str.startswith("C")
    df = df[~cancelled_mask]
    n_cancelled = n_before - len(df)
    print(f"  Removed {n_cancelled:,} cancelled orders (Invoice starts with 'C')") if verbose else None

    # Also drop any remaining negative-quantity rows not caught by the 'C' prefix
    n_before = len(df)
    df = df[df["Quantity"] > 0]
    n_neg_qty = n_before - len(df)
    if n_neg_qty > 0:
        print(f"  Removed {n_neg_qty:,} additional negative-quantity rows") if verbose else None

    # ── Step 6: Remove zero or negative Price rows ────────────────────────────
    # WHY: Items with Price = 0 are typically internal test transactions, gifts,
    # or data entry errors. They contribute £0 revenue and would distort average
    # order value calculations. A zero-price row with Quantity > 0 is almost
    # certainly not a real commercial transaction.
    n_before = len(df)
    df = df[df["Price"] > 0]
    n_zero_price = n_before - len(df)
    print(f"  Removed {n_zero_price:,} rows with zero/negative Price") if verbose else None

    # ── Step 7: Remove exact duplicate rows ───────────────────────────────────
    # WHY: A small number of rows are exact duplicates across all columns —
    # likely caused by double-entry at the point of sale or data pipeline errors.
    # We keep the first occurrence.
    n_before = len(df)
    df = df.drop_duplicates()
    n_dupes = n_before - len(df)
    print(f"  Removed {n_dupes:,} exact duplicate rows") if verbose else None

    # ── Step 8: Add Revenue column ────────────────────────────────────────────
    # Revenue = Quantity × Price. This is the fundamental metric for all
    # monetary analyses. We compute it once here so it's consistent everywhere.
    df["Revenue"] = df["Quantity"] * df["Price"]

    # ── Step 9: Strip whitespace from string columns ──────────────────────────
    # Trailing/leading spaces in Description and Country can cause groupby
    # mismatches (e.g., "United Kingdom " vs "United Kingdom").
    df["Description"] = df["Description"].str.strip()
    df["Country"] = df["Country"].str.strip()
    df["StockCode"] = df["StockCode"].str.strip().str.upper()

    # ── Summary report ────────────────────────────────────────────────────────
    n_clean = len(df)
    n_customers = df["CustomerID"].nunique()
    n_invoices = df["Invoice"].nunique()
    date_min = df["InvoiceDate"].min().strftime("%Y-%m-%d")
    date_max = df["InvoiceDate"].max().strftime("%Y-%m-%d")
    total_revenue = df["Revenue"].sum()

    if verbose:
        print("\n-- Cleaning Summary ------------------------------------------")
        print(f"  Raw rows:          {n_raw:>12,}")
        print(f"  Cleaned rows:      {n_clean:>12,}  ({n_clean/n_raw:.1%} retained)")
        print(f"  Unique customers:  {n_customers:>12,}")
        print(f"  Unique invoices:   {n_invoices:>12,}")
        print(f"  Date range:        {date_min} -> {date_max}")
        print(f"  Total revenue (GBP): {total_revenue:>12,.2f}")
        print("--------------------------------------------------------------")

    # ── Save processed file ───────────────────────────────────────────────────
    if save_processed:
        processed_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(processed_path, index=False, engine="pyarrow")
        if verbose:
            print(f"\nCleaned data saved to: {processed_path}")

    return df


# ── Utility: reload from parquet (fast) ──────────────────────────────────────

def load_cleaned(processed_path: str | Path = PROCESSED_PATH) -> pd.DataFrame:
    """
    Load the already-cleaned data from parquet. Much faster than re-running
    the full cleaning pipeline — use this in later notebooks after the first
    cleaning pass has been completed.
    """
    return pd.read_parquet(Path(processed_path), engine="pyarrow")
