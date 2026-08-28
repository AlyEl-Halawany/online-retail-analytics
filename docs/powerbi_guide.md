# Power BI Dashboard — Build Guide
**Project:** Online Retail II Customer Analytics  
**Data source:** `app/dashboard_data/` (5 CSV files)

This guide walks you through building the full interactive dashboard from the pre-exported CSVs. Estimated time: 60–90 minutes for a first build.

---

## Step 1: Load Data

1. Open **Power BI Desktop** → **Get Data → Text/CSV**
2. Load all five files from `app/dashboard_data/`:

| File | Contents |
|---|---|
| `customers_rfm.csv` | One row per customer: RFM scores, segment, historical spend |
| `clv_predictions.csv` | One row per customer: predicted 90-day CLV + segment |
| `monthly_revenue.csv` | Monthly revenue for trend visual |
| `forecast.csv` | Historical + forecast revenue with confidence intervals |
| `cohort_matrix.csv` | Cohort retention rates (wide format, rows = cohort months) |

3. In **Power Query**, verify:
   - `customers_rfm.csv`: CustomerID as Text, Recency/Frequency/Monetary as Decimal
   - `forecast.csv`: `date` column → change type to **Date**
   - `cohort_matrix.csv`: First column = "CohortMonth" as Text

---

## Step 2: Data Model (Relationships)

In the **Model** view, create one relationship:

- `customers_rfm[CustomerID]` → `clv_predictions[CustomerID]` (Many-to-one, `clv_predictions` is the one side)

The `forecast` and `cohort_matrix` tables are standalone — no relationships needed.

---

## Step 3: DAX Measures

Create a dedicated **Measures table** (Enter Data → blank table named "Measures").

Paste each measure below:

```dax
-- Total Historical Revenue
Total Revenue = SUM(customers_rfm[Monetary])

-- Total Customers
Total Customers = DISTINCTCOUNT(customers_rfm[CustomerID])

-- Average CLV (next 90 days)
Avg CLV 90d = AVERAGE(clv_predictions[predicted_clv_90d])

-- Revenue by Segment (used in segment slicer visuals)
Segment Revenue = 
CALCULATE(
    SUM(customers_rfm[Monetary]),
    ALLEXCEPT(customers_rfm, customers_rfm[Segment])
)

-- % of Total Revenue
Revenue Share % = 
DIVIDE(
    SUM(customers_rfm[Monetary]),
    CALCULATE(SUM(customers_rfm[Monetary]), ALL(customers_rfm))
) * 100

-- Customer Count by Segment
Customers in Segment = COUNTROWS(customers_rfm)

-- Average Recency (days)
Avg Recency = AVERAGE(customers_rfm[Recency])

-- At-Risk Revenue (customers in At Risk segments)
At Risk Revenue = 
CALCULATE(
    SUM(customers_rfm[Monetary]),
    customers_rfm[Segment] IN {"At Risk", "At Risk - Low Value"}
)

-- Champion Revenue Share
Champion Revenue % = 
DIVIDE(
    CALCULATE(SUM(customers_rfm[Monetary]), customers_rfm[Segment] = "Champions"),
    SUM(customers_rfm[Monetary])
) * 100
```

---

## Step 4: Report Pages

Build 4 pages:

---

### Page 1: Executive Overview

**Visuals:**
1. **4 KPI Cards** (top row):
   - Total Revenue: `Total Revenue` → Format as GBP
   - Total Customers: `Total Customers`
   - Champion Revenue Share: `Champion Revenue %` → format as %
   - At-Risk Revenue: `At Risk Revenue` → format as GBP

2. **Donut Chart** — Revenue by Segment:
   - Legend: `customers_rfm[Segment]`
   - Values: `Total Revenue`
   - Colours: match `SEGMENT_COLORS` from the Python analysis (Champions = `#2E86AB`, etc.)

3. **Bar Chart** — Customer Count by Segment:
   - Axis: `customers_rfm[Segment]`
   - Values: `Total Customers`
   - Sort by `Total Revenue` descending

4. **Matrix** — Segment summary table:
   - Rows: `Segment`
   - Values: `Total Customers`, `Total Revenue`, `Revenue Share %`, `Avg Recency`, `Avg CLV 90d`

**Filters:** Add a **Slicer** on `customers_rfm[Segment]` (tile style)

---

### Page 2: Revenue Trends & Forecast

**Visuals:**
1. **Line Chart** — Historical Revenue:
   - X-axis: `forecast[date]`
   - Values: `forecast[revenue]` (label: "Actual")
   - Filter to `forecast[type] = "Historical"`

2. **Line + Shaded Area** — Revenue Forecast:
   - Create a second line: `forecast[forecast_mean]`
   - Add error bars or ribbon using `forecast[lower_80]` and `forecast[upper_80]`
   - *Tip:* Use a combo chart — line for actual, shaded area for CI bands

3. **Bar Chart** — Seasonal Pattern (from the seasonal component values in `forecast.csv`, or use the monthly revenue table):
   - X-axis: Month name (derive from `date` column: `FORMAT([date], "MMM")`)
   - Values: `forecast[revenue]` aggregated by month name (average)

**Filters:** Date range slicer on `forecast[date]`

---

### Page 3: Customer Segments & CLV

**Visuals:**
1. **Scatter Plot** — Recency vs Frequency:
   - X-axis: `customers_rfm[Recency]`
   - Y-axis: `customers_rfm[Frequency]`
   - Color: `customers_rfm[Segment]`
   - Size: `customers_rfm[Monetary]`
   - Tooltip: CustomerID, Monetary, Segment

2. **Bar Chart** — Average CLV by Segment:
   - Axis: `clv_predictions[Segment]`
   - Values: `Avg CLV 90d`

3. **Clustered Bar Chart** — Historical Spend vs Predicted CLV:
   - Axis: `Segment`
   - Values: `Total Revenue` (historical) + `Avg CLV 90d`

4. **Table** — Top 20 customers by predicted CLV:
   - Columns: CustomerID, Segment, Recency, Frequency, Monetary, predicted_clv_90d
   - Sort: `predicted_clv_90d` descending

**Filters:** Segment slicer, Country slicer (from `customers_rfm[Country]` if available)

---

### Page 4: Cohort Retention

**Visuals:**
1. **Matrix (Heatmap)** — Cohort Retention:
   - First, unpivot the `cohort_matrix.csv` in Power Query:
     - Select all month columns → Transform → Unpivot Other Columns
     - Rename: Attribute → "MonthNumber", Value → "RetentionRate"
   - In the visual: Rows = `CohortMonth`, Columns = `MonthNumber`, Values = `RetentionRate`
   - In Format → Conditional Formatting → Background Color → apply colour scale (white → red, min=0, max=100)

2. **Line Chart** — Average Retention Curve:
   - X-axis: `MonthNumber`
   - Y-axis: Average of `RetentionRate`
   - Add a reference line at y=21.2% (Month 1 average) for the "industry gap" call-out

3. **Card** — Month 1 Retention:
   - Measure: `CALCULATE(AVERAGE(cohort_unpivoted[RetentionRate]), cohort_unpivoted[MonthNumber] = "1")`

**No additional filters needed on this page**

---

## Step 5: Interactive Filters (Global)

Add to every page via **Sync Slicers** (View → Sync Slicers):
- **Segment slicer** — tile style, multi-select enabled
- **Country slicer** — dropdown (from `customers_rfm` — requires merging country back in if not present)

---

## Step 6: Formatting Tips

- Theme: Create a custom theme JSON or use "Executive" built-in theme
- Font: Segoe UI throughout (Power BI default — clean and readable)
- Segment colours — set manually to match the Python charts:
  - Champions: `#2E86AB`
  - Loyal Customers: `#A23B72`
  - Potential Loyalists: `#F18F01`
  - At Risk: `#E84855`
  - At Risk - Low Value: `#F4A261`
  - Hibernating: `#8D99AE`
- Add a text box on each page with a 1-sentence "INSIGHT:" annotation explaining the key takeaway of that page

---

## Step 7: Publish

1. Save as `app/online_retail_dashboard.pbix`
2. Publish to Power BI Service (optional — requires Power BI Pro or free trial)
3. Share the link or export key pages as PDF for documentation
