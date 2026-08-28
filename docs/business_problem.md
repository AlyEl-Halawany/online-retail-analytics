# Business Problem Statement
### Online Retail II — Customer Analytics Initiative
**Prepared by:** Analytics Team  
**Requested by:** Marketing & Customer Retention Leadership  
**Date:** Q3 2024  
**Status:** Approved for analysis

---

## Who Is Asking and Why

The VP of Marketing and the Head of Customer Retention have jointly requested this analysis ahead of the annual budget planning cycle. The company — a UK-based online gift retailer — has seen strong top-line revenue growth over the past two years, but the Marketing team has no systematic view of *which customers are actually driving that growth* and no early-warning system for when high-value customers start to disengage.

Currently, retention campaigns are sent to the entire customer base with no targeting. The Retention team suspects a large share of budget is being spent on customers who were never at risk of leaving (low-value, infrequent buyers) while genuinely high-value customers who are quietly drifting away receive the same generic communication.

The Finance team has additionally flagged that customer acquisition costs have risen year-over-year, making *retention of existing customers* a higher-ROI priority than it has historically been.

---

## The Business Question — In Plain Language

> **"Which customers are our highest-value, which are at risk of churning, and where should we direct our retention budget to get the most return?"**

Three sub-questions that need answering:

1. **Who are we keeping?** — What does the revenue distribution across our customer base actually look like? Is it highly concentrated (Pareto-style) or broadly distributed?
2. **Who should we be worried about?** — Which customers used to buy frequently and have gone quiet? How much revenue is at stake?
3. **Where should we invest next?** — Given our budget constraints, which customer segments offer the best return on retention spend?

---

## Success Metrics — Defined Up Front

The analysis will be considered successful if it delivers:

| Metric | Target |
|---|---|
| Revenue concentration | Identify the customer segment that represents **≥ 60% of total revenue at ≤ 25% of the customer base** — confirming or disconfirming Pareto concentration |
| At-Risk revenue quantification | Estimate the total annual revenue at risk from customers showing disengagement signals |
| Segment clarity | Produce **≤ 7 named segments** with a plain-English description and a specific recommended action for each |
| Forecasting confidence | Produce a next-quarter revenue forecast with a confidence interval narrow enough to be used in budget planning (target: ± 15% of actual) |
| Retention insight | Identify the month-over-month point at which the largest retention drop occurs, so the CRM team can design an intervention at the right moment |

---

## Constraints

**Budget:** No new software licenses — analysis uses open-source tooling throughout. Interactive dashboard built with Plotly Dash (Python).

**Timeline:** Initial findings due within 3 weeks; full interactive dashboard within 5 weeks.

**Data availability:** We have two years of transactional data (Dec 2009 – Dec 2011) covering ~1 million rows across 40+ countries. The data does **not** include:
- Marketing spend or campaign attribution (we cannot directly measure campaign ROI — this is a known limitation)
- Customer demographics beyond country
- Product margin data (all revenue figures are gross, not net)
- Returns/refund resolution status (cancellations are identified by invoice prefix but final resolution is unknown)

**Scope:** This analysis focuses on the UK and international customer base as a whole. Country-level sub-analysis will be produced for the top 5 revenue-generating countries.

---

## How This Anchors the Rest of the Project

Every analytical step in this project traces back to the business question above:

- **RFM Segmentation** → directly answers "who is high-value and who is at risk"
- **CLV Prediction** → quantifies the revenue at stake for each segment, making the "where to invest" decision data-driven
- **Sales Forecasting** → gives Retention and Finance a shared planning baseline for next quarter
- **Cohort Retention** → identifies *when* customers drop off so the CRM team knows the right moment to intervene
- **Recommendations Memo** → translates all findings back into prioritized budget decisions

If any analytical result cannot be connected back to one of these four questions, it will not appear in the final deliverable.
