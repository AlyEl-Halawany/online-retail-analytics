"""
src/rfm.py
==========
RFM (Recency, Frequency, Monetary) segmentation pipeline.

WHY RFM?
--------
RFM is a proven, 50-year-old direct marketing framework. Every dimension maps
to a specific behavioural signal:

  - RECENCY   → How recently did this customer buy?
                A customer who bought yesterday is more engaged than one who
                bought 18 months ago. Recency is the strongest predictor of
                future purchase probability.

  - FREQUENCY → How many times have they bought?
                Repeat buyers have demonstrated loyalty and lower price
                sensitivity. They are more likely to respond to upsell offers.

  - MONETARY  → How much have they spent in total?
                High-spend customers have higher absolute retention value.
                Losing a £5,000/year customer hurts more than losing a £50/year
                customer, even if the probability of churn is identical.

WHY QUINTILE SCORING (not raw values)?
---------------------------------------
Raw RFM values (e.g., Recency = 42 days, Monetary = £3,500) are not directly
comparable across dimensions — they have different scales and distributions.
Quintile scoring (1–5 per dimension) normalises everything onto the same scale
so scores can be combined meaningfully.

  Score 5 = best quintile for that dimension
  Score 1 = worst quintile

NOTE on Recency scoring: lower days-since-purchase = better, so we invert
the scoring (score 5 = most recent = smallest recency value).

SEGMENT NAMING — DESIGN DECISION
----------------------------------
We use a rule-based approach to name segments rather than clustering (e.g.,
k-means). This is deliberate:
  - Rules are transparent and explainable to any stakeholder
  - Clusters require justifying the choice of k and interpreting abstract
    cluster centroids — harder to defend in a BA context
  - Rule-based segments can be directly translated into action
    (e.g., "all At-Risk customers get Campaign X") without a lookup table

USAGE
-----
    from src.rfm import compute_rfm, assign_segments
    rfm = compute_rfm(df)
    rfm = assign_segments(rfm)
"""

import pandas as pd
import numpy as np
from pathlib import Path


# ── Segment definitions ───────────────────────────────────────────────────────
# Each entry: (segment_name, condition_function)
# Conditions are evaluated top-to-bottom; first match wins.
# This ordering is intentional — Champions and Loyal must be checked before
# the broader At-Risk rule can accidentally capture them.

SEGMENT_RULES = [
    # Champions: recent, frequent, high-spend. The crown jewels.
    ("Champions",          lambda r: (r.R >= 4) & (r.F >= 4) & (r.M >= 4)),

    # Loyal Customers: frequent + high-spend, even if not super-recent.
    # These are repeat buyers who form the backbone of the business.
    ("Loyal Customers",    lambda r: (r.F >= 3) & (r.M >= 3)),

    # Potential Loyalists: recent first/second-time buyers with some spend.
    # The conversion opportunity — get them to a 3rd purchase.
    ("Potential Loyalists",lambda r: (r.R >= 4) & (r.F <= 2) & (r.M >= 2)),

    # New Customers: very recent, only 1 order, any spend level.
    # Priority: onboarding experience and first repeat purchase.
    ("New Customers",      lambda r: (r.R >= 4) & (r.F == 1)),

    # At Risk: used to buy frequently/spend well but have gone quiet.
    # High urgency — these represent significant revenue at risk.
    ("At Risk",            lambda r: (r.R <= 2) & (r.F >= 3) & (r.M >= 3)),

    # At Risk - Low Value: previously engaged but lower spend. Lower priority.
    ("At Risk - Low Value",lambda r: (r.R <= 2) & (r.F >= 2)),

    # Hibernating: low across all dimensions but still in the data.
    # Low ROI to target — passive monitoring only.
    ("Hibernating",        lambda r: (r.R <= 2) & (r.F <= 2) & (r.M <= 2)),
]

# Catch-all for any customer who doesn't match the above rules
DEFAULT_SEGMENT = "Needs Attention"


# ── Business action mapping ───────────────────────────────────────────────────
# This is the core BA deliverable: for each segment, what is the SPECIFIC
# action the business should take? Not vague advice — concrete next steps.

SEGMENT_ACTIONS = {
    "Champions": (
        "Reward and leverage. Offer early access to new products, a loyalty "
        "programme, or referral incentives. These customers are brand advocates "
        "— make them feel recognised. Do NOT over-discount: they already buy "
        "without a price stimulus."
    ),
    "Loyal Customers": (
        "Upsell and cross-sell. Introduce higher-margin product lines or "
        "complementary categories. Consider a tiered loyalty scheme. "
        "Monitor Recency — if it starts dropping, move to At-Risk protocols."
    ),
    "Potential Loyalists": (
        "Convert to habit. The goal is the 3rd purchase — research shows this "
        "is where customers cross from trial to retention. Send a personalised "
        "'we noticed you liked X' follow-up email within 30 days of their "
        "last order with a soft incentive (free shipping, not discount)."
    ),
    "New Customers": (
        "Onboarding sequence. Send a 3-email welcome series over 30 days: "
        "(1) order confirmation + brand story, (2) how-to/product care at day 7, "
        "(3) 'customers like you also bought' recommendation at day 21. "
        "Goal: drive the second purchase before 90-day recency decay."
    ),
    "At Risk": (
        "WIN-BACK CAMPAIGN — HIGH PRIORITY. These customers represent the most "
        "acute revenue risk. Send a personalised reactivation offer within this "
        "quarter. Reference their purchase history ('It's been a while since "
        "your last [product category] order'). Budget: up to 20% discount is "
        "justified given their historical spend level."
    ),
    "At Risk - Low Value": (
        "Light-touch reactivation. A single email campaign is appropriate; "
        "do not invest significant budget. If they don't respond, move to "
        "Hibernating and deprioritise."
    ),
    "Hibernating": (
        "Passive only. Include in quarterly newsletter but do not allocate "
        "dedicated campaign budget. Consider a low-cost 'We miss you' email "
        "once per year. Focus resources on higher-value segments."
    ),
    "Needs Attention": (
        "Review individually or reassign to nearest segment based on raw "
        "RFM scores. This segment should be small if rules are well-calibrated."
    ),
}


# ── Core functions ────────────────────────────────────────────────────────────

def compute_rfm(df: pd.DataFrame, snapshot_date: pd.Timestamp = None) -> pd.DataFrame:
    """
    Calculate raw RFM values per customer.

    Parameters
    ----------
    df : cleaned transaction DataFrame (output of data_cleaning.load_and_clean)
    snapshot_date : the reference date for recency calculation.
                    Defaults to max(InvoiceDate) + 1 day.
                    Using max_date + 1 (not today) makes recency reproducible
                    regardless of when the notebook is run.

    Returns
    -------
    DataFrame with columns: CustomerID, Recency, Frequency, Monetary
    """
    if snapshot_date is None:
        # +1 day so the most recent customer has Recency=1, not 0
        snapshot_date = df["InvoiceDate"].max() + pd.Timedelta(days=1)

    print(f"RFM snapshot date: {snapshot_date.date()}")

    rfm = (
        df.groupby("CustomerID")
        .agg(
            # Days since last purchase (lower = better = more recent)
            Recency=("InvoiceDate", lambda x: (snapshot_date - x.max()).days),
            # Count of unique invoices (not rows — avoids counting multi-item orders multiple times)
            Frequency=("Invoice", "nunique"),
            # Sum of all revenue attributed to this customer
            Monetary=("Revenue", "sum"),
        )
        .reset_index()
    )

    return rfm


def score_rfm(rfm: pd.DataFrame, n_quantiles: int = 5) -> pd.DataFrame:
    """
    Add quintile scores (1–5) for each RFM dimension.

    DESIGN NOTE on ties (duplicates=False):
    When many customers share the same value (e.g., Frequency=1 for half the
    base), pd.qcut raises a ValueError if it can't form unique bin edges.
    duplicates='drop' merges identical edges, potentially producing fewer than
    n_quantiles bins. We handle this gracefully and note it in output.

    Recency scoring is INVERTED: score 5 = most recent (smallest days value).
    Frequency and Monetary: score 5 = highest value.
    """
    rfm = rfm.copy()

    # Recency: invert so that smaller recency = higher score
    rfm["R"] = pd.qcut(
        rfm["Recency"],
        q=n_quantiles,
        labels=False,
        duplicates="drop",
    )
    # After qcut, lower bin index = lower recency value = more recent.
    # We want score 5 = most recent, so invert by subtracting from max.
    rfm["R"] = rfm["R"].max() - rfm["R"] + 1

    # Frequency: higher = better = higher score
    rfm["F"] = pd.qcut(
        rfm["Frequency"].rank(method="first"),   # rank() breaks ties deterministically
        q=n_quantiles,
        labels=False,
        duplicates="drop",
    ) + 1   # shift from 0-indexed to 1-indexed

    # Monetary: higher = better = higher score
    rfm["M"] = pd.qcut(
        rfm["Monetary"].rank(method="first"),
        q=n_quantiles,
        labels=False,
        duplicates="drop",
    ) + 1

    # Combined RFM score (simple sum — not the only approach, but transparent
    # and easy to explain: a score of 15 = perfect across all three dimensions)
    rfm["RFM_Score"] = rfm["R"] + rfm["F"] + rfm["M"]

    return rfm


def assign_segments(rfm: pd.DataFrame) -> pd.DataFrame:
    """
    Apply segment rules to the scored RFM table.
    Returns the rfm DataFrame with a new 'Segment' column.
    """
    rfm = rfm.copy()
    rfm["Segment"] = DEFAULT_SEGMENT

    # Apply rules in order; first match wins
    for segment_name, condition_fn in SEGMENT_RULES:
        mask = condition_fn(rfm) & (rfm["Segment"] == DEFAULT_SEGMENT)
        rfm.loc[mask, "Segment"] = segment_name

    # Add the plain-English action for each customer's segment
    rfm["RecommendedAction"] = rfm["Segment"].map(SEGMENT_ACTIONS)

    return rfm


def run_rfm_pipeline(
    df: pd.DataFrame,
    save_path: str | Path = "data/processed/rfm_segments.parquet",
    csv_path: str | Path = "app/dashboard_data/customers_rfm.csv",
) -> pd.DataFrame:
    """
    End-to-end: raw transactions -> scored + segmented RFM table.
    Saves both a parquet (for downstream Python) and a CSV (for Power BI).
    """
    print("Computing raw RFM values...")
    rfm = compute_rfm(df)

    print("Scoring RFM dimensions (quintiles)...")
    rfm = score_rfm(rfm)

    print("Assigning segments...")
    rfm = assign_segments(rfm)

    # Summary
    print("\n-- RFM Segment Summary -------------------------------------------")
    summary = (
        rfm.groupby("Segment")
        .agg(
            Customers=("CustomerID", "count"),
            AvgRecency=("Recency", "mean"),
            AvgFrequency=("Frequency", "mean"),
            TotalRevenue=("Monetary", "sum"),
            AvgMonetary=("Monetary", "mean"),
        )
        .sort_values("TotalRevenue", ascending=False)
    )
    summary["RevenuePct"] = summary["TotalRevenue"] / summary["TotalRevenue"].sum() * 100
    summary["CustomerPct"] = summary["Customers"] / summary["Customers"].sum() * 100
    print(summary[["Customers", "CustomerPct", "TotalRevenue", "RevenuePct",
                    "AvgRecency", "AvgFrequency", "AvgMonetary"]].to_string())
    print("------------------------------------------------------------------")

    # Save outputs
    save_path = Path(save_path)
    save_path.parent.mkdir(parents=True, exist_ok=True)
    rfm.to_parquet(save_path, index=False, engine="pyarrow")
    print(f"\nSaved parquet: {save_path}")

    csv_path = Path(csv_path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    # Drop the long action text for the CSV (too wide for Power BI columns)
    rfm.drop(columns=["RecommendedAction"]).to_csv(csv_path, index=False)
    print(f"Saved CSV:     {csv_path}")

    return rfm
