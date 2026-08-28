# Power BI Dashboard — Step-by-Step Build Guide

> This guide is written for someone who has never built this specific dashboard before.
> Every click is described. Screenshots are described by what you'll see on screen.

---

## Before you start — what you need

- Power BI Desktop installed (free download from microsoft.com/en-us/power-bi)
- The `app/dashboard_data/` folder from this repo with these 5 files:
  - `customers_rfm.csv`
  - `clv_predictions.csv`
  - `monthly_revenue.csv`
  - `forecast.csv`
  - `cohort_matrix.csv`

---

## PART 1 — Load the data (15 min)

### 1a. Open Power BI Desktop

When it opens you'll see a splash screen with "New", "Open", "Recent".
Click anywhere outside it to dismiss, or click **Get data** in the top ribbon.

---

### 1b. Load customers_rfm.csv

1. Click **Home** tab in the top ribbon
2. Click **Get data** (the icon with a cylinder and an arrow)
3. In the dropdown, click **Text/CSV**
4. A file browser opens — navigate to your `app/dashboard_data/` folder
5. Select `customers_rfm.csv` → click **Open**
6. A preview window appears showing the data. Check that:
   - `CustomerID` column shows numbers like `12346`, `12347`
   - `Recency` shows whole numbers (days)
   - `Monetary` shows decimals (revenue in GBP)
7. Click **Load** (bottom right of the preview window)
8. You'll see a loading bar at the bottom right. Wait for it to finish.

---

### 1c. Load the other 4 files — repeat step 1b for each:

Go to **Home → Get data → Text/CSV** each time.

| File to load | What to check in the preview |
|---|---|
| `clv_predictions.csv` | `predicted_clv_90d` column shows decimal numbers |
| `monthly_revenue.csv` | `date` column shows dates like `2009-12-01` |
| `forecast.csv` | Has columns: `date`, `revenue`, `type`, `forecast_mean`, `lower_80`, `upper_80` |
| `cohort_matrix.csv` | First column is `CohortMonth` with values like `2009-12` |

---

### 1d. Fix the date column in forecast.csv

After loading, the `date` column might be read as text. Fix it:

1. Click **Transform data** in the Home ribbon (this opens Power Query Editor)
2. In the left panel (**Queries**), click `forecast`
3. Click the `date` column header to select it
4. In the top ribbon, click **Transform** tab
5. Click **Data Type** → select **Date**
6. A dialog may appear asking "Replace or Add step?" — click **Replace current**
7. Do the same for `monthly_revenue` → select `date` column → change to **Date**
8. Click **Close & Apply** (top-left of Power Query Editor)
9. Wait for it to apply — a loading bar appears at the bottom

---

### 1e. Fix the cohort_matrix — unpivot it (IMPORTANT)

The cohort matrix is in "wide" format (months as columns). Power BI needs it in "tall" format (one row per cohort × month). Do this:

1. Click **Transform data** again (Home ribbon)
2. In the **Queries** panel (left side), click `cohort_matrix`
3. Click the `CohortMonth` column header to select it
4. Hold **Ctrl** and click any other column you want to **keep** as-is — only select `CohortMonth`
5. In the ribbon, click **Transform** tab
6. Click **Unpivot Columns** dropdown → choose **Unpivot Other Columns**
7. Two new columns appear: `Attribute` and `Value`
8. Double-click the `Attribute` column header → rename it to `MonthNumber`
9. Double-click the `Value` column header → rename it to `RetentionRate`
10. Select the `MonthNumber` column → change type to **Whole Number** (Transform → Data Type)
11. Select the `RetentionRate` column → change type to **Decimal Number**
12. Click **Close & Apply**

---

## PART 2 — Create the data relationship (2 min)

1. Click the **Model** icon in the left sidebar (looks like 3 boxes connected by lines)
2. You'll see boxes representing each of your 5 tables
3. Find `customers_rfm` and `clv_predictions`
4. Look for `CustomerID` in both boxes
5. Click and **drag** `CustomerID` from `clv_predictions` onto `CustomerID` in `customers_rfm`
6. A line appears connecting the two tables — this is the relationship
7. Double-click the line to check it says: Many (clv_predictions) → One (customers_rfm)
8. Click **OK**

That's the only relationship needed. The other tables are standalone.

---

## PART 3 — Create DAX Measures (15 min)

**IMPORTANT: Each measure must be created separately, one at a time.**

### How to create a measure:

1. Click the **Data** icon in the left sidebar (looks like a table)
2. In the **Fields** panel (right side), click `customers_rfm` to select it
3. Right-click `customers_rfm` → click **New measure**
4. A formula bar appears at the top with the cursor ready
5. **Delete** what's already there (`Measure =`)
6. **Type or paste exactly one measure** from the list below
7. Press **Enter** or click the checkmark (✓) to confirm
8. The measure appears under `customers_rfm` in the Fields panel with a calculator icon

---

### Measure 1 — Total Revenue

Click `customers_rfm` in Fields → right-click → **New measure** → paste this:

```
Total Revenue = SUM(customers_rfm[Monetary])
```

Press Enter. ✓

---

### Measure 2 — Total Customers

Right-click `customers_rfm` → **New measure** → paste:

```
Total Customers = DISTINCTCOUNT(customers_rfm[CustomerID])
```

Press Enter. ✓

---

### Measure 3 — Average CLV (90 days)

Right-click `customers_rfm` → **New measure** → paste:

```
Avg CLV 90d = AVERAGE(clv_predictions[predicted_clv_90d])
```

Press Enter. ✓

---

### Measure 4 — Revenue Share %

Right-click `customers_rfm` → **New measure** → paste:

```
Revenue Share % =
DIVIDE(
    SUM(customers_rfm[Monetary]),
    CALCULATE(SUM(customers_rfm[Monetary]), ALL(customers_rfm))
) * 100
```

Press Enter. ✓

> **Note:** You can type it on multiple lines in the formula bar — Power BI accepts this.
> Just make sure the whole block is in one measure, not split across multiple.

---

### Measure 5 — Customers in Segment

Right-click `customers_rfm` → **New measure** → paste:

```
Customers in Segment = COUNTROWS(customers_rfm)
```

Press Enter. ✓

---

### Measure 6 — Avg Recency

Right-click `customers_rfm` → **New measure** → paste:

```
Avg Recency = AVERAGE(customers_rfm[Recency])
```

Press Enter. ✓

---

### Measure 7 — At Risk Revenue

Right-click `customers_rfm` → **New measure** → paste:

```
At Risk Revenue =
CALCULATE(
    SUM(customers_rfm[Monetary]),
    customers_rfm[Segment] IN {"At Risk", "At Risk - Low Value"}
)
```

Press Enter. ✓

---

### Measure 8 — Champion Revenue %

Right-click `customers_rfm` → **New measure** → paste:

```
Champion Revenue % =
DIVIDE(
    CALCULATE(
        SUM(customers_rfm[Monetary]),
        customers_rfm[Segment] = "Champions"
    ),
    CALCULATE(SUM(customers_rfm[Monetary]), ALL(customers_rfm))
) * 100
```

Press Enter. ✓

> **Why this is different from the original:** The denominator must use `ALL()` to ignore any
> active filters, otherwise it divides by the already-filtered total and always returns 100%.

---

## PART 4 — Build the Report Pages

Click the **Report** icon in the left sidebar (looks like a bar chart).

You'll see a blank canvas. At the bottom there's a tab called **Page 1**.

---

### PAGE 1: Executive Overview

**Right-click** the "Page 1" tab at the bottom → **Rename** → type `Overview`

#### Add KPI Cards (top row)

Cards show a single number prominently. Add 4 of them:

**Card 1 — Total Revenue:**
1. Click a blank area of the canvas
2. In **Visualizations** panel (right side), click the **Card** icon (looks like `123`)
3. A blank card appears on the canvas
4. In the **Fields** panel (right), find `customers_rfm` → expand it → drag `Total Revenue` into the **Fields** well of the Visualizations panel
5. The card shows the number. Click the paintbrush icon (Format) to:
   - Under **Callout value** → set Decimal places to `0`
   - Under **Category label** → type `Total Revenue (GBP)`

**Card 2 — Total Customers:**
- Repeat the same steps, drag `Total Customers` into a new card

**Card 3 — Champion Revenue %:**
- Repeat, drag `Champion Revenue %` → set Decimal places to `1`

**Card 4 — At Risk Revenue:**
- Repeat, drag `At Risk Revenue`

Resize and arrange the 4 cards in a row across the top by dragging their corners.

---

#### Add a Donut Chart — Revenue by Segment

1. Click a blank area below the cards
2. In **Visualizations**, click the **Donut chart** icon (circle with hole)
3. From **Fields → customers_rfm**:
   - Drag `Segment` → into the **Legend** well
   - Drag `Total Revenue` → into the **Values** well
4. The chart shows slices by segment

**Set segment colours** (so they match the charts in the notebooks):
1. Click the donut chart to select it
2. Click the **paintbrush** (Format) icon in Visualizations
3. Expand **Slices** → click each segment name → set its colour manually:
   - Champions → `#2E86AB`
   - Loyal Customers → `#A23B72`
   - Potential Loyalists → `#F18F01`
   - At Risk → `#E84855`
   - At Risk - Low Value → `#F4A261`
   - Hibernating → `#8D99AE`
   - About to Sleep → `#BFC0C0`

---

#### Add a Bar Chart — Customer Count by Segment

1. Click blank canvas area
2. In **Visualizations**, click the **Clustered bar chart** (horizontal bars)
3. From **Fields → customers_rfm**:
   - Drag `Segment` → into the **Y-axis** well
   - Drag `Customers in Segment` → into the **X-axis** well
4. Click the **...** (more options) on the chart → **Sort axis** → sort by `Customers in Segment`

---

#### Add a Slicer — filter by Segment

1. Click blank canvas
2. In **Visualizations**, click the **Slicer** icon (funnel shape)
3. From **Fields → customers_rfm**, drag `Segment` → into the **Field** well
4. In Format (paintbrush) → **Slicer settings** → **Options** → Style → choose **Tile**
5. Now clicking a tile filters everything else on the page

---

### PAGE 2: Revenue & Forecast

**Right-click** the `+` at the bottom → Add page → rename to `Revenue Forecast`

#### Add a Line Chart — Historical Revenue

1. Click **Visualizations → Line chart**
2. From **Fields → forecast**:
   - Drag `date` → into **X-axis**
   - Drag `revenue` → into **Y-axis**
3. Click the **Filters** pane (funnel icon, right side) → drag `type` into **Filters on this visual** → set to `Historical`
4. This shows only the historical revenue line

#### Add a Line Chart — Forecast with confidence band

1. Add another **Line chart** (or use a **Line and clustered column chart**)
2. From **Fields → forecast**:
   - Drag `date` → X-axis
   - Drag `forecast_mean` → Y-axis (Line values)
   - Drag `lower_80` → Y-axis (additional line)
   - Drag `upper_80` → Y-axis (additional line)
3. Filter `type` to `Forecast`
4. In Format → set `lower_80` and `upper_80` lines to same colour but lighter/dashed

> **Tip:** To get a shaded band between upper and lower, use the **Area chart** visual instead
> and put `upper_80` in Y-axis and `lower_80` in Y-axis (secondary). Then colour the area.

---

### PAGE 3: Segments & CLV

Add page → rename to `Segments & CLV`

#### Add Scatter Plot — Recency vs Frequency

1. Click **Visualizations → Scatter chart**
2. From **Fields → customers_rfm**:
   - Drag `Recency` → into **X-axis**
   - Drag `Frequency` → into **Y-axis**
   - Drag `Segment` → into **Legend**
   - Drag `Monetary` → into **Size**
   - Drag `CustomerID` → into **Details** (this makes one dot per customer)
3. In Format → set the axis titles to "Days Since Last Purchase" and "Number of Orders"

#### Add a Bar Chart — Average CLV by Segment

1. Click **Visualizations → Clustered bar chart**
2. From **Fields**:
   - `clv_predictions[Segment]` → Y-axis
   - `Avg CLV 90d` (your measure) → X-axis
3. Sort by `Avg CLV 90d` descending

#### Add a Table — Top Customers by CLV

1. Click **Visualizations → Table**
2. Drag these fields in order:
   - `customers_rfm[CustomerID]`
   - `customers_rfm[Segment]`
   - `customers_rfm[Recency]`
   - `customers_rfm[Frequency]`
   - `customers_rfm[Monetary]`
   - `clv_predictions[predicted_clv_90d]`
3. In Filters → add `predicted_clv_90d` → set to Top N → Top 20

---

### PAGE 4: Cohort Retention

Add page → rename to `Cohort Retention`

#### Add a Matrix — Cohort Heatmap

1. Click **Visualizations → Matrix**
2. From **Fields → cohort_matrix**:
   - Drag `CohortMonth` → into **Rows**
   - Drag `MonthNumber` → into **Columns**
   - Drag `RetentionRate` → into **Values**
3. In Format (paintbrush):
   - Expand **Cell elements** → turn on **Background color**
   - Click **Advanced controls** → set colour scale:
     - Minimum: `0` → white
     - Maximum: `100` → dark blue (`#2E86AB`)
   - This creates the heatmap effect

#### Add a Line Chart — Average Retention Curve

1. Click **Visualizations → Line chart**
2. From **Fields → cohort_matrix**:
   - Drag `MonthNumber` → X-axis
   - Drag `RetentionRate` → Y-axis (this automatically averages across cohorts)
3. In Format → Y-axis → set range 0 to 100
4. Add a **Constant line** at y = 21.2 (Format → Analytics tab → Constant line → add → value 21.2)

---

## PART 5 — Add Global Filters (Synced across all pages)

1. Go to **View** tab in the top ribbon
2. Click **Sync slicers** (this opens the Sync Slicers panel)
3. Go to page 1 → click the Segment slicer you created
4. In the Sync Slicers panel, check the box for **all 4 pages** in both the "Sync" and "Visible" columns
5. Now the segment slicer on page 1 filters all other pages simultaneously

---

## PART 6 — Final formatting

For each page:
1. Click blank canvas area → right-click → **Page background** → set to white (`#FFFFFF`)
2. Add a **Text box** (Insert tab → Text box) at the top of each page with a one-line title
3. For page titles, use font size 16, bold, colour `#2E86AB`

For the overall file:
1. **File → Save as** → save as `app/online_retail_dashboard.pbix`
2. Take a screenshot of each page (Windows: `Win + Shift + S`)
3. Save screenshots to `app/screenshots/`

---

## Common errors and fixes

| Error message | What it means | Fix |
|---|---|---|
| `The syntax for 'X' is incorrect` | You pasted multiple measures at once | Delete everything in the formula bar, paste **only one** measure, press Enter |
| `A table with the same name already exists` | You loaded the same CSV twice | In Power Query, delete the duplicate table |
| `Column does not exist` | Wrong table selected when creating measure | Make sure you right-clicked on `customers_rfm` before clicking New measure |
| The donut chart shows `(Blank)` as a segment | Some rows have null Segment | Filter out nulls: in Filters pane → Segment → uncheck `(Blank)` |
| Scatter plot has too many dots and crashes | Too many data points | Add a filter: `Monetary > 100` to limit to meaningful customers |
