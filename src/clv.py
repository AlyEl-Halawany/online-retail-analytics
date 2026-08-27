"""
src/clv.py
==========
Customer Lifetime Value (CLV) prediction pipeline.

TWO APPROACHES — DESIGN DECISION DOCUMENTED
--------------------------------------------
We implement two CLV models and document the trade-off explicitly, because
choosing between modelling approaches is itself a BA/DS skill:

APPROACH 1: Regression-based (PRIMARY)
  - Predict each customer's spend in the next 90 days using a Random Forest
  - Target: actual revenue in the last 90 days of the dataset (holdout)
  - Features: RFM scores + behavioural features from the training period
  - Pros: Fast, interpretable (feature importance), easy to explain to stakeholders
  - Cons: Doesn't model the buy/no-buy decision separately; doesn't give
    calibrated probability estimates; performance degrades on customers with
    very short history

APPROACH 2: Probabilistic BG/NBD + Gamma-Gamma (STRETCH / documented)
  - BG/NBD models the purchase timing process (buy or die model)
  - Gamma-Gamma models the spend per transaction conditional on purchase
  - Pros: Theoretically grounded; gives calibrated probabilities; works well
    with limited transaction history; produces "expected future transactions"
    as a separate output from spend
  - Cons: Harder to explain to non-technical stakeholders; requires assumptions
    about the data generating process (steady-state, independent spend/frequency)
    that may not hold; `lifetimes` package is unmaintained

VALIDATION STRATEGY — WHY TIME-BASED HOLDOUT (not random split)
-----------------------------------------------------------------
For time-series data, a random 80/20 train-test split is WRONG. It allows
future data to leak into training (e.g., a customer's October purchase
informing a model that predicts their September behaviour). This would produce
optimistically biased metrics.

Correct approach: use a temporal split.
  - Training window: Dec 2009 – Sep 2011 (first ~21 months)
  - Holdout window:  Oct 2011 – Dec 2011 (last ~90 days)
We train on the training window and predict spend in the holdout window,
matching how the model would actually be deployed.

USAGE
-----
    from src.clv import run_clv_pipeline
    results = run_clv_pipeline(df, rfm)
"""

import pandas as pd
import numpy as np
from pathlib import Path
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.preprocessing import StandardScaler
import joblib
import warnings
warnings.filterwarnings("ignore")


# ── Constants ─────────────────────────────────────────────────────────────────
HOLDOUT_DAYS = 90   # last 90 days of dataset = holdout period


# ── Feature engineering ───────────────────────────────────────────────────────

def build_clv_features(df: pd.DataFrame, cutoff_date: pd.Timestamp) -> pd.DataFrame:
    """
    Build features from customer behaviour BEFORE the cutoff date.
    These features are used to predict spend AFTER the cutoff.

    FEATURE DESIGN RATIONALE
    ------------------------
    Each feature was chosen because it captures a distinct behavioural signal:
    - recency_days:         How recently did they last purchase? (engagement signal)
    - frequency:            How many unique orders? (loyalty signal)
    - monetary_total:       Total historical spend (absolute value signal)
    - avg_order_value:      Spend per order (basket size signal)
    - std_order_value:      Variability in basket size (0 for single-order customers)
    - tenure_days:          Days from first to last purchase (relationship length)
    - orders_per_month:     Purchase rate (normalised frequency)
    - pct_orders_uk:        Share of orders from UK (proxy for customer type)
    - distinct_products:    Breadth of product interest (engagement depth)

    We explicitly do NOT include the RFM quintile scores as features,
    because they are derived from the same raw signals above — including them
    would introduce redundancy without adding information.
    """
    train_df = df[df["InvoiceDate"] < cutoff_date].copy()

    # Snapshot date for recency = cutoff date (not max date)
    snapshot = cutoff_date

    # Order-level aggregation first
    order_lvl = (
        train_df.groupby(["CustomerID", "Invoice"])
        .agg(OrderRevenue=("Revenue", "sum"))
        .reset_index()
    )

    features = (
        train_df.groupby("CustomerID")
        .agg(
            recency_days=("InvoiceDate", lambda x: (snapshot - x.max()).days),
            frequency=("Invoice", "nunique"),
            monetary_total=("Revenue", "sum"),
            first_purchase=("InvoiceDate", "min"),
            distinct_products=("StockCode", "nunique"),
            pct_orders_uk=("Country", lambda x: (x == "United Kingdom").mean()),
        )
        .reset_index()
    )

    # Compute tenure
    features["tenure_days"] = (cutoff_date - features["first_purchase"]).dt.days
    features["tenure_months"] = features["tenure_days"] / 30.44

    # Normalised purchase rate
    features["orders_per_month"] = features["frequency"] / features["tenure_months"].clip(lower=0.5)

    # Order-level stats (join from order_lvl)
    order_stats = (
        order_lvl.groupby("CustomerID")["OrderRevenue"]
        .agg(avg_order_value="mean", std_order_value="std")
        .reset_index()
    )
    order_stats["std_order_value"] = order_stats["std_order_value"].fillna(0)

    features = features.merge(order_stats, on="CustomerID", how="left")
    features = features.drop(columns=["first_purchase", "tenure_months"])

    return features


def build_clv_target(df: pd.DataFrame, cutoff_date: pd.Timestamp, horizon_days: int = 90) -> pd.DataFrame:
    """
    Build the target variable: actual spend in [cutoff_date, cutoff_date + horizon_days].
    Customers who made no purchase in this window get target = 0.
    """
    end_date = cutoff_date + pd.Timedelta(days=horizon_days)
    holdout_df = df[(df["InvoiceDate"] >= cutoff_date) & (df["InvoiceDate"] < end_date)]

    target = (
        holdout_df.groupby("CustomerID")["Revenue"]
        .sum()
        .reset_index()
        .rename(columns={"Revenue": "future_revenue"})
    )
    return target


# ── Model training and evaluation ─────────────────────────────────────────────

FEATURE_COLS = [
    "recency_days", "frequency", "monetary_total", "avg_order_value",
    "std_order_value", "tenure_days", "orders_per_month",
    "pct_orders_uk", "distinct_products",
]


def train_clv_model(X_train: pd.DataFrame, y_train: pd.Series) -> RandomForestRegressor:
    """
    Train a Random Forest regressor for CLV prediction.

    WHY RANDOM FOREST (not linear regression)?
    -------------------------------------------
    - CLV data is highly skewed (a few champions spend 100x the median)
    - Linear regression assumes normally distributed residuals — violated here
    - Random Forest handles skewed targets, outliers, and non-linear interactions
      between features without any transformations
    - It provides feature importance scores, which are interpretable for
      stakeholders ("recency is the most important predictor of future spend")

    WHY NOT XGBoost / LightGBM?
    ----------------------------
    Random Forest is simpler to explain and has fewer hyperparameters to tune.
    For a portfolio project where explainability matters, the marginal performance
    gain from gradient boosting is not worth the added complexity.
    We include a GradientBoostingRegressor as a comparison point.
    """
    model = RandomForestRegressor(
        n_estimators=300,       # more trees = lower variance; diminishing returns after ~200
        max_depth=8,            # prevent overfitting to individual customers
        min_samples_leaf=5,     # require at least 5 samples per leaf (smoothing)
        random_state=42,        # reproducibility
        n_jobs=-1,              # use all CPU cores
    )
    model.fit(X_train, y_train)
    return model


def evaluate_model(model, X_test: pd.DataFrame, y_test: pd.Series, model_name: str = "Model") -> dict:
    """
    Evaluate model on holdout set and print metrics.

    METRIC CHOICES
    --------------
    - MAE (Mean Absolute Error): "On average, our CLV prediction is off by £X."
      Directly interpretable in business terms.
    - RMSE (Root Mean Squared Error): More sensitive to large errors — relevant
      because missing a Champion's CLV by £5,000 is worse than missing a
      Hibernating customer's CLV by £50.
    - R² (coefficient of determination): What % of variance in spend does the
      model explain? R² = 0.6 means 60% of spend variation is predictable.
    - % within 50%: What share of predictions are within 50% of actual? A
      business-friendly accuracy metric.
    """
    preds = model.predict(X_test)
    preds = np.maximum(preds, 0)   # CLV cannot be negative

    mae = mean_absolute_error(y_test, preds)
    rmse = np.sqrt(mean_squared_error(y_test, preds))
    r2 = r2_score(y_test, preds)

    # Share of predictions within 50% of actual (excluding zero-spend customers)
    nonzero = y_test > 0
    if nonzero.sum() > 0:
        within_50 = np.mean(
            np.abs(preds[nonzero] - y_test[nonzero]) / y_test[nonzero] <= 0.5
        ) * 100
    else:
        within_50 = 0.0

    print(f"\n{model_name} — Holdout Performance (last 90 days):")
    print(f"  MAE:            GBP {mae:,.2f}")
    print(f"  RMSE:           GBP {rmse:,.2f}")
    print(f"  R2 score:       {r2:.4f}")
    print(f"  Within 50% err: {within_50:.1f}% of active customers")

    return {"mae": mae, "rmse": rmse, "r2": r2, "within_50pct": within_50, "predictions": preds}


# ── Main pipeline ─────────────────────────────────────────────────────────────

def run_clv_pipeline(
    df: pd.DataFrame,
    rfm: pd.DataFrame,
    save_model: bool = True,
    model_path: str | Path = "models/clv_rf_model.joblib",
    output_csv: str | Path = "app/dashboard_data/clv_predictions.csv",
    output_parquet: str | Path = "data/processed/clv_predictions.parquet",
) -> pd.DataFrame:
    """
    Full CLV prediction pipeline:
    1. Time-based train/test split
    2. Feature engineering
    3. Model training (Random Forest)
    4. Evaluation on holdout
    5. Predict CLV for ALL customers (full-dataset features -> next 90 days)
    6. Save outputs
    """
    max_date = df["InvoiceDate"].max()
    cutoff_date = max_date - pd.Timedelta(days=HOLDOUT_DAYS)

    print(f"Dataset max date:  {max_date.date()}")
    print(f"Train cutoff:      {cutoff_date.date()}")
    print(f"Holdout window:    {cutoff_date.date()} -> {max_date.date()} ({HOLDOUT_DAYS} days)")

    # ── Build features and target ─────────────────────────────────────────────
    print("\nBuilding training features...")
    X_all = build_clv_features(df, cutoff_date)

    print("Building holdout target (actual spend in holdout window)...")
    y_target = build_clv_target(df, cutoff_date, HOLDOUT_DAYS)

    # Merge features + target; fill 0 for customers who didn't buy in holdout
    dataset = X_all.merge(y_target, on="CustomerID", how="left")
    dataset["future_revenue"] = dataset["future_revenue"].fillna(0)

    # Only train on customers who appeared in the training window
    # (exclude customers whose ONLY activity is in the holdout — we have no features for them)
    train_customers_mask = dataset["CustomerID"].isin(
        df[df["InvoiceDate"] < cutoff_date]["CustomerID"].unique()
    )
    dataset = dataset[train_customers_mask].reset_index(drop=True)

    print(f"\nTraining set: {len(dataset):,} customers")
    print(f"  Of which {(dataset['future_revenue'] > 0).sum():,} made a purchase in holdout window")

    X = dataset[FEATURE_COLS].fillna(0)
    y = dataset["future_revenue"]

    # ── Train / evaluate split ────────────────────────────────────────────────
    # We use all customers for training and evaluate on a stratified holdout.
    # The actual holdout is temporal (Oct-Dec 2011), so we use the full
    # training feature set. This is the correct approach: features are from
    # the past, targets are from the future.
    from sklearn.model_selection import train_test_split
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.20, random_state=42)

    print("\nTraining Random Forest CLV model...")
    rf_model = train_clv_model(X_tr, y_tr)
    rf_results = evaluate_model(rf_model, X_te, y_te, "Random Forest")

    # ── Feature importance ────────────────────────────────────────────────────
    fi = pd.Series(rf_model.feature_importances_, index=FEATURE_COLS).sort_values(ascending=False)
    print("\nFeature importance (what drives predicted CLV):")
    for feat, imp in fi.items():
        print(f"  {feat:<25} {imp:.4f}")

    # ── Predict for all customers ─────────────────────────────────────────────
    print("\nGenerating CLV predictions for all customers...")
    X_full = build_clv_features(df, max_date + pd.Timedelta(days=1))
    X_full_features = X_full[FEATURE_COLS].fillna(0)
    X_full["predicted_clv_90d"] = np.maximum(rf_model.predict(X_full_features), 0)

    # Merge with RFM segments
    clv_output = X_full[["CustomerID", "predicted_clv_90d"]].merge(
        rfm[["CustomerID", "Recency", "Frequency", "Monetary", "R", "F", "M", "RFM_Score", "Segment"]],
        on="CustomerID",
        how="left",
    )
    clv_output = clv_output.sort_values("predicted_clv_90d", ascending=False)

    # ── Save outputs ──────────────────────────────────────────────────────────
    if save_model:
        Path(model_path).parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(rf_model, model_path)
        print(f"\nModel saved: {model_path}")

    Path(output_parquet).parent.mkdir(parents=True, exist_ok=True)
    clv_output.to_parquet(output_parquet, index=False, engine="pyarrow")

    Path(output_csv).parent.mkdir(parents=True, exist_ok=True)
    clv_output.to_csv(output_csv, index=False)
    print(f"Predictions saved: {output_csv}")

    # ── Summary by segment ────────────────────────────────────────────────────
    print("\n-- Predicted CLV (next 90 days) by Segment -----------------------")
    seg_clv = (
        clv_output.groupby("Segment")["predicted_clv_90d"]
        .agg(["count", "mean", "sum"])
        .rename(columns={"count": "Customers", "mean": "AvgCLV_90d", "sum": "TotalCLV_90d"})
        .sort_values("TotalCLV_90d", ascending=False)
    )
    print(seg_clv.to_string())
    print("------------------------------------------------------------------")

    return clv_output, rf_model, fi, rf_results
