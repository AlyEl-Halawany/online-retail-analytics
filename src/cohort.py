"""
src/cohort.py
=============
Cohort retention analysis.

WHAT IS COHORT ANALYSIS?
-------------------------
A cohort is a group of customers defined by a shared characteristic —
in this case, the month of their FIRST purchase. Cohort analysis tracks
what fraction of each cohort returns in subsequent months.

WHY COHORT ANALYSIS (not just overall retention rate)?
-------------------------------------------------------
A single headline retention number (e.g., "30% of customers return in Month 2")
is misleading because it aggregates customers who joined at different times.
Cohort analysis disaggregates this:
  - Was the retention rate getting better or worse over time?
  - Do customers acquired in Q4 (Christmas) have lower lifetime retention than
    those acquired in Q1 (they may have been one-off gift buyers)?
  - When exactly do customers drop off? Month 2? Month 6?

Each of these questions has a specific business action attached to it.

OUTPUT: A retention matrix (heatmap) where:
  - Rows = acquisition cohort (month of first purchase)
  - Columns = month number since first purchase (0, 1, 2, ...)
  - Values = % of original cohort still active in that month
  - Month 0 = 100% by definition (all customers were active when they first joined)

USAGE
-----
    from src.cohort import run_cohort_pipeline
    retention_df = run_cohort_pipeline(df)
"""

import pandas as pd
import numpy as np
from pathlib import Path


def build_cohort_matrix(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Build the cohort retention matrix from transaction data.

    Returns
    -------
    retention_pct : DataFrame of retention rates (0-100 scale)
    cohort_sizes  : Series of how many customers were in each cohort at Month 0
    """

    # ── Step 1: Assign each customer their cohort month ────────────────────────
    # Cohort = the month of their very first purchase.
    # WHY: Grouping by acquisition period lets us compare like-for-like.
    # A customer who first bought in Dec 2009 and Dec 2011 are at very different
    # lifecycle stages — we can't compare their Month 6 retention directly
    # without a cohort framework.

    df = df.copy()

    # First purchase date per customer
    first_purchase = (
        df.groupby("CustomerID")["InvoiceDate"]
        .min()
        .reset_index()
        .rename(columns={"InvoiceDate": "CohortDate"})
    )
    first_purchase["CohortMonth"] = first_purchase["CohortDate"].dt.to_period("M")

    # Join cohort back onto the transaction table
    df = df.merge(first_purchase[["CustomerID", "CohortMonth"]], on="CustomerID", how="left")

    # ── Step 2: Compute the "period number" for each transaction ───────────────
    # PeriodNumber = how many months after first purchase is this transaction?
    # Month 0 = the cohort's first month (always 100%)
    # Month 1 = one month later, etc.

    df["TransactionMonth"] = df["InvoiceDate"].dt.to_period("M")
    df["PeriodNumber"] = (
        df["TransactionMonth"] - df["CohortMonth"]
    ).apply(lambda x: x.n)   # .n extracts the integer difference in periods

    # Only keep non-negative period numbers (safeguard against data anomalies)
    df = df[df["PeriodNumber"] >= 0]

    # ── Step 3: Count unique active customers per cohort × period ──────────────
    cohort_data = (
        df.groupby(["CohortMonth", "PeriodNumber"])["CustomerID"]
        .nunique()
        .reset_index()
        .rename(columns={"CustomerID": "ActiveCustomers"})
    )

    # ── Step 4: Build the pivot table ─────────────────────────────────────────
    cohort_pivot = cohort_data.pivot_table(
        index="CohortMonth",
        columns="PeriodNumber",
        values="ActiveCustomers",
    )

    # Cohort sizes = column 0 (customers in their first month)
    cohort_sizes = cohort_pivot[0]

    # Retention rates = active customers / cohort size × 100
    retention_pct = cohort_pivot.divide(cohort_sizes, axis=0) * 100

    return retention_pct, cohort_sizes


def run_cohort_pipeline(
    df: pd.DataFrame,
    output_csv: str | Path = "app/dashboard_data/cohort_matrix.csv",
    output_parquet: str | Path = "data/processed/cohort_matrix.parquet",
) -> tuple[pd.DataFrame, pd.Series]:
    """
    Build and save the cohort retention matrix.
    """
    print("Building cohort retention matrix...")
    retention_pct, cohort_sizes = build_cohort_matrix(df)

    # Summary statistics
    # Average retention by month number (across all cohorts)
    avg_retention = retention_pct.mean(axis=0)

    print("\n-- Average Retention by Month Number (across all cohorts) --------")
    print(f"  Month 0:  {avg_retention.get(0, 100):.1f}% (baseline)")
    for m in [1, 2, 3, 6, 9, 12]:
        if m in avg_retention.index:
            print(f"  Month {m:<2}: {avg_retention[m]:.1f}%")
    print("------------------------------------------------------------------")

    # Find steepest drop
    drops = avg_retention.diff().dropna()
    steepest_drop_month = drops.idxmin()
    steepest_drop_value = drops.min()
    print(f"\nLargest single-month retention drop:")
    print(f"  Between Month {steepest_drop_month-1} and Month {steepest_drop_month}: "
          f"{steepest_drop_value:.1f}pp drop")
    print(f"  BUSINESS IMPLICATION: The sharpest customer loss happens between")
    print(f"  months {steepest_drop_month-1} and {steepest_drop_month} post-acquisition.")
    print(f"  CRM intervention (e.g., follow-up email, personalised recommendation)")
    print(f"  should be timed to arrive BEFORE this drop — i.e., at ~day")
    print(f"  {(steepest_drop_month-1)*30} post-first-purchase.")

    # ── Save outputs ──────────────────────────────────────────────────────────
    Path(output_csv).parent.mkdir(parents=True, exist_ok=True)
    # Save as string index for readability in CSV
    retention_pct.index = retention_pct.index.astype(str)
    retention_pct.to_csv(output_csv)

    Path(output_parquet).parent.mkdir(parents=True, exist_ok=True)
    retention_pct.to_parquet(output_parquet, engine="pyarrow")
    print(f"\nCohort matrix saved: {output_csv}")

    return retention_pct, cohort_sizes
