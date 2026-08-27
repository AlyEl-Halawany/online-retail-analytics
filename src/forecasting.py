"""
src/forecasting.py
==================
Revenue forecasting using statsmodels SARIMAX.

WHY SARIMAX INSTEAD OF PROPHET?
---------------------------------
Prophet (by Meta) is the more commonly cited choice for this type of problem,
but it has known installation issues on Python 3.12+ (requires pystan, which
requires a C++ compiler). On Python 3.14.2 it cannot be reliably installed
without a separate virtual environment.

SARIMAX (Seasonal AutoRegressive Integrated Moving Average with eXogenous
variables) from statsmodels is a strong alternative:
  - Ships with statsmodels, which is already installed
  - Handles both trend and seasonality in a single principled model
  - Produces confidence intervals that are calibrated (based on likelihood theory)
  - Every parameter has a direct statistical interpretation

SARIMAX MODEL NOTATION: SARIMAX(p,d,q)(P,D,Q,m)
  p = AR order (how many lags of the series itself)
  d = differencing order (how many times to difference for stationarity)
  q = MA order (how many lags of the residual)
  P,D,Q = seasonal equivalents of p,d,q
  m = seasonal period (12 = annual seasonality on monthly data)

We use order=(1,1,1)(1,1,1,12) which is a standard starting point for
monthly retail data: AR(1) captures momentum, I(1) removes trend,
MA(1) captures short-term shocks, and the seasonal component handles
the annual Christmas pattern.

VALIDATION: We train on the first 20 months and forecast the last 4 months
(Oct-Dec 2011 plus Dec 2009 as a warmup). We compare predicted vs actual
monthly revenue for those 4 months.

USAGE
-----
    from src.forecasting import run_forecasting_pipeline
    forecast_df = run_forecasting_pipeline(df)
"""

import pandas as pd
import numpy as np
from pathlib import Path
import warnings
warnings.filterwarnings("ignore")

import statsmodels.api as sm
from statsmodels.tsa.statespace.sarimax import SARIMAX


# ── Constants ─────────────────────────────────────────────────────────────────
FORECAST_PERIODS = 13      # ~one quarter ahead (13 weeks if weekly, 3 months if monthly)
TRAIN_CUTOFF_MONTHS = 20   # train on first 20 months, test on remaining


def build_monthly_revenue(df: pd.DataFrame) -> pd.Series:
    """
    Aggregate transaction data into a monthly revenue time series.
    Returns a pd.Series indexed by period (monthly).
    """
    monthly = (
        df.assign(Month=df["InvoiceDate"].dt.to_period("M"))
        .groupby("Month")["Revenue"]
        .sum()
        .sort_index()
    )
    # Convert PeriodIndex to DatetimeIndex (required by statsmodels)
    monthly.index = monthly.index.to_timestamp()
    return monthly


def run_forecasting_pipeline(
    df: pd.DataFrame,
    forecast_months: int = 3,
    output_csv: str | Path = "app/dashboard_data/forecast.csv",
    output_parquet: str | Path = "data/processed/forecast.parquet",
) -> pd.DataFrame:
    """
    Full forecasting pipeline:
    1. Build monthly revenue series
    2. Train-test split (temporal — first 20 months vs last ~4 months)
    3. Fit SARIMAX(1,1,1)(1,1,1,12)
    4. Evaluate on holdout
    5. Forecast next quarter with confidence intervals
    6. Return + save outputs
    """
    print("Building monthly revenue time series...")
    monthly = build_monthly_revenue(df)
    print(f"  Time series: {monthly.index[0].date()} to {monthly.index[-1].date()} ({len(monthly)} months)")

    # ── Train/test split (temporal) ───────────────────────────────────────────
    # IMPORTANT: We split temporally, not randomly. This mirrors actual deployment:
    # the model would be trained on all available history and used to forecast forward.
    #
    # NOTE ON MODEL CHOICE:
    # With only 25 months of data, SARIMAX(1,1,1)(1,1,1,12) is too aggressive —
    # seasonal differencing (D=1) consumes 12 observations just for the lag,
    # leaving very few effective training points. We use (1,1,1)(1,0,1,12) instead:
    # seasonal AR(1) and MA(1) capture the annual pattern without differencing,
    # which is appropriate when the series is not seasonally non-stationary
    # (i.e., the seasonal pattern is stable, not growing/shrinking year on year).
    n_test = 3   # hold out last 3 months — balances evaluation vs training data
    train = monthly.iloc[:-n_test]
    test = monthly.iloc[-n_test:]
    print(f"  Training on: {train.index[0].date()} to {train.index[-1].date()} ({len(train)} months)")
    print(f"  Holdout:     {test.index[0].date()} to {test.index[-1].date()} ({len(test)} months)")

    # ── Fit SARIMAX model ─────────────────────────────────────────────────────
    print("\nFitting SARIMAX(1,1,1)(1,0,1,12)...")
    print("  Note: D=0 (no seasonal differencing) chosen because 25 months of data")
    print("  is insufficient for stable seasonal differencing (needs 24+ obs for lag alone).")
    model = SARIMAX(
        train,
        order=(1, 1, 1),             # non-seasonal: AR(1), one difference, MA(1)
        seasonal_order=(1, 0, 1, 12), # seasonal: SAR(1) + SMA(1), no seasonal diff
        enforce_stationarity=False,
        enforce_invertibility=False,
    )
    fitted = model.fit(disp=False)  # disp=False suppresses optimiser output

    print(f"\nModel AIC: {fitted.aic:.2f}  (lower = better fit)")

    # ── Evaluate on holdout ───────────────────────────────────────────────────
    holdout_forecast = fitted.get_forecast(steps=n_test)
    holdout_pred = holdout_forecast.predicted_mean
    holdout_ci = holdout_forecast.conf_int(alpha=0.20)   # 80% CI

    mae = np.mean(np.abs(holdout_pred - test.values))
    mape = np.mean(np.abs((holdout_pred - test.values) / test.values)) * 100

    print(f"\nHoldout performance ({n_test} months):")
    print(f"  MAE:  GBP {mae:,.0f}")
    print(f"  MAPE: {mape:.1f}%")
    print("\nActual vs Predicted (holdout):")
    for date, actual, pred in zip(test.index, test.values, holdout_pred):
        print(f"  {date.strftime('%Y-%m')}: Actual GBP {actual:>10,.0f} | "
              f"Predicted GBP {pred:>10,.0f} | "
              f"Error {abs(actual-pred)/actual*100:.1f}%")

    # ── Refit on full series and forecast forward ─────────────────────────────
    print("\nRefitting on full dataset and forecasting next quarter...")
    full_model = SARIMAX(
        monthly,
        order=(1, 1, 1),
        seasonal_order=(1, 1, 1, 12),
        enforce_stationarity=False,
        enforce_invertibility=False,
    )
    full_fitted = full_model.fit(disp=False)

    forecast = full_fitted.get_forecast(steps=forecast_months)
    forecast_mean = forecast.predicted_mean
    forecast_ci_80 = forecast.conf_int(alpha=0.20)   # 80% CI
    forecast_ci_95 = forecast.conf_int(alpha=0.05)   # 95% CI

    # ── Build output DataFrame ────────────────────────────────────────────────
    # Historical + forecast combined — useful for the Power BI trend visual

    hist_df = pd.DataFrame({
        "date": monthly.index,
        "revenue": monthly.values,
        "type": "Historical",
        "forecast_mean": monthly.values,
        "lower_80": np.nan,
        "upper_80": np.nan,
        "lower_95": np.nan,
        "upper_95": np.nan,
    })

    fcast_df = pd.DataFrame({
        "date": forecast_mean.index,
        "revenue": np.nan,
        "type": "Forecast",
        "forecast_mean": forecast_mean.values,
        "lower_80": forecast_ci_80.iloc[:, 0].values,
        "upper_80": forecast_ci_80.iloc[:, 1].values,
        "lower_95": forecast_ci_95.iloc[:, 0].values,
        "upper_95": forecast_ci_95.iloc[:, 1].values,
    })

    output_df = pd.concat([hist_df, fcast_df], ignore_index=True)

    # Print forecast
    print(f"\nNext-quarter revenue forecast (GBP):")
    for _, row in fcast_df.iterrows():
        print(f"  {row['date'].strftime('%Y-%m')}: "
              f"GBP {row['forecast_mean']:>10,.0f}  "
              f"[80% CI: {row['lower_80']:,.0f} – {row['upper_80']:,.0f}]")

    # ── Seasonality decomposition ─────────────────────────────────────────────
    # Extract the seasonal component to quantify the Christmas effect
    decomp = sm.tsa.seasonal_decompose(monthly, model="additive", period=12)
    seasonal_component = decomp.seasonal

    peak_month = seasonal_component.groupby(seasonal_component.index.month).mean().idxmax()
    trough_month = seasonal_component.groupby(seasonal_component.index.month).mean().idxmin()
    month_names = {1:"Jan",2:"Feb",3:"Mar",4:"Apr",5:"May",6:"Jun",
                   7:"Jul",8:"Aug",9:"Sep",10:"Oct",11:"Nov",12:"Dec"}
    print(f"\nSeasonality analysis:")
    print(f"  Peak month:   {month_names[peak_month]} (strongest Christmas build-up)")
    print(f"  Trough month: {month_names[trough_month]} (weakest demand period)")
    seasonal_range = seasonal_component.groupby(seasonal_component.index.month).mean()
    swing = seasonal_range.max() - seasonal_range.min()
    print(f"  Seasonal swing (peak-to-trough): GBP {swing:,.0f}/month")
    print("  BUSINESS IMPLICATION: Inventory orders and staffing should be")
    print(f"  front-loaded by 6-8 weeks ahead of {month_names[peak_month]} — orders must")
    print("  arrive before the demand surge, not during it.")

    # ── Save ──────────────────────────────────────────────────────────────────
    Path(output_csv).parent.mkdir(parents=True, exist_ok=True)
    output_df.to_csv(output_csv, index=False)
    Path(output_parquet).parent.mkdir(parents=True, exist_ok=True)
    output_df.to_parquet(output_parquet, index=False, engine="pyarrow")
    print(f"\nForecast saved: {output_csv}")

    return output_df, fitted, decomp
