# Online Retail II — Customer Analytics

> Customer analytics project — RFM segmentation, Customer Lifetime Value prediction, sales forecasting, and cohort retention analysis on ~1M retail transactions from a UK-based online retailer.

[![Python](https://img.shields.io/badge/Python-3.11%2B-blue)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## Problem

A UK-based online gift retailer has two years of transaction history and no systematic view of which customers are driving revenue, which are at risk of churning, or where retention budget should go. Marketing campaigns are sent to the entire customer base with no targeting — a costly and ineffective approach when most revenue is concentrated in a small fraction of customers.

**Business question:** Which customers are highest-value, which are at risk of lapsing, and where should retention investment go to maximise return?

---

## Dataset

| Attribute | Detail |
|---|---|
| Source | [UCI Machine Learning Repository — Online Retail II](https://archive.ics.uci.edu/dataset/502/online+retail+ii) |
| Rows | ~1,067,371 (raw); 779,425 after cleaning |
| Customers | 5,878 (after removing guest transactions) |
| Time period | 01 Dec 2009 – 09 Dec 2011 (25 months) |
| Countries | 40+ |
| Revenue | £17.37M (cleaned) |
| Columns | Invoice, StockCode, Description, Quantity, InvoiceDate, Price, CustomerID, Country |

**Cleaning decisions (all documented in `src/data_cleaning.py`):**
- Removed 243,007 rows with missing CustomerID — guest transactions cannot be attributed to a customer-level model
- Removed 18,744 cancelled orders (Invoice prefix "C") — negative quantities corrupt monetary metrics
- Removed 71 zero-price rows (test/gift items)
- Removed 26,124 exact duplicates

---

## Approach

Each step traces back to a specific business question from the [problem statement](docs/business_problem.md).

```
Step 0  Business problem framing       docs/business_problem.md
Step 1  Data cleaning + EDA            src/data_cleaning.py  |  notebooks/01_eda.py
Step 2  RFM Segmentation               src/rfm.py            |  notebooks/02_rfm_segmentation.py
Step 3  CLV Prediction                 src/clv.py            |  notebooks/03_clv_prediction.py
Step 4  Sales Forecasting              src/forecasting.py    |  notebooks/04_forecasting.py
Step 5  Cohort Retention               src/cohort.py         |  notebooks/05_cohort_retention.py
Step 6  Dashboard                      app/dashboard_data/   |  docs/powerbi_guide.md
Step 7  Recommendations Memo           docs/recommendations_memo.md
```

### Step 2 — RFM Segmentation

Customers are scored on three dimensions from their transaction history:
- **Recency** — days since last purchase (lower = better)
- **Frequency** — number of unique invoices
- **Monetary** — total revenue attributable to the customer

Each dimension is scored in quintiles (1–5) and combined into named segments using a transparent rule-based approach — deliberately chosen over clustering for stakeholder explainability.

### Step 3 — CLV Prediction

Primary model: **Random Forest Regressor** predicting each customer's spend in the next 90 days. Trained on a time-based split (not a random split — this is a temporal problem). Features include recency, frequency, monetary, tenure, purchase rate, and product diversity.

The probabilistic approach (BG/NBD + Gamma-Gamma) is documented in `src/clv.py` with a full trade-off writeup.

### Step 4 — Sales Forecasting

**SARIMAX(1,1,1)(1,0,1,12)** on monthly revenue. Seasonal differencing (D=1) was excluded because 25 months of data is insufficient to estimate it stably. The model correctly identifies November as the peak month (Christmas gifting demand) with a seasonal swing of £728K above the February trough.

Holdout performance (Oct–Nov 2011): **MAE = 13.8% and 15.5%** — within the target ±15% confidence window (December is excluded from the evaluation because the dataset ends on 9 Dec, so the "actual" is only 9 days of the month).

### Step 5 — Cohort Retention

Customers grouped by first-purchase month. The retention matrix tracks what fraction of each cohort returns in subsequent months.

---

## Results

### Key Findings

| Finding | Metric |
|---|---|
| Revenue concentration | Top 20% of customers drive **77.2% of revenue** |
| Champion segment | 22% of customers, **68.3% of revenue**, avg spend £9,144 |
| Month 1 retention | Only **21.2%** of customers make a second purchase |
| Seasonal peak | November is **£728K above** the seasonal baseline |
| At-Risk revenue | £4.1M (23% of total) in historically loyal but now lapsing customers |
| CLV (Champions, next 90d) | Avg £1,880 predicted per customer |

### RFM Segment Summary

| Segment | Customers | % of Base | Revenue | % of Revenue | Avg Spend |
|---|---|---|---|---|---|
| Champions | 1,297 | 22.1% | £11.9M | 68.3% | £9,144 |
| Loyal Customers | 1,754 | 29.8% | £4.1M | 23.4% | £2,322 |
| At Risk - Low Value | 915 | 15.6% | £454K | 2.6% | £496 |
| Needs Attention | 806 | 13.7% | £442K | 2.5% | £548 |
| Potential Loyalists | 277 | 4.7% | £364K | 2.1% | £1,313 |
| Hibernating | 732 | 12.5% | £168K | 1.0% | £229 |
| New Customers | 97 | 1.7% | £16K | 0.1% | £166 |

---

## Business Impact

*For a non-technical reader.*

Three actions are immediately justified by the data:

**1. Win-back the Loyal Customers.** Nearly 1,800 customers who used to buy regularly have gone quiet — they represent £4.1M in historical spend. A personalised reactivation campaign with a 15% conversion rate could recover ~£350,000 this quarter alone.

**2. Protect the Champions.** 1,300 customers generate nearly £12M in annual revenue. A lightweight VIP recognition programme (early access, exclusive previews) costs very little and protects the business's most critical relationships. These customers do not need discounts — they already buy.

**3. Fix the onboarding gap.** Only 1 in 5 new customers ever makes a second purchase. A structured 30-day email welcome sequence costs almost nothing to implement and could lift second-purchase conversion from 21% to 30% — adding hundreds of retained customers per year without spending a pound on acquisition.

---

## Limitations

This project is honest about what the data cannot answer:

- **Single retailer, single geography.** All findings are specific to this retailer's customer base. The patterns (Pareto concentration, seasonal spike) are common in gift retail, but the specific numbers should not be assumed to generalise.

- **No marketing attribution data.** The dataset does not include which customers received which campaigns, or when. We cannot measure campaign ROI or account for marketing spend in the revenue model.

- **No product margin data.** Revenue is gross (Quantity × Price). High-revenue segments may not be high-profit segments if margins differ by product category.

- **Two-year window.** The dataset ends in December 2011. Customer behaviour may have shifted. The cohort retention analysis is particularly sensitive to this — later cohorts have fewer follow-up months available by definition.

- **Guest transactions excluded.** ~23% of raw transactions had no Customer ID and were excluded. If guest buyers behave systematically differently from registered customers, our customer-level metrics will not reflect the full picture.

- **SARIMAX forecasting on short series.** 25 months of monthly data is at the minimum viable range for seasonal time series modelling. Confidence intervals on the forecast are wide — treat the forecast as directional planning input, not a precise prediction.

---

## Project Structure

```
/data/raw/             Raw CSV (gitignored — too large to commit)
/data/processed/       Cleaned parquet files and output CSVs
/data/processed/figures/  All charts generated by notebooks
/notebooks/            Analysis scripts (01–05)
/src/                  Reusable pipeline modules
/app/dashboard_data/   CSV exports for Power BI
/docs/                 Business problem statement, recommendations memo, Power BI guide
/models/               Saved model artifacts (gitignored if >50MB)
```

## Reproducing the Analysis

```bash
# 1. Clone the repo
git clone https://github.com/AlyEl-Halawany/online-retail-analytics.git
cd online-retail-analytics

# 2. Install dependencies
pip install -r requirements.txt

# 3. Place the raw data file
# Download from: https://archive.ics.uci.edu/dataset/502/online+retail+ii
# Save as: data/raw/online_retail_II.csv

# 4. Run notebooks in order
python notebooks/01_eda.py
python notebooks/02_rfm_segmentation.py
python notebooks/03_clv_prediction.py
python notebooks/04_forecasting.py
python notebooks/05_cohort_retention.py

# All figures are saved to data/processed/figures/
# Dashboard CSVs are saved to app/dashboard_data/
```

---

## Tools Used

| Tool | Purpose |
|---|---|
| Python 3.11+ | Core language |
| pandas | Data manipulation and cleaning |
| scikit-learn | Random Forest CLV model |
| statsmodels | SARIMAX time-series forecasting |
| matplotlib / seaborn | All visualisations |
| Power BI Desktop | Interactive dashboard |
| Git / GitHub | Version control with incremental commits |
